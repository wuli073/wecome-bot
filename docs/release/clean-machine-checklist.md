# Clean-machine trial release checklist

Use this checklist in Windows Sandbox or a clean VM. Record every result in `docs/release/verification-matrix.md` and attach script logs.

| Check | Status | Evidence |
|---|---|---|
| No Python installed on the machine before trial setup | UNVERIFIED | |
| No Node installed on the machine before trial setup | UNVERIFIED | |
| No Git installed on the machine before trial setup | UNVERIFIED | |
| No uv/pnpm installed on the machine before trial setup | UNVERIFIED | |
| Ordinary non-admin user account | UNVERIFIED | |
| Chinese username account | UNVERIFIED | |
| Install path containing spaces | UNVERIFIED | |
| Offline launch with networking disabled | UNVERIFIED | |
| VC++ missing scenario invokes prerequisite handling | UNVERIFIED | |
| UAC cancellation is handled without repeated prompts or partial setup | UNVERIFIED | |
| Port conflict reports a clear failure and does not silently switch | UNVERIFIED | |
| Installer completes per-user installation | UNVERIFIED | |
| First launch opens the product through the shortcut | UNVERIFIED | |
| Connector dry-run uses packaged connector runtime only | UNVERIFIED | |
| RPA status endpoint reports expected safe state | UNVERIFIED | |
| Upgrade preserves user data and normal configuration | UNVERIFIED | |
| Uninstall removes program files | UNVERIFIED | |
| User data is retained by default after uninstall | UNVERIFIED | |
| No controlled process remains after exit or uninstall | UNVERIFIED | |
| Real sending remains disabled by default | UNVERIFIED | |

## Required evidence

- `verify-trial-release-result.json` for Portable checks.
- `test-trial-install-result.json` for Installer, upgrade, and uninstall checks.
- `processes.json` for child-process path and no-residual-process proof.
- Screenshot or written operator note only for interactive UAC cancellation and SmartScreen observations.

## Failure handling

If any item fails, keep the clean-machine state until logs are copied out. Do not rerun setup over the failed state unless the rerun is explicitly recorded as a separate attempt.
