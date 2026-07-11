from __future__ import annotations

import quart

from ..api.http.controller import group


@group.group_class("local_connectors", "/api/v1/local-connectors")
class LocalConnectorsRouterGroup(group.RouterGroup):
    async def initialize(self) -> None:
        @self.route("", methods=["GET"], auth_type=group.AuthType.USER_TOKEN)
        async def _() -> str:
            return self.success(data={"connectors": await self.ap.local_connectors_service.list_connectors()})

        @self.route("/<connector_id>/status", methods=["GET"], auth_type=group.AuthType.USER_TOKEN)
        async def _(connector_id: str) -> str:
            return self.success(data={"connector": await self.ap.local_connectors_service.get_connector_status(connector_id)})

        @self.route("/<connector_id>/detect", methods=["POST"], auth_type=group.AuthType.USER_TOKEN)
        async def _(connector_id: str) -> str:
            return self.success(data={"connector": await self.ap.local_connectors_service.detect_connector(connector_id)})

        @self.route("/<connector_id>/setup", methods=["POST"], auth_type=group.AuthType.USER_TOKEN)
        async def _(connector_id: str) -> str:
            return self.success(data=await self.ap.local_connectors_service.start_setup(connector_id))

        @self.route("/<connector_id>/refresh", methods=["POST"], auth_type=group.AuthType.USER_TOKEN)
        async def _(connector_id: str) -> str:
            return self.success(data={"connector": await self.ap.local_connectors_service.refresh_connector(connector_id)})

        @self.route("/<connector_id>/start", methods=["POST"], auth_type=group.AuthType.USER_TOKEN)
        async def _(connector_id: str) -> str:
            return self.success(data={"connector": await self.ap.local_connectors_service.start_worker(connector_id)})

        @self.route("/<connector_id>/stop", methods=["POST"], auth_type=group.AuthType.USER_TOKEN)
        async def _(connector_id: str) -> str:
            return self.success(data={"connector": await self.ap.local_connectors_service.stop_worker(connector_id)})

        @self.route("/<connector_id>/restart", methods=["POST"], auth_type=group.AuthType.USER_TOKEN)
        async def _(connector_id: str) -> str:
            return self.success(data={"connector": await self.ap.local_connectors_service.restart_worker(connector_id)})

        @self.route("/<connector_id>/logs", methods=["GET"], auth_type=group.AuthType.USER_TOKEN)
        async def _(connector_id: str) -> str:
            return self.success(data=self.ap.local_connectors_service.get_logs(connector_id))

        @self.route("/wxwork-local/monitor/status", methods=["GET"], auth_type=group.AuthType.USER_TOKEN)
        async def _() -> str:
            return self.success(data={"monitor": await self.ap.local_connectors_service.get_monitor_status("wxwork-local")})

        @self.route("/wxwork-local/monitor/start", methods=["POST"], auth_type=group.AuthType.USER_TOKEN)
        async def _() -> str:
            connector = await self.ap.local_connectors_service.start_monitor("wxwork-local")
            return self.success(data={"connector": connector})

        @self.route("/wxwork-local/monitor/stop", methods=["POST"], auth_type=group.AuthType.USER_TOKEN)
        async def _() -> str:
            connector = await self.ap.local_connectors_service.stop_monitor("wxwork-local")
            return self.success(data={"connector": connector})

        @self.route("/wxwork-local/monitor/restart", methods=["POST"], auth_type=group.AuthType.USER_TOKEN)
        async def _() -> str:
            connector = await self.ap.local_connectors_service.restart_monitor("wxwork-local")
            return self.success(data={"connector": connector})

        @self.route("/internal/events", methods=["POST"], auth_type=group.AuthType.NONE)
        async def _() -> str:
            if not self.ap.local_connectors_service.is_loopback_request(quart.request.remote_addr):
                return self.http_status(403, -1, "Local requests only")
            if (quart.request.content_length or 0) > 64 * 1024:
                return self.http_status(413, -1, "Payload too large")
            token = quart.request.headers.get("X-Wecome-Connector-Token", "")
            if not self.ap.local_connectors_service.validate_internal_event_token("wxwork-local", token):
                return self.http_status(401, -1, "Invalid connector token")
            payload = await quart.request.get_json(silent=True) or {}
            try:
                result = await self.ap.database_mode_service.ingest_internal_event(payload)
            except ValueError as exc:
                return self.http_status(400, -1, str(exc))
            response_data = {
                "accepted": result.accepted,
                "duplicate": result.duplicate,
                "event_id": result.event_id,
            }
            if result.timings is not None:
                response_data["timings"] = result.timings
            return self.success(data=response_data)

        @self.route("/jobs/<job_id>", methods=["GET"], auth_type=group.AuthType.USER_TOKEN)
        async def _(job_id: str) -> str:
            return self.success(data={"job": self.ap.local_connectors_service.get_job(job_id)})
