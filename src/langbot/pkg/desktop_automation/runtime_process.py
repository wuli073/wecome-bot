from __future__ import annotations

import asyncio
import datetime
import json
import logging
import os
import re
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable, Mapping

import psutil

from ..broadcast.send_gate import resolve_broadcast_send_gate
from ..utils import paths as runtime_paths
from .client import DesktopRuntimeClient
from .errors import (
    DesktopAutomationError,
    RPA_RUNTIME_NOT_AVAILABLE,
    RUNTIME_DISABLED,
    RUNTIME_OWNERSHIP_CONFLICT,
    RUNTIME_PROTOCOL_MISMATCH,
    RUNTIME_START_FAILED,
    RUNTIME_UNAVAILABLE,
)

logger = logging.getLogger(__name__)

SpawnRuntimeCallable = Callable[..., Awaitable[Any]]

_OFFICIAL_RUNTIME_EXE_NAME = 'LangBot Desktop RPA Runtime.exe'
_OFFICIAL_RUNTIME_BUILD_DIR_PATTERN = re.compile(r'^\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}-\d{3}Z$')
_PACKAGED_RUNTIME_RELATIVE_PATH = Path('runtime') / 'desktop-rpa' / _OFFICIAL_RUNTIME_EXE_NAME
_DETERMINISTIC_SOURCE_RUNTIME_RELATIVE_PATH = (
    Path('apps') / 'desktop-rpa-runtime' / 'dist-phase2-official' / 'win-dir' / 'win-unpacked' / _OFFICIAL_RUNTIME_EXE_NAME
)


@dataclass(frozen=True)
class RuntimeCandidate:
    executable_path: Path
    parsed_timestamp: datetime.datetime


@dataclass(frozen=True)
class OwnedRuntimeSnapshot:
    process: Any | None
    pid: int | None
    process_create_time: float | None
    manager_session_id: str
    runtime_info: dict[str, Any] | None
    client: DesktopRuntimeClient | Any | None
    stderr_task: asyncio.Task[Any] | None
    selected_runtime_executable: Path | None


def _normalize_path(pathlike: str | Path | None) -> Path | None:
    if pathlike is None:
        return None
    path_str = str(pathlike).strip()
    if not path_str:
        return None
    try:
        return Path(path_str).resolve(strict=False)
    except OSError:
        return Path(path_str)


def _official_runtime_root(root: Path) -> Path:
    return root / 'apps' / 'desktop-rpa-runtime' / 'dist-phase2-official'


def _deterministic_source_runtime_executable(root: Path) -> Path:
    return root / _DETERMINISTIC_SOURCE_RUNTIME_RELATIVE_PATH


def _packaged_runtime_executable(root: Path) -> Path:
    return root / _PACKAGED_RUNTIME_RELATIVE_PATH


def _is_under_runtime_output_root(candidate: Path, root: Path) -> bool:
    official_root = _official_runtime_root(root).resolve(strict=False)
    try:
        candidate.resolve(strict=False).relative_to(official_root)
    except ValueError:
        return False
    return True


def _normalize_runtime_executable_candidate(pathlike: str | Path | None) -> Path | None:
    normalized = _normalize_path(pathlike)
    if normalized is None:
        return None
    if normalized.is_dir():
        direct_candidate = normalized / _OFFICIAL_RUNTIME_EXE_NAME
        if direct_candidate.exists():
            return direct_candidate.resolve(strict=False)
        unpacked_candidate = normalized / 'win-unpacked' / _OFFICIAL_RUNTIME_EXE_NAME
        if unpacked_candidate.exists():
            return unpacked_candidate.resolve(strict=False)
        return None
    if normalized.name != _OFFICIAL_RUNTIME_EXE_NAME:
        return None
    return normalized


def _is_valid_packaged_runtime_executable_path(candidate: Path, root: Path) -> bool:
    normalized = _normalize_path(candidate)
    if normalized is None or normalized.name != _OFFICIAL_RUNTIME_EXE_NAME:
        return False
    expected = _packaged_runtime_executable(root).resolve(strict=False)
    return normalized == expected


def _is_valid_runtime_executable_path(candidate: Path, root: Path) -> bool:
    if runtime_paths.is_packaged_mode():
        return _is_valid_packaged_runtime_executable_path(candidate, root)
    normalized = _normalize_path(candidate)
    if normalized is None:
        return False
    if normalized == _deterministic_source_runtime_executable(root).resolve(strict=False):
        return True
    if normalized.name != _OFFICIAL_RUNTIME_EXE_NAME:
        return False
    if normalized.parent.name != 'win-unpacked':
        return False
    build_dir = normalized.parent.parent
    return (
        build_dir.parent == _official_runtime_root(root)
        and _OFFICIAL_RUNTIME_BUILD_DIR_PATTERN.match(build_dir.name) is not None
    )


def _is_valid_official_runtime_build_dir(path: Path) -> bool:
    return path.is_dir() and _OFFICIAL_RUNTIME_BUILD_DIR_PATTERN.match(path.name) is not None


def _parse_runtime_build_timestamp(build_dir_name: str) -> datetime.datetime | None:
    if _OFFICIAL_RUNTIME_BUILD_DIR_PATTERN.fullmatch(build_dir_name) is None:
        return None
    try:
        return datetime.datetime.strptime(build_dir_name, '%Y-%m-%dT%H-%M-%S-%fZ').replace(tzinfo=datetime.timezone.utc)
    except ValueError:
        return None


def list_runtime_candidates(*, repo_root=None) -> list[RuntimeCandidate]:
    root = Path(repo_root or _default_runtime_root())
    if runtime_paths.is_packaged_mode():
        packaged_executable = resolve_runtime_executable_path(repo_root=root)
        if packaged_executable is None:
            return []
        return [
            RuntimeCandidate(
                executable_path=packaged_executable,
                parsed_timestamp=datetime.datetime.fromtimestamp(0, tz=datetime.timezone.utc),
            )
        ]
    deterministic_runtime = _deterministic_source_runtime_executable(root).resolve(strict=False)
    if deterministic_runtime.exists():
        return [
            RuntimeCandidate(
                executable_path=deterministic_runtime,
                parsed_timestamp=datetime.datetime.fromtimestamp(0, tz=datetime.timezone.utc),
            )
        ]
    official_root = _official_runtime_root(root)
    if not official_root.exists():
        return []

    candidates: list[RuntimeCandidate] = []
    for build_dir in official_root.iterdir():
        if not _is_valid_official_runtime_build_dir(build_dir):
            continue
        parsed_timestamp = _parse_runtime_build_timestamp(build_dir.name)
        if parsed_timestamp is None:
            continue
        executable_path = build_dir / 'win-unpacked' / _OFFICIAL_RUNTIME_EXE_NAME
        if not executable_path.exists():
            continue
        candidates.append(
            RuntimeCandidate(
                executable_path=executable_path,
                parsed_timestamp=parsed_timestamp,
            )
        )

    candidates.sort(key=lambda candidate: candidate.parsed_timestamp, reverse=True)
    return candidates


def resolve_latest_runtime_executable(*, repo_root=None) -> Path | None:
    candidates = list_runtime_candidates(repo_root=repo_root)
    if not candidates:
        return None
    return candidates[0].executable_path


def resolve_runtime_executable_path(*, configured: str = '', repo_root=None):
    root = Path(repo_root or _default_runtime_root())
    configured_candidate = _normalize_runtime_executable_candidate(configured)
    if configured_candidate is not None:
        if runtime_paths.is_packaged_mode():
            if _is_valid_packaged_runtime_executable_path(configured_candidate, root):
                return configured_candidate
        elif configured_candidate.exists():
            deterministic_candidate = _deterministic_source_runtime_executable(root).resolve(strict=False)
            if configured_candidate == deterministic_candidate:
                return configured_candidate
            if not _is_under_runtime_output_root(configured_candidate, root):
                return configured_candidate

    if runtime_paths.is_packaged_mode():
        packaged_candidate = _normalize_runtime_executable_candidate(
            os.environ.get('CHATBOT_RPA_RUNTIME_PATH', '').strip()
        )
        if packaged_candidate is None:
            packaged_candidate = _packaged_runtime_executable(root).resolve(strict=False)
        if _is_valid_packaged_runtime_executable_path(packaged_candidate, root):
            return packaged_candidate
        return None

    return resolve_latest_runtime_executable(repo_root=root)


def _default_runtime_root() -> Path:
    if runtime_paths.is_packaged_mode():
        return Path(runtime_paths.get_install_root())
    repo_root = runtime_paths.get_repo_root()
    if repo_root:
        return Path(repo_root)
    return Path(__file__).resolve().parents[4]


def apply_local_desktop_automation_defaults(config: dict[str, Any] | None) -> dict[str, Any]:
    normalized = dict(config or {})
    normalized.setdefault('enabled', False)
    normalized.setdefault('runtime_executable', '')
    normalized.setdefault('startup_timeout_seconds', 30)
    normalized.setdefault('task_timeout_seconds', 120)
    normalized.setdefault('stale_run_seconds', 300)
    normalized.setdefault('expected_protocol_version', '1')
    normalized.setdefault('runtime_version', '0.1.0')
    return normalized


class DesktopRuntimeProcessManager:
    def __init__(
        self,
        *,
        config: dict[str, Any],
        broadcast_config: dict[str, Any] | None = None,
        runtime_root=None,
        spawn_runtime=None,
        client_factory=None,
    ) -> None:
        self.config = apply_local_desktop_automation_defaults(config)
        self.broadcast_config = dict(broadcast_config or {})
        self.runtime_root = Path(runtime_root or _default_runtime_root())
        self.spawn_runtime = spawn_runtime or self._spawn_runtime
        self.client_factory = client_factory or self._build_client
        self.process = None
        self.client: DesktopRuntimeClient | Any | None = None
        self.runtime_info: dict[str, Any] | None = None
        self._lock = asyncio.Lock()
        self._stderr_task = None
        self._selected_runtime_executable: Path | None = None
        self._manager_session_id = secrets.token_hex(8)
        self._stopping = False
        self._runtime_log_dir = _normalize_path(os.environ.get('LANGBOT_RPA_LOG_DIR'))

    async def ensure_started(self) -> dict[str, Any]:
        async with self._lock:
            runtime_candidates = list_runtime_candidates(repo_root=self.runtime_root)
            for candidate in runtime_candidates:
                logger.info(
                    'Desktop runtime candidate: %s | parsedTimestamp=%s',
                    str(candidate.executable_path),
                    candidate.parsed_timestamp.isoformat(),
                )
            target_runtime = resolve_runtime_executable_path(
                configured=str(self.config.get('runtime_executable') or ''),
                repo_root=self.runtime_root,
            )
            if target_runtime is None:
                if not bool(self.config.get('enabled')):
                    raise DesktopAutomationError(RUNTIME_DISABLED, 'Desktop automation runtime is disabled')
                raise DesktopAutomationError(
                    RPA_RUNTIME_NOT_AVAILABLE,
                    'Desktop automation runtime executable is not available',
                )

            if not bool(self.config.get('enabled')):
                raise DesktopAutomationError(RUNTIME_DISABLED, 'Desktop automation runtime is disabled')

            self._selected_runtime_executable = target_runtime
            if await self._can_reuse_running_runtime(target_runtime):
                logger.info('Reusing desktop runtime: %s', str(target_runtime))
                return dict(self.runtime_info)

            conflict = self._find_unmanaged_runtime_conflict(target_runtime)
            if conflict is not None:
                raise DesktopAutomationError(
                    RUNTIME_OWNERSHIP_CONFLICT,
                    '检测到独立运行的 Desktop Runtime。请关闭该进程，或使用启动器的显式恢复参数后重试。',
                    details=conflict,
                )

            self._replace_stale_runtime_processes(target_runtime)

            logger.info('Selected desktop runtime: %s', str(target_runtime))
            token = secrets.token_urlsafe(48)
            env = dict(os.environ)
            send_gate = self._resolve_send_gate(env=env)
            env['LANGBOT_RPA_MANAGED'] = '1'
            env['LANGBOT_RPA_TOKEN'] = token
            env.update(send_gate.to_runtime_environment())
            env['LANGBOT_RPA_ALLOW_AUTO_SEND'] = '1' if send_gate.send_enabled else '0'
            env['LANGBOT_RPA_FORCE_DISABLE_SEND'] = '0' if send_gate.send_enabled else '1'
            logger.info(
                'Desktop runtime broadcast send gate: broadcast_send_enabled=%s allowed_connector_count=%s',
                send_gate.send_enabled,
                send_gate.allowed_connector_count,
            )

            try:
                self.process = await self.spawn_runtime(target_runtime, env=env, cwd=target_runtime.parent)
            except Exception as exc:  # pragma: no cover - exercised by integration later
                raise DesktopAutomationError(RUNTIME_START_FAILED, 'Failed to spawn desktop runtime') from exc

            if getattr(self.process, 'stderr', None) is not None:
                self._stderr_task = asyncio.create_task(self._drain_stream(self.process.stderr))

            try:
                handshake = await self._read_handshake(self.process)
                spawn_pid = int(getattr(self.process, 'pid'))
                if int(handshake['pid']) != spawn_pid:
                    raise DesktopAutomationError(RUNTIME_START_FAILED, 'Desktop runtime handshake pid mismatch')
                expected_protocol_version = str(self.config.get('expected_protocol_version') or '1')
                if str(handshake['protocolVersion']) != expected_protocol_version:
                    raise DesktopAutomationError(
                        RUNTIME_PROTOCOL_MISMATCH,
                        f'Runtime protocol mismatch: expected {expected_protocol_version}, got {handshake["protocolVersion"]}',
                    )

                runtime_info = {
                    'pid': spawn_pid,
                    'processCreateTime': self._read_process_create_time(spawn_pid),
                    'host': '127.0.0.1',
                    'port': int(handshake['port']),
                    'protocolVersion': str(handshake['protocolVersion']),
                    'runtimeVersion': str(handshake['runtimeVersion']),
                    'token': token,
                    'executablePath': str(target_runtime),
                }
                self.client = self.client_factory(runtime_info)
                await self._wait_until_ready()
                self.runtime_info = runtime_info
                return dict(runtime_info)
            except BaseException as exc:
                await self._cleanup_failed_startup(exc)
                raise

    async def stop(self) -> None:
        async with self._lock:
            await self._stop_locked()
        return None

    async def _stop_locked(self) -> None:
        snapshot = self._build_owned_snapshot()
        if snapshot is None:
            return None

        self._stopping = True
        try:
            await self._terminate_owned_runtime_snapshot(snapshot)
        finally:
            await self._cleanup_stderr_task(snapshot.stderr_task)
            self.process = None
            self.client = None
            self.runtime_info = None
            self._stderr_task = None
            self._selected_runtime_executable = None
            self._stopping = False
        return None

    def close(self) -> None:
        return None

    async def get_status(self) -> dict[str, Any]:
        send_gate = self._resolve_send_gate()
        if not bool(self.config.get('enabled')):
            return {
                'status': 'disabled',
                'errorCode': RUNTIME_DISABLED,
                'runtime_configured': False,
                'runtime_startable': False,
                'runtime_reachable': False,
                'send_enabled': False,
                'allowed_connector_count': send_gate.allowed_connector_count,
                'send_error_code': send_gate.error_code,
            }

        runtime_executable = resolve_runtime_executable_path(
            configured=str(self.config.get('runtime_executable') or ''),
            repo_root=self.runtime_root,
        )
        if runtime_executable is None:
            return {
                'status': 'not_available',
                'errorCode': RPA_RUNTIME_NOT_AVAILABLE,
                'runtime_configured': False,
                'runtime_startable': False,
                'runtime_reachable': False,
                'send_enabled': False,
                'allowed_connector_count': send_gate.allowed_connector_count,
                'send_error_code': send_gate.error_code,
            }

        if self.client is None or self.runtime_info is None:
            try:
                await self.ensure_started()
            except DesktopAutomationError as exc:
                return {
                    'status': 'failed' if exc.code == RUNTIME_UNAVAILABLE else 'stopped',
                    'errorCode': exc.code,
                    'runtime_configured': True,
                    'runtime_startable': True,
                    'runtime_reachable': False,
                    'send_enabled': False,
                    'allowed_connector_count': send_gate.allowed_connector_count,
                    'send_error_code': send_gate.error_code,
                }
            except Exception:
                return {
                    'status': 'failed',
                    'errorCode': RUNTIME_UNAVAILABLE,
                    'runtime_configured': True,
                    'runtime_startable': True,
                    'runtime_reachable': False,
                    'send_enabled': False,
                    'allowed_connector_count': send_gate.allowed_connector_count,
                    'send_error_code': send_gate.error_code,
                }

        try:
            health = await self.client.health()
            status_payload = await self.client.capabilities()
        except Exception:
            return {
                'status': 'failed',
                'errorCode': RUNTIME_UNAVAILABLE,
                'runtime_configured': True,
                'runtime_startable': True,
                'runtime_reachable': False,
                'send_enabled': False,
                'allowed_connector_count': send_gate.allowed_connector_count,
                'send_error_code': send_gate.error_code,
            }

        return {
            'status': health.get('status', 'ready'),
            'host': self.runtime_info['host'],
            'port': self.runtime_info['port'],
            'runtimeVersion': self.runtime_info['runtimeVersion'],
            'protocolVersion': self.runtime_info['protocolVersion'],
            'runtime_configured': True,
            'runtime_startable': True,
            'runtime_reachable': True,
            'send_enabled': bool(status_payload.get('sendEnabled', send_gate.send_enabled)),
            'allowed_connector_count': int(
                status_payload.get('allowedConnectorCount', send_gate.allowed_connector_count)
            ),
            'send_error_code': status_payload.get('sendErrorCode', send_gate.error_code),
            'windowingAvailable': status_payload.get('windowingAvailable'),
            'captureAvailable': status_payload.get('captureAvailable'),
            'inputAvailable': status_payload.get('inputAvailable'),
            'providerHubReady': status_payload.get('providerHubReady'),
        }

    def _resolve_send_gate(self, *, env: Mapping[str, Any] | None = None):
        return resolve_broadcast_send_gate(
            broadcast_config=self.broadcast_config,
            env=env or os.environ,
        )

    def _build_client(self, runtime_info: dict[str, Any]) -> DesktopRuntimeClient:
        return DesktopRuntimeClient(
            base_url=f'http://{runtime_info["host"]}:{runtime_info["port"]}',
            token=str(runtime_info['token']),
            expected_protocol_version=str(self.config.get('expected_protocol_version') or '1'),
        )

    async def _can_reuse_running_runtime(self, target_runtime: Path) -> bool:
        target_path = _normalize_path(target_runtime)
        current_runtime = self.runtime_info or {}
        current_path = _normalize_path(current_runtime.get('executablePath'))
        if (
            self._stopping
            or self.process is None
            or self.client is None
            or self.runtime_info is None
            or target_path is None
            or current_path != target_path
        ):
            return False

        if not self._process_is_alive(self.process):
            return False

        process_path = self._get_process_executable_path(self.process)
        if process_path != target_path:
            return False
        if not self._process_create_time_matches(self.process, current_runtime.get('processCreateTime')):
            return False

        try:
            health = await self.client.health()
        except Exception:
            return False
        return health.get('status') == 'ready'

    def _replace_stale_runtime_processes(self, target_runtime: Path) -> None:
        normalized_target = _normalize_path(target_runtime)
        if normalized_target is None:
            return
        logger.info(
            'Skipping global stale desktop runtime cleanup for ownership isolation: target=%s session=%s',
            str(normalized_target),
            self._manager_session_id,
        )

    def _find_unmanaged_runtime_conflict(self, target_runtime: Path) -> dict[str, Any] | None:
        normalized_target = _normalize_path(target_runtime)
        if normalized_target is None:
            return None

        owned_snapshot = self._build_owned_snapshot()
        for process in self._iter_runtime_processes():
            executable_path = self._get_process_executable_path(process)
            if executable_path is None or not self._is_project_runtime_path(executable_path):
                continue
            if self._is_owned_runtime_process(process, executable_path, owned_snapshot):
                continue
            build_timestamp = executable_path.parent.parent.name
            return {
                'pid': int(getattr(process, 'pid')),
                'executable_path': str(executable_path),
                'build_timestamp': build_timestamp,
            }
        return None

    def _iter_runtime_processes(self):
        for process in psutil.process_iter():
            try:
                process_name = process.name()
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.Error):
                continue
            if process_name != _OFFICIAL_RUNTIME_EXE_NAME:
                continue
            yield process

    def _get_process_executable_path(self, process) -> Path | None:
        if hasattr(process, 'exe'):
            try:
                executable = process.exe()
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.Error, OSError):
                return None
            return _normalize_path(executable)

        if self._selected_runtime_executable is not None and process is self.process:
            return _normalize_path(self._selected_runtime_executable)

        try:
            args = list(getattr(process, 'args', []))
        except TypeError:
            return None
        if not args:
            return None
        return _normalize_path(args[0])

    def _is_project_runtime_path(self, executable_path: Path) -> bool:
        try:
            executable_path.relative_to(self.runtime_root.resolve(strict=False))
        except ValueError:
            return False

        if runtime_paths.is_packaged_mode():
            return _is_valid_packaged_runtime_executable_path(executable_path, self.runtime_root)
        if executable_path == _deterministic_source_runtime_executable(self.runtime_root).resolve(strict=False):
            return True

        if executable_path.name != _OFFICIAL_RUNTIME_EXE_NAME:
            return False
        if executable_path.parent.name != 'win-unpacked':
            return False
        build_dir = executable_path.parent.parent
        if build_dir.parent != _official_runtime_root(self.runtime_root):
            return False
        return _OFFICIAL_RUNTIME_BUILD_DIR_PATTERN.match(build_dir.name) is not None

    def _is_owned_runtime_process(self, process, executable_path: Path, snapshot: OwnedRuntimeSnapshot | None) -> bool:
        if snapshot is None or snapshot.pid is None or snapshot.process_create_time is None:
            return False
        if int(getattr(process, 'pid', -1)) != int(snapshot.pid):
            return False
        if snapshot.selected_runtime_executable is not None and executable_path != snapshot.selected_runtime_executable:
            return False
        actual_create_time = self._safe_get_process_create_time(process)
        if actual_create_time is None:
            return False
        return abs(actual_create_time - float(snapshot.process_create_time)) <= 2

    def _terminate_psutil_tree(self, process) -> None:
        try:
            children = list(process.children(recursive=True))
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.Error):
            children = []

        for child in children:
            try:
                child.terminate()
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.Error):
                continue

        try:
            process.terminate()
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.Error):
            pass

        processes = children + [process]

        try:
            _, alive = psutil.wait_procs(processes, timeout=5)
        except AttributeError:
            alive = []

        alive_children = [child for child in alive if getattr(child, 'pid', None) != getattr(process, 'pid', None)]
        alive_parent = next(
            (child for child in alive if getattr(child, 'pid', None) == getattr(process, 'pid', None)),
            None,
        )

        for child in alive_children:
            try:
                child.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.Error):
                continue

        if alive_parent is not None:
            try:
                alive_parent.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.Error):
                pass

        try:
            psutil.wait_procs(alive, timeout=5)
        except AttributeError:
            pass

    @staticmethod
    def _process_is_alive(process) -> bool:
        if process is None:
            return False
        if hasattr(process, 'is_running'):
            try:
                return bool(process.is_running())
            except Exception:
                return False
        return getattr(process, 'returncode', None) is None

    @staticmethod
    def _is_psutil_process(process) -> bool:
        return isinstance(process, psutil.Process)

    @staticmethod
    def _process_create_time_matches(process, expected_created_at: float | None) -> bool:
        if expected_created_at is None:
            return True
        try:
            pid = int(getattr(process, 'pid'))
            actual_create_time = psutil.Process(pid).create_time()
        except (AttributeError, TypeError, ValueError, psutil.NoSuchProcess, psutil.AccessDenied, psutil.Error):
            return False
        return abs(actual_create_time - float(expected_created_at)) <= 2

    async def _wait_until_ready(self) -> None:
        timeout_seconds = float(self.config.get('startup_timeout_seconds') or 30)
        deadline = asyncio.get_running_loop().time() + timeout_seconds
        last_health_error: Exception | None = None

        while asyncio.get_running_loop().time() < deadline:
            if self.process is not None and not self._process_is_alive(self.process):
                raise DesktopAutomationError(RUNTIME_START_FAILED, 'Desktop runtime exited before readiness')
            try:
                health = await self.client.health()
            except Exception as exc:
                last_health_error = exc
                await asyncio.sleep(0.1)
                continue
            if health.get('status') == 'ready':
                return
            await asyncio.sleep(0.1)
        if last_health_error is not None:
            raise DesktopAutomationError(RUNTIME_UNAVAILABLE, 'Desktop runtime readiness health check failed') from last_health_error
        raise DesktopAutomationError(RUNTIME_UNAVAILABLE, 'Desktop runtime failed to become ready in time')

    async def _read_handshake(self, process) -> dict[str, Any]:
        stdout = getattr(process, 'stdout', None)
        if stdout is None or not hasattr(stdout, 'readline'):
            raise DesktopAutomationError(RUNTIME_START_FAILED, 'Runtime stdout is not readable')

        timeout_seconds = float(self.config.get('startup_timeout_seconds') or 30)
        deadline = asyncio.get_running_loop().time() + timeout_seconds
        raw_line = b''
        while asyncio.get_running_loop().time() < deadline:
            remaining = max(0.1, deadline - asyncio.get_running_loop().time())
            try:
                raw_line = await asyncio.wait_for(stdout.readline(), timeout=remaining)
            except asyncio.TimeoutError as exc:
                raise DesktopAutomationError(
                    RUNTIME_UNAVAILABLE, 'Timed out waiting for desktop runtime handshake'
                ) from exc
            if not raw_line:
                raise DesktopAutomationError(RUNTIME_START_FAILED, 'Desktop runtime exited before handshake')
            if raw_line.strip():
                break
        if not raw_line.strip():
            raise DesktopAutomationError(RUNTIME_UNAVAILABLE, 'Timed out waiting for desktop runtime handshake')
        try:
            payload = json.loads(raw_line.decode('utf-8').strip())
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise DesktopAutomationError(RUNTIME_START_FAILED, 'Desktop runtime handshake is not valid JSON') from exc

        required_keys = {'pid', 'port', 'protocolVersion', 'runtimeVersion'}
        if set(payload.keys()) != required_keys:
            raise DesktopAutomationError(RUNTIME_START_FAILED, 'Desktop runtime handshake shape is invalid')
        return payload

    async def _spawn_runtime(self, runtime_executable: Path, *, env: dict[str, str], cwd: Path):
        command = [str(runtime_executable)]
        runtime_user_data_dir = str(env.get('LANGBOT_RPA_USER_DATA_DIR', '')).strip()
        if runtime_user_data_dir:
            command.append(f'--user-data-dir={runtime_user_data_dir}')
        return await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(cwd),
            env=env,
        )

    async def _drain_stream(self, stream) -> None:
        while True:
            line = await stream.readline()
            if not line:
                return
            self._write_runtime_stderr_event(line)

    def _write_runtime_stderr_event(self, line: bytes) -> None:
        """Record a sanitized runtime stderr event without persisting user content."""
        if self._runtime_log_dir is None:
            return
        try:
            self._runtime_log_dir.mkdir(parents=True, exist_ok=True)
            raw = line.decode('utf-8', errors='replace').strip()
            code_match = re.search(r'\b([A-Z][A-Z0-9_]{2,})\b', raw)
            code = code_match.group(1) if code_match else 'RUNTIME_STDERR'
            entry = json.dumps(
                {
                    'event': 'runtime_stderr',
                    'code': code,
                    'session': self._manager_session_id,
                },
                ensure_ascii=True,
            )
            with (self._runtime_log_dir / 'desktop-runtime.stderr.log').open('a', encoding='utf-8') as file:
                file.write(entry + '\n')
        except OSError:
            logger.debug('Unable to write desktop runtime stderr event', exc_info=True)

    def _build_owned_snapshot(self) -> OwnedRuntimeSnapshot | None:
        process = self.process
        runtime_info = self.runtime_info
        client = self.client
        stderr_task = self._stderr_task
        selected_runtime_executable = _normalize_path(
            self._selected_runtime_executable
            or ((runtime_info or {}).get('executablePath') if isinstance(runtime_info, dict) else None)
        )
        pid = self._coerce_int(getattr(process, 'pid', None))
        if pid is None and isinstance(runtime_info, dict):
            pid = self._coerce_int(runtime_info.get('pid'))

        process_create_time = None
        if isinstance(runtime_info, dict):
            process_create_time = self._coerce_float(runtime_info.get('processCreateTime'))
        if process_create_time is None and pid is not None:
            process_create_time = self._read_process_create_time(pid)

        if (
            process is None
            and runtime_info is None
            and client is None
            and stderr_task is None
            and selected_runtime_executable is None
        ):
            return None

        return OwnedRuntimeSnapshot(
            process=process,
            pid=pid,
            process_create_time=process_create_time,
            manager_session_id=self._manager_session_id,
            runtime_info=runtime_info,
            client=client,
            stderr_task=stderr_task,
            selected_runtime_executable=selected_runtime_executable,
        )

    async def _cleanup_failed_startup(self, original_exc: BaseException) -> None:
        try:
            await self._stop_locked()
        except BaseException as cleanup_exc:
            logger.warning(
                'Desktop runtime startup cleanup failed after %s: %s (session=%s)',
                original_exc.__class__.__name__,
                cleanup_exc,
                self._manager_session_id,
            )

    async def _terminate_owned_runtime_snapshot(self, snapshot: OwnedRuntimeSnapshot) -> None:
        owned_process = self._resolve_owned_psutil_process(snapshot)
        if owned_process is not None:
            self._terminate_psutil_tree(owned_process)

    async def _cleanup_stderr_task(self, task: asyncio.Task[Any] | None) -> None:
        if task is None:
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            return
        except Exception:
            return

    def _resolve_owned_psutil_process(self, snapshot: OwnedRuntimeSnapshot):
        if snapshot.pid is None:
            return None

        try:
            process = psutil.Process(snapshot.pid)
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.Error):
            logger.warning('Desktop runtime process is no longer available during stop: pid=%s', snapshot.pid)
            return None

        expected_create_time = snapshot.process_create_time
        if expected_create_time is None:
            logger.warning(
                'Desktop runtime create time is unavailable during stop; refusing termination: pid=%s session=%s',
                snapshot.pid,
                snapshot.manager_session_id,
            )
            return None
        try:
            actual_create_time = process.create_time()
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.Error):
            return None
        if abs(actual_create_time - float(expected_create_time)) > 2:
            logger.warning(
                'Desktop runtime PID reuse detected during stop: pid=%s expected_create_time=%s actual_create_time=%s session=%s',
                snapshot.pid,
                expected_create_time,
                actual_create_time,
                snapshot.manager_session_id,
            )
            return None

        expected_path = snapshot.selected_runtime_executable
        if expected_path is None:
            logger.warning('Desktop runtime executable path is unavailable during stop: pid=%s', snapshot.pid)
            return None

        actual_path = self._get_process_executable_path(process)
        if actual_path != expected_path:
            logger.warning(
                'Desktop runtime executable path changed before stop: pid=%s expected=%s actual=%s',
                snapshot.pid,
                str(expected_path),
                str(actual_path),
            )
            return None

        if not _is_valid_runtime_executable_path(actual_path, self.runtime_root):
            logger.warning('Desktop runtime executable path is no longer owned: pid=%s path=%s', snapshot.pid, str(actual_path))
            return None

        return process

    @staticmethod
    def _coerce_int(value) -> int | None:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _coerce_float(value) -> float | None:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _read_process_create_time(pid: int) -> float | None:
        try:
            return float(psutil.Process(int(pid)).create_time())
        except (AttributeError, TypeError, ValueError, psutil.NoSuchProcess, psutil.AccessDenied, psutil.Error):
            return None

    @staticmethod
    def _safe_get_process_create_time(process) -> float | None:
        try:
            return float(process.create_time())
        except (AttributeError, TypeError, ValueError, psutil.NoSuchProcess, psutil.AccessDenied, psutil.Error):
            return None
