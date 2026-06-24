# Database Mode SSE Realtime Update Design

## Goal

Implement realtime auto-refresh for `/home/database-mode` using Server-Sent Events (SSE) for change notification and the existing REST APIs for full data retrieval. The page should update automatically when WeCom database messages are ingested or modified, without requiring users to click the refresh button.

## Scope

This design applies only to the `C:\Users\33031\Desktop\bot` repository.

In scope:

- Add an application-scoped `DatabaseModeEventBus`
- Add authenticated SSE session handshake and SSE stream routes
- Publish database-mode change events only after successful business commits
- Add frontend SSE subscription and reconnect handling
- Add debounced REST refresh orchestration on the database-mode page
- Protect unsaved local draft edits during realtime refresh
- Preserve scroll position behavior and add restrained new-message notifications
- Add backend unit tests and frontend E2E coverage for realtime behavior
- Fix database-mode refresh label, status display, and time formatting issues
- Support only a single backend process / single worker deployment for this in-process EventBus design

Out of scope:

- Changes to `wechat-decrypt`
- Changes to DB/WAL monitor algorithms
- Multi-process or multi-worker event fan-out
- WebSocket support
- Sending full message bodies through SSE
- Connector detail page SSE adoption
- Changes to the existing five WeCom MCP tools
- Real message sending, auto-reply, or RobotGo work

## Requirements Summary

1. SSE only carries invalidation/change hints, never full messages or full conversations.
2. REST remains the source of truth for all rendered data.
3. The SSE channel must be authenticated without query tokens or frontend-readable cookies.
4. SSE failures must never affect successful database writes.
5. The frontend must coalesce bursts of events into controlled refreshes.
6. Unsaved draft text must not be overwritten by background refreshes.
7. When SSE is unavailable, the page must fall back to 15-second low-frequency polling only while visible.
8. Events may be published only after `commit()` succeeds or a transaction context exits normally; rollback or commit failure publishes nothing.
9. SSE does not support replay and does not depend on `Last-Event-ID`; every successful connect or reconnect must trigger `refreshAll()`.
10. Backend timestamps returned to the frontend must remain offset-aware ISO 8601 strings; the frontend converts them to local display time.

## Current State

### Backend

`DatabaseModeService` currently provides:

- message ingestion from the internal WeCom monitor event path
- conversation and message listing
- draft generation and saving
- process, skip, delete, and batch operations

There is no event bus, no SSE route, and no post-commit invalidation mechanism.

### Frontend

`web/src/app/home/database-mode/page.tsx` currently:

- fetches connector status, conversation list, and message list through REST
- depends on manual `refreshSelection()` calls after user actions
- polls connector monitor state every 5 seconds
- stores local draft edits, but does not merge them against background refreshes
- renders raw timestamps from API payloads directly

There is no SSE hook, no reconnect logic, and no refresh orchestration for bursty updates.

### Authentication Constraint

The existing Web UI uses Bearer tokens attached by Axios request interceptors. Browser `EventSource` cannot attach custom `Authorization` headers, so the SSE path needs a dedicated authenticated handshake that issues a short-lived SSE-only cookie.

## Architecture

### High-Level Flow

```text
WXWork monitor internal event
-> DatabaseModeService writes database state
-> successful commit
-> DatabaseModeEventBus publishes minimal change event
-> GET /api/v1/database-mode/events SSE stream emits notification
-> useDatabaseModeEvents receives event
-> page schedules debounced REST refresh
-> UI updates from REST responses
```

### Backend Units

#### `src/langbot/pkg/database_mode/events.py`

Add a focused module containing:

- `DatabaseModeEventType`
- `DatabaseModeEvent`
- `DatabaseModeSubscriber`
- `DatabaseModeEventBus`
- SSE payload serialization helpers

Responsibilities:

- maintain in-process subscribers
- isolate SSE fan-out mechanics from business logic
- enforce bounded per-subscriber queues
- support cleanup on disconnect and app shutdown

#### `DatabaseModeService`

Continue owning all database-mode business writes and reads.

New responsibility:

- publish minimal invalidation events after successful commits

It must not:

- manage subscriber lifetime directly
- embed HTTP/SSE transport concerns

#### `database_mode` router group

Continue hosting database-mode REST endpoints.

New responsibilities:

- `POST /api/v1/database-mode/events/session`
- `GET /api/v1/database-mode/events`
- SSE-only cookie issuance and validation
- stream assembly with ready event, heartbeat comments, disabled compression, and no replay semantics

### Frontend Units

#### `useDatabaseModeEvents`

New hook under `web/src/app/home/database-mode/hooks/` or the local page directory.

Responsibilities:

- call the SSE session handshake endpoint
- create and own a single `EventSource`
- expose `connectionState` and `reconnectCount`
- notify the page about open/error/message events
- back off reconnect attempts to avoid tight failure loops
- cleanly close connections during unmount and StrictMode remounts

#### `page.tsx`

Continue owning rendered database-mode UI and user actions.

New responsibilities:

- split loading into stable refresh functions
- merge SSE-derived invalidation intents
- debounce refreshes
- preserve unsaved drafts during refreshes
- preserve scroll position unless the user is near the bottom
- start fallback polling only while SSE is disconnected and the page is visible

#### Shared formatting helper

Add a small date/time formatter for database-mode timestamps so the page stops rendering raw ISO strings and consistently shows user-local `YYYY-MM-DD HH:mm:ss` or `--`.

## Backend Design

### Event Model

Supported event types:

- `database-message-created`
- `database-message-updated`
- `database-message-deleted`
- `database-conversation-updated`
- `database-mode-invalidated`
- `ready` for the initial stream bootstrap

Publication rules:

- `database-message-created` is the only primary event for new-message writes
- `database-message-updated` is the only primary event for message updates
- `database-message-deleted` is the only primary event for deletes
- `database-mode-invalidated` is the only primary event for batch operations and overflow coalescing
- `database-conversation-updated` is reserved for independent conversation metadata changes and must not be emitted alongside the message create/update/delete events above

Business event payloads include only minimal identifiers:

```json
{
  "type": "database-message-created",
  "conversation_id": 123,
  "message_id": 456,
  "event_id": "wxwork-local:hash",
  "occurred_at": "2026-06-24T10:00:00+08:00"
}
```

Forbidden fields:

- message body
- draft body
- contact detail blobs
- database path
- connector token
- bearer token
- internal keys or raw database record dumps

### EventBus Behavior

`DatabaseModeEventBus` is application-scoped and created during `BuildAppStage`.

Behavior:

- each subscriber gets its own `asyncio.Queue(maxsize=100)`
- the bus is valid only inside one backend process / one worker; cross-process fan-out is explicitly unsupported in this iteration
- `publish()` iterates over a snapshot of subscribers
- publish failures are isolated per subscriber
- queue overflow must not block publishers or grow memory unbounded
- queue overflow must coalesce pending work for that subscriber into exactly one `database-mode-invalidated` event so the frontend eventually runs `refreshAll()`
- overflow handling must not silently discard the refresh signal; it may replace queued fine-grained events with the invalidation fallback to stay within bounds
- disconnects remove the subscriber immediately
- subscriber shutdown uses a sentinel item to stop stream loops cleanly
- app shutdown pushes the sentinel to subscribers and then clears all subscribers
- SSE history is not persisted, replay is unsupported, and incoming `Last-Event-ID` must be ignored

This system is intentionally ephemeral. It does not persist SSE history or guarantee exact once delivery. The design relies on REST refresh to converge state.

### Post-Commit Publish Rules

Global rule:

- publish only after `session.commit()` succeeds, or after a transaction context exits normally and the commit has succeeded
- if the write path rolls back, raises before commit, or raises during commit, publish nothing
- publish happens after the business result is durably committed, never before

#### New message ingest

`ingest_internal_event` publishes after successful inserts/updates complete and the commit succeeds:

- `database-message-created`

If `event_id` already exists or `message_key` is duplicate:

- mark the ingest result as duplicate as today
- do not publish `database-message-created`

#### Message updates

After successful completion of:

- `generate_draft`
- `update_draft`
- `process_message`
- `skip_message`

publish:

- `database-message-updated`

#### Deletes

After successful `delete_message`:

- `database-message-deleted`

#### Batch operations

After successful completion of:

- `batch_process`
- `batch_skip`
- `batch_delete`

publish only:

- `database-mode-invalidated`

This keeps bursty bulk actions from emitting many fine-grained events that would only be coalesced immediately by the frontend.

#### Conversation metadata-only updates

If a future or existing business action changes conversation metadata without being a message create/update/delete action, it may publish only:

- `database-conversation-updated`

### SSE Authentication

#### Handshake route

Add:

- `POST /api/v1/database-mode/events/session`

Authentication:

- use existing `USER_TOKEN` Bearer validation

Behavior:

- validate the authenticated user
- issue a short-lived SSE-only signed cookie
- return `204 No Content` with no token material in the body
- set `Cache-Control: no-store`

Cookie rules:

- fixed cookie name: `langbot_dbmode_sse`
- `HttpOnly`
- `SameSite=Strict`, with `Lax` only if existing login compatibility forces it
- `Path=/api/v1/database-mode/events`
- `Max-Age` between 5 and 10 minutes
- `Secure=True` only when the current environment is HTTPS
- do not set `Domain`
- no database persistence
- no Bearer token copy
- sign with HMAC-SHA256 or reuse an existing app signing utility with equivalent guarantees
- do not hardcode the signing secret; source it from existing config/app secret management

Cookie contents:

- signed claims must include `version`, `purpose`, `issued_at`, `expires_at`, and `session_id`
- `purpose` must be specific to database-mode SSE usage
- authenticated user identity may be included as a subject or equivalent server-validated claim
- signature must be verified server-side on every stream connect

If the cookie expires while an SSE stream is already established, the open stream may continue. Reconnects must perform a fresh handshake before recreating `EventSource`.

#### Stream route

Add:

- `GET /api/v1/database-mode/events`

Authentication:

- validate only the dedicated SSE cookie
- do not accept query tokens
- do not accept connector tokens
- do not use `Last-Event-ID` for replay or resume

Response headers:

- `Content-Type: text/event-stream`
- `Cache-Control: no-store`
- `Connection: keep-alive`
- `X-Accel-Buffering: no`
- disable SSE response compression

Initial stream output:

```text
retry: 3000

event: ready
data: {"type":"ready"}

```

Heartbeat:

- every 20 seconds emit `: heartbeat`
- heartbeat contains no business payload

Disconnect cleanup:

- remove the subscriber from the event bus
- stop the generator loop cleanly

## Frontend Design

### Connection Lifecycle

The page initializes database-mode data as it does today, then prepares SSE:

1. call `POST /api/v1/database-mode/events/session`
2. create `new EventSource('/api/v1/database-mode/events')`
3. on `open` or `ready`, trigger `refreshAll()`
4. on `error`, mark `disconnected`, close the broken source, and schedule reconnect with backoff
5. on reconnect success, stop fallback business polling and immediately run `refreshAll()` again

Reconnect handling:

- limited retry frequency
- progressive backoff
- re-run session handshake before every reconnect attempt
- no token exposure in URL, logs, or frontend-readable cookie storage
- do not depend on `Last-Event-ID` because replay is unsupported

### Page Refresh Functions

Refactor `page.tsx` around stable functions:

- `refreshConversations()`
- `refreshCurrentConversation()`
- `refreshCurrentMessages()`
- `refreshAll()`

Each function updates only the state it owns and respects request versioning to avoid stale responses overwriting newer state.

### Event-to-Refresh Mapping

`database-message-created`

- refresh conversations
- refresh current conversation stats
- refresh current messages only if the event targets the selected conversation

`database-message-updated`

- refresh current messages
- refresh current conversation stats
- refresh conversation list aggregates

`database-message-deleted`

- refresh current messages
- refresh current conversation stats
- refresh conversation list

`database-conversation-updated`

- use only for standalone conversation metadata changes
- refresh conversations
- refresh current conversation stats if it is selected

`database-mode-invalidated`

- trigger one `refreshAll()`

### Debounce and Concurrency

The page must not launch uncontrolled duplicate requests for every SSE notification.

Design:

- accumulate refresh intents in a pending set
- debounce execution within 150 to 300ms
- allow only one refresh batch at a time
- if more events arrive while a batch is in flight, mark a pending rerun and execute one follow-up batch after completion

Stale result protection:

- every refresh batch gets a monotonically increasing request version
- every request also carries a `querySignature`
- `querySignature` must cover selected conversation, filters, search terms, and pagination inputs
- only the latest version may commit state updates
- responses may update state only when both `requestVersion` and `querySignature` still match the active view state
- if practical with existing HTTP utilities, requests may also be cancelled

### Draft Preservation

Maintain a dirty-state structure keyed by `message.id`.

When background refresh returns messages:

- non-dirty messages fully adopt server data
- dirty messages retain local `draft_text`
- other fields on dirty messages still update from the server

When save succeeds:

- clear dirty flag
- replace the local draft with server-confirmed data

Realtime refresh must not:

- clear the current text area
- change the selected message
- reset scroll position

### Scroll Behavior and Notification

Track whether the user is already near the bottom of the message list.

If a selected conversation receives new messages and the user is near the bottom:

- auto-scroll to the newest message after refresh

If the user is reviewing older messages:

- preserve the scroll position
- show a restrained `sonner` toast like `Received 1 new WeCom message`

Multiple messages arriving in quick succession must merge into a single notification instead of producing one toast per message.

### Fallback Polling

While `connectionState === 'connected'`:

- do not run database-mode business polling
- continue the existing connector monitor status polling if it remains useful to the page

While `connectionState === 'disconnected'`:

- poll conversation/current message data every 15 seconds
- only while the database-mode page is mounted
- pause polling when `document.visibilityState !== 'visible'`
- on visibility regain, immediately run `refreshAll()`
- stop polling as soon as SSE reconnects successfully

The existing manual refresh button remains available.

## i18n and Display Fixes

### Refresh label

The database-mode page must not show the raw key `common.refresh`.

Use an existing resolved translation if available; otherwise add a dedicated key whose values are:

- `zh-Hans`: `刷新`
- `en-US`: `Refresh`
- `ja-JP`: `更新`

### Status labels

Statuses must always render through i18n keys, not raw enum strings:

- pending
- processing
- draft_ready
- failed
- processed
- skipped

### Time formatting

Backend contract:

- database-mode REST responses keep returning offset-aware ISO 8601 timestamps
- the backend must not pre-localize timestamps into server-local display strings

Frontend contract:

- database-mode timestamps must use a shared formatter
- the formatter renders user-local `YYYY-MM-DD HH:mm:ss`
- the formatter renders `--` when the source value is empty or invalid

The formatter should be reused in all database-mode timestamp locations, including message cards and details dialog.

## Error Handling

### Backend

- publish failures log warnings/debug and do not affect business success
- invalid or expired SSE cookie rejects the stream request
- handshake failure leaves the page in reconnect/backoff mode

### Frontend

- failed handshake schedules a bounded retry
- failed SSE stream closes the old source before retrying
- reconnect attempts are backoff-driven to avoid hot loops
- REST refresh failures surface as page/toast errors without breaking the connection manager

## Testing Strategy

### Backend Unit Tests

Add or extend tests under:

- `tests/unit_tests/database_mode/`
- `tests/unit_tests/api/`

Cover:

1. EventBus subscribe/publish/unsubscribe behavior
2. two subscribers receiving the same event
3. bounded queue behavior for slow clients
4. queue overflow coalescing to one `database-mode-invalidated` event instead of losing the eventual refresh signal
5. subscriber sentinel shutdown path
6. no publish on rollback or commit failure
7. stream ignores `Last-Event-ID`
8. handshake returns `204` and `Cache-Control: no-store`
9. SSE cookie uses the fixed name and required signed claims
10. stream response content type and required headers
11. initial `ready` event
12. heartbeat output
13. unauthenticated handshake/stream rejection
14. successful post-commit created event after ingest
15. duplicate ingest not republishing created
16. draft save publishing updated
17. process and skip publishing updated
18. delete publishing deleted
19. batch actions publishing invalidated
20. publish exceptions not affecting committed database updates
21. payload excluding sensitive fields

### Frontend E2E

Extend Playwright coverage under:

- `web/tests/e2e/home-smoke.spec.ts`
- or a dedicated `web/tests/e2e/database-mode-realtime.spec.ts`

Mock:

- SSE handshake endpoint
- database-mode REST endpoints
- browser `EventSource`

Cover:

1. handshake before stream creation
2. page mount creates exactly one active EventSource
3. created event triggers automatic REST refresh
4. debounced coalescing of burst events
5. disconnected state starting 15-second polling
6. reconnect stopping polling
7. visibility regain triggering immediate refresh
8. unsaved draft preservation
9. cleanup on unmount
10. fixed refresh label
11. translated statuses including `processing`
12. local time formatting instead of raw ISO
13. reconnect success forcing `refreshAll()`
14. stale-response protection using `requestVersion + querySignature`

### Manual Verification

Manual verification remains required against the real local WeCom flow:

- open `/home/database-mode`
- send new WeCom messages from another account
- confirm automatic list/stats/message updates
- confirm no full page refresh or flicker
- confirm dirty draft preservation
- confirm disconnect fallback and reconnect resync

This manual step is user-executed and must not be claimed as passed without real execution.

## Risks and Mitigations

### Risk: SSE authentication mismatch with current token-only UI

Mitigation:

- explicit handshake route using existing Bearer auth
- short-lived SSE-only cookie scoped narrowly to the event endpoint

### Risk: event bursts causing repeated REST storms

Mitigation:

- debounced intent coalescing
- single in-flight refresh batch
- rerun-once flag after in-flight refresh completes

### Risk: background refresh overwriting in-progress operator work

Mitigation:

- dirty draft tracking
- per-message merge behavior instead of full blind replacement

### Risk: slow or abandoned SSE clients growing memory

Mitigation:

- bounded queue per subscriber
- overflow coalescing to `database-mode-invalidated`
- unsubscribe on disconnect
- clear all subscribers on shutdown

### Risk: this design does not fan out across multiple workers

Mitigation:

- explicitly constrain this iteration to one backend process / one worker deployment
- defer cross-process broadcast infrastructure to a later design if multi-worker deployment becomes required

## Files Expected To Change

Backend:

- `src/langbot/pkg/database_mode/events.py`
- `src/langbot/pkg/database_mode/service.py`
- `src/langbot/pkg/core/app.py`
- `src/langbot/pkg/core/stages/build_app.py`
- `src/langbot/pkg/api/http/controller/groups/database_mode.py`

Frontend:

- `web/src/app/home/database-mode/page.tsx`
- `web/src/app/home/database-mode/hooks/useDatabaseModeEvents.ts` or equivalent
- `web/src/app/infra/http/BackendClient.ts`
- `web/src/app/infra/entities/api/index.ts`
- shared database-mode formatting helper if added
- `web/src/i18n/locales/en-US.ts`
- `web/src/i18n/locales/zh-Hans.ts`
- `web/src/i18n/locales/ja-JP.ts`

Tests:

- `tests/unit_tests/database_mode/test_database_mode_service.py`
- new backend tests for event bus and SSE controller behavior
- `web/tests/e2e/home-smoke.spec.ts` and/or dedicated realtime spec
- `web/tests/e2e/fixtures/langbot-api.ts`

## Non-Goals and Guardrails

- no WebSocket fallback
- no query-token authentication
- no token values in URLs or logs
- no full message content in SSE payloads
- no changes to WeCom monitor ingestion algorithms
- no repository-wide SSE abstraction work beyond database mode

## Implementation Readiness

The design is intentionally narrow:

- reuse the existing database-mode REST surface
- add one focused event bus
- add one focused authentication handshake
- add one frontend subscription hook
- keep all realtime state convergence REST-based

That makes the work suitable for a single implementation plan without needing to split it into separate sub-projects.
