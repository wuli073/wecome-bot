import asyncio
import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import sqlalchemy
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.sql.dml import Update

from langbot.pkg.api.http.service.bot import BotService
from langbot.pkg.entity.persistence import bot as persistence_bot
from langbot.pkg.entity.persistence import database_mode as persistence_database_mode
from langbot.pkg.entity.persistence import pipeline as persistence_pipeline


class _FakeResult:
    def __init__(self, value):
        self.value = value

    def first(self):
        return self.value


class _PersistenceManager:
    def __init__(self, db_url: str = "sqlite+aiosqlite:///:memory:"):
        self.engine = create_async_engine(db_url)
        self.sessionmaker = async_sessionmaker(self.engine, expire_on_commit=False)
        self.update_values = None
        self.insert_values = None

    async def initialize(self):
        async with self.engine.begin() as conn:
            await conn.run_sync(persistence_bot.Bot.__table__.create)
            await conn.run_sync(persistence_pipeline.LegacyPipeline.__table__.create)
            await conn.run_sync(persistence_database_mode.ChannelAccount.__table__.create)
            await conn.run_sync(persistence_database_mode.BotChannelBinding.__table__.create)

    async def execute_async(self, statement):
        if isinstance(statement, Update) and getattr(statement.table, 'name', None) == persistence_bot.Bot.__tablename__:
            self.update_values = {
                key: value for key, value in statement.compile().params.items() if not key.startswith('uuid_')
            }

        statement_type = statement.__class__.__name__.lower()
        if 'insert' in statement_type and getattr(statement, 'table', None) is not None:
            if statement.table.name == persistence_bot.Bot.__tablename__:
                self.insert_values = dict(statement.compile().params)

        async with self.sessionmaker() as session:
            result = await session.execute(statement)
            if statement_type in {'insert', 'update', 'delete'}:
                await session.commit()
                return result
            await session.commit()

            rows = list(result.all())

            class _MaterializedResult:
                def __init__(self, rows):
                    self._rows = rows

                @staticmethod
                def _unwrap(row):
                    if hasattr(row, '_mapping'):
                        values = list(row._mapping.values())
                        if len(values) == 1:
                            return values[0]
                    if isinstance(row, tuple) and len(row) == 1:
                        return row[0]
                    return row

                def first(self):
                    return self._unwrap(self._rows[0]) if self._rows else None

                def all(self):
                    return [self._unwrap(row) for row in self._rows]

                def scalar(self):
                    return self.first()

                def scalar_one(self):
                    value = self.scalar()
                    if value is None:
                        raise LookupError('No rows')
                    return value

                def scalars(self):
                    outer = self

                    class _Scalars:
                        def first(self_inner):
                            values = self_inner.all()
                            return values[0] if values else None

                        def all(self_inner):
                            return [outer._unwrap(row) for row in outer._rows]

                    return _Scalars()

            return _MaterializedResult(rows)

    async def get_channel_account(self, connector_id: str = 'wxwork-local'):
        result = await self.execute_async(
            sqlalchemy.select(persistence_database_mode.ChannelAccount).where(
                persistence_database_mode.ChannelAccount.connector_id == connector_id,
                persistence_database_mode.ChannelAccount.channel_type == 'wxwork_database',
                persistence_database_mode.ChannelAccount.external_account_id == connector_id,
            )
        )
        return result.scalars().first()

    async def get_binding(self, bot_uuid: str):
        result = await self.execute_async(
            sqlalchemy.select(persistence_database_mode.BotChannelBinding).where(
                persistence_database_mode.BotChannelBinding.bot_uuid == bot_uuid
            )
        )
        return result.scalars().first()

    def serialize_model(self, model, data, masked_columns=None):
        masked_columns = masked_columns or []
        return {
            column.name: getattr(data, column.name)
            if not isinstance(getattr(data, column.name), datetime.datetime)
            else getattr(data, column.name).isoformat()
            for column in model.__table__.columns
            if column.name not in masked_columns
        }

    async def dispose(self):
        await self.engine.dispose()


async def test_update_bot_copies_input_before_filtering_and_setting_pipeline_name():
    persistence_mgr = _PersistenceManager()
    await persistence_mgr.initialize()
    async with persistence_mgr.sessionmaker() as session:
        await session.execute(
            sqlalchemy.insert(persistence_pipeline.LegacyPipeline).values(
                {
                    'uuid': 'pipeline-1',
                    'name': 'Updated Pipeline',
                    'description': 'desc',
                    'for_version': '1.0',
                    'is_default': False,
                    'stages': [],
                    'config': {},
                    'extensions_preferences': {'enable_all_plugins': True, 'enable_all_mcp_servers': True, 'plugins': [], 'mcp_servers': []},
                }
            )
        )
        await session.commit()
    runtime_bot = SimpleNamespace(enable=False)
    platform_mgr = SimpleNamespace(
        remove_bot=AsyncMock(),
        load_bot=AsyncMock(return_value=runtime_bot),
    )
    ap = SimpleNamespace(
        persistence_mgr=persistence_mgr,
        platform_mgr=platform_mgr,
        sess_mgr=SimpleNamespace(session_list=[]),
    )
    service = BotService(ap)
    service.get_bot = AsyncMock(return_value={'uuid': 'bot-1'})
    payload = {
        'uuid': 'caller-owned-uuid',
        'name': 'Test Bot',
        'use_pipeline_uuid': 'pipeline-1',
    }

    await service.update_bot('bot-1', payload)

    assert payload == {
        'uuid': 'caller-owned-uuid',
        'name': 'Test Bot',
        'use_pipeline_uuid': 'pipeline-1',
    }
    assert persistence_mgr.update_values == {
        'name': 'Test Bot',
        'use_pipeline_uuid': 'pipeline-1',
        'use_pipeline_name': 'Updated Pipeline',
    }


async def test_create_wxwork_database_bot_sets_processing_since_and_binding_defaults():
    persistence_mgr = _PersistenceManager()
    await persistence_mgr.initialize()
    platform_mgr = SimpleNamespace(load_bot=AsyncMock())
    ap = SimpleNamespace(
        instance_config=SimpleNamespace(data={'system': {'limitation': {}}}),
        persistence_mgr=persistence_mgr,
        platform_mgr=platform_mgr,
    )
    service = BotService(ap)
    service.get_bots = AsyncMock(return_value=[])
    service.get_bot = AsyncMock(return_value={'uuid': 'created-bot'})

    payload = {
        'name': 'WXWork DB Bot',
        'description': 'desc',
        'adapter': 'wxwork_database',
        'adapter_config': {
            'connector_id': 'wxwork-local',
            'auto_generate_draft': True,
        },
        'enable': True,
    }

    bot_uuid = await service.create_bot(payload)

    assert bot_uuid == 'created-bot'
    assert payload['adapter_config']['connector_id'] == 'wxwork-local'
    assert payload['adapter_config']['auto_generate_draft'] is True
    assert payload['adapter_config']['processing_since']
    assert persistence_mgr.insert_values['adapter'] == 'wxwork_database'
    channel_account = await persistence_mgr.get_channel_account()
    created_bot_uuid = persistence_mgr.insert_values['uuid']
    binding = await persistence_mgr.get_binding(created_bot_uuid)
    assert channel_account is not None
    assert channel_account.connector_id == 'wxwork-local'
    assert channel_account.channel_type == 'wxwork_database'
    assert channel_account.external_account_id == 'wxwork-local'
    assert binding is not None
    assert binding.bot_uuid == created_bot_uuid
    assert binding.enabled is True
    assert binding.auto_generate_draft is True
    assert binding.effective_from is not None
    await persistence_mgr.dispose()


async def test_create_wxwork_database_bot_rejects_second_enabled_bot_on_same_connector():
    persistence_mgr = _PersistenceManager()
    await persistence_mgr.initialize()
    platform_mgr = SimpleNamespace(load_bot=AsyncMock())
    ap = SimpleNamespace(
        instance_config=SimpleNamespace(data={'system': {'limitation': {}}}),
        persistence_mgr=persistence_mgr,
        platform_mgr=platform_mgr,
    )
    service = BotService(ap)
    service.get_bots = AsyncMock(
        return_value=[
            {
                'uuid': 'existing-bot',
                'adapter': 'wxwork_database',
                'enable': True,
                'adapter_config': {'connector_id': 'wxwork-local'},
            }
        ]
    )

    with pytest.raises(ValueError, match='Only one enabled wxwork_database bot is allowed'):
        await service.create_bot(
            {
                'name': 'WXWork DB Bot 2',
                'description': 'desc',
                'adapter': 'wxwork_database',
                'adapter_config': {
                    'connector_id': 'wxwork-local',
                    'auto_generate_draft': True,
                },
                'enable': True,
            }
        )

    await persistence_mgr.dispose()


async def test_update_wxwork_database_bot_backfills_missing_binding_and_lifecycle_states():
    persistence_mgr = _PersistenceManager()
    await persistence_mgr.initialize()
    platform_mgr = SimpleNamespace(
        remove_bot=AsyncMock(),
        load_bot=AsyncMock(return_value=SimpleNamespace(enable=True, run=AsyncMock())),
    )
    ap = SimpleNamespace(
        instance_config=SimpleNamespace(data={'system': {'limitation': {}}}),
        persistence_mgr=persistence_mgr,
        platform_mgr=platform_mgr,
        sess_mgr=SimpleNamespace(session_list=[]),
    )
    service = BotService(ap)

    bot_uuid = 'existing-wxwork-bot'
    async with persistence_mgr.sessionmaker() as session:
        await session.execute(
            sqlalchemy.insert(persistence_bot.Bot).values(
                {
                    'uuid': bot_uuid,
                    'name': 'WXWork DB Bot',
                    'description': 'desc',
                    'adapter': 'wxwork_database',
                    'adapter_config': {'connector_id': 'wxwork-local', 'auto_generate_draft': True},
                    'enable': True,
                    'pipeline_routing_rules': [],
                }
            )
        )
        await session.commit()

    await service.update_bot(bot_uuid, {'name': 'Renamed Bot'})

    binding = await persistence_mgr.get_binding(bot_uuid)
    assert binding is not None
    assert binding.enabled is True
    assert binding.auto_generate_draft is True
    assert binding.effective_from is not None

    first_effective_from = binding.effective_from

    await service.update_bot(bot_uuid, {'enable': False})
    binding = await persistence_mgr.get_binding(bot_uuid)
    assert binding is not None
    assert binding.enabled is False
    assert binding.effective_from == first_effective_from

    await service.update_bot(bot_uuid, {'enable': True})
    binding = await persistence_mgr.get_binding(bot_uuid)
    assert binding is not None
    assert binding.enabled is True
    assert binding.effective_from is not None

    channel_account = await persistence_mgr.get_channel_account()
    assert channel_account is not None

    await service.update_bot(bot_uuid, {'adapter': 'telegram', 'adapter_config': {'token': 'abc'}})
    binding = await persistence_mgr.get_binding(bot_uuid)
    assert binding is not None
    assert binding.enabled is False
    channel_account = await persistence_mgr.get_channel_account()
    assert channel_account is not None


async def test_delete_wxwork_database_bot_removes_binding_but_keeps_channel_account():
    persistence_mgr = _PersistenceManager()
    await persistence_mgr.initialize()
    platform_mgr = SimpleNamespace(remove_bot=AsyncMock())
    ap = SimpleNamespace(
        persistence_mgr=persistence_mgr,
        platform_mgr=platform_mgr,
    )
    service = BotService(ap)

    bot_uuid = 'delete-wxwork-bot'
    async with persistence_mgr.sessionmaker() as session:
        await session.execute(
            sqlalchemy.insert(persistence_bot.Bot).values(
                {
                    'uuid': bot_uuid,
                    'name': 'WXWork DB Bot',
                    'description': 'desc',
                    'adapter': 'wxwork_database',
                    'adapter_config': {'connector_id': 'wxwork-local', 'auto_generate_draft': False},
                    'enable': True,
                    'pipeline_routing_rules': [],
                }
            )
        )
        await session.commit()

    await service._ensure_wxwork_database_binding(
        bot_uuid=bot_uuid,
        adapter_config={'connector_id': 'wxwork-local', 'auto_generate_draft': False},
        bot_enabled=True,
    )

    await service.delete_bot(bot_uuid)

    binding = await persistence_mgr.get_binding(bot_uuid)
    assert binding is None
    channel_account = await persistence_mgr.get_channel_account()
    assert channel_account is not None
    await persistence_mgr.dispose()


async def test_ensure_wxwork_database_binding_recovers_from_concurrent_insert(tmp_path):
    persistence_mgr = _PersistenceManager(f"sqlite+aiosqlite:///{tmp_path / 'concurrent_binding.db'}")
    await persistence_mgr.initialize()
    await persistence_mgr.execute_async(
        sqlalchemy.insert(persistence_database_mode.ChannelAccount).values(
            {
                'connector_id': 'wxwork-local',
                'channel_type': 'wxwork_database',
                'external_account_id': 'wxwork-local',
                'display_name': 'WXWork Database',
                'enabled': True,
                'channel_metadata': {},
            }
        )
    )
    async with persistence_mgr.engine.begin() as conn:
        await conn.execute(
            sqlalchemy.text(
                'CREATE UNIQUE INDEX ux_bot_channel_bindings_bot_channel '
                'ON bot_channel_bindings (bot_uuid, channel_account_id)'
            )
        )

    ap = SimpleNamespace(persistence_mgr=persistence_mgr)
    service = BotService(ap)
    adapter_config = {
        'connector_id': 'wxwork-local',
        'auto_generate_draft': True,
        'processing_since': '2026-06-21T10:00:00Z',
    }

    await asyncio.gather(
        service._ensure_wxwork_database_binding(
            bot_uuid='concurrent-bot',
            adapter_config=adapter_config,
            bot_enabled=True,
        ),
        service._ensure_wxwork_database_binding(
            bot_uuid='concurrent-bot',
            adapter_config=adapter_config,
            bot_enabled=True,
        ),
    )

    binding_count = (
        await persistence_mgr.execute_async(
            sqlalchemy.select(sqlalchemy.func.count()).select_from(persistence_database_mode.BotChannelBinding).where(
                persistence_database_mode.BotChannelBinding.bot_uuid == 'concurrent-bot'
            )
        )
    ).scalar_one()

    assert binding_count == 1
    await persistence_mgr.dispose()


async def test_repeated_save_of_wxwork_database_bot_keeps_single_binding():
    persistence_mgr = _PersistenceManager()
    await persistence_mgr.initialize()
    platform_mgr = SimpleNamespace(
        remove_bot=AsyncMock(),
        load_bot=AsyncMock(return_value=SimpleNamespace(enable=True, run=AsyncMock())),
    )
    ap = SimpleNamespace(
        persistence_mgr=persistence_mgr,
        platform_mgr=platform_mgr,
        sess_mgr=SimpleNamespace(session_list=[]),
    )
    service = BotService(ap)

    bot_uuid = 'save-wxwork-bot'
    async with persistence_mgr.sessionmaker() as session:
        await session.execute(
            sqlalchemy.insert(persistence_bot.Bot).values(
                {
                    'uuid': bot_uuid,
                    'name': 'WXWork DB Bot',
                    'description': 'desc',
                    'adapter': 'wxwork_database',
                    'adapter_config': {'connector_id': 'wxwork-local', 'auto_generate_draft': False},
                    'enable': True,
                    'pipeline_routing_rules': [],
                }
            )
        )
        await session.commit()

    await service.update_bot(bot_uuid, {'name': 'Renamed Bot 1'})
    await service.update_bot(bot_uuid, {'name': 'Renamed Bot 2'})
    await service.update_bot(bot_uuid, {'enable': True})

    binding_count = (
        await persistence_mgr.execute_async(
            sqlalchemy.select(sqlalchemy.func.count()).select_from(persistence_database_mode.BotChannelBinding).where(
                persistence_database_mode.BotChannelBinding.bot_uuid == bot_uuid
            )
        )
    ).scalar_one()

    assert binding_count == 1
    await persistence_mgr.dispose()


async def test_update_wxwork_database_bot_rejects_enabling_when_another_enabled_bot_exists():
    persistence_mgr = _PersistenceManager()
    platform_mgr = SimpleNamespace(
        remove_bot=AsyncMock(),
        load_bot=AsyncMock(return_value=SimpleNamespace(enable=False)),
    )
    ap = SimpleNamespace(
        persistence_mgr=persistence_mgr,
        platform_mgr=platform_mgr,
        sess_mgr=SimpleNamespace(session_list=[]),
    )
    service = BotService(ap)
    service.get_bot = AsyncMock(
        side_effect=[
            {
                'uuid': 'bot-2',
                'adapter': 'wxwork_database',
                'enable': False,
                'adapter_config': {'connector_id': 'wxwork-local'},
            }
        ]
    )
    service.get_bots = AsyncMock(
        return_value=[
            {
                'uuid': 'bot-1',
                'adapter': 'wxwork_database',
                'enable': True,
                'adapter_config': {'connector_id': 'wxwork-local'},
            },
            {
                'uuid': 'bot-2',
                'adapter': 'wxwork_database',
                'enable': False,
                'adapter_config': {'connector_id': 'wxwork-local'},
            },
        ]
    )

    with pytest.raises(ValueError, match='Only one enabled wxwork_database bot is allowed'):
        await service.update_bot(
            'bot-2',
            {
                'enable': True,
                'adapter_config': {
                    'connector_id': 'wxwork-local',
                    'auto_generate_draft': False,
                },
            },
        )

    await persistence_mgr.dispose()
