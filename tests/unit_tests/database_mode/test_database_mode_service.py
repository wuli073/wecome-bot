from __future__ import annotations

import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import sqlalchemy
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncTransaction, create_async_engine

from langbot.pkg.database_mode.events import DatabaseModeEventBus, DatabaseModeEventType
from langbot.pkg.database_mode.service import (
    DatabaseModeService,
    MESSAGE_STATUS_DRAFT_READY,
    MESSAGE_STATUS_PENDING,
    MESSAGE_STATUS_PROCESSED,
    MESSAGE_STATUS_SKIPPED,
)
from langbot.pkg.entity.persistence import database_mode as persistence_database_mode


pytestmark = pytest.mark.asyncio


class RecordingEventBus(DatabaseModeEventBus):
    def __init__(self) -> None:
        super().__init__()
        self.published_events = []

    async def publish(self, event) -> None:
        self.published_events.append(event)
        await super().publish(event)


class _TransactionContext:
    def __init__(self, manager: 'MiniPersistenceManager') -> None:
        self._manager = manager
        self._conn: AsyncConnection | None = None
        self._tx: AsyncTransaction | None = None

    async def __aenter__(self) -> AsyncConnection:
        self._conn = await self._manager.engine.connect()
        self._tx = await self._conn.begin()
        return self._conn

    async def __aexit__(self, exc_type, exc, tb) -> None:
        try:
            if exc_type is not None:
                await self._tx.rollback()
                return
            if self._manager.fail_next_commit:
                self._manager.fail_next_commit = False
                await self._tx.rollback()
                raise RuntimeError('Simulated commit failure')
            await self._tx.commit()
        finally:
            if self._conn is not None:
                await self._conn.close()


class _EngineBeginContext:
    def __init__(self, manager: 'MiniPersistenceManager') -> None:
        self._transaction_context = _TransactionContext(manager)

    async def __aenter__(self) -> AsyncConnection:
        return await self._transaction_context.__aenter__()

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self._transaction_context.__aexit__(exc_type, exc, tb)


class _EngineProxy:
    def __init__(self, manager: 'MiniPersistenceManager', engine: AsyncEngine) -> None:
        self._manager = manager
        self._engine = engine

    def begin(self) -> _EngineBeginContext:
        return _EngineBeginContext(self._manager)

    def connect(self):
        return self._engine.connect()


class MiniPersistenceManager:
    def __init__(self) -> None:
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        self.engine_proxy = _EngineProxy(self, self.engine)
        self.fail_next_commit = False

    async def initialize(self) -> None:
        async with self.engine.begin() as conn:
            await conn.run_sync(persistence_database_mode.LocalConnectorEvent.__table__.create)
            await conn.run_sync(persistence_database_mode.DatabaseConversation.__table__.create)
            await conn.run_sync(persistence_database_mode.DatabaseMessage.__table__.create)

    async def dispose(self) -> None:
        await self.engine.dispose()

    async def execute_async(self, *args, conn: AsyncConnection | None = None, **kwargs):
        if conn is not None:
            return await conn.execute(*args, **kwargs)

        async with self.engine.connect() as standalone_conn:
            result = await standalone_conn.execute(*args, **kwargs)
            await standalone_conn.commit()
            return result

    def get_db_engine(self):
        return self.engine_proxy

    def serialize_model(self, model, data, masked_columns=None):
        masked_columns = masked_columns or []
        return {
            column.name: getattr(data, column.name)
            if not isinstance(getattr(data, column.name), datetime.datetime)
            else getattr(data, column.name).isoformat()
            for column in model.__table__.columns
            if column.name not in masked_columns
        }


@pytest.fixture
async def service_app():
    persistence_mgr = MiniPersistenceManager()
    await persistence_mgr.initialize()
    ap = SimpleNamespace(
        persistence_mgr=persistence_mgr,
        model_mgr=SimpleNamespace(llm_models=[]),
        database_mode_event_bus=RecordingEventBus(),
    )
    service = DatabaseModeService(ap)
    try:
        yield service, ap
    finally:
        await ap.persistence_mgr.dispose()


def _sample_payload() -> dict:
    return {
        "connector_id": "wxwork-local",
        "source": "wxwork",
        "event_id": "wxwork-local:evt-1",
        "message_key": "wxwork:key-1",
        "conversation": {
            "external_conversation_id": "S:100_200",
            "conversation_name": "Customer A",
            "conversation_type": "direct",
        },
        "message": {
            "external_message_id": "101",
            "sender_id": "200",
            "sender_name": "Customer A",
            "content": "Need pricing details",
            "message_type": "text",
            "sent_at": "2026-06-23T12:00:00",
            "observed_at": "2026-06-23T12:00:02",
        },
    }


async def _ingest_and_get_message(service: DatabaseModeService):
    await service.ingest_internal_event(_sample_payload())
    conversations = await service.list_conversations()
    messages = await service.list_messages(conversations["conversations"][0]["id"])
    return conversations["conversations"][0]["id"], messages["messages"][0]["id"]


async def _ingest_two_messages(service: DatabaseModeService):
    await service.ingest_internal_event(_sample_payload())
    second_payload = _sample_payload() | {"event_id": "wxwork-local:evt-2", "message_key": "wxwork:key-2"}
    second_payload["message"] = dict(second_payload["message"], external_message_id="102", content="Need a refund")
    await service.ingest_internal_event(second_payload)
    conversations = await service.list_conversations()
    messages = await service.list_messages(conversations["conversations"][0]["id"])
    return conversations["conversations"][0]["id"], [message["id"] for message in messages["messages"]]


async def test_ingest_internal_event_is_idempotent(service_app):
    service, ap = service_app

    first = await service.ingest_internal_event(_sample_payload())
    second = await service.ingest_internal_event(_sample_payload())
    conversations = await service.list_conversations()
    messages = await service.list_messages(conversations["conversations"][0]["id"])

    assert first.accepted is True
    assert first.duplicate is False
    assert second.accepted is True
    assert second.duplicate is True
    assert conversations["total"] == 1
    assert messages["total"] == 1
    assert messages["messages"][0]["status"] == MESSAGE_STATUS_PENDING
    assert len(ap.database_mode_event_bus.published_events) == 1
    assert ap.database_mode_event_bus.published_events[0].type == DatabaseModeEventType.MESSAGE_CREATED


async def test_ingest_internal_event_publishes_latency_timestamps(service_app):
    service, ap = service_app
    payload = _sample_payload()
    payload["timings"] = {
        "langbot_ingested_at": "2026-06-24T10:00:00.100000+00:00",
        "delivery_succeeded_at": "2026-06-24T10:00:00.050000+00:00",
    }

    await service.ingest_internal_event(payload)

    event = ap.database_mode_event_bus.published_events[0]
    assert event.occurred_at is not None
    assert event.metadata["timings"]["langbot_ingested_at"] == "2026-06-24T10:00:00.100000+00:00"
    assert event.metadata["timings"]["delivery_succeeded_at"] == "2026-06-24T10:00:00.050000+00:00"
    assert event.metadata["timings"]["sse_published_at"]


async def test_ingest_internal_event_does_not_publish_or_persist_partial_writes_when_commit_fails(service_app):
    service, ap = service_app
    ap.persistence_mgr.fail_next_commit = True

    with pytest.raises(RuntimeError, match='Simulated commit failure'):
        await service.ingest_internal_event(_sample_payload())

    local_event_count = (
        await ap.persistence_mgr.execute_async(
            sqlalchemy.select(sqlalchemy.func.count()).select_from(persistence_database_mode.LocalConnectorEvent)
        )
    ).scalar_one()
    conversation_count = (
        await ap.persistence_mgr.execute_async(
            sqlalchemy.select(sqlalchemy.func.count()).select_from(persistence_database_mode.DatabaseConversation)
        )
    ).scalar_one()
    message_count = (
        await ap.persistence_mgr.execute_async(
            sqlalchemy.select(sqlalchemy.func.count()).select_from(persistence_database_mode.DatabaseMessage)
        )
    ).scalar_one()

    assert local_event_count == 0
    assert conversation_count == 0
    assert message_count == 0
    assert ap.database_mode_event_bus.published_events == []


async def test_ingest_duplicate_message_does_not_persist_event_when_commit_fails(service_app):
    service, ap = service_app
    await service.ingest_internal_event(_sample_payload())
    ap.database_mode_event_bus.published_events.clear()

    duplicate_message_payload = _sample_payload() | {"event_id": "wxwork-local:evt-2"}
    ap.persistence_mgr.fail_next_commit = True

    with pytest.raises(RuntimeError, match='Simulated commit failure'):
        await service.ingest_internal_event(duplicate_message_payload)

    local_event_ids = (
        await ap.persistence_mgr.execute_async(
            sqlalchemy.select(persistence_database_mode.LocalConnectorEvent.event_id).order_by(
                persistence_database_mode.LocalConnectorEvent.id.asc()
            )
        )
    ).scalars().all()

    assert local_event_ids == ["wxwork-local:evt-1"]
    assert ap.database_mode_event_bus.published_events == []


async def test_ingest_duplicate_message_key_returns_duplicate_and_publishes_invalidated(service_app):
    service, ap = service_app
    await service.ingest_internal_event(_sample_payload())
    ap.database_mode_event_bus.published_events.clear()

    replay_payload = _sample_payload() | {"event_id": "wxwork-local:evt-2"}

    result = await service.ingest_internal_event(replay_payload)

    assert result.accepted is True
    assert result.duplicate is True
    assert [event.type for event in ap.database_mode_event_bus.published_events] == [
        DatabaseModeEventType.INVALIDATED
    ]


async def test_generate_draft_publishes_one_updated_event_after_commit(service_app):
    service, ap = service_app
    _, message_id = await _ingest_and_get_message(service)

    provider = SimpleNamespace(
        invoke_llm=AsyncMock(return_value=SimpleNamespace(content="Thanks, we will follow up shortly."))
    )
    ap.model_mgr.llm_models = [SimpleNamespace(provider=provider)]
    ap.database_mode_event_bus.published_events.clear()

    updated = await service.generate_draft(message_id)

    assert updated["status"] == MESSAGE_STATUS_DRAFT_READY
    assert updated["draft_text"] == "Thanks, we will follow up shortly."
    assert updated["draft_source"] == "ai"
    assert len(ap.database_mode_event_bus.published_events) == 1
    event = ap.database_mode_event_bus.published_events[0]
    assert event.type == DatabaseModeEventType.MESSAGE_UPDATED
    assert event.message_id == message_id


async def test_update_draft_publishes_one_updated_event_after_commit(service_app):
    service, ap = service_app
    _, message_id = await _ingest_and_get_message(service)
    ap.database_mode_event_bus.published_events.clear()

    updated = await service.update_draft(message_id, "Handled manually.", draft_source="manual")

    assert updated["status"] == MESSAGE_STATUS_DRAFT_READY
    assert updated["draft_text"] == "Handled manually."
    assert updated["draft_source"] == "manual"
    assert len(ap.database_mode_event_bus.published_events) == 1
    event = ap.database_mode_event_bus.published_events[0]
    assert event.type == DatabaseModeEventType.MESSAGE_UPDATED
    assert event.message_id == message_id


async def test_generate_draft_does_not_publish_when_commit_fails(service_app):
    service, ap = service_app
    _, message_id = await _ingest_and_get_message(service)

    provider = SimpleNamespace(
        invoke_llm=AsyncMock(return_value=SimpleNamespace(content="Thanks, we will follow up shortly."))
    )
    ap.model_mgr.llm_models = [SimpleNamespace(provider=provider)]
    ap.database_mode_event_bus.published_events.clear()
    ap.persistence_mgr.fail_next_commit = True

    with pytest.raises(RuntimeError, match='Simulated commit failure'):
        await service.generate_draft(message_id)

    current = await service.get_message(message_id)
    assert current["status"] == MESSAGE_STATUS_PENDING
    assert ap.database_mode_event_bus.published_events == []


@pytest.mark.parametrize(
    "operation_name",
    ["update_draft", "process_message", "skip_message", "delete_message", "batch_process", "batch_skip", "batch_delete"],
)
async def test_write_methods_do_not_publish_when_commit_fails(service_app, operation_name):
    service, ap = service_app
    conversation_id, message_id = await _ingest_and_get_message(service)
    batch_message_ids: list[int] | None = None
    if operation_name in {"batch_process", "batch_skip", "batch_delete"}:
        conversation_id, batch_message_ids = await _ingest_two_messages(service)

    ap.database_mode_event_bus.published_events.clear()
    ap.persistence_mgr.fail_next_commit = True

    with pytest.raises(RuntimeError, match='Simulated commit failure'):
        if operation_name == "update_draft":
            await service.update_draft(message_id, "Handled manually.", draft_source="manual")
        elif operation_name == "process_message":
            await service.process_message(message_id)
        elif operation_name == "skip_message":
            await service.skip_message(message_id)
        elif operation_name == "delete_message":
            await service.delete_message(message_id)
        elif operation_name == "batch_process":
            await service.batch_process(batch_message_ids)
        elif operation_name == "batch_skip":
            await service.batch_skip(batch_message_ids)
        elif operation_name == "batch_delete":
            await service.batch_delete(batch_message_ids)
        else:
            raise AssertionError(f"Unexpected operation {operation_name}")

    assert ap.database_mode_event_bus.published_events == []

    if operation_name == "update_draft":
        current = await service.get_message(message_id)
        assert current["status"] == MESSAGE_STATUS_PENDING
        assert current["draft_text"] is None
        assert current["draft_source"] is None
    elif operation_name in {"process_message", "skip_message"}:
        current = await service.get_message(message_id)
        assert current["status"] == MESSAGE_STATUS_PENDING
    elif operation_name == "delete_message":
        remaining = await service.list_messages(conversation_id)
        assert remaining["total"] == 1
        assert remaining["messages"][0]["id"] == message_id
    elif operation_name == "batch_process":
        remaining = await service.list_messages(conversation_id)
        assert [message["id"] for message in remaining["messages"]] == batch_message_ids
        assert [message["status"] for message in remaining["messages"]] == [
            MESSAGE_STATUS_PENDING,
            MESSAGE_STATUS_PENDING,
        ]
    elif operation_name == "batch_skip":
        remaining = await service.list_messages(conversation_id)
        assert [message["id"] for message in remaining["messages"]] == batch_message_ids
        assert [message["status"] for message in remaining["messages"]] == [
            MESSAGE_STATUS_PENDING,
            MESSAGE_STATUS_PENDING,
        ]
    elif operation_name == "batch_delete":
        remaining = await service.list_messages(conversation_id)
        assert [message["id"] for message in remaining["messages"]] == batch_message_ids
        assert [message["status"] for message in remaining["messages"]] == [
            MESSAGE_STATUS_PENDING,
            MESSAGE_STATUS_PENDING,
        ]


async def test_list_conversations_returns_searchable_summary_fields(service_app):
    service, _ = service_app
    await service.ingest_internal_event(_sample_payload())

    result = await service.list_conversations(keyword="pricing")

    assert result["total"] == 1
    conversation = result["conversations"][0]
    assert conversation["connector_id"] == "wxwork-local"
    assert conversation["external_conversation_id"] == "S:100_200"
    assert conversation["latest_customer"] == "Customer A"
    assert conversation["latest_message_summary"] == "Need pricing details"
    assert conversation["last_message_at"].endswith("+00:00")


async def test_get_message_serializes_datetimes_with_timezone_offset(service_app):
    service, _ = service_app
    _, message_id = await _ingest_and_get_message(service)

    message = await service.get_message(message_id)

    assert message["sent_at"].endswith("+00:00")
    assert message["observed_at"].endswith("+00:00")
    assert message["created_at"].endswith("+00:00")
    assert message["updated_at"].endswith("+00:00")


async def test_delete_message_publishes_deleted_event(service_app):
    service, ap = service_app
    conversation_id, message_id = await _ingest_and_get_message(service)
    ap.database_mode_event_bus.published_events.clear()

    await service.delete_message(message_id)

    remaining = await service.list_messages(conversation_id)
    assert remaining["total"] == 0
    assert len(ap.database_mode_event_bus.published_events) == 1
    event = ap.database_mode_event_bus.published_events[0]
    assert event.type == DatabaseModeEventType.MESSAGE_DELETED
    assert event.message_id == message_id


async def test_process_and_skip_publish_updated_event(service_app):
    service, ap = service_app
    _, message_id = await _ingest_and_get_message(service)
    ap.database_mode_event_bus.published_events.clear()

    processed = await service.process_message(message_id)
    skipped = await service.skip_message(message_id)

    assert processed["status"] == MESSAGE_STATUS_PROCESSED
    assert processed["attempt_count"] == 1
    assert skipped["status"] == MESSAGE_STATUS_SKIPPED
    assert [event.type for event in ap.database_mode_event_bus.published_events] == [
        DatabaseModeEventType.MESSAGE_UPDATED,
        DatabaseModeEventType.MESSAGE_UPDATED,
    ]
    assert [event.message_id for event in ap.database_mode_event_bus.published_events] == [message_id, message_id]


async def test_batch_delete_publishes_one_invalidated_event(service_app):
    service, ap = service_app
    _, message_ids = await _ingest_two_messages(service)
    ap.database_mode_event_bus.published_events.clear()

    result = await service.batch_delete(message_ids)

    assert result == {"deleted_ids": message_ids}
    assert len(ap.database_mode_event_bus.published_events) == 1
    event = ap.database_mode_event_bus.published_events[0]
    assert event.type == DatabaseModeEventType.INVALIDATED
    assert event.conversation_id is None
    assert event.message_id is None


async def test_batch_process_publishes_one_invalidated_event(service_app):
    service, ap = service_app
    _, message_ids = await _ingest_two_messages(service)
    ap.database_mode_event_bus.published_events.clear()

    result = await service.batch_process(message_ids)

    assert [message["status"] for message in result["messages"]] == [
        MESSAGE_STATUS_PROCESSED,
        MESSAGE_STATUS_PROCESSED,
    ]
    assert len(ap.database_mode_event_bus.published_events) == 1
    assert ap.database_mode_event_bus.published_events[0].type == DatabaseModeEventType.INVALIDATED


async def test_batch_skip_publishes_one_invalidated_event(service_app):
    service, ap = service_app
    _, message_ids = await _ingest_two_messages(service)
    ap.database_mode_event_bus.published_events.clear()

    result = await service.batch_skip(message_ids)

    assert [message["status"] for message in result["messages"]] == [
        MESSAGE_STATUS_SKIPPED,
        MESSAGE_STATUS_SKIPPED,
    ]
    assert len(ap.database_mode_event_bus.published_events) == 1
    assert ap.database_mode_event_bus.published_events[0].type == DatabaseModeEventType.INVALIDATED


async def test_batch_operations_require_message_ids(service_app):
    service, _ = service_app

    with pytest.raises(ValueError, match="message_ids is required"):
        await service.batch_process([])


async def test_database_mode_service_uses_real_persistence_manager_contract_without_transaction_method(service_app):
    service, ap = service_app

    assert not hasattr(ap.persistence_mgr, 'transaction')

    result = await service.ingest_internal_event(_sample_payload())

    assert result.accepted is True
    assert result.duplicate is False
