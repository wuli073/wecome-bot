# Trial release maintainer guide

This guide describes how maintainers build, inspect, and verify the Windows trial release.

## Build prerequisites

Install or provide these build inputs before running the release build:

- Windows 10/11 x64 build host.
- `uv` for the backend build and locked dependency verification.
- Node.js plus the frontend package manager declared by `web/package.json`.
- .NET SDK for the self-contained launcher publish.
- Inno Setup 6 for `packaging/installer/ChatbotTrial.iss`.
- VC++ redistributable input, normally provided as `vc_redist.x64.exe` through `-VcRedistPath`.
- Runtime cache entries described by `packaging/runtime-manifest.json`.

## Python Runtime manifest

`packaging/runtime-manifest.json` is the source of truth for packaged Python Runtime archives. Keep server and connector runtime entries pinned and review their SHA values before rebuilding. Do not replace runtime archives without updating the manifest and rerunning runtime-manifest verification.

## Runtime cache

Runtime cache contents are external build inputs. Keep cache paths outside source control and follow `packaging/runtime-cache-notes.md`. A cache hit must still be verified against the manifest. A cache miss should be treated as `BLOCKED` for offline builds unless the archive is already available from an approved source.

## Build commands

Full release build:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\build-trial-release.ps1 `
  -Version 0.1.0 `
  -VcRedistPath "C:\path\to\vc_redist.x64.exe"
```

PortableOnly build for layout work that intentionally skips ZIP and Installer outputs:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\build-trial-release.ps1 `
  -Version 0.1.0 `
  -PortableOnly
```

Offline build:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\build-trial-release.ps1 `
  -Version 0.1.0 `
  -Offline `
  -VcRedistPath "C:\path\to\vc_redist.x64.exe"
```

## Artifact locations

Expected outputs under `build\release`:

- `Chatbot-Trial-0.1.0-x64\`
- `Chatbot-Trial-0.1.0-x64.zip`
- `Chatbot-Setup-0.1.0-x64.exe`
- `Chatbot-Trial-0.1.0-x64\manifest.json`
- `Chatbot-Trial-0.1.0-x64\SHA256SUMS.txt`
- `Chatbot-Trial-0.1.0-x64\build-report.json`
- `Chatbot-Trial-0.1.0-x64\build-sensitive-scan.json`

## Sensitive scan

The build writes `build-sensitive-scan.json`. Treat any blocked scan or unresolved high-risk finding as a release blocker. The report must not echo full secret values. If the report contains build-machine absolute paths, desktop backup paths, databases, or user runtime state, rebuild from a clean work directory.

## manifest/SHA checks

`manifest.json` must parse as JSON and all critical file hashes must match. `SHA256SUMS.txt` must match every listed file. If a post-build smoke test mutates `.pyc` or runtime state under the release directory, rebuild before publishing and rerun verification from a fresh artifact copy.

## Installer

The Installer is produced by Inno Setup from `packaging/installer/ChatbotTrial.iss`. It is a per-user install, creates Start menu and optional desktop shortcuts, runs VC++ prerequisite handling when needed, and defaults to retaining user data on uninstall.

## Verification commands

Portable verification:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\verify-trial-release.ps1 `
  -ReleasePath ".\build\release\Chatbot-Trial-0.1.0-x64" `
  -ZipPath ".\build\release\Chatbot-Trial-0.1.0-x64.zip" `
  -MinimizedPath
```

Installer verification with an isolated install root:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\test-trial-install.ps1 `
  -SetupPath ".\build\release\Chatbot-Setup-0.1.0-x64.exe" `
  -ExpectedInstallRoot "$env:TEMP\Chatbot Trial Install" `
  -Silent
```

Windows Sandbox verification:

```powershell
Invoke-Item .\packaging\sandbox\ChatbotTrial.wsb
```

Inside Sandbox, copy artifacts to local temporary storage before running verification. Do not map the full repository or real user data.

## Unsigned SmartScreen

Trial builds are currently unsigned. Windows SmartScreen can show a warning. User-facing instructions should say to verify the file source, choose **More info**, and then **Run anyway**. Do not describe SmartScreen as a product failure.

## BLOCKED and UNVERIFIED reporting rules

- Use `PASS` only when a verification script or clean-machine log proves the item.
- Use `FAIL` when a script executed and reported failure.
- Use `BLOCKED` when a required prerequisite is unavailable, such as Inno Setup, VC++ missing snapshot, or Windows Sandbox access.
- Use `UNVERIFIED` when a test was skipped, was not run on a clean machine, or needs an interactive condition such as UAC cancellation.
- Never convert a development-machine result into a clean-machine PASS.
