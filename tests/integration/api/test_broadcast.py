from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest
import sqlalchemy
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
        assert invalid_profile_payload['message'] == '变量配置填写有误，请按提示修改'
        assert invalid_profile_payload['details'] == ['第 1 条规则的多条数据处理方式无效']

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
        assert actionable_profile_payload['message'] == '变量配置填写不完整，请检查后重试'
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

        list_names_response = await quart_test_client.get(
            f'/api/v1/broadcast/group-names?{_query_scope()}',
            headers=_auth_headers(),
        )
        list_names_payload = (await list_names_response.get_json())['data']
        assert [item['name'] for item in list_names_payload] == ['Acme Group', 'Northwind Group']

        delete_name_wrong_scope = await quart_test_client.delete(
            f"/api/v1/broadcast/group-names/{list_names_payload[0]['id']}?{_query_scope(bot_uuid='bot-2', connector_id='wxwork-other')}",
            headers=_auth_headers(),
        )
        wrong_scope_payload = await delete_name_wrong_scope.get_json()
        assert delete_name_wrong_scope.status_code == 404
        assert wrong_scope_payload['msg'] == 'BROADCAST_GROUP_NAME_NOT_FOUND'
