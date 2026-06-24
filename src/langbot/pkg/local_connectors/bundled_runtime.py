from __future__ import annotations

import os
import sys
from pathlib import Path

from ..utils import paths as path_utils


def _find_source_root() -> Path | None:
    source_root = path_utils._find_source_root()
    if source_root is None:
        return None
    return Path(source_root).resolve()


def _packaged_runtime_candidates() -> list[Path]:
    candidates: list[Path] = []

    resource_path = Path(path_utils.get_resource_path('vendor/wechat_decrypt')).resolve()
    candidates.append(resource_path)

    executable_dir = Path(sys.executable).resolve().parent
    candidates.append(executable_dir / 'vendor' / 'wechat_decrypt')
    candidates.append(executable_dir.parent / 'vendor' / 'wechat_decrypt')

    return candidates


def resolve_wechat_decrypt_root() -> Path:
    for candidate in _packaged_runtime_candidates():
        if candidate.exists():
            return candidate.resolve()

    source_root = _find_source_root()
    if source_root is not None:
        source_vendor = source_root / 'vendor' / 'wechat_decrypt'
        if source_vendor.exists():
            return source_vendor.resolve()

    override = os.environ.get('WECOME_WECHAT_DECRYPT_DIR', '').strip()
    if override:
        override_path = Path(override).expanduser()
        if override_path.exists():
            return override_path.resolve()

    raise FileNotFoundError(
        'Bundled wechat-decrypt runtime not found. Expected vendor/wechat_decrypt '
        'in the packaged app or source checkout; WECOME_WECHAT_DECRYPT_DIR is optional.'
    )


def resolve_wechat_decrypt_entrypoint(name: str) -> Path:
    entrypoint = Path(name)
    if entrypoint.name != name:
        raise ValueError(f'Entrypoint must be a single filename: {name}')

    resolved = resolve_wechat_decrypt_root() / entrypoint
    if not resolved.exists():
        raise FileNotFoundError(f'Bundled wechat-decrypt entrypoint not found: {resolved}')
    return resolved.resolve()
