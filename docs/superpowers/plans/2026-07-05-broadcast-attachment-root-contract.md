# Broadcast Attachment Root Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace absolute attachment-path delivery with a shared task-level attachment root plus relative paths, while preserving path-safety checks, legacy-data compatibility, and the existing keyboard-only paste flow.

**Architecture:** The backend becomes the single authority for the controlled attachment root and stores a stable `relative_path` alongside legacy `stored_path`. Runtime tasks carry one canonical `attachmentRoot` plus per-attachment `relativePath`, and the desktop runtime resolves each file via `realpath` + `path.relative` without relying on `process.cwd()` or packaged executable paths.

**Tech Stack:** Python (Quart, SQLAlchemy, Alembic, pytest), TypeScript (Electron runtime, Node fs/path, node:test), React/Vite frontend i18n.

---

### Task 1: Persist stable relative attachment paths with legacy compatibility

**Files:**
- Modify: `C:/Users/33031/Desktop/bot/src/langbot/pkg/entity/persistence/broadcast.py`
- Modify: `C:/Users/33031/Desktop/bot/src/langbot/pkg/persistence/alembic/versions/0017_broadcast_attach.py`
- Modify: `C:/Users/33031/Desktop/bot/src/langbot/pkg/broadcast/repository.py`
- Test: `C:/Users/33031/Desktop/bot/tests/unit_tests/broadcast/test_repository.py`

- [ ] Add `relative_path` to the attachment asset model and migration, keeping legacy `stored_path`.
- [ ] Backfill `relative_path` from existing `stored_path` values under the controlled root during migration.
- [ ] Update repository selects to expose `relative_path` anywhere attachment assets are joined.
- [ ] Add/adjust repository tests for reading legacy absolute-path rows and new relative-path rows.

### Task 2: Make backend attachment root resolution explicit and safe

**Files:**
- Modify: `C:/Users/33031/Desktop/bot/src/langbot/pkg/broadcast/service.py`
- Modify: `C:/Users/33031/Desktop/bot/src/langbot/pkg/broadcast/runtime_gateway.py`
- Modify: `C:/Users/33031/Desktop/bot/src/langbot/pkg/broadcast/executors/base.py`
- Modify: `C:/Users/33031/Desktop/bot/src/langbot/pkg/broadcast/executors/wecom.py`
- Test: `C:/Users/33031/Desktop/bot/tests/unit_tests/broadcast/test_service.py`
- Test: `C:/Users/33031/Desktop/bot/tests/unit_tests/broadcast/test_runtime_gateway.py`

- [ ] Replace backend root guessing via `os.getcwd()` with a shared root resolver for `runtime/broadcast_attachments`.
- [ ] Write uploads only into that root, persist `relative_path`, and keep old `stored_path` for compatibility.
- [ ] Build Runtime paste payloads with task-level `attachmentRoot` and attachment-level `relativePath` only.
- [ ] Keep absolute paths out of frontend-facing task/evidence payloads.
- [ ] Map `ATTACHMENT_PATH_OUTSIDE_ROOT` to failed task/attempt/execution status and use the corrected user-facing message.
- [ ] Add service/runtime-gateway tests for payload shape, legacy-path fallback, and failed status mapping.

### Task 3: Make desktop runtime resolve attachments only from task payload

**Files:**
- Modify: `C:/Users/33031/Desktop/bot/apps/desktop-rpa-runtime/src/main/domain/task-types.ts`
- Modify: `C:/Users/33031/Desktop/bot/apps/desktop-rpa-runtime/src/main/api/local-http-server.ts`
- Modify: `C:/Users/33031/Desktop/bot/apps/desktop-rpa-runtime/src/main/input/file-clipboard-controller.ts`
- Modify: `C:/Users/33031/Desktop/bot/apps/desktop-rpa-runtime/src/main/input/paste-controller.ts`
- Modify: `C:/Users/33031/Desktop/bot/apps/desktop-rpa-runtime/src/main/runtime/runtime-host.ts`
- Test: `C:/Users/33031/Desktop/bot/apps/desktop-rpa-runtime/tests/phase2-core.test.ts`

- [ ] Extend task contracts with `attachmentRoot` and `relativePath`.
- [ ] Remove attachment root inference from `process.cwd()`.
- [ ] Resolve root and file via `fs.realpath`, verify containment via `path.relative`, and preserve size/SHA/file checks.
- [ ] Return precise sanitized runtime `errorCode` / `errorMessage` for attachment root violations.
- [ ] Add runtime tests for valid in-root attachments, prefix collisions, `..` escape, digest mismatch, and multi-attachment success.

### Task 4: Keep API/frontend messaging aligned without leaking absolute paths

**Files:**
- Modify: `C:/Users/33031/Desktop/bot/src/langbot/pkg/api/http/controller/groups/broadcast.py`
- Modify: `C:/Users/33031/Desktop/bot/web/src/app/home/broadcast/datasources/BroadcastDataSource.ts`
- Modify: `C:/Users/33031/Desktop/bot/web/src/app/home/broadcast/components/logs/ExecutionLogPanel.tsx`
- Modify: `C:/Users/33031/Desktop/bot/web/src/i18n/locales/en-US.ts`
- Modify: `C:/Users/33031/Desktop/bot/web/src/i18n/locales/zh-Hans.ts`
- Modify: `C:/Users/33031/Desktop/bot/web/src/i18n/locales/ja-JP.ts`
- Test: `C:/Users/33031/Desktop/bot/tests/integration/api/test_broadcast.py`

- [ ] Keep API error responses precise for attachment-root violations.
- [ ] Ensure frontend log display uses corrected message/error code paths without exposing absolute local paths.
- [ ] Add/update API integration tests for error messaging and path redaction.

### Task 5: Verify and package

**Files:**
- Modify: `C:/Users/33031/Desktop/bot/docs/superpowers/plans/2026-07-05-broadcast-attachment-root-contract.md`

- [ ] Run `npm --prefix apps/desktop-rpa-runtime test`.
- [ ] Run `npm --prefix apps/desktop-rpa-runtime run typecheck`.
- [ ] Run `npm --prefix apps/desktop-rpa-runtime run build`.
- [ ] Run `C:/Users/33031/Desktop/bot/.venv/Scripts/python.exe -m pytest tests/unit_tests/broadcast tests/integration/api/test_broadcast.py -q`.
- [ ] Run `pnpm --dir web exec tsc --noEmit`.
- [ ] Run `pnpm --dir web build`.
- [ ] Run frontend lint/prettier checks for changed frontend files.
- [ ] Run `git diff --check`.
- [ ] Run `npm --prefix apps/desktop-rpa-runtime run package:win`.
