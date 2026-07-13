# Trial release verification matrix

This matrix records Task 17 verification evidence for the Windows trial release. Status values are limited to `PASS`, `FAIL`, `BLOCKED`, and `UNVERIFIED`. A local development-machine result is never used as a substitute for a Windows Sandbox or clean-VM result.

Current artifacts:

- Portable directory: `C:\Users\33031\Desktop\bot\build\release\Chatbot-Trial-0.1.0-x64`
- ZIP: `C:\Users\33031\Desktop\bot\build\release\Chatbot-Trial-0.1.0-x64.zip`
- Setup: `C:\Users\33031\Desktop\bot\build\release\Chatbot-Setup-0.1.0-x64.exe`
- Manifest: `C:\Users\33031\Desktop\bot\build\release\Chatbot-Trial-0.1.0-x64\manifest.json`
- Build report: `C:\Users\33031\Desktop\bot\build\release\Chatbot-Trial-0.1.0-x64\build-report.json`
- Sensitive scan: `C:\Users\33031\Desktop\bot\build\release\Chatbot-Trial-0.1.0-x64\build-sensitive-scan.json`
- SHA256SUMS: `C:\Users\33031\Desktop\bot\build\release\Chatbot-Trial-0.1.0-x64\SHA256SUMS.txt`

## Evidence commands

```powershell
powershell -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\verify-trial-release.ps1 `
  -ReleasePath ".\build\release\Chatbot-Trial-0.1.0-x64" `
  -ZipPath ".\build\release\Chatbot-Trial-0.1.0-x64.zip" `
  -MinimizedPath `
  -SkipLaunch

powershell -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\test-trial-install.ps1 `
  -SetupPath ".\build\release\Chatbot-Setup-0.1.0-x64.exe" `
  -ExpectedInstallRoot "$env:TEMP\Chatbot Trial Install Task17 Fixed" `
  -Silent
```

| 验证项 | 环境 | 状态 | 证据 | 日志路径 | 说明 |
|---|---|---|---|---|---|
| 开发机 Portable | Local development machine | FAIL | `portable-structure`, `launcher-config`, `zip-contents`, `sensitive-scan`, `real-send-defaults`, `connector-smoke`, `minimized-path`, and `no-residual-processes` passed; `sha256sums` failed on mutated `.pyc`; forbidden absolute path scan failed on packaged third-party files. | `C:\Users\33031\AppData\Local\Temp\ChatbotTrialVerify\5e765d5a3119421eb438384ec5d23599\logs\verify-trial-release-result.json` | Launch and port-conflict were intentionally `UNVERIFIED` in this local run because `-SkipLaunch` was used to avoid GUI/user-data pollution on the development machine. |
| 开发机 Installer | Local development machine using isolated install root | FAIL | Setup SHA, install, VC++ static prerequisite evidence, and upgrade were recorded; first-launch failed before HTTP verification in the completed run; a later fixed-script rerun exceeded the 5-minute command budget during uninstall. | `C:\Users\33031\AppData\Local\Temp\ChatbotTrialInstallVerify\3c1a25e46e464dada34f6ced96d2aa6d\logs\test-trial-install-result.json`; timeout run cleaned from `%TEMP%\Chatbot Trial Install Task17 Final` | The script now quotes `/DIR` for paths with spaces and avoids matching the verification PowerShell as a controlled process; no PASS is claimed for first launch/uninstall. |
| Windows Sandbox Portable | Windows Sandbox | UNVERIFIED | `packaging/sandbox/ChatbotTrial.wsb` maps only `build\release` and `scripts`, then copies artifacts into Sandbox `%TEMP%` before testing. | Sandbox `%TEMP%\ChatbotTrialVerify\<session>\logs\verify-trial-release-result.json` | Not run in this session; must remain UNVERIFIED until executed in Windows Sandbox or a clean VM. |
| Windows Sandbox Installer | Windows Sandbox | UNVERIFIED | Run `test-trial-install.ps1` from Sandbox local copy with an isolated install root. | Sandbox `%TEMP%\ChatbotTrialInstallVerify\<session>\logs\test-trial-install-result.json` | Not run in this session; must remain UNVERIFIED until executed in Windows Sandbox or a clean VM. |
| VC++ 缺失测试 | Clean VM / snapshot with VC++ absent | UNVERIFIED | Installer spec contains `vc_redist.x64.exe` and `ShouldRunVcRedist`; runtime absence requires clean-machine simulation. | Installer verification log | Current development machine is not evidence for VC++-missing behavior. |
| UAC 取消测试 | Clean VM / snapshot | UNVERIFIED | Installer/launcher prerequisite flow must be exercised by cancelling UAC in a clean-machine scenario. | Installer verification log plus operator notes | Requires an interactive clean-machine test; no local PASS recorded. |
| 离线测试 | Windows Sandbox / clean VM with networking disabled | UNVERIFIED | Sandbox config disables networking by default; run Portable and Installer verification inside Sandbox. | Sandbox verification logs | Must verify no dependency fetch from Python/Node/uv/pnpm/Git. |
| Connector smoke test | Local development machine | PASS | Import-only dry-run used `connectors\runtime\python\python.exe` and imported `connectors\app\wechat-decrypt\connector_runtime.py`; no send/decrypt/key extraction was performed. | `C:\Users\33031\AppData\Local\Temp\ChatbotTrialVerify\5e765d5a3119421eb438384ec5d23599\logs\connector-smoke-stdout.json` | This proves packaged Connector Python path for the dry-run only; clean-machine repeat is still recommended. |
| Minimized PATH | Local development machine | PASS | `-MinimizedPath` PATH contained Windows system directories plus release `server\runtime\python`, `connectors\runtime\python`, `runtime\desktop-rpa`, and release root only. | `C:\Users\33031\AppData\Local\Temp\ChatbotTrialVerify\5e765d5a3119421eb438384ec5d23599\logs\verify-trial-release-result.json` | No permanent PATH was modified. |
| 子进程路径 | Local development machine | UNVERIFIED | Connector smoke path evidence was collected; backend/RPA child paths require launcher run without `-SkipLaunch`. | `C:\Users\33031\AppData\Local\Temp\ChatbotTrialVerify\5e765d5a3119421eb438384ec5d23599\logs\processes.json` | Backend/RPA runtime path proof remains UNVERIFIED in the local `-SkipLaunch` run. |
| 真实发送关闭 | Local development machine | PASS | Launcher source sets `LANGBOT_BROADCAST_SEND_ENABLED=0`, empty allow-list, `LANGBOT_RPA_ALLOW_AUTO_SEND=0`, and `LANGBOT_RPA_FORCE_DISABLE_SEND=1`. | `C:\Users\33031\AppData\Local\Temp\ChatbotTrialVerify\5e765d5a3119421eb438384ec5d23599\logs\verify-trial-release-result.json` | Runtime HTTP proof still requires successful launcher run; static startup default evidence passed. |
| 无进程残留 | Local development machine | PASS | Verification found no release-root controlled processes after cleanup. | `C:\Users\33031\AppData\Local\Temp\ChatbotTrialVerify\5e765d5a3119421eb438384ec5d23599\logs\processes.json` | Earlier exploratory release processes were cleaned by matching only release-root executable paths. |
| 升级 | Isolated install root | PASS | Same-version overlay setup preserved an isolated user-data marker in the completed installer run. | `C:\Users\33031\AppData\Local\Temp\ChatbotTrialInstallVerify\3c1a25e46e464dada34f6ced96d2aa6d\logs\setup-upgrade.log` | First-launch and uninstall failures mean the overall installer row remains FAIL. |
| 卸载保留用户数据 | Isolated install root | FAIL | Completed run reported controlled process residue after uninstall; later timeout run required manual cleanup of the isolated `%TEMP%` install root. | `C:\Users\33031\AppData\Local\Temp\ChatbotTrialInstallVerify\3c1a25e46e464dada34f6ced96d2aa6d\logs\test-trial-install-result.json` | Do not treat this as clean-machine PASS; rerun after installer/launcher lifecycle issues are resolved. |

## Reporting rule

- `PASS` requires script output or clean-machine log evidence.
- `FAIL` requires the failing script item and log path.
- `BLOCKED` is used when a prerequisite such as Windows Sandbox, clean VM access, or VC++-missing simulation is unavailable.
- `UNVERIFIED` is used when a test was not executed or when the local development machine cannot prove a clean-machine property.
