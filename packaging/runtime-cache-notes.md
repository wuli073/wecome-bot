# Runtime cache notes

## Selected provider

- Provider: `python-build-standalone`
- Release tag: `20260623`
- Pinned artifact for both `server` and `connector` roles:
  `cpython-3.11.15+20260623-x86_64-pc-windows-msvc-install_only_stripped.tar.gz`
- SHA-256:
  `6589ca6d63f520bec4096d62b3ab91da3d0a80b16b594c99a6b677e335814683`

This trial release intentionally uses the same pinned Windows x64 CPython artifact
for both packaged Python runtime roles. Later packaging tasks may install different
locked dependencies into separate extracted runtime directories, but they must start
from the same verified upstream archive.

## Cache directory policy

Repository-relative runtime cache root:

- `build/runtime-cache`

Subdirectories:

- `build/runtime-cache/archives`
- `build/runtime-cache/expanded`

Cache path rules:

1. Archive cache path is `build/runtime-cache/archives/<artifactName>`.
2. Extracted cache path is `build/runtime-cache/expanded/<role>/<version>`.
3. Extracted cache is disposable and may be recreated from a verified archive at any time.
4. Only SHA-256-verified archives may be extracted or reused.

## Online build behavior

For ordinary online builds:

1. Read `packaging/runtime-manifest.json`.
2. Resolve the archive cache path from `artifactName`.
3. If the archive is missing, download it from the pinned `url` into a temporary file.
4. Verify the downloaded file against the pinned `sha256`.
5. Move the verified download into the cache path atomically.
6. If the archive already exists, verify its SHA-256 before reusing it.
7. Populate or refresh the extracted cache from the verified archive only.

## `-Offline` build behavior

For `-Offline` builds:

1. Network download is forbidden.
2. The build must use only files already present under `build/runtime-cache`.
3. If the pinned archive is missing, the build must fail immediately.
4. If the pinned archive hash does not match `runtime-manifest.json`, the build must fail immediately.
5. If an extracted cache is missing, the build may recreate it from the already-verified cached archive.

## Manifest validation rules

`packaging/build/verify-runtime-manifest.py` is the single manifest validator for Task 6.
It must be runnable from Windows PowerShell via:

```powershell
uv run python packaging\build\verify-runtime-manifest.py
```

The verifier rejects:

- missing role fields
- floating or `latest` URLs
- non-64-character SHA-256 values
- absolute cache-root definitions
- incomplete extracted-layout metadata

## Upstream layout notes

The pinned `install_only_stripped` archive extracts under a top-level `python/` directory.
Inspection of the pinned archive confirms:

- runtime executable: `python/python.exe`
- GUI executable: `python/pythonw.exe`
- license file: `python/LICENSE.txt`
- `site-packages` path: `python/Lib/site-packages`
- `pip` is included upstream and should be invoked as `python/python.exe -m pip`

No floating provider selection or alternate runtime source is allowed for this release line.
