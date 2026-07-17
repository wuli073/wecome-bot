from __future__ import annotations

import asyncio
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest


pytestmark = pytest.mark.asyncio


def _make_worker(results: list[bool]):
    from langbot.pkg.broadcast.worker import BroadcastExecutionWorker

    service = SimpleNamespace(
        run_next_execution_task=AsyncMock(side_effect=results),
        verify_execution_schema=AsyncMock(return_value=None),
        reconcile_running_executions=AsyncMock(return_value=0),
    )
    worker = BroadcastExecutionWorker(service=service)
    return worker, service


async def test_worker_run_once_delegates_to_service():
    worker, service = _make_worker([True])

    result = await worker.run_once()

    assert result is True
    service.run_next_execution_task.assert_awaited_once()


async def test_worker_run_once_returns_false_when_no_task_claimed():
    worker, service = _make_worker([False])

    result = await worker.run_once()

    assert result is False
    service.run_next_execution_task.assert_awaited_once()


async def test_worker_run_once_processes_tasks_serially():
    worker, service = _make_worker([])
    active_runs = 0
    peak_active_runs = 0
    processed = 0

    async def run_next_execution_task():
      nonlocal active_runs, peak_active_runs, processed
      active_runs += 1
      peak_active_runs = max(peak_active_runs, active_runs)
      await asyncio.sleep(0.01)
      active_runs -= 1
      processed += 1
      return processed < 3

    service.run_next_execution_task = AsyncMock(side_effect=run_next_execution_task)

    first = await worker.run_once()
    second = await worker.run_once()
    third = await worker.run_once()

    assert [first, second, third] == [True, True, False]
    assert peak_active_runs == 1


async def test_worker_start_calls_reconcile_before_loop():
    worker, service = _make_worker([False, False])

    await worker.start()
    await asyncio.sleep(0.02)
    await worker.stop()

    service.reconcile_running_executions.assert_awaited_once()
    assert service.run_next_execution_task.await_count >= 1


async def test_worker_start_verifies_schema_and_recovers_before_claiming():
    events: list[str] = []

    async def verify_execution_schema():
        events.append('schema')

    async def reconcile_running_executions():
        events.append('recovery')
        return 3

    async def run_next_execution_task():
        events.append('claim')
        return False

    from langbot.pkg.broadcast.worker import BroadcastExecutionWorker

    service = SimpleNamespace(
        verify_execution_schema=AsyncMock(side_effect=verify_execution_schema),
        reconcile_running_executions=AsyncMock(side_effect=reconcile_running_executions),
        run_next_execution_task=AsyncMock(side_effect=run_next_execution_task),
    )
    worker = BroadcastExecutionWorker(service=service, poll_interval=60)

    await worker.start()
    await asyncio.sleep(0)
    await worker.stop()

    assert events[:3] == ['schema', 'recovery', 'claim']
    assert worker.health_snapshot()['broadcast_schema_ready'] is True
    assert worker.health_snapshot()['broadcast_recovery_completed'] is True
    assert worker.health_snapshot()['stale_running_task_count'] == 3


async def test_worker_start_failure_marks_health_failed_without_creating_runner():
    worker, service = _make_worker([])
    service.verify_execution_schema.side_effect = RuntimeError('missing migration')

    with pytest.raises(RuntimeError, match='missing migration'):
        await worker.start()

    health = worker.health_snapshot()
    assert worker._runner_task is None
    assert health['broadcast_worker_state'] == 'failed'
    assert health['broadcast_worker_running'] is False
    assert health['broadcast_schema_ready'] is False
    assert health['broadcast_recovery_completed'] is False
    assert health['broadcast_last_error'] == 'RuntimeError'


async def test_worker_start_is_idempotent_and_does_not_duplicate_recovery_or_runner():
    worker, service = _make_worker([False, False])

    await asyncio.gather(worker.start(), worker.start())
    first_runner = worker._runner_task
    await worker.start()
    await asyncio.sleep(0)
    await worker.stop()

    assert first_runner is not None
    service.verify_execution_schema.assert_awaited_once()
    service.reconcile_running_executions.assert_awaited_once()


async def test_worker_wake_triggers_waiting_loop():
    worker, service = _make_worker([False, True, False])

    await worker.start()
    worker.wake()
    await asyncio.sleep(0.05)
    await worker.stop()

    assert service.run_next_execution_task.await_count >= 1


async def test_worker_logs_sanitized_exception_and_keeps_running(caplog):
    from langbot.pkg.broadcast.worker import BroadcastExecutionWorker

    calls = 0

    async def run_next_execution_task():
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError('token=top-secret conversation=Acme draft body leaked')
        if calls == 2:
            return True
        return False

    service = SimpleNamespace(
        run_next_execution_task=AsyncMock(side_effect=run_next_execution_task),
        verify_execution_schema=AsyncMock(return_value=None),
        reconcile_running_executions=AsyncMock(return_value=0),
    )
    worker = BroadcastExecutionWorker(service=service, poll_interval=0.01)

    caplog.set_level(logging.WARNING)
    await worker.start()
    await asyncio.sleep(0.08)
    await worker.stop()

    assert calls >= 2
    assert 'Broadcast execution worker run_once failed' in caplog.text
    assert 'RuntimeError' in caplog.text
    assert 'top-secret' not in caplog.text
    assert 'Acme' not in caplog.text
    assert 'draft body leaked' not in caplog.text
