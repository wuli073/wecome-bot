from __future__ import annotations

import pytest

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


class _FakeDesktopAutomationService:
    def __init__(self) -> None:
        self.requests: list[dict] = []
        self.cancelled_task_ids: list[str] = []

    async def runtime_health(self):
        return {'status': 'ready', 'protocolVersion': '1', 'runtimeVersion': '0.1.0'}

    async def runtime_capabilities(self):
        return {'supportsPaste': True, 'supportsSend': False}

    async def runtime_create_task(self, request):
        self.requests.append(request)
        return {'id': 'task-1', 'status': 'queued', 'stage': 'queued', 'result': {'ok': True}}

    async def runtime_get_task(self, task_id: str):
        return {'id': task_id, 'status': 'queued', 'stage': 'queued'}

    async def runtime_cancel_task(self, task_id: str):
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
            'attachments': [],
        }
    ]


async def test_runtime_gateway_sends_task_level_attachment_root_and_attachment_relative_paths():
    from langbot.pkg.broadcast.runtime_gateway import BroadcastRuntimeGateway

    runtime_client = _FakeRuntimeClient()
    gateway = BroadcastRuntimeGateway(runtime_client)

    await gateway.create_paste_task(
        conversation_name='Acme Group',
        draft_text='Hello Acme',
        idempotency_key='broadcast:1:3',
        request_digest='digest-3',
        attachment_root='C:/runtime/broadcast_attachments',
        attachments=[
            {
                'relativePath': 'bot-1/drafts/1/quote.pdf',
                'filename': 'quote.pdf',
                'size': 8,
                'sha256': 'digest-quote',
            }
        ],
    )

    assert runtime_client.requests[-1] == {
        'action': 'paste_draft',
        'conversationName': 'Acme Group',
        'draftText': 'Hello Acme',
        'idempotencyKey': 'broadcast:1:3',
        'requestDigest': 'digest-3',
        'attachmentRoot': 'C:/runtime/broadcast_attachments',
        'attachments': [
            {
                'relativePath': 'bot-1/drafts/1/quote.pdf',
                'filename': 'quote.pdf',
                'size': 8,
                'sha256': 'digest-quote',
            }
        ],
    }
    assert 'localPath' not in runtime_client.requests[-1]['attachments'][0]


async def test_runtime_gateway_keeps_send_contract_separate():
    from langbot.pkg.broadcast.runtime_gateway import BroadcastRuntimeGateway

    runtime_client = _FakeRuntimeClient()
    gateway = BroadcastRuntimeGateway(runtime_client)

    result = await gateway.create_send_task(
        conversation_name='Acme Group',
        message_text='Hello Acme',
        idempotency_key='broadcast:1:2',
        request_digest='digest-2',
        attachment_root='C:/runtime/broadcast_attachments',
        attachments=[
            {
                'relativePath': 'bot-1/drafts/1/quote.pdf',
                'filename': 'quote.pdf',
                'size': 8,
                'sha256': 'digest-quote',
            }
        ],
    )

    assert result['id'] == 'task-1'
    assert runtime_client.requests == [
        {
            'action': 'send_draft',
            'conversationName': 'Acme Group',
            'draftText': 'Hello Acme',
            'idempotencyKey': 'broadcast:1:2',
            'requestDigest': 'digest-2',
            'attachmentRoot': 'C:/runtime/broadcast_attachments',
            'attachments': [
                {
                    'relativePath': 'bot-1/drafts/1/quote.pdf',
                    'filename': 'quote.pdf',
                    'size': 8,
                    'sha256': 'digest-quote',
                }
            ],
            'sendAuthorized': True,
            'allowAutoSend': True,
            'sendStrategy': 'enter',
        }
    ]


async def test_runtime_gateway_exposes_query_and_cancel_task():
    from langbot.pkg.broadcast.runtime_gateway import BroadcastRuntimeGateway

    runtime_client = _FakeRuntimeClient()
    gateway = BroadcastRuntimeGateway(runtime_client)

    task = await gateway.query_task('runtime-1')
    cancelled = await gateway.cancel_task('runtime-1')

    assert task['id'] == 'runtime-1'
    assert cancelled['status'] == 'cancelled'
    assert runtime_client.cancelled_task_ids == ['runtime-1']


async def test_runtime_gateway_uses_desktop_automation_service_public_runtime_interface():
    from langbot.pkg.broadcast.runtime_gateway import BroadcastRuntimeGateway

    desktop_automation_service = _FakeDesktopAutomationService()
    gateway = BroadcastRuntimeGateway(desktop_automation_service)

    health = await gateway.health_check()
    capabilities = await gateway.get_capabilities()
    created = await gateway.create_paste_task(
        conversation_name='Acme Group',
        draft_text='Hello Acme',
        idempotency_key='broadcast:1:1',
        request_digest='digest-1',
    )
    queried = await gateway.query_task('runtime-1')
    cancelled = await gateway.cancel_task('runtime-1')

    assert health['status'] == 'ready'
    assert capabilities['supportsPaste'] is True
    assert created['id'] == 'task-1'
    assert queried['id'] == 'runtime-1'
    assert cancelled['status'] == 'cancelled'
    assert desktop_automation_service.requests == [
        {
            'action': 'paste_draft',
            'conversationName': 'Acme Group',
            'draftText': 'Hello Acme',
            'idempotencyKey': 'broadcast:1:1',
            'requestDigest': 'digest-1',
            'attachments': [],
        }
    ]
    assert desktop_automation_service.cancelled_task_ids == ['runtime-1']
