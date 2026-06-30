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
from typing import Any, Awaitable, Callable

import psutil

from .client import DesktopRuntimeClient
from .errors import (
    DesktopAutomationError,
    RPA_RUNTIME_NOT_AVAILABLE,
    RUNTIME_DISABLED,
    RUNTIME_PROTOCOL_MISMATCH,
    RUNTIME_START_FAILED,
    RUNTIME_UNAVAILABLE,
)

logger = logging.getLogger(__name__)

SpawnRuntimeCallable = Callable[..., Awaitable[Any]]

_OFFICIAL_RUNTIME_EXE_NAME = 'LangBot Desktop RPA Runtime.exe'
_OFFICIAL_RUNTIME_BUILD_DIR_PATTERN = re.compile(r'^\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}-\d{3}Z$')


@dataclass(frozen=True)
class RuntimeCandidate:
    executable_path: Path
    parsed_timestamp: datetime.datetime


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


def _is_valid_runtime_executable_path(candidate: Path, root: Path) -> bool:
    normalized = _normalize_path(candidate)
    if normalized is None:
        return False
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
    root = Path(repo_root or Path(__file__).resolve().parents[4])
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
    _ = configured
    return resolve_latest_runtime_executable(repo_root=repo_root)


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
    def __init__(self, *, config: dict[str, Any], runtime_root=None, spawn_runtime=None, client_factory=None) -> None:
        self.config = apply_local_desktop_automation_defaults(config)
        self.runtime_root = Path(runtime_root or Path(__file__).resolve().parents[4])
        self.spawn_runtime = spawn_runtime or self._spawn_runtime
        self.client_factory = client_factory or self._build_client
        self.process = None
        self.client: DesktopRuntimeClient | Any | None = None
        self.runtime_info: dict[str, Any] | None = None
        self._lock = asyncio.Lock()
        self._stderr_task = None
        self._selected_runtime_executable: Path | None = None

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

            self._replace_stale_runtime_processes(target_runtime)

            logger.info('Selected desktop runtime: %s', str(target_runtime))
            token = secrets.token_urlsafe(48)
            env = dict(os.environ)
            env['LANGBOT_RPA_TOKEN'] = token

            try:
                self.process = await self.spawn_runtime(target_runtime, env=env, cwd=target_runtime.parent)
            except Exception as exc:  # pragma: no cover - exercised by integration later
                raise DesktopAutomationError(RUNTIME_START_FAILED, 'Failed to spawn desktop runtime') from exc

            if getattr(self.process, 'stderr', None) is not None:
                self._stderr_task = asyncio.create_task(self._drain_stream(self.process.stderr))

            handshake = await self._read_handshake(self.process)
            expected_protocol_version = str(self.config.get('expected_protocol_version') or '1')
            if str(handshake['protocolVersion']) != expected_protocol_version:
                await self.stop()
                raise DesktopAutomationError(
                    RUNTIME_PROTOCOL_MISMATCH,
                    f'Runtime protocol mismatch: expected {expected_protocol_version}, got {handshake["protocolVersion"]}',
                )

            runtime_info = {
                'pid': int(handshake['pid']),
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

    async def stop(self) -> None:
        if self.process is None:
            return None
        process = self.process
        self.process = None
        self.runtime_info = None
        self.client = None

        try:
            if getattr(process, 'returncode', None) is None and hasattr(process, 'terminate'):
                process.terminate()
            if hasattr(process, 'wait'):
                wait_result = process.wait(timeout=5) if self._is_psutil_process(process) else process.wait()
                if asyncio.iscoroutine(wait_result):
                    await asyncio.wait_for(wait_result, timeout=5)
        except Exception:
            if hasattr(process, 'kill'):
                process.kill()
        finally:
            if self._stderr_task is not None:
                self._stderr_task.cancel()
                self._stderr_task = None
        return None

    def close(self) -> None:
        return None

    async def get_status(self) -> dict[str, Any]:
        if not bool(self.config.get('enabled')):
            return {
                'status': 'disabled',
                'errorCode': RUNTIME_DISABLED,
                'runtime_configured': False,
                'runtime_startable': False,
                'runtime_reachable': False,
                'send_enabled': False,
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
            }

        if self.client is None or self.runtime_info is None:
            return {
                'status': 'stopped',
                'errorCode': None,
                'runtime_configured': True,
                'runtime_startable': True,
                'runtime_reachable': False,
                'send_enabled': False,
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
            'send_enabled': False,
            'windowingAvailable': status_payload.get('windowingAvailable'),
            'captureAvailable': status_payload.get('captureAvailable'),
            'inputAvailable': status_payload.get('inputAvailable'),
            'providerHubReady': status_payload.get('providerHubReady'),
        }

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
            self.process is None
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

        try:
            health = await self.client.health()
        except Exception:
            return False
        return health.get('status') == 'ready'

    def _replace_stale_runtime_processes(self, target_runtime: Path) -> None:
        normalized_target = _normalize_path(target_runtime)
        if normalized_target is None:
            return

        for runtime_process in self._iter_runtime_processes():
            executable_path = self._get_process_executable_path(runtime_process)
            if executable_path is None or executable_path == normalized_target:
                if executable_path == normalized_target:
                    logger.info(
                        'Replacing stale desktop runtime: %s -> %s',
                        str(executable_path),
                        str(normalized_target),
                    )
                    self._terminate_process_tree(runtime_process)
                continue

            if self._is_project_runtime_path(executable_path):
                logger.info('Replacing stale desktop runtime: %s -> %s', str(executable_path), str(normalized_target))
                self._terminate_process_tree(runtime_process)

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

        if executable_path.name != _OFFICIAL_RUNTIME_EXE_NAME:
            return False
        if executable_path.parent.name != 'win-unpacked':
            return False
        build_dir = executable_path.parent.parent
        if build_dir.parent != _official_runtime_root(self.runtime_root):
            return False
        return _OFFICIAL_RUNTIME_BUILD_DIR_PATTERN.match(build_dir.name) is not None

    def _terminate_process_tree(self, process) -> None:
        processes = list(process.children(recursive=True)) + [process]
        for child in reversed(processes):
            try:
                child.terminate()
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.Error):
                continue

        try:
            _, alive = psutil.wait_procs(processes, timeout=5)
        except AttributeError:
            alive = []

        for child in alive:
            try:
                child.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.Error):
                continue

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

    async def _wait_until_ready(self) -> None:
        timeout_seconds = float(self.config.get('startup_timeout_seconds') or 30)

        async def _poll() -> None:
            while True:
                health = await self.client.health()
                if health.get('status') == 'ready':
                    return
                await asyncio.sleep(0.1)

        try:
            await asyncio.wait_for(_poll(), timeout=timeout_seconds)
        except asyncio.TimeoutError as exc:
            await self.stop()
            raise DesktopAutomationError(RUNTIME_UNAVAILABLE, 'Desktop runtime failed to become ready in time') from exc

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
        return await asyncio.create_subprocess_exec(
            str(runtime_executable),
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
