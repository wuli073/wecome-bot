from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from langbot.pkg.desktop_automation.errors import (
    RPA_RUNTIME_NOT_AVAILABLE,
    RUNTIME_CONTRACT_INVALID,
    RUNTIME_CONTRACT_UNAVAILABLE,
    RUNTIME_HANDSHAKE_TOKEN_INVALID,
    RUNTIME_OWNERSHIP_CONFLICT,
    RUNTIME_PROTOCOL_MISMATCH,
    RUNTIME_START_FAILED,
    RUNTIME_UNAVAILABLE,
    DesktopAutomationError,
)
from langbot.pkg.desktop_automation.runtime_process import (
    DesktopRuntimeProcessManager,
    apply_local_desktop_automation_defaults,
    list_runtime_candidates,
    resolve_latest_runtime_executable,
    resolve_runtime_executable_path,
)
from langbot.pkg.desktop_automation.runtime_contract import load_runtime_contract


pytestmark = pytest.mark.asyncio


class _FakeStdout:
    def __init__(self, lines: list[str]) -> None:
        self._lines = [line.encode('utf-8') for line in lines]

    async def readline(self) -> bytes:
        await asyncio.sleep(0)
        if self._lines:
            return self._lines.pop(0)
        return b''


class _FakeStderr(_FakeStdout):
    pass


class _FakeProcess:
    def __init__(self, stdout_lines: list[str], *, pid: int = 4321) -> None:
        self.stdout = _FakeStdout(stdout_lines)
        self.stderr = _FakeStderr([])
        self.pid = pid
        self.returncode = None
        self.terminated = False
        self.killed = False

    def terminate(self) -> None:
        self.terminated = True
        self.returncode = 0

    def kill(self) -> None:
        self.killed = True
        self.returncode = 1

    async def wait(self) -> int:
        await asyncio.sleep(0)
        self.returncode = 0
        return 0


class _FakePsutilProcess:
    def __init__(
        self,
        pid: int,
        exe: str | None,
        *,
        children: list[_FakePsutilProcess] | None = None,
        running: bool = True,
        create_time: float = 10.0,
        events: list[tuple[str, int]] | None = None,
    ) -> None:
        self.pid = pid
        self._exe = exe
        self._children = children or []
        self.terminated = False
        self.killed = False
        self.waited_timeout = None
        self.running = running
        self._create_time = create_time
        self._events = events

    def name(self) -> str:
        return 'LangBot Desktop RPA Runtime.exe'

    def exe(self) -> str | None:
        if self._exe is None:
            raise RuntimeError('missing exe')
        return self._exe

    def create_time(self) -> float:
        return self._create_time

    def children(self, recursive: bool = False):
        if not recursive:
            return list(self._children)
        descendants = list(self._children)
        for child in self._children:
            descendants.extend(child.children(recursive=True))
        return descendants

    def terminate(self) -> None:
        self.terminated = True
        if self._events is not None:
            self._events.append(('terminate', self.pid))

    def kill(self) -> None:
        self.killed = True
        if self._events is not None:
            self._events.append(('kill', self.pid))

    def wait(self, timeout: float | None = None) -> int:
        self.waited_timeout = timeout
        return 0

    def is_running(self) -> bool:
        return self.running and not self.terminated and not self.killed


class _FakePsutilModule:
    class Error(Exception):
        pass

    class NoSuchProcess(Error):
        pass

    class AccessDenied(Error):
        pass

    class TimeoutExpired(Error):
        pass

    def __init__(
        self,
        processes: list[_FakePsutilProcess],
        *,
        iter_processes: list[_FakePsutilProcess] | None = None,
    ) -> None:
        self._processes = processes
        self._iter_processes = iter_processes if iter_processes is not None else processes
        self.wait_procs_calls: list[tuple[list[int], float | None]] = []
        self.Process = self._get_process

    def _get_process(self, pid: int):
        for process in self._processes:
            if process.pid == pid:
                return process
        raise self.NoSuchProcess(pid)

    def process_iter(self, attrs=None):
        return iter(self._iter_processes)

    def wait_procs(self, procs, timeout=None):
        proc_list = list(procs)
        self.wait_procs_calls.append(([proc.pid for proc in proc_list], timeout))
        return ([], [])


def _official_runtime_executable(root: Path, build_dir: str) -> Path:
    return (
        root
        / 'apps'
        / 'desktop-rpa-runtime'
        / 'dist-phase2-official'
        / build_dir
        / 'win-unpacked'
        / 'LangBot Desktop RPA Runtime.exe'
    )


def _write_official_runtime(root: Path, build_dir: str) -> Path:
    _write_runtime_contract(root)
    executable = _official_runtime_executable(root, build_dir)
    executable.parent.mkdir(parents=True, exist_ok=True)
    executable.write_text(build_dir, encoding='utf-8')
    return executable


def _write_deterministic_runtime(root: Path) -> Path:
    _write_runtime_contract(root)
    executable = (
        root
        / 'apps'
        / 'desktop-rpa-runtime'
        / 'dist-phase2-official'
        / 'win-dir'
        / 'win-unpacked'
        / 'LangBot Desktop RPA Runtime.exe'
    )
    executable.parent.mkdir(parents=True, exist_ok=True)
    executable.write_text('win-dir', encoding='utf-8')
    return executable


def _write_runtime_contract(
    root: Path,
    *,
    protocol_version: str = '2',
    runtime_version: str = '0.1.2',
    release_available: bool = True,
) -> Path:
    descriptor = root / 'distribution' / 'runtime' / 'desktop-runtime-release.json'
    descriptor.parent.mkdir(parents=True, exist_ok=True)
    descriptor.write_text(
        json.dumps(
            {
                'protocol_version': protocol_version,
                'runtime_version': runtime_version,
                'tag': f'desktop-runtime-v{runtime_version}',
                'release_available': release_available,
            }
        ),
        encoding='utf-8',
    )
    return descriptor


def test_defaults_remove_retired_runtime_version_configuration():
    config = apply_local_desktop_automation_defaults(
        {
            'enabled': True,
            'runtime_executable': 'C:/runtime/runtime.exe',
        }
    )

    assert config['enabled'] is True
    assert config['runtime_executable'] == 'C:/runtime/runtime.exe'
    assert 'expected_protocol_version' not in config
    assert 'runtime_version' not in config


def test_runtime_contract_reads_the_local_descriptor():
    with TemporaryDirectory() as temp_dir:
        tmp_path = Path(temp_dir)
        _write_runtime_contract(tmp_path, protocol_version='2', runtime_version='0.1.2')

        contract = load_runtime_contract(tmp_path)

    assert contract.protocol_version == '2'
    assert contract.runtime_version == '0.1.2'
    assert contract.tag == 'desktop-runtime-v0.1.2'


@pytest.mark.parametrize(
    ('descriptor_content', 'error_code'),
    [
        (None, RUNTIME_CONTRACT_UNAVAILABLE),
        ('not-json', RUNTIME_CONTRACT_INVALID),
        ('{"release_available": false}', RUNTIME_CONTRACT_UNAVAILABLE),
        ('{"release_available": true, "runtime_version": "0.1.2", "tag": "tag"}', RUNTIME_CONTRACT_INVALID),
    ],
)
def test_runtime_contract_reports_missing_or_invalid_descriptors(descriptor_content, error_code):
    with TemporaryDirectory() as temp_dir:
        tmp_path = Path(temp_dir)
        if descriptor_content is not None:
            descriptor = tmp_path / 'distribution' / 'runtime' / 'desktop-runtime-release.json'
            descriptor.parent.mkdir(parents=True, exist_ok=True)
            descriptor.write_text(descriptor_content, encoding='utf-8')

        with pytest.raises(DesktopAutomationError) as exc_info:
            load_runtime_contract(tmp_path)

    assert exc_info.value.code == error_code


def test_runtime_executable_resolution_ignores_configured_old_path_and_selects_latest_official_runtime():
    with TemporaryDirectory(dir=r'C:\Users\33031\Desktop\bot\.tmp-pytest') as temp_dir:
        tmp_path = Path(temp_dir)
        configured_old = _write_official_runtime(tmp_path, '2026-06-29T17-02-42-920Z')
        expected_latest = _write_official_runtime(tmp_path, '2026-06-30T04-24-26-368Z')

        resolved = resolve_runtime_executable_path(configured=str(configured_old), repo_root=tmp_path)

        assert resolved == expected_latest
        assert resolved != configured_old


def test_runtime_executable_resolution_returns_none_when_no_candidate_exists():
    with TemporaryDirectory(dir=r'C:\Users\33031\Desktop\bot\.tmp-pytest') as temp_dir:
        tmp_path = Path(temp_dir)
        resolved = resolve_runtime_executable_path(configured='', repo_root=tmp_path)

        assert resolved is None


def test_runtime_executable_resolution_prefers_latest_official_packaged_runtime():
    with TemporaryDirectory(dir=r'C:\Users\33031\Desktop\bot\.tmp-pytest') as temp_dir:
        tmp_path = Path(temp_dir)
        oldest_executable = _write_official_runtime(tmp_path, '2026-06-29T17-02-42-920Z')
        middle_executable = _write_official_runtime(tmp_path, '2026-06-29T18-44-26-872Z')
        newer_executable = _write_official_runtime(tmp_path, '2026-06-30T04-24-26-368Z')

        resolved = resolve_runtime_executable_path(configured='', repo_root=tmp_path)

        assert resolved == newer_executable
        assert resolved != middle_executable
        assert resolved != oldest_executable


def test_runtime_executable_resolution_prefers_deterministic_source_runtime_over_timestamped_builds():
    with TemporaryDirectory(dir=r'C:\Users\33031\Desktop\bot\.tmp-pytest') as temp_dir:
        tmp_path = Path(temp_dir)
        deterministic = _write_deterministic_runtime(tmp_path)
        _write_official_runtime(tmp_path, '2026-06-30T04-24-26-368Z')

        resolved = resolve_runtime_executable_path(configured='', repo_root=tmp_path)

        assert resolved == deterministic


def test_runtime_executable_resolution_accepts_configured_custom_runtime_outside_official_output_root():
    with TemporaryDirectory(dir=r'C:\Users\33031\Desktop\bot\.tmp-pytest') as temp_dir:
        tmp_path = Path(temp_dir)
        custom_runtime = tmp_path / 'custom-runtime' / 'LangBot Desktop RPA Runtime.exe'
        custom_runtime.parent.mkdir(parents=True, exist_ok=True)
        custom_runtime.write_text('custom', encoding='utf-8')
        _write_official_runtime(tmp_path, '2026-06-30T04-24-26-368Z')

        resolved = resolve_runtime_executable_path(configured=str(custom_runtime), repo_root=tmp_path)

        assert resolved == custom_runtime


def test_list_runtime_candidates_sorts_by_parsed_utc_timestamp_descending():
    with TemporaryDirectory(dir=r'C:\Users\33031\Desktop\bot\.tmp-pytest') as temp_dir:
        tmp_path = Path(temp_dir)
        first = _write_official_runtime(tmp_path, '2026-06-29T17-02-42-920Z')
        second = _write_official_runtime(tmp_path, '2026-06-30T04-24-26-368Z')
        third = _write_official_runtime(tmp_path, '2026-06-29T18-44-26-872Z')

        candidates = list_runtime_candidates(repo_root=tmp_path)

        assert [candidate.executable_path for candidate in candidates] == [second, third, first]
        assert [candidate.executable_path.parent.parent.name for candidate in candidates] == [
            '2026-06-30T04-24-26-368Z',
            '2026-06-29T18-44-26-872Z',
            '2026-06-29T17-02-42-920Z',
        ]


def test_resolve_latest_runtime_executable_falls_back_when_latest_executable_missing():
    with TemporaryDirectory(dir=r'C:\Users\33031\Desktop\bot\.tmp-pytest') as temp_dir:
        tmp_path = Path(temp_dir)
        expected = _write_official_runtime(tmp_path, '2026-06-29T18-44-26-872Z')
        newest_build_dir = (
            tmp_path / 'apps' / 'desktop-rpa-runtime' / 'dist-phase2-official' / '2026-06-30T04-24-26-368Z'
        )
        (newest_build_dir / 'win-unpacked').mkdir(parents=True, exist_ok=True)
        _write_official_runtime(tmp_path, '2026-06-29T17-02-42-920Z')

        resolved = resolve_latest_runtime_executable(repo_root=tmp_path)

        assert resolved == expected


def test_list_runtime_candidates_ignores_invalid_directory_names():
    with TemporaryDirectory(dir=r'C:\Users\33031\Desktop\bot\.tmp-pytest') as temp_dir:
        tmp_path = Path(temp_dir)
        official_root = tmp_path / 'apps' / 'desktop-rpa-runtime' / 'dist-phase2-official'
        invalid_dir = official_root / '2026-06-30'
        (invalid_dir / 'win-unpacked').mkdir(parents=True, exist_ok=True)
        (invalid_dir / 'win-unpacked' / 'LangBot Desktop RPA Runtime.exe').write_text('invalid', encoding='utf-8')
        expected = _write_official_runtime(tmp_path, '2026-06-30T04-24-26-368Z')

        candidates = list_runtime_candidates(repo_root=tmp_path)

        assert [candidate.executable_path for candidate in candidates] == [expected]


def test_resolve_runtime_executable_path_does_not_add_fixed_old_path_when_configured_is_invalid():
    with TemporaryDirectory(dir=r'C:\Users\33031\Desktop\bot\.tmp-pytest') as temp_dir:
        tmp_path = Path(temp_dir)
        expected = _write_official_runtime(tmp_path, '2026-06-30T04-24-26-368Z')
        invalid_configured = (
            tmp_path
            / 'apps'
            / 'desktop-rpa-runtime'
            / 'dist-phase2-official'
            / '2026-06-29T17-02-42-920Z'
            / 'win-unpacked'
            / 'LangBot Desktop RPA Runtime.exe'
        )

        resolved = resolve_runtime_executable_path(configured=str(invalid_configured), repo_root=tmp_path)

        assert resolved == expected


def test_resolve_latest_runtime_executable_does_not_reuse_stale_resolution_cache():
    with TemporaryDirectory(dir=r'C:\Users\33031\Desktop\bot\.tmp-pytest') as temp_dir:
        tmp_path = Path(temp_dir)
        first = _write_official_runtime(tmp_path, '2026-06-29T17-02-42-920Z')

        assert resolve_latest_runtime_executable(repo_root=tmp_path) == first

        second = _write_official_runtime(tmp_path, '2026-06-30T04-24-26-368Z')

        assert resolve_latest_runtime_executable(repo_root=tmp_path) == second


def test_runtime_executable_resolution_ignores_official_directories_without_win_unpacked_executable():
    with TemporaryDirectory(dir=r'C:\Users\33031\Desktop\bot\.tmp-pytest') as temp_dir:
        tmp_path = Path(temp_dir)
        missing = (
            tmp_path
            / 'apps'
            / 'desktop-rpa-runtime'
            / 'dist-phase2-official'
            / '2026-06-30T04-24-26-368Z'
            / 'win-unpacked'
        )
        missing.mkdir(parents=True, exist_ok=True)
        expected = _write_official_runtime(tmp_path, '2026-06-30T04-18-12-228Z')

        resolved = resolve_runtime_executable_path(configured='', repo_root=tmp_path)

        assert resolved == expected


def test_runtime_executable_resolution_skips_legacy_official_root_win_unpacked_path():
    with TemporaryDirectory(dir=r'C:\Users\33031\Desktop\bot\.tmp-pytest') as temp_dir:
        tmp_path = Path(temp_dir)
        legacy = (
            tmp_path
            / 'apps'
            / 'desktop-rpa-runtime'
            / 'dist-phase2-official'
            / 'win-unpacked'
            / 'LangBot Desktop RPA Runtime.exe'
        )
        legacy.parent.mkdir(parents=True, exist_ok=True)
        legacy.write_text('legacy-root', encoding='utf-8')
        expected = _write_official_runtime(tmp_path, '2026-06-30T04-24-26-368Z')

        resolved = resolve_runtime_executable_path(configured='', repo_root=tmp_path)

        assert resolved == expected
        assert resolved != legacy


def test_packaged_runtime_resolution_uses_only_fixed_packaged_path(monkeypatch):
    with TemporaryDirectory(dir=r'C:\Users\33031\Desktop\bot\.tmp-pytest') as temp_dir:
        tmp_path = Path(temp_dir)
        packaged_runtime = tmp_path / 'runtime' / 'desktop-rpa' / 'LangBot Desktop RPA Runtime.exe'
        packaged_runtime.parent.mkdir(parents=True, exist_ok=True)
        packaged_runtime.write_text('packaged', encoding='utf-8')
        _write_official_runtime(tmp_path, '2026-06-30T04-24-26-368Z')
        monkeypatch.setenv('CHATBOT_PACKAGED', '1')
        monkeypatch.setenv('CHATBOT_INSTALL_ROOT', str(tmp_path))

        resolved = resolve_runtime_executable_path(configured='', repo_root=tmp_path)
        candidates = list_runtime_candidates(repo_root=tmp_path)

        assert resolved == packaged_runtime
        assert [candidate.executable_path for candidate in candidates] == [packaged_runtime]


async def test_runtime_process_manager_starts_and_returns_runtime_info(monkeypatch):
    with TemporaryDirectory(dir=r'C:\Users\33031\Desktop\bot\.tmp-pytest') as temp_dir:
        tmp_path = Path(temp_dir)
        runtime_executable = _write_official_runtime(tmp_path, '2026-06-30T04-24-26-368Z')
        monkeypatch.delenv('LANGBOT_BROADCAST_SEND_ENABLED', raising=False)
        monkeypatch.delenv('LANGBOT_BROADCAST_SEND_ALLOW_CONNECTORS', raising=False)
        monkeypatch.delenv('LANGBOT_RPA_FORCE_DISABLE_SEND', raising=False)
        monkeypatch.delenv('LANGBOT_RPA_ALLOW_AUTO_SEND', raising=False)

        async def spawn_runtime(path: Path, *, env: dict[str, str], cwd: Path):
            assert path == runtime_executable
            assert f'LANGBOT_RPA_{"MANAGED"}' not in env
            assert f'LANGBOT_RPA_{"TOKEN"}' not in env
            assert env['LANGBOT_BROADCAST_SEND_ENABLED'] == '1'
            assert env['LANGBOT_BROADCAST_SEND_ALLOW_CONNECTORS'] == '*'
            assert env['LANGBOT_RPA_FORCE_DISABLE_SEND'] == '0'
            assert env['LANGBOT_RPA_ALLOW_AUTO_SEND'] == '1'
            assert cwd == runtime_executable.parent
            return _FakeProcess(['{"pid": 4321, "port": 55123, "token": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "protocolVersion": "2", "runtimeVersion": "0.1.2"}\n'])

        fake_client = SimpleNamespace(
            health=AsyncMock(return_value={'status': 'ready'}), capabilities=AsyncMock(return_value={})
        )

        manager = DesktopRuntimeProcessManager(
            config={'enabled': True, 'runtime_executable': str(runtime_executable)},
            spawn_runtime=spawn_runtime,
            client_factory=lambda runtime_info: fake_client,
            runtime_root=tmp_path,
        )

        runtime_info = await manager.ensure_started()

        assert runtime_info['host'] == '127.0.0.1'
        assert runtime_info['port'] == 55123
        assert runtime_info['protocolVersion'] == '2'
        assert runtime_info['runtimeVersion'] == '0.1.2'
        assert runtime_info['token']
        assert isinstance(manager.client, object)


async def test_legacy_runtime_versions_do_not_override_descriptor_handshake(monkeypatch):
    with TemporaryDirectory() as temp_dir:
        tmp_path = Path(temp_dir)
        runtime_executable = _write_official_runtime(tmp_path, '2026-06-30T04-24-26-368Z')
        monkeypatch.setattr(
            'langbot.pkg.desktop_automation.runtime_process.psutil.Process',
            lambda _pid: _FakePsutilProcess(4321, str(runtime_executable), create_time=12.5),
        )
        monkeypatch.setattr('langbot.pkg.desktop_automation.runtime_process.psutil.process_iter', lambda attrs=None: iter(()))

        async def spawn_runtime(path: Path, *, env: dict[str, str], cwd: Path):
            assert path == runtime_executable
            return _FakeProcess(
                ['{"pid": 4321, "port": 55123, "token": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "protocolVersion": "2", "runtimeVersion": "0.1.2"}\n']
            )

        fake_client = SimpleNamespace(
            health=AsyncMock(return_value={'status': 'ready'}),
            capabilities=AsyncMock(return_value={'inputAvailable': True, 'sendEnabled': True}),
        )
        manager = DesktopRuntimeProcessManager(
            config={
                'enabled': True,
                'runtime_executable': str(runtime_executable),
                'expected_protocol_version': '1',
                'runtime_version': '0.1.1',
            },
            spawn_runtime=spawn_runtime,
            client_factory=lambda _runtime_info: fake_client,
            runtime_root=tmp_path,
        )

        status = await manager.get_status()

    assert 'expected_protocol_version' not in manager.config
    assert 'runtime_version' not in manager.config
    assert status['status'] == 'ready', status
    assert status['runtime_reachable'] is True
    assert status['send_enabled'] is True
    assert 'token' not in status


async def test_runtime_process_manager_propagates_enabled_broadcast_send_to_runtime(monkeypatch):
    with TemporaryDirectory(dir=r'C:\Users\33031\Desktop\bot\.tmp-pytest') as temp_dir:
        tmp_path = Path(temp_dir)
        runtime_executable = _write_official_runtime(tmp_path, '2026-06-30T04-24-26-368Z')
        monkeypatch.setenv('LANGBOT_BROADCAST_SEND_ENABLED', '1')
        monkeypatch.setenv('LANGBOT_BROADCAST_SEND_ALLOW_CONNECTORS', 'wxwork-local')
        monkeypatch.setenv('LANGBOT_RPA_FORCE_DISABLE_SEND', '1')
        monkeypatch.setenv('LANGBOT_RPA_ALLOW_AUTO_SEND', '0')

        async def spawn_runtime(path: Path, *, env: dict[str, str], cwd: Path):
            assert path == runtime_executable
            assert env['LANGBOT_BROADCAST_SEND_ENABLED'] == '1'
            assert env['LANGBOT_BROADCAST_SEND_ALLOW_CONNECTORS'] == '*'
            assert env['LANGBOT_RPA_FORCE_DISABLE_SEND'] == '0'
            assert env['LANGBOT_RPA_ALLOW_AUTO_SEND'] == '1'
            assert cwd == runtime_executable.parent
            return _FakeProcess(['{"pid": 4321, "port": 55123, "token": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "protocolVersion": "2", "runtimeVersion": "0.1.2"}\n'])

        fake_client = SimpleNamespace(
            health=AsyncMock(return_value={'status': 'ready'}),
            capabilities=AsyncMock(return_value={}),
        )

        manager = DesktopRuntimeProcessManager(
            config={'enabled': True, 'runtime_executable': str(runtime_executable)},
            spawn_runtime=spawn_runtime,
            client_factory=lambda runtime_info: fake_client,
            runtime_root=tmp_path,
        )

        await manager.ensure_started()


async def test_runtime_process_manager_reports_ownership_conflict_for_other_official_runtime(monkeypatch):
    with TemporaryDirectory(dir=r'C:\Users\33031\Desktop\bot\.tmp-pytest') as temp_dir:
        tmp_path = Path(temp_dir)
        runtime_executable = _write_official_runtime(tmp_path, '2026-06-30T04-24-26-368Z')
        conflicting_process = _FakePsutilProcess(6101, str(runtime_executable), create_time=88.5)
        fake_psutil = _FakePsutilModule([conflicting_process])
        spawn_calls: list[Path] = []

        async def spawn_runtime(path: Path, *, env: dict[str, str], cwd: Path):
            spawn_calls.append(path)
            return _FakeProcess(['{"pid": 4321, "port": 55123, "token": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "protocolVersion": "2", "runtimeVersion": "0.1.2"}\n'])

        monkeypatch.setattr('langbot.pkg.desktop_automation.runtime_process.psutil', fake_psutil)
        manager = DesktopRuntimeProcessManager(
            config={'enabled': True, 'runtime_executable': str(runtime_executable)},
            spawn_runtime=spawn_runtime,
            runtime_root=tmp_path,
        )

        with pytest.raises(DesktopAutomationError) as exc_info:
            await manager.ensure_started()

        assert exc_info.value.code == RUNTIME_OWNERSHIP_CONFLICT
        assert spawn_calls == []
        assert exc_info.value.details == {
            'pid': 6101,
            'executable_path': str(runtime_executable),
            'build_timestamp': '2026-06-30T04-24-26-368Z',
        }


async def test_runtime_process_manager_reuses_owned_runtime_before_conflict_scan(monkeypatch):
    with TemporaryDirectory(dir=r'C:\Users\33031\Desktop\bot\.tmp-pytest') as temp_dir:
        tmp_path = Path(temp_dir)
        target = _write_official_runtime(tmp_path, '2026-06-30T04-24-26-368Z')
        owned_process = _FakePsutilProcess(6001, str(target), create_time=10.0)
        conflicting_process = _FakePsutilProcess(6002, str(target), create_time=20.0)
        fake_psutil = _FakePsutilModule([owned_process, conflicting_process])

        class _FakeClient:
            async def health(self):
                return {'status': 'ready'}

            async def capabilities(self):
                return {}

        monkeypatch.setattr('langbot.pkg.desktop_automation.runtime_process.psutil', fake_psutil)
        manager = DesktopRuntimeProcessManager(config={'enabled': True}, runtime_root=tmp_path)
        manager.process = owned_process
        manager.client = _FakeClient()
        manager.runtime_info = {
            'pid': 6001,
            'processCreateTime': 10.0,
            'host': '127.0.0.1',
            'port': 55123,
            'protocolVersion': '2',
            'runtimeVersion': '0.1.2',
            'token': 'memory-only-token',
            'executablePath': str(target),
        }

        runtime_info = await manager.ensure_started()

        assert runtime_info['pid'] == 6001
        assert runtime_info['executablePath'] == str(target)


async def test_runtime_process_manager_reports_not_available_when_runtime_missing():
    with TemporaryDirectory(dir=r'C:\Users\33031\Desktop\bot\.tmp-pytest') as temp_dir:
        tmp_path = Path(temp_dir)
        manager = DesktopRuntimeProcessManager(config={'enabled': True}, runtime_root=tmp_path)

        status = await manager.get_status()

        assert status['status'] == 'not_available'
        assert status['errorCode'] == RPA_RUNTIME_NOT_AVAILABLE
        assert status['runtime_startable'] is False


async def test_runtime_process_manager_stop_terminates_child(monkeypatch):
    with TemporaryDirectory(dir=r'C:\Users\33031\Desktop\bot\.tmp-pytest') as temp_dir:
        tmp_path = Path(temp_dir)
        runtime_executable = _write_official_runtime(tmp_path, '2026-06-30T04-24-26-368Z')
        process = _FakeProcess(['{"pid": 4321, "port": 55123, "token": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "protocolVersion": "2", "runtimeVersion": "0.1.2"}\n'])
        owned_process = _FakePsutilProcess(4321, str(runtime_executable), create_time=10.0)

        async def spawn_runtime(path: Path, *, env: dict[str, str], cwd: Path):
            return process

        fake_client = SimpleNamespace(
            health=AsyncMock(return_value={'status': 'ready'}), capabilities=AsyncMock(return_value={})
        )
        monkeypatch.setattr('langbot.pkg.desktop_automation.runtime_process.psutil.Process', lambda pid: owned_process)
        monkeypatch.setattr('langbot.pkg.desktop_automation.runtime_process.psutil.process_iter', lambda attrs=None: iter(()))

        manager = DesktopRuntimeProcessManager(
            config={'enabled': True, 'runtime_executable': str(runtime_executable)},
            spawn_runtime=spawn_runtime,
            client_factory=lambda runtime_info: fake_client,
            runtime_root=tmp_path,
        )

        await manager.ensure_started()
        await manager.stop()

        assert owned_process.terminated is True


async def test_runtime_restart_replaces_the_in_memory_handshake_token(monkeypatch):
    with TemporaryDirectory(dir=r'C:\Users\33031\Desktop\bot\.tmp-pytest') as temp_dir:
        tmp_path = Path(temp_dir)
        runtime_executable = _write_official_runtime(tmp_path, '2026-06-30T04-24-26-368Z')
        owned_process = _FakePsutilProcess(4321, str(runtime_executable), create_time=10.0)
        handshake_tokens = ['a' * 64, 'b' * 64]

        async def spawn_runtime(path: Path, *, env: dict[str, str], cwd: Path):
            token = handshake_tokens.pop(0)
            return _FakeProcess([
                json.dumps({
                    'pid': 4321,
                    'port': 55123,
                    'token': token,
                    'protocolVersion': '2',
                    'runtimeVersion': '0.1.2',
                }) + '\n'
            ])

        fake_client = SimpleNamespace(
            health=AsyncMock(return_value={'status': 'ready'}), capabilities=AsyncMock(return_value={})
        )
        monkeypatch.setattr('langbot.pkg.desktop_automation.runtime_process.psutil.Process', lambda pid: owned_process)
        monkeypatch.setattr('langbot.pkg.desktop_automation.runtime_process.psutil.process_iter', lambda attrs=None: iter(()))
        manager = DesktopRuntimeProcessManager(
            config={'enabled': True, 'runtime_executable': str(runtime_executable)},
            spawn_runtime=spawn_runtime,
            client_factory=lambda runtime_info: fake_client,
            runtime_root=tmp_path,
        )

        first = await manager.ensure_started()
        await manager.stop()
        second = await manager.ensure_started()

        assert first['token'] == 'a' * 64
        assert second['token'] == 'b' * 64
        assert first['token'] != second['token']


async def test_runtime_process_manager_allows_only_blank_stdout_before_handshake():
    manager = DesktopRuntimeProcessManager(config={'enabled': True}, runtime_root=Path('C:/missing'))
    process = _FakeProcess(
        ['\r\n', '   \n', '{"pid": 4321, "port": 55123, "token": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "protocolVersion": "2", "runtimeVersion": "0.1.2"}\n']
    )

    handshake = await manager._read_handshake(process)

    assert handshake['port'] == 55123


async def test_runtime_process_manager_rejects_non_empty_stdout_before_handshake():
    manager = DesktopRuntimeProcessManager(config={'enabled': True}, runtime_root=Path('C:/missing'))
    process = _FakeProcess(
        ['not-json\n', '{"pid": 4321, "port": 55123, "token": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "protocolVersion": "2", "runtimeVersion": "0.1.2"}\n']
    )

    with pytest.raises(DesktopAutomationError) as exc_info:
        await manager._read_handshake(process)

    assert exc_info.value.code == RUNTIME_START_FAILED


async def test_runtime_process_manager_rejects_missing_stdout_before_handshake():
    manager = DesktopRuntimeProcessManager(config={'enabled': True}, runtime_root=Path('C:/missing'))
    process = SimpleNamespace(stdout=None)

    with pytest.raises(DesktopAutomationError) as exc_info:
        await manager._read_handshake(process)

    assert exc_info.value.code == RUNTIME_START_FAILED
    assert str(exc_info.value) == 'Runtime stdout is not readable'


async def test_runtime_process_manager_rejects_handshake_eof():
    manager = DesktopRuntimeProcessManager(config={'enabled': True}, runtime_root=Path('C:/missing'))
    process = _FakeProcess([])

    with pytest.raises(DesktopAutomationError) as exc_info:
        await manager._read_handshake(process)

    assert exc_info.value.code == RUNTIME_START_FAILED
    assert str(exc_info.value) == 'Desktop runtime exited before handshake'


async def test_runtime_process_manager_rejects_handshake_shape_mismatch():
    manager = DesktopRuntimeProcessManager(config={'enabled': True}, runtime_root=Path('C:/missing'))
    process = _FakeProcess(['{"pid": 4321, "port": 55123, "protocolVersion": "2"}\n'])

    with pytest.raises(DesktopAutomationError) as exc_info:
        await manager._read_handshake(process)

    assert exc_info.value.code == RUNTIME_HANDSHAKE_TOKEN_INVALID
    assert str(exc_info.value) == 'Desktop runtime handshake token is invalid'


@pytest.mark.parametrize('token', ['', 'invalid token', 123])
async def test_runtime_process_manager_rejects_empty_or_malformed_handshake_token(token):
    manager = DesktopRuntimeProcessManager(config={'enabled': True}, runtime_root=Path('C:/missing'))
    process = _FakeProcess([
        json.dumps({
            'pid': 4321,
            'port': 55123,
            'token': token,
            'protocolVersion': '2',
            'runtimeVersion': '0.1.2',
        }) + '\n'
    ])

    with pytest.raises(DesktopAutomationError) as exc_info:
        await manager._read_handshake(process)

    assert exc_info.value.code == RUNTIME_HANDSHAKE_TOKEN_INVALID


async def test_runtime_process_manager_rejects_invalid_handshake_port():
    manager = DesktopRuntimeProcessManager(config={'enabled': True}, runtime_root=Path('C:/missing'))
    process = _FakeProcess([
        '{"pid": 4321, "port": 0, "token": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "protocolVersion": "2", "runtimeVersion": "0.1.2"}\n'
    ])

    with pytest.raises(DesktopAutomationError) as exc_info:
        await manager._read_handshake(process)

    assert exc_info.value.code == RUNTIME_START_FAILED


async def test_runtime_token_is_never_written_to_auth_token_file():
    with TemporaryDirectory(dir=r'C:\Users\33031\Desktop\bot\.tmp-pytest') as temp_dir:
        tmp_path = Path(temp_dir)
        runtime_executable = _write_official_runtime(tmp_path, '2026-06-30T04-24-26-368Z')
        token_file = tmp_path / 'auth-token.txt'

        async def spawn_runtime(path: Path, *, env: dict[str, str], cwd: Path):
            assert f'LANGBOT_RPA_{"TOKEN"}' not in env
            assert not token_file.exists()
            return _FakeProcess(['{"pid": 4321, "port": 55123, "token": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "protocolVersion": "2", "runtimeVersion": "0.1.2"}\n'])

        fake_client = SimpleNamespace(
            health=AsyncMock(return_value={'status': 'ready'}), capabilities=AsyncMock(return_value={})
        )
        manager = DesktopRuntimeProcessManager(
            config={'enabled': True, 'runtime_executable': str(runtime_executable)},
            spawn_runtime=spawn_runtime,
            client_factory=lambda runtime_info: fake_client,
            runtime_root=tmp_path,
        )

        await manager.ensure_started()

        assert not token_file.exists()
        assert not (tmp_path / 'data' / 'desktop_automation' / 'runtime_state.json').exists()


async def test_runtime_process_manager_reuses_matching_project_runtime_process(monkeypatch, caplog):
    with TemporaryDirectory(dir=r'C:\Users\33031\Desktop\bot\.tmp-pytest') as temp_dir:
        tmp_path = Path(temp_dir)
        target = _write_official_runtime(tmp_path, '2026-06-30T04-24-26-368Z')
        process = _FakePsutilProcess(6001, str(target))
        fake_psutil = _FakePsutilModule([process])
        health_calls = 0

        class _FakeClient:
            async def health(self):
                nonlocal health_calls
                health_calls += 1
                return {'status': 'ready'}

            async def capabilities(self):
                return {}

        monkeypatch.setattr('langbot.pkg.desktop_automation.runtime_process.psutil', fake_psutil)
        caplog.set_level(logging.INFO)
        manager = DesktopRuntimeProcessManager(config={'enabled': True}, runtime_root=tmp_path)
        manager.process = process
        manager.client = _FakeClient()
        manager.runtime_info = {
            'pid': 6001,
            'host': '127.0.0.1',
            'port': 55123,
            'protocolVersion': '2',
            'runtimeVersion': '0.1.2',
            'token': 'memory-only-token',
            'executablePath': str(target),
        }

        runtime_info = await manager.ensure_started()

        assert runtime_info['pid'] == 6001
        assert runtime_info['executablePath'] == str(target)
        assert health_calls == 1
        assert 'Reusing desktop runtime' in caplog.text
        assert 'memory-only-token' not in caplog.text


def test_runtime_process_manager_replaces_stale_project_runtime_process(monkeypatch, caplog):
    with TemporaryDirectory(dir=r'C:\Users\33031\Desktop\bot\.tmp-pytest') as temp_dir:
        tmp_path = Path(temp_dir)
        stale = _write_official_runtime(tmp_path, '2026-06-29T17-02-42-920Z')
        target = _write_official_runtime(tmp_path, '2026-06-30T04-24-26-368Z')
        stale_child = _FakePsutilProcess(7002, str(stale.parent / 'child-helper.exe'))
        stale_proc = _FakePsutilProcess(7001, str(stale), children=[stale_child])
        foreign_proc = _FakePsutilProcess(7003, 'C:/Program Files/Some App/LangBot Desktop RPA Runtime.exe')
        fake_psutil = _FakePsutilModule([stale_proc, foreign_proc])

        monkeypatch.setattr('langbot.pkg.desktop_automation.runtime_process.psutil', fake_psutil)
        caplog.set_level(logging.INFO)
        manager = DesktopRuntimeProcessManager(config={'enabled': True}, runtime_root=tmp_path)

        manager._replace_stale_runtime_processes(target)

        assert stale_proc.terminated is False
        assert stale_child.terminated is False
        assert foreign_proc.terminated is False
        assert 'Skipping global stale desktop runtime cleanup for ownership isolation' in caplog.text
        assert str(target) in caplog.text


def test_runtime_process_manager_does_not_terminate_non_project_runtime_process(monkeypatch):
    with TemporaryDirectory(dir=r'C:\Users\33031\Desktop\bot\.tmp-pytest') as temp_dir:
        tmp_path = Path(temp_dir)
        target = _write_official_runtime(tmp_path, '2026-06-30T04-24-26-368Z')
        foreign = _FakePsutilProcess(
            8001,
            'D:/OtherProject/dist-phase2-official/2026-06-29T17-02-42-920Z/win-unpacked/LangBot Desktop RPA Runtime.exe',
        )
        fake_psutil = _FakePsutilModule([foreign])

        monkeypatch.setattr('langbot.pkg.desktop_automation.runtime_process.psutil', fake_psutil)
        manager = DesktopRuntimeProcessManager(config={'enabled': True}, runtime_root=tmp_path)

        manager._replace_stale_runtime_processes(target)

        assert foreign.terminated is False
        assert foreign.killed is False


def test_runtime_process_manager_does_not_terminate_process_without_create_time(monkeypatch):
    with TemporaryDirectory(dir=r'C:\Users\33031\Desktop\bot\.tmp-pytest') as temp_dir:
        tmp_path = Path(temp_dir)
        target = _write_official_runtime(tmp_path, '2026-06-30T04-24-26-368Z')

        class _MissingCreateTimeProcess(_FakePsutilProcess):
            def create_time(self) -> float:
                raise _FakePsutilModule.AccessDenied('missing create time')

        stale = _MissingCreateTimeProcess(8201, str(target))
        fake_psutil = _FakePsutilModule([stale])
        monkeypatch.setattr('langbot.pkg.desktop_automation.runtime_process.psutil', fake_psutil)
        manager = DesktopRuntimeProcessManager(config={'enabled': True}, runtime_root=tmp_path)

        manager._replace_stale_runtime_processes(target)

        assert stale.terminated is False
        assert stale.killed is False


async def test_runtime_process_manager_new_python_process_reports_ownership_conflict_for_existing_target_runtime(
    monkeypatch, caplog
):
    with TemporaryDirectory(dir=r'C:\Users\33031\Desktop\bot\.tmp-pytest') as temp_dir:
        tmp_path = Path(temp_dir)
        target = _write_official_runtime(tmp_path, '2026-06-30T04-24-26-368Z')
        existing = _FakePsutilProcess(8101, str(target))
        fake_psutil = _FakePsutilModule([existing])
        selected_paths: list[Path] = []
        tokens: list[str] = []
        fake_client = SimpleNamespace(
            health=AsyncMock(return_value={'status': 'ready'}),
            capabilities=AsyncMock(return_value={}),
        )

        async def spawn_runtime(path: Path, *, env: dict[str, str], cwd: Path):
            selected_paths.append(path)
            tokens.append('spawned')
            return _FakeProcess(
                ['{"pid": 4321, "port": 55123, "token": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "protocolVersion": "2", "runtimeVersion": "0.1.2"}\n'],
                pid=4321,
            )

        monkeypatch.setattr('langbot.pkg.desktop_automation.runtime_process.psutil', fake_psutil)
        caplog.set_level(logging.INFO)
        manager = DesktopRuntimeProcessManager(
            config={'enabled': True},
            runtime_root=tmp_path,
            spawn_runtime=spawn_runtime,
            client_factory=lambda runtime_info: fake_client,
        )

        with pytest.raises(DesktopAutomationError) as exc_info:
            await manager.ensure_started()

        assert exc_info.value.code == RUNTIME_OWNERSHIP_CONFLICT
        assert selected_paths == []
        assert existing.terminated is False
        assert tokens == []
        assert 'Reusing desktop runtime' not in caplog.text
        assert 'Selected desktop runtime' not in caplog.text


async def test_runtime_process_manager_ensure_started_selects_latest_runtime_and_logs_path(monkeypatch, caplog):
    with TemporaryDirectory(dir=r'C:\Users\33031\Desktop\bot\.tmp-pytest') as temp_dir:
        tmp_path = Path(temp_dir)
        _write_official_runtime(tmp_path, '2026-06-30T04-10-57-293Z')
        target = _write_official_runtime(tmp_path, '2026-06-30T04-24-26-368Z')
        selected_paths: list[Path] = []
        fake_psutil = _FakePsutilModule([])
        fake_client = SimpleNamespace(
            health=AsyncMock(return_value={'status': 'ready'}), capabilities=AsyncMock(return_value={})
        )

        async def spawn_runtime(path: Path, *, env: dict[str, str], cwd: Path):
            selected_paths.append(path)
            assert cwd == target.parent
            return _FakeProcess(['{"pid": 4321, "port": 55123, "token": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "protocolVersion": "2", "runtimeVersion": "0.1.2"}\n'])

        monkeypatch.setattr('langbot.pkg.desktop_automation.runtime_process.psutil', fake_psutil)
        caplog.set_level(logging.INFO)
        manager = DesktopRuntimeProcessManager(
            config={'enabled': True},
            runtime_root=tmp_path,
            spawn_runtime=spawn_runtime,
            client_factory=lambda runtime_info: fake_client,
        )

        await manager.ensure_started()

        assert selected_paths == [target]
        assert 'Desktop runtime candidate' in caplog.text
        assert 'parsedTimestamp=2026-06-30T04:24:26.368000+00:00' in caplog.text
        assert 'Selected desktop runtime' in caplog.text
        assert str(target) in caplog.text
        assert 'token' not in caplog.text.lower()


async def test_runtime_process_manager_get_status_bootstraps_runtime_when_startable():
    with TemporaryDirectory(dir=r'C:\Users\33031\Desktop\bot\.tmp-pytest') as temp_dir:
        tmp_path = Path(temp_dir)
        runtime_executable = _write_official_runtime(tmp_path, '2026-06-30T04-24-26-368Z')

        async def spawn_runtime(path: Path, *, env: dict[str, str], cwd: Path):
            assert path == runtime_executable
            assert f'LANGBOT_RPA_{"MANAGED"}' not in env
            assert f'LANGBOT_RPA_{"TOKEN"}' not in env
            assert cwd == runtime_executable.parent
            return _FakeProcess(['{"pid": 4321, "port": 55123, "token": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "protocolVersion": "2", "runtimeVersion": "0.1.2"}\n'])

        fake_client = SimpleNamespace(
            health=AsyncMock(return_value={'status': 'ready'}),
            capabilities=AsyncMock(
                return_value={
                    'windowingAvailable': True,
                    'captureAvailable': True,
                    'inputAvailable': True,
                    'providerHubReady': True,
                    'sendEnabled': True,
                    'allowedConnectorCount': 1,
                    'sendErrorCode': None,
                }
            ),
        )

        manager = DesktopRuntimeProcessManager(
            config={'enabled': True, 'runtime_executable': str(runtime_executable)},
            spawn_runtime=spawn_runtime,
            client_factory=lambda runtime_info: fake_client,
            runtime_root=tmp_path,
        )

        status = await manager.get_status()

        assert status['status'] == 'ready'
        assert status['runtime_configured'] is True
        assert status['runtime_startable'] is True
        assert status['runtime_reachable'] is True
        assert status['host'] == '127.0.0.1'
        assert status['port'] == 55123
        assert status['send_enabled'] is True
        assert status['allowed_connector_count'] == 1
        assert status['send_error_code'] is None


async def test_runtime_process_manager_get_status_restarts_after_lost_runtime():
    with TemporaryDirectory(dir=r'C:\Users\33031\Desktop\bot\.tmp-pytest') as temp_dir:
        tmp_path = Path(temp_dir)
        runtime_executable = _write_official_runtime(tmp_path, '2026-06-30T04-24-26-368Z')
        spawn_count = 0

        async def spawn_runtime(path: Path, *, env: dict[str, str], cwd: Path):
            nonlocal spawn_count
            spawn_count += 1
            assert path == runtime_executable
            assert f'LANGBOT_RPA_{"MANAGED"}' not in env
            assert f'LANGBOT_RPA_{"TOKEN"}' not in env
            token = 'a' * 64 if spawn_count == 1 else 'b' * 64
            return _FakeProcess(
                [
                    '{"pid": %s, "port": %s, "token": "%s", "protocolVersion": "2", "runtimeVersion": "0.1.2"}\n'
                    % (4320 + spawn_count, 55122 + spawn_count, token)
                ],
                pid=4320 + spawn_count,
            )

        unavailable_client = SimpleNamespace(
            health=AsyncMock(return_value={'status': 'ready'}),
            capabilities=AsyncMock(side_effect=RuntimeError('runtime exited')),
        )
        ready_client = SimpleNamespace(
            health=AsyncMock(return_value={'status': 'ready'}),
            capabilities=AsyncMock(
                return_value={
                    'sendEnabled': True,
                    'allowedConnectorCount': 0,
                    'sendErrorCode': None,
                }
            ),
        )
        clients = iter((unavailable_client, ready_client))
        manager = DesktopRuntimeProcessManager(
            config={'enabled': True, 'runtime_executable': str(runtime_executable)},
            spawn_runtime=spawn_runtime,
            client_factory=lambda runtime_info: next(clients),
            runtime_root=tmp_path,
        )
        manager._terminate_owned_runtime_snapshot = AsyncMock()

        status = await manager.get_status()

        assert spawn_count == 2
        assert manager.runtime_info is not None
        assert manager.runtime_info['port'] == 55124
        assert manager.runtime_info['token'] == 'b' * 64
        assert manager.client is ready_client
        assert status['status'] == 'ready'
        assert status['runtime_reachable'] is True
        assert status['protocolVersion'] == '2'


async def test_runtime_process_manager_get_status_reports_unrestricted_send():
    with TemporaryDirectory(dir=r'C:\Users\33031\Desktop\bot\.tmp-pytest') as temp_dir:
        tmp_path = Path(temp_dir)
        runtime_executable = _write_official_runtime(tmp_path, '2026-06-30T04-24-26-368Z')

        async def spawn_runtime(path: Path, *, env: dict[str, str], cwd: Path):
            assert path == runtime_executable
            return _FakeProcess(['{"pid": 4321, "port": 55123, "token": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "protocolVersion": "2", "runtimeVersion": "0.1.2"}\n'])

        fake_client = SimpleNamespace(
            health=AsyncMock(return_value={'status': 'ready'}),
            capabilities=AsyncMock(
                return_value={
                    'windowingAvailable': True,
                    'captureAvailable': True,
                    'inputAvailable': True,
                    'providerHubReady': True,
                    'sendEnabled': False,
                    'allowedConnectorCount': 0,
                    'sendErrorCode': None,
                }
            ),
        )

        manager = DesktopRuntimeProcessManager(
            config={'enabled': True, 'runtime_executable': str(runtime_executable)},
            spawn_runtime=spawn_runtime,
            client_factory=lambda runtime_info: fake_client,
            runtime_root=tmp_path,
        )

        status = await manager.get_status()

        assert status['status'] == 'ready'
        assert status['send_enabled'] is False
        assert status['allowed_connector_count'] == 0
    assert status['send_error_code'] is None


async def test_runtime_stop_uses_owned_snapshot_and_clears_fields_in_finally(monkeypatch):
    with TemporaryDirectory(dir=r'C:\Users\33031\Desktop\bot\.tmp-pytest') as temp_dir:
        tmp_path = Path(temp_dir)
        target = _write_official_runtime(tmp_path, '2026-06-30T04-24-26-368Z')
        manager = DesktopRuntimeProcessManager(config={'enabled': True}, runtime_root=tmp_path)
        process = _FakeProcess([], pid=4321)
        runtime_info = {
            'pid': 4321,
            'processCreateTime': 10.0,
            'host': '127.0.0.1',
            'port': 55123,
            'protocolVersion': '2',
            'runtimeVersion': '0.1.2',
            'token': 'memory-only-token',
            'executablePath': str(target),
        }
        client = object()
        stderr_task = asyncio.create_task(asyncio.sleep(10))
        manager.process = process
        manager.client = client
        manager.runtime_info = runtime_info
        manager._stderr_task = stderr_task
        manager._selected_runtime_executable = target

        observed = {}

        async def fake_terminate(snapshot) -> None:
            observed['snapshot'] = snapshot
            assert snapshot.process is process
            assert snapshot.pid == process.pid
            assert snapshot.runtime_info == runtime_info
            assert snapshot.client is client
            assert snapshot.stderr_task is stderr_task
            assert snapshot.selected_runtime_executable == target
            assert manager.process is process
            assert manager.runtime_info == runtime_info
            assert manager.client is client
            raise RuntimeError('cleanup failed')

        monkeypatch.setattr(manager, '_terminate_owned_runtime_snapshot', fake_terminate)

        with pytest.raises(RuntimeError, match='cleanup failed'):
            await manager.stop()

        await asyncio.sleep(0)

        assert observed['snapshot'].pid == 4321
        assert manager.process is None
        assert manager.client is None
        assert manager.runtime_info is None
        assert manager._stderr_task is None
        assert manager._selected_runtime_executable is None
        assert manager._stopping is False
        assert stderr_task.cancelled() is True


def test_runtime_stop_does_not_kill_reused_pid_when_create_time_differs(monkeypatch):
    with TemporaryDirectory(dir=r'C:\Users\33031\Desktop\bot\.tmp-pytest') as temp_dir:
        tmp_path = Path(temp_dir)
        target = _write_official_runtime(tmp_path, '2026-06-30T04-24-26-368Z')
        reused_process = _FakePsutilProcess(4321, str(target), create_time=99.0)

        class _ExplodingAsyncProcess:
            pid = 4321
            returncode = None

            def terminate(self) -> None:
                raise AssertionError('stop() must not terminate asyncio process directly when PID was reused')

            def kill(self) -> None:
                raise AssertionError('stop() must not kill asyncio process directly when PID was reused')

        monkeypatch.setattr('langbot.pkg.desktop_automation.runtime_process.psutil.Process', lambda pid: reused_process)
        manager = DesktopRuntimeProcessManager(config={'enabled': True}, runtime_root=tmp_path)
        manager.process = _ExplodingAsyncProcess()
        manager.runtime_info = {
            'pid': 4321,
            'processCreateTime': 10.0,
            'host': '127.0.0.1',
            'port': 55123,
            'protocolVersion': '2',
            'runtimeVersion': '0.1.2',
            'token': 'memory-only-token',
            'executablePath': str(target),
        }
        manager.client = object()
        manager._selected_runtime_executable = target

        asyncio.run(manager.stop())

        assert reused_process.terminated is False
        assert reused_process.killed is False
        assert manager.process is None
        assert manager.runtime_info is None
        assert manager.client is None


async def test_runtime_spawn_records_pid_create_time(monkeypatch):
    with TemporaryDirectory(dir=r'C:\Users\33031\Desktop\bot\.tmp-pytest') as temp_dir:
        tmp_path = Path(temp_dir)
        runtime_executable = _write_official_runtime(tmp_path, '2026-06-30T04-24-26-368Z')

        async def spawn_runtime(path: Path, *, env: dict[str, str], cwd: Path):
            return _FakeProcess(
                ['{"pid": 4321, "port": 55123, "token": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "protocolVersion": "2", "runtimeVersion": "0.1.2"}\n'],
                pid=4321,
            )

        fake_client = SimpleNamespace(
            health=AsyncMock(return_value={'status': 'ready'}), capabilities=AsyncMock(return_value={})
        )
        owned_process = _FakePsutilProcess(4321, str(runtime_executable), create_time=12.5)
        monkeypatch.setattr('langbot.pkg.desktop_automation.runtime_process.psutil.Process', lambda pid: owned_process)
        monkeypatch.setattr('langbot.pkg.desktop_automation.runtime_process.psutil.process_iter', lambda attrs=None: iter(()))
        manager = DesktopRuntimeProcessManager(
            config={'enabled': True, 'runtime_executable': str(runtime_executable)},
            spawn_runtime=spawn_runtime,
            client_factory=lambda runtime_info: fake_client,
            runtime_root=tmp_path,
        )

        runtime_info = await manager.ensure_started()

        assert runtime_info['pid'] == 4321
        assert runtime_info['processCreateTime'] == 12.5


async def test_runtime_handshake_pid_mismatch_stops_spawned_process_and_fails(monkeypatch):
    with TemporaryDirectory(dir=r'C:\Users\33031\Desktop\bot\.tmp-pytest') as temp_dir:
        tmp_path = Path(temp_dir)
        runtime_executable = _write_official_runtime(tmp_path, '2026-06-30T04-24-26-368Z')
        events: list[tuple[str, int]] = []
        child = _FakePsutilProcess(5001, str(runtime_executable.parent / 'helper.exe'), events=events)
        owned_process = _FakePsutilProcess(
            4321,
            str(runtime_executable),
            children=[child],
            create_time=12.5,
            events=events,
        )
        fake_psutil = _FakePsutilModule([owned_process], iter_processes=[])

        async def spawn_runtime(path: Path, *, env: dict[str, str], cwd: Path):
            return _FakeProcess(
                ['{"pid": 9999, "port": 55123, "token": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "protocolVersion": "2", "runtimeVersion": "0.1.2"}\n'],
                pid=4321,
            )

        client_factory = AsyncMock()
        monkeypatch.setattr('langbot.pkg.desktop_automation.runtime_process.psutil', fake_psutil)
        manager = DesktopRuntimeProcessManager(
            config={'enabled': True, 'runtime_executable': str(runtime_executable)},
            spawn_runtime=spawn_runtime,
            client_factory=client_factory,
            runtime_root=tmp_path,
        )

        with pytest.raises(DesktopAutomationError) as exc_info:
            await manager.ensure_started()

        assert exc_info.value.code == RUNTIME_START_FAILED
        assert str(exc_info.value) == 'Desktop runtime handshake pid mismatch'
        assert events == [
            ('terminate', 5001),
            ('terminate', 4321),
        ]
        assert manager.process is None
        assert manager.runtime_info is None
        assert manager.client is None
        client_factory.assert_not_called()


async def test_runtime_handshake_protocol_mismatch_stops_spawned_process_and_fails(monkeypatch):
    with TemporaryDirectory(dir=r'C:\Users\33031\Desktop\bot\.tmp-pytest') as temp_dir:
        tmp_path = Path(temp_dir)
        runtime_executable = _write_official_runtime(tmp_path, '2026-06-30T04-24-26-368Z')
        owned_process = _FakePsutilProcess(4321, str(runtime_executable), create_time=12.5)
        fake_psutil = _FakePsutilModule([owned_process], iter_processes=[])

        async def spawn_runtime(path: Path, *, env: dict[str, str], cwd: Path):
            return _FakeProcess(
                ['{"pid": 4321, "port": 55123, "token": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "protocolVersion": "999", "runtimeVersion": "0.1.2"}\n'],
                pid=4321,
            )

        client_factory = AsyncMock()
        monkeypatch.setattr('langbot.pkg.desktop_automation.runtime_process.psutil', fake_psutil)
        manager = DesktopRuntimeProcessManager(
            config={'enabled': True, 'expected_protocol_version': '2'},
            spawn_runtime=spawn_runtime,
            client_factory=client_factory,
            runtime_root=tmp_path,
        )

        with pytest.raises(DesktopAutomationError) as exc_info:
            await manager.ensure_started()

        assert exc_info.value.code == RUNTIME_PROTOCOL_MISMATCH
        assert 'expected 2, got 999' in str(exc_info.value)
        assert owned_process.terminated is True
        assert manager.process is None
        assert manager.runtime_info is None
        assert manager.client is None
        client_factory.assert_not_called()


async def test_runtime_handshake_runtime_version_mismatch_stops_spawned_process_and_fails(monkeypatch):
    with TemporaryDirectory(dir=r'C:\Users\33031\Desktop\bot\.tmp-pytest') as temp_dir:
        tmp_path = Path(temp_dir)
        runtime_executable = _write_official_runtime(tmp_path, '2026-06-30T04-24-26-368Z')
        owned_process = _FakePsutilProcess(4321, str(runtime_executable), create_time=12.5)
        fake_psutil = _FakePsutilModule([owned_process], iter_processes=[])

        async def spawn_runtime(path: Path, *, env: dict[str, str], cwd: Path):
            return _FakeProcess([
                '{"pid": 4321, "port": 55123, "token": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "protocolVersion": "2", "runtimeVersion": "999"}\n'
            ], pid=4321)

        client_factory = AsyncMock()
        monkeypatch.setattr('langbot.pkg.desktop_automation.runtime_process.psutil', fake_psutil)
        manager = DesktopRuntimeProcessManager(
            config={'enabled': True},
            spawn_runtime=spawn_runtime,
            client_factory=client_factory,
            runtime_root=tmp_path,
        )

        with pytest.raises(DesktopAutomationError) as exc_info:
            await manager.ensure_started()

        assert exc_info.value.code == RUNTIME_PROTOCOL_MISMATCH
        assert 'expected 0.1.2, got 999' in str(exc_info.value)
        assert owned_process.terminated is True
        assert manager.runtime_info is None
        assert manager.client is None
        client_factory.assert_not_called()


async def test_runtime_readiness_timeout_stops_spawned_process_and_clears_state(monkeypatch):
    with TemporaryDirectory(dir=r'C:\Users\33031\Desktop\bot\.tmp-pytest') as temp_dir:
        tmp_path = Path(temp_dir)
        runtime_executable = _write_official_runtime(tmp_path, '2026-06-30T04-24-26-368Z')
        owned_process = _FakePsutilProcess(4321, str(runtime_executable), create_time=12.5)
        fake_psutil = _FakePsutilModule([owned_process], iter_processes=[])

        async def spawn_runtime(path: Path, *, env: dict[str, str], cwd: Path):
            return _FakeProcess(
                ['{"pid": 4321, "port": 55123, "token": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "protocolVersion": "2", "runtimeVersion": "0.1.2"}\n'],
                pid=4321,
            )

        fake_client = SimpleNamespace(
            health=AsyncMock(return_value={'status': 'starting'}),
            capabilities=AsyncMock(return_value={}),
        )
        monkeypatch.setattr('langbot.pkg.desktop_automation.runtime_process.psutil', fake_psutil)
        manager = DesktopRuntimeProcessManager(
            config={'enabled': True, 'startup_timeout_seconds': 0.05},
            spawn_runtime=spawn_runtime,
            client_factory=lambda runtime_info: fake_client,
            runtime_root=tmp_path,
        )

        with pytest.raises(DesktopAutomationError) as exc_info:
            await manager.ensure_started()

        assert exc_info.value.code == RUNTIME_UNAVAILABLE
        assert str(exc_info.value) == 'Desktop runtime failed to become ready in time'
        assert owned_process.terminated is True
        assert manager.process is None
        assert manager.runtime_info is None
        assert manager.client is None


async def test_runtime_readiness_health_exception_stops_spawned_process_and_preserves_primary_error(monkeypatch):
    with TemporaryDirectory(dir=r'C:\Users\33031\Desktop\bot\.tmp-pytest') as temp_dir:
        tmp_path = Path(temp_dir)
        runtime_executable = _write_official_runtime(tmp_path, '2026-06-30T04-24-26-368Z')
        owned_process = _FakePsutilProcess(4321, str(runtime_executable), create_time=12.5)
        fake_psutil = _FakePsutilModule([owned_process], iter_processes=[])

        async def spawn_runtime(path: Path, *, env: dict[str, str], cwd: Path):
            return _FakeProcess(
                ['{"pid": 4321, "port": 55123, "token": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "protocolVersion": "2", "runtimeVersion": "0.1.2"}\n'],
                pid=4321,
            )

        fake_client = SimpleNamespace(
            health=AsyncMock(side_effect=RuntimeError('health exploded')),
            capabilities=AsyncMock(return_value={}),
        )
        monkeypatch.setattr('langbot.pkg.desktop_automation.runtime_process.psutil', fake_psutil)
        manager = DesktopRuntimeProcessManager(
            config={'enabled': True, 'startup_timeout_seconds': 0.05},
            spawn_runtime=spawn_runtime,
            client_factory=lambda runtime_info: fake_client,
            runtime_root=tmp_path,
        )

        with pytest.raises(DesktopAutomationError) as exc_info:
            await manager.ensure_started()

        assert exc_info.value.code == RUNTIME_UNAVAILABLE
        assert str(exc_info.value) == 'Desktop runtime readiness health check failed'
        assert isinstance(exc_info.value.__cause__, RuntimeError)
        assert owned_process.terminated is True
        assert manager.process is None
        assert manager.runtime_info is None
        assert manager.client is None


async def test_runtime_readiness_child_exits_early_stops_spawned_process(monkeypatch):
    with TemporaryDirectory(dir=r'C:\Users\33031\Desktop\bot\.tmp-pytest') as temp_dir:
        tmp_path = Path(temp_dir)
        runtime_executable = _write_official_runtime(tmp_path, '2026-06-30T04-24-26-368Z')
        owned_process = _FakePsutilProcess(4321, str(runtime_executable), create_time=12.5)
        fake_psutil = _FakePsutilModule([owned_process], iter_processes=[])

        class _ExitedProcess(_FakeProcess):
            def __init__(self):
                super().__init__(
                    ['{"pid": 4321, "port": 55123, "token": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "protocolVersion": "2", "runtimeVersion": "0.1.2"}\n'],
                    pid=4321,
                )
                self.returncode = 1

        async def spawn_runtime(path: Path, *, env: dict[str, str], cwd: Path):
            return _ExitedProcess()

        fake_client = SimpleNamespace(
            health=AsyncMock(return_value={'status': 'starting'}),
            capabilities=AsyncMock(return_value={}),
        )
        monkeypatch.setattr('langbot.pkg.desktop_automation.runtime_process.psutil', fake_psutil)
        manager = DesktopRuntimeProcessManager(
            config={'enabled': True, 'startup_timeout_seconds': 0.2},
            spawn_runtime=spawn_runtime,
            client_factory=lambda runtime_info: fake_client,
            runtime_root=tmp_path,
        )

        with pytest.raises(DesktopAutomationError) as exc_info:
            await manager.ensure_started()

        assert exc_info.value.code == RUNTIME_START_FAILED
        assert str(exc_info.value) == 'Desktop runtime exited before readiness'
        assert owned_process.terminated is True
        assert manager.process is None
        assert manager.runtime_info is None
        assert manager.client is None


async def test_runtime_stop_terminates_children_before_parent_and_kills_remaining_after_wait(monkeypatch):
    with TemporaryDirectory(dir=r'C:\Users\33031\Desktop\bot\.tmp-pytest') as temp_dir:
        tmp_path = Path(temp_dir)
        target = _write_official_runtime(tmp_path, '2026-06-30T04-24-26-368Z')
        events: list[tuple[str, int]] = []
        child_one = _FakePsutilProcess(5001, str(target.parent / 'child-one.exe'), events=events)
        child_two = _FakePsutilProcess(5002, str(target.parent / 'child-two.exe'), events=events)
        owned_process = _FakePsutilProcess(
            4321,
            str(target),
            children=[child_one, child_two],
            create_time=10.0,
            events=events,
        )

        wait_calls = []

        def fake_wait_procs(procs, timeout=None):
            proc_list = list(procs)
            wait_calls.append(([proc.pid for proc in proc_list], timeout))
            if len(wait_calls) == 1:
                return ([], proc_list)
            return (proc_list, [])

        class _ExplodingAsyncProcess:
            pid = 4321
            returncode = None

            def terminate(self) -> None:
                raise AssertionError('stop() must terminate via psutil tree, not asyncio process directly')

            def kill(self) -> None:
                raise AssertionError('stop() must kill via psutil tree, not asyncio process directly')

        monkeypatch.setattr('langbot.pkg.desktop_automation.runtime_process.psutil.Process', lambda pid: owned_process)
        monkeypatch.setattr('langbot.pkg.desktop_automation.runtime_process.psutil.wait_procs', fake_wait_procs)
        manager = DesktopRuntimeProcessManager(config={'enabled': True}, runtime_root=tmp_path)
        manager.process = _ExplodingAsyncProcess()
        manager.runtime_info = {
            'pid': 4321,
            'processCreateTime': 10.0,
            'host': '127.0.0.1',
            'port': 55123,
            'protocolVersion': '2',
            'runtimeVersion': '0.1.2',
            'token': 'memory-only-token',
            'executablePath': str(target),
        }
        manager.client = object()
        manager._selected_runtime_executable = target

        await manager.stop()

        assert events == [
            ('terminate', 5001),
            ('terminate', 5002),
            ('terminate', 4321),
            ('kill', 5001),
            ('kill', 5002),
            ('kill', 4321),
        ]
        assert wait_calls == [([5001, 5002, 4321], 5), ([5001, 5002, 4321], 5)]
