from __future__ import annotations

import asyncio


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
            except Exception:
                processed = False
            if processed:
                continue
            self._wake_event.clear()
            try:
                await asyncio.wait_for(self._wake_event.wait(), timeout=self.poll_interval)
            except asyncio.TimeoutError:
                continue
