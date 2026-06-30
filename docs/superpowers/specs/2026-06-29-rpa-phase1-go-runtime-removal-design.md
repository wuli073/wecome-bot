# RPA Phase 1 Design: Remove Legacy Go Desktop Runtime

## Status

- Date: 2026-06-29
- Scope: Phase 1 only
- Commit: intentionally not created in this task

## Goal

Remove the repository's legacy Go-based desktop RPA runtime and all repository-side coupling to it, while preserving existing product entry points and compatibility-layer business APIs. Before the new Electron/TypeScript runtime is integrated, all desktop automation behavior must fail closed with a single explicit error:

`RPA_RUNTIME_NOT_AVAILABLE`

Phase 1 must stop after cleanup and verification. It must not begin the Electron runtime migration.

## Non-Goals

- Do not implement the new Electron/TypeScript runtime in this phase.
- Do not perform any real desktop automation.
- Do not silently succeed, partially degrade, or fall back to clipboard/mouse/send behavior.
- Do not delete user-local files outside the repository workspace.
- Do not commit or push.

## Current Context

The current workspace still contains the legacy Go runtime at `apps/desktop-runtime/`, Python hosting logic under `src/langbot/pkg/desktop_automation/`, related tests, and frontend dry-run integration. The workspace also has unrelated in-progress changes, so this phase must avoid destructive git operations and must only touch files required for Phase 1.

## User-Approved Execution Boundary

Phase 1 will:

1. Remove the legacy Go runtime source tree and binaries from the repository.
2. Remove Go-runtime-specific Python orchestration, capability detection, protocol coupling, and error mapping.
3. Preserve the business-layer API surface for calibration, current-session confirmation, paste-draft, and desktop automation run entry points, but make them fail closed until a new runtime exists.
4. Remove old frontend dry-run and Go-runtime-specific UX/state handling while keeping the business entry point and user feedback path.
5. Verify repository cleanup before any Phase 2 work is considered.

Additional constraints approved by the user:

1. Preserve shared business models that can be reused by Phase 2. Only Go-runtime-specific implementation should be deleted.
2. Define one fail-closed protocol for all runtime-dependent operations, including HTTP status, API envelope behavior, and frontend user-facing copy.
3. Preserve the existing calibration entry location, but make it unavailable in Phase 1.
4. Separate code/test/build residue grep results from documentation-only historical references.
5. Protect the current working tree and explicitly classify existing uncommitted files as RPA-related or non-RPA-related before implementation.

## Design Overview

### 1. Runtime Removal

Delete `apps/desktop-runtime/` completely, including source, tests, build artifacts, module files, and checked-in executables.

This phase treats the Go runtime as fully retired. The repository must not keep a parallel Go runtime alive after cleanup.

### 2. Backend Fail-Closed Shape

The Python desktop automation layer remains as a compatibility shell, but all Go-runtime-specific behaviors are removed:

- no `robotgo`/stub/backend capability inspection
- no Go runtime executable discovery or launch assumptions
- no `runtime-info.json` coupling
- no legacy runtime protocol compatibility handling
- no Go-runtime-specific readiness checks

Before deleting anything in the Python layer, Phase 1 must distinguish between:

- Go-specific runtime implementation
- runtime-agnostic business shell / reusable data model

The following categories are preserved if they are not intrinsically tied to the Go runtime and can be reused by Phase 2:

- desktop automation run persistence model
- task/run status model
- API DTO / envelope shapes
- database tables and persistence entities
- repository/service shell code that expresses business semantics rather than Go-runtime transport details

Business-facing methods and API routes remain present where required by the current frontend and backend contracts, but runtime-dependent operations return `RPA_RUNTIME_NOT_AVAILABLE`.

This explicit failure must apply before any desktop action is attempted.

### 3. API Behavior

The existing business entry points remain available in shape, but not in effect:

- calibration
- current-session confirmation
- paste-draft
- desktop automation run flows

Until Phase 2 lands, these routes should produce a clear fail-closed result rather than:

- success without action
- downgraded local clipboard behavior
- partial state transitions
- fake send/paste completion

Fail-closed response protocol is uniform:

- logical error code: `RPA_RUNTIME_NOT_AVAILABLE`
- HTTP status: `503`
- existing API envelope: keep the current response envelope format used by these routes, and place the failure in that existing structure instead of inventing per-route variants
- frontend message: a consistent unavailable message meaning “RPA Runtime 尚未接入” / “RPA runtime is not integrated yet”

Additional prohibitions:

- do not create a successful desktop automation run
- do not write `pasted`, `sent`, or `completed` outcomes
- do not advance persisted run/message/draft state as if runtime work occurred

If a route currently creates a run record before dispatch, Phase 1 must block earlier and return the unavailable response without creating a success path or fake in-progress artifact.

### 4. Frontend Behavior

Frontend keeps the user-facing access point, but old Go-runtime-specific controls are removed.

Keep:

- the small-plane action entry
- draft validation / feedback
- paste-draft business entry location
- calibration entry location
- success/failure notification framework

Remove:

- Dry Run button
- Dry Run result panel
- `send-draft-dry-run` frontend call path
- Go runtime capability display
- stub/backend-specific UI branching
- old confirmation-token logic coupled to Go task flow

If the frontend reaches a runtime-dependent action before Phase 2 exists, it should surface an unavailable state instead of showing half-working controls.

Calibration is preserved as an entry point only. In Phase 1, clicking calibration must show the same unavailable message and must not attempt to call or start the old Go runtime.

### 5. Legacy Protocol and State Cleanup

Repository code must stop reading or writing old Go profile/state conventions, including:

- old region profile compatibility fields such as `conversationTitleRegion`, `messageInputRegion`, `windowClassHash`
- client-relative normalized-region compatibility paths
- camelCase/snake_case compatibility code that exists only for the old Go profile shape
- repository-side use of `data/desktop-automation/runtime-info.json`
- repository-side use of `%LOCALAPPDATA%\\WecomeBot\\connectors\\wxwork-local\\state.json`

This phase does not delete user-local files outside the repo. It only ensures the new code no longer depends on them. If needed, a migration note can explain that these files are now ignored.

## Target File Groups

### Delete

- `C:\Users\33031\Desktop\bot\apps\desktop-runtime\`

### Refactor / Simplify

- `C:\Users\33031\Desktop\bot\src\langbot\pkg\desktop_automation\client.py`
- `C:\Users\33031\Desktop\bot\src\langbot\pkg\desktop_automation\service.py`
- `C:\Users\33031\Desktop\bot\src\langbot\pkg\api\http\controller\groups\bot_database_mode.py`

### Likely Additional Cleanup Targets

- desktop automation repository/process helpers
- desktop automation tests
- frontend bot session composer / confirmation state files
- frontend HTTP client calls
- e2e tests that still reference dry-run behavior

## Error Handling Contract

Phase 1 introduces a single clear unavailable result for runtime-dependent operations:

- error code: `RPA_RUNTIME_NOT_AVAILABLE`

This code must be mapped consistently across the backend and frontend so the UI can explain that RPA is unavailable before the new runtime is integrated.

The contract is:

- backend HTTP status: `503`
- backend envelope: use the existing route-family response envelope and surface `RPA_RUNTIME_NOT_AVAILABLE` there
- frontend notification copy: one consistent unavailable message, not route-specific variants
- persistence effect: no fake success, no fake send, no fake paste, no completed run state

## Verification Plan

Phase 1 is accepted only if all of the following are true:

1. `apps/desktop-runtime/` no longer exists.
2. The repository no longer contains Go runtime source or checked-in binaries.
3. The repository no longer contains robotgo/stub build logic.
4. Python no longer attempts to start `desktop-runtime.exe`.
5. Frontend no longer exposes Dry Run UX.
6. Runtime-dependent desktop actions clearly report RPA unavailable.
7. Non-RPA bot/database workflows still run.
8. No real desktop action is performed.
9. No commit and no push occur.

Repository search verification will specifically check for:

- `desktop-runtime`
- `robotgo`
- `DESKTOP_RUNTIME_ENABLE_SEND`
- `send-draft-dry-run`
- `RUNTIME_BACKEND_UNAVAILABLE`
- `runtime-info.json`

Search verification must be reported in two buckets:

1. code/test/build residue hits — must be zero after Phase 1
2. documentation/migration-note historical mentions — allowed when explaining prior architecture or cleanup history

This avoids treating planned documentation references as implementation residue.

## Execution Order

1. Inventory and remove Go runtime files and old build/test residue.
2. Refactor backend desktop automation compatibility layer to fail closed.
3. Remove frontend dry-run and old Go-runtime-specific state/UX paths.
4. Update or remove tests to reflect fail-closed behavior.
5. Run targeted grep, diff, lint, and test verification.
6. Stop if Phase 1 verification fails.

## Risks and Constraints

- The workspace contains unrelated in-progress modifications; avoid broad cleanup commands and destructive git operations.
- The implementation plan must begin by listing current uncommitted files and classifying them into:
  - RPA-related
  - non-RPA-related
- Non-RPA uncommitted files must not be modified, deleted, or reformatted.
- Forbidden commands include:
  - `git reset`
  - `git restore`
  - `git checkout --`
  - `git clean`
- Some current unit/e2e coverage may still encode old dry-run behavior and will need rewrite or removal.
- Existing business entry points must remain stable enough that the rest of the application still loads and operates.
- Phase 2 must not begin unless Phase 1 cleanup is verified.

## Phase 1 Completion Output

When Phase 1 work finishes, the result report should include:

1. deleted files and residue grep results
2. newly modified files for Phase 1
3. verification command results
4. failed checks, if any
5. explicit confirmation that there was no real sending, no commit, and no push
