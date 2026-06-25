from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.sql.dml import Update

from langbot.pkg.api.http.service.bot import BotService


class _FakeResult:
    def __init__(self, value):
        self.value = value

    def first(self):
        return self.value


class _PersistenceManager:
    def __init__(self):
        self.update_values = None
        self.insert_values = None

    async def execute_async(self, statement):
        if isinstance(statement, Update):
            self.update_values = {
                key: value for key, value in statement.compile().params.items() if not key.startswith('uuid_')
            }
            return None

        statement_type = statement.__class__.__name__.lower()
        if 'insert' in statement_type:
            self.insert_values = dict(statement.compile().params)
            return None

        return _FakeResult(SimpleNamespace(uuid='pipeline-1', name='Updated Pipeline'))


async def test_update_bot_copies_input_before_filtering_and_setting_pipeline_name():
    persistence_mgr = _PersistenceManager()
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


async def test_create_wxwork_database_bot_rejects_second_enabled_bot_on_same_connector():
    persistence_mgr = _PersistenceManager()
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
