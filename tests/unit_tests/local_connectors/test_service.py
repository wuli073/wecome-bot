from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest


pytestmark = pytest.mark.asyncio


class TestLocalConnectorsServiceBuiltinBootstrap:
    async def test_initialize_builtin_mcp_servers_creates_missing_rows(self, monkeypatch, tmp_path):
        from langbot.pkg.local_connectors.service import LocalConnectorsService

        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
        ap = SimpleNamespace()
        ap.persistence_mgr = SimpleNamespace()
        ap.persistence_mgr.execute_async = AsyncMock(
            side_effect=[
                Mock(all=Mock(return_value=[])),
                Mock(),
                Mock(),
                Mock(),
            ]
        )
        ap.logger = Mock()

        service = LocalConnectorsService(ap)

        created = await service.initialize_builtin_mcp_servers()

        assert created == ["wechat-local", "wxwork-local"]

    async def test_initialize_builtin_mcp_servers_backfills_existing_row(self, monkeypatch, tmp_path):
        from langbot.pkg.local_connectors.service import LocalConnectorsService

        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
        ap = SimpleNamespace()
        ap.persistence_mgr = SimpleNamespace()
        existing = SimpleNamespace(
            uuid="legacy-uuid",
            name="微信解密",
            mode="remote",
            enable=False,
            extra_args={"url": "http://127.0.0.1:5680/mcp"},
            builtin=False,
            locked=False,
            managed_by=None,
            connector_id=None,
        )
        ap.persistence_mgr.execute_async = AsyncMock(
            side_effect=[
                Mock(all=Mock(return_value=[existing])),
                Mock(),
                Mock(),
                Mock(),
            ]
        )
        ap.logger = Mock()

        service = LocalConnectorsService(ap)

        created = await service.initialize_builtin_mcp_servers()

        assert created == ["wxwork-local"]


class TestLocalConnectorsStatus:
    async def test_get_connector_status_returns_unsupported_on_non_windows(self, monkeypatch, tmp_path):
        from langbot.pkg.local_connectors import schemas
        from langbot.pkg.local_connectors.service import LocalConnectorsService

        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
        ap = SimpleNamespace()
        service = LocalConnectorsService(ap)
        monkeypatch.setattr(service, "_platform_supported", lambda: False)

        status = await service.get_connector_status("wechat-local")

        assert status["status"] == schemas.CONNECTOR_STATUS_UNSUPPORTED
        assert status["last_error_code"] == "UNSUPPORTED_PLATFORM"
        assert status["worker"]["owned"] is False

    async def test_get_connector_status_marks_configured_but_not_running_as_stopped(self, monkeypatch, tmp_path):
        from langbot.pkg.local_connectors import schemas
        from langbot.pkg.local_connectors.service import LocalConnectorsService

        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
        ap = SimpleNamespace()
        service = LocalConnectorsService(ap)
        monkeypatch.setattr(service, "_platform_supported", lambda: True)
        service.repository.save_state(
            "wechat-local",
            {
                "connector_id": "wechat-local",
                "name": "微信解密",
                "status": schemas.CONNECTOR_STATUS_CONNECTED,
                "db_dir": r"C:\wechat\db_storage",
                "keys_file": r"C:\wechat\all_keys.json",
                "decrypted_dir": r"C:\wechat\decrypted",
            },
        )

        status = await service.get_connector_status("wechat-local")

        assert status["status"] == schemas.CONNECTOR_STATUS_STOPPED
        assert status["worker"]["owned"] is False

    async def test_get_connector_status_reports_stopped_when_monitor_disabled_and_runtime_state_is_stale(
        self, monkeypatch, tmp_path
    ):
        from langbot.pkg.local_connectors.service import LocalConnectorsService

        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
        ap = SimpleNamespace()
        service = LocalConnectorsService(ap)
        monkeypatch.setattr(service, "_platform_supported", lambda: True)
        service.repository.save_state(
            "wxwork-local",
            {
                "connector_id": "wxwork-local",
                "name": "WXWork",
                "status": "connected",
                "db_dir": r"C:\wxwork\db_storage",
                "keys_file": r"C:\wxwork\wxwork_keys.json",
                "decrypted_dir": r"C:\wxwork\decrypted",
                "monitor_enabled": False,
            },
        )
        service.repository.read_monitor_runtime_info = Mock(
            return_value={"running_status": "running", "warmup_completed": "true"}
        )

        status = await service.get_connector_status("wxwork-local")

        assert status["monitor"]["enabled"] is False
        assert status["monitor"]["owned"] is False
        assert status["monitor"]["running_status"] == "stopped"

    async def test_get_connector_status_reports_starting_when_monitor_enabled_but_process_not_owned(
        self, monkeypatch, tmp_path
    ):
        from langbot.pkg.local_connectors.service import LocalConnectorsService

        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
        ap = SimpleNamespace()
        service = LocalConnectorsService(ap)
        monkeypatch.setattr(service, "_platform_supported", lambda: True)
        service.repository.save_state(
            "wxwork-local",
            {
                "connector_id": "wxwork-local",
                "name": "WXWork",
                "status": "connected",
                "db_dir": r"C:\wxwork\db_storage",
                "keys_file": r"C:\wxwork\wxwork_keys.json",
                "decrypted_dir": r"C:\wxwork\decrypted",
                "monitor_enabled": True,
            },
        )
        service.repository.read_monitor_runtime_info = Mock(
            return_value={"running_status": "running", "warmup_completed": "true"}
        )

        status = await service.get_connector_status("wxwork-local")

        assert status["monitor"]["enabled"] is True
        assert status["monitor"]["owned"] is False
        assert status["monitor"]["running_status"] == "starting"


class TestLocalConnectorsSetupErrors:
    async def test_run_setup_job_marks_client_not_running_failed(self, monkeypatch, tmp_path):
        from langbot.pkg.local_connectors import schemas
        from langbot.pkg.local_connectors.service import LocalConnectorsService

        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
        ap = SimpleNamespace()
        service = LocalConnectorsService(ap)
        monkeypatch.setattr(service, "_platform_supported", lambda: True)
        service.detect_connector = AsyncMock(
            return_value={
                "status": schemas.CONNECTOR_STATUS_CLIENT_NOT_RUNNING,
                "last_error_code": "CLIENT_NOT_RUNNING",
                "last_error_message": "Client is not running",
            }
        )

        job = service.job_store.create_job("wechat-local")
        await service._run_setup_job(job)

        saved_job = service.get_job(job["job_id"])
        state = service.repository.load_state("wechat-local")
        assert saved_job["status"] == schemas.JOB_STATUS_FAILED
        assert saved_job["error_code"] == "CLIENT_NOT_RUNNING"
        assert state["status"] == schemas.CONNECTOR_STATUS_CLIENT_NOT_RUNNING

    async def test_run_setup_job_marks_uac_cancelled_failed(self, monkeypatch, tmp_path):
        from langbot.pkg.local_connectors import schemas
        from langbot.pkg.local_connectors.service import LocalConnectorsService

        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
        ap = SimpleNamespace()
        service = LocalConnectorsService(ap)
        monkeypatch.setattr(service, "_platform_supported", lambda: True)
        service.detect_connector = AsyncMock(return_value={"status": schemas.JOB_STAGE_DETECTING})

        fake_connector = SimpleNamespace(
            connector_id="wechat-local",
            cli_connector_name="wechat",
            expected_tool_names=("get_recent_sessions",),
            port=5680,
            resolve_python_executable=lambda: r"C:\repo\bot\python.exe",
            resolve_decrypt_dir=lambda: tmp_path,
            resolve_entrypoint=lambda name: tmp_path / name,
            run_cli=AsyncMock(),
        )
        service._connectors["wechat-local"] = fake_connector

        monkeypatch.setattr(
            "langbot.pkg.local_connectors.service.uac_helper.run_elevated_extract",
            AsyncMock(
                return_value={
                    "ok": False,
                    "error_code": "UAC_CANCELLED",
                    "error_message": "UAC was cancelled",
                }
            ),
        )

        job = service.job_store.create_job("wechat-local")
        await service._run_setup_job(job)

        saved_job = service.get_job(job["job_id"])
        state = service.repository.load_state("wechat-local")
        assert saved_job["status"] == schemas.JOB_STATUS_FAILED
        assert saved_job["error_code"] == "UAC_CANCELLED"
        assert state["status"] == schemas.CONNECTOR_STATUS_PERMISSION_REQUIRED

    async def test_run_setup_job_marks_port_in_use_failed(self, monkeypatch, tmp_path):
        from langbot.pkg.local_connectors import schemas
        from langbot.pkg.local_connectors.process_manager import PortInUseError
        from langbot.pkg.local_connectors.service import LocalConnectorsService

        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
        ap = SimpleNamespace()
        service = LocalConnectorsService(ap)
        monkeypatch.setattr(service, "_platform_supported", lambda: True)
        service.detect_connector = AsyncMock(return_value={"status": schemas.JOB_STAGE_DETECTING})

        fake_connector = SimpleNamespace(
            connector_id="wechat-local",
            cli_connector_name="wechat",
            expected_tool_names=("get_recent_sessions",),
            port=5680,
            resolve_python_executable=lambda: r"C:\repo\bot\python.exe",
            resolve_decrypt_dir=lambda: tmp_path,
            resolve_entrypoint=lambda name: tmp_path / name,
            run_cli=AsyncMock(return_value={"ok": True, "decrypted_dir": str(tmp_path / "decrypted")}),
        )
        service._connectors["wechat-local"] = fake_connector

        monkeypatch.setattr(
            "langbot.pkg.local_connectors.service.uac_helper.run_elevated_extract",
            AsyncMock(
                return_value={
                    "ok": True,
                    "keys_file": str(tmp_path / "secrets" / "all_keys.json"),
                }
            ),
        )
        service.process_manager.start = AsyncMock(side_effect=PortInUseError("Port 5680 is already in use"))

        job = service.job_store.create_job("wechat-local")
        await service._run_setup_job(job)

        saved_job = service.get_job(job["job_id"])
        state = service.repository.load_state("wechat-local")
        assert saved_job["status"] == schemas.JOB_STATUS_FAILED
        assert saved_job["error_code"] == "PORT_IN_USE"
        assert state["status"] == schemas.CONNECTOR_STATUS_PORT_IN_USE


class TestLocalConnectorsWorkerRuntime:
    async def test_start_worker_reconnects_enabled_runtime(self, monkeypatch, tmp_path):
        from langbot.pkg.local_connectors import schemas
        from langbot.pkg.local_connectors.service import LocalConnectorsService

        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
        ap = SimpleNamespace()
        ap.mcp_service = SimpleNamespace()
        ap.tool_mgr = SimpleNamespace()
        ap.mcp_service.get_mcp_server_by_connector_id = AsyncMock(
            return_value={"uuid": "builtin-uuid", "name": "微信解密", "enable": True}
        )
        service = LocalConnectorsService(ap)
        monkeypatch.setattr(service, "_platform_supported", lambda: True)
        service.runtime_bridge.wait_for_mcp_protocol_ready = AsyncMock(
            return_value={"tool_count": 17, "tools": [{"name": "get_recent_sessions"}]}
        )
        service.runtime_bridge.ensure_session_ready = AsyncMock(return_value={"tool_count": 17, "tools": []})
        service.process_manager.start = AsyncMock()
        service.repository.save_state(
            "wechat-local",
            {
                "connector_id": "wechat-local",
                "name": "微信解密",
                "db_dir": r"C:\wechat\db_storage",
                "keys_file": r"C:\wechat\all_keys.json",
                "decrypted_dir": r"C:\wechat\decrypted",
                "status": schemas.CONNECTOR_STATUS_STOPPED,
            },
        )

        state = await service.start_worker("wechat-local")

        service.process_manager.start.assert_awaited_once()
        service.runtime_bridge.ensure_session_ready.assert_awaited_once_with(
            "wechat-local",
            expected_tool_names=service._get_connector("wechat-local").expected_tool_names,
        )
        assert state["status"] == schemas.CONNECTOR_STATUS_CONNECTED
        assert state["tool_count"] == 17

    async def test_restore_configured_connectors_waits_for_session_ready_before_monitor(self, monkeypatch, tmp_path):
        from langbot.pkg.local_connectors.service import LocalConnectorsService

        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
        ap = SimpleNamespace()
        ap.tool_mgr = SimpleNamespace()
        ap.logger = Mock()
        ap.instance_config = SimpleNamespace(data={"api": {"port": 5300}})
        service = LocalConnectorsService(ap)
        monkeypatch.setattr(service, "_platform_supported", lambda: True)

        order: list[str] = []

        async def fake_start(connector, runtime_dir, role="mcp", env_overrides=None):
            order.append(f"start:{role}")
            if role == "mcp":
                return {"pid": 3001, "controller_pid": 3000, "port": 5681}
            return {"pid": 4001, "controller_pid": 4000, "port": None}

        async def fake_wait_protocol(url: str, **_kwargs):
            order.append(f"protocol:{url}")
            return {
                "tool_count": 5,
                "tools": [{"name": "wxwork_get_recent_sessions"}],
            }

        async def fake_session_ready(connector_id: str, **_kwargs):
            order.append(f"session:{connector_id}")
            return {
                "tool_count": 5,
                "tools": [{"name": "wxwork_get_recent_sessions"}],
            }

        service.process_manager.start = AsyncMock(side_effect=fake_start)
        service.runtime_bridge.wait_for_mcp_protocol_ready = AsyncMock(side_effect=fake_wait_protocol)
        service.runtime_bridge.ensure_session_ready = AsyncMock(side_effect=fake_session_ready)
        service.repository.read_monitor_runtime_info = Mock(return_value={"running_status": "running"})
        service.repository.save_state(
            "wxwork-local",
            {
                "connector_id": "wxwork-local",
                "name": "WXWork",
                "db_dir": r"C:\wxwork\db_storage",
                "keys_file": r"C:\wxwork\wxwork_keys.json",
                "decrypted_dir": r"C:\wxwork\decrypted",
                "monitor_enabled": True,
            },
        )

        await service.restore_configured_connectors()

        assert order == [
            "start:mcp",
            "protocol:http://127.0.0.1:5681/mcp",
            "session:wxwork-local",
            "start:mcp",
            "protocol:http://127.0.0.1:5681/mcp",
            "session:wxwork-local",
            "start:monitor",
        ]

    async def test_restore_configured_connectors_updates_builtin_tool_counts(self, monkeypatch, tmp_path):
        from langbot.pkg.local_connectors import schemas
        from langbot.pkg.local_connectors.service import LocalConnectorsService

        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
        ap = SimpleNamespace()
        ap.tool_mgr = SimpleNamespace()
        ap.logger = Mock()
        service = LocalConnectorsService(ap)
        monkeypatch.setattr(service, "_platform_supported", lambda: True)

        service.process_manager.start = AsyncMock(
            side_effect=[
                {"pid": 3001, "controller_pid": 3000, "port": 5680},
                {"pid": 3003, "controller_pid": 3002, "port": 5681},
            ]
        )

        async def fake_protocol(connector_id: str, **_kwargs):
            if connector_id == "wechat-local":
                return {"tool_count": 17, "tools": [{"name": "get_recent_sessions"}]}
            return {"tool_count": 5, "tools": [{"name": "wxwork_get_recent_sessions"}]}

        async def fake_session(connector_id: str, **_kwargs):
            return await fake_protocol(connector_id)

        service.runtime_bridge.wait_for_mcp_protocol_ready = AsyncMock(side_effect=fake_protocol)
        service.runtime_bridge.ensure_session_ready = AsyncMock(side_effect=fake_session)
        service.repository.save_state(
            "wechat-local",
            {
                "connector_id": "wechat-local",
                "name": "寰俊瑙ｅ瘑",
                "db_dir": r"C:\wechat\db_storage",
                "keys_file": r"C:\wechat\all_keys.json",
                "decrypted_dir": r"C:\wechat\decrypted",
                "status": schemas.CONNECTOR_STATUS_STOPPED,
            },
        )
        service.repository.save_state(
            "wxwork-local",
            {
                "connector_id": "wxwork-local",
                "name": "WXWork",
                "db_dir": r"C:\wxwork\db_storage",
                "keys_file": r"C:\wxwork\wxwork_keys.json",
                "decrypted_dir": r"C:\wxwork\decrypted",
                "status": schemas.CONNECTOR_STATUS_STOPPED,
            },
        )

        await service.restore_configured_connectors()

        assert service.repository.load_state("wechat-local")["tool_count"] == 17
        assert service.repository.load_state("wxwork-local")["tool_count"] == 5

    async def test_restore_and_manual_start_do_not_spawn_second_worker(self, monkeypatch, tmp_path):
        from langbot.pkg.local_connectors.service import LocalConnectorsService

        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
        ap = SimpleNamespace()
        ap.tool_mgr = SimpleNamespace()
        ap.logger = Mock()
        service = LocalConnectorsService(ap)
        monkeypatch.setattr(service, "_platform_supported", lambda: True)

        service.repository.save_state(
            "wechat-local",
            {
                "connector_id": "wechat-local",
                "name": "寰俊瑙ｅ瘑",
                "db_dir": r"C:\wechat\db_storage",
                "keys_file": r"C:\wechat\all_keys.json",
                "decrypted_dir": r"C:\wechat\decrypted",
            },
        )

        start_calls = 0

        async def fake_start(connector, *_args, **_kwargs):
            nonlocal start_calls
            existing = service.repository.load_process(connector.connector_id)
            if existing is not None:
                return existing
            start_calls += 1
            service.repository.save_process(
                connector.connector_id,
                {
                    "pid": 3001,
                    "created_at": 10.0,
                    "controller_pid": 3000,
                    "controller_created_at": 10.0,
                    "script_path": r"C:\repo\bot\vendor\wechat_decrypt\mcp_http_server.py",
                    "python_executable": r"C:\repo\bot\python.exe",
                },
            )
            await asyncio.sleep(0)
            return {"pid": 3001, "controller_pid": 3000, "port": 5680}

        service.process_manager.start = AsyncMock(side_effect=fake_start)
        service.runtime_bridge.wait_for_mcp_protocol_ready = AsyncMock(
            return_value={"tool_count": 17, "tools": [{"name": "get_recent_sessions"}]}
        )
        service.runtime_bridge.ensure_session_ready = AsyncMock(
            return_value={"tool_count": 17, "tools": [{"name": "get_recent_sessions"}]}
        )

        await asyncio.gather(
            service.restore_configured_connectors(),
            service.start_worker("wechat-local"),
        )

        assert start_calls == 1

    async def test_restore_configured_connectors_starts_only_configured(self, monkeypatch, tmp_path):
        from langbot.pkg.local_connectors.service import LocalConnectorsService

        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
        ap = SimpleNamespace()
        ap.tool_mgr = SimpleNamespace()
        ap.logger = Mock()
        service = LocalConnectorsService(ap)
        monkeypatch.setattr(service, "_platform_supported", lambda: True)
        service.start_worker = AsyncMock()
        service.repository.save_state(
            "wechat-local",
            {
                "connector_id": "wechat-local",
                "name": "微信解密",
                "db_dir": r"C:\wechat\db_storage",
                "keys_file": r"C:\wechat\all_keys.json",
                "decrypted_dir": r"C:\wechat\decrypted",
            },
        )

        await service.restore_configured_connectors()

        service.start_worker.assert_awaited_once_with("wechat-local")

    async def test_start_monitor_uses_runtime_metadata_and_enables_state(self, monkeypatch, tmp_path):
        from langbot.pkg.local_connectors.service import LocalConnectorsService

        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
        ap = SimpleNamespace()
        ap.instance_config = SimpleNamespace(data={"api": {"port": 5300}})
        service = LocalConnectorsService(ap)
        service.process_manager.start = AsyncMock()
        service.repository.save_state(
            "wxwork-local",
            {
                "connector_id": "wxwork-local",
                "name": "WXWork",
                "db_dir": r"C:\wxwork\db_storage",
                "keys_file": r"C:\wxwork\wxwork_keys.json",
                "decrypted_dir": r"C:\wxwork\decrypted",
            },
        )

        state = await service.start_monitor("wxwork-local")

        assert service.process_manager.start.await_count == 2
        _, runtime_dir = service.process_manager.start.await_args_list[-1].args[:2]
        assert runtime_dir.endswith("wxwork-local")
        assert state["monitor_enabled"] is True
        assert service.repository.load_internal_event_token("wxwork-local")

    async def test_restore_configured_connectors_restarts_enabled_monitor(self, monkeypatch, tmp_path):
        from langbot.pkg.local_connectors.service import LocalConnectorsService

        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
        ap = SimpleNamespace()
        ap.tool_mgr = SimpleNamespace()
        ap.logger = Mock()
        service = LocalConnectorsService(ap)
        monkeypatch.setattr(service, "_platform_supported", lambda: True)
        service.start_worker = AsyncMock()
        service.start_monitor = AsyncMock()
        service.repository.save_state(
            "wxwork-local",
            {
                "connector_id": "wxwork-local",
                "name": "WXWork",
                "db_dir": r"C:\wxwork\db_storage",
                "keys_file": r"C:\wxwork\wxwork_keys.json",
                "decrypted_dir": r"C:\wxwork\decrypted",
                "monitor_enabled": True,
            },
        )

        await service.restore_configured_connectors()

        service.start_worker.assert_awaited_once_with("wxwork-local")
        service.start_monitor.assert_awaited_once_with("wxwork-local", enable_on_success=True)
