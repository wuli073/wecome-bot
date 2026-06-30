# Source Manifest

| Source repository | Source commit | Source file | Target file | Migration mode | Notes |
|---|---|---|---|---|---|
| sightflow-dev/sightflow-desktop-agent | 8bbc196ac372c9365f732bf8eb9d6fb83b3eb5e3 | `src/core/runtime-host.ts` | `src/main/runtime/runtime-host.ts` | rewritten | Simplified for LangBot runtime orchestration |
| sightflow-dev/sightflow-desktop-agent | 8bbc196ac372c9365f732bf8eb9d6fb83b3eb5e3 | `src/core/session-types.ts` | `src/main/domain/runtime-types.ts` | rewritten | Runtime task and API contracts only |
| sightflow-dev/sightflow-desktop-agent | 8bbc196ac372c9365f732bf8eb9d6fb83b3eb5e3 | `src/main/overlay-window.ts` | `src/main/overlay/overlay-window.ts` | rewritten | Overlay bootstrap adapted to headless API-driven runtime |
