# Broadcast Phase 4–7 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver Broadcast Phase 4–7 execution, queueing, capability, audit, and default-off send infrastructure on top of Phase 3 while preserving the current working-tree baseline and never causing real send outside dedicated test environments.

**Architecture:** Extend the existing Broadcast domain with new execution persistence entities, a runtime gateway, executor abstractions, a serial worker, audit/redaction helpers, and frontend execution/log/send-confirmation flows. Keep routers thin, state changes transactional, execution durable in the database, and paste/send fully separated end-to-end.

**Tech Stack:** Python 3.11+, Quart, SQLAlchemy, Alembic, pytest, React, TypeScript, Playwright, Electron runtime TypeScript tests, existing Broadcast frontend/data-source stack, existing desktop runtime app

---

## Fixed constraints

- Preserve current uncommitted Phase 3 working-tree changes.
- Do not modify, delete, stage, or clean `.tmp/`, `docs/superpowers/plans/**`, or `docs/superpowers/specs/**` except for creating these new Phase 4–7 doc files.
- Do not use `git reset`, `git restore`, `git checkout --`, `git clean`, `git stash`, `git add .`, or `git add -A`.
- Do not commit, push, create a PR, or merge `main`.
- Follow TDD: every production change starts with a failing test.
- Use `0015_broadcast_execution` with `down_revision = '0014_broadcast_phase3'`.
- Phase 4–6 must remain paste-only and must never send.

## Baseline verification already completed

- [x] Review current working-tree diff and confirm Phase 3 acceptance changes are non-conflicting.
- [x] Run `web/tests/e2e/broadcast-workspace.spec.ts`, `broadcast-import-feedback.spec.ts`, `broadcast-scope-selector.spec.ts`.
- [x] Run `pnpm build` in `web/`.
- [x] Treat the current working tree as the implementation baseline.

---

### Task 1: Add failing migration tests for execution persistence

**Files:**
- Modify: `C:/Users/33031/Desktop/bot/tests/integration/persistence/test_migrations.py`
- Modify: `C:/Users/33031/Desktop/bot/tests/integration/persistence/test_migrations_postgres.py`

- [ ] **Step 1: Write failing SQLite migration tests for execution tables, indexes, and FK behavior**
- [ ] **Step 2: Write failing PostgreSQL migration tests for upgrade/downgrade and metadata presence**
- [ ] **Step 3: Run targeted migration tests and verify failure because `0015_broadcast_execution` does not exist yet**

Run:
`uv run pytest tests/integration/persistence/test_migrations.py -q`

Run:
`uv run pytest tests/integration/persistence/test_migrations_postgres.py -q`

Expected: FAIL with missing revision/table assertions.

---

### Task 2: Implement execution ORM and migration

**Files:**
- Modify: `C:/Users/33031/Desktop/bot/src/langbot/pkg/entity/persistence/broadcast.py`
- Add: `C:/Users/33031/Desktop/bot/src/langbot/pkg/persistence/alembic/versions/0015_broadcast_execution.py`

- [ ] **Step 1: Add `BroadcastExecutionBatch`, `BroadcastExecutionTask`, `BroadcastExecutionAttempt`, `BroadcastExecutionEvidence`, and send-confirmation persistence models with exact fields/constraints**
- [ ] **Step 2: Implement guarded Alembic upgrade/downgrade for `0015_broadcast_execution`**
- [ ] **Step 3: Run migration tests and verify green**

Run:
`uv run pytest tests/integration/persistence/test_migrations.py tests/integration/persistence/test_migrations_postgres.py -q`

Expected: PASS for execution migration coverage.

---

### Task 3: Add failing repository/state-machine tests for execution CRUD and transitions

**Files:**
- Modify: `C:/Users/33031/Desktop/bot/tests/unit_tests/broadcast/test_repository.py`
- Modify: `C:/Users/33031/Desktop/bot/tests/unit_tests/broadcast/test_service.py`
- Add: `C:/Users/33031/Desktop/bot/tests/unit_tests/broadcast/test_execution_worker.py`

- [ ] **Step 1: Write failing repository tests for batch/task/attempt/evidence CRUD, summary recompute, and cascade behavior**
- [ ] **Step 2: Write failing service tests for allowed/forbidden transitions, idempotency digest rules, and transactional rollback expectations**
- [ ] **Step 3: Write failing worker tests for serial claiming, pause, cancel, retry, and restart recovery**
- [ ] **Step 4: Run focused unit tests and verify failure**

Run:
`uv run pytest tests/unit_tests/broadcast/test_repository.py tests/unit_tests/broadcast/test_service.py tests/unit_tests/broadcast/test_execution_worker.py -q`

Expected: FAIL because execution repository/service/worker methods do not exist yet.

---

### Task 4: Implement repository execution persistence methods

**Files:**
- Modify: `C:/Users/33031/Desktop/bot/src/langbot/pkg/broadcast/repository.py`

- [ ] **Step 1: Add repository methods for batch/task/attempt/evidence/send-confirmation CRUD and scoped lookup helpers**
- [ ] **Step 2: Add atomic task-claim/update helpers for serial worker consumption**
- [ ] **Step 3: Add summary recomputation helpers that keep batch counts canonical in persistence/service transactions**
- [ ] **Step 4: Run repository-focused unit tests and verify green**

Run:
`uv run pytest tests/unit_tests/broadcast/test_repository.py -q`

Expected: PASS.

---

### Task 5: Add failing runtime gateway and executor tests

**Files:**
- Add: `C:/Users/33031/Desktop/bot/tests/unit_tests/broadcast/test_runtime_gateway.py`
- Add: `C:/Users/33031/Desktop/bot/tests/unit_tests/broadcast/test_executors.py`

- [ ] **Step 1: Write failing runtime gateway tests for health, capability, version mismatch, force-disable-send checks, timeout/query/idempotency behavior, and send endpoint separation**
- [ ] **Step 2: Write failing executor tests for WeCom paste-only behavior, unsupported channels, capability validation, evidence normalization, and send-default-disabled behavior**
- [ ] **Step 3: Run tests and verify failure**

Run:
`uv run pytest tests/unit_tests/broadcast/test_runtime_gateway.py tests/unit_tests/broadcast/test_executors.py -q`

Expected: FAIL because gateway/executor modules do not exist yet.

---

### Task 6: Implement runtime gateway and executor abstractions

**Files:**
- Add: `C:/Users/33031/Desktop/bot/src/langbot/pkg/broadcast/runtime_gateway.py`
- Add: `C:/Users/33031/Desktop/bot/src/langbot/pkg/broadcast/executors/base.py`
- Add: `C:/Users/33031/Desktop/bot/src/langbot/pkg/broadcast/executors/wecom.py`
- Add: `C:/Users/33031/Desktop/bot/src/langbot/pkg/broadcast/executors/registry.py`

- [ ] **Step 1: Implement gateway methods for health/capability/version checks, paste task creation, send task creation, query, and cancel**
- [ ] **Step 2: Implement `ConversationDraftExecutor` and `WeComDraftExecutor` with paste-only capabilities for Phase 4–6**
- [ ] **Step 3: Register unsupported channel executors that return explicit unsupported errors**
- [ ] **Step 4: Run gateway/executor unit tests and verify green**

Run:
`uv run pytest tests/unit_tests/broadcast/test_runtime_gateway.py tests/unit_tests/broadcast/test_executors.py -q`

Expected: PASS.

---

### Task 7: Add failing Phase 4 API and service tests

**Files:**
- Modify: `C:/Users/33031/Desktop/bot/tests/unit_tests/broadcast/test_service.py`
- Modify: `C:/Users/33031/Desktop/bot/tests/unit_tests/broadcast/test_routes.py`
- Modify: `C:/Users/33031/Desktop/bot/tests/integration/api/test_broadcast.py`

- [ ] **Step 1: Write failing tests for single-draft execution batch creation, start, cancel, retry, task detail, attempt/evidence retrieval, and scope enforcement**
- [ ] **Step 2: Add failing tests for stale/pending_review/invalid rejection, conversation-not-found failure, input-not-found failure, duplicate idempotency, and timeout-no-blind-retry behavior**
- [ ] **Step 3: Run focused backend tests and verify failure**

Run:
`uv run pytest tests/unit_tests/broadcast/test_service.py tests/unit_tests/broadcast/test_routes.py tests/integration/api/test_broadcast.py -q`

Expected: FAIL with missing execution API/service behavior.

---

### Task 8: Implement Phase 4 service and router flows

**Files:**
- Modify: `C:/Users/33031/Desktop/bot/src/langbot/pkg/broadcast/errors.py`
- Modify: `C:/Users/33031/Desktop/bot/src/langbot/pkg/broadcast/schemas.py`
- Modify: `C:/Users/33031/Desktop/bot/src/langbot/pkg/broadcast/service.py`
- Modify: `C:/Users/33031/Desktop/bot/src/langbot/pkg/api/http/controller/groups/broadcast.py`
- Add: `C:/Users/33031/Desktop/bot/src/langbot/pkg/broadcast/audit.py`

- [ ] **Step 1: Add execution error codes and localized safety messages**
- [ ] **Step 2: Implement single-batch creation and task creation with preflight validation, digest/key computation, and audit**
- [ ] **Step 3: Implement start/cancel/retry/task-detail/attempt/evidence service methods and router endpoints**
- [ ] **Step 4: Ensure Phase 4 only allows one draft per batch and only `paste_only` mode**
- [ ] **Step 5: Run focused backend tests and verify green**

Run:
`uv run pytest tests/unit_tests/broadcast/test_service.py tests/unit_tests/broadcast/test_routes.py tests/integration/api/test_broadcast.py -q`

Expected: PASS for Phase 4 backend coverage.

---

### Task 9: Add failing frontend execution tests for Phase 4

**Files:**
- Modify: `C:/Users/33031/Desktop/bot/web/tests/e2e/fixtures/langbot-api.ts`
- Add: `C:/Users/33031/Desktop/bot/web/tests/e2e/broadcast-execution-phase4.spec.ts`

- [ ] **Step 1: Add failing fixture support for execution batch/task/attempt/evidence endpoints**
- [ ] **Step 2: Add failing E2E for single ready draft execution, disabled buttons for stale/invalid/pending_review, retry flow, and real log display**
- [ ] **Step 3: Run Playwright test and verify failure**

Run:
`pnpm exec playwright test tests/e2e/broadcast-execution-phase4.spec.ts --project chromium`

Expected: FAIL because frontend execution UI does not exist yet.

---

### Task 10: Implement frontend Phase 4 execution UI

**Files:**
- Modify: `C:/Users/33031/Desktop/bot/web/src/app/home/broadcast/types.ts`
- Modify: `C:/Users/33031/Desktop/bot/web/src/app/infra/http/BackendClient.ts`
- Modify: `C:/Users/33031/Desktop/bot/web/src/app/home/broadcast/datasources/BroadcastDataSource.ts`
- Modify: `C:/Users/33031/Desktop/bot/web/src/app/home/broadcast/components/drafts/DraftQueue.tsx`
- Modify: `C:/Users/33031/Desktop/bot/web/src/app/home/broadcast/components/drafts/DraftDetail.tsx`
- Modify: `C:/Users/33031/Desktop/bot/web/src/app/home/broadcast/components/logs/ExecutionLogPanel.tsx`
- Modify: `C:/Users/33031/Desktop/bot/web/src/app/home/broadcast/components/BroadcastWorkspace.tsx`
- Add: execution-specific components as needed under `web/src/app/home/broadcast/components/`

- [ ] **Step 1: Extend frontend types and client/data-source methods for execution batches/tasks/attempts/evidence/capability/health**
- [ ] **Step 2: Add single execution confirmation, target conversation/body preview, start/retry buttons, and disabled-state logic**
- [ ] **Step 3: Replace mock execution logs with real batch/task/attempt/evidence rendering**
- [ ] **Step 4: Run TypeScript + Phase 4 Playwright tests and verify green**

Run:
`pnpm exec tsc --noEmit`

Run:
`pnpm exec playwright test tests/e2e/broadcast-execution-phase4.spec.ts --project chromium`

Expected: PASS.

---

### Task 11: Add failing runtime tests for Broadcast paste contract hardening

**Files:**
- Modify: `C:/Users/33031/Desktop/bot/apps/desktop-rpa-runtime/tests/phase2-core.test.ts`
- Add: `C:/Users/33031/Desktop/bot/apps/desktop-rpa-runtime/tests/broadcast-paste.test.ts`

- [ ] **Step 1: Add failing tests for Broadcast-specific paste idempotency, timeout query safety, force-disable-send enforcement, and evidence normalization**
- [ ] **Step 2: Add static assertions that paste paths do not trigger send behavior**
- [ ] **Step 3: Run runtime tests and verify failure**

Run:
`npm test -- --test-name-pattern "paste|broadcast"`

Expected: FAIL before runtime changes.

---

### Task 12: Implement runtime paste-path hardening

**Files:**
- Modify: `C:/Users/33031/Desktop/bot/apps/desktop-rpa-runtime/src/main/domain/task-types.ts`
- Modify: `C:/Users/33031/Desktop/bot/apps/desktop-rpa-runtime/src/main/runtime/runtime-host.ts`
- Modify: `C:/Users/33031/Desktop/bot/apps/desktop-rpa-runtime/src/main/input/paste-controller.ts`
- Modify: `C:/Users/33031/Desktop/bot/apps/desktop-rpa-runtime/src/main/api/local-http-server.ts`
- Modify: `C:/Users/33031/Desktop/bot/apps/desktop-rpa-runtime/src/main/api/routes-actions.ts`

- [ ] **Step 1: Enforce Broadcast paste request validation and force-disable-send checks in runtime**
- [ ] **Step 2: Keep idempotent replay returning the original task without duplicate paste**
- [ ] **Step 3: Ensure timeout/ambiguous states can be queried rather than blindly replayed**
- [ ] **Step 4: Run runtime paste tests and verify green**

Run:
`npm test -- --test-name-pattern "paste|broadcast"`

Expected: PASS.

---

### Task 13: Add failing Phase 5 worker/queue tests across backend and frontend

**Files:**
- Modify: `C:/Users/33031/Desktop/bot/tests/unit_tests/broadcast/test_execution_worker.py`
- Modify: `C:/Users/33031/Desktop/bot/tests/integration/api/test_broadcast.py`
- Add: `C:/Users/33031/Desktop/bot/web/tests/e2e/broadcast-execution-phase5.spec.ts`

- [ ] **Step 1: Add failing worker tests for strict ordering, pause, resume, cancel pending, retry attempts, and restart recovery**
- [ ] **Step 2: Add failing integration tests for batch queue endpoints and summary updates**
- [ ] **Step 3: Add failing frontend E2E for multi-select queue management and restart recovery display**
- [ ] **Step 4: Run tests and verify failure**

Run:
`uv run pytest tests/unit_tests/broadcast/test_execution_worker.py tests/integration/api/test_broadcast.py -q`

Run:
`pnpm exec playwright test tests/e2e/broadcast-execution-phase5.spec.ts --project chromium`

Expected: FAIL.

---

### Task 14: Implement Phase 5 worker, pause/resume/cancel/retry, and restart recovery

**Files:**
- Add: `C:/Users/33031/Desktop/bot/src/langbot/pkg/broadcast/worker.py`
- Modify: `C:/Users/33031/Desktop/bot/src/langbot/pkg/broadcast/service.py`
- Modify: `C:/Users/33031/Desktop/bot/src/langbot/pkg/broadcast/repository.py`
- Modify: `C:/Users/33031/Desktop/bot/src/langbot/pkg/api/http/controller/groups/broadcast.py`

- [ ] **Step 1: Implement durable serial worker claim/consume loop with concurrency 1**
- [ ] **Step 2: Implement pause/resume/cancel-remaining/retry semantics and batch summary updates**
- [ ] **Step 3: Implement startup recovery that marks running tasks interrupted without replay**
- [ ] **Step 4: Run backend queue tests and verify green**

Run:
`uv run pytest tests/unit_tests/broadcast/test_execution_worker.py tests/unit_tests/broadcast/test_service.py tests/integration/api/test_broadcast.py -q`

Expected: PASS.

---

### Task 15: Implement frontend Phase 5 queue management

**Files:**
- Modify: `C:/Users/33031/Desktop/bot/web/src/app/home/broadcast/types.ts`
- Modify: `C:/Users/33031/Desktop/bot/web/src/app/home/broadcast/datasources/BroadcastDataSource.ts`
- Modify: `C:/Users/33031/Desktop/bot/web/src/app/home/broadcast/components/drafts/DraftQueue.tsx`
- Modify: `C:/Users/33031/Desktop/bot/web/src/app/home/broadcast/components/logs/ExecutionLogPanel.tsx`
- Modify: `C:/Users/33031/Desktop/bot/web/src/app/home/broadcast/components/BroadcastWorkspace.tsx`

- [ ] **Step 1: Add multi-select batch creation and queue controls**
- [ ] **Step 2: Add real-time summary display, attempt/evidence drill-down, and restart recovery status display**
- [ ] **Step 3: Run TypeScript and Phase 5 Playwright tests and verify green**

Run:
`pnpm exec tsc --noEmit`

Run:
`pnpm exec playwright test tests/e2e/broadcast-execution-phase5.spec.ts --project chromium`

Expected: PASS.

---

### Task 16: Add failing Phase 6 capability/health/audit/redaction tests

**Files:**
- Add: `C:/Users/33031/Desktop/bot/tests/unit_tests/broadcast/test_audit_redaction.py`
- Modify: `C:/Users/33031/Desktop/bot/tests/unit_tests/broadcast/test_executors.py`
- Modify: `C:/Users/33031/Desktop/bot/tests/integration/api/test_broadcast.py`
- Add: `C:/Users/33031/Desktop/bot/web/tests/e2e/broadcast-execution-phase6.spec.ts`

- [ ] **Step 1: Add failing tests for capability and runtime health/version APIs**
- [ ] **Step 2: Add failing tests for audit event storage and log/evidence redaction**
- [ ] **Step 3: Add failing frontend E2E for capability unavailable / health visibility / hidden technical details**
- [ ] **Step 4: Run tests and verify failure**

Run:
`uv run pytest tests/unit_tests/broadcast/test_audit_redaction.py tests/unit_tests/broadcast/test_executors.py tests/integration/api/test_broadcast.py -q`

Run:
`pnpm exec playwright test tests/e2e/broadcast-execution-phase6.spec.ts --project chromium`

Expected: FAIL.

---

### Task 17: Implement Phase 6 capability, health, audit, redaction, and config hardening

**Files:**
- Modify: `C:/Users/33031/Desktop/bot/src/langbot/pkg/broadcast/service.py`
- Modify: `C:/Users/33031/Desktop/bot/src/langbot/pkg/broadcast/errors.py`
- Modify: `C:/Users/33031/Desktop/bot/src/langbot/pkg/broadcast/runtime_gateway.py`
- Modify: `C:/Users/33031/Desktop/bot/src/langbot/pkg/broadcast/executors/base.py`
- Modify: `C:/Users/33031/Desktop/bot/src/langbot/pkg/broadcast/executors/wecom.py`
- Modify: `C:/Users/33031/Desktop/bot/src/langbot/pkg/broadcast/audit.py`
- Modify: `C:/Users/33031/Desktop/bot/src/langbot/pkg/api/http/controller/groups/broadcast.py`

- [ ] **Step 1: Add capability and health endpoints with version and send-disable checks**
- [ ] **Step 2: Add audit events and redaction helpers for logs/evidence/technical details**
- [ ] **Step 3: Add configurable runtime address, timeouts, retry limits, failure policy, version constraints, and startup recovery settings**
- [ ] **Step 4: Run Phase 6 backend tests and verify green**

Run:
`uv run pytest tests/unit_tests/broadcast/test_audit_redaction.py tests/unit_tests/broadcast/test_runtime_gateway.py tests/unit_tests/broadcast/test_executors.py tests/integration/api/test_broadcast.py -q`

Expected: PASS.

---

### Task 18: Implement frontend Phase 6 capability/health/audit display

**Files:**
- Modify: `C:/Users/33031/Desktop/bot/web/src/app/home/broadcast/types.ts`
- Modify: `C:/Users/33031/Desktop/bot/web/src/app/home/broadcast/datasources/BroadcastDataSource.ts`
- Modify: `C:/Users/33031/Desktop/bot/web/src/app/home/broadcast/components/logs/ExecutionLogPanel.tsx`
- Modify: `C:/Users/33031/Desktop/bot/web/src/app/home/broadcast/components/BroadcastWorkspace.tsx`

- [ ] **Step 1: Show executor capability/health status in the workspace/log views**
- [ ] **Step 2: Keep technical details folded and user-facing strings localized**
- [ ] **Step 3: Run TypeScript and Phase 6 Playwright tests and verify green**

Run:
`pnpm exec tsc --noEmit`

Run:
`pnpm exec playwright test tests/e2e/broadcast-execution-phase6.spec.ts --project chromium`

Expected: PASS.

---

### Task 19: Add failing Phase 7 send-flag and confirmation tests

**Files:**
- Modify: `C:/Users/33031/Desktop/bot/tests/unit_tests/broadcast/test_service.py`
- Modify: `C:/Users/33031/Desktop/bot/tests/unit_tests/broadcast/test_runtime_gateway.py`
- Modify: `C:/Users/33031/Desktop/bot/tests/unit_tests/broadcast/test_executors.py`
- Modify: `C:/Users/33031/Desktop/bot/tests/integration/api/test_broadcast.py`
- Add: `C:/Users/33031/Desktop/bot/web/tests/e2e/broadcast-send-flags.spec.ts`
- Add: `C:/Users/33031/Desktop/bot/web/tests/e2e/broadcast-send-confirmation.spec.ts`
- Add: `C:/Users/33031/Desktop/bot/apps/desktop-rpa-runtime/tests/send-message.test.ts`

- [ ] **Step 1: Add failing backend tests for all send flag combinations and one-time token behavior**
- [ ] **Step 2: Add failing runtime tests for isolated `send-message` contract and idempotent non-replay**
- [ ] **Step 3: Add failing frontend E2E for send-disabled and confirmation flows**
- [ ] **Step 4: Run tests and verify failure**

Run:
`uv run pytest tests/unit_tests/broadcast/test_service.py tests/unit_tests/broadcast/test_runtime_gateway.py tests/unit_tests/broadcast/test_executors.py tests/integration/api/test_broadcast.py -q`

Run:
`pnpm exec playwright test tests/e2e/broadcast-send-flags.spec.ts tests/e2e/broadcast-send-confirmation.spec.ts --project chromium`

Run:
`npm test -- --test-name-pattern "send-message|send"`

Expected: FAIL.

---

### Task 20: Implement Phase 7 feature flags, send confirmation, and backend send path

**Files:**
- Modify: `C:/Users/33031/Desktop/bot/src/langbot/pkg/broadcast/service.py`
- Modify: `C:/Users/33031/Desktop/bot/src/langbot/pkg/broadcast/repository.py`
- Modify: `C:/Users/33031/Desktop/bot/src/langbot/pkg/broadcast/runtime_gateway.py`
- Modify: `C:/Users/33031/Desktop/bot/src/langbot/pkg/broadcast/executors/base.py`
- Modify: `C:/Users/33031/Desktop/bot/src/langbot/pkg/broadcast/executors/wecom.py`
- Modify: `C:/Users/33031/Desktop/bot/src/langbot/pkg/broadcast/errors.py`
- Modify: `C:/Users/33031/Desktop/bot/src/langbot/pkg/api/http/controller/groups/broadcast.py`

- [ ] **Step 1: Add send feature flags and enforce default-off gating**
- [ ] **Step 2: Add send confirmation issuance/consumption with one-time token hashing**
- [ ] **Step 3: Add isolated send task creation path in backend, separate from paste**
- [ ] **Step 4: Run backend send tests and verify green**

Run:
`uv run pytest tests/unit_tests/broadcast/test_service.py tests/unit_tests/broadcast/test_runtime_gateway.py tests/unit_tests/broadcast/test_executors.py tests/integration/api/test_broadcast.py -q`

Expected: PASS.

---

### Task 21: Implement runtime `send-message` isolation and no-op testable path

**Files:**
- Modify: `C:/Users/33031/Desktop/bot/apps/desktop-rpa-runtime/src/main/domain/task-types.ts`
- Modify: `C:/Users/33031/Desktop/bot/apps/desktop-rpa-runtime/src/main/api/local-http-server.ts`
- Modify: `C:/Users/33031/Desktop/bot/apps/desktop-rpa-runtime/src/main/runtime/runtime-host.ts`
- Modify: `C:/Users/33031/Desktop/bot/apps/desktop-rpa-runtime/src/main/input/send-controller.ts`
- Add: any send-specific route/controller file needed for strict separation

- [ ] **Step 1: Add a separate `send_message` task action and `/v1/tasks/send-message` route**
- [ ] **Step 2: Enforce confirmation token, send flags, and idempotent replay behavior inside runtime**
- [ ] **Step 3: Keep send code isolated from paste controller logic**
- [ ] **Step 4: Run runtime send tests and verify green**

Run:
`npm test -- --test-name-pattern "send-message|send"`

Expected: PASS.

---

### Task 22: Implement frontend Phase 7 send confirmation UX

**Files:**
- Modify: `C:/Users/33031/Desktop/bot/web/src/app/home/broadcast/types.ts`
- Modify: `C:/Users/33031/Desktop/bot/web/src/app/infra/http/BackendClient.ts`
- Modify: `C:/Users/33031/Desktop/bot/web/src/app/home/broadcast/datasources/BroadcastDataSource.ts`
- Modify: `C:/Users/33031/Desktop/bot/web/src/app/home/broadcast/components/drafts/DraftDetail.tsx`
- Modify: `C:/Users/33031/Desktop/bot/web/src/app/home/broadcast/components/BroadcastWorkspace.tsx`
- Add: send confirmation components as needed

- [ ] **Step 1: Add single-item send confirmation flow with preview, conversation/body confirmation, warning, countdown, and token submission**
- [ ] **Step 2: Keep multi-send disabled by default**
- [ ] **Step 3: Run TypeScript and send E2E tests and verify green**

Run:
`pnpm exec tsc --noEmit`

Run:
`pnpm exec playwright test tests/e2e/broadcast-send-flags.spec.ts tests/e2e/broadcast-send-confirmation.spec.ts --project chromium`

Expected: PASS.

---

### Task 23: Phase-gate verification commands

**Files:**
- No new production files unless a final verified gap is found.

- [ ] **Step 1: Run backend unit suites for Broadcast execution**
- [ ] **Step 2: Run backend integration/API suites**
- [ ] **Step 3: Run migration suites**
- [ ] **Step 4: Run frontend TypeScript + E2E + build**
- [ ] **Step 5: Run runtime tests**
- [ ] **Step 6: Run git diff verification commands**

Run:
`uv run pytest tests/unit_tests/broadcast -q`

Run:
`uv run pytest tests/integration/api/test_broadcast.py -q`

Run:
`uv run pytest tests/integration/persistence/test_migrations.py -q`

Run:
`uv run pytest tests/integration/persistence/test_migrations_postgres.py -q`

Run:
`pnpm exec tsc --noEmit`

Run:
`pnpm exec playwright test tests/e2e/broadcast-*.spec.ts --project chromium`

Run:
`pnpm build`

Run:
`npm test`

Run:
`git diff --check`

Run:
`git diff --stat`

Run:
`git status --short`

Expected: collect fresh evidence for the final report.

---

### Task 24: Live validation boundaries

**Files:**
- No mandatory code change.

- [ ] **Step 1: Perform Phase 4 real WeCom paste-only verification if the local environment is available**
- [ ] **Step 2: Perform Phase 5 serial-queue desktop validation if the local environment is available**
- [ ] **Step 3: Record Phase 6 stability checks for the available environment**
- [ ] **Step 4: Perform Phase 7 live send only if a dedicated test account and dedicated test group are explicitly available**

Expected:
- Phase 4 and 5 live validation may complete locally if the environment supports it.
- Phase 7 live send must remain **not completed** unless a dedicated test environment is actually present.

---

## Final handoff checklist

- [ ] Phase 4 paste-only backend/API/frontend/runtime behavior implemented and verified.
- [ ] Phase 5 durable serial queue behavior implemented and verified.
- [ ] Phase 6 capability/health/audit/redaction/config hardening implemented and verified.
- [ ] Phase 7 code paths implemented with default-off flags and isolated send contract.
- [ ] No non-test real send occurred.
- [ ] No commit, push, or PR created.
