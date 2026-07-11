from __future__ import annotations

import sqlalchemy
import uuid
import asyncio

from ....core import app
from ....entity.persistence import mcp as persistence_mcp
from ....core import taskmgr
from ....provider.tools.loaders.mcp import RuntimeMCPSession, MCPSessionStatus


class MCPService:
    ap: app.Application

    def __init__(self, ap: app.Application) -> None:
        self.ap = ap

    def _is_builtin_server(self, server: object) -> bool:
        return bool(getattr(server, 'builtin', False) or getattr(server, 'connector_id', None))

    def _get_server_url(self, server: object) -> str | None:
        extra_args = getattr(server, 'extra_args', {}) or {}
        return extra_args.get('url')

    def _validate_builtin_update(self, old_server: object, server_data: dict) -> None:
        if not self._is_builtin_server(old_server):
            return

        if 'name' in server_data and server_data['name'] != old_server.name:
            raise ValueError('Built-in MCP server name cannot be changed')
        if 'mode' in server_data and server_data['mode'] != old_server.mode:
            raise ValueError('Built-in MCP server mode cannot be changed')
        if 'builtin' in server_data and not server_data['builtin']:
            raise ValueError('Built-in MCP server cannot be downgraded')
        if 'connector_id' in server_data and server_data['connector_id'] != getattr(old_server, 'connector_id', None):
            raise ValueError('Built-in MCP server connector_id cannot be changed')

        if 'extra_args' in server_data:
            new_url = (server_data.get('extra_args') or {}).get('url')
            old_url = self._get_server_url(old_server)
            if new_url is not None and old_url is not None and new_url != old_url:
                raise ValueError('Built-in MCP server URL cannot be changed')

    async def get_runtime_info(self, server_name: str) -> dict | None:
        session = self.ap.tool_mgr.mcp_tool_loader.get_session(server_name)
        if session:
            return session.get_runtime_info_dict()
        return None

    async def get_mcp_server_by_connector_id(self, connector_id: str) -> dict | None:
        result = await self.ap.persistence_mgr.execute_async(
            sqlalchemy.select(persistence_mcp.MCPServer).where(
                persistence_mcp.MCPServer.connector_id == connector_id
            )
        )
        server = result.first()
        if server is None:
            return None
        server_data = self.ap.persistence_mgr.serialize_model(persistence_mcp.MCPServer, server)
        server_data["runtime_info"] = await self.get_runtime_info(server_data["name"])
        return server_data

    async def refresh_mcp_server_runtime(self, server_name: str) -> dict:
        async def _load_and_start_fresh_session() -> RuntimeMCPSession:
            server_data = await self.get_mcp_server_by_name(server_name)
            if server_data is None:
                raise ValueError(f'Server not found: {server_name}')
            fresh_session = await self.ap.tool_mgr.mcp_tool_loader.load_mcp_server(server_config=server_data)
            self.ap.tool_mgr.mcp_tool_loader.sessions[server_name] = fresh_session
            await fresh_session.start()
            return fresh_session

        runtime_mcp_session: RuntimeMCPSession | None = None
        if self.ap.tool_mgr and self.ap.tool_mgr.mcp_tool_loader:
            runtime_mcp_session = self.ap.tool_mgr.mcp_tool_loader.get_session(server_name)
        if runtime_mcp_session is None:
            runtime_mcp_session = await _load_and_start_fresh_session()
            return runtime_mcp_session.get_runtime_info_dict()

        try:
            if runtime_mcp_session.status == MCPSessionStatus.ERROR:
                await runtime_mcp_session.start()
            else:
                await runtime_mcp_session.refresh()
        except Exception as exc:
            self.ap.logger.warning(
                f'MCP server {server_name} runtime session became stale, rebuilding session: {exc}'
            )
            await self.ap.tool_mgr.mcp_tool_loader.remove_mcp_server(server_name)
            runtime_mcp_session = await _load_and_start_fresh_session()

        return runtime_mcp_session.get_runtime_info_dict()

    async def get_mcp_servers(self, contain_runtime_info: bool = False) -> list[dict]:
        result = await self.ap.persistence_mgr.execute_async(sqlalchemy.select(persistence_mcp.MCPServer))

        servers = result.all()
        serialized_servers = [
            self.ap.persistence_mgr.serialize_model(persistence_mcp.MCPServer, server) for server in servers
        ]
        if contain_runtime_info:
            for server in serialized_servers:
                runtime_info = await self.get_runtime_info(server['name'])

                server['runtime_info'] = runtime_info if runtime_info else None

        return serialized_servers

    async def create_mcp_server(self, server_data: dict) -> str:
        # Check limitation (extensions = MCP servers + plugins)
        limitation = self.ap.instance_config.data.get('system', {}).get('limitation', {})
        max_extensions = limitation.get('max_extensions', -1)
        if max_extensions >= 0:
            existing_mcp_servers = await self.get_mcp_servers()
            plugins = await self.ap.plugin_connector.list_plugins()
            total_extensions = len(existing_mcp_servers) + len(plugins)
            if total_extensions >= max_extensions:
                raise ValueError(f'Maximum number of extensions ({max_extensions}) reached')

        server_data['uuid'] = str(uuid.uuid4())
        await self.ap.persistence_mgr.execute_async(sqlalchemy.insert(persistence_mcp.MCPServer).values(server_data))

        result = await self.ap.persistence_mgr.execute_async(
            sqlalchemy.select(persistence_mcp.MCPServer).where(persistence_mcp.MCPServer.uuid == server_data['uuid'])
        )
        server_entity = result.first()
        if server_entity:
            server_config = self.ap.persistence_mgr.serialize_model(persistence_mcp.MCPServer, server_entity)
            if self.ap.tool_mgr.mcp_tool_loader:
                task = asyncio.create_task(self.ap.tool_mgr.mcp_tool_loader.host_mcp_server(server_config))
                self.ap.tool_mgr.mcp_tool_loader._hosted_mcp_tasks.append(task)

        return server_data['uuid']

    async def get_mcp_server_by_name(self, server_name: str) -> dict | None:
        result = await self.ap.persistence_mgr.execute_async(
            sqlalchemy.select(persistence_mcp.MCPServer).where(persistence_mcp.MCPServer.name == server_name)
        )
        server = result.first()
        if server is None:
            return None

        runtime_info = await self.get_runtime_info(server.name)
        server_data = self.ap.persistence_mgr.serialize_model(persistence_mcp.MCPServer, server)
        server_data['runtime_info'] = runtime_info if runtime_info else None
        return server_data

    async def update_mcp_server(self, server_uuid: str, server_data: dict) -> None:
        result = await self.ap.persistence_mgr.execute_async(
            sqlalchemy.select(persistence_mcp.MCPServer).where(persistence_mcp.MCPServer.uuid == server_uuid)
        )
        old_server = result.first()
        old_server_name = old_server.name if old_server else None
        old_enable = old_server.enable if old_server else False

        if old_server is not None:
            self._validate_builtin_update(old_server, server_data)

        await self.ap.persistence_mgr.execute_async(
            sqlalchemy.update(persistence_mcp.MCPServer)
            .where(persistence_mcp.MCPServer.uuid == server_uuid)
            .values(server_data)
        )

        if self.ap.tool_mgr.mcp_tool_loader:
            new_enable = server_data.get('enable', False)

            need_remove = old_server_name and old_server_name in self.ap.tool_mgr.mcp_tool_loader.sessions

            if old_enable and not new_enable:
                if need_remove:
                    await self.ap.tool_mgr.mcp_tool_loader.remove_mcp_server(old_server_name)

            elif not old_enable and new_enable:
                result = await self.ap.persistence_mgr.execute_async(
                    sqlalchemy.select(persistence_mcp.MCPServer).where(persistence_mcp.MCPServer.uuid == server_uuid)
                )
                updated_server = result.first()
                if updated_server:
                    server_config = self.ap.persistence_mgr.serialize_model(persistence_mcp.MCPServer, updated_server)
                    task = asyncio.create_task(self.ap.tool_mgr.mcp_tool_loader.host_mcp_server(server_config))
                    self.ap.tool_mgr.mcp_tool_loader._hosted_mcp_tasks.append(task)

            elif old_enable and new_enable:
                if need_remove:
                    await self.ap.tool_mgr.mcp_tool_loader.remove_mcp_server(old_server_name)
                result = await self.ap.persistence_mgr.execute_async(
                    sqlalchemy.select(persistence_mcp.MCPServer).where(persistence_mcp.MCPServer.uuid == server_uuid)
                )
                updated_server = result.first()
                if updated_server:
                    server_config = self.ap.persistence_mgr.serialize_model(persistence_mcp.MCPServer, updated_server)
                    task = asyncio.create_task(self.ap.tool_mgr.mcp_tool_loader.host_mcp_server(server_config))
                    self.ap.tool_mgr.mcp_tool_loader._hosted_mcp_tasks.append(task)

    async def delete_mcp_server(self, server_uuid: str) -> None:
        result = await self.ap.persistence_mgr.execute_async(
            sqlalchemy.select(persistence_mcp.MCPServer).where(persistence_mcp.MCPServer.uuid == server_uuid)
        )
        server = result.first()
        server_name = server.name if server else None

        if server is not None and self._is_builtin_server(server):
            raise ValueError('Built-in MCP server cannot be deleted')

        await self.ap.persistence_mgr.execute_async(
            sqlalchemy.delete(persistence_mcp.MCPServer).where(persistence_mcp.MCPServer.uuid == server_uuid)
        )

        if server_name and self.ap.tool_mgr.mcp_tool_loader:
            if server_name in self.ap.tool_mgr.mcp_tool_loader.sessions:
                await self.ap.tool_mgr.mcp_tool_loader.remove_mcp_server(server_name)

    async def test_mcp_server(self, server_name: str, server_data: dict) -> int:
        """测试 MCP 服务器连接并返回任务 ID"""

        runtime_mcp_session: RuntimeMCPSession | None = None

        ctx = taskmgr.TaskContext.new()

        if server_name != '_':
            runtime_mcp_session = self.ap.tool_mgr.mcp_tool_loader.get_session(server_name)
            if runtime_mcp_session is None:
                raise ValueError(f'Server not found: {server_name}')

            persisted_session = runtime_mcp_session

            async def _refresh_and_report() -> None:
                if persisted_session.status == MCPSessionStatus.ERROR:
                    await persisted_session.start()
                else:
                    await persisted_session.refresh()
                # Surface the discovered tools so the config page can render them
                # even for an already-hosted server.
                ctx.metadata['runtime_info'] = persisted_session.get_runtime_info_dict()

            coroutine = _refresh_and_report()
        else:
            runtime_mcp_session = await self.ap.tool_mgr.mcp_tool_loader.load_mcp_server(server_config=server_data)

            # A transient test owns an isolated Box session. Always tear it down
            # after the test completes (success or failure) so it does not leak.
            test_session = runtime_mcp_session

            async def _run_and_cleanup() -> None:
                try:
                    await test_session.start()
                    # Capture the runtime info (status + discovered tools) BEFORE
                    # shutting the transient session down. The create/edit config
                    # page has no persisted server to reload from, so without this
                    # a successful test could only show "no tools found". The
                    # frontend reads ctx.metadata.runtime_info to render the tools.
                    ctx.metadata['runtime_info'] = test_session.get_runtime_info_dict()
                finally:
                    try:
                        await test_session.shutdown()
                    except Exception as exc:
                        self.ap.logger.warning(
                            f'Failed to tear down transient MCP test session '
                            f'{test_session.server_name}: {type(exc).__name__}: {exc}'
                        )

            coroutine = _run_and_cleanup()

        wrapper = self.ap.task_mgr.create_user_task(
            coroutine,
            kind='mcp-operation',
            name=f'mcp-test-{server_name}',
            label=f'Testing MCP server {server_name}',
            context=ctx,
        )
        return wrapper.id
