from __future__ import annotations

import pytest

from langbot.pkg.desktop_automation.client import DesktopRuntimeClient, RuntimeAuthError


pytestmark = pytest.mark.asyncio


async def test_runtime_client_health_and_status_use_bearer_auth():
    calls: list[tuple[str, str, dict[str, str], dict | None]] = []

    async def transport(method: str, path: str, *, headers: dict[str, str], json: dict | None = None):
        calls.append((method, path, headers, json))
        if path == '/healthz':
            return 200, {
                'status': 'ready',
                'protocolVersion': '1',
                'runtimeVersion': '0.1.0',
                'uptimeMs': 10,
            }
        if path == '/v1/runtime/status':
            return 200, {
                'windowingAvailable': True,
                'captureAvailable': True,
                'inputAvailable': False,
                'providerHubReady': False,
                'activeTaskCount': 0,
                'lastErrorCode': None,
                'displaySummary': [],
            }
        raise AssertionError(path)

    client = DesktopRuntimeClient(
        base_url='http://127.0.0.1:5812',
        token='secret-token',
        transport=transport,
    )

    health = await client.health()
    status = await client.capabilities()

    assert health['status'] == 'ready'
    assert status['windowingAvailable'] is True
    assert calls[0][2]['Authorization'] == 'Bearer secret-token'
    assert calls[1][2]['Authorization'] == 'Bearer secret-token'


async def test_runtime_client_raises_auth_error_for_401():
    async def transport(method: str, path: str, *, headers: dict[str, str], json: dict | None = None):
        return 401, {'errorCode': 'RUNTIME_UNAUTHORIZED', 'message': 'Invalid bearer token'}

    client = DesktopRuntimeClient(
        base_url='http://127.0.0.1:5812',
        token='secret-token',
        transport=transport,
    )

    with pytest.raises(RuntimeAuthError) as exc_info:
        await client.health()

    assert exc_info.value.error_code == 'RUNTIME_UNAUTHORIZED'


async def test_runtime_client_task_routes_forward_json_payloads():
    calls: list[tuple[str, str, dict | None]] = []

    async def transport(method: str, path: str, *, headers: dict[str, str], json: dict | None = None):
        calls.append((method, path, json))
        return 200, {'ok': True, 'path': path}

    client = DesktopRuntimeClient(
        base_url='http://127.0.0.1:5812',
        token='secret-token',
        transport=transport,
    )

    await client.create_task(request={'action': 'paste'})
    await client.get_task('task-1')
    await client.cancel_task('task-1')
    await client.create_task(request={'action': 'conversation_search'})
    await client.create_task(request={'action': 'history_search'})
    await client.create_task(request={'action': 'quote_reply'})

    assert calls == [
        ('POST', '/v1/tasks/paste-draft', {'action': 'paste'}),
        ('GET', '/v1/tasks/task-1', None),
        ('POST', '/v1/tasks/task-1/cancel', None),
        ('POST', '/v1/tasks/conversation-search', {'action': 'conversation_search'}),
        ('POST', '/v1/tasks/history-search', {'action': 'history_search'}),
        ('POST', '/v1/tasks/quote-reply', {'action': 'quote_reply'}),
    ]
