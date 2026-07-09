# Chatbot Windows x64 Self-Contained Trial Release Design

## Summary

This design defines a Windows x64 self-contained trial release for Chatbot that installs and runs on a clean user machine without requiring Python, Node.js, pnpm, uv, Git, or developer shell commands. The release will produce both an installer and a portable bundle, with a graphical launcher as the only user-facing entrypoint.

## Goals

1. Produce these release artifacts:
   - `build/release/Chatbot-Setup-<version>-x64.exe`
   - `build/release/Chatbot-Trial-<version>-x64.zip`
2. Ensure the installed product runs on Windows x64 without system Python, Node.js, pnpm, uv, Git, or Build Tools.
3. Make the user flow:
   - install
   - double-click desktop shortcut
   - start backend automatically
   - start RPA runtime automatically
   - open browser automatically
4. Keep program files and user data separated.
5. Keep real sending disabled by default.
6. Ensure the portable and installer builds are deterministic, validated, and scanned for sensitive data.

## Non-Goals

1. Code signing.
2. Auto-update.
3. Broad refactoring of unrelated business logic.
4. Shipping the full upstream `wechat-decrypt` toolbox.
5. Changing current development-mode semantics for `/C:/Users/33031/Desktop/bot/scripts/start-local.ps1`.

## Constraints

1. Only the allowed files and directories from the task may be changed.
2. Existing unrelated working tree changes must not be overwritten, restored, deleted, or committed.
3. Release artifacts must not be committed to Git.
4. The build must never depend on desktop-side `wechat-decrypt` at release runtime.
5. The final release build may only consume `/C:/Users/33031/Desktop/bot/vendor/wechat_decrypt` as the Connector source tree.
6. Desktop backup content is only an audit reference and cannot be packaged directly.

## Existing State

### Repository packaging state

The repository currently lacks a release packaging framework:

- `/C:/Users/33031/Desktop/bot/packaging` does not exist
- `/C:/Users/33031/Desktop/bot/launcher` does not exist
- `/C:/Users/33031/Desktop/bot/scripts/build-trial-release.ps1` does not exist
- `/C:/Users/33031/Desktop/bot/scripts/verify-trial-release.ps1` does not exist
- `/C:/Users/33031/Desktop/bot/scripts/test-trial-install.ps1` does not exist
- `/C:/Users/33031/Desktop/bot/docs/release` does not exist

### Path/runtime risks

Current code still assumes source/developer execution patterns:

- `/C:/Users/33031/Desktop/bot/src/langbot/pkg/utils/paths.py` falls back to source root or current working directory
- `/C:/Users/33031/Desktop/bot/src/langbot/pkg/core/bootutils/deps.py` can install dependencies at runtime
- `/C:/Users/33031/Desktop/bot/src/langbot/pkg/local_connectors/repository.py` writes to `%LOCALAPPDATA%\\WecomeBot\\connectors`
- `/C:/Users/33031/Desktop/bot/src/langbot/pkg/local_connectors/connectors/base.py` uses `sys.executable`
- `/C:/Users/33031/Desktop/bot/src/langbot/pkg/local_connectors/bundled_runtime.py` still contains source/developer discovery paths

### RPA runtime risks

`/C:/Users/33031/Desktop/bot/apps/desktop-rpa-runtime` currently builds into timestamped folders under `dist-phase2-official`, which is not acceptable for deterministic release assembly.

### vendor/wechat_decrypt scope decision

The release must use only `/C:/Users/33031/Desktop/bot/vendor/wechat_decrypt`. The desktop backup is an audit source only.

The approved scope is a **minimal releasable medium set**:

- include only the recursive runtime files required for LangBot Connector, MCP, Monitor, key extraction, and database decryption
- add:
  - `requirements.txt`
  - `requirements.lock.txt`
  - a minimal release note
  - `source-manifest.json`
- exclude full upstream toolbox content unless dependency analysis proves it is required

## Release Architecture

The release is organized as a layered packaged application with one user-facing launcher and several internal runtimes.

### Install root

Default install root:

- `%LOCALAPPDATA%\\Programs\\Chatbot`

Packaged structure:

```text
Chatbot/
|-- ChatbotLauncher.exe
|-- manifest.json
|-- launcher.json
|-- server/
|   |-- runtime/
|   `-- app/
|-- connectors/
|   |-- runtime/
|   `-- app/wechat-decrypt/
|-- resources/
|   |-- web/dist/
|   |-- templates/
|   |-- migrations/
|   `-- defaults/
|-- runtime/
|   `-- desktop-rpa/
|-- prerequisites/
|   `-- vc_redist.x64.exe
`-- licenses/
```

### User data root

All user-mutated data lives under:

- `%LOCALAPPDATA%\\Chatbot`

Subdirectories:

- `%LOCALAPPDATA%\\Chatbot\\data`
- `%LOCALAPPDATA%\\Chatbot\\config`
- `%LOCALAPPDATA%\\Chatbot\\connectors`
- `%LOCALAPPDATA%\\Chatbot\\logs`
- `%LOCALAPPDATA%\\Chatbot\\runtime`
- `%LOCALAPPDATA%\\Chatbot\\uploads`
- `%LOCALAPPDATA%\\Chatbot\\temp`

The install directory must remain readable-only at runtime without breaking application startup.

## Runtime Boundary Design

### 1. Launcher

The launcher is the only end-user entrypoint. It is a self-contained `.NET 8` Windows GUI application published for:

- `win-x64`
- self-contained
- single-file
- `OutputType=WinExe`

Responsibilities:

1. Enforce single instance using named mutex.
2. Validate packaged installation completeness.
3. Initialize user directories.
4. Materialize runtime environment variables.
5. Start the backend with hidden window and redirected logs.
6. Wait for backend health.
7. Start the packaged RPA runtime.
8. Open the browser after backend readiness.
9. Expose tray actions:
   - open Chatbot
   - view status
   - restart
   - export diagnostics
   - exit
10. Stop only launcher-owned processes.
11. Write launcher state to `%LOCALAPPDATA%\\Chatbot\\runtime\\launcher-state.json`.
12. Surface user-friendly errors while keeping stack traces in logs only.

### 2. Backend runtime

The backend uses a dedicated packaged CPython runtime with only locked runtime dependencies and required app/resources.

It must contain:

1. Fixed-version CPython standalone runtime for Windows x64.
2. LangBot runtime dependencies installed from `uv.lock`.
3. Backend source and entrypoint.
4. Templates and Alembic resources.
5. Frontend build path or copied frontend assets.
6. CA certificates and required DLLs.

It must not contain:

1. `.venv`
2. developer Python installation
3. pip caches
4. test/build/lint tools
5. `.git`
6. runtime data or logs

### 3. Connector runtime

The Connector runtime is independent from the backend runtime and contains:

1. separate packaged CPython runtime
2. a minimized `/vendor/wechat_decrypt` runtime tree
3. locked connector dependencies
4. runtime data written only under `%LOCALAPPDATA%\\Chatbot\\connectors`

The packaged runtime must not scan:

1. desktop folders
2. repository parent folders
3. system Python
4. external `wechat-decrypt` sources

### 4. RPA runtime

The Electron runtime must be assembled from a deterministic `win-unpacked` output copied wholesale into the release tree. The launcher starts it by a fixed executable path passed through environment/configuration.

### 5. Installer

The installer is built with Inno Setup using user-level installation, Chinese UI, VC++ runtime bootstrap, desktop/start-menu shortcuts, upgrade-aware replacement, and default preservation of user data on uninstall.

## Path Resolution Design

### Runtime mode switch

The packaged mode switch is:

- `CHATBOT_PACKAGED=1`

Compatibility variable retained:

- `LANGBOT_DATA_ROOT`

Additional packaged variables:

- `CHATBOT_INSTALL_ROOT`
- `CHATBOT_LOG_ROOT`
- `CHATBOT_RUNTIME_ROOT`
- `CHATBOT_CONNECTOR_ROOT`
- `CHATBOT_CONNECTOR_PYTHON`
- `CHATBOT_RPA_RUNTIME_PATH`

### Path policy

All packaged paths must resolve from:

1. install root
2. user data root
3. explicit environment variables

Packaged mode must not resolve from:

1. current working directory
2. desktop directory
3. repository parent directory
4. developer username
5. external relative paths

### Development mode preservation

Development startup through:

- `/C:/Users/33031/Desktop/bot/scripts/start-local.ps1`

must keep existing semantics for:

- backend development startup
- web dev server on port `3000`
- current backend dev port behavior

## Port and Health Design

Approved port strategy:

1. default backend port is `5302`
2. maintainers may override it through `launcher.json`
3. the launcher is the single source of truth for packaged startup port configuration
4. the launcher does not silently allocate random fallback ports
5. on conflict, it shows a clear user-facing error and writes detailed diagnostics to logs/diagnostic bundle

## Dependency Installation Policy

### Packaged runtime

Packaged runtime must never execute:

1. `pip install`
2. `uv sync`
3. `npm install`
4. `pnpm install`
5. `corepack`
6. online dependency downloads at startup

### Source runtime

Source mode may keep compatibility behavior where explicitly needed, but packaged mode must hard-fail with a clear code such as `PACKAGED_DEPENDENCY_MISSING` and instruct the user to reinstall the full release.

### Plugin dependency policy

Packaged mode must disable automatic installation of plugin `requirements.txt`.

## Frontend Packaging Design

The frontend is built during release build only:

1. install dependencies with locked package manager state
2. run production build
3. copy `web/dist` into release resources
4. serve packaged SPA from backend in packaged mode
5. support SPA fallback for direct route refreshes
6. never require Vite or Node.js at runtime

## vendor/wechat_decrypt Design

### Source governance

Only `/C:/Users/33031/Desktop/bot/vendor/wechat_decrypt` is releasable.

Desktop backup is used only to:

1. compare missing files
2. inspect changed implementations
3. selectively sync reviewed files into `vendor`

### Allowed content model

The release-oriented vendor tree will contain only the minimum recursively required subset for:

1. Connector CLI entry
2. WeChat MCP
3. WeCom MCP
4. WeCom Monitor
5. WeChat key extraction
6. WeCom key extraction
7. WeChat DB decryption
8. WeCom DB decryption

Plus release metadata:

1. `requirements.txt`
2. `requirements.lock.txt`
3. `source-manifest.json`
4. minimal release note

### Excluded by default

These stay excluded unless dependency analysis proves them necessary:

1. `main.py`
2. `monitor_web.py`
3. export scripts
4. image tools
5. voice tools
6. `build.bat`
7. legacy `WeChatDecrypt.spec`
8. full upstream docs/toolbox

## Build Pipeline Design

### New build entrypoint

Primary build script:

- `/C:/Users/33031/Desktop/bot/scripts/build-trial-release.ps1`

Required parameters:

- `-Version`
- `-WechatDecryptSource`
- `-VcRedistPath`
- `-OutputRoot`
- `-SkipTests`
- `-Offline`
- `-KeepWorkDirectory`

Behavior:

1. stop on first error
2. stage-by-stage logs with durations
3. deterministic output locations
4. no `git clean`
5. no unrelated directory deletions
6. no mutation of user `data`, `runtime`, or config
7. reusable build cache for downloaded Python runtimes
8. SHA-256 verification for fixed runtime inputs

### Runtime manifest

A fixed runtime manifest file records:

- Python version
- architecture
- runtime type
- download URL
- SHA-256

The build must refuse floating/latest runtime inputs.

### Verification

Release verification script:

- `/C:/Users/33031/Desktop/bot/scripts/verify-trial-release.ps1`

It validates:

1. directory completeness
2. manifest shape
3. SHA-256
4. no absolute build-machine paths
5. no sensitive data
6. packaged Python executables
7. critical module imports
8. RPA runtime presence
9. launcher start/stop behavior
10. backend health
11. frontend 200 + SPA route access
12. no use of system Python/Node/uv
13. no writes outside user data roots

Optional clean-machine validation helper:

- `/C:/Users/33031/Desktop/bot/packaging/sandbox/ChatbotTrial.wsb`

## Sensitive Data and Integrity Design

### Sensitive scan

The build performs a final release-directory scan and emits:

- `build-sensitive-scan.json`

It must fail on:

1. tokens
2. cookies
3. API keys
4. connector secrets
5. user databases
6. `.git`
7. `.venv`
8. developer absolute paths
9. desktop backup source paths

### Integrity outputs

The build also emits:

1. `manifest.json`
2. `SHA256SUMS.txt`
3. `build-report.json`

The launcher validates key files before startup; full per-file hashing remains available in the manifest for diagnostics and verification.

## File/Module Impact

### Expected modifications

Core path/runtime changes:

- `/C:/Users/33031/Desktop/bot/src/langbot/pkg/utils/paths.py`
- `/C:/Users/33031/Desktop/bot/src/langbot/pkg/core/bootutils/deps.py`
- `/C:/Users/33031/Desktop/bot/src/langbot/pkg/local_connectors/**`

RPA packaging changes:

- `/C:/Users/33031/Desktop/bot/apps/desktop-rpa-runtime/package.json`
- `/C:/Users/33031/Desktop/bot/apps/desktop-rpa-runtime/electron-builder.yml`
- `/C:/Users/33031/Desktop/bot/apps/desktop-rpa-runtime/scripts/**`

Release tooling:

- `/C:/Users/33031/Desktop/bot/packaging/**`
- `/C:/Users/33031/Desktop/bot/scripts/build-trial-release.ps1`
- `/C:/Users/33031/Desktop/bot/scripts/verify-trial-release.ps1`
- `/C:/Users/33031/Desktop/bot/scripts/test-trial-install.ps1`
- `/C:/Users/33031/Desktop/bot/docs/release/**`
- `/C:/Users/33031/Desktop/bot/.gitignore`

vendor scope updates:

- `/C:/Users/33031/Desktop/bot/vendor/wechat_decrypt/**`

### Expected new components

1. packaged backend entrypoint
2. launcher solution + app + tests
3. Inno Setup script
4. runtime manifest
5. release assembly helpers
6. sensitive scan helpers
7. release manifest generator

## Testing Strategy

### Unit tests

Add focused tests for:

1. source vs packaged path resolution
2. environment overrides
3. missing `LOCALAPPDATA`
4. Chinese usernames and spaces in paths
5. launcher config parsing
6. launcher environment construction
7. launcher state file handling
8. process ownership detection
9. diagnostics redaction

### Integration/build verification

Run:

1. backend test/lint
2. frontend lint/typecheck/build
3. RPA typecheck/lint/test/package
4. launcher restore/build/test/publish
5. full release build
6. release verification script

### Clean-machine validation

At least one Windows Sandbox or fresh VM validation is required for:

1. install
2. first launch
3. stop/restart
4. uninstall

If not completed in the current session, final reporting must explicitly mark it as **unverified**.

## Risks and Mitigations

### Risk 1: packaged mode accidentally falls back to source/developer behavior

Mitigation:

1. explicit packaged env variables
2. packaged-only assertions
3. tests for arbitrary working directory startup

### Risk 2: connector runtime unintentionally includes sensitive desktop/runtime data

Mitigation:

1. vendor-only source policy
2. allowlist-based file selection
3. sensitive scan before packaging

### Risk 3: Electron runtime assembly remains timestamp-driven

Mitigation:

1. introduce deterministic `package:win:dir`
2. copy only fixed `win-unpacked` output

### Risk 4: launcher kills unrelated processes

Mitigation:

1. persist launcher-owned process identity
2. validate executable path and creation time
3. force-kill only owned child processes after timeout

## Implementation Phases

1. packaged path system and tests
2. packaged no-install dependency behavior
3. vendor/wechat_decrypt minimal medium-set synchronization
4. backend and connector Python runtimes
5. deterministic Electron runtime packaging
6. .NET launcher and diagnostics
7. Inno Setup installer
8. end-to-end build/verify scripts
9. release docs and clean-machine checklist

## Acceptance Mapping

This design directly targets all required acceptance dimensions:

1. self-contained runtime startup
2. one-click user flow
3. isolated user data
4. real-send disabled by default
5. deterministic artifacts
6. installer + portable bundle
7. verification automation
8. clean-machine compatibility
