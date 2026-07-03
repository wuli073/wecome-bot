from __future__ import annotations

import pytest


pytestmark = pytest.mark.asyncio


class _FakeGateway:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def assert_force_disable_send(self) -> None:
        return None

    async def create_paste_task(self, **kwargs):
        self.calls.append(('paste', kwargs))
        return {
            'id': 'runtime-task-1',
            'status': 'succeeded',
            'stage': 'pasted_to_input',
            'action': 'paste_draft',
            'result': {'messageSent': False, 'clipboardRestoreFailed': False},
        }

    async def create_send_task(self, **kwargs):
        self.calls.append(('send', kwargs))
        return {
            'id': 'runtime-task-2',
            'status': 'succeeded',
            'stage': 'message_sent',
            'action': 'send_message',
            'result': {'messageSent': True, 'clipboardRestoreFailed': False},
        }

    async def cancel_task(self, runtime_task_id: str):
        return {'id': runtime_task_id, 'status': 'cancelled'}

    async def query_task(self, runtime_task_id: str):
        return {'id': runtime_task_id, 'status': 'succeeded'}


async def test_wecom_executor_exposes_capabilities_and_normalizes_paste_evidence():
    from langbot.pkg.broadcast.executors.wecom import WeComDraftExecutor

    executor = WeComDraftExecutor(_FakeGateway())
    capability = executor.validate_capability('paste_draft')

    assert capability['supports_paste'] is True
    assert capability['supports_send'] is True

    result = await executor.paste_draft(
        conversation_name='Acme Group',
        draft_text='Hello Acme',
        idempotency_key='broadcast:1:1',
        request_digest='digest-1',
    )
    evidence = executor.normalize_evidence(result)
    assert evidence['action'] == 'paste_draft'
    assert evidence['send_triggered'] is False
    assert evidence['draft_written'] is True


async def test_wecom_executor_supports_isolated_send_message_path():
    from langbot.pkg.broadcast.executors.wecom import WeComDraftExecutor

    gateway = _FakeGateway()
    executor = WeComDraftExecutor(gateway)

    result = await executor.send_message(
        conversation_name='Acme Group',
        message_text='Hello Acme',
        idempotency_key='broadcast:1:2',
        request_digest='digest-2',
        confirmation_token='confirm-123',
    )
    evidence = executor.normalize_evidence(result)

    assert gateway.calls == [
        (
            'send',
            {
                'conversation_name': 'Acme Group',
                'message_text': 'Hello Acme',
                'idempotency_key': 'broadcast:1:2',
                'request_digest': 'digest-2',
                'confirmation_token': 'confirm-123',
            },
        )
    ]
    assert evidence['action'] == 'send_message'
    assert evidence['send_triggered'] is True
