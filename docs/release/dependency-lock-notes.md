# Dependency lock notes

## Goal

These lock files are release-specific runtime locks for Windows x64 packaging. They are intentionally separate from the development environment.

## Server runtime export

The backend project currently keeps several developer-oriented tools in `[project.dependencies]`. To produce a runtime-only lock from `uv.lock` without mutating `pyproject.toml`, export from the locked graph and prune the forbidden package names exactly:

```powershell
uv export --frozen --format requirements.txt --no-dev --no-editable --no-emit-project --python 3.12 `
  --prune ruff --prune uv --prune mypy --prune pre-commit --prune pytest `
  -o packaging\serverequirements.lock.txt
```

This preserves exact locked versions and hashes from `uv.lock` while removing the release-forbidden tool roots.

## Connector runtime export

Compile the connector direct runtime requirements for Windows x64 with hashes:

```powershell
uv pip compile vendor\wechat_decryptequirements.txt `
  --python-version 3.12 `
  --python-platform x86_64-pc-windows-msvc `
  --generate-hashes `
  -o vendor\wechat_decryptequirements.lock.txt
```

## Validation

Run:

```powershell
uv run python packaginguilderify-dependency-locks.py
```

Validation rules:

- both lock files must exist
- requirement names are parsed by normalized distribution name, not substring matching
- the forbidden names are exactly: `pytest`, `ruff`, `mypy`, `pre-commit`, `uv`
- `uvicorn` remains valid and must not be rejected as `uv`

