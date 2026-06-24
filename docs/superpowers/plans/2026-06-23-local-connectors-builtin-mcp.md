# Builtin Local Connectors Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add two fixed builtin Windows-only local connectors for WeChat and WXWork, expose one-click setup and worker lifecycle APIs, and keep LangBot MCP runtime in sync without affecting normal third-party MCP servers.

**Architecture:** LangBot gets a new `local_connectors` control plane that owns connector status, setup jobs, worker process state, and runtime bridging. `mcp_servers` remains the runtime connection registry, augmented with builtin metadata and protected server semantics. `wechat-decrypt` gains a non-interactive JSON CLI that LangBot orchestrates.

**Tech Stack:** Quart, SQLAlchemy, Alembic, asyncio task manager, Windows PowerShell process launch, React Router 7, Playwright, pytest.

---

### Task 1: Persist builtin MCP metadata and idempotent bootstrap

**Files:**
- Modify: `C:/Users/33031/Desktop/bot/src/langbot/pkg/entity/persistence/mcp.py`
- Create: `C:/Users/33031/Desktop/bot/src/langbot/pkg/persistence/alembic/versions/0007_builtin_local_connectors.py`
- Create: `C:/Users/33031/Desktop/bot/src/langbot/pkg/local_connectors/models.py`
- Create: `C:/Users/33031/Desktop/bot/src/langbot/pkg/local_connectors/repository.py`
- Create: `C:/Users/33031/Desktop/bot/src/langbot/pkg/local_connectors/service.py`
- Modify: `C:/Users/33031/Desktop/bot/src/langbot/pkg/core/stages/build_app.py`
- Test: `C:/Users/33031/Desktop/bot/tests/unit_tests/api/service/test_mcp_service.py`
- Test: `C:/Users/33031/Desktop/bot/tests/integration/persistence/test_migrations.py`

- [ ] Add `builtin`, `locked`, `managed_by`, `connector_id` to the MCP ORM model.
- [ ] Add Alembic migration guarded for SQLite/PostgreSQL and create a unique index on non-null `connector_id`.
- [ ] Introduce builtin connector definitions and a bootstrap path that claims or creates the fixed MCP rows after migrations complete.
- [ ] Cover idempotent bootstrap and no-duplicate takeover behavior in tests.

### Task 2: Protect builtin MCP rows at the backend service layer

**Files:**
- Modify: `C:/Users/33031/Desktop/bot/src/langbot/pkg/api/http/service/mcp.py`
- Modify: `C:/Users/33031/Desktop/bot/src/langbot/pkg/api/http/controller/groups/resources/mcp.py`
- Test: `C:/Users/33031/Desktop/bot/tests/unit_tests/api/service/test_mcp_service.py`
- Test: `C:/Users/33031/Desktop/bot/tests/integration/api/test_smoke.py`

- [ ] Enforce backend rules for builtin MCP rows: no delete, no rename, no URL change, no mode change, no builtin downgrade.
- [ ] Keep enable/disable allowed and preserve existing behavior for normal MCP servers.
- [ ] Surface stable error messages/codes the frontend can distinguish.

### Task 3: Add non-interactive connector CLI in `wechat-decrypt`

**Files:**
- Create: `C:/Users/33031/Desktop/wechat-decrypt/connector_cli.py`
- Create: `C:/Users/33031/Desktop/wechat-decrypt/connector_runtime.py`
- Create: `C:/Users/33031/Desktop/wechat-decrypt/connector_errors.py`
- Modify: `C:/Users/33031/Desktop/wechat-decrypt/requirements.txt`
- Modify: `C:/Users/33031/Desktop/wechat-decrypt/.gitignore`
- Test: `C:/Users/33031/Desktop/wechat-decrypt/tests/test_connector_cli.py`

- [ ] Build JSON-only commands for `wechat` and `wxwork`: `detect`, `extract-key`, `decrypt`.
- [ ] Reuse the current WeChat/WXWork code paths without changing the semantics of the existing 17 and 5 MCP tools.
- [ ] Resolve all paths absolutely, support Chinese/space paths, and keep secrets out of stdout/logs.
- [ ] Pin `mcp` dependency to `1.26.0` for this repo.

### Task 4: Add local connector domain model, state, and detection APIs

**Files:**
- Create: `C:/Users/33031/Desktop/bot/src/langbot/pkg/local_connectors/schemas.py`
- Create: `C:/Users/33031/Desktop/bot/src/langbot/pkg/local_connectors/jobs.py`
- Create: `C:/Users/33031/Desktop/bot/src/langbot/pkg/local_connectors/routes.py`
- Create: `C:/Users/33031/Desktop/bot/src/langbot/pkg/local_connectors/connectors/base.py`
- Create: `C:/Users/33031/Desktop/bot/src/langbot/pkg/local_connectors/connectors/wechat.py`
- Create: `C:/Users/33031/Desktop/bot/src/langbot/pkg/local_connectors/connectors/wxwork.py`
- Modify: `C:/Users/33031/Desktop/bot/src/langbot/pkg/api/http/controller/main.py`
- Test: `C:/Users/33031/Desktop/bot/tests/unit_tests/local_connectors/test_service.py`
- Test: `C:/Users/33031/Desktop/bot/tests/integration/api/test_local_connectors.py`

- [ ] Model connector definitions, status snapshots, persisted last result, job metadata, and unsupported-platform state.
- [ ] Add list/status/detect/job lookup/log APIs.
- [ ] Ensure non-Windows hosts return `unsupported_platform` but still show builtin cards.

### Task 5: Implement async setup jobs and UAC helper boundary

**Files:**
- Create: `C:/Users/33031/Desktop/bot/src/langbot/pkg/local_connectors/uac_helper.py`
- Modify: `C:/Users/33031/Desktop/bot/src/langbot/pkg/local_connectors/jobs.py`
- Modify: `C:/Users/33031/Desktop/bot/src/langbot/pkg/local_connectors/service.py`
- Test: `C:/Users/33031/Desktop/bot/tests/unit_tests/local_connectors/test_jobs.py`

- [ ] Run setup as a background job with persisted last-known status and stage.
- [ ] Restrict elevation to `extract-key` only, via result-file handoff and timeout/error handling.
- [ ] Implement `UAC_CANCELLED` and related stable connector error codes.

### Task 6: Implement process ownership and runtime bridge

**Files:**
- Create: `C:/Users/33031/Desktop/bot/src/langbot/pkg/local_connectors/process_manager.py`
- Create: `C:/Users/33031/Desktop/bot/src/langbot/pkg/local_connectors/runtime_bridge.py`
- Modify: `C:/Users/33031/Desktop/bot/src/langbot/pkg/api/http/service/mcp.py`
- Test: `C:/Users/33031/Desktop/bot/tests/unit_tests/local_connectors/test_process_manager.py`
- Test: `C:/Users/33031/Desktop/bot/tests/unit_tests/local_connectors/test_runtime_bridge.py`

- [ ] Manage only workers started by LangBot and validate PID plus process creation time plus command identity.
- [ ] Return `PORT_IN_USE` when ports `5680` or `5681` are held by unknown processes.
- [ ] On setup success, enable the builtin MCP and refresh/start the formal runtime session, then capture tool count.

### Task 7: Add frontend builtin MCP presentation and control surface

**Files:**
- Modify: `C:/Users/33031/Desktop/bot/web/src/app/infra/entities/api/index.ts`
- Modify: `C:/Users/33031/Desktop/bot/web/src/app/infra/http/BackendClient.ts`
- Modify: `C:/Users/33031/Desktop/bot/web/src/app/home/plugins/components/plugin-installed/PluginInstalledComponent.tsx`
- Modify: `C:/Users/33031/Desktop/bot/web/src/app/home/plugins/components/plugin-installed/ExtensionCardComponent.tsx`
- Modify: `C:/Users/33031/Desktop/bot/web/src/app/home/mcp/MCPDetailContent.tsx`
- Create: `C:/Users/33031/Desktop/bot/web/src/app/home/mcp/BuiltinConnectorDetail.tsx`
- Modify: `C:/Users/33031/Desktop/bot/web/tests/e2e/crud-smoke.spec.ts`
- Modify: `C:/Users/33031/Desktop/bot/web/tests/e2e/fixtures/langbot-api.ts`
- Modify: `C:/Users/33031/Desktop/bot/web/src/i18n/locales/en-US.ts`
- Modify: `C:/Users/33031/Desktop/bot/web/src/i18n/locales/zh-Hans.ts`
- Modify: `C:/Users/33031/Desktop/bot/web/src/i18n/locales/ja-JP.ts`

- [ ] Show fixed builtin cards inside the existing MCP installed page.
- [ ] Switch the detail page into a connector-specific view when `builtin + connector_id` is present.
- [ ] Hide URL/mode/delete controls for builtin MCP and add setup/progress/log/start/stop/reconfigure actions.

### Task 8: Verification and acceptance

**Files:**
- Modify as needed: targeted tests only

- [ ] Run backend unit/integration tests for migration, MCP protection, connector service, jobs, and process manager.
- [ ] Run `wechat-decrypt` pytest plus CLI smoke commands.
- [ ] Run frontend e2e/build commands available in the repo.
- [ ] Attempt real Windows acceptance for WXWork and WeChat one-click setup on this machine, and report any blocker precisely.
