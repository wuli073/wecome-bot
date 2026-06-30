# Desktop RPA Runtime

Headless Electron + TypeScript runtime for LangBot desktop automation.

## Commands

```powershell
npm install
npm run typecheck
npm run lint
npm test
npm run rebuild:native
npm run build
npm run package:win
```

## Security

- Runtime listens on `127.0.0.1` only.
- Authentication uses an in-memory bearer token passed through environment variables.
- Runtime never writes the bearer token to stdout, stderr, or disk.

## Stdout handshake contract

The packaged Runtime writes exactly one non-empty stdout line during startup: the JSON handshake with `pid`, `port`, `protocolVersion`, and `runtimeVersion`. Python keeps a narrow compatibility path for Electron builds that may emit leading CRLF-only blank lines before the handshake. Only whitespace-only lines are skipped; any other non-empty stdout content before the handshake is treated as startup failure. The Runtime must write diagnostics to stderr, never stdout, and must never print the bearer token.
