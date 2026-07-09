from __future__ import annotations

import importlib
import sys
import types
from types import SimpleNamespace
from unittest.mock import AsyncMock

import quart
import pytest

from langbot.pkg.desktop_automation.errors import DesktopAutomationError, RPA_RUNTIME_NOT_AVAILABLE, RUN_NOT_FOUND

core_app_stub = types.ModuleType('langbot.pkg.core.app')
core_app_stub.Application = object
_previous_core_app_module = sys.modules.get('langbot.pkg.core.app')
sys.modules['langbot.pkg.core.app'] = core_app_stub

_router_module = importlib.import_module('langbot.pkg.api.http.controller.groups.bot_database_mode')
BotDatabaseModeRouterGroup = _router_module.BotDatabaseModeRouterGroup
DesktopAutomationRouterGroup = _router_module.DesktopAutomationRouterGroup


pytestmark = pytest.mark.asyncio


async def _make_client():
    app = quart.Quart(__name__)
    ap = SimpleNamespace(
        instance_config=SimpleNamespace(data={'system': {'jwt': {'secret': 'test-secret', 'expire': 3600}}}),
        user_service=SimpleNamespace(
            verify_jwt_token=AsyncMock(return_value='user@example.com'),
            get_user_by_email=AsyncMock(return_value=SimpleNamespace(user='user@example.com')),
        ),
        bot_service=SimpleNamespace(
            get_bot=AsyncMock(return_value={'uuid': 'bot-1', 'adapter': 'wxwork_database', 'enable': True})
        ),
        persistence_mgr=SimpleNamespace(execute_async=AsyncMock()),
        desktop_automation_service=SimpleNamespace(
            create_paste_draft_run=AsyncMock(
                side_effect=DesktopAutomationError(
                    RPA_RUNTIME_NOT_AVAILABLE,
                    'RPA runtime is not integrated yet',
                )
            ),
            create_send_draft_run=AsyncMock(
                side_effect=DesktopAutomationError(
                    RPA_RUNTIME_NOT_AVAILABLE,
                    'RPA runtime is not integrated yet',
                )
            ),
            create_diagnose_run=AsyncMock(
                side_effect=DesktopAutomationError(
                    RPA_RUNTIME_NOT_AVAILABLE,
                    'RPA runtime is not integrated yet',
                )
            ),
            create_conversation_search_run=AsyncMock(
                side_effect=DesktopAutomationError(
                    RPA_RUNTIME_NOT_AVAILABLE,
                    'RPA runtime is not integrated yet',
                )
            ),
            create_history_search_run=AsyncMock(
                side_effect=DesktopAutomationError(
                    RPA_RUNTIME_NOT_AVAILABLE,
                    'RPA runtime is not integrated yet',
                )
            ),
            create_quote_reply_run=AsyncMock(
                side_effect=DesktopAutomationError(
                    RPA_RUNTIME_NOT_AVAILABLE,
                    'RPA runtime is not integrated yet',
                )
            ),
            get_run=AsyncMock(side_effect=DesktopAutomationError(RUN_NOT_FOUND, 'desktop automation run not found')),
            cancel_run=AsyncMock(
                side_effect=DesktopAutomationError(
                    RPA_RUNTIME_NOT_AVAILABLE,
                    'RPA runtime is not integrated yet',
                )
            ),
            get_runtime_status=AsyncMock(
                return_value={
                    'status': 'not_available',
                    'errorCode': RPA_RUNTIME_NOT_AVAILABLE,
                    'runtime_configured': False,
                    'runtime_startable': False,
                    'runtime_reachable': False,
                    'send_enabled': False,
                }
            ),
        ),
    )
    bot_router = BotDatabaseModeRouterGroup(ap, app)
    desktop_router = DesktopAutomationRouterGroup(ap, app)
    await bot_router.initialize()
    await desktop_router.initialize()
    return app.test_client(), ap


if _previous_core_app_module is not None:
    sys.modules['langbot.pkg.core.app'] = _previous_core_app_module
else:
    sys.modules.pop('langbot.pkg.core.app', None)


def _execute_async_side_effect():
    return [
        SimpleNamespace(scalar=lambda: 'wxwork-local'),
        SimpleNamespace(scalar=lambda: 1),
    ]


async def test_send_draft_route_requires_draft_id():
    client, _ap = await _make_client()

    response = await client.post(
        '/api/v1/bots/bot-1/messages/1/send-draft',
        headers={'Authorization': 'Bearer valid-user-token'},
        json={},
    )
    payload = await response.get_json()

    assert response.status_code == 400
    assert payload['msg'] == 'draft_id is required'


async def test_send_draft_route_returns_runtime_not_available():
    client, ap = await _make_client()
    ap.persistence_mgr.execute_async.side_effect = _execute_async_side_effect()

    response = await client.post(
        '/api/v1/bots/bot-1/messages/1/send-draft',
        headers={'Authorization': 'Bearer valid-user-token'},
        json={'draft_id': 31},
    )
    payload = await response.get_json()

    assert response.status_code == 503
    assert payload['msg'] == RPA_RUNTIME_NOT_AVAILABLE
    ap.desktop_automation_service.create_send_draft_run.assert_awaited_once_with(
        'bot-1',
        1,
        31,
        explicit_frontend_send=False,
        python_authorized=False,
        send_strategy=None,
        idempotency_key=None,
    )


async def test_paste_draft_route_requires_idempotency_key_without_calling_service():
    client, ap = await _make_client()
    ap.persistence_mgr.execute_async.side_effect = _execute_async_side_effect()

    response = await client.post(
        '/api/v1/bots/bot-1/messages/1/paste-draft',
        headers={'Authorization': 'Bearer valid-user-token'},
        json={'draft_id': 31},
    )
    payload = await response.get_json()

    assert response.status_code == 400
    assert payload['msg'] == 'IDEMPOTENCY_KEY_REQUIRED'
    ap.desktop_automation_service.create_paste_draft_run.assert_not_called()


async def test_paste_draft_route_rejects_request_body_extra_fields():
    client, ap = await _make_client()
    ap.persistence_mgr.execute_async.side_effect = _execute_async_side_effect()

    response = await client.post(
        '/api/v1/bots/bot-1/messages/1/paste-draft',
        headers={'Authorization': 'Bearer valid-user-token', 'Idempotency-Key': 'idem-1'},
        json={'draft_id': 31, 'unexpected_field': 'forbidden'},
    )
    payload = await response.get_json()

    assert response.status_code == 400
    assert payload['msg'] == 'paste-draft body must contain only draft_id'
    ap.desktop_automation_service.create_paste_draft_run.assert_not_called()


async def test_paste_draft_route_returns_runtime_not_available_and_forwards_idempotency_key():
    client, ap = await _make_client()
    ap.persistence_mgr.execute_async.side_effect = _execute_async_side_effect()

    response = await client.post(
        '/api/v1/bots/bot-1/messages/1/paste-draft',
        headers={'Authorization': 'Bearer valid-user-token', 'Idempotency-Key': 'idem-1'},
        json={'draft_id': 31},
    )
    payload = await response.get_json()

    assert response.status_code == 503
    assert payload['msg'] == RPA_RUNTIME_NOT_AVAILABLE
    ap.desktop_automation_service.create_paste_draft_run.assert_awaited_once_with(
        'bot-1', 1, 31, idempotency_key='idem-1'
    )


async def test_runtime_status_route_returns_not_available_shape():
    client, _ap = await _make_client()

    response = await client.get(
        '/api/v1/desktop-automation/runtime/status',
        headers={'Authorization': 'Bearer valid-user-token'},
    )
    payload = await response.get_json()

    assert response.status_code == 200
    assert payload['data']['status'] == 'not_available'
    assert payload['data']['errorCode'] == RPA_RUNTIME_NOT_AVAILABLE
    assert payload['data']['runtime_startable'] is False


async def test_runtime_status_route_allows_packaged_observation_without_user_token(monkeypatch):
    monkeypatch.setenv('CHATBOT_PACKAGED', '1')
    client, _ap = await _make_client()

    response = await client.get('/api/v1/desktop-automation/runtime/status')
    payload = await response.get_json()

    assert response.status_code == 200
    assert payload['data']['status'] == 'not_available'


async def test_calibration_route_is_removed():
    client, _ap = await _make_client()

    response = await client.post(
        '/api/v1/bots/bot-1/desktop-automation/calibration-sessions',
        headers={'Authorization': 'Bearer valid-user-token'},
        json={},
    )

    assert response.status_code == 404


async def test_conversation_search_route_returns_runtime_not_available():
    client, ap = await _make_client()
    ap.persistence_mgr.execute_async.side_effect = _execute_async_side_effect()

    response = await client.post(
        '/api/v1/bots/bot-1/messages/1/conversation-search',
        headers={'Authorization': 'Bearer valid-user-token'},
        json={'draft_id': 31, 'query_text': '专用测试会话'},
    )
    payload = await response.get_json()

    assert response.status_code == 503
    assert payload['msg'] == RPA_RUNTIME_NOT_AVAILABLE
    ap.desktop_automation_service.create_conversation_search_run.assert_awaited_once_with(
        'bot-1', 1, 31, query_text='专用测试会话'
    )


async def test_history_search_route_returns_runtime_not_available():
    client, ap = await _make_client()
    ap.persistence_mgr.execute_async.side_effect = _execute_async_side_effect()

    response = await client.post(
        '/api/v1/bots/bot-1/messages/1/history-search',
        headers={'Authorization': 'Bearer valid-user-token'},
        json={'draft_id': 31, 'query_text': 'sentinel'},
    )
    payload = await response.get_json()

    assert response.status_code == 503
    assert payload['msg'] == RPA_RUNTIME_NOT_AVAILABLE
    ap.desktop_automation_service.create_history_search_run.assert_awaited_once_with(
        'bot-1', 1, 31, query_text='sentinel'
    )


async def test_quote_reply_route_returns_runtime_not_available():
    client, ap = await _make_client()
    ap.persistence_mgr.execute_async.side_effect = _execute_async_side_effect()

    response = await client.post(
        '/api/v1/bots/bot-1/messages/1/quote-reply',
        headers={'Authorization': 'Bearer valid-user-token'},
        json={'draft_id': 31, 'query_text': 'target message'},
    )
    payload = await response.get_json()

    assert response.status_code == 503
    assert payload['msg'] == RPA_RUNTIME_NOT_AVAILABLE
    ap.desktop_automation_service.create_quote_reply_run.assert_awaited_once_with(
        'bot-1', 1, 31, query_text='target message'
    )
