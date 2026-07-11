# Local Startup Runtime Lifecycle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement backend-owned Runtime graceful shutdown, non-blocking Runtime prewarm, and a Windows local launcher for Bundled/Dev workflows without expanding Runtime ownership beyond the backend.

**Architecture:** The backend gains a main-coroutine-owned shutdown coordinator, control-file-driven graceful stop, and owned-snapshot Runtime teardown with PID/create-time protection. The Windows launcher becomes a thin PowerShell 5.1-compatible process supervisor for backend and Dev-mode Vite only, with atomic state files, port ownership checks, and repo-scoped mutual exclusion.

**Tech Stack:** Python 3.11+, asyncio, Quart/Hypercorn, psutil, pytest, Windows PowerShell 5.1, Start-Process, cmd.exe, pnpm

---

## File Map

### Backend lifecycle and shutdown

- Modify: `C:\Users\33031\Desktop\bot\src\langbot\__main__.py`
  - Preserve non-zero exit codes from boot/application lifecycle
- Modify: `C:\Users\33031\Desktop\bot\src\langbot\pkg\core\app.py`
  - Add shutdown coordinator state/events
  - Replace never-ending task pattern
  - Add critical task monitoring and failure propagation
  - Add Runtime prewarm background task scheduling
- Modify: `C:\Users\33031\Desktop\bot\src\langbot\pkg\core\boot.py`
  - Add pending-shutdown handling before app creation completes
  - Convert signal path to request-only flow
  - Return non-zero on critical task failure after cleanup
- Modify: `C:\Users\33031\Desktop\bot\src\langbot\pkg\core\taskmgr.py`
  - Add bounded cancel-and-wait by scope for shutdown collection
- Create: `C:\Users\33031\Desktop\bot\src\langbot\pkg\core\local_shutdown_control.py`
  - Validate control-file path under repo `.tmp/local-stack/control`
  - Implement control-file consume/watch loop
- Modify: `C:\Users\33031\Desktop\bot\src\langbot\pkg\core\stages\build_app.py`
  - Wire shutdown watcher, app lifecycle hooks, and non-blocking prewarm
- Modify: `C:\Users\33031\Desktop\bot\src\langbot\pkg\api\http\controller\main.py`
  - Add internal shutdown event and `request_shutdown()`

### Broadcast and desktop automation

- Modify: `C:\Users\33031\Desktop\bot\src\langbot\pkg\broadcast\worker.py`
  - Make `stop()` concurrency-safe, idempotent, and self-contained
- Modify: `C:\Users\33031\Desktop\bot\src\langbot\pkg\desktop_automation\service.py`
  - Keep `shutdown()` explicit and async-first
- Modify: `C:\Users\33031\Desktop\bot\src\langbot\pkg\desktop_automation\runtime_process.py`
  - Add owned snapshot stop flow
  - Add PID/create-time ownership checks
  - Add asyncio-subprocess → psutil conversion
  - Split `stop()` / `_stop_locked()`

### Windows launcher

- Create: `C:\Users\33031\Desktop\bot\scripts\start-local.ps1`
  - Repo mutex
  - Dynamic host/port loading
  - TCP port ownership protection
  - Atomic state/control files
  - Start-Process stdout/stderr direct file redirection
  - Bundled/Dev process management
- Create: `C:\Users\33031\Desktop\bot\scripts\start-local.cmd`
  - Thin wrapper only
- Modify if needed: `C:\Users\33031\Desktop\bot\.gitignore`
  - Add `.tmp/` if missing

### Tests

- Modify: `C:\Users\33031\Desktop\bot\tests\unit_tests\core\test_boot.py`
- Create or modify: `C:\Users\33031\Desktop\bot\tests\unit_tests\core\test_app_shutdown.py`
- Create: `C:\Users\33031\Desktop\bot\tests\unit_tests\core\test_local_shutdown_control.py`
- Modify: `C:\Users\33031\Desktop\bot\tests\unit_tests\desktop_automation\test_runtime_process.py`
- Modify: `C:\Users\33031\Desktop\bot\tests\unit_tests\desktop_automation\test_service.py`
- Create if useful: `C:\Users\33031\Desktop\bot\scripts\tests\start-local.Tests.ps1`

## Phase Order

1. Backend exit-code chain, shutdown coordinator, watcher, and early-signal handling
2. Broadcast worker concurrent stop hardening
3. Runtime manager owned-snapshot stop and PID/create-time safety
4. Runtime prewarm background task and degraded startup behavior
5. Launcher core utilities: mutex, atomic files, port/config/process helpers
6. Launcher Start/Stop/Restart/Status/DryRun flows
7. Verification, rollback checks, and manual Windows validation

## Phase 1: Backend exit-code chain, shutdown coordinator, watcher, and early-signal handling

**Files:**
- Modify: `C:\Users\33031\Desktop\bot\src\langbot\__main__.py`
- Modify: `C:\Users\33031\Desktop\bot\src\langbot\pkg\core\app.py`
- Modify: `C:\Users\33031\Desktop\bot\src\langbot\pkg\core\boot.py`
- Modify: `C:\Users\33031\Desktop\bot\src\langbot\pkg\core\taskmgr.py`
- Create: `C:\Users\33031\Desktop\bot\src\langbot\pkg\core\local_shutdown_control.py`
- Modify: `C:\Users\33031\Desktop\bot\src\langbot\pkg\api\http\controller\main.py`
- Test: `C:\Users\33031\Desktop\bot\tests\unit_tests\core\test_boot.py`
- Test: `C:\Users\33031\Desktop\bot\tests\unit_tests\core\test_app_shutdown.py`
- Test: `C:\Users\33031\Desktop\bot\tests\unit_tests\core\test_local_shutdown_control.py`

- [ ] **Step 1: Write failing tests for exit-code propagation, signal-before-app, bounded task shutdown, pending shutdown, and local shutdown watcher**

```python
import asyncio
import signal
from types import SimpleNamespace

import pytest

from langbot import __main__ as langbot_main
from langbot.pkg.core import boot


@pytest.mark.asyncio
async def test_signal_before_app_created_sets_pending_shutdown_and_exits_cleanly(monkeypatch):
    captured_handler = {}
    observed = {}

    def fake_signal(sig, handler):
        captured_handler[sig] = handler

    async def fake_make_app(loop):
        captured_handler[signal.SIGINT](signal.SIGINT, None)
        app = SimpleNamespace()
        app.request_shutdown = lambda reason=None: observed.setdefault("reason", reason or "signal")
        async def fake_run():
            return 0
        app.run = fake_run
        app.dispose = lambda: observed.setdefault("disposed", True)
        return app

    monkeypatch.setattr(signal, "signal", fake_signal)
    monkeypatch.setattr(boot, "make_app", fake_make_app)

    await boot.main(SimpleNamespace())

    assert observed["reason"] in {"signal", "pending-signal"}


@pytest.mark.asyncio
async def test_application_run_requests_shutdown_when_critical_task_crashes_before_manual_shutdown():
    ...


@pytest.mark.asyncio
async def test_application_run_returns_nonzero_status_after_cleanup_when_critical_task_failed():
    ...


@pytest.mark.asyncio
async def test_boot_main_nonzero_exit_code_is_preserved_by_langbot_main_entry(monkeypatch):
    async def fake_boot_main(loop):
        return 1

    monkeypatch.setattr(langbot_main, "boot_main", fake_boot_main)

    exit_code = await langbot_main.main_entry()

    assert exit_code == 1


@pytest.mark.asyncio
async def test_local_shutdown_control_watcher_only_requests_shutdown_for_matching_session():
    ...


@pytest.mark.asyncio
async def test_cancel_and_wait_by_scope_is_bounded_and_excludes_shutdown_coordinator():
    ...
```

- [ ] **Step 2: Run targeted core lifecycle and watcher tests and confirm they fail first**

Run: `C:\Users\33031\Desktop\bot\.venv\Scripts\python.exe -m pytest tests\unit_tests\core\test_boot.py tests\unit_tests\core\test_app_shutdown.py tests\unit_tests\core\test_local_shutdown_control.py -q`

Expected: FAIL with missing shutdown coordinator / pending shutdown / bounded task collection / watcher / non-zero exit propagation coverage.

- [ ] **Step 3: Implement boot-level pending shutdown and non-zero failure propagation**

```python
# C:\Users\33031\Desktop\bot\src\langbot\pkg\core\boot.py
from __future__ import annotations

import asyncio
import signal
import traceback

from . import app


async def main(loop: asyncio.AbstractEventLoop) -> int:
    app_inst: app.Application | None = None
    pending_shutdown = False

    def signal_handler(sig, frame):
        nonlocal pending_shutdown, app_inst
        pending_shutdown = True
        if app_inst is not None:
            loop.call_soon_threadsafe(app_inst.request_shutdown, f"signal:{sig}")

    signal.signal(signal.SIGINT, signal_handler)

    try:
        app_inst = await make_app(loop)
        if pending_shutdown:
            app_inst.request_shutdown("pending-signal")
        return await app_inst.run()
    except Exception:
        if app_inst is not None:
            await app_inst.shutdown()
            app_inst.dispose()
        traceback.print_exc()
        return 1
```

- [ ] **Step 4: Preserve all current `src/langbot/__main__.py` behaviors and add exit-code propagation only**

```python
# C:\Users\33031\Desktop\bot\src\langbot\__main__.py
# keep existing:
# - argparse
# - --standalone-runtime
# - --standalone-box
# - --debug
# - Python version check
# - dependency check/install
# - config generation
# - data root / working directory setup
# - current explicit event loop lifecycle
#
# only change the return chain:
#   Application.run() -> int
#   boot.main() -> int
#   main_entry(loop) -> int
#   main() -> SystemExit(exit_code)
#
# and preserve:
# - normal shutdown => 0
# - critical task failure after cleanup => non-zero
```

- [ ] **Step 5: Implement bounded TaskManager shutdown collection API and use it from Application.shutdown()**

```python
# C:\Users\33031\Desktop\bot\src\langbot\pkg\core\taskmgr.py
class AsyncTaskManager:
    async def cancel_and_wait_by_scope(
        self,
        scope: core_entities.LifecycleControlScope,
        timeout: float,
    ) -> list[object]:
        wrappers = [
            wrapper
            for wrapper in list(self.tasks)
            if scope in wrapper.scopes and not wrapper.task.done()
        ]
        for wrapper in wrappers:
            wrapper.task.cancel()
        try:
            return await asyncio.wait_for(
                asyncio.gather(*[wrapper.task for wrapper in wrappers], return_exceptions=True),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            return []
```

Requirements:

- snapshot tasks first;
- cancel only the requested scope;
- bounded gather only;
- `return_exceptions=True`;
- timeout must not block later dispose;
- shutdown coordinator task is not in this set;
- do not use unbounded `wait_all()` for shutdown collection.

- [ ] **Step 6: Implement Application main-coroutine-owned shutdown coordinator and critical task monitoring**

```python
# C:\Users\33031\Desktop\bot\src\langbot\pkg\core\app.py
class Application:
    def __init__(self):
        self.shutdown_requested_event = asyncio.Event()
        self._shutdown_lock = asyncio.Lock()
        self._shutdown_started = False
        self._critical_failure: BaseException | None = None

    def request_shutdown(self, reason: str | None = None) -> None:
        self.shutdown_requested_event.set()

    async def run(self) -> int:
        critical_tasks = {
            "platform-manager": self.task_mgr.create_task(...).task,
            "query-controller": self.task_mgr.create_task(...).task,
            "http-api-controller": self.task_mgr.create_task(...).task,
        }
        shutdown_waiter = asyncio.create_task(self.shutdown_requested_event.wait(), name="shutdown-requested-waiter")
        try:
            while True:
                done, _ = await asyncio.wait(
                    [shutdown_waiter, *critical_tasks.values()],
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if shutdown_waiter in done:
                    break
                for name, task in critical_tasks.items():
                    if task in done and not self.shutdown_requested_event.is_set():
                        self._critical_failure = task.exception() or RuntimeError(f"{name} exited unexpectedly")
                        self.request_shutdown(f"critical-task:{name}")
                        break
                if self.shutdown_requested_event.is_set():
                    break
            await self.shutdown()
            return 1 if self._critical_failure is not None else 0
        finally:
            shutdown_waiter.cancel()
```

- [ ] **Step 7: Implement local graceful shutdown watcher as a dedicated module with optional enablement**

```python
# C:\Users\33031\Desktop\bot\src\langbot\pkg\core\local_shutdown_control.py
from __future__ import annotations

from pathlib import Path


class LocalShutdownControlWatcher:
    def __init__(self, *, app, repo_root: Path, session_id: str, request_path: str) -> None:
        self.app = app
        self.repo_root = repo_root
        self.session_id = session_id
        self.request_path = request_path

    def validate_control_path(self) -> Path:
        ...

    def consume_shutdown_request(self) -> bool:
        # validate path
        # read JSON once
        # sessionId match required
        # consume accepted or malformed file
        # call app.request_shutdown() only
        ...

    async def watch(self) -> None:
        while not self.app.shutdown_requested_event.is_set():
            self.consume_shutdown_request()
            await asyncio.sleep(0.5)


def build_local_shutdown_watcher_from_env(*, app, repo_root: Path):
    # create watcher only when BOTH env vars exist and validate:
    # - LANGBOT_LOCAL_STACK_SESSION_ID
    # - LANGBOT_LOCAL_SHUTDOWN_REQUEST_PATH
    # if missing -> return None without error
    # if path escapes repo control dir -> warning and return None
```

- [ ] **Step 8: Add internal HTTP shutdown event wiring**

```python
# C:\Users\33031\Desktop\bot\src\langbot\pkg\api\http\controller\main.py
class HTTPController:
    def __init__(self, ap):
        self._shutdown_event = asyncio.Event()

    def request_shutdown(self) -> None:
        self._shutdown_event.set()

    def run(self):
        return self._run_with_readiness(..., shutdown_trigger=self._shutdown_event.wait)
```

- [ ] **Step 9: Wire optional watcher into app startup as an `APPLICATION` scope task while keeping shutdown coordination in `Application.run()`**

```python
# C:\Users\33031\Desktop\bot\src\langbot\pkg\core\stages\build_app.py
watcher = build_local_shutdown_watcher_from_env(app=ap, repo_root=...)
ap.local_shutdown_control_watcher = watcher
if watcher is not None:
    ap.task_mgr.create_task(
        watcher.watch(),
        name="local-shutdown-control-watcher",
        scopes=[core_entities.LifecycleControlScope.APPLICATION],
    )
```

- [ ] **Step 10: Re-run core lifecycle tests**

Run: `C:\Users\33031\Desktop\bot\.venv\Scripts\python.exe -m pytest tests\unit_tests\core\test_boot.py tests\unit_tests\core\test_app_shutdown.py tests\unit_tests\core\test_local_shutdown_control.py -q`

Expected: PASS

## Phase 2: Broadcast worker concurrent stop hardening

**Files:**
- Modify: `C:\Users\33031\Desktop\bot\src\langbot\pkg\broadcast\worker.py`
- Modify: `C:\Users\33031\Desktop\bot\src\langbot\pkg\core\app.py`
- Test: `C:\Users\33031\Desktop\bot\tests\unit_tests\core\test_app_shutdown.py`

- [ ] **Step 1: Write failing tests for concurrent stop calls and timeout-contained worker shutdown**

```python
@pytest.mark.asyncio
async def test_broadcast_worker_stop_is_idempotent_when_called_twice_concurrently():
    ...


@pytest.mark.asyncio
async def test_application_shutdown_does_not_touch_worker_private_runner_task():
    ...
```

- [ ] **Step 2: Run worker/shutdown tests and confirm failure**

Run: `C:\Users\33031\Desktop\bot\.venv\Scripts\python.exe -m pytest tests\unit_tests\core\test_app_shutdown.py -q`

Expected: FAIL with missing concurrency-safe stop behavior.

- [ ] **Step 3: Implement worker-owned stop single-flight logic**

```python
# C:\Users\33031\Desktop\bot\src\langbot\pkg\broadcast\worker.py
class BroadcastExecutionWorker:
    def __init__(self, *, service, scope=None, poll_interval: float = 0.5) -> None:
        ...
        self._stop_lock = asyncio.Lock()
        self._stop_task: asyncio.Task[None] | None = None

    async def stop(self) -> None:
        async with self._stop_lock:
            if self._stop_task is None or self._stop_task.done():
                self._stop_task = asyncio.create_task(self._stop_once(), name="broadcast-worker-stop")
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
```

- [ ] **Step 4: Update Application.shutdown() to call only the public worker API**

```python
# C:\Users\33031\Desktop\bot\src\langbot\pkg\core\app.py
if self.broadcast_execution_worker is not None:
    await self.broadcast_execution_worker.stop()
```

- [ ] **Step 5: Re-run worker lifecycle tests**

Run: `C:\Users\33031\Desktop\bot\.venv\Scripts\python.exe -m pytest tests\unit_tests\core\test_app_shutdown.py -q`

Expected: PASS

## Phase 3: Runtime manager owned-snapshot stop and PID/create-time safety

**Files:**
- Modify: `C:\Users\33031\Desktop\bot\src\langbot\pkg\desktop_automation\runtime_process.py`
- Modify: `C:\Users\33031\Desktop\bot\src\langbot\pkg\desktop_automation\service.py`
- Test: `C:\Users\33031\Desktop\bot\tests\unit_tests\desktop_automation\test_runtime_process.py`
- Test: `C:\Users\33031\Desktop\bot\tests\unit_tests\desktop_automation\test_service.py`

- [ ] **Step 1: Write failing tests for `_stop_locked()`, handshake PID validation, process create-time ownership, and PID reuse protection**

```python
@pytest.mark.asyncio
async def test_runtime_stop_uses_owned_snapshot_and_clears_fields_in_finally():
    ...


@pytest.mark.asyncio
async def test_runtime_stop_does_not_kill_reused_pid_when_create_time_differs(monkeypatch):
    ...


@pytest.mark.asyncio
async def test_runtime_spawn_records_pid_create_time(monkeypatch):
    ...


@pytest.mark.asyncio
async def test_runtime_handshake_pid_mismatch_stops_spawned_process_and_fails(monkeypatch):
    ...
```

- [ ] **Step 2: Run desktop automation unit tests and confirm red state**

Run: `C:\Users\33031\Desktop\bot\.venv\Scripts\python.exe -m pytest tests\unit_tests\desktop_automation -q`

Expected: FAIL with missing snapshot/create-time stop protections.

- [ ] **Step 3: Implement spawn-time PID/create-time capture**

```python
# C:\Users\33031\Desktop\bot\src\langbot\pkg\desktop_automation\runtime_process.py
runtime_info = {
    "pid": int(handshake["pid"]),
    "processCreateTime": self._read_process_create_time(self.process.pid),
    ...
}
```

- [ ] **Step 4: Validate `handshake["pid"] == self.process.pid` before creating a client**

```python
# C:\Users\33031\Desktop\bot\src\langbot\pkg\desktop_automation\runtime_process.py
spawn_pid = int(getattr(self.process, "pid"))
if int(handshake["pid"]) != spawn_pid:
    await self._stop_locked()
    raise DesktopAutomationError(RUNTIME_START_FAILED, "Desktop runtime handshake pid mismatch")
```

Requirements:

- compare handshake PID to the spawned process PID;
- on mismatch call locked `_stop_locked()`;
- do not create client;
- return `RUNTIME_START_FAILED`;
- do not leave Runtime/Electron children behind;
- `processCreateTime` must come from the same spawn PID.

- [ ] **Step 5: Split public `stop()` and locked `_stop_locked()` with owned snapshot**

```python
async def stop(self) -> None:
    async with self._lock:
        await self._stop_locked()


async def _stop_locked(self) -> None:
    snapshot = self._build_owned_snapshot()
    if snapshot is None:
        return
    self._stopping = True
    try:
        await self._terminate_owned_runtime_snapshot(snapshot)
    finally:
        self.process = None
        self.client = None
        self.runtime_info = None
        self._stderr_task = None
        self._selected_runtime_executable = None
        self._stopping = False
```

- [ ] **Step 6: Implement asyncio-subprocess to psutil conversion and ordered tree termination**

```python
def _resolve_owned_psutil_process(self, snapshot) -> psutil.Process | None:
    try:
        proc = psutil.Process(snapshot.pid)
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return None
    if proc.create_time() != snapshot.process_create_time:
        return None
    if _normalize_path(proc.exe()) != snapshot.selected_runtime_executable:
        return None
    return proc


def _terminate_psutil_tree(self, proc: psutil.Process) -> None:
    children = proc.children(recursive=True)
    for child in children:
        ...
    proc.terminate()
    ...
```

- [ ] **Step 7: Update ensure_started() failure paths to call `_stop_locked()` only while lock is held**

```python
if str(handshake["protocolVersion"]) != expected_protocol_version:
    await self._stop_locked()
    raise DesktopAutomationError(...)
```

- [ ] **Step 8: Keep `DesktopAutomationService.shutdown()` async-first and fallback `close()` minimal**

```python
async def shutdown(self) -> None:
    if self.runtime_process_manager is not None:
        await self.runtime_process_manager.stop()
```

- [ ] **Step 9: Re-run desktop automation tests**

Run: `C:\Users\33031\Desktop\bot\.venv\Scripts\python.exe -m pytest tests\unit_tests\desktop_automation -q`

Expected: PASS

## Phase 4: Runtime prewarm background task and degraded startup behavior

**Files:**
- Modify: `C:\Users\33031\Desktop\bot\src\langbot\pkg\core\app.py`
- Modify: `C:\Users\33031\Desktop\bot\src\langbot\pkg\core\stages\build_app.py`
- Test: `C:\Users\33031\Desktop\bot\tests\unit_tests\core\test_app_shutdown.py`
- Test: `C:\Users\33031\Desktop\bot\tests\unit_tests\desktop_automation\test_service.py`

- [ ] **Step 1: Write failing tests for background prewarm scheduling and degraded non-blocking startup**

```python
@pytest.mark.asyncio
async def test_runtime_prewarm_is_scheduled_as_application_task_when_enabled():
    ...


@pytest.mark.asyncio
async def test_runtime_prewarm_failure_does_not_fail_http_startup():
    ...
```

- [ ] **Step 2: Run targeted tests and confirm failure**

Run: `C:\Users\33031\Desktop\bot\.venv\Scripts\python.exe -m pytest tests\unit_tests\core\test_app_shutdown.py tests\unit_tests\desktop_automation\test_service.py -q`

Expected: FAIL due to missing background prewarm task behavior.

- [ ] **Step 3: Implement prewarm scheduler in Application.initialize() or equivalent hook**

```python
# C:\Users\33031\Desktop\bot\src\langbot\pkg\core\app.py
async def initialize(self):
    if not self.instance_config.data["desktop_automation"]["enabled"]:
        self.logger.info("Desktop runtime disabled.")
        return

    async def prewarm_runtime():
        try:
            await self.desktop_automation_service.ensure_runtime_client()
            self.logger.info("Desktop runtime ready (prewarm).")
        except Exception as exc:
            self.logger.warning("Desktop runtime prewarm degraded: %s", exc)

    self.task_mgr.create_task(
        prewarm_runtime(),
        name="desktop-runtime-prewarm",
        scopes=[core_entities.LifecycleControlScope.APPLICATION],
    )
```

- [ ] **Step 4: Ensure BuildAppStage no longer blocks on Runtime prewarm**

```python
# C:\Users\33031\Desktop\bot\src\langbot\pkg\core\stages\build_app.py
# Build service objects only; do not await ensure_runtime_client() here.
```

- [ ] **Step 5: Re-run targeted prewarm tests**

Run: `C:\Users\33031\Desktop\bot\.venv\Scripts\python.exe -m pytest tests\unit_tests\core\test_app_shutdown.py tests\unit_tests\desktop_automation\test_service.py -q`

Expected: PASS

## Phase 5: Launcher core utilities — mutex, atomic files, port/config/process helpers

**Files:**
- Create: `C:\Users\33031\Desktop\bot\scripts\start-local.ps1`
- Modify if needed: `C:\Users\33031\Desktop\bot\.gitignore`
- Test: `C:\Users\33031\Desktop\bot\scripts\tests\start-local.Tests.ps1`

- [ ] **Step 1: Write failing PowerShell tests or dry-run assertions for mutex, atomic state writes, TCP ownership checks, and direct file redirection**

```powershell
Describe "start-local core helpers" {
  It "uses repo-scoped launcher mutex for Start/Stop/Restart" {
    # placeholder for helper-level verification
  }

  It "writes state.json through atomic replace" {
    # helper should emit temp path + replace sequence
  }

  It "refuses unknown occupied backend port before startup" {
    # TCP listener exists, but no matching repo-owned process
  }

  It "uses File.Replace when the target already exists and Move when creating for the first time" {
    # verify atomic writer behavior
  }
}
```

- [ ] **Step 2: Verify whether `.tmp/` needs to be ignored**

Run: `Get-Content -Path 'C:\Users\33031\Desktop\bot\.gitignore'`

Expected: If `.tmp/` is missing, plan to add exactly:

```gitignore
.tmp/
```

- [ ] **Step 3: Implement PowerShell helper functions for repo mutex, atomic files, and config loading**

```powershell
# C:\Users\33031\Desktop\bot\scripts\start-local.ps1
function Acquire-LauncherMutex {
  param([string]$MutexName, [int]$TimeoutMs = 15000)
  $mutex = New-Object System.Threading.Mutex($false, $MutexName)
  if (-not $mutex.WaitOne($TimeoutMs)) {
    throw "Another launcher operation is already in progress."
  }
  return $mutex
}

function Write-JsonAtomically {
  param([string]$Path, [object]$Data)
  $tmp = "$Path.tmp"
  $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
  try {
    [System.IO.File]::WriteAllText($tmp, ($Data | ConvertTo-Json -Depth 8), $utf8NoBom)
    if (Test-Path -LiteralPath $Path) {
      [System.IO.File]::Replace($tmp, $Path, $null, $true)
    } else {
      [System.IO.File]::Move($tmp, $Path)
    }
  } finally {
    if (Test-Path -LiteralPath $tmp) { Remove-Item -LiteralPath $tmp -Force -ErrorAction SilentlyContinue }
  }
}
```

- [ ] **Step 4: Implement TCP port-listener and repo ownership helpers**

```powershell
function Test-TcpPortListening {
  param([string]$Host, [int]$Port)
  # use TcpClient connect with short timeout
}

function Get-ProcessIdentitySnapshot {
  param([int]$Pid)
  # return PID, CreationDate, ExecutablePath, CommandLine
}

function Test-BackendOwnership {
  param($Identity, [string]$RepoRoot, [string]$PythonPath, [string]$MainPath, [double]$ProcessStartTimeUtcTicks)
}
```

- [ ] **Step 5: Implement Windows PowerShell 5.1 `Start-Process` direct file redirection for child process logs**

```powershell
function Start-ManagedProcess {
  param(
    [string]$FilePath,
    [string[]]$ArgumentList,
    [string]$WorkingDirectory,
    [hashtable]$Environment,
    [string]$StdoutLogPath,
    [string]$StderrLogPath
  )

  $savedEnv = @{}
  try {
    foreach ($key in $Environment.Keys) {
      $savedEnv[$key] = [System.Environment]::GetEnvironmentVariable($key, "Process")
      [System.Environment]::SetEnvironmentVariable($key, [string]$Environment[$key], "Process")
    }
    $proc = Start-Process `
      -FilePath $FilePath `
      -ArgumentList $ArgumentList `
      -WorkingDirectory $WorkingDirectory `
      -RedirectStandardOutput $StdoutLogPath `
      -RedirectStandardError $StderrLogPath `
      -PassThru
    return $proc
  } finally {
    foreach ($key in $Environment.Keys) {
      [System.Environment]::SetEnvironmentVariable($key, $savedEnv[$key], "Process")
    }
  }
}
```

Requirements:

- launcher does not keep long-lived stdout/stderr readers;
- child output goes directly to files;
- environment is overridden only for launch and restored in `finally`.

- [ ] **Step 6: Re-run helper-level tests or dry-run checks**

Run: `powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\Users\33031\Desktop\bot\scripts\start-local.ps1 -Action Start -WebMode Bundled -DryRun`

Expected: No file writes, no process launches, helper output only.

## Phase 6: Launcher Start/Stop/Restart/Status/DryRun flows

**Files:**
- Create: `C:\Users\33031\Desktop\bot\scripts\start-local.ps1`
- Create: `C:\Users\33031\Desktop\bot\scripts\start-local.cmd`
- Test: `C:\Users\33031\Desktop\bot\scripts\tests\start-local.Tests.ps1`

- [ ] **Step 1: Write failing tests for provisional state, graceful shutdown request, Dev absolute pnpm path, and PID/create-time ownership validation**

```powershell
Describe "start-local lifecycle flows" {
  It "stores processStartTimeUtcTicks in backend and web state" { }
  It "writes shutdown control file with matching sessionId on Stop" { }
  It "uses absolute pnpm.cmd path and absolute repo web path in Dev mode" { }
  It "refuses to kill a reused PID when creation time differs" { }
  It "forwards all CMD arguments to start-local.ps1 through %*" { }
}
```

- [ ] **Step 2: Implement Start flow with provisional state and unknown-port rejection**

```powershell
function Start-BackendStack {
  param([string]$WebMode)
  # 1) Acquire mutex
  # 2) Resolve config host/port
  # 3) If TCP listening and ownership unknown -> throw conflict
  # 4) Start backend via Start-Process
  # 5) Capture PID + processStartTimeUtcTicks
  # 6) Write state status=starting atomically
  # 7) Wait /healthz
  # 8) Update state status=running
}
```

- [ ] **Step 3: Implement graceful Stop/Restart via control file**

```powershell
function Request-GracefulBackendShutdown {
  param([string]$ControlPath, [string]$SessionId)
  $payload = @{
    sessionId = $SessionId
    action = "shutdown"
    requestedAt = [DateTime]::UtcNow.ToString("o")
    reason = "launcher-stop"
  }
  Write-JsonAtomically -Path $ControlPath -Data $payload
}

function Stop-BackendStack {
  # stop web first
  # write shutdown request
  # wait for backend exit
  # if timeout -> validate pid/create_time/exe/cmd/repoRoot -> taskkill /T /PID
  # print "graceful shutdown timed out" when forced
}
```

- [ ] **Step 4: Implement Dev mode absolute `pnpm.cmd` launch**

```powershell
function Resolve-PnpmCmdPath {
  $cmd = Get-Command pnpm.cmd -ErrorAction Stop
  return $cmd.Source
}

function Start-WebDevServer {
  param([string]$RepoRoot, [string]$BackendUrl)
  $pnpm = Resolve-PnpmCmdPath
  $webPath = Join-Path $RepoRoot "web"
  $cmdArgs = @("/d", "/s", "/c", ('"{0}" --dir "{1}" dev' -f $pnpm, $webPath))
  Start-ManagedProcess -FilePath "cmd.exe" -ArgumentList $cmdArgs ...
}
```

- [ ] **Step 5: Use `processStartTimeUtcTicks` as the canonical launcher process identity field**

```powershell
function Get-ProcessStartTimeUtcTicks {
  param([int]$Pid)
  return [System.Diagnostics.Process]::GetProcessById($Pid).StartTime.ToUniversalTime().Ticks
}
```

Requirements:

- state stores `processStartTimeUtcTicks`, not `processCreatedAt`;
- stop-time validation re-reads ticks and compares as integers;
- CIM/WMI is used only for `ExecutablePath` and `CommandLine`;
- ownership must match:
  - PID
  - `processStartTimeUtcTicks`
  - `ExecutablePath`
  - `CommandLine`
  - `repoRoot`

- [ ] **Step 6: Implement Status and DryRun boundaries**

```powershell
function Get-StackStatus {
  # backend: pid + creation time + /healthz
  # web: pid + creation time + port/http if dev
  # runtime: fixed managed-by-backend
}
```

- [ ] **Step 7: Implement rollback paths for failed backend or Dev startup**

```powershell
function Rollback-PartialStart {
  # stop only repo-owned processes from this attempt
  # delete provisional state
}
```

- [ ] **Step 8: Implement thin CMD wrapper with `%*` forwarding and failure-only pause**

```bat
@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-local.ps1" %*
set "EXITCODE=%ERRORLEVEL%"
if not "%EXITCODE%"=="0" pause
exit /b %EXITCODE%
```

- [ ] **Step 9: Re-run PowerShell dry-run commands**

Run: `powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\Users\33031\Desktop\bot\scripts\start-local.ps1 -Action Restart -WebMode Bundled -DryRun`

Expected: Shows backend command, mode, URLs, PIDs to check, safe-send disabled, Runtime managed by backend.

- [ ] **Step 10: Re-run Dev dry-run command**

Run: `powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\Users\33031\Desktop\bot\scripts\start-local.ps1 -Action Restart -WebMode Dev -DryRun`

Expected: Shows absolute `pnpm.cmd`, absolute `web` path, no writes or process launches.

## Phase 7: Verification, rollback checks, and manual Windows validation

**Files:**
- Verify all modified files

- [ ] **Step 1: Run backend desktop automation tests**

Run: `C:\Users\33031\Desktop\bot\.venv\Scripts\python.exe -m pytest tests\unit_tests\desktop_automation -q`

Expected: PASS

- [ ] **Step 2: Run backend core lifecycle tests**

Run: `C:\Users\33031\Desktop\bot\.venv\Scripts\python.exe -m pytest tests\unit_tests\core -q`

Expected: PASS

- [ ] **Step 3: Run PowerShell dry-run verification**

Run: `powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\Users\33031\Desktop\bot\scripts\start-local.ps1 -Action Restart -WebMode Bundled -DryRun`

Expected: PASS, no persistent writes

- [ ] **Step 4: Run PowerShell Dev dry-run verification**

Run: `powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\Users\33031\Desktop\bot\scripts\start-local.ps1 -Action Restart -WebMode Dev -DryRun`

Expected: PASS, absolute `pnpm.cmd` and absolute repo `web` path reported

- [ ] **Step 5: Manual Bundled validation**

Run: `powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\Users\33031\Desktop\bot\scripts\start-local.ps1 -Action Restart -WebMode Bundled -NoBrowser`

Expected:
- backend starts
- provisional state becomes running
- `/healthz` returns ok
- Runtime is started by backend only
- real sending remains disabled
- no Vite dev process in Bundled mode

- [ ] **Step 6: Manual Status validation**

Run: `powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\Users\33031\Desktop\bot\scripts\start-local.ps1 -Action Status`

Expected:
- Backend ok/down correctly shown
- Web ok/down/not-used correctly shown
- Runtime shown as `managed-by-backend`

- [ ] **Step 7: Manual graceful Stop validation**

Run: `powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\Users\33031\Desktop\bot\scripts\start-local.ps1 -Action Stop`

Expected:
- shutdown control file written then consumed
- backend exits normally when healthy
- Runtime main process and Electron children stop with backend
- no unrelated Python/Node processes touched
- `data\langbot.db` still exists
- `runtime\broadcast_attachments` still exists

- [ ] **Step 8: Manual Dev validation**

Run: `powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\Users\33031\Desktop\bot\scripts\start-local.ps1 -Action Restart -WebMode Dev -NoBrowser`

Expected:
- backend healthy
- `cmd.exe` root process launches absolute `pnpm.cmd` with absolute repo `web` path
- `http://127.0.0.1:3000` available
- Vite root PID stored with `processStartTimeUtcTicks`

- [ ] **Step 9: Run repository diff sanity checks**

Run: `git diff --check`

Expected: no whitespace/conflict errors

- [ ] **Step 10: Run repository status check**

Run: `git status --short`

Expected: only intended modified/new files

- [ ] **Step 11: Run repository diff summary**

Run: `git diff --stat`

Expected: summary of intended lifecycle + launcher changes

## Verification Plan

### Test-first verification order

1. `C:\Users\33031\Desktop\bot\.venv\Scripts\python.exe -m pytest tests\unit_tests\core\test_boot.py tests\unit_tests\core\test_app_shutdown.py tests\unit_tests\core\test_local_shutdown_control.py -q`
2. `C:\Users\33031\Desktop\bot\.venv\Scripts\python.exe -m pytest tests\unit_tests\desktop_automation\test_runtime_process.py tests\unit_tests\desktop_automation\test_service.py -q`
3. `C:\Users\33031\Desktop\bot\.venv\Scripts\python.exe -m pytest tests\unit_tests\core -q`
4. `C:\Users\33031\Desktop\bot\.venv\Scripts\python.exe -m pytest tests\unit_tests\desktop_automation -q`

Must explicitly cover:

- boot/main exit code propagation through `src/langbot/__main__.py`
- `AsyncTaskManager.cancel_and_wait_by_scope(...)`
- optional watcher enablement / invalid path disablement
- Runtime handshake PID mismatch cleanup
- launcher `processStartTimeUtcTicks` identity checks

### Launcher dry-run verification

1. `powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\Users\33031\Desktop\bot\scripts\start-local.ps1 -Action Restart -WebMode Bundled -DryRun`
2. `powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\Users\33031\Desktop\bot\scripts\start-local.ps1 -Action Restart -WebMode Dev -DryRun`

### Manual graceful shutdown verification

1. `powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\Users\33031\Desktop\bot\scripts\start-local.ps1 -Action Restart -WebMode Bundled -NoBrowser`
2. `powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\Users\33031\Desktop\bot\scripts\start-local.ps1 -Action Status`
3. `powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\Users\33031\Desktop\bot\scripts\start-local.ps1 -Action Stop`

Verify:

- backend exits with code `0` for user Stop / Ctrl+C / control-file shutdown;
- backend exits with non-zero when a critical long-lived task crashes unexpectedly after cleanup;
- Runtime follows backend exit when shutdown is graceful;
- forced backend kill, if required, prints `graceful shutdown timed out` and does not claim graceful Runtime cleanup.

### Manual Dev verification

1. `powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\Users\33031\Desktop\bot\scripts\start-local.ps1 -Action Restart -WebMode Dev -NoBrowser`
2. `powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\Users\33031\Desktop\bot\scripts\start-local.ps1 -Action Status`
3. `powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\Users\33031\Desktop\bot\scripts\start-local.ps1 -Action Stop`

Verify:

- Dev launch uses absolute `pnpm.cmd` and absolute `web` path;
- `cmd.exe` root PID is stored with `processStartTimeUtcTicks`;
- port `3000` unknown ownership blocks startup instead of being adopted.

## Rollback and Failure Handling Checklist

- Backend startup failure after provisional state write:
  - stop only the just-started repo-owned backend process
  - close log writers
  - remove `state.json`
- Dev startup failure after backend success:
  - stop repo-owned Vite root process
  - stop just-started repo-owned backend if this run was a fresh start/restart
  - remove provisional state
- Graceful stop timeout:
  - force-kill only repo-owned backend pid after PID/create_time/exe/cmd/repoRoot validation
  - print `graceful shutdown timed out`
  - do not claim Runtime cleaned up gracefully
- PID reuse detected:
  - refuse termination
  - warn
  - leave stale cleanup to next safe startup path if applicable
- Unknown port listener:
  - refuse startup
  - do not adopt or kill

## Required Implementation Constraints To Preserve

1. `Application.run()` must monitor critical long-lived tasks and convert unexpected task death into shutdown + non-zero exit.
2. PID reuse protection must rely on process creation time for both backend/runtime and launcher-managed backend/web processes.
3. `src/langbot\__main__.py` must preserve non-zero exit codes all the way to `SystemExit(exit_code)`.
4. Dev startup must resolve absolute `pnpm.cmd` and include absolute repo `web` path in `cmd.exe` command line.
5. TCP listener protection must reject unknown ownership even if `/healthz` succeeds.
6. Early Ctrl+C before app construction completes must still request shutdown through a pending mechanism.
7. Local shutdown watcher must validate repo-local control path, consume accepted requests once, and only call `Application.request_shutdown()`.
8. PowerShell 5.1 launcher startup must use direct stdout/stderr file redirection via `Start-Process`, with temporary process-scope environment overrides restored after launch.
9. Atomic JSON writes must use UTF-8 without BOM plus `File.Replace` for existing targets and `File.Move` for first creation.
10. Runtime handshake PID must match the spawn PID before client creation.
11. Launcher process identity must use `processStartTimeUtcTicks` for backend and web state records.
12. Watcher creation is optional and only enabled when both local-stack environment variables are present and valid.

## Self-Review

- Plan includes spec-mandated shutdown coordinator ownership.
- Plan includes explicit non-zero exit handling for critical task failure.
- Plan includes PID/create-time checks, not command-line-only checks.
- Plan includes `__main__.py` exit-code propagation while preserving the existing CLI/bootstrap behaviors.
- Plan includes bounded `TaskManager` cancellation instead of using unbounded `wait_all()` for shutdown collection.
- Plan includes PowerShell 5.1-compatible direct file redirection rather than launcher-owned long-lived pipe readers.
- Plan includes repo-scoped launcher mutex and atomic state/control file writes.
- Plan includes dry-run, Bundled, Dev, graceful stop, rollback, and diff verification.

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-07-06-local-startup-runtime-lifecycle-implementation.md`. Two execution options:**

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
