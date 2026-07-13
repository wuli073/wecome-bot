from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest


pytestmark = pytest.mark.asyncio


async def test_runtime_bridge_enables_server_before_refresh():
    from langbot.pkg.local_connectors.runtime_bridge import LocalConnectorRuntimeBridge

    ap = SimpleNamespace()
    ap.mcp_service = SimpleNamespace()
    ap.mcp_service.get_mcp_server_by_connector_id = AsyncMock(
        return_value={"uuid": "uuid-1", "name": "微信解密", "enable": False}
    )
    ap.mcp_service.update_mcp_server = AsyncMock()
    ap.mcp_service.refresh_mcp_server_runtime = AsyncMock(
        return_value={"tool_count": 17, "tools": []}
    )

    bridge = LocalConnectorRuntimeBridge(ap)
    result = await bridge.enable_and_refresh("wechat-local")

    ap.mcp_service.update_mcp_server.assert_awaited_once_with("uuid-1", {"enable": True})
    ap.mcp_service.refresh_mcp_server_runtime.assert_awaited_once_with("微信解密")
    assert result["tool_count"] == 17


async def test_runtime_bridge_raises_when_builtin_server_missing():
    from langbot.pkg.local_connectors.runtime_bridge import LocalConnectorRuntimeBridge

    ap = SimpleNamespace()
    ap.mcp_service = SimpleNamespace()
    ap.mcp_service.get_mcp_server_by_connector_id = AsyncMock(return_value=None)

    bridge = LocalConnectorRuntimeBridge(ap)

    with pytest.raises(ValueError, match="MCP server not found"):
        await bridge.enable_and_refresh("wechat-local")


async def test_runtime_bridge_waits_until_protocol_exposes_expected_tools():
    from langbot.pkg.local_connectors.runtime_bridge import LocalConnectorRuntimeBridge

    ap = SimpleNamespace()
    ap.logger = SimpleNamespace(debug=lambda *_args, **_kwargs: None)

    bridge = LocalConnectorRuntimeBridge(ap)

    attempts = []

    async def fake_probe(url: str, timeout_seconds: float):
        attempts.append((url, timeout_seconds))
        if len(attempts) == 1:
            raise RuntimeError("worker not ready")
        if len(attempts) == 2:
            return {"tool_count": 1, "tools": [{"name": "partial_tool"}]}
        return {
            "tool_count": 2,
            "tools": [
                {"name": "expected_tool"},
                {"name": "second_tool"},
            ],
        }

    bridge._probe_mcp_protocol = fake_probe

    result = await bridge.wait_for_mcp_protocol_ready(
        "http://127.0.0.1:5680/mcp",
        expected_tool_names=("expected_tool",),
        timeout_seconds=1.0,
        poll_interval_seconds=0.0,
    )

    assert len(attempts) == 3
    assert result["tool_count"] == 2


async def test_runtime_bridge_ensure_session_ready_retries_after_initial_failure():
    from langbot.pkg.local_connectors.runtime_bridge import LocalConnectorRuntimeBridge

    ap = SimpleNamespace()
    ap.logger = SimpleNamespace(debug=lambda *_args, **_kwargs: None)
    ap.mcp_service = SimpleNamespace()
    ap.mcp_service.get_mcp_server_by_connector_id = AsyncMock(
        return_value={"uuid": "uuid-1", "name": "寰俊瑙ｅ瘑", "enable": True}
    )

    bridge = LocalConnectorRuntimeBridge(ap)

    attempts = 0

    async def fake_enable_and_refresh(connector_id: str):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("Connection timeout after 30 seconds")
        return {
            "tool_count": 17,
            "tools": [{"name": "get_recent_sessions"}],
        }

    bridge.enable_and_refresh = fake_enable_and_refresh

    result = await bridge.ensure_session_ready(
        "wechat-local",
        expected_tool_names=("get_recent_sessions",),
        retry_delays=(0.0, 0.0),
    )

    assert attempts == 2
    assert result["tool_count"] == 17
