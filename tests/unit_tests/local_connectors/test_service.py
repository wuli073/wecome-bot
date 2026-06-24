from __future__ import annotations

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
            resolve_python_executable=lambda: r"C:\repo\wechat-decrypt\.venv\Scripts\python.exe",
            resolve_decrypt_dir=lambda: tmp_path,
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
            resolve_python_executable=lambda: r"C:\repo\wechat-decrypt\.venv\Scripts\python.exe",
            resolve_decrypt_dir=lambda: tmp_path,
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
        ap.mcp_service.get_mcp_server_by_connector_id = AsyncMock(
            return_value={"uuid": "builtin-uuid", "name": "微信解密", "enable": True}
        )
        service = LocalConnectorsService(ap)
        monkeypatch.setattr(service, "_platform_supported", lambda: True)
        service.runtime_bridge.enable_and_refresh = AsyncMock(return_value={"tool_count": 17, "tools": []})
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
        service.runtime_bridge.enable_and_refresh.assert_awaited_once_with("wechat-local")
        assert state["status"] == schemas.CONNECTOR_STATUS_CONNECTED
        assert state["tool_count"] == 17

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

        service.process_manager.start.assert_awaited_once()
        _, runtime_dir = service.process_manager.start.await_args.args[:2]
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
