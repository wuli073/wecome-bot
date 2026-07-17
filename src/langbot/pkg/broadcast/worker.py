from __future__ import annotations

import asyncio
import logging
import re
import uuid


logger = logging.getLogger(__name__)


class BroadcastExecutionWorker:
    def __init__(self, *, service, scope=None, poll_interval: float = 0.5) -> None:
        self.service = service
        self.scope = scope
        self.poll_interval = poll_interval
        self._wake_event = asyncio.Event()
        self._stop_event = asyncio.Event()
        self._runner_task: asyncio.Task[None] | None = None
        self._run_lock = asyncio.Lock()
        self._start_lock = asyncio.Lock()
        self._stop_lock = asyncio.Lock()
        self._stop_task: asyncio.Task[None] | None = None
        self._consecutive_failures = 0
        self._state = 'not_started'
        self._schema_ready = False
        self._recovery_completed = False
        self._stale_running_task_count = 0
        self._last_error: str | None = None
        self._instance_id = f'broadcast-worker-{uuid.uuid4().hex[:12]}'

    async def start(self) -> None:
        async with self._start_lock:
            if self.is_running():
                return

            self._stop_event.clear()
            self._state = 'starting'
            self._schema_ready = False
            self._recovery_completed = False
            self._stale_running_task_count = 0
            self._last_error = None
            try:
                verify_execution_schema = getattr(self.service, 'verify_execution_schema', None)
                if callable(verify_execution_schema):
                    await verify_execution_schema()
                self._schema_ready = True

                self._state = 'recovering'
                recovered = await self.service.reconcile_running_executions()
                self._stale_running_task_count = int(recovered or 0)
                self._recovery_completed = True

                self._state = 'running'
                self._runner_task = asyncio.create_task(
                    self.run_forever(),
                    name='broadcast-execution-worker',
                )
                self.wake()
            except Exception as exc:
                self._state = 'failed'
                self._last_error = exc.__class__.__name__
                self._runner_task = None
                raise

    async def stop(self) -> None:
        async with self._stop_lock:
            if self._stop_task is None or self._stop_task.done():
                self._stop_task = asyncio.create_task(self._stop_once(), name='broadcast-worker-stop')
            stop_task = self._stop_task
        await stop_task

    async def _stop_once(self) -> None:
        runner_task = self._runner_task
        if runner_task is None:
            if self._state not in {'failed', 'not_started'}:
                self._state = 'stopped'
            return

        self._state = 'stopping'
        self._stop_event.set()
        self.wake()
        try:
            await asyncio.wait_for(runner_task, timeout=10)
        except asyncio.TimeoutError:
            runner_task.cancel()
            await asyncio.gather(runner_task, return_exceptions=True)
        finally:
            self._runner_task = None
            self._state = 'stopped'

    def is_running(self) -> bool:
        return self._state == 'running' and self._runner_task is not None and not self._runner_task.done()

    def health_snapshot(self) -> dict[str, object]:
        return {
            'broadcast_schema_ready': self._schema_ready,
            'broadcast_recovery_completed': self._recovery_completed,
            'broadcast_worker_state': self._state,
            'broadcast_worker_running': self.is_running(),
            'broadcast_worker_instance': self._instance_id,
            'broadcast_last_error': self._last_error,
            'stale_running_task_count': self._stale_running_task_count,
        }

    def wake(self) -> None:
        self._wake_event.set()

    async def run_once(self) -> bool:
        async with self._run_lock:
            return await self.service.run_next_execution_task()

    async def run_forever(self) -> None:
        while not self._stop_event.is_set():
            try:
                processed = await self.run_once()
                self._consecutive_failures = 0
            except Exception as exc:
                self._consecutive_failures += 1
                self._last_error = exc.__class__.__name__
                logger.warning(
                    'Broadcast execution worker run_once failed: error_type=%s message=%s consecutive_failures=%s',
                    exc.__class__.__name__,
                    self._sanitize_exception_message(exc),
                    self._consecutive_failures,
                )
                processed = False
            if processed:
                continue
            self._wake_event.clear()
            timeout = self.poll_interval
            if self._consecutive_failures > 0:
                timeout = min(max(self.poll_interval, self.poll_interval * self._consecutive_failures), 5.0)
            try:
                await asyncio.wait_for(self._wake_event.wait(), timeout=timeout)
            except asyncio.TimeoutError:
                continue

    @staticmethod
    def _sanitize_exception_message(exc: Exception) -> str:
        raw = str(exc or '').strip()
        if not raw:
            return ''

        redacted = raw
        for secret_pattern in (
            r'(?i)token\s*=\s*\S+',
            r'(?i)authorization\s*=\s*\S+',
            r'(?i)cookie\s*=\s*\S+',
            r'(?i)conversation\s*=\s*[^,\s]+',
            r'(?i)draft(?:\s+body|\s*text)?\s*=\s.+',
            r'(?i)draft\s+body\b.*',
        ):
            redacted = re.sub(secret_pattern, '[redacted]', redacted)
        return redacted[:200]
