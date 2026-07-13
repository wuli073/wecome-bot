# Post-READY Backend Exit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep the packaged HTTP backend alive after `READY` when an optional runtime or service fails, while making every backend and launcher exit attributable.

**Architecture:** Treat the HTTP listener as the only post-`CORE_READY` critical process component. Optional initialization, plugin-runtime loss, Box unavailability, and Desktop RPA failures update the lifecycle to `DEGRADED` and remain observable without requesting application shutdown. Add structured lifecycle diagnostics at the Python process boundary and the launcher process boundary; optional HTTP routes return a deterministic service-state response until their dependency is ready.

**Tech Stack:** Python 3.11 asyncio/Quart/Hypercorn/pytest; C# .NET 8/xUnit; PowerShell release verifier.

---

### Task 1: Capture backend exit provenance

**Files:**
- Modify: `packaging/server/entrypoint.py`
- Modify: `src/langbot/pkg/core/app.py`
- Test: `tests/unit_tests/core/test_packaged_boot.py`
- Test: `tests/unit_tests/core/test_app_shutdown.py`

- [ ] Record the current lifecycle state, final boot stage, shutdown reason, loop exceptions, task exceptions, Hypercorn completion, and `packaged_main` result as structured `BACKEND_*` records.
- [ ] Verify an optional task exception is logged and transitions the application to `DEGRADED` without resolving the backend main task.
- [ ] Verify a controlled shutdown records exit code zero and its control-file reason.

### Task 2: Isolate optional failures from process lifetime

**Files:**
- Modify: `src/langbot/pkg/core/app.py`
- Modify: `src/langbot/pkg/core/stages/build_app.py`
- Test: `tests/unit_tests/core/test_runtime_lifecycle.py`

- [ ] Add an optional-failure reporter that preserves the HTTP task and sets `RuntimeState.DEGRADED`.
- [ ] Run plugin reconnect, Desktop RPA prewarm, and other post-core tasks under that reporter rather than allowing an unobserved task failure.
- [ ] Verify Box, plugin runtime, Desktop RPA, and optional task failures leave the application run task alive.

### Task 3: Make optional APIs lifecycle-safe

**Files:**
- Modify: `src/langbot/pkg/api/http/controller/group.py`
- Modify: `src/langbot/pkg/api/http/controller/groups/box.py`
- Modify: `src/langbot/pkg/api/http/controller/groups/extensions.py`
- Modify: `src/langbot/pkg/api/http/controller/groups/resources/tools.py`
- Test: `tests/unit_tests/api/http/test_optional_service_lifecycle.py`

- [ ] Return a structured `SERVICE_INITIALIZING` or `SERVICE_UNAVAILABLE` response before dereferencing an unavailable optional dependency.
- [ ] Assert the response is not a traceback/`AttributeError`, and that the normal endpoint response resumes when the dependency is attached.

### Task 4: Attribute launcher stops and unexpected process exits

**Files:**
- Modify: `packaging/launcher/ChatbotLauncher/LauncherProcessManager.cs`
- Modify: `packaging/launcher/ChatbotLauncher/TrayController.cs`
- Test: `packaging/launcher/ChatbotLauncher.Tests/LifecycleTests.cs`

- [ ] Subscribe to `Process.Exited` at backend creation and log PID, timestamp, exit code, launcher-initiated state, stop reason, last probe, lifecycle state, and last `BOOT_STAGE`.
- [ ] Log every stop request before the shutdown control file is written and log any force kill decision.
- [ ] Verify startup success, browser failure, and tray/status probe failure do not call `StopAsync`; verify only explicit user exit, startup failure, and owned cleanup do.

### Task 5: Release validation

**Files:**
- Modify: `scripts/verify-trial-release.ps1`
- Test: `tests/unit_tests/release/test_trial_release_verification.py`

- [ ] Poll health and runtime after `READY`, inject each optional failure scenario, and verify `DEGRADED` with the backend PID and listener retained.
- [ ] Build `0.1.5-rc5`, run backend, launcher, release, portable, installer, post-start survival, shutdown, port-release, residual-process, and uninstall checks.
