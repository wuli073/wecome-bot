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
