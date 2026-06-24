from __future__ import annotations

import asyncio
from contextlib import AsyncExitStack
from typing import TYPE_CHECKING

import httpx
from mcp import ClientSession
from mcp.client.sse import sse_client
from mcp.client.streamable_http import streamable_http_client

if TYPE_CHECKING:
    from ..core import app


class LocalConnectorRuntimeBridge:
    _DEFAULT_PROTOCOL_TIMEOUT_SECONDS = 45.0
    _DEFAULT_POLL_INTERVAL_SECONDS = 0.5

    def __init__(self, ap: "app.Application") -> None:
        self.ap = ap

    async def enable_and_refresh(self, connector_id: str) -> dict:
        server = await self.ap.mcp_service.get_mcp_server_by_connector_id(connector_id)
        if server is None:
            raise ValueError(f"MCP server not found for connector {connector_id}")

        if not server.get("enable", False):
            await self.ap.mcp_service.update_mcp_server(server["uuid"], {"enable": True})

        return await self.ap.mcp_service.refresh_mcp_server_runtime(server["name"])

    async def ensure_session_ready(
        self,
        connector_id: str,
        *,
        expected_tool_names: tuple[str, ...] = (),
        retry_delays: tuple[float, ...] = (0.0, 1.0, 2.0, 4.0),
    ) -> dict | None:
        server = await self.ap.mcp_service.get_mcp_server_by_connector_id(connector_id)
        if server is None:
            raise ValueError(f"MCP server not found for connector {connector_id}")
        if not server.get("enable", False):
            return None

        last_error: Exception | None = None
        for delay in retry_delays:
            if delay > 0:
                await asyncio.sleep(delay)
            try:
                runtime_info = await self.enable_and_refresh(connector_id)
                self._validate_expected_tools(runtime_info, expected_tool_names)
                return runtime_info
            except Exception as exc:  # pragma: no cover - exercised via retry behavior
                last_error = exc

        if last_error is not None:
            raise last_error
        raise RuntimeError(f"Failed to ready MCP session for connector {connector_id}")

    async def wait_for_mcp_protocol_ready(
        self,
        url: str,
        *,
        expected_tool_names: tuple[str, ...] = (),
        timeout_seconds: float | None = None,
        poll_interval_seconds: float | None = None,
    ) -> dict:
        timeout = timeout_seconds if timeout_seconds is not None else self._DEFAULT_PROTOCOL_TIMEOUT_SECONDS
        poll_interval = (
            poll_interval_seconds if poll_interval_seconds is not None else self._DEFAULT_POLL_INTERVAL_SECONDS
        )
        deadline = asyncio.get_running_loop().time() + timeout
        last_error: Exception | None = None

        while True:
            try:
                runtime_info = await self._probe_mcp_protocol(url, timeout_seconds=min(10.0, timeout))
                self._validate_expected_tools(runtime_info, expected_tool_names)
                return runtime_info
            except Exception as exc:
                last_error = exc
                if asyncio.get_running_loop().time() >= deadline:
                    break
                await asyncio.sleep(poll_interval)

        if last_error is not None:
            raise TimeoutError(f"MCP protocol was not ready for {url}: {last_error}") from last_error
        raise TimeoutError(f"MCP protocol was not ready for {url}")

    async def _probe_mcp_protocol(self, url: str, timeout_seconds: float) -> dict:
        try:
            return await self._probe_streamable_http(url, timeout_seconds)
        except Exception as streamable_error:
            logger = getattr(self.ap, "logger", None)
            if logger is not None:
                logger.debug(f"Builtin MCP probe fallback for {url}: {streamable_error}")
            return await self._probe_sse(url, timeout_seconds)

    async def _probe_streamable_http(self, url: str, timeout_seconds: float) -> dict:
        async with AsyncExitStack() as stack:
            transport = await stack.enter_async_context(
                streamable_http_client(
                    url,
                    http_client=httpx.AsyncClient(
                        timeout=timeout_seconds,
                        follow_redirects=True,
                    ),
                )
            )
            read, write, _ = transport
            session = await stack.enter_async_context(ClientSession(read, write))
            await session.initialize()
            tools = await session.list_tools()
            return self._serialize_tools_result(tools)

    async def _probe_sse(self, url: str, timeout_seconds: float) -> dict:
        async with AsyncExitStack() as stack:
            transport = await stack.enter_async_context(
                sse_client(
                    url,
                    timeout=timeout_seconds,
                    sse_read_timeout=timeout_seconds,
                )
            )
            read, write = transport
            session = await stack.enter_async_context(ClientSession(read, write))
            await session.initialize()
            tools = await session.list_tools()
            return self._serialize_tools_result(tools)

    @staticmethod
    def _serialize_tools_result(tools_result: object) -> dict:
        tools = getattr(tools_result, "tools", []) or []
        return {
            "tool_count": len(tools),
            "tools": [
                {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.inputSchema,
                }
                for tool in tools
            ],
        }

    @staticmethod
    def _validate_expected_tools(runtime_info: dict, expected_tool_names: tuple[str, ...]) -> None:
        if not expected_tool_names:
            return
        tool_names = {tool.get("name") for tool in runtime_info.get("tools", [])}
        missing = [name for name in expected_tool_names if name not in tool_names]
        if missing:
            raise RuntimeError(f"Expected MCP tools were not exposed yet: {', '.join(missing)}")
