# RPA Phase 1 Go Runtime Removal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove only the legacy Go-runtime-specific desktop RPA implementation, keep reusable desktop automation business models and entry points, and make all runtime-dependent operations fail closed with `RPA_RUNTIME_NOT_AVAILABLE`.

**Architecture:** Treat `src/langbot/pkg/desktop_automation/` as two layers: reusable business shell versus Go-runtime-specific transport/runtime implementation. Delete the Go runtime tree and Go-specific branches, preserve reusable persistence and API envelopes, and route all runtime-dependent flows through one uniform unavailable response without creating successful runs or mutating send/paste/completed state.

**Tech Stack:** Python 3.11+, Quart, SQLAlchemy, Alembic, pytest, Vite, React Router 7, TypeScript, Playwright, PowerShell, git grep.

---

## File Responsibility Map

### Protected but not to be changed in Phase 1 unless explicitly classified as RPA-related

- `C:\Users\33031\Desktop\bot\docs\superpowers\plans\2026-06-23-local-connectors-builtin-mcp.md` — non-RPA in-progress planning doc
- `C:\Users\33031\Desktop\bot\src\langbot\pkg\core\app.py` — application wiring; only touch if desktop automation service registration cannot remain stable otherwise
- `C:\Users\33031\Desktop\bot\src\langbot\pkg\core\bootutils\files.py` — non-RPA unless desktop-runtime path bootstrapping is present
- `C:\Users\33031\Desktop\bot\src\langbot\pkg\core\stages\build_app.py` — non-RPA unless desktop automation bootstrap is present
- `C:\Users\33031\Desktop\bot\src\langbot\pkg\database_mode\service.py` — bot/database workflow; only touch if fail-closed adapter boundary requires it
- `C:\Users\33031\Desktop\bot\src\langbot\pkg\entity\persistence\database_mode.py` — preserve shared models such as `DesktopAutomationRun`
- `C:\Users\33031\Desktop\bot\src\langbot\pkg\local_connectors\service.py` — only touch if old region-profile/runtime-info coupling exists
- `C:\Users\33031\Desktop\bot\src\langbot\pkg\persistence\alembic\versions\0012_desktop_runs.py` — preserve if it defines reusable run persistence
- `C:\Users\33031\Desktop\bot\tests\integration\persistence\test_migrations.py` — only touch if migration expectations mention Go-specific behavior
- `C:\Users\33031\Desktop\bot\tests\unit_tests\database_mode\test_database_mode_service.py` — only touch if desktop automation compatibility expectations need updating
- `C:\Users\33031\Desktop\bot\web\pnpm-lock.yaml` — do not touch in Phase 1

### Phase 1 RPA inventory / likely touch points

- `C:\Users\33031\Desktop\bot\apps\desktop-runtime\` — delete whole legacy Go runtime tree
- `C:\Users\33031\Desktop\bot\src\langbot\pkg\desktop_automation\client.py` — remove Go backend/capability probing, preserve reusable client error mapping only if still needed
- `C:\Users\33031\Desktop\bot\src\langbot\pkg\desktop_automation\service.py` — convert runtime-dependent methods to uniform fail-closed
- `C:\Users\33031\Desktop\bot\src\langbot\pkg\desktop_automation\runtime_process.py` — remove executable launch/runtime-info logic or reduce to explicit unavailable manager
- `C:\Users\33031\Desktop\bot\src\langbot\pkg\desktop_automation\errors.py` — add/keep `RPA_RUNTIME_NOT_AVAILABLE`, remove Go-only error surface where no longer used
- `C:\Users\33031\Desktop\bot\src\langbot\pkg\desktop_automation\repository.py` — preserve reusable run/profile persistence pieces, remove old state-file compatibility only if present
- `C:\Users\33031\Desktop\bot\src\langbot\pkg\api\http\controller\groups\bot_database_mode.py` — normalize HTTP 503 fail-closed envelope, keep calibration and paste entry points, remove dry-run route
- `C:\Users\33031\Desktop\bot\tests\unit_tests\desktop_automation\test_api.py` — assert HTTP 503 + envelope + no successful run side effects
- `C:\Users\33031\Desktop\bot\tests\unit_tests\desktop_automation\test_client.py` — remove Go capability checks and cover unavailable contract if client remains
- `C:\Users\33031\Desktop\bot\tests\unit_tests\desktop_automation\test_runtime_process.py` — rewrite around unavailable runtime manager or remove if launch manager disappears
- `C:\Users\33031\Desktop\bot\tests\unit_tests\desktop_automation\test_service.py` — assert no run creation, no pasted/sent/completed state, no runtime startup
- `C:\Users\33031\Desktop\bot\web\src\app\infra\http\BackendClient.ts` — remove `send-draft-dry-run` client method, keep paste/calibration methods
- `C:\Users\33031\Desktop\bot\web\src\app\infra\entities\api\bot-database.ts` — trim dry-run/Go-specific types only if no longer referenced
- `C:\Users\33031\Desktop\bot\web\src\app\infra\entities\api\index.ts` — re-export adjusted API types
- `C:\Users\33031\Desktop\bot\web\src\app\home\bots\components\bot-session\components\DatabaseBotSessionMonitor.tsx` — preserve entry surface, remove Go capability/dry-run state
- `C:\Users\33031\Desktop\bot\web\src\app\home\bots\components\bot-session\components\DatabaseChatComposer.tsx` — keep paste + calibration entry locations, show unified unavailable message
- `C:\Users\33031\Desktop\bot\web\src\app\home\bots\components\bot-session\components\DatabaseAiActionPopover.tsx` — remove dry-run actions if exposed here
- `C:\Users\33031\Desktop\bot\web\src\app\home\bots\components\bot-session\components\DatabaseMessageActionsMenu.tsx` — remove dry-run menu items
- `C:\Users\33031\Desktop\bot\web\src\app\home\bots\components\bot-session\components\desktopConfirmationState.ts` — delete or reduce if only used by old Go confirmation-token flow
- `C:\Users\33031\Desktop\bot\web\src\app\home\bots\components\bot-session\datasources\DatabaseBotDataSource.ts` — keep paste business call path, remove dry-run wrappers
- `C:\Users\33031\Desktop\bot\web\src\app\home\bots\components\bot-session\datasources\RuntimeBotDataSource.ts` — inspect only if it carries dry-run/runtime status branching
- `C:\Users\33031\Desktop\bot\web\src\app\home\bots\components\bot-session\types\index.ts` — update state/types to remove dry-run and Go capability assumptions
- `C:\Users\33031\Desktop\bot\web\src\i18n\locales\en-US.ts` — add unified unavailable copy and remove dry-run text
- `C:\Users\33031\Desktop\bot\web\src\i18n\locales\ja-JP.ts` — add unified unavailable copy and remove dry-run text
- `C:\Users\33031\Desktop\bot\web\src\i18n\locales\zh-Hans.ts` — add unified unavailable copy and remove dry-run text
- `C:\Users\33031\Desktop\bot\web\tests\e2e\bot-database-session-composer.spec.ts` — replace dry-run expectations with fail-closed paste/calibration expectations
- `C:\Users\33031\Desktop\bot\web\tests\e2e\desktop-confirmation-state.spec.ts` — delete if confirmation token state is removed with the Go flow

---

### Task 1: Protect the current working tree before any code change

**Files:**
- Inspect only: `C:\Users\33031\Desktop\bot\` working tree via `git status --short`
- Document in work log or task notes: current modified/untracked files

- [ ] **Step 1: Capture the current uncommitted file list**

Run:

```powershell
Set-Location "C:\Users\33031\Desktop\bot"
git status --short
```

Expected: a mixed list of modified and untracked files, including RPA and non-RPA work.

- [ ] **Step 2: Classify the current list into RPA-related and non-RPA-related buckets**

Use this classification baseline:

```text
RPA 相关
- apps/
- src/langbot/pkg/desktop_automation/
- src/langbot/pkg/api/http/controller/groups/bot_database_mode.py
- src/langbot/pkg/persistence/alembic/versions/0012_desktop_runs.py
- tests/unit_tests/desktop_automation/
- web/src/app/home/bots/components/bot-session/components/DatabaseBotSessionMonitor.tsx
- web/src/app/home/bots/components/bot-session/components/DatabaseChatComposer.tsx
- web/src/app/home/bots/components/bot-session/components/desktopConfirmationState.ts
- web/src/app/home/bots/components/bot-session/datasources/DatabaseBotDataSource.ts
- web/src/app/home/bots/components/bot-session/datasources/RuntimeBotDataSource.ts
- web/src/app/home/bots/components/bot-session/types/index.ts
- web/src/app/infra/entities/api/bot-database.ts
- web/src/app/infra/entities/api/index.ts
- web/src/app/infra/http/BackendClient.ts
- web/src/i18n/locales/en-US.ts
- web/src/i18n/locales/ja-JP.ts
- web/src/i18n/locales/zh-Hans.ts
- web/tests/e2e/bot-database-session-composer.spec.ts
- web/tests/e2e/desktop-confirmation-state.spec.ts
- temporary files with desktop/runtime naming such as .tmp-codex-runtime-*, .tmp-desktop-*, .tmp-manual-runtime-*

非 RPA 相关
- docs/superpowers/plans/2026-06-23-local-connectors-builtin-mcp.md
- src/langbot/pkg/core/app.py (treat as protected unless desktop automation wiring must change)
- src/langbot/pkg/core/bootutils/files.py
- src/langbot/pkg/core/stages/build_app.py
- src/langbot/pkg/database_mode/service.py
- src/langbot/pkg/entity/persistence/database_mode.py (shared model file; inspect before modifying)
- src/langbot/pkg/local_connectors/service.py
- src/langbot/templates/config.yaml
- tests/integration/persistence/test_migrations.py
- tests/unit_tests/database_mode/test_database_mode_service.py
- tests/unit_tests/core/test_bootutils_files.py
- web/pnpm-lock.yaml
- docs/superpowers/plans/2026-06-25-wxwork-database-channel-bot-processing.md
- docs/superpowers/plans/2026-06-25-wxwork-database-frontend-integration.md
- .claude/
- unrelated .tmp-* folders not tied to desktop automation if identified during review
```

Expected: a human-reviewed list that prevents accidental edits to non-RPA files.

- [ ] **Step 3: Record forbidden cleanup operations for the execution session**

Do not run:

```text
git reset
git restore
git checkout --
git clean
```

Expected: Phase 1 execution proceeds only with targeted file edits/deletes.

---

### Task 2: Inventory shared business shell versus Go-specific implementation

**Files:**
- Inspect/Modify: `C:\Users\33031\Desktop\bot\src\langbot\pkg\desktop_automation\errors.py`
- Inspect/Modify: `C:\Users\33031\Desktop\bot\src\langbot\pkg\desktop_automation\repository.py`
- Inspect/Modify: `C:\Users\33031\Desktop\bot\src\langbot\pkg\desktop_automation\runtime_process.py`
- Inspect/Modify: `C:\Users\33031\Desktop\bot\src\langbot\pkg\desktop_automation\service.py`
- Inspect only unless needed: `C:\Users\33031\Desktop\bot\src\langbot\pkg\entity\persistence\database_mode.py`
- Inspect only unless needed: `C:\Users\33031\Desktop\bot\src\langbot\pkg\persistence\alembic\versions\0012_desktop_runs.py`
- Test: `C:\Users\33031\Desktop\bot\tests\unit_tests\desktop_automation\test_repository.py`

- [ ] **Step 1: Write a preservation checklist for shared models**

Use this checklist while editing:

```text
Preserve if reusable in Phase 2:
- DesktopAutomationRun persistence model and statuses
- ReplyDraft / message linkage queries used by business routes
- existing API envelope contracts
- repository helpers that read/write run records

Delete or collapse if Go-specific:
- desktop-runtime.exe discovery
- runtime-info.json management
- robotgo/stub/win32/uia capability probing
- old region-profile compatibility for Go runtime
- old confirmation-token/runtime-transport assumptions
```

Expected: no shared run model is deleted only because it was introduced with the Go runtime.

- [ ] **Step 2: Add code comments that mark reusable shell versus retired Go implementation**

Target comments like:

```python
# Compatibility shell preserved for the future Electron runtime.
# Legacy Go runtime transport has been removed in Phase 1.
```

and

```python
# Shared run persistence remains intentionally preserved for Phase 2 reuse.
```

Expected: later cleanup decisions are explicit instead of implicit.

- [ ] **Step 3: Run the repository-focused test file before refactoring shared pieces**

Run:

```powershell
Set-Location "C:\Users\33031\Desktop\bot"
uv run pytest tests/unit_tests/desktop_automation/test_repository.py -q
```

Expected: current behavior baseline is captured before any shared-shell edits.

---

### Task 3: Define one backend fail-closed contract and cover it with tests first

**Files:**
- Modify: `C:\Users\33031\Desktop\bot\src\langbot\pkg\desktop_automation\errors.py`
- Modify: `C:\Users\33031\Desktop\bot\src\langbot\pkg\desktop_automation\service.py`
- Modify: `C:\Users\33031\Desktop\bot\src\langbot\pkg\api\http\controller\groups\bot_database_mode.py`
- Test: `C:\Users\33031\Desktop\bot\tests\unit_tests\desktop_automation\test_service.py`
- Test: `C:\Users\33031\Desktop\bot\tests\unit_tests\desktop_automation\test_api.py`

- [ ] **Step 1: Add failing service tests that require a uniform unavailable error before any run is created**

Add tests shaped like:

```python
async def test_create_send_draft_run_fails_closed_without_creating_run():
    repository = _FakeRepository()
    repository.message = {
        'bot': {'uuid': 'bot-1'},
        'channel_account': {'connector_id': 'wxwork-local'},
        'message': {'id': 101},
        'conversation': {'id': 201, 'conversation_name': 'Customer A', 'conversation_type': 'direct'},
        'active_draft': None,
        'active_draft_count': 1,
    }
    repository.draft = {'id': 301, 'content': 'hello', 'status': 'active'}
    service = _build_service(repository=repository, runtime_process_manager=AsyncMock())

    with pytest.raises(DesktopAutomationError) as exc:
        await service.create_send_draft_run('bot-1', 101, 301)

    assert exc.value.code == 'RPA_RUNTIME_NOT_AVAILABLE'
    assert repository.created_run is None
```

```python
async def test_start_calibration_fails_closed_with_runtime_not_available():
    service = _build_service(repository=_FakeRepository(), runtime_process_manager=AsyncMock())

    with pytest.raises(DesktopAutomationError) as exc:
        await service.start_calibration('bot-1')

    assert exc.value.code == 'RPA_RUNTIME_NOT_AVAILABLE'
```

Expected: FAIL until service logic blocks early and avoids persistence side effects.

- [ ] **Step 2: Add failing API tests that require HTTP 503 and the existing response envelope**

Add tests shaped like:

```python
async def test_paste_draft_returns_http_503_with_runtime_not_available(client):
    response = await client.post('/api/v1/bots/bot-1/messages/101/paste-draft', json={'draft_id': 301})
    assert response.status_code == 503
    payload = await response.get_json()
    assert payload['code'] == -1
    assert payload['message'] == 'RPA_RUNTIME_NOT_AVAILABLE'
```

```python
async def test_start_calibration_returns_http_503_with_runtime_not_available(client):
    response = await client.post('/api/v1/bots/bot-1/desktop-automation/calibration-sessions', json={})
    assert response.status_code == 503
    payload = await response.get_json()
    assert payload['message'] == 'RPA_RUNTIME_NOT_AVAILABLE'
```

Expected: FAIL until the router normalizes these routes.

- [ ] **Step 3: Implement the shared unavailable constant and service guard**

Implement behavior like:

```python
RPA_RUNTIME_NOT_AVAILABLE = 'RPA_RUNTIME_NOT_AVAILABLE'
```

```python
def _raise_runtime_not_available(self) -> None:
    raise DesktopAutomationError(
        RPA_RUNTIME_NOT_AVAILABLE,
        'RPA runtime is not integrated yet',
    )
```

and call that guard before any run creation, task creation, or calibration session creation.

Expected: service methods fail before mutating run/message/draft state.

- [ ] **Step 4: Implement one router-level HTTP mapping for the new unavailable code**

Add mapping behavior like:

```python
if code == RPA_RUNTIME_NOT_AVAILABLE:
    return 503
```

Expected: all runtime-dependent bot-scoped routes return the same 503 envelope.

- [ ] **Step 5: Run the focused backend tests**

Run:

```powershell
Set-Location "C:\Users\33031\Desktop\bot"
uv run pytest tests/unit_tests/desktop_automation/test_service.py -q
uv run pytest tests/unit_tests/desktop_automation/test_api.py -q
```

Expected: PASS with no created successful run and no pasted/sent/completed state mutation.

---

### Task 4: Remove Go-runtime-specific client and process-manager behavior

**Files:**
- Modify or delete: `C:\Users\33031\Desktop\bot\src\langbot\pkg\desktop_automation\client.py`
- Modify or delete: `C:\Users\33031\Desktop\bot\src\langbot\pkg\desktop_automation\runtime_process.py`
- Modify: `C:\Users\33031\Desktop\bot\src\langbot\pkg\desktop_automation\service.py`
- Test: `C:\Users\33031\Desktop\bot\tests\unit_tests\desktop_automation\test_client.py`
- Test: `C:\Users\33031\Desktop\bot\tests\unit_tests\desktop_automation\test_runtime_process.py`

- [ ] **Step 1: Add failing tests that ban legacy Go executable and runtime-info coupling**

Add tests shaped like:

```python
def test_runtime_process_manager_does_not_resolve_legacy_desktop_runtime_executable():
    from langbot.pkg.desktop_automation import runtime_process
    assert 'desktop-runtime.exe' not in runtime_process.__file__
```

```python
async def test_runtime_status_reports_not_available_without_start_attempt():
    manager = DesktopRuntimeProcessManager(config={'enabled': True})
    status = await manager.get_status()
    assert status['status'] == 'not_available'
    assert status['errorCode'] == 'RPA_RUNTIME_NOT_AVAILABLE'
```

Expected: FAIL until old startup/discovery logic is removed.

- [ ] **Step 2: Replace the launch manager with an explicit unavailable manager or stub**

Target behavior:

```python
class DesktopRuntimeProcessManager:
    async def ensure_started(self) -> dict[str, Any]:
        raise DesktopAutomationError(RPA_RUNTIME_NOT_AVAILABLE, 'RPA runtime is not integrated yet')

    async def get_status(self) -> dict[str, Any]:
        return {
            'status': 'not_available',
            'errorCode': RPA_RUNTIME_NOT_AVAILABLE,
            'runtime_configured': False,
            'runtime_reachable': False,
        }
```

Expected: no path discovery, no subprocess spawn, no runtime-info.json reads/writes.

- [ ] **Step 3: Delete or reduce Go-specific client methods**

Remove methods and checks tied to:

```text
robotgo
isStub
driverBackend
windowBackend
uiaBackend
boxSelectAvailable
send_current_wecom_draft_dry_run
runtime protocol version checks used only by the retired Go runtime
```

Preserve only code still required by the shared Phase 1 shell.

Expected: source no longer contains Go backend capability checks.

- [ ] **Step 4: Run the focused unit tests**

Run:

```powershell
Set-Location "C:\Users\33031\Desktop\bot"
uv run pytest tests/unit_tests/desktop_automation/test_client.py -q
uv run pytest tests/unit_tests/desktop_automation/test_runtime_process.py -q
```

Expected: PASS with no runtime startup attempt and no Go capability probing.

---

### Task 5: Remove the legacy Go runtime tree and source/build/test references

**Files:**
- Delete: `C:\Users\33031\Desktop\bot\apps\desktop-runtime\`
- Modify if needed: `C:\Users\33031\Desktop\bot\src\langbot\pkg\core\bootutils\files.py`
- Modify if needed: `C:\Users\33031\Desktop\bot\src\langbot\pkg\core\stages\build_app.py`
- Modify if needed: `C:\Users\33031\Desktop\bot\src\langbot\pkg\local_connectors\service.py`
- Test: `C:\Users\33031\Desktop\bot\tests\unit_tests\core\test_bootutils_files.py`

- [ ] **Step 1: Search for repository code that still references the Go runtime tree**

Run:

```powershell
Set-Location "C:\Users\33031\Desktop\bot"
git grep -n "apps/desktop-runtime"
git grep -n "desktop-runtime.exe"
git grep -n "runtime-info.json"
```

Expected: a reviewable list of exact files to fix before deletion.

- [ ] **Step 2: Delete the legacy runtime directory with a targeted workspace-local delete**

Run:

```powershell
Set-Location "C:\Users\33031\Desktop\bot"
Remove-Item -LiteralPath "C:\Users\33031\Desktop\bot\apps\desktop-runtime" -Recurse -Force
```

Expected: the directory is removed and no other workspace content is touched.

- [ ] **Step 3: Remove any remaining source/build wiring that assumes the deleted tree exists**

Target patterns to remove:

```text
desktop_runtime_robotgo
desktop_runtime_stub
DESKTOP_RUNTIME_ENABLE_SEND
desktop-runtime.exe
desktop-runtime-stub.exe
runtime-info.json
```

Expected: repository code no longer tries to bootstrap or inspect the retired Go runtime.

- [ ] **Step 4: Run the focused checks**

Run:

```powershell
Set-Location "C:\Users\33031\Desktop\bot"
uv run pytest tests/unit_tests/core/test_bootutils_files.py -q
git grep -n "desktop-runtime" -- . ":(exclude)docs/**"
```

Expected: code/build/test hits are empty or reduced only to planned non-code files still under review.

---

### Task 6: Remove dry-run and Go-specific frontend behavior while keeping paste and calibration entries

**Files:**
- Modify: `C:\Users\33031\Desktop\bot\web\src\app\infra\http\BackendClient.ts`
- Modify: `C:\Users\33031\Desktop\bot\web\src\app\infra\entities\api\bot-database.ts`
- Modify: `C:\Users\33031\Desktop\bot\web\src\app\infra\entities\api\index.ts`
- Modify: `C:\Users\33031\Desktop\bot\web\src\app\home\bots\components\bot-session\components\DatabaseBotSessionMonitor.tsx`
- Modify: `C:\Users\33031\Desktop\bot\web\src\app\home\bots\components\bot-session\components\DatabaseChatComposer.tsx`
- Modify: `C:\Users\33031\Desktop\bot\web\src\app\home\bots\components\bot-session\components\DatabaseAiActionPopover.tsx`
- Modify: `C:\Users\33031\Desktop\bot\web\src\app\home\bots\components\bot-session\components\DatabaseMessageActionsMenu.tsx`
- Modify or delete: `C:\Users\33031\Desktop\bot\web\src\app\home\bots\components\bot-session\components\desktopConfirmationState.ts`
- Modify: `C:\Users\33031\Desktop\bot\web\src\app\home\bots\components\bot-session\datasources\DatabaseBotDataSource.ts`
- Modify if referenced: `C:\Users\33031\Desktop\bot\web\src\app\home\bots\components\bot-session\datasources\RuntimeBotDataSource.ts`
- Modify: `C:\Users\33031\Desktop\bot\web\src\app\home\bots\components\bot-session\types\index.ts`
- Modify: `C:\Users\33031\Desktop\bot\web\src\i18n\locales\en-US.ts`
- Modify: `C:\Users\33031\Desktop\bot\web\src\i18n\locales\ja-JP.ts`
- Modify: `C:\Users\33031\Desktop\bot\web\src\i18n\locales\zh-Hans.ts`
- Test: `C:\Users\33031\Desktop\bot\web\tests\e2e\bot-database-session-composer.spec.ts`
- Test/Delete: `C:\Users\33031\Desktop\bot\web\tests\e2e\desktop-confirmation-state.spec.ts`

- [ ] **Step 1: Add failing UI tests for the Phase 1 contract**

Update or add assertions like:

```typescript
test('paste entry remains visible but shows runtime unavailable when invoked', async ({ page }) => {
  await page.getByRole('button', { name: /paste/i }).click();
  await expect(page.getByText(/RPA Runtime 尚未接入/i)).toBeVisible();
});
```

```typescript
test('calibration entry remains visible but does not start a Go runtime session', async ({ page }) => {
  await page.getByRole('button', { name: /校准|calibration/i }).click();
  await expect(page.getByText(/RPA Runtime 尚未接入/i)).toBeVisible();
});
```

```typescript
test('dry run action is not rendered', async ({ page }) => {
  await expect(page.getByRole('button', { name: /dry run/i })).toHaveCount(0);
});
```

Expected: FAIL until the UI is simplified.

- [ ] **Step 2: Remove the frontend `send-draft-dry-run` call path**

Delete the API method shaped like:

```typescript
public sendBotDraftDryRun(...) {
  return this.post(`/api/v1/bots/${botId}/messages/${messageId}/send-draft-dry-run`, ...);
}
```

Expected: no caller can trigger the dry-run route.

- [ ] **Step 3: Keep paste and calibration entry locations but map failures to one message**

Target handling shape:

```typescript
if (errorMessage === 'RPA_RUNTIME_NOT_AVAILABLE') {
  toast.error(t('botDatabase.desktopAutomation.runtimeNotAvailable'));
  return;
}
```

Expected: the user sees one consistent unavailable notice.

- [ ] **Step 4: Remove old confirmation-token state if it exists only for the Go flow**

Delete or simplify code tied to:

```text
human_confirmation_token
desktop confirmation token reuse
dry-run confirmation preview state
```

Expected: no half-preserved Go confirmation UX remains.

- [ ] **Step 5: Run the focused frontend checks**

Run:

```powershell
Set-Location "C:\Users\33031\Desktop\bot\web"
pnpm exec tsc --noEmit
pnpm exec eslint src/app/home/bots/components/bot-session/components/ src/app/infra/http/BackendClient.ts
pnpm exec playwright test tests/e2e/bot-database-session-composer.spec.ts
```

Expected: PASS with paste/calibration entry points still present and dry-run absent.

---

### Task 7: Update router surface and preserve calibration/paste entry points only

**Files:**
- Modify: `C:\Users\33031\Desktop\bot\src\langbot\pkg\api\http\controller\groups\bot_database_mode.py`
- Test: `C:\Users\33031\Desktop\bot\tests\unit_tests\desktop_automation\test_api.py`

- [ ] **Step 1: Remove or disable the dry-run route**

Remove handling for:

```text
POST /api/v1/bots/{bot_id}/messages/{message_id}/send-draft-dry-run
```

Either delete the route outright or make it return the same unavailable envelope if callers still exist during refactor.

Expected: no successful dry-run behavior survives.

- [ ] **Step 2: Preserve route shape for paste and calibration and normalize them to HTTP 503**

Preserve:

```text
POST /api/v1/bots/{bot_id}/messages/{message_id}/paste-draft
POST /api/v1/bots/{bot_id}/desktop-automation/calibration-sessions
GET  /api/v1/desktop-automation/runtime/status
```

Expected response contract:

```json
{
  "code": -1,
  "message": "RPA_RUNTIME_NOT_AVAILABLE"
}
```

Expected: callers keep the same envelope family and get one clear unavailable result.

- [ ] **Step 3: Ensure no route creates success-path run data before returning unavailable**

Add assertions in tests like:

```python
assert repository.created_run is None
assert payload['message'] == 'RPA_RUNTIME_NOT_AVAILABLE'
```

Expected: runtime-dependent routes fail before persistence mutation.

- [ ] **Step 4: Re-run focused API tests**

Run:

```powershell
Set-Location "C:\Users\33031\Desktop\bot"
uv run pytest tests/unit_tests/desktop_automation/test_api.py -q
```

Expected: PASS with the normalized HTTP contract.

---

### Task 8: Clean and rewrite tests so they validate Phase 1 rather than the retired Go runtime

**Files:**
- Modify/Delete: `C:\Users\33031\Desktop\bot\tests\unit_tests\desktop_automation\test_client.py`
- Modify/Delete: `C:\Users\33031\Desktop\bot\tests\unit_tests\desktop_automation\test_runtime_process.py`
- Modify: `C:\Users\33031\Desktop\bot\tests\unit_tests\desktop_automation\test_service.py`
- Modify: `C:\Users\33031\Desktop\bot\tests\unit_tests\desktop_automation\test_api.py`
- Modify: `C:\Users\33031\Desktop\bot\web\tests\e2e\bot-database-session-composer.spec.ts`
- Delete if obsolete: `C:\Users\33031\Desktop\bot\web\tests\e2e\desktop-confirmation-state.spec.ts`

- [ ] **Step 1: Remove tests that only assert Go backend capability detection**

Delete expectations tied to:

```text
driverBackend == robotgo
windowBackend == win32
uiaBackend == windows-uia
isStub == false
boxSelectAvailable == true
```

Expected: tests no longer encode the retired runtime.

- [ ] **Step 2: Replace them with Phase 1 invariants**

Use invariants like:

```text
HTTP 503 for runtime-dependent routes
message == RPA_RUNTIME_NOT_AVAILABLE
no successful DesktopAutomationRun is created
no pasted/sent/completed status is written
paste and calibration entry locations still exist in the UI
Dry Run controls are absent
```

Expected: test suite now matches the intended Phase 1 behavior.

- [ ] **Step 3: Run the desktop automation and related bot-session test set**

Run:

```powershell
Set-Location "C:\Users\33031\Desktop\bot"
uv run pytest tests/unit_tests/desktop_automation/ -q
uv run pytest tests/unit_tests/database_mode/ -q

Set-Location "C:\Users\33031\Desktop\bot\web"
pnpm exec playwright test tests/e2e/bot-database-session-composer.spec.ts
```

Expected: PASS with no Go-runtime-specific assertions left.

---

### Task 9: Perform Phase 1 acceptance verification with split grep reporting

**Files:**
- Inspect only: repository-wide code/test/build files
- Optional report note: `C:\Users\33031\Desktop\bot\docs\superpowers\specs\2026-06-29-rpa-phase1-go-runtime-removal-design.md`

- [ ] **Step 1: Run mandatory residue searches for code/test/build files**

Run:

```powershell
Set-Location "C:\Users\33031\Desktop\bot"
git grep -n "desktop-runtime" -- . ":(exclude)docs/**"
git grep -n "robotgo" -- . ":(exclude)docs/**"
git grep -n "DESKTOP_RUNTIME_ENABLE_SEND" -- . ":(exclude)docs/**"
git grep -n "send-draft-dry-run" -- . ":(exclude)docs/**"
git grep -n "RUNTIME_BACKEND_UNAVAILABLE" -- . ":(exclude)docs/**"
git grep -n "runtime-info.json" -- . ":(exclude)docs/**"
```

Expected: no hits in source, tests, or build configuration.

- [ ] **Step 2: Run the documentation-only historical searches separately**

Run:

```powershell
Set-Location "C:\Users\33031\Desktop\bot"
git grep -n "desktop-runtime" -- docs
git grep -n "robotgo" -- docs
git grep -n "runtime-info.json" -- docs
```

Expected: hits are allowed only where documentation explains historical cleanup or migration notes.

- [ ] **Step 3: Run formatting, lint, diff, and targeted test verification**

Run:

```powershell
Set-Location "C:\Users\33031\Desktop\bot"
uv run pytest tests/unit_tests/desktop_automation/ -q
uv run pytest tests/unit_tests/database_mode/ -q
uv run ruff check src/langbot/pkg/desktop_automation tests/unit_tests/desktop_automation
uv run ruff format --check src/langbot/pkg/desktop_automation tests/unit_tests/desktop_automation
git diff --check
git status --short
git diff --stat

Set-Location "C:\Users\33031\Desktop\bot\web"
pnpm exec tsc --noEmit
pnpm exec eslint src/app/home/bots/components/bot-session/components/ src/app/infra/http/BackendClient.ts
pnpm exec playwright test tests/e2e/bot-database-session-composer.spec.ts
```

Expected: verification passes or produces a precise stop list.

- [ ] **Step 4: Stop after Phase 1 and produce the acceptance report**

The report must contain:

```text
1. Deleted Phase 1 files
2. Modified Phase 1 files
3. Code residue grep results
4. Documentation-only grep hits
5. Test and lint results
6. Failed checks and reasons
7. Explicit statement: no real desktop action, no commit, no push
```

Expected: if any Phase 1 acceptance item fails, do not proceed to Phase 2.
