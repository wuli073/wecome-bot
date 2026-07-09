# Chatbot Windows x64 Trial Release Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a deterministic Windows x64 self-contained Chatbot trial release pipeline that produces both Portable ZIP and Inno Setup installer artifacts, runs from a graphical launcher without developer tools on the target machine, keeps all mutable user data under `%LOCALAPPDATA%\Chatbot`, and keeps real sending disabled by default.

**Architecture:** The release is assembled as a layered packaged app: a packaged backend Python runtime, an isolated packaged connector Python runtime built only from `vendor/wechat_decrypt`, a deterministic Electron Desktop RPA runtime copied from a fixed `win-unpacked` output, shared top-level `resources/`, and a `.NET 8` launcher as the only user-facing entrypoint. Build-time scripts, pinned runtime manifests, release-specific dependency locks, integrity manifests, and installer/verification automation are added incrementally so every late-stage artifact depends on already-validated lower layers instead of rediscovering paths or dependencies.

**Tech Stack:** Python 3.11+, Quart, uv, pytest, PowerShell 5.1+, pnpm 9, Vite, Electron Builder, Node.js 22, .NET 8 SDK, Inno Setup 6, Windows Sandbox, SHA-256 manifests.

---

## Baseline and guardrails

- Repository root: `C:\Users\33031\Desktop\bot`
- Required branch: `codex/integrate-wechat-decrypt`
- Observed HEAD when this plan was written: `05b3a83ee3526fc62cddca1d605d44e4ec21328a`
- Required design baseline: `C:\Users\33031\Desktop\bot\docs\superpowers\specs\2026-07-09-chatbot-windows-trial-release-design.md`
- Confirmed design commit exists: `05b3a83e`
- Existing unrelated working-tree changes must remain untouched.

## Repository observations that drive the task order

1. `C:\Users\33031\Desktop\bot\src\langbot\pkg\utils\paths.py` still falls back to source checkout and `cwd`, so packaged mode cannot safely start until path roots are split first.
2. `C:\Users\33031\Desktop\bot\src\langbot\pkg\core\bootutils\deps.py` can still install dependencies at runtime, so packaged mode needs an explicit hard-fail branch before any release startup flow is credible.
3. `C:\Users\33031\Desktop\bot\src\langbot\pkg\local_connectors\repository.py`, `...connectors\base.py`, and `...bundled_runtime.py` still assume `WecomeBot`, `sys.executable`, and source/vendor discovery, so connector isolation must be solved before launcher/installer work.
4. `C:\Users\33031\Desktop\bot\apps\desktop-rpa-runtime` still produces timestamped `dist-phase2-official\...` outputs through `package:win`, so deterministic RPA packaging must be normalized before any final release assembly script can depend on it.
5. `C:\Users\33031\Desktop\bot\packaging\` and `C:\Users\33031\Desktop\bot\docs\release\` do not exist yet, so build/installer/verification/docs tasks must explicitly create those surfaces instead of assuming them.

## File map

### Existing files that will be modified during implementation

- `C:\Users\33031\Desktop\bot\src\langbot\pkg\utils\paths.py`
- `C:\Users\33031\Desktop\bot\src\langbot\pkg\core\bootutils\deps.py`
- `C:\Users\33031\Desktop\bot\src\langbot\pkg\local_connectors\bundled_runtime.py`
- `C:\Users\33031\Desktop\bot\src\langbot\pkg\local_connectors\repository.py`
- `C:\Users\33031\Desktop\bot\src\langbot\pkg\local_connectors\connectors\base.py`
- `C:\Users\33031\Desktop\bot\src\langbot\pkg\local_connectors\uac_helper.py`
- `C:\Users\33031\Desktop\bot\src\langbot\pkg\local_connectors\service.py`
- `C:\Users\33031\Desktop\bot\src\langbot\pkg\desktop_automation\runtime_process.py`
- `C:\Users\33031\Desktop\bot\src\langbot\pkg\desktop_automation\service.py`
- `C:\Users\33031\Desktop\bot\src\langbot\pkg\api\http\controller\groups\bot_database_mode.py`
- `C:\Users\33031\Desktop\bot\apps\desktop-rpa-runtime\package.json`
- `C:\Users\33031\Desktop\bot\apps\desktop-rpa-runtime\electron-builder.yml`
- `C:\Users\33031\Desktop\bot\apps\desktop-rpa-runtime\scripts\package-win.mjs`
- `C:\Users\33031\Desktop\bot\vendor\wechat_decrypt\connector_cli.py`
- `C:\Users\33031\Desktop\bot\vendor\wechat_decrypt\connector_runtime.py`
- `C:\Users\33031\Desktop\bot\.gitignore`

### New packaging / release surfaces that implementation will introduce

- `C:\Users\33031\Desktop\bot\packaging\runtime-manifest.json`
- `C:\Users\33031\Desktop\bot\packaging\server\requirements.lock.txt`
- `C:\Users\33031\Desktop\bot\packaging\server\entrypoint.py`
- `C:\Users\33031\Desktop\bot\packaging\server\verify_runtime.py`
- `C:\Users\33031\Desktop\bot\packaging\launcher\ChatbotLauncher.sln`
- `C:\Users\33031\Desktop\bot\packaging\launcher\ChatbotLauncher\ChatbotLauncher.csproj`
- `C:\Users\33031\Desktop\bot\packaging\launcher\ChatbotLauncher\Program.cs`
- `C:\Users\33031\Desktop\bot\packaging\launcher\ChatbotLauncher\launcher.json`
- `C:\Users\33031\Desktop\bot\packaging\launcher\ChatbotLauncher.Tests\...`
- `C:\Users\33031\Desktop\bot\packaging\installer\ChatbotTrial.iss`
- `C:\Users\33031\Desktop\bot\packaging\sandbox\ChatbotTrial.wsb`
- `C:\Users\33031\Desktop\bot\scripts\build-trial-release.ps1`
- `C:\Users\33031\Desktop\bot\scripts\verify-trial-release.ps1`
- `C:\Users\33031\Desktop\bot\scripts\test-trial-install.ps1`
- `C:\Users\33031\Desktop\bot\docs\release\trial-user-guide.md`
- `C:\Users\33031\Desktop\bot\docs\release\trial-maintainer-guide.md`
- `C:\Users\33031\Desktop\bot\docs\release\clean-machine-checklist.md`

### Existing tests to extend

- `C:\Users\33031\Desktop\bot\tests\unit_tests\utils\test_paths.py`
- `C:\Users\33031\Desktop\bot\tests\unit_tests\core\test_bootutils_deps.py`
- `C:\Users\33031\Desktop\bot\tests\unit_tests\local_connectors\test_connectors_base.py`
- `C:\Users\33031\Desktop\bot\tests\unit_tests\core\test_app_local_connector_restore.py`
- `C:\Users\33031\Desktop\bot\tests\vendor_wechat_decrypt\test_connector_cli.py`
- `C:\Users\33031\Desktop\bot\tests\unit_tests\desktop_automation\test_runtime_process.py`
- `C:\Users\33031\Desktop\bot\tests\unit_tests\desktop_automation\test_service.py`
- `C:\Users\33031\Desktop\bot\tests\unit_tests\desktop_automation\test_api.py`

### New tests to add during implementation

- `C:\Users\33031\Desktop\bot\tests\unit_tests\utils\test_packaged_paths.py`
- `C:\Users\33031\Desktop\bot\tests\unit_tests\core\test_packaged_boot.py`
- `C:\Users\33031\Desktop\bot\tests\unit_tests\local_connectors\test_repository_paths.py`
- `C:\Users\33031\Desktop\bot\tests\unit_tests\local_connectors\test_uac_helper.py`
- `C:\Users\33031\Desktop\bot\tests\vendor_wechat_decrypt\test_runtime_layout.py`
- `C:\Users\33031\Desktop\bot\apps\desktop-rpa-runtime\tests\package-win-dir.test.ts`
- `C:\Users\33031\Desktop\bot\packaging\launcher\ChatbotLauncher.Tests\LauncherConfigTests.cs`
- `C:\Users\33031\Desktop\bot\packaging\launcher\ChatbotLauncher.Tests\LifecycleTests.cs`
- `C:\Users\33031\Desktop\bot\packaging\launcher\ChatbotLauncher.Tests\DiagnosticsTests.cs`

## Task dependency summary

1. Task 1 records the baseline and freezes investigation outputs that later tasks cite.
2. Tasks 2-3 establish packaged path roots and packaged no-install behavior; every later runtime/launcher/build task depends on these two behavioral switches.
3. Task 4 defines the releasable connector content; Task 5 creates all release lock files; Task 6 pins Python runtime sources.
4. Tasks 7-10 package the backend, connector, frontend, and RPA runtime layers into stable layouts that the launcher can target.
5. Tasks 11-13 add the launcher and prerequisite handling on top of already-stable packaged layers.
6. Task 14 performs baseline build + Portable directory assembly only; Task 15 adds scan/manifest/SHA/build-report; Task 16 adds Inno Setup; Task 17 performs complete end-to-end validation; Task 18 documents the finished release.

## External inputs and where they first become mandatory

| External input | First required task | Why it is external |
| --- | --- | --- |
| Pinned Windows x64 portable CPython artifact URL + SHA-256 | Task 6 | Must be selected from an upstream provider and recorded in `runtime-manifest.json` |
| `vc_redist.x64.exe` path + SHA-256 | Task 13 | Setup is the primary prerequisite executor; Launcher only uses it for Portable fallback. The repo must not vendor the binary in Git |
| .NET 8 SDK | Task 11 | Required to restore/build/publish the launcher |
| Inno Setup 6 | Task 16 | Required to build the installer |
| Windows Sandbox / fresh VM | Task 17 | Required for clean-machine validation that cannot be proven from the dev machine alone |

## Verification layers

- **Layer 1: unit behavior** — packaged paths, dependency gating, connector runtime isolation, launcher config parsing, diagnostics redaction.
- **Layer 2: component build** — frontend build, RPA package dir build, launcher build/test/publish.
- **Layer 3: baseline Portable directory assembly** — Task 14 `scripts/build-trial-release.ps1 -PortableOnly`.
- **Layer 4: scanned Portable artifact + installer assembly** — Task 15 scan/manifest/SHA/build-report, then Task 16 Inno Setup.
- **Layer 5: complete end-to-end validation** — Task 17 `scripts/verify-trial-release.ps1`, `scripts/test-trial-install.ps1`, and `packaging/sandbox/ChatbotTrial.wsb`.

---

## Task 1: Freeze baseline investigation and release constraints

### Goal

Capture the exact current repository/runtime/build baseline, document the investigation outputs that later tasks depend on, and make the implementation sequence auditable before any behavior changes are attempted.

### Prerequisites

- Approved spec exists at `C:\Users\33031\Desktop\bot\docs\superpowers\specs\2026-07-09-chatbot-windows-trial-release-design.md`.
- Branch is `codex/integrate-wechat-decrypt`.

### Order rationale

This task must come first because later tasks need explicit evidence for current ports, health endpoints, path assumptions, connector entrypoints, and RPA packaging outputs. Skipping it would force later tasks to guess file names or command surfaces, which violates the repo rule against inventing interfaces.

### Files

- Create: `C:\Users\33031\Desktop\bot\docs\release\trial-baseline-investigation.md`
- Reference only:  
  `C:\Users\33031\Desktop\bot\AGENTS.md`  
  `C:\Users\33031\Desktop\bot\docs\superpowers\specs\2026-07-09-chatbot-windows-trial-release-design.md`  
  `C:\Users\33031\Desktop\bot\pyproject.toml`  
  `C:\Users\33031\Desktop\bot\uv.lock`  
  `C:\Users\33031\Desktop\bot\web\package.json`  
  `C:\Users\33031\Desktop\bot\apps\desktop-rpa-runtime\package.json`  
  `C:\Users\33031\Desktop\bot\apps\desktop-rpa-runtime\electron-builder.yml`  
  `C:\Users\33031\Desktop\bot\scripts\start-local.ps1`  
  `C:\Users\33031\Desktop\bot\src\langbot\pkg\utils\paths.py`  
  `C:\Users\33031\Desktop\bot\src\langbot\pkg\core\bootutils\deps.py`  
  `C:\Users\33031\Desktop\bot\src\langbot\pkg\local_connectors\**\*`  
  `C:\Users\33031\Desktop\bot\vendor\wechat_decrypt\**\*`

### Implementation steps

- [ ] Run and record:
  - `git status --short`
  - `git branch --show-current`
  - `git rev-parse HEAD`
  - `git log -5 --oneline`
- [ ] Record the current backend packaged-risk findings:
  - default data root behavior
  - frontend path resolution behavior
  - runtime dependency installation behavior
  - desktop automation runtime status API path
- [ ] Add an interface investigation table named `Packaged startup interface contract` with these rows and fill every column from current code, not from assumptions:

  | Interface | Current code location | Current route / mechanism | Auth requirement | Packaged decision input | Later tasks that must cite this row |
  | --- | --- | --- | --- | --- | --- |
  | backend health | exact file + line range found in Task 1 | exact path such as `/healthz` after verification | auth or none | launcher health probe path | Tasks 7, 11, 12, 14, 17 |
  | Desktop RPA runtime status | exact file + line range found in Task 1 | exact path such as `/api/v1/desktop-automation/runtime/status` after verification | user token / packaged bypass / other verified mode | launcher observes backend-owned RPA only | Tasks 7, 10, 12, 17 |
  | graceful shutdown | exact file + line range found in Task 1 | control file / HTTP endpoint / signal path after verification | local-only / owner-only rule | launcher stop/restart flow | Tasks 7, 12, 17 |
  | packaged host/port source | exact file + line range found in Task 1 | config/env/CLI precedence after verification | maintainer `launcher.json` | Tasks 7, 11, 12, 14, 17 |

- [ ] Mark every later task that touches health, runtime status, graceful shutdown, or host/port as blocked until it cites the matching Task 1 table row.
- [ ] Record connector findings:
  - current `%LOCALAPPDATA%\WecomeBot\connectors` assumption
  - `sys.executable` usage
  - vendor runtime entrypoints used for MCP / monitor / extract / decrypt
  - UAC helper behavior and cancellation code
- [ ] Record frontend build findings:
  - production output directory
  - lockfile manager and build commands
- [ ] Record RPA runtime findings:
  - current `package:win` command
  - current output directory pattern
  - current packaged exe name
- [ ] Record build-tool prerequisites that are missing from the repo:
  - pinned Python runtime artifact
  - VC++ redistributable binary
  - .NET 8 SDK
  - Inno Setup
  - Windows Sandbox validation environment

### Forbidden changes

- Do not modify `approved spec`.
- Do not create `packaging\` code yet.
- Do not build frontend, RPA, installer, or launcher binaries.

### Tests and verification

- `git status --short`
- `git diff --check`

### Expected result

A baseline investigation document exists and explicitly lists the observed commands, outputs, paths, ports, and dependency surfaces that later implementation tasks will use.

### Acceptance criteria

- The document names the exact health endpoint and runtime-status endpoint already present in the repo.
- The document names the exact current connector root and packaged-risk fallbacks.
- The document identifies which later tasks depend on each investigation output.

### Suggested commit

`docs(release): capture Windows trial release baseline`

---

## Task 2: Introduce packaged path roots and runtime mode switching

### Goal

Add a packaged-mode path policy controlled by `CHATBOT_PACKAGED=1` so runtime roots resolve only from install root, user-data root, and explicit environment variables, while preserving existing source-mode behavior.

### Prerequisites

- Task 1 baseline document exists.

### Order rationale

This task must precede dependency locking, backend packaging, connector packaging, and launcher work because every later release surface depends on trustworthy path resolution. If packaged mode can still fall back to `cwd` or repo-relative guessing, no subsequent artifact is trustworthy.

### Files

- Modify: `C:\Users\33031\Desktop\bot\src\langbot\pkg\utils\paths.py`
- Create: `C:\Users\33031\Desktop\bot\tests\unit_tests\utils\test_packaged_paths.py`
- Modify: `C:\Users\33031\Desktop\bot\tests\unit_tests\utils\test_paths.py`

### Implementation steps

- [ ] Add explicit helpers in `paths.py` for:
  - packaged mode detection
  - install root resolution
  - user data root resolution
  - shared `resources/` root resolution
  - per-resource overrides:
    `CHATBOT_WEB_ROOT`, `CHATBOT_TEMPLATE_ROOT`, `CHATBOT_MIGRATION_ROOT`, `CHATBOT_DEFAULTS_ROOT`
- [ ] Keep `LANGBOT_DATA_ROOT` as a compatibility override, but make packaged mode prefer `%LOCALAPPDATA%\Chatbot` when explicit overrides are absent.
- [ ] Add a packaged-only error for missing `LOCALAPPDATA` instead of silently falling back to `cwd`.
- [ ] Make frontend/resource/template/migration/default roots resolve from the single top-level `resources\` tree in packaged mode.
- [ ] Preserve `scripts/start-local.ps1` source-mode semantics and current source checkout detection.
- [ ] Add focused tests for:
  - packaged install root + user-data root resolution
  - environment override precedence
  - missing `LOCALAPPDATA`
  - arbitrary working directory startup
  - Chinese usernames and spaces in paths

### Forbidden changes

- Do not introduce launcher-specific startup logic here.
- Do not change backend port behavior here.
- Do not write release assembly scripts yet.

### Tests and verification

- `uv run pytest tests/unit_tests/utils/test_paths.py tests/unit_tests/utils/test_packaged_paths.py -q`
- `git diff --check`

### Expected result

Packaged-mode path behavior is explicit, test-covered, and fully separated from source-mode `cwd`/repo discovery.

### Acceptance criteria

- Packaged mode never resolves data/resources from `cwd`.
- Packaged mode can start from arbitrary working directories.
- Tests cover Chinese and space-containing path roots.

### Suggested commit

`feat(release): add packaged path root resolution`

---

## Task 3: Disable packaged runtime dependency installation and plugin auto-install

### Goal

Ensure packaged mode never attempts `pip install`, `uv sync`, or plugin `requirements.txt` installation at startup, and instead returns a clear packaged dependency failure signal.

### Prerequisites

- Task 2 packaged-mode switch is available.

### Order rationale

This task must follow the path switch and precede any packaged runtime assembly because the release cannot claim to be self-contained while startup still mutates dependencies or installs plugin requirements.

### Files

- Modify: `C:\Users\33031\Desktop\bot\src\langbot\pkg\core\bootutils\deps.py`
- Modify: `C:\Users\33031\Desktop\bot\tests\unit_tests\core\test_bootutils_deps.py`
- Create: `C:\Users\33031\Desktop\bot\tests\unit_tests\core\test_packaged_boot.py`

### Implementation steps

- [ ] Add packaged-mode checks in `deps.py` so:
  - `check_deps()` still reports missing modules
  - `install_deps()` is never called in packaged mode
  - missing packaged dependencies produce a stable code such as `PACKAGED_DEPENDENCY_MISSING`
- [ ] Disable plugin `requirements.txt` auto-install when `CHATBOT_PACKAGED=1`.
- [ ] Add structured logging for packaged dependency failures without suggesting end-user shell commands.
- [ ] Add unit tests covering:
  - source mode still keeps current behavior
  - packaged mode blocks install attempts
  - plugin dependency auto-install is skipped in packaged mode
  - failure code/message shape is stable

### Forbidden changes

- Do not generate lock files yet.
- Do not modify `pyproject.toml`.

### Tests and verification

- `uv run pytest tests/unit_tests/core/test_bootutils_deps.py tests/unit_tests/core/test_packaged_boot.py -q`
- `uv run ruff check src/langbot/pkg/core/bootutils/deps.py tests/unit_tests/core/test_bootutils_deps.py tests/unit_tests/core/test_packaged_boot.py`

### Expected result

Packaged startup either runs with already-bundled dependencies or fails fast with a packaged-specific error; it never installs anything online or from plugin requirement files.

### Acceptance criteria

- Packaged mode never calls `pip.main(...)`.
- Packaged mode never installs plugin requirements.
- Failure mode is test-covered and deterministic.

### Suggested commit

`feat(release): block dependency installs in packaged mode`

---

## Task 4: Reduce `vendor/wechat_decrypt` to a releasable medium set with audit metadata

### Goal

Turn `vendor/wechat_decrypt` into the only releasable connector source tree, define the minimum included runtime subset, and add release metadata plus exclusion rules without packaging any desktop backup content.

### Prerequisites

- Tasks 1-3 are complete.

### Order rationale

This task must happen before lock export, connector packaging, and build scripting because the release cannot lock/install/package connector dependencies until the releasable file set is explicitly defined.

### Files

- Modify: `C:\Users\33031\Desktop\bot\vendor\wechat_decrypt\connector_cli.py`
- Modify: `C:\Users\33031\Desktop\bot\vendor\wechat_decrypt\connector_runtime.py`
- Create: `C:\Users\33031\Desktop\bot\vendor\wechat_decrypt\requirements.txt`
- Create: `C:\Users\33031\Desktop\bot\vendor\wechat_decrypt\source-manifest.json`
- Create: `C:\Users\33031\Desktop\bot\vendor\wechat_decrypt\README.release.md`
- Create: `C:\Users\33031\Desktop\bot\tests\vendor_wechat_decrypt\test_runtime_layout.py`
- Modify: `C:\Users\33031\Desktop\bot\tests\vendor_wechat_decrypt\test_connector_cli.py`
- Modify: `C:\Users\33031\Desktop\bot\.gitignore`

### Implementation steps

- [ ] Read the Task 1 `Packaged startup interface contract` before naming Connector MCP entrypoints.
- [ ] Perform a recursive dependency audit from the actual product entrypoints confirmed by Task 1. The expected current stdio MCP entrypoint candidates are:
  - `mcp_server.py`
  - `mcp_wxwork_server.py`
  - `wxwork_message_monitor.py`
  - `connector_cli.py`
  - `find_all_keys_windows.py`
  - `find_wxwork_keys.py`
  - `decrypt_db.py`
  - `decrypt_wxwork_db.py`
- [ ] If Task 1 confirms different product entrypoints, update `source-manifest.json` to cite the exact finding and use those files; do not assume HTTP-suffixed alternative server filenames are product entrypoints without evidence.
- [ ] Record dynamic imports, subprocess calls, config files, DLL/runtime assumptions, and required ancillary modules in `source-manifest.json`.
- [ ] Add `README.release.md` that documents:
  - what is included
  - what is excluded
  - that desktop backup is audit-only
  - how `source-manifest.json` should be maintained
- [ ] Add `requirements.txt` listing direct runtime dependencies only. Do not create or modify `vendor\wechat_decrypt\requirements.lock.txt` in Task 4; all lock files are created by Task 5.
- [ ] Add tests that assert connector runtime layout stays self-contained and does not expose secret values or relative runtime-dir acceptance regressions.
- [ ] Update `.gitignore` only if new runtime-output patterns are discovered during the audit.

### Forbidden changes

- Do not sync files directly from a desktop backup into final packaging outputs.
- Do not add optional toolbox files unless dependency analysis proves they are required.
- Do not create `requirements.lock.txt`; Task 5 owns every release lock file.
- Do not generate release ZIPs yet.

### Tests and verification

- `uv run pytest tests/vendor_wechat_decrypt/test_connector_cli.py tests/vendor_wechat_decrypt/test_runtime_layout.py -q`
- `git diff --check`

### Expected result

`vendor/wechat_decrypt` becomes an auditable, minimal, releasable connector source tree with explicit manifest metadata and no accidental inclusion of desktop backup content.

### Acceptance criteria

- `source-manifest.json` lists required runtime files and excluded files, and cites the Task 1-confirmed MCP entrypoints.
- Desktop backup paths are not part of the releasable tree.
- Connector tests still pass with the narrowed source model.

### Suggested commit

`feat(release): define releasable vendor wechat decrypt set`

---

## Task 5: Create release-specific dependency lock files for server and connector runtimes

### Goal

Derive Windows x64 runtime-only dependency locks from repository authorities without shipping dev/build tools inside packaged Python runtimes.

### Prerequisites

- Task 4 direct dependency list exists for `vendor/wechat_decrypt`.

### Order rationale

This task must precede Python runtime assembly because backend and connector runtimes must install from release-specific locks, not from the repo-wide mixed development environment.

### Files

- Create: `C:\Users\33031\Desktop\bot\packaging\server\requirements.lock.txt`
- Create: `C:\Users\33031\Desktop\bot\vendor\wechat_decrypt\requirements.lock.txt`
- Create: `C:\Users\33031\Desktop\bot\docs\release\dependency-lock-notes.md`
- Create: `C:\Users\33031\Desktop\bot\packaging\build\verify-dependency-locks.py`

### Implementation steps

- [ ] Define the exact export procedure from `uv.lock` for Windows x64 runtime-only dependencies.
- [ ] Generate `packaging\server\requirements.lock.txt` from the backend runtime dependency subset.
- [ ] Generate or refresh `vendor\wechat_decrypt\requirements.lock.txt` from the connector direct requirements.
- [ ] Ensure lock generation includes exact versions and hashes where the export/install flow supports them.
- [ ] Document the export command and validation rules in `dependency-lock-notes.md`.
- [ ] Create `packaging\build\verify-dependency-locks.py` as the dedicated Windows PowerShell-compatible Python verifier for the two lock files.
- [ ] Add a verification step that packaged runtimes must not contain:
  - `pytest`
  - `ruff`
  - `mypy`
  - `pre-commit`
  - `uv`

### Forbidden changes

- Do not mutate `pyproject.toml` dependency declarations.
- Do not re-resolve dependencies on end-user machines.

### Tests and verification

- `uv sync --frozen --dev`
- `uv run python packaging\build\verify-dependency-locks.py`

`packaging\build\verify-dependency-locks.py` must be executable from Windows PowerShell, must parse each requirement line to a normalized distribution name, must compare complete package names only, and must validate exactly:

```python
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LOCKS = [
    ROOT / 'packaging' / 'server' / 'requirements.lock.txt',
    ROOT / 'vendor' / 'wechat_decrypt' / 'requirements.lock.txt',
]
FORBIDDEN = {'pytest', 'ruff', 'mypy', 'pre-commit', 'uv'}
NAME_RE = re.compile(r'^([A-Za-z0-9][A-Za-z0-9._-]*)\s*(?:\[|==|~=|!=|<=|>=|<|>|===|@|;|\s|$)')


def canonicalize_name(name: str) -> str:
    return re.sub(r'[-_.]+', '-', name).lower()


def iter_requirement_names(lock_path: Path):
    for line_number, raw_line in enumerate(lock_path.read_text(encoding='utf-8').splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith('#'):
            continue
        if line.endswith('\\'):
            line = line[:-1].rstrip()
        if line.startswith('-'):
            continue
        line = line.split(' #', 1)[0].strip()
        match = NAME_RE.match(line)
        if not match:
            raise SystemExit(f'cannot parse requirement name in {lock_path}:{line_number}: {raw_line}')
        yield canonicalize_name(match.group(1))


for lock_path in LOCKS:
    if not lock_path.exists():
        raise SystemExit(f'missing lock file: {lock_path}')
    names = set(iter_requirement_names(lock_path))
    forbidden_found = names & FORBIDDEN
    if forbidden_found:
        raise SystemExit(f'forbidden package names {sorted(forbidden_found)} found in {lock_path}')
print('dependency locks verified')
```

### Expected result

Both packaged Python runtimes have explicit Windows x64 lock files that are separate from repo development tooling.

### Acceptance criteria

- Lock generation method is documented.
- Both lock files exist.
- Forbidden dev/build tools are absent from the lock outputs by normalized complete package-name comparison, not by substring search.

### Suggested commit

`feat(release): add release dependency lock files`

---

## Task 6: Pin the packaged Python runtime provider and cache policy

### Goal

Choose and record the single allowed Windows x64 portable CPython artifact(s), their exact URLs, SHA-256 values, extraction expectations, and offline cache behavior for both backend and connector runtime roles.

### Prerequisites

- Task 5 release lock strategy is complete.

### Order rationale

This task must precede backend/connector runtime assembly and the unified build script because later tasks need a fixed runtime manifest instead of floating downloads or guessed extraction layouts.

### Files

- Create: `C:\Users\33031\Desktop\bot\packaging\runtime-manifest.json`
- Create: `C:\Users\33031\Desktop\bot\packaging\runtime-cache-notes.md`
- Create: `C:\Users\33031\Desktop\bot\packaging\build\verify-runtime-manifest.py`

### Implementation steps

- [ ] Investigate candidate Windows x64 portable CPython providers and select the one artifact model approved for this release.
- [ ] Record in `runtime-manifest.json` for each runtime role:
  - provider
  - exact version
  - artifact URL
  - SHA-256
  - archive type
  - extracted layout
  - whether `pip` is present upstream
  - `site-packages` enablement approach
  - license file source
- [ ] Create `packaging\build\verify-runtime-manifest.py` as the dedicated Windows PowerShell-compatible Python verifier for `runtime-manifest.json`.
- [ ] Define cache directory behavior for online and `-Offline` builds.
- [ ] Document manifest validation and cache population rules in `runtime-cache-notes.md`.
- [ ] If a provider cannot be selected yet, block execution here until the exact artifact URL + SHA-256 are known; do not invent them.

### Forbidden changes

- Do not use `"latest"` or floating URLs.
- Do not build runtimes yet.

### Tests and verification

- `uv run python packaging\build\verify-runtime-manifest.py`

`packaging\build\verify-runtime-manifest.py` must be executable from Windows PowerShell and must validate exactly:

```python
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / 'packaging' / 'runtime-manifest.json'
data = json.loads(MANIFEST.read_text(encoding='utf-8'))
for role in ('server', 'connector'):
    entry = data.get(role) or {}
    for key in ('provider', 'version', 'url', 'sha256', 'archiveType', 'artifactName'):
        if not entry.get(key):
            raise SystemExit(f'{role}.{key} is required')
    if str(entry['url']).lower().endswith('/latest') or 'latest' in str(entry['url']).lower():
        raise SystemExit(f'{role}.url must not be floating/latest')
    if str(entry['sha256']).lower() in {'', 'latest'} or len(str(entry['sha256'])) != 64:
        raise SystemExit(f'{role}.sha256 must be a fixed 64-character SHA-256')
print('runtime manifest verified')
```

### Expected result

The release has a pinned runtime manifest that later tasks can consume without any ambiguity.

### Acceptance criteria

- `runtime-manifest.json` contains exact URLs and SHA-256 values.
- Offline cache behavior is explicitly defined.
- No floating runtime artifacts remain.

### Suggested commit

`feat(release): pin packaged python runtime manifest`

---

## Task 7: Add packaged backend entrypoint and resource-root startup wiring

### Goal

Make the backend start from the packaged Python runtime using only launcher-provided host/port and packaged resource roots, while keeping user data under `%LOCALAPPDATA%\Chatbot` and preserving backend ownership of Desktop RPA runtime lifecycle.

### Prerequisites

- Tasks 2, 3, 5, and 6 are complete.

### Order rationale

This task must happen before launcher implementation because the launcher needs a stable packaged backend entrypoint and a reliable health/rpa-status contract to supervise.

### Files

- Create: `C:\Users\33031\Desktop\bot\packaging\server\entrypoint.py`
- Create: `C:\Users\33031\Desktop\bot\packaging\server\verify_runtime.py`
- Modify: `C:\Users\33031\Desktop\bot\src\langbot\pkg\desktop_automation\runtime_process.py`
- Modify: `C:\Users\33031\Desktop\bot\src\langbot\pkg\desktop_automation\service.py`
- Modify: `C:\Users\33031\Desktop\bot\src\langbot\pkg\api\http\controller\groups\bot_database_mode.py`
- Modify: `C:\Users\33031\Desktop\bot\tests\unit_tests\core\test_packaged_boot.py`
- Modify: `C:\Users\33031\Desktop\bot\tests\unit_tests\desktop_automation\test_service.py`
- Modify: `C:\Users\33031\Desktop\bot\tests\unit_tests\desktop_automation\test_api.py`

### Implementation steps

- [ ] Cite the Task 1 `Packaged startup interface contract` rows for backend health, runtime status, graceful shutdown, and packaged host/port source before changing startup code.
- [ ] Create a packaged backend entrypoint that:
  - sets `CHATBOT_PACKAGED=1`
  - wires shared resource root environment variables
  - sets data/log/runtime roots under `%LOCALAPPDATA%\Chatbot`
  - starts the existing LangBot app via explicit host/port arguments or environment variables
- [ ] Ensure packaged host/port comes only from the Task 1-confirmed launcher configuration input and always binds `127.0.0.1`.
- [ ] Keep the Task 1-confirmed health and runtime-status routes as the launcher observation surfaces; do not hard-code paths in this task without citing the investigation table.
- [ ] Make Desktop RPA runtime path injectable via `CHATBOT_RPA_RUNTIME_PATH` while keeping backend as the only lifecycle owner.
- [ ] Add graceful shutdown handling so launcher stop requests can wait for backend-owned runtime teardown.
- [ ] Add focused tests for packaged backend env construction and runtime-status reachability assumptions.

### Forbidden changes

- Do not add launcher code yet.
- Do not allow packaged mode to derive host/port from `config.yaml`.
- Do not let launcher directly start or stop RPA.

### Tests and verification

- `uv run pytest tests/unit_tests/core/test_packaged_boot.py tests/unit_tests/desktop_automation/test_service.py tests/unit_tests/desktop_automation/test_api.py -q`
- `uv run ruff check packaging/server src/langbot/pkg/desktop_automation src/langbot/pkg/api/http/controller/groups/bot_database_mode.py tests/unit_tests/core/test_packaged_boot.py`

### Expected result

There is a stable packaged backend bootstrap surface that the launcher can invoke, and it exposes consistent health/runtime-status behavior on loopback only.

### Acceptance criteria

- Packaged backend binds only to `127.0.0.1`.
- Backend host/port comes from one packaged source.
- Backend still owns RPA runtime lifecycle.

### Suggested commit

`feat(release): add packaged backend startup entrypoint`

---

## Task 8: Isolate connector runtime roots, packaged Python selection, and UAC helper behavior

### Goal

Make local connectors run from the packaged connector Python runtime and packaged vendor tree, write state only under `%LOCALAPPDATA%\Chatbot\connectors`, and stop using `sys.executable`, `WecomeBot`, and source/vendor discovery fallbacks in packaged mode.

### Prerequisites

- Tasks 2-7 are complete.

### Order rationale

This task must precede full assembly, launcher work, and installer work because the release cannot be self-contained while connectors still fall back to source trees or dev Python.

### Files

- Modify: `C:\Users\33031\Desktop\bot\src\langbot\pkg\local_connectors\bundled_runtime.py`
- Modify: `C:\Users\33031\Desktop\bot\src\langbot\pkg\local_connectors\repository.py`
- Modify: `C:\Users\33031\Desktop\bot\src\langbot\pkg\local_connectors\connectors\base.py`
- Modify: `C:\Users\33031\Desktop\bot\src\langbot\pkg\local_connectors\uac_helper.py`
- Modify: `C:\Users\33031\Desktop\bot\src\langbot\pkg\local_connectors\service.py`
- Modify: `C:\Users\33031\Desktop\bot\tests\unit_tests\local_connectors\test_connectors_base.py`
- Create: `C:\Users\33031\Desktop\bot\tests\unit_tests\local_connectors\test_repository_paths.py`
- Create: `C:\Users\33031\Desktop\bot\tests\unit_tests\local_connectors\test_uac_helper.py`
- Modify: `C:\Users\33031\Desktop\bot\tests\unit_tests\core\test_app_local_connector_restore.py`

### Implementation steps

- [ ] Add packaged connector root resolution using:
  - `CHATBOT_CONNECTOR_ROOT`
  - `CHATBOT_CONNECTOR_PYTHON`
  - packaged `vendor\wechat_decrypt`
- [ ] Change repository user-data root from `%LOCALAPPDATA%\WecomeBot\connectors` to `%LOCALAPPDATA%\Chatbot\connectors` in packaged mode, while preserving source/dev behavior where required.
- [ ] Stop using `sys.executable` as the packaged connector Python fallback.
- [ ] Ensure monitor, MCP, extract-key, decrypt, and UAC helper flows all use the packaged connector runtime paths.
- [ ] Add cleanup handling for helper temp/result files and preserve `UAC_CANCELLED`.
- [ ] Add tests for:
  - Chinese/space-containing connector roots
  - missing packaged connector python
  - packaged root precedence
  - temp-file cleanup
  - packaged restore/start behavior

### Forbidden changes

- Do not scan desktop backup or repo parent folders in packaged mode.
- Do not allow system Python as a packaged fallback.

### Tests and verification

- `uv run pytest tests/unit_tests/local_connectors/test_connectors_base.py tests/unit_tests/local_connectors/test_repository_paths.py tests/unit_tests/local_connectors/test_uac_helper.py tests/unit_tests/core/test_app_local_connector_restore.py -q`
- `uv run ruff check src/langbot/pkg/local_connectors tests/unit_tests/local_connectors tests/unit_tests/core/test_app_local_connector_restore.py`

### Expected result

Connector runtime behavior is fully isolated to packaged inputs and packaged/user-data roots.

### Acceptance criteria

- Packaged connectors do not use `sys.executable`.
- Packaged connectors do not write to `%LOCALAPPDATA%\WecomeBot`.
- UAC helper behavior is deterministic and test-covered.

### Suggested commit

`feat(release): isolate packaged connector runtime`

---

## Task 9: Package frontend production assets into shared resources

### Goal

Make the release serve the built SPA from `resources\web\dist` and remove any packaged dependence on Vite or port `3000`.

### Prerequisites

- Tasks 2 and 7 are complete.

### Order rationale

This task must precede build scripting and launcher browser-opening logic because the launcher needs a packaged backend that can serve the SPA itself.

### Files

- Modify only if investigation proves the existing release build command is missing: `C:\Users\33031\Desktop\bot\web\package.json`
- Create: `C:\Users\33031\Desktop\bot\packaging\web\copy-web-dist.ps1`
- Create: `C:\Users\33031\Desktop\bot\tests\unit_tests\utils\test_packaged_web_root.py`

### Implementation steps

- [ ] Read `C:\Users\33031\Desktop\bot\web\package.json` first and record whether an existing production build command already exists.
- [ ] Preserve existing frontend dev scripts.
- [ ] Modify `web\package.json` only when the investigation proves no usable release/production build command exists. If the existing `build` script is sufficient, leave `web\package.json` unchanged and make build orchestration call that existing script.
- [ ] Add release-oriented copy/verification logic that stages `web\dist` into `resources\web\dist`.
- [ ] Define how the build script will run locked install + production build.
- [ ] Ensure packaged backend resource lookup supports SPA fallback for direct route refreshes.
- [ ] Add a small verification test/script for:
  - `index.html` presence
  - static asset availability
  - SPA route fallback under packaged resource roots

### Forbidden changes

- Do not change the dev server model in `scripts/start-local.ps1`.
- Do not modify `web\package.json` solely to rename or duplicate an existing production build command.
- Do not introduce runtime use of port `3000` in packaged mode.

### Tests and verification

- `cd C:\Users\33031\Desktop\bot\web; corepack pnpm install --frozen-lockfile`
- `cd C:\Users\33031\Desktop\bot\web; corepack pnpm run build`
- `uv run pytest tests/unit_tests/utils/test_packaged_web_root.py -q`

### Expected result

The packaged backend can serve built frontend assets from `resources\web\dist` with SPA fallback and no runtime dependence on Vite.

### Acceptance criteria

- Packaged runtime has no dependency on frontend dev server.
- `resources\web\dist` is the single packaged web asset location.
- Sub-route refresh behavior is explicitly verified.

### Suggested commit

`feat(release): package frontend dist into shared resources`

---

## Task 10: Make Desktop RPA runtime packaging deterministic and backend-addressable

### Goal

Replace timestamp-discovery-driven RPA packaging with a fixed `package:win:dir` output and make backend packaged mode target a stable runtime executable path.

### Prerequisites

- Task 7 packaged backend wiring exists.

### Order rationale

This task must precede launcher and unified build work because the launcher needs a fixed runtime directory to validate and pass to the backend.

### Files

- Modify: `C:\Users\33031\Desktop\bot\apps\desktop-rpa-runtime\package.json`
- Modify: `C:\Users\33031\Desktop\bot\apps\desktop-rpa-runtime\electron-builder.yml`
- Modify: `C:\Users\33031\Desktop\bot\apps\desktop-rpa-runtime\scripts\package-win.mjs`
- Create: `C:\Users\33031\Desktop\bot\apps\desktop-rpa-runtime\tests\package-win-dir.test.ts`
- Modify: `C:\Users\33031\Desktop\bot\src\langbot\pkg\desktop_automation\runtime_process.py`

### Implementation steps

- [ ] Add a deterministic `package:win:dir` npm script that produces a fixed `win-unpacked` output directory.
- [ ] Stop using timestamped folder discovery for release assembly.
- [ ] Ensure native rebuild expectations for `robotjs`, `active-win`, and `node-window-manager` are documented inside the packaging script flow.
- [ ] Make backend packaged mode validate the fixed runtime exe path instead of scanning `dist-phase2-official`.
- [ ] Add tests for:
  - deterministic output directory calculation
  - stable exe path naming
  - no duplicate runtime instance startup assumptions in packaged mode

### Forbidden changes

- Do not let launcher directly manage RPA processes.
- Do not reintroduce timestamp directory discovery for official release assembly.

### Tests and verification

- `cd C:\Users\33031\Desktop\bot\apps\desktop-rpa-runtime; npm ci`
- `cd C:\Users\33031\Desktop\bot\apps\desktop-rpa-runtime; npm run typecheck`
- `cd C:\Users\33031\Desktop\bot\apps\desktop-rpa-runtime; npm run lint`
- `cd C:\Users\33031\Desktop\bot\apps\desktop-rpa-runtime; npm test`
- `cd C:\Users\33031\Desktop\bot\apps\desktop-rpa-runtime; npm run rebuild:native`
- `cd C:\Users\33031\Desktop\bot\apps\desktop-rpa-runtime; npm run package:win:dir`

### Expected result

The RPA runtime has a deterministic directory output and a fixed packaged exe path that the backend can own.

### Acceptance criteria

- Release assembly no longer depends on timestamp folder scanning.
- Fixed runtime exe path is documented and test-covered.
- Backend remains the only RPA lifecycle owner.

### Suggested commit

`feat(release): make desktop rpa packaging deterministic`

---

## Task 11: Scaffold the .NET launcher solution, config schema, and diagnostics model

### Goal

Create the Windows GUI launcher solution and its configuration/state/diagnostics contracts before implementing lifecycle behavior.

### Prerequisites

- Tasks 7-10 are complete.
- .NET 8 SDK is available locally.

### Order rationale

This task must come before launcher lifecycle implementation because the config schema, launcher-state schema, diagnostics bundle format, and publish model must be frozen before process control logic is added on top.

### Files

- Create: `C:\Users\33031\Desktop\bot\packaging\launcher\ChatbotLauncher.sln`
- Create: `C:\Users\33031\Desktop\bot\packaging\launcher\ChatbotLauncher\ChatbotLauncher.csproj`
- Create: `C:\Users\33031\Desktop\bot\packaging\launcher\ChatbotLauncher\Program.cs`
- Create: `C:\Users\33031\Desktop\bot\packaging\launcher\ChatbotLauncher\launcher.json`
- Create: `C:\Users\33031\Desktop\bot\packaging\launcher\ChatbotLauncher\launcher-state.schema.json`
- Create: `C:\Users\33031\Desktop\bot\packaging\launcher\ChatbotLauncher.Tests\LauncherConfigTests.cs`
- Create: `C:\Users\33031\Desktop\bot\packaging\launcher\ChatbotLauncher.Tests\DiagnosticsTests.cs`

### Implementation steps

- [ ] Create a `.NET 8` Windows GUI app configured for:
  - `win-x64`
  - self-contained publish
  - single-file publish
  - `OutputType=WinExe`
- [ ] Define `launcher.json` schema including:
  - backend host
  - backend port
  - health path
  - runtime-status path
  - startup timeout
- [ ] Define `launcher-state.json` schema under `%LOCALAPPDATA%\Chatbot\runtime`.
- [ ] Define diagnostics ZIP/report shape with log redaction rules and legacy-directory detection notes.
- [ ] Add tests for:
  - config parsing
  - invalid port/host rejection
  - diagnostics redaction of secrets and absolute paths

### Forbidden changes

- Do not implement process launch/stop yet.
- Do not start or stop RPA directly.

### Tests and verification

- `dotnet restore C:\Users\33031\Desktop\bot\packaging\launcher\ChatbotLauncher.sln`
- `dotnet build C:\Users\33031\Desktop\bot\packaging\launcher\ChatbotLauncher.sln -c Release`
- `dotnet test C:\Users\33031\Desktop\bot\packaging\launcher\ChatbotLauncher.sln -c Release`

### Expected result

The launcher has a compilable solution and stable contract files for configuration, state, and diagnostics.

### Acceptance criteria

- The launcher builds as a GUI app.
- Config/state schema files exist.
- Diagnostics redaction rules are test-covered.

### Suggested commit

`feat(release): scaffold trial launcher solution`

---

## Task 12: Implement launcher lifecycle, single-instance ownership, and browser/tray flows

### Goal

Implement the launcher as the only user-facing process that starts the backend, waits for health/runtime readiness, opens the browser, exposes tray controls, and shuts down only launcher-owned backend process trees.

### Prerequisites

- Task 11 launcher scaffolding is complete.
- Tasks 7-10 provide stable packaged backend and runtime paths.

### Order rationale

This task follows launcher scaffolding and packaged runtime stabilization because lifecycle code depends on the exact launcher config schema, packaged backend entrypoint, and fixed RPA runtime path established earlier.

### Files

- Modify: `C:\Users\33031\Desktop\bot\packaging\launcher\ChatbotLauncher\Program.cs`
- Create: `C:\Users\33031\Desktop\bot\packaging\launcher\ChatbotLauncher\LauncherProcessManager.cs`
- Create: `C:\Users\33031\Desktop\bot\packaging\launcher\ChatbotLauncher\TrayController.cs`
- Create: `C:\Users\33031\Desktop\bot\packaging\launcher\ChatbotLauncher.Tests\LifecycleTests.cs`

### Implementation steps

- [ ] Implement named mutex single-instance enforcement.
- [ ] Validate installation completeness before first launch:
  - backend runtime exists
  - connector runtime exists
  - shared resources exist
  - RPA runtime exe exists
- [ ] Materialize packaged environment variables, including packaged safety defaults:
  - `LANGBOT_BROADCAST_SEND_ENABLED=0`
  - `LANGBOT_BROADCAST_SEND_ALLOW_CONNECTORS=`
  - `LANGBOT_RPA_ALLOW_AUTO_SEND=0`
  - `LANGBOT_RPA_FORCE_DISABLE_SEND=1`
- [ ] Start backend hidden, read Task 1-confirmed `healthPath` and `runtimeStatusPath` from `launcher.json`, wait for `healthPath`, then poll `runtimeStatusPath` until ready; do not hard-code route literals in Launcher lifecycle code.
- [ ] Open the browser only after backend readiness.
- [ ] Implement tray actions:
  - open
  - status
  - restart
  - export diagnostics
  - exit
- [ ] Implement graceful shutdown request and only force-kill launcher-owned backend process trees after timeout with PID/path/create-time validation.
- [ ] Add tests for:
  - port conflict errors
  - ownership validation
  - default-disabled real-send state
  - runtime-status observation
  - `launcher.json` `healthPath` / `runtimeStatusPath` override behavior

### Forbidden changes

- Do not directly start or terminate RPA runtime from the launcher.
- Do not silently pick random fallback ports.
- Do not hard-code health or runtime-status route strings in launcher lifecycle code; they must come from Task 1-confirmed `launcher.json` fields.

### Tests and verification

- `dotnet build C:\Users\33031\Desktop\bot\packaging\launcher\ChatbotLauncher.sln -c Release`
- `dotnet test C:\Users\33031\Desktop\bot\packaging\launcher\ChatbotLauncher.sln -c Release`
- `dotnet publish C:\Users\33031\Desktop\bot\packaging\launcher\ChatbotLauncher\ChatbotLauncher.csproj -c Release -r win-x64 --self-contained true`

### Expected result

The launcher can supervise the packaged backend, observe backend-managed RPA readiness, and provide the entire end-user start/stop/restart experience.

### Acceptance criteria

- Only `ChatbotLauncher.exe` is user-facing.
- Launcher does not control RPA directly.
- Port conflicts and ownership errors are user-friendly and deterministic.

### Suggested commit

`feat(release): implement launcher lifecycle and tray controls`

---

## Task 13: Add VC++ runtime prerequisite handling without elevating normal startup

### Goal

Handle missing VC++ 2015-2022 x64 runtime with clear responsibility boundaries: Setup is the primary prerequisite executor for normal installed deployments, while Launcher only provides Portable fallback detection and a one-time install entrypoint.

### Prerequisites

- Task 11 launcher config and diagnostics contracts exist.
- External `vc_redist.x64.exe` path is available.

### Order rationale

This task must be isolated from launcher lifecycle and installer assembly because prerequisite handling has its own privilege boundary, failure modes, and UAC-specific validation.

### Files

- Modify: `C:\Users\33031\Desktop\bot\packaging\launcher\ChatbotLauncher\Program.cs`
- Create: `C:\Users\33031\Desktop\bot\packaging\launcher\ChatbotLauncher\VcRuntimeProbe.cs`
- Create: `C:\Users\33031\Desktop\bot\packaging\launcher\ChatbotLauncher.Tests\VcRuntimeTests.cs`
- Create: `C:\Users\33031\Desktop\bot\packaging\prerequisites\README.md`

### Implementation steps

- [ ] Define how the build pipeline stages `vc_redist.x64.exe` under `prerequisites\` for Setup and Portable bundles without committing the binary to Git.
- [ ] Implement VC++ runtime detection logic that both Setup checks and Launcher Portable fallback can reuse.
- [ ] Document that Setup is the normal installed-flow prerequisite executor; Launcher must not supersede Setup for ordinary installs.
- [ ] Implement Launcher Portable fallback as a one-time user-triggered prerequisite invocation flow with clear handling for:
  - missing prerequisite binary
  - UAC cancelled
  - install failed
- [ ] Ensure Launcher records a failed/cancelled Portable fallback attempt and does not request UAC on every startup as a retry strategy.
- [ ] Add tests for probe logic, Setup-vs-Launcher responsibility, one-time Portable fallback, and cancellation/error reporting.

### Forbidden changes

- Do not commit the actual VC++ binary to Git.
- Do not elevate the whole app by default.

### Tests and verification

- `dotnet test C:\Users\33031\Desktop\bot\packaging\launcher\ChatbotLauncher.sln -c Release --filter VcRuntime`
- `git diff --check`

### Expected result

VC++ prerequisite handling is explicit, bounded, and separate from normal launcher startup.

### Acceptance criteria

- Missing VC++ runtime produces a clear actionable error.
- UAC cancellation is distinguished from installation failure.
- Setup is documented as the primary prerequisite executor for normal installs.
- Launcher exposes only Portable fallback detection/one-time install and does not repeatedly request elevation after a failed/cancelled prerequisite install.

### Suggested commit

`feat(release): add vc runtime prerequisite handling`

---

## Task 14: Implement baseline build script and Portable directory assembly

### Goal

Create the baseline release build entrypoint that performs environment checks, component builds, runtime assembly, and Portable directory assembly only. Sensitive scanning, manifest/SHA/build-report generation, ZIP finalization, Inno Setup, and complete end-to-end validation are intentionally deferred to Tasks 15-17.

### Prerequisites

- Tasks 4-13 are complete.

### Order rationale

This task must come after all lower-level runtime and launcher packaging surfaces exist, but before scan/installer/verification integration. Keeping Task 14 Portable-only lets it be independently accepted with `-PortableOnly` before Task 15 and Task 16 add gates that depend on its assembled directory.

### Files

- Create: `C:\Users\33031\Desktop\bot\scripts\build-trial-release.ps1`
- Create: `C:\Users\33031\Desktop\bot\packaging\build\BuildContext.psm1`
- Create: `C:\Users\33031\Desktop\bot\packaging\build\portable-layout.json`

### Implementation steps

- [ ] Implement the PowerShell parameter block with these exact responsibilities:

  | Parameter | Type | Mandatory in Task 14 | Default | Notes |
  | --- | --- | --- | --- | --- |
  | `Version` | `[string]` | yes | none | Release version used in directory names and later artifact names. |
  | `OutputRoot` | `[string]` | no | `.\build\release` | Root for assembled Portable directory and later artifacts. |
  | `VcRedistPath` | `[string]` | no when `-PortableOnly`; yes when installer target is enabled in Task 16 | empty string | Task 14 may stage Portable without VC++ installer execution. Task 16 requires this for Setup. |
  | `SkipTests` | `[switch]` | no | `$false` | Skips component tests only when explicitly supplied. |
  | `Offline` | `[switch]` | no | `$false` | Uses pre-populated runtime cache and fails if required cached artifacts are missing. |
  | `KeepWorkDirectory` | `[switch]` | no | `$false` | Keeps temporary build work directories for diagnostics. |
  | `PortableOnly` | `[switch]` | no | `$false` | Forces Task 14 acceptance path: assemble Portable directory only; skip scan, manifest, ZIP, Inno Setup, and installer verification. |
  | `AuditWechatDecryptSource` | `[string]` | no | empty string | Audit-only comparison input; never changes packaged source selection. |

- [ ] Split Task 14 script into these build stages only:
  1. environment check
  2. git state capture
  3. frontend build using the Task 9-confirmed command
  4. server runtime assembly
  5. connector runtime assembly
  6. vendor tree assembly
  7. RPA runtime copy
  8. launcher publish
  9. portable directory assembly
  10. minimal Portable layout sanity check that does not require Task 15 manifest files
- [ ] Ensure stage logs include durations and stop on first error.
- [ ] Ensure the script never runs `git clean`, never deletes unrelated directories, and never writes into user `data\`, `runtime\`, or config roots.
- [ ] Ensure Task 14 exits successfully with `-PortableOnly` only when the Portable directory exists and contains launcher, server runtime, connector runtime, RPA runtime, resources, licenses, and `launcher.json`.

### Forbidden changes

- Do not add sensitive scanning in Task 14.
- Do not generate `manifest.json`, `SHA256SUMS.txt`, `build-report.json`, or `build-sensitive-scan.json` in Task 14.
- Do not create ZIP or Inno Setup installer outputs in Task 14.
- Do not accept alternate connector source directories for final packaging.
- Do not use `git add .`, `git clean -fd`, or `git reset --hard`.

### Tests and verification

- `powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\build-trial-release.ps1 -Version "0.1.0" -OutputRoot ".\build\release" -PortableOnly -SkipTests`
- `Test-Path .\build\release\Chatbot-Trial-0.1.0-x64\ChatbotLauncher.exe`
- `git diff --check`

### Expected result

There is one baseline build script that can independently assemble the Portable release directory without scan/manifest/installer dependencies.

### Acceptance criteria

- `-PortableOnly` provides a standalone Task 14 acceptance path.
- No Task 15 scan/manifest/SHA/build-report files are required for Task 14 success.
- No Task 16 installer files are required for Task 14 success.
- The script never mutates unrelated workspace state.

### Suggested commit

`feat(release): add portable trial release build script`

---

## Task 15: Add sensitive scanning, manifest, SHA256, build-report, and Portable ZIP finalization

### Goal

Attach release integrity gates to the Task 14 Portable directory: sensitive-data scanning, manifest generation, SHA256 outputs, build-report generation, launcher key-file validation data, and final Portable ZIP creation.

### Prerequisites

- Task 14 can assemble `build\release\Chatbot-Trial-<version>-x64` with `-PortableOnly`.

### Order rationale

This task must follow Portable directory assembly and precede installer integration. Inno Setup should consume a scanned and manifest-backed Portable directory rather than packaging unverified files.

### Files

- Create: `C:\Users\33031\Desktop\bot\packaging\build\sensitive-scan.py`
- Create: `C:\Users\33031\Desktop\bot\packaging\build\manifest.py`
- Create: `C:\Users\33031\Desktop\bot\packaging\build\allowlist.json`
- Modify: `C:\Users\33031\Desktop\bot\scripts\build-trial-release.ps1`
- Modify: `C:\Users\33031\Desktop\bot\packaging\launcher\ChatbotLauncher\Program.cs`
- Create: `C:\Users\33031\Desktop\bot\packaging\launcher\ChatbotLauncher\ManifestValidator.cs`
- Modify: `C:\Users\33031\Desktop\bot\packaging\launcher\ChatbotLauncher.Tests\LifecycleTests.cs`

### Implementation steps

- [ ] Implement a structured allowlist-aware sensitive scan that checks the Task 14 Portable directory for:
  - tokens
  - cookies
  - API keys
  - private-key headers
  - non-placeholder secrets
  - databases
  - runtime state
  - `.git`
  - `.venv`
  - absolute build-machine paths
  - desktop backup paths
- [ ] Avoid naive binary keyword scanning that would create high false positives.
- [ ] Generate:
  - `build-sensitive-scan.json`
  - `manifest.json`
  - `SHA256SUMS.txt`
  - `build-report.json`
- [ ] Generate `Chatbot-Trial-<version>-x64.zip` only after scan, manifest, SHA256, and build-report generation succeed.
- [ ] Create `ManifestValidator.cs` to load `manifest.json`, validate required key-file presence, and compare SHA-256 values for key files before normal launcher startup continues.
- [ ] Wire `Program.cs` so manifest validation runs once during startup after locating the release root and before starting backend processes.
- [ ] Add launcher tests for manifest missing, key file missing, SHA-256 mismatch, and non-key file absence not blocking fast startup.
- [ ] Update `build-trial-release.ps1` so a normal non-`-PortableOnly` run executes Task 14 assembly followed by Task 15 gates, but still skips Inno Setup until Task 16 is implemented.

### Forbidden changes

- Do not echo full secret values into reports.
- Do not fail binaries solely on field-name keywords like `token` or `secret` inside source text.
- Do not invoke Inno Setup in Task 15.

### Tests and verification

- `powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\build-trial-release.ps1 -Version "0.1.0" -OutputRoot ".\build\release" -SkipTests`
- `Test-Path .\build\release\Chatbot-Trial-0.1.0-x64\manifest.json`
- `Test-Path .\build\release\Chatbot-Trial-0.1.0-x64\build-sensitive-scan.json`
- `Test-Path .\build\release\Chatbot-Trial-0.1.0-x64\build-report.json`
- `Test-Path .\build\release\SHA256SUMS.txt`
- `Test-Path .\build\release\Chatbot-Trial-0.1.0-x64.zip`
- `dotnet test C:\Users\33031\Desktop\bot\packaging\launcher\ChatbotLauncher.sln -c Release --filter ManifestValidator`

### Expected result

Every assembled Portable release is scanned, manifest-backed, hash-listed, report-backed, and zipped before any installer task packages it.

### Acceptance criteria

- Scan report is structured and redacted.
- Manifest, SHA256, and build-report outputs exist before ZIP creation.
- Desktop backup/build-machine path leakage is checked explicitly.
- Launcher manifest validation blocks missing/tampered key files and does not block fast startup for non-key-file absence.
- Inno Setup remains out of scope for Task 15.

### Suggested commit

`feat(release): add release sensitive scan and manifests`

---

## Task 16: Add the Inno Setup installer project and wire installer build

### Goal

Create the user-level Chinese Inno Setup installer that consumes the Task 15 scanned Portable directory, handles upgrades, adds shortcuts, preserves user data by default, and acts as the primary VC++ prerequisite executor for normal installed deployments.

### Prerequisites

- Task 15 produces a scanned Portable directory, manifest outputs, SHA256 outputs, build report, and Portable ZIP.
- Inno Setup is available locally.
- `-VcRedistPath` points to the actual `vc_redist.x64.exe` when building installer artifacts.

### Order rationale

This task must follow scan/manifest integration because the installer should package already-verified Portable outputs. It must precede Task 17 because end-to-end validation needs both Portable and Setup artifacts.

### Files

- Create: `C:\Users\33031\Desktop\bot\packaging\installer\ChatbotTrial.iss`
- Modify: `C:\Users\33031\Desktop\bot\scripts\build-trial-release.ps1`
- Create: `C:\Users\33031\Desktop\bot\packaging\installer\README.md`

### Implementation steps

- [ ] Define stable `AppId`, Chinese UI, default install directory, desktop shortcut, and start-menu shortcut behavior.
- [ ] Package the scanned Portable directory from Task 15 into the installer payload.
- [ ] Wire VC++ prerequisite execution in Setup as the primary normal installed-flow prerequisite path.
- [ ] Make `build-trial-release.ps1` require non-empty `-VcRedistPath` when installer output is enabled and skip this requirement when `-PortableOnly` is used.
- [ ] Preserve Task 13's Launcher Portable fallback boundary: Launcher may offer one-time Portable fallback detection/install, but Setup owns ordinary install prerequisite execution.
- [ ] Implement upgrade/overlay install behavior and user-data preservation rules.
- [ ] Implement uninstall defaults that preserve user data with an explicit optional deletion path.
- [ ] Handle running launcher shutdown before overwrite.
- [ ] Include unsigned-build messaging appropriate for SmartScreen expectations.

### Forbidden changes

- Do not claim code signing or auto-update support.
- Do not move user data into the install root.
- Do not make Launcher repeatedly request UAC for installed deployments.

### Tests and verification

- `powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\build-trial-release.ps1 -Version "0.1.0" -OutputRoot ".\build\release" -VcRedistPath "<actual path>"`
- `Test-Path .\build\release\Chatbot-Setup-0.1.0-x64.exe`
- `Test-Path .\build\release\Chatbot-Trial-0.1.0-x64.zip`

### Expected result

The build pipeline can produce both a scanned Portable ZIP and a user-level installer consistent with the packaged layout and prerequisite policy.

### Acceptance criteria

- Installer output name matches the approved pattern.
- Installer preserves `%LOCALAPPDATA%\Chatbot` by default on uninstall.
- Setup is the primary VC++ prerequisite executor for ordinary installs.
- Launcher remains a Portable fallback only for VC++ prerequisite recovery.

### Suggested commit

`feat(release): add trial installer project`

---

## Task 17: Execute full end-to-end Portable, installer, and clean-machine verification

### Goal

Add the release verification entrypoints and execute the complete end-to-end acceptance path for both Task 15 Portable artifacts and Task 16 installer artifacts, including Windows Sandbox proof that the packaged product does not use system Python, Node, or uv.

### Prerequisites

- Tasks 14-16 are complete.
- Task 1 has filled the `Packaged startup interface contract` rows for backend health, Desktop RPA runtime status, graceful shutdown, and packaged host/port source.
- Task 15 produced a scanned Portable directory, Portable ZIP, `manifest.json`, `SHA256SUMS.txt`, and `build-report.json`.
- Task 16 produced `Chatbot-Setup-<version>-x64.exe` from the scanned Portable directory.

### Order rationale

This task must follow Task 16 because full end-to-end validation needs both deliverables: the scanned Portable release from Task 15 and the Setup installer from Task 16. It must remain separate from "build successful" because clean-machine behavior, child-process executable paths, installer prerequisite behavior, and shutdown/uninstall residue cannot be proven by artifact assembly alone.

### Files

- Create: `C:\Users\33031\Desktop\bot\scripts\verify-trial-release.ps1`
- Create: `C:\Users\33031\Desktop\bot\scripts\test-trial-install.ps1`
- Create: `C:\Users\33031\Desktop\bot\packaging\sandbox\ChatbotTrial.wsb`
- Create: `C:\Users\33031\Desktop\bot\docs\release\verification-matrix.md`

### Implementation steps

- [ ] Implement `verify-trial-release.ps1` for the Task 15 Portable directory and ZIP. It must validate:
  - directory completeness for launcher, backend runtime, connector runtime, RPA runtime, shared `resources/`, `launcher.json`, licenses, `manifest.json`, and `build-report.json`
  - `SHA256SUMS.txt` against every listed file
  - launcher start/stop using the Task 1-confirmed graceful shutdown mechanism
  - backend health using the Task 1-confirmed health route
  - Desktop RPA runtime status using the Task 1-confirmed status route
  - SPA 200 response and route refresh behavior from the packaged static assets
  - no writes outside `%LOCALAPPDATA%\Chatbot` and the release directory
  - packaged child process executable paths for backend Python, connector Python, RPA runtime, and launcher-owned descendants
- [ ] Implement `verify-trial-release.ps1 -MinimizedPath` mode. This mode must launch with a deliberately minimal `PATH` containing only Windows system directories and the packaged release directories required by the launcher. It must fail if any child process resolves `python.exe`, `node.exe`, `uv.exe`, `pnpm.exe`, or `git.exe` from outside the release directory.
- [ ] Implement child-process executable path collection in the verifier by recording PID, parent PID, executable path, command line, and create time before stop/uninstall checks. The acceptance output must show that runtime processes come from packaged paths, not system Python/Node/uv.
- [ ] Execute a no-send, no-decrypt, no-key-export Connector smoke test from `verify-trial-release.ps1`: start the packaged Connector detection/status command, record the Connector Python executable path, verify the path is under `release\connectors\runtime`, and stop the Connector cleanly.
- [ ] Implement `test-trial-install.ps1` for the Task 16 Setup artifact. It must validate:
  - setup install as a normal user
  - Setup-driven VC++ prerequisite execution when the prerequisite is missing
  - first launch from Start Menu/desktop shortcut
  - restart/stop using Task 1-confirmed shutdown behavior
  - upgrade over an existing install
  - uninstall with default user-data retention
  - no unmanaged process residue after uninstall
  - no repeated Launcher UAC prompt on ordinary startup after prerequisites are satisfied
- [ ] Add `ChatbotTrial.wsb` that maps in only the release artifacts and verification scripts, not the developer checkout, and documents the exact Sandbox steps for Portable and installer validation.
- [ ] In Windows Sandbox, run Portable validation with minimized `PATH`, then run installer validation. Record the resulting verification logs in the matrix with PASS/FAIL/UNVERIFIED status.
- [ ] Make both scripts report `UNVERIFIED` clearly when Windows Sandbox or equivalent clean-machine conditions are not actually exercised. Local developer-machine results must not be labeled as clean-machine results.

### Forbidden changes

- Do not collapse Sandbox validation into general build success.
- Do not silently mark unavailable clean-machine checks as passed.
- Do not rely on `where python`, `where node`, or `where uv` alone; child-process executable paths must be inspected.
- Do not mark "no system Python/Node/uv" as passed unless minimized `PATH` and process-path verification both pass, and Windows Sandbox or a clean VM has exercised the same flow.
- Do not send messages during the Connector smoke test.
- Do not decrypt real user databases during the Connector smoke test.
- Do not extract or export real keys during the Connector smoke test.

### Tests and verification

- `powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify-trial-release.ps1 -ReleasePath ".\build\release\Chatbot-Trial-0.1.0-x64" -ZipPath ".\build\release\Chatbot-Trial-0.1.0-x64.zip" -MinimizedPath -ConnectorSmokeTest`
- `powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\test-trial-install.ps1 -SetupPath ".\build\release\Chatbot-Setup-0.1.0-x64.exe" -ExpectedInstallRoot "$env:LOCALAPPDATA\Programs\Chatbot"`
- Launch `C:\Users\33031\Desktop\bot\packaging\sandbox\ChatbotTrial.wsb` and repeat both commands inside Sandbox against the mapped release artifacts.

### Expected result

The release has executed, auditable verification entrypoints for Portable, installer, and clean-machine validation, with explicit evidence for packaged runtime usage and no silent clean-machine pass-through.

### Acceptance criteria

- Verification scripts are separate and cover Portable, installer, and Sandbox flows.
- Sandbox asset exists and maps release artifacts without depending on the developer checkout.
- The "no system Python/Node/uv" claim is backed by minimized `PATH`, child-process executable path logs, Connector smoke-test process evidence, and Windows Sandbox or clean-VM execution.
- Any unrun clean-machine checks are explicitly marked `UNVERIFIED`.

### Suggested commit

`test(release): add trial release end-to-end verification`

---

## Task 18: Write user/maintainer release documentation and clean-machine checklist

### Goal

Document the trial release for end users, maintainers, and clean-machine validators without exposing developer-only startup details to normal users.

### Prerequisites

- Tasks 14-17 are complete so docs can describe the actual build and verification flow.

### Order rationale

Docs must come last because they should describe the implemented build, installer, launcher, and verification surfaces instead of predicting them.

### Files

- Create: `C:\Users\33031\Desktop\bot\docs\release\trial-user-guide.md`
- Create: `C:\Users\33031\Desktop\bot\docs\release\trial-maintainer-guide.md`
- Create: `C:\Users\33031\Desktop\bot\docs\release\clean-machine-checklist.md`

### Implementation steps

- [ ] Write the user guide focused on:
  - install
  - launch
  - tray actions
  - default-disabled real-send behavior
  - uninstall
- [ ] Explicitly keep user docs free of:
  - PowerShell commands
  - Python/Node installation
  - port configuration
  - environment variables
  - manual multi-exe startup instructions
- [ ] Write the maintainer guide covering:
  - build prerequisites
  - build commands
  - runtime cache management
  - external inputs
  - verification flow
  - known limits
  - SmartScreen note for unsigned builds
- [ ] Write the clean-machine checklist for Sandbox/VM acceptance.

### Forbidden changes

- Do not duplicate the approved spec as prose.
- Do not expose internal multi-process startup instructions in the user guide.

### Tests and verification

- Manual editorial check against the spec acceptance points.
- `git diff --check`

### Expected result

The release has final user-facing and maintainer-facing documentation that matches the packaged product and verification workflow.

### Acceptance criteria

- User docs stay non-technical.
- Maintainer docs cover build inputs and validation.
- Clean-machine checklist is explicit and actionable.

### Suggested commit

`docs(release): add trial release guides and checklist`

---

## Verification strategy by layer

### Unit / targeted verification

- `uv run pytest tests/unit_tests/utils/test_paths.py tests/unit_tests/utils/test_packaged_paths.py -q`
- `uv run pytest tests/unit_tests/core/test_bootutils_deps.py tests/unit_tests/core/test_packaged_boot.py -q`
- `uv run pytest tests/unit_tests/local_connectors/test_connectors_base.py tests/unit_tests/local_connectors/test_repository_paths.py tests/unit_tests/local_connectors/test_uac_helper.py -q`
- `uv run pytest tests/vendor_wechat_decrypt/test_connector_cli.py tests/vendor_wechat_decrypt/test_runtime_layout.py -q`
- `uv run pytest tests/unit_tests/desktop_automation/test_runtime_process.py tests/unit_tests/desktop_automation/test_service.py tests/unit_tests/desktop_automation/test_api.py -q`

### Component build verification

- `cd C:\Users\33031\Desktop\bot\web; corepack pnpm install --frozen-lockfile`
- `cd C:\Users\33031\Desktop\bot\web; corepack pnpm run build`
- `cd C:\Users\33031\Desktop\bot\apps\desktop-rpa-runtime; npm ci`
- `cd C:\Users\33031\Desktop\bot\apps\desktop-rpa-runtime; npm run typecheck`
- `cd C:\Users\33031\Desktop\bot\apps\desktop-rpa-runtime; npm run lint`
- `cd C:\Users\33031\Desktop\bot\apps\desktop-rpa-runtime; npm test`
- `cd C:\Users\33031\Desktop\bot\apps\desktop-rpa-runtime; npm run rebuild:native`
- `cd C:\Users\33031\Desktop\bot\apps\desktop-rpa-runtime; npm run package:win:dir`
- `dotnet restore C:\Users\33031\Desktop\bot\packaging\launcher\ChatbotLauncher.sln`
- `dotnet build C:\Users\33031\Desktop\bot\packaging\launcher\ChatbotLauncher.sln -c Release`
- `dotnet test C:\Users\33031\Desktop\bot\packaging\launcher\ChatbotLauncher.sln -c Release`
- `dotnet publish C:\Users\33031\Desktop\bot\packaging\launcher\ChatbotLauncher\ChatbotLauncher.csproj -c Release -r win-x64 --self-contained true`

### Full build / portable verification

- Task 14 baseline Portable-only acceptance: `powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\build-trial-release.ps1 -Version "0.1.0" -OutputRoot ".\build\release" -PortableOnly -SkipTests`
- Task 15 scanned Portable artifact acceptance before installer wiring: `powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\build-trial-release.ps1 -Version "0.1.0" -OutputRoot ".\build\release" -SkipTests`
- Task 17 verifier: `powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify-trial-release.ps1 -ReleasePath ".\build\release\Chatbot-Trial-0.1.0-x64" -ZipPath ".\build\release\Chatbot-Trial-0.1.0-x64.zip" -MinimizedPath -ConnectorSmokeTest`

### Installer verification

- Task 16 full installer build: `powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\build-trial-release.ps1 -Version "0.1.0" -OutputRoot ".\build\release" -VcRedistPath "<actual path>"`
- Task 17 installer verifier: `powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\test-trial-install.ps1 -SetupPath ".\build\release\Chatbot-Setup-0.1.0-x64.exe" -ExpectedInstallRoot "$env:LOCALAPPDATA\Programs\Chatbot"`

### Clean-machine / Windows Sandbox verification

- Launch `C:\Users\33031\Desktop\bot\packaging\sandbox\ChatbotTrial.wsb`
- Validate inside Sandbox or an equivalent clean VM:
  - minimized `PATH` contains no developer Python, Node, uv, pnpm, Git, or repository paths
  - safe Connector smoke test runs without sending messages, decrypting real databases, or exporting keys
  - child-process executable path logs prove backend Python, connector Python, and RPA runtime came from packaged directories
  - `python.exe`, `node.exe`, `uv.exe`, `pnpm.exe`, and `git.exe` are not resolved from the host/system developer toolchain
  - Portable ZIP extraction and first launch
  - installer first install, upgrade, and uninstall
  - Chinese username / space path tolerance
  - offline launch behavior
  - port conflict errors
  - VC++ prerequisite handling and UAC cancellation behavior
  - no repeated Launcher UAC prompt on ordinary startup after prerequisites are satisfied
  - default-disabled real sending
  - no unmanaged process residue after stop/uninstall

## Tasks that require external inputs

- Task 6 requires the final pinned Python runtime artifact URL + SHA-256.
- Task 13 requires the actual `vc_redist.x64.exe` path and SHA-256 for prerequisite staging/docs and Launcher Portable fallback wiring.
- Task 11 and Task 12 require .NET 8 SDK.
- Task 16 requires Inno Setup and the actual `vc_redist.x64.exe` path when building installer artifacts; `-PortableOnly` remains the path for Task 14 acceptance without installer prerequisites.
- Task 17 requires Windows Sandbox or a clean VM capable of minimized-`PATH` execution and child-process executable path inspection.

## Tasks that must be validated on Windows Sandbox or a clean machine

- Task 13: VC++ prerequisite/UAC boundary behavior
- Task 16: installer UX, upgrade, uninstall
- Task 17: portable/install verification under no-dev-tools conditions
- Task 18: checklist execution against a real clean-machine environment

## Independent-commit guidance

These tasks should remain independently reviewable commits:

1. Task 2 — packaged path roots
2. Task 3 — packaged dependency gating
3. Task 4 — vendor medium-set + manifest
4. Task 5 — release lock files
5. Task 6 — runtime manifest pinning
6. Task 7 — packaged backend entrypoint
7. Task 8 — connector runtime isolation
8. Task 9 — frontend resource packaging
9. Task 10 — deterministic RPA packaging
10. Task 11 — launcher scaffold
11. Task 12 — launcher lifecycle
12. Task 13 — VC++ prerequisite handling
13. Task 14 — baseline Portable assembly
14. Task 15 — sensitive scan + manifest/SHA/build-report
15. Task 16 — installer
16. Task 17 — full end-to-end verification
17. Task 18 — release docs

## Explicit unverified reporting rule

If the implementation session completes any local unit/build work but does not execute Windows Sandbox or equivalent clean-machine validation, final status must explicitly mark the following as **UNVERIFIED**:

- clean-machine first launch
- clean-machine installer upgrade
- clean-machine uninstall retention behavior
- missing-VC++ prerequisite behavior on a real clean machine
- offline launch on a machine without dev tools

## Self-review

- The task order matches the approved phase ordering: baseline → path/deps → vendor/locks/runtime → backend/connector/frontend/RPA → launcher/prereq → Portable assembly → scan/manifest/SHA/build-report → installer → full E2E verify/docs.
- Launcher work is intentionally split from path work, connector work, and installer work.
- Verification is explicitly separated into unit/component/portable/installer/clean-machine layers.
- External inputs are called out instead of guessed.
- The plan never reopens already-approved decisions such as layered release structure, installer+portable outputs, launcher-only entrypoint, backend-owned RPA lifecycle, loopback-only backend listening, default port `5302`, top-level shared `resources/`, `%LOCALAPPDATA%\Chatbot`, vendor-only connector source, fixed Python artifact pinning, or deferred code signing/auto-update.

## Execution handoff

**Plan complete and saved to `C:\Users\33031\Desktop\bot\docs\superpowers\plans\2026-07-09-chatbot-windows-trial-release-implementation-plan.md`. Two execution options:**

**1. Subagent-Driven (recommended)** - Dispatch a fresh subagent per task, review between tasks, and keep each release layer isolated.

**2. Inline Execution** - Execute tasks in this session using `executing-plans`, batching related checkpoints in order.

**Which approach?**
