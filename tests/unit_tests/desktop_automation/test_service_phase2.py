from __future__ import annotations

from types import SimpleNamespace

import pytest

from langbot.pkg.database_mode.events import DatabaseModeEventBus
from langbot.pkg.desktop_automation.errors import (
    CONVERSATION_NAME_NOT_UNIQUE,
    CONVERSATION_NAME_REQUIRED,
    DRAFT_TEXT_REQUIRED,
    DesktopAutomationError,
)
from langbot.pkg.desktop_automation.service import DesktopAutomationService


pytestmark = pytest.mark.asyncio


class _FakePersistenceManager:
    def serialize_model(self, model, data, masked_columns=None):
        return dict(vars(data))


class _Repo:
    def __init__(self):
        self.run = None
        self.task_payloads = []
        self.conversation_name = 'Customer A'
        self.draft_text = 'Hello draft'
        self.conversation_name_count = 1

    async def get_message_context(self, bot_uuid, message_id, draft_id):
        return {
            'conversation': {
                'id': 20,
                'connector_id': 'wxwork-local',
                'external_conversation_id': 'conv-20',
                'conversation_name': self.conversation_name,
            },
            'draft': {
                'id': draft_id,
                'bot_uuid': bot_uuid,
                'message_id': message_id,
                'content': self.draft_text,
                'status': 'active',
            },
            'latest_succeeded_send_run': None,
        }

    async def find_run_by_request_digest(self, request_digest):
        return None

    async def create_run(self, payload):
        self.run = SimpleNamespace(id=1, **payload)
        return self.run

    async def update_run_status(self, run_id, **changes):
        for key, value in changes.items():
            setattr(self.run, key, value)
        return self.run

    async def count_conversations_by_name(self, connector_id, conversation_name):
        assert connector_id == 'wxwork-local'
        assert conversation_name == self.conversation_name.strip()
        return self.conversation_name_count


class _RuntimeClient:
    def __init__(self, task):
        self.task = task
        self.requests = []

    async def create_task(self, *, request):
        self.requests.append(request)
        return self.task


class _RuntimeProcessManager:
    def __init__(self, runtime_client, runtime_info=None):
        self.runtime_client = runtime_client
        self.runtime_info = runtime_info or {
            'pid': 4321,
            'host': '127.0.0.1',
            'port': 55123,
            'protocolVersion': '2',
            'runtimeVersion': '0.1.0',
            'token': 'redacted-token',
        }
        self.client = runtime_client
        self.ensure_started_calls = 0

    async def ensure_started(self):
        self.ensure_started_calls += 1
        return dict(self.runtime_info)


def _service(task):
    ap = SimpleNamespace(
        instance_config=SimpleNamespace(data={'desktop_automation': {'stale_run_seconds': 300}}),
        persistence_mgr=_FakePersistenceManager(),
        database_mode_event_bus=DatabaseModeEventBus(),
    )
    repo = _Repo()
    client = _RuntimeClient(task)
    return DesktopAutomationService(ap, repository=repo, runtime_client=client), repo, client


async def test_paste_only_creates_run_and_never_marks_message_sent():
    service, repo, client = _service(
        {
            'id': 'task-1',
            'status': 'succeeded',
            'stage': 'pasted_to_input',
            'sendAuthorized': False,
            'messageSent': False,
            'pasteAttemptCount': 1,
            'ctrlVCount': 1,
            'focusAttemptCount': 1,
            'beforeImageDigest': 'before-digest',
            'afterImageDigest': 'after-digest',
            'clipboardSnapshotDigest': 'clipboard-digest',
        }
    )

    run = await service.create_paste_draft_run('bot-1', 10, 30, idempotency_key='idem-1')

    assert run['status'] == 'succeeded'
    assert run['stage'] == 'pasted_to_input'
    assert run['execution_mode'] == 'paste_only'
    assert run['result_evidence']['sendAuthorized'] is False
    assert run['result_evidence']['messageSent'] is False
    assert run['result_evidence']['messageSent'] is False
    assert client.requests[0] == {
        'action': 'paste_draft',
        'idempotencyKey': 'idem-1',
        'requestDigest': repo.run.request_digest,
        'conversationName': 'Customer A',
        'draftText': 'Hello draft',
    }


async def test_paste_only_preserves_clipboard_warning():
    service, _repo, _client = _service(
        {
            'id': 'task-2',
            'status': 'succeeded_with_warning',
            'stage': 'pasted_to_input',
            'sendAuthorized': False,
            'messageSent': False,
            'clipboardRestoreFailed': True,
        }
    )

    run = await service.create_paste_draft_run('bot-1', 10, 30, idempotency_key='idem-1')

    assert run['status'] == 'succeeded_with_warning'
    assert run['result_evidence']['clipboardRestoreFailed'] is True


async def test_paste_only_runtime_request_excludes_removed_context_fields():
    service, _repo, client = _service(
        {
            'id': 'task-ctx-1',
            'status': 'succeeded',
            'stage': 'pasted_to_input',
            'sendAuthorized': False,
            'messageSent': False,
        }
    )

    await service.create_paste_draft_run('bot-1', 10, 30, idempotency_key='same-idem')

    assert client.requests[0]['idempotencyKey'] == 'same-idem'
    for forbidden_key in (
        'profile',
        'windowBinding',
        'windowKey',
        'regionProfile',
        'calibrationSessionId',
        'humanConfirmationToken',
        'targetConversation',
    ):
        assert forbidden_key not in client.requests[0]


async def test_paste_only_uses_runtime_process_manager_client_without_profile_validation():
    ap = SimpleNamespace(
        instance_config=SimpleNamespace(data={'desktop_automation': {'stale_run_seconds': 300}}),
        persistence_mgr=_FakePersistenceManager(),
        database_mode_event_bus=DatabaseModeEventBus(),
    )
    repo = _Repo()
    client = _RuntimeClient(
        {
            'id': 'task-runtime-1',
            'status': 'succeeded',
            'stage': 'pasted_to_input',
            'sendAuthorized': False,
            'messageSent': False,
        }
    )
    runtime_process_manager = _RuntimeProcessManager(client)
    service = DesktopAutomationService(ap, repository=repo, runtime_process_manager=runtime_process_manager)

    run = await service.create_paste_draft_run('bot-1', 10, 30, idempotency_key='idem-runtime-1')

    assert runtime_process_manager.ensure_started_calls == 1
    assert run['status'] == 'succeeded'
    assert run['stage'] == 'pasted_to_input'
    assert run['last_error_code'] is None
    assert run['result_evidence']['stage'] == 'pasted_to_input'
    assert 'profile' not in client.requests[0]
    assert 'regionProfile' not in client.requests[0]


async def test_paste_only_rejects_empty_conversation_name():
    service, repo, _client = _service({'id': 'task-1', 'status': 'succeeded', 'stage': 'pasted_to_input'})
    repo.conversation_name = '   '

    with pytest.raises(DesktopAutomationError) as exc_info:
        await service.create_paste_draft_run('bot-1', 10, 30, idempotency_key='idem-1')

    assert exc_info.value.code == CONVERSATION_NAME_REQUIRED


async def test_paste_only_rejects_non_unique_local_conversation_name():
    service, repo, _client = _service({'id': 'task-1', 'status': 'succeeded', 'stage': 'pasted_to_input'})
    repo.conversation_name_count = 2

    with pytest.raises(DesktopAutomationError) as exc_info:
        await service.create_paste_draft_run('bot-1', 10, 30, idempotency_key='idem-1')

    assert exc_info.value.code == CONVERSATION_NAME_NOT_UNIQUE


async def test_paste_only_rejects_empty_draft_text():
    service, repo, _client = _service({'id': 'task-1', 'status': 'succeeded', 'stage': 'pasted_to_input'})
    repo.draft_text = '   '

    with pytest.raises(DesktopAutomationError) as exc_info:
        await service.create_paste_draft_run('bot-1', 10, 30, idempotency_key='idem-1')

    assert exc_info.value.code == DRAFT_TEXT_REQUIRED


async def test_auto_send_requires_explicit_authorization():
    service, _repo, _client = _service({'id': 'task-3', 'status': 'succeeded', 'stage': 'sent_with_mock_driver'})

    with pytest.raises(DesktopAutomationError) as exc_info:
        await service.create_send_draft_run('bot-1', 10, 30)

    assert exc_info.value.code == 'AUTO_SEND_NOT_AUTHORIZED'


async def test_conversation_search_creates_non_sending_runtime_run():
    service, _repo, client = _service(
        {
            'id': 'task-cs-1',
            'status': 'succeeded',
            'stage': 'conversation_selected',
            'messageSent': False,
            'resultCount': 1,
            'selectedResultIndex': 0,
            'confidence': 0.99,
        }
    )

    run = await service.create_conversation_search_run('bot-1', 10, 30, query_text='专用测试会话')

    assert run['status'] == 'succeeded'
    assert run['result_evidence']['messageSent'] is False
    assert client.requests[0]['action'] == 'conversation_search'
    assert client.requests[0]['queryText'] == '专用测试会话'


async def test_history_search_creates_non_sending_runtime_run():
    service, _repo, client = _service(
        {
            'id': 'task-hs-1',
            'status': 'succeeded',
            'stage': 'history_result_located',
            'messageSent': False,
            'resultCount': 1,
            'selectedResultIndex': 0,
            'confidence': 0.88,
        }
    )

    run = await service.create_history_search_run('bot-1', 10, 30, query_text='sentinel')

    assert run['status'] == 'succeeded'
    assert client.requests[0]['action'] == 'history_search'
    assert client.requests[0]['queryText'] == 'sentinel'
    assert run['result_evidence']['messageSent'] is False


async def test_quote_reply_creates_non_sending_runtime_run():
    service, _repo, client = _service(
        {
            'id': 'task-qr-1',
            'status': 'succeeded',
            'stage': 'quote_prepared',
            'messageSent': False,
            'quotePrepared': True,
            'pasteAttemptCount': 1,
            'ctrlVCount': 1,
        }
    )

    run = await service.create_quote_reply_run('bot-1', 10, 30, query_text='target message')

    assert run['status'] == 'succeeded'
    assert client.requests[0]['action'] == 'quote_reply'
    assert client.requests[0]['queryText'] == 'target message'
    assert run['result_evidence']['messageSent'] is False
