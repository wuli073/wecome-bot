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
    BATCH_VALIDATION_FAILED,
    BROADCAST_GROUP_NAME_NOT_FOUND,
    BROADCAST_IMPORT_GROUP_FIELD_CONFIRMATION_REQUIRED,
    BROADCAST_IMPORT_GROUP_FIELD_OVERRIDE_INVALID,
    BROADCAST_IMPORT_GROUP_FIELD_UNRESOLVABLE,
    BROADCAST_IMPORT_GROUP_NOT_FOUND,
    BROADCAST_IMPORT_GROUP_RULE_BULK_ASSIGN_FAILED,
    BROADCAST_IMPORT_READY_DRAFT_EXISTS,
    BROADCAST_GROUP_RULE_DUPLICATE,
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
            await conn.run_sync(persistence_broadcast.BroadcastImportGroupTemplateAssignment.__table__.create)
            await conn.run_sync(persistence_broadcast.BroadcastDraft.__table__.create)
            await conn.run_sync(persistence_broadcast.BroadcastAttachmentAsset.__table__.create)
            await conn.run_sync(persistence_broadcast.BroadcastImportGroupAttachment.__table__.create)
            await conn.run_sync(persistence_broadcast.BroadcastDraftAttachment.__table__.create)
            await conn.run_sync(persistence_broadcast.BroadcastExecutionBatch.__table__.create)
            await conn.run_sync(persistence_broadcast.BroadcastExecutionTask.__table__.create)
            await conn.run_sync(persistence_broadcast.BroadcastExecutionTaskAttachment.__table__.create)
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
        return {
            'windowingAvailable': True,
            'captureAvailable': True,
            'inputAvailable': True,
            'providerHubReady': True,
            'activeTaskCount': 0,
            'lastErrorCode': None,
            'pasteVerification': {
                'available': True,
                'reason': None,
                'method': 'windows_uia',
                'requiresManualConversationOpen': True,
                'supportedErrorCodes': [
                    'TARGET_WINDOW_CHANGED',
                    'CONVERSATION_MISMATCH',
                    'INPUT_NOT_LOCATED',
                    'PASTE_CONTENT_MISMATCH',
                    'PASTE_VERIFICATION_UNAVAILABLE',
                ],
            },
            'supportsPaste': True,
            'supportsSend': False,
        }

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


def test_normalize_group_customer_name_preserves_falsey_non_none_values():
    from langbot.pkg.broadcast.service import normalize_group_customer_name

    assert normalize_group_customer_name(None) == ''
    assert normalize_group_customer_name(0) == '0'
    assert normalize_group_customer_name(False) == 'False'


async def _all_import_group_keys(service, import_id: int) -> list[str]:
    groups = await service.list_import_groups(import_id, _scope(), {})
    return [item['group_key'] for item in groups['groups']]


async def _prepare_group_rule_candidate_batch(service) -> dict[str, object]:
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
    configured_rule = await service.create_group_rule(
        _scope(),
        {
            'source_value': 'Configured Co',
            'match_type': 'exact',
            'match_expression': 'Configured Co',
            'target_conversation_id': 'configured-group',
            'target_conversation_name': 'Configured Group',
            'priority': 0,
            'enabled': True,
        },
    )
    repair_rule = await service.create_group_rule(
        _scope(),
        {
            'source_value': 'Repair Co',
            'match_type': 'exact',
            'match_expression': 'Repair Co',
            'target_conversation_id': 'repair-group',
            'target_conversation_name': 'Repair Group',
            'priority': 0,
            'enabled': False,
        },
    )
    contains_rule = await service.create_group_rule(
        _scope(),
        {
            'source_value': 'Ac',
            'match_type': 'contains',
            'match_expression': 'Ac',
            'target_conversation_id': 'contains-group',
            'target_conversation_name': 'Contains Group',
            'priority': 10,
            'enabled': True,
        },
    )
    created = await service.upload_import(
        _scope(),
        {
            'filename': 'customers.csv',
            'body': '客户名称\nFresh Co\nConfigured Co\nRepair Co\nAcme\n'.encode('utf-8'),
        },
    )
    async with service.ap.persistence_mgr.get_db_engine().begin() as conn:
        await service.ap.persistence_mgr.execute_async(
            sqlalchemy.insert(persistence_broadcast.BroadcastImportRow).values(
                {
                    'import_batch_id': created['id'],
                    'source_row_number': 6,
                    'raw_data': {'客户名称': '   '},
                    'group_value': None,
                    'matched_conversation_id': None,
                    'matched_conversation_name': None,
                    'matched_rule_id': None,
                    'match_status': 'invalid',
                    'error_message': None,
                }
            ),
            conn=conn,
        )
        await service.ap.persistence_mgr.execute_async(
            sqlalchemy.update(persistence_broadcast.BroadcastImportBatch)
            .where(persistence_broadcast.BroadcastImportBatch.id == created['id'])
            .values(
                {
                    'total_rows': 5,
                    'valid_rows': 4,
                    'invalid_rows': 1,
                    'matched_rows': 3,
                    'unmatched_rows': 1,
                }
            ),
            conn=conn,
        )
    return {
        'import_id': created['id'],
        'configured_rule': configured_rule,
        'repair_rule': repair_rule,
        'contains_rule': contains_rule,
    }


async def _prepare_group_rule_candidate_status_batch(service) -> dict[str, object]:
    async with service.ap.persistence_mgr.get_db_engine().begin() as conn:
        await service.ap.persistence_mgr.execute_async(
            sqlalchemy.insert(persistence_database_mode.DatabaseConversation).values(
                [
                    {
                        'connector_id': 'wxwork-local',
                        'source': 'wxwork',
                        'external_conversation_id': 'configured-group',
                        'conversation_name': 'Configured Group',
                        'conversation_type': 'group',
                    },
                    {
                        'connector_id': 'wxwork-local',
                        'source': 'wxwork',
                        'external_conversation_id': 'repair-valid-group',
                        'conversation_name': 'Repair Valid Group',
                        'conversation_type': 'group',
                    },
                    {
                        'connector_id': 'wxwork-local',
                        'source': 'wxwork',
                        'external_conversation_id': 'contains-group',
                        'conversation_name': 'Contains Group',
                        'conversation_type': 'group',
                    },
                ]
            ),
            conn=conn,
        )
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
    configured_rule = await service.create_group_rule(
        _scope(),
        {
            'source_value': 'Configured Co',
            'match_type': 'exact',
            'match_expression': 'Configured Co',
            'target_conversation_id': 'configured-group',
            'target_conversation_name': 'Configured Group',
            'priority': 0,
            'enabled': True,
        },
    )
    repair_rule = await service.create_group_rule(
        _scope(),
        {
            'source_value': 'Repair Co',
            'match_type': 'exact',
            'match_expression': 'Repair Co',
            'target_conversation_id': 'repair-valid-group',
            'target_conversation_name': 'Repair Valid Group',
            'priority': 0,
            'enabled': True,
        },
    )
    repair_disabled_rule = await service.create_group_rule(
        _scope(),
        {
            'source_value': 'Repair Co',
            'match_type': 'exact',
            'match_expression': 'Repair Co Backup',
            'target_conversation_id': 'repair-missing-group',
            'target_conversation_name': 'Repair Missing Group',
            'priority': -1,
            'enabled': False,
        },
    )
    contains_rule = await service.create_group_rule(
        _scope(),
        {
            'source_value': 'Ac',
            'match_type': 'contains',
            'match_expression': 'Ac',
            'target_conversation_id': 'contains-group',
            'target_conversation_name': 'Contains Group',
            'priority': 10,
            'enabled': True,
        },
    )
    created = await service.upload_import(
        _scope(),
        {
            'filename': 'customers.csv',
            'body': (
                '客户名称\n'
                'Fresh Co\n'
                'Configured Co\n'
                'Repair Co\n'
                'Acme\n'
            ).encode('utf-8'),
        },
    )
    async with service.ap.persistence_mgr.get_db_engine().begin() as conn:
        await service.ap.persistence_mgr.execute_async(
            sqlalchemy.insert(persistence_broadcast.BroadcastImportRow).values(
                {
                    'import_batch_id': created['id'],
                    'source_row_number': 6,
                    'raw_data': {'客户名称': '   '},
                    'group_value': None,
                    'matched_conversation_id': None,
                    'matched_conversation_name': None,
                    'matched_rule_id': None,
                    'match_status': 'invalid',
                    'error_message': None,
                }
            ),
            conn=conn,
        )
        await service.ap.persistence_mgr.execute_async(
            sqlalchemy.update(persistence_broadcast.BroadcastImportBatch)
            .where(persistence_broadcast.BroadcastImportBatch.id == created['id'])
            .values(
                {
                    'total_rows': 5,
                    'valid_rows': 4,
                    'invalid_rows': 1,
                    'matched_rows': 3,
                    'unmatched_rows': 1,
                }
            ),
            conn=conn,
        )
    return {
        'import_id': created['id'],
        'configured_rule': configured_rule,
        'repair_rule': repair_rule,
        'repair_disabled_rule': repair_disabled_rule,
        'contains_rule': contains_rule,
    }


async def _create_invalid_import_draft(
    service,
    *,
    import_id: int,
    template: dict[str, object],
    group_value: str,
    error_message: str = '未匹配到群聊',
) -> int:
    async with service.ap.persistence_mgr.get_db_engine().begin() as conn:
        return await service.repository.create_draft(
            conn,
            {
                **_scope(),
                'import_batch_id': import_id,
                'group_value': group_value,
                'target_conversation_name': None,

                'target_conversation_id': None,
                'template_id': int(template['id']),
                'template_name_snapshot': str(template['name']),
                'template_content_snapshot': str(template['content']),
                'render_variables': {},
                'draft_text': '',
                'status': 'invalid',
                'send_status': 'pending',
                'sent_at': None,
                'error_message': error_message,
            },
        )


async def _prepare_bulk_assign_batch(
    service,
    *,
    header: str = '瀹㈡埛鍚嶇О',
    rows: list[str] | None = None,
    target_groups: list[tuple[str, str]] | None = None,
) -> dict[str, object]:
    batch_rows = rows or ['Acme', 'Globex']
    groups = target_groups or [
        ('group-acme', 'Acme Group'),
        ('group-globex', 'Globex Group'),
    ]
    await service.save_variable_profile(
        _scope(),
        {
            'group_field': header,
            'mapping_rules': [
                {
                    'source_field': header,
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
            'body': (header + '\n' + '\n'.join(batch_rows) + '\n').encode('utf-8'),
        },
    )
    async with service.ap.persistence_mgr.get_db_engine().begin() as conn:
        await service.ap.persistence_mgr.execute_async(
            sqlalchemy.insert(persistence_broadcast.BroadcastGroupName).values(
                [
                    {
                        'bot_uuid': 'bot-1',
                        'connector_id': 'wxwork-local',
                        'name': name,
                        'external_conversation_id': external_id,
                    }
                    for external_id, name in groups
                ]
            ),
            conn=conn,
        )
    import_groups = await service.list_import_groups(created['id'], _scope(), {})
    return {
        'import_id': created['id'],
        'group_key_by_value': {
            item['group_value']: item['group_key']
            for item in import_groups['groups']
        },
        'target_groups': {
            external_id: name for external_id, name in groups
        },
    }


async def _create_ready_import_draft(
    service,
    *,
    import_id: int,
    group_value: str,
) -> int:
    template = await service.create_template(
        _scope(),
        {
            'name': 'Ready Template',
            'content': 'Hello {{customer_name}}',
            'enabled': True,
        },
    )
    async with service.ap.persistence_mgr.get_db_engine().begin() as conn:
        return await service.repository.create_draft(
            conn,
            {
                **_scope(),
                'import_batch_id': import_id,
                'group_value': group_value,
                'target_conversation_name': 'Ready Group',
                'target_conversation_id': 'ready-group',
                'template_id': int(template['id']),
                'template_name_snapshot': str(template['name']),
                'template_content_snapshot': str(template['content']),
                'render_variables': {'customer_name': group_value},
                'draft_text': f'Hello {group_value}',
                'status': 'ready',
                'send_status': 'pending',
                'sent_at': None,
                'error_message': None,
            },
        )


async def _prepare_ready_drafts_for_execution(
    service,
    draft_specs: list[tuple[str, str]] | None = None,
) -> dict[str, object]:
    specs = draft_specs or [('Acme', 'Acme Group')]
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
    for index, (source_value, target_conversation_name) in enumerate(specs, start=1):
        await service.create_group_rule(
            _scope(),
            {
                'source_value': source_value,
                'match_type': 'exact',
                'match_expression': source_value,
                'target_conversation_name': target_conversation_name,

                'target_conversation_id': target_conversation_name,
                'priority': index * 10,
                'enabled': True,
            },
        )
    created = await service.upload_import(
        _scope(),
        {
            'filename': 'customers.csv',
            'body': (
                '客户名称\n'
                + '\n'.join(source_value for source_value, _ in specs)
                + '\n'
            ).encode('utf-8'),
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
    await service.generate_import_drafts(
        created['id'],
        _scope(),
        {
            'template_id': template['id'],
            'group_keys': await _all_import_group_keys(service, created['id']),
        },
    )
    generated_drafts = await service.list_drafts(_scope(), {'import_batch_id': created['id']})
    draft_ids = [
        next(item['id'] for item in generated_drafts if item['group_value'] == source_value)
        for source_value, _ in specs
    ]
    await service.update_draft_statuses(_scope(), {'draft_ids': draft_ids, 'status': 'ready'})
    drafts = [await service.get_draft_detail(draft_id, _scope()) for draft_id in draft_ids]
    return {
        'import_id': created['id'],
        'draft': drafts[0],
        'drafts': drafts,
    }


async def _prepare_ready_draft_for_execution(service) -> dict[str, object]:
    return await _prepare_ready_drafts_for_execution(service)


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


async def test_resolve_persisted_batch_group_field_uses_legacy_fallback_without_persisting(service_fixture):
    service, _ = service_fixture

    resolved = service._resolve_persisted_batch_group_field(
        batch=SimpleNamespace(group_field_used=None, group_field_source=None),
        variable_profile=SimpleNamespace(group_field='客户名称'),
    )

    assert resolved['group_field'] == '客户名称'
    assert resolved['source'] == 'legacy_fallback'


async def test_resolve_persisted_batch_group_field_keeps_contract_source_when_batch_field_exists(
    service_fixture,
):
    service, _ = service_fixture

    resolved = service._resolve_persisted_batch_group_field(
        batch=SimpleNamespace(group_field_used='客户名称', group_field_source='auto_detected'),
        variable_profile=SimpleNamespace(group_field='其他字段'),
    )

    assert resolved['group_field'] == '客户名称'
    assert resolved['source'] == 'auto_detected'


async def test_resolve_persisted_batch_group_field_falls_back_to_configured_source_when_batch_source_missing(
    service_fixture,
):
    service, _ = service_fixture

    resolved = service._resolve_persisted_batch_group_field(
        batch=SimpleNamespace(group_field_used='客户名称', group_field_source=None),
        variable_profile=SimpleNamespace(group_field='其他字段'),
    )

    assert resolved['group_field'] == '客户名称'
    assert resolved['source'] == 'configured'


async def test_resolve_persisted_batch_group_field_raises_when_legacy_fallback_is_unavailable(
    service_fixture,
):
    service, _ = service_fixture

    with pytest.raises(BroadcastError) as exc_info:
        service._resolve_persisted_batch_group_field(
            batch=SimpleNamespace(group_field_used=None, group_field_source=None),
            variable_profile=SimpleNamespace(group_field=''),
        )

    assert exc_info.value.code == BROADCAST_IMPORT_GROUP_FIELD_UNRESOLVABLE


async def test_resolve_upload_group_field_maps_confirmation_required_to_object_details_with_filename(
    service_fixture,
):
    service, _ = service_fixture

    with pytest.raises(BroadcastError) as exc_info:
        service._resolve_upload_group_field(
            headers=['客户', '姓名', '订单号'],
            variable_profile={'group_field': '配置客户字段', 'mapping_rules': []},
            original_file_name='customers.csv',
        )

    assert exc_info.value.code == BROADCAST_IMPORT_GROUP_FIELD_CONFIRMATION_REQUIRED
    assert exc_info.value.details == {
        'headers': ['客户', '姓名', '订单号'],
        'candidates': ['客户', '姓名'],
        'configured_group_field': '配置客户字段',
        'original_file_name': 'customers.csv',
    }


async def test_resolve_upload_group_field_keeps_empty_candidates_and_filename_for_unresolved_confirmation(
    service_fixture,
):
    service, _ = service_fixture

    with pytest.raises(BroadcastError) as exc_info:
        service._resolve_upload_group_field(
            headers=['订单号', '联系人手机号'],
            variable_profile={'group_field': None, 'mapping_rules': []},
            original_file_name='customers.csv',
        )

    assert exc_info.value.code == BROADCAST_IMPORT_GROUP_FIELD_CONFIRMATION_REQUIRED
    assert exc_info.value.details == {
        'headers': ['订单号', '联系人手机号'],
        'candidates': [],
        'configured_group_field': None,
        'original_file_name': 'customers.csv',
    }


async def test_resolve_upload_group_field_maps_invalid_override_to_object_details_with_filename(
    service_fixture,
):
    service, _ = service_fixture

    with pytest.raises(BroadcastError) as exc_info:
        service._resolve_upload_group_field(
            headers=['客户名称', '订单号'],
            variable_profile={'group_field': '客户名称', 'mapping_rules': []},
            group_field_override='用户名',
            original_file_name='customers.csv',
        )

    assert exc_info.value.code == BROADCAST_IMPORT_GROUP_FIELD_OVERRIDE_INVALID
    assert exc_info.value.details == {
        'group_field_override': '用户名',
        'headers': ['客户名称', '订单号'],
        'original_file_name': 'customers.csv',
    }


async def test_list_group_rule_candidates_defaults_to_new_and_returns_batch_stats(
    service_fixture,
):
    service, _ = service_fixture
    setup = await _prepare_group_rule_candidate_status_batch(service)

    result = await service.list_group_rule_candidates(
        setup['import_id'],
        _scope(),
        {},
    )

    assert result['import_batch_id'] == setup['import_id']
    assert result['group_field_used'] == '客户名称'
    assert result['group_field_source'] == 'configured'
    assert result['raw_row_total'] == 5
    assert result['unique_customer_total'] == 5
    assert result['stats'] == {
        'new_count': 1,
        'configured_count': 1,
        'needs_repair_count': 1,
        'conflict_count': 1,
        'invalid_count': 1,
    }
    assert result['page'] == 1
    assert result['page_size'] == 50
    assert result['total'] == 1
    assert result['total_pages'] == 1
    assert len(result['items']) == 1
    assert result['items'][0]['customer_name'] == 'Fresh Co'
    assert result['items'][0]['status'] == 'new'
    assert result['items'][0]['existing_rule_ids'] == []
    assert result['items'][0]['existing_rules'] == []
    assert result['items'][0]['current_matched_rule'] is None
    assert result['items'][0]['current_target_conversation_id'] is None
    assert result['items'][0]['current_target_conversation_name'] is None
    assert result['items'][0]['current_match_type'] is None


async def test_list_group_rule_candidates_distinguishes_configured_repair_conflict_and_invalid(
    service_fixture,
):
    service, _ = service_fixture
    setup = await _prepare_group_rule_candidate_status_batch(service)

    result = await service.list_group_rule_candidates(
        setup['import_id'],
        _scope(),
        {'status': 'all'},
    )
    items_by_name = {
        item['customer_name']: item for item in result['items'] if item['customer_name']
    }
    invalid_items = [item for item in result['items'] if not item['customer_name']]

    configured = items_by_name['Configured Co']
    assert configured['status'] == 'configured'
    assert configured['existing_rule_ids'] == [setup['configured_rule']['id']]
    assert [item['id'] for item in configured['existing_rules']] == [
        setup['configured_rule']['id']
    ]
    assert configured['current_matched_rule']['id'] == setup['configured_rule']['id']
    assert configured['current_target_conversation_id'] == 'configured-group'
    assert configured['current_target_conversation_name'] == 'Configured Group'
    assert configured['current_match_type'] == 'exact'

    repair = items_by_name['Repair Co']
    assert repair['status'] == 'needs_repair'
    assert set(repair['existing_rule_ids']) == {
        setup['repair_rule']['id'],
        setup['repair_disabled_rule']['id'],
    }
    assert {item['id'] for item in repair['existing_rules']} == {
        setup['repair_rule']['id'],
        setup['repair_disabled_rule']['id'],
    }
    assert repair['current_matched_rule']['id'] == setup['repair_rule']['id']
    assert repair['current_target_conversation_id'] == 'repair-valid-group'
    assert repair['current_target_conversation_name'] == 'Repair Valid Group'
    assert repair['current_match_type'] == 'exact'
    assert repair['reason']

    conflict = items_by_name['Acme']
    assert conflict['status'] == 'conflict'
    assert conflict['existing_rule_ids'] == []
    assert conflict['existing_rules'] == []
    assert conflict['current_matched_rule']['id'] == setup['contains_rule']['id']
    assert conflict['current_target_conversation_id'] == 'contains-group'
    assert conflict['current_target_conversation_name'] == 'Contains Group'
    assert conflict['current_match_type'] == 'contains'
    assert conflict['reason']

    assert len(invalid_items) == 1
    assert invalid_items[0]['status'] == 'invalid'
    assert invalid_items[0]['customer_name'] == ''
    assert invalid_items[0]['existing_rule_ids'] == []
    assert invalid_items[0]['current_matched_rule'] is None


async def test_list_group_rule_candidates_supports_status_filter_pagination_and_keyword(
    service_fixture,
):
    service, _ = service_fixture
    setup = await _prepare_group_rule_candidate_status_batch(service)

    paged = await service.list_group_rule_candidates(
        setup['import_id'],
        _scope(),
        {'status': 'all', 'page': 2, 'page_size': 2},
    )
    assert paged['total'] == 5
    assert paged['total_pages'] == 3
    assert [item['customer_name'] for item in paged['items']] == ['Repair Co', 'Acme']

    conflict_only = await service.list_group_rule_candidates(
        setup['import_id'],
        _scope(),
        {'status': 'conflict'},
    )
    assert conflict_only['total'] == 1
    assert [item['customer_name'] for item in conflict_only['items']] == ['Acme']

    keyword_filtered = await service.list_group_rule_candidates(
        setup['import_id'],
        _scope(),
        {'status': 'all', 'keyword': 'Repair'},
    )
    assert keyword_filtered['total'] == 1
    assert keyword_filtered['items'][0]['customer_name'] == 'Repair Co'
    assert keyword_filtered['items'][0]['status'] == 'needs_repair'


async def test_list_group_rule_candidates_keeps_group_name_fallback_as_new_when_no_rule_conflict(
    service_fixture,
):
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
    await service.create_group_names(
        _scope(),
        {
            'names': ['Fallback Co'],
        },
    )
    created = await service.upload_import(
        _scope(),
        {
            'filename': 'customers.csv',
            'body': '客户名称\nFallback Co\n'.encode('utf-8'),
        },
    )

    result = await service.list_group_rule_candidates(
        created['id'],
        _scope(),
        {'status': 'all'},
    )

    assert result['stats'] == {
        'new_count': 1,
        'configured_count': 0,
        'needs_repair_count': 0,
        'conflict_count': 0,
        'invalid_count': 0,
    }
    assert result['items'][0]['customer_name'] == 'Fallback Co'
    assert result['items'][0]['status'] == 'new'
    assert result['items'][0]['current_matched_rule'] is None
    assert result['items'][0]['current_match_type'] == 'group_name_fallback'
    assert result['items'][0]['current_target_conversation_name'] == 'Fallback Co'


async def test_list_group_rule_candidates_uses_runtime_legacy_fallback_without_persisting_batch(
    service_fixture,
):
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
    async with service.ap.persistence_mgr.get_db_engine().begin() as conn:
        await service.ap.persistence_mgr.execute_async(
            sqlalchemy.update(persistence_broadcast.BroadcastImportBatch)
            .where(persistence_broadcast.BroadcastImportBatch.id == created['id'])
            .values({'group_field_used': None, 'group_field_source': None}),
            conn=conn,
        )

    result = await service.list_group_rule_candidates(
        created['id'],
        _scope(),
        {'status': 'all'},
    )
    batch = await service.repository.get_import_batch(created['id'], **_scope())

    assert result['group_field_used'] == '客户名称'
    assert result['group_field_source'] == 'legacy_fallback'
    assert batch.group_field_used is None
    assert batch.group_field_source is None


async def test_list_group_rule_candidates_rejects_legacy_batch_when_group_field_is_unresolvable(
    service_fixture,
):
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
    async with service.ap.persistence_mgr.get_db_engine().begin() as conn:
        await service.ap.persistence_mgr.execute_async(
            sqlalchemy.update(persistence_broadcast.BroadcastImportBatch)
            .where(persistence_broadcast.BroadcastImportBatch.id == created['id'])
            .values({'group_field_used': None, 'group_field_source': None}),
            conn=conn,
        )
        await service.ap.persistence_mgr.execute_async(
            sqlalchemy.update(persistence_broadcast.BroadcastVariableProfile)
            .where(
                persistence_broadcast.BroadcastVariableProfile.bot_uuid == 'bot-1',
                persistence_broadcast.BroadcastVariableProfile.connector_id == 'wxwork-local',
            )
            .values({'group_field': None}),
            conn=conn,
        )

    with pytest.raises(BroadcastError) as exc_info:
        await service.list_group_rule_candidates(
            created['id'],
            _scope(),
            {'status': 'all'},
        )

    assert exc_info.value.code == BROADCAST_IMPORT_GROUP_FIELD_UNRESOLVABLE


async def test_bulk_assign_import_group_rules_rejects_empty_items(service_fixture):
    service, _ = service_fixture
    setup = await _prepare_bulk_assign_batch(service)

    with pytest.raises(BroadcastError) as exc_info:
        await service.bulk_assign_import_group_rules(
            setup['import_id'],
            _scope(),
            {'items': []},
        )

    assert exc_info.value.code == BATCH_VALIDATION_FAILED


async def test_bulk_assign_import_group_rules_rejects_duplicate_group_keys(service_fixture):
    service, _ = service_fixture
    setup = await _prepare_bulk_assign_batch(service)
    group_key = setup['group_key_by_value']['Acme']

    with pytest.raises(BroadcastError) as exc_info:
        await service.bulk_assign_import_group_rules(
            setup['import_id'],
            _scope(),
            {
                'items': [
                    {'group_key': group_key, 'target_conversation_id': 'group-acme'},
                    {'group_key': group_key, 'target_conversation_id': 'group-globex'},
                ]
            },
        )

    assert exc_info.value.code == BATCH_VALIDATION_FAILED


async def test_bulk_assign_import_group_rules_returns_item_error_when_group_missing(service_fixture):
    service, _ = service_fixture
    setup = await _prepare_bulk_assign_batch(service)

    with pytest.raises(BroadcastError) as exc_info:
        await service.bulk_assign_import_group_rules(
            setup['import_id'],
            _scope(),
            {
                'items': [
                    {
                        'group_key': 'missing-group-key',
                        'target_conversation_id': 'group-acme',
                    }
                ]
            },
        )

    assert exc_info.value.code == BROADCAST_IMPORT_GROUP_RULE_BULK_ASSIGN_FAILED
    assert exc_info.value.details['items'][0]['code'] == BROADCAST_IMPORT_GROUP_NOT_FOUND


async def test_bulk_assign_import_group_rules_returns_item_error_when_target_missing(service_fixture):
    service, _ = service_fixture
    setup = await _prepare_bulk_assign_batch(service)

    with pytest.raises(BroadcastError) as exc_info:
        await service.bulk_assign_import_group_rules(
            setup['import_id'],
            _scope(),
            {
                'items': [
                    {
                        'group_key': setup['group_key_by_value']['Acme'],
                        'target_conversation_id': 'missing-group',
                    }
                ]
            },
        )

    assert exc_info.value.code == BROADCAST_IMPORT_GROUP_RULE_BULK_ASSIGN_FAILED
    assert exc_info.value.details['items'][0]['code'] == BROADCAST_GROUP_NAME_NOT_FOUND


async def test_bulk_assign_import_group_rules_rejects_non_new_candidates(service_fixture):
    service, _ = service_fixture
    setup = await _prepare_group_rule_candidate_status_batch(service)
    candidates = await service.list_group_rule_candidates(
        setup['import_id'],
        _scope(),
        {'status': 'all'},
    )
    configured = next(item for item in candidates['items'] if item['customer_name'] == 'Configured Co')

    with pytest.raises(BroadcastError) as exc_info:
        await service.bulk_assign_import_group_rules(
            setup['import_id'],
            _scope(),
            {
                'items': [
                    {
                        'group_key': configured['group_key'],
                        'target_conversation_id': 'configured-group',
                    }
                ]
            },
        )

    assert exc_info.value.code == BROADCAST_IMPORT_GROUP_RULE_BULK_ASSIGN_FAILED
    assert exc_info.value.details['items'][0]['group_key'] == configured['group_key']
    assert exc_info.value.details['items'][0]['customer_name'] == 'Configured Co'


async def test_bulk_assign_import_group_rules_blocks_ready_drafts(service_fixture):
    service, _ = service_fixture
    setup = await _prepare_bulk_assign_batch(service)
    await _create_ready_import_draft(
        service,
        import_id=setup['import_id'],
        group_value='Acme',
    )

    with pytest.raises(BroadcastError) as exc_info:
        await service.bulk_assign_import_group_rules(
            setup['import_id'],
            _scope(),
            {
                'items': [
                    {
                        'group_key': setup['group_key_by_value']['Acme'],
                        'target_conversation_id': 'group-acme',
                    }
                ]
            },
        )

    assert exc_info.value.code == BROADCAST_IMPORT_READY_DRAFT_EXISTS


async def test_bulk_assign_import_group_rules_rolls_back_when_formal_match_is_intercepted(
    service_fixture,
    monkeypatch,
):
    service, _ = service_fixture
    setup = await _prepare_bulk_assign_batch(service, rows=['Acme'])
    original_create_group_rule = service.repository.create_group_rule

    async def create_group_rule_with_interceptor(conn, payload):
        rule_id = await original_create_group_rule(conn, payload)
        if payload['source_value'] == 'Acme':
            await original_create_group_rule(
                conn,
                {
                    **_scope(),
                    'source_value': 'Ac',
                    'match_type': 'contains',
                    'match_expression': 'Acme',
                    'target_conversation_id': 'steal-group',
                    'target_conversation_name': 'Steal Group',
                    'priority': 99,
                    'enabled': True,
                },
            )
        return rule_id

    monkeypatch.setattr(service.repository, 'create_group_rule', create_group_rule_with_interceptor)

    with pytest.raises(BroadcastError) as exc_info:
        await service.bulk_assign_import_group_rules(
            setup['import_id'],
            _scope(),
            {
                'items': [
                    {
                        'group_key': setup['group_key_by_value']['Acme'],
                        'target_conversation_id': 'group-acme',
                    }
                ]
            },
        )

    assert exc_info.value.code == BROADCAST_IMPORT_GROUP_RULE_BULK_ASSIGN_FAILED
    assert exc_info.value.details['items'][0]['customer_name'] == 'Acme'
    rules = await service.list_group_rules(_scope())
    assert rules == []


async def test_bulk_assign_import_group_rules_uses_persisted_batch_field_and_rematches(
    service_fixture,
):
    service, _ = service_fixture
    await service.save_variable_profile(
        _scope(),
        {
            'group_field': '昵称',
            'mapping_rules': [
                {
                    'source_field': '昵称',
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
            'body': '昵称,客户名\nlegacy-acme,visible-acme\n'.encode('utf-8'),
        },
    )
    async with service.ap.persistence_mgr.get_db_engine().begin() as conn:
        await service.ap.persistence_mgr.execute_async(
            sqlalchemy.insert(persistence_broadcast.BroadcastGroupName).values(
                {
                    'bot_uuid': 'bot-1',
                    'connector_id': 'wxwork-local',
                    'name': 'Acme Stable Group',
                    'external_conversation_id': 'group-acme-stable',
                }
            ),
            conn=conn,
        )
    await service.save_variable_profile(
        _scope(),
        {
            'group_field': '客户名',
            'mapping_rules': [
                {
                    'source_field': '客户名',
                    'variable_key': 'customer_name',
                    'merge_mode': 'first',
                    'order': 1,
                }
            ],
        },
    )
    groups = await service.list_import_groups(created['id'], _scope(), {})
    group_key = groups['groups'][0]['group_key']

    result = await service.bulk_assign_import_group_rules(
        created['id'],
        _scope(),
        {
            'items': [
                {
                    'group_key': group_key,
                    'target_conversation_id': 'group-acme-stable',
                }
            ]
        },
    )

    rules = await service.list_group_rules(_scope())
    assert result['group_field_used'] == '昵称'
    assert rules[0]['source_value'] == 'legacy-acme'
    assert rules[0]['match_expression'] == 'legacy-acme'
    detail = await service.get_import_detail(created['id'], _scope(), {})
    assert detail['rows'][0]['group_value'] == 'legacy-acme'
    assert detail['rows'][0]['matched_conversation_id'] == 'group-acme-stable'
    assert detail['rows'][0]['matched_rule_id'] == rules[0]['id']


async def test_bulk_assign_import_group_rules_uses_legacy_fallback_without_persisting_batch(
    service_fixture,
):
    service, _ = service_fixture
    setup = await _prepare_bulk_assign_batch(service, rows=['Acme'])
    async with service.ap.persistence_mgr.get_db_engine().begin() as conn:
        await service.ap.persistence_mgr.execute_async(
            sqlalchemy.update(persistence_broadcast.BroadcastImportBatch)
            .where(persistence_broadcast.BroadcastImportBatch.id == setup['import_id'])
            .values({'group_field_used': None, 'group_field_source': None}),
            conn=conn,
        )

    result = await service.bulk_assign_import_group_rules(
        setup['import_id'],
        _scope(),
        {
            'items': [
                {
                    'group_key': setup['group_key_by_value']['Acme'],
                    'target_conversation_id': 'group-acme',
                }
            ]
        },
    )
    batch = await service.repository.get_import_batch(setup['import_id'], **_scope())

    assert result['group_field_source'] == 'legacy_fallback'
    assert batch.group_field_used is None
    assert batch.group_field_source is None


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

                'target_conversation_id': 'Acme Group',
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

                    'target_conversation_id': '??',
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
        'matched_rule_id': None,
        'rule_id': None,
        'source_value': '??',
        'target_conversation_name': None,

        'target_conversation_id': None,
        'match_type': None,
        'candidate_count': 0,
        'candidate_rules': [],
        'conflict': False,
        'reason': 'no_matching_rule',
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


async def test_create_group_rule_rejects_duplicate_exact_rule_after_normalization(service_fixture):
    service, _ = service_fixture

    await service.create_group_rule(
        _scope(),
        {
            'source_value': '  Acme  ',
            'match_type': 'exact',
            'match_expression': 'Acme',
            'target_conversation_id': 'group-1',
            'target_conversation_name': 'Acme Group',
            'priority': 10,
            'enabled': True,
        },
    )

    with pytest.raises(BroadcastError) as exc_info:
        await service.create_group_rule(
            _scope(),
            {
                'source_value': 'Acme',
                'match_type': 'exact',
                'match_expression': '  Acme  ',
                'target_conversation_id': 'group-2',
                'target_conversation_name': 'Another Group',
                'priority': 1,
                'enabled': True,
            },
        )

    assert exc_info.value.code == BROADCAST_GROUP_RULE_DUPLICATE


async def test_update_group_rule_rejects_duplicate_exact_rule_but_allows_self_exclusion(service_fixture):
    service, _ = service_fixture

    first_rule = await service.create_group_rule(
        _scope(),
        {
            'source_value': 'Acme',
            'match_type': 'exact',
            'match_expression': 'Acme',
            'target_conversation_id': 'group-1',
            'target_conversation_name': 'Acme Group',
            'priority': 10,
            'enabled': True,
        },
    )
    second_rule = await service.create_group_rule(
        _scope(),
        {
            'source_value': 'Globex',
            'match_type': 'exact',
            'match_expression': 'Globex',
            'target_conversation_id': 'group-2',
            'target_conversation_name': 'Globex Group',
            'priority': 9,
            'enabled': True,
        },
    )

    updated = await service.update_group_rule(
        first_rule['id'],
        _scope(),
        {
            'source_value': '  Acme  ',
            'match_type': 'exact',
            'match_expression': 'Acme',
            'target_conversation_id': 'group-1-updated',
            'target_conversation_name': 'Acme Group Updated',
            'priority': 8,
            'enabled': True,
        },
    )
    assert updated['id'] == first_rule['id']
    assert updated['target_conversation_id'] == 'group-1-updated'

    with pytest.raises(BroadcastError) as exc_info:
        await service.update_group_rule(
            second_rule['id'],
            _scope(),
            {
                'source_value': 'Acme',
                'match_type': 'exact',
                'match_expression': '  Acme  ',
                'target_conversation_id': 'group-2',
                'target_conversation_name': 'Globex Group',
                'priority': 9,
                'enabled': True,
            },
        )

    assert exc_info.value.code == BROADCAST_GROUP_RULE_DUPLICATE


async def test_match_group_rule_returns_candidate_diagnostics_in_formal_match_order(service_fixture):
    service, persistence_mgr = service_fixture

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
                    'target_conversation_id': '??',
                    'priority': 999,
                    'enabled': True,
                }
            )
        )

    exact_rule = await service.create_group_rule(
        _scope(),
        {
            'source_value': 'Acme',
            'match_type': 'exact',
            'match_expression': 'Acme',
            'target_conversation_id': 'exact-group',
            'target_conversation_name': 'Exact Group',
            'priority': 10,
            'enabled': True,
        },
    )
    contains_rule = await service.create_group_rule(
        _scope(),
        {
            'source_value': 'Ac',
            'match_type': 'contains',
            'match_expression': 'Ac',
            'target_conversation_id': 'contains-group',
            'target_conversation_name': 'Contains Group',
            'priority': 10,
            'enabled': True,
        },
    )
    regex_rule = await service.create_group_rule(
        _scope(),
        {
            'source_value': 'Acme',
            'match_type': 'regex',
            'match_expression': '^Acme$',
            'target_conversation_id': 'regex-group',
            'target_conversation_name': 'Regex Group',
            'priority': 20,
            'enabled': True,
        },
    )

    matched = await service.match_group_rule(_scope(), {'source_value': '  Acme  '})

    assert matched['matched'] is True
    assert matched['matched_rule_id'] == regex_rule['id']
    assert matched['rule_id'] == regex_rule['id']
    assert matched['source_value'] == 'Acme'
    assert matched['match_type'] == 'regex'
    assert matched['target_conversation_id'] == 'regex-group'
    assert matched['target_conversation_name'] == 'Regex Group'
    assert matched['candidate_count'] == 3
    assert [item['id'] for item in matched['candidate_rules']] == [
        regex_rule['id'],
        exact_rule['id'],
        contains_rule['id'],
    ]
    assert [item['match_type'] for item in matched['candidate_rules']] == [
        'regex',
        'exact',
        'contains',
    ]
    assert matched['conflict'] is True
    assert matched['reason'] == 'multiple_matching_rules'

    unmatched = await service.match_group_rule(_scope(), {'source_value': 'Northwind'})

    assert unmatched['matched'] is False
    assert unmatched['matched_rule_id'] is None
    assert unmatched['candidate_count'] == 0
    assert unmatched['candidate_rules'] == []
    assert unmatched['conflict'] is False
    assert unmatched['reason'] == 'no_matching_rule'


async def test_match_group_rule_does_not_trim_historical_exact_match_expression(service_fixture):
    service, persistence_mgr = service_fixture

    async with persistence_mgr.engine.begin() as conn:
        await conn.execute(
            sqlalchemy.insert(persistence_broadcast.BroadcastGroupRule).values(
                {
                    'bot_uuid': 'bot-1',
                    'connector_id': 'wxwork-local',
                    'source_value': 'Acme',
                    'match_type': 'exact',
                    'match_expression': '  Acme  ',
                    'target_conversation_name': 'Historical Exact Group',
                    'target_conversation_id': 'historical-exact-group',
                    'priority': 10,
                    'enabled': True,
                }
            )
        )

    preview = await service.match_group_rule(_scope(), {'source_value': 'Acme'})

    assert preview['matched'] is False
    assert preview['matched_rule_id'] is None
    assert preview['candidate_count'] == 0
    assert preview['candidate_rules'] == []
    assert preview['conflict'] is False
    assert preview['reason'] == 'no_matching_rule'


async def test_create_group_rule_rejects_placeholder_and_requires_target_conversation_id(service_fixture):
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
                'target_conversation_id': 'placeholder-id',
                'target_conversation_name': '??',

                'target_conversation_id': '??',
                'priority': 1,
                'enabled': True,
            },
        )
    assert placeholder_error.value.code == BROADCAST_GROUP_RULE_REGEX_INVALID

    created = await service.create_group_rule(
        _scope(),
        {
            'source_value': '小满',
            'match_type': 'exact',
            'match_expression': '小满',
            'target_conversation_id': 'conversation-stable-id',
            'target_conversation_name': '不存在的群',
            'priority': 1,
            'enabled': True,
        },
    )
    assert created['target_conversation_name'] == '不存在的群'
    assert created['target_conversation_id'] == 'conversation-stable-id'

    with pytest.raises(BroadcastError) as missing_id_error:
        await service.create_group_rule(
            _scope(),
            {
                'source_value': '小满',
                'match_type': 'exact',
                'match_expression': '小满',
                'target_conversation_id': '',
                'target_conversation_name': '不存在的群',
                'priority': 1,
                'enabled': True,
            },
        )
    assert missing_id_error.value.code == BROADCAST_GROUP_RULE_REGEX_INVALID


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

            'target_conversation_id': '小满',
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



async def test_upload_import_requires_group_field_confirmation_for_ambiguous_alias_headers(service_fixture):
    service, _ = service_fixture

    await service.save_variable_profile(
        _scope(),
        {
            'group_field': '\u5386\u53f2\u5ba2\u6237\u540d\u79f0',
            'mapping_rules': [
                {
                    'source_field': '\u8ba2\u5355\u53f7',
                    'variable_key': 'order_no',
                    'merge_mode': 'first',
                    'order': 1,
                }
            ],
        },
    )

    with pytest.raises(BroadcastError) as exc_info:
        await service.upload_import(
            _scope(),
            {
                'filename': 'customers.csv',
                'body': '\u5ba2\u6237,\u59d3\u540d,\u8ba2\u5355\u53f7\nAcme,\u5f20\u4e09,SO-001\n'.encode('utf-8'),
            },
        )

    assert exc_info.value.code == BROADCAST_IMPORT_GROUP_FIELD_CONFIRMATION_REQUIRED
    details = exc_info.value.details
    assert isinstance(details, dict)
    assert details['headers'] == ['\u5ba2\u6237', '\u59d3\u540d', '\u8ba2\u5355\u53f7']
    assert details['candidates'] == ['\u5ba2\u6237', '\u59d3\u540d']
    assert details['configured_group_field'] == '\u5386\u53f2\u5ba2\u6237\u540d\u79f0'
    assert details['original_file_name'] == 'customers.csv'


async def test_upload_import_requires_group_field_confirmation_when_no_candidate_header_matches(service_fixture):
    service, _ = service_fixture

    await service.save_variable_profile(
        _scope(),
        {
            'group_field': '\u5386\u53f2\u5ba2\u6237\u540d\u79f0',
            'mapping_rules': [
                {
                    'source_field': '\u8ba2\u5355\u53f7',
                    'variable_key': 'order_no',
                    'merge_mode': 'first',
                    'order': 1,
                }
            ],
        },
    )

    with pytest.raises(BroadcastError) as exc_info:
        await service.upload_import(
            _scope(),
            {
                'filename': 'customers.csv',
                'body': '\u8ba2\u5355\u53f7,\u8054\u7cfb\u4eba\u624b\u673a\u53f7\nSO-001,13800000000\n'.encode('utf-8'),
            },
        )

    assert exc_info.value.code == BROADCAST_IMPORT_GROUP_FIELD_CONFIRMATION_REQUIRED
    details = exc_info.value.details
    assert isinstance(details, dict)
    assert details['headers'] == ['\u8ba2\u5355\u53f7', '\u8054\u7cfb\u4eba\u624b\u673a\u53f7']
    assert details['candidates'] == []
    assert details['configured_group_field'] == '\u5386\u53f2\u5ba2\u6237\u540d\u79f0'
    assert details['original_file_name'] == 'customers.csv'


async def test_upload_import_rejects_invalid_group_field_override_with_structured_details(service_fixture):
    service, _ = service_fixture

    await service.save_variable_profile(
        _scope(),
        {
            'group_field': '\u5ba2\u6237\u540d\u79f0',
            'mapping_rules': [
                {
                    'source_field': '\u8ba2\u5355\u53f7',
                    'variable_key': 'order_no',
                    'merge_mode': 'first',
                    'order': 1,
                }
            ],
        },
    )

    with pytest.raises(BroadcastError) as exc_info:
        await service.upload_import(
            _scope(),
            {
                'filename': 'customers.csv',
                'body': '\u5ba2\u6237\u540d\u79f0,\u8ba2\u5355\u53f7\nAcme,SO-001\n'.encode('utf-8'),
                'group_field_override': '\u7528\u6237\u540d',
            },
        )

    assert exc_info.value.code == BROADCAST_IMPORT_GROUP_FIELD_OVERRIDE_INVALID
    details = exc_info.value.details
    assert isinstance(details, dict)
    assert details['group_field_override'] == '\u7528\u6237\u540d'
    assert details['headers'] == ['\u5ba2\u6237\u540d\u79f0', '\u8ba2\u5355\u53f7']
    assert details['original_file_name'] == 'customers.csv'
