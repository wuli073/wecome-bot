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
    'operation',
    [
        lambda service: service.create_send_draft_run('bot-1', 11, 31),
        lambda service: service.create_diagnose_run('bot-1', 11, 31),
        lambda service: service.create_send_draft_dry_run('bot-1', 11, 31),
        lambda service: service.cancel_run('bot-1', 1),
    ],
)
async def test_runtime_dependent_operations_fail_closed_without_creating_run(operation):
    repository = _FakeRepository()
    service = _build_service(repository=repository, runtime_process_manager=_FakeRuntimeProcessManager())

    with pytest.raises(DesktopAutomationError) as exc_info:
        await operation(service)

    assert exc_info.value.code == RPA_RUNTIME_NOT_AVAILABLE
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
