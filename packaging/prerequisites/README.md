# VC++ prerequisite staging

`vc_redist.x64.exe` is an external build input and must **not** be committed to Git.

## Build-time contract

- The release build pipeline receives the real `vc_redist.x64.exe` path explicitly.
- The pipeline copies that binary into the assembled release tree as:
  - `prerequisites/vc_redist.x64.exe` for Portable bundles
  - `prerequisites/vc_redist.x64.exe` inside the installer payload for Setup
- Repository source control keeps only this README and the launcher/install logic; the binary itself remains outside Git.

## Responsibility boundary

- **Setup is the primary prerequisite executor** for normal installed deployments under `%LOCALAPPDATA%\Programs\Chatbot`.
- **Launcher is only a Portable fallback** when the app is running from an unpacked directory and the VC++ runtime is missing.
- Launcher must never elevate the whole application by default and must not replace Setup as the normal install path.

## Portable fallback behavior

- Probe the machine for the VC++ 2015-2022 x64 runtime first.
- If missing and `prerequisites/vc_redist.x64.exe` is absent, show a clear actionable error.
- If missing and the fallback installer is present, the launcher may offer a **one-time** user-triggered elevation flow.
- If the user cancels UAC or installation fails, the launcher records that result and does not request elevation again on every startup.
