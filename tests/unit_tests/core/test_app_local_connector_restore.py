from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest


pytestmark = pytest.mark.asyncio


async def test_application_run_schedules_local_connector_restore():
    from langbot.pkg.core.app import Application

    app = Application()
    app.plugin_connector = SimpleNamespace(initialize_plugins=AsyncMock())
    app.local_connectors_service = SimpleNamespace(restore_configured_connectors=AsyncMock())
    app.platform_mgr = SimpleNamespace(run=AsyncMock())
    app.ctrl = SimpleNamespace(run=AsyncMock())
    app.http_ctrl = SimpleNamespace(run=AsyncMock())
    app.task_mgr = SimpleNamespace(create_task=Mock(), wait_all=AsyncMock(side_effect=asyncio.CancelledError()))
    app.telemetry = None
    app.instance_config = SimpleNamespace(data={"monitoring": {"auto_cleanup": {"enabled": False}}, "storage": {"cleanup": {"enabled": False}}})
    app.monitoring_service = None
    app.maintenance_service = None
    app.logger = Mock()
    app.print_web_access_info = AsyncMock()

    await app.run()

    scheduled = [call.kwargs["name"] for call in app.task_mgr.create_task.call_args_list]
    assert "local-connector-restore" in scheduled
