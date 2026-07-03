from __future__ import annotations

import sys
import types
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import quart

core_app_stub = types.ModuleType('langbot.pkg.core.app')
core_app_stub.Application = object
_previous_core_app_module = sys.modules.get('langbot.pkg.core.app')
sys.modules['langbot.pkg.core.app'] = core_app_stub

from langbot.pkg.api.http.controller.groups.broadcast import (  # noqa: E402
    BroadcastRouterGroup,
)
from langbot.pkg.broadcast.errors import (  # noqa: E402
    BROADCAST_SCOPE_REQUIRED,
    BroadcastError,
)

if _previous_core_app_module is not None:
    sys.modules['langbot.pkg.core.app'] = _previous_core_app_module
else:
    sys.modules.pop('langbot.pkg.core.app', None)


pytestmark = pytest.mark.asyncio


async def _make_client():
    app = quart.Quart(__name__)
    ap = SimpleNamespace(
        user_service=SimpleNamespace(
            verify_jwt_token=AsyncMock(return_value='user@example.com'),
            get_user_by_email=AsyncMock(return_value=SimpleNamespace(user='user@example.com')),
        ),
        broadcast_service=SimpleNamespace(
            validate_scope=AsyncMock(
                side_effect=lambda scope: {
                    'bot_uuid': scope['bot_uuid'],
                    'connector_id': scope['connector_id'],
                }
            ),
            list_templates=AsyncMock(return_value=[]),
            create_template=AsyncMock(
                return_value={
                    'id': 1,
                    'name': 'Arrival Reminder',
                    'content': 'Hello {{name}}',
                    'variables': ['name'],
                    'enabled': True,
                }
            ),
            update_template=AsyncMock(
                return_value={
                    'id': 1,
                    'name': 'Arrival Reminder v2',
                    'content': 'Hi {{name}}',
                    'variables': ['name'],
                    'enabled': False,
                }
            ),
            delete_template=AsyncMock(return_value={'deleted': True}),
            render_template=AsyncMock(
                return_value={
                    'rendered_text': 'Hello Acme',
                    'required_variables': ['name'],
                    'missing_variables': [],
                    'valid': True,
                }
            ),
            get_variable_profile=AsyncMock(return_value={'group_field': None, 'mapping_rules': []}),
            save_variable_profile=AsyncMock(return_value={'group_field': 'customer_name', 'mapping_rules': []}),
            list_group_rules=AsyncMock(return_value=[]),
            create_group_rule=AsyncMock(
                return_value={
                    'id': 1,
                    'source_value': 'Acme',
                    'match_type': 'exact',
                    'match_expression': 'Acme',
                    'target_conversation_name': 'Acme Group',
                    'priority': 1,
                    'enabled': True,
                }
            ),
            update_group_rule=AsyncMock(
                return_value={
                    'id': 1,
                    'source_value': 'Acme',
                    'match_type': 'exact',
                    'match_expression': 'Acme',
                    'target_conversation_name': 'Acme Group',
                    'priority': 2,
                    'enabled': False,
                }
            ),
            delete_group_rule=AsyncMock(return_value={'deleted': True}),
            match_group_rule=AsyncMock(
                return_value={
                    'matched': True,
                    'rule_id': 1,
                    'target_conversation_name': 'Acme Group',
                    'match_type': 'exact',
                }
            ),
            list_group_names=AsyncMock(return_value=[]),
            create_group_names=AsyncMock(return_value={'group_names': []}),
            delete_group_name=AsyncMock(return_value={'deleted': True}),
        ),
    )
    router = BroadcastRouterGroup(ap, app)
    await router.initialize()
    return app.test_client(), ap


async def test_get_templates_uses_query_scope_and_validates_once():
    client, ap = await _make_client()

    response = await client.get(
        '/api/v1/broadcast/templates?bot_uuid=bot-1&connector_id=wxwork-local',
        headers={'Authorization': 'Bearer valid-user-token'},
    )
    payload = await response.get_json()

    assert response.status_code == 200
    assert payload['code'] == 0
    ap.broadcast_service.validate_scope.assert_awaited_once_with(
        {
            'bot_uuid': 'bot-1',
            'connector_id': 'wxwork-local',
        }
    )
    ap.broadcast_service.list_templates.assert_awaited_once()


async def test_render_template_uses_body_scope():
    client, ap = await _make_client()

    response = await client.post(
        '/api/v1/broadcast/templates/render',
        headers={'Authorization': 'Bearer valid-user-token'},
        json={
            'bot_uuid': 'bot-1',
            'connector_id': 'wxwork-local',
            'content': 'Hello {{name}}',
            'variables': {'name': 'Acme'},
        },
    )
    payload = await response.get_json()

    assert response.status_code == 200
    assert payload['data']['rendered_text'] == 'Hello Acme'
    ap.broadcast_service.validate_scope.assert_awaited_once_with(
        {
            'bot_uuid': 'bot-1',
            'connector_id': 'wxwork-local',
        }
    )


async def test_missing_scope_returns_400():
    client, ap = await _make_client()
    ap.broadcast_service.validate_scope = AsyncMock(side_effect=BroadcastError(BROADCAST_SCOPE_REQUIRED))

    response = await client.get(
        '/api/v1/broadcast/templates',
        headers={'Authorization': 'Bearer valid-user-token'},
    )
    payload = await response.get_json()

    assert response.status_code == 400
    assert payload['msg'] == BROADCAST_SCOPE_REQUIRED


async def test_variable_profile_error_returns_code_and_chinese_message_details():
    client, ap = await _make_client()
    ap.broadcast_service.save_variable_profile = AsyncMock(
        side_effect=BroadcastError(
            'BROADCAST_VARIABLE_PROFILE_INVALID',
            '变量配置填写不完整，请检查后重试',
            ['请填写分组字段', '第 2 条规则缺少消息变量'],
        )
    )

    response = await client.put(
        '/api/v1/broadcast/variable-profile',
        headers={'Authorization': 'Bearer valid-user-token'},
        json={
            'bot_uuid': 'bot-1',
            'connector_id': 'wxwork-local',
            'group_field': '',
            'mapping_rules': [],
        },
    )
    payload = await response.get_json()

    assert response.status_code == 400
    assert payload['msg'] == 'BROADCAST_VARIABLE_PROFILE_INVALID'
    assert payload['message'] == '变量配置填写不完整，请检查后重试'
    assert payload['details'] == ['请填写分组字段', '第 2 条规则缺少消息变量']


async def test_get_variable_profile_returns_empty_config_not_404():
    client, ap = await _make_client()

    response = await client.get(
        '/api/v1/broadcast/variable-profile?bot_uuid=bot-1&connector_id=wxwork-local',
        headers={'Authorization': 'Bearer valid-user-token'},
    )
    payload = await response.get_json()

    assert response.status_code == 200
    assert payload['data'] == {'group_field': None, 'mapping_rules': []}


async def test_post_template_uses_body_scope():
    client, ap = await _make_client()

    response = await client.post(
        '/api/v1/broadcast/templates',
        headers={'Authorization': 'Bearer valid-user-token'},
        json={
            'bot_uuid': 'bot-1',
            'connector_id': 'wxwork-local',
            'name': 'Arrival Reminder',
            'content': 'Hello {{name}}',
            'enabled': True,
        },
    )
    payload = await response.get_json()

    assert response.status_code == 200
    assert payload['data']['name'] == 'Arrival Reminder'
    ap.broadcast_service.create_template.assert_awaited_once()


async def test_delete_template_uses_query_scope():
    client, ap = await _make_client()

    response = await client.delete(
        '/api/v1/broadcast/templates/1?bot_uuid=bot-1&connector_id=wxwork-local',
        headers={'Authorization': 'Bearer valid-user-token'},
    )
    payload = await response.get_json()

    assert response.status_code == 200
    assert payload['data'] == {'deleted': True}
    ap.broadcast_service.delete_template.assert_awaited_once_with(
        1,
        {'bot_uuid': 'bot-1', 'connector_id': 'wxwork-local'},
    )
