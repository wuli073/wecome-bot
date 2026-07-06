from __future__ import annotations

import asyncio
import logging
import re


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
        self._stop_lock = asyncio.Lock()
        self._stop_task: asyncio.Task[None] | None = None
        self._consecutive_failures = 0

    async def start(self) -> None:
        if self._runner_task is not None and not self._runner_task.done():
            return
        self._stop_event.clear()
        self._runner_task = asyncio.create_task(self.run_forever(), name='broadcast-execution-worker')
        self.wake()

    async def stop(self) -> None:
        async with self._stop_lock:
            if self._stop_task is None or self._stop_task.done():
                self._stop_task = asyncio.create_task(self._stop_once(), name='broadcast-worker-stop')
            stop_task = self._stop_task
        await stop_task

    async def _stop_once(self) -> None:
        self._stop_event.set()
        self.wake()
        if self._runner_task is None:
            return
        try:
            await asyncio.wait_for(self._runner_task, timeout=10)
        except asyncio.TimeoutError:
            self._runner_task.cancel()
            await asyncio.gather(self._runner_task, return_exceptions=True)
        finally:
            self._runner_task = None

    def wake(self) -> None:
        self._wake_event.set()

    async def run_once(self) -> bool:
        async with self._run_lock:
            return await self.service.run_next_execution_task()

    async def run_forever(self) -> None:
        await self.service.reconcile_running_executions()
        while not self._stop_event.is_set():
            try:
                processed = await self.run_once()
                self._consecutive_failures = 0
            except Exception as exc:
                self._consecutive_failures += 1
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
            r'(?i)draft(?:\s+body|\s*text)?\s*=\s*.+',
            r'(?i)draft\s+body\b.*',
        ):
            redacted = re.sub(secret_pattern, '[redacted]', redacted)
        return redacted[:200]
