from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest


pytestmark = pytest.mark.asyncio


async def test_application_run_does_not_schedule_redundant_local_connector_restore():
    from langbot.pkg.core.app import Application
    from langbot.pkg.core import taskmgr as taskmgr_module

    app = Application()
    app.event_loop = asyncio.get_running_loop()
    app.plugin_connector = SimpleNamespace(initialize_plugins=AsyncMock())
    app.local_connectors_service = SimpleNamespace(restore_configured_connectors=AsyncMock())
    shutdown_gate = asyncio.Event()

    async def long_running():
        await shutdown_gate.wait()

    app.platform_mgr = SimpleNamespace(run=long_running)
    app.ctrl = SimpleNamespace(run=long_running)
    app.http_ctrl = SimpleNamespace(run=long_running, request_shutdown=Mock())
    app.task_mgr = taskmgr_module.AsyncTaskManager(app)
    app.telemetry = None
    app.instance_config = SimpleNamespace(
        data={
            "monitoring": {"auto_cleanup": {"enabled": False}},
            "storage": {"cleanup": {"enabled": False}},
            "desktop_automation": {"enabled": False},
            "system": {"task_retention": {"completed_limit": 200}},
            "api": {"port": 5300},
        }
    )
    app.monitoring_service = None
    app.maintenance_service = None
    app.broadcast_execution_worker = None
    app.desktop_automation_service = None
    app.logger = Mock()
    app.print_web_access_info = AsyncMock()
    app.dispose = Mock()

    run_task = asyncio.create_task(app.run())
    await asyncio.sleep(0)
    app.request_shutdown("test-finish")
    await asyncio.wait_for(run_task, timeout=5)

    scheduled = [wrapper.name for wrapper in app.task_mgr.tasks]
    assert "local-connector-restore" not in scheduled
