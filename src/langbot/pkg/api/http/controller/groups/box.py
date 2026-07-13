from __future__ import annotations

from .. import group


@group.group_class('box', '/api/v1/box')
class BoxRouterGroup(group.RouterGroup):
    async def initialize(self) -> None:
        @self.route('/status', methods=['GET'], auth_type=group.AuthType.USER_TOKEN)
        async def _() -> str:
            box_service = self.require_optional_service('box_service')
            if isinstance(box_service, tuple):
                return box_service
            status = await box_service.get_status()
            return self.success(data=status)

        @self.route('/sessions', methods=['GET'], auth_type=group.AuthType.USER_TOKEN)
        async def _() -> str:
            box_service = self.require_optional_service('box_service')
            if isinstance(box_service, tuple):
                return box_service
            sessions = await box_service.get_sessions()
            return self.success(data=sessions)

        @self.route('/errors', methods=['GET'], auth_type=group.AuthType.USER_TOKEN)
        async def _() -> str:
            box_service = self.require_optional_service('box_service')
            if isinstance(box_service, tuple):
                return box_service
            errors = box_service.get_recent_errors()
            return self.success(data=errors)
