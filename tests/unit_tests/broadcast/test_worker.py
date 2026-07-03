from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest


pytestmark = pytest.mark.asyncio


def _make_worker(results: list[bool]):
    from langbot.pkg.broadcast.worker import BroadcastExecutionWorker

    service = SimpleNamespace(
        run_next_execution_task=AsyncMock(side_effect=results),
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


async def test_worker_wake_triggers_waiting_loop():
    worker, service = _make_worker([False, True, False])

    await worker.start()
    worker.wake()
    await asyncio.sleep(0.05)
    await worker.stop()

    assert service.run_next_execution_task.await_count >= 1
