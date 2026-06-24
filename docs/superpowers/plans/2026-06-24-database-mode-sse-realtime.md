# Database Mode SSE Realtime Updates Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement single-worker, in-process SSE invalidation for `/home/database-mode` so committed backend writes trigger debounced REST resyncs without overwriting local draft edits.

**Architecture:** Add an application-scoped `DatabaseModeEventBus`, move database-mode writes onto explicit transaction boundaries, and publish exactly one post-commit event per business action. Authenticate the SSE stream with a short-lived HS256 cookie signed from the existing `system.jwt.secret`, then consume the stream on the frontend through one `EventSource` hook that coalesces events into guarded `refreshAll()` batches.

**Tech Stack:** Python 3.12, Quart, SQLAlchemy async engine, PyJWT HS256, React 19, React Router 7, Playwright, pnpm, pytest

---

## File Structure

- Create: `src/langbot/pkg/database_mode/events.py`
  Responsibility: in-process event types, subscriber queues, overflow coalescing, SSE serialization, shutdown sentinel.
- Modify: `src/langbot/pkg/persistence/mgr.py`
  Responsibility: expose an explicit async transaction context so service code can publish only after a real commit succeeds.
- Modify: `src/langbot/pkg/core/app.py`
  Responsibility: add `database_mode_event_bus` to the application object and dispose it on shutdown.
- Modify: `src/langbot/pkg/core/stages/build_app.py`
  Responsibility: instantiate the event bus before `DatabaseModeService`.
- Modify: `src/langbot/pkg/database_mode/service.py`
  Responsibility: route writes through transactions, publish one primary event per successful operation, and serialize offset-aware ISO 8601 timestamps for database-mode responses.
- Modify: `src/langbot/pkg/api/http/controller/groups/database_mode.py`
  Responsibility: add SSE session handshake and stream routes, sign/verify the SSE cookie, emit `ready` + heartbeat, ignore `Last-Event-ID`.
- Create: `tests/unit_tests/database_mode/test_event_bus.py`
  Responsibility: cover bus subscribe/publish/unsubscribe, overflow coalescing, and sentinel shutdown.
- Modify: `tests/unit_tests/database_mode/test_database_mode_service.py`
  Responsibility: cover created/updated/deleted/invalidated publish rules and the “no publish on rollback/commit failure” contract.
- Create: `tests/unit_tests/database_mode/test_database_mode_routes.py`
  Responsibility: cover SSE handshake status/cookies/headers plus stream auth, `ready`, heartbeat, and no-replay behavior.
- Modify: `web/src/app/infra/entities/api/index.ts`
  Responsibility: add typed realtime event payloads.
- Modify: `web/src/app/infra/http/BackendClient.ts`
  Responsibility: add the SSE session handshake client method.
- Create: `web/src/app/home/database-mode/hooks/useDatabaseModeEvents.ts`
  Responsibility: own one `EventSource`, handshake/reconnect behavior, and event callbacks.
- Create: `web/src/app/home/database-mode/utils.ts`
  Responsibility: `formatDatabaseModeDateTime()` and `buildDatabaseModeQuerySignature()`.
- Modify: `web/src/app/home/database-mode/page.tsx`
  Responsibility: integrate the SSE hook, requestVersion + querySignature guards, refresh coalescing, draft merge, scroll preservation, toast behavior, and polling split.
- Modify: `web/src/i18n/locales/en-US.ts`
- Modify: `web/src/i18n/locales/zh-Hans.ts`
- Modify: `web/src/i18n/locales/ja-JP.ts`
  Responsibility: add the missing `common.refresh` key if still absent and add `databaseMode.status.processing`.
- Create: `web/tests/e2e/database-mode-realtime.spec.ts`
  Responsibility: mock EventSource + backend responses and verify the realtime UX contract end-to-end.

### Task 1: Add The Event Bus And Transaction Primitive

**Files:**
- Create: `tests/unit_tests/database_mode/test_event_bus.py`
- Create: `src/langbot/pkg/database_mode/events.py`
- Modify: `src/langbot/pkg/persistence/mgr.py`
- Modify: `src/langbot/pkg/core/app.py`
- Modify: `src/langbot/pkg/core/stages/build_app.py`

- [ ] **Step 1: Write the failing EventBus tests**

```python
from __future__ import annotations

import pytest

from langbot.pkg.database_mode.events import (
    DATABASE_MODE_EVENT_SENTINEL,
    DatabaseModeEvent,
    DatabaseModeEventBus,
    DatabaseModeEventType,
)


pytestmark = pytest.mark.asyncio


async def test_two_subscribers_receive_the_same_event():
    bus = DatabaseModeEventBus(queue_maxsize=4)
    first = bus.subscribe()
    second = bus.subscribe()
    event = DatabaseModeEvent(
        type=DatabaseModeEventType.MESSAGE_CREATED,
        conversation_id=1,
        message_id=2,
        occurred_at="2026-06-24T10:00:00+00:00",
    )

    await bus.publish(event)

    assert await first.queue.get() == event
    assert await second.queue.get() == event


async def test_overflow_coalesces_to_single_invalidated_event():
    bus = DatabaseModeEventBus(queue_maxsize=2)
    subscriber = bus.subscribe()

    await bus.publish(DatabaseModeEvent(type=DatabaseModeEventType.MESSAGE_CREATED, conversation_id=1, message_id=1))
    await bus.publish(DatabaseModeEvent(type=DatabaseModeEventType.MESSAGE_UPDATED, conversation_id=1, message_id=1))
    await bus.publish(DatabaseModeEvent(type=DatabaseModeEventType.MESSAGE_DELETED, conversation_id=1, message_id=1))

    drained = [subscriber.queue.get_nowait(), subscriber.queue.get_nowait()]

    assert drained[0].type == DatabaseModeEventType.MESSAGE_CREATED
    assert drained[1].type == DatabaseModeEventType.INVALIDATED


async def test_close_pushes_the_shutdown_sentinel():
    bus = DatabaseModeEventBus(queue_maxsize=1)
    subscriber = bus.subscribe()

    bus.close()

    assert subscriber.queue.get_nowait() is DATABASE_MODE_EVENT_SENTINEL
```

- [ ] **Step 2: Run the new backend test to confirm the missing implementation fails**

Run: `uv run pytest tests/unit_tests/database_mode/test_event_bus.py -q`

Expected: FAIL with `ModuleNotFoundError: No module named 'langbot.pkg.database_mode.events'`

- [ ] **Step 3: Implement the event bus, sentinel, and transaction helper**

```python
# src/langbot/pkg/database_mode/events.py
from __future__ import annotations

import asyncio
import dataclasses
import datetime
import enum
import json
import uuid


DATABASE_MODE_EVENT_SENTINEL = object()


class DatabaseModeEventType(str, enum.Enum):
    MESSAGE_CREATED = "database-message-created"
    MESSAGE_UPDATED = "database-message-updated"
    MESSAGE_DELETED = "database-message-deleted"
    CONVERSATION_UPDATED = "database-conversation-updated"
    INVALIDATED = "database-mode-invalidated"
    READY = "ready"


@dataclasses.dataclass(slots=True)
class DatabaseModeEvent:
    type: DatabaseModeEventType
    conversation_id: int | None = None
    message_id: int | None = None
    occurred_at: str | None = None
    event_id: str = dataclasses.field(default_factory=lambda: str(uuid.uuid4()))


@dataclasses.dataclass(slots=True)
class DatabaseModeSubscriber:
    subscriber_id: str
    queue: asyncio.Queue


class DatabaseModeEventBus:
    def __init__(self, queue_maxsize: int = 100) -> None:
        self._queue_maxsize = queue_maxsize
        self._subscribers: dict[str, DatabaseModeSubscriber] = {}

    def subscribe(self) -> DatabaseModeSubscriber:
        subscriber = DatabaseModeSubscriber(
            subscriber_id=str(uuid.uuid4()),
            queue=asyncio.Queue(maxsize=self._queue_maxsize),
        )
        self._subscribers[subscriber.subscriber_id] = subscriber
        return subscriber

    def unsubscribe(self, subscriber_id: str) -> None:
        self._subscribers.pop(subscriber_id, None)

    async def publish(self, event: DatabaseModeEvent) -> None:
        for subscriber in list(self._subscribers.values()):
            self._publish_to_subscriber(subscriber, event)

    def _publish_to_subscriber(self, subscriber: DatabaseModeSubscriber, event: DatabaseModeEvent) -> None:
        try:
            subscriber.queue.put_nowait(event)
            return
        except asyncio.QueueFull:
            pass

        invalidated = DatabaseModeEvent(
            type=DatabaseModeEventType.INVALIDATED,
            occurred_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        )

        try:
            subscriber.queue.get_nowait()
        except asyncio.QueueEmpty:
            pass

        while True:
            try:
                subscriber.queue.put_nowait(invalidated)
                return
            except asyncio.QueueFull:
                subscriber.queue.get_nowait()

    def close(self) -> None:
        for subscriber in list(self._subscribers.values()):
            try:
                subscriber.queue.put_nowait(DATABASE_MODE_EVENT_SENTINEL)
            except asyncio.QueueFull:
                subscriber.queue.get_nowait()
                subscriber.queue.put_nowait(DATABASE_MODE_EVENT_SENTINEL)
        self._subscribers.clear()


def serialize_sse_event(event: DatabaseModeEvent) -> str:
    return (
        f"event: {event.type.value}\n"
        f"data: {json.dumps(dataclasses.asdict(event), ensure_ascii=True)}\n\n"
    )
```

```python
# src/langbot/pkg/persistence/mgr.py
from contextlib import asynccontextmanager

@asynccontextmanager
async def transaction(self):
    async with self.get_db_engine().begin() as conn:
        yield conn
```

```python
# src/langbot/pkg/core/app.py
from ..database_mode.events import DatabaseModeEventBus

database_mode_event_bus: DatabaseModeEventBus | None = None

def dispose(self):
    if self.database_mode_event_bus is not None:
        self.database_mode_event_bus.close()
```

```python
# src/langbot/pkg/core/stages/build_app.py
from ...database_mode.events import DatabaseModeEventBus

ap.database_mode_event_bus = DatabaseModeEventBus()
database_mode_service_inst = database_mode_service.DatabaseModeService(ap)
ap.database_mode_service = database_mode_service_inst
```

- [ ] **Step 4: Run the EventBus test again**

Run: `uv run pytest tests/unit_tests/database_mode/test_event_bus.py -q`

Expected: PASS with `3 passed`

- [ ] **Step 5: Commit the foundation work**

```bash
git add tests/unit_tests/database_mode/test_event_bus.py src/langbot/pkg/database_mode/events.py src/langbot/pkg/persistence/mgr.py src/langbot/pkg/core/app.py src/langbot/pkg/core/stages/build_app.py
git commit -m "feat(database_mode): add realtime event bus foundation"
```

### Task 2: Publish Exactly One Event After A Successful Commit

**Files:**
- Modify: `tests/unit_tests/database_mode/test_database_mode_service.py`
- Modify: `src/langbot/pkg/database_mode/service.py`

- [ ] **Step 1: Write the failing service publish-contract tests**

```python
class RecordingEventBus:
    def __init__(self) -> None:
        self.events = []

    async def publish(self, event) -> None:
        self.events.append(event)


async def test_generate_draft_publishes_updated_once_after_commit():
    service, ap = await _create_service()
    try:
        await service.ingest_internal_event(_sample_payload())
        conversations = await service.list_conversations()
        message_id = (await service.list_messages(conversations["conversations"][0]["id"]))["messages"][0]["id"]
        provider = SimpleNamespace(
            invoke_llm=AsyncMock(return_value=SimpleNamespace(content="Draft reply"))
        )
        ap.model_mgr.llm_models = [SimpleNamespace(provider=provider)]

        await service.generate_draft(message_id)

        assert [event.type.value for event in ap.database_mode_event_bus.events] == ["database-message-updated"]
    finally:
        await ap.persistence_mgr.dispose()


async def test_batch_delete_publishes_invalidated_once():
    service, ap = await _create_service()
    try:
        first = _sample_payload()
        second = _sample_payload()
        second["event_id"] = "wxwork-local:evt-2"
        second["message_key"] = "wxwork:key-2"
        second["message"]["external_message_id"] = "102"
        await service.ingest_internal_event(first)
        await service.ingest_internal_event(second)
        conversations = await service.list_conversations()
        message_ids = [item["id"] for item in (await service.list_messages(conversations["conversations"][0]["id"]))["messages"]]

        await service.batch_delete(message_ids)

        assert [event.type.value for event in ap.database_mode_event_bus.events[-1:]] == ["database-mode-invalidated"]
    finally:
        await ap.persistence_mgr.dispose()


async def test_commit_failure_does_not_publish():
    service, ap = await _create_service(fail_commit=True)
    try:
        with pytest.raises(RuntimeError, match="commit failed"):
            await service.ingest_internal_event(_sample_payload())

        assert ap.database_mode_event_bus.events == []
    finally:
        await ap.persistence_mgr.dispose()
```

- [ ] **Step 2: Run the service test file and capture the failing publish assertions**

Run: `uv run pytest tests/unit_tests/database_mode/test_database_mode_service.py -q`

Expected: FAIL because no events are published and `_create_service()` does not yet provide a transaction-aware persistence manager.

- [ ] **Step 3: Upgrade the test harness to support transactions and commit-failure injection**

```python
class MiniPersistenceManager:
    def __init__(self, *, fail_commit: bool = False) -> None:
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        self.fail_commit = fail_commit

    @asynccontextmanager
    async def transaction(self):
        async with self.engine.connect() as conn:
            trans = await conn.begin()
            try:
                yield conn
                if self.fail_commit:
                    raise RuntimeError("commit failed")
                await trans.commit()
            except Exception:
                await trans.rollback()
                raise


async def _create_service(*, fail_commit: bool = False):
    persistence_mgr = MiniPersistenceManager(fail_commit=fail_commit)
    await persistence_mgr.initialize()
    ap = SimpleNamespace(
        persistence_mgr=persistence_mgr,
        model_mgr=SimpleNamespace(llm_models=[]),
        database_mode_event_bus=RecordingEventBus(),
    )
    return DatabaseModeService(ap), ap
```

- [ ] **Step 4: Route every database-mode write through one transaction and publish after commit**

```python
from .events import DatabaseModeEvent, DatabaseModeEventType

async def _publish_after_commit(self, events: list[DatabaseModeEvent]) -> None:
    bus = getattr(self.ap, "database_mode_event_bus", None)
    if bus is None:
        return
    for event in events:
        await bus.publish(event)

def _make_event(self, event_type: DatabaseModeEventType, *, conversation_id: int | None, message_id: int | None):
    return DatabaseModeEvent(
        type=event_type,
        conversation_id=conversation_id,
        message_id=message_id,
        occurred_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
    )

async def ingest_internal_event(self, payload: dict) -> EventIngestResult:
    published_events: list[DatabaseModeEvent] = []
    async with self.ap.persistence_mgr.transaction() as conn:
        existing_event = await self._fetch_optional_model(
            persistence_database_mode.LocalConnectorEvent,
            sqlalchemy.select(persistence_database_mode.LocalConnectorEvent).where(
                persistence_database_mode.LocalConnectorEvent.event_id == event_id
            ),
            conn=conn,
        )
        if existing_event is not None:
            return EventIngestResult(accepted=True, duplicate=True, event_id=event_id)

        existing_message = await self._fetch_optional_model(
            persistence_database_mode.DatabaseMessage,
            sqlalchemy.select(persistence_database_mode.DatabaseMessage).where(
                persistence_database_mode.DatabaseMessage.message_key == message_key
            ),
            conn=conn,
        )
        if existing_message is not None:
            await conn.execute(
                sqlalchemy.insert(persistence_database_mode.LocalConnectorEvent).values(
                    {
                        "event_id": event_id,
                        "connector_id": connector_id,
                        "message_key": message_key,
                        "status": MESSAGE_STATUS_PROCESSED,
                        "received_at": observed_at,
                        "processed_at": datetime.datetime.utcnow(),
                    }
                )
            )
            return EventIngestResult(accepted=True, duplicate=True, event_id=event_id)

        await conn.execute(
            sqlalchemy.insert(persistence_database_mode.LocalConnectorEvent).values(
                {
                    "event_id": event_id,
                    "connector_id": connector_id,
                    "message_key": message_key,
                    "status": MESSAGE_STATUS_PROCESSING,
                    "received_at": observed_at,
                }
            )
        )
        conversation = await self._get_or_create_conversation(
            connector_id=connector_id,
            source=source,
            external_conversation_id=external_conversation_id,
            conversation_name=conversation_name,
            conversation_type=conversation_type,
            last_message_at=sent_at,
            conn=conn,
        )
        await conn.execute(
            sqlalchemy.insert(persistence_database_mode.DatabaseMessage).values(
                {
                    "event_id": event_id,
                    "message_key": message_key,
                    "conversation_id": conversation["id"],
                    "external_message_id": external_message_id,
                    "sender_id": sender_id,
                    "sender_name": sender_name,
                    "content": content,
                    "message_type": message_type,
                    "sent_at": sent_at,
                    "observed_at": observed_at,
                    "status": MESSAGE_STATUS_PENDING,
                    "draft_text": None,
                    "draft_source": None,
                    "attempt_count": 0,
                    "last_error": None,
                }
            )
        )
        stored_message = await self._fetch_required_model(
            persistence_database_mode.DatabaseMessage,
            sqlalchemy.select(persistence_database_mode.DatabaseMessage).where(
                persistence_database_mode.DatabaseMessage.message_key == message_key
            ),
            conn=conn,
            error_message="Message not found after insert",
        )
        await conn.execute(
            sqlalchemy.update(persistence_database_mode.LocalConnectorEvent)
            .where(persistence_database_mode.LocalConnectorEvent.event_id == event_id)
            .values(
                {
                    "status": MESSAGE_STATUS_PROCESSED,
                    "processed_at": datetime.datetime.utcnow(),
                    "last_error": None,
                }
            )
        )
        published_events.append(
            self._make_event(
                DatabaseModeEventType.MESSAGE_CREATED,
                conversation_id=int(conversation["id"]),
                message_id=int(stored_message.id),
            )
        )
    await self._publish_after_commit(published_events)
    return EventIngestResult(accepted=True, duplicate=False, event_id=event_id)

async def update_draft(self, message_id: int, draft_text: str, draft_source: str | None = None) -> dict:
    async with self.ap.persistence_mgr.transaction() as conn:
        await self._require_message(message_id, conn=conn)
        await conn.execute(
            sqlalchemy.update(persistence_database_mode.DatabaseMessage)
            .where(persistence_database_mode.DatabaseMessage.id == message_id)
            .values(
                {
                    "status": MESSAGE_STATUS_DRAFT_READY,
                    "draft_text": draft_text,
                    "draft_source": draft_source or "manual",
                    "last_error": None,
                    "updated_at": datetime.datetime.utcnow(),
                }
            )
        )
    message = await self.get_message(message_id)
    await self._publish_after_commit(
        [self._make_event(DatabaseModeEventType.MESSAGE_UPDATED, conversation_id=message["conversation_id"], message_id=message_id)]
    )
    return message
```

```python
def _serialize_model(self, model, instance) -> dict:
    data = {}
    for column in model.__table__.columns:
        value = getattr(instance, column.name)
        if isinstance(value, datetime.datetime):
            if value.tzinfo is None:
                value = value.replace(tzinfo=datetime.timezone.utc)
            data[column.name] = value.isoformat()
        else:
            data[column.name] = value
    return data
```

Implementation rules in this step:

- new ingest publishes only `database-message-created`
- `generate_draft`, `update_draft`, `process_message`, and `skip_message` publish only `database-message-updated`
- `delete_message` publishes only `database-message-deleted`
- `batch_process`, `batch_skip`, and `batch_delete` publish only `database-mode-invalidated`
- commit errors and rollbacks publish nothing

- [ ] **Step 5: Run the service tests again**

Run: `uv run pytest tests/unit_tests/database_mode/test_database_mode_service.py -q`

Expected: PASS with the publish-contract tests succeeding, including the commit-failure case.

- [ ] **Step 6: Commit the service integration**

```bash
git add tests/unit_tests/database_mode/test_database_mode_service.py src/langbot/pkg/database_mode/service.py
git commit -m "feat(database_mode): publish events after commit"
```

### Task 3: Add The SSE Handshake And Stream Routes

**Files:**
- Create: `tests/unit_tests/database_mode/test_database_mode_routes.py`
- Modify: `src/langbot/pkg/api/http/controller/groups/database_mode.py`

- [ ] **Step 1: Write the failing route tests for the cookie handshake and stream**

```python
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import quart

from langbot.pkg.api.http.controller.groups.database_mode import DatabaseModeRouterGroup
from langbot.pkg.database_mode.events import DatabaseModeEventBus


pytestmark = pytest.mark.asyncio


async def _make_client():
    app = quart.Quart(__name__)
    ap = SimpleNamespace(
        user_service=SimpleNamespace(
            verify_jwt_token=AsyncMock(return_value="user@example.com"),
            get_user_by_email=AsyncMock(return_value=SimpleNamespace(email="user@example.com")),
        ),
        instance_config=SimpleNamespace(data={"system": {"jwt": {"secret": "test-secret", "expire": 3600}}, "api": {"port": 5300}}),
        database_mode_event_bus=DatabaseModeEventBus(queue_maxsize=4),
        database_mode_service=SimpleNamespace(),
    )
    router = DatabaseModeRouterGroup(ap, app)
    await router.initialize()
    return app.test_client(), ap


async def test_session_handshake_returns_204_and_sets_cookie():
    client, _ap = await _make_client()

    response = await client.post("/api/v1/database-mode/events/session", headers={"Authorization": "Bearer token"})

    assert response.status_code == 204
    assert response.headers["Cache-Control"] == "no-store"
    assert "langbot_dbmode_sse=" in response.headers["Set-Cookie"]


async def test_stream_rejects_missing_cookie():
    client, _ap = await _make_client()

    response = await client.get("/api/v1/database-mode/events")

    assert response.status_code == 401


async def test_stream_ignores_last_event_id_and_emits_ready():
    client, ap = await _make_client()
    await client.post("/api/v1/database-mode/events/session", headers={"Authorization": "Bearer token"})

    cookie = client.cookie_jar._cookies["localhost.local"]["/api/v1/database-mode/events"]["langbot_dbmode_sse"].value
    response = await client.get(
        "/api/v1/database-mode/events",
        headers={"Last-Event-ID": "old-event-id", "Cookie": f"langbot_dbmode_sse={cookie}"},
    )
    body = (await response.get_data()).decode()

    assert response.status_code == 200
    assert response.headers["Content-Type"].startswith("text/event-stream")
    assert response.headers["Cache-Control"] == "no-store"
    assert "event: ready" in body
```

- [ ] **Step 2: Run the route tests to confirm the new endpoints are missing**

Run: `uv run pytest tests/unit_tests/database_mode/test_database_mode_routes.py -q`

Expected: FAIL with `404` responses for `/events/session` and `/events`

- [ ] **Step 3: Implement the signed cookie handshake and SSE stream**

```python
COOKIE_NAME = "langbot_dbmode_sse"
COOKIE_PURPOSE = "database-mode-sse"
COOKIE_VERSION = 1

def _encode_sse_cookie(self, user_email: str, session_id: str) -> str:
    now = datetime.datetime.now(datetime.timezone.utc)
    payload = {
        "sub": user_email,
        "version": COOKIE_VERSION,
        "purpose": COOKIE_PURPOSE,
        "issued_at": int(now.timestamp()),
        "expires_at": int((now + datetime.timedelta(minutes=5)).timestamp()),
        "session_id": session_id,
    }
    secret = self.ap.instance_config.data["system"]["jwt"]["secret"]
    return jwt.encode(payload, secret, algorithm="HS256")

def _decode_sse_cookie(self, raw_cookie: str | None) -> dict:
    if not raw_cookie:
        raise ValueError("Missing SSE session cookie")
    secret = self.ap.instance_config.data["system"]["jwt"]["secret"]
    payload = jwt.decode(raw_cookie, secret, algorithms=["HS256"])
    if payload.get("purpose") != COOKIE_PURPOSE:
        raise ValueError("Invalid SSE cookie purpose")
    return payload

@self.route("/events/session", methods=["POST"], auth_type=group.AuthType.USER_TOKEN)
async def create_events_session(user_email: str) -> quart.Response:
    token = self._encode_sse_cookie(user_email=user_email, session_id=str(uuid.uuid4()))
    response = quart.Response(status=204)
    response.headers["Cache-Control"] = "no-store"
    response.set_cookie(
        COOKIE_NAME,
        token,
        httponly=True,
        samesite="Strict",
        secure=quart.request.scheme == "https",
        path="/api/v1/database-mode/events",
        max_age=300,
    )
    return response

@self.route("/events", methods=["GET"], auth_type=group.AuthType.NONE)
async def stream_events() -> quart.Response:
    self._decode_sse_cookie(quart.request.cookies.get(COOKIE_NAME))
    subscriber = self.ap.database_mode_event_bus.subscribe()

    async def event_stream():
        try:
            yield "retry: 3000\n\n"
            yield 'event: ready\ndata: {"type":"ready"}\n\n'
            while True:
                try:
                    item = await asyncio.wait_for(subscriber.queue.get(), timeout=20)
                except asyncio.TimeoutError:
                    yield ": heartbeat\n\n"
                    continue
                if item is DATABASE_MODE_EVENT_SENTINEL:
                    break
                yield serialize_sse_event(item)
        finally:
            self.ap.database_mode_event_bus.unsubscribe(subscriber.subscriber_id)

    response = quart.Response(event_stream(), content_type="text/event-stream")
    response.headers["Cache-Control"] = "no-store"
    response.headers["Connection"] = "keep-alive"
    response.headers["X-Accel-Buffering"] = "no"
    response.headers["Content-Encoding"] = "identity"
    return response
```

Implementation rules in this step:

- do not set a `Domain` attribute on the cookie
- do not accept query tokens or connector tokens on the stream route
- ignore `Last-Event-ID`
- keep replay unsupported
- reuse `system.jwt.secret`; do not hardcode a new secret

- [ ] **Step 4: Re-run the route tests**

Run: `uv run pytest tests/unit_tests/database_mode/test_database_mode_routes.py -q`

Expected: PASS with handshake, cookie, header, and `ready` assertions succeeding.

- [ ] **Step 5: Commit the SSE API work**

```bash
git add tests/unit_tests/database_mode/test_database_mode_routes.py src/langbot/pkg/api/http/controller/groups/database_mode.py
git commit -m "feat(database_mode): add authenticated sse routes"
```

### Task 4: Add The Frontend Realtime Test Harness

**Files:**
- Create: `web/tests/e2e/database-mode-realtime.spec.ts`

- [ ] **Step 1: Write the failing Playwright spec that models the realtime contract**

```typescript
import { expect, test } from '@playwright/test';

import { installLangBotApiMocks } from './fixtures/langbot-api';

test('database mode refreshes after SSE ready and coalesces invalidation', async ({ page }) => {
  await installLangBotApiMocks(page, { authenticated: true });

  await page.addInitScript(() => {
    class FakeEventSource {
      static instances: FakeEventSource[] = [];
      url: string;
      onopen: ((event: Event) => void) | null = null;
      onerror: ((event: Event) => void) | null = null;
      listeners = new Map<string, Array<(event: MessageEvent) => void>>();

      constructor(url: string) {
        this.url = url;
        FakeEventSource.instances.push(this);
        (window as any).__fakeEventSourceInstances = FakeEventSource.instances;
      }

      addEventListener(type: string, listener: (event: MessageEvent) => void) {
        const next = this.listeners.get(type) ?? [];
        next.push(listener);
        this.listeners.set(type, next);
      }

      close() {}

      emit(type: string, data: unknown) {
        for (const listener of this.listeners.get(type) ?? []) {
          listener(new MessageEvent(type, { data: JSON.stringify(data) }));
        }
      }
    }

    (window as any).EventSource = FakeEventSource as any;
  });

  let handshakeCount = 0;
  let conversationsCount = 0;

  await page.route('**/api/v1/local-connectors/wxwork-local/status', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        code: 0,
        msg: 'ok',
        data: {
          connector: {
            connector_id: 'wxwork-local',
            name: 'WeCom Local Connector',
            managed_by: 'builtin',
            expected_tool_count: 5,
            status: 'running',
            tool_count: 5,
            updated_at: Date.now(),
            worker: { owned: true, port: 5681, started_at: null },
            monitor: {
              enabled: true,
              owned: true,
              running_status: 'running',
              warmup_completed: true,
              outbox_pending: 0,
            },
          },
        },
      }),
    });
  });

  await page.route('**/api/v1/database-mode/events/session', async (route) => {
    handshakeCount += 1;
    await route.fulfill({ status: 204, headers: { 'Cache-Control': 'no-store', 'Set-Cookie': 'langbot_dbmode_sse=test; Path=/api/v1/database-mode/events; HttpOnly; SameSite=Strict' } });
  });

  await page.route('**/api/v1/database-mode/conversations**', async (route) => {
    conversationsCount += 1;
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        code: 0,
        msg: 'ok',
        data: {
          conversations: [
            {
              id: 1,
              source: 'wxwork',
              conversation_name: 'Customer A',
              conversation_type: 'direct',
              last_message_at: '2026-06-24T10:00:00+00:00',
              pending_count: 1,
              failed_count: 0,
              latest_customer: 'Customer A',
              latest_message_summary: 'Need pricing details',
            },
          ],
          total: 1,
          page: 1,
          page_size: 100,
        },
      }),
    });
  });

  await page.route('**/api/v1/database-mode/conversations/1', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        code: 0,
        msg: 'ok',
        data: {
          conversation: {
            id: 1,
            connector_id: 'wxwork-local',
            source: 'wxwork',
            external_conversation_id: 'S:100_200',
            conversation_name: 'Customer A',
            conversation_type: 'direct',
            last_message_at: '2026-06-24T10:00:00+00:00',
            stats: { pending: 1, processing: 0, draft_ready: 0, failed: 0, processed: 0, skipped: 0, total: 1 },
            latest_customer: 'Customer A',
          },
        },
      }),
    });
  });

  await page.route('**/api/v1/database-mode/conversations/1/messages**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        code: 0,
        msg: 'ok',
        data: {
          messages: [
            {
              id: 7,
              event_id: 'evt-1',
              message_key: 'wxwork:key-1',
              conversation_id: 1,
              sender_id: '200',
              sender_name: 'Customer A',
              content: 'Need pricing details',
              content_preview: 'Need pricing details',
              message_type: 'text',
              sent_at: '2026-06-24T10:00:00+00:00',
              observed_at: '2026-06-24T10:00:02+00:00',
              status: 'pending',
              attempt_count: 0,
            },
          ],
          total: 1,
          page: 1,
          page_size: 200,
          stats: { pending: 1, processing: 0, draft_ready: 0, failed: 0, processed: 0, skipped: 0, total: 1 },
        },
      }),
    });
  });

  await page.goto('/home/database-mode');

  await expect(page.getByRole('heading', { name: 'Database Mode' })).toBeVisible();
  await expect.poll(() => handshakeCount).toBe(1);

  await page.evaluate(() => {
    const source = (window as any).__fakeEventSourceInstances[0];
    source.onopen?.(new Event('open'));
    source.emit('ready', { type: 'ready' });
    source.emit('database-mode-invalidated', { type: 'database-mode-invalidated' });
  });

  await expect.poll(() => conversationsCount).toBeGreaterThan(1);
});
```

- [ ] **Step 2: Run the Playwright spec to confirm it fails before the frontend implementation exists**

Run: `pnpm --dir web exec playwright test tests/e2e/database-mode-realtime.spec.ts --project=chromium`

Expected: FAIL because the page does not handshake, does not create an `EventSource`, and does not auto-refresh after `ready`.

- [ ] **Step 3: Commit the failing browser contract**

```bash
git add web/tests/e2e/database-mode-realtime.spec.ts
git commit -m "test(database_mode): add failing realtime browser contract"
```

### Task 5: Implement The Frontend SSE Hook And Refresh Orchestration

**Files:**
- Modify: `web/src/app/infra/entities/api/index.ts`
- Modify: `web/src/app/infra/http/BackendClient.ts`
- Create: `web/src/app/home/database-mode/hooks/useDatabaseModeEvents.ts`
- Create: `web/src/app/home/database-mode/utils.ts`
- Modify: `web/src/app/home/database-mode/page.tsx`
- Modify: `web/src/i18n/locales/en-US.ts`
- Modify: `web/src/i18n/locales/zh-Hans.ts`
- Modify: `web/src/i18n/locales/ja-JP.ts`

- [ ] **Step 1: Add typed realtime payloads and the handshake client method**

```typescript
// web/src/app/infra/entities/api/index.ts
export type DatabaseModeRealtimeEventType =
  | 'database-message-created'
  | 'database-message-updated'
  | 'database-message-deleted'
  | 'database-conversation-updated'
  | 'database-mode-invalidated'
  | 'ready';

export interface DatabaseModeRealtimeEvent {
  type: DatabaseModeRealtimeEventType;
  event_id?: string;
  conversation_id?: number | null;
  message_id?: number | null;
  occurred_at?: string | null;
}
```

```typescript
// web/src/app/infra/http/BackendClient.ts
public createDatabaseModeEventSession(): Promise<void> {
  return this.request({
    method: 'post',
    url: '/api/v1/database-mode/events/session',
  });
}
```

- [ ] **Step 2: Add the hook and utility helpers**

```typescript
// web/src/app/home/database-mode/utils.ts
export function formatDatabaseModeDateTime(raw?: string | null): string {
  if (!raw) return '--';
  const date = new Date(raw);
  if (Number.isNaN(date.getTime())) return '--';
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  const hours = String(date.getHours()).padStart(2, '0');
  const minutes = String(date.getMinutes()).padStart(2, '0');
  const seconds = String(date.getSeconds()).padStart(2, '0');
  return `${year}-${month}-${day} ${hours}:${minutes}:${seconds}`;
}

export function buildDatabaseModeQuerySignature(input: {
  selectedConversationId: number | null;
  conversationStatus: string;
  messageStatus: string;
  keyword: string;
  conversationPage: number;
  conversationPageSize: number;
  messagePage: number;
  messagePageSize: number;
}): string {
  return JSON.stringify(input);
}
```

```typescript
// web/src/app/home/database-mode/hooks/useDatabaseModeEvents.ts
import { useEffect, useRef, useState, useEffectEvent } from 'react';
import { httpClient } from '@/app/infra/http/HttpClient';
import type { DatabaseModeRealtimeEvent, DatabaseModeRealtimeEventType } from '@/app/infra/entities/api';

export function useDatabaseModeEvents({
  enabled,
  onConnectRefresh,
  onEvent,
}: {
  enabled: boolean;
  onConnectRefresh: () => void;
  onEvent: (event: DatabaseModeRealtimeEvent) => void;
}) {
  const sourceRef = useRef<EventSource | null>(null);
  const retryTimerRef = useRef<number | null>(null);
  const retryCountRef = useRef(0);
  const [connectionState, setConnectionState] = useState<'connecting' | 'connected' | 'disconnected'>('connecting');

  const cleanup = useEffectEvent(() => {
    if (retryTimerRef.current != null) window.clearTimeout(retryTimerRef.current);
    retryTimerRef.current = null;
    sourceRef.current?.close();
    sourceRef.current = null;
  });

  const scheduleReconnect = useEffectEvent(() => {
    cleanup();
    setConnectionState('disconnected');
    const delay = Math.min(30_000, 1_000 * 2 ** retryCountRef.current);
    retryTimerRef.current = window.setTimeout(() => {
      retryCountRef.current += 1;
      void connect();
    }, delay);
  });

  const connect = useEffectEvent(async () => {
    if (!enabled) return;
    setConnectionState('connecting');
    await httpClient.createDatabaseModeEventSession();
    const source = new EventSource('/api/v1/database-mode/events');
    sourceRef.current = source;
    source.onopen = () => {
      retryCountRef.current = 0;
      setConnectionState('connected');
      onConnectRefresh();
    };
    source.onerror = () => scheduleReconnect();
    for (const type of ['ready', 'database-message-created', 'database-message-updated', 'database-message-deleted', 'database-conversation-updated', 'database-mode-invalidated'] as DatabaseModeRealtimeEventType[]) {
      source.addEventListener(type, (event) => {
        const payload = JSON.parse((event as MessageEvent).data) as DatabaseModeRealtimeEvent;
        if (type === 'ready') onConnectRefresh();
        onEvent(payload);
      });
    }
  });

  useEffect(() => {
    if (!enabled) {
      cleanup();
      return;
    }
    void connect();
    return cleanup;
  }, [enabled, cleanup, connect]);

  return { connectionState };
}
```

- [ ] **Step 3: Integrate guarded refresh batching into `page.tsx`**

```typescript
const conversationPage = 1;
const conversationPageSize = 100;
const messagePage = 1;
const messagePageSize = 200;
const requestVersionRef = useRef(0);
const refreshTimerRef = useRef<number | null>(null);
const inFlightRef = useRef(false);
const rerunRef = useRef(false);
const pendingIntentsRef = useRef(new Set<'conversations' | 'messages' | 'conversation' | 'all'>());

const getQuerySignature = useEffectEvent(() =>
  buildDatabaseModeQuerySignature({
    selectedConversationId,
    conversationStatus,
    messageStatus,
    keyword,
    conversationPage,
    conversationPageSize,
    messagePage,
    messagePageSize,
  }),
);

const applyIfCurrent = useEffectEvent(
  (
    requestVersion: number,
    querySignature: string,
    apply: () => void,
  ) => {
    if (
      requestVersion !== requestVersionRef.current ||
      querySignature !== getQuerySignature()
    ) {
      return;
    }
    startTransition(apply);
  },
);

const refreshAll = useEffectEvent(async () => {
  const requestVersion = ++requestVersionRef.current;
  const querySignature = getQuerySignature();
  const [connectorResp, conversationsResp] = await Promise.all([
    httpClient.getLocalConnectorStatus('wxwork-local'),
    httpClient.getDatabaseModeConversations({
      keyword,
      status: conversationStatus,
      page: conversationPage,
      page_size: conversationPageSize,
    }),
  ]);
  applyIfCurrent(requestVersion, querySignature, () => {
    setConnector(connectorResp.connector);
    setConversations(conversationsResp.conversations);
  });
  if (selectedConversationId != null) {
    const [conversationResp, messagesResp] = await Promise.all([
      httpClient.getDatabaseModeConversation(selectedConversationId),
      httpClient.getDatabaseModeMessages(selectedConversationId, {
        status: messageStatus,
        page: messagePage,
        page_size: messagePageSize,
      }),
    ]);
    applyIfCurrent(requestVersion, querySignature, () => {
      setSelectedConversation(conversationResp.conversation);
      setStats(messagesResp.stats);
      setMessages((current) =>
        messagesResp.messages.map((serverMessage) => {
          const dirtyDraft = draftEdits[serverMessage.id];
          return dirtyDraft == null
            ? serverMessage
            : { ...serverMessage, draft_text: dirtyDraft, ai_suggested_reply: dirtyDraft };
        }),
      );
    });
  }
});

const scheduleRefresh = useEffectEvent((intent: 'conversations' | 'messages' | 'conversation' | 'all') => {
  pendingIntentsRef.current.add(intent);
  if (inFlightRef.current) {
    rerunRef.current = true;
    return;
  }
  window.clearTimeout(refreshTimerRef.current);
  refreshTimerRef.current = window.setTimeout(async () => {
    inFlightRef.current = true;
    const intents = new Set(pendingIntentsRef.current);
    pendingIntentsRef.current.clear();
    try {
      if (intents.has('all')) {
        await refreshAll();
      } else {
        await refreshAll();
      }
    } finally {
      inFlightRef.current = false;
      if (rerunRef.current) {
        rerunRef.current = false;
        scheduleRefresh('all');
      }
    }
  }, 200);
});
```

Realtime wiring rules in this step:

- `ready` and every successful reconnect call `refreshAll()`
- `database-message-created`, `database-message-updated`, and `database-message-deleted` map to their minimal refresh intents
- `database-mode-invalidated` always maps to `refreshAll()`
- `database-conversation-updated` only refreshes conversation metadata
- when SSE is connected, stop only database-mode business polling; keep connector monitor polling
- when disconnected, restart 15-second business polling only while the page is visible

- [ ] **Step 4: Finish the page polish, formatter usage, and i18n**

```typescript
const CONVERSATION_STATUS_OPTIONS = ['all', 'pending', 'processing', 'draft_ready', 'failed', 'processed', 'skipped'] as const;
const MESSAGE_STATUS_OPTIONS = ['all', 'pending', 'processing', 'draft_ready', 'failed', 'processed', 'skipped'] as const;

function statusTone(status: string): string {
  switch (status) {
    case 'pending':
      return 'border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-900/70 dark:bg-amber-950/40 dark:text-amber-300';
    case 'processing':
      return 'border-violet-200 bg-violet-50 text-violet-700 dark:border-violet-900/70 dark:bg-violet-950/40 dark:text-violet-300';
    case 'draft_ready':
      return 'border-sky-200 bg-sky-50 text-sky-700 dark:border-sky-900/70 dark:bg-sky-950/40 dark:text-sky-300';
    case 'failed':
      return 'border-red-200 bg-red-50 text-red-700 dark:border-red-900/70 dark:bg-red-950/40 dark:text-red-300';
    case 'processed':
      return 'border-green-200 bg-green-50 text-green-700 dark:border-green-900/70 dark:bg-green-950/40 dark:text-green-300';
    case 'skipped':
      return 'border-muted-foreground/30 bg-muted text-muted-foreground';
    default:
      return 'border-muted-foreground/20 bg-muted text-muted-foreground';
  }
}

<Button variant="outline" onClick={() => refreshAll().catch(() => undefined)}>
  <RefreshCcw className="mr-2 size-4" />
  {t('common.refresh')}
</Button>

<span>{formatDatabaseModeDateTime(conversation.last_message_at)}</span>
<p className="mt-1 text-xs text-muted-foreground">
  {selectedConversation.conversation_name} | {formatDatabaseModeDateTime(message.sent_at)}
</p>
<p>{formatDatabaseModeDateTime(detailsMessage.observed_at)}</p>
```

```typescript
// locales
common: {
  refresh: 'Refresh',
}
databaseMode: {
  status: {
    processing: 'Processing',
  },
  statusProcessing: 'Processing',
}
```

- [ ] **Step 5: Run the realtime Playwright spec again**

Run: `pnpm --dir web exec playwright test tests/e2e/database-mode-realtime.spec.ts --project=chromium`

Expected: PASS with one EventSource instance, a session handshake before connect, and automatic refresh after `ready` / invalidation.

- [ ] **Step 6: Commit the frontend realtime implementation**

```bash
git add web/src/app/infra/entities/api/index.ts web/src/app/infra/http/BackendClient.ts web/src/app/home/database-mode/hooks/useDatabaseModeEvents.ts web/src/app/home/database-mode/utils.ts web/src/app/home/database-mode/page.tsx web/src/i18n/locales/en-US.ts web/src/i18n/locales/zh-Hans.ts web/src/i18n/locales/ja-JP.ts
git commit -m "feat(database_mode): add realtime frontend refresh flow"
```

### Task 6: Run The Focused Verification Suite

**Files:**
- Modify: `web/tests/e2e/database-mode-realtime.spec.ts` only if the first pass exposes a missing assertion

- [ ] **Step 1: Run the focused backend suite**

Run: `uv run pytest tests/unit_tests/database_mode/test_event_bus.py tests/unit_tests/database_mode/test_database_mode_service.py tests/unit_tests/database_mode/test_database_mode_routes.py -q`

Expected: PASS with all realtime backend tests green.

- [ ] **Step 2: Run the focused frontend suite**

Run: `pnpm --dir web exec playwright test tests/e2e/database-mode-realtime.spec.ts tests/e2e/home-smoke.spec.ts --project=chromium`

Expected: PASS with the dedicated realtime spec and the existing `/home/database-mode` smoke coverage both green.

- [ ] **Step 3: Run a backend syntax/lint sanity check only on touched Python files**

Run: `uv run python -m py_compile src/langbot/pkg/database_mode/events.py src/langbot/pkg/database_mode/service.py src/langbot/pkg/api/http/controller/groups/database_mode.py src/langbot/pkg/persistence/mgr.py`

Expected: no output

- [ ] **Step 4: Commit any final test-only adjustments**

```bash
git add tests/unit_tests/database_mode/test_event_bus.py tests/unit_tests/database_mode/test_database_mode_service.py tests/unit_tests/database_mode/test_database_mode_routes.py web/tests/e2e/database-mode-realtime.spec.ts
git commit -m "test(database_mode): cover realtime sse contracts"
```

- [ ] **Step 5: Record the manual verification checklist without claiming it passed**

```text
Manual follow-up required:
1. Open /home/database-mode against a real wxwork-local monitor.
2. Send a new WeCom message from another account.
3. Confirm the page refreshes without clicking Refresh.
4. Confirm draft text remains intact during background refresh.
5. Confirm disconnect -> reconnect triggers refreshAll() and business polling stops again.
```

## Self-Review

**1. Spec coverage:** The plan covers the single-worker scope, post-commit publish-only behavior, overflow-to-invalidated coalescing, one-primary-event-per-action, signed SSE cookie claims, 204 + `no-store` handshake, no replay / no `Last-Event-ID`, offset-aware ISO timestamps, `processing` translations, sentinel shutdown, disabled compression header, `requestVersion + querySignature`, and the “stop only business polling, keep connector polling” frontend rule.

**2. Placeholder scan:** No `TODO`, `TBD`, “appropriate handling”, or “similar to above” placeholders remain. Every task includes exact files, concrete code blocks, commands, and expected outcomes.

**3. Type consistency:** The same names are used throughout the plan: `DatabaseModeEventBus`, `DatabaseModeEventType`, `DatabaseModeRealtimeEvent`, `createDatabaseModeEventSession`, `useDatabaseModeEvents`, `formatDatabaseModeDateTime`, and `buildDatabaseModeQuerySignature`.

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-06-24-database-mode-sse-realtime.md`. Two execution options:**

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
