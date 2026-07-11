from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from langbot.pkg.database_mode.events import DatabaseModeEventBus
from langbot.pkg.desktop_automation.errors import (
    DesktopAutomationError,
    IDEMPOTENCY_KEY_REQUIRED,
    RPA_RUNTIME_NOT_AVAILABLE,
    RUN_NOT_FOUND,
    TASK_CANCELLED,
)
from langbot.pkg.desktop_automation.service import DesktopAutomationService


pytestmark = pytest.mark.asyncio


class _FakePersistenceManager:
    def serialize_model(self, model, data, masked_columns=None):
        masked_columns = masked_columns or []
        return {
            column.name: getattr(data, column.name)
            for column in model.__table__.columns
            if column.name not in masked_columns
        }


def _build_service(*, repository=None, runtime_process_manager=None):
    ap = SimpleNamespace(
        instance_config=SimpleNamespace(
            data={
                'desktop_automation': {
                    'enabled': True,
                    'stale_run_seconds': 300,
                }
            }
        ),
        bot_service=SimpleNamespace(get_bot=AsyncMock()),
        persistence_mgr=_FakePersistenceManager(),
        database_mode_event_bus=DatabaseModeEventBus(),
        task_mgr=SimpleNamespace(create_task=lambda coro, **kwargs: asyncio.create_task(coro)),
        logger=SimpleNamespace(
            info=lambda *args, **kwargs: None,
            warning=lambda *args, **kwargs: None,
            exception=lambda *args, **kwargs: None,
        ),
    )
    return DesktopAutomationService(
        ap,
        repository=repository,
        runtime_process_manager=runtime_process_manager,
    )


def _build_ap():
    return SimpleNamespace(
        instance_config=SimpleNamespace(
            data={
                'desktop_automation': {
                    'enabled': True,
                    'stale_run_seconds': 300,
                }
            }
        ),
        bot_service=SimpleNamespace(get_bot=AsyncMock()),
        persistence_mgr=_FakePersistenceManager(),
        database_mode_event_bus=DatabaseModeEventBus(),
        task_mgr=SimpleNamespace(create_task=lambda coro, **kwargs: asyncio.create_task(coro)),
        logger=SimpleNamespace(
            info=lambda *args, **kwargs: None,
            warning=lambda *args, **kwargs: None,
            exception=lambda *args, **kwargs: None,
        ),
    )


class _FakeRepository:
    def __init__(self):
        self.created_run = None
        self.reconciled = False
        self.current_run = None

    async def create_run(self, payload: dict):
        self.created_run = payload
        self.current_run = SimpleNamespace(id=1, **payload)
        return self.current_run

    async def reconcile_stale_runs(self, stale_seconds: int):
        self.reconciled = True
        return []

    async def get_run_for_bot(self, run_id: int, bot_uuid: str):
        if self.current_run is None:
            return None
        if self.current_run.id != run_id or getattr(self.current_run, 'bot_uuid', None) != bot_uuid:
            return None
        return self.current_run

    async def get_run(self, run_id: int):
        if self.current_run is None or self.current_run.id != run_id:
            return None
        return self.current_run


class _FakeRuntimeProcessManager:
    def __init__(self):
        self.stopped = False
        self.closed = False

    async def get_status(self):
        return {
            'status': 'not_available',
            'errorCode': RPA_RUNTIME_NOT_AVAILABLE,
            'runtime_configured': False,
            'runtime_startable': False,
            'runtime_reachable': False,
            'send_enabled': False,
        }

    async def stop(self):
        self.stopped = True

    def close(self):
        self.closed = True


@pytest.mark.parametrize(
    ('operation', 'expected_code'),
    [
        (lambda service: service.create_send_draft_run('bot-1', 11, 31), RPA_RUNTIME_NOT_AVAILABLE),
        (lambda service: service.create_diagnose_run('bot-1', 11, 31), RPA_RUNTIME_NOT_AVAILABLE),
        (lambda service: service.create_send_draft_dry_run('bot-1', 11, 31), RPA_RUNTIME_NOT_AVAILABLE),
        (lambda service: service.cancel_run('bot-1', 1), RUN_NOT_FOUND),
    ],
)
async def test_runtime_dependent_operations_fail_closed_without_creating_run(operation, expected_code):
    repository = _FakeRepository()
    service = _build_service(repository=repository, runtime_process_manager=_FakeRuntimeProcessManager())

    with pytest.raises(DesktopAutomationError) as exc_info:
        await operation(service)

    assert exc_info.value.code == expected_code
    assert repository.created_run is None


async def test_paste_draft_requires_idempotency_key_before_runtime_use():
    repository = _FakeRepository()
    service = _build_service(repository=repository, runtime_process_manager=_FakeRuntimeProcessManager())

    with pytest.raises(DesktopAutomationError) as exc_info:
        await service.create_paste_draft_run('bot-1', 11, 31)

    assert exc_info.value.code == IDEMPOTENCY_KEY_REQUIRED
    assert repository.created_run is None


async def test_get_runtime_status_returns_not_available_shape():
    service = _build_service(
        repository=_FakeRepository(),
        runtime_process_manager=_FakeRuntimeProcessManager(),
    )

    status = await service.get_runtime_status()

    assert status['status'] == 'not_available'
    assert status['errorCode'] == RPA_RUNTIME_NOT_AVAILABLE
    assert status['send_enabled'] is False


async def test_get_runtime_status_preserves_runtime_manager_observation_surface():
    runtime_process_manager = SimpleNamespace(
        get_status=AsyncMock(
            return_value={
                'status': 'ready',
                'host': '127.0.0.1',
                'port': 5302,
                'runtime_configured': True,
                'runtime_startable': True,
                'runtime_reachable': True,
                'send_enabled': False,
                'allowed_connector_count': 0,
                'send_error_code': None,
            }
        )
    )
    service = _build_service(
        repository=_FakeRepository(),
        runtime_process_manager=runtime_process_manager,
    )

    status = await service.get_runtime_status()

    assert status == {
        'status': 'ready',
        'host': '127.0.0.1',
        'port': 5302,
        'runtime_configured': True,
        'runtime_startable': True,
        'runtime_reachable': True,
        'send_enabled': False,
        'allowed_connector_count': 0,
        'send_error_code': None,
    }


async def test_reconcile_stale_runs_preserves_shared_repository_shell():
    repository = _FakeRepository()
    service = _build_service(repository=repository, runtime_process_manager=_FakeRuntimeProcessManager())

    await service.reconcile_stale_runs()

    assert repository.reconciled is True


async def test_get_run_returns_existing_run_without_starting_runtime():
    repository = _FakeRepository()
    repository.current_run = SimpleNamespace(id=51, bot_uuid='bot-1', status='queued', draft_id=31)
    service = _build_service(repository=repository, runtime_process_manager=_FakeRuntimeProcessManager())

    run = await service.get_run('bot-1', 51)

    assert run['id'] == 51
    assert run['status'] == 'queued'


async def test_get_run_raises_not_found_for_missing_run():
    service = _build_service(repository=_FakeRepository(), runtime_process_manager=_FakeRuntimeProcessManager())

    with pytest.raises(DesktopAutomationError) as exc_info:
        await service.get_run('bot-1', 999)

    assert exc_info.value.code == RUN_NOT_FOUND


async def test_shutdown_and_close_delegate_to_runtime_process_manager():
    runtime_process_manager = _FakeRuntimeProcessManager()
    service = _build_service(repository=_FakeRepository(), runtime_process_manager=runtime_process_manager)

    await service.shutdown()
    service.close()

    assert runtime_process_manager.stopped is True
    assert runtime_process_manager.closed is True


async def test_shutdown_is_async_first_and_does_not_require_close():
    runtime_process_manager = SimpleNamespace(
        stop=AsyncMock(),
        close=AsyncMock(),
    )
    service = _build_service(repository=_FakeRepository(), runtime_process_manager=runtime_process_manager)

    await service.shutdown()

    runtime_process_manager.stop.assert_awaited_once()
    runtime_process_manager.close.assert_not_called()


async def test_runtime_create_task_polls_until_terminal_and_persists_nested_result_evidence():
    repository = _FakeRepository()
    repository.get_message_context = AsyncMock(return_value={
        'conversation': {
            'id': 20,
            'connector_id': 'wxwork-local',
            'external_conversation_id': 'conv-20',
            'conversation_name': 'Customer A',
        },
        'draft': {
            'id': 31,
            'bot_uuid': 'bot-1',
            'message_id': 11,
            'content': 'Hello draft',
            'status': 'active',
        },
        'latest_succeeded_send_run': None,
    })
    repository.find_run_by_request_digest = AsyncMock(return_value=None)
    repository.create_run = AsyncMock(return_value=SimpleNamespace(id=1, status='queued', stage='queued'))
    repository.update_run_status = AsyncMock(return_value=SimpleNamespace(id=1, status='succeeded', stage='text_pasted_unverified'))
    repository.count_conversations_by_name = AsyncMock(return_value=1)
    runtime_client = SimpleNamespace(
        create_task=AsyncMock(return_value={
            'id': 'task-1',
            'status': 'running',
            'stage': 'running',
            'idempotencyKey': 'idem-1',
            'requestDigest': 'digest-1',
        }),
        get_task=AsyncMock(side_effect=[
            {
                'id': 'task-1',
                'status': 'running',
                'stage': 'running',
                'idempotencyKey': 'idem-1',
                'requestDigest': 'digest-1',
            },
            {
                'id': 'task-1',
                'status': 'succeeded_with_warning',
                'stage': 'text_pasted_unverified',
                'idempotencyKey': 'idem-1',
                'requestDigest': 'digest-1',
                'result': {
                    'draftWritten': True,
                    'draftPasteCount': 1,
                    'attachmentPasteRequested': False,
                    'messageSent': False,
                    'clipboardRestoreFailed': False,
                    'warning': 'PASTE_RESULT_NOT_VERIFIED',
                },
            },
        ]),
        cancel_task=AsyncMock(),
    )
    service = _build_service(repository=repository, runtime_process_manager=_FakeRuntimeProcessManager())
    service.runtime_client = runtime_client
    service.ensure_runtime_client = AsyncMock(return_value=runtime_client)
    service.ap.instance_config.data['desktop_automation']['task_timeout_seconds'] = 2

    run = await service.create_paste_draft_run('bot-1', 11, 31, idempotency_key='idem-1')

    assert run['status'] == 'succeeded'
    runtime_client.create_task.assert_awaited_once()
    assert runtime_client.get_task.await_count == 2
    runtime_client.cancel_task.assert_not_awaited()
    update_changes = repository.update_run_status.await_args.kwargs
    assert update_changes['runtime_task_id'] == 'task-1'
    assert update_changes['status'] == 'succeeded_with_warning'
    assert update_changes['result_evidence']['draftWritten'] is True
    assert update_changes['result_evidence']['draftPasteCount'] == 1
    assert update_changes['result_evidence']['warning'] == 'PASTE_RESULT_NOT_VERIFIED'


async def test_runtime_create_task_cancels_after_timeout_and_marks_run_timed_out():
    repository = _FakeRepository()
    repository.get_message_context = AsyncMock(return_value={
        'conversation': {
            'id': 20,
            'connector_id': 'wxwork-local',
            'external_conversation_id': 'conv-20',
            'conversation_name': 'Customer A',
        },
        'draft': {
            'id': 31,
            'bot_uuid': 'bot-1',
            'message_id': 11,
            'content': 'Hello draft',
            'status': 'active',
        },
        'latest_succeeded_send_run': None,
    })
    repository.find_run_by_request_digest = AsyncMock(return_value=None)
    repository.create_run = AsyncMock(return_value=SimpleNamespace(id=1, status='queued', stage='queued'))
    repository.update_run_status = AsyncMock(return_value=SimpleNamespace(id=1, status='timed_out', stage='timed_out'))
    repository.count_conversations_by_name = AsyncMock(return_value=1)
    runtime_client = SimpleNamespace(
        create_task=AsyncMock(return_value={
            'id': 'task-timeout',
            'status': 'running',
            'stage': 'running',
            'idempotencyKey': 'idem-timeout',
            'requestDigest': 'digest-timeout',
        }),
        get_task=AsyncMock(side_effect=[
            {
                'id': 'task-timeout',
                'status': 'running',
                'stage': 'running',
                'idempotencyKey': 'idem-timeout',
                'requestDigest': 'digest-timeout',
            },
            {
                'id': 'task-timeout',
                'status': 'running',
                'stage': 'running',
                'idempotencyKey': 'idem-timeout',
                'requestDigest': 'digest-timeout',
            },
        ]),
        cancel_task=AsyncMock(return_value={
            'id': 'task-timeout',
            'status': 'cancelled',
            'stage': 'cancelled',
        }),
    )
    service = _build_service(repository=repository, runtime_process_manager=_FakeRuntimeProcessManager())
    service.runtime_client = runtime_client
    service.ensure_runtime_client = AsyncMock(return_value=runtime_client)
    service.ap.instance_config.data['desktop_automation']['task_timeout_seconds'] = 0

    run = await service.create_paste_draft_run('bot-1', 11, 31, idempotency_key='idem-timeout')

    assert run['status'] == 'timed_out'
    runtime_client.cancel_task.assert_awaited_once_with('task-timeout')
    update_changes = repository.update_run_status.await_args.kwargs
    assert update_changes['status'] == 'cancelled'
    assert update_changes['stage'] == 'cancelled'
    assert update_changes['last_error_code'] == 'TASK_TIMEOUT'


async def test_runtime_timeout_uses_runtime_terminal_state_when_cancel_races_with_success():
    repository = _FakeRepository()
    repository.get_message_context = AsyncMock(return_value={
        'conversation': {
            'id': 20,
            'connector_id': 'wxwork-local',
            'external_conversation_id': 'conv-20',
            'conversation_name': 'Customer A',
        },
        'draft': {
            'id': 31,
            'bot_uuid': 'bot-1',
            'message_id': 11,
            'content': 'Hello draft',
            'status': 'active',
        },
        'latest_succeeded_send_run': None,
    })
    repository.find_run_by_request_digest = AsyncMock(return_value=None)
    repository.create_run = AsyncMock(return_value=SimpleNamespace(id=1, status='queued', stage='queued'))
    repository.update_run_status = AsyncMock(
        return_value=SimpleNamespace(id=1, status='succeeded_with_warning', stage='text_pasted_unverified')
    )
    repository.count_conversations_by_name = AsyncMock(return_value=1)
    runtime_client = SimpleNamespace(
        create_task=AsyncMock(return_value={
            'id': 'task-race-success',
            'status': 'running',
            'stage': 'running',
            'idempotencyKey': 'idem-race-success',
            'requestDigest': 'digest-race-success',
        }),
        get_task=AsyncMock(side_effect=[
            {
                'id': 'task-race-success',
                'status': 'succeeded_with_warning',
                'stage': 'text_pasted_unverified',
                'idempotencyKey': 'idem-race-success',
                'requestDigest': 'digest-race-success',
                'result': {
                    'draftWritten': True,
                    'draftPasteCount': 1,
                    'messageSent': False,
                    'clipboardRestoreFailed': False,
                    'warning': 'PASTE_RESULT_NOT_VERIFIED',
                },
            }
        ]),
        cancel_task=AsyncMock(return_value={
            'id': 'task-race-success',
            'status': 'running',
            'stage': 'cancelling',
            'idempotencyKey': 'idem-race-success',
            'requestDigest': 'digest-race-success',
        }),
    )
    service = _build_service(repository=repository, runtime_process_manager=_FakeRuntimeProcessManager())
    service.runtime_client = runtime_client
    service.ensure_runtime_client = AsyncMock(return_value=runtime_client)
    service.ap.instance_config.data['desktop_automation']['task_timeout_seconds'] = 0

    run = await service.create_paste_draft_run('bot-1', 11, 31, idempotency_key='idem-race-success')

    assert run['status'] == 'succeeded_with_warning'
    runtime_client.cancel_task.assert_awaited_once_with('task-race-success')
    update_changes = repository.update_run_status.await_args.kwargs
    assert update_changes['status'] == 'succeeded_with_warning'
    assert update_changes['result_evidence']['draftWritten'] is True


async def test_runtime_timeout_marks_cancel_requested_when_runtime_never_confirms_terminal_state():
    repository = _FakeRepository()
    repository.get_message_context = AsyncMock(return_value={
        'conversation': {
            'id': 20,
            'connector_id': 'wxwork-local',
            'external_conversation_id': 'conv-20',
            'conversation_name': 'Customer A',
        },
        'draft': {
            'id': 31,
            'bot_uuid': 'bot-1',
            'message_id': 11,
            'content': 'Hello draft',
            'status': 'active',
        },
        'latest_succeeded_send_run': None,
    })
    repository.find_run_by_request_digest = AsyncMock(return_value=None)
    repository.create_run = AsyncMock(return_value=SimpleNamespace(id=1, status='queued', stage='queued'))
    repository.update_run_status = AsyncMock(
        return_value=SimpleNamespace(id=1, status='running', stage='cancel_requested')
    )
    repository.count_conversations_by_name = AsyncMock(return_value=1)
    runtime_client = SimpleNamespace(
        create_task=AsyncMock(return_value={
            'id': 'task-cancel-requested',
            'status': 'running',
            'stage': 'running',
            'idempotencyKey': 'idem-cancel-requested',
            'requestDigest': 'digest-cancel-requested',
        }),
        get_task=AsyncMock(side_effect=[
            *[
                {
                    'id': 'task-cancel-requested',
                    'status': 'running',
                    'stage': 'cancelling',
                    'idempotencyKey': 'idem-cancel-requested',
                    'requestDigest': 'digest-cancel-requested',
                }
                for _ in range(10)
            ]
        ]),
        cancel_task=AsyncMock(return_value={
            'id': 'task-cancel-requested',
            'status': 'running',
            'stage': 'cancelling',
            'idempotencyKey': 'idem-cancel-requested',
            'requestDigest': 'digest-cancel-requested',
        }),
    )
    service = _build_service(repository=repository, runtime_process_manager=_FakeRuntimeProcessManager())
    service.runtime_client = runtime_client
    service.ensure_runtime_client = AsyncMock(return_value=runtime_client)
    service.ap.instance_config.data['desktop_automation']['task_timeout_seconds'] = 0

    run = await service.create_paste_draft_run('bot-1', 11, 31, idempotency_key='idem-cancel-requested')

    assert run['status'] == 'running'
    update_changes = repository.update_run_status.await_args.kwargs
    assert update_changes['status'] == 'running'
    assert update_changes['stage'] == 'cancel_requested'
    assert update_changes['last_error_code'] == 'TASK_TIMEOUT'
    assert update_changes['result_evidence']['stage'] == 'cancel_requested'


async def test_cancel_run_waits_for_runtime_terminal_state_before_persisting():
    repository = _FakeRepository()
    repository.current_run = SimpleNamespace(id=1, bot_uuid='bot-1', runtime_task_id='task-cancel-run')
    repository.update_run_status = AsyncMock(return_value=SimpleNamespace(id=1, status='cancelled', stage='cancelled'))
    runtime_client = SimpleNamespace(
        cancel_task=AsyncMock(return_value={
            'id': 'task-cancel-run',
            'status': 'running',
            'stage': 'cancelling',
            'idempotencyKey': 'idem-cancel-run',
            'requestDigest': 'digest-cancel-run',
        }),
        get_task=AsyncMock(return_value={
            'id': 'task-cancel-run',
            'status': 'cancelled',
            'stage': 'cancelled',
            'idempotencyKey': 'idem-cancel-run',
            'requestDigest': 'digest-cancel-run',
            'result': {
                'errorCode': TASK_CANCELLED,
            },
        }),
    )
    service = _build_service(repository=repository, runtime_process_manager=_FakeRuntimeProcessManager())
    service.runtime_client = runtime_client
    service.ensure_runtime_client = AsyncMock(return_value=runtime_client)

    run = await service.cancel_run('bot-1', 1)

    assert run['status'] == 'cancelled'
    runtime_client.cancel_task.assert_awaited_once_with('task-cancel-run')
    runtime_client.get_task.assert_awaited_once_with('task-cancel-run')
    update_changes = repository.update_run_status.await_args.kwargs
    assert update_changes['status'] == 'cancelled'
    assert update_changes['stage'] == 'cancelled'


async def test_cancel_run_without_runtime_task_id_marks_cancelled_locally():
    repository = _FakeRepository()
    repository.current_run = SimpleNamespace(id=1, bot_uuid='bot-1', runtime_task_id=None)
    repository.update_run_status = AsyncMock(return_value=SimpleNamespace(id=1, status='cancelled', stage='cancelled'))
    service = _build_service(repository=repository, runtime_process_manager=_FakeRuntimeProcessManager())

    run = await service.cancel_run('bot-1', 1)

    assert run['status'] == 'cancelled'
    update_changes = repository.update_run_status.await_args.kwargs
    assert update_changes['status'] == 'cancelled'
    assert update_changes['stage'] == 'cancelled'
    assert update_changes['last_error_code'] == TASK_CANCELLED
