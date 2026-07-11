# Windows trial release baseline investigation

Generated for Task 1 on 2026-07-09 from repository root `C:\Users\33031\Desktop\bot`.

## Git baseline

```text
$ git status --short
D docs/superpowers/plans/2026-06-23-local-connectors-builtin-mcp.md
 D docs/superpowers/plans/2026-06-25-wxwork-database-channel-bot-processing.md
 D docs/superpowers/plans/2026-06-25-wxwork-database-frontend-integration.md
 D docs/superpowers/plans/2026-06-29-rpa-phase1-go-runtime-removal.md
 D docs/superpowers/plans/2026-06-29-rpa-phase2-electron-runtime-implementation-plan.md
 D docs/superpowers/plans/2026-07-02-broadcast-phase2-persistence.md
 D docs/superpowers/plans/2026-07-02-broadcast-usability-fixes.md
 D docs/superpowers/plans/2026-07-02-broadcast-workspace-phase1.md
 D docs/superpowers/plans/2026-07-03-broadcast-phase3-implementation.md
 D docs/superpowers/plans/2026-07-03-broadcast-phase4-7-implementation.md
 D docs/superpowers/specs/2026-06-29-rpa-phase1-go-runtime-removal-design.md
 D docs/superpowers/specs/2026-06-29-rpa-phase2-electron-runtime-design.md
 D docs/superpowers/specs/2026-06-30-wxwork-paste-only-keyboard-design-revised.md
 D docs/superpowers/specs/2026-07-02-broadcast-workspace-design.md
 D docs/superpowers/specs/2026-07-03-broadcast-phase3-design.md
 D docs/superpowers/specs/2026-07-03-broadcast-phase4-7-design.md
?? output/
?? runtime/

$ git branch --show-current
codex/integrate-wechat-decrypt

$ git rev-parse HEAD
ac1c47576cf2ff20545bfb01ce5004891e7eb8eb

$ git log -5 --oneline
ac1c47576 docs(release): finalize Windows trial release implementation plan
a94677f61 docs(release): refine Windows trial release implementation plan
70ae2aaef docs(release): add Windows trial release implementation plan
05b3a83ee docs(release): refine trial release runtime boundaries
582e2232f docs(release): add Windows trial release design
```

The working tree already contained unrelated deletions under `docs/superpowers/plans`, `docs/superpowers/specs`, plus untracked `output/` and `runtime/`. These are intentionally left untouched.

## Packaged startup interface contract

| Interface | Current code location | Current route / mechanism | Auth requirement | Packaged decision input | Later tasks that must cite this row |
| --- | --- | --- | --- | --- | --- |
| backend health | `src/langbot/pkg/api/http/controller/main.py:272-275` | `GET /healthz`, returns `{"code": 0, "msg": "ok"}` | none; direct Quart route without `RouterGroup` auth wrapper | launcher `launcher.json.backend.healthPath`; default `/healthz` | Tasks 7, 11, 12, 14, 17 |
| Desktop RPA runtime status | `src/langbot/pkg/api/http/controller/groups/bot_database_mode.py:661-677` | `GET /api/v1/desktop-automation/runtime/status`; delegates to `desktop_automation_service.get_runtime_status()` | `AuthType.USER_TOKEN` in current source mode; packaged launcher must either use the backend-owned local bypass/API-key design or keep user-token semantics verified before E2E | launcher observes backend-owned RPA only through `launcher.json.backend.runtimeStatusPath`; default `/api/v1/desktop-automation/runtime/status` | Tasks 7, 10, 12, 17 |
| graceful shutdown | `src/langbot/pkg/core/local_shutdown_control.py:54-74` and `src/langbot/pkg/api/http/controller/main.py:74-75` | source control-file watcher uses `LANGBOT_LOCAL_STACK_SESSION_ID` + `LANGBOT_LOCAL_SHUTDOWN_REQUEST_PATH`; HTTP controller exposes `request_shutdown()` internally | local control file path is constrained to repo `.tmp/local-stack/control` in source mode; packaged launcher needs its own `%LOCALAPPDATA%\Chatbot\runtime` control path or direct process signal | launcher stop/restart flow writes an owner-scoped shutdown control file and only terminates owned backend if graceful stop times out | Tasks 7, 12, 17 |
| packaged host/port source | `src/langbot/pkg/api/http/controller/main.py:63-70,262-270`; current port from `instance_config.data['api']['port']`, host from `api.host` or default `127.0.0.1` | Hypercorn bind host/port from config; default host constant is `127.0.0.1` | n/a | maintainer `launcher.json` is the packaged source of truth; Task 7 entrypoint must override config/env to force `127.0.0.1:5302` unless launcher config changes it | Tasks 7, 11, 12, 14, 17 |

Any later task touching these interfaces must cite the relevant row above and must not invent a different endpoint or lifecycle API.

## Backend packaged-risk findings

- Data root: `src/langbot/pkg/utils/paths.py` currently prioritizes `LANGBOT_DATA_ROOT`, then source-root `data`, then `cwd/data`.
- Frontend path: `get_frontend_path()` currently probes source/cwd/package `web/dist` and legacy `web/out`.
- Runtime dependency installation: `src/langbot/pkg/core/bootutils/deps.py` currently calls `pip.main(['install', ...])` in `install_deps()` and scans `plugins/*/requirements.txt` in `precheck_plugin_deps()`.
- RPA status API: confirmed as `GET /api/v1/desktop-automation/runtime/status` with user-token auth in source mode.

## Connector findings

- Current connector repository root: `src/langbot/pkg/local_connectors/repository.py` writes to `%LOCALAPPDATA%\WecomeBot\connectors` when `LOCALAPPDATA` exists, else `cwd/data/local-connectors`.
- Current connector Python: `src/langbot/pkg/local_connectors/connectors/base.py` uses `sys.executable`.
- Current bundled runtime resolution: `src/langbot/pkg/local_connectors/bundled_runtime.py` checks packaged/resource candidates, source `vendor/wechat_decrypt`, then `WECOME_WECHAT_DECRYPT_DIR`.
- Product entrypoints observed in `vendor/wechat_decrypt`: `connector_cli.py, connector_runtime.py, decrypt_db.py, decrypt_wxwork_db.py, find_all_keys_windows.py, find_wxwork_keys.py, mcp_server.py, mcp_wxwork_server.py, wxwork_message_monitor.py`.
- UAC helper: `src/langbot/pkg/local_connectors/uac_helper.py` writes a temporary PowerShell helper and maps Windows cancel code `1223` to `UAC_CANCELLED`; helper script is deleted in `finally`.

## Frontend build findings

- `web/package.json` declares `packageManager: pnpm@9.15.4`.
- Production build command is `pnpm run build`, which runs `tsc && vite build`.
- Production output directory is `web/dist`.

## RPA runtime findings

- Current command: `apps/desktop-rpa-runtime/package.json` exposes `npm run package:win`.
- Current implementation: `apps/desktop-rpa-runtime/scripts/package-win.mjs` writes timestamped output under `dist-phase2-official/<timestamp>` and computes a fixed executable candidate under `dist-phase2-official/win-unpacked/LangBot Desktop RPA Runtime.exe`.
- Current Electron builder targets both `portable` and `nsis`; deterministic release assembly needs a fixed `win-unpacked` directory-only build.

## Missing build-tool prerequisites

- Pinned Python runtime artifact: not yet recorded in repository before Task 6.
- VC++ redistributable binary: not vendored and must remain a build input/cache item.
- .NET 8 SDK: available locally as `dotnet --version` output observed outside this document during implementation; Task 11 verifies again.
- Inno Setup: `iscc` is not available on PATH in this environment; installer build may be BLOCKED until installed or an explicit path is supplied.
- Windows Sandbox / clean VM: not proven available in this repository baseline; Task 17 must mark clean-machine checks UNVERIFIED unless actually run.
