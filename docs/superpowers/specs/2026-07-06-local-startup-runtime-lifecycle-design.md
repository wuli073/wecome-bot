# Historical: Windows Local Startup and Runtime Lifecycle Design

**Date:** 2026-07-06
**Scope:** Windows local launcher + backend-owned desktop Runtime shutdown/prewarm lifecycle
**Status:** Historical design draft, superseded by the Runtime self-generated-token handshake protocol. This document is retained for design history only and is not current operational guidance.

## 1. Goal

Implement a Windows one-click local startup flow where:

- the Python backend remains the only owner of the desktop Runtime process;
- the backend can shut the Runtime down reliably during normal exit;
- a thin PowerShell launcher manages only the backend and optional Vite dev server;
- Runtime prewarm remains backend-owned and never blocks the rest of the backend from starting.

## 2. Explicit Non-Goals

This design does **not**:

- add a public or unauthenticated HTTP shutdown endpoint;
- let the launcher start, inspect, or stop `LangBot Desktop RPA Runtime.exe` directly;
- let the launcher generate or store a Runtime authentication token;
- let the launcher read Runtime handshake data or Runtime random ports;
- add a second Runtime process manager, Windows Service, login bypass, or debug backdoor;
- modify Broadcast business logic, paste-only state machine, attachment logic, or send safety lock.

## 3. Existing Root Cause

Runtime processes can remain after backend exit because the current normal-exit path does not await asynchronous desktop automation cleanup:

1. `src/langbot/pkg/core/boot.py` installs a signal handler.
2. The signal handler currently disposes synchronously and exits the process directly.
3. `DesktopAutomationService.shutdown()` is not part of the normal awaited exit path.
4. `DesktopRuntimeProcessManager.stop()` is therefore skipped during normal exit.
5. The Runtime main process and Electron child processes can outlive the backend.

The fix is to route normal exit through an idempotent async shutdown path and reserve synchronous cleanup for exceptional fallback only.

## 4. Architecture Overview

### 4.1 Process ownership

Normal mode:

```text
start-local.ps1
└─ Python backend
   └─ DesktopRuntimeProcessManager
      └─ LangBot Desktop RPA Runtime.exe
```

Dev mode:

```text
start-local.ps1
├─ Python backend
│  └─ DesktopRuntimeProcessManager
│     └─ LangBot Desktop RPA Runtime.exe
└─ pnpm --dir web dev
```

### 4.2 Responsibility boundary

**Backend owns:**

- Runtime executable selection;
- stale Runtime replacement logic;
- Runtime authentication-token generation;
- Runtime spawn;
- stdout handshake parsing;
- Runtime client creation;
- Runtime ready waiting;
- Runtime prewarm;
- Runtime stop and process-tree cleanup.

**Launcher owns:**

- backend process start/stop/restart/status;
- Vite root process start/stop/restart/status in Dev mode;
- local state/log files under `.tmp/local-stack`;
- graceful backend shutdown request via control file;
- backend `/healthz` probing.

**Launcher never owns:**

- Runtime tokens;
- Runtime ports;
- Runtime ready detection;
- Runtime process lifecycle.

## 5. Backend Normal Shutdown Design

## 5.1 Signal handling rules

`src/langbot/pkg/core/boot.py` will be updated so that:

- the signal handler never `await`s directly;
- the signal handler never performs blocking cleanup;
- the signal handler does not call `os._exit(0)` on the normal path;
- the signal handler only requests shutdown, for example via:
  - `loop.call_soon_threadsafe(...)` to schedule `Application.request_shutdown()`;
  - or setting an internal `asyncio.Event`;
- the signal handler never performs the real cleanup itself.

Repeated signals must be idempotent and must not spawn multiple shutdown tasks.

## 5.2 Unified async shutdown entrypoint

`src/langbot/pkg/core/app.py` will gain:

- `Application.request_shutdown(reason: str | None = None) -> None`
- `Application.shutdown() -> Awaitable[None]`
- `Application.shutdown_requested_event: asyncio.Event`

`request_shutdown()` only marks or schedules shutdown.
`shutdown()` performs the real cleanup and is safe to call multiple times.

### Shutdown coordinator ownership

The shutdown coordinator must **not** belong to `AsyncTaskManager`.

Required control flow:

1. signal handler calls `Application.request_shutdown()`;
2. shutdown control watcher calls `Application.request_shutdown()`;
3. both only set state / `shutdown_requested_event`;
4. `Application.run()` main coroutine waits:
   - `await shutdown_requested_event.wait()`
5. after the wait completes, `Application.run()` itself calls:
   - `await Application.shutdown()`

This ensures the real shutdown sequence is owned by the main application coroutine rather than by an `APPLICATION` scope background task that could be cancelled by `cancel_by_scope(APPLICATION)`.

## 5.3 Fixed shutdown order

Normal backend shutdown must follow this order:

1. `Application.run()` main coroutine waits for `shutdown_requested_event`;
2. `await Application.shutdown()`;
3. mark `shutting_down`;
4. request HTTP shutdown so new requests stop being accepted;
5. stop `BroadcastExecutionWorker` with a bounded timeout;
6. `await DesktopAutomationService.shutdown()`;
7. `await DesktopRuntimeProcessManager.stop()`;
8. cancel `APPLICATION` scope tasks;
9. await task-manager drain/collection;
10. run final synchronous `dispose()` fallback;
11. return from `Application.run()`;
12. return normally from `boot.main()`.

Any failure in one step is logged and does not prevent later cleanup steps from running.

Normal shutdown must not call `os._exit(0)`.

## 5.4 HTTP shutdown integration

`src/langbot/pkg/api/http/controller/main.py` will switch from the current infinite placeholder trigger to an internal `asyncio.Event`.

New internal API:

- `HTTPController.request_shutdown()`
- Hypercorn `shutdown_trigger` waits on the internal event.

`Application.shutdown()` will call `http_ctrl.request_shutdown()` early so the HTTP service stops accepting new requests before task and Runtime cleanup continues.

No new public route, no public control API, and no unauthenticated management interface will be added.

## 5.5 Broadcast worker bounded stop

`Application.shutdown()` will treat the Broadcast worker as bounded cleanup, but timeout/cancellation enforcement must be encapsulated **inside the worker**, not in `Application`.

`BroadcastExecutionWorker.stop()` must become:

- idempotent;
- concurrency-safe;
- safe if called both from Quart `after_serving` and from `Application.shutdown()`.

Suggested implementation shape:

- internal `_stop_lock`;
- internal shared `_stop_task` or equivalent single-flight mechanism;
- worker-owned timeout handling;
- worker-owned fallback cancellation of its own runner.

`Application` must not access worker private fields such as `_runner_task`.

This prevents double-stop races and keeps stop semantics inside the worker abstraction.

## 5.6 Task manager收口

After Runtime cleanup:

- cancel all `APPLICATION` scope tasks through the existing task manager;
- wait for outstanding tasks with bounded gathering/collection;
- tolerate cancelled tasks and log unexpected exceptions;
- continue to final disposal even if some background tasks misbehave.

The current permanent `never_ending()` task must be removed or replaced. `Application.run()` should stay alive by awaiting the explicit shutdown coordinator event plus the managed long-lived server/platform tasks, not by using an artificial forever task.

## 6. Backend Graceful Stop Control Channel

The launcher must not rely on `Stop-Process`/`taskkill` for the normal stop path because that bypasses Python async shutdown.

## 6.1 Control file path

The launcher and backend will use a non-HTTP shutdown control file:

```text
.tmp/local-stack/control/shutdown.request.json
```

Absolute path is passed to the backend through:

- `LANGBOT_LOCAL_STACK_SESSION_ID=<random sessionId>`
- `LANGBOT_LOCAL_SHUTDOWN_REQUEST_PATH=<absolute path>`

The same non-sensitive `sessionId` is also stored in `state.json`.

## 6.2 Control file protocol

The launcher writes a request atomically. Proposed payload:

```json
{
  "sessionId": "7dcb5a7b4c0f4f9498f7d69e2f77b2b5",
  "action": "shutdown",
  "requestedAt": "2026-07-06T12:34:56.789Z",
  "reason": "launcher-stop"
}
```

Rules:

- the launcher writes to a temp file in the same directory and renames it atomically;
- the backend only accepts a request whose `sessionId` matches its own environment session;
- old-session files are ignored;
- backend startup removes or ignores stale files from older sessions;
- after a valid request is consumed, the backend deletes it or atomically moves it away so it is not processed twice;
- malformed request files are logged once and then deleted or moved aside to avoid log storms;
- the backend must verify that the configured shutdown request path is inside the current repo:
  `.tmp/local-stack/control/`;
- the backend must not operate on an arbitrary path supplied by the environment;
- the control file contains no token or credential.

## 6.3 Backend watch mechanism

During initialization, the backend starts a lightweight background watcher task, scoped to `APPLICATION`, that:

- polls for the shutdown request file;
- parses JSON safely;
- validates `sessionId`;
- calls `Application.request_shutdown()` when a valid request is observed;
- atomically consumes the accepted request file.

The watcher must be idempotent and must not call shutdown twice.

## 6.4 Launcher Stop/Restart behavior

For `Stop` or `Restart`, the launcher must:

1. atomically write the shutdown request file with the current `sessionId`;
2. wait for backend process exit within a bounded timeout;
3. only if that timeout expires:
   - verify PID ownership using PID, `ExecutablePath`, and `CommandLine`;
   - run `taskkill /T /PID <backendPid>`;
   - report `graceful shutdown timed out`.

The launcher must not claim Runtime was cleaned up normally if forced termination was required.

## 7. Runtime Manager Design

## 7.1 Locking model

`DesktopRuntimeProcessManager.ensure_started()` currently holds `self._lock` and can reach stop logic during failure paths. To avoid lock re-entry deadlocks:

- public `stop()` acquires `self._lock` and delegates to `_stop_locked()`;
- `_stop_locked()` contains the actual stop logic;
- `ensure_started()` may call `_stop_locked()` while already holding the lock;
- `ensure_started()` must not call public `stop()`.

Both `stop()` and `_stop_locked()` must be idempotent.

## 7.2 Ownership model

The manager only stops the Runtime process that it explicitly owns:

- the process object stored on `self.process`;
- the Runtime executable stored on `self._selected_runtime_executable`;
- the Runtime info/client created by this manager instance.

It must not scan the system for arbitrary same-name processes during normal stop.

## 7.3 Owned snapshot and stopping state

Runtime stop must operate on an owned snapshot captured while the lock is held.

Inside `_stop_locked()`:

1. capture a snapshot of:
   - `process`
   - `pid`
   - `runtime_info`
   - `stderr_task`
   - `selected_runtime_executable`
2. mark manager state as `stopping` so `ensure_started()` will not reuse the process during cleanup;
3. perform ownership validation and cleanup using the snapshot;
4. clear manager-owned fields only in a `finally` block after cleanup decisions complete.

Manager fields must **not** be cleared before the snapshot is complete.

## 7.4 Stop sequence

When stopping an owned Runtime:

1. capture current manager-owned references:
   - process
   - client
   - runtime_info
   - stderr task
   - selected runtime executable
2. validate that the process still belongs to the selected official Runtime path;
3. precompute the full recursive child process set **before** terminating the parent;
4. terminate child processes;
5. terminate parent process;
6. bounded wait;
7. kill remaining child processes;
8. kill remaining parent process;
9. bounded wait again;
10. cancel/await stderr task cleanup;
11. clear all internal manager state.

If the Runtime was never started, `stop()` returns safely.

## 7.5 asyncio subprocess to psutil conversion

`self.process` is usually an `asyncio.subprocess.Process`, not a `psutil.Process`.

Runtime process-tree cleanup therefore must explicitly convert:

1. read `self.process.pid` from the owned snapshot;
2. construct `psutil.Process(pid)`;
3. read `exe()` for path validation;
4. enumerate `children(recursive=True)`.

The implementation must handle:

- `psutil.NoSuchProcess`;
- `psutil.AccessDenied`;
- parent process already exited;
- children exiting concurrently during collection or termination.

If the parent process no longer exists:

- do not scan globally by process name;
- log a warning;
- rely on existing next-start stale cleanup as fallback.

## 7.6 Runtime process-tree validation

Before any termination action, the manager must validate:

- PID matches the process it owns;
- executable path resolves successfully;
- executable path equals the manager-selected Runtime executable;
- executable path is inside the official Runtime directory structure:
  `apps/desktop-rpa-runtime/dist-phase2-official/<timestamp>/win-unpacked/LangBot Desktop RPA Runtime.exe`

If validation fails:

- do not terminate the process tree;
- log a warning;
- still clear manager-owned in-memory references so shutdown can continue.

## 7.7 Fallback `close()`

If synchronous `close()` remains:

- it is exceptional fallback only;
- it may only act on the manager-owned process;
- it must re-use the same PID/path ownership validation rules;
- it must not scan for or terminate arbitrary same-name processes;
- it must not replace normal async `stop()`.

## 8. Runtime Prewarm Design

Runtime prewarm must not block backend startup for up to 30 seconds in `BuildAppStage`.

## 8.1 Prewarm launch point

Prewarm will run in `Application.initialize()` or an equivalent post-build startup hook via the task manager:

- task name: `desktop-runtime-prewarm`
- task scope: `APPLICATION`

## 8.2 Prewarm behavior

If `desktop_automation.enabled = false`:

- do not prewarm Runtime;
- log `Runtime disabled`.

If `desktop_automation.enabled = true`:

- call the existing `ensure_runtime_client()`;
- do not add a new spawn path;
- do not generate tokens outside the existing manager;
- catch exceptions;
- log degraded state and error code clearly;
- do not block HTTP startup;
- keep real sending disabled.

Successful prewarm logging is limited to:

- Runtime ready;
- PID;
- Runtime version;
- protocol version;
- selected Runtime version directory.

No token is logged.

## 9. Launcher Design

## 9.1 Files

New files:

- `scripts/start-local.ps1`
- `scripts/start-local.cmd`

State/log/control files:

- `.tmp/local-stack/state.json`
- `.tmp/local-stack/control/shutdown.request.json`
- `.tmp/local-stack/logs/backend.stdout.log`
- `.tmp/local-stack/logs/backend.stderr.log`
- `.tmp/local-stack/logs/web.stdout.log`
- `.tmp/local-stack/logs/web.stderr.log`

## 9.1.1 Launcher mutual exclusion

`Start`, `Stop`, and `Restart` must use repository-local mutual exclusion.

Preferred options:

- `.tmp/local-stack/launcher.lock`
- or a repoRoot-derived Windows named mutex

Requirements:

- exclusive acquisition before any mutating launcher operation;
- bounded wait timeout;
- explicit error if another launcher action is already in progress;
- release in `finally`.

`Status` is read-only and must not mutate state.
`DryRun` must not write persistent files.

## 9.2 Launcher parameters

```powershell
param(
  [ValidateSet('Start', 'Stop', 'Restart', 'Status')]
  [string]$Action = 'Start',

  [ValidateSet('Bundled', 'Dev')]
  [string]$WebMode = 'Bundled',

  [switch]$NoBrowser,

  [switch]$DryRun
)
```

## 9.3 Required backend command

The backend command remains:

```powershell
C:\Users\33031\Desktop\bot\.venv\Scripts\python.exe C:\Users\33031\Desktop\bot\main.py
```

Working directory:

```text
C:\Users\33031\Desktop\bot
```

## 9.4 Required backend environment

The launcher forcibly sets:

- `LANGBOT_RPA_FORCE_DISABLE_SEND=1`
- `LANGBOT_RPA_ALLOW_AUTO_SEND=0`
- `LANGBOT_BROADCAST_SEND_ENABLED=0`
- `PYTHONPATH=C:\Users\33031\Desktop\bot\src`
- `LANGBOT_LOCAL_STACK_SESSION_ID=<random sessionId>`
- `LANGBOT_LOCAL_SHUTDOWN_REQUEST_PATH=<absolute control file path>`

The launcher must **not** set:

- the Runtime authentication token

## 9.5 Dynamic config and URL resolution

The launcher must not hardcode backend ports.

It reads `api.host` and `api.port` through repository Python/config logic using the local `.venv` Python. The launcher never writes configuration back to disk.

Browser URL rules:

- if host is `0.0.0.0`, `::`, or empty, use `127.0.0.1`;
- otherwise use the configured host;
- use configured `api.port`.

Backend health success requires:

- `GET /healthz`
- HTTP 200
- JSON `{"code": 0, "msg": "ok"}`

### Unknown port ownership protection

Even if `state.json` does not exist, the launcher must probe the dynamically resolved backend URL before startup.

If a healthy service already answers on the configured backend port, but the launcher cannot prove ownership through current-state PID plus command-line validation for this repo, it must:

- refuse to start;
- not adopt the service;
- not stop the service;
- report that the configured port is already occupied by a service of unknown ownership.

Dev port `3000` follows the same rule.

## 9.6 Provisional state file

After spawning the backend, the launcher writes a provisional state immediately:

```json
{
  "status": "starting",
  "repoRoot": "C:\\Users\\33031\\Desktop\\bot",
  "startedAt": "2026-07-06T12:34:56.789Z",
  "sessionId": "7dcb5a7b4c0f4f9498f7d69e2f77b2b5",
  "webMode": "Bundled",
  "backend": {
    "pid": 1234,
    "command": "C:\\Users\\33031\\Desktop\\bot\\.venv\\Scripts\\python.exe C:\\Users\\33031\\Desktop\\bot\\main.py",
    "url": "http://127.0.0.1:5300"
  },
  "web": {
    "pid": null,
    "command": null,
    "url": null
  }
}
```

When `/healthz` succeeds, update:

- `"status": "running"`

If startup fails or is rolled back:

- delete `state.json`

`state.json` must not store any token, credential, attachment path, or user data.

`state.json` updates must use a temp file plus atomic replace, not in-place partial writes.

## 9.7 Bundled mode

`Start` in Bundled mode:

1. validate required files including `web/dist/index.html`;
2. read dynamic backend host/port;
3. inspect current `state.json`;
4. if backend is already healthy and `webMode=Bundled`:
   - print already running;
   - open backend URL unless `-NoBrowser`;
   - do not restart;
5. if state is stale:
   - only clean up validated backend/web processes owned by this repo;
   - do not touch Runtime;
6. set required environment including session/control path;
7. launch backend;
8. write provisional `state.json` with `status=starting`;
9. wait for `/healthz` up to 30 seconds;
10. update state to `status=running`;
11. open backend URL unless `-NoBrowser`.

Bundled mode must not launch Node/Vite.

## 9.8 Dev mode

`Start -WebMode Dev`:

1. start backend as above and wait for `/healthz`;
2. set:
   - `VITE_API_BASE_URL=http://<resolved-backend-host>:<resolved-backend-port>`;
3. launch the real command:
   - `pnpm --dir web dev`;
4. wait for `http://127.0.0.1:3000`;
5. if Vite startup fails, roll back this start attempt;
6. save Vite root PID in `state.json`;
7. open `http://127.0.0.1:3000` unless `-NoBrowser`.

Vite strict port behavior must be respected. If port `3000` is occupied and Dev startup fails, the launcher must treat the run as failed rather than silently switching ports.

### Windows PowerShell 5.1 compatibility

The launcher must remain compatible with Windows PowerShell 5.1.

It must not depend on PowerShell 7-only features such as `Start-Process -Environment`.

Recommended process launch mechanism:

- `System.Diagnostics.ProcessStartInfo`
- explicit `EnvironmentVariables`
- explicit `WorkingDirectory`
- redirected stdout/stderr
- direct access to the root process PID

For Dev mode, launch:

```text
cmd.exe /d /s /c "pnpm --dir web dev"
```

and store the `cmd.exe` root PID in state. Stop logic must validate and terminate that owned root process tree rather than guessing child processes by name.

## 9.9 Stop

Stop order:

1. stop Vite root process tree if present and ownership validation succeeds;
2. write shutdown control file for the backend session;
3. wait for graceful backend exit;
4. if backend does not exit in time:
   - validate PID ownership;
   - `taskkill /T /PID <backendPid>`;
   - print `graceful shutdown timed out`;
5. delete `state.json`;
6. keep logs and user data.

The launcher must not directly terminate Runtime.

## 9.10 Restart

Restart order:

1. stop Vite;
2. request graceful backend shutdown via control file;
3. wait for backend exit;
4. force kill only if graceful shutdown times out and ownership validation passes;
5. start again in the requested mode.

## 9.11 Status

Status output:

```text
Component  PID   ProcessAlive  Health/State       URL
Backend    ...   yes/no        ok/down            ...
Web        ...   yes/no        ok/down/not-used   ...
Runtime    -     managed       managed-by-backend managed-by-backend
```

Rules:

- Backend status is based on process ownership checks plus `/healthz`.
- Web status is based on mode plus Vite process/http availability.
- Runtime is always shown as `managed-by-backend` unless there is an already-existing safe, legal, authenticated capability that can be reused without widening scope.
- The launcher must not read Runtime token or Runtime port.
- The launcher must not fabricate `ready`.

## 9.12 DryRun

DryRun prints only:

- repo root;
- backend command;
- mode;
- backend URL;
- Vite URL;
- PIDs that would be checked;
- health checks that would run;
- safe-send environment state (`DISABLED`);
- Runtime ownership note (`managed by backend`).

DryRun must not:

- start processes;
- stop processes;
- write files;
- open browser;
- modify config;
- create tokens.

## 9.13 PID ownership validation

### Backend

Before termination, all of the following must hold:

- PID comes from current state;
- executable path is the repo `.venv\Scripts\python.exe`, or command line clearly uses it;
- command line contains this repo `main.py`;
- command line or executable path corresponds to the current repo root.

If validation fails:

- do not terminate;
- print warning;
- drop stale state entry.

### Web

Before termination, all of the following must hold:

- PID comes from current state;
- command line contains this repo `web` directory;
- command line matches `pnpm --dir web dev` / Vite dev semantics.

If validation fails:

- do not terminate;
- print warning;
- drop stale state entry.

The launcher must never bulk-kill by process name alone.

## 9.14 CMD entrypoint

`scripts/start-local.cmd` only locates the repo and forwards to PowerShell:

```bat
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-local.ps1" -Action Start -WebMode Bundled
```

Requirements:

- support spaces in path;
- preserve PowerShell exit code;
- show failure and pause on error;
- do not duplicate PowerShell business logic.

## 9.15 Log rotation and ignore rules

Launcher log files must either be truncated on each new start or rotated with a retention cap of the most recent 5 runs.

They must not grow without bound.

Repository hygiene rule:

- inspect `.gitignore`;
- if `.tmp/` is not ignored, add the minimal entry:
  - `.tmp/`

This change must not delete any existing `.tmp` data.

## 10. Files To Modify

Primary backend files:

- `src/langbot/pkg/core/app.py`
- `src/langbot/pkg/core/boot.py`
- `src/langbot/pkg/core/stages/build_app.py`
- `src/langbot/pkg/api/http/controller/main.py`
- `src/langbot/pkg/desktop_automation/service.py`
- `src/langbot/pkg/desktop_automation/runtime_process.py`

New launcher files:

- `scripts/start-local.ps1`
- `scripts/start-local.cmd`

Likely tests:

- `tests/unit_tests/core/test_boot.py`
- `tests/unit_tests/core/test_app_shutdown.py` (new)
- `tests/unit_tests/desktop_automation/test_runtime_process.py`
- `tests/unit_tests/desktop_automation/test_service.py`
- `scripts/tests/start-local.Tests.ps1` if Pester is available

## 11. Test Matrix

### 11.1 Backend lifecycle

1. signal handler requests shutdown without direct `await`;
2. normal exit path does not use `os._exit(0)`;
3. `Application.run()` main coroutine owns shutdown coordination;
4. shutdown coordinator is not an `APPLICATION` scope task;
5. permanent `never_ending()` task is removed/replaced;
6. `Application.shutdown()` is idempotent;
7. HTTP shutdown event is triggered on shutdown;
8. Broadcast worker stop uses internal timeout and does not block forever;
9. worker stop is concurrency-safe when called twice;
10. shutdown continues even if worker stop fails or times out;
11. `DesktopAutomationService.shutdown()` is called;
12. `DesktopRuntimeProcessManager.stop()` is called;
13. `APPLICATION` tasks are cancelled and collected;
14. `dispose()` remains fallback-only.

### 11.2 Runtime manager

1. `stop()` is idempotent;
2. `stop()` is safe when Runtime was never started;
3. stop captures owned snapshot before field clearing;
4. stop marks `stopping` and blocks reuse during cleanup;
5. `stop()` clears process/client/runtime_info/stderr_task/selected runtime in `finally`;
6. `ensure_started()` failure paths call `_stop_locked()` rather than public `stop()`;
7. `_stop_locked()` handles protocol mismatch cleanup safely;
8. asyncio subprocess PID converts to `psutil.Process(pid)` correctly;
9. parent already missing logs warning and does not trigger global name scan;
10. stop validates PID and executable path before termination;
11. stop precomputes recursive children before termination;
12. stop terminates children then parent;
13. stop kills remaining children then parent after timeout;
14. stop only touches manager-owned Runtime;
15. fallback `close()` does not kill non-owned Runtime;
16. latest Runtime selection behavior remains unchanged;
17. token generation remains backend-only;
18. safety env vars still reach Runtime spawn.

### 11.3 Runtime prewarm

1. `enabled=false` does not prewarm and logs disabled;
2. `enabled=true` schedules `desktop-runtime-prewarm`;
3. prewarm uses existing `ensure_runtime_client()`;
4. prewarm failure is logged as degraded;
5. prewarm failure does not block HTTP/backend startup;
6. prewarm does not enable real sending.

### 11.4 Launcher

1. default mode is `Start + Bundled`;
2. backend command uses repo `.venv` Python and `main.py`;
3. launcher mutex blocks concurrent Start/Stop/Restart;
4. `Status` is read-only;
5. `DryRun` writes no persistent files;
6. host/port are read dynamically, not hardcoded;
7. unknown occupied backend port without provable ownership aborts startup;
8. unknown occupied Dev port without provable ownership aborts startup;
9. safe-send env vars are forced;
10. launcher does not set a Runtime authentication token;
11. provisional `state.json` is written with `status=starting`;
12. `state.json` writes use atomic replace;
13. successful health check updates state to `status=running`;
14. failed startup removes provisional state;
15. Bundled mode does not launch Vite;
16. Dev mode launches `cmd.exe /d /s /c "pnpm --dir web dev"`;
17. Dev mode sets correct `VITE_API_BASE_URL`;
18. launcher uses PowerShell 5.1-compatible process start APIs;
19. `Status` shows Runtime as `managed-by-backend`;
20. stop writes shutdown control file with matching sessionId;
21. backend ignores mismatched sessionId control files;
22. accepted shutdown request is consumed/deleted once;
23. malformed shutdown request is quarantined/deleted without log storm;
24. launcher waits for graceful shutdown before force kill;
25. forced backend kill requires ownership validation;
26. forced kill prints `graceful shutdown timed out`;
27. launcher never kills Runtime directly;
28. launcher never kills unrelated Python/Node processes;
29. missing `web/dist` in Bundled mode yields explicit error;
30. `/healthz` timeout rolls back startup;
31. log retention is bounded to the most recent 5 runs;
32. CMD wrapper forwards parameters and exit code correctly.

## 12. Verification Plan

Required verification commands after implementation:

```powershell
C:\Users\33031\Desktop\bot\.venv\Scripts\python.exe -m pytest tests\unit_tests\desktop_automation -q
C:\Users\33031\Desktop\bot\.venv\Scripts\python.exe -m pytest tests\unit_tests\core -q
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\start-local.ps1 -Action Restart -WebMode Bundled -DryRun
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\start-local.ps1 -Action Restart -WebMode Dev -DryRun
```

If safe on the local machine, then run:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\start-local.ps1 -Action Restart -WebMode Bundled -NoBrowser
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\start-local.ps1 -Action Status
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\start-local.ps1 -Action Stop
git diff --check
git status --short
git diff --stat
```

## 13. Self-Review

- No public shutdown endpoint is introduced.
- Runtime ownership remains backend-only.
- Graceful shutdown path uses a control file rather than forced process kill.
- Normal shutdown path is async and idempotent.
- Runtime stop lock re-entry deadlock is explicitly avoided.
- Runtime prewarm is backgrounded and non-blocking.
- Launcher state remains non-sensitive.
- Runtime `Status` remains `managed-by-backend`.
