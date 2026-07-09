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
    explicit_root = os.environ.get('CHATBOT_CONNECTOR_ROOT', '').strip()
    if explicit_root:
        candidates.append(Path(explicit_root).expanduser().resolve())

    install_root = Path(path_utils.get_install_root()).resolve()
    candidates.append((install_root / 'connectors' / 'app' / 'wechat-decrypt').resolve())

    return candidates


def resolve_connector_python_executable() -> Path:
    explicit_python = os.environ.get('CHATBOT_CONNECTOR_PYTHON', '').strip()
    if explicit_python:
        candidate = Path(explicit_python).expanduser().resolve()
        if candidate.exists():
            return candidate
        raise FileNotFoundError(f'Packaged connector python executable not found: {candidate}')

    if path_utils.is_packaged_mode():
        candidate = (Path(path_utils.get_install_root()) / 'connectors' / 'runtime' / 'python' / 'python.exe').resolve()
        if candidate.exists():
            return candidate
        raise FileNotFoundError(f'Packaged connector python executable not found: {candidate}')

    return Path(sys.executable).resolve()


def resolve_wechat_decrypt_root() -> Path:
    if path_utils.is_packaged_mode():
        for candidate in _packaged_runtime_candidates():
            if candidate.exists():
                return candidate.resolve()
        raise FileNotFoundError(
            'Packaged wechat-decrypt runtime not found. Expected CHATBOT_CONNECTOR_ROOT '
            'or <install_root>/connectors/app/wechat-decrypt.'
        )

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
