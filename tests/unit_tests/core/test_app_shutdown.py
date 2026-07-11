from __future__ import annotations

import asyncio
import logging
from types import SimpleNamespace

import pytest

from langbot.pkg.broadcast.worker import BroadcastExecutionWorker
from langbot.pkg.core import app as app_module
from langbot.pkg.core import entities as core_entities
from langbot.pkg.core import taskmgr as taskmgr_module


pytestmark = pytest.mark.asyncio


def _make_logger():
    return logging.getLogger('test-app-shutdown')


def _make_application() -> app_module.Application:
    ap = app_module.Application()
    ap.event_loop = asyncio.get_running_loop()
    ap.logger = _make_logger()
    ap.instance_config = SimpleNamespace(
        data={
            'monitoring': {'auto_cleanup': {'enabled': False}},
            'storage': {'cleanup': {'enabled': False}},
            'desktop_automation': {'enabled': False},
            'system': {'task_retention': {'completed_limit': 200}},
            'api': {'port': 5300},
        }
    )
    ap.task_mgr = taskmgr_module.AsyncTaskManager(ap)
    ap.plugin_connector = SimpleNamespace(initialize_plugins=_async_noop(), dispose=lambda: None)
    ap.platform_mgr = SimpleNamespace(run=_wait_forever)
    ap.ctrl = SimpleNamespace(run=_wait_forever)
    ap.http_ctrl = SimpleNamespace(run=_wait_forever, request_shutdown=lambda: None)
    ap.print_web_access_info = _async_noop()
    ap.dispose = lambda: None
    ap.monitoring_service = None
    ap.maintenance_service = None
    ap.telemetry = None
    ap.broadcast_execution_worker = None
    ap.desktop_automation_service = None
    ap.database_mode_event_bus = None
    ap.local_connectors_service = None
    ap.box_service = None
    return ap


def _async_noop(result=None):
    async def _inner(*args, **kwargs):
        return result

    return _inner


async def _wait_forever(*args, **kwargs):
    await asyncio.Future()


async def test_application_run_requests_shutdown_when_critical_task_crashes_before_manual_shutdown():
    ap = _make_application()

    async def crashing_run():
        raise RuntimeError('boom')

    ap.platform_mgr = SimpleNamespace(run=crashing_run)
    reasons: list[str | None] = []
    original_request_shutdown = ap.request_shutdown

    def tracking_request_shutdown(reason=None):
        reasons.append(reason)
        original_request_shutdown(reason)

    ap.request_shutdown = tracking_request_shutdown
    ap.shutdown = _async_noop()

    exit_code = await ap.run()

    assert exit_code == 1
    assert reasons == ['critical-task:platform-manager']


async def test_application_run_returns_nonzero_status_after_cleanup_when_critical_task_failed():
    ap = _make_application()
    startup_complete = asyncio.Event()

    async def platform_startup_only():
        startup_complete.set()
        return None

    async def crashing_run():
        await startup_complete.wait()
        raise RuntimeError('boom')

    ap.platform_mgr = SimpleNamespace(run=platform_startup_only)
    ap.ctrl = SimpleNamespace(run=crashing_run)
    shutdown_calls: list[str] = []

    async def fake_shutdown():
        shutdown_calls.append('shutdown')

    ap.shutdown = fake_shutdown

    exit_code = await ap.run()

    assert exit_code == 1
    assert shutdown_calls == ['shutdown']


async def test_cancel_and_wait_by_scope_is_bounded_and_excludes_shutdown_coordinator():
    ap = _make_application()
    manager = ap.task_mgr

    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def long_task():
        started.set()
        try:
            await asyncio.Future()
        except asyncio.CancelledError:
            cancelled.set()
            raise

    wrapper = manager.create_task(
        long_task(),
        name='application-task',
        scopes=[core_entities.LifecycleControlScope.APPLICATION],
    )
    await started.wait()

    results = await manager.cancel_and_wait_by_scope(core_entities.LifecycleControlScope.APPLICATION, timeout=1)

    assert len(results) == 1
    assert isinstance(results[0], asyncio.CancelledError)
    assert cancelled.is_set()
    assert wrapper.task.cancelled() or wrapper.task.done()


async def test_broadcast_worker_stop_is_idempotent_when_called_twice_concurrently():
    runner_released = asyncio.Event()
    run_calls = 0

    class _Service:
        async def reconcile_running_executions(self):
            return None

        async def run_next_execution_task(self):
            nonlocal run_calls
            run_calls += 1
            await runner_released.wait()
            return False

    worker = BroadcastExecutionWorker(service=_Service(), poll_interval=60)
    await worker.start()
    await asyncio.sleep(0)
    runner_released.set()

    await asyncio.gather(worker.stop(), worker.stop())

    assert worker._runner_task is None
    assert run_calls == 1


async def test_application_shutdown_does_not_touch_worker_private_runner_task():
    ap = _make_application()
    private_runner = object()
    stop_calls: list[str] = []

    class _Worker:
        _runner_task = private_runner

        async def stop(self):
            stop_calls.append('stop')

    ap.broadcast_execution_worker = _Worker()
    ap.shutdown_requested_event = asyncio.Event()

    await ap.shutdown()

    assert stop_calls == ['stop']
    assert ap.broadcast_execution_worker._runner_task is private_runner


async def test_runtime_prewarm_is_scheduled_as_application_task_when_enabled():
    ap = _make_application()
    ap.instance_config.data['desktop_automation']['enabled'] = True
    ensure_calls: list[str] = []

    async def ensure_runtime_client():
        ensure_calls.append('ensure')

    ap.desktop_automation_service = SimpleNamespace(ensure_runtime_client=ensure_runtime_client)

    await ap.initialize()
    await asyncio.sleep(0)

    assert any(wrapper.name == 'desktop-runtime-prewarm' for wrapper in ap.task_mgr.tasks)
    assert ensure_calls == ['ensure']


async def test_runtime_prewarm_failure_does_not_fail_http_startup():
    ap = _make_application()
    ap.instance_config.data['desktop_automation']['enabled'] = True

    async def ensure_runtime_client():
        raise RuntimeError('prewarm failed')

    ap.desktop_automation_service = SimpleNamespace(ensure_runtime_client=ensure_runtime_client)

    await ap.initialize()
    await asyncio.sleep(0)

    assert any(wrapper.name == 'desktop-runtime-prewarm' for wrapper in ap.task_mgr.tasks)


async def test_application_run_allows_platform_manager_startup_to_return_after_spawning_platform_tasks():
    ap = _make_application()

    async def platform_startup_only():
        return None

    ap.platform_mgr = SimpleNamespace(run=platform_startup_only)
    run_task = asyncio.create_task(ap.run())

    await asyncio.sleep(0.05)
    assert not run_task.done()

    ap.request_shutdown('test-stop')
    exit_code = await run_task

    assert exit_code == 0


async def test_application_run_does_not_start_critical_tasks_after_startup_shutdown_request():
    ap = _make_application()
    critical_task_starts: list[str] = []

    async def platform_startup_only():
        ap.request_shutdown('startup-shutdown')

    async def critical_task():
        critical_task_starts.append('started')
        await asyncio.Future()

    ap.platform_mgr = SimpleNamespace(run=platform_startup_only)
    ap.ctrl = SimpleNamespace(run=critical_task)
    ap.http_ctrl = SimpleNamespace(run=critical_task, request_shutdown=lambda: None)
    ap.shutdown = _async_noop()

    exit_code = await ap.run()

    assert exit_code == 0
    assert critical_task_starts == []


async def test_application_run_treats_http_controller_failure_as_critical():
    ap = _make_application()
    startup_complete = asyncio.Event()

    async def platform_startup_only():
        startup_complete.set()
        return None

    async def crashing_http_run():
        await startup_complete.wait()
        raise RuntimeError('http controller boom')

    ap.platform_mgr = SimpleNamespace(run=platform_startup_only)
    ap.http_ctrl = SimpleNamespace(run=crashing_http_run, request_shutdown=lambda: None)
    reasons: list[str | None] = []
    original_request_shutdown = ap.request_shutdown

    def tracking_request_shutdown(reason=None):
        reasons.append(reason)
        original_request_shutdown(reason)

    ap.request_shutdown = tracking_request_shutdown
    ap.shutdown = _async_noop()

    exit_code = await ap.run()

    assert exit_code == 1
    assert reasons == ['critical-task:http-api-controller']


async def test_application_run_detects_http_controller_failure_before_first_wait():
    ap = _make_application()

    async def platform_startup_only():
        return None

    async def crashing_http_run():
        raise RuntimeError('http controller boom before first wait')

    ap.platform_mgr = SimpleNamespace(run=platform_startup_only)
    ap.http_ctrl = SimpleNamespace(run=crashing_http_run, request_shutdown=lambda: None)
    shutdown_calls: list[str] = []

    async def fake_shutdown():
        shutdown_calls.append('shutdown')

    ap.shutdown = fake_shutdown

    exit_code = await ap.run()

    assert exit_code == 1
    assert shutdown_calls == ['shutdown']
    assert isinstance(ap._critical_failure, RuntimeError)
    assert str(ap._critical_failure) == 'http controller boom before first wait'
    assert ap.shutdown_requested_event.is_set()
    assert ap._shutdown_reason == 'critical-task:http-api-controller'


async def test_application_run_detects_query_controller_failure_before_first_wait():
    ap = _make_application()

    async def platform_startup_only():
        return None

    async def crashing_query_run():
        raise RuntimeError('query controller boom before first wait')

    ap.platform_mgr = SimpleNamespace(run=platform_startup_only)
    ap.ctrl = SimpleNamespace(run=crashing_query_run)
    shutdown_calls: list[str] = []

    async def fake_shutdown():
        shutdown_calls.append('shutdown')

    ap.shutdown = fake_shutdown

    exit_code = await ap.run()

    assert exit_code == 1
    assert shutdown_calls == ['shutdown']
    assert isinstance(ap._critical_failure, RuntimeError)
    assert str(ap._critical_failure) == 'query controller boom before first wait'
    assert ap.shutdown_requested_event.is_set()
    assert ap._shutdown_reason == 'critical-task:query-controller'


async def test_application_run_cancelled_error_still_runs_shutdown():
    ap = _make_application()
    shutdown_calls: list[str] = []

    async def cancelled_platform_run():
        raise asyncio.CancelledError()

    async def fake_shutdown():
        shutdown_calls.append('shutdown')

    ap.platform_mgr = SimpleNamespace(run=cancelled_platform_run)
    ap.shutdown = fake_shutdown

    exit_code = await ap.run()

    assert exit_code == 0
    assert shutdown_calls == ['shutdown']
