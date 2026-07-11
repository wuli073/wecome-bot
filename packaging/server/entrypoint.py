from __future__ import annotations

import argparse
import asyncio
import json
import os
import signal
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from langbot.pkg.core import boot


# Task 1 packaged startup interface contract references:
# - backend health: src/langbot/pkg/api/http/controller/main.py:272-275 -> GET /healthz
# - Desktop RPA runtime status: src/langbot/pkg/api/http/controller/groups/bot_database_mode.py:661-677
#   -> GET /api/v1/desktop-automation/runtime/status
# - graceful shutdown: packaged launcher uses an owner-scoped control file under %LOCALAPPDATA%\Chatbot\runtime
# - packaged host/port source: launcher-provided host/port overrides, always forced to 127.0.0.1
BACKEND_HEALTH_PATH = '/healthz'
BACKEND_RUNTIME_STATUS_PATH = '/api/v1/desktop-automation/runtime/status'
PACKAGED_BIND_HOST = '127.0.0.1'
DEFAULT_BACKEND_PORT = 5302
DEFAULT_SHUTDOWN_FILENAME = 'backend-shutdown.json'
DEFAULT_SHUTDOWN_ACK_FILENAME = 'backend-shutdown.ack.json'
DEFAULT_RPA_RUNTIME_RELATIVE_PATH = Path('runtime') / 'desktop-rpa' / 'LangBot Desktop RPA Runtime.exe'


@dataclass(frozen=True)
class PackagedBackendConfig:
    install_root: Path
    resources_root: Path
    user_data_root: Path
    data_root: Path
    log_root: Path
    runtime_root: Path
    shutdown_request_path: Path
    rpa_runtime_path: Path
    host: str
    port: int


def _resolve_path(pathlike: str | Path) -> Path:
    return Path(pathlike).expanduser().resolve(strict=False)


def _parse_port(value: int | str) -> int:
    try:
        port = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f'invalid backend port: {value!r}') from exc
    if not 1 <= port <= 65535:
        raise ValueError(f'backend port must be between 1 and 65535: {value!r}')
    return port


def build_packaged_backend_config(
    *,
    install_root: str | Path,
    local_app_data: str | Path | None = None,
    user_data_root: str | Path | None = None,
    host: str = PACKAGED_BIND_HOST,
    port: int | str = DEFAULT_BACKEND_PORT,
    rpa_runtime_path: str | Path | None = None,
    shutdown_request_path: str | Path | None = None,
) -> PackagedBackendConfig:
    install_root_path = _resolve_path(install_root)
    resources_root = install_root_path / 'resources'

    if user_data_root is not None:
        resolved_user_data_root = _resolve_path(user_data_root)
    else:
        if local_app_data is None:
            raise ValueError('local_app_data is required when user_data_root is not provided')
        resolved_user_data_root = (_resolve_path(local_app_data) / 'Chatbot').resolve(strict=False)

    data_root = resolved_user_data_root / 'data'
    log_root = resolved_user_data_root / 'logs'
    runtime_root = resolved_user_data_root / 'runtime'

    resolved_shutdown_request_path = (
        _resolve_path(shutdown_request_path)
        if shutdown_request_path is not None
        else (runtime_root / DEFAULT_SHUTDOWN_FILENAME).resolve(strict=False)
    )
    try:
        resolved_shutdown_request_path.relative_to(runtime_root)
    except ValueError as exc:
        raise ValueError('shutdown_request_path must stay within the packaged runtime root') from exc

    resolved_rpa_runtime_path = (
        _resolve_path(rpa_runtime_path)
        if rpa_runtime_path is not None
        else (install_root_path / DEFAULT_RPA_RUNTIME_RELATIVE_PATH).resolve(strict=False)
    )

    return PackagedBackendConfig(
        install_root=install_root_path,
        resources_root=resources_root.resolve(strict=False),
        user_data_root=resolved_user_data_root,
        data_root=data_root.resolve(strict=False),
        log_root=log_root.resolve(strict=False),
        runtime_root=runtime_root.resolve(strict=False),
        shutdown_request_path=resolved_shutdown_request_path,
        rpa_runtime_path=resolved_rpa_runtime_path,
        host=PACKAGED_BIND_HOST if host else PACKAGED_BIND_HOST,
        port=_parse_port(port),
    )


def build_packaged_environment(
    config: PackagedBackendConfig,
    *,
    base_env: Mapping[str, str] | None = None,
) -> dict[str, str]:
    env = dict(base_env or os.environ)
    session_id = env.get('CHATBOT_LAUNCH_SESSION_ID', '').strip()
    session_log_root = env.get('CHATBOT_LOG_ROOT', '').strip() if session_id else ''
    env.update(
        {
            'CHATBOT_PACKAGED': '1',
            'CHATBOT_INSTALL_ROOT': str(config.install_root),
            'CHATBOT_USER_DATA_ROOT': str(config.user_data_root),
            'LANGBOT_DATA_ROOT': str(config.data_root),
            'CHATBOT_RESOURCES_ROOT': str(config.resources_root),
            'CHATBOT_WEB_ROOT': str(config.resources_root / 'web' / 'dist'),
            'CHATBOT_TEMPLATE_ROOT': str(config.resources_root / 'templates'),
            'CHATBOT_MIGRATION_ROOT': str(config.resources_root / 'migrations'),
            'CHATBOT_DEFAULTS_ROOT': str(config.resources_root / 'defaults'),
            'CHATBOT_LOG_ROOT': session_log_root or str(config.log_root),
            'CHATBOT_RUNTIME_ROOT': str(config.runtime_root),
            'CHATBOT_RPA_RUNTIME_PATH': str(config.rpa_runtime_path),
            'CHATBOT_BACKEND_HEALTH_PATH': BACKEND_HEALTH_PATH,
            'CHATBOT_BACKEND_RUNTIME_STATUS_PATH': BACKEND_RUNTIME_STATUS_PATH,
            'API__HOST': PACKAGED_BIND_HOST,
            'API__PORT': str(config.port),
            'DESKTOP_AUTOMATION__ENABLED': 'true',
            'DESKTOP_AUTOMATION__RUNTIME_EXECUTABLE': str(config.rpa_runtime_path),
            'PYTHONDONTWRITEBYTECODE': '1',
            'PYTHONUTF8': '1',
            'PYTHONIOENCODING': 'utf-8',
        }
    )
    return env


def prepare_packaged_runtime(config: PackagedBackendConfig) -> None:
    config.user_data_root.mkdir(parents=True, exist_ok=True)
    config.data_root.mkdir(parents=True, exist_ok=True)
    (config.data_root / 'logs').mkdir(parents=True, exist_ok=True)
    (config.data_root / 'labels').mkdir(parents=True, exist_ok=True)
    (config.data_root / 'metadata').mkdir(parents=True, exist_ok=True)
    config.log_root.mkdir(parents=True, exist_ok=True)
    config.runtime_root.mkdir(parents=True, exist_ok=True)
    os.chdir(config.user_data_root)


async def watch_shutdown_requests(*, app_inst, shutdown_request_path: Path) -> None:
    acknowledgement_path = shutdown_request_path.with_name(DEFAULT_SHUTDOWN_ACK_FILENAME)
    expected_session_id = os.environ.get('CHATBOT_LAUNCH_SESSION_ID', '').strip()
    while not app_inst.shutdown_requested_event.is_set():
        if shutdown_request_path.exists():
            try:
                payload = json.loads(shutdown_request_path.read_text(encoding='utf-8'))
            except Exception:
                payload = {}
            shutdown_request_path.unlink(missing_ok=True)
            if payload.get('action') == 'shutdown':
                request_id = str(payload.get('requestId') or '')
                request_session_id = str(payload.get('sessionId') or '')
                backend_pid = payload.get('backendPid')
                if not request_id or (expected_session_id and request_session_id != expected_session_id) or (expected_session_id and backend_pid != os.getpid()):
                    continue
                acknowledgement = {
                    'accepted': True,
                    'action': 'shutdown',
                    'requestId': request_id,
                    'sessionId': expected_session_id,
                    'backendPid': os.getpid(),
                }
                temporary_acknowledgement_path = acknowledgement_path.with_name(f'{acknowledgement_path.name}.tmp-{request_id}')
                temporary_acknowledgement_path.write_text(json.dumps(acknowledgement), encoding='utf-8')
                temporary_acknowledgement_path.replace(acknowledgement_path)
                reason = str(payload.get('reason') or 'packaged-control-file')
                app_inst.request_shutdown(f'packaged-control-file:{reason}')
                await app_inst.shutdown()
                return
        await asyncio.sleep(0.5)


async def packaged_main(
    loop: asyncio.AbstractEventLoop,
    *,
    shutdown_request_path: Path,
    state: dict[str, object] | None = None,
) -> int:
    app_inst = await boot.make_app(loop)
    if state is not None:
        state['app'] = app_inst
        if state.get('pending_shutdown'):
            app_inst.request_shutdown('pending-signal')
    watcher_task = loop.create_task(
        watch_shutdown_requests(app_inst=app_inst, shutdown_request_path=shutdown_request_path),
        name='packaged-backend-shutdown-watcher',
    )
    try:
        return await app_inst.run()
    finally:
        watcher_task.cancel()
        await asyncio.gather(watcher_task, return_exceptions=True)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Packaged LangBot backend entrypoint')
    parser.add_argument('--host', default=PACKAGED_BIND_HOST)
    parser.add_argument('--port', default=str(DEFAULT_BACKEND_PORT))
    parser.add_argument('--install-root', default=os.environ.get('CHATBOT_INSTALL_ROOT', ''))
    parser.add_argument('--user-data-root', default=os.environ.get('CHATBOT_USER_DATA_ROOT', ''))
    parser.add_argument('--shutdown-request-path', default='')
    parser.add_argument('--rpa-runtime-path', default=os.environ.get('CHATBOT_RPA_RUNTIME_PATH', ''))
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    os.environ['CHATBOT_PACKAGED'] = '1'

    install_root = args.install_root.strip()
    if not install_root:
        from langbot.pkg.utils import paths

        install_root = paths.get_install_root()

    user_data_root = args.user_data_root.strip() or None
    local_app_data = os.environ.get('LOCALAPPDATA', '').strip() or None
    if user_data_root is None and not local_app_data:
        raise SystemExit('LOCALAPPDATA is required for packaged startup when user-data root is not provided')

    config = build_packaged_backend_config(
        install_root=install_root,
        local_app_data=local_app_data,
        user_data_root=user_data_root,
        host=args.host,
        port=args.port,
        rpa_runtime_path=args.rpa_runtime_path.strip() or None,
        shutdown_request_path=args.shutdown_request_path.strip() or None,
    )

    prepare_packaged_runtime(config)
    os.environ.update(build_packaged_environment(config))

    loop = asyncio.new_event_loop()
    state: dict[str, object] = {'pending_shutdown': False, 'app': None}

    def signal_handler(sig, _frame):
        state['pending_shutdown'] = True
        app_inst = state.get('app')
        if loop.is_running() and app_inst is not None:
            loop.call_soon_threadsafe(app_inst.request_shutdown, f'signal:{sig}')

    signal.signal(signal.SIGINT, signal_handler)

    asyncio.set_event_loop(loop)
    try:
        task = loop.create_task(
            packaged_main(
                loop,
                shutdown_request_path=config.shutdown_request_path,
                state=state,
            ),
            name='packaged-backend-main',
        )
        return loop.run_until_complete(task)
    except KeyboardInterrupt:
        return 0
    finally:
        loop.run_until_complete(asyncio.gather(*asyncio.all_tasks(loop), return_exceptions=True))
        loop.close()
        asyncio.set_event_loop(None)


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
