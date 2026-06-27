from __future__ import annotations

import asyncio
import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
import sqlalchemy
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncTransaction, create_async_engine

import langbot_plugin.api.definition.abstract.platform.event_logger as abstract_platform_logger
import langbot_plugin.api.entities.builtin.platform.message as platform_message
from langbot.pkg.database_mode.events import DatabaseModeEventBus, DatabaseModeEventType
from langbot.pkg.database_mode.processing_service import (
    DRAFT_STATUS_ACTIVE,
    DRAFT_STATUS_SUPERSEDED,
    DatabaseModeProcessingService,
    RUN_STATUS_FAILED,
    RUN_STATUS_PROCESSING,
)
from langbot.pkg.database_mode.service import (
    DatabaseModeService,
    MESSAGE_STATUS_DRAFT_READY,
    MESSAGE_STATUS_FAILED,
    MESSAGE_STATUS_PENDING,
    MESSAGE_STATUS_PROCESSED,
    MESSAGE_STATUS_SKIPPED,
)
from langbot.pkg.entity.persistence import bot as persistence_bot
from langbot.pkg.entity.persistence import pipeline as persistence_pipeline
from langbot.pkg.entity.persistence import database_mode as persistence_database_mode
from langbot.pkg.pipeline.aggregator import MessageAggregator
from langbot.pkg.pipeline.controller import Controller
from langbot.pkg.pipeline import entities as pipeline_entities
from langbot.pkg.pipeline.pipelinemgr import RuntimePipeline, StageInstContainer
from langbot.pkg.pipeline.pool import QueryPool
from langbot.pkg.platform.botmgr import RuntimeBot
from langbot.pkg.platform.sources.wxwork_database import WXWorkDatabaseAdapter
from langbot.pkg.provider.session.sessionmgr import SessionManager


pytestmark = pytest.mark.asyncio


def test_database_mode_persistence_exposes_channel_binding_and_draft_entities():
    assert hasattr(persistence_database_mode, 'ChannelAccount')
    assert hasattr(persistence_database_mode, 'BotChannelBinding')
    assert hasattr(persistence_database_mode, 'MessageProcessingRun')
    assert hasattr(persistence_database_mode, 'ReplyDraft')


class RecordingEventBus(DatabaseModeEventBus):
    def __init__(self) -> None:
        super().__init__()
        self.published_events = []

    async def publish(self, event) -> None:
        self.published_events.append(event)
        await super().publish(event)


class DummyEventLogger(abstract_platform_logger.AbstractEventLogger):
    async def info(self, text, images=None, message_session_id=None, no_throw=True):
        return None

    async def debug(self, text, images=None, message_session_id=None, no_throw=True):
        return None

    async def warning(self, text, images=None, message_session_id=None, no_throw=True):
        return None

    async def error(self, text, images=None, message_session_id=None, no_throw=True):
        return None


class DummySyncLogger:
    def __init__(self) -> None:
        self.records = []

    def info(self, payload, *args, **kwargs):
        self.records.append(('info', payload))

    def debug(self, payload, *args, **kwargs):
        self.records.append(('debug', payload))

    def warning(self, payload, *args, **kwargs):
        self.records.append(('warning', payload))

    def error(self, payload, *args, **kwargs):
        self.records.append(('error', payload))

    def exception(self, payload, *args, **kwargs):
        self.records.append(('exception', payload))


def _event_context():
    event = SimpleNamespace(reply_message_chain=None, user_message_alter=None)
    return SimpleNamespace(
        event=event,
        is_prevented_default=Mock(return_value=False),
    )


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


async def _install_formal_runtime_processing(
    ap,
    *,
    pipeline,
    adapter: WXWorkDatabaseAdapter,
    bot_uuid: str = 'bot-enabled',
    pipeline_uuid: str = 'pipeline-123',
):
    if not hasattr(ap, 'instance_config'):
        ap.instance_config = SimpleNamespace(data={})
    ap.instance_config.data.setdefault('concurrency', {'pipeline': 2, 'session': 1})
    ap.logger = getattr(ap, 'logger', DummySyncLogger())
    ap.query_pool = getattr(ap, 'query_pool', None) or QueryPool()
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
    return runtime_bot


async def _run_mock_pipeline_now(
    ap,
    event,
    *,
    adapter,
    pipeline_uuid: str = 'pipeline-123',
    bot_uuid: str = 'bot-enabled',
    launcher_id: str = 'S:100_200',
    sender_id: str = '201',
):
    query_id = getattr(ap, '_test_query_id_counter', 0)
    ap._test_query_id_counter = query_id + 1
    query = SimpleNamespace(
        bot_uuid=bot_uuid,
        query_id=query_id,
        launcher_type=SimpleNamespace(value='person'),
        launcher_id=launcher_id,
        sender_id=sender_id,
        message_event=event,
        message_chain=event.message_chain,
        adapter=adapter,
        pipeline_uuid=pipeline_uuid,
        variables={},
        resp_messages=[],
        resp_message_chain=[],
    )

    pipeline = await ap.pipeline_mgr.get_pipeline_by_uuid(pipeline_uuid)
    pipeline_result = await pipeline.run(query)
    new_query = getattr(pipeline_result, 'new_query', None)
    if new_query is not None:
        if not hasattr(new_query, 'query_id'):
            new_query.query_id = query.query_id
        if not hasattr(new_query, 'variables') or new_query.variables is None:
            new_query.variables = dict(query.variables)
        if not hasattr(new_query, 'adapter'):
            new_query.adapter = adapter
        if not hasattr(new_query, 'message_event'):
            new_query.message_event = event
        if not hasattr(new_query, 'resp_messages') or new_query.resp_messages is None:
            new_query.resp_messages = []
        return new_query
    return query


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
            await conn.run_sync(persistence_database_mode.ChannelAccount.__table__.create)
            await conn.run_sync(persistence_database_mode.BotChannelBinding.__table__.create)
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

    async def dispose(self) -> None:
        await self.engine.dispose()

    async def execute_async(self, *args, conn: AsyncConnection | None = None, **kwargs):
        if conn is not None:
            return await conn.execute(*args, **kwargs)

        async with self.engine.connect() as standalone_conn:
            result = await standalone_conn.execute(*args, **kwargs)

            # For SELECT queries that return ORM objects, we need to materialize them before commit
            # because SQLAlchemy's lazy loading won't work after the connection closes
            if result.returns_rows:
                # Materialize all data structures that might need lazy loading
                # We need to handle both scalar queries and Row queries
                try:
                    # Try to get all rows first
                    all_rows = list(result.all())

                    # Force load all attributes on ORM objects to prevent lazy loading issues
                    for row in all_rows:
                        if hasattr(row, '__dict__'):
                            # It's an ORM object, touch all columns to load them
                            for key in row.__dict__.keys():
                                if not key.startswith('_'):
                                    getattr(row, key, None)
                        elif hasattr(row, '_mapping'):
                            # It's a Row object, touch all values
                            for value in row._mapping.values():
                                if hasattr(value, '__dict__'):
                                    for key in value.__dict__.keys():
                                        if not key.startswith('_'):
                                            getattr(value, key, None)

                    # Create a simple proxy that holds the materialized rows
                    class _MaterializedResult:
                        def __init__(self, rows):
                            self._all_rows = rows
                            self._index = 0

                        def scalars(self):
                            # Return self to support chaining
                            return self

                        def first(self):
                            return self._all_rows[0] if self._all_rows else None

                        def all(self):
                            return self._all_rows

                        def scalar(self):
                            first = self.first()
                            # For scalar queries, extract the actual value
                            if hasattr(first, '_mapping') and len(first._mapping) == 1:
                                return list(first._mapping.values())[0]
                            return first

                        def scalar_one(self):
                            # Return scalar value and raise if none or multiple
                            if len(self._all_rows) == 0:
                                from sqlalchemy.exc import NoResultFound
                                raise NoResultFound()
                            if len(self._all_rows) > 1:
                                from sqlalchemy.exc import MultipleResultsFound
                                raise MultipleResultsFound()
                            first = self._all_rows[0]
                            if hasattr(first, '_mapping') and len(first._mapping) == 1:
                                return list(first._mapping.values())[0]
                            return first

                        def scalars(self):
                            # Return values directly without tuple wrapping
                            class _ScalarsResult:
                                def __init__(self, rows):
                                    self._rows = rows

                                def all(self):
                                    result = []
                                    for row in self._rows:
                                        if hasattr(row, '_mapping') and len(row._mapping) == 1:
                                            result.append(list(row._mapping.values())[0])
                                        elif isinstance(row, tuple) and len(row) == 1:
                                            result.append(row[0])
                                        else:
                                            result.append(row)
                                    return result

                                def first(self):
                                    all_vals = self.all()
                                    return all_vals[0] if all_vals else None

                            return _ScalarsResult(self._all_rows)

                        def mappings(self):
                            class _MappingsResult:
                                def __init__(self, rows):
                                    self._rows = rows

                                def all(self):
                                    mappings = []
                                    for row in self._rows:
                                        if hasattr(row, '_mapping'):
                                            mappings.append(row._mapping)
                                        else:
                                            mappings.append(row)
                                    return mappings

                                def first(self):
                                    all_vals = self.all()
                                    return all_vals[0] if all_vals else None

                            return _MappingsResult(self._all_rows)

                        @property
                        def returns_rows(self):
                            return True

                        @property
                        def rowcount(self):
                            return len(self._all_rows)

                        @property
                        def inserted_primary_key(self):
                            # For INSERT statements
                            return None

                        @property
                        def lastrowid(self):
                            # For INSERT statements
                            return None

                        def __iter__(self):
                            return iter(self._all_rows)

                    materialized = _MaterializedResult(all_rows)
                    await standalone_conn.commit()
                    return materialized

                except Exception:
                    # If materialization fails, fall back to commit and return original result
                    await standalone_conn.commit()
                    return result
            else:
                # For non-SELECT queries (INSERT, UPDATE, DELETE), commit normally
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


class RawConnectionPersistenceManager:
    """Mirror production execute_async semantics for connection-level SELECT results."""

    def __init__(self) -> None:
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        self.engine_proxy = _EngineProxy(self, self.engine)
        self.fail_next_commit = False

    async def initialize(self) -> None:
        async with self.engine.begin() as conn:
            await conn.run_sync(persistence_database_mode.LocalConnectorEvent.__table__.create)
            await conn.run_sync(persistence_database_mode.DatabaseConversation.__table__.create)
            await conn.run_sync(persistence_database_mode.DatabaseMessage.__table__.create)
            await conn.run_sync(persistence_database_mode.ChannelAccount.__table__.create)
            await conn.run_sync(persistence_database_mode.BotChannelBinding.__table__.create)
            await conn.run_sync(persistence_database_mode.MessageProcessingRun.__table__.create)
            await conn.run_sync(persistence_database_mode.ReplyDraft.__table__.create)
            await conn.run_sync(persistence_bot.Bot.__table__.create)
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


@pytest.fixture
async def raw_processing_app():
    persistence_mgr = RawConnectionPersistenceManager()
    await persistence_mgr.initialize()
    ap = SimpleNamespace(
        persistence_mgr=persistence_mgr,
        model_mgr=SimpleNamespace(llm_models=[]),
        database_mode_event_bus=RecordingEventBus(),
    )
    try:
        yield ap
    finally:
        await ap.persistence_mgr.dispose()


def _sample_payload(*, conversation_type: str = "direct") -> dict:
    return {
        "connector_id": "wxwork-local",
        "source": "wxwork",
        "event_id": "wxwork-local:evt-1",
        "message_key": "wxwork:key-1",
        "conversation": {
            "external_conversation_id": "S:100_200",
            "conversation_name": "Customer A",
            "conversation_type": conversation_type,
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


def _fake_message_chain(text: str) -> platform_message.MessageChain:
    return platform_message.MessageChain([platform_message.Plain(text=text)])


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


async def _insert_bound_message(
    ap,
    *,
    bot_uuid: str = 'bot-enabled',
    account_suffix: str,
    conversation_suffix: str,
    message_suffix: str,
    content: str,
    sender_id: str,
    sender_name: str,
) -> int:
    async with ap.persistence_mgr.get_db_engine().begin() as conn:
        existing_bot = (
            await conn.execute(
                sqlalchemy.select(persistence_bot.Bot.uuid).where(
                    persistence_bot.Bot.uuid == bot_uuid
                )
            )
        ).first()
        if existing_bot is None:
            await conn.execute(
                sqlalchemy.insert(persistence_bot.Bot).values({
                    'uuid': bot_uuid,
                    'name': 'Database Bot',
                    'description': '',
                    'adapter': 'wxwork_database',
                    'adapter_config': {'connector_id': 'wxwork-local'},
                    'enable': True,
                    'use_pipeline_name': None,
                    'use_pipeline_uuid': 'pipeline-123',
                    'pipeline_routing_rules': [],
                })
            )
        channel_account_result = await conn.execute(
            sqlalchemy.insert(persistence_database_mode.ChannelAccount).values({
                'connector_id': 'wxwork-local',
                'channel_type': 'wxwork',
                'external_account_id': f'acc-{account_suffix}',
                'display_name': 'Raw Account',
                'enabled': True,
            })
        )
        channel_account_id = channel_account_result.inserted_primary_key[0]
        await conn.execute(
            sqlalchemy.insert(persistence_database_mode.BotChannelBinding).values({
                'bot_uuid': bot_uuid,
                'channel_account_id': channel_account_id,
                'enabled': True,
                'auto_generate_draft': False,
            })
        )
        conversation_result = await conn.execute(
            sqlalchemy.insert(persistence_database_mode.DatabaseConversation).values({
                'connector_id': 'wxwork-local',
                'source': 'wxwork',
                'external_conversation_id': f'S:100_{conversation_suffix}',
                'conversation_name': f'Customer {conversation_suffix}',
                'conversation_type': 'direct',
            })
        )
        conversation_id = conversation_result.inserted_primary_key[0]
        message_result = await conn.execute(
            sqlalchemy.insert(persistence_database_mode.DatabaseMessage).values({
                'event_id': f'wxwork-local:evt-{message_suffix}',
                'message_key': f'wxwork-local:key-{message_suffix}',
                'conversation_id': conversation_id,
                'external_message_id': message_suffix,
                'sender_id': sender_id,
                'sender_name': sender_name,
                'content': content,
                'message_type': 'text',
                'sent_at': datetime.datetime.now(datetime.timezone.utc),
                'observed_at': datetime.datetime.now(datetime.timezone.utc),
                'status': MESSAGE_STATUS_PENDING,
            })
        )
        return message_result.inserted_primary_key[0]


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


@pytest.mark.parametrize(
    ("raw_conversation_type", "expected_conversation_type"),
    [
        ("单聊", "direct"),
        ("群组", "group"),
    ],
)
async def test_ingest_internal_event_normalizes_conversation_type_aliases(
    service_app,
    raw_conversation_type,
    expected_conversation_type,
):
    service, _ap = service_app

    await service.ingest_internal_event(_sample_payload(conversation_type=raw_conversation_type))

    conversations = await service.list_conversations()

    assert conversations["conversations"][0]["conversation_type"] == expected_conversation_type


async def test_ingest_internal_event_rejects_unknown_conversation_type(service_app):
    service, ap = service_app

    with pytest.raises(ValueError, match="Unsupported conversation type: weird_type"):
        await service.ingest_internal_event(_sample_payload(conversation_type="weird_type"))

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

    assert conversation_count == 0
    assert message_count == 0


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

    # Mock processing service to simulate successful draft generation
    async def mock_generate_draft(msg_id, bot_uuid, trigger='manual'):
        # Simulate what processing service does - update message and return result
        async with ap.persistence_mgr.get_db_engine().begin() as conn:
            await conn.execute(
                sqlalchemy.update(persistence_database_mode.DatabaseMessage)
                .where(persistence_database_mode.DatabaseMessage.id == msg_id)
                .values({
                    'status': MESSAGE_STATUS_DRAFT_READY,
                    'draft_text': 'Thanks, we will follow up shortly.',
                    'draft_source': 'pipeline',
                })
            )
        return {'status': 'succeeded'}

    ap.database_mode_processing_service = SimpleNamespace(generate_draft=mock_generate_draft)
    ap.bot_service = SimpleNamespace(
        get_bots=AsyncMock(return_value=[{
            'uuid': 'bot-1',
            'adapter': 'wxwork_database',
            'enable': True,
            'adapter_config': {'connector_id': 'wxwork-local'}
        }])
    )
    ap.database_mode_event_bus.published_events.clear()

    updated = await service.generate_draft(message_id)

    assert updated["status"] == MESSAGE_STATUS_DRAFT_READY
    assert updated["draft_text"] == "Thanks, we will follow up shortly."
    assert updated["draft_source"] == "pipeline"


async def test_generate_draft_delegates_to_processing_service(service_app):
    service, ap = service_app
    _, message_id = await _ingest_and_get_message(service)

    # Mock bot service to return enabled bot
    ap.bot_service = SimpleNamespace(
        get_bots=AsyncMock(return_value=[{
            'uuid': 'bot-1',
            'adapter': 'wxwork_database',
            'enable': True,
            'adapter_config': {'connector_id': 'wxwork-local'}
        }])
    )

    # Mock processing service
    async def mock_generate_draft(msg_id, bot_uuid, trigger='manual'):
        # Update the message to draft_ready
        async with ap.persistence_mgr.get_db_engine().begin() as conn:
            await conn.execute(
                sqlalchemy.update(persistence_database_mode.DatabaseMessage)
                .where(persistence_database_mode.DatabaseMessage.id == msg_id)
                .values({
                    'status': MESSAGE_STATUS_DRAFT_READY,
                    'draft_text': 'Pipeline generated reply',
                    'draft_source': 'pipeline',
                })
            )
        return {'status': 'succeeded'}

    ap.database_mode_processing_service = SimpleNamespace(generate_draft=mock_generate_draft)

    message = await service.generate_draft(message_id)

    assert message['id'] == message_id
    assert message['draft_text'] == 'Pipeline generated reply'
    assert message['draft_source'] == 'pipeline'


async def test_processing_service_generate_draft_uses_enabled_wxwork_database_bot_pipeline(service_app):
    """Test that processing service uses formal RuntimeBot/Pipeline path."""
    service, ap = service_app
    conversation_id, message_id = await _ingest_and_get_message(service)

    # Verify message was created correctly
    messages = await service.list_messages(conversation_id)
    assert len(messages['messages']) == 1

    captured = {}

    # Mock RuntimeBot with resolve_pipeline_uuid
    class _MockRuntimeBot:
        def __init__(self):
            self.bot_entity = SimpleNamespace(uuid='bot-enabled', use_pipeline_uuid='pipeline-123')
            self.adapter = SimpleNamespace(
                reply_message=AsyncMock(return_value={'status': 'draft_ready', 'content': 'Reply', 'is_final': True}),
                reply_message_chunk=AsyncMock(return_value={'status': 'draft_ready', 'content': 'Reply', 'is_final': True}),
            )

        def resolve_pipeline_uuid(self, launcher_type, launcher_id, message_text, message_element_types=None):
            return 'pipeline-123', False

        async def process_message_event_now(self, event, **kwargs):
            return await _run_mock_pipeline_now(ap, event, adapter=self.adapter)

    # Mock Pipeline that captures query details
    class _FakePipeline:
        pipeline_entity = SimpleNamespace(config={})

        async def run(self, query):
            captured['bot_uuid'] = query.bot_uuid
            captured['pipeline_uuid'] = query.pipeline_uuid
            query.resp_message_chain = [platform_message.Plain(text='Pipeline generated draft')]

    # Set up all required mocks
    mock_runtime_bot = _MockRuntimeBot()
    ap.platform_mgr = SimpleNamespace(bots=[mock_runtime_bot])
    ap.pipeline_mgr = SimpleNamespace(get_pipeline_by_uuid=AsyncMock(return_value=_FakePipeline()))
    ap.query_pool = SimpleNamespace(add_query=AsyncMock(side_effect=lambda **kw: SimpleNamespace(**kw)))
    ap.bot_service = SimpleNamespace(
        get_bot=AsyncMock(return_value={
            'uuid': 'bot-enabled',
            'adapter': 'wxwork_database',
            'enable': True,
            'adapter_config': {'connector_id': 'wxwork-local'}
        })
    )
    ap.database_mode_event_bus = RecordingEventBus()
    ap.task_mgr = SimpleNamespace(create_task=lambda coro, **kw: None)

    # Create channel account and binding in database
    async with ap.persistence_mgr.get_db_engine().begin() as conn:
        result = await conn.execute(
            sqlalchemy.insert(persistence_database_mode.ChannelAccount).values({
                'connector_id': 'wxwork-local',
                'channel_type': 'wxwork',
                'external_account_id': 'acc-1',
                'display_name': 'Test Account',
                'enabled': True,
            })
        )
        channel_account_id = result.inserted_primary_key[0]
        await conn.execute(
            sqlalchemy.insert(persistence_database_mode.BotChannelBinding).values({
                'bot_uuid': 'bot-enabled',
                'channel_account_id': channel_account_id,
                'enabled': True,
                'auto_generate_draft': False,
            })
        )

    processing_service = DatabaseModeProcessingService(ap)
    result = await processing_service.generate_draft(message_id, 'bot-enabled', trigger='manual')

    assert result['status'] == 'succeeded'
    assert captured['bot_uuid'] == 'bot-enabled'
    assert captured['pipeline_uuid'] == 'pipeline-123'

    # Verify the message was updated
    updated_message = await service.get_message(message_id)
    assert updated_message['status'] == MESSAGE_STATUS_DRAFT_READY


async def test_processing_service_generate_draft_reuses_runtime_bot_entry_for_launcher_resolution(
    raw_processing_app,
):
    ap = raw_processing_app
    processing_service = DatabaseModeProcessingService(ap)

    class _LauncherAwareAdapter(WXWorkDatabaseAdapter):
        def get_launcher_id(self, event):
            return 'custom-launcher'

    adapter = _LauncherAwareAdapter(config={'connector_id': 'wxwork-local'}, logger=DummyEventLogger())

    class _FormalOnlyPipeline:
        pipeline_entity = SimpleNamespace(config=_runtime_pipeline_config())

        async def run(self, query):
            if query.launcher_id != 'custom-launcher':
                return None
            await query.adapter.reply_message(
                message_source=query.message_event,
                message=platform_message.MessageChain([platform_message.Plain(text='Formal runtime entry draft')]),
            )

    await _install_formal_runtime_processing(ap, pipeline=_FormalOnlyPipeline(), adapter=adapter)
    ap.bot_service = SimpleNamespace(
        get_bot=AsyncMock(return_value={
            'uuid': 'bot-enabled',
            'adapter': 'wxwork_database',
            'enable': True,
            'adapter_config': {'connector_id': 'wxwork-local'},
        })
    )

    message_id = await _insert_bound_message(
        ap,
        account_suffix='formal-runtime',
        conversation_suffix='700',
        message_suffix='111',
        content='Need formal runtime entry',
        sender_id='209',
        sender_name='Customer J',
    )

    result = await processing_service.generate_draft(message_id, 'bot-enabled', trigger='manual')

    assert result['status'] == 'succeeded'
    assert result['draft']['content'] == 'Formal runtime entry draft'


async def test_processing_service_generate_draft_preserves_capture_inside_async_child_task(
    raw_processing_app,
):
    ap = raw_processing_app
    processing_service = DatabaseModeProcessingService(ap)
    adapter = WXWorkDatabaseAdapter(config={'connector_id': 'wxwork-local'}, logger=DummyEventLogger())

    class _TaskReplyPipeline:
        pipeline_entity = SimpleNamespace(config=_runtime_pipeline_config())

        async def run(self, query):
            async def _reply():
                await query.adapter.reply_message(
                    message_source=query.message_event,
                    message=platform_message.MessageChain([platform_message.Plain(text='Async child task draft')]),
                )

            await asyncio.create_task(_reply())

    await _install_formal_runtime_processing(ap, pipeline=_TaskReplyPipeline(), adapter=adapter)
    ap.bot_service = SimpleNamespace(
        get_bot=AsyncMock(return_value={
            'uuid': 'bot-enabled',
            'adapter': 'wxwork_database',
            'enable': True,
            'adapter_config': {'connector_id': 'wxwork-local'},
        })
    )

    message_id = await _insert_bound_message(
        ap,
        account_suffix='child-task',
        conversation_suffix='701',
        message_suffix='112',
        content='Need async task reply',
        sender_id='210',
        sender_name='Customer K',
    )

    result = await processing_service.generate_draft(message_id, 'bot-enabled', trigger='manual')

    assert result['status'] == 'succeeded'
    assert result['draft']['content'] == 'Async child task draft'


async def test_processing_service_generate_draft_never_calls_real_send_message(raw_processing_app):
    ap = raw_processing_app
    processing_service = DatabaseModeProcessingService(ap)

    class _SpyAdapter(WXWorkDatabaseAdapter):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            object.__setattr__(self, 'send_message_mock', AsyncMock())

        async def send_message(self, target_type: str, target_id: str, message):
            await self.send_message_mock(target_type, target_id, message)
            return await super().send_message(target_type, target_id, message)

    adapter = _SpyAdapter(config={'connector_id': 'wxwork-local'}, logger=DummyEventLogger())

    class _ReplyPipeline:
        pipeline_entity = SimpleNamespace(config=_runtime_pipeline_config())

        async def run(self, query):
            await query.adapter.reply_message(
                message_source=query.message_event,
                message=platform_message.MessageChain([platform_message.Plain(text='No active send happened')]),
            )

    await _install_formal_runtime_processing(ap, pipeline=_ReplyPipeline(), adapter=adapter)
    ap.bot_service = SimpleNamespace(
        get_bot=AsyncMock(return_value={
            'uuid': 'bot-enabled',
            'adapter': 'wxwork_database',
            'enable': True,
            'adapter_config': {'connector_id': 'wxwork-local'},
        })
    )

    message_id = await _insert_bound_message(
        ap,
        account_suffix='no-send',
        conversation_suffix='702',
        message_suffix='113',
        content='Need draft only',
        sender_id='211',
        sender_name='Customer L',
    )

    result = await processing_service.generate_draft(message_id, 'bot-enabled', trigger='manual')

    assert result['status'] == 'succeeded'
    adapter.send_message_mock.assert_not_awaited()


async def test_processing_service_generate_draft_keeps_concurrent_drafts_isolated(raw_processing_app):
    ap = raw_processing_app
    processing_service = DatabaseModeProcessingService(ap)
    adapter = WXWorkDatabaseAdapter(config={'connector_id': 'wxwork-local'}, logger=DummyEventLogger())

    class _ConcurrentPipeline:
        pipeline_entity = SimpleNamespace(config=_runtime_pipeline_config())

        async def run(self, query):
            draft_text = f'Draft for {query.sender_id}'

            async def _reply():
                await query.adapter.reply_message(
                    message_source=query.message_event,
                    message=platform_message.MessageChain([platform_message.Plain(text=draft_text)]),
                )

            await asyncio.create_task(_reply())

    await _install_formal_runtime_processing(ap, pipeline=_ConcurrentPipeline(), adapter=adapter)
    ap.bot_service = SimpleNamespace(
        get_bot=AsyncMock(return_value={
            'uuid': 'bot-enabled',
            'adapter': 'wxwork_database',
            'enable': True,
            'adapter_config': {'connector_id': 'wxwork-local'},
        })
    )

    left_message_id = await _insert_bound_message(
        ap,
        account_suffix='concurrent-left',
        conversation_suffix='703',
        message_suffix='114',
        content='Need left draft',
        sender_id='301',
        sender_name='Customer M',
    )
    right_message_id = await _insert_bound_message(
        ap,
        account_suffix='concurrent-right',
        conversation_suffix='704',
        message_suffix='115',
        content='Need right draft',
        sender_id='302',
        sender_name='Customer N',
    )

    left_result, right_result = await asyncio.gather(
        processing_service.generate_draft(left_message_id, 'bot-enabled', trigger='manual'),
        processing_service.generate_draft(right_message_id, 'bot-enabled', trigger='manual'),
    )

    assert left_result['draft']['content'] == 'Draft for 301'
    assert right_result['draft']['content'] == 'Draft for 302'


async def test_processing_service_generate_draft_returns_active_run_for_recent_processing(raw_processing_app):
    ap = raw_processing_app
    processing_service = DatabaseModeProcessingService(ap)

    message_id = await _insert_bound_message(
        ap,
        account_suffix='recent-processing',
        conversation_suffix='705',
        message_suffix='116',
        content='Need recent processing status',
        sender_id='303',
        sender_name='Customer O',
    )

    started_at = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
    async with ap.persistence_mgr.get_db_engine().begin() as conn:
        run_result = await conn.execute(
            sqlalchemy.insert(persistence_database_mode.MessageProcessingRun).values({
                'message_id': message_id,
                'bot_uuid': 'bot-enabled',
                'pipeline_uuid': None,
                'trigger': 'manual',
                'status': RUN_STATUS_PROCESSING,
                'attempt_count': 2,
                'started_at': started_at,
                'completed_at': None,
                'last_error': None,
            })
        )
        run_id = run_result.inserted_primary_key[0]

    result = await processing_service.generate_draft(message_id, 'bot-enabled', trigger='manual')

    assert result['status'] == 'processing'
    assert result['message'] == 'Draft generation is already in progress'
    assert result['run']['id'] == run_id
    assert result['run']['status'] == RUN_STATUS_PROCESSING
    assert result['run']['attempt_count'] == 2


async def test_processing_service_generate_draft_recovers_stale_processing_and_retries(raw_processing_app):
    ap = raw_processing_app
    ap.instance_config = SimpleNamespace(data={'database_mode': {'processing_run_stale_seconds': 300}})
    processing_service = DatabaseModeProcessingService(ap)
    adapter = WXWorkDatabaseAdapter(config={'connector_id': 'wxwork-local'}, logger=DummyEventLogger())

    class _ReplyPipeline:
        pipeline_entity = SimpleNamespace(config=_runtime_pipeline_config())

        async def run(self, query):
            await query.adapter.reply_message(
                message_source=query.message_event,
                message=platform_message.MessageChain([platform_message.Plain(text='Recovered stale draft')]),
            )

    await _install_formal_runtime_processing(ap, pipeline=_ReplyPipeline(), adapter=adapter)
    ap.bot_service = SimpleNamespace(
        get_bot=AsyncMock(return_value={
            'uuid': 'bot-enabled',
            'adapter': 'wxwork_database',
            'enable': True,
            'adapter_config': {'connector_id': 'wxwork-local'},
        })
    )

    message_id = await _insert_bound_message(
        ap,
        account_suffix='stale-processing',
        conversation_suffix='706',
        message_suffix='117',
        content='Need stale recovery',
        sender_id='304',
        sender_name='Customer P',
    )

    stale_started_at = (
        datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=15)
    ).replace(tzinfo=None)
    async with ap.persistence_mgr.get_db_engine().begin() as conn:
        stale_run_result = await conn.execute(
            sqlalchemy.insert(persistence_database_mode.MessageProcessingRun).values({
                'message_id': message_id,
                'bot_uuid': 'bot-enabled',
                'pipeline_uuid': None,
                'trigger': 'manual',
                'status': RUN_STATUS_PROCESSING,
                'attempt_count': 2,
                'started_at': stale_started_at,
                'completed_at': None,
                'last_error': None,
            })
        )
        stale_run_id = stale_run_result.inserted_primary_key[0]
        await conn.execute(
            sqlalchemy.update(persistence_database_mode.DatabaseMessage)
            .where(persistence_database_mode.DatabaseMessage.id == message_id)
            .values({'status': MESSAGE_STATUS_PENDING})
        )

    result = await processing_service.generate_draft(message_id, 'bot-enabled', trigger='manual')

    assert result['status'] == 'succeeded'
    assert result['draft']['content'] == 'Recovered stale draft'
    assert result['run']['attempt_count'] == 3

    run_rows = (
        await ap.persistence_mgr.execute_async(
            sqlalchemy.select(
                persistence_database_mode.MessageProcessingRun.id,
                persistence_database_mode.MessageProcessingRun.status,
                persistence_database_mode.MessageProcessingRun.attempt_count,
                persistence_database_mode.MessageProcessingRun.completed_at,
                persistence_database_mode.MessageProcessingRun.last_error,
            )
            .where(
                persistence_database_mode.MessageProcessingRun.message_id == message_id,
                persistence_database_mode.MessageProcessingRun.bot_uuid == 'bot-enabled',
            )
            .order_by(persistence_database_mode.MessageProcessingRun.id.asc())
        )
    ).mappings().all()

    assert len(run_rows) == 2
    assert dict(run_rows[0]) == {
        'id': stale_run_id,
        'status': RUN_STATUS_FAILED,
        'attempt_count': 2,
        'completed_at': run_rows[0]['completed_at'],
        'last_error': 'Stale processing run recovered after timeout',
    }
    assert run_rows[0]['completed_at'] is not None
    assert run_rows[1]['status'] == 'succeeded'
    assert run_rows[1]['attempt_count'] == 3


async def test_processing_service_require_message_returns_object_with_raw_connection_result(raw_processing_app):
    ap = raw_processing_app
    processing_service = DatabaseModeProcessingService(ap)

    async with ap.persistence_mgr.get_db_engine().begin() as conn:
        conversation_result = await conn.execute(
            sqlalchemy.insert(persistence_database_mode.DatabaseConversation).values({
                'connector_id': 'wxwork-local',
                'source': 'wxwork',
                'external_conversation_id': 'S:100_200',
                'conversation_name': 'Customer A',
                'conversation_type': 'direct',
            })
        )
        conversation_id = conversation_result.inserted_primary_key[0]
        message_result = await conn.execute(
            sqlalchemy.insert(persistence_database_mode.DatabaseMessage).values({
                'event_id': 'wxwork-local:evt-raw-1',
                'message_key': 'wxwork-local:key-raw-1',
                'conversation_id': conversation_id,
                'external_message_id': '101',
                'sender_id': '200',
                'sender_name': 'Customer A',
                'content': 'Need pricing details',
                'message_type': 'text',
                'sent_at': datetime.datetime.now(datetime.timezone.utc),
                'observed_at': datetime.datetime.now(datetime.timezone.utc),
                'status': MESSAGE_STATUS_PENDING,
            })
        )
        message_id = message_result.inserted_primary_key[0]

    message = await processing_service._require_message(message_id)

    assert not isinstance(message, int)
    assert message.id == message_id
    assert message.conversation_id == conversation_id
    assert message.sender_id == '200'
    assert message.sender_name == 'Customer A'
    assert message.content == 'Need pricing details'
    assert message.status == MESSAGE_STATUS_PENDING


async def test_processing_service_require_conversation_returns_object_with_raw_connection_result(raw_processing_app):
    ap = raw_processing_app
    processing_service = DatabaseModeProcessingService(ap)

    async with ap.persistence_mgr.get_db_engine().begin() as conn:
        result = await conn.execute(
            sqlalchemy.insert(persistence_database_mode.DatabaseConversation).values({
                'connector_id': 'wxwork-local',
                'source': 'wxwork',
                'external_conversation_id': 'S:100_200',
                'conversation_name': 'Customer A',
                'conversation_type': 'direct',
            })
        )
        conversation_id = result.inserted_primary_key[0]

    conversation = await processing_service._require_conversation(conversation_id)

    assert not isinstance(conversation, int)
    assert conversation.id == conversation_id
    assert conversation.connector_id == 'wxwork-local'
    assert conversation.external_conversation_id == 'S:100_200'
    assert conversation.conversation_type == 'direct'
    assert conversation.conversation_name == 'Customer A'


async def test_processing_service_helper_queries_return_objects_with_raw_connection_results(raw_processing_app):
    ap = raw_processing_app
    processing_service = DatabaseModeProcessingService(ap)

    async with ap.persistence_mgr.get_db_engine().begin() as conn:
        await conn.execute(
            sqlalchemy.insert(persistence_bot.Bot).values({
                'uuid': 'bot-enabled',
                'name': 'Database Bot',
                'description': '',
                'adapter': 'wxwork_database',
                'adapter_config': {'connector_id': 'wxwork-local'},
                'enable': True,
                'use_pipeline_name': None,
                'use_pipeline_uuid': 'pipeline-123',
                'pipeline_routing_rules': [],
            })
        )
        channel_account_result = await conn.execute(
            sqlalchemy.insert(persistence_database_mode.ChannelAccount).values({
                'connector_id': 'wxwork-local',
                'channel_type': 'wxwork',
                'external_account_id': 'acc-raw-1',
                'display_name': 'Raw Account',
                'enabled': True,
            })
        )
        channel_account_id = channel_account_result.inserted_primary_key[0]
        await conn.execute(
            sqlalchemy.insert(persistence_database_mode.BotChannelBinding).values({
                'bot_uuid': 'bot-raw',
                'channel_account_id': channel_account_id,
                'enabled': True,
                'auto_generate_draft': False,
            })
        )
        run_result = await conn.execute(
            sqlalchemy.insert(persistence_database_mode.MessageProcessingRun).values({
                'message_id': 7,
                'bot_uuid': 'bot-raw',
                'pipeline_uuid': 'pipeline-123',
                'trigger': 'manual',
                'status': 'succeeded',
                'attempt_count': 1,
                'started_at': datetime.datetime.now(datetime.timezone.utc),
                'completed_at': datetime.datetime.now(datetime.timezone.utc),
                'last_error': None,
            })
        )
        run_id = run_result.inserted_primary_key[0]
        draft_result = await conn.execute(
            sqlalchemy.insert(persistence_database_mode.ReplyDraft).values({
                'processing_run_id': run_id,
                'message_id': 7,
                'bot_uuid': 'bot-raw',
                'content': 'Draft text',
                'source': 'pipeline',
                'version': 1,
                'status': 'active',
            })
        )
        draft_id = draft_result.inserted_primary_key[0]

    latest_run = await processing_service._get_latest_run(7, 'bot-raw')
    active_draft = await processing_service._get_active_draft(7, 'bot-raw')
    channel_account = await processing_service._get_channel_account_for_bot('bot-raw')
    binding = await processing_service._get_bot_channel_binding('bot-raw', channel_account_id)
    draft = await processing_service._require_draft(draft_id)
    run = await processing_service._require_run(run_id)

    assert latest_run.id == run_id
    assert latest_run.status == 'succeeded'
    assert active_draft.id == draft_id
    assert active_draft.content == 'Draft text'
    assert channel_account.id == channel_account_id
    assert channel_account.connector_id == 'wxwork-local'
    assert binding.bot_uuid == 'bot-raw'
    assert binding.channel_account_id == channel_account_id
    assert draft.id == draft_id
    assert processing_service._serialize_draft(draft)['content'] == 'Draft text'
    assert run.id == run_id
    assert processing_service._serialize_run(run)['status'] == 'succeeded'


async def test_processing_service_require_bot_fallback_returns_object_with_raw_connection_result(raw_processing_app):
    ap = raw_processing_app
    processing_service = DatabaseModeProcessingService(ap)

    async with ap.persistence_mgr.get_db_engine().begin() as conn:
        await conn.execute(
            sqlalchemy.insert(persistence_bot.Bot).values({
                'uuid': 'bot-fallback',
                'name': 'Fallback Bot',
                'description': 'Bot for fallback lookup',
                'adapter': 'wxwork_database',
                'adapter_config': {'connector_id': 'wxwork-local'},
                'enable': True,
                'use_pipeline_name': None,
                'use_pipeline_uuid': 'pipeline-123',
                'pipeline_routing_rules': [],
            })
        )

    bot = await processing_service._require_bot('bot-fallback')

    assert bot.uuid == 'bot-fallback'
    assert bot.adapter == 'wxwork_database'
    assert bot.enable is True


async def test_processing_service_generate_draft_succeeds_with_raw_connection_results(raw_processing_app):
    ap = raw_processing_app
    processing_service = DatabaseModeProcessingService(ap)
    captured = {}

    class _MockRuntimeBot:
        def __init__(self):
            self.bot_entity = SimpleNamespace(uuid='bot-enabled', use_pipeline_uuid='pipeline-123')
            self.adapter = 'wxwork_database'

        def resolve_pipeline_uuid(self, launcher_type, launcher_id, message_text, message_element_types=None):
            captured['launcher_type'] = launcher_type
            captured['launcher_id'] = launcher_id
            captured['message_text'] = message_text
            return 'pipeline-123', False

        async def process_message_event_now(self, *args, **kwargs):
            return await _run_mock_pipeline_now(ap, args[0], adapter=self.adapter)

    class _FakePipeline:
        pipeline_entity = SimpleNamespace(config={})

        async def run(self, query):
            captured['pipeline_run_count'] = captured.get('pipeline_run_count', 0) + 1
            query.resp_message_chain = [platform_message.Plain(text='Pipeline generated draft')]

    ap.platform_mgr = SimpleNamespace(bots=[_MockRuntimeBot()])
    ap.pipeline_mgr = SimpleNamespace(get_pipeline_by_uuid=AsyncMock(return_value=_FakePipeline()))
    ap.query_pool = SimpleNamespace(add_query=AsyncMock(side_effect=lambda **kw: SimpleNamespace(**kw)))
    ap.bot_service = SimpleNamespace(
        get_bot=AsyncMock(return_value={
            'uuid': 'bot-enabled',
            'adapter': 'wxwork_database',
            'enable': True,
            'adapter_config': {'connector_id': 'wxwork-local'},
        })
    )

    async with ap.persistence_mgr.get_db_engine().begin() as conn:
        channel_account_result = await conn.execute(
            sqlalchemy.insert(persistence_database_mode.ChannelAccount).values({
                'connector_id': 'wxwork-local',
                'channel_type': 'wxwork',
                'external_account_id': 'acc-raw-2',
                'display_name': 'Raw Account',
                'enabled': True,
            })
        )
        channel_account_id = channel_account_result.inserted_primary_key[0]
        await conn.execute(
            sqlalchemy.insert(persistence_database_mode.BotChannelBinding).values({
                'bot_uuid': 'bot-enabled',
                'channel_account_id': channel_account_id,
                'enabled': True,
                'auto_generate_draft': False,
            })
        )
        conversation_result = await conn.execute(
            sqlalchemy.insert(persistence_database_mode.DatabaseConversation).values({
                'connector_id': 'wxwork-local',
                'source': 'wxwork',
                'external_conversation_id': 'S:100_200',
                'conversation_name': 'Customer A',
                'conversation_type': 'direct',
            })
        )
        conversation_id = conversation_result.inserted_primary_key[0]
        message_result = await conn.execute(
            sqlalchemy.insert(persistence_database_mode.DatabaseMessage).values({
                'event_id': 'wxwork-local:evt-raw-2',
                'message_key': 'wxwork-local:key-raw-2',
                'conversation_id': conversation_id,
                'external_message_id': '102',
                'sender_id': '200',
                'sender_name': 'Customer A',
                'content': 'Need pricing details',
                'message_type': 'text',
                'sent_at': datetime.datetime.now(datetime.timezone.utc),
                'observed_at': datetime.datetime.now(datetime.timezone.utc),
                'status': MESSAGE_STATUS_PENDING,
            })
        )
        message_id = message_result.inserted_primary_key[0]

    result = await processing_service.generate_draft(message_id, 'bot-enabled', trigger='manual')

    assert result['status'] == 'succeeded'
    assert result['draft']['message_id'] == message_id
    assert result['draft']['status'] == 'active'
    assert result['run']['status'] == 'succeeded'
    assert captured['launcher_type'] == 'person'
    assert captured['launcher_id'] == 'S:100_200'
    assert captured['message_text'] == 'Need pricing details'
    assert captured['pipeline_run_count'] == 1

    current_message_result = await ap.persistence_mgr.execute_async(
        sqlalchemy.select(
            persistence_database_mode.DatabaseMessage.status,
            persistence_database_mode.DatabaseMessage.draft_text,
            persistence_database_mode.DatabaseMessage.draft_source,
        ).where(persistence_database_mode.DatabaseMessage.id == message_id)
    )
    current_message = current_message_result.mappings().first()
    assert dict(current_message) == {
        'status': MESSAGE_STATUS_DRAFT_READY,
        'draft_text': 'Pipeline generated draft',
        'draft_source': 'pipeline',
    }


@pytest.mark.parametrize("conversation_type", ["person", "单聊"])
@pytest.mark.parametrize("trigger", ["manual", "automatic"])
async def test_processing_service_generate_draft_treats_private_conversation_alias_as_private_chat(
    raw_processing_app,
    conversation_type,
    trigger,
):
    ap = raw_processing_app
    processing_service = DatabaseModeProcessingService(ap)
    adapter = WXWorkDatabaseAdapter(config={'connector_id': 'wxwork-local'}, logger=DummyEventLogger())
    captured = {}

    class _OutputOnlyStage:
        def __init__(self, ap):
            self.ap = ap

        async def initialize(self, pipeline_config):
            return None

        async def process(self, query, stage_inst_name):
            captured['launcher_type'] = query.launcher_type.value
            captured['message_event_type'] = type(query.message_event).__name__
            captured['stage_trace_before_reply'] = list(query.variables.get('_stage_trace', []))
            query.resp_message_chain = [platform_message.MessageChain([platform_message.Plain(text='Person conversation draft')])]
            query.variables['_output_stage_entered'] = True
            return pipeline_entities.StageProcessResult(
                result_type=pipeline_entities.ResultType.CONTINUE,
                new_query=query,
                user_notice=None,
                debug_notice='',
                console_notice='',
                error_notice='',
            )

    runtime_pipeline = RuntimePipeline(
        ap,
        persistence_pipeline.LegacyPipeline(
            uuid='pipeline-123',
            name='Person Conversation Pipeline',
            description='',
            emoji='',
            for_version=4,
            is_default=False,
            stages=['GroupRespondRuleCheckStage', 'OutputOnlyStage'],
            config={
                'trigger': {'group-respond-rules': {}},
                **_runtime_pipeline_config(),
            },
            extensions_preferences={},
        ),
        [
            StageInstContainer(
                inst_name='GroupRespondRuleCheckStage',
                inst=(__import__('langbot.pkg.pipeline.resprule.resprule', fromlist=['GroupRespondRuleCheckStage']).GroupRespondRuleCheckStage(ap)),
            ),
            StageInstContainer(
                inst_name='OutputOnlyStage',
                inst=_OutputOnlyStage(ap),
            ),
        ],
    )
    for stage_container in runtime_pipeline.stage_containers:
        await stage_container.inst.initialize(runtime_pipeline.pipeline_entity.config)

    await _install_formal_runtime_processing(ap, pipeline=runtime_pipeline, adapter=adapter)
    ap.bot_service = SimpleNamespace(
        get_bot=AsyncMock(return_value={
            'uuid': 'bot-enabled',
            'adapter': 'wxwork_database',
            'enable': True,
            'adapter_config': {'connector_id': 'wxwork-local'},
        })
    )

    async with ap.persistence_mgr.get_db_engine().begin() as conn:
        channel_account_result = await conn.execute(
            sqlalchemy.insert(persistence_database_mode.ChannelAccount).values({
                'connector_id': 'wxwork-local',
                'channel_type': 'wxwork',
                'external_account_id': 'acc-person-conversation',
                'display_name': 'Raw Account',
                'enabled': True,
            })
        )
        channel_account_id = channel_account_result.inserted_primary_key[0]
        await conn.execute(
            sqlalchemy.insert(persistence_database_mode.BotChannelBinding).values({
                'bot_uuid': 'bot-enabled',
                'channel_account_id': channel_account_id,
                'enabled': True,
                'auto_generate_draft': False,
            })
        )
        conversation_result = await conn.execute(
            sqlalchemy.insert(persistence_database_mode.DatabaseConversation).values({
                'connector_id': 'wxwork-local',
                'source': 'wxwork',
                'external_conversation_id': 'S:100_person',
                'conversation_name': 'Customer Person',
                'conversation_type': conversation_type,
            })
        )
        conversation_id = conversation_result.inserted_primary_key[0]
        message_result = await conn.execute(
            sqlalchemy.insert(persistence_database_mode.DatabaseMessage).values({
                'event_id': 'wxwork-local:evt-person-conversation',
                'message_key': 'wxwork-local:key-person-conversation',
                'conversation_id': conversation_id,
                'external_message_id': 'person-1',
                'sender_id': 'person-200',
                'sender_name': 'Customer Person',
                'content': 'Need a private follow-up',
                'message_type': 'text',
                'sent_at': datetime.datetime.now(datetime.timezone.utc),
                'observed_at': datetime.datetime.now(datetime.timezone.utc),
                'status': MESSAGE_STATUS_PENDING,
            })
        )
        message_id = message_result.inserted_primary_key[0]

    result = await processing_service.generate_draft(message_id, 'bot-enabled', trigger=trigger)

    assert result['status'] == 'succeeded'
    assert result['draft']['content'] == 'Person conversation draft'
    assert captured['launcher_type'] == 'person'
    assert captured['message_event_type'] == 'FriendMessage'
    assert captured['stage_trace_before_reply'][0]['stage_name'] == 'GroupRespondRuleCheckStage'
    assert captured['stage_trace_before_reply'][0]['entered'] is True
    assert captured['stage_trace_before_reply'][1]['stage_name'] == 'GroupRespondRuleCheckStage'
    assert captured['stage_trace_before_reply'][1]['result_type'] == 'CONTINUE'
    assert captured['stage_trace_before_reply'][1]['interrupted'] is False


async def test_processing_service_rejects_unknown_conversation_type(raw_processing_app):
    ap = raw_processing_app
    processing_service = DatabaseModeProcessingService(ap)

    class _MockRuntimeBot:
        def __init__(self):
            self.bot_entity = SimpleNamespace(uuid='bot-enabled', use_pipeline_uuid='pipeline-123')
            self.adapter = 'wxwork_database'

        def resolve_pipeline_uuid(self, launcher_type, launcher_id, message_text, message_element_types=None):
            return 'pipeline-123', False

        async def process_message_event_now(self, event, **kwargs):
            raise AssertionError('Unknown conversation type should fail before runtime pipeline execution')

    ap.platform_mgr = SimpleNamespace(bots=[_MockRuntimeBot()])
    ap.pipeline_mgr = SimpleNamespace(get_pipeline_by_uuid=AsyncMock(return_value=None))
    ap.query_pool = SimpleNamespace(add_query=AsyncMock(side_effect=lambda **kw: SimpleNamespace(**kw)))
    ap.bot_service = SimpleNamespace(
        get_bot=AsyncMock(return_value={
            'uuid': 'bot-enabled',
            'adapter': 'wxwork_database',
            'enable': True,
            'adapter_config': {'connector_id': 'wxwork-local'},
        })
    )

    async with ap.persistence_mgr.get_db_engine().begin() as conn:
        channel_account_result = await conn.execute(
            sqlalchemy.insert(persistence_database_mode.ChannelAccount).values({
                'connector_id': 'wxwork-local',
                'channel_type': 'wxwork',
                'external_account_id': 'acc-unknown-conversation',
                'display_name': 'Raw Account',
                'enabled': True,
            })
        )
        channel_account_id = channel_account_result.inserted_primary_key[0]
        await conn.execute(
            sqlalchemy.insert(persistence_database_mode.BotChannelBinding).values({
                'bot_uuid': 'bot-enabled',
                'channel_account_id': channel_account_id,
                'enabled': True,
                'auto_generate_draft': False,
            })
        )
        conversation_result = await conn.execute(
            sqlalchemy.insert(persistence_database_mode.DatabaseConversation).values({
                'connector_id': 'wxwork-local',
                'source': 'wxwork',
                'external_conversation_id': 'S:100_unknown',
                'conversation_name': 'Customer Unknown',
                'conversation_type': 'weird_type',
            })
        )
        conversation_id = conversation_result.inserted_primary_key[0]
        message_result = await conn.execute(
            sqlalchemy.insert(persistence_database_mode.DatabaseMessage).values({
                'event_id': 'wxwork-local:evt-unknown-conversation',
                'message_key': 'wxwork-local:key-unknown-conversation',
                'conversation_id': conversation_id,
                'external_message_id': 'unknown-1',
                'sender_id': 'unknown-200',
                'sender_name': 'Customer Unknown',
                'content': 'Need an answer',
                'message_type': 'text',
                'sent_at': datetime.datetime.now(datetime.timezone.utc),
                'observed_at': datetime.datetime.now(datetime.timezone.utc),
                'status': MESSAGE_STATUS_PENDING,
            })
        )
        message_id = message_result.inserted_primary_key[0]

    with pytest.raises(ValueError, match="Unsupported conversation type: weird_type"):
        await processing_service.generate_draft(message_id, 'bot-enabled', trigger='manual')


async def test_processing_service_uses_publish_not_emit(raw_processing_app):
    ap = raw_processing_app
    processing_service = DatabaseModeProcessingService(ap)

    assert not hasattr(ap.database_mode_event_bus, 'emit')

    class _MockRuntimeBot:
        def __init__(self):
            self.bot_entity = SimpleNamespace(uuid='bot-enabled', use_pipeline_uuid='pipeline-123')
            self.adapter = 'wxwork_database'

        def resolve_pipeline_uuid(self, launcher_type, launcher_id, message_text, message_element_types=None):
            return 'pipeline-123', False

        async def process_message_event_now(self, event, **kwargs):
            return await _run_mock_pipeline_now(ap, event, adapter=self.adapter)

    class _FakePipeline:
        pipeline_entity = SimpleNamespace(config={})

        async def run(self, query):
            query.resp_message_chain = [platform_message.Plain(text='Pipeline generated draft')]

    ap.platform_mgr = SimpleNamespace(bots=[_MockRuntimeBot()])
    ap.pipeline_mgr = SimpleNamespace(get_pipeline_by_uuid=AsyncMock(return_value=_FakePipeline()))
    ap.query_pool = SimpleNamespace(add_query=AsyncMock(side_effect=lambda **kw: SimpleNamespace(**kw)))
    ap.bot_service = SimpleNamespace(
        get_bot=AsyncMock(return_value={
            'uuid': 'bot-enabled',
            'adapter': 'wxwork_database',
            'enable': True,
            'adapter_config': {'connector_id': 'wxwork-local'},
        })
    )

    async with ap.persistence_mgr.get_db_engine().begin() as conn:
        channel_account_result = await conn.execute(
            sqlalchemy.insert(persistence_database_mode.ChannelAccount).values({
                'connector_id': 'wxwork-local',
                'channel_type': 'wxwork',
                'external_account_id': 'acc-raw-emit',
                'display_name': 'Raw Account',
                'enabled': True,
            })
        )
        channel_account_id = channel_account_result.inserted_primary_key[0]
        await conn.execute(
            sqlalchemy.insert(persistence_database_mode.BotChannelBinding).values({
                'bot_uuid': 'bot-enabled',
                'channel_account_id': channel_account_id,
                'enabled': True,
                'auto_generate_draft': False,
            })
        )
        conversation_result = await conn.execute(
            sqlalchemy.insert(persistence_database_mode.DatabaseConversation).values({
                'connector_id': 'wxwork-local',
                'source': 'wxwork',
                'external_conversation_id': 'S:100_300',
                'conversation_name': 'Customer B',
                'conversation_type': 'direct',
            })
        )
        conversation_id = conversation_result.inserted_primary_key[0]
        message_result = await conn.execute(
            sqlalchemy.insert(persistence_database_mode.DatabaseMessage).values({
                'event_id': 'wxwork-local:evt-raw-emit',
                'message_key': 'wxwork-local:key-raw-emit',
                'conversation_id': conversation_id,
                'external_message_id': '103',
                'sender_id': '201',
                'sender_name': 'Customer B',
                'content': 'Need support',
                'message_type': 'text',
                'sent_at': datetime.datetime.now(datetime.timezone.utc),
                'observed_at': datetime.datetime.now(datetime.timezone.utc),
                'status': MESSAGE_STATUS_PENDING,
            })
        )
        message_id = message_result.inserted_primary_key[0]

    result = await processing_service.generate_draft(message_id, 'bot-enabled', trigger='manual')

    assert result['status'] == 'succeeded'
    assert [event.type for event in ap.database_mode_event_bus.published_events] == [
        DatabaseModeEventType.MESSAGE_UPDATED,
        DatabaseModeEventType.MESSAGE_UPDATED,
    ]
    assert ap.database_mode_event_bus.published_events[0].metadata['processing_status'] == 'processing'
    assert ap.database_mode_event_bus.published_events[1].metadata['processing_status'] == MESSAGE_STATUS_DRAFT_READY


async def test_processing_service_failure_preserves_original_exception_when_event_publish_fails(raw_processing_app):
    ap = raw_processing_app
    processing_service = DatabaseModeProcessingService(ap)
    logger = SimpleNamespace(info=AsyncMock(), exception=AsyncMock())
    ap.logger = logger

    class _FailingEventBus(DatabaseModeEventBus):
        async def publish(self, event) -> None:
            raise RuntimeError('event bus failed')

    class _MockRuntimeBot:
        def __init__(self):
            self.bot_entity = SimpleNamespace(uuid='bot-enabled', use_pipeline_uuid='pipeline-123')
            self.adapter = 'wxwork_database'

        def resolve_pipeline_uuid(self, launcher_type, launcher_id, message_text, message_element_types=None):
            return 'pipeline-123', False

        async def process_message_event_now(self, event, **kwargs):
            return await _run_mock_pipeline_now(ap, event, adapter=self.adapter)

    class _FailingPipeline:
        pipeline_entity = SimpleNamespace(config={})

        async def run(self, query):
            raise ValueError('pipeline exploded')

    ap.database_mode_event_bus = _FailingEventBus()
    ap.platform_mgr = SimpleNamespace(bots=[_MockRuntimeBot()])
    ap.pipeline_mgr = SimpleNamespace(get_pipeline_by_uuid=AsyncMock(return_value=_FailingPipeline()))
    ap.query_pool = SimpleNamespace(add_query=AsyncMock(side_effect=lambda **kw: SimpleNamespace(**kw)))
    ap.bot_service = SimpleNamespace(
        get_bot=AsyncMock(return_value={
            'uuid': 'bot-enabled',
            'adapter': 'wxwork_database',
            'enable': True,
            'adapter_config': {'connector_id': 'wxwork-local'},
        })
    )

    async with ap.persistence_mgr.get_db_engine().begin() as conn:
        channel_account_result = await conn.execute(
            sqlalchemy.insert(persistence_database_mode.ChannelAccount).values({
                'connector_id': 'wxwork-local',
                'channel_type': 'wxwork',
                'external_account_id': 'acc-raw-fail',
                'display_name': 'Raw Account',
                'enabled': True,
            })
        )
        channel_account_id = channel_account_result.inserted_primary_key[0]
        await conn.execute(
            sqlalchemy.insert(persistence_database_mode.BotChannelBinding).values({
                'bot_uuid': 'bot-enabled',
                'channel_account_id': channel_account_id,
                'enabled': True,
                'auto_generate_draft': False,
            })
        )
        conversation_result = await conn.execute(
            sqlalchemy.insert(persistence_database_mode.DatabaseConversation).values({
                'connector_id': 'wxwork-local',
                'source': 'wxwork',
                'external_conversation_id': 'S:100_400',
                'conversation_name': 'Customer C',
                'conversation_type': 'direct',
            })
        )
        conversation_id = conversation_result.inserted_primary_key[0]
        message_result = await conn.execute(
            sqlalchemy.insert(persistence_database_mode.DatabaseMessage).values({
                'event_id': 'wxwork-local:evt-raw-fail',
                'message_key': 'wxwork-local:key-raw-fail',
                'conversation_id': conversation_id,
                'external_message_id': '104',
                'sender_id': '202',
                'sender_name': 'Customer C',
                'content': 'Need escalation',
                'message_type': 'text',
                'sent_at': datetime.datetime.now(datetime.timezone.utc),
                'observed_at': datetime.datetime.now(datetime.timezone.utc),
                'status': MESSAGE_STATUS_PENDING,
            })
        )
        message_id = message_result.inserted_primary_key[0]

    with pytest.raises(ValueError, match='pipeline exploded'):
        await processing_service.generate_draft(message_id, 'bot-enabled', trigger='manual')


async def test_processing_service_success_transaction_supersedes_old_draft_and_increments_version(raw_processing_app):
    ap = raw_processing_app
    processing_service = DatabaseModeProcessingService(ap)

    class _MockRuntimeBot:
        def __init__(self):
            self.bot_entity = SimpleNamespace(uuid='bot-enabled', use_pipeline_uuid='pipeline-123')
            self.adapter = 'wxwork_database'

        def resolve_pipeline_uuid(self, launcher_type, launcher_id, message_text, message_element_types=None):
            return 'pipeline-123', False

        async def process_message_event_now(self, event, **kwargs):
            return await _run_mock_pipeline_now(ap, event, adapter=self.adapter)

    class _FakePipeline:
        pipeline_entity = SimpleNamespace(config={})

        async def run(self, query):
            query.resp_message_chain = [platform_message.Plain(text='New pipeline draft')]

    ap.platform_mgr = SimpleNamespace(bots=[_MockRuntimeBot()])
    ap.pipeline_mgr = SimpleNamespace(get_pipeline_by_uuid=AsyncMock(return_value=_FakePipeline()))
    ap.query_pool = SimpleNamespace(add_query=AsyncMock(side_effect=lambda **kw: SimpleNamespace(**kw)))
    ap.bot_service = SimpleNamespace(
        get_bot=AsyncMock(return_value={
            'uuid': 'bot-enabled',
            'adapter': 'wxwork_database',
            'enable': True,
            'adapter_config': {'connector_id': 'wxwork-local'},
        })
    )

    async with ap.persistence_mgr.get_db_engine().begin() as conn:
        channel_account_result = await conn.execute(
            sqlalchemy.insert(persistence_database_mode.ChannelAccount).values({
                'connector_id': 'wxwork-local',
                'channel_type': 'wxwork',
                'external_account_id': 'acc-raw-success',
                'display_name': 'Raw Account',
                'enabled': True,
            })
        )
        channel_account_id = channel_account_result.inserted_primary_key[0]
        await conn.execute(
            sqlalchemy.insert(persistence_database_mode.BotChannelBinding).values({
                'bot_uuid': 'bot-enabled',
                'channel_account_id': channel_account_id,
                'enabled': True,
                'auto_generate_draft': False,
            })
        )
        conversation_result = await conn.execute(
            sqlalchemy.insert(persistence_database_mode.DatabaseConversation).values({
                'connector_id': 'wxwork-local',
                'source': 'wxwork',
                'external_conversation_id': 'S:100_500',
                'conversation_name': 'Customer D',
                'conversation_type': 'direct',
            })
        )
        conversation_id = conversation_result.inserted_primary_key[0]
        message_result = await conn.execute(
            sqlalchemy.insert(persistence_database_mode.DatabaseMessage).values({
                'event_id': 'wxwork-local:evt-raw-success',
                'message_key': 'wxwork-local:key-raw-success',
                'conversation_id': conversation_id,
                'external_message_id': '105',
                'sender_id': '203',
                'sender_name': 'Customer D',
                'content': 'Need quote',
                'message_type': 'text',
                'sent_at': datetime.datetime.now(datetime.timezone.utc),
                'observed_at': datetime.datetime.now(datetime.timezone.utc),
                'status': MESSAGE_STATUS_PENDING,
            })
        )
        message_id = message_result.inserted_primary_key[0]
        previous_run_result = await conn.execute(
            sqlalchemy.insert(persistence_database_mode.MessageProcessingRun).values({
                'message_id': message_id,
                'bot_uuid': 'bot-enabled',
                'pipeline_uuid': 'pipeline-old',
                'trigger': 'manual',
                'status': RUN_STATUS_FAILED,
                'attempt_count': 1,
                'started_at': datetime.datetime.now(datetime.timezone.utc),
                'completed_at': datetime.datetime.now(datetime.timezone.utc),
                'last_error': 'old error',
            })
        )
        previous_run_id = previous_run_result.inserted_primary_key[0]
        await conn.execute(
            sqlalchemy.insert(persistence_database_mode.ReplyDraft).values({
                'processing_run_id': previous_run_id,
                'message_id': message_id,
                'bot_uuid': 'bot-enabled',
                'content': 'Old active draft',
                'source': 'manual',
                'version': 1,
                'status': DRAFT_STATUS_ACTIVE,
            })
        )

    result = await processing_service.generate_draft(message_id, 'bot-enabled', trigger='manual')

    assert result['status'] == 'succeeded'
    drafts_result = await ap.persistence_mgr.execute_async(
        sqlalchemy.select(
            persistence_database_mode.ReplyDraft.content,
            persistence_database_mode.ReplyDraft.version,
            persistence_database_mode.ReplyDraft.status,
        )
        .where(
            persistence_database_mode.ReplyDraft.message_id == message_id,
            persistence_database_mode.ReplyDraft.bot_uuid == 'bot-enabled',
        )
        .order_by(persistence_database_mode.ReplyDraft.version.asc())
    )
    drafts = [dict(row) for row in drafts_result.mappings().all()]
    assert drafts == [
        {'content': 'Old active draft', 'version': 1, 'status': DRAFT_STATUS_SUPERSEDED},
        {'content': 'New pipeline draft', 'version': 2, 'status': DRAFT_STATUS_ACTIVE},
    ]

    active_count = (
        await ap.persistence_mgr.execute_async(
            sqlalchemy.select(sqlalchemy.func.count()).select_from(persistence_database_mode.ReplyDraft).where(
                persistence_database_mode.ReplyDraft.message_id == message_id,
                persistence_database_mode.ReplyDraft.bot_uuid == 'bot-enabled',
                persistence_database_mode.ReplyDraft.status == DRAFT_STATUS_ACTIVE,
            )
        )
    ).scalar_one()
    assert active_count == 1


async def test_processing_service_generate_draft_uses_new_query_from_stage_result(raw_processing_app):
    ap = raw_processing_app
    processing_service = DatabaseModeProcessingService(ap)

    class _MockRuntimeBot:
        def __init__(self):
            self.bot_entity = SimpleNamespace(uuid='bot-enabled', use_pipeline_uuid='pipeline-123')
            self.adapter = 'wxwork_database'

        def resolve_pipeline_uuid(self, launcher_type, launcher_id, message_text, message_element_types=None):
            return 'pipeline-123', False

        async def process_message_event_now(self, event, **kwargs):
            return await _run_mock_pipeline_now(ap, event, adapter=self.adapter)

    class _FakePipeline:
        pipeline_entity = SimpleNamespace(config={})

        async def run(self, query):
            final_query = SimpleNamespace(
                resp_message_chain=[platform_message.MessageChain([platform_message.Plain(text='Result from new_query')])],
                resp_messages=[],
            )
            return SimpleNamespace(new_query=final_query)

    ap.platform_mgr = SimpleNamespace(bots=[_MockRuntimeBot()])
    ap.pipeline_mgr = SimpleNamespace(get_pipeline_by_uuid=AsyncMock(return_value=_FakePipeline()))
    ap.query_pool = SimpleNamespace(add_query=AsyncMock(side_effect=lambda **kw: SimpleNamespace(**kw)))
    ap.bot_service = SimpleNamespace(
        get_bot=AsyncMock(return_value={
            'uuid': 'bot-enabled',
            'adapter': 'wxwork_database',
            'enable': True,
            'adapter_config': {'connector_id': 'wxwork-local'},
        })
    )

    async with ap.persistence_mgr.get_db_engine().begin() as conn:
        channel_account_result = await conn.execute(
            sqlalchemy.insert(persistence_database_mode.ChannelAccount).values({
                'connector_id': 'wxwork-local',
                'channel_type': 'wxwork',
                'external_account_id': 'acc-raw-new-query',
                'display_name': 'Raw Account',
                'enabled': True,
            })
        )
        channel_account_id = channel_account_result.inserted_primary_key[0]
        await conn.execute(
            sqlalchemy.insert(persistence_database_mode.BotChannelBinding).values({
                'bot_uuid': 'bot-enabled',
                'channel_account_id': channel_account_id,
                'enabled': True,
                'auto_generate_draft': False,
            })
        )
        conversation_result = await conn.execute(
            sqlalchemy.insert(persistence_database_mode.DatabaseConversation).values({
                'connector_id': 'wxwork-local',
                'source': 'wxwork',
                'external_conversation_id': 'S:100_610',
                'conversation_name': 'Customer F',
                'conversation_type': 'direct',
            })
        )
        conversation_id = conversation_result.inserted_primary_key[0]
        message_result = await conn.execute(
            sqlalchemy.insert(persistence_database_mode.DatabaseMessage).values({
                'event_id': 'wxwork-local:evt-raw-new-query',
                'message_key': 'wxwork-local:key-raw-new-query',
                'conversation_id': conversation_id,
                'external_message_id': '107',
                'sender_id': '205',
                'sender_name': 'Customer F',
                'content': 'Need pricing follow-up',
                'message_type': 'text',
                'sent_at': datetime.datetime.now(datetime.timezone.utc),
                'observed_at': datetime.datetime.now(datetime.timezone.utc),
                'status': MESSAGE_STATUS_PENDING,
            })
        )
        message_id = message_result.inserted_primary_key[0]

    result = await processing_service.generate_draft(message_id, 'bot-enabled', trigger='manual')

    assert result['status'] == 'succeeded'
    assert result['draft']['content'] == 'Result from new_query'


async def test_processing_service_generate_draft_uses_adapter_capture_when_pipeline_replies_via_adapter(raw_processing_app):
    ap = raw_processing_app
    processing_service = DatabaseModeProcessingService(ap)
    adapter = WXWorkDatabaseAdapter(config={'connector_id': 'wxwork-local'}, logger=DummyEventLogger())

    class _MockRuntimeBot:
        def __init__(self):
            self.bot_entity = SimpleNamespace(uuid='bot-enabled', use_pipeline_uuid='pipeline-123')
            self.adapter = adapter

        def resolve_pipeline_uuid(self, launcher_type, launcher_id, message_text, message_element_types=None):
            return 'pipeline-123', False

        async def process_message_event_now(self, event, **kwargs):
            return await _run_mock_pipeline_now(ap, event, adapter=self.adapter)

    class _FakePipeline:
        pipeline_entity = SimpleNamespace(config={})

        async def run(self, query):
            await query.adapter.reply_message(
                message_source=query.message_event,
                message=platform_message.MessageChain([platform_message.Plain(text='Adapter captured reply')]),
            )

    ap.platform_mgr = SimpleNamespace(bots=[_MockRuntimeBot()])
    ap.pipeline_mgr = SimpleNamespace(get_pipeline_by_uuid=AsyncMock(return_value=_FakePipeline()))
    ap.query_pool = SimpleNamespace(add_query=AsyncMock(side_effect=lambda **kw: SimpleNamespace(**kw)))
    ap.bot_service = SimpleNamespace(
        get_bot=AsyncMock(return_value={
            'uuid': 'bot-enabled',
            'adapter': 'wxwork_database',
            'enable': True,
            'adapter_config': {'connector_id': 'wxwork-local'},
        })
    )

    async with ap.persistence_mgr.get_db_engine().begin() as conn:
        channel_account_result = await conn.execute(
            sqlalchemy.insert(persistence_database_mode.ChannelAccount).values({
                'connector_id': 'wxwork-local',
                'channel_type': 'wxwork',
                'external_account_id': 'acc-raw-adapter-capture',
                'display_name': 'Raw Account',
                'enabled': True,
            })
        )
        channel_account_id = channel_account_result.inserted_primary_key[0]
        await conn.execute(
            sqlalchemy.insert(persistence_database_mode.BotChannelBinding).values({
                'bot_uuid': 'bot-enabled',
                'channel_account_id': channel_account_id,
                'enabled': True,
                'auto_generate_draft': False,
            })
        )
        conversation_result = await conn.execute(
            sqlalchemy.insert(persistence_database_mode.DatabaseConversation).values({
                'connector_id': 'wxwork-local',
                'source': 'wxwork',
                'external_conversation_id': 'S:100_620',
                'conversation_name': 'Customer G',
                'conversation_type': 'direct',
            })
        )
        conversation_id = conversation_result.inserted_primary_key[0]
        message_result = await conn.execute(
            sqlalchemy.insert(persistence_database_mode.DatabaseMessage).values({
                'event_id': 'wxwork-local:evt-raw-adapter-capture',
                'message_key': 'wxwork-local:key-raw-adapter-capture',
                'conversation_id': conversation_id,
                'external_message_id': '108',
                'sender_id': '206',
                'sender_name': 'Customer G',
                'content': 'Need discount',
                'message_type': 'text',
                'sent_at': datetime.datetime.now(datetime.timezone.utc),
                'observed_at': datetime.datetime.now(datetime.timezone.utc),
                'status': MESSAGE_STATUS_PENDING,
            })
        )
        message_id = message_result.inserted_primary_key[0]

    result = await processing_service.generate_draft(message_id, 'bot-enabled', trigger='manual')

    assert result['status'] == 'succeeded'
    assert result['draft']['content'] == 'Adapter captured reply'


async def test_processing_service_generate_draft_uses_stream_capture_when_pipeline_replies_in_chunks(raw_processing_app):
    ap = raw_processing_app
    processing_service = DatabaseModeProcessingService(ap)
    adapter = WXWorkDatabaseAdapter(config={'connector_id': 'wxwork-local'}, logger=DummyEventLogger())

    class _MockRuntimeBot:
        def __init__(self):
            self.bot_entity = SimpleNamespace(uuid='bot-enabled', use_pipeline_uuid='pipeline-123')
            self.adapter = adapter

        def resolve_pipeline_uuid(self, launcher_type, launcher_id, message_text, message_element_types=None):
            return 'pipeline-123', False

        async def process_message_event_now(self, event, **kwargs):
            return await _run_mock_pipeline_now(ap, event, adapter=self.adapter)

    class _FakePipeline:
        pipeline_entity = SimpleNamespace(config={})

        async def run(self, query):
            await query.adapter.reply_message_chunk(
                message_source=query.message_event,
                bot_message={'id': 'stream-1'},
                message=platform_message.MessageChain([platform_message.Plain(text='hello ')]),
                is_final=False,
            )
            await query.adapter.reply_message_chunk(
                message_source=query.message_event,
                bot_message={'id': 'stream-1'},
                message=platform_message.MessageChain([platform_message.Plain(text='world')]),
                is_final=True,
            )

    ap.platform_mgr = SimpleNamespace(bots=[_MockRuntimeBot()])
    ap.pipeline_mgr = SimpleNamespace(get_pipeline_by_uuid=AsyncMock(return_value=_FakePipeline()))
    ap.query_pool = SimpleNamespace(add_query=AsyncMock(side_effect=lambda **kw: SimpleNamespace(**kw)))
    ap.bot_service = SimpleNamespace(
        get_bot=AsyncMock(return_value={
            'uuid': 'bot-enabled',
            'adapter': 'wxwork_database',
            'enable': True,
            'adapter_config': {'connector_id': 'wxwork-local'},
        })
    )

    async with ap.persistence_mgr.get_db_engine().begin() as conn:
        channel_account_result = await conn.execute(
            sqlalchemy.insert(persistence_database_mode.ChannelAccount).values({
                'connector_id': 'wxwork-local',
                'channel_type': 'wxwork',
                'external_account_id': 'acc-raw-stream-capture',
                'display_name': 'Raw Account',
                'enabled': True,
            })
        )
        channel_account_id = channel_account_result.inserted_primary_key[0]
        await conn.execute(
            sqlalchemy.insert(persistence_database_mode.BotChannelBinding).values({
                'bot_uuid': 'bot-enabled',
                'channel_account_id': channel_account_id,
                'enabled': True,
                'auto_generate_draft': False,
            })
        )
        conversation_result = await conn.execute(
            sqlalchemy.insert(persistence_database_mode.DatabaseConversation).values({
                'connector_id': 'wxwork-local',
                'source': 'wxwork',
                'external_conversation_id': 'S:100_630',
                'conversation_name': 'Customer H',
                'conversation_type': 'direct',
            })
        )
        conversation_id = conversation_result.inserted_primary_key[0]
        message_result = await conn.execute(
            sqlalchemy.insert(persistence_database_mode.DatabaseMessage).values({
                'event_id': 'wxwork-local:evt-raw-stream-capture',
                'message_key': 'wxwork-local:key-raw-stream-capture',
                'conversation_id': conversation_id,
                'external_message_id': '109',
                'sender_id': '207',
                'sender_name': 'Customer H',
                'content': 'Need ETA',
                'message_type': 'text',
                'sent_at': datetime.datetime.now(datetime.timezone.utc),
                'observed_at': datetime.datetime.now(datetime.timezone.utc),
                'status': MESSAGE_STATUS_PENDING,
            })
        )
        message_id = message_result.inserted_primary_key[0]

    result = await processing_service.generate_draft(message_id, 'bot-enabled', trigger='manual')

    assert result['status'] == 'succeeded'
    assert result['draft']['content'] == 'hello world'


async def test_processing_service_failure_transaction_marks_failed_without_creating_empty_draft(raw_processing_app):
    ap = raw_processing_app
    processing_service = DatabaseModeProcessingService(ap)

    class _MockRuntimeBot:
        def __init__(self):
            self.bot_entity = SimpleNamespace(uuid='bot-enabled', use_pipeline_uuid='pipeline-123')
            self.adapter = 'wxwork_database'

        def resolve_pipeline_uuid(self, launcher_type, launcher_id, message_text, message_element_types=None):
            return 'pipeline-123', False

        async def process_message_event_now(self, event, **kwargs):
            return await _run_mock_pipeline_now(ap, event, adapter=self.adapter)

    class _FailingPipeline:
        pipeline_entity = SimpleNamespace(config={})

        async def run(self, query):
            raise ValueError('pipeline exploded')

    ap.platform_mgr = SimpleNamespace(bots=[_MockRuntimeBot()])
    ap.pipeline_mgr = SimpleNamespace(get_pipeline_by_uuid=AsyncMock(return_value=_FailingPipeline()))
    ap.query_pool = SimpleNamespace(add_query=AsyncMock(side_effect=lambda **kw: SimpleNamespace(**kw)))
    ap.bot_service = SimpleNamespace(
        get_bot=AsyncMock(return_value={
            'uuid': 'bot-enabled',
            'adapter': 'wxwork_database',
            'enable': True,
            'adapter_config': {'connector_id': 'wxwork-local'},
        })
    )

    async with ap.persistence_mgr.get_db_engine().begin() as conn:
        channel_account_result = await conn.execute(
            sqlalchemy.insert(persistence_database_mode.ChannelAccount).values({
                'connector_id': 'wxwork-local',
                'channel_type': 'wxwork',
                'external_account_id': 'acc-raw-failure',
                'display_name': 'Raw Account',
                'enabled': True,
            })
        )
        channel_account_id = channel_account_result.inserted_primary_key[0]
        await conn.execute(
            sqlalchemy.insert(persistence_database_mode.BotChannelBinding).values({
                'bot_uuid': 'bot-enabled',
                'channel_account_id': channel_account_id,
                'enabled': True,
                'auto_generate_draft': False,
            })
        )
        conversation_result = await conn.execute(
            sqlalchemy.insert(persistence_database_mode.DatabaseConversation).values({
                'connector_id': 'wxwork-local',
                'source': 'wxwork',
                'external_conversation_id': 'S:100_600',
                'conversation_name': 'Customer E',
                'conversation_type': 'direct',
            })
        )
        conversation_id = conversation_result.inserted_primary_key[0]
        message_result = await conn.execute(
            sqlalchemy.insert(persistence_database_mode.DatabaseMessage).values({
                'event_id': 'wxwork-local:evt-raw-failure',
                'message_key': 'wxwork-local:key-raw-failure',
                'conversation_id': conversation_id,
                'external_message_id': '106',
                'sender_id': '204',
                'sender_name': 'Customer E',
                'content': 'Need callback',
                'message_type': 'text',
                'sent_at': datetime.datetime.now(datetime.timezone.utc),
                'observed_at': datetime.datetime.now(datetime.timezone.utc),
                'status': MESSAGE_STATUS_PENDING,
            })
        )
        message_id = message_result.inserted_primary_key[0]

    with pytest.raises(ValueError, match='pipeline exploded'):
        await processing_service.generate_draft(message_id, 'bot-enabled', trigger='manual')

    run_row = (
        await ap.persistence_mgr.execute_async(
            sqlalchemy.select(
                persistence_database_mode.MessageProcessingRun.status,
                persistence_database_mode.MessageProcessingRun.last_error,
            )
            .where(
                persistence_database_mode.MessageProcessingRun.message_id == message_id,
                persistence_database_mode.MessageProcessingRun.bot_uuid == 'bot-enabled',
            )
            .order_by(persistence_database_mode.MessageProcessingRun.id.desc())
            .limit(1)
        )
    ).mappings().first()
    assert dict(run_row) == {
        'status': RUN_STATUS_FAILED,
        'last_error': 'pipeline exploded',
    }

    message_row = (
        await ap.persistence_mgr.execute_async(
            sqlalchemy.select(
                persistence_database_mode.DatabaseMessage.status,
                persistence_database_mode.DatabaseMessage.last_error,
            ).where(persistence_database_mode.DatabaseMessage.id == message_id)
        )
    ).mappings().first()
    assert dict(message_row) == {
        'status': MESSAGE_STATUS_FAILED,
        'last_error': 'pipeline exploded',
    }

    draft_count = (
        await ap.persistence_mgr.execute_async(
            sqlalchemy.select(sqlalchemy.func.count()).select_from(persistence_database_mode.ReplyDraft).where(
                persistence_database_mode.ReplyDraft.message_id == message_id,
                persistence_database_mode.ReplyDraft.bot_uuid == 'bot-enabled',
            )
        )
    ).scalar_one()
    assert draft_count == 0


async def test_processing_service_generate_draft_fails_with_clear_message_when_pipeline_has_no_text_output(raw_processing_app):
    ap = raw_processing_app
    processing_service = DatabaseModeProcessingService(ap)
    adapter = WXWorkDatabaseAdapter(config={'connector_id': 'wxwork-local'}, logger=DummyEventLogger())

    class _MockRuntimeBot:
        def __init__(self):
            self.bot_entity = SimpleNamespace(uuid='bot-enabled', use_pipeline_uuid='pipeline-123')
            self.adapter = adapter

        def resolve_pipeline_uuid(self, launcher_type, launcher_id, message_text, message_element_types=None):
            return 'pipeline-123', False

        async def process_message_event_now(self, event, **kwargs):
            return await _run_mock_pipeline_now(ap, event, adapter=self.adapter)

    class _FakePipeline:
        pipeline_entity = SimpleNamespace(config={})

        async def run(self, query):
            return None

    ap.platform_mgr = SimpleNamespace(bots=[_MockRuntimeBot()])
    ap.pipeline_mgr = SimpleNamespace(get_pipeline_by_uuid=AsyncMock(return_value=_FakePipeline()))
    ap.query_pool = SimpleNamespace(add_query=AsyncMock(side_effect=lambda **kw: SimpleNamespace(**kw)))
    ap.bot_service = SimpleNamespace(
        get_bot=AsyncMock(return_value={
            'uuid': 'bot-enabled',
            'adapter': 'wxwork_database',
            'enable': True,
            'adapter_config': {'connector_id': 'wxwork-local'},
        })
    )

    async with ap.persistence_mgr.get_db_engine().begin() as conn:
        channel_account_result = await conn.execute(
            sqlalchemy.insert(persistence_database_mode.ChannelAccount).values({
                'connector_id': 'wxwork-local',
                'channel_type': 'wxwork',
                'external_account_id': 'acc-raw-no-text',
                'display_name': 'Raw Account',
                'enabled': True,
            })
        )
        channel_account_id = channel_account_result.inserted_primary_key[0]
        await conn.execute(
            sqlalchemy.insert(persistence_database_mode.BotChannelBinding).values({
                'bot_uuid': 'bot-enabled',
                'channel_account_id': channel_account_id,
                'enabled': True,
                'auto_generate_draft': False,
            })
        )
        conversation_result = await conn.execute(
            sqlalchemy.insert(persistence_database_mode.DatabaseConversation).values({
                'connector_id': 'wxwork-local',
                'source': 'wxwork',
                'external_conversation_id': 'S:100_640',
                'conversation_name': 'Customer I',
                'conversation_type': 'direct',
            })
        )
        conversation_id = conversation_result.inserted_primary_key[0]
        message_result = await conn.execute(
            sqlalchemy.insert(persistence_database_mode.DatabaseMessage).values({
                'event_id': 'wxwork-local:evt-raw-no-text',
                'message_key': 'wxwork-local:key-raw-no-text',
                'conversation_id': conversation_id,
                'external_message_id': '110',
                'sender_id': '208',
                'sender_name': 'Customer I',
                'content': 'Need update',
                'message_type': 'text',
                'sent_at': datetime.datetime.now(datetime.timezone.utc),
                'observed_at': datetime.datetime.now(datetime.timezone.utc),
                'status': MESSAGE_STATUS_PENDING,
            })
        )
        message_id = message_result.inserted_primary_key[0]

    with pytest.raises(ValueError, match='Pipeline pipeline-123 completed without a text response'):
        await processing_service.generate_draft(message_id, 'bot-enabled', trigger='manual')

    draft_count = (
        await ap.persistence_mgr.execute_async(
            sqlalchemy.select(sqlalchemy.func.count()).select_from(persistence_database_mode.ReplyDraft).where(
                persistence_database_mode.ReplyDraft.message_id == message_id,
                persistence_database_mode.ReplyDraft.bot_uuid == 'bot-enabled',
            )
        )
    ).scalar_one()
    assert draft_count == 0


async def test_processing_service_generate_draft_finalizes_failed_state_on_cancelled_error(raw_processing_app):
    ap = raw_processing_app
    processing_service = DatabaseModeProcessingService(ap)

    class _CancelledRuntimeBot:
        def __init__(self):
            self.bot_entity = SimpleNamespace(uuid='bot-enabled', use_pipeline_uuid='pipeline-123')
            self.adapter = 'wxwork_database'

        def resolve_pipeline_uuid(self, launcher_type, launcher_id, message_text, message_element_types=None):
            return 'pipeline-123', False

        async def process_message_event_now(self, event, **kwargs):
            raise asyncio.CancelledError()

    ap.platform_mgr = SimpleNamespace(bots=[_CancelledRuntimeBot()])
    ap.pipeline_mgr = SimpleNamespace(get_pipeline_by_uuid=AsyncMock(return_value=SimpleNamespace()))
    ap.bot_service = SimpleNamespace(
        get_bot=AsyncMock(return_value={
            'uuid': 'bot-enabled',
            'adapter': 'wxwork_database',
            'enable': True,
            'adapter_config': {'connector_id': 'wxwork-local'},
        })
    )

    message_id = await _insert_bound_message(
        ap,
        account_suffix='cancelled-processing',
        conversation_suffix='707',
        message_suffix='118',
        content='Need cancellation handling',
        sender_id='305',
        sender_name='Customer Q',
    )

    with pytest.raises(asyncio.CancelledError):
        await processing_service.generate_draft(message_id, 'bot-enabled', trigger='manual')

    run_row = (
        await ap.persistence_mgr.execute_async(
            sqlalchemy.select(
                persistence_database_mode.MessageProcessingRun.status,
                persistence_database_mode.MessageProcessingRun.completed_at,
                persistence_database_mode.MessageProcessingRun.last_error,
            )
            .where(
                persistence_database_mode.MessageProcessingRun.message_id == message_id,
                persistence_database_mode.MessageProcessingRun.bot_uuid == 'bot-enabled',
            )
            .order_by(persistence_database_mode.MessageProcessingRun.id.desc())
            .limit(1)
        )
    ).mappings().first()
    assert run_row['status'] == RUN_STATUS_FAILED
    assert run_row['completed_at'] is not None
    assert 'cancel' in (run_row['last_error'] or '').lower()

    message_row = (
        await ap.persistence_mgr.execute_async(
            sqlalchemy.select(
                persistence_database_mode.DatabaseMessage.status,
                persistence_database_mode.DatabaseMessage.last_error,
            ).where(persistence_database_mode.DatabaseMessage.id == message_id)
        )
    ).mappings().first()
    assert message_row['status'] == MESSAGE_STATUS_FAILED
    assert 'cancel' in (message_row['last_error'] or '').lower()


async def test_processing_service_generate_draft_times_out_and_marks_run_failed(raw_processing_app):
    ap = raw_processing_app
    ap.instance_config = SimpleNamespace(data={'database_mode': {'draft_generation_timeout_seconds': 0.01}})
    processing_service = DatabaseModeProcessingService(ap)

    class _SlowRuntimeBot:
        def __init__(self):
            self.bot_entity = SimpleNamespace(uuid='bot-enabled', use_pipeline_uuid='pipeline-123')
            self.adapter = 'wxwork_database'

        def resolve_pipeline_uuid(self, launcher_type, launcher_id, message_text, message_element_types=None):
            return 'pipeline-123', False

        async def process_message_event_now(self, event, **kwargs):
            await asyncio.sleep(0.05)
            return None

    ap.platform_mgr = SimpleNamespace(bots=[_SlowRuntimeBot()])
    ap.pipeline_mgr = SimpleNamespace(get_pipeline_by_uuid=AsyncMock(return_value=SimpleNamespace()))
    ap.bot_service = SimpleNamespace(
        get_bot=AsyncMock(return_value={
            'uuid': 'bot-enabled',
            'adapter': 'wxwork_database',
            'enable': True,
            'adapter_config': {'connector_id': 'wxwork-local'},
        })
    )

    message_id = await _insert_bound_message(
        ap,
        account_suffix='timeout-processing',
        conversation_suffix='708',
        message_suffix='119',
        content='Need timeout handling',
        sender_id='306',
        sender_name='Customer R',
    )

    with pytest.raises(asyncio.TimeoutError):
        await processing_service.generate_draft(message_id, 'bot-enabled', trigger='manual')

    run_row = (
        await ap.persistence_mgr.execute_async(
            sqlalchemy.select(
                persistence_database_mode.MessageProcessingRun.status,
                persistence_database_mode.MessageProcessingRun.completed_at,
                persistence_database_mode.MessageProcessingRun.last_error,
            )
            .where(
                persistence_database_mode.MessageProcessingRun.message_id == message_id,
                persistence_database_mode.MessageProcessingRun.bot_uuid == 'bot-enabled',
            )
            .order_by(persistence_database_mode.MessageProcessingRun.id.desc())
            .limit(1)
        )
    ).mappings().first()
    assert run_row['status'] == RUN_STATUS_FAILED
    assert run_row['completed_at'] is not None
    assert 'timed out' in (run_row['last_error'] or '').lower()

    message_row = (
        await ap.persistence_mgr.execute_async(
            sqlalchemy.select(
                persistence_database_mode.DatabaseMessage.status,
                persistence_database_mode.DatabaseMessage.last_error,
            ).where(persistence_database_mode.DatabaseMessage.id == message_id)
        )
    ).mappings().first()
    assert message_row['status'] == MESSAGE_STATUS_FAILED
    assert 'timed out' in (message_row['last_error'] or '').lower()


async def test_processing_service_reconcile_stale_processing_runs_is_idempotent(raw_processing_app):
    ap = raw_processing_app
    ap.instance_config = SimpleNamespace(data={'database_mode': {'processing_run_stale_seconds': 300}})
    ap.logger = DummySyncLogger()
    processing_service = DatabaseModeProcessingService(ap)

    message_id = await _insert_bound_message(
        ap,
        account_suffix='reconcile-processing',
        conversation_suffix='709',
        message_suffix='120',
        content='Need reconcile handling',
        sender_id='307',
        sender_name='Customer S',
    )

    stale_started_at = (
        datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=20)
    ).replace(tzinfo=None)
    async with ap.persistence_mgr.get_db_engine().begin() as conn:
        await conn.execute(
            sqlalchemy.insert(persistence_database_mode.MessageProcessingRun).values({
                'message_id': message_id,
                'bot_uuid': 'bot-enabled',
                'pipeline_uuid': None,
                'trigger': 'automatic',
                'status': RUN_STATUS_PROCESSING,
                'attempt_count': 1,
                'started_at': stale_started_at,
                'completed_at': None,
                'last_error': None,
            })
        )
        await conn.execute(
            sqlalchemy.update(persistence_database_mode.DatabaseMessage)
            .where(persistence_database_mode.DatabaseMessage.id == message_id)
            .values({'status': 'processing', 'last_error': None})
        )

    await processing_service.reconcile_stale_processing_runs()
    await processing_service.reconcile_stale_processing_runs()

    run_rows = (
        await ap.persistence_mgr.execute_async(
            sqlalchemy.select(
                persistence_database_mode.MessageProcessingRun.status,
                persistence_database_mode.MessageProcessingRun.completed_at,
                persistence_database_mode.MessageProcessingRun.last_error,
            ).where(
                persistence_database_mode.MessageProcessingRun.message_id == message_id,
                persistence_database_mode.MessageProcessingRun.bot_uuid == 'bot-enabled',
            )
        )
    ).mappings().all()
    assert len(run_rows) == 1
    assert run_rows[0]['status'] == RUN_STATUS_FAILED
    assert run_rows[0]['completed_at'] is not None
    assert run_rows[0]['last_error'] == 'Stale processing run recovered after timeout'

    message_row = (
        await ap.persistence_mgr.execute_async(
            sqlalchemy.select(
                persistence_database_mode.DatabaseMessage.status,
                persistence_database_mode.DatabaseMessage.last_error,
            ).where(persistence_database_mode.DatabaseMessage.id == message_id)
        )
    ).mappings().first()
    assert message_row['status'] == MESSAGE_STATUS_FAILED
    assert message_row['last_error'] == 'Stale processing run recovered after timeout'


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

    # Set up mocks
    ap.bot_service = SimpleNamespace(
        get_bots=AsyncMock(return_value=[{
            'uuid': 'bot-1',
            'adapter': 'wxwork_database',
            'enable': True,
            'adapter_config': {'connector_id': 'wxwork-local'}
        }])
    )

    async def failing_generate_draft(msg_id, bot_uuid, trigger='manual'):
        ap.persistence_mgr.fail_next_commit = True
        async with ap.persistence_mgr.get_db_engine().begin() as conn:
            await conn.execute(
                sqlalchemy.update(persistence_database_mode.DatabaseMessage)
                .where(persistence_database_mode.DatabaseMessage.id == msg_id)
                .values({'status': MESSAGE_STATUS_DRAFT_READY, 'draft_text': 'Will fail'})
            )
        return {'status': 'succeeded'}

    ap.database_mode_processing_service = SimpleNamespace(generate_draft=failing_generate_draft)
    ap.database_mode_event_bus.published_events.clear()

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


async def test_list_conversations_can_filter_by_connector_id(service_app):
    service, ap = service_app
    await service.ingest_internal_event(_sample_payload())
    async with ap.persistence_mgr.get_db_engine().begin() as conn:
        await conn.execute(
            sqlalchemy.insert(persistence_database_mode.DatabaseConversation).values(
                {
                    "connector_id": "other-connector",
                    "source": "wxwork",
                    "external_conversation_id": "S:200_300",
                    "conversation_name": "Other Customer",
                    "conversation_type": "direct",
                    "last_message_at": datetime.datetime.now(datetime.timezone.utc),
                }
            )
        )

    result = await service.list_conversations(connector_id="wxwork-local")

    assert result["total"] == 1
    assert [conversation["connector_id"] for conversation in result["conversations"]] == ["wxwork-local"]


async def test_get_conversation_and_list_messages_can_filter_by_connector_id(service_app):
    service, _ = service_app
    await service.ingest_internal_event(_sample_payload())
    result = await service.list_conversations(connector_id="wxwork-local")
    conversation_id = result["conversations"][0]["id"]

    conversation = await service.get_conversation(conversation_id, connector_id="wxwork-local")
    assert conversation is not None
    assert conversation["connector_id"] == "wxwork-local"

    messages = await service.list_messages(conversation_id, connector_id="wxwork-local")
    assert messages["total"] == 1
    assert messages["messages"][0]["status"] == MESSAGE_STATUS_PENDING


async def test_auto_draft_schedule_loads_binding_as_model_even_when_scalar_path_is_misleading(raw_processing_app):
    ap = raw_processing_app
    service = DatabaseModeService(ap)
    scheduled = []
    generated = []

    async with ap.persistence_mgr.get_db_engine().begin() as conn:
        await conn.execute(
            sqlalchemy.insert(persistence_bot.Bot).values({
                'uuid': 'bot-enabled',
                'name': 'Database Bot',
                'description': '',
                'adapter': 'wxwork_database',
                'adapter_config': {'connector_id': 'wxwork-local'},
                'enable': True,
                'use_pipeline_name': None,
                'use_pipeline_uuid': 'pipeline-123',
                'pipeline_routing_rules': [],
            })
        )
        channel_account_result = await conn.execute(
            sqlalchemy.insert(persistence_database_mode.ChannelAccount).values({
                'connector_id': 'wxwork-local',
                'channel_type': 'wxwork',
                'external_account_id': 'acc-auto-draft-binding',
                'display_name': 'Raw Account',
                'enabled': True,
            })
        )
        channel_account_id = channel_account_result.inserted_primary_key[0]
        await conn.execute(
            sqlalchemy.insert(persistence_database_mode.BotChannelBinding).values({
                'bot_uuid': 'bot-enabled',
                'channel_account_id': channel_account_id,
                'enabled': True,
                'auto_generate_draft': True,
            })
        )
        conversation_result = await conn.execute(
            sqlalchemy.insert(persistence_database_mode.DatabaseConversation).values({
                'connector_id': 'wxwork-local',
                'source': 'wxwork',
                'external_conversation_id': 'S:100_auto_draft',
                'conversation_name': 'Customer Auto',
                'conversation_type': 'direct',
                'last_message_at': datetime.datetime.now(datetime.timezone.utc),
            })
        )
        conversation_id = conversation_result.inserted_primary_key[0]
        message_result = await conn.execute(
            sqlalchemy.insert(persistence_database_mode.DatabaseMessage).values({
                'event_id': 'wxwork-local:evt-auto-draft-binding',
                'message_key': 'wxwork-local:key-auto-draft-binding',
                'conversation_id': conversation_id,
                'external_message_id': 'auto-draft-1',
                'sender_id': '300',
                'sender_name': 'Customer Auto',
                'content': 'Please draft this automatically',
                'message_type': 'text',
                'sent_at': datetime.datetime.now(datetime.timezone.utc),
                'observed_at': datetime.datetime.now(datetime.timezone.utc),
                'status': MESSAGE_STATUS_PENDING,
            })
        )
        message_id = message_result.inserted_primary_key[0]

    binding_model = await service._fetch_required_model(
        persistence_database_mode.BotChannelBinding,
        sqlalchemy.select(persistence_database_mode.BotChannelBinding).where(
            persistence_database_mode.BotChannelBinding.bot_uuid == 'bot-enabled',
            persistence_database_mode.BotChannelBinding.channel_account_id == channel_account_id,
        ),
        error_message='Binding should exist for test setup',
    )

    original_execute_async = ap.persistence_mgr.execute_async

    async def execute_async_with_misleading_binding(*args, conn=None, **kwargs):
        stmt = args[0] if args else None
        text = str(stmt) if stmt is not None else ''
        if (
            conn is None
            and 'FROM bot_channel_bindings' in text
            and 'channel_account_id' in text
            and 'bot_uuid' in text
        ):
            class _MisleadingBindingResult:
                def scalars(self):
                    class _Scalars:
                        def first(self_inner):
                            return channel_account_id

                    return _Scalars()

                def first(self):
                    return SimpleNamespace(
                        _mapping={persistence_database_mode.BotChannelBinding: binding_model}
                    )

                def keys(self):
                    return ['BotChannelBinding']

            return _MisleadingBindingResult()
        return await original_execute_async(*args, conn=conn, **kwargs)

    ap.persistence_mgr.execute_async = execute_async_with_misleading_binding
    ap.bot_service = SimpleNamespace(
        get_bots=AsyncMock(side_effect=lambda include_secret=True: [{
            'uuid': 'bot-enabled',
            'adapter': 'wxwork_database',
            'enable': True,
            'adapter_config': {'connector_id': 'wxwork-local'},
        }]),
        get_bot=AsyncMock(return_value={
            'uuid': 'bot-enabled',
            'adapter': 'wxwork_database',
            'enable': True,
            'adapter_config': {'connector_id': 'wxwork-local'},
        }),
    )
    ap.database_mode_processing_service = SimpleNamespace(
        generate_draft=AsyncMock(side_effect=lambda message_id, bot_uuid, trigger='automatic': generated.append({
            'message_id': message_id,
            'bot_uuid': bot_uuid,
            'trigger': trigger,
        }) or {'status': 'succeeded'})
    )

    class _TaskManager:
        def create_task(self, coro, **kwargs):
            scheduled.append({'coro': coro, 'kwargs': kwargs})
            return SimpleNamespace(id='task-auto-draft')

    ap.task_mgr = _TaskManager()

    await service._maybe_schedule_auto_draft(message_id, conversation_id)

    assert len(scheduled) == 1
    assert scheduled[0]['kwargs']['name'] == f'auto-draft-{message_id}'
    assert scheduled[0]['kwargs']['kind'] == 'database-mode-auto-draft'

    await scheduled[0]['coro']
    assert generated == [{
        'message_id': message_id,
        'bot_uuid': 'bot-enabled',
        'trigger': 'automatic',
    }]




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
