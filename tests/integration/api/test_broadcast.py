from __future__ import annotations

import json
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest
import sqlalchemy
from werkzeug.datastructures import FileStorage
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

from tests.factories import FakeApp


pytestmark = pytest.mark.integration


class _TransactionContext:
    def __init__(self, manager: '_PersistenceManager') -> None:
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
    def __init__(self, manager: '_PersistenceManager') -> None:
        self._manager = manager

    def begin(self) -> _TransactionContext:
        return _TransactionContext(self._manager)


class _PersistenceManager:
    def __init__(self) -> None:
        from langbot.pkg.entity.persistence import base

        self.engine = create_async_engine('sqlite+aiosqlite:///:memory:')
        self.meta = base.Base.metadata
        self.engine_proxy = _EngineProxy(self)

    async def initialize(self) -> None:
        async with self.engine.begin() as conn:
            await conn.run_sync(self.meta.create_all)

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
        import datetime

        masked_columns = masked_columns or []
        return {
            column.name: getattr(data, column.name)
            if not isinstance(getattr(data, column.name), datetime.datetime)
            else getattr(data, column.name).isoformat()
            for column in model.__table__.columns
            if column.name not in masked_columns
        }


@pytest.fixture(scope='module')
def mock_circular_import_chain():
    from tests.utils.import_isolation import MockLifecycleControlScope, isolated_sys_modules

    class FakeMinimalApplication:
        pass

    mock_app = MagicMock()
    mock_app.Application = FakeMinimalApplication

    mock_entities = MagicMock()
    mock_entities.LifecycleControlScope = MockLifecycleControlScope

    clear = [
        'langbot.pkg.api.http.controller.group',
        'langbot.pkg.api.http.controller.groups',
        'langbot.pkg.api.http.controller.main',
    ]

    with isolated_sys_modules(
        mocks={
            'langbot.pkg.core.app': mock_app,
            'langbot.pkg.core.entities': mock_entities,
        },
        clear=clear,
    ):
        import langbot.pkg.api.http.controller.groups.broadcast as _broadcast  # noqa: F401

        yield


@pytest.fixture
async def fake_broadcast_app():
    from langbot.pkg.broadcast.service import BroadcastService
    from langbot.pkg.entity.persistence import bot as persistence_bot
    from langbot.pkg.entity.persistence import database_mode as persistence_database_mode

    app = FakeApp()
    app.instance_config.data.update(
        {
            'api': {'port': 5300},
            'system': {'allow_modify_login_info': True, 'limitation': {}},
        }
    )

    app.user_service = Mock()
    app.user_service.is_initialized = AsyncMock(return_value=True)
    app.user_service.verify_jwt_token = AsyncMock(return_value='test@example.com')
    app.user_service.get_user_by_email = AsyncMock(return_value=Mock(email='test@example.com'))
    app.apikey_service = Mock()
    app.apikey_service.verify_api_key = AsyncMock(return_value=True)

    persistence_mgr = _PersistenceManager()
    await persistence_mgr.initialize()
    app.persistence_mgr = persistence_mgr

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
        channel_local_id = (
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
        channel_other_id = (
            await conn.execute(
                sqlalchemy.insert(persistence_database_mode.ChannelAccount).values(
                    {
                        'connector_id': 'wxwork-other',
                        'channel_type': 'wxwork_database',
                        'external_account_id': 'wxwork-other',
                        'display_name': 'WXWork Database',
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
                    'channel_account_id': channel_local_id,
                    'enabled': True,
                    'auto_generate_draft': False,
                }
            )
        )
        await conn.execute(
            sqlalchemy.insert(persistence_database_mode.BotChannelBinding).values(
                {
                    'bot_uuid': 'bot-2',
                    'channel_account_id': channel_other_id,
                    'enabled': True,
                    'auto_generate_draft': False,
                }
            )
        )
        await conn.execute(
            sqlalchemy.insert(persistence_database_mode.DatabaseConversation).values(
                [
                    {
                        'connector_id': 'wxwork-local',
                        'source': 'wxwork',
                        'external_conversation_id': 'direct-1',
                        'conversation_name': '杨炳恒',
                        'conversation_type': 'direct',
                    },
                    {
                        'connector_id': 'wxwork-local',
                        'source': 'wxwork',
                        'external_conversation_id': 'group-1',
                        'conversation_name': '小满',
                        'conversation_type': 'group',
                    },
                ]
            )
        )

    app.bot_service = SimpleNamespace(
        get_bot=AsyncMock(
            side_effect=lambda bot_uuid, include_secret=False: {
                'uuid': bot_uuid,
                'adapter': 'wxwork_database',
                'enable': True,
            }
            if bot_uuid in {'bot-1', 'bot-2'}
            else None
        )
    )
    app.broadcast_service = BroadcastService(app)

    try:
        yield app
    finally:
        await persistence_mgr.dispose()


@pytest.fixture
async def quart_test_client(fake_broadcast_app, http_controller_cls):
    controller = http_controller_cls(fake_broadcast_app)
    await controller.initialize()
    client = controller.quart_app.test_client()
    try:
        yield client
    finally:
        if getattr(controller, 'mcp_mount', None) is not None:
            await controller.mcp_mount.stop_session_manager()


def _auth_headers() -> dict[str, str]:
    return {'Authorization': 'Bearer test_token'}


def _query_scope(bot_uuid: str = 'bot-1', connector_id: str = 'wxwork-local') -> str:
    return f'bot_uuid={bot_uuid}&connector_id={connector_id}'


async def _get_import_group_key(
    quart_test_client,
    import_id: int,
    *,
    group_value: str,
) -> str:
    response = await quart_test_client.get(
        f'/api/v1/broadcast/imports/{import_id}/groups?{_query_scope()}',
        headers=_auth_headers(),
    )
    payload = await response.get_json()
    assert response.status_code == 200
    groups = payload['data']['groups']
    return next(item['group_key'] for item in groups if item['group_value'] == group_value)


async def _get_all_import_group_keys(
    quart_test_client,
    import_id: int,
) -> list[str]:
    response = await quart_test_client.get(
        f'/api/v1/broadcast/imports/{import_id}/groups?{_query_scope()}',
        headers=_auth_headers(),
    )
    payload = await response.get_json()
    assert response.status_code == 200
    return [item['group_key'] for item in payload['data']['groups']]


async def _insert_group_name(
    fake_broadcast_app,
    *,
    external_conversation_id: str,
    name: str,
) -> None:
    from langbot.pkg.entity.persistence import broadcast as persistence_broadcast

    async with fake_broadcast_app.persistence_mgr.get_db_engine().begin() as conn:
        await fake_broadcast_app.persistence_mgr.execute_async(
            sqlalchemy.insert(persistence_broadcast.BroadcastGroupName).values(
                {
                    'bot_uuid': 'bot-1',
                    'connector_id': 'wxwork-local',
                    'name': name,
                    'external_conversation_id': external_conversation_id,
                }
            ),
            conn=conn,
        )


async def _create_invalid_import_draft(
    fake_broadcast_app,
    *,
    import_id: int,
    template_id: int,
    template_name: str,
    template_content: str,
    group_value: str,
    error_message: str = '未匹配到群聊',
) -> int:
    repository = fake_broadcast_app.broadcast_service.repository
    async with fake_broadcast_app.persistence_mgr.get_db_engine().begin() as conn:
        return await repository.create_draft(
            conn,
            {
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'import_batch_id': import_id,
                'group_value': group_value,
                'target_conversation_name': None,

                'target_conversation_id': None,
                'template_id': template_id,
                'template_name_snapshot': template_name,
                'template_content_snapshot': template_content,
                'render_variables': {},
                'draft_text': '',
                'status': 'invalid',
                'send_status': 'pending',
                'sent_at': None,
                'error_message': error_message,
            },
        )


def _enable_real_send(fake_broadcast_app, connector_id: str = 'wxwork-local') -> None:
    fake_broadcast_app.instance_config.data.setdefault('broadcast', {}).update(
        {
            'send_enabled': '1',
            'allow_send_connectors': {connector_id: True},
        }
    )


class _QueuedRuntimeClient:
    def __init__(self, responses: list[dict[str, object]]) -> None:
        self.responses = list(responses)
        self.requests: list[dict[str, object]] = []

    async def create_task(self, *, request):
        self.requests.append(request)
        if not self.responses:
            raise AssertionError('unexpected runtime send request')
        return self.responses.pop(0)


async def _create_ready_drafts(
    quart_test_client,
    *,
    group_values: list[str],
    conversation_targets: dict[str, tuple[str, str]] | None = None,
    template_content: str = 'Hello {{customer_name}}',
) -> list[dict[str, object]]:
    await quart_test_client.put(
        '/api/v1/broadcast/variable-profile',
        headers=_auth_headers(),
        json={
            'bot_uuid': 'bot-1',
            'connector_id': 'wxwork-local',
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

    for group_value in group_values:
        target_name, target_id = (conversation_targets or {}).get(
            group_value,
            (f'{group_value} Group', f'{group_value} Group'),
        )
        await quart_test_client.post(
            '/api/v1/broadcast/group-rules',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'source_value': group_value,
                'match_type': 'exact',
                'match_expression': group_value,
                'target_conversation_name': target_name,
                'target_conversation_id': target_id,
                'priority': 10,
                'enabled': True,
            },
        )

    upload_response = await quart_test_client.post(
        '/api/v1/broadcast/imports',
        headers=_auth_headers(),
        form={'bot_uuid': 'bot-1', 'connector_id': 'wxwork-local'},
        files={
            'file': FileStorage(
                stream=BytesIO(
                    ('客户名称\n' + '\n'.join(group_values) + '\n').encode('utf-8')
                ),
                filename='customers.csv',
            ),
        },
    )
    import_id = (await upload_response.get_json())['data']['id']

    template_response = await quart_test_client.post(
        '/api/v1/broadcast/templates',
        headers=_auth_headers(),
        json={
            'bot_uuid': 'bot-1',
            'connector_id': 'wxwork-local',
            'name': f'Arrival Reminder {"-".join(group_values)}',
            'content': template_content,
            'enabled': True,
        },
    )
    template_id = (await template_response.get_json())['data']['id']

    await quart_test_client.post(
        f'/api/v1/broadcast/imports/{import_id}/generate-drafts',
        headers=_auth_headers(),
        json={
            'bot_uuid': 'bot-1',
            'connector_id': 'wxwork-local',
            'template_id': template_id,
            'group_keys': await _get_all_import_group_keys(quart_test_client, import_id),
        },
    )

    drafts_response = await quart_test_client.get(
        f'/api/v1/broadcast/drafts?{_query_scope()}&import_batch_id={import_id}',
        headers=_auth_headers(),
    )
    drafts = (await drafts_response.get_json())['data']
    drafts_by_group_value = {draft['group_value']: draft for draft in drafts}
    ordered_drafts = [drafts_by_group_value[group_value] for group_value in group_values]

    await quart_test_client.post(
        '/api/v1/broadcast/drafts/batch-status',
        headers=_auth_headers(),
        json={
            'bot_uuid': 'bot-1',
            'connector_id': 'wxwork-local',
            'draft_ids': [int(draft['id']) for draft in ordered_drafts],
            'status': 'ready',
        },
    )

    refreshed_response = await quart_test_client.get(
        f'/api/v1/broadcast/drafts?{_query_scope()}&import_batch_id={import_id}',
        headers=_auth_headers(),
    )
    refreshed_drafts = (await refreshed_response.get_json())['data']
    refreshed_by_group_value = {draft['group_value']: draft for draft in refreshed_drafts}
    return [refreshed_by_group_value[group_value] for group_value in group_values]


async def _create_send_execution_task_with_attempt(
    quart_test_client,
    fake_broadcast_app,
    *,
    task_status: str,
    response_summary: dict[str, object] | None,
    technical_details: dict[str, object] | None = None,
    send_triggered: bool = False,
    error_code: str | None = None,
    error_message: str | None = None,
) -> int:
    draft = (
        await _create_ready_drafts(
            quart_test_client,
            group_values=['Acme'],
            conversation_targets={'Acme': ('Acme Group', 'acme-group')},
        )
    )[0]
    repository = fake_broadcast_app.broadcast_service.repository
    async with fake_broadcast_app.persistence_mgr.get_db_engine().begin() as conn:
        batch_id = await repository.create_execution_batch(
            conn,
            {
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'channel': 'wxwork_database',
                'mode': 'send',
                'status': 'running',
                'total_tasks': 1,
                'pending_tasks': 0,
                'running_tasks': 1,
                'succeeded_tasks': 0,
                'failed_tasks': 0,
                'cancelled_tasks': 0,
                'interrupted_tasks': 0,
                'created_by': 'tester@example.com',
                'last_action_by': 'tester@example.com',
                'error_message': None,
                'version': 1,
            },
        )
        task_id = await repository.create_execution_task(
            conn,
            {
                'execution_batch_id': batch_id,
                'draft_id': int(draft['id']),
                'draft_text_snapshot': str(draft['draft_text']),
                'target_conversation_snapshot': str(draft['target_conversation_name']),
                'channel': 'wxwork_database',
                'action': 'send_message',
                'status': task_status,
                'sequence_no': 1,
                'attempt_count': 1,
                'max_attempts': 3,
                'idempotency_key': f'broadcast:{batch_id}:1',
                'request_digest': 'fixture-digest',
                'runtime_task_id': 'runtime-fixture',
                'error_code': error_code,
                'error_message': error_message,
                'operator_note': None,
                'finished_at': sqlalchemy.func.now(),
            },
        )
        attempt_id = await repository.create_execution_attempt(
            conn,
            {
                'execution_task_id': task_id,
                'attempt_no': 1,
                'idempotency_key': f'broadcast:{task_id}:1',
                'request_digest': 'fixture-digest',
                'runtime_task_id': 'runtime-fixture',
                'request_summary': json.dumps({'action': 'send_message'}, ensure_ascii=False),
                'response_summary': json.dumps(response_summary, ensure_ascii=False)
                if response_summary is not None
                else None,
                'status': task_status,
                'error_code': error_code,
                'error_message': error_message,
                'finished_at': sqlalchemy.func.now(),
            },
        )
        await repository.create_execution_evidence(
            conn,
            {
                'execution_attempt_id': int(attempt_id),
                'window_title': '企业微信',
                'target_conversation': str(draft['target_conversation_name']),
                'action': 'send_message',
                'input_located': True,
                'draft_written': True,
                'send_triggered': send_triggered,
                'clipboard_restored': True,
                'runtime_state': str((response_summary or {}).get('status') or task_status),
                'evidence_summary': 'fixture',
                'technical_details': json.dumps(technical_details, ensure_ascii=False)
                if technical_details is not None
                else None,
            },
        )
        await repository.recompute_execution_batch_counts(
            batch_id,
            bot_uuid='bot-1',
            connector_id='wxwork-local',
            conn=conn,
        )
    return int(task_id)


@pytest.mark.usefixtures('mock_circular_import_chain')
class TestBroadcastApi:
    @pytest.mark.asyncio
    async def test_group_rule_allows_a_manual_target_name_without_a_stable_id(
        self,
        quart_test_client,
    ):
        response = await quart_test_client.post(
            '/api/v1/broadcast/group-rules',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'source_value': 'Acme',
                'match_type': 'exact',
                'match_expression': 'Acme',
                'target_conversation_name': '  Acme Manual Group  ',
                'target_conversation_id': '',
                'priority': 10,
                'enabled': True,
            },
        )
        payload = await response.get_json()

        assert response.status_code == 200
        assert payload['data']['target_conversation_name'] == 'Acme Manual Group'
        assert payload['data']['target_conversation_id'] is None
        assert payload['data']['target_resolution_status'] == 'deferred'

    @pytest.mark.asyncio
    async def test_group_rule_binds_a_unique_manual_target_name_to_its_stable_id(
        self,
        quart_test_client,
        fake_broadcast_app,
    ):
        await _insert_group_name(
            fake_broadcast_app,
            external_conversation_id='group-acme-manual',
            name='Acme Manual Group',
        )

        response = await quart_test_client.post(
            '/api/v1/broadcast/group-rules',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'source_value': 'Acme',
                'match_type': 'exact',
                'match_expression': 'Acme',
                'target_conversation_name': '  Acme Manual Group  ',
                'target_conversation_id': '',
                'priority': 10,
                'enabled': True,
            },
        )
        payload = await response.get_json()

        assert response.status_code == 200
        assert payload['data']['target_conversation_name'] == 'Acme Manual Group'
        assert payload['data']['target_conversation_id'] is None
        assert payload['data']['target_resolution_status'] == 'deferred'

    @pytest.mark.asyncio
    async def test_group_rule_marks_a_manual_target_name_as_ambiguous_when_multiple_groups_share_it(
        self,
        quart_test_client,
        fake_broadcast_app,
    ):
        await _insert_group_name(
            fake_broadcast_app,
            external_conversation_id='group-acme-1',
            name='Acme Manual Group',
        )
        await _insert_group_name(
            fake_broadcast_app,
            external_conversation_id='group-acme-2',
            name='Acme Manual Group',
        )

        response = await quart_test_client.post(
            '/api/v1/broadcast/group-rules',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'source_value': 'Acme',
                'match_type': 'exact',
                'match_expression': 'Acme',
                'target_conversation_name': 'Acme Manual Group',
                'target_conversation_id': '',
                'priority': 10,
                'enabled': True,
            },
        )
        payload = await response.get_json()

        assert response.status_code == 200
        assert payload['data']['target_conversation_name'] == 'Acme Manual Group'
        assert payload['data']['target_conversation_id'] is None
        assert payload['data']['target_resolution_status'] == 'deferred'

    @pytest.mark.asyncio
    async def test_generate_selected_group_drafts_rejects_unresolved_manual_target_name(
        self,
        quart_test_client,
    ):
        await quart_test_client.put(
            '/api/v1/broadcast/variable-profile',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'group_field': '瀹㈡埛鍚嶇О',
                'mapping_rules': [
                    {
                        'source_field': '瀹㈡埛鍚嶇О',
                        'variable_key': 'customer_name',
                        'merge_mode': 'first',
                        'order': 1,
                    }
                ],
            },
        )
        await quart_test_client.post(
            '/api/v1/broadcast/group-rules',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'source_value': 'Acme',
                'match_type': 'exact',
                'match_expression': 'Acme',
                'target_conversation_name': 'Acme Manual Group',
                'target_conversation_id': '',
                'priority': 10,
                'enabled': True,
            },
        )
        upload_response = await quart_test_client.post(
            '/api/v1/broadcast/imports',
            headers=_auth_headers(),
            form={'bot_uuid': 'bot-1', 'connector_id': 'wxwork-local'},
            files={
                'file': FileStorage(
                    stream=BytesIO('瀹㈡埛鍚嶇О\nAcme\n'.encode('utf-8')),
                    filename='customers.csv',
                ),
            },
        )
        import_id = (await upload_response.get_json())['data']['id']
        template_response = await quart_test_client.post(
            '/api/v1/broadcast/templates',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'name': 'Manual Target Template',
                'content': 'Hello {{customer_name}}',
                'enabled': True,
            },
        )
        template_id = (await template_response.get_json())['data']['id']
        group_key = await _get_import_group_key(
            quart_test_client,
            import_id,
            group_value='Acme',
        )

        generate_response = await quart_test_client.post(
            f'/api/v1/broadcast/imports/{import_id}/generate-drafts',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'group_keys': [group_key],
                'template_id': template_id,
                'overwrite_existing': False,
            },
        )
        payload = await generate_response.get_json()

        assert generate_response.status_code == 200
        assert payload['code'] == 0
        assert int(payload['data']['created_count']) == 1

    @pytest.mark.asyncio
    async def test_generate_selected_group_drafts_rejects_ambiguous_manual_target_name(
        self,
        quart_test_client,
        fake_broadcast_app,
    ):
        await _insert_group_name(
            fake_broadcast_app,
            external_conversation_id='group-acme-1',
            name='Acme Manual Group',
        )
        await _insert_group_name(
            fake_broadcast_app,
            external_conversation_id='group-acme-2',
            name='Acme Manual Group',
        )
        await quart_test_client.put(
            '/api/v1/broadcast/variable-profile',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'group_field': '瀹㈡埛鍚嶇О',
                'mapping_rules': [
                    {
                        'source_field': '瀹㈡埛鍚嶇О',
                        'variable_key': 'customer_name',
                        'merge_mode': 'first',
                        'order': 1,
                    }
                ],
            },
        )
        await quart_test_client.post(
            '/api/v1/broadcast/group-rules',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'source_value': 'Acme',
                'match_type': 'exact',
                'match_expression': 'Acme',
                'target_conversation_name': 'Acme Manual Group',
                'target_conversation_id': '',
                'priority': 10,
                'enabled': True,
            },
        )
        upload_response = await quart_test_client.post(
            '/api/v1/broadcast/imports',
            headers=_auth_headers(),
            form={'bot_uuid': 'bot-1', 'connector_id': 'wxwork-local'},
            files={
                'file': FileStorage(
                    stream=BytesIO('瀹㈡埛鍚嶇О\nAcme\n'.encode('utf-8')),
                    filename='customers.csv',
                ),
            },
        )
        import_id = (await upload_response.get_json())['data']['id']
        template_response = await quart_test_client.post(
            '/api/v1/broadcast/templates',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'name': 'Ambiguous Manual Target Template',
                'content': 'Hello {{customer_name}}',
                'enabled': True,
            },
        )
        template_id = (await template_response.get_json())['data']['id']
        group_key = await _get_import_group_key(
            quart_test_client,
            import_id,
            group_value='Acme',
        )

        generate_response = await quart_test_client.post(
            f'/api/v1/broadcast/imports/{import_id}/generate-drafts',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'group_keys': [group_key],
                'template_id': template_id,
                'overwrite_existing': False,
            },
        )
        payload = await generate_response.get_json()

        assert generate_response.status_code == 200
        assert payload['code'] == 0
        assert int(payload['data']['created_count']) == 1

    @pytest.mark.asyncio
    async def test_variable_profile_get_returns_empty_default(self, quart_test_client):
        response = await quart_test_client.get(
            f'/api/v1/broadcast/variable-profile?{_query_scope()}',
            headers=_auth_headers(),
        )

        assert response.status_code == 200
        payload = await response.get_json()
        assert payload['code'] == 0
        assert payload['data'] == {'group_field': None, 'mapping_rules': []}

    @pytest.mark.asyncio
    async def test_import_group_template_assignments_and_selected_group_generation(
        self,
        quart_test_client,
    ):
        await quart_test_client.put(
            '/api/v1/broadcast/variable-profile',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
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
        await quart_test_client.post(
            '/api/v1/broadcast/group-rules',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'source_value': 'Acme',
                'match_type': 'exact',
                'match_expression': 'Acme',
                'target_conversation_name': 'Acme Group',

                'target_conversation_id': 'Acme Group',
                'priority': 10,
                'enabled': True,
            },
        )
        await quart_test_client.post(
            '/api/v1/broadcast/group-rules',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'source_value': 'Globex',
                'match_type': 'exact',
                'match_expression': 'Globex',
                'target_conversation_name': 'Globex Group',

                'target_conversation_id': 'Globex Group',
                'priority': 9,
                'enabled': True,
            },
        )
        upload_response = await quart_test_client.post(
            '/api/v1/broadcast/imports',
            headers=_auth_headers(),
            form={'bot_uuid': 'bot-1', 'connector_id': 'wxwork-local'},
            files={
                'file': FileStorage(
                    stream=BytesIO('客户名称\nAcme\nGlobex\n'.encode('utf-8')),
                    filename='customers.csv',
                ),
            },
        )
        import_id = (await upload_response.get_json())['data']['id']
        groups_response = await quart_test_client.get(
            f'/api/v1/broadcast/imports/{import_id}/groups?{_query_scope()}',
            headers=_auth_headers(),
        )
        groups_payload = (await groups_response.get_json())['data']
        assert groups_response.status_code == 200
        assert groups_payload['groups'][0]['template_id'] is None

        template_a_response = await quart_test_client.post(
            '/api/v1/broadcast/templates',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'name': 'Template A',
                'content': 'Hello {{customer_name}} from A',
                'enabled': True,
            },
        )
        template_b_response = await quart_test_client.post(
            '/api/v1/broadcast/templates',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'name': 'Template B',
                'content': 'Hello {{customer_name}} from B',
                'enabled': True,
            },
        )
        template_a_id = (await template_a_response.get_json())['data']['id']
        template_b_id = (await template_b_response.get_json())['data']['id']
        group_key_by_value = {
            item['group_value']: item['group_key'] for item in groups_payload['groups']
        }

        assignment_response = await quart_test_client.put(
            f'/api/v1/broadcast/imports/{import_id}/group-template-assignments',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'items': [
                    {
                        'group_key': group_key_by_value['Acme'],
                        'template_id': template_a_id,
                    },
                    {
                        'group_key': group_key_by_value['Globex'],
                        'template_id': template_b_id,
                    },
                ],
            },
        )
        assert assignment_response.status_code == 200

        refreshed_groups_response = await quart_test_client.get(
            f'/api/v1/broadcast/imports/{import_id}/groups?{_query_scope()}',
            headers=_auth_headers(),
        )
        refreshed_groups = (await refreshed_groups_response.get_json())['data']['groups']
        assert {
            item['group_value']: item['template_name'] for item in refreshed_groups
        } == {
            'Acme': 'Template A',
            'Globex': 'Template B',
        }

        generate_response = await quart_test_client.post(
            f'/api/v1/broadcast/imports/{import_id}/generate-drafts',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'group_keys': [group_key_by_value['Globex']],
                'overwrite_existing': False,
            },
        )
        generated_payload = await generate_response.get_json()
        assert generate_response.status_code == 200
        assert generated_payload['data']['created_count'] == 1
        assert generated_payload['data']['updated_count'] == 0
        assert generated_payload['data']['generated_group_keys'] == [
            group_key_by_value['Globex']
        ]

        drafts_response = await quart_test_client.get(
            f'/api/v1/broadcast/drafts?{_query_scope()}&import_batch_id={import_id}',
            headers=_auth_headers(),
        )
        drafts_payload = (await drafts_response.get_json())['data']
        assert [item['group_value'] for item in drafts_payload] == ['Globex']
        assert drafts_payload[0]['template_name_snapshot'] == 'Template B'

    @pytest.mark.asyncio
    async def test_generate_selected_group_drafts_requires_explicit_group_keys(
        self,
        quart_test_client,
    ):
        await quart_test_client.put(
            '/api/v1/broadcast/variable-profile',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
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
        await quart_test_client.post(
            '/api/v1/broadcast/group-rules',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'source_value': 'Acme',
                'match_type': 'exact',
                'match_expression': 'Acme',
                'target_conversation_name': 'Acme Group',

                'target_conversation_id': 'Acme Group',
                'priority': 10,
                'enabled': True,
            },
        )
        upload_response = await quart_test_client.post(
            '/api/v1/broadcast/imports',
            headers=_auth_headers(),
            form={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
            },
            files={
                'file': FileStorage(
                    stream=BytesIO('客户名称\nAcme\n'.encode('utf-8')),
                    filename='customers.csv',
                ),
            },
        )
        import_id = (await upload_response.get_json())['data']['id']
        template_response = await quart_test_client.post(
            '/api/v1/broadcast/templates',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'name': 'Arrival Reminder',
                'content': 'Hello {{customer_name}}',
                'enabled': True,
            },
        )
        template_id = (await template_response.get_json())['data']['id']

        generate_response = await quart_test_client.post(
            f'/api/v1/broadcast/imports/{import_id}/generate-drafts',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'template_id': template_id,
            },
        )
        generate_payload = await generate_response.get_json()
        assert generate_response.status_code == 400
        assert generate_payload['message'] == '请先选择至少一个分组'

        drafts_response = await quart_test_client.get(
            f'/api/v1/broadcast/drafts?{_query_scope()}&import_batch_id={import_id}',
            headers=_auth_headers(),
        )
        drafts_payload = await drafts_response.get_json()
        assert drafts_response.status_code == 200
        assert drafts_payload['data'] == []

    @pytest.mark.asyncio
    async def test_generate_selected_group_drafts_rejects_duplicate_target_conversations(
        self,
        quart_test_client,
    ):
        await quart_test_client.put(
            '/api/v1/broadcast/variable-profile',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
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
        for source_value in ['Acme', 'Globex']:
            await quart_test_client.post(
                '/api/v1/broadcast/group-rules',
                headers=_auth_headers(),
                json={
                    'bot_uuid': 'bot-1',
                    'connector_id': 'wxwork-local',
                    'source_value': source_value,
                    'match_type': 'exact',
                    'match_expression': source_value,
                    'target_conversation_id': 'shared-group-id',
                    'target_conversation_name': 'Shared Group',

                    'target_conversation_id': 'Shared Group',
                    'priority': 10,
                    'enabled': True,
                },
            )
        upload_response = await quart_test_client.post(
            '/api/v1/broadcast/imports',
            headers=_auth_headers(),
            form={'bot_uuid': 'bot-1', 'connector_id': 'wxwork-local'},
            files={
                'file': FileStorage(
                    stream=BytesIO('客户名称\nAcme\nGlobex\n'.encode('utf-8')),
                    filename='customers.csv',
                ),
            },
        )
        import_id = (await upload_response.get_json())['data']['id']
        groups_response = await quart_test_client.get(
            f'/api/v1/broadcast/imports/{import_id}/groups?{_query_scope()}',
            headers=_auth_headers(),
        )
        groups_payload = (await groups_response.get_json())['data']
        template_response = await quart_test_client.post(
            '/api/v1/broadcast/templates',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'name': 'Template A',
                'content': 'Hello {{customer_name}}',
                'enabled': True,
            },
        )
        template_id = (await template_response.get_json())['data']['id']
        await quart_test_client.put(
            f'/api/v1/broadcast/imports/{import_id}/group-template-assignments',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'items': [
                    {
                        'group_key': item['group_key'],
                        'template_id': template_id,
                    }
                    for item in groups_payload['groups']
                ],
            },
        )

        generate_response = await quart_test_client.post(
            f'/api/v1/broadcast/imports/{import_id}/generate-drafts',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'group_keys': [item['group_key'] for item in groups_payload['groups']],
                'overwrite_existing': False,
            },
        )
        generate_payload = await generate_response.get_json()
        assert generate_response.status_code == 200
        assert generate_payload['code'] == 0
        assert generate_payload['data']['pending_review_count'] == 2

        drafts_response = await quart_test_client.get(
            f'/api/v1/broadcast/drafts?{_query_scope()}&import_batch_id={import_id}',
            headers=_auth_headers(),
        )
        drafts_payload = (await drafts_response.get_json())['data']
        assert len(drafts_payload) == 2

        execution_response = await quart_test_client.post(
            '/api/v1/broadcast/executions',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'draft_ids': [item['id'] for item in drafts_payload],
                'mode': 'paste_only',
                'operator': 'tester@example.com',
            },
        )
        execution_payload = await execution_response.get_json()
        assert execution_response.status_code == 409
        assert execution_payload['msg'] == 'DUPLICATE_TARGET_CONVERSATION'

    @pytest.mark.asyncio
    async def test_import_group_template_assignments_support_explicit_clear(
        self,
        quart_test_client,
    ):
        await quart_test_client.put(
            '/api/v1/broadcast/variable-profile',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
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
        await quart_test_client.post(
            '/api/v1/broadcast/group-rules',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'source_value': 'Acme',
                'match_type': 'exact',
                'match_expression': 'Acme',
                'target_conversation_name': 'Acme Group',
                'target_conversation_id': 'acme-group-1',
                'priority': 10,
                'enabled': True,
            },
        )
        upload_response = await quart_test_client.post(
            '/api/v1/broadcast/imports',
            headers=_auth_headers(),
            form={'bot_uuid': 'bot-1', 'connector_id': 'wxwork-local'},
            files={
                'file': FileStorage(
                    stream=BytesIO('客户名称\nAcme\n'.encode('utf-8')),
                    filename='customers.csv',
                ),
            },
        )
        import_id = (await upload_response.get_json())['data']['id']
        group_key = await _get_import_group_key(
            quart_test_client,
            import_id,
            group_value='Acme',
        )
        template_response = await quart_test_client.post(
            '/api/v1/broadcast/templates',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'name': 'Template A',
                'content': 'Hello {{customer_name}}',
                'enabled': True,
            },
        )
        template_id = (await template_response.get_json())['data']['id']

        assign_response = await quart_test_client.put(
            f'/api/v1/broadcast/imports/{import_id}/group-template-assignments',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'items': [{'group_key': group_key, 'template_id': template_id}],
            },
        )
        assert assign_response.status_code == 200

        clear_response = await quart_test_client.put(
            f'/api/v1/broadcast/imports/{import_id}/group-template-assignments',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'items': [{'group_key': group_key, 'template_id': None}],
            },
        )
        clear_payload = await clear_response.get_json()
        assert clear_response.status_code == 200
        assert clear_payload['data']['items'] == [
            {'group_key': group_key, 'template_id': None}
        ]

        groups_response = await quart_test_client.get(
            f'/api/v1/broadcast/imports/{import_id}/groups?{_query_scope()}',
            headers=_auth_headers(),
        )
        groups_payload = (await groups_response.get_json())['data']
        assert groups_payload['groups'][0]['template_id'] is None
        assert groups_payload['groups'][0]['template_name'] is None
        assert groups_payload['groups'][0]['template_enabled'] is None

    @pytest.mark.asyncio
    async def test_import_group_template_assignments_are_atomic_when_any_item_is_invalid(
        self,
        quart_test_client,
    ):
        await quart_test_client.put(
            '/api/v1/broadcast/variable-profile',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
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
        for priority, group_name in enumerate(['Acme', 'Globex'], start=9):
            await quart_test_client.post(
                '/api/v1/broadcast/group-rules',
                headers=_auth_headers(),
                json={
                    'bot_uuid': 'bot-1',
                    'connector_id': 'wxwork-local',
                    'source_value': group_name,
                    'match_type': 'exact',
                    'match_expression': group_name,
                    'target_conversation_name': f'{group_name} Group',
                    'target_conversation_id': f'{group_name.lower()}-group',
                    'priority': priority,
                    'enabled': True,
                },
            )
        upload_response = await quart_test_client.post(
            '/api/v1/broadcast/imports',
            headers=_auth_headers(),
            form={'bot_uuid': 'bot-1', 'connector_id': 'wxwork-local'},
            files={
                'file': FileStorage(
                    stream=BytesIO('客户名称\nAcme\nGlobex\n'.encode('utf-8')),
                    filename='customers.csv',
                ),
            },
        )
        import_id = (await upload_response.get_json())['data']['id']
        group_key_by_value = {
            group_value: await _get_import_group_key(
                quart_test_client,
                import_id,
                group_value=group_value,
            )
            for group_value in ['Acme', 'Globex']
        }
        template_response = await quart_test_client.post(
            '/api/v1/broadcast/templates',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'name': 'Template A',
                'content': 'Hello {{customer_name}}',
                'enabled': True,
            },
        )
        template_id = (await template_response.get_json())['data']['id']
        await quart_test_client.put(
            f'/api/v1/broadcast/imports/{import_id}/group-template-assignments',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'items': [
                    {
                        'group_key': group_key_by_value['Acme'],
                        'template_id': template_id,
                    }
                ],
            },
        )

        response = await quart_test_client.put(
            f'/api/v1/broadcast/imports/{import_id}/group-template-assignments',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'items': [
                    {
                        'group_key': group_key_by_value['Acme'],
                        'template_id': None,
                    },
                    {
                        'group_key': group_key_by_value['Globex'],
                        'template_id': 999999,
                    },
                ],
            },
        )
        payload = await response.get_json()
        assert response.status_code == 404
        assert payload['msg'] == 'BROADCAST_TEMPLATE_NOT_FOUND'

        groups_response = await quart_test_client.get(
            f'/api/v1/broadcast/imports/{import_id}/groups?{_query_scope()}',
            headers=_auth_headers(),
        )
        groups_payload = (await groups_response.get_json())['data']
        group_by_value = {
            item['group_value']: item for item in groups_payload['groups']
        }
        assert group_by_value['Acme']['template_id'] == template_id
        assert group_by_value['Globex']['template_id'] is None

    @pytest.mark.asyncio
    async def test_generate_selected_group_drafts_overwrites_pending_in_place(
        self,
        quart_test_client,
    ):
        await quart_test_client.put(
            '/api/v1/broadcast/variable-profile',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'group_field': '瀹㈡埛鍚嶇О',
                'mapping_rules': [
                    {
                        'source_field': '瀹㈡埛鍚嶇О',
                        'variable_key': 'customer_name',
                        'merge_mode': 'first',
                        'order': 1,
                    }
                ],
            },
        )
        await quart_test_client.post(
            '/api/v1/broadcast/group-rules',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'source_value': 'Acme',
                'match_type': 'exact',
                'match_expression': 'Acme',
                'target_conversation_name': 'Acme Group',
                'target_conversation_id': 'acme-group-1',
                'priority': 10,
                'enabled': True,
            },
        )
        upload_response = await quart_test_client.post(
            '/api/v1/broadcast/imports',
            headers=_auth_headers(),
            form={'bot_uuid': 'bot-1', 'connector_id': 'wxwork-local'},
            files={
                'file': FileStorage(
                    stream=BytesIO('瀹㈡埛鍚嶇О\nAcme\n'.encode('utf-8')),
                    filename='customers.csv',
                ),
            },
        )
        import_id = (await upload_response.get_json())['data']['id']
        template_a_response = await quart_test_client.post(
            '/api/v1/broadcast/templates',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'name': 'Template A',
                'content': 'Hello {{customer_name}} from A',
                'enabled': True,
            },
        )
        template_b_response = await quart_test_client.post(
            '/api/v1/broadcast/templates',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'name': 'Template B',
                'content': 'Hello {{customer_name}} from B',
                'enabled': True,
            },
        )
        template_a_id = (await template_a_response.get_json())['data']['id']
        template_b_id = (await template_b_response.get_json())['data']['id']
        group_key = await _get_import_group_key(quart_test_client, import_id, group_value='Acme')
        await quart_test_client.put(
            f'/api/v1/broadcast/imports/{import_id}/group-template-assignments',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'items': [{'group_key': group_key, 'template_id': template_a_id}],
            },
        )

        first_generate_response = await quart_test_client.post(
            f'/api/v1/broadcast/imports/{import_id}/generate-drafts',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'group_keys': [group_key],
                'overwrite_existing': True,
            },
        )
        first_generate_payload = await first_generate_response.get_json()
        assert first_generate_response.status_code == 200
        assert first_generate_payload['data']['created_count'] == 1
        draft_id = first_generate_payload['data']['draft_ids'][0]

        drafts_response = await quart_test_client.get(
            f'/api/v1/broadcast/drafts?{_query_scope()}&import_batch_id={import_id}',
            headers=_auth_headers(),
        )
        drafts_payload = (await drafts_response.get_json())['data']
        assert drafts_payload[0]['id'] == draft_id
        created_at = drafts_payload[0]['created_at']

        await quart_test_client.put(
            f'/api/v1/broadcast/imports/{import_id}/group-template-assignments',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'items': [{'group_key': group_key, 'template_id': template_b_id}],
            },
        )

        overwrite_response = await quart_test_client.post(
            f'/api/v1/broadcast/imports/{import_id}/generate-drafts',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'group_keys': [group_key],
                'overwrite_existing': True,
            },
        )
        overwrite_payload = await overwrite_response.get_json()
        assert overwrite_response.status_code == 200
        assert overwrite_payload['data']['created_count'] == 0
        assert overwrite_payload['data']['updated_count'] == 1
        assert overwrite_payload['data']['draft_ids'] == [draft_id]
        assert overwrite_payload['data']['draft_results'] == [
            {
                'group_key': group_key,
                'draft_id': draft_id,
                'operation': 'updated',
                'modified_fields': [
                    'template_id',
                    'template_name_snapshot',
                    'template_content_snapshot',
                    'render_variables',
                    'draft_text',
                    'target_conversation_id',
                    'target_conversation_name',
                    'attachment_snapshots',
                    'status',
                    'error_message',
                    'attachments_stale',
                    'updated_at',
                ],
            }
        ]

        refreshed_drafts_response = await quart_test_client.get(
            f'/api/v1/broadcast/drafts?{_query_scope()}&import_batch_id={import_id}',
            headers=_auth_headers(),
        )
        refreshed_drafts = (await refreshed_drafts_response.get_json())['data']
        assert len(refreshed_drafts) == 1
        assert refreshed_drafts[0]['id'] == draft_id
        assert refreshed_drafts[0]['created_at'] == created_at
        assert refreshed_drafts[0]['template_name_snapshot'] == 'Template B'
        assert refreshed_drafts[0]['draft_text'] == 'Hello Acme from B'
        assert refreshed_drafts[0]['send_status'] == 'pending'

    @pytest.mark.asyncio
    async def test_generate_selected_group_drafts_rejects_sent_overwrite_atomically(
        self,
        quart_test_client,
    ):
        await quart_test_client.put(
            '/api/v1/broadcast/variable-profile',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'group_field': '瀹㈡埛鍚嶇О',
                'mapping_rules': [
                    {
                        'source_field': '瀹㈡埛鍚嶇О',
                        'variable_key': 'customer_name',
                        'merge_mode': 'first',
                        'order': 1,
                    }
                ],
            },
        )
        for priority, group_name in enumerate(['Acme', 'Globex'], start=9):
            await quart_test_client.post(
                '/api/v1/broadcast/group-rules',
                headers=_auth_headers(),
                json={
                    'bot_uuid': 'bot-1',
                    'connector_id': 'wxwork-local',
                    'source_value': group_name,
                    'match_type': 'exact',
                    'match_expression': group_name,
                    'target_conversation_name': f'{group_name} Group',
                    'target_conversation_id': f'{group_name.lower()}-group',
                    'priority': priority,
                    'enabled': True,
                },
            )
        upload_response = await quart_test_client.post(
            '/api/v1/broadcast/imports',
            headers=_auth_headers(),
            form={'bot_uuid': 'bot-1', 'connector_id': 'wxwork-local'},
            files={
                'file': FileStorage(
                    stream=BytesIO('瀹㈡埛鍚嶇О\nAcme\nGlobex\n'.encode('utf-8')),
                    filename='customers.csv',
                ),
            },
        )
        import_id = (await upload_response.get_json())['data']['id']
        template_response = await quart_test_client.post(
            '/api/v1/broadcast/templates',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'name': 'Template A',
                'content': 'Hello {{customer_name}}',
                'enabled': True,
            },
        )
        template_id = (await template_response.get_json())['data']['id']
        group_keys = await _get_all_import_group_keys(quart_test_client, import_id)
        await quart_test_client.put(
            f'/api/v1/broadcast/imports/{import_id}/group-template-assignments',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'items': [
                    {'group_key': group_key, 'template_id': template_id}
                    for group_key in group_keys
                ],
            },
        )
        acme_group_key = await _get_import_group_key(quart_test_client, import_id, group_value='Acme')
        first_generate_response = await quart_test_client.post(
            f'/api/v1/broadcast/imports/{import_id}/generate-drafts',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'group_keys': [acme_group_key],
                'overwrite_existing': True,
            },
        )
        first_generate_payload = await first_generate_response.get_json()
        draft_id = first_generate_payload['data']['draft_ids'][0]
        mark_sent_response = await quart_test_client.post(
            '/api/v1/broadcast/drafts/batch-status',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'draft_ids': [draft_id],
                'status': 'sent',
            },
        )
        assert mark_sent_response.status_code == 200

        reject_response = await quart_test_client.post(
            f'/api/v1/broadcast/imports/{import_id}/generate-drafts',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'group_keys': group_keys,
                'overwrite_existing': True,
            },
        )
        reject_payload = await reject_response.get_json()
        assert reject_response.status_code == 400
        assert reject_payload['msg'] == 'BATCH_VALIDATION_FAILED'
        assert reject_payload['message'] == 'Acme: 已发送草稿不允许覆盖，请先恢复为待发送'
        assert reject_payload['details'] == ['Acme: 已发送草稿不允许覆盖，请先恢复为待发送']

        drafts_response = await quart_test_client.get(
            f'/api/v1/broadcast/drafts?{_query_scope()}&import_batch_id={import_id}',
            headers=_auth_headers(),
        )
        drafts_payload = (await drafts_response.get_json())['data']
        assert len(drafts_payload) == 1
        assert drafts_payload[0]['id'] == draft_id
        assert drafts_payload[0]['send_status'] == 'sent'

    @pytest.mark.asyncio
    async def test_generate_selected_group_drafts_supports_mixed_create_and_update(
        self,
        quart_test_client,
    ):
        await quart_test_client.put(
            '/api/v1/broadcast/variable-profile',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'group_field': '瀹㈡埛鍚嶇О',
                'mapping_rules': [
                    {
                        'source_field': '瀹㈡埛鍚嶇О',
                        'variable_key': 'customer_name',
                        'merge_mode': 'first',
                        'order': 1,
                    }
                ],
            },
        )
        for priority, group_name in enumerate(['Acme', 'Globex', 'Northwind'], start=8):
            await quart_test_client.post(
                '/api/v1/broadcast/group-rules',
                headers=_auth_headers(),
                json={
                    'bot_uuid': 'bot-1',
                    'connector_id': 'wxwork-local',
                    'source_value': group_name,
                    'match_type': 'exact',
                    'match_expression': group_name,
                    'target_conversation_name': f'{group_name} Group',
                    'target_conversation_id': f'{group_name.lower()}-group',
                    'priority': priority,
                    'enabled': True,
                },
            )
        upload_response = await quart_test_client.post(
            '/api/v1/broadcast/imports',
            headers=_auth_headers(),
            form={'bot_uuid': 'bot-1', 'connector_id': 'wxwork-local'},
            files={
                'file': FileStorage(
                    stream=BytesIO('瀹㈡埛鍚嶇О\nAcme\nGlobex\nNorthwind\n'.encode('utf-8')),
                    filename='customers.csv',
                ),
            },
        )
        import_id = (await upload_response.get_json())['data']['id']
        template_a_response = await quart_test_client.post(
            '/api/v1/broadcast/templates',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'name': 'Template A',
                'content': 'Hello {{customer_name}} from A',
                'enabled': True,
            },
        )
        template_b_response = await quart_test_client.post(
            '/api/v1/broadcast/templates',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'name': 'Template B',
                'content': 'Hello {{customer_name}} from B',
                'enabled': True,
            },
        )
        template_a_id = (await template_a_response.get_json())['data']['id']
        template_b_id = (await template_b_response.get_json())['data']['id']
        group_key_by_value = {
            group_value: await _get_import_group_key(quart_test_client, import_id, group_value=group_value)
            for group_value in ['Acme', 'Globex', 'Northwind']
        }
        await quart_test_client.put(
            f'/api/v1/broadcast/imports/{import_id}/group-template-assignments',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'items': [
                    {'group_key': group_key, 'template_id': template_a_id}
                    for group_key in group_key_by_value.values()
                ],
            },
        )
        first_generate_response = await quart_test_client.post(
            f'/api/v1/broadcast/imports/{import_id}/generate-drafts',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'group_keys': [
                    group_key_by_value['Acme'],
                    group_key_by_value['Northwind'],
                ],
                'overwrite_existing': True,
            },
        )
        first_generate_payload = await first_generate_response.get_json()
        original_draft_ids = {
            item['group_key']: item['draft_id']
            for item in first_generate_payload['data']['draft_results']
        }
        drafts_before_response = await quart_test_client.get(
            f'/api/v1/broadcast/drafts?{_query_scope()}&import_batch_id={import_id}',
            headers=_auth_headers(),
        )
        drafts_before = (await drafts_before_response.get_json())['data']
        northwind_before = next(item for item in drafts_before if item['group_value'] == 'Northwind')

        await quart_test_client.put(
            f'/api/v1/broadcast/imports/{import_id}/group-template-assignments',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'items': [
                    {'group_key': group_key_by_value['Acme'], 'template_id': template_b_id},
                    {'group_key': group_key_by_value['Globex'], 'template_id': template_b_id},
                ],
            },
        )
        second_generate_response = await quart_test_client.post(
            f'/api/v1/broadcast/imports/{import_id}/generate-drafts',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'group_keys': [
                    group_key_by_value['Acme'],
                    group_key_by_value['Globex'],
                ],
                'overwrite_existing': True,
            },
        )
        second_generate_payload = await second_generate_response.get_json()
        assert second_generate_response.status_code == 200
        assert second_generate_payload['data']['created_count'] == 1
        assert second_generate_payload['data']['updated_count'] == 1
        assert second_generate_payload['data']['draft_results'][0]['operation'] == 'updated'
        assert second_generate_payload['data']['draft_results'][1]['operation'] == 'created'

        drafts_after_response = await quart_test_client.get(
            f'/api/v1/broadcast/drafts?{_query_scope()}&import_batch_id={import_id}',
            headers=_auth_headers(),
        )
        drafts_after = (await drafts_after_response.get_json())['data']
        assert len(drafts_after) == 3
        draft_by_group = {item['group_value']: item for item in drafts_after}
        assert draft_by_group['Acme']['id'] == original_draft_ids[group_key_by_value['Acme']]
        assert draft_by_group['Acme']['template_name_snapshot'] == 'Template B'
        assert draft_by_group['Globex']['template_name_snapshot'] == 'Template B'
        assert draft_by_group['Northwind']['id'] == original_draft_ids[group_key_by_value['Northwind']]
        assert draft_by_group['Northwind']['draft_text'] == northwind_before['draft_text']

    @pytest.mark.asyncio
    async def test_template_crud_and_render_validation(self, quart_test_client):
        invalid_response = await quart_test_client.post(
            '/api/v1/broadcast/templates/render',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'variables': {},
            },
        )
        invalid_payload = await invalid_response.get_json()
        assert invalid_response.status_code == 400
        assert invalid_payload['msg'] == 'TEMPLATE_RENDER_INPUT_INVALID'

        create_response = await quart_test_client.post(
            '/api/v1/broadcast/templates',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'name': 'Arrival Reminder',
                'content': 'Hello {{customer_name}}, order {{order_no}}',
                'enabled': True,
            },
        )
        assert create_response.status_code == 200
        created = (await create_response.get_json())['data']
        assert created['variables'] == ['customer_name', 'order_no']

        duplicate_response = await quart_test_client.post(
            '/api/v1/broadcast/templates',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'name': 'Arrival Reminder',
                'content': 'Duplicate',
                'enabled': False,
            },
        )
        duplicate_payload = await duplicate_response.get_json()
        assert duplicate_response.status_code == 409
        assert duplicate_payload['msg'] == 'BROADCAST_TEMPLATE_NAME_DUPLICATE'

        list_response = await quart_test_client.get(
            f'/api/v1/broadcast/templates?{_query_scope()}',
            headers=_auth_headers(),
        )
        listed = (await list_response.get_json())['data']
        assert [item['name'] for item in listed] == ['Arrival Reminder']

        render_response = await quart_test_client.post(
            '/api/v1/broadcast/templates/render',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'template_id': created['id'],
                'variables': {
                    'customer_name': 'Acme',
                },
            },
        )
        render_payload = (await render_response.get_json())['data']
        assert render_payload['missing_variables'] == ['order_no']
        assert render_payload['valid'] is False

        update_response = await quart_test_client.put(
            f"/api/v1/broadcast/templates/{created['id']}",
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'name': 'Arrival Reminder V2',
                'content': 'Hi {{customer_name}}',
                'enabled': False,
            },
        )
        updated = (await update_response.get_json())['data']
        assert updated['name'] == 'Arrival Reminder V2'
        assert updated['enabled'] is False

        scoped_delete_response = await quart_test_client.delete(
            f"/api/v1/broadcast/templates/{created['id']}?{_query_scope(bot_uuid='bot-2', connector_id='wxwork-other')}",
            headers=_auth_headers(),
        )
        scoped_delete_payload = await scoped_delete_response.get_json()
        assert scoped_delete_response.status_code == 404
        assert scoped_delete_payload['msg'] == 'BROADCAST_TEMPLATE_NOT_FOUND'

        delete_response = await quart_test_client.delete(
            f"/api/v1/broadcast/templates/{created['id']}?{_query_scope()}",
            headers=_auth_headers(),
        )
        assert delete_response.status_code == 200

    @pytest.mark.asyncio
    async def test_variable_profile_group_rules_group_names_and_scope_isolation(self, quart_test_client):
        profile_response = await quart_test_client.put(
            '/api/v1/broadcast/variable-profile',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'group_field': 'customer_name',
                'mapping_rules': [
                    {
                        'source_field': 'Customer Name',
                        'variable_key': 'customer_name',
                        'merge_mode': 'first',
                        'order': 1,
                    }
                ],
            },
        )
        profile_payload = (await profile_response.get_json())['data']
        assert profile_payload['group_field'] == 'customer_name'
        assert profile_payload['mapping_rules'] == [
            {
                'source_field': 'Customer Name',
                'variable_key': 'customer_name',
                'merge_mode': 'first',
                'order': 1,
            }
        ]

        profile_read_response = await quart_test_client.get(
            f'/api/v1/broadcast/variable-profile?{_query_scope()}',
            headers=_auth_headers(),
        )
        profile_read_payload = (await profile_read_response.get_json())['data']
        assert profile_read_payload == profile_payload

        invalid_profile_response = await quart_test_client.put(
            '/api/v1/broadcast/variable-profile',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'group_field': 'customer_name',
                'mapping_rules': [
                    {
                        'source_field': 'Customer Name',
                        'variable_key': 'customer_name',
                        'merge_mode': 'bad-mode',
                        'order': 1,
                    }
                ],
            },
        )
        invalid_profile_payload = await invalid_profile_response.get_json()
        assert invalid_profile_response.status_code == 400
        assert invalid_profile_payload['msg'] == 'BROADCAST_VARIABLE_PROFILE_INVALID'
        assert invalid_profile_payload['message']
        assert invalid_profile_payload['details']

        actionable_profile_response = await quart_test_client.put(
            '/api/v1/broadcast/variable-profile',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'group_field': '',
                'mapping_rules': [
                    {
                        'source_field': '客户名称',
                        'variable_key': '',
                        'merge_mode': 'first',
                        'order': 1,
                    },
                    {
                        'source_field': '{{客户名称}}',
                        'variable_key': 'customer_name',
                        'merge_mode': 'first',
                        'order': 2,
                    },
                ],
            },
        )
        actionable_profile_payload = await actionable_profile_response.get_json()
        assert actionable_profile_response.status_code == 400
        assert actionable_profile_payload['msg'] == 'BROADCAST_VARIABLE_PROFILE_INVALID'
        assert actionable_profile_payload['message']
        assert actionable_profile_payload['details'] == [
            '请填写分组字段',
            '第 1 条规则缺少消息变量',
            '请填写“客户名称”，不要填写“{{客户名称}}”',
        ]

        create_rule_response = await quart_test_client.post(
            '/api/v1/broadcast/group-rules',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'source_value': 'Acme',
                'match_type': 'exact',
                'match_expression': 'Acme',
                'target_conversation_name': 'Acme Primary',

                'target_conversation_id': 'Acme Primary',
                'priority': 10,
                'enabled': True,
            },
        )
        high_rule = (await create_rule_response.get_json())['data']

        await quart_test_client.post(
            '/api/v1/broadcast/group-rules',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'source_value': 'Acme',
                'match_type': 'contains',
                'match_expression': 'Acme',
                'target_conversation_name': 'Acme Backup',

                'target_conversation_id': 'Acme Backup',
                'priority': 1,
                'enabled': True,
            },
        )

        invalid_rule_response = await quart_test_client.post(
            '/api/v1/broadcast/group-rules',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'source_value': 'Acme',
                'match_type': 'regex',
                'match_expression': '[',
                'target_conversation_name': 'Broken Regex',

                'target_conversation_id': 'Broken Regex',
                'priority': 1,
                'enabled': True,
            },
        )
        invalid_rule_payload = await invalid_rule_response.get_json()
        assert invalid_rule_response.status_code == 400
        assert invalid_rule_payload['msg'] == 'BROADCAST_GROUP_RULE_REGEX_INVALID'

        match_response = await quart_test_client.post(
            '/api/v1/broadcast/group-rules/match',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'source_value': 'Acme',
            },
        )
        match_payload = (await match_response.get_json())['data']
        assert match_payload['matched'] is True
        assert match_payload['rule_id'] == high_rule['id']

        list_rules_response = await quart_test_client.get(
            f'/api/v1/broadcast/group-rules?{_query_scope()}',
            headers=_auth_headers(),
        )
        list_rules_payload = (await list_rules_response.get_json())['data']
        assert len(list_rules_payload) == 2
        assert list_rules_payload[0]['id'] == high_rule['id']

        update_rule_response = await quart_test_client.put(
            f"/api/v1/broadcast/group-rules/{high_rule['id']}",
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'source_value': 'Acme',
                'match_type': 'exact',
                'match_expression': 'Acme',
                'target_conversation_name': 'Acme Primary',

                'target_conversation_id': 'Acme Primary',
                'priority': 10,
                'enabled': False,
            },
        )
        updated_rule = (await update_rule_response.get_json())['data']
        assert updated_rule['enabled'] is False

        create_names_response = await quart_test_client.post(
            '/api/v1/broadcast/group-names',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'names': [' Acme Group ', 'Acme Group', 'Northwind Group'],
            },
        )
        create_names_payload = (await create_names_response.get_json())['data']
        assert [item['name'] for item in create_names_payload['group_names']] == [
            'Acme Group',
            'Northwind Group',
        ]

        duplicate_name_response = await quart_test_client.post(
            '/api/v1/broadcast/group-names',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'name': 'Acme Group',
            },
        )
        duplicate_name_payload = await duplicate_name_response.get_json()
        assert duplicate_name_response.status_code == 409
        assert duplicate_name_payload['msg'] == 'BROADCAST_GROUP_NAME_DUPLICATE'

        sync_names_response = await quart_test_client.post(
            f'/api/v1/broadcast/group-names/sync?{_query_scope()}',
            headers=_auth_headers(),
        )
        sync_names_payload = await sync_names_response.get_json()
        assert sync_names_response.status_code == 200
        assert sync_names_payload['data'] == {
            'scanned': 1,
            'inserted': 1,
            'updated': 0,
            'unchanged': 0,
            'skipped': 1,
            'errors': [],
        }

        synced_names_response = await quart_test_client.get(
            f'/api/v1/broadcast/group-names?{_query_scope()}',
            headers=_auth_headers(),
        )
        synced_names_payload = (await synced_names_response.get_json())['data']
        assert [item['name'] for item in synced_names_payload] == [
            'Acme Group',
            'Northwind Group',
            '小满',
        ]
        assert next(
            item for item in synced_names_payload if item['name'] == '小满'
        )['external_conversation_id'] == 'group-1'

        list_names_response = await quart_test_client.get(
            f'/api/v1/broadcast/group-names?{_query_scope()}',
            headers=_auth_headers(),
        )
        list_names_payload = (await list_names_response.get_json())['data']
        assert [item['name'] for item in list_names_payload] == [
            'Acme Group',
            'Northwind Group',
            '小满',
        ]

        delete_name_wrong_scope = await quart_test_client.delete(
            f"/api/v1/broadcast/group-names/{list_names_payload[0]['id']}?{_query_scope(bot_uuid='bot-2', connector_id='wxwork-other')}",
            headers=_auth_headers(),
        )
        wrong_scope_payload = await delete_name_wrong_scope.get_json()
        assert delete_name_wrong_scope.status_code == 404
        assert wrong_scope_payload['msg'] == 'BROADCAST_GROUP_NAME_NOT_FOUND'

    @pytest.mark.asyncio
    async def test_import_upload_persists_first_match_results_and_detail_refresh(self, quart_test_client):
        await quart_test_client.put(
            '/api/v1/broadcast/variable-profile',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
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
        await quart_test_client.post(
            '/api/v1/broadcast/group-rules',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'source_value': 'Acme',
                'match_type': 'exact',
                'match_expression': 'Acme',
                'target_conversation_name': 'Acme Group',

                'target_conversation_id': 'Acme Group',
                'priority': 10,
                'enabled': True,
            },
        )
        await quart_test_client.post(
            '/api/v1/broadcast/group-rules',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'source_value': 'North',
                'match_type': 'contains',
                'match_expression': 'North',
                'target_conversation_name': 'Disabled Group',

                'target_conversation_id': 'Disabled Group',
                'priority': 99,
                'enabled': False,
            },
        )
        await quart_test_client.post(
            '/api/v1/broadcast/group-names',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'names': ['Northwind Team'],
            },
        )

        upload_response = await quart_test_client.post(
            '/api/v1/broadcast/imports',
            headers=_auth_headers(),
            form={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
            },
            files={
                'file': FileStorage(
                    stream=BytesIO(
                        (
                            '客户名称,订单号\n'
                            'Acme,SO-001\n'
                            'Northwind Team,SO-002\n'
                            '   ,SO-003\n'
                        ).encode('utf-8')
                    ),
                    filename='customers.csv',
                ),
            },
        )
        upload_payload = await upload_response.get_json()

        assert upload_response.status_code == 200
        assert upload_payload['data']['matched_rows'] == 1
        assert upload_payload['data']['unmatched_rows'] == 1
        assert upload_payload['data']['invalid_rows'] == 1
        assert 'rows' not in upload_payload['data']
        assert (
            upload_payload['data']['matched_rows']
            + upload_payload['data']['unmatched_rows']
            + upload_payload['data']['invalid_rows']
            == upload_payload['data']['total_rows']
        )

        import_id = upload_payload['data']['id']
        list_response = await quart_test_client.get(
            f'/api/v1/broadcast/imports?{_query_scope()}',
            headers=_auth_headers(),
        )
        list_payload = await list_response.get_json()
        assert [item['id'] for item in list_payload['data']] == [import_id]

        detail_response = await quart_test_client.get(
            f'/api/v1/broadcast/imports/{import_id}?{_query_scope()}',
            headers=_auth_headers(),
        )
        detail_payload = await detail_response.get_json()
        assert detail_payload['data']['page'] == 1
        assert detail_payload['data']['page_size'] == 50
        assert detail_payload['data']['total'] == 3
        assert detail_payload['data']['total_pages'] == 1
        assert [row['match_status'] for row in detail_payload['data']['rows']] == ['matched', 'unmatched', 'invalid']
        assert detail_payload['data']['rows'][0]['matched_conversation_name'] == 'Acme Group'
        assert detail_payload['data']['rows'][1]['matched_conversation_name'] is None
        assert detail_payload['data']['rows'][1]['matched_rule_id'] is None

        second_page_response = await quart_test_client.get(
            f'/api/v1/broadcast/imports/{import_id}?{_query_scope()}&page=2&page_size=2',
            headers=_auth_headers(),
        )
        second_page_payload = await second_page_response.get_json()
        assert second_page_payload['data']['page'] == 2
        assert second_page_payload['data']['page_size'] == 2
        assert second_page_payload['data']['total'] == 3
        assert second_page_payload['data']['total_pages'] == 2
        assert [row['source_row_number'] for row in second_page_payload['data']['rows']] == [4]

    @pytest.mark.asyncio
    async def test_import_upload_persists_auto_detected_batch_group_field(
        self,
        quart_test_client,
    ):
        group_field = '\u5ba2\u6237\u540d\u79f0'
        order_field = '\u8ba2\u5355\u53f7'
        username_field = '\u7528\u6237\u540d'
        await quart_test_client.put(
            '/api/v1/broadcast/variable-profile',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'group_field': group_field,
                'mapping_rules': [
                    {
                        'source_field': order_field,
                        'variable_key': 'order_no',
                        'merge_mode': 'first',
                        'order': 1,
                    }
                ],
            },
        )
        await quart_test_client.post(
            '/api/v1/broadcast/group-rules',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'source_value': 'legacy-acme',
                'match_type': 'exact',
                'match_expression': 'legacy-acme',
                'target_conversation_name': 'Acme Group',
                'target_conversation_id': 'acme-group-1',
                'priority': 10,
                'enabled': True,
            },
        )

        response = await quart_test_client.post(
            '/api/v1/broadcast/imports',
            headers=_auth_headers(),
            form={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
            },
            files={
                'file': FileStorage(
                    stream=BytesIO(f'{username_field},{order_field}\nlegacy-acme,SO-001\n'.encode('utf-8')),
                    filename='customers.csv',
                ),
            },
        )
        payload = await response.get_json()

        assert response.status_code == 200
        assert payload['data']['group_field_used'] == username_field
        assert payload['data']['group_field_source'] == 'auto_detected'

        import_id = payload['data']['id']
        detail_response = await quart_test_client.get(
            f'/api/v1/broadcast/imports/{import_id}?{_query_scope()}',
            headers=_auth_headers(),
        )
        detail_payload = await detail_response.get_json()
        assert detail_response.status_code == 200
        assert detail_payload['data']['rows'][0]['group_value'] == 'legacy-acme'
        assert detail_payload['data']['rows'][0]['match_status'] == 'matched'

    @pytest.mark.asyncio
    async def test_import_upload_returns_object_details_when_group_field_confirmation_is_required(
        self,
        quart_test_client,
    ):
        await quart_test_client.put(
            '/api/v1/broadcast/variable-profile',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'group_field': '客户',
                'mapping_rules': [
                    {
                        'source_field': '运单号',
                        'variable_key': 'tracking_no',
                        'merge_mode': 'first',
                        'order': 1,
                    }
                ],
            },
        )

        response = await quart_test_client.post(
            '/api/v1/broadcast/imports',
            headers=_auth_headers(),
            form={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
            },
            files={
                'file': FileStorage(
                    stream=BytesIO('运单号,联系人手机号\nSO-001,13800138000\n'.encode('utf-8')),
                    filename='customers.csv',
                ),
            },
        )
        payload = await response.get_json()

        assert response.status_code == 400
        assert payload['msg'] == 'BROADCAST_IMPORT_GROUP_FIELD_CONFIRMATION_REQUIRED'
        assert isinstance(payload['details'], dict)
        assert payload['details'] == {
            'headers': ['运单号', '联系人手机号'],
            'candidates': [],
            'configured_group_field': '客户',
            'original_file_name': 'customers.csv',
        }

    @pytest.mark.asyncio
    async def test_import_upload_returns_object_details_when_group_field_override_is_invalid(
        self,
        quart_test_client,
    ):
        await quart_test_client.put(
            '/api/v1/broadcast/variable-profile',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'group_field': '客户名称',
                'mapping_rules': [
                    {
                        'source_field': '运单号',
                        'variable_key': 'tracking_no',
                        'merge_mode': 'first',
                        'order': 1,
                    }
                ],
            },
        )

        response = await quart_test_client.post(
            '/api/v1/broadcast/imports',
            headers=_auth_headers(),
            form={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'group_field_override': '用户名',
            },
            files={
                'file': FileStorage(
                    stream=BytesIO('客户名称,运单号\nAcme,SO-001\n'.encode('utf-8')),
                    filename='customers.csv',
                ),
            },
        )
        payload = await response.get_json()

        assert response.status_code == 400
        assert payload['msg'] == 'BROADCAST_IMPORT_GROUP_FIELD_OVERRIDE_INVALID'
        assert isinstance(payload['details'], dict)
        assert payload['details'] == {
            'group_field_override': '用户名',
            'headers': ['客户名称', '运单号'],
            'original_file_name': 'customers.csv',
        }



    @pytest.mark.asyncio
    async def test_import_upload_requires_group_field_confirmation_for_ambiguous_alias_headers(
        self,
        quart_test_client,
    ):
        await quart_test_client.put(
            '/api/v1/broadcast/variable-profile',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'group_field': '历史客户字段',
                'mapping_rules': [
                    {
                        'source_field': '订单号',
                        'variable_key': 'order_no',
                        'merge_mode': 'first',
                        'order': 1,
                    }
                ],
            },
        )

        response = await quart_test_client.post(
            '/api/v1/broadcast/imports',
            headers=_auth_headers(),
            form={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
            },
            files={
                'file': FileStorage(
                    stream=BytesIO('客户,姓名,订单号\nAcme,张三,SO-001\n'.encode('utf-8')),
                    filename='customers.csv',
                ),
            },
        )
        payload = await response.get_json()

        assert response.status_code == 400
        assert payload['msg'] == 'BROADCAST_IMPORT_GROUP_FIELD_CONFIRMATION_REQUIRED'
        assert isinstance(payload['details'], dict)
        assert payload['details']['headers'] == ['客户', '姓名', '订单号']
        assert payload['details']['candidates'] == ['客户', '姓名']
        assert payload['details']['configured_group_field'] == '历史客户字段'
        assert payload['details']['original_file_name'] == 'customers.csv'


    @pytest.mark.asyncio
    async def test_import_upload_requires_group_field_confirmation_when_no_candidate_header_matches(
        self,
        quart_test_client,
    ):
        await quart_test_client.put(
            '/api/v1/broadcast/variable-profile',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'group_field': '历史客户字段',
                'mapping_rules': [
                    {
                        'source_field': '订单号',
                        'variable_key': 'order_no',
                        'merge_mode': 'first',
                        'order': 1,
                    }
                ],
            },
        )

        response = await quart_test_client.post(
            '/api/v1/broadcast/imports',
            headers=_auth_headers(),
            form={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
            },
            files={
                'file': FileStorage(
                    stream=BytesIO('订单号,联系人手机号\nSO-001,13800000000\n'.encode('utf-8')),
                    filename='customers.csv',
                ),
            },
        )
        payload = await response.get_json()

        assert response.status_code == 400
        assert payload['msg'] == 'BROADCAST_IMPORT_GROUP_FIELD_CONFIRMATION_REQUIRED'
        assert isinstance(payload['details'], dict)
        assert payload['details']['headers'] == ['订单号', '联系人手机号']
        assert payload['details']['candidates'] == []
        assert payload['details']['configured_group_field'] == '历史客户字段'
        assert payload['details']['original_file_name'] == 'customers.csv'


    @pytest.mark.asyncio
    async def test_import_upload_rejects_invalid_group_field_override_with_structured_details(
        self,
        quart_test_client,
    ):
        await quart_test_client.put(
            '/api/v1/broadcast/variable-profile',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'group_field': '客户名称',
                'mapping_rules': [
                    {
                        'source_field': '订单号',
                        'variable_key': 'order_no',
                        'merge_mode': 'first',
                        'order': 1,
                    }
                ],
            },
        )

        response = await quart_test_client.post(
            '/api/v1/broadcast/imports',
            headers=_auth_headers(),
            form={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'group_field_override': '用户名',
            },
            files={
                'file': FileStorage(
                    stream=BytesIO('客户名称,订单号\nAcme,SO-001\n'.encode('utf-8')),
                    filename='customers.csv',
                ),
            },
        )
        payload = await response.get_json()

        assert response.status_code == 400
        assert payload['msg'] == 'BROADCAST_IMPORT_GROUP_FIELD_OVERRIDE_INVALID'
        assert isinstance(payload['details'], dict)
        assert payload['details']['group_field_override'] == '用户名'
        assert payload['details']['headers'] == ['客户名称', '订单号']
        assert payload['details']['original_file_name'] == 'customers.csv'


    @pytest.mark.asyncio
    async def test_import_rematch_uses_persisted_batch_group_field_after_profile_change(
        self,
        quart_test_client,
    ):
        group_field = '\u5ba2\u6237\u540d\u79f0'
        username_field = '\u7528\u6237\u540d'
        await quart_test_client.put(
            '/api/v1/broadcast/variable-profile',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'group_field': group_field,
                'mapping_rules': [
                    {
                        'source_field': group_field,
                        'variable_key': 'customer_name',
                        'merge_mode': 'first',
                        'order': 1,
                    }
                ],
            },
        )
        await quart_test_client.post(
            '/api/v1/broadcast/group-rules',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'source_value': 'legacy-acme',
                'match_type': 'exact',
                'match_expression': 'legacy-acme',
                'target_conversation_name': 'Acme Group',
                'target_conversation_id': 'acme-group-1',
                'priority': 10,
                'enabled': True,
            },
        )
        upload_response = await quart_test_client.post(
            '/api/v1/broadcast/imports',
            headers=_auth_headers(),
            form={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
            },
            files={
                'file': FileStorage(
                    stream=BytesIO(f'{username_field},{group_field}\nlegacy-acme,Acme\n'.encode('utf-8')),
                    filename='customers.csv',
                ),
            },
        )
        upload_payload = await upload_response.get_json()
        assert upload_response.status_code == 200
        assert upload_payload['data']['group_field_used'] == username_field
        import_id = upload_payload['data']['id']

        await quart_test_client.put(
            '/api/v1/broadcast/variable-profile',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'group_field': group_field,
                'mapping_rules': [
                    {
                        'source_field': group_field,
                        'variable_key': 'customer_name',
                        'merge_mode': 'first',
                        'order': 1,
                    }
                ],
            },
        )

        rematch_response = await quart_test_client.post(
            f'/api/v1/broadcast/imports/{import_id}/rematch',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
            },
        )
        rematch_payload = await rematch_response.get_json()

        assert rematch_response.status_code == 200
        assert rematch_payload['data']['group_field_used'] == username_field
        assert rematch_payload['data']['group_field_source'] == 'auto_detected'
        assert rematch_payload['data']['rows'][0]['group_value'] == 'legacy-acme'
        assert rematch_payload['data']['rows'][0]['match_status'] == 'matched'


    @pytest.mark.asyncio
    async def test_import_rematch_blocks_legacy_unresolvable_batch(
        self,
        quart_test_client,
        fake_broadcast_app,
    ):
        from langbot.pkg.entity.persistence import broadcast as persistence_broadcast

        group_field = '\u5ba2\u6237\u540d\u79f0'
        await quart_test_client.put(
            '/api/v1/broadcast/variable-profile',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'group_field': group_field,
                'mapping_rules': [
                    {
                        'source_field': group_field,
                        'variable_key': 'customer_name',
                        'merge_mode': 'first',
                        'order': 1,
                    }
                ],
            },
        )
        upload_response = await quart_test_client.post(
            '/api/v1/broadcast/imports',
            headers=_auth_headers(),
            form={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
            },
            files={
                'file': FileStorage(
                    stream=BytesIO(f'{group_field}\nAcme\n'.encode('utf-8')),
                    filename='customers.csv',
                ),
            },
        )
        assert upload_response.status_code == 200
        import_id = (await upload_response.get_json())['data']['id']

        async with fake_broadcast_app.persistence_mgr.get_db_engine().begin() as conn:
            await fake_broadcast_app.persistence_mgr.execute_async(
                sqlalchemy.update(persistence_broadcast.BroadcastImportBatch)
                .where(persistence_broadcast.BroadcastImportBatch.id == import_id)
                .values({'group_field_used': None, 'group_field_source': None}),
                conn=conn,
            )
            await fake_broadcast_app.persistence_mgr.execute_async(
                sqlalchemy.update(persistence_broadcast.BroadcastVariableProfile)
                .where(
                    persistence_broadcast.BroadcastVariableProfile.bot_uuid == 'bot-1',
                    persistence_broadcast.BroadcastVariableProfile.connector_id == 'wxwork-local',
                )
                .values({'group_field': None}),
                conn=conn,
            )

        rematch_response = await quart_test_client.post(
            f'/api/v1/broadcast/imports/{import_id}/rematch',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
            },
        )
        rematch_payload = await rematch_response.get_json()

        assert rematch_response.status_code == 400
        assert rematch_payload['msg'] == 'BROADCAST_IMPORT_GROUP_FIELD_UNRESOLVABLE'

        detail_response = await quart_test_client.get(
            f'/api/v1/broadcast/imports/{import_id}?{_query_scope()}',
            headers=_auth_headers(),
        )
        detail_payload = await detail_response.get_json()
        assert detail_response.status_code == 200
        assert detail_payload['data']['group_field_used'] is None
        assert detail_payload['data']['group_field_source'] is None


    @pytest.mark.asyncio
    async def test_import_rematch_returns_runtime_legacy_fallback_metadata_without_persisting_batch(
        self,
        quart_test_client,
        fake_broadcast_app,
    ):
        from langbot.pkg.entity.persistence import broadcast as persistence_broadcast

        group_field = '客户名称'
        await quart_test_client.put(
            '/api/v1/broadcast/variable-profile',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'group_field': group_field,
                'mapping_rules': [
                    {
                        'source_field': group_field,
                        'variable_key': 'customer_name',
                        'merge_mode': 'first',
                        'order': 1,
                    }
                ],
            },
        )
        await quart_test_client.post(
            '/api/v1/broadcast/group-rules',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'source_value': 'Acme',
                'match_type': 'exact',
                'match_expression': 'Acme',
                'target_conversation_name': 'Acme Group',
                'target_conversation_id': 'acme-group-1',
                'priority': 10,
                'enabled': True,
            },
        )
        upload_response = await quart_test_client.post(
            '/api/v1/broadcast/imports',
            headers=_auth_headers(),
            form={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
            },
            files={
                'file': FileStorage(
                    stream=BytesIO(f'{group_field}\nAcme\n'.encode('utf-8')),
                    filename='customers.csv',
                ),
            },
        )
        assert upload_response.status_code == 200
        import_id = (await upload_response.get_json())['data']['id']

        async with fake_broadcast_app.persistence_mgr.get_db_engine().begin() as conn:
            await fake_broadcast_app.persistence_mgr.execute_async(
                sqlalchemy.update(persistence_broadcast.BroadcastImportBatch)
                .where(persistence_broadcast.BroadcastImportBatch.id == import_id)
                .values({'group_field_used': None, 'group_field_source': None}),
                conn=conn,
            )

        rematch_response = await quart_test_client.post(
            f'/api/v1/broadcast/imports/{import_id}/rematch',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
            },
        )
        rematch_payload = await rematch_response.get_json()

        assert rematch_response.status_code == 200
        assert rematch_payload['data']['group_field_used'] == group_field
        assert rematch_payload['data']['group_field_source'] == 'legacy_fallback'
        assert rematch_payload['data']['rows'][0]['group_value'] == 'Acme'
        assert rematch_payload['data']['rows'][0]['match_status'] == 'matched'

        detail_response = await quart_test_client.get(
            f'/api/v1/broadcast/imports/{import_id}?{_query_scope()}',
            headers=_auth_headers(),
        )
        detail_payload = await detail_response.get_json()
        assert detail_response.status_code == 200
        assert detail_payload['data']['group_field_used'] is None
        assert detail_payload['data']['group_field_source'] is None


    @pytest.mark.asyncio
    async def test_group_rule_candidates_api_supports_default_status_pagination_and_filters(
        self,
        quart_test_client,
        fake_broadcast_app,
    ):
        from langbot.pkg.entity.persistence import broadcast as persistence_broadcast

        await quart_test_client.put(
            '/api/v1/broadcast/variable-profile',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
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
        await quart_test_client.post(
            '/api/v1/broadcast/group-rules',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'source_value': 'Configured Co',
                'match_type': 'exact',
                'match_expression': 'Configured Co',
                'target_conversation_name': 'Configured Group',
                'target_conversation_id': 'group-1',
                'priority': 0,
                'enabled': True,
            },
        )
        await quart_test_client.post(
            '/api/v1/broadcast/group-rules',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'source_value': 'Repair Co',
                'match_type': 'exact',
                'match_expression': 'Repair Co',
                'target_conversation_name': 'Repair Valid Group',
                'target_conversation_id': 'group-1',
                'priority': 0,
                'enabled': True,
            },
        )
        await quart_test_client.post(
            '/api/v1/broadcast/group-rules',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'source_value': 'Repair Co',
                'match_type': 'exact',
                'match_expression': 'Repair Co Backup',
                'target_conversation_name': 'Repair Missing Group',
                'target_conversation_id': 'repair-missing-group',
                'priority': -1,
                'enabled': False,
            },
        )
        await quart_test_client.post(
            '/api/v1/broadcast/group-rules',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'source_value': 'Ac',
                'match_type': 'contains',
                'match_expression': 'Ac',
                'target_conversation_name': 'Contains Group',
                'target_conversation_id': 'group-1',
                'priority': 10,
                'enabled': True,
            },
        )
        upload_response = await quart_test_client.post(
            '/api/v1/broadcast/imports',
            headers=_auth_headers(),
            form={'bot_uuid': 'bot-1', 'connector_id': 'wxwork-local'},
            files={
                'file': FileStorage(
                    stream=BytesIO('客户名称\nFresh Co\nConfigured Co\nRepair Co\nAcme\n"   "\n'.encode('utf-8')),
                    filename='customers.csv',
                )
            },
        )
        upload_payload = await upload_response.get_json()
        assert upload_response.status_code == 200
        import_id = upload_payload['data']['id']
        async with fake_broadcast_app.persistence_mgr.get_db_engine().begin() as conn:
            await fake_broadcast_app.persistence_mgr.execute_async(
                sqlalchemy.insert(persistence_broadcast.BroadcastImportRow).values(
                    {
                        'import_batch_id': import_id,
                        'source_row_number': 6,
                        'raw_data': {'????': '   '},
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
            await fake_broadcast_app.persistence_mgr.execute_async(
                sqlalchemy.update(persistence_broadcast.BroadcastImportBatch)
                .where(persistence_broadcast.BroadcastImportBatch.id == import_id)
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


        default_response = await quart_test_client.get(
            f'/api/v1/broadcast/imports/{import_id}/group-rule-candidates?{_query_scope()}',
            headers=_auth_headers(),
        )
        default_payload = await default_response.get_json()
        assert default_response.status_code == 200
        assert default_payload['data']['group_field_used'] == '客户名称'
        assert default_payload['data']['group_field_source'] == 'configured'
        assert default_payload['data']['stats'] == {
            'new_count': 1,
            'configured_count': 1,
            'needs_repair_count': 1,
            'conflict_count': 1,
            'invalid_count': 1,
        }
        assert [item['customer_name'] for item in default_payload['data']['items']] == ['Fresh Co']
        assert default_payload['data']['items'][0]['status'] == 'new'

        paged_response = await quart_test_client.get(
            f'/api/v1/broadcast/imports/{import_id}/group-rule-candidates?{_query_scope()}&status=all&page=2&page_size=2',
            headers=_auth_headers(),
        )
        paged_payload = await paged_response.get_json()
        assert paged_response.status_code == 200
        assert paged_payload['data']['total'] == 5
        assert paged_payload['data']['total_pages'] == 3
        assert [item['customer_name'] for item in paged_payload['data']['items']] == ['Repair Co', 'Acme']

        repair_response = await quart_test_client.get(
            f'/api/v1/broadcast/imports/{import_id}/group-rule-candidates?{_query_scope()}&status=needs_repair&keyword=Repair',
            headers=_auth_headers(),
        )
        repair_payload = await repair_response.get_json()
        assert repair_response.status_code == 200
        assert repair_payload['data']['total'] == 1
        repair_item = repair_payload['data']['items'][0]
        assert repair_item['customer_name'] == 'Repair Co'
        assert repair_item['status'] == 'needs_repair'
        assert len(repair_item['existing_rule_ids']) == 2
        assert repair_item['current_match_type'] == 'exact'

        conflict_response = await quart_test_client.get(
            f'/api/v1/broadcast/imports/{import_id}/group-rule-candidates?{_query_scope()}&status=conflict',
            headers=_auth_headers(),
        )
        conflict_payload = await conflict_response.get_json()
        assert conflict_response.status_code == 200
        assert conflict_payload['data']['total'] == 1
        assert conflict_payload['data']['items'][0]['customer_name'] == 'Acme'
        assert conflict_payload['data']['items'][0]['current_match_type'] == 'contains'


    @pytest.mark.asyncio
    async def test_group_rule_candidates_api_uses_runtime_legacy_fallback_without_persisting_batch(
        self,
        quart_test_client,
        fake_broadcast_app,
    ):
        from langbot.pkg.entity.persistence import broadcast as persistence_broadcast

        await quart_test_client.put(
            '/api/v1/broadcast/variable-profile',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
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
        upload_response = await quart_test_client.post(
            '/api/v1/broadcast/imports',
            headers=_auth_headers(),
            form={'bot_uuid': 'bot-1', 'connector_id': 'wxwork-local'},
            files={
                'file': FileStorage(
                    stream=BytesIO('客户名称\nAcme\n'.encode('utf-8')),
                    filename='customers.csv',
                )
            },
        )
        import_id = (await upload_response.get_json())['data']['id']
        async with fake_broadcast_app.persistence_mgr.get_db_engine().begin() as conn:
            await fake_broadcast_app.persistence_mgr.execute_async(
                sqlalchemy.update(persistence_broadcast.BroadcastImportBatch)
                .where(persistence_broadcast.BroadcastImportBatch.id == import_id)
                .values({'group_field_used': None, 'group_field_source': None}),
                conn=conn,
            )

        response = await quart_test_client.get(
            f'/api/v1/broadcast/imports/{import_id}/group-rule-candidates?{_query_scope()}&status=all',
            headers=_auth_headers(),
        )
        payload = await response.get_json()
        assert response.status_code == 200
        assert payload['data']['group_field_used'] == '客户名称'
        assert payload['data']['group_field_source'] == 'legacy_fallback'

        detail_response = await quart_test_client.get(
            f'/api/v1/broadcast/imports/{import_id}?{_query_scope()}',
            headers=_auth_headers(),
        )
        detail_payload = await detail_response.get_json()
        assert detail_response.status_code == 200
        assert detail_payload['data']['group_field_used'] is None
        assert detail_payload['data']['group_field_source'] is None


    @pytest.mark.asyncio
    async def test_group_rule_candidates_api_rejects_legacy_unresolvable_batch(
        self,
        quart_test_client,
        fake_broadcast_app,
    ):
        from langbot.pkg.entity.persistence import broadcast as persistence_broadcast

        await quart_test_client.put(
            '/api/v1/broadcast/variable-profile',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
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
        upload_response = await quart_test_client.post(
            '/api/v1/broadcast/imports',
            headers=_auth_headers(),
            form={'bot_uuid': 'bot-1', 'connector_id': 'wxwork-local'},
            files={
                'file': FileStorage(
                    stream=BytesIO('客户名称\nAcme\n'.encode('utf-8')),
                    filename='customers.csv',
                )
            },
        )
        import_id = (await upload_response.get_json())['data']['id']
        async with fake_broadcast_app.persistence_mgr.get_db_engine().begin() as conn:
            await fake_broadcast_app.persistence_mgr.execute_async(
                sqlalchemy.update(persistence_broadcast.BroadcastImportBatch)
                .where(persistence_broadcast.BroadcastImportBatch.id == import_id)
                .values({'group_field_used': None, 'group_field_source': None}),
                conn=conn,
            )
            await fake_broadcast_app.persistence_mgr.execute_async(
                sqlalchemy.update(persistence_broadcast.BroadcastVariableProfile)
                .where(
                    persistence_broadcast.BroadcastVariableProfile.bot_uuid == 'bot-1',
                    persistence_broadcast.BroadcastVariableProfile.connector_id == 'wxwork-local',
                )
                .values({'group_field': None}),
                conn=conn,
            )

        response = await quart_test_client.get(
            f'/api/v1/broadcast/imports/{import_id}/group-rule-candidates?{_query_scope()}&status=all',
            headers=_auth_headers(),
        )
        payload = await response.get_json()
        assert response.status_code == 400
        assert payload['msg'] == 'BROADCAST_IMPORT_GROUP_FIELD_UNRESOLVABLE'


    @pytest.mark.asyncio
    async def test_bulk_assign_group_rules_happy_path(
        self,
        quart_test_client,
        fake_broadcast_app,
    ):
        await quart_test_client.put(
            '/api/v1/broadcast/variable-profile',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
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
        upload_response = await quart_test_client.post(
            '/api/v1/broadcast/imports',
            headers=_auth_headers(),
            form={'bot_uuid': 'bot-1', 'connector_id': 'wxwork-local'},
            files={
                'file': FileStorage(
                    stream=BytesIO('客户名称\nAcme\n'.encode('utf-8')),
                    filename='customers.csv',
                )
            },
        )
        upload_payload = await upload_response.get_json()
        assert upload_response.status_code == 200
        import_id = upload_payload['data']['id']
        await _insert_group_name(
            fake_broadcast_app,
            external_conversation_id='group-acme',
            name='Acme Group',
        )
        group_key = await _get_import_group_key(
            quart_test_client,
            import_id,
            group_value='Acme',
        )

        bulk_assign_response = await quart_test_client.post(
            f'/api/v1/broadcast/imports/{import_id}/group-rules/bulk-assign',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'items': [
                    {
                        'group_key': group_key,
                        'target_conversation_id': 'group-acme',
                    }
                ],
            },
        )
        bulk_assign_payload = await bulk_assign_response.get_json()
        assert bulk_assign_response.status_code == 200
        assert bulk_assign_payload['data']['created_count'] == 1
        assert bulk_assign_payload['data']['group_field_used'] == '客户名称'
        assert bulk_assign_payload['data']['group_field_source'] == 'configured'
        created_rule_id = bulk_assign_payload['data']['items'][0]['rule_id']

        rules_response = await quart_test_client.get(
            f'/api/v1/broadcast/group-rules?{_query_scope()}',
            headers=_auth_headers(),
        )
        rules_payload = await rules_response.get_json()
        assert rules_response.status_code == 200
        assert len(rules_payload['data']) == 1
        assert rules_payload['data'][0]['id'] == created_rule_id
        assert rules_payload['data'][0]['source_value'] == 'Acme'
        assert rules_payload['data'][0]['match_type'] == 'exact'
        assert rules_payload['data'][0]['match_expression'] == 'Acme'
        assert rules_payload['data'][0]['target_conversation_id'] == 'group-acme'
        assert rules_payload['data'][0]['target_conversation_name'] == 'Acme Group'

        detail_response = await quart_test_client.get(
            f'/api/v1/broadcast/imports/{import_id}?{_query_scope()}',
            headers=_auth_headers(),
        )
        detail_payload = await detail_response.get_json()
        assert detail_response.status_code == 200
        assert detail_payload['data']['rows'][0]['group_value'] == 'Acme'
        assert detail_payload['data']['rows'][0]['matched_conversation_id'] == 'group-acme'
        assert detail_payload['data']['rows'][0]['matched_conversation_name'] == 'Acme Group'
        assert detail_payload['data']['rows'][0]['matched_rule_id'] == created_rule_id


    @pytest.mark.asyncio
    async def test_bulk_assign_group_rules_uses_legacy_fallback_without_persisting_batch(
        self,
        quart_test_client,
        fake_broadcast_app,
    ):
        from langbot.pkg.entity.persistence import broadcast as persistence_broadcast

        await quart_test_client.put(
            '/api/v1/broadcast/variable-profile',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
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
        upload_response = await quart_test_client.post(
            '/api/v1/broadcast/imports',
            headers=_auth_headers(),
            form={'bot_uuid': 'bot-1', 'connector_id': 'wxwork-local'},
            files={
                'file': FileStorage(
                    stream=BytesIO('客户名称\nAcme\n'.encode('utf-8')),
                    filename='customers.csv',
                )
            },
        )
        upload_payload = await upload_response.get_json()
        assert upload_response.status_code == 200
        import_id = upload_payload['data']['id']
        await _insert_group_name(
            fake_broadcast_app,
            external_conversation_id='group-acme',
            name='Acme Group',
        )
        async with fake_broadcast_app.persistence_mgr.get_db_engine().begin() as conn:
            await fake_broadcast_app.persistence_mgr.execute_async(
                sqlalchemy.update(persistence_broadcast.BroadcastImportBatch)
                .where(persistence_broadcast.BroadcastImportBatch.id == import_id)
                .values({'group_field_used': None, 'group_field_source': None}),
                conn=conn,
            )
        group_key = await _get_import_group_key(
            quart_test_client,
            import_id,
            group_value='Acme',
        )

        bulk_assign_response = await quart_test_client.post(
            f'/api/v1/broadcast/imports/{import_id}/group-rules/bulk-assign',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'items': [
                    {
                        'group_key': group_key,
                        'target_conversation_id': 'group-acme',
                    }
                ],
            },
        )
        bulk_assign_payload = await bulk_assign_response.get_json()
        assert bulk_assign_response.status_code == 200
        assert bulk_assign_payload['data']['group_field_used'] == '客户名称'
        assert bulk_assign_payload['data']['group_field_source'] == 'legacy_fallback'

        detail_response = await quart_test_client.get(
            f'/api/v1/broadcast/imports/{import_id}?{_query_scope()}',
            headers=_auth_headers(),
        )
        detail_payload = await detail_response.get_json()
        assert detail_response.status_code == 200
        assert detail_payload['data']['group_field_used'] is None
        assert detail_payload['data']['group_field_source'] is None
        assert detail_payload['data']['rows'][0]['matched_conversation_id'] == 'group-acme'


    @pytest.mark.asyncio
    async def test_bulk_assign_group_rules_rolls_back_when_formal_match_conflicts(
        self,
        quart_test_client,
        fake_broadcast_app,
        monkeypatch,
    ):
        await quart_test_client.put(
            '/api/v1/broadcast/variable-profile',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
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
        upload_response = await quart_test_client.post(
            '/api/v1/broadcast/imports',
            headers=_auth_headers(),
            form={'bot_uuid': 'bot-1', 'connector_id': 'wxwork-local'},
            files={
                'file': FileStorage(
                    stream=BytesIO('客户名称\nAcme\n'.encode('utf-8')),
                    filename='customers.csv',
                )
            },
        )
        upload_payload = await upload_response.get_json()
        assert upload_response.status_code == 200
        import_id = upload_payload['data']['id']
        await _insert_group_name(
            fake_broadcast_app,
            external_conversation_id='group-acme',
            name='Acme Group',
        )
        group_key = await _get_import_group_key(
            quart_test_client,
            import_id,
            group_value='Acme',
        )

        repository = fake_broadcast_app.broadcast_service.repository
        original_create_group_rule = repository.create_group_rule

        async def create_group_rule_with_interceptor(conn, payload):
            rule_id = await original_create_group_rule(conn, payload)
            if payload.get('source_value') == 'Acme' and payload.get('match_type') == 'exact':
                await original_create_group_rule(
                    conn,
                    {
                        'bot_uuid': 'bot-1',
                        'connector_id': 'wxwork-local',
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

        monkeypatch.setattr(repository, 'create_group_rule', create_group_rule_with_interceptor)

        bulk_assign_response = await quart_test_client.post(
            f'/api/v1/broadcast/imports/{import_id}/group-rules/bulk-assign',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'items': [
                    {
                        'group_key': group_key,
                        'target_conversation_id': 'group-acme',
                    }
                ],
            },
        )
        bulk_assign_payload = await bulk_assign_response.get_json()
        assert bulk_assign_response.status_code == 400
        assert bulk_assign_payload['msg'] == 'BROADCAST_IMPORT_GROUP_RULE_BULK_ASSIGN_FAILED'
        assert bulk_assign_payload['details']['items'][0]['customer_name'] == 'Acme'

        rules_response = await quart_test_client.get(
            f'/api/v1/broadcast/group-rules?{_query_scope()}',
            headers=_auth_headers(),
        )
        rules_payload = await rules_response.get_json()
        assert rules_response.status_code == 200
        assert rules_payload['data'] == []

        detail_response = await quart_test_client.get(
            f'/api/v1/broadcast/imports/{import_id}?{_query_scope()}',
            headers=_auth_headers(),
        )
        detail_payload = await detail_response.get_json()
        assert detail_response.status_code == 200
        assert detail_payload['data']['rows'][0]['matched_rule_id'] is None
        assert detail_payload['data']['rows'][0]['matched_conversation_id'] is None


    @pytest.mark.asyncio
    async def test_import_upload_rejects_missing_required_fields_with_chinese_error(self, quart_test_client):
        await quart_test_client.put(
            '/api/v1/broadcast/variable-profile',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
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

        response = await quart_test_client.post(
            '/api/v1/broadcast/imports',
            headers=_auth_headers(),
            form={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
            },
            files={
                'file': FileStorage(
                    stream=BytesIO('客户名称\nAcme\n'.encode('utf-8')),
                    filename='customers.csv',
                ),
            },
        )
        payload = await response.get_json()

        assert response.status_code == 400
        assert payload['message'] == '导入文件缺少以下字段：订单号'

    @pytest.mark.asyncio
    async def test_import_generate_drafts_renders_chinese_variable_from_uploaded_value(self, quart_test_client):
        await quart_test_client.put(
            '/api/v1/broadcast/variable-profile',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
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
        await quart_test_client.post(
            '/api/v1/broadcast/group-rules',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'source_value': '小满',
                'match_type': 'exact',
                'match_expression': '小满',
                'target_conversation_name': '小满',

                'target_conversation_id': '小满',
                'priority': 10,
                'enabled': True,
            },
        )

        upload_response = await quart_test_client.post(
            '/api/v1/broadcast/imports',
            headers=_auth_headers(),
            form={'bot_uuid': 'bot-1', 'connector_id': 'wxwork-local'},
            files={
                'file': FileStorage(
                    stream=BytesIO('\ufeff 客户 , 运单号 \n 小满 , TEST-20260704-001 \n'.encode('utf-8')),
                    filename='customers.csv',
                )
            },
        )
        upload_payload = await upload_response.get_json()
        assert upload_response.status_code == 200
        import_id = upload_payload['data']['id']

        template_response = await quart_test_client.post(
            '/api/v1/broadcast/templates',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'name': '查验通知',
                'content': '查验通知：\n\n涉及单号如下：\n{{运单号}}',
                'enabled': True,
            },
        )
        template_id = (await template_response.get_json())['data']['id']

        generate_response = await quart_test_client.post(
            f'/api/v1/broadcast/imports/{import_id}/generate-drafts',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'template_id': template_id,
                'group_keys': await _get_all_import_group_keys(quart_test_client, import_id),
            },
        )
        assert generate_response.status_code == 200

        drafts_response = await quart_test_client.get(
            f'/api/v1/broadcast/drafts?{_query_scope()}&import_batch_id={import_id}',
            headers=_auth_headers(),
        )
        drafts = (await drafts_response.get_json())['data']
        assert drafts[0]['draft_text'] == '查验通知：\n\n涉及单号如下：\nTEST-20260704-001'

    @pytest.mark.asyncio
    async def test_drafts_list_edit_ready_rollback_and_invalid_confirm_forbidden(
        self,
        quart_test_client,
        fake_broadcast_app,
    ):
        await quart_test_client.put(
            '/api/v1/broadcast/variable-profile',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
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
        await quart_test_client.post(
            '/api/v1/broadcast/group-rules',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'source_value': 'Acme',
                'match_type': 'exact',
                'match_expression': 'Acme',
                'target_conversation_name': 'Acme Group',

                'target_conversation_id': 'Acme Group',
                'priority': 10,
                'enabled': True,
            },
        )
        upload_response = await quart_test_client.post(
            '/api/v1/broadcast/imports',
            headers=_auth_headers(),
            form={'bot_uuid': 'bot-1', 'connector_id': 'wxwork-local'},
            files={
                'file': FileStorage(
                    stream=BytesIO('客户名称\nAcme\nNorthwind\n'.encode('utf-8')),
                    filename='customers.csv',
                )
            },
        )
        import_id = (await upload_response.get_json())['data']['id']
        template_response = await quart_test_client.post(
            '/api/v1/broadcast/templates',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'name': 'Arrival Reminder',
                'content': 'Hello {{customer_name}}',
                'enabled': True,
            },
        )
        template_id = (await template_response.get_json())['data']['id']
        matched_group_key = await _get_import_group_key(
            quart_test_client,
            import_id,
            group_value='Acme',
        )
        generate_response = await quart_test_client.post(
            f'/api/v1/broadcast/imports/{import_id}/generate-drafts',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'group_keys': [matched_group_key],
                'template_id': template_id,
            },
        )
        generate_payload = await generate_response.get_json()
        assert generate_response.status_code == 200
        assert generate_payload['data']['generated_group_keys'] == [matched_group_key]
        invalid_draft_id = await _create_invalid_import_draft(
            fake_broadcast_app,
            import_id=import_id,
            template_id=template_id,
            template_name='Arrival Reminder',
            template_content='Hello {{customer_name}}',
            group_value='Northwind',
        )

        list_response = await quart_test_client.get(
            f'/api/v1/broadcast/drafts?{_query_scope()}&import_batch_id={import_id}',
            headers=_auth_headers(),
        )
        drafts = (await list_response.get_json())['data']
        matched_draft = next(item for item in drafts if item['status'] == 'pending_review')

        await quart_test_client.post(
            '/api/v1/broadcast/drafts/batch-status',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'draft_ids': [matched_draft['id']],
                'status': 'ready',
            },
        )

        edit_response = await quart_test_client.put(
            f"/api/v1/broadcast/drafts/{matched_draft['id']}",
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'draft_text': 'Updated ready draft',
            },
        )
        edit_payload = await edit_response.get_json()
        assert edit_response.status_code == 200
        assert edit_payload['data']['status'] == 'pending_review'
        assert edit_payload['data']['message'] == '草稿内容已修改，请重新确认'

        invalid_confirm_response = await quart_test_client.post(
            '/api/v1/broadcast/drafts/batch-status',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'draft_ids': [invalid_draft_id],
                'status': 'ready',
            },
        )
        invalid_confirm_payload = await invalid_confirm_response.get_json()
        assert invalid_confirm_response.status_code == 400
        assert invalid_confirm_payload['msg'] == 'BROADCAST_DRAFT_INVALID_CONFIRM_FORBIDDEN'

    @pytest.mark.asyncio
    async def test_drafts_list_audit_filters_map_legacy_queries_and_hide_invalid(
        self,
        quart_test_client,
        fake_broadcast_app,
    ):
        await quart_test_client.put(
            '/api/v1/broadcast/variable-profile',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
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
        await quart_test_client.post(
            '/api/v1/broadcast/group-rules',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'source_value': 'Acme',
                'match_type': 'exact',
                'match_expression': 'Acme',
                'target_conversation_name': 'Acme Group',

                'target_conversation_id': 'Acme Group',
                'priority': 10,
                'enabled': True,
            },
        )
        upload_response = await quart_test_client.post(
            '/api/v1/broadcast/imports',
            headers=_auth_headers(),
            form={'bot_uuid': 'bot-1', 'connector_id': 'wxwork-local'},
            files={
                'file': FileStorage(
                    stream=BytesIO('客户名称\nAcme\nNorthwind\n'.encode('utf-8')),
                    filename='customers.csv',
                )
            },
        )
        import_id = (await upload_response.get_json())['data']['id']
        template_response = await quart_test_client.post(
            '/api/v1/broadcast/templates',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'name': 'Arrival Reminder',
                'content': 'Hello {{customer_name}}',
                'enabled': True,
            },
        )
        template_id = (await template_response.get_json())['data']['id']
        matched_group_key = await _get_import_group_key(
            quart_test_client,
            import_id,
            group_value='Acme',
        )
        generate_response = await quart_test_client.post(
            f'/api/v1/broadcast/imports/{import_id}/generate-drafts',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'group_keys': [matched_group_key],
                'template_id': template_id,
            },
        )
        generate_payload = await generate_response.get_json()
        assert generate_response.status_code == 200
        assert generate_payload['data']['generated_group_keys'] == [matched_group_key]
        await _create_invalid_import_draft(
            fake_broadcast_app,
            import_id=import_id,
            template_id=template_id,
            template_name='Arrival Reminder',
            template_content='Hello {{customer_name}}',
            group_value='Northwind',
        )

        all_response = await quart_test_client.get(
            f'/api/v1/broadcast/drafts?{_query_scope()}&import_batch_id={import_id}&status=all',
            headers=_auth_headers(),
        )
        pending_response = await quart_test_client.get(
            f'/api/v1/broadcast/drafts?{_query_scope()}&import_batch_id={import_id}&status=pending',
            headers=_auth_headers(),
        )
        pending_review_response = await quart_test_client.get(
            f'/api/v1/broadcast/drafts?{_query_scope()}&import_batch_id={import_id}&status=pending_review',
            headers=_auth_headers(),
        )
        ready_response = await quart_test_client.get(
            f'/api/v1/broadcast/drafts?{_query_scope()}&import_batch_id={import_id}&status=ready',
            headers=_auth_headers(),
        )
        invalid_response = await quart_test_client.get(
            f'/api/v1/broadcast/drafts?{_query_scope()}&import_batch_id={import_id}&status=invalid',
            headers=_auth_headers(),
        )

        all_drafts = (await all_response.get_json())['data']
        pending_drafts = (await pending_response.get_json())['data']
        pending_review_drafts = (await pending_review_response.get_json())['data']
        ready_drafts = (await ready_response.get_json())['data']
        invalid_drafts = (await invalid_response.get_json())['data']

        assert [item['group_value'] for item in all_drafts] == ['Acme']
        assert [item['send_status'] for item in all_drafts] == ['pending']
        assert [item['group_value'] for item in pending_drafts] == ['Acme']
        assert [item['group_value'] for item in pending_review_drafts] == ['Acme']
        assert [item['group_value'] for item in ready_drafts] == ['Acme']
        assert invalid_drafts == []

    @pytest.mark.asyncio
    async def test_execution_batch_create_and_detail_routes(self, quart_test_client):
        await quart_test_client.put(
            '/api/v1/broadcast/variable-profile',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
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
        await quart_test_client.post(
            '/api/v1/broadcast/group-rules',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'source_value': 'Acme',
                'match_type': 'exact',
                'match_expression': 'Acme',
                'target_conversation_name': 'Acme Group',

                'target_conversation_id': 'Acme Group',
                'priority': 10,
                'enabled': True,
            },
        )
        upload_response = await quart_test_client.post(
            '/api/v1/broadcast/imports',
            headers=_auth_headers(),
            form={'bot_uuid': 'bot-1', 'connector_id': 'wxwork-local'},
            files={
                'file': FileStorage(
                    stream=BytesIO('客户名称\nAcme\n'.encode('utf-8')),
                    filename='customers.csv',
                )
            },
        )
        import_id = (await upload_response.get_json())['data']['id']
        template_response = await quart_test_client.post(
            '/api/v1/broadcast/templates',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'name': 'Arrival Reminder',
                'content': 'Hello {{customer_name}}',
                'enabled': True,
            },
        )
        template_id = (await template_response.get_json())['data']['id']
        await quart_test_client.post(
            f'/api/v1/broadcast/imports/{import_id}/generate-drafts',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'template_id': template_id,
                'group_keys': await _get_all_import_group_keys(quart_test_client, import_id),
            },
        )
        drafts_response = await quart_test_client.get(
            f'/api/v1/broadcast/drafts?{_query_scope()}&import_batch_id={import_id}',
            headers=_auth_headers(),
        )
        draft = (await drafts_response.get_json())['data'][0]
        await quart_test_client.post(
            '/api/v1/broadcast/drafts/batch-status',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'draft_ids': [draft['id']],
                'status': 'ready',
            },
        )

        create_response = await quart_test_client.post(
            '/api/v1/broadcast/executions',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'draft_ids': [draft['id']],
                'mode': 'paste_only',
                'operator': 'tester@example.com',
            },
        )
        create_payload = await create_response.get_json()
        assert create_response.status_code == 200
        assert create_payload['data']['status'] == 'created'
        assert create_payload['data']['total_tasks'] == 1
        task_id = create_payload['data']['tasks'][0]['id']

        list_response = await quart_test_client.get(
            f'/api/v1/broadcast/executions?{_query_scope()}',
            headers=_auth_headers(),
        )
        list_payload = await list_response.get_json()
        assert list_response.status_code == 200
        assert [item['id'] for item in list_payload['data']] == [create_payload['data']['id']]

        detail_response = await quart_test_client.get(
            f"/api/v1/broadcast/executions/{create_payload['data']['id']}?{_query_scope()}",
            headers=_auth_headers(),
        )
        detail_payload = await detail_response.get_json()
        assert detail_response.status_code == 200
        assert detail_payload['data']['tasks'][0]['id'] == task_id

        task_response = await quart_test_client.get(
            f'/api/v1/broadcast/execution-tasks/{task_id}?{_query_scope()}',
            headers=_auth_headers(),
        )
        task_payload = await task_response.get_json()
        assert task_response.status_code == 200
        assert task_payload['data']['id'] == task_id

    @pytest.mark.asyncio
    async def test_executor_capabilities_and_health_routes_return_stable_verification_codes(
        self,
        quart_test_client,
        fake_broadcast_app,
    ):
        class _FakeRuntimeClient:
            async def health(self):
                return {
                    'status': 'ready',
                    'protocolVersion': '2',
                    'runtimeVersion': '0.1.0-test',
                }

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
                    'displaySummary': [],
                }

        fake_broadcast_app.desktop_automation_service = SimpleNamespace(
            runtime_client=_FakeRuntimeClient(),
        )

        capability_response = await quart_test_client.get(
            f'/api/v1/broadcast/executors/capabilities?{_query_scope()}',
            headers=_auth_headers(),
        )
        capability_raw = await capability_response.get_data(as_text=True)
        capability_payload = await capability_response.get_json()
        assert capability_response.status_code == 200
        assert capability_payload['data']['supports_paste_verification'] is False
        assert capability_payload['data']['supports_post_send_verification'] is False
        assert capability_payload['data']['content_verification'] == 'disabled'
        assert capability_payload['data']['post_send_verification'] == 'unavailable'
        assert capability_payload['data']['requires_manual_conversation_open'] is False
        assert '"supports_paste_verification":false' in capability_raw

        health_response = await quart_test_client.get(
            f'/api/v1/broadcast/executors/health?{_query_scope()}',
            headers=_auth_headers(),
        )
        health_raw = await health_response.get_data(as_text=True)
        health_payload = await health_response.get_json()
        assert health_response.status_code == 200
        assert health_payload['data']['runtime_version'] == '0.1.0-test'
        assert health_payload['data']['runtime_status']['pasteVerification'] == {
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
        }
        assert '"method":"windows_uia"' in health_raw

    @pytest.mark.asyncio
    @pytest.mark.asyncio
    async def test_execution_attempt_evidence_route_returns_specific_not_available_code(
        self,
        quart_test_client,
        fake_broadcast_app,
    ):
        from langbot.pkg.broadcast.errors import BroadcastError

        async def missing_evidence(_attempt_id, _scope):
            raise BroadcastError('BROADCAST_EXECUTION_EVIDENCE_NOT_AVAILABLE', 'execution evidence not available')

        fake_broadcast_app.broadcast_service.get_execution_evidence = missing_evidence

        response = await quart_test_client.get(
            f'/api/v1/broadcast/execution-attempts/123/evidence?{_query_scope()}',
            headers=_auth_headers(),
        )
        payload = await response.get_json()

        assert response.status_code == 404
        assert payload['msg'] == 'BROADCAST_EXECUTION_EVIDENCE_NOT_AVAILABLE'


    async def test_execution_task_start_route_maps_attachment_paste_warning_to_success(
        self,
        quart_test_client,
        fake_broadcast_app,
        monkeypatch,
    ):
        monkeypatch.setenv('LANGBOT_RPA_FORCE_DISABLE_SEND', '1')

        class _WarningRuntimeClient:
            async def create_task(self, *, request):
                return {
                    'id': 'runtime-warning',
                    'status': 'succeeded_with_warning',
                    'stage': 'attachments_pasted_unverified',
                    'result': {
                        'messageSent': False,
                        'message_sent': False,
                        'clipboardRestoreFailed': False,
                        'warning': 'PASTE_RESULT_NOT_VERIFIED',
                        'contentVerified': False,
                        'draftWritten': True,
                        'inputLocated': False,
                        'enterDispatched': False,
                        'terminalConfirmed': True,
                        'retryAllowed': False,
                        'attachmentsPrepared': True,
                        'attachmentPasteRequested': True,
                        'attachmentsVerified': False,
                        'attachmentCount': 1,
                        'observationAvailable': False,
                        'attachments': [{'name': 'quote.pdf'}],
                    },
                }

            async def health(self):
                return {
                    'status': 'ready',
                    'protocolVersion': '2',
                    'runtimeVersion': '0.1.0-test',
                }

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
                        'supportedErrorCodes': [],
                    },
                    'displaySummary': [],
                }

        fake_broadcast_app.desktop_automation_service = SimpleNamespace(
            runtime_client=_WarningRuntimeClient(),
        )

        await quart_test_client.put(
            '/api/v1/broadcast/variable-profile',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
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
        await quart_test_client.post(
            '/api/v1/broadcast/group-rules',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'source_value': 'Acme',
                'match_type': 'exact',
                'match_expression': 'Acme',
                'target_conversation_name': 'Acme Group',

                'target_conversation_id': 'Acme Group',
                'priority': 10,
                'enabled': True,
            },
        )
        upload_response = await quart_test_client.post(
            '/api/v1/broadcast/imports',
            headers=_auth_headers(),
            form={'bot_uuid': 'bot-1', 'connector_id': 'wxwork-local'},
            files={
                'file': FileStorage(
                    stream=BytesIO('客户名称\nAcme\n'.encode('utf-8')),
                    filename='customers.csv',
                ),
            },
        )
        import_id = (await upload_response.get_json())['data']['id']
        template_response = await quart_test_client.post(
            '/api/v1/broadcast/templates',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'name': 'Arrival Reminder',
                'content': 'Hello {{customer_name}}',
                'enabled': True,
            },
        )
        template_id = (await template_response.get_json())['data']['id']
        await quart_test_client.post(
            f'/api/v1/broadcast/imports/{import_id}/generate-drafts',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'template_id': template_id,
                'group_keys': await _get_all_import_group_keys(quart_test_client, import_id),
            },
        )
        drafts_response = await quart_test_client.get(
            f'/api/v1/broadcast/drafts?{_query_scope()}&import_batch_id={import_id}',
            headers=_auth_headers(),
        )
        draft = (await drafts_response.get_json())['data'][0]
        await quart_test_client.post(
            '/api/v1/broadcast/drafts/batch-status',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'draft_ids': [draft['id']],
                'status': 'ready',
            },
        )
        create_response = await quart_test_client.post(
            '/api/v1/broadcast/executions',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'draft_ids': [draft['id']],
                'mode': 'paste_only',
                'operator': 'tester@example.com',
            },
        )
        task_id = (await create_response.get_json())['data']['tasks'][0]['id']

        start_response = await quart_test_client.post(
            f'/api/v1/broadcast/execution-tasks/{task_id}/start',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'operator': 'tester@example.com',
            },
        )
        start_payload = await start_response.get_json()

        assert start_response.status_code == 200
        assert start_payload['data']['status'] == 'succeeded'
        assert start_payload['data']['retry_allowed'] is False

        attempts_response = await quart_test_client.get(
            f'/api/v1/broadcast/execution-tasks/{task_id}/attempts?{_query_scope()}',
            headers=_auth_headers(),
        )
        attempts_payload = await attempts_response.get_json()
        assert attempts_payload['data'][0]['status'] == 'succeeded'

        evidence_response = await quart_test_client.get(
            f"/api/v1/broadcast/execution-attempts/{attempts_payload['data'][0]['id']}/evidence?{_query_scope()}",
            headers=_auth_headers(),
        )
        evidence_payload = await evidence_response.get_json()
        assert evidence_payload['data']['evidence_summary'] == '已粘贴附件，未发送'
        technical_details = json.loads(evidence_payload['data']['technical_details'])
        assert technical_details['warning'] == 'PASTE_RESULT_NOT_VERIFIED'
        assert technical_details['attachment_count'] == 1
        assert technical_details['attachment_names'] == ['quote.pdf']

    @pytest.mark.asyncio
    async def test_execution_batch_allows_pending_review_draft(self, quart_test_client):
        await quart_test_client.put(
            '/api/v1/broadcast/variable-profile',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
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
        await quart_test_client.post(
            '/api/v1/broadcast/group-rules',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'source_value': 'Acme',
                'match_type': 'exact',
                'match_expression': 'Acme',
                'target_conversation_name': 'Acme Group',

                'target_conversation_id': 'Acme Group',
                'priority': 10,
                'enabled': True,
            },
        )
        upload_response = await quart_test_client.post(
            '/api/v1/broadcast/imports',
            headers=_auth_headers(),
            form={'bot_uuid': 'bot-1', 'connector_id': 'wxwork-local'},
            files={
                'file': FileStorage(
                    stream=BytesIO('客户名称\nAcme\n'.encode('utf-8')),
                    filename='customers.csv',
                )
            },
        )
        import_id = (await upload_response.get_json())['data']['id']
        template_response = await quart_test_client.post(
            '/api/v1/broadcast/templates',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'name': 'Arrival Reminder',
                'content': 'Hello {{customer_name}}',
                'enabled': True,
            },
        )
        template_id = (await template_response.get_json())['data']['id']
        await quart_test_client.post(
            f'/api/v1/broadcast/imports/{import_id}/generate-drafts',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'template_id': template_id,
                'group_keys': await _get_all_import_group_keys(quart_test_client, import_id),
            },
        )
        drafts_response = await quart_test_client.get(
            f'/api/v1/broadcast/drafts?{_query_scope()}&import_batch_id={import_id}',
            headers=_auth_headers(),
        )
        draft = (await drafts_response.get_json())['data'][0]

        create_response = await quart_test_client.post(
            '/api/v1/broadcast/executions',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'draft_ids': [draft['id']],
                'mode': 'paste_only',
                'operator': 'tester@example.com',
            },
        )
        create_payload = await create_response.get_json()
        assert create_response.status_code == 200
        assert create_payload['data']['mode'] == 'paste_only'
        assert create_payload['data']['total_tasks'] == 1

    @pytest.mark.asyncio
    async def test_execution_evidence_keeps_selected_window_and_task_verification_diagnostic(
        self,
        quart_test_client,
        fake_broadcast_app,
        monkeypatch,
    ):
        monkeypatch.setenv('LANGBOT_RPA_FORCE_DISABLE_SEND', '1')

        class _InputNotLocatedRuntimeClient:
            def __init__(self) -> None:
                self.requests = []

            async def create_task(self, *, request):
                self.requests.append(request)
                return {
                    'id': 'runtime-api-input-not-located',
                    'status': 'interrupted',
                    'stage': 'input_not_located',
                    'errorCode': 'INPUT_NOT_LOCATED',
                    'result': {
                        'messageSent': False,
                        'clipboardRestoreFailed': False,
                        'contentVerified': False,
                        'verificationFailed': True,
                        'draftWritten': False,
                        'inputLocated': False,
                        'windowTitle': '企业微信',
                        'candidateCountBeforeFilter': 3,
                        'candidateCountAfterFilter': 1,
                        'canonicalCandidateCount': 2,
                        'rejectedCandidateCount': 2,
                        'selectedWindow': {
                            'hwnd': '1769682',
                            'rootHwnd': '1769682',
                            'ownerHwnd': '0',
                            'processId': 5516,
                            'processName': 'wxwork.exe',
                            'executableName': 'wxwork.exe',
                            'title': '企业微信',
                            'className': 'Qt51514QWindowIcon',
                            'visible': True,
                            'minimized': False,
                            'source': 'node-window-manager',
                            'accepted': True,
                            'rejectionReason': None,
                        },
                        'taskVerificationDiagnostic': {
                            'scriptKind': 'input_inspection',
                            'spawnSucceeded': True,
                            'timedOut': False,
                            'exitCode': 0,
                            'stdoutJsonFound': True,
                            'stderrCategory': 'none',
                            'tempFileCreated': True,
                            'tempFileCleanupSucceeded': True,
                            'failureStep': 'INPUT_LOOKUP',
                            'windowFound': True,
                            'conversationObserved': True,
                            'conversationMatched': True,
                            'inputElementFound': False,
                            'valuePatternAvailable': False,
                            'textPatternAvailable': False,
                            'textObserved': False,
                        },
                    },
                }

            async def health(self):
                return {
                    'status': 'ready',
                    'protocolVersion': '2',
                    'runtimeVersion': '0.1.0-test',
                }

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
                            'UIA_TASK_SCRIPT_FAILED',
                            'PASTE_VERIFICATION_UNAVAILABLE',
                        ],
                    },
                    'displaySummary': [],
                }

        fake_broadcast_app.desktop_automation_service = SimpleNamespace(
            runtime_client=_InputNotLocatedRuntimeClient(),
        )

        await quart_test_client.put(
            '/api/v1/broadcast/variable-profile',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
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
        await quart_test_client.post(
            '/api/v1/broadcast/group-rules',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'source_value': 'Acme',
                'match_type': 'exact',
                'match_expression': 'Acme',
                'target_conversation_name': 'Acme Group',

                'target_conversation_id': 'Acme Group',
                'priority': 10,
                'enabled': True,
            },
        )
        upload_response = await quart_test_client.post(
            '/api/v1/broadcast/imports',
            headers=_auth_headers(),
            form={'bot_uuid': 'bot-1', 'connector_id': 'wxwork-local'},
            files={
                'file': FileStorage(
                    stream=BytesIO('客户名称\nAcme\n'.encode('utf-8')),
                    filename='customers.csv',
                )
            },
        )
        import_id = (await upload_response.get_json())['data']['id']
        template_response = await quart_test_client.post(
            '/api/v1/broadcast/templates',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'name': 'Arrival Reminder',
                'content': 'Hello {{customer_name}}',
                'enabled': True,
            },
        )
        template_id = (await template_response.get_json())['data']['id']
        await quart_test_client.post(
            f'/api/v1/broadcast/imports/{import_id}/generate-drafts',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'template_id': template_id,
                'group_keys': await _get_all_import_group_keys(quart_test_client, import_id),
            },
        )
        drafts_response = await quart_test_client.get(
            f'/api/v1/broadcast/drafts?{_query_scope()}&import_batch_id={import_id}',
            headers=_auth_headers(),
        )
        draft = (await drafts_response.get_json())['data'][0]
        await quart_test_client.post(
            '/api/v1/broadcast/drafts/batch-status',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'draft_ids': [draft['id']],
                'status': 'ready',
            },
        )

        create_response = await quart_test_client.post(
            '/api/v1/broadcast/executions',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'draft_ids': [draft['id']],
                'mode': 'paste_only',
                'operator': 'tester@example.com',
            },
        )
        task_id = (await create_response.get_json())['data']['tasks'][0]['id']

        start_response = await quart_test_client.post(
            f'/api/v1/broadcast/execution-tasks/{task_id}/start',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'operator': 'tester@example.com',
            },
        )
        start_payload = await start_response.get_json()
        assert start_response.status_code == 200
        assert start_payload['data']['error_code'] == 'INPUT_NOT_LOCATED'
        assert start_payload['data']['enter_dispatched'] is False
        assert start_payload['data']['message_sent'] is False
        assert start_payload['data']['terminal_confirmed'] is True

        attempts_response = await quart_test_client.get(
            f'/api/v1/broadcast/execution-tasks/{task_id}/attempts?{_query_scope()}',
            headers=_auth_headers(),
        )
        attempts_payload = await attempts_response.get_json()
        attempt_id = attempts_payload['data'][0]['id']

        evidence_response = await quart_test_client.get(
            f'/api/v1/broadcast/execution-attempts/{attempt_id}/evidence?{_query_scope()}',
            headers=_auth_headers(),
        )
        evidence_payload = await evidence_response.get_json()
        assert evidence_response.status_code == 200
        assert evidence_payload['data']['window_title'] == '企业微信'
        technical_details = json.loads(evidence_payload['data']['technical_details'])
        assert technical_details['error_code'] == 'INPUT_NOT_LOCATED'
        assert technical_details['selected_window']['hwnd'] == '1769682'
        assert technical_details['task_verification_diagnostic']['failureStep'] == 'INPUT_LOOKUP'

    @pytest.mark.asyncio
    async def test_send_execution_uses_executions_api_and_updates_draft_status(
        self,
        quart_test_client,
        fake_broadcast_app,
    ):
        _enable_real_send(fake_broadcast_app)
        runtime_client = _QueuedRuntimeClient(
            [
                {
                    'id': 'runtime-send-success',
                    'status': 'succeeded',
                    'stage': 'sent',
                    'result': {
                        'messageSent': True,
                        'sendKeyCount': 1,
                    },
                }
            ]
        )
        fake_broadcast_app.desktop_automation_service = SimpleNamespace(
            runtime_client=runtime_client,
        )
        drafts = await _create_ready_drafts(
            quart_test_client,
            group_values=['Acme'],
        )

        response = await quart_test_client.post(
            '/api/v1/broadcast/executions',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'draft_ids': [drafts[0]['id']],
                'mode': 'send',
                'operator': 'tester@example.com',
            },
        )
        payload = await response.get_json()

        assert response.status_code == 200
        assert payload['data']['mode'] == 'send'
        assert payload['data']['sent_count'] == 1
        assert payload['data']['failed_count'] == 0
        assert payload['data']['unknown_count'] == 0
        assert payload['data']['items'][0]['outcome'] == 'sent'
        assert runtime_client.requests == [
            {
                'action': 'send_draft',
                'conversationName': 'Acme Group',
                'draftText': 'Hello Acme',
                'idempotencyKey': runtime_client.requests[0]['idempotencyKey'],
                'requestDigest': runtime_client.requests[0]['requestDigest'],
                'attachments': [],
                'sendAuthorized': True,
                'allowAutoSend': True,
                'sendStrategy': 'enter',
            }
        ]

        drafts_response = await quart_test_client.get(
            f'/api/v1/broadcast/drafts?{_query_scope()}',
            headers=_auth_headers(),
        )
        draft_payload = (await drafts_response.get_json())['data'][0]
        assert draft_payload['send_status'] == 'sent'

    @pytest.mark.asyncio
    async def test_send_execution_rejects_invalid_mode(
        self,
        quart_test_client,
        fake_broadcast_app,
    ):
        _enable_real_send(fake_broadcast_app)
        fake_broadcast_app.desktop_automation_service = SimpleNamespace(
            runtime_client=_QueuedRuntimeClient([]),
        )
        drafts = await _create_ready_drafts(quart_test_client, group_values=['Acme'])

        response = await quart_test_client.post(
            '/api/v1/broadcast/executions',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'draft_ids': [drafts[0]['id']],
                'mode': 'invalid-mode',
                'operator': 'tester@example.com',
            },
        )
        payload = await response.get_json()

        assert response.status_code == 400
        assert payload['msg'] == 'BROADCAST_EXECUTION_MODE_INVALID'

    @pytest.mark.asyncio
    async def test_send_execution_rejects_executor_without_send_support(
        self,
        quart_test_client,
        fake_broadcast_app,
        monkeypatch,
    ):
        _enable_real_send(fake_broadcast_app)
        fake_broadcast_app.desktop_automation_service = SimpleNamespace(
            runtime_client=_QueuedRuntimeClient([]),
        )
        drafts = await _create_ready_drafts(quart_test_client, group_values=['Acme'])

        class _UnsupportedSendExecutor:
            def validate_capability(self, _action: str):
                return {
                    'supports_send': False,
                    'supports_attachment_send': False,
                }

        monkeypatch.setattr(
            'langbot.pkg.broadcast.service.build_executor',
            lambda _channel, _gateway: _UnsupportedSendExecutor(),
        )

        response = await quart_test_client.post(
            '/api/v1/broadcast/executions',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'draft_ids': [drafts[0]['id']],
                'mode': 'send',
                'operator': 'tester@example.com',
            },
        )
        payload = await response.get_json()

        assert response.status_code == 400
        assert payload['msg'] == 'EXECUTOR_SEND_UNSUPPORTED'

    @pytest.mark.asyncio
    async def test_send_execution_rejects_attachment_send_without_executor_support(
        self,
        quart_test_client,
        fake_broadcast_app,
        monkeypatch,
    ):
        _enable_real_send(fake_broadcast_app)
        fake_broadcast_app.desktop_automation_service = SimpleNamespace(
            runtime_client=_QueuedRuntimeClient([]),
        )
        draft = (await _create_ready_drafts(quart_test_client, group_values=['Acme']))[0]

        attachment_response = await quart_test_client.post(
            f"/api/v1/broadcast/drafts/{draft['id']}/attachments",
            headers=_auth_headers(),
            form={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
            },
            files={
                'files': FileStorage(
                    stream=BytesIO(b'quote-data'),
                    filename='quote.txt',
                ),
            },
        )
        assert attachment_response.status_code == 200

        await quart_test_client.post(
            '/api/v1/broadcast/drafts/batch-status',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'draft_ids': [draft['id']],
                'status': 'ready',
            },
        )

        class _NoAttachmentSendExecutor:
            def validate_capability(self, _action: str):
                return {
                    'supports_send': True,
                    'supports_attachment_send': False,
                }

        monkeypatch.setattr(
            'langbot.pkg.broadcast.service.build_executor',
            lambda _channel, _gateway: _NoAttachmentSendExecutor(),
        )

        response = await quart_test_client.post(
            '/api/v1/broadcast/executions',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'draft_ids': [draft['id']],
                'mode': 'send',
                'operator': 'tester@example.com',
            },
        )
        payload = await response.get_json()

        assert response.status_code == 400
        assert payload['msg'] == 'EXECUTOR_ATTACHMENT_SEND_UNSUPPORTED'

    @pytest.mark.asyncio
    async def test_send_execution_continues_after_failed_item(
        self,
        quart_test_client,
        fake_broadcast_app,
    ):
        _enable_real_send(fake_broadcast_app)
        runtime_client = _QueuedRuntimeClient(
            [
                {
                    'id': 'runtime-send-failed',
                    'status': 'failed',
                    'stage': 'input_focus',
                    'errorCode': 'INPUT_NOT_LOCATED',
                    'result': {
                        'enterDispatched': False,
                        'messageSent': False,
                        'inputLocated': False,
                    },
                },
                {
                    'id': 'runtime-send-succeeded',
                    'status': 'succeeded',
                    'stage': 'sent',
                    'result': {
                        'messageSent': True,
                    },
                },
            ]
        )
        fake_broadcast_app.desktop_automation_service = SimpleNamespace(
            runtime_client=runtime_client,
        )
        drafts = await _create_ready_drafts(
            quart_test_client,
            group_values=['Acme', 'Northwind'],
        )

        response = await quart_test_client.post(
            '/api/v1/broadcast/executions',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'draft_ids': [draft['id'] for draft in drafts],
                'mode': 'send',
                'operator': 'tester@example.com',
            },
        )
        payload = await response.get_json()

        assert response.status_code == 200
        assert payload['data']['failed_count'] == 1
        assert payload['data']['sent_count'] == 1
        assert [item['outcome'] for item in payload['data']['items']] == ['failed', 'sent']
        assert len(runtime_client.requests) == 2

    @pytest.mark.asyncio
    async def test_send_execution_continues_after_unknown_item(
        self,
        quart_test_client,
        fake_broadcast_app,
    ):
        _enable_real_send(fake_broadcast_app)
        runtime_client = _QueuedRuntimeClient(
            [
                {
                    'id': 'runtime-send-unknown',
                    'status': 'succeeded_with_warning',
                    'stage': 'sent_unconfirmed',
                    'result': {
                        'messageSent': None,
                        'enterDispatched': True,
                        'terminalConfirmed': True,
                        'retryAllowed': False,
                        'sendKeyCount': 1,
                    },
                },
                {
                    'id': 'runtime-send-succeeded',
                    'status': 'succeeded',
                    'stage': 'sent',
                    'result': {
                        'messageSent': True,
                    },
                },
            ]
        )
        fake_broadcast_app.desktop_automation_service = SimpleNamespace(
            runtime_client=runtime_client,
        )
        drafts = await _create_ready_drafts(
            quart_test_client,
            group_values=['Acme', 'Northwind'],
        )

        response = await quart_test_client.post(
            '/api/v1/broadcast/executions',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'draft_ids': [draft['id'] for draft in drafts],
                'mode': 'send',
                'operator': 'tester@example.com',
            },
        )
        payload = await response.get_json()

        assert response.status_code == 200
        assert payload['data']['unknown_count'] == 1
        assert payload['data']['sent_count'] == 1
        assert [item['outcome'] for item in payload['data']['items']] == ['unknown', 'sent']
        assert payload['data']['items'][0]['enter_dispatched'] is True
        assert payload['data']['items'][0]['message_sent'] is None
        assert len(runtime_client.requests) == 2

    @pytest.mark.asyncio
    async def test_send_execution_allows_duplicate_target_conversations(
        self,
        quart_test_client,
        fake_broadcast_app,
    ):
        _enable_real_send(fake_broadcast_app)
        runtime_client = _QueuedRuntimeClient(
            [
                {
                    'id': 'runtime-send-success-1',
                    'status': 'succeeded',
                    'stage': 'sent',
                    'result': {'messageSent': True},
                },
                {
                    'id': 'runtime-send-success-2',
                    'status': 'succeeded',
                    'stage': 'sent',
                    'result': {'messageSent': True},
                },
            ]
        )
        fake_broadcast_app.desktop_automation_service = SimpleNamespace(
            runtime_client=runtime_client,
        )
        drafts = await _create_ready_drafts(
            quart_test_client,
            group_values=['Acme', 'Northwind'],
            conversation_targets={
                'Acme': ('VIP Group', 'vip-group'),
                'Northwind': ('VIP Group', 'vip-group'),
            },
        )

        response = await quart_test_client.post(
            '/api/v1/broadcast/executions',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'draft_ids': [draft['id'] for draft in drafts],
                'mode': 'send',
                'operator': 'tester@example.com',
            },
        )
        payload = await response.get_json()

        assert response.status_code == 200
        assert payload['data']['duplicate_target_count'] == 1
        assert len(payload['data']['items']) == 2
        assert len(runtime_client.requests) == 2

    @pytest.mark.asyncio
    async def test_send_execution_detail_reports_sent_failed_unknown_skipped_and_duplicates(
        self,
        quart_test_client,
        fake_broadcast_app,
    ):
        drafts = await _create_ready_drafts(
            quart_test_client,
            group_values=['Acme', 'Northwind', 'Contoso', 'Fabrikam'],
            conversation_targets={
                'Acme': ('VIP Group', 'vip-group'),
                'Northwind': ('VIP Group', 'vip-group'),
                'Contoso': ('Contoso Group', 'contoso-group'),
                'Fabrikam': ('Fabrikam Group', 'fabrikam-group'),
            },
        )

        async with fake_broadcast_app.persistence_mgr.get_db_engine().begin() as conn:
            repository = fake_broadcast_app.broadcast_service.repository
            batch_id = await repository.create_execution_batch(
                conn,
                {
                    'bot_uuid': 'bot-1',
                    'connector_id': 'wxwork-local',
                    'channel': 'wxwork_database',
                    'mode': 'send',
                    'status': 'completed',
                    'total_tasks': 4,
                    'pending_tasks': 0,
                    'running_tasks': 0,
                    'succeeded_tasks': 1,
                    'failed_tasks': 1,
                    'cancelled_tasks': 1,
                    'interrupted_tasks': 1,
                    'created_by': 'tester@example.com',
                    'last_action_by': 'tester@example.com',
                    'error_message': None,
                    'version': 1,
                },
            )

            task_specs = [
                (drafts[0], 'VIP Group', 'succeeded', True),
                (drafts[1], 'VIP Group', 'failed', False),
                (drafts[2], 'Contoso Group', 'interrupted', True),
                (drafts[3], 'Fabrikam Group', 'cancelled', False),
            ]
            for sequence_no, (draft, target_name, status, send_triggered) in enumerate(task_specs, start=1):
                task_id = await repository.create_execution_task(
                    conn,
                    {
                        'execution_batch_id': batch_id,
                        'draft_id': int(draft['id']),
                        'draft_text_snapshot': str(draft['draft_text']),
                        'target_conversation_snapshot': target_name,
                        'channel': 'wxwork_database',
                        'action': 'send_message',
                        'status': status,
                        'sequence_no': sequence_no,
                        'attempt_count': 1,
                        'max_attempts': 1,
                        'idempotency_key': f'broadcast:{batch_id}:{sequence_no}',
                        'request_digest': f'digest-{sequence_no}',
                        'runtime_task_id': f'runtime-{sequence_no}',
                        'error_code': None if status == 'succeeded' else f'error-{sequence_no}',
                        'error_message': None if status == 'succeeded' else f'message-{sequence_no}',
                        'operator_note': None,
                    },
                )
                attempt_id = await repository.create_execution_attempt(
                    conn,
                    {
                        'execution_task_id': task_id,
                        'attempt_no': 1,
                        'idempotency_key': f'broadcast:{task_id}:1',
                        'request_digest': f'digest-{sequence_no}',
                        'runtime_task_id': f'runtime-{sequence_no}',
                        'request_summary': json.dumps(
                            {
                                'action': 'send_message',
                                'channel': 'wxwork_database',
                                'target_conversation': target_name,
                            },
                            ensure_ascii=False,
                        ),
                        'response_summary': json.dumps(
                            {
                                'id': f'runtime-{sequence_no}',
                                'status': (
                                    'succeeded'
                                    if status == 'succeeded'
                                    else 'failed'
                                    if status == 'failed'
                                    else 'unknown'
                                    if status == 'interrupted'
                                    else 'cancelled'
                                ),
                                'stage': (
                                    'message_sent'
                                    if status == 'succeeded'
                                    else 'pre_send_verification_failed'
                                    if status == 'failed'
                                    else 'terminal_state_unknown'
                                    if status == 'interrupted'
                                    else 'cancelled'
                                ),
                                'errorCode': (
                                    'BROADCAST_RUNTIME_TERMINAL_STATE_UNKNOWN'
                                    if status == 'interrupted'
                                    else None
                                ),
                                'result': (
                                    {
                                        'enterDispatched': True,
                                        'messageSent': True,
                                        'terminalConfirmed': True,
                                        'terminalSource': 'runtime',
                                    }
                                    if status == 'succeeded'
                                    else {
                                        'enterDispatched': False,
                                        'messageSent': False,
                                        'terminalConfirmed': True,
                                        'terminalSource': 'runtime',
                                    }
                                    if status == 'failed'
                                    else {
                                        'enterDispatched': None,
                                        'messageSent': None,
                                        'terminalConfirmed': False,
                                        'terminalSource': 'backend_synthetic_unknown',
                                    }
                                    if status == 'interrupted'
                                    else {
                                        'enterDispatched': False,
                                        'messageSent': False,
                                        'terminalConfirmed': True,
                                        'terminalSource': 'runtime',
                                    }
                                ),
                            },
                            ensure_ascii=False,
                        ),
                        'status': status,
                        'error_code': None if status == 'succeeded' else f'error-{sequence_no}',
                        'error_message': None if status == 'succeeded' else f'message-{sequence_no}',
                        'finished_at': None,
                    },
                )
                await repository.create_execution_evidence(
                    conn,
                    {
                        'execution_attempt_id': int(attempt_id),
                        'window_title': '企业微信',
                        'target_conversation': target_name,
                        'action': 'send_message',
                        'input_located': True,
                        'draft_written': True,
                        'send_triggered': send_triggered,
                        'clipboard_restored': True,
                        'runtime_state': status,
                        'evidence_summary': status,
                        'technical_details': json.dumps(
                            {
                                'status': status,
                                'send_triggered': send_triggered,
                                'enter_dispatched': (
                                    True
                                    if status == 'succeeded'
                                    else False
                                    if status in {'failed', 'cancelled'}
                                    else None
                                ),
                                'message_sent': True if status == 'succeeded' else False,
                                'terminal_source': (
                                    'backend_synthetic_unknown'
                                    if status == 'interrupted'
                                    else 'runtime'
                                ),
                            },
                            ensure_ascii=False,
                        ),
                    },
                )

        response = await quart_test_client.get(
            f'/api/v1/broadcast/executions/{batch_id}?{_query_scope()}',
            headers=_auth_headers(),
        )
        payload = await response.get_json()

        assert response.status_code == 200
        assert payload['data']['sent_count'] == 1
        assert payload['data']['failed_count'] == 1
        assert payload['data']['unknown_count'] == 1
        assert payload['data']['skipped_count'] == 1
        assert payload['data']['duplicate_target_count'] == 1
        assert [item['outcome'] for item in payload['data']['items']] == [
            'sent',
            'failed',
            'unknown',
            'skipped',
        ]
        assert [item['enter_dispatched'] for item in payload['data']['items']] == [
            True,
            False,
            None,
            False,
        ]

    @pytest.mark.asyncio
    async def test_send_execution_rejects_sent_sending_and_unknown_drafts(
        self,
        quart_test_client,
        fake_broadcast_app,
        monkeypatch,
    ):
        _enable_real_send(fake_broadcast_app)
        runtime_client = _QueuedRuntimeClient(
            [
                {
                    'id': 'runtime-send-unknown',
                    'status': 'running',
                    'stage': 'sent_pending_confirmation',
                    'result': {'messageSent': True},
                }
            ]
        )
        fake_broadcast_app.desktop_automation_service = SimpleNamespace(
            runtime_client=runtime_client,
        )

        sent_draft = (await _create_ready_drafts(quart_test_client, group_values=['Acme']))[0]
        await quart_test_client.post(
            '/api/v1/broadcast/drafts/batch-status',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'draft_ids': [sent_draft['id']],
                'status': 'sent',
            },
        )

        unknown_draft = (await _create_ready_drafts(quart_test_client, group_values=['Northwind']))[0]
        await quart_test_client.post(
            '/api/v1/broadcast/executions',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'draft_ids': [unknown_draft['id']],
                'mode': 'send',
                'operator': 'tester@example.com',
            },
        )

        sending_draft = (await _create_ready_drafts(quart_test_client, group_values=['Contoso']))[0]
        async with fake_broadcast_app.persistence_mgr.get_db_engine().begin() as conn:
            batch_id = await fake_broadcast_app.broadcast_service.repository.create_execution_batch(
                conn,
                {
                    'bot_uuid': 'bot-1',
                    'connector_id': 'wxwork-local',
                    'channel': 'wxwork_database',
                    'mode': 'send',
                    'status': 'running',
                    'total_tasks': 1,
                    'pending_tasks': 0,
                    'running_tasks': 1,
                    'succeeded_tasks': 0,
                    'failed_tasks': 0,
                    'cancelled_tasks': 0,
                    'interrupted_tasks': 0,
                    'created_by': 'tester@example.com',
                    'last_action_by': 'tester@example.com',
                    'error_message': None,
                    'version': 1,
                },
            )
            await fake_broadcast_app.broadcast_service.repository.create_execution_task(
                conn,
                {
                    'execution_batch_id': batch_id,
                    'draft_id': int(sending_draft['id']),
                    'draft_text_snapshot': 'Hello Contoso',
                    'target_conversation_snapshot': 'Contoso Group',
                    'channel': 'wxwork_database',
                    'action': 'send_message',
                    'status': 'running',
                    'sequence_no': 1,
                    'attempt_count': 1,
                    'max_attempts': 1,
                    'idempotency_key': 'broadcast:active-send:1',
                    'request_digest': 'digest-active-send',
                    'runtime_task_id': 'runtime-active-send',
                    'error_code': None,
                    'error_message': None,
                    'operator_note': None,
                },
            )

        sent_response = await quart_test_client.post(
            '/api/v1/broadcast/executions',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'draft_ids': [sent_draft['id']],
                'mode': 'send',
                'operator': 'tester@example.com',
            },
        )
        sent_payload = await sent_response.get_json()
        assert sent_response.status_code == 400
        assert sent_payload['msg'] == 'BROADCAST_DRAFT_ALREADY_SENT'

        unknown_response = await quart_test_client.post(
            '/api/v1/broadcast/executions',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'draft_ids': [unknown_draft['id']],
                'mode': 'send',
                'operator': 'tester@example.com',
            },
        )
        unknown_payload = await unknown_response.get_json()
        assert unknown_response.status_code == 400
        assert (
            unknown_payload['msg']
            == 'BROADCAST_SEND_RESULT_UNKNOWN_REQUIRES_REVIEW'
        )

        sending_response = await quart_test_client.post(
            '/api/v1/broadcast/executions',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'draft_ids': [sending_draft['id']],
                'mode': 'send',
                'operator': 'tester@example.com',
            },
        )
        sending_payload = await sending_response.get_json()
        assert sending_response.status_code == 400
        assert sending_payload['msg'] == 'BROADCAST_DRAFT_SEND_IN_PROGRESS'

    @pytest.mark.asyncio
    async def test_unknown_draft_must_be_manually_restored_before_resend(
        self,
        quart_test_client,
        fake_broadcast_app,
    ):
        _enable_real_send(fake_broadcast_app)
        runtime_client = _QueuedRuntimeClient(
            [
                {
                    'id': 'runtime-send-unknown',
                    'status': 'running',
                    'stage': 'sent_pending_confirmation',
                    'result': {'messageSent': True},
                },
                {
                    'id': 'runtime-send-success',
                    'status': 'succeeded',
                    'stage': 'sent',
                    'result': {'messageSent': True},
                },
            ]
        )
        fake_broadcast_app.desktop_automation_service = SimpleNamespace(
            runtime_client=runtime_client,
        )
        draft = (await _create_ready_drafts(quart_test_client, group_values=['Acme']))[0]

        first_send_response = await quart_test_client.post(
            '/api/v1/broadcast/executions',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'draft_ids': [draft['id']],
                'mode': 'send',
                'operator': 'tester@example.com',
            },
        )
        first_send_payload = await first_send_response.get_json()
        assert first_send_response.status_code == 200
        assert first_send_payload['data']['unknown_count'] == 1

        blocked_retry_response = await quart_test_client.post(
            '/api/v1/broadcast/executions',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'draft_ids': [draft['id']],
                'mode': 'send',
                'operator': 'tester@example.com',
            },
        )
        blocked_retry_payload = await blocked_retry_response.get_json()
        assert blocked_retry_response.status_code == 400
        assert (
            blocked_retry_payload['msg']
            == 'BROADCAST_SEND_RESULT_UNKNOWN_REQUIRES_REVIEW'
        )

        restore_response = await quart_test_client.post(
            '/api/v1/broadcast/drafts/batch-status',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'draft_ids': [draft['id']],
                'status': 'pending',
            },
        )
        restore_payload = await restore_response.get_json()
        assert restore_response.status_code == 200
        assert restore_payload['data']['updated_count'] == 1

        resend_response = await quart_test_client.post(
            '/api/v1/broadcast/executions',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'draft_ids': [draft['id']],
                'mode': 'send',
                'operator': 'tester@example.com',
            },
        )
        resend_payload = await resend_response.get_json()
        assert resend_response.status_code == 200
        assert resend_payload['data']['sent_count'] == 1
        assert len(runtime_client.requests) == 2

    @pytest.mark.asyncio
    async def test_retry_unknown_send_task_returns_explicit_rejection(
        self,
        quart_test_client,
        fake_broadcast_app,
    ):
        task_id = await _create_send_execution_task_with_attempt(
            quart_test_client,
            fake_broadcast_app,
            task_status='interrupted',
            response_summary={
                'id': 'runtime-unknown',
                'status': 'unknown',
                'stage': 'terminal_state_unknown',
                'errorCode': 'BROADCAST_RUNTIME_TERMINAL_STATE_UNKNOWN',
                'result': {
                    'enterDispatched': None,
                    'messageSent': None,
                    'terminalConfirmed': False,
                    'terminalSource': 'backend_synthetic_unknown',
                },
            },
            technical_details={
                'message_sent': True,
                'terminal_source': 'backend_synthetic_unknown',
            },
            send_triggered=True,
            error_code='BROADCAST_RUNTIME_TERMINAL_STATE_UNKNOWN',
            error_message='已执行发送操作，请人工检查目标会话',
        )

        task_response = await quart_test_client.get(
            f'/api/v1/broadcast/execution-tasks/{task_id}?{_query_scope()}',
            headers=_auth_headers(),
        )
        task_payload = await task_response.get_json()
        assert task_response.status_code == 200
        assert task_payload['data']['retry_allowed'] is False
        assert task_payload['data']['enter_dispatched'] is None
        assert task_payload['data']['message_sent'] is None
        assert task_payload['data']['terminal_confirmed'] is False
        assert (
            task_payload['data']['terminal_source']
            == 'backend_synthetic_unknown'
        )

        retry_response = await quart_test_client.post(
            f'/api/v1/broadcast/execution-tasks/{task_id}/retry',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'operator': 'tester@example.com',
            },
        )
        retry_payload = await retry_response.get_json()

        assert retry_response.status_code == 400
        assert retry_payload['msg'] == 'BROADCAST_RETRY_SEND_RESULT_UNKNOWN'

    @pytest.mark.asyncio
    async def test_retry_confirmed_pre_send_failure_requeues_task(
        self,
        quart_test_client,
        fake_broadcast_app,
    ):
        task_id = await _create_send_execution_task_with_attempt(
            quart_test_client,
            fake_broadcast_app,
            task_status='failed',
            response_summary={
                'id': 'runtime-failed',
                'status': 'failed',
                'stage': 'pre_send_verification_failed',
                'errorCode': 'BROADCAST_PRE_SEND_VERIFICATION_FAILED',
                'result': {
                    'enterDispatched': False,
                    'messageSent': False,
                    'terminalConfirmed': True,
                    'terminalSource': 'runtime',
                },
            },
            technical_details={
                'enter_dispatched': False,
                'message_sent': False,
                'terminal_source': 'runtime',
            },
            send_triggered=False,
            error_code='BROADCAST_PRE_SEND_VERIFICATION_FAILED',
            error_message='Unable to verify the prepared message before sending',
        )

        before_response = await quart_test_client.get(
            f'/api/v1/broadcast/execution-tasks/{task_id}?{_query_scope()}',
            headers=_auth_headers(),
        )
        before_payload = await before_response.get_json()
        assert before_response.status_code == 200
        assert before_payload['data']['retry_allowed'] is True
        assert before_payload['data']['send_outcome'] == 'failed'
        assert before_payload['data']['enter_dispatched'] is False
        assert before_payload['data']['message_sent'] is False
        assert before_payload['data']['terminal_confirmed'] is True

        retry_response = await quart_test_client.post(
            f'/api/v1/broadcast/execution-tasks/{task_id}/retry',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'operator': 'tester@example.com',
            },
        )
        retry_payload = await retry_response.get_json()
        assert retry_response.status_code == 200
        assert retry_payload['data']['status'] == 'pending'

        after_response = await quart_test_client.get(
            f'/api/v1/broadcast/execution-tasks/{task_id}?{_query_scope()}',
            headers=_auth_headers(),
        )
        after_payload = await after_response.get_json()
        assert after_response.status_code == 200
        assert after_payload['data']['status'] == 'pending'

    @pytest.mark.asyncio
    async def test_mark_sent_updates_state_without_calling_executor(
        self,
        quart_test_client,
        fake_broadcast_app,
    ):
        draft = (await _create_ready_drafts(quart_test_client, group_values=['Acme']))[0]
        runtime_client = _QueuedRuntimeClient([])
        fake_broadcast_app.desktop_automation_service = SimpleNamespace(
            runtime_client=runtime_client,
        )

        response = await quart_test_client.post(
            '/api/v1/broadcast/drafts/batch-status',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'draft_ids': [draft['id']],
                'status': 'sent',
            },
        )
        payload = await response.get_json()

        assert response.status_code == 200
        assert payload['data']['updated_count'] == 1
        assert runtime_client.requests == []
