# WXWork Paste-Only Keyboard State Machine Design

## 1. Background and Goals

LangBot currently includes a wxwork desktop automation path that depends on a calibration system built around overlay-assisted region selection, persisted region profiles, and coordinate-based or visual verification behavior. This design replaces that architecture for the `paste_only` / `paste-draft` mainline with a single pure-keyboard path and removes the calibration system from production code.

The new `paste_only` flow must follow exactly one fixed sequence:

```text
snapshot clipboard
→ activate WXWork main window
→ Ctrl+F x1
→ wait 400ms
→ paste conversationName x1
→ wait 400ms
→ Enter x1
→ wait 1000ms
→ paste draftText x1
→ restore clipboard
→ finish
```

The final successful result must remain:

```text
status=succeeded
stage=pasted_to_input
messageSent=false
sendKeyCount=0
```

This design intentionally does not add OCR, VLM, UI Automation, coordinate clicks, keyboard fallback branches, automatic retries, or context-confirmation token flows.

## 2. Explicit Removal Scope

### 2.1 Frontend

Remove the following from production UI and tests:

- calibration entry buttons such as start/restart calibration
- persisted calibration status displays
- calibration in-progress state
- calibration error hints
- `region_profile_configured` gating logic
- runtime calibration status UI
- calibration API calls
- related i18n strings
- related E2E assertions

The page must only keep the manual confirmation dialog and a single `paste-draft` request.

### 2.2 Python backend

Remove the following from production code and tests:

- calibration routes
- calibration service methods
- calibration repository methods
- RegionProfileV2 validation and persistence logic
- `region_profile_configured` response field
- `CALIBRATION_REQUIRED` error code
- profile / window binding / calibration session request assembly and propagation used by `paste-draft` or calibration-only paths

The `paste-draft` path must not read or depend on:

```text
channel_metadata.desktop_automation.region_profile_v2
profile
windowBinding
windowKey
profileDigest
```

This hard deletion applies to the `paste-draft` / `paste_only` mainline and to calibration-only code. If non-refactored actions such as `send`, `diagnose`, `history-search`, or `quote-reply` still genuinely depend on shared `windowBinding` or `windowKey` infrastructure, that shared capability may remain for those actions only and must be listed in the final implementation report with its caller and reason.

### 2.3 Runtime

Remove calibration-only and overlay-only code, including:

- overlay renderer page and assets
- overlay BrowserWindow and session flow
- overlay wizard IPC or preload exposure
- calibration HTTP routes
- calibration task/session types
- RegionProfileV2 types and validators
- profile digest handling
- region-coordinate conversion utilities used only by calibration flows
- calibration persistence protocol
- calibration-specific tests and build entries

Shared window, clipboard, keyboard, auth, task registry, and task lock utilities must be kept when still needed by the new keyboard flow or other non-refactored actions.

## 3. Final System Architecture

Adopt a hard-cut architecture with no calibration compatibility layer.

### 3.1 Web

```text
click plane icon
→ show manual confirmation dialog
→ user clicks "Confirm and paste"
→ send one POST /paste-draft request
```

No preparation API, no token signing, no second confirmation request.

### 3.2 Python

The `paste-draft` HTTP request performs a single-request validation and dispatch flow:

```text
authenticate user
→ validate bot / conversation / message / draft ownership
→ load conversationName
→ validate conversationName non-empty
→ validate conversationName unique within local bot/channel scope
→ load draftText
→ validate draftText non-empty
→ require Idempotency-Key header
→ build requestDigest
→ ensure runtime started
→ call runtime once
```

### 3.3 Runtime

The runtime receives only the minimum payload required for the keyboard flow and executes one fixed state machine. It does not load overlay resources, does not validate calibration state, and does not perform visual or coordinate-based interaction.

## 4. Paste-Only State Machine

The only runtime state machine for `paste_only` / `paste-draft` is:

```text
queued
→ activating_window
→ opening_search
→ pasting_conversation_name
→ confirming_conversation
→ waiting_input_focus
→ pasting_draft
→ restoring_clipboard
→ succeeded / succeeded_with_warning
```

Possible terminal error statuses remain:

```text
blocked
failed
cancelled
timed_out
```

### 4.1 Fixed execution order

The runtime must execute exactly this sequence once:

```text
snapshot clipboard
→ find the unique visible WXWork.exe main window
→ activate WXWork
→ Ctrl+F
→ sleep(400)
→ paste conversationName
→ sleep(400)
→ Enter
→ sleep(1000)
→ paste draftText
→ restore clipboard
→ finish
```

### 4.2 WXWork main-window definition

A valid WXWork main-window candidate must satisfy all of the following:

```text
process executable is WXWork.exe
window is a top-level/root window
window is not a child window
window is not an overlay or tool window
visible=true
width >= 300
height >= 300
```

Candidate handling is deliberately minimal:

```text
0 candidates → TARGET_WINDOW_NOT_FOUND
1 candidate  → activate and continue
2+ candidates → TARGET_WINDOW_AMBIGUOUS
```

Do not reintroduce candidate scoring, owner-chain recursion, area-based selection, or automatic promotion from arbitrary child windows.

### 4.3 Runtime restrictions

Do not add:

- search-box focus detection
- input-box focus detection
- UI Automation
- OCR / VLM
- region selection or coordinate logic
- mouse clicking
- Tab fallback
- automatic retry
- context confirmation tokens
- extra protocol checks such as request-digest mismatch semantics beyond existing request correlation

### 4.4 Known behavioral assumption

The first version relies on the standard WXWork behavior of `Ctrl+F`, search-result confirmation by `Enter`, and subsequent input focus movement. It does not handle shortcut failure, unexpected modal dialogs, or special focus states.

## 5. Web / Python / Runtime Responsibilities

### 5.1 Web responsibilities

Web is responsible for:

- showing the manual confirmation dialog
- generating a fresh UUID idempotency key when the user confirms
- reusing the same key for the same network retry chain
- disabling the plane icon and confirm button while the request is in flight
- not calling the API on cancel
- showing the existing success message that the draft was written to the input box and was not sent

Web is not responsible for:

- calibration
- token preparation
- runtime window selection
- conversation uniqueness validation logic

### 5.2 Python responsibilities

Python is responsible for:

- request authentication and ownership validation
- local conversation-name validation
- draft text validation
- requiring the `Idempotency-Key` HTTP header
- building `requestDigest`
- passing the same idempotency key to runtime
- calling `ensure_started()` before runtime task creation
- mapping runtime task state and errors back to the API response

Python must document the limitation that local uniqueness only proves the LangBot record is unique within the local bot/channel scope and does not prove that WXWork search results are globally unambiguous.

### 5.3 Runtime responsibilities

Runtime is responsible for:

- Bearer authentication
- idempotent task execution
- clipboard snapshot and restore
- unique-window discovery
- keyboard-only execution
- strict send blocking after draft paste begins
- returning redacted evidence fields

Runtime is not responsible for:

- calibration
- overlay rendering
- visual verification
- mouse fallback
- human confirmation tokens

## 6. Request and Response Protocol

### 6.1 Web → Python request

HTTP request:

```http
POST /api/v1/bots/{botId}/messages/{messageId}/paste-draft
Idempotency-Key: <uuid>
Content-Type: application/json
```

JSON body:

```json
{
  "draft_id": 123
}
```

If the header is missing:

```text
IDEMPOTENCY_KEY_REQUIRED
```

Python must not call runtime in that case.

### 6.2 Python → Runtime request

The runtime request for `paste-draft` keeps only these fields:

```json
{
  "action": "paste_draft",
  "conversationName": "...",
  "draftText": "...",
  "idempotencyKey": "...",
  "requestDigest": "..."
}
```

The following fields must not be carried by the `paste-draft` path:

```text
profile
windowBinding
windowKey
regionProfile
calibrationSessionId
humanConfirmationToken
targetConversation
```

### 6.3 Runtime result evidence

Keep only redacted evidence fields such as:

```text
status
stage
errorCode
messageSent
clipboardRestoreFailed
searchShortcutCount
conversationPasteCount
conversationConfirmEnterCount
draftPasteCount
sendKeyCount
idempotencyKey
requestDigest
```

Do not return:

```text
conversationName
draftText
clipboard raw contents
```

## 7. Error Codes

### 7.1 Backend-facing validation errors

Keep or add:

```text
CONVERSATION_NAME_REQUIRED
CONVERSATION_NAME_NOT_UNIQUE
DRAFT_TEXT_REQUIRED
IDEMPOTENCY_KEY_REQUIRED
RPA_RUNTIME_NOT_AVAILABLE
```

### 7.2 Runtime execution errors

Keep or add:

```text
TARGET_WINDOW_NOT_FOUND
TARGET_WINDOW_AMBIGUOUS
WINDOW_ACTIVATION_FAILED
WINDOW_FOCUS_LOST
CLIPBOARD_FORMAT_UNSUPPORTED
CLIPBOARD_RESTORE_MISMATCH
SEND_ACTION_FORBIDDEN
```

### 7.3 Remove from production code

```text
CALIBRATION_REQUIRED
HUMAN_CONFIRMATION_REQUIRED
HUMAN_CONFIRMATION_EXPIRED
HUMAN_CONFIRMATION_REPLAYED
HUMAN_CONFIRMATION_MISMATCH
```

## 8. Idempotency Rules

### 8.1 Web boundary

When the user clicks the confirmation action, web generates a fresh UUID and places it in the `Idempotency-Key` header.

- network retries for that same request reuse the same key
- a later user-initiated click generates a new key

This prevents accidental duplicate execution caused by retries while still allowing the user to intentionally paste the same draft again later.

### 8.2 Python boundary

Python must require the header, pass it through unchanged, and preserve the same key for any internal retry behavior.

### 8.3 Runtime boundary

Runtime must ensure the same idempotency key does not produce a second paste execution for the same logical task submission.

## 9. Safety and Send-Blocking Constraints

The keyboard flow is allowed to perform only:

```text
Ctrl+F once
paste conversationName once
Enter once for conversation confirmation
paste draftText once
```

The flow must never perform:

```text
Enter after draft paste
Ctrl+Enter
click send button
mouse coordinate click
OCR
VLM
full-task automatic retry
```

Required result invariants:

```text
sendKeyCount=0
messageSent=false
```

The runtime must preserve clipboard snapshot and restore behavior.

Once the clipboard snapshot succeeds, any path that overwrites the clipboard must attempt restoration in a `finally`-equivalent cleanup path, regardless of whether the task ends as `succeeded`, `blocked`, `failed`, `cancelled`, or `timed_out`.

Clipboard restore result rules:

- if the main task succeeds but restore verification fails:

  ```text
  status=succeeded_with_warning
  clipboardRestoreFailed=true
  errorCode=CLIPBOARD_RESTORE_MISMATCH
  ```

- if the main task has already failed and restore also fails:
  - preserve the original terminal status and original error code
  - add `clipboardRestoreFailed=true`
  - do not convert the task to `succeeded_with_warning`

`messageSent=false` means that the runtime did not issue a send action. It does not claim that the runtime visually verified the WXWork UI or proved that no external send occurred.

## 10. Legacy Database Metadata Handling

For historical metadata keys such as old region-profile data, this task performs only:

```text
stop reading
stop writing
```

Do not perform opportunistic cleanup while saving unrelated metadata. Historical JSON values may remain stored but become fully inert. Any physical cleanup must be handled by a future dedicated cleanup task.

## 11. File-Level Modification and Deletion Scope

### 11.1 Files expected to be deleted

Runtime calibration/overlay files are expected to be removed, including files such as:

- `apps/desktop-rpa-runtime/src/main/api/routes-calibration.ts`
- `apps/desktop-rpa-runtime/src/main/domain/region-profile.ts`
- `apps/desktop-rpa-runtime/src/main/overlay/*`
- `apps/desktop-rpa-runtime/src/renderer/overlay*`
- runtime calibration/overlay tests such as `tests/minimal-calibration.test.ts` and `tests/overlay-renderer.test.ts`

### 11.2 Files expected to be modified

Likely impact areas include, but are not limited to:

- web session monitor and related API client/types/i18n
- Python desktop automation service/client/errors/repository/runtime process/router
- runtime task runner, runtime host, local HTTP server, error/type definitions, window activation/finder helpers
- test fixtures and E2E flows

This list is a candidate impact range only. The final implementation must follow real imports, route registration, runtime wiring, and test dependencies rather than forcing unnecessary file edits.

### 11.3 Shared modules that must remain if still used

Keep shared modules when still required by the new keyboard flow or by non-refactored actions, for example:

- window finder and window activator
- clipboard controller
- keyboard input driver
- runtime auth and bearer-token handling
- task registry and task locks

The `paste-draft` / `paste_only` path and all calibration-only paths must contain no dependency on `profile`, `windowBinding`, `windowKey`, or `RegionProfileV2`. If `send`, `diagnose`, `history-search`, or `quote-reply` still genuinely use shared `windowBinding` or `windowKey` capabilities, that is allowed for those actions only, but the final implementation report must list the caller and the reason.

## 12. Test Matrix

### 12.1 Runtime

Runtime tests must prove:

1. calibration routes are removed
2. overlay is not built or loaded
3. `paste-draft` request handling does not accept or use `profile`, `windowBinding`, `windowKey`, or `humanConfirmationToken`
4. unique-window selection rules work using only valid WXWork top-level/root windows that are visible, at least 300x300, and are neither child windows nor overlay/tool windows:
   - zero valid windows → `TARGET_WINDOW_NOT_FOUND`
   - one valid window → proceed
   - multiple valid windows → `TARGET_WINDOW_AMBIGUOUS`
5. the fixed keyboard sequence runs exactly once
6. `Ctrl+F` count is 1
7. conversation-name paste count is 1
8. conversation-confirm Enter count is 1
9. draft paste count is 1
10. no send action occurs
11. `sendKeyCount=0`
12. `messageSent=false`
13. clipboard restore warning path is covered
14. every path that overwrites the clipboard attempts restoration, including blocked, failed, cancelled, and timed-out paths
15. a restore failure after an existing task failure preserves the original status/error and only adds `clipboardRestoreFailed=true`
16. the same `idempotencyKey` does not trigger duplicate execution
17. tests do not sleep in real time; waiting must be injected or mocked and assertions must verify:

```text
sleep(400)
sleep(400)
sleep(1000)
```

in that exact order

### 12.2 Python

Python tests must prove:

1. `paste-draft` only accepts body `{ "draft_id": ... }`
2. missing `Idempotency-Key` returns `IDEMPOTENCY_KEY_REQUIRED`
3. missing idempotency header does not call runtime
4. empty conversation name returns `CONVERSATION_NAME_REQUIRED`
5. non-unique conversation name returns `CONVERSATION_NAME_NOT_UNIQUE`
6. empty draft returns `DRAFT_TEXT_REQUIRED`
7. `paste-draft` does not read RegionProfileV2 or calibration metadata
8. runtime status and API surfaces no longer expose calibration fields for this feature
9. runtime bearer-auth behavior remains unchanged
10. the same idempotency key is forwarded unchanged

### 12.3 Web

Web tests must prove:

1. there is no calibration entry in the UI
2. `paste-draft` can be used without calibration
3. canceling the confirmation dialog does not call the API
4. confirming calls the API exactly once
5. repeated clicks during submission do not create duplicate requests
6. request body contains only `draft_id`
7. the `Idempotency-Key` header is sent
8. success messaging still indicates the draft was written but not sent

### 12.4 Residual symbol search

The following calibration-specific symbols must be zero in production code:

```text
RegionProfileV2
region_profile_configured
profileDigest
CALIBRATION_REQUIRED
overlay-wizard
start_calibration
calibrationSession
routes-calibration
region_profile_v2
```

Run the zero-match search only against production-code paths so that the design spec and intentional test descriptions do not create false positives:

```powershell
git grep -n -E "RegionProfileV2|region_profile_configured|profileDigest|CALIBRATION_REQUIRED|overlay-wizard|start_calibration|calibrationSession|routes-calibration|region_profile_v2" -- `
  "src/langbot/pkg/desktop_automation" `
  "src/langbot/pkg/api/http/controller/groups/bot_database_mode.py" `
  "apps/desktop-rpa-runtime/src" `
  "web/src"
```

For `paste-draft` / `paste_only`, verify that request typing, call parameters, validation, and state-machine code no longer reference:

```text
windowBinding
windowKey
regionProfile
calibrationSessionId
humanConfirmationToken
```

Broad terms such as `profile`, `inputBox`, and `chatHistory` are not valid whole-repository zero-match criteria because they may be used by unrelated features. Review them only along the `paste-draft` / `paste_only` call chain.

If non-refactored actions still use `windowBinding` or `windowKey`, list them in the final report with the caller and justification.

## 13. Acceptance Commands

### Runtime

```powershell
cd C:\Users\33031\Desktop\bot\apps\desktop-rpa-runtime
npm run typecheck
npm run lint
npm test
npm run build
npm run package:win
```

### Python

```powershell
cd C:\Users\33031\Desktop\bot
uv run pytest tests/unit_tests/desktop_automation/ -q
uv run pytest tests/unit_tests/database_mode/ -q
uv run ruff check src/langbot/pkg/desktop_automation tests/unit_tests/desktop_automation
uv run ruff format --check src/langbot/pkg/desktop_automation tests/unit_tests/desktop_automation
```

### Web

```powershell
cd C:\Users\33031\Desktop\bot\web
pnpm exec tsc --noEmit
pnpm exec eslint <modified files in this change>
pnpm exec playwright test tests/e2e/bot-database-session-composer.spec.ts
```

### Residual search

```powershell
git grep -n -E "RegionProfileV2|region_profile_configured|profileDigest|CALIBRATION_REQUIRED|overlay-wizard|start_calibration|calibrationSession|routes-calibration|region_profile_v2" -- `
  "src/langbot/pkg/desktop_automation" `
  "src/langbot/pkg/api/http/controller/groups/bot_database_mode.py" `
  "apps/desktop-rpa-runtime/src" `
  "web/src"
```

## 14. Known Limitations

The first version relies on standard WXWork keyboard behavior and does not attempt to detect or correct:

- shortcut failure
- unexpected modal dialogs
- special focus states
- ambiguous WXWork search results beyond local LangBot uniqueness checks

The local conversation-name uniqueness check only proves uniqueness within LangBot's local bot/channel records and cannot guarantee that WXWork itself will always present a single obvious result.

## 15. Prohibited Actions

Do not:

- keep a hidden advanced calibration entry
- keep compatibility request fields that are silently ignored for `paste-draft`
- leave unreferenced overlay files in production runtime code
- execute a real send
- commit
- push
- use destructive git cleanup commands
