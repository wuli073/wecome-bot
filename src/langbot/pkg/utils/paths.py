"""Utility functions for finding package resources and runtime data roots."""

from __future__ import annotations

import os
import sys
from pathlib import Path


_is_source_install = None
_source_root = None


class PackagedPathError(RuntimeError):
    """Raised when packaged-mode path roots cannot be resolved safely."""


def _find_source_root() -> Path | None:
    """Locate the LangBot repository root when running from source."""
    global _source_root

    if _source_root is not None:
        return _source_root

    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / 'pyproject.toml').exists() and (parent / 'main.py').exists():
            _source_root = parent
            return parent

    _source_root = None
    return None


def _check_if_source_install() -> bool:
    """
    Check if we're running from the LangBot source tree.
    Cached to avoid repeated filesystem scans.
    """
    global _is_source_install

    if _is_source_install is not None:
        return _is_source_install

    _is_source_install = _find_source_root() is not None
    return _is_source_install


def is_packaged_mode() -> bool:
    """Return true when the process is running from a packaged release."""
    return os.environ.get('CHATBOT_PACKAGED', '').strip() == '1'


def _resolve_env_path(name: str) -> Path | None:
    value = os.environ.get(name, '').strip()
    if not value:
        return None
    return Path(value).expanduser().resolve()


def _packaged_base_from_executable() -> Path:
    executable = Path(sys.executable).resolve()
    # Packaged backend Python lives below server/runtime or server/runtime/python.
    # Walk up a bounded number of levels and prefer a directory that owns launcher.json.
    for parent in [executable.parent, *list(executable.parents)[:6]]:
        if (parent / 'launcher.json').exists() or (parent / 'resources').exists():
            return parent
    return executable.parent


def get_install_root() -> str:
    """Return the immutable install root for packaged mode."""
    env_root = _resolve_env_path('CHATBOT_INSTALL_ROOT')
    if env_root is not None:
        return str(env_root)
    if is_packaged_mode():
        return str(_packaged_base_from_executable())
    source_root = _find_source_root()
    return str(source_root.resolve()) if source_root is not None else str(Path.cwd().resolve())


def get_user_data_root() -> str:
    """Return the mutable user-data root."""
    env_root = _resolve_env_path('CHATBOT_USER_DATA_ROOT')
    if env_root is not None:
        return str(env_root)

    env_root = _resolve_env_path('LANGBOT_DATA_ROOT')
    if env_root is not None:
        return str(env_root)

    if is_packaged_mode():
        local_app_data = os.environ.get('LOCALAPPDATA', '').strip()
        if not local_app_data:
            raise PackagedPathError('LOCALAPPDATA is required when CHATBOT_PACKAGED=1')
        return str((Path(local_app_data).expanduser() / 'Chatbot').resolve())

    source_root = _find_source_root()
    if source_root is not None:
        return str((source_root / 'data').resolve())
    return str((Path.cwd() / 'data').resolve())


def get_resources_root() -> str:
    """Return the shared top-level resources directory."""
    env_root = _resolve_env_path('CHATBOT_RESOURCES_ROOT')
    if env_root is not None:
        return str(env_root)
    if is_packaged_mode():
        return str((Path(get_install_root()) / 'resources').resolve())
    source_root = _find_source_root()
    if source_root is not None:
        return str(source_root.resolve())
    return str(Path.cwd().resolve())


def _packaged_resource_override(resource: str) -> Path | None:
    normalized = resource.replace('\\', '/').strip('/')
    override_map = {
        'web/dist': 'CHATBOT_WEB_ROOT',
        'templates': 'CHATBOT_TEMPLATE_ROOT',
        'src/langbot/templates': 'CHATBOT_TEMPLATE_ROOT',
        'src/langbot/pkg/persistence/alembic': 'CHATBOT_MIGRATION_ROOT',
        'defaults': 'CHATBOT_DEFAULTS_ROOT',
    }
    for prefix, env_name in override_map.items():
        if normalized == prefix or normalized.startswith(prefix + '/'):
            override = _resolve_env_path(env_name)
            if override is None:
                continue
            suffix = normalized[len(prefix):].lstrip('/')
            return (override / suffix).resolve()
    return None


def get_data_root() -> str:
    """
    Get the runtime data root.

    Priority:
    1. CHATBOT_USER_DATA_ROOT / LANGBOT_DATA_ROOT environment override
    2. Packaged %LOCALAPPDATA%/Chatbot when CHATBOT_PACKAGED=1
    3. Source checkout root /data when running from source
    4. Current working directory /data for installed-package usage
    """
    return get_user_data_root()


def get_repo_root() -> str | None:
    """Get the LangBot repository root when running from a source checkout."""
    source_root = _find_source_root()
    if source_root is None:
        return None
    return str(source_root.resolve())


def get_data_path(*parts: str) -> str:
    """Join path segments under the resolved data root."""
    data_root = Path(get_data_root())
    if not parts:
        return str(data_root)
    return str((data_root.joinpath(*parts)).resolve())


def get_frontend_path() -> str:
    """
    Get the path to the frontend build files.

    Returns the path to web/dist directory, handling both source mode and
    packaged mode. Packaged mode never probes cwd.
    """
    if is_packaged_mode():
        override = _resolve_env_path('CHATBOT_WEB_ROOT')
        if override is not None:
            return str(override)
        return str((Path(get_resources_root()) / 'web' / 'dist').resolve())

    for dirname in ('dist', 'out'):
        web_dir = f'web/{dirname}'

        if _check_if_source_install() and os.path.exists(web_dir):
            return web_dir

        if os.path.exists(web_dir):
            return web_dir

        pkg_dir = Path(__file__).parent.parent.parent
        frontend_path = pkg_dir / 'web' / dirname
        if frontend_path.exists():
            return str(frontend_path)

    return 'web/dist'


def get_resource_path(resource: str) -> str:
    """
    Get the path to a resource file.

    Args:
        resource: Relative path to resource (e.g., 'templates/config.yaml')

    Returns:
        Absolute path to the resource in packaged mode, or the historical source-mode path.
    """
    if is_packaged_mode():
        override = _packaged_resource_override(resource)
        if override is not None:
            return str(override)

        normalized = resource.replace('\\', '/').strip('/')
        roots = {
            'web/dist': Path(get_resources_root()) / 'web' / 'dist',
            'templates': Path(get_resources_root()) / 'templates',
            'src/langbot/templates': Path(get_resources_root()) / 'templates',
            'src/langbot/pkg/persistence/alembic': Path(get_resources_root()) / 'migrations',
            'defaults': Path(get_resources_root()) / 'defaults',
        }
        for prefix, root in roots.items():
            if normalized == prefix or normalized.startswith(prefix + '/'):
                suffix = normalized[len(prefix):].lstrip('/')
                return str((root / suffix).resolve())
        return str((Path(get_resources_root()) / normalized).resolve())

    source_root = _find_source_root()
    if source_root is not None:
        source_resource = source_root / resource
        if source_resource.exists():
            if Path.cwd().resolve() == source_root.resolve():
                return resource
            return str(source_resource)

    if os.path.exists(resource):
        return resource

    pkg_dir = Path(__file__).parent.parent.parent
    resource_path = pkg_dir / resource
    if resource_path.exists():
        return str(resource_path)

    return resource
