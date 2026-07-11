# Broadcast Phase 4–7 Design

## 1. Background and Goal

Phase 3 completed real import, rematch, draft generation, and review workflows inside the existing Broadcast domain. The next milestone is to extend that domain into a persistent, auditable desktop execution pipeline that can:

- Phase 4: write a single confirmed draft into the chat input box without sending;
- Phase 5: execute multiple draft tasks through a durable serial queue with pause, resume, cancel, retry, and restart recovery;
- Phase 6: generalize execution through executor capabilities, runtime health/version checks, audit/redaction, and production hardening;
- Phase 7: implement isolated real-send code paths behind default-off feature flags and one-time confirmation tokens.

The implementation must preserve the current Phase 3 workspace changes in the working tree, keep the existing Broadcast scope model `(bot_uuid, connector_id)`, and never silently convert “paste into input box” into “message sent”.

This design treats the user’s phase-by-phase requirements as pre-approved design input. The remaining gates are execution tests, runtime safety checks, and real blocking conditions only.

---

## 2. Fixed Scope and Non-Goals

### 2.1 Included scope

- New execution persistence entities for batches, tasks, attempts, and evidence.
- New Alembic migration `0015_broadcast_execution` chained from `0014_broadcast_phase3`.
- New Broadcast execution repository/service/router flows.
- New durable `BroadcastExecutionWorker` with serial task consumption.
- New runtime gateway abstraction for the desktop runtime protocol.
- New executor abstraction with a first concrete `WeComDraftExecutor`.
- Broadcast frontend support for single execution, multi-task queue management, execution logs, capability/health display, and send confirmation UX.
- Runtime protocol extensions for `paste-draft` reuse and a separate `send-message` action.
- Audit, redaction, feature flags, and restart recovery.

### 2.2 Explicit non-goals

- Do not reuse `DatabaseMessage`, `ReplyDraft`, or any fake `message_id` to model broadcast execution.
- Do not change global `BaseHttpClient` semantics.
- Do not place state-machine logic inside the HTTP router.
- Do not place desktop selector logic directly inside `BroadcastService`.
- Do not default to saving screenshots, raw runtime request bodies, complete customer contact details, or full message bodies in logs/evidence.
- Do not allow real sending by default in any environment.
- Do not batch real auto-send in Phase 7.
- Do not commit, push, create a PR, merge `main`, or clean/stash/reset the working tree.

---

## 3. Phase 3 Baseline Closure Result

The current working tree already contains post-Phase-3 acceptance changes that must be preserved:

- broadcast bot / connector selector;
- XLSX worksheet-name display;
- Chinese upload error feedback improvements;
- matching frontend E2E additions;
- current i18n file changes.

Baseline verification result before Phase 4 work:

- `web/tests/e2e/broadcast-workspace.spec.ts`: pass
- `web/tests/e2e/broadcast-import-feedback.spec.ts`: pass
- `web/tests/e2e/broadcast-scope-selector.spec.ts`: pass
- `pnpm build` in `web/`: pass

The only baseline issue was missing `VITE_API_BASE_URL` during local verification; this is an environment requirement, not a code conflict.

---

## 4. Unified Architecture

### 4.1 Fixed execution chain

`ready draft`
→ create execution batch
→ create execution tasks
→ preflight validation
→ channel executor
→ runtime gateway
→ locate conversation
→ write into input box or send
→ persist attempt/evidence
→ update task and batch status

### 4.2 Fixed layering

- **Entity**: execution batches, tasks, attempts, evidence, send confirmations, audit records.
- **Repository**: persistence-only methods; no business transitions.
- **Service**: transactions, scope checks, state machine, idempotency, feature flags, capability gates, audit, error mapping inputs.
- **Worker**: durable serial consumption of pending tasks.
- **Executor**: channel-specific behavior and evidence normalization.
- **RuntimeGateway**: runtime HTTP contract, health/version checks, idempotency propagation, timeout/cancel/query wrappers.
- **Router**: request parsing and error/status mapping only.
- **Frontend DataSource**: API mapping and UI-oriented model adaptation only.

### 4.3 Existing-code integration points

- Reuse the existing Broadcast domain package under `src/langbot/pkg/broadcast/`.
- Reuse the existing desktop runtime app under `apps/desktop-rpa-runtime/` but add a new isolated gateway surface instead of directly coupling Broadcast service to desktop client helpers.
- Keep current `DesktopRuntimeClient` behavior available for existing surfaces, but Phase 4–7 Broadcast execution should use a new gateway abstraction that can enforce the Broadcast-specific contract and safety rules.

---

## 5. Data Model

### 5.1 `BroadcastExecutionBatch`

Fields:

- `id`
- `bot_uuid`
- `connector_id`
- `channel`
- `mode` = `paste_only | send`
- `status` = `created | queued | running | paused | completed | partially_failed | failed | cancelled | interrupted`
- `total_tasks`
- `pending_tasks`
- `running_tasks`
- `succeeded_tasks`
- `failed_tasks`
- `cancelled_tasks`
- `interrupted_tasks`
- `created_at`
- `started_at`
- `paused_at`
- `finished_at`
- `cancelled_at`
- `error_message`
- `version`
- `created_by` (operator identity for audit)
- `last_action_by` (optional convenience snapshot)

Indexes:

- `bot_uuid`
- `connector_id`
- `(bot_uuid, connector_id)`
- `status`
- `created_at`

### 5.2 `BroadcastExecutionTask`

Fields:

- `id`
- `execution_batch_id`
- `draft_id` nullable
- `draft_text_snapshot`
- `target_conversation_snapshot`
- `channel`
- `action` = `paste_draft | send_message`
- `status` = `pending | running | succeeded | failed | cancelled | interrupted`
- `sequence_no`
- `attempt_count`
- `max_attempts`
- `idempotency_key`
- `request_digest`
- `runtime_task_id`
- `error_code`
- `error_message`
- `created_at`
- `started_at`
- `finished_at`
- `cancelled_at`
- `updated_at`
- `operator_note` nullable

Constraints:

- unique `(execution_batch_id, sequence_no)`
- unique successful-attempt replay prevention should be enforced logically in service/runtime, not by over-constraining the task row

### 5.3 `BroadcastExecutionAttempt`

Fields:

- `id`
- `execution_task_id`
- `attempt_no`
- `idempotency_key`
- `request_digest`
- `runtime_task_id`
- `request_summary`
- `response_summary`
- `status`
- `error_code`
- `error_message`
- `started_at`
- `finished_at`

Constraints:

- unique `(execution_task_id, attempt_no)`
- unique `idempotency_key`

### 5.4 `BroadcastExecutionEvidence`

Fields:

- `id`
- `execution_attempt_id`
- `window_title`
- `target_conversation`
- `action`
- `input_located`
- `draft_written`
- `send_triggered`
- `clipboard_restored`
- `runtime_state`
- `evidence_summary`
- `technical_details`
- `created_at`

Rules:

- Phase 4–6: `send_triggered` must always be `false`.
- Default evidence must be redacted, structured, and text-only.
- No screenshot storage by default.
- No raw runtime body persistence by default.

### 5.5 `BroadcastSendConfirmation`

Phase 7 adds a one-time send confirmation token table:

- `id`
- `execution_task_id`
- `confirmation_token_hash`
- `issued_at`
- `expires_at`
- `used_at`
- `issued_by`
- `used_by`
- `status` = `issued | used | expired | revoked`

### 5.6 Audit model

The implementation should add either a dedicated broadcast audit table or reuse an existing generic audit facility if one already exists cleanly. Required audit events:

- batch created
- batch started
- batch paused
- batch resumed
- batch cancelled
- task retry requested
- send confirmation issued
- send confirmation consumed
- runtime safety rejection

The stored audit payload must be redacted and scope-bound.

---

## 6. Migration Strategy

New migration:

- file: `src/langbot/pkg/persistence/alembic/versions/0015_broadcast_execution.py`
- `down_revision = '0014_broadcast_phase3'`
- revision length `<= 32`

Migration requirements:

- guarded existence checks for create/drop/index operations;
- SQLite and PostgreSQL upgrade/downgrade support;
- metadata registration tests;
- FK behavior coverage;
- no branch split.

Expected FK behavior:

- batch → tasks: `ON DELETE CASCADE`
- task → attempts: `ON DELETE CASCADE`
- attempt → evidence: `ON DELETE CASCADE`
- task → draft: `ON DELETE SET NULL`
- send confirmation → task: `ON DELETE CASCADE`

---

## 7. Preconditions for Execution

A draft may enter execution only if all of the following are true:

- `draft.status == 'ready'`
- its import batch has `drafts_stale = false`
- `target_conversation_name` is non-empty
- `draft_text` is non-empty
- scope `(bot_uuid, connector_id)` is valid and resource ownership matches
- requested `action` is allowed for the current phase and mode
- executor capability covers the action
- runtime health/version checks pass
- required feature flags pass
- for Phase 4–6, force-disable-send is enabled at every layer

Failure should happen before runtime invocation and return user-facing Chinese errors.

---

## 8. State Machines and Transactions

### 8.1 Batch transitions

Allowed:

- `created -> queued`
- `queued -> running`
- `running -> paused`
- `paused -> running`
- `running -> completed`
- `running -> partially_failed`
- `running -> failed`
- `running -> cancelled`
- `running -> interrupted`
- `queued -> cancelled`
- `paused -> cancelled`
- `queued|paused|interrupted -> running` only through explicit start/resume paths with validation

Forbidden:

- frontend directly computing and writing summary counts/statuses
- automatic resurrection of interrupted/running tasks after restart

### 8.2 Task transitions

Allowed:

- `pending -> running`
- `pending -> cancelled`
- `running -> succeeded`
- `running -> failed`
- `running -> interrupted`
- `failed -> pending` only by manual retry
- `interrupted -> pending` only by explicit user-confirmed resume/retry

Forbidden:

- `succeeded -> pending`
- `cancelled -> running`
- auto-infinite retries
- cross-scope state updates

### 8.3 Transaction boundaries

Each of the following must use one connection and one transaction:

- create batch + all tasks
- claim one pending task and mark it running
- create attempt row
- finish attempt and update task + batch summaries
- pause / resume batch
- cancel pending tasks
- manual retry
- startup recovery marking running tasks as interrupted
- delete a batch and all child rows

No half-commits are allowed.

---

## 9. Idempotency Rules

`request_digest`:

`SHA-256(action + "\0" + channel + "\0" + target_conversation + "\0" + draft_text_snapshot)`

`idempotency_key`:

`broadcast:{execution_task_id}:{attempt_no}`

Rules:

- repeating the same attempt must not duplicate execution;
- manual retry increments `attempt_no` and gets a new key;
- a succeeded attempt cannot be replayed;
- backend and runtime both enforce idempotency;
- runtime timeout cannot trigger blind retry before querying state.

---

## 10. Runtime Gateway Contract

### 10.1 Gateway interface

The backend gateway should expose at least:

- `health_check()`
- `get_capabilities()`
- `assert_compatible_version()`
- `assert_force_disable_send()`
- `create_paste_task()`
- `create_send_task()`
- `query_task()`
- `cancel_task()`

### 10.2 Phase 4 paste contract

Reuse runtime endpoint:

`POST /v1/tasks/paste-draft`

Request body:

```json
{
  "action": "paste_draft",
  "conversationName": "...",
  "draftText": "...",
  "idempotencyKey": "...",
  "requestDigest": "..."
}
```

Safety requirement:

`LANGBOT_RPA_FORCE_DISABLE_SEND=1` must be validated at:

- backend startup/config load
- execution creation
- worker execution start
- runtime action handling

Any failure rejects before performing desktop actions.

### 10.3 Phase 7 send contract

A separate runtime endpoint is required, for example:

`POST /v1/tasks/send-message`

Request body:

```json
{
  "action": "send_message",
  "conversationName": "...",
  "messageText": "...",
  "idempotencyKey": "...",
  "requestDigest": "...",
  "confirmationToken": "..."
}
```

Paste and send must stay completely separated in routing, task action, capability flags, audit, and code organization.

### 10.4 Runtime result normalization

The gateway must normalize runtime outputs into:

- safe user-facing error classes
- structured attempt summaries
- redacted evidence fragments
- interruptible / terminal / ambiguous states

---

## 11. Executor Architecture

### 11.1 Abstract executor

Introduce `ConversationDraftExecutor` with:

- `validate_capability()`
- `health_check()`
- `paste_draft()`
- `send_message()`
- `cancel()`
- `query_status()`
- `normalize_evidence()`

### 11.2 First concrete executor

- `WeComDraftExecutor` is the first real implementation.
- It uses the runtime gateway and WeCom-specific capability/health rules.
- It remains paste-only through Phase 6.

### 11.3 Declared but unsupported channels

Stub registration only, returning clear unsupported errors:

- WeChat
- DingTalk
- Feishu
- Slack
- Telegram

No fake support claims.

### 11.4 Capability model

At minimum:

- `supports_paste`
- `supports_send`
- `supports_cancel`
- `supports_status_query`
- `supports_clipboard_restore`
- `supports_evidence`
- `executor_version`
- `runtime_min_version`

Phase 4–6 force:

- `supports_send = false`

---

## 12. Worker Model

### 12.1 `BroadcastExecutionWorker`

Rules:

- global concurrency fixed at `1`
- strict ordering by `sequence_no`
- next task cannot start until current task reaches a terminal state
- persistent DB-backed queue only
- atomic claim / locking to prevent double-claim in multi-instance scenarios
- no default automatic retries

### 12.2 Pause behavior

- never forcibly interrupt a desktop action already in progress;
- stop claiming the next task after the current running task finishes.

### 12.3 Cancel behavior

- cancel pending tasks immediately;
- running task cancellation only if the runtime explicitly supports safe cancel;
- succeeded tasks remain untouched.

### 12.4 Restart recovery

On startup:

- detect tasks/batches left in `running`;
- mark those tasks `interrupted`;
- recompute batch summaries/status to `interrupted` or `partially_failed` as appropriate;
- do not automatically replay anything.

---

## 13. API Design

All endpoints must apply:

- `validate_scope()`
- ownership checks
- state checks
- capability checks
- feature flag checks

### 13.1 Batch APIs

- `POST /api/v1/broadcast/executions`
- `GET /api/v1/broadcast/executions`
- `GET /api/v1/broadcast/executions/{batch_id}`
- `POST /api/v1/broadcast/executions/{batch_id}/start`
- `POST /api/v1/broadcast/executions/{batch_id}/pause`
- `POST /api/v1/broadcast/executions/{batch_id}/resume`
- `POST /api/v1/broadcast/executions/{batch_id}/cancel`

Phase 4 batch creation accepts exactly one draft.

### 13.2 Task APIs

- `GET /api/v1/broadcast/execution-tasks/{task_id}`
- `POST /api/v1/broadcast/execution-tasks/{task_id}/start`
- `POST /api/v1/broadcast/execution-tasks/{task_id}/cancel`
- `POST /api/v1/broadcast/execution-tasks/{task_id}/retry`
- `POST /api/v1/broadcast/execution-tasks/{task_id}/send`

### 13.3 Attempt and evidence APIs

- `GET /api/v1/broadcast/execution-tasks/{task_id}/attempts`
- `GET /api/v1/broadcast/execution-attempts/{attempt_id}`
- `GET /api/v1/broadcast/execution-attempts/{attempt_id}/evidence`

### 13.4 Capability and health APIs

- `GET /api/v1/broadcast/executors/capabilities`
- `GET /api/v1/broadcast/executors/health`

### 13.5 Send confirmation APIs

- `POST /api/v1/broadcast/send-confirmations`
- `POST /api/v1/broadcast/execution-tasks/{task_id}/send`

### 13.6 Error semantics

Use the existing Broadcast localized error response shape:

```json
{
  "code": -1,
  "msg": "ERROR_CODE",
  "message": "中文概述",
  "details": ["中文细节"]
}
```

No internal paths, stack traces, SQL, or runtime raw bodies in user-facing responses.

---

## 14. Frontend Design

### 14.1 Review page evolution

Add Phase 4 actions and state:

- write into input box
- pre-execution confirmation
- target conversation display
- message preview
- runtime state/result display
- retry failed task
- execution status indicator

Button enabled only when:

- draft is `ready`
- not stale
- target group exists
- draft body exists

### 14.2 Multi-task queue UX

Phase 5 adds:

- multi-select ready drafts
- create execution batch
- batch list
- task list
- real-time counters
- pause / resume / cancel remaining
- retry failed task
- view attempts
- view evidence

### 14.3 Execution log page

Replace mock logs with real:

- batches
- tasks
- attempts
- evidence summaries
- audit-friendly operator history
- capability / health panels

### 14.4 Send safety UX

Phase 7 send UI must require:

- single item preview only
- conversation confirmation
- body confirmation
- explicit “real send” warning
- secondary confirmation
- short countdown
- one-time token flow
- one-task-only send path
- no default bulk auto-send

---

## 15. Audit, Redaction, and Privacy

Required guarantees:

- operator identity is recorded for create/start/pause/resume/cancel/retry/send-confirmation actions;
- normal logs must not print full message bodies;
- normal logs must not print full customer contact details;
- runtime technical details remain collapsible/secondary in UI;
- evidence stores redacted summaries, not screenshots or raw payloads by default.

Redaction policy:

- retain conversation name snapshots because they are required to explain execution targeting;
- redact message body to summary/hash/truncated preview unless the draft snapshot field itself is intentionally persisted for task reproducibility;
- redact confirmation tokens using hash-only storage;
- redact runtime raw details into whitelisted structured fields.

---

## 16. Feature Flags and Phase 7 Safety Boundary

Default values must all disable real send:

- `LANGBOT_BROADCAST_SEND_ENABLED=0`
- `connector.allow_send = false`
- `executor.supports_send = false`
- batch `mode != send`
- no valid user secondary confirmation

Real send is allowed only when all required gates pass.

Paste-only phases also require:

- `LANGBOT_RPA_FORCE_DISABLE_SEND=1`

Any missing gate must reject with a localized safe error before runtime invocation.

---

## 17. Testing Strategy

### 17.1 Backend unit tests

Add/extend tests for:

- execution repository
- execution state machine
- idempotency
- worker
- runtime gateway
- WeCom executor
- capability logic
- feature flags
- send confirmation
- audit/redaction

### 17.2 Backend integration tests

Add/extend tests for:

- execution APIs
- scope isolation
- transactions
- restart recovery
- worker locking
- runtime timeout handling
- duplicate runtime responses
- send flag combinations

### 17.3 Migration tests

- SQLite upgrade/downgrade
- PostgreSQL upgrade/downgrade
- FK cascade/set-null
- indexes
- unique constraints
- metadata registration

### 17.4 Frontend E2E

- single paste-only execution
- multi-task queue
- pause/resume/cancel/retry
- restart recovery display
- execution logs
- capability unavailable
- send disabled by flag
- send confirmation flow
- no duplicate requests

### 17.5 Runtime tests

- runtime unit tests
- paste-draft integration tests
- send-message isolated tests
- idempotency tests
- clipboard restore tests
- no-accidental-send tests

### 17.6 Static safety scan

Phase 4–6 execution paths must not contain:

- `press("Enter")`
- `keyboard.press("Enter")`
- send button click logic
- `send_message`
- `send-message` runtime calls

Phase 7 may contain send-specific logic only inside isolated, flag-protected send executor/runtime paths.

---

## 18. Phase-by-Phase Acceptance Gates

### Phase 4

Must verify:

- pending_review / invalid / stale drafts cannot execute
- cross-scope execution is rejected
- conversation-not-found fails correctly
- input-box-not-found fails correctly
- clipboard restore is recorded correctly
- duplicate idempotency key does not paste twice
- timeout does not duplicate execution
- no Enter simulation for sending
- no send button click
- no send_message call
- real WeCom validation pastes into input only and does not send

### Phase 5

Must verify:

- strict serial execution
- stable order
- pause stops next claim
- resume restarts claiming
- cancel affects pending tasks
- retry creates new attempt
- attempt history is preserved
- restart marks running to interrupted
- no automatic duplicate write
- no sending behavior

### Phase 6

Must verify:

- capability and health gates work
- runtime version gate works
- force-disable-send remains effective
- audit/redaction works
- scale/display/minimized/occluded/runtime-reconnect scenarios are handled and recorded

### Phase 7

Must verify:

- all send flags are default off
- any disabled gate blocks send
- paste and send are fully separate
- confirmation token is one-time-use
- idempotency blocks repeat send
- timeout does not trigger blind resend
- send result is auditable
- only dedicated test account/group may be used for live validation
- production remains default-disabled

If no dedicated send-test environment exists, Phase 7 real send live validation remains incomplete by design.

---

## 19. File and Module Plan

### Backend Broadcast domain

Expected new or modified files:

- `src/langbot/pkg/entity/persistence/broadcast.py`
- `src/langbot/pkg/persistence/alembic/versions/0015_broadcast_execution.py`
- `src/langbot/pkg/broadcast/repository.py`
- `src/langbot/pkg/broadcast/service.py`
- `src/langbot/pkg/broadcast/errors.py`
- `src/langbot/pkg/broadcast/schemas.py`
- `src/langbot/pkg/broadcast/runtime_gateway.py` (new)
- `src/langbot/pkg/broadcast/executors/base.py` (new)
- `src/langbot/pkg/broadcast/executors/wecom.py` (new)
- `src/langbot/pkg/broadcast/executors/registry.py` (new)
- `src/langbot/pkg/broadcast/worker.py` (new)
- `src/langbot/pkg/broadcast/audit.py` (new or reuse helper module)
- `src/langbot/pkg/api/http/controller/groups/broadcast.py`

### Backend tests

- `tests/unit_tests/broadcast/test_repository.py`
- `tests/unit_tests/broadcast/test_service.py`
- `tests/unit_tests/broadcast/test_routes.py`
- `tests/unit_tests/broadcast/test_execution_worker.py` (new)
- `tests/unit_tests/broadcast/test_runtime_gateway.py` (new)
- `tests/unit_tests/broadcast/test_executors.py` (new)
- `tests/unit_tests/broadcast/test_audit_redaction.py` (new)
- `tests/integration/api/test_broadcast.py`
- `tests/integration/persistence/test_migrations.py`
- `tests/integration/persistence/test_migrations_postgres.py`

### Frontend

- `web/src/app/home/broadcast/types.ts`
- `web/src/app/home/broadcast/datasources/BroadcastDataSource.ts`
- `web/src/app/infra/http/BackendClient.ts`
- `web/src/app/home/broadcast/components/drafts/DraftQueue.tsx`
- `web/src/app/home/broadcast/components/drafts/DraftDetail.tsx`
- `web/src/app/home/broadcast/components/logs/ExecutionLogPanel.tsx`
- `web/src/app/home/broadcast/components/BroadcastWorkspace.tsx`
- execution-specific new components as needed under `web/src/app/home/broadcast/components/`
- `web/tests/e2e/broadcast-workspace.spec.ts`
- `web/tests/e2e/broadcast-import-feedback.spec.ts`
- `web/tests/e2e/broadcast-scope-selector.spec.ts`
- new execution/send E2E specs as needed
- `web/tests/e2e/fixtures/langbot-api.ts`

### Runtime

- `apps/desktop-rpa-runtime/src/main/domain/task-types.ts`
- `apps/desktop-rpa-runtime/src/main/api/routes-actions.ts`
- `apps/desktop-rpa-runtime/src/main/api/local-http-server.ts`
- `apps/desktop-rpa-runtime/src/main/runtime/runtime-host.ts`
- `apps/desktop-rpa-runtime/src/main/runtime/task-registry.ts`
- `apps/desktop-rpa-runtime/src/main/input/paste-controller.ts`
- `apps/desktop-rpa-runtime/src/main/input/send-controller.ts`
- runtime route/task files as needed for send-message separation
- `apps/desktop-rpa-runtime/tests/*.test.ts`

---

## 20. Acceptance Summary

Completion of the overall Phase 4–7 implementation means:

- Phase 4 paste-only execution is real, auditable, idempotent, and non-sending.
- Phase 5 queueing is durable, serial, restart-safe, and manually controllable.
- Phase 6 capability/health/audit/redaction/stability gates are in place.
- Phase 7 real-send code exists behind strict default-off feature flags and dedicated confirmation flow.
- No non-test real send occurs.
- No PR, commit, or push is performed in this task.
