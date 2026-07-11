from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest


def test_process_manager_is_running_checks_pid_create_time_and_command(monkeypatch, tmp_path):
    from langbot.pkg.local_connectors.process_manager import LocalConnectorProcessManager
    from langbot.pkg.local_connectors.repository import LocalConnectorRepository

    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    repository = LocalConnectorRepository()
    manager = LocalConnectorProcessManager(repository)
    repository.save_process(
        "wechat-local",
        {
            "pid": 1234,
            "created_at": 10.0,
            "script_path": r"C:\repo\bot\vendor\wechat_decrypt\mcp_http_server.py",
            "python_executable": r"C:\repo\bot\python.exe",
        },
    )

    class FakeProcess:
        def create_time(self):
            return 10.0

        def cmdline(self):
            return [
                r"C:\repo\bot\python.exe",
                r"C:\repo\bot\vendor\wechat_decrypt\mcp_http_server.py",
            ]

        def exe(self):
            return r"C:\repo\bot\python.exe"

    monkeypatch.setattr(
        "langbot.pkg.local_connectors.process_manager.psutil.Process",
        lambda _pid: FakeProcess(),
    )

    assert manager.is_running("wechat-local") is True


def test_process_manager_raises_when_port_is_in_use(monkeypatch, tmp_path):
    from langbot.pkg.local_connectors.process_manager import LocalConnectorProcessManager, PortInUseError
    from langbot.pkg.local_connectors.repository import LocalConnectorRepository

    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    repository = LocalConnectorRepository()
    manager = LocalConnectorProcessManager(repository)
    monkeypatch.setattr(manager, "_find_listener_pid", lambda _port: 9999)

    with pytest.raises(PortInUseError, match="already in use"):
        manager.ensure_port_available(5680)


@pytest.mark.asyncio
async def test_process_manager_start_records_listener_child_pid(monkeypatch, tmp_path):
    from langbot.pkg.local_connectors.process_manager import LocalConnectorProcessManager
    from langbot.pkg.local_connectors.repository import LocalConnectorRepository

    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    repository = LocalConnectorRepository()
    manager = LocalConnectorProcessManager(repository)

    connector = SimpleNamespace(
        connector_id="wechat-local",
        port=5680,
        port_for_role=lambda role: 5680 if role == "mcp" else None,
        build_start_command=lambda role="mcp", runtime_dir=None: [
            r"C:\repo\bot\python.exe",
            "-X",
            "utf8",
            r"C:\repo\bot\vendor\wechat_decrypt\mcp_http_server.py",
        ],
        resolve_decrypt_dir=lambda: tmp_path,
        build_start_env=lambda _runtime_dir, role="mcp": {},
        build_command_identity=lambda runtime_dir, role="mcp": {
            "script_path": r"C:\repo\bot\vendor\wechat_decrypt\mcp_http_server.py",
            "python_executable": r"C:\repo\bot\python.exe",
            "app_dir": runtime_dir,
        },
    )

    class FakeAsyncProcess:
        pid = 2000

    async def fake_create_subprocess_exec(*_args, **_kwargs):
        return FakeAsyncProcess()

    class FakeControllerProcess:
        def __init__(self, pid):
            self.pid = pid

        def create_time(self):
            return 11.0

    class FakeListenerParent:
        pid = 2000

    class FakeListenerProcess:
        pid = 3000

        def create_time(self):
            return 12.0

        def parent(self):
            return FakeListenerParent()

    monkeypatch.setattr(
        "langbot.pkg.local_connectors.process_manager.asyncio.create_subprocess_exec",
        fake_create_subprocess_exec,
    )
    monkeypatch.setattr(
        "langbot.pkg.local_connectors.process_manager.psutil.Process",
        lambda pid: FakeControllerProcess(pid) if pid == 2000 else FakeListenerProcess(),
    )
    listener_pids = iter([None, 3000])
    monkeypatch.setattr(manager, "_find_listener_pid", lambda _port: next(listener_pids))

    record = await manager.start(connector, str(tmp_path / "runtime"))

    assert record["pid"] == 3000
    assert record["controller_pid"] == 2000
    assert record["created_at"] == 12.0
    assert record["controller_created_at"] == 11.0


@pytest.mark.asyncio
async def test_process_manager_start_waits_long_enough_for_delayed_listener(monkeypatch, tmp_path):
    from langbot.pkg.local_connectors.process_manager import LocalConnectorProcessManager
    from langbot.pkg.local_connectors.repository import LocalConnectorRepository

    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    repository = LocalConnectorRepository()
    manager = LocalConnectorProcessManager(repository)

    connector = SimpleNamespace(
        connector_id="wechat-local",
        port=5680,
        port_for_role=lambda role: 5680 if role == "mcp" else None,
        build_start_command=lambda role="mcp", runtime_dir=None: [
            r"C:\repo\bot\python.exe",
            "-X",
            "utf8",
            r"C:\repo\bot\vendor\wechat_decrypt\mcp_http_server.py",
        ],
        resolve_decrypt_dir=lambda: tmp_path,
        build_start_env=lambda _runtime_dir, role="mcp": {},
        build_command_identity=lambda runtime_dir, role="mcp": {
            "script_path": r"C:\repo\bot\vendor\wechat_decrypt\mcp_http_server.py",
            "python_executable": r"C:\repo\bot\python.exe",
            "app_dir": runtime_dir,
        },
    )

    class FakeAsyncProcess:
        pid = 2000

    async def fake_create_subprocess_exec(*_args, **_kwargs):
        return FakeAsyncProcess()

    class FakeControllerProcess:
        def __init__(self, pid):
            self.pid = pid

        def create_time(self):
            return 11.0

    class FakeListenerParent:
        pid = 2000

    class FakeListenerProcess:
        pid = 3000

        def create_time(self):
            return 12.0

        def parent(self):
            return FakeListenerParent()

    monkeypatch.setattr(
        "langbot.pkg.local_connectors.process_manager.asyncio.create_subprocess_exec",
        fake_create_subprocess_exec,
    )
    monkeypatch.setattr(
        "langbot.pkg.local_connectors.process_manager.psutil.Process",
        lambda pid: FakeControllerProcess(pid) if pid == 2000 else FakeListenerProcess(),
    )
    listener_pids = iter([None] * 149 + [3000])
    monkeypatch.setattr(manager, "_find_listener_pid", lambda _port: next(listener_pids))

    record = await manager.start(connector, str(tmp_path / "runtime"))

    assert record["pid"] == 3000


@pytest.mark.asyncio
async def test_process_manager_start_supports_monitor_role_without_listener_port(monkeypatch, tmp_path):
    from langbot.pkg.local_connectors.process_manager import LocalConnectorProcessManager
    from langbot.pkg.local_connectors.repository import LocalConnectorRepository

    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    repository = LocalConnectorRepository()
    manager = LocalConnectorProcessManager(repository)

    connector = SimpleNamespace(
        connector_id="wxwork-local",
        port=5681,
        port_for_role=lambda role: None if role == "monitor" else 5681,
        build_start_command=lambda role="mcp", runtime_dir=None: [
            r"C:\repo\bot\python.exe",
            "-X",
            "utf8",
            r"C:\repo\bot\vendor\wechat_decrypt\wxwork_message_monitor.py",
            "--runtime-dir",
            runtime_dir,
        ],
        resolve_decrypt_dir=lambda: tmp_path,
        build_start_env=lambda _runtime_dir, role="mcp": {"ROLE": role},
        build_command_identity=lambda runtime_dir, role="mcp": {
            "script_path": r"C:\repo\bot\vendor\wechat_decrypt\wxwork_message_monitor.py",
            "python_executable": r"C:\repo\bot\python.exe",
            "app_dir": runtime_dir,
        },
    )

    class FakeAsyncProcess:
        pid = 4100

    async def fake_create_subprocess_exec(*_args, **_kwargs):
        return FakeAsyncProcess()

    class FakeControllerProcess:
        def __init__(self, pid):
            self.pid = pid

        def create_time(self):
            return 21.0

    class FakeChildProcess:
        pid = 4200

        def create_time(self):
            return 22.0

    monkeypatch.setattr(
        "langbot.pkg.local_connectors.process_manager.asyncio.create_subprocess_exec",
        fake_create_subprocess_exec,
    )
    monkeypatch.setattr(
        "langbot.pkg.local_connectors.process_manager.psutil.Process",
        lambda pid: FakeControllerProcess(pid),
    )
    wait_for_child = AsyncMock(return_value=FakeChildProcess())
    monkeypatch.setattr(manager, "_wait_for_child_process", wait_for_child)

    record = await manager.start(connector, str(tmp_path / "runtime"), role="monitor")

    wait_for_child.assert_awaited_once()
    assert record["pid"] == 4200
    assert record["controller_pid"] == 4100
    assert record["port"] is None
    assert record["role"] == "monitor"
    assert record["created_at"] == 22.0


def test_process_manager_is_running_accepts_listener_record_via_controller_identity(monkeypatch, tmp_path):
    from langbot.pkg.local_connectors.process_manager import LocalConnectorProcessManager
    from langbot.pkg.local_connectors.repository import LocalConnectorRepository

    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    repository = LocalConnectorRepository()
    manager = LocalConnectorProcessManager(repository)
    repository.save_process(
        "wechat-local",
        {
            "pid": 3000,
            "created_at": 12.0,
            "controller_pid": 2000,
            "controller_created_at": 11.0,
            "script_path": r"C:\repo\bot\vendor\wechat_decrypt\mcp_http_server.py",
            "python_executable": r"C:\repo\bot\python.exe",
        },
    )

    class FakeListenerProcess:
        def create_time(self):
            return 12.0

        def cmdline(self):
            return [r"C:\Python312\python.exe", "-X", "utf8", r"C:\repo\bot\vendor\wechat_decrypt\mcp_http_server.py"]

        def exe(self):
            return r"C:\Python312\python.exe"

    class FakeControllerProcess:
        def create_time(self):
            return 11.0

        def cmdline(self):
            return [
                r"C:\repo\bot\python.exe",
                "-X",
                "utf8",
                r"C:\repo\bot\vendor\wechat_decrypt\mcp_http_server.py",
            ]

        def exe(self):
            return r"C:\repo\bot\python.exe"

    monkeypatch.setattr(
        "langbot.pkg.local_connectors.process_manager.psutil.Process",
        lambda pid: FakeListenerProcess() if pid == 3000 else FakeControllerProcess(),
    )

    assert manager.is_running("wechat-local") is True


def test_process_manager_stop_terminates_controller_then_listener(monkeypatch, tmp_path):
    from langbot.pkg.local_connectors.process_manager import LocalConnectorProcessManager
    from langbot.pkg.local_connectors.repository import LocalConnectorRepository

    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    repository = LocalConnectorRepository()
    manager = LocalConnectorProcessManager(repository)
    repository.save_process(
        "wechat-local",
        {
            "pid": 3000,
            "created_at": 12.0,
            "controller_pid": 2000,
            "controller_created_at": 11.0,
            "script_path": r"C:\repo\bot\vendor\wechat_decrypt\mcp_http_server.py",
            "python_executable": r"C:\repo\bot\python.exe",
        },
    )

    class FakeListenerProcess:
        def create_time(self):
            return 12.0

        def cmdline(self):
            return [r"C:\Python312\python.exe", "-X", "utf8", r"C:\repo\bot\vendor\wechat_decrypt\mcp_http_server.py"]

        def exe(self):
            return r"C:\Python312\python.exe"

    class FakeControllerProcess:
        def create_time(self):
            return 11.0

        def cmdline(self):
            return [
                r"C:\repo\bot\python.exe",
                "-X",
                "utf8",
                r"C:\repo\bot\vendor\wechat_decrypt\mcp_http_server.py",
            ]

        def exe(self):
            return r"C:\repo\bot\python.exe"

    listener = Mock()
    listener.terminate = Mock()
    listener.wait = Mock()
    controller = Mock()
    controller.pid = 2000
    controller.children = Mock(return_value=[])
    controller.terminate = Mock()
    controller.wait = Mock()

    def fake_process(pid):
        if pid == 3000:
            return listener
        if pid == 2000:
            return controller
        if pid == 9999:
            return FakeListenerProcess()
        return FakeControllerProcess()

    monkeypatch.setattr(
        "langbot.pkg.local_connectors.process_manager.psutil.Process",
        fake_process,
    )
    monkeypatch.setattr(manager, "_is_owned_process", lambda _record: True)

    manager.stop_sync(SimpleNamespace(connector_id="wechat-local"))

    controller.terminate.assert_called_once()
    listener.terminate.assert_called_once()
    assert repository.load_process("wechat-local") is None


def test_process_manager_stop_monitor_terminates_controller_process_tree(monkeypatch, tmp_path):
    from langbot.pkg.local_connectors.process_manager import LocalConnectorProcessManager
    from langbot.pkg.local_connectors.repository import LocalConnectorRepository

    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    repository = LocalConnectorRepository()
    manager = LocalConnectorProcessManager(repository)
    repository.save_process(
        "wxwork-local",
        {
            "pid": 4100,
            "role": "monitor",
            "created_at": 22.0,
            "controller_pid": 4100,
            "controller_created_at": 21.0,
            "script_path": r"C:\repo\bot\vendor\wechat_decrypt\wxwork_message_monitor.py",
            "python_executable": r"C:\repo\bot\python.exe",
        },
        role="monitor",
    )

    class FakeMonitorProcess:
        def create_time(self):
            return 21.0

        def cmdline(self):
            return [
                r"C:\repo\bot\python.exe",
                "-X",
                "utf8",
                r"C:\repo\bot\vendor\wechat_decrypt\wxwork_message_monitor.py",
            ]

        def exe(self):
            return r"C:\repo\bot\python.exe"

    controller = Mock()
    controller.pid = 4100
    child = Mock()
    controller.children = Mock(return_value=[child])
    controller.terminate = Mock()
    controller.wait = Mock()
    child.pid = 4200
    child.terminate = Mock()
    child.wait = Mock()

    def fake_process(pid):
        if pid == 4100:
            return controller
        if pid == 4200:
            return child
        return FakeMonitorProcess()

    monkeypatch.setattr(
        "langbot.pkg.local_connectors.process_manager.psutil.Process",
        fake_process,
    )
    monkeypatch.setattr(manager, "_is_owned_process", lambda _record: True)

    manager.stop_sync(SimpleNamespace(connector_id="wxwork-local"), role="monitor")

    child.terminate.assert_called_once()
    controller.terminate.assert_called_once()
    assert repository.load_process("wxwork-local", role="monitor") is None


def test_process_manager_ignores_legacy_process_json(monkeypatch, tmp_path):
    from langbot.pkg.local_connectors.process_manager import LocalConnectorProcessManager
    from langbot.pkg.local_connectors.repository import LocalConnectorRepository

    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    repository = LocalConnectorRepository()
    manager = LocalConnectorProcessManager(repository)

    legacy_file = repository.connector_dir("wechat-local") / "process.json"
    legacy_file.write_text(
        '{"pid": 9999, "script_path": "C:\\\\legacy\\\\worker.py", "python_executable": "C:\\\\legacy\\\\python.exe"}',
        encoding="utf-8",
    )

    assert repository.load_process("wechat-local") is None
    assert manager.is_running("wechat-local") is False
