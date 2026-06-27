from __future__ import annotations

import asyncio
import sys
import types
import datetime
from types import SimpleNamespace

import jwt
import pytest
import quart
import sqlalchemy
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncTransaction, create_async_engine
from unittest.mock import AsyncMock, Mock

import langbot_plugin.api.definition.abstract.platform.event_logger as abstract_platform_logger
import langbot_plugin.api.entities.builtin.platform.message as platform_message
core_app_stub = types.ModuleType("langbot.pkg.core.app")
core_app_stub.Application = object
_previous_core_app_module = sys.modules.get("langbot.pkg.core.app")
sys.modules["langbot.pkg.core.app"] = core_app_stub

from langbot.pkg.api.http.controller.groups.bot_database_mode import BotDatabaseModeRouterGroup
from langbot.pkg.api.http.controller.groups.database_mode import DatabaseModeRouterGroup
from langbot.pkg.database_mode.events import DatabaseModeEventBus
from langbot.pkg.database_mode.processing_service import DatabaseModeProcessingService

if _previous_core_app_module is not None:
    sys.modules["langbot.pkg.core.app"] = _previous_core_app_module
else:
    sys.modules.pop("langbot.pkg.core.app", None)


pytestmark = pytest.mark.asyncio


import langbot.pkg.api.http.controller.groups.database_mode as database_mode_module
from langbot.pkg.database_mode.events import (
    DatabaseModeEvent,
    DatabaseModeEventBus,
    DatabaseModeEventType,
)
from langbot.pkg.database_mode.service import DatabaseModeService
from langbot.pkg.entity.persistence import database_mode as persistence_database_mode
from langbot.pkg.entity.persistence import bot as persistence_bot
from langbot.pkg.pipeline.aggregator import MessageAggregator
from langbot.pkg.pipeline.controller import Controller
from langbot.pkg.pipeline.pool import QueryPool
from langbot.pkg.platform.botmgr import RuntimeBot
from langbot.pkg.platform.sources.wxwork_database import WXWorkDatabaseAdapter
from langbot.pkg.provider.session.sessionmgr import SessionManager


def _user_record(email: str = "user@example.com") -> SimpleNamespace:
    return SimpleNamespace(user=email)


class DummySyncLogger:
    def info(self, *args, **kwargs):
        return None

    def debug(self, *args, **kwargs):
        return None

    def warning(self, *args, **kwargs):
        return None

    def error(self, *args, **kwargs):
        return None

    def exception(self, *args, **kwargs):
        return None


class DummyEventLogger(abstract_platform_logger.AbstractEventLogger):
    async def info(self, text, images=None, message_session_id=None, no_throw=True):
        return None

    async def debug(self, text, images=None, message_session_id=None, no_throw=True):
        return None

    async def warning(self, text, images=None, message_session_id=None, no_throw=True):
        return None

    async def error(self, text, images=None, message_session_id=None, no_throw=True):
        return None


def _event_context():
    event = SimpleNamespace(reply_message_chain=None, user_message_alter=None)
    return SimpleNamespace(event=event, is_prevented_default=Mock(return_value=False))


def _runtime_pipeline_config() -> dict:
    return {
        'output': {
            'force-delay': {'min': 0.0, 'max': 0.0},
            'misc': {
                'at-sender': False,
                'quote-origin': False,
                'exception-handling': 'show-error',
                'failure-hint': 'Request failed.',
            },
        }
    }


async def _install_formal_runtime_processing(ap, *, pipeline, adapter, bot_uuid='bot-1', pipeline_uuid='pipeline-123'):
    ap.instance_config.data.setdefault('concurrency', {'pipeline': 2, 'session': 1})
    ap.logger = DummySyncLogger()
    ap.query_pool = QueryPool()
    ap.sess_mgr = SessionManager(ap)
    ap.msg_aggregator = MessageAggregator(ap)
    ap.ctrl = Controller(ap)
    ap.monitoring_service = SimpleNamespace(
        record_message=AsyncMock(return_value='monitoring-message-id'),
        update_session_activity=AsyncMock(return_value=True),
        record_session_start=AsyncMock(return_value=None),
        update_message_status=AsyncMock(return_value=None),
        record_error=AsyncMock(return_value=None),
    )
    ap.plugin_connector = SimpleNamespace(emit_event=AsyncMock(return_value=_event_context()))
    ap.pipeline_mgr = SimpleNamespace(get_pipeline_by_uuid=AsyncMock(return_value=pipeline))

    runtime_bot = RuntimeBot(
        ap=ap,
        bot_entity=persistence_bot.Bot(
            uuid=bot_uuid,
            name='Database Bot',
            description='',
            adapter='wxwork_database',
            adapter_config={'connector_id': 'wxwork-local'},
            enable=True,
            use_pipeline_uuid=pipeline_uuid,
        ),
        adapter=adapter,
        logger=DummyEventLogger(),
    )
    await runtime_bot.initialize()
    ap.platform_mgr = SimpleNamespace(bots=[runtime_bot])


async def _make_client(*, scheme: str = "http", user_exists: bool = True):
    app = quart.Quart(__name__)
    verified_user_email = "user@example.com"

    async def verify_jwt_token(_token: str) -> str:
        return verified_user_email

    async def get_user_by_email(_email: str):
        if not user_exists:
            return None
        return _user_record(verified_user_email)

    ap = SimpleNamespace(
        instance_config=SimpleNamespace(
            data={
                "system": {
                    "jwt": {
                        "secret": "test-secret",
                        "expire": 3600,
                    }
                }
            }
        ),
        user_service=SimpleNamespace(
            verify_jwt_token=verify_jwt_token,
            get_user_by_email=get_user_by_email,
        ),
        database_mode_service=SimpleNamespace(),
        database_mode_event_bus=DatabaseModeEventBus(),
    )

    router = DatabaseModeRouterGroup(ap, app)
    await router.initialize()
    return app, app.test_client(), ap, scheme


async def _create_bot_scope_data(ap) -> None:
    async with ap.persistence_mgr.get_db_engine().begin() as conn:
        result = await conn.execute(
            sqlalchemy.insert(persistence_database_mode.ChannelAccount).values(
                {
                    "connector_id": "wxwork-local",
                    "channel_type": "wxwork",
                    "external_account_id": "acc-1",
                    "display_name": "Test Account",
                    "enabled": True,
                }
            )
        )
        channel_account_id = result.inserted_primary_key[0]
        await conn.execute(
            sqlalchemy.insert(persistence_database_mode.BotChannelBinding).values(
                {
                    "bot_uuid": "bot-1",
                    "channel_account_id": channel_account_id,
                    "enabled": True,
                    "auto_generate_draft": False,
                }
            )
        )
        await conn.execute(
            sqlalchemy.insert(persistence_database_mode.DatabaseConversation).values(
                {
                    "connector_id": "wxwork-local",
                    "source": "wxwork",
                    "external_conversation_id": "S:100_200",
                    "conversation_name": "Customer A",
                    "conversation_type": "direct",
                    "last_message_at": datetime.datetime.now(datetime.timezone.utc),
                }
            )
        )
        await conn.execute(
            sqlalchemy.insert(persistence_database_mode.DatabaseConversation).values(
                {
                    "connector_id": "other-connector",
                    "source": "wxwork",
                    "external_conversation_id": "S:300_400",
                    "conversation_name": "Customer B",
                    "conversation_type": "direct",
                    "last_message_at": datetime.datetime.now(datetime.timezone.utc),
                }
            )
        )
        wxwork_conversation_id = (
            await conn.execute(
                sqlalchemy.select(persistence_database_mode.DatabaseConversation.id).where(
                    persistence_database_mode.DatabaseConversation.connector_id == "wxwork-local"
                )
            )
        ).scalar_one()
        other_conversation_id = (
            await conn.execute(
                sqlalchemy.select(persistence_database_mode.DatabaseConversation.id).where(
                    persistence_database_mode.DatabaseConversation.connector_id == "other-connector"
                )
            )
        ).scalar_one()
        await conn.execute(
            sqlalchemy.insert(persistence_database_mode.DatabaseMessage).values(
                {
                    "event_id": "wxwork-local:evt-1",
                    "message_key": "wxwork-local:key-1",
                    "conversation_id": wxwork_conversation_id,
                    "external_message_id": "101",
                    "sender_id": "200",
                    "sender_name": "Customer A",
                    "content": "Need pricing details",
                    "message_type": "text",
                    "sent_at": datetime.datetime.now(datetime.timezone.utc),
                    "observed_at": datetime.datetime.now(datetime.timezone.utc),
                    "status": "pending",
                    "draft_text": None,
                    "draft_source": None,
                    "attempt_count": 0,
                    "last_error": None,
                }
            )
        )
        await conn.execute(
            sqlalchemy.insert(persistence_database_mode.DatabaseMessage).values(
                {
                    "event_id": "other-connector:evt-1",
                    "message_key": "other-connector:key-1",
                    "conversation_id": other_conversation_id,
                    "external_message_id": "201",
                    "sender_id": "300",
                    "sender_name": "Customer B",
                    "content": "Other connector message",
                    "message_type": "text",
                    "sent_at": datetime.datetime.now(datetime.timezone.utc),
                    "observed_at": datetime.datetime.now(datetime.timezone.utc),
                    "status": "pending",
                    "draft_text": None,
                    "draft_source": None,
                    "attempt_count": 0,
                    "last_error": None,
                }
            )
        )


async def _make_bot_client():
    app = quart.Quart(__name__)

    class _TxnContext:
        def __init__(self, manager):
            self._manager = manager
            self._conn: AsyncConnection | None = None
            self._tx: AsyncTransaction | None = None

        async def __aenter__(self):
            self._conn = await self._manager.engine.connect()
            self._tx = await self._conn.begin()
            return self._conn

        async def __aexit__(self, exc_type, exc, tb):
            try:
                if exc_type is not None:
                    await self._tx.rollback()
                else:
                    await self._tx.commit()
            finally:
                if self._conn is not None:
                    await self._conn.close()

    class _EngineProxy:
        def __init__(self, manager, engine):
            self._manager = manager
            self._engine = engine

        def begin(self):
            return _TxnContext(self._manager)

    class _MiniPersistenceManager:
        def __init__(self):
            self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
            self.engine_proxy = _EngineProxy(self, self.engine)

        async def initialize(self):
            async with self.engine.begin() as conn:
                await conn.run_sync(persistence_database_mode.ChannelAccount.__table__.create)
                await conn.run_sync(persistence_database_mode.BotChannelBinding.__table__.create)
                await conn.run_sync(persistence_database_mode.DatabaseConversation.__table__.create)
                await conn.run_sync(persistence_database_mode.DatabaseMessage.__table__.create)

        async def dispose(self):
            await self.engine.dispose()

        async def execute_async(self, *args, conn=None, **kwargs):
            if conn is not None:
                return await conn.execute(*args, **kwargs)
            async with self.engine.connect() as standalone_conn:
                result = await standalone_conn.execute(*args, **kwargs)
                if result.returns_rows:
                    rows = list(result.all())

                    class _Result:
                        def __init__(self, rows):
                            self._rows = rows

                        def scalar(self):
                            first = self._rows[0] if self._rows else None
                            if hasattr(first, "_mapping") and len(first._mapping) == 1:
                                return list(first._mapping.values())[0]
                            return first

                        def scalar_one(self):
                            return self.scalar()

                        def all(self):
                            return self._rows

                        def first(self):
                            return self._rows[0] if self._rows else None

                        def scalars(self):
                            class _Scalars:
                                def __init__(self, rows):
                                    self._rows = rows

                                def first(self):
                                    return self.all()[0] if self.all() else None

                                def all(self):
                                    values = []
                                    for row in self._rows:
                                        if hasattr(row, "_mapping") and len(row._mapping) == 1:
                                            values.append(list(row._mapping.values())[0])
                                        else:
                                            values.append(row)
                                    return values

                            return _Scalars(self._rows)

                    await standalone_conn.commit()
                    return _Result(rows)
                await standalone_conn.commit()
                return result

        def get_db_engine(self):
            return self.engine_proxy

        def serialize_model(self, model, data, masked_columns=None):
            masked_columns = masked_columns or []
            return {
                column.name: getattr(data, column.name)
                for column in model.__table__.columns
                if column.name not in masked_columns
            }

    persistence_mgr = _MiniPersistenceManager()
    await persistence_mgr.initialize()
    ap = SimpleNamespace(
        instance_config=SimpleNamespace(
            data={
                "system": {
                    "jwt": {"secret": "test-secret", "expire": 3600},
                }
            }
        ),
        user_service=SimpleNamespace(
            verify_jwt_token=AsyncMock(return_value="user@example.com"),
            get_user_by_email=AsyncMock(return_value=_user_record()),
        ),
        bot_service=SimpleNamespace(
            get_bot=AsyncMock(return_value={"uuid": "bot-1", "adapter": "wxwork_database", "enable": True}),
        ),
        persistence_mgr=persistence_mgr,
        database_mode_service=DatabaseModeService(SimpleNamespace()),
        database_mode_event_bus=DatabaseModeEventBus(),
    )
    ap.database_mode_service.ap = ap
    await _create_bot_scope_data(ap)
    router = BotDatabaseModeRouterGroup(ap, app)
    await router.initialize()
    return app, app.test_client(), ap, persistence_mgr


async def _make_bot_client_with_processing_service():
    app = quart.Quart(__name__)

    class _TxnContext:
        def __init__(self, manager):
            self._manager = manager
            self._conn: AsyncConnection | None = None
            self._tx: AsyncTransaction | None = None

        async def __aenter__(self):
            self._conn = await self._manager.engine.connect()
            self._tx = await self._conn.begin()
            return self._conn

        async def __aexit__(self, exc_type, exc, tb):
            try:
                if exc_type is not None:
                    await self._tx.rollback()
                else:
                    await self._tx.commit()
            finally:
                if self._conn is not None:
                    await self._conn.close()

    class _EngineProxy:
        def __init__(self, manager, engine):
            self._manager = manager
            self._engine = engine

        def begin(self):
            return _TxnContext(self._manager)

    class _RawPersistenceManager:
        def __init__(self):
            self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
            self.engine_proxy = _EngineProxy(self, self.engine)

        async def initialize(self):
            async with self.engine.begin() as conn:
                await conn.run_sync(persistence_database_mode.ChannelAccount.__table__.create)
                await conn.run_sync(persistence_database_mode.BotChannelBinding.__table__.create)
                await conn.run_sync(persistence_database_mode.DatabaseConversation.__table__.create)
                await conn.run_sync(persistence_database_mode.DatabaseMessage.__table__.create)
                await conn.run_sync(persistence_database_mode.MessageProcessingRun.__table__.create)
                await conn.run_sync(persistence_database_mode.ReplyDraft.__table__.create)
                await conn.execute(
                    sqlalchemy.text(
                        "CREATE UNIQUE INDEX ix_message_processing_runs_atomic_claim "
                        "ON message_processing_runs (message_id, bot_uuid) "
                        "WHERE status = 'processing'"
                    )
                )
                await conn.execute(
                    sqlalchemy.text(
                        "CREATE UNIQUE INDEX ix_reply_drafts_active_unique "
                        "ON reply_drafts (message_id, bot_uuid) "
                        "WHERE status = 'active'"
                    )
                )

        async def dispose(self):
            await self.engine.dispose()

        async def execute_async(self, *args, conn=None, **kwargs):
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

    class _LauncherAwareAdapter(WXWorkDatabaseAdapter):
        def get_launcher_id(self, event):
            return 'custom-launcher'

    class _FakePipeline:
        pipeline_entity = SimpleNamespace(config=_runtime_pipeline_config())

        async def run(self, query):
            if query.launcher_id != 'custom-launcher':
                return None
            await query.adapter.reply_message(
                message_source=query.message_event,
                message=platform_message.MessageChain([platform_message.Plain(text="Pipeline generated draft")]),
            )

    persistence_mgr = _RawPersistenceManager()
    await persistence_mgr.initialize()
    ap = SimpleNamespace(
        instance_config=SimpleNamespace(
            data={
                "system": {
                    "jwt": {"secret": "test-secret", "expire": 3600},
                }
            }
        ),
        user_service=SimpleNamespace(
            verify_jwt_token=AsyncMock(return_value="user@example.com"),
            get_user_by_email=AsyncMock(return_value=_user_record()),
        ),
        bot_service=SimpleNamespace(
            get_bot=AsyncMock(return_value={"uuid": "bot-1", "adapter": "wxwork_database", "enable": True}),
        ),
        persistence_mgr=persistence_mgr,
        database_mode_service=DatabaseModeService(SimpleNamespace()),
        database_mode_event_bus=DatabaseModeEventBus(),
    )
    ap.database_mode_service.ap = ap
    await _install_formal_runtime_processing(
        ap,
        pipeline=_FakePipeline(),
        adapter=_LauncherAwareAdapter(config={'connector_id': 'wxwork-local'}, logger=DummyEventLogger()),
    )
    ap.database_mode_processing_service = DatabaseModeProcessingService(ap)
    await _create_bot_scope_data(ap)
    router = BotDatabaseModeRouterGroup(ap, app)
    await router.initialize()
    return app, app.test_client(), ap, persistence_mgr


async def _make_legacy_database_mode_client():
    app = quart.Quart(__name__)

    class _TxnContext:
        def __init__(self, manager):
            self._manager = manager
            self._conn: AsyncConnection | None = None
            self._tx: AsyncTransaction | None = None

        async def __aenter__(self):
            self._conn = await self._manager.engine.connect()
            self._tx = await self._conn.begin()
            return self._conn

        async def __aexit__(self, exc_type, exc, tb):
            try:
                if exc_type is not None:
                    await self._tx.rollback()
                else:
                    await self._tx.commit()
            finally:
                if self._conn is not None:
                    await self._conn.close()

    class _EngineProxy:
        def __init__(self, manager, engine):
            self._manager = manager
            self._engine = engine

        def begin(self):
            return _TxnContext(self._manager)

    class _MiniPersistenceManager:
        def __init__(self):
            self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
            self.engine_proxy = _EngineProxy(self, self.engine)

        async def initialize(self):
            async with self.engine.begin() as conn:
                await conn.run_sync(persistence_database_mode.ChannelAccount.__table__.create)
                await conn.run_sync(persistence_database_mode.BotChannelBinding.__table__.create)
                await conn.run_sync(persistence_database_mode.DatabaseConversation.__table__.create)
                await conn.run_sync(persistence_database_mode.DatabaseMessage.__table__.create)

        async def dispose(self):
            await self.engine.dispose()

        async def execute_async(self, *args, conn=None, **kwargs):
            if conn is not None:
                return await conn.execute(*args, **kwargs)
            async with self.engine.connect() as standalone_conn:
                result = await standalone_conn.execute(*args, **kwargs)
                if result.returns_rows:
                    rows = list(result.all())

                    class _Result:
                        def __init__(self, rows):
                            self._rows = rows

                        def scalar(self):
                            first = self._rows[0] if self._rows else None
                            if hasattr(first, "_mapping") and len(first._mapping) == 1:
                                return list(first._mapping.values())[0]
                            return first

                        def scalar_one(self):
                            return self.scalar()

                        def all(self):
                            return self._rows

                        def first(self):
                            return self._rows[0] if self._rows else None

                        def scalars(self):
                            class _Scalars:
                                def __init__(self, rows):
                                    self._rows = rows

                                def first(self):
                                    return self.all()[0] if self.all() else None

                                def all(self):
                                    values = []
                                    for row in self._rows:
                                        if hasattr(row, "_mapping") and len(row._mapping) == 1:
                                            values.append(list(row._mapping.values())[0])
                                        else:
                                            values.append(row)
                                    return values

                            return _Scalars(self._rows)

                    await standalone_conn.commit()
                    return _Result(rows)
                await standalone_conn.commit()
                return result

        def get_db_engine(self):
            return self.engine_proxy

        def serialize_model(self, model, data, masked_columns=None):
            masked_columns = masked_columns or []
            return {
                column.name: getattr(data, column.name)
                for column in model.__table__.columns
                if column.name not in masked_columns
            }

    persistence_mgr = _MiniPersistenceManager()
    await persistence_mgr.initialize()
    ap = SimpleNamespace(
        instance_config=SimpleNamespace(
            data={
                "system": {
                    "jwt": {"secret": "test-secret", "expire": 3600},
                }
            }
        ),
        user_service=SimpleNamespace(
            verify_jwt_token=AsyncMock(return_value="user@example.com"),
            get_user_by_email=AsyncMock(return_value=_user_record()),
        ),
        database_mode_service=DatabaseModeService(SimpleNamespace()),
        database_mode_event_bus=DatabaseModeEventBus(),
        persistence_mgr=persistence_mgr,
    )
    ap.database_mode_service.ap = ap
    await _create_bot_scope_data(ap)
    router = DatabaseModeRouterGroup(ap, app)
    await router.initialize()
    return app, app.test_client(), ap, persistence_mgr


def _decode_cookie(cookie_value: str, secret: str) -> dict:
    return jwt.decode(cookie_value, secret, algorithms=["HS256"])


async def test_handshake_returns_204_and_sets_cookie():
    _app, client, ap, scheme = await _make_client()

    response = await client.post(
        "/api/v1/database-mode/events/session",
        headers={"Authorization": "Bearer valid-user-token"},
        scheme=scheme,
    )

    assert response.status_code == 204
    assert response.headers["Cache-Control"] == "no-store"

    set_cookie = response.headers.get("Set-Cookie")
    assert set_cookie is not None
    assert "langbot_dbmode_sse=" in set_cookie
    assert "HttpOnly" in set_cookie
    assert "SameSite=Strict" in set_cookie
    assert "Path=/api/v1/database-mode/events" in set_cookie
    assert "Domain=" not in set_cookie
    assert "Secure" not in set_cookie

    cookie_value = set_cookie.split("langbot_dbmode_sse=", 1)[1].split(";", 1)[0]
    payload = _decode_cookie(cookie_value, ap.instance_config.data["system"]["jwt"]["secret"])
    assert payload["version"] == 1
    assert payload["purpose"] == "database-mode-sse"
    assert payload["sub"] == "user@example.com"
    assert payload["session_id"]
    assert payload["issued_at"]
    assert payload["expires_at"]


async def test_handshake_sets_secure_cookie_for_https():
    _app, client, _ap, _scheme = await _make_client(scheme="https")

    response = await client.post(
        "/api/v1/database-mode/events/session",
        headers={"Authorization": "Bearer valid-user-token"},
        scheme="https",
    )

    assert response.status_code == 204
    assert "Secure" in response.headers["Set-Cookie"]


async def test_stream_rejects_missing_cookie():
    _app, client, _ap, scheme = await _make_client()

    response = await client.get("/api/v1/database-mode/events", scheme=scheme)
    payload = await response.get_json()

    assert response.status_code == 401
    assert payload["msg"] == "Missing SSE session cookie"


async def test_stream_rejects_expired_cookie():
    _app, client, ap, scheme = await _make_client()
    expired_payload = {
        "sub": "user@example.com",
        "version": 1,
        "purpose": "database-mode-sse",
        "issued_at": (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=10)).isoformat(),
        "expires_at": (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=5)).isoformat(),
        "session_id": "expired-session",
    }
    expired_cookie = jwt.encode(
        expired_payload,
        ap.instance_config.data["system"]["jwt"]["secret"],
        algorithm="HS256",
    )

    response = await client.get(
        "/api/v1/database-mode/events",
        headers={"Cookie": f"langbot_dbmode_sse={expired_cookie}"},
        scheme=scheme,
    )
    payload = await response.get_json()

    assert response.status_code == 401
    assert payload["msg"] == "SSE session expired"


async def test_stream_rejects_cookie_for_deleted_user():
    _app, client, ap, scheme = await _make_client(user_exists=False)
    issued_at = datetime.datetime.now(datetime.timezone.utc)
    payload = {
        "sub": "user@example.com",
        "version": 1,
        "purpose": "database-mode-sse",
        "issued_at": issued_at.isoformat(),
        "expires_at": (issued_at + datetime.timedelta(minutes=5)).isoformat(),
        "session_id": "active-session",
    }
    cookie_value = jwt.encode(
        payload,
        ap.instance_config.data["system"]["jwt"]["secret"],
        algorithm="HS256",
    )

    response = await client.get(
        "/api/v1/database-mode/events",
        headers={"Cookie": f"langbot_dbmode_sse={cookie_value}"},
        scheme=scheme,
    )
    data = await response.get_json()

    assert response.status_code == 401
    assert data["msg"] == "User not found"


async def _create_sse_cookie(client, scheme: str) -> str:
    handshake = await client.post(
        "/api/v1/database-mode/events/session",
        headers={"Authorization": "Bearer valid-user-token"},
        scheme=scheme,
    )
    set_cookie = handshake.headers["Set-Cookie"]
    return set_cookie.split("langbot_dbmode_sse=", 1)[1].split(";", 1)[0]


async def _receive_until(
    connection,
    predicate,
    *,
    attempts: int = 10,
    timeout: float = 1,
):
    chunks = []
    for _ in range(attempts):
        chunk = await asyncio.wait_for(connection.receive(), timeout=timeout)
        chunks.append(chunk)
        if predicate(chunk):
            return chunk, chunks
    raise AssertionError(f"Did not receive expected chunk after {attempts} attempts: {chunks!r}")


async def test_stream_ignores_last_event_id_and_emits_ready(monkeypatch):
    app, client, ap, scheme = await _make_client()
    monkeypatch.setattr(database_mode_module, "DATABASE_MODE_SSE_HEARTBEAT_INTERVAL_SECONDS", 0.01)
    captured_response = None
    original_make_response = app.make_response

    async def capture_make_response(result):
        nonlocal captured_response
        response = await original_make_response(result)
        if quart.request.path == "/api/v1/database-mode/events":
            captured_response = response
        return response

    app.make_response = capture_make_response

    cookie_value = await _create_sse_cookie(client, scheme)
    cookie_header = f"langbot_dbmode_sse={cookie_value}"

    async with client.request(
        "/api/v1/database-mode/events",
        method="GET",
        headers={
            "Cookie": cookie_header,
            "Last-Event-ID": "should-be-ignored",
        },
        scheme=scheme,
    ) as connection:
        initial_chunk = await connection.receive()
        assert b"event: ready\n" in initial_chunk
        assert b'"type": "ready"' in initial_chunk
        heartbeat_one = await asyncio.wait_for(connection.receive(), timeout=1)
        heartbeat_two = await asyncio.wait_for(connection.receive(), timeout=1)
        assert heartbeat_one == b": heartbeat\n\n"
        assert heartbeat_two == b": heartbeat\n\n"
        assert ap.database_mode_event_bus.subscriber_count == 1
        await connection.disconnect()
        ap.database_mode_event_bus.close()
        response = await connection.as_response()

    assert captured_response is not None
    assert captured_response.timeout is None
    assert response.status_code == 200
    assert response.headers["Content-Type"].startswith("text/event-stream")
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["Content-Encoding"] == "identity"
    assert response.headers["X-Accel-Buffering"] == "no"
    assert ap.database_mode_event_bus.subscriber_count == 0


async def test_stream_business_event_is_followed_by_heartbeat(monkeypatch):
    _app, client, ap, scheme = await _make_client()
    monkeypatch.setattr(database_mode_module, "DATABASE_MODE_SSE_HEARTBEAT_INTERVAL_SECONDS", 0.01)
    cookie_value = await _create_sse_cookie(client, scheme)

    async with client.request(
        "/api/v1/database-mode/events",
        method="GET",
        headers={"Cookie": f"langbot_dbmode_sse={cookie_value}"},
        scheme=scheme,
    ) as connection:
        initial_chunk = await connection.receive()
        assert b"event: ready\n" in initial_chunk
        event = DatabaseModeEvent(
            type=DatabaseModeEventType.MESSAGE_CREATED,
            message_id=7,
            occurred_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        )
        await ap.database_mode_event_bus.publish(event)
        business_chunk, observed_chunks = await _receive_until(
            connection,
            lambda chunk: b"event: database-message-created\n" in chunk,
        )
        assert b"event: database-message-created\n" in business_chunk
        assert f'"message_id": {event.message_id}'.encode() in business_chunk
        assert any(chunk == b": heartbeat\n\n" for chunk in observed_chunks[:-1]) or observed_chunks[0] == business_chunk
        heartbeat_chunk, _ = await _receive_until(
            connection,
            lambda chunk: chunk == b": heartbeat\n\n",
        )
        assert heartbeat_chunk == b": heartbeat\n\n"
        await connection.disconnect()
        ap.database_mode_event_bus.close()
        response = await connection.as_response()

    assert response.status_code == 200
    assert ap.database_mode_event_bus.subscriber_count == 0


async def test_stream_shutdown_sentinel_ends_stream_and_cleans_subscriber(monkeypatch):
    _app, client, ap, scheme = await _make_client()
    monkeypatch.setattr(database_mode_module, "DATABASE_MODE_SSE_HEARTBEAT_INTERVAL_SECONDS", 0.01)
    cookie_value = await _create_sse_cookie(client, scheme)

    async with client.request(
        "/api/v1/database-mode/events",
        method="GET",
        headers={"Cookie": f"langbot_dbmode_sse={cookie_value}"},
        scheme=scheme,
    ) as connection:
        initial_chunk = await connection.receive()
        assert b"event: ready\n" in initial_chunk
        assert ap.database_mode_event_bus.subscriber_count == 1
        ap.database_mode_event_bus.close()
        terminal_chunk, observed_chunks = await _receive_until(
            connection,
            lambda chunk: chunk == b"",
        )
        response = await connection.as_response()

    assert terminal_chunk == b""
    assert any(chunk == b": heartbeat\n\n" for chunk in observed_chunks[:-1]) or observed_chunks == [b""]
    assert response.status_code == 200
    assert ap.database_mode_event_bus.subscriber_count == 0


async def test_sse_preflight_returns_credentialed_cors_headers_for_allowed_origin():
    _app, client, _ap, scheme = await _make_client()
    origin = "http://127.0.0.1:3000"

    response = await client.options(
        "/api/v1/database-mode/events/session",
        headers={
            "Origin": origin,
            "Host": "127.0.0.1:5300",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Authorization, Content-Type",
        },
        scheme=scheme,
    )

    assert response.status_code == 200
    assert response.headers["Access-Control-Allow-Origin"] == origin
    assert response.headers["Access-Control-Allow-Credentials"] == "true"
    assert response.headers["Access-Control-Allow-Methods"] == "POST, GET, OPTIONS"
    assert response.headers["Access-Control-Allow-Headers"] == "Authorization, Content-Type"
    assert response.headers["Vary"] == "Origin"


async def test_sse_handshake_returns_precise_origin_and_cookie_for_allowed_origin():
    _app, client, _ap, scheme = await _make_client()
    origin = "http://127.0.0.1:3000"

    response = await client.post(
        "/api/v1/database-mode/events/session",
        headers={
            "Origin": origin,
            "Host": "127.0.0.1:5300",
            "Authorization": "Bearer valid-user-token",
        },
        scheme=scheme,
    )

    assert response.status_code == 204
    assert response.headers["Access-Control-Allow-Origin"] == origin
    assert response.headers["Access-Control-Allow-Credentials"] == "true"
    assert response.headers["Vary"] == "Origin"
    assert response.headers.get("Set-Cookie") is not None
    assert response.headers["Access-Control-Allow-Origin"] != "*"


async def test_sse_handshake_rejects_disallowed_origin():
    _app, client, _ap, scheme = await _make_client()

    response = await client.post(
        "/api/v1/database-mode/events/session",
        headers={
            "Origin": "http://localhost:3000",
            "Host": "127.0.0.1:5300",
            "Authorization": "Bearer valid-user-token",
        },
        scheme=scheme,
    )

    assert response.status_code == 403
    assert response.headers.get("Access-Control-Allow-Origin") is None
    assert response.headers.get("Access-Control-Allow-Credentials") is None
    assert response.headers["Vary"] == "Origin"


async def test_sse_stream_error_response_still_includes_credentialed_cors_headers():
    _app, client, _ap, scheme = await _make_client()
    origin = "http://127.0.0.1:3000"

    response = await client.get(
        "/api/v1/database-mode/events",
        headers={
            "Origin": origin,
            "Host": "127.0.0.1:5300",
        },
        scheme=scheme,
    )
    payload = await response.get_json()

    assert response.status_code == 401
    assert payload["msg"] == "Missing SSE session cookie"
    assert response.headers["Access-Control-Allow-Origin"] == origin
    assert response.headers["Access-Control-Allow-Credentials"] == "true"
    assert response.headers["Vary"] == "Origin"


async def test_bot_scoped_conversations_are_filtered_by_connector_id():
    app, client, ap, _persistence_mgr = await _make_bot_client()

    response = await client.get(
        "/api/v1/bots/bot-1/conversations",
        headers={"Authorization": "Bearer valid-user-token"},
    )
    payload = await response.get_json()

    assert response.status_code == 200
    assert payload["data"]["total"] == 1
    assert [conversation["connector_id"] for conversation in payload["data"]["conversations"]] == ["wxwork-local"]


async def test_bot_scoped_messages_reject_other_connector_conversation():
    _app, client, ap, _persistence_mgr = await _make_bot_client()

    response = await client.get(
        "/api/v1/bots/bot-1/conversations/2/messages",
        headers={"Authorization": "Bearer valid-user-token"},
    )
    payload = await response.get_json()

    assert response.status_code == 404
    assert payload["msg"] == "Conversation does not belong to bot"


async def test_bot_scoped_generate_draft_returns_200_with_real_processing_service():
    _app, client, ap, persistence_mgr = await _make_bot_client_with_processing_service()

    response = await client.post(
        "/api/v1/bots/bot-1/messages/1/generate-draft",
        headers={"Authorization": "Bearer valid-user-token"},
    )
    payload = await response.get_json()

    assert response.status_code == 200
    assert payload["data"]["status"] == "succeeded"
    assert payload["data"]["draft"]["message_id"] == 1
    assert payload["data"]["run"]["status"] == "succeeded"

    message_result = await ap.persistence_mgr.execute_async(
        sqlalchemy.select(
            persistence_database_mode.DatabaseMessage.status,
            persistence_database_mode.DatabaseMessage.draft_text,
            persistence_database_mode.DatabaseMessage.draft_source,
        ).where(persistence_database_mode.DatabaseMessage.id == 1)
    )
    message_row = message_result.mappings().first()
    assert dict(message_row) == {
        "status": "draft_ready",
        "draft_text": "Pipeline generated draft",
        "draft_source": "pipeline",
    }

    await persistence_mgr.dispose()


async def test_bot_scoped_generate_draft_processing_returns_200_with_active_run_payload():
    _app, client, ap, persistence_mgr = await _make_bot_client_with_processing_service()

    ap.database_mode_processing_service = SimpleNamespace(
        generate_draft=AsyncMock(return_value={
            'status': 'processing',
            'message_id': 1,
            'message': 'Draft generation is already in progress',
            'run': {
                'id': 41,
                'status': 'processing',
                'started_at': '2026-06-27T00:00:00+00:00',
                'attempt_count': 2,
            },
        })
    )

    response = await client.post(
        "/api/v1/bots/bot-1/messages/1/generate-draft",
        headers={"Authorization": "Bearer valid-user-token"},
    )
    payload = await response.get_json()

    assert response.status_code == 200
    assert payload["data"] == {
        'status': 'processing',
        'message_id': 1,
        'message': 'Draft generation is already in progress',
        'run': {
            'id': 41,
            'status': 'processing',
            'started_at': '2026-06-27T00:00:00+00:00',
            'attempt_count': 2,
        },
    }

    await persistence_mgr.dispose()


async def test_bot_scoped_generate_draft_already_succeeded_returns_200_with_existing_draft():
    _app, client, ap, persistence_mgr = await _make_bot_client_with_processing_service()

    ap.database_mode_processing_service = SimpleNamespace(
        generate_draft=AsyncMock(return_value={
            'status': 'already_succeeded',
            'draft': {
                'id': 71,
                'message_id': 1,
                'content': 'Existing draft payload',
                'source': 'pipeline',
                'version': 2,
                'status': 'active',
                'created_at': '2026-06-27T00:00:00+00:00',
                'updated_at': '2026-06-27T00:00:01+00:00',
            },
            'run': {
                'id': 72,
                'message_id': 1,
                'bot_uuid': 'bot-1',
                'trigger': 'manual',
                'status': 'succeeded',
                'attempt_count': 2,
            },
        })
    )

    response = await client.post(
        "/api/v1/bots/bot-1/messages/1/generate-draft",
        headers={"Authorization": "Bearer valid-user-token"},
    )
    payload = await response.get_json()

    assert response.status_code == 200
    assert payload["data"]["status"] == "already_succeeded"
    assert payload["data"]["draft"]["content"] == "Existing draft payload"
    assert payload["data"]["run"]["status"] == "succeeded"

    await persistence_mgr.dispose()


async def test_bot_scoped_generate_draft_failure_returns_json_not_html():
    _app, client, ap, persistence_mgr = await _make_bot_client_with_processing_service()

    class _FailingPipeline:
        pipeline_entity = SimpleNamespace(config={})

        async def run(self, query):
            raise ValueError("pipeline exploded")

    ap.pipeline_mgr = SimpleNamespace(get_pipeline_by_uuid=AsyncMock(return_value=_FailingPipeline()))

    response = await client.post(
        "/api/v1/bots/bot-1/messages/1/generate-draft",
        headers={"Authorization": "Bearer valid-user-token"},
    )
    payload = await response.get_json()
    text = await response.get_data(as_text=True)

    assert response.status_code == 500
    assert response.content_type.startswith("application/json")
    assert payload["code"] == -2
    assert "ValueError: pipeline exploded" in payload["msg"]
    assert "<html" not in text.lower()

    await persistence_mgr.dispose()


async def test_database_mode_list_conversations_keeps_all_connectors():
    app, client, ap, persistence_mgr = await _make_legacy_database_mode_client()

    response = await client.get(
        "/api/v1/database-mode/conversations",
        headers={"Authorization": "Bearer valid-user-token"},
    )
    payload = await response.get_json()

    assert response.status_code == 200
    assert payload["data"]["total"] == 2
    await persistence_mgr.dispose()
