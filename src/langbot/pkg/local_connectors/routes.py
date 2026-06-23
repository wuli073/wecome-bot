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

        @self.route("/jobs/<job_id>", methods=["GET"], auth_type=group.AuthType.USER_TOKEN)
        async def _(job_id: str) -> str:
            return self.success(data={"job": self.ap.local_connectors_service.get_job(job_id)})
