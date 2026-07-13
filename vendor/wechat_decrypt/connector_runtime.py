from __future__ import annotations

import glob
import json
import os
import subprocess
import sys
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path

import connector_errors as errors


SCRIPT_DIR = Path(__file__).resolve().parent
RELEASE_RUNTIME_ENTRYPOINTS = (
    'connector_cli.py',
    'connector_runtime.py',
    'mcp_server.py',
    'mcp_wxwork_server.py',
    'wxwork_message_monitor.py',
    'find_all_keys_windows.py',
    'find_wxwork_keys.py',
    'decrypt_db.py',
    'decrypt_wxwork_db.py',
)
RELEASE_RUNTIME_SUPPORT_FILES = (
    'config.py',
    'connector_errors.py',
    'key_scan_common.py',
    'key_utils.py',
    'decode_image.py',
    'wxwork_crypto.py',
    'wxwork_query.py',
)
RELEASE_EXCLUDED_FILES = (
    'main.py',
    'monitor_web.py',
    'mcp_http_server.py',
    'mcp_wxwork_http_server.py',
    'export_wxwork_messages.py',
    'find_all_keys.py',
    'find_all_keys_linux.py',
    'build.bat',
    'WeChatDecrypt.spec',
)

CONNECTOR_SPECS = {
    'wechat': {
        'process': 'Weixin.exe',
        'extract_script': 'find_all_keys_windows.py',
        'decrypt_script': 'decrypt_db.py',
        'keys_file': 'all_keys.json',
        'config_key_db_dir': 'db_dir',
        'config_key_keys_file': 'keys_file',
        'config_key_decrypted_dir': 'decrypted_dir',
    },
    'wxwork': {
        'process': 'WXWork.exe',
        'extract_script': 'find_wxwork_keys.py',
        'decrypt_script': 'decrypt_wxwork_db.py',
        'keys_file': 'wxwork_keys.json',
        'config_key_db_dir': 'wxwork_db_dir',
        'config_key_keys_file': 'wxwork_keys_file',
        'config_key_decrypted_dir': 'wxwork_decrypted_dir',
    },
}


def build_result(
    *,
    ok: bool,
    connector: str,
    action: str,
    error_code: str | None = None,
    error_message: str | None = None,
    **extra,
) -> dict:
    payload = {
        'ok': ok,
        'connector': connector,
        'action': action,
        'error_code': error_code,
        'error_message': error_message,
    }
    payload.update(extra)
    return payload


def is_windows() -> bool:
    return sys.platform.startswith('win')


def resolve_runtime_dir(runtime_dir: str) -> str:
    if not runtime_dir:
        raise ValueError('runtime_dir is required')
    if not os.path.isabs(runtime_dir):
        raise ValueError('runtime_dir must be absolute')
    runtime_root = os.path.abspath(runtime_dir)
    if os.path.isfile(runtime_root):
        raise ValueError('runtime_dir must be a directory path')
    return runtime_root


def ensure_runtime_layout(runtime_dir: str) -> dict:
    runtime_root = resolve_runtime_dir(runtime_dir)
    paths = {
        'runtime_root': runtime_root,
        'app_dir': os.path.join(runtime_root, 'config'),
        'secrets_dir': os.path.join(runtime_root, 'secrets'),
        'decrypted_dir': os.path.join(runtime_root, 'decrypted'),
        'logs_dir': os.path.join(runtime_root, 'logs'),
        'jobs_dir': os.path.join(runtime_root, 'jobs'),
    }
    for path in paths.values():
        os.makedirs(path, exist_ok=True)
    paths['config_file'] = os.path.join(paths['app_dir'], 'config.json')
    return paths


def run_tasklist(image_name: str) -> str:
    result = subprocess.run(
        ['tasklist', '/FI', f'IMAGENAME eq {image_name}', '/FO', 'CSV', '/NH'],
        capture_output=True,
        text=True,
        encoding='utf-8',
        errors='replace',
    )
    return result.stdout


def is_process_running(image_name: str) -> bool:
    output = run_tasklist(image_name)
    for line in output.splitlines():
        if image_name.lower() in line.lower():
            return True
    return False


def detect_wechat_db_dir_from_ini(config_dir: str) -> str | None:
    if not os.path.isdir(config_dir):
        return None

    candidates: list[str] = []
    seen: set[str] = set()
    for ini_file in glob.glob(os.path.join(config_dir, '*.ini')):
        content = None
        for encoding in ('utf-8', 'gbk'):
            try:
                with open(ini_file, 'r', encoding=encoding) as handle:
                    content = handle.read(1024).strip()
                break
            except UnicodeDecodeError:
                continue
            except OSError:
                content = None
                break
        if not content or any(char in content for char in '\n\r\x00') or not os.path.isdir(content):
            continue

        for match in glob.glob(os.path.join(content, 'xwechat_files', '*', 'db_storage')):
            normalized = os.path.normcase(os.path.normpath(match))
            if os.path.isdir(match) and normalized not in seen:
                seen.add(normalized)
                candidates.append(match)

    candidates.sort(key=lambda path: os.path.getmtime(path), reverse=True)
    return candidates[0] if candidates else None


def detect_connector(connector: str) -> dict:
    if connector not in CONNECTOR_SPECS:
        return build_result(
            ok=False,
            connector=connector,
            action='detect',
            error_code=errors.INVALID_CONNECTOR,
            error_message='Unknown connector',
        )
    if not is_windows():
        return build_result(
            ok=False,
            connector=connector,
            action='detect',
            error_code=errors.UNSUPPORTED_PLATFORM,
            error_message='Only Windows is supported',
        )

    spec = CONNECTOR_SPECS[connector]
    if not is_process_running(spec['process']):
        return build_result(
            ok=False,
            connector=connector,
            action='detect',
            error_code=errors.CLIENT_NOT_RUNNING,
            error_message=f"{spec['process']} is not running",
        )

    if connector == 'wechat':
        appdata = os.environ.get('APPDATA', '')
        config_dir = os.path.join(appdata, 'Tencent', 'xwechat', 'config')
        db_dir = detect_wechat_db_dir_from_ini(config_dir)
    else:
        from find_wxwork_keys import auto_detect_wxwork_db_dir

        previous = os.environ.get('WXWORK_AUTO_SELECT_DB')
        os.environ['WXWORK_AUTO_SELECT_DB'] = '1'
        try:
            silent_stream = StringIO()
            with redirect_stdout(silent_stream), redirect_stderr(silent_stream):
                db_dir = auto_detect_wxwork_db_dir()
        finally:
            if previous is None:
                os.environ.pop('WXWORK_AUTO_SELECT_DB', None)
            else:
                os.environ['WXWORK_AUTO_SELECT_DB'] = previous

    if not db_dir or not os.path.isdir(db_dir):
        return build_result(
            ok=False,
            connector=connector,
            action='detect',
            error_code=errors.CLIENT_NOT_LOGGED_IN,
            error_message='Client is running but no logged-in data directory was found',
        )

    return build_result(
        ok=True,
        connector=connector,
        action='detect',
        error_code=errors.OK,
        db_dir=os.path.abspath(db_dir),
        process_name=spec['process'],
    )


def build_runtime_config(connector: str, runtime_dir: str, db_dir: str) -> dict:
    spec = CONNECTOR_SPECS[connector]
    layout = ensure_runtime_layout(runtime_dir)
    keys_file = os.path.join(layout['secrets_dir'], spec['keys_file'])
    config = {
        spec['config_key_db_dir']: os.path.abspath(db_dir),
        spec['config_key_keys_file']: keys_file,
        spec['config_key_decrypted_dir']: layout['decrypted_dir'],
    }
    if connector == 'wechat':
        config['db_dir'] = os.path.abspath(db_dir)
        config['keys_file'] = keys_file
        config['decrypted_dir'] = layout['decrypted_dir']
    return {
        **layout,
        'db_dir': os.path.abspath(db_dir),
        'keys_file': keys_file,
        'config': config,
    }


def write_runtime_config(connector: str, runtime_dir: str, db_dir: str) -> dict:
    runtime = build_runtime_config(connector, runtime_dir, db_dir)
    with open(runtime['config_file'], 'w', encoding='utf-8') as handle:
        json.dump(runtime['config'], handle, ensure_ascii=False, indent=2)
    return runtime


def load_runtime_config(connector: str, runtime_dir: str) -> dict | None:
    spec = CONNECTOR_SPECS[connector]
    layout = ensure_runtime_layout(runtime_dir)
    if not os.path.exists(layout['config_file']):
        return None
    with open(layout['config_file'], encoding='utf-8') as handle:
        config = json.load(handle)
    return {
        **layout,
        'config': config,
        'db_dir': config.get(spec['config_key_db_dir'], ''),
        'keys_file': config.get(
            spec['config_key_keys_file'],
            os.path.join(layout['secrets_dir'], spec['keys_file']),
        ),
    }


def run_managed_script(script_name: str, app_dir: str, *args: str, timeout: int = 1200) -> dict:
    script_path = SCRIPT_DIR / script_name
    env = os.environ.copy()
    env['WECHAT_DECRYPT_APP_DIR'] = app_dir
    env['WECHAT_DECRYPT_NONINTERACTIVE'] = '1'
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    env['PYTHONUTF8'] = '1'
    env['PYTHONIOENCODING'] = 'utf-8'
    proc = subprocess.run(
        [sys.executable, '-X', 'utf8', str(script_path), *args],
        cwd=str(SCRIPT_DIR),
        env=env,
        capture_output=True,
        text=True,
        encoding='utf-8',
        errors='replace',
        timeout=timeout,
    )
    return {
        'returncode': proc.returncode,
        'stdout': proc.stdout,
        'stderr': proc.stderr,
    }


def extract_key(connector: str, runtime_dir: str) -> dict:
    detect = detect_connector(connector)
    if not detect['ok']:
        return build_result(
            ok=False,
            connector=connector,
            action='extract-key',
            error_code=detect['error_code'],
            error_message=detect['error_message'],
        )

    runtime = write_runtime_config(connector, runtime_dir, detect['db_dir'])
    spec = CONNECTOR_SPECS[connector]
    try:
        script_result = run_managed_script(spec['extract_script'], runtime['app_dir'])
    except PermissionError:
        return build_result(
            ok=False,
            connector=connector,
            action='extract-key',
            error_code=errors.PROCESS_ACCESS_DENIED,
            error_message='Access to the client process was denied',
        )

    if script_result['returncode'] != 0 or not os.path.exists(runtime['keys_file']):
        diagnostic = (script_result.get('stderr', '') + '\n' + script_result.get('stdout', '')).lower()
        if 'access is denied' in diagnostic or 'permission denied' in diagnostic:
            error_code = errors.PROCESS_ACCESS_DENIED
            error_message = 'Access to the client process was denied'
        elif 'unsupported' in diagnostic and 'version' in diagnostic:
            error_code = errors.CLIENT_VERSION_UNSUPPORTED
            error_message = 'Client version is not supported for key extraction'
        elif script_result['returncode'] == 0:
            error_code = errors.KEY_NOT_FOUND
            error_message = 'No key was found in the running client process'
        else:
            error_code = errors.KEY_EXTRACTION_FAILED
            error_message = 'Key extraction failed'
        return build_result(
            ok=False,
            connector=connector,
            action='extract-key',
            error_code=error_code,
            error_message=error_message,
            runtime_dir=runtime['runtime_root'],
            keys_file=runtime['keys_file'],
        )

    return build_result(
        ok=True,
        connector=connector,
        action='extract-key',
        error_code=errors.OK,
        runtime_dir=runtime['runtime_root'],
        config_file=runtime['config_file'],
        keys_file=runtime['keys_file'],
    )


def decrypt(connector: str, runtime_dir: str, database_list: list[str] | None = None) -> dict:
    runtime = load_runtime_config(connector, runtime_dir)
    if runtime is None:
        detect = detect_connector(connector)
        if not detect['ok']:
            return build_result(
                ok=False,
                connector=connector,
                action='decrypt',
                error_code=detect['error_code'],
                error_message=detect['error_message'],
            )
        runtime = write_runtime_config(connector, runtime_dir, detect['db_dir'])

    if not runtime['db_dir'] or not os.path.isdir(runtime['db_dir']):
        return build_result(
            ok=False,
            connector=connector,
            action='decrypt',
            error_code=errors.DATA_PATH_NOT_FOUND,
            error_message='Data path not found',
        )
    if not os.path.exists(runtime['keys_file']):
        return build_result(
            ok=False,
            connector=connector,
            action='decrypt',
            error_code=errors.KEY_INVALID,
            error_message='Key file not found',
        )

    spec = CONNECTOR_SPECS[connector]
    extra_args: list[str] = []
    for database_name in database_list or []:
        name = str(database_name or '').strip()
        if name:
            extra_args.extend(['--db', name])

    script_result = run_managed_script(spec['decrypt_script'], runtime['app_dir'], *extra_args)
    if script_result['returncode'] != 0:
        return build_result(
            ok=False,
            connector=connector,
            action='decrypt',
            error_code=errors.DECRYPT_FAILED,
            error_message='Decrypt failed',
            runtime_dir=runtime['runtime_root'],
        )

    return build_result(
        ok=True,
        connector=connector,
        action='decrypt',
        error_code=errors.OK,
        runtime_dir=runtime['runtime_root'],
        decrypted_dir=runtime['decrypted_dir'],
        stdout=script_result.get('stdout', ''),
        stderr=script_result.get('stderr', ''),
    )
