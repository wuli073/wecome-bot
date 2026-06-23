from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..core import app


class LocalConnectorRuntimeBridge:
    def __init__(self, ap: "app.Application") -> None:
        self.ap = ap

    async def enable_and_refresh(self, connector_id: str) -> dict:
        server = await self.ap.mcp_service.get_mcp_server_by_connector_id(connector_id)
        if server is None:
            raise ValueError(f"MCP server not found for connector {connector_id}")

        if not server.get("enable", False):
            await self.ap.mcp_service.update_mcp_server(server["uuid"], {"enable": True})

        return await self.ap.mcp_service.refresh_mcp_server_runtime(server["name"])
