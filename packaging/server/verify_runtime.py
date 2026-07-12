from __future__ import annotations

import os
from pathlib import Path
from typing import Mapping

BACKEND_HEALTH_PATH = '/healthz'
BACKEND_RUNTIME_STATUS_PATH = '/api/v1/system/runtime/status'
PACKAGED_BIND_HOST = '127.0.0.1'
REQUIRED_KEYS = (
    'CHATBOT_PACKAGED',
    'CHATBOT_INSTALL_ROOT',
    'CHATBOT_USER_DATA_ROOT',
    'CHATBOT_RESOURCES_ROOT',
    'CHATBOT_WEB_ROOT',
    'CHATBOT_TEMPLATE_ROOT',
    'CHATBOT_MIGRATION_ROOT',
    'CHATBOT_DEFAULTS_ROOT',
    'CHATBOT_RUNTIME_ROOT',
    'CHATBOT_RPA_RUNTIME_PATH',
    'API__HOST',
    'API__PORT',
    'DESKTOP_AUTOMATION__ENABLED',
    'DESKTOP_AUTOMATION__RUNTIME_EXECUTABLE',
    'PYTHONDONTWRITEBYTECODE',
    'PYTHONUTF8',
    'PYTHONIOENCODING',
)


def verify_runtime_environment(env: Mapping[str, str] | None = None) -> None:
    current_env = dict(env or os.environ)
    for key in REQUIRED_KEYS:
        if not str(current_env.get(key, '')).strip():
            raise SystemExit(f'{key} is required')

    if str(current_env['CHATBOT_PACKAGED']).strip() != '1':
        raise SystemExit('CHATBOT_PACKAGED must equal 1')
    if str(current_env['API__HOST']).strip() != PACKAGED_BIND_HOST:
        raise SystemExit(f'API__HOST must equal {PACKAGED_BIND_HOST}')

    try:
        port = int(str(current_env['API__PORT']).strip())
    except ValueError as exc:
        raise SystemExit('API__PORT must be an integer') from exc
    if not 1 <= port <= 65535:
        raise SystemExit('API__PORT must be between 1 and 65535')

    install_root = Path(current_env['CHATBOT_INSTALL_ROOT']).resolve(strict=False)
    resources_root = Path(current_env['CHATBOT_RESOURCES_ROOT']).resolve(strict=False)
    user_data_root = Path(current_env['CHATBOT_USER_DATA_ROOT']).resolve(strict=False)
    runtime_root = Path(current_env['CHATBOT_RUNTIME_ROOT']).resolve(strict=False)
    rpa_runtime_path = Path(current_env['CHATBOT_RPA_RUNTIME_PATH']).resolve(strict=False)

    if resources_root != (install_root / 'resources').resolve(strict=False):
        raise SystemExit('CHATBOT_RESOURCES_ROOT must resolve to <install_root>/resources')

    try:
        runtime_root.relative_to(user_data_root)
    except ValueError as exc:
        raise SystemExit('CHATBOT_RUNTIME_ROOT must stay under CHATBOT_USER_DATA_ROOT') from exc

    if rpa_runtime_path.name != 'LangBot Desktop RPA Runtime.exe':
        raise SystemExit('CHATBOT_RPA_RUNTIME_PATH must point to LangBot Desktop RPA Runtime.exe')

    if str(current_env.get('CHATBOT_BACKEND_HEALTH_PATH', BACKEND_HEALTH_PATH)).strip() != BACKEND_HEALTH_PATH:
        raise SystemExit(f'CHATBOT_BACKEND_HEALTH_PATH must equal {BACKEND_HEALTH_PATH}')
    if (
        str(current_env.get('CHATBOT_BACKEND_RUNTIME_STATUS_PATH', BACKEND_RUNTIME_STATUS_PATH)).strip()
        != BACKEND_RUNTIME_STATUS_PATH
    ):
        raise SystemExit(
            f'CHATBOT_BACKEND_RUNTIME_STATUS_PATH must equal {BACKEND_RUNTIME_STATUS_PATH}'
        )
    if str(current_env['DESKTOP_AUTOMATION__ENABLED']).strip().lower() != 'true':
        raise SystemExit('DESKTOP_AUTOMATION__ENABLED must equal true')
    if (
        Path(current_env['DESKTOP_AUTOMATION__RUNTIME_EXECUTABLE']).resolve(strict=False)
        != rpa_runtime_path
    ):
        raise SystemExit('DESKTOP_AUTOMATION__RUNTIME_EXECUTABLE must match CHATBOT_RPA_RUNTIME_PATH')
    if str(current_env['PYTHONDONTWRITEBYTECODE']).strip() != '1':
        raise SystemExit('PYTHONDONTWRITEBYTECODE must equal 1')
    if str(current_env['PYTHONUTF8']).strip() != '1':
        raise SystemExit('PYTHONUTF8 must equal 1')
    if str(current_env['PYTHONIOENCODING']).strip().lower() != 'utf-8':
        raise SystemExit('PYTHONIOENCODING must equal utf-8')


def main() -> None:
    verify_runtime_environment()
    print('packaged runtime environment verified')


if __name__ == '__main__':
    main()
