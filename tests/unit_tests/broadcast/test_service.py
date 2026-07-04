from __future__ import annotations

import asyncio
import datetime
import hashlib
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import sqlalchemy
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

from langbot.pkg.entity.persistence import bot as persistence_bot
from langbot.pkg.entity.persistence import broadcast as persistence_broadcast
from langbot.pkg.entity.persistence import database_mode as persistence_database_mode
from langbot.pkg.broadcast.errors import (
    BROADCAST_GROUP_RULE_REGEX_INVALID,
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
            await conn.run_sync(persistence_database_mode.DatabaseConversation.__table__.create)
            await conn.run_sync(persistence_broadcast.BroadcastTemplate.__table__.create)
            await conn.run_sync(persistence_broadcast.BroadcastVariableProfile.__table__.create)
            await conn.run_sync(persistence_broadcast.BroadcastGroupRule.__table__.create)
            await conn.run_sync(persistence_broadcast.BroadcastGroupName.__table__.create)
            await conn.run_sync(persistence_broadcast.BroadcastImportBatch.__table__.create)
            await conn.run_sync(persistence_broadcast.BroadcastImportRow.__table__.create)
            await conn.run_sync(persistence_broadcast.BroadcastDraft.__table__.create)
            await conn.run_sync(persistence_broadcast.BroadcastExecutionBatch.__table__.create)
            await conn.run_sync(persistence_broadcast.BroadcastExecutionTask.__table__.create)
            await conn.run_sync(persistence_broadcast.BroadcastExecutionAttempt.__table__.create)
            await conn.run_sync(persistence_broadcast.BroadcastExecutionEvidence.__table__.create)
            await conn.run_sync(persistence_broadcast.BroadcastSendConfirmation.__table__.create)

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


class _FakeRuntimeClient:
    def __init__(self) -> None:
        self.requests: list[dict[str, object]] = []

    async def health(self):
        return {'status': 'ready', 'protocolVersion': '1'}

    async def capabilities(self):
        return {'supportsPaste': True, 'supportsSend': False}

    async def create_task(self, *, request: dict[str, object]):
        self.requests.append(request)
        return {
            'id': f"runtime-{len(self.requests)}",
            'status': 'succeeded',
            'stage': 'pasted_to_input',
            'result': {
                'messageSent': False,
                'clipboardRestoreFailed': False,
                'contentVerified': True,
                'draftWritten': True,
                'inputLocated': True,
            },
        }


class _DeferredRuntimeDesktopAutomationService:
    def __init__(self) -> None:
        self.runtime_client = None
        self.ensure_client_calls = 0
        self.health_calls = 0
        self.capability_calls = 0
        self.create_task_calls: list[dict[str, object]] = []

    async def ensure_runtime_client(self):
        self.ensure_client_calls += 1
        if self.runtime_client is None:
            self.runtime_client = _FakeRuntimeClient()
        return self.runtime_client

    async def runtime_health(self):
        self.health_calls += 1
        client = await self.ensure_runtime_client()
        payload = await client.health()
        return {
            **payload,
            'runtimeVersion': '0.1.0',
        }

    async def runtime_capabilities(self):
        self.capability_calls += 1
        client = await self.ensure_runtime_client()
        return await client.capabilities()

    async def runtime_create_task(self, request):
        client = await self.ensure_runtime_client()
        self.create_task_calls.append(dict(request))
        return await client.create_task(request=request)

    async def runtime_get_task(self, runtime_task_id: str):
        client = await self.ensure_runtime_client()
        return await client.get_task(runtime_task_id)

    async def runtime_cancel_task(self, runtime_task_id: str):
        client = await self.ensure_runtime_client()
        return await client.cancel_task(runtime_task_id)


@pytest.fixture
async def service_fixture():
    from langbot.pkg.broadcast.service import BroadcastService

    persistence_mgr = _MiniPersistenceManager()
    await persistence_mgr.initialize()

    ap = SimpleNamespace(
        persistence_mgr=persistence_mgr,
        instance_config=SimpleNamespace(data={'broadcast': {}, 'desktop_automation': {'stale_run_seconds': 300}}),
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
        desktop_automation_service=SimpleNamespace(runtime_client=_FakeRuntimeClient()),
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


async def _prepare_ready_draft_for_execution(service) -> dict[str, object]:
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
                }
            ],
        },
    )
    await service.create_group_rule(
        _scope(),
        {
            'source_value': 'Acme',
            'match_type': 'exact',
            'match_expression': 'Acme',
            'target_conversation_name': 'Acme Group',
            'priority': 10,
            'enabled': True,
        },
    )
    created = await service.upload_import(
        _scope(),
        {
            'filename': 'customers.csv',
            'body': '客户名称\nAcme\n'.encode('utf-8'),
        },
    )
    template = await service.create_template(
        _scope(),
        {
            'name': 'Arrival Reminder',
            'content': 'Hello {{customer_name}}',
            'enabled': True,
        },
    )
    await service.generate_import_drafts(created['id'], _scope(), {'template_id': template['id']})
    draft = (await service.list_drafts(_scope(), {'import_batch_id': created['id']}))[0]
    await service.update_draft_statuses(_scope(), {'draft_ids': [draft['id']], 'status': 'ready'})
    return {
        'import_id': created['id'],
        'draft': await service.get_draft_detail(draft['id'], _scope()),
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
    assert error.code == BROADCAST_VARIABLE_PROFILE_INVALID
    assert error.details


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


async def test_sync_group_names_imports_only_bound_group_conversations_idempotently(service_fixture):
    service, persistence_mgr = service_fixture

    async with persistence_mgr.engine.begin() as conn:
        await conn.execute(
            sqlalchemy.insert(persistence_database_mode.DatabaseConversation).values(
                [
                    {
                        'connector_id': 'wxwork-local',
                        'source': 'wxwork',
                        'external_conversation_id': 'group-1',
                        'conversation_name': '小满',
                        'conversation_type': 'group',
                    },
                    {
                        'connector_id': 'wxwork-local',
                        'source': 'wxwork',
                        'external_conversation_id': 'direct-1',
                        'conversation_name': '杨炳恒',
                        'conversation_type': 'direct',
                    },
                    {
                        'connector_id': 'wxwork-other',
                        'source': 'wxwork',
                        'external_conversation_id': 'other-group',
                        'conversation_name': '其他群',
                        'conversation_type': 'group',
                    },
                ]
            )
        )

    first = await service.sync_group_names_from_conversations(_scope())
    assert first == {
        'scanned': 1,
        'inserted': 1,
        'updated': 0,
        'unchanged': 0,
        'skipped': 1,
        'errors': [],
    }

    listed = await service.list_group_names(_scope())
    assert len(listed) == 1
    assert listed[0]['name'] == '小满'
    assert listed[0]['external_conversation_id'] == 'group-1'

    second = await service.sync_group_names_from_conversations(_scope())
    assert second == {
        'scanned': 1,
        'inserted': 0,
        'updated': 0,
        'unchanged': 1,
        'skipped': 1,
        'errors': [],
    }


async def test_sync_group_names_updates_name_by_external_conversation_id_without_deleting_old_rows(service_fixture):
    service, persistence_mgr = service_fixture

    async with persistence_mgr.engine.begin() as conn:
        await conn.execute(
            sqlalchemy.insert(persistence_broadcast.BroadcastGroupName).values(
                {
                    'bot_uuid': 'bot-1',
                    'connector_id': 'wxwork-local',
                    'name': '旧群名',
                    'external_conversation_id': 'group-1',
                }
            )
        )
        await conn.execute(
            sqlalchemy.insert(persistence_broadcast.BroadcastGroupName).values(
                {
                    'bot_uuid': 'bot-1',
                    'connector_id': 'wxwork-local',
                    'name': '历史孤儿群',
                    'external_conversation_id': 'legacy-group',
                }
            )
        )
        await conn.execute(
            sqlalchemy.insert(persistence_database_mode.DatabaseConversation).values(
                {
                    'connector_id': 'wxwork-local',
                    'source': 'wxwork',
                    'external_conversation_id': 'group-1',
                    'conversation_name': '新群名',
                    'conversation_type': 'group',
                }
            )
        )

    result = await service.sync_group_names_from_conversations(_scope())
    assert result == {
        'scanned': 1,
        'inserted': 0,
        'updated': 1,
        'unchanged': 0,
        'skipped': 0,
        'errors': [],
    }

    listed = await service.list_group_names(_scope())
    assert [item['name'] for item in listed] == ['历史孤儿群', '新群名']
    assert {item['external_conversation_id'] for item in listed} == {'group-1', 'legacy-group'}


async def test_match_group_rule_ignores_invalid_placeholder_history_rule(service_fixture):
    service, persistence_mgr = service_fixture

    await service.save_variable_profile(
        _scope(),
        {
            'group_field': '用户名',
            'mapping_rules': [
                {
                    'source_field': '运单号',
                    'variable_key': '运单号',
                    'merge_mode': 'first',
                    'order': 1,
                }
            ],
        },
    )

    async with persistence_mgr.engine.begin() as conn:
        await conn.execute(
            sqlalchemy.insert(persistence_broadcast.BroadcastGroupRule).values(
                {
                    'bot_uuid': 'bot-1',
                    'connector_id': 'wxwork-local',
                    'source_value': '??',
                    'match_type': 'exact',
                    'match_expression': '??',
                    'target_conversation_name': '??',
                    'priority': 100,
                    'enabled': True,
                }
            )
        )
        await conn.execute(
            sqlalchemy.insert(persistence_broadcast.BroadcastGroupName).values(
                {
                    'bot_uuid': 'bot-1',
                    'connector_id': 'wxwork-local',
                    'name': '小满',
                    'external_conversation_id': 'group-1',
                }
            )
        )

    unmatched = await service.match_group_rule(_scope(), {'source_value': '??'})
    assert unmatched == {
        'matched': False,
        'rule_id': None,
        'target_conversation_name': None,
        'match_type': None,
    }

    imported = await service.upload_import(
        _scope(),
        {
            'filename': 'users.csv',
            'body': '用户名,运单号\n??,WB-001\n小满,WB-002\n'.encode('utf-8'),
        },
    )
    detail = await service.get_import_detail(imported['id'], _scope(), {})
    rows = {row['group_value']: row for row in detail['rows']}
    assert rows['??']['match_status'] == 'unmatched'
    assert rows['??']['matched_conversation_name'] is None
    assert rows['小满']['match_status'] == 'matched'
    assert rows['小满']['matched_conversation_name'] == '小满'


async def test_create_group_rule_rejects_placeholder_and_unknown_target_group(service_fixture):
    service, persistence_mgr = service_fixture

    async with persistence_mgr.engine.begin() as conn:
        await conn.execute(
            sqlalchemy.insert(persistence_broadcast.BroadcastGroupName).values(
                {
                    'bot_uuid': 'bot-1',
                    'connector_id': 'wxwork-local',
                    'name': '小满',
                    'external_conversation_id': 'group-1',
                }
            )
        )

    with pytest.raises(BroadcastError) as placeholder_error:
        await service.create_group_rule(
            _scope(),
            {
                'source_value': '??',
                'match_type': 'exact',
                'match_expression': '??',
                'target_conversation_name': '??',
                'priority': 1,
                'enabled': True,
            },
        )
    assert placeholder_error.value.code == BROADCAST_GROUP_RULE_REGEX_INVALID

    with pytest.raises(BroadcastError) as unknown_target_error:
        await service.create_group_rule(
            _scope(),
            {
                'source_value': '小满',
                'match_type': 'exact',
                'match_expression': '小满',
                'target_conversation_name': '不存在的群',
                'priority': 1,
                'enabled': True,
            },
        )
    assert unknown_target_error.value.code == BROADCAST_GROUP_RULE_REGEX_INVALID


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


async def test_upload_import_keeps_existing_batches_when_new_upload_validation_fails(service_fixture):
    service, _ = service_fixture

    await service.save_variable_profile(
        _scope(),
        {
            'group_field': '客户',
            'mapping_rules': [
                {
                    'source_field': '客户',
                    'variable_key': '客户',
                    'merge_mode': 'first',
                    'order': 1,
                },
                {
                    'source_field': '运单号',
                    'variable_key': '运单号',
                    'merge_mode': 'first',
                    'order': 2,
                },
            ],
        },
    )
    await service.create_group_rule(
        _scope(),
        {
            'source_value': '小满',
            'match_type': 'exact',
            'match_expression': '小满',
            'target_conversation_name': '小满',
            'priority': 10,
            'enabled': True,
        },
    )

    created = await service.upload_import(
        _scope(),
        {
            'filename': 'ok.csv',
            'body': '客户,运单号\n小满,TEST-20260704-001\n'.encode('utf-8'),
        },
    )
    before_batches = await service.list_import_batches(_scope())

    with pytest.raises(BroadcastError) as exc_info:
        await service.upload_import(
            _scope(),
            {
                'filename': 'bad.csv',
                'body': '客户\n小满\n'.encode('utf-8'),
            },
        )

    assert exc_info.value.code == 'BROADCAST_IMPORT_FIELDS_MISSING'
    after_batches = await service.list_import_batches(_scope())
    assert [item['id'] for item in after_batches] == [item['id'] for item in before_batches]
    detail = await service.get_import_detail(created['id'], _scope(), {})
    assert detail['rows'][0]['raw_data']['运单号'] == 'TEST-20260704-001'


async def test_generate_import_drafts_renders_chinese_variable_values(service_fixture):
    service, _ = service_fixture

    await service.save_variable_profile(
        _scope(),
        {
            'group_field': '客户',
            'mapping_rules': [
                {
                    'source_field': '客户',
                    'variable_key': '客户',
                    'merge_mode': 'first',
                    'order': 1,
                },
                {
                    'source_field': '运单号',
                    'variable_key': '运单号',
                    'merge_mode': 'first',
                    'order': 2,
                },
            ],
        },
    )
    await service.create_group_rule(
        _scope(),
        {
            'source_value': '小满',
            'match_type': 'exact',
            'match_expression': '小满',
            'target_conversation_name': '小满',
            'priority': 10,
            'enabled': True,
        },
    )
    created = await service.upload_import(
        _scope(),
        {
            'filename': 'customers.csv',
            'body': '\ufeff 客户 , 运单号 \n 小满 , TEST-20260704-001 \n'.encode('utf-8'),
        },
    )
    template = await service.create_template(
        _scope(),
        {
            'name': '查验通知',
            'content': '查验通知：\n\n涉及单号如下：\n{{运单号}}',
            'enabled': True,
        },
    )

    result = await service.generate_import_drafts(
        created['id'],
        _scope(),
        {'template_id': template['id']},
    )

    drafts = await service.list_drafts(_scope(), {'import_batch_id': created['id']})
    assert result['total_group_count'] == 1
    assert drafts[0]['draft_text'] == '查验通知：\n\n涉及单号如下：\nTEST-20260704-001'
    assert drafts[0]['render_variables']['运单号'] == 'TEST-20260704-001'


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


async def test_upload_import_creates_first_match_results_immediately(service_fixture):
    service, persistence_mgr = service_fixture

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
                    'source_field': '订单号',
                    'variable_key': 'order_no',
                    'merge_mode': 'lines',
                    'order': 2,
                },
            ],
        },
    )
    await service.create_group_rule(
        _scope(),
        {
            'source_value': 'Acme',
            'match_type': 'exact',
            'match_expression': 'Acme',
            'target_conversation_name': 'Acme Group',
            'priority': 10,
            'enabled': True,
        },
    )
    await service.create_group_rule(
        _scope(),
        {
            'source_value': 'North',
            'match_type': 'contains',
            'match_expression': 'North',
            'target_conversation_name': 'Disabled Group',
            'priority': 999,
            'enabled': False,
        },
    )
    await service.create_group_names(
        _scope(),
        {
            'names': ['Northwind Team'],
        },
    )

    result = await service.upload_import(
        _scope(),
        {
            'filename': 'customers.csv',
            'body': (
                '客户名称,订单号\n'
                'Acme,SO-001\n'
                'Northwind Team,SO-002\n'
                '   ,SO-003\n'
            ).encode('utf-8'),
        },
    )

    assert result['total_rows'] == 3
    assert result['matched_rows'] == 2
    assert result['unmatched_rows'] == 0
    assert result['invalid_rows'] == 1
    assert result['matched_rows'] + result['unmatched_rows'] + result['invalid_rows'] == result['total_rows']
    assert 'rows' not in result

    detail = await service.get_import_detail(result['id'], _scope(), {})
    assert [row['match_status'] for row in detail['rows']] == ['matched', 'matched', 'invalid']
    assert detail['rows'][0]['matched_conversation_name'] == 'Acme Group'
    assert detail['rows'][1]['matched_conversation_name'] == 'Northwind Team'
    assert detail['rows'][1]['matched_rule_id'] is None
    assert detail['rows'][2]['group_value'] is None
    assert detail['page'] == 1
    assert detail['page_size'] == 50
    assert detail['total'] == 3
    assert detail['total_pages'] == 1


async def test_get_import_detail_applies_default_pagination_and_second_page(service_fixture):
    service, _ = service_fixture

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
                }
            ],
        },
    )
    created = await service.upload_import(
        _scope(),
        {
            'filename': 'customers.csv',
            'body': (
                '客户名称\n'
                'Acme\n'
                'Northwind\n'
                'Globex\n'
            ).encode('utf-8'),
        },
    )

    first_page = await service.get_import_detail(created['id'], _scope(), {})
    assert first_page['page'] == 1
    assert first_page['page_size'] == 50
    assert first_page['total'] == 3
    assert first_page['total_pages'] == 1
    assert [row['source_row_number'] for row in first_page['rows']] == [2, 3, 4]

    second_page = await service.get_import_detail(
        created['id'],
        _scope(),
        {'page': 2, 'page_size': 2},
    )
    assert second_page['page'] == 2
    assert second_page['page_size'] == 2
    assert second_page['total'] == 3
    assert second_page['total_pages'] == 2
    assert [row['source_row_number'] for row in second_page['rows']] == [4]


async def test_get_import_detail_rejects_page_size_larger_than_200(service_fixture):
    service, _ = service_fixture

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
                }
            ],
        },
    )
    created = await service.upload_import(
        _scope(),
        {
            'filename': 'customers.csv',
            'body': '客户名称\nAcme\n'.encode('utf-8'),
        },
    )

    with pytest.raises(BroadcastError):
        await service.get_import_detail(
            created['id'],
            _scope(),
            {'page': 1, 'page_size': 201},
        )


async def test_upload_import_uses_parser_outside_transaction_and_persists_after_refresh(service_fixture):
    service, _ = service_fixture

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
                }
            ],
        },
    )

    parsed_before_transaction = []
    import langbot.pkg.broadcast.service as service_module

    original_parse = service_module.parse_import_file

    async def wrapped_parse(file_name: str, payload: bytes):
        parsed_before_transaction.append(service.ap.persistence_mgr.engine.pool is not None)
        return await original_parse(file_name, payload)
    try:
        service_module.parse_import_file = wrapped_parse
        created = await service.upload_import(
            _scope(),
            {
                'filename': 'customers.csv',
                'body': '客户名称\nAcme\n'.encode('utf-8'),
            },
        )
    finally:
        service_module.parse_import_file = original_parse

    assert parsed_before_transaction == [True]
    listed = await service.list_import_batches(_scope())
    detail = await service.get_import_detail(created['id'], _scope(), {})
    assert [item['id'] for item in listed] == [created['id']]
    assert [row['group_value'] for row in detail['rows']] == ['Acme']


async def test_rematch_uses_latest_profile_and_marks_drafts_stale_only_when_old_drafts_exist(service_fixture):
    service, _ = service_fixture

    await service.save_variable_profile(
        _scope(),
        {
            'group_field': '历史客户名称',
            'mapping_rules': [
                {
                    'source_field': '历史客户名称',
                    'variable_key': 'customer_name',
                    'merge_mode': 'first',
                    'order': 1,
                }
            ],
        },
    )
    created = await service.upload_import(
        _scope(),
        {
            'filename': 'customers.csv',
            'body': '历史客户名称,最新客户名称\nLegacy Acme,Acme\n'.encode('utf-8'),
        },
    )
    await service.create_template(
        _scope(),
        {
            'name': 'Arrival Reminder',
            'content': 'Hello {{customer_name}}',
            'enabled': True,
        },
    )

    await service.save_variable_profile(
        _scope(),
        {
            'group_field': '最新客户名称',
            'mapping_rules': [
                {
                    'source_field': '最新客户名称',
                    'variable_key': 'customer_name',
                    'merge_mode': 'first',
                    'order': 1,
                }
            ],
        },
    )
    await service.create_group_rule(
        _scope(),
        {
            'source_value': 'Acme',
            'match_type': 'exact',
            'match_expression': 'Acme',
            'target_conversation_name': 'Acme Group',
            'priority': 10,
            'enabled': True,
        },
    )

    rematched = await service.rematch_import(created['id'], _scope())
    assert rematched['drafts_stale'] is False

    template = (await service.list_templates(_scope()))[0]
    await service.generate_import_drafts(created['id'], _scope(), {'template_id': template['id']})

    second_rematch = await service.rematch_import(created['id'], _scope())
    assert second_rematch['drafts_stale'] is True
    detail = await service.get_import_detail(created['id'], _scope(), {})
    assert detail['rows'][0]['group_value'] == 'Acme'
    assert detail['rows'][0]['match_status'] == 'matched'


async def test_rematch_rejects_batch_when_latest_required_fields_are_missing(service_fixture):
    service, _ = service_fixture

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
                }
            ],
        },
    )
    created = await service.upload_import(
        _scope(),
        {
            'filename': 'customers.csv',
            'body': '客户名称\nAcme\n'.encode('utf-8'),
        },
    )

    await service.save_variable_profile(
        _scope(),
        {
            'group_field': '最新客户名称',
            'mapping_rules': [
                {
                    'source_field': '最新客户名称',
                    'variable_key': 'customer_name',
                    'merge_mode': 'first',
                    'order': 1,
                },
                {
                    'source_field': '订单号',
                    'variable_key': 'order_no',
                    'merge_mode': 'lines',
                    'order': 2,
                },
            ],
        },
    )

    from langbot.pkg.broadcast.errors import BroadcastError

    with pytest.raises(BroadcastError) as exc_info:
        await service.rematch_import(created['id'], _scope())
    assert exc_info.value.code in {'BROADCAST_IMPORT_REMATCH_FIELDS_MISSING', 'BROADCAST_IMPORT_FILE_INVALID'}


async def test_list_and_get_drafts_are_scoped_and_filterable(service_fixture):
    service, _ = service_fixture

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
                }
            ],
        },
    )
    await service.create_group_rule(
        _scope(),
        {
            'source_value': 'Acme',
            'match_type': 'exact',
            'match_expression': 'Acme',
            'target_conversation_name': 'Acme Group',
            'priority': 10,
            'enabled': True,
        },
    )
    created = await service.upload_import(
        _scope(),
        {
            'filename': 'customers.csv',
            'body': '客户名称\nAcme\nNorthwind\n'.encode('utf-8'),
        },
    )
    template = await service.create_template(
        _scope(),
        {
            'name': 'Arrival Reminder',
            'content': 'Hello {{customer_name}}',
            'enabled': True,
        },
    )
    await service.generate_import_drafts(created['id'], _scope(), {'template_id': template['id']})

    drafts = await service.list_drafts(_scope(), {'import_batch_id': created['id'], 'status': 'invalid'})
    assert [draft['group_value'] for draft in drafts] == ['Northwind']

    detail = await service.get_draft_detail(drafts[0]['id'], _scope())
    assert detail['group_value'] == 'Northwind'
    assert detail['status'] == 'invalid'


async def test_edit_ready_draft_rolls_back_to_pending_review_with_message(service_fixture):
    service, _ = service_fixture

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
                }
            ],
        },
    )
    await service.create_group_rule(
        _scope(),
        {
            'source_value': 'Acme',
            'match_type': 'exact',
            'match_expression': 'Acme',
            'target_conversation_name': 'Acme Group',
            'priority': 10,
            'enabled': True,
        },
    )
    created = await service.upload_import(
        _scope(),
        {
            'filename': 'customers.csv',
            'body': '客户名称\nAcme\n'.encode('utf-8'),
        },
    )
    template = await service.create_template(
        _scope(),
        {
            'name': 'Arrival Reminder',
            'content': 'Hello {{customer_name}}',
            'enabled': True,
        },
    )
    await service.generate_import_drafts(created['id'], _scope(), {'template_id': template['id']})
    draft = (await service.list_drafts(_scope(), {'import_batch_id': created['id']}))[0]
    await service.update_draft_statuses(_scope(), {'draft_ids': [draft['id']], 'status': 'ready'})

    updated = await service.update_draft_text(draft['id'], _scope(), {'draft_text': 'Updated draft'})
    assert updated['status'] == 'pending_review'
    assert updated['draft_text'] == 'Updated draft'
    assert updated['message'] == '草稿内容已修改，请重新确认'


async def test_edit_invalid_draft_keeps_invalid_and_cannot_be_confirmed(service_fixture):
    service, _ = service_fixture

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
                }
            ],
        },
    )
    created = await service.upload_import(
        _scope(),
        {
            'filename': 'customers.csv',
            'body': '客户名称\nNorthwind\n'.encode('utf-8'),
        },
    )
    template = await service.create_template(
        _scope(),
        {
            'name': 'Arrival Reminder',
            'content': 'Hello {{customer_name}}',
            'enabled': True,
        },
    )
    await service.generate_import_drafts(created['id'], _scope(), {'template_id': template['id']})
    draft = (await service.list_drafts(_scope(), {'import_batch_id': created['id']}))[0]

    updated = await service.update_draft_text(draft['id'], _scope(), {'draft_text': 'Manual preview'})
    assert updated['status'] == 'invalid'

    with pytest.raises(BroadcastError, match='BROADCAST_DRAFT_INVALID_CONFIRM_FORBIDDEN') as exc_info:
        await service.update_draft_statuses(_scope(), {'draft_ids': [draft['id']], 'status': 'ready'})
    assert exc_info.value.code == 'BROADCAST_DRAFT_INVALID_CONFIRM_FORBIDDEN'


async def test_stale_draft_cannot_be_confirmed_and_cross_scope_ids_reject_whole_batch(service_fixture):
    service, _ = service_fixture

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
                }
            ],
        },
    )
    await service.create_group_rule(
        _scope(),
        {
            'source_value': 'Acme',
            'match_type': 'exact',
            'match_expression': 'Acme',
            'target_conversation_name': 'Acme Group',
            'priority': 10,
            'enabled': True,
        },
    )
    created = await service.upload_import(
        _scope(),
        {
            'filename': 'customers.csv',
            'body': '客户名称,新客户名称\nAcme,Acme\n'.encode('utf-8'),
        },
    )
    template = await service.create_template(
        _scope(),
        {
            'name': 'Arrival Reminder',
            'content': 'Hello {{customer_name}}',
            'enabled': True,
        },
    )
    await service.generate_import_drafts(created['id'], _scope(), {'template_id': template['id']})
    draft = (await service.list_drafts(_scope(), {'import_batch_id': created['id']}))[0]

    await service.save_variable_profile(
        _scope(),
        {
            'group_field': '新客户名称',
            'mapping_rules': [
                {
                    'source_field': '新客户名称',
                    'variable_key': 'customer_name',
                    'merge_mode': 'first',
                    'order': 1,
                }
            ],
        },
    )
    await service.rematch_import(created['id'], _scope())

    with pytest.raises(BroadcastError, match='BROADCAST_DRAFT_STALE_CONFIRM_FORBIDDEN') as exc_info:
        await service.update_draft_statuses(_scope(), {'draft_ids': [draft['id']], 'status': 'ready'})
    assert exc_info.value.code == 'BROADCAST_DRAFT_STALE_CONFIRM_FORBIDDEN'


async def test_create_execution_batch_phase4_persists_single_ready_task_with_digest(service_fixture):
    service, _ = service_fixture

    prepared = await _prepare_ready_draft_for_execution(service)
    draft = prepared['draft']

    batch = await service.create_execution_batch(
        _scope(),
        {
            'draft_ids': [draft['id']],
            'mode': 'paste_only',
            'operator': 'tester@example.com',
        },
    )

    expected_digest = hashlib.sha256(
        ('paste_draft' + '\0' + 'wxwork_database' + '\0' + 'Acme Group' + '\0' + 'Hello Acme').encode('utf-8')
    ).hexdigest()

    assert batch['mode'] == 'paste_only'
    assert batch['status'] == 'created'
    assert batch['total_tasks'] == 1
    assert batch['pending_tasks'] == 1
    assert len(batch['tasks']) == 1
    assert batch['tasks'][0]['draft_id'] == draft['id']
    assert batch['tasks'][0]['target_conversation_snapshot'] == 'Acme Group'
    assert batch['tasks'][0]['action'] == 'paste_draft'
    assert batch['tasks'][0]['status'] == 'pending'
    assert batch['tasks'][0]['request_digest'] == expected_digest
    assert batch['tasks'][0]['idempotency_key'] == f"broadcast:{batch['tasks'][0]['id']}:1"


async def test_create_execution_batch_rejects_non_ready_and_cross_scope_drafts(service_fixture):
    service, _ = service_fixture

    prepared = await _prepare_ready_draft_for_execution(service)
    ready_draft = prepared['draft']

    await service.update_draft_text(ready_draft['id'], _scope(), {'draft_text': 'Edited after ready'})
    pending_review_draft = await service.get_draft_detail(ready_draft['id'], _scope())

    with pytest.raises(BroadcastError, match='BROADCAST_EXECUTION_DRAFT_NOT_READY'):
        await service.create_execution_batch(
            _scope(),
            {
                'draft_ids': [pending_review_draft['id']],
                'mode': 'paste_only',
                'operator': 'tester@example.com',
            },
        )

    with pytest.raises(BroadcastError, match='BROADCAST_EXECUTION_SCOPE_MISMATCH'):
        await service.create_execution_batch(
            _scope(bot_uuid='bot-2', connector_id='wxwork-other'),
            {
                'draft_ids': [pending_review_draft['id']],
                'mode': 'paste_only',
                'operator': 'tester@example.com',
            },
        )


async def test_start_execution_task_creates_attempt_and_evidence_and_updates_batch(service_fixture, monkeypatch):
    service, _ = service_fixture
    monkeypatch.setenv('LANGBOT_RPA_FORCE_DISABLE_SEND', '1')

    prepared = await _prepare_ready_draft_for_execution(service)
    draft = prepared['draft']
    batch = await service.create_execution_batch(
        _scope(),
        {
            'draft_ids': [draft['id']],
            'mode': 'paste_only',
            'operator': 'tester@example.com',
        },
    )
    task_id = batch['tasks'][0]['id']

    started = await service.start_execution_task(
        task_id,
        _scope(),
        {
            'operator': 'tester@example.com',
        },
    )

    assert started['status'] == 'succeeded'
    assert started['attempt_count'] == 1
    assert started['runtime_task_id'] == 'runtime-1'

    attempts = await service.list_execution_attempts(task_id, _scope())
    assert len(attempts) == 1
    assert attempts[0]['attempt_no'] == 1
    assert attempts[0]['status'] == 'succeeded'
    assert attempts[0]['runtime_task_id'] == 'runtime-1'

    evidence = await service.get_execution_evidence(attempts[0]['id'], _scope())
    assert evidence['action'] == 'paste_draft'
    assert evidence['draft_written'] is True
    assert evidence['technical_details']
    assert evidence['send_triggered'] is False
    assert evidence['clipboard_restored'] is True

    refreshed_batch = await service.get_execution_batch_detail(batch['id'], _scope())
    assert refreshed_batch['status'] == 'completed'
    assert refreshed_batch['pending_tasks'] == 0
    assert refreshed_batch['succeeded_tasks'] == 1


async def test_retry_execution_task_resets_failed_task_and_uses_new_attempt_number(service_fixture, monkeypatch):
    service, _ = service_fixture
    monkeypatch.setenv('LANGBOT_RPA_FORCE_DISABLE_SEND', '1')

    prepared = await _prepare_ready_draft_for_execution(service)
    draft = prepared['draft']
    batch = await service.create_execution_batch(
        _scope(),
        {
            'draft_ids': [draft['id']],
            'mode': 'paste_only',
            'operator': 'tester@example.com',
        },
    )
    task_id = batch['tasks'][0]['id']

    await service.start_execution_task(task_id, _scope(), {'operator': 'tester@example.com'})

    async with service.ap.persistence_mgr.get_db_engine().begin() as conn:
        await service.repository.update_execution_task(
            task_id,
            bot_uuid='bot-1',
            connector_id='wxwork-local',
            updates={
                'status': 'failed',
                'error_code': 'RUNTIME_TIMEOUT',
                'error_message': 'timeout',
            },
            conn=conn,
        )

    retried = await service.retry_execution_task(
        task_id,
        _scope(),
        {
            'operator': 'tester@example.com',
        },
    )
    assert retried['status'] == 'pending'
    assert retried['idempotency_key'] == f'broadcast:{task_id}:2'

    await service.start_execution_task(task_id, _scope(), {'operator': 'tester@example.com'})
    attempts = await service.list_execution_attempts(task_id, _scope())
    assert [attempt['attempt_no'] for attempt in attempts] == [1, 2]


async def test_start_execution_task_rejects_when_safety_lock_is_disabled(service_fixture, monkeypatch):
    service, _ = service_fixture
    monkeypatch.delenv('LANGBOT_RPA_FORCE_DISABLE_SEND', raising=False)

    prepared = await _prepare_ready_draft_for_execution(service)
    draft = prepared['draft']
    batch = await service.create_execution_batch(
        _scope(),
        {
            'draft_ids': [draft['id']],
            'mode': 'paste_only',
            'operator': 'tester@example.com',
        },
    )

    with pytest.raises(BroadcastError, match='BROADCAST_EXECUTION_SAFETY_LOCK_REQUIRED'):
        await service.start_execution_task(
            batch['tasks'][0]['id'],
            _scope(),
            {'operator': 'tester@example.com'},
        )


async def test_cancel_execution_task_recomputes_batch_summary(service_fixture):
    service, _ = service_fixture

    prepared = await _prepare_ready_draft_for_execution(service)
    draft = prepared['draft']
    batch = await service.create_execution_batch(
        _scope(),
        {
            'draft_ids': [draft['id']],
            'mode': 'paste_only',
            'operator': 'tester@example.com',
        },
    )

    cancelled = await service.cancel_execution_task(
        batch['tasks'][0]['id'],
        _scope(),
        {'operator': 'tester@example.com'},
    )
    assert cancelled['status'] == 'cancelled'

    refreshed_batch = await service.get_execution_batch_detail(batch['id'], _scope())
    assert refreshed_batch['status'] == 'cancelled'
    assert refreshed_batch['pending_tasks'] == 0
    assert refreshed_batch['cancelled_tasks'] == 1


async def test_start_execution_task_rejects_replay_after_success_without_new_attempt(
    service_fixture,
    monkeypatch,
):
    service, _ = service_fixture
    monkeypatch.setenv('LANGBOT_RPA_FORCE_DISABLE_SEND', '1')

    prepared = await _prepare_ready_draft_for_execution(service)
    draft = prepared['draft']
    batch = await service.create_execution_batch(
        _scope(),
        {
            'draft_ids': [draft['id']],
            'mode': 'paste_only',
            'operator': 'tester@example.com',
        },
    )
    task_id = batch['tasks'][0]['id']

    runtime_client = service.ap.desktop_automation_service.runtime_client

    started = await service.start_execution_task(task_id, _scope(), {'operator': 'tester@example.com'})
    assert started['status'] == 'succeeded'
    assert len(runtime_client.requests) == 1

    with pytest.raises(BroadcastError, match='BROADCAST_EXECUTION_TASK_STATUS_INVALID'):
        await service.start_execution_task(task_id, _scope(), {'operator': 'tester@example.com'})

    attempts = await service.list_execution_attempts(task_id, _scope())
    assert len(attempts) == 1
    assert len(runtime_client.requests) == 1


async def test_start_execution_task_timeout_marks_interrupted_without_blind_retry(
    service_fixture,
    monkeypatch,
):
    service, _ = service_fixture
    monkeypatch.setenv('LANGBOT_RPA_FORCE_DISABLE_SEND', '1')

    prepared = await _prepare_ready_draft_for_execution(service)
    draft = prepared['draft']
    batch = await service.create_execution_batch(
        _scope(),
        {
            'draft_ids': [draft['id']],
            'mode': 'paste_only',
            'operator': 'tester@example.com',
        },
    )
    task_id = batch['tasks'][0]['id']

    runtime_client = service.ap.desktop_automation_service.runtime_client

    async def timeout_create_task(*, request):
        runtime_client.requests.append(request)
        raise TimeoutError('runtime timeout')

    runtime_client.create_task = timeout_create_task

    started = await service.start_execution_task(task_id, _scope(), {'operator': 'tester@example.com'})
    assert started['status'] == 'interrupted'
    assert started['attempt_count'] == 1

    attempts = await service.list_execution_attempts(task_id, _scope())
    assert len(attempts) == 1
    assert attempts[0]['attempt_no'] == 1
    assert attempts[0]['status'] == 'interrupted'
    assert len(runtime_client.requests) == 1

    refreshed_batch = await service.get_execution_batch_detail(batch['id'], _scope())
    assert refreshed_batch['status'] == 'interrupted'
    assert refreshed_batch['interrupted_tasks'] == 1


async def test_start_execution_task_treats_send_triggered_as_security_failure(
    service_fixture,
    monkeypatch,
):
    service, _ = service_fixture
    monkeypatch.setenv('LANGBOT_RPA_FORCE_DISABLE_SEND', '1')

    prepared = await _prepare_ready_draft_for_execution(service)
    draft = prepared['draft']
    batch = await service.create_execution_batch(
        _scope(),
        {
            'draft_ids': [draft['id']],
            'mode': 'paste_only',
            'operator': 'tester@example.com',
        },
    )
    task_id = batch['tasks'][0]['id']

    runtime_client = service.ap.desktop_automation_service.runtime_client

    async def create_task_with_send_trigger(*, request):
        runtime_client.requests.append(request)
        return {
            'id': 'runtime-danger',
            'status': 'succeeded',
            'stage': 'sent',
            'result': {
                'messageSent': True,
                'clipboardRestoreFailed': False,
            },
        }

    runtime_client.create_task = create_task_with_send_trigger

    started = await service.start_execution_task(task_id, _scope(), {'operator': 'tester@example.com'})
    assert started['status'] == 'failed'
    assert started['error_code'] == 'BROADCAST_EXECUTION_SEND_TRIGGERED'

    attempts = await service.list_execution_attempts(task_id, _scope())
    evidence = await service.get_execution_evidence(attempts[0]['id'], _scope())
    assert evidence['send_triggered'] is True


async def test_start_execution_task_does_not_mark_succeeded_when_content_verification_fails(
    service_fixture,
    monkeypatch,
):
    service, _ = service_fixture
    monkeypatch.setenv('LANGBOT_RPA_FORCE_DISABLE_SEND', '1')

    prepared = await _prepare_ready_draft_for_execution(service)
    draft = prepared['draft']
    batch = await service.create_execution_batch(
        _scope(),
        {
            'draft_ids': [draft['id']],
            'mode': 'paste_only',
            'operator': 'tester@example.com',
        },
    )
    task_id = batch['tasks'][0]['id']
    runtime_client = service.ap.desktop_automation_service.runtime_client

    async def create_unverified_task(*, request):
        runtime_client.requests.append(request)
        return {
            'id': 'runtime-unverified',
            'status': 'succeeded',
            'stage': 'pasted_to_input',
            'result': {
                'messageSent': False,
                'clipboardRestoreFailed': False,
                'contentVerified': False,
                'verificationFailed': True,
                'draftWritten': False,
                'inputLocated': True,
            },
        }

    runtime_client.create_task = create_unverified_task

    started = await service.start_execution_task(task_id, _scope(), {'operator': 'tester@example.com'})

    assert started['status'] == 'interrupted'
    assert started['error_code'] == 'PASTE_VERIFICATION_FAILED'

    attempts = await service.list_execution_attempts(task_id, _scope())
    evidence = await service.get_execution_evidence(attempts[0]['id'], _scope())
    assert evidence['draft_written'] is False
    technical_details = json.loads(evidence['technical_details'])
    assert technical_details['content_verified'] is False


async def test_start_execution_task_persists_mismatch_diagnostics_and_error_code(
    service_fixture,
    monkeypatch,
):
    service, _ = service_fixture
    monkeypatch.setenv('LANGBOT_RPA_FORCE_DISABLE_SEND', '1')

    prepared = await _prepare_ready_draft_for_execution(service)
    draft = prepared['draft']
    batch = await service.create_execution_batch(
        _scope(),
        {
            'draft_ids': [draft['id']],
            'mode': 'paste_only',
            'operator': 'tester@example.com',
        },
    )
    task_id = batch['tasks'][0]['id']
    runtime_client = service.ap.desktop_automation_service.runtime_client

    async def create_mismatch_task(*, request):
        runtime_client.requests.append(request)
        return {
            'id': 'runtime-mismatch',
            'status': 'interrupted',
            'stage': 'paste_content_mismatch',
            'errorCode': 'PASTE_CONTENT_MISMATCH',
            'result': {
                'messageSent': False,
                'clipboardRestoreFailed': False,
                'contentVerified': False,
                'verificationFailed': True,
                'draftWritten': True,
                'inputLocated': True,
                'clipboardRoundtripVerified': True,
                'verificationMethod': 'uia_value_pattern',
                'verificationErrorCode': 'PASTE_CONTENT_MISMATCH',
                'expectedTextLength': 12,
                'actualTextLength': 11,
                'expectedDigest': 'digest-expected',
                'actualDigest': 'digest-actual',
                'expectedLineCount': 4,
                'actualLineCount': 3,
            },
        }

    runtime_client.create_task = create_mismatch_task

    started = await service.start_execution_task(task_id, _scope(), {'operator': 'tester@example.com'})

    assert started['status'] == 'interrupted'
    assert started['error_code'] == 'PASTE_CONTENT_MISMATCH'

    attempts = await service.list_execution_attempts(task_id, _scope())
    evidence = await service.get_execution_evidence(attempts[0]['id'], _scope())
    assert evidence['draft_written'] is True
    assert evidence['input_located'] is True
    technical_details = json.loads(evidence['technical_details'])
    assert technical_details['verification_method'] == 'uia_value_pattern'
    assert technical_details['verification_error_code'] == 'PASTE_CONTENT_MISMATCH'
    assert technical_details['clipboard_roundtrip_verified'] is True
    assert technical_details['expected_text_length'] == 12
    assert technical_details['actual_text_length'] == 11


async def test_concurrent_start_execution_task_creates_one_attempt_and_one_runtime_call(
    service_fixture,
    monkeypatch,
):
    service, _ = service_fixture
    monkeypatch.setenv('LANGBOT_RPA_FORCE_DISABLE_SEND', '1')

    prepared = await _prepare_ready_draft_for_execution(service)
    draft = prepared['draft']
    batch = await service.create_execution_batch(
        _scope(),
        {
            'draft_ids': [draft['id']],
            'mode': 'paste_only',
            'operator': 'tester@example.com',
        },
    )
    task_id = batch['tasks'][0]['id']

    runtime_client = service.ap.desktop_automation_service.runtime_client
    first_call_started = asyncio.Event()

    async def slow_create_task(*, request):
        runtime_client.requests.append(request)
        first_call_started.set()
        await asyncio.sleep(0.05)
        return {
            'id': 'runtime-1',
            'status': 'succeeded',
            'stage': 'pasted_to_input',
            'result': {
                'messageSent': False,
                'clipboardRestoreFailed': False,
                'contentVerified': True,
                'draftWritten': True,
                'inputLocated': True,
            },
        }

    runtime_client.create_task = slow_create_task

    async def start_once():
        try:
            return await service.start_execution_task(task_id, _scope(), {'operator': 'tester@example.com'})
        except Exception as exc:  # pragma: no cover - asserted below
            return exc

    first = asyncio.create_task(start_once())
    await first_call_started.wait()
    second = asyncio.create_task(start_once())
    results = await asyncio.gather(first, second)

    assert sum(isinstance(item, dict) and item['status'] == 'succeeded' for item in results) == 1
    assert sum(isinstance(item, BroadcastError) for item in results) == 1
    assert len(runtime_client.requests) == 1

    attempts = await service.list_execution_attempts(task_id, _scope())
    assert len(attempts) == 1


async def test_reconcile_running_tasks_marks_tasks_and_batches_interrupted(service_fixture):
    service, _ = service_fixture

    prepared = await _prepare_ready_draft_for_execution(service)
    draft = prepared['draft']
    batch = await service.create_execution_batch(
        _scope(),
        {
            'draft_ids': [draft['id']],
            'mode': 'paste_only',
            'operator': 'tester@example.com',
        },
    )
    task_id = batch['tasks'][0]['id']

    async with service.ap.persistence_mgr.get_db_engine().begin() as conn:
        await service.repository.update_execution_task(
            task_id,
            bot_uuid='bot-1',
            connector_id='wxwork-local',
            updates={'status': 'running'},
            conn=conn,
        )
        await service.repository.recompute_execution_batch_counts(
            batch['id'],
            bot_uuid='bot-1',
            connector_id='wxwork-local',
            conn=conn,
        )

    updated_count = await service.reconcile_running_executions()
    assert updated_count == 1

    refreshed_task = await service.get_execution_task_detail(task_id, _scope())
    assert refreshed_task['status'] == 'interrupted'

    refreshed_batch = await service.get_execution_batch_detail(batch['id'], _scope())
    assert refreshed_batch['status'] == 'interrupted'
    assert refreshed_batch['running_tasks'] == 0
    assert refreshed_batch['interrupted_tasks'] == 1


async def test_start_execution_task_marks_interrupted_when_result_persistence_fails(
    service_fixture,
    monkeypatch,
):
    service, _ = service_fixture
    monkeypatch.setenv('LANGBOT_RPA_FORCE_DISABLE_SEND', '1')

    prepared = await _prepare_ready_draft_for_execution(service)
    draft = prepared['draft']
    batch = await service.create_execution_batch(
        _scope(),
        {
            'draft_ids': [draft['id']],
            'mode': 'paste_only',
            'operator': 'tester@example.com',
        },
    )
    task_id = batch['tasks'][0]['id']
    runtime_client = service.ap.desktop_automation_service.runtime_client

    original_create_execution_evidence = service.repository.create_execution_evidence
    failure_injected = False

    async def failing_create_execution_evidence(conn, payload):
        nonlocal failure_injected
        if not failure_injected:
            failure_injected = True
            raise RuntimeError('persist-evidence-failed')
        return await original_create_execution_evidence(conn, payload)

    monkeypatch.setattr(
        service.repository,
        'create_execution_evidence',
        failing_create_execution_evidence,
    )

    started = await service.start_execution_task(task_id, _scope(), {'operator': 'tester@example.com'})

    assert started['status'] == 'interrupted'
    assert started['attempt_count'] == 1
    assert started['runtime_task_id'] == 'runtime-1'
    assert started['error_code'] == 'BROADCAST_EXECUTION_RESULT_PERSISTENCE_FAILED'
    assert len(runtime_client.requests) == 1

    attempts = await service.list_execution_attempts(task_id, _scope())
    assert len(attempts) == 1
    assert attempts[0]['status'] == 'interrupted'
    assert attempts[0]['runtime_task_id'] == 'runtime-1'
    assert attempts[0]['error_code'] == 'BROADCAST_EXECUTION_RESULT_PERSISTENCE_FAILED'

    with pytest.raises(BroadcastError, match='BROADCAST_EXECUTION_TASK_NOT_FOUND'):
        await service.get_execution_evidence(attempts[0]['id'], _scope())

    refreshed_batch = await service.get_execution_batch_detail(batch['id'], _scope())
    assert refreshed_batch['status'] == 'interrupted'
    assert refreshed_batch['interrupted_tasks'] == 1


async def test_start_execution_task_redacts_sensitive_response_summary_and_evidence_details(
    service_fixture,
    monkeypatch,
):
    service, _ = service_fixture
    monkeypatch.setenv('LANGBOT_RPA_FORCE_DISABLE_SEND', '1')

    prepared = await _prepare_ready_draft_for_execution(service)
    draft = prepared['draft']
    batch = await service.create_execution_batch(
        _scope(),
        {
            'draft_ids': [draft['id']],
            'mode': 'paste_only',
            'operator': 'tester@example.com',
        },
    )
    task_id = batch['tasks'][0]['id']
    runtime_client = service.ap.desktop_automation_service.runtime_client

    async def create_sensitive_task(*, request):
        runtime_client.requests.append(request)
        return {
            'id': 'runtime-secret',
            'status': 'succeeded',
            'stage': 'pasted_to_input',
            'result': {
                'messageSent': False,
                'clipboardRestoreFailed': False,
                'contentVerified': True,
                'draftWritten': True,
                'inputLocated': True,
            },
            'technical_details': {
                'Authorization': 'Bearer secret-token',
                'token': 'top-secret-token',
                'Cookie': 'sid=session-cookie',
                'path': 'C:\\Users\\33031\\Desktop\\bot\\secrets.txt',
                'draftText': 'Hello Acme',
            },
        }

    class _SensitiveExecutor:
        def validate_capability(self, action: str):
            return {'supports_paste': True}

        async def paste_draft(
            self,
            *,
            conversation_name: str,
            draft_text: str,
            idempotency_key: str,
            request_digest: str,
        ) -> dict[str, object]:
            return await create_sensitive_task(
                request={
                    'conversationName': conversation_name,
                    'draftText': draft_text,
                    'idempotencyKey': idempotency_key,
                    'requestDigest': request_digest,
                }
            )

        def normalize_evidence(self, result: dict[str, object]) -> dict[str, object]:
            return {
                'action': 'paste_draft',
                'input_located': True,
                'draft_written': True,
                'content_verified': True,
                'verification_failed': False,
                'send_triggered': False,
                'clipboard_restored': True,
                'runtime_state': 'pasted_to_input',
                'evidence_summary': 'pasted_to_input',
                'technical_details': dict(result.get('technical_details') or {}),
                'window_title': 'WeCom',
                'target_conversation': 'Acme Group',
            }

    import langbot.pkg.broadcast.service as broadcast_service_module

    monkeypatch.setattr(
        broadcast_service_module,
        'build_executor',
        lambda channel, gateway: _SensitiveExecutor(),
    )

    started = await service.start_execution_task(task_id, _scope(), {'operator': 'tester@example.com'})
    assert started['status'] == 'succeeded'

    attempts = await service.list_execution_attempts(task_id, _scope())
    attempt_detail = await service.get_execution_attempt_detail(attempts[0]['id'], _scope())
    evidence = await service.get_execution_evidence(attempts[0]['id'], _scope())

    response_summary = attempt_detail['response_summary'] or ''
    technical_details = evidence['technical_details'] or ''

    for secret in (
        'Bearer secret-token',
        'top-secret-token',
        'session-cookie',
        'C:\\Users\\33031\\Desktop\\bot\\secrets.txt',
        'Hello Acme',
    ):
        assert secret not in response_summary
        assert secret not in technical_details

    assert 'runtime-secret' in response_summary
    assert 'pasted_to_input' in response_summary


async def test_start_execution_task_rejects_duplicate_runtime_task_id_across_batches(
    service_fixture,
    monkeypatch,
):
    service, _ = service_fixture
    monkeypatch.setenv('LANGBOT_RPA_FORCE_DISABLE_SEND', '1')

    prepared = await _prepare_ready_draft_for_execution(service)
    draft = prepared['draft']
    runtime_client = service.ap.desktop_automation_service.runtime_client

    async def duplicate_runtime_task(*, request):
        runtime_client.requests.append(request)
        return {
            'id': 'runtime-duplicate',
            'status': 'succeeded',
            'stage': 'pasted_to_input',
            'result': {
                'messageSent': False,
                'clipboardRestoreFailed': False,
                'contentVerified': True,
                'draftWritten': True,
                'inputLocated': True,
            },
        }

    runtime_client.create_task = duplicate_runtime_task

    first_batch = await service.create_execution_batch(
        _scope(),
        {
            'draft_ids': [draft['id']],
            'mode': 'paste_only',
            'operator': 'tester@example.com',
        },
    )
    first_task_id = first_batch['tasks'][0]['id']
    first_started = await service.start_execution_task(first_task_id, _scope(), {'operator': 'tester@example.com'})
    assert first_started['status'] == 'succeeded'

    second_batch = await service.create_execution_batch(
        _scope(),
        {
            'draft_ids': [draft['id']],
            'mode': 'paste_only',
            'operator': 'tester@example.com',
        },
    )
    second_task_id = second_batch['tasks'][0]['id']
    second_started = await service.start_execution_task(second_task_id, _scope(), {'operator': 'tester@example.com'})

    assert second_started['status'] == 'failed'
    assert second_started['error_code'] == 'BROADCAST_EXECUTION_RUNTIME_TASK_ID_CONFLICT'
    assert len(runtime_client.requests) == 2

    second_attempts = await service.list_execution_attempts(second_task_id, _scope())
    assert len(second_attempts) == 1
    assert second_attempts[0]['status'] == 'failed'
    assert second_attempts[0]['error_code'] == 'BROADCAST_EXECUTION_RUNTIME_TASK_ID_CONFLICT'


async def test_get_executor_health_uses_public_runtime_interface_when_runtime_client_is_none(service_fixture):
    service, _ = service_fixture
    deferred_runtime = _DeferredRuntimeDesktopAutomationService()
    service.ap.desktop_automation_service = deferred_runtime

    health = await service.get_executor_health(_scope())

    assert health['status'] == 'ready'
    assert health['protocol_version'] == '1'
    assert health['runtime_version'] == '0.1.0'
    assert health['runtime_status']['supportsPaste'] is True
    assert deferred_runtime.ensure_client_calls >= 2
    assert deferred_runtime.health_calls == 1
    assert deferred_runtime.capability_calls == 1


async def test_start_execution_task_uses_public_runtime_interface_when_runtime_client_is_none(
    service_fixture,
    monkeypatch,
):
    service, _ = service_fixture
    monkeypatch.setenv('LANGBOT_RPA_FORCE_DISABLE_SEND', '1')
    deferred_runtime = _DeferredRuntimeDesktopAutomationService()
    service.ap.desktop_automation_service = deferred_runtime

    prepared = await _prepare_ready_draft_for_execution(service)
    draft = prepared['draft']
    batch = await service.create_execution_batch(
        _scope(),
        {
            'draft_ids': [draft['id']],
            'mode': 'paste_only',
            'operator': 'tester@example.com',
        },
    )
    task_id = batch['tasks'][0]['id']

    started = await service.start_execution_task(task_id, _scope(), {'operator': 'tester@example.com'})

    assert started['status'] == 'succeeded'
    assert len(deferred_runtime.create_task_calls) == 1
    assert deferred_runtime.create_task_calls[0]['action'] == 'paste_draft'
