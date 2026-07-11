# Broadcast Workspace Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the LangBot broadcast workspace sidebar entry, route, Phase 1 UI skeleton, mock interactions, TypeScript contract types, and Playwright coverage without any backend or runtime integration.

**Architecture:** Implement a route-scoped frontend feature under `web/src/app/home/broadcast/` with small presentational components plus one in-memory datasource. Keep all state local to the page/workspace and expose mock mutations through typed helpers. Reuse current LangBot layout primitives, cards, tabs, buttons, Sonner, and TanStack Table.

**Tech Stack:** React 19, React Router, TypeScript, Tailwind CSS, Radix UI Tabs, lucide-react, TanStack Table, Sonner, Playwright

---

### Task 1: Add the failing end-to-end spec first

**Files:**
- Create: `C:/Users/33031/Desktop/bot/web/tests/e2e/broadcast-workspace.spec.ts`

- [ ] **Step 1: Write the failing test**
- [ ] **Step 2: Run `pnpm exec playwright test tests/e2e/broadcast-workspace.spec.ts` and verify it fails because the route/UI does not exist yet**

### Task 2: Add navigation and route entry

**Files:**
- Modify: `C:/Users/33031/Desktop/bot/web/src/app/home/components/home-sidebar/sidbarConfigList.tsx`
- Modify: `C:/Users/33031/Desktop/bot/web/src/app/home/layout.tsx`
- Modify: `C:/Users/33031/Desktop/bot/web/src/router.tsx`
- Modify: `C:/Users/33031/Desktop/bot/web/src/i18n/locales/en-US.ts`
- Modify: `C:/Users/33031/Desktop/bot/web/src/i18n/locales/zh-Hans.ts`
- Modify: `C:/Users/33031/Desktop/bot/web/src/i18n/locales/ja-JP.ts`

- [ ] **Step 1: Add sidebar metadata and translations for Broadcast**
- [ ] **Step 2: Add `/home/broadcast` route and document title fallback**

### Task 3: Build typed mock data and contracts

**Files:**
- Create: `C:/Users/33031/Desktop/bot/web/src/app/home/broadcast/types.ts`
- Create: `C:/Users/33031/Desktop/bot/web/src/app/home/broadcast/mockData.ts`
- Create: `C:/Users/33031/Desktop/bot/web/src/app/home/broadcast/datasources/BroadcastDataSource.ts`

- [ ] **Step 1: Define tabs, statuses, entity types, draft/log models, and paste-only contract types**
- [ ] **Step 2: Add seeded mock records for templates, variable mappings, group rules, import rows, drafts, and execution logs**
- [ ] **Step 3: Implement in-memory read/update helpers used by the workspace**

### Task 4: Build the page and split components

**Files:**
- Create: `C:/Users/33031/Desktop/bot/web/src/app/home/broadcast/page.tsx`
- Create: `C:/Users/33031/Desktop/bot/web/src/app/home/broadcast/components/BroadcastWorkspace.tsx`
- Create: `C:/Users/33031/Desktop/bot/web/src/app/home/broadcast/components/BroadcastHeader.tsx`
- Create: `C:/Users/33031/Desktop/bot/web/src/app/home/broadcast/components/BroadcastTabs.tsx`
- Create: `C:/Users/33031/Desktop/bot/web/src/app/home/broadcast/components/rules/VariableMappingPanel.tsx`
- Create: `C:/Users/33031/Desktop/bot/web/src/app/home/broadcast/components/rules/TemplatePanel.tsx`
- Create: `C:/Users/33031/Desktop/bot/web/src/app/home/broadcast/components/rules/GroupMatchingPanel.tsx`
- Create: `C:/Users/33031/Desktop/bot/web/src/app/home/broadcast/components/import/ImportMatchingPanel.tsx`
- Create: `C:/Users/33031/Desktop/bot/web/src/app/home/broadcast/components/drafts/DraftQueue.tsx`
- Create: `C:/Users/33031/Desktop/bot/web/src/app/home/broadcast/components/drafts/DraftDetail.tsx`
- Create: `C:/Users/33031/Desktop/bot/web/src/app/home/broadcast/components/logs/ExecutionLogPanel.tsx`

- [ ] **Step 1: Implement the top-level workspace shell and rules sub-tabs**
- [ ] **Step 2: Implement import preview, review queue/detail, and execution log panels**
- [ ] **Step 3: Wire mock search, filters, selection, editing, batch progress, and toast feedback**

### Task 5: Verify and harden

**Files:**
- Modify: `C:/Users/33031/Desktop/bot/web/tests/e2e/broadcast-workspace.spec.ts`

- [ ] **Step 1: Run the broadcast Playwright spec and fix any UI/test issues**
- [ ] **Step 2: Run `pnpm build`**
- [ ] **Step 3: Run `git diff --check`**
- [ ] **Step 4: Collect `git diff --stat` and `git status --short` for handoff**

**Note:** Do not commit in this phase because the user explicitly asked for no commit and no push.
