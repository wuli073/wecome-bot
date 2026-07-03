from __future__ import annotations

import pytest

from langbot.pkg.broadcast.errors import BroadcastError


pytestmark = pytest.mark.asyncio


class _FakeRuntimeClient:
    def __init__(self) -> None:
        self.requests: list[dict] = []
        self.cancelled_task_ids: list[str] = []

    async def health(self):
        return {'status': 'ready', 'protocolVersion': '1'}

    async def capabilities(self):
        return {'supportsPaste': True, 'supportsSend': False}

    async def create_task(self, *, request):
        self.requests.append(request)
        return {'id': 'task-1', 'status': 'queued', 'stage': 'queued', 'result': {'ok': True}}

    async def get_task(self, task_id: str):
        return {'id': task_id, 'status': 'queued', 'stage': 'queued'}

    async def cancel_task(self, task_id: str):
        self.cancelled_task_ids.append(task_id)
        return {'id': task_id, 'status': 'cancelled', 'stage': 'cancelled'}


async def test_runtime_gateway_reuses_paste_contract_payload():
    from langbot.pkg.broadcast.runtime_gateway import BroadcastRuntimeGateway

    runtime_client = _FakeRuntimeClient()
    gateway = BroadcastRuntimeGateway(runtime_client)

    result = await gateway.create_paste_task(
        conversation_name='Acme Group',
        draft_text='Hello Acme',
        idempotency_key='broadcast:1:1',
        request_digest='digest-1',
    )

    assert result['id'] == 'task-1'
    assert runtime_client.requests == [
        {
            'action': 'paste_draft',
            'conversationName': 'Acme Group',
            'draftText': 'Hello Acme',
            'idempotencyKey': 'broadcast:1:1',
            'requestDigest': 'digest-1',
        }
    ]


async def test_runtime_gateway_keeps_send_contract_separate():
    from langbot.pkg.broadcast.runtime_gateway import BroadcastRuntimeGateway

    runtime_client = _FakeRuntimeClient()
    gateway = BroadcastRuntimeGateway(runtime_client)

    result = await gateway.create_send_task(
        conversation_name='Acme Group',
        message_text='Hello Acme',
        idempotency_key='broadcast:1:2',
        request_digest='digest-2',
        confirmation_token='confirm-123',
    )

    assert result['id'] == 'task-1'
    assert runtime_client.requests == [
        {
            'action': 'send_message',
            'conversationName': 'Acme Group',
            'messageText': 'Hello Acme',
            'idempotencyKey': 'broadcast:1:2',
            'requestDigest': 'digest-2',
            'confirmationToken': 'confirm-123',
        }
    ]


async def test_runtime_gateway_requires_force_disable_send_for_phase4(monkeypatch):
    from langbot.pkg.broadcast.runtime_gateway import BroadcastRuntimeGateway

    runtime_client = _FakeRuntimeClient()
    gateway = BroadcastRuntimeGateway(runtime_client)

    monkeypatch.delenv('LANGBOT_RPA_FORCE_DISABLE_SEND', raising=False)
    with pytest.raises(BroadcastError, match='BROADCAST_EXECUTION_SAFETY_LOCK_REQUIRED'):
        gateway.assert_force_disable_send()

    monkeypatch.setenv('LANGBOT_RPA_FORCE_DISABLE_SEND', '1')
    gateway.assert_force_disable_send()


async def test_runtime_gateway_exposes_query_and_cancel_task():
    from langbot.pkg.broadcast.runtime_gateway import BroadcastRuntimeGateway

    runtime_client = _FakeRuntimeClient()
    gateway = BroadcastRuntimeGateway(runtime_client)

    task = await gateway.query_task('runtime-1')
    cancelled = await gateway.cancel_task('runtime-1')

    assert task['id'] == 'runtime-1'
    assert cancelled['status'] == 'cancelled'
    assert runtime_client.cancelled_task_ids == ['runtime-1']
