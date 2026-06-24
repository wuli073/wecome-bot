from __future__ import annotations

import asyncio
import os
import subprocess

import psutil

from .repository import LocalConnectorRepository


class PortInUseError(RuntimeError):
    pass


class LocalConnectorProcessManager:
    def __init__(self, repository: LocalConnectorRepository) -> None:
        self.repository = repository

    def get_process_record(self, connector_id: str, role: str = "mcp") -> dict | None:
        return self.repository.load_process(connector_id, role=role)

    @staticmethod
    def _cmdline_contains(process: psutil.Process, expected_part: str) -> bool:
        cmdline = [os.path.normcase(part) for part in process.cmdline()]
        return os.path.normcase(expected_part) in cmdline

    @staticmethod
    def _process_create_time_matches(process: psutil.Process, expected_created_at: float | None) -> bool:
        if expected_created_at is None:
            return True
        return abs(process.create_time() - float(expected_created_at)) <= 2

    def _process_matches_identity(
        self,
        process: psutil.Process,
        *,
        expected_script: str,
        expected_python: str,
        expected_created_at: float | None = None,
        require_python_match: bool = True,
    ) -> bool:
        if not self._process_create_time_matches(process, expected_created_at):
            return False

        if expected_script and not self._cmdline_contains(process, expected_script):
            return False

        if not expected_python:
            return True

        exe_path = ""
        try:
            exe_path = os.path.normcase(process.exe())
        except psutil.Error:
            exe_path = ""
        expected_python = os.path.normcase(expected_python)
        python_matches = exe_path == expected_python or self._cmdline_contains(process, expected_python)
        if require_python_match and not python_matches:
            return False

        return True

    def _process_matches_record(self, process: psutil.Process, record: dict) -> bool:
        expected_script = os.path.normcase(record.get("script_path", ""))
        expected_python = os.path.normcase(record.get("python_executable", ""))
        if self._process_matches_identity(
            process,
            expected_script=expected_script,
            expected_python=expected_python,
            expected_created_at=record.get("created_at"),
            require_python_match=False,
        ):
            return True

        controller_pid = record.get("controller_pid")
        if not controller_pid:
            return False
        try:
            controller_process = psutil.Process(int(controller_pid))
        except (TypeError, ValueError, psutil.Error):
            return False
        return self._process_matches_identity(
            controller_process,
            expected_script=expected_script,
            expected_python=expected_python,
            expected_created_at=record.get("controller_created_at"),
        )

    def _is_owned_process(self, record: dict | None) -> bool:
        if not record:
            return False
        try:
            process = psutil.Process(record["pid"])
        except (KeyError, psutil.Error):
            return False
        return self._process_matches_record(process, record)

    def is_running(self, connector_id: str, role: str = "mcp") -> bool:
        return self._is_owned_process(self.get_process_record(connector_id, role=role))

    def _find_listener_pid(self, port: int) -> int | None:
        for conn in psutil.net_connections(kind="tcp"):
            if conn.status == psutil.CONN_LISTEN and conn.laddr and conn.laddr.port == port:
                return conn.pid
        return None

    @staticmethod
    def _is_descendant_process(process: psutil.Process, ancestor_pid: int) -> bool:
        current = process
        while True:
            try:
                parent = current.parent()
            except psutil.Error:
                return False
            if parent is None:
                return False
            if parent.pid == ancestor_pid:
                return True
            current = parent

    async def _wait_for_listener_process(self, port: int, controller_pid: int) -> psutil.Process | None:
        for _ in range(50):
            listener_pid = self._find_listener_pid(port)
            if listener_pid is not None:
                try:
                    listener_process = psutil.Process(listener_pid)
                except psutil.Error:
                    listener_process = None
                if listener_process is not None:
                    if listener_process.pid == controller_pid or self._is_descendant_process(
                        listener_process, controller_pid
                    ):
                        return listener_process
            await asyncio.sleep(0.1)
        return None

    async def _wait_for_child_process(
        self,
        controller_pid: int,
        *,
        expected_script: str,
        expected_python: str,
    ) -> psutil.Process | None:
        for _ in range(50):
            try:
                controller_process = psutil.Process(controller_pid)
                children = controller_process.children(recursive=True)
            except psutil.Error:
                return None
            for child_process in children:
                if self._process_matches_identity(
                    child_process,
                    expected_script=expected_script,
                    expected_python=expected_python,
                    require_python_match=False,
                ):
                    return child_process
            await asyncio.sleep(0.1)
        return None

    def _terminate_process(self, pid: int | None) -> None:
        if not pid:
            return
        try:
            process = psutil.Process(int(pid))
        except (TypeError, ValueError, psutil.Error):
            return
        try:
            process.terminate()
            process.wait(timeout=10)
        except psutil.NoSuchProcess:
            return
        except psutil.TimeoutExpired:
            try:
                process.kill()
                process.wait(timeout=5)
            except psutil.Error:
                return
        except psutil.Error:
            return

    def _terminate_process_tree(self, pid: int | None) -> None:
        if not pid:
            return
        try:
            process = psutil.Process(int(pid))
        except (TypeError, ValueError, psutil.Error):
            return
        try:
            children = process.children(recursive=True)
        except psutil.Error:
            children = []
        for child in reversed(children):
            self._terminate_process(child.pid)
        self._terminate_process(process.pid)

    def ensure_port_available(self, port: int, owned_pid: int | None = None) -> None:
        listener_pid = self._find_listener_pid(port)
        if listener_pid is not None and listener_pid != owned_pid:
            raise PortInUseError(f"Port {port} is already in use")

    async def start(self, connector, runtime_dir: str, role: str = "mcp", env_overrides: dict | None = None) -> dict:
        existing = self.get_process_record(connector.connector_id, role=role)
        if self._is_owned_process(existing):
            return existing

        self.repository.save_process(connector.connector_id, None, role=role)
        role_port = connector.port_for_role(role)
        if role_port is not None:
            self.ensure_port_available(role_port)

        log_handle = open(self.repository.log_file(connector.connector_id, role=role), "a", encoding="utf-8")
        try:
            env = connector.build_start_env(runtime_dir, role=role)
            if env_overrides:
                env.update(env_overrides)
            process = await asyncio.create_subprocess_exec(
                *connector.build_start_command(role=role, runtime_dir=runtime_dir),
                cwd=str(connector.resolve_decrypt_dir()),
                env=env,
                stdout=log_handle,
                stderr=asyncio.subprocess.STDOUT,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        finally:
            log_handle.close()

        ps_process = psutil.Process(process.pid)
        listener_process = None
        identity = connector.build_command_identity(runtime_dir, role=role)
        if role_port is not None:
            listener_process = await self._wait_for_listener_process(role_port, process.pid)
        else:
            listener_process = await self._wait_for_child_process(
                process.pid,
                expected_script=os.path.normcase(identity.get("script_path", "")),
                expected_python=os.path.normcase(identity.get("python_executable", "")),
            )
        record = {
            "connector_id": connector.connector_id,
            "role": role,
            "pid": listener_process.pid if listener_process is not None else process.pid,
            "port": role_port,
            "created_at": listener_process.create_time() if listener_process is not None else ps_process.create_time(),
            "started_at": ps_process.create_time(),
            "controller_pid": process.pid,
            "controller_created_at": ps_process.create_time(),
            "command": connector.build_start_command(role=role, runtime_dir=runtime_dir),
            **identity,
        }
        self.repository.save_process(connector.connector_id, record, role=role)
        return record

    def stop_sync(self, connector, role: str = "mcp") -> None:
        record = self.get_process_record(connector.connector_id, role=role)
        if not self._is_owned_process(record):
            self.repository.save_process(connector.connector_id, None, role=role)
            return
        self._terminate_process_tree(record.get("controller_pid"))
        if record.get("pid") != record.get("controller_pid"):
            self._terminate_process(record.get("pid"))
        self.repository.save_process(connector.connector_id, None, role=role)

    async def stop(self, connector, role: str = "mcp") -> None:
        self.stop_sync(connector, role=role)

    async def restart(
        self,
        connector,
        runtime_dir: str,
        role: str = "mcp",
        env_overrides: dict | None = None,
    ) -> dict:
        await self.stop(connector, role=role)
        return await self.start(connector, runtime_dir, role=role, env_overrides=env_overrides)
