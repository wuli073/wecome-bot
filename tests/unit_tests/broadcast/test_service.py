from __future__ import annotations

import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import sqlalchemy
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

from langbot.pkg.entity.persistence import bot as persistence_bot
from langbot.pkg.entity.persistence import broadcast as persistence_broadcast
from langbot.pkg.entity.persistence import database_mode as persistence_database_mode
from langbot.pkg.broadcast.errors import (
    BROADCAST_VARIABLE_PROFILE_INVALID,
    BroadcastError,
)


pytestmark = pytest.mark.asyncio


class _TransactionContext:
    def __init__(self, manager: '_MiniPersistenceManager') -> None:
        self._manager = manager
        self._conn: AsyncConnection | None = None
        self._tx = None

    async def __aenter__(self) -> AsyncConnection:
        self._conn = await self._manager.engine.connect()
        self._tx = await self._conn.begin()
        return self._conn

    async def __aexit__(self, exc_type, exc, tb) -> None:
        try:
            if exc_type is not None:
                await self._tx.rollback()
                return
            await self._tx.commit()
        finally:
            if self._conn is not None:
                await self._conn.close()


class _EngineProxy:
    def __init__(self, manager: '_MiniPersistenceManager') -> None:
        self._manager = manager

    def begin(self) -> _TransactionContext:
        return _TransactionContext(self._manager)


class _MiniPersistenceManager:
    def __init__(self) -> None:
        self.engine = create_async_engine('sqlite+aiosqlite:///:memory:')
        self.engine_proxy = _EngineProxy(self)

    async def initialize(self) -> None:
        async with self.engine.begin() as conn:
            await conn.run_sync(persistence_bot.Bot.__table__.create)
            await conn.run_sync(persistence_database_mode.ChannelAccount.__table__.create)
            await conn.run_sync(persistence_database_mode.BotChannelBinding.__table__.create)
            await conn.run_sync(persistence_broadcast.BroadcastTemplate.__table__.create)
            await conn.run_sync(persistence_broadcast.BroadcastVariableProfile.__table__.create)
            await conn.run_sync(persistence_broadcast.BroadcastGroupRule.__table__.create)
            await conn.run_sync(persistence_broadcast.BroadcastGroupName.__table__.create)

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
async def service_fixture():
    from langbot.pkg.broadcast.service import BroadcastService

    persistence_mgr = _MiniPersistenceManager()
    await persistence_mgr.initialize()

    ap = SimpleNamespace(
        persistence_mgr=persistence_mgr,
        bot_service=SimpleNamespace(
            get_bot=AsyncMock(
                side_effect=lambda bot_uuid, include_secret=False: {
                    'uuid': bot_uuid,
                    'adapter': 'wxwork_database',
                    'enable': True,
                    'adapter_config': {'connector_id': 'wxwork-local'},
                }
                if bot_uuid in {'bot-1', 'bot-2'}
                else None
            )
        ),
    )

    async with persistence_mgr.engine.begin() as conn:
        await conn.execute(
            sqlalchemy.insert(persistence_bot.Bot).values(
                {
                    'uuid': 'bot-1',
                    'name': 'Bot 1',
                    'description': '',
                    'adapter': 'wxwork_database',
                    'adapter_config': {'connector_id': 'wxwork-local'},
                    'enable': True,
                    'pipeline_routing_rules': [],
                }
            )
        )
        await conn.execute(
            sqlalchemy.insert(persistence_bot.Bot).values(
                {
                    'uuid': 'bot-2',
                    'name': 'Bot 2',
                    'description': '',
                    'adapter': 'wxwork_database',
                    'adapter_config': {'connector_id': 'wxwork-other'},
                    'enable': True,
                    'pipeline_routing_rules': [],
                }
            )
        )
        channel_account_id = (
            await conn.execute(
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
        ).inserted_primary_key[0]
        channel_account_id_other = (
            await conn.execute(
                sqlalchemy.insert(persistence_database_mode.ChannelAccount).values(
                    {
                        'connector_id': 'wxwork-other',
                        'channel_type': 'wxwork_database',
                        'external_account_id': 'wxwork-other',
                        'display_name': 'WXWork Database Other',
                        'enabled': True,
                        'channel_metadata': {},
                    }
                )
            )
        ).inserted_primary_key[0]
        await conn.execute(
            sqlalchemy.insert(persistence_database_mode.BotChannelBinding).values(
                {
                    'bot_uuid': 'bot-1',
                    'channel_account_id': channel_account_id,
                    'enabled': True,
                    'auto_generate_draft': False,
                }
            )
        )
        await conn.execute(
            sqlalchemy.insert(persistence_database_mode.BotChannelBinding).values(
                {
                    'bot_uuid': 'bot-2',
                    'channel_account_id': channel_account_id_other,
                    'enabled': True,
                    'auto_generate_draft': False,
                }
            )
        )

    try:
        yield BroadcastService(ap), persistence_mgr
    finally:
        await persistence_mgr.dispose()


def _scope(bot_uuid: str = 'bot-1', connector_id: str = 'wxwork-local') -> dict[str, str]:
    return {
        'bot_uuid': bot_uuid,
        'connector_id': connector_id,
    }


async def test_render_template_requires_exactly_one_of_template_id_or_content(service_fixture):
    service, _ = service_fixture

    with pytest.raises(Exception, match='TEMPLATE_RENDER_INPUT_INVALID'):
        await service.render_template(
            _scope(),
            {
                'variables': {},
            },
        )

    with pytest.raises(Exception, match='TEMPLATE_RENDER_INPUT_INVALID'):
        await service.render_template(
            _scope(),
            {
                'template_id': 1,
                'content': 'Hello {{name}}',
                'variables': {},
            },
        )


async def test_render_template_extracts_and_reports_missing_variables(service_fixture):
    service, _ = service_fixture

    result = await service.render_template(
        _scope(),
        {
            'content': 'Hello {{name}}, order {{order_no}}, hello {{name}}',
            'variables': {'name': 'Acme'},
        },
    )

    assert result['rendered_text'] == 'Hello Acme, order {{order_no}}, hello Acme'
    assert result['required_variables'] == ['name', 'order_no']
    assert result['missing_variables'] == ['order_no']
    assert result['valid'] is False


async def test_save_variable_profile_rejects_duplicate_variable_keys_and_invalid_merge_mode(service_fixture):
    service, _ = service_fixture

    with pytest.raises(Exception, match='BROADCAST_VARIABLE_PROFILE_INVALID'):
        await service.save_variable_profile(
            _scope(),
            {
                'group_field': 'customer_name',
                'mapping_rules': [
                    {
                        'source_field': 'Customer',
                        'variable_key': 'customer_name',
                        'merge_mode': 'bad-mode',
                        'order': 1,
                    }
                ],
            },
        )


async def test_save_variable_profile_returns_actionable_chinese_error_details(service_fixture):
    service, _ = service_fixture

    with pytest.raises(BroadcastError) as exc_info:
        await service.save_variable_profile(
            _scope(),
            {
                'group_field': '',
                'mapping_rules': [
                    {
                        'source_field': '客户名称',
                        'variable_key': '',
                        'merge_mode': 'first',
                        'order': 1,
                    }
                ],
            },
        )

    error = exc_info.value
    assert error.code == BROADCAST_VARIABLE_PROFILE_INVALID
    assert error.message == '变量配置填写不完整，请检查后重试'
    assert error.details == ['请填写分组字段', '第 1 条规则缺少消息变量']


async def test_save_variable_profile_rejects_duplicate_keys_and_brace_wrapped_values_with_details(
    service_fixture,
):
    service, _ = service_fixture

    with pytest.raises(BroadcastError) as exc_info:
        await service.save_variable_profile(
            _scope(),
            {
                'group_field': '客户名称',
                'mapping_rules': [
                    {
                        'source_field': '客户名称',
                        'variable_key': 'customer_name',
                        'merge_mode': 'first',
                        'order': 1,
                    },
                    {
                        'source_field': '客户简称',
                        'variable_key': 'customer_name',
                        'merge_mode': 'lines',
                        'order': 2,
                    },
                    {
                        'source_field': '{{客户名称}}',
                        'variable_key': 'customer_alias',
                        'merge_mode': 'first',
                        'order': 3,
                    },
                ],
            },
        )

    error = exc_info.value
    assert error.code == BROADCAST_VARIABLE_PROFILE_INVALID
    assert error.message == '变量配置填写有误，请按提示修改'
    assert error.details == [
        '消息变量“customer_name”重复',
        '请填写“客户名称”，不要填写“{{客户名称}}”',
    ]

    with pytest.raises(Exception, match='BROADCAST_VARIABLE_PROFILE_INVALID'):
        await service.save_variable_profile(
            _scope(),
            {
                'group_field': 'customer_name',
                'mapping_rules': [
                    {
                        'source_field': 'Customer',
                        'variable_key': 'customer_name',
                        'merge_mode': 'first',
                        'order': 1,
                    },
                    {
                        'source_field': 'Customer Alias',
                        'variable_key': 'customer_name',
                        'merge_mode': 'lines',
                        'order': 2,
                    },
                ],
            },
        )


async def test_create_group_rule_rejects_invalid_regex(service_fixture):
    service, _ = service_fixture

    with pytest.raises(Exception, match='BROADCAST_GROUP_RULE_REGEX_INVALID'):
        await service.create_group_rule(
            _scope(),
            {
                'source_value': 'Acme',
                'match_type': 'regex',
                'match_expression': '[',
                'target_conversation_name': 'Acme Group',
                'priority': 1,
                'enabled': True,
            },
        )


async def test_group_names_are_trimmed_deduped_and_persisted(service_fixture):
    service, _ = service_fixture

    result = await service.create_group_names(
        _scope(),
        {
            'names': ['  Acme Group  ', 'Acme Group', '', ' Northwind Group '],
        },
    )

    assert [item['name'] for item in result['group_names']] == ['Acme Group', 'Northwind Group']

    listed = await service.list_group_names(_scope())
    assert [item['name'] for item in listed] == ['Acme Group', 'Northwind Group']


async def test_validate_scope_rejects_connector_mismatch(service_fixture):
    service, _ = service_fixture

    with pytest.raises(Exception, match='BROADCAST_SCOPE_REQUIRED'):
        await service.validate_scope(
            {
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-other',
            }
        )


async def test_template_crud_extracts_variables_and_rejects_duplicate_names(service_fixture):
    service, _ = service_fixture

    created = await service.create_template(
        _scope(),
        {
            'name': 'Arrival Reminder',
            'content': 'Hello {{customer_name}}, order {{order_no}}',
            'enabled': True,
        },
    )

    assert created['name'] == 'Arrival Reminder'
    assert created['variables'] == ['customer_name', 'order_no']

    rendered = await service.render_template(
        _scope(),
        {
            'template_id': created['id'],
            'variables': {
                'customer_name': 'Acme',
                'order_no': 'SO-1001',
            },
        },
    )
    assert rendered['rendered_text'] == 'Hello Acme, order SO-1001'
    assert rendered['valid'] is True

    with pytest.raises(Exception, match='BROADCAST_TEMPLATE_NAME_DUPLICATE'):
        await service.create_template(
            _scope(),
            {
                'name': 'Arrival Reminder',
                'content': 'Duplicate {{customer_name}}',
                'enabled': False,
            },
        )

    updated = await service.update_template(
        created['id'],
        _scope(),
        {
            'name': 'Arrival Reminder V2',
            'content': 'Hi {{customer_name}}',
            'enabled': False,
        },
    )
    assert updated['name'] == 'Arrival Reminder V2'
    assert updated['variables'] == ['customer_name']
    assert updated['enabled'] is False

    await service.delete_template(created['id'], _scope())
    assert await service.list_templates(_scope()) == []


async def test_group_rule_crud_match_and_scope_isolation(service_fixture):
    service, _ = service_fixture

    low_priority = await service.create_group_rule(
        _scope(),
        {
            'source_value': 'Acme',
            'match_type': 'contains',
            'match_expression': 'Acme',
            'target_conversation_name': 'Acme Backup',
            'priority': 1,
            'enabled': True,
        },
    )
    high_priority = await service.create_group_rule(
        _scope(),
        {
            'source_value': 'Acme',
            'match_type': 'exact',
            'match_expression': 'Acme',
            'target_conversation_name': 'Acme Primary',
            'priority': 10,
            'enabled': True,
        },
    )
    await service.create_group_rule(
        _scope(bot_uuid='bot-2', connector_id='wxwork-other'),
        {
            'source_value': 'Acme',
            'match_type': 'exact',
            'match_expression': 'Acme',
            'target_conversation_name': 'Other Scope',
            'priority': 99,
            'enabled': True,
        },
    )

    rules = await service.list_group_rules(_scope())
    assert [rule['id'] for rule in rules] == [high_priority['id'], low_priority['id']]

    matched = await service.match_group_rule(
        _scope(),
        {
            'source_value': 'Acme',
        },
    )
    assert matched == {
        'matched': True,
        'rule_id': high_priority['id'],
        'target_conversation_name': 'Acme Primary',
        'match_type': 'exact',
    }

    updated = await service.update_group_rule(
        high_priority['id'],
        _scope(),
        {
            'source_value': 'Acme',
            'match_type': 'regex',
            'match_expression': '^Acme$',
            'target_conversation_name': 'Acme Regex',
            'priority': 15,
            'enabled': False,
        },
    )
    assert updated['match_type'] == 'regex'
    assert updated['enabled'] is False

    matched_after_disable = await service.match_group_rule(
        _scope(),
        {
            'source_value': 'Acme',
        },
    )
    assert matched_after_disable == {
        'matched': True,
        'rule_id': low_priority['id'],
        'target_conversation_name': 'Acme Backup',
        'match_type': 'contains',
    }

    await service.delete_group_rule(low_priority['id'], _scope())

    with pytest.raises(Exception, match='BROADCAST_GROUP_RULE_NOT_FOUND'):
        await service.delete_group_rule(low_priority['id'], _scope())


async def test_group_names_reject_existing_duplicate_and_delete_by_scope(service_fixture):
    service, _ = service_fixture

    await service.create_group_names(
        _scope(),
        {
            'names': ['Acme Ops Group'],
        },
    )

    with pytest.raises(Exception, match='BROADCAST_GROUP_NAME_DUPLICATE'):
        await service.create_group_names(
            _scope(),
            {
                'name': 'Acme Ops Group',
            },
        )

    group_names = await service.list_group_names(_scope())
    await service.delete_group_name(group_names[0]['id'], _scope())
    assert await service.list_group_names(_scope()) == []
