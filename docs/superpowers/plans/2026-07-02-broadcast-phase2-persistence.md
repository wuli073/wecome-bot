# Broadcast Phase 2 Persistence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add bot/connector-scoped broadcast rule persistence, HTTP CRUD APIs, and frontend Rules-tab integration while keeping import/review/log tabs on Mock data and avoiding any runtime or agent-surface changes.

**Architecture:** Add a dedicated broadcast domain under `src/langbot/pkg/broadcast/`, dedicated ORM models under `src/langbot/pkg/entity/persistence/broadcast.py`, and a dedicated controller under `src/langbot/pkg/api/http/controller/groups/broadcast.py`. Scope parsing and validation are centralized in one controller helper, service-level business rules are isolated from repository SQL, and the frontend swaps only the three Rules sub-tabs from mock state to `BackendClient` APIs.

**Tech Stack:** Python 3.11+, Quart, SQLAlchemy, Alembic, pytest, Playwright, React, TypeScript, Vite, Sonner

---

### Task 1: Register ORM models and migration first

**Files:**
- Create: `C:/Users/33031/Desktop/bot/src/langbot/pkg/entity/persistence/broadcast.py`
- Modify: `C:/Users/33031/Desktop/bot/tests/integration/persistence/test_migrations.py`
- Modify: `C:/Users/33031/Desktop/bot/tests/integration/persistence/test_migrations_postgres.py`
- Create: `C:/Users/33031/Desktop/bot/src/langbot/pkg/persistence/alembic/versions/0013_broadcast_rules.py`

- [ ] **Step 1: Write failing migration/model registration tests**
- [ ] **Step 2: Run the focused persistence tests and verify they fail because broadcast tables are not registered yet**
- [ ] **Step 3: Add broadcast ORM models with unique constraints and indexes for `bot_uuid + connector_id` scoping**
- [ ] **Step 4: Add Alembic migration with guarded `upgrade()` / `downgrade()` for SQLite and PostgreSQL**
- [ ] **Step 5: Re-run the focused persistence tests and verify they pass**

### Task 2: Build repository contract with scoped CRUD

**Files:**
- Create: `C:/Users/33031/Desktop/bot/src/langbot/pkg/broadcast/repository.py`
- Create: `C:/Users/33031/Desktop/bot/tests/unit_tests/broadcast/test_repository.py`

- [ ] **Step 1: Write failing repository tests for scoped create/read/update/delete and sort order**
- [ ] **Step 2: Run `uv run pytest tests/unit_tests/broadcast/test_repository.py -q` and verify it fails**
- [ ] **Step 3: Implement repository methods that always query by `id + bot_uuid + connector_id` for updates/deletes and use one connection for write batches**
- [ ] **Step 4: Re-run the repository tests and verify they pass**

### Task 3: Build service rules and safe template engine

**Files:**
- Create: `C:/Users/33031/Desktop/bot/src/langbot/pkg/broadcast/errors.py`
- Create: `C:/Users/33031/Desktop/bot/src/langbot/pkg/broadcast/template_engine.py`
- Create: `C:/Users/33031/Desktop/bot/src/langbot/pkg/broadcast/schemas.py`
- Create: `C:/Users/33031/Desktop/bot/src/langbot/pkg/broadcast/service.py`
- Create: `C:/Users/33031/Desktop/bot/src/langbot/pkg/broadcast/__init__.py`
- Modify: `C:/Users/33031/Desktop/bot/src/langbot/pkg/core/app.py`
- Modify: `C:/Users/33031/Desktop/bot/src/langbot/pkg/core/stages/build_app.py`
- Create: `C:/Users/33031/Desktop/bot/tests/unit_tests/broadcast/test_service.py`

- [ ] **Step 1: Write failing service tests for scope validation hooks, template variable extraction/rendering, variable-profile validation, group-rule validation, and group-name dedupe**
- [ ] **Step 2: Run `uv run pytest tests/unit_tests/broadcast/test_service.py -q` and verify it fails**
- [ ] **Step 3: Implement explicit error codes, safe `{{variable}}` rendering, `template_id xor content` validation, regex validation, merge-mode validation, and single-transaction writes**
- [ ] **Step 4: Wire `broadcast_service` onto the application build chain**
- [ ] **Step 5: Re-run the service tests and verify they pass**

### Task 4: Expose HTTP API with centralized scope parsing

**Files:**
- Create: `C:/Users/33031/Desktop/bot/src/langbot/pkg/api/http/controller/groups/broadcast.py`
- Create: `C:/Users/33031/Desktop/bot/tests/unit_tests/broadcast/test_routes.py`
- Create: `C:/Users/33031/Desktop/bot/tests/integration/api/test_broadcast.py`

- [ ] **Step 1: Write failing route tests for centralized `validate_scope()`, GET/DELETE query scope, POST/PUT body scope, and error mapping**
- [ ] **Step 2: Run `uv run pytest tests/unit_tests/broadcast/test_routes.py -q` and verify it fails**
- [ ] **Step 3: Implement controller routes under `/api/v1/broadcast` that parse scope once and delegate to the service**
- [ ] **Step 4: Write failing API integration tests for CRUD, isolation, render validation, and empty variable-profile GET**
- [ ] **Step 5: Run `uv run pytest tests/integration/api/test_broadcast.py -q` and verify it fails**
- [ ] **Step 6: Fix controller/service integration until route and API tests pass**

### Task 5: Add frontend API types and client methods

**Files:**
- Modify: `C:/Users/33031/Desktop/bot/web/src/app/infra/entities/api/index.ts`
- Modify: `C:/Users/33031/Desktop/bot/web/src/app/infra/http/BackendClient.ts`
- Modify: `C:/Users/33031/Desktop/bot/web/src/app/home/broadcast/types.ts`
- Modify: `C:/Users/33031/Desktop/bot/web/src/app/home/broadcast/datasources/BroadcastDataSource.ts`

- [ ] **Step 1: Write the minimal failing TypeScript surface by referencing new broadcast API methods/types from the datasource**
- [ ] **Step 2: Run the broadcast Playwright spec or `pnpm build` to verify the frontend currently lacks those types/methods**
- [ ] **Step 3: Add broadcast API response/request types and `BackendClient` methods using the required scope placement rules**
- [ ] **Step 4: Refactor `BroadcastDataSource` so only Rules-tab data uses real API while import/drafts/logs remain Mock**
- [ ] **Step 5: Re-run frontend type/build verification and verify it passes**

### Task 6: Replace the three Rules sub-tabs only

**Files:**
- Modify: `C:/Users/33031/Desktop/bot/web/src/app/home/broadcast/components/BroadcastWorkspace.tsx`
- Modify: `C:/Users/33031/Desktop/bot/web/src/app/home/broadcast/components/rules/VariableMappingPanel.tsx`
- Modify: `C:/Users/33031/Desktop/bot/web/src/app/home/broadcast/components/rules/TemplatePanel.tsx`
- Modify: `C:/Users/33031/Desktop/bot/web/src/app/home/broadcast/components/rules/GroupMatchingPanel.tsx`

- [ ] **Step 1: Write/adjust failing UI assertions for loading, empty, save, delete-confirm, and error handling on the three Rules tabs**
- [ ] **Step 2: Run `pnpm exec playwright test tests/e2e/broadcast-workspace.spec.ts` and verify those expectations fail**
- [ ] **Step 3: Connect the three panels to real datasource calls while leaving import/review/log sections on existing mock flows**
- [ ] **Step 4: Add render-preview, inline validation feedback, toasts, and refresh-after-save behavior**
- [ ] **Step 5: Re-run the broadcast Playwright spec and verify it passes**

### Task 7: Full verification and manual persistence check

**Files:**
- Modify: `C:/Users/33031/Desktop/bot/web/tests/e2e/broadcast-workspace.spec.ts`

- [ ] **Step 1: Run `uv run pytest tests/unit_tests/broadcast -q`**
- [ ] **Step 2: Run `uv run pytest tests/integration/api/test_broadcast.py -q`**
- [ ] **Step 3: Run `uv run ruff check src/langbot/pkg/broadcast src/langbot/pkg/api/http/controller/groups/broadcast.py tests/unit_tests/broadcast tests/integration/api/test_broadcast.py`**
- [ ] **Step 4: Run `pnpm exec playwright test tests/e2e/broadcast-workspace.spec.ts` from `C:/Users/33031/Desktop/bot/web`**
- [ ] **Step 5: Run `pnpm build` from `C:/Users/33031/Desktop/bot/web`**
- [ ] **Step 6: Run `git diff --check`, `git diff --name-status`, and `git status --short` from `C:/Users/33031/Desktop/bot`**
- [ ] **Step 7: Perform manual browser verification for refresh persistence, bot/connector isolation, and absence of `/paste-draft`, `/send-draft`, and `/v1/tasks` calls**
