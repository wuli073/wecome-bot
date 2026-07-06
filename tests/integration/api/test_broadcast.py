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


@pytest.mark.usefixtures('mock_circular_import_chain')
class TestBroadcastApi:
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
        assert upload_payload['data']['matched_rows'] == 2
        assert upload_payload['data']['unmatched_rows'] == 0
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
        assert [row['match_status'] for row in detail_payload['data']['rows']] == ['matched', 'matched', 'invalid']
        assert detail_payload['data']['rows'][0]['matched_conversation_name'] == 'Acme Group'
        assert detail_payload['data']['rows'][1]['matched_conversation_name'] == 'Northwind Team'
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
        await quart_test_client.post(
            f'/api/v1/broadcast/imports/{import_id}/generate-drafts',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'template_id': template_id,
            },
        )

        list_response = await quart_test_client.get(
            f'/api/v1/broadcast/drafts?{_query_scope()}&import_batch_id={import_id}',
            headers=_auth_headers(),
        )
        drafts = (await list_response.get_json())['data']
        matched_draft = next(item for item in drafts if item['status'] == 'pending_review')
        invalid_rows = await fake_broadcast_app.broadcast_service.repository.list_drafts(
            bot_uuid='bot-1',
            connector_id='wxwork-local',
            import_batch_id=import_id,
            status='invalid',
        )
        invalid_draft_id = int(invalid_rows[0].id)

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
    async def test_drafts_list_audit_filters_map_legacy_queries_and_hide_invalid(self, quart_test_client):
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
        await quart_test_client.post(
            f'/api/v1/broadcast/imports/{import_id}/generate-drafts',
            headers=_auth_headers(),
            json={
                'bot_uuid': 'bot-1',
                'connector_id': 'wxwork-local',
                'template_id': template_id,
            },
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
                    'protocolVersion': '1',
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


    async def test_execution_task_start_route_preserves_succeeded_with_warning_status(
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
                        'clipboardRestoreFailed': False,
                        'warning': 'PASTE_RESULT_NOT_VERIFIED',
                        'contentVerified': False,
                        'draftWritten': True,
                        'inputLocated': False,
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
                    'protocolVersion': '1',
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
        assert start_payload['data']['status'] == 'succeeded_with_warning'

        attempts_response = await quart_test_client.get(
            f'/api/v1/broadcast/execution-tasks/{task_id}/attempts?{_query_scope()}',
            headers=_auth_headers(),
        )
        attempts_payload = await attempts_response.get_json()
        assert attempts_payload['data'][0]['status'] == 'succeeded_with_warning'

        evidence_response = await quart_test_client.get(
            f"/api/v1/broadcast/execution-attempts/{attempts_payload['data'][0]['id']}/evidence?{_query_scope()}",
            headers=_auth_headers(),
        )
        evidence_payload = await evidence_response.get_json()
        assert evidence_payload['data']['evidence_summary'] == '已写入，附件待人工确认'
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
                    'protocolVersion': '1',
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
