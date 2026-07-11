# Broadcast Workspace Design

**Goal**

Add a new first-level “Broadcast” workspace to the LangBot web app that mirrors the reference Notifications workspace information architecture and main UI patterns while staying fully frontend-only for Phase 1.

**Scope**

- Add a new sidebar entry under the Home section:
  - id: `broadcast`
  - route: `/home/broadcast`
  - icon: `Megaphone`
- Add a route and page entry for the broadcast workspace.
- Build the full page skeleton with four top-level tabs:
  - Rules
  - Import Matching
  - Review & Paste
  - Execution Logs
- Add three rule sub-tabs:
  - Variable Mapping
  - Message Templates
  - Group Matching
- Provide mock data, mock interactions, search/filter/selection, draft editing, batch progress UI, and execution log UI.
- Define TypeScript-only paste-only RPA contract types and interfaces for a later backend integration.

**Out of Scope**

- Database models, migrations, or persistence.
- Python backend APIs.
- Desktop Runtime calls.
- Real paste/send requests.
- Changes to existing bot session pages or existing RPA interfaces.

**Reference Adaptation**

Keep from the reference project:

- rules-first information architecture
- tabbed workspace
- multi-column review layout
- grouped draft queue
- batch toolbar and progress
- log panel

Do not port:

- Electron shell structure
- IPC wiring
- electron-store persistence
- dark/gradient styling
- large single-file component organization

**UI Shape**

- Use `HomeLayout` and current LangBot light theme.
- Compose the page from small feature components under `web/src/app/home/broadcast/`.
- Use Radix Tabs for primary and secondary tabs.
- Use cards for each major work area.
- Use TanStack Table for import preview and logs.
- Use Sonner for mock save/batch feedback.

**Data Model Direction**

Phase 1 keeps all state in a local mock datasource abstraction. The page owns:

- active tabs
- filters
- selected draft ids
- selected draft detail
- editable draft text
- mock batch progress state

The datasource returns stable in-memory arrays and exposes pure frontend mutation methods.

**RPA Contract**

Phase 1 defines a dedicated broadcast request contract that is intentionally decoupled from message history objects:

```ts
{
  botUuid: string
  connectorId: string
  broadcastDraftId: number
  conversationName: string
  draftText: string
  idempotencyKey: string
}
```

The later Python adapter may translate this into the existing runtime paste request:

```ts
{
  action: "paste_draft"
  conversationName: string
  draftText: string
  idempotencyKey: string
  requestDigest: string
}
```

The contract must not depend on:

- `message_id`
- `DatabaseMessage`
- `ReplyDraft`
- chat history

**Safety Model**

- Paste-only in this phase.
- No auto-send button.
- No send-draft call.
- No runtime invocation.
- UI may show paste preparation/progress only as mock state.

**Testing**

Add Playwright coverage for:

- sidebar visibility
- route navigation
- top-level tab switching
- sub-tab switching
- draft selection
- search/filter
- editing and saving a mock draft
- mock batch progress
- refresh reload behavior
