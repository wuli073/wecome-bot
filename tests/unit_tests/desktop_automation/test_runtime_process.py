from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from langbot.pkg.desktop_automation.errors import (
    RPA_RUNTIME_NOT_AVAILABLE,
    RUNTIME_START_FAILED,
    DesktopAutomationError,
)
from langbot.pkg.desktop_automation.runtime_process import (
    DesktopRuntimeProcessManager,
    apply_local_desktop_automation_defaults,
    list_runtime_candidates,
    resolve_latest_runtime_executable,
    resolve_runtime_executable_path,
)


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
    def __init__(self, stdout_lines: list[str]) -> None:
        self.stdout = _FakeStdout(stdout_lines)
        self.stderr = _FakeStderr([])
        self.pid = 4321
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
    ) -> None:
        self.pid = pid
        self._exe = exe
        self._children = children or []
        self.terminated = False
        self.killed = False
        self.waited_timeout = None
        self.running = running

    def name(self) -> str:
        return 'LangBot Desktop RPA Runtime.exe'

    def exe(self) -> str | None:
        if self._exe is None:
            raise RuntimeError('missing exe')
        return self._exe

    def children(self, recursive: bool = False):
        if not recursive:
            return list(self._children)
        descendants = list(self._children)
        for child in self._children:
            descendants.extend(child.children(recursive=True))
        return descendants

    def terminate(self) -> None:
        self.terminated = True

    def kill(self) -> None:
        self.killed = True

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

    def __init__(self, processes: list[_FakePsutilProcess]) -> None:
        self._processes = processes
        self.wait_procs_calls: list[tuple[list[int], float | None]] = []

    def process_iter(self, attrs=None):
        return iter(self._processes)

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
    executable = _official_runtime_executable(root, build_dir)
    executable.parent.mkdir(parents=True, exist_ok=True)
    executable.write_text(build_dir, encoding='utf-8')
    return executable


def test_defaults_keep_runtime_configuration_in_phase2():
    config = apply_local_desktop_automation_defaults(
        {
            'enabled': True,
            'runtime_executable': 'C:/runtime/runtime.exe',
        }
    )

    assert config['enabled'] is True
    assert config['runtime_executable'] == 'C:/runtime/runtime.exe'
    assert config['expected_protocol_version'] == '1'


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


async def test_runtime_process_manager_starts_and_returns_runtime_info():
    with TemporaryDirectory(dir=r'C:\Users\33031\Desktop\bot\.tmp-pytest') as temp_dir:
        tmp_path = Path(temp_dir)
        runtime_executable = _write_official_runtime(tmp_path, '2026-06-30T04-24-26-368Z')

        async def spawn_runtime(path: Path, *, env: dict[str, str], cwd: Path):
            assert path == runtime_executable
            assert env['LANGBOT_RPA_TOKEN']
            assert cwd == runtime_executable.parent
            return _FakeProcess(['{"pid": 4321, "port": 55123, "protocolVersion": "1", "runtimeVersion": "0.1.0"}\n'])

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
        assert runtime_info['protocolVersion'] == '1'
        assert runtime_info['runtimeVersion'] == '0.1.0'
        assert runtime_info['token']
        assert isinstance(manager.client, object)


async def test_runtime_process_manager_reports_not_available_when_runtime_missing():
    with TemporaryDirectory(dir=r'C:\Users\33031\Desktop\bot\.tmp-pytest') as temp_dir:
        tmp_path = Path(temp_dir)
        manager = DesktopRuntimeProcessManager(config={'enabled': True}, runtime_root=tmp_path)

        status = await manager.get_status()

        assert status['status'] == 'not_available'
        assert status['errorCode'] == RPA_RUNTIME_NOT_AVAILABLE
        assert status['runtime_startable'] is False


async def test_runtime_process_manager_stop_terminates_child():
    with TemporaryDirectory(dir=r'C:\Users\33031\Desktop\bot\.tmp-pytest') as temp_dir:
        tmp_path = Path(temp_dir)
        runtime_executable = _write_official_runtime(tmp_path, '2026-06-30T04-24-26-368Z')
        process = _FakeProcess(['{"pid": 4321, "port": 55123, "protocolVersion": "1", "runtimeVersion": "0.1.0"}\n'])

        async def spawn_runtime(path: Path, *, env: dict[str, str], cwd: Path):
            return process

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
        await manager.stop()

        assert process.terminated is True


async def test_runtime_process_manager_allows_only_blank_stdout_before_handshake():
    manager = DesktopRuntimeProcessManager(config={'enabled': True}, runtime_root=Path('C:/missing'))
    process = _FakeProcess(
        ['\r\n', '   \n', '{"pid": 4321, "port": 55123, "protocolVersion": "1", "runtimeVersion": "0.1.0"}\n']
    )

    handshake = await manager._read_handshake(process)

    assert handshake['port'] == 55123


async def test_runtime_process_manager_rejects_non_empty_stdout_before_handshake():
    manager = DesktopRuntimeProcessManager(config={'enabled': True}, runtime_root=Path('C:/missing'))
    process = _FakeProcess(
        ['not-json\n', '{"pid": 4321, "port": 55123, "protocolVersion": "1", "runtimeVersion": "0.1.0"}\n']
    )

    with pytest.raises(DesktopAutomationError) as exc_info:
        await manager._read_handshake(process)

    assert exc_info.value.code == RUNTIME_START_FAILED


async def test_runtime_token_is_never_written_to_auth_token_file():
    with TemporaryDirectory(dir=r'C:\Users\33031\Desktop\bot\.tmp-pytest') as temp_dir:
        tmp_path = Path(temp_dir)
        runtime_executable = _write_official_runtime(tmp_path, '2026-06-30T04-24-26-368Z')
        token_file = tmp_path / 'auth-token.txt'

        async def spawn_runtime(path: Path, *, env: dict[str, str], cwd: Path):
            assert env['LANGBOT_RPA_TOKEN']
            assert not token_file.exists()
            return _FakeProcess(['{"pid": 4321, "port": 55123, "protocolVersion": "1", "runtimeVersion": "0.1.0"}\n'])

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
            'protocolVersion': '1',
            'runtimeVersion': '0.1.0',
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

        assert stale_proc.terminated is True
        assert stale_child.terminated is True
        assert foreign_proc.terminated is False
        assert 'Replacing stale desktop runtime' in caplog.text
        assert str(stale) in caplog.text
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


async def test_runtime_process_manager_new_python_process_does_not_take_over_existing_target_runtime(
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
            tokens.append(env['LANGBOT_RPA_TOKEN'])
            return _FakeProcess(['{"pid": 9101, "port": 55123, "protocolVersion": "1", "runtimeVersion": "0.1.0"}\n'])

        monkeypatch.setattr('langbot.pkg.desktop_automation.runtime_process.psutil', fake_psutil)
        caplog.set_level(logging.INFO)
        manager = DesktopRuntimeProcessManager(
            config={'enabled': True},
            runtime_root=tmp_path,
            spawn_runtime=spawn_runtime,
            client_factory=lambda runtime_info: fake_client,
        )

        runtime_info = await manager.ensure_started()

        assert selected_paths == [target]
        assert existing.terminated is True
        assert runtime_info['pid'] == 9101
        assert tokens and tokens[0]
        assert 'Reusing desktop runtime' not in caplog.text
        assert 'Replacing stale desktop runtime' in caplog.text
        assert 'Selected desktop runtime' in caplog.text
        assert tokens[0] not in caplog.text


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
            return _FakeProcess(['{"pid": 4321, "port": 55123, "protocolVersion": "1", "runtimeVersion": "0.1.0"}\n'])

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
