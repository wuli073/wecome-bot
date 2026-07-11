# Broadcast Usability Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix broadcast workspace scrolling, Chinese user-facing copy, variable-mapping usability, and clear backend validation messages without changing runtime, database schema, or non-broadcast feature scope.

**Architecture:** Keep the fix set scoped to `web/src/app/home/broadcast/**` first, only touching `web/src/app/home/layout.tsx` if the Broadcast page cannot own scroll safely by itself. Preserve internal API/database/TypeScript enums in English while adding display-label mapping and frontend validation. Keep backend error codes stable and add explicit Chinese `message/details` so the frontend can surface actionable errors.

**Tech Stack:** React 19, TypeScript, Vite, Playwright, Quart, Python 3.11+, pytest, Ruff

---

### Task 1: Rewrite the broadcast E2E spec to express the new usability contract

**Files:**
- Modify: `C:/Users/33031/Desktop/bot/web/tests/e2e/broadcast-workspace.spec.ts`
- Modify: `C:/Users/33031/Desktop/bot/web/tests/e2e/fixtures/langbot-api.ts`

- [ ] **Step 1: Write the failing Playwright expectations for Chinese UI, scroll reachability, enum display mapping, row deletion, validation messaging, and forbidden runtime calls**
- [ ] **Step 2: Run `pnpm exec playwright test tests/e2e/broadcast-workspace.spec.ts` from `C:/Users/33031/Desktop/bot/web` and verify it fails for the expected reasons**

### Task 2: Add failing backend tests for explicit broadcast validation messages

**Files:**
- Modify: `C:/Users/33031/Desktop/bot/tests/integration/api/test_broadcast.py`
- Modify: `C:/Users/33031/Desktop/bot/tests/unit_tests/broadcast/test_service.py`
- Modify: `C:/Users/33031/Desktop/bot/tests/unit_tests/broadcast/test_routes.py`

- [ ] **Step 1: Write failing tests for empty `group_field`, half-empty mapping rows, duplicate `variable_key`, braces in labels, and Chinese `message/details` while preserving the original error code**
- [ ] **Step 2: Run `uv run pytest tests/unit_tests/broadcast/test_service.py tests/unit_tests/broadcast/test_routes.py tests/integration/api/test_broadcast.py -q` and verify it fails for the new assertions**

### Task 3: Fix broadcast page scrolling with broadcast-local containers first

**Files:**
- Modify: `C:/Users/33031/Desktop/bot/web/src/app/home/broadcast/components/BroadcastWorkspace.tsx`
- Modify: `C:/Users/33031/Desktop/bot/web/src/app/home/broadcast/components/BroadcastTabs.tsx`
- Modify: `C:/Users/33031/Desktop/bot/web/src/app/home/broadcast/components/rules/VariableMappingPanel.tsx`
- Modify: `C:/Users/33031/Desktop/bot/web/src/app/home/broadcast/components/rules/TemplatePanel.tsx`
- Modify: `C:/Users/33031/Desktop/bot/web/src/app/home/broadcast/components/rules/GroupMatchingPanel.tsx`
- Modify: `C:/Users/33031/Desktop/bot/web/src/app/home/broadcast/components/import/ImportMatchingPanel.tsx`
- Modify: `C:/Users/33031/Desktop/bot/web/src/app/home/broadcast/components/drafts/DraftQueue.tsx`
- Modify: `C:/Users/33031/Desktop/bot/web/src/app/home/broadcast/components/drafts/DraftDetail.tsx`
- Modify: `C:/Users/33031/Desktop/bot/web/src/app/home/broadcast/components/logs/ExecutionLogPanel.tsx`
- Modify if strictly necessary: `C:/Users/33031/Desktop/bot/web/src/app/home/layout.tsx`

- [ ] **Step 1: Make the Broadcast route own a stable vertical scroll container that can reach the page bottom across all four top tabs and all three rule subtabs without changing runtime behavior**
- [ ] **Step 2: Re-run `pnpm exec playwright test tests/e2e/broadcast-workspace.spec.ts` and verify the scroll assertions now pass before moving on**

### Task 4: Localize user-visible broadcast content and hide internal terms

**Files:**
- Modify: `C:/Users/33031/Desktop/bot/web/src/app/home/broadcast/components/BroadcastHeader.tsx`
- Modify: `C:/Users/33031/Desktop/bot/web/src/app/home/broadcast/components/BroadcastWorkspace.tsx`
- Modify: `C:/Users/33031/Desktop/bot/web/src/app/home/broadcast/components/rules/VariableMappingPanel.tsx`
- Modify: `C:/Users/33031/Desktop/bot/web/src/app/home/broadcast/components/rules/TemplatePanel.tsx`
- Modify: `C:/Users/33031/Desktop/bot/web/src/app/home/broadcast/components/rules/GroupMatchingPanel.tsx`
- Modify: `C:/Users/33031/Desktop/bot/web/src/app/home/broadcast/components/import/ImportMatchingPanel.tsx`
- Modify: `C:/Users/33031/Desktop/bot/web/src/app/home/broadcast/components/drafts/DraftQueue.tsx`
- Modify: `C:/Users/33031/Desktop/bot/web/src/app/home/broadcast/components/drafts/DraftDetail.tsx`
- Modify: `C:/Users/33031/Desktop/bot/web/src/app/home/broadcast/components/logs/ExecutionLogPanel.tsx`
- Modify: `C:/Users/33031/Desktop/bot/web/src/app/home/broadcast/mockData.ts`
- Modify: `C:/Users/33031/Desktop/bot/web/src/app/home/broadcast/utils.ts`
- Modify: `C:/Users/33031/Desktop/bot/web/src/i18n/locales/zh-Hans.ts`
- Modify if needed for route/sidebar label parity only: `C:/Users/33031/Desktop/bot/web/src/i18n/locales/en-US.ts`, `C:/Users/33031/Desktop/bot/web/src/i18n/locales/ja-JP.ts`

- [ ] **Step 1: Add display-label mapping for merge modes, group-match types, and statuses while preserving submitted enum values**
- [ ] **Step 2: Replace visible English/technical copy in the broadcast module with Chinese business-language labels, descriptions, buttons, sample data, and statuses only**
- [ ] **Step 3: Move any remaining technical JSON preview behind a default-collapsed ???????? section**
- [ ] **Step 4: Re-run `pnpm exec playwright test tests/e2e/broadcast-workspace.spec.ts` and verify the Chinese UI and hidden-term assertions pass**

### Task 5: Implement variable-mapping deletion, filtering, validation, and frontend error rendering

**Files:**
- Modify: `C:/Users/33031/Desktop/bot/web/src/app/home/broadcast/components/rules/VariableMappingPanel.tsx`
- Modify: `C:/Users/33031/Desktop/bot/web/src/app/home/broadcast/components/BroadcastWorkspace.tsx`
- Modify: `C:/Users/33031/Desktop/bot/web/src/app/home/broadcast/datasources/BroadcastDataSource.ts`
- Modify: `C:/Users/33031/Desktop/bot/web/src/app/home/broadcast/utils.ts`
- Modify: `C:/Users/33031/Desktop/bot/web/src/app/home/broadcast/types.ts`

- [ ] **Step 1: Add per-row delete actions and automatic `order` reindexing after deletion**
- [ ] **Step 2: Filter fully blank rows before save, but block save on half-empty rows with row-specific Chinese messages**
- [ ] **Step 3: Block duplicate variable keys, brace-decorated labels such as `{{????}}`, empty group field, invalid merge mode, invalid order, and empty resulting rule set with actionable Chinese messages**
- [ ] **Step 4: Prevent `{{}}` generation by excluding empty variable keys from the variable pool and preview helpers**
- [ ] **Step 5: Re-run `pnpm exec playwright test tests/e2e/broadcast-workspace.spec.ts` and verify the row deletion and validation assertions pass**

### Task 6: Add backend Chinese validation messages while preserving existing error codes

**Files:**
- Modify: `C:/Users/33031/Desktop/bot/src/langbot/pkg/broadcast/errors.py`
- Modify: `C:/Users/33031/Desktop/bot/src/langbot/pkg/broadcast/service.py`
- Modify: `C:/Users/33031/Desktop/bot/src/langbot/pkg/api/http/controller/groups/broadcast.py`

- [ ] **Step 1: Keep broadcast error codes unchanged and attach explicit Chinese `message` plus field-level or row-level `details` for invalid variable profiles**
- [ ] **Step 2: Ensure the controller returns those messages/details to the frontend while still exposing the internal code for non-UI handling**
- [ ] **Step 3: Run `uv run pytest tests/unit_tests/broadcast/test_service.py tests/unit_tests/broadcast/test_routes.py tests/integration/api/test_broadcast.py -q` and verify the backend validation tests pass**

### Task 7: Full verification and diff hygiene

**Files:**
- Verify only: `C:/Users/33031/Desktop/bot`

- [ ] **Step 1: Run `pnpm exec playwright test tests/e2e/broadcast-workspace.spec.ts` from `C:/Users/33031/Desktop/bot/web`**
- [ ] **Step 2: Run `pnpm build` from `C:/Users/33031/Desktop/bot/web`**
- [ ] **Step 3: Run `uv run pytest tests/unit_tests/broadcast -q` from `C:/Users/33031/Desktop/bot`**
- [ ] **Step 4: Run `uv run pytest tests/integration/api/test_broadcast.py -q` from `C:/Users/33031/Desktop/bot`**
- [ ] **Step 5: Run `uv run ruff check src/langbot/pkg/broadcast src/langbot/pkg/api/http/controller/groups/broadcast.py tests/unit_tests/broadcast tests/integration/api/test_broadcast.py` from `C:/Users/33031/Desktop/bot`**
- [ ] **Step 6: Run `git diff --check` from `C:/Users/33031/Desktop/bot`**
- [ ] **Step 7: Run browser-based acceptance to confirm top-to-bottom scrolling, Chinese UI coverage, save-refresh persistence, precise errors, and absence of runtime / paste-draft / send-draft calls**
