# WXWork Database Channel Bot Processing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Integrate WXWork database mode into the unified channel and bot processing architecture while preserving the current `database_mode` API as a compatibility layer.

**Architecture:** Keep `database_conversations` and `database_messages` as the first-stage channel-backed source of truth, then add channel account, bot binding, processing run, and reply draft entities around them. Move new processing logic into dedicated channel and bot-processing services, and make the legacy `database_mode` routes call those services without changing their public response contracts.

**Tech Stack:** Quart, SQLAlchemy, Alembic, asyncio task manager, React Router 7, shadcn/ui, Tailwind CSS, pytest, Playwright.

---

### Task 1: Add persistence models and migration for channel binding and draft processing

**Files:**
- Modify: `C:\Users\33031\Desktop\bot\src\langbot\pkg\entity\persistence\database_mode.py`
- Create: `C:\Users\33031\Desktop\bot\src\langbot\pkg\persistence\alembic\versions\0009_channel_bot_processing.py`
- Test: `C:\Users\33031\Desktop\bot\tests\unit_tests\database_mode\test_database_mode_service.py`

- [ ] Add `ChannelAccount`, `BotChannelBinding`, `MessageProcessingRun`, and `ReplyDraft` ORM models.
- [ ] Keep old `DatabaseConversation` and `DatabaseMessage` fields for compatibility, without adding `bot_uuid` ownership to source messages.
- [ ] Add guarded Alembic migration that creates new tables and indexes only when missing.
- [ ] Extend test fixtures to create the new tables in the in-memory test database.

### Task 2: Add channel and bot-processing domain services

**Files:**
- Create: `C:\Users\33031\Desktop\bot\src\langbot\pkg\database_mode\channel_service.py`
- Create: `C:\Users\33031\Desktop\bot\src\langbot\pkg\database_mode\processing_service.py`
- Modify: `C:\Users\33031\Desktop\bot\src\langbot\pkg\core\app.py`
- Modify: `C:\Users\33031\Desktop\bot\src\langbot\pkg\database_mode\__init__.py`
- Test: `C:\Users\33031\Desktop\bot\tests\unit_tests\database_mode\test_database_mode_service.py`

- [ ] Move connector ingest, channel account resolution, and message lookup helpers into a dedicated channel service.
- [ ] Add bot binding lookup, `effective_from` checks, processing-run claim logic, and reply draft persistence to a processing service.
- [ ] Register the new services on `Application`.
- [ ] Keep services explicit about `bot_uuid`, `message_id`, `connector_id`, `event_id`, `message_key`, and `pipeline_uuid` to avoid hidden mutable state.

### Task 3: Register the `wxwork_database` adapter and bot validation rules

**Files:**
- Create: `C:\Users\33031\Desktop\bot\src\langbot\pkg\platform\sources\wxwork_database.py`
- Create: `C:\Users\33031\Desktop\bot\src\langbot\pkg\platform\sources\wxwork_database.yaml`
- Modify: `C:\Users\33031\Desktop\bot\src\langbot\pkg\api\http\service\bot.py`
- Modify: `C:\Users\33031\Desktop\bot\src\langbot\pkg\platform\botmgr.py`
- Test: `C:\Users\33031\Desktop\bot\tests\unit_tests\api\http\service\test_bot_service.py`

- [ ] Register a discoverable adapter named `wxwork_database` with the correct label and config schema.
- [ ] Make bot create and update validate the single-enabled-binding rule for `connector_id=wxwork-local`.
- [ ] Persist `processing_since` in adapter config only when transitioning from disabled to enabled.
- [ ] Ensure `send_message()` does not perform real sending and is only used for reply-draft output or explicit unsupported errors.

### Task 4: Rewire compatibility-layer `database_mode` service to the new domain services

**Files:**
- Modify: `C:\Users\33031\Desktop\bot\src\langbot\pkg\database_mode\service.py`
- Modify: `C:\Users\33031\Desktop\bot\src\langbot\pkg\api\http\controller\groups\database_mode.py`
- Test: `C:\Users\33031\Desktop\bot\tests\unit_tests\database_mode\test_database_mode_service.py`
- Test: `C:\Users\33031\Desktop\bot\tests\unit_tests\database_mode\test_database_mode_routes.py`

- [ ] Keep all current `/api/v1/database-mode/*` routes and response structures.
- [ ] Make `generate_draft`, `process`, `skip`, delete, and batch operations delegate to the new processing service.
- [ ] Keep SSE event contracts intact while publishing from the new processing flow.
- [ ] Mark the legacy service and routes as compatibility-layer code in comments, without shrinking functionality.

### Task 5: Reuse RuntimeBot and pipeline routing for WXWork database processing

**Files:**
- Modify: `C:\Users\33031\Desktop\bot\src\langbot\pkg\platform\botmgr.py`
- Modify: `C:\Users\33031\Desktop\bot\src\langbot\pkg\pipeline\aggregator.py`
- Modify: `C:\Users\33031\Desktop\bot\src\langbot\pkg\database_mode\processing_service.py`
- Test: `C:\Users\33031\Desktop\bot\tests\unit_tests\database_mode\test_database_mode_service.py`

- [ ] Add a safe path to build a standard LangBot message event from a channel-backed database message.
- [ ] Reuse `RuntimeBot.resolve_pipeline_uuid()` and the existing pipeline execution path instead of hard-coding model usage.
- [ ] Save the complete generated output once into `ReplyDraft` and compatibility fields, never token-stream partial output.
- [ ] Ensure automatic and manual processing converge on the same claim-and-run code path.

### Task 6: Add minimal bot-scoped conversation and draft APIs

**Files:**
- Modify: `C:\Users\33031\Desktop\bot\src\langbot\pkg\api\http\controller\groups\platform\bots.py`
- Modify: `C:\Users\33031\Desktop\bot\src\langbot\pkg\api\http\service\bot.py`
- Modify: `C:\Users\33031\Desktop\bot\src\langbot\pkg\database_mode\processing_service.py`
- Test: `C:\Users\33031\Desktop\bot\tests\unit_tests\api\http\service\test_bot_service.py`

- [ ] Add bot-scoped conversation, message, generate-draft, update-draft, process, skip, and delete entry points only where needed by the bot UI.
- [ ] Validate bot existence, adapter type, active binding, and message ownership by bound channel account.
- [ ] Avoid building a parallel duplicate API surface beyond the minimal bot-scoped wrapper needed for the new sessions tab.

### Task 7: Reuse bot UI for config, logs, and sessions

**Files:**
- Modify: `C:\Users\33031\Desktop\bot\web\src\app\home\bots\components\bot-form\BotForm.tsx`
- Modify: `C:\Users\33031\Desktop\bot\web\src\app\home\bots\components\bot-session\BotSessionMonitor.tsx`
- Modify: `C:\Users\33031\Desktop\bot\web\src\app\home\bots\BotDetailContent.tsx`
- Modify: `C:\Users\33031\Desktop\bot\web\src\app\infra\http\BackendClient.ts`
- Modify: `C:\Users\33031\Desktop\bot\web\src\app\infra\entities\api.ts`
- Test: `C:\Users\33031\Desktop\bot\web\tests\e2e\database-mode-realtime.spec.ts`

- [ ] Show `wxwork_database` in the adapter list with a reduced adapter-config form.
- [ ] Reuse the current config and log tabs for the new adapter without showing official webhook fields or streaming options.
- [ ] Refactor `BotSessionMonitor` to support a runtime-bot source and a channel-message source, rather than cloning the whole page.
- [ ] Disable send actions and keep only the first-stage AI card behavior enabled for database-backed sessions.

### Task 8: Redirect old database-mode UI entry and keep legacy realtime hooks

**Files:**
- Modify: `C:\Users\33031\Desktop\bot\web\src\app\home\database-mode\page.tsx`
- Modify: `C:\Users\33031\Desktop\bot\web\src\app\home\components\home-sidebar\sidbarConfigList.tsx`
- Modify: `C:\Users\33031\Desktop\bot\web\src\router.tsx`
- Test: `C:\Users\33031\Desktop\bot\web\tests\e2e\database-mode-realtime.spec.ts`

- [ ] Redirect `/home/database-mode` to `/home/bots?id=<bot_uuid>&tab=sessions` for the unique enabled `wxwork_database` bot.
- [ ] If no enabled bot exists, redirect to `/home/bots` and show a create-or-enable prompt.
- [ ] Remove the standalone sidebar entry while keeping the old page code as a redirect shell.
- [ ] Leave `useDatabaseModeEvents.ts` connection-management logic untouched and reuse it from the sessions experience.

### Task 9: Verify regressions and targeted acceptance coverage

**Files:**
- Modify as needed: targeted backend/frontend tests only

- [ ] Run `uv run pytest tests\unit_tests\database_mode -q --basetemp ".tmp-pytest-channel-bot"`
- [ ] Run `uv run pytest tests\unit_tests\api\http\service\test_bot_service.py -q --basetemp ".tmp-pytest-channel-bot"`
- [ ] Run `uv run pytest tests\unit_tests\local_connectors -q --basetemp ".tmp-pytest-channel-bot"`
- [ ] Run `uv run pytest tests\unit_tests -q --basetemp ".tmp-pytest-unit"`
- [ ] Run `corepack pnpm exec eslint src/app/home/bots src/app/home/database-mode src/router.tsx`
- [ ] Run `corepack pnpm exec playwright test tests/e2e/database-mode-realtime.spec.ts`
- [ ] Run `corepack pnpm build`
- [ ] Run `git diff --check`, `git status --short`, and `git diff --stat`
