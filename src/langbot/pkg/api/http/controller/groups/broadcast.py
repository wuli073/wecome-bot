from __future__ import annotations

import quart

from .. import group
from .....broadcast.errors import (
    BROADCAST_GROUP_NAME_DUPLICATE,
    BROADCAST_GROUP_NAME_NOT_FOUND,
    BROADCAST_GROUP_RULE_DUPLICATE,
    BROADCAST_GROUP_RULE_NOT_FOUND,
    BROADCAST_GROUP_RULE_REGEX_INVALID,
    BROADCAST_SCOPE_REQUIRED,
    BROADCAST_TEMPLATE_CONTENT_REQUIRED,
    BROADCAST_TEMPLATE_NAME_DUPLICATE,
    BROADCAST_TEMPLATE_NOT_FOUND,
    BROADCAST_VARIABLE_PROFILE_INVALID,
    TEMPLATE_RENDER_INPUT_INVALID,
    BroadcastError,
)


@group.group_class('broadcast', '/api/v1/broadcast')
class BroadcastRouterGroup(group.RouterGroup):
    async def initialize(self) -> None:
        @self.route('/templates', methods=['GET', 'POST'], auth_type=group.AuthType.USER_TOKEN)
        async def templates() -> str:
            try:
                if quart.request.method == 'GET':
                    scope = await self.validate_scope(from_query=True)
                    data = await self.ap.broadcast_service.list_templates(scope)
                    return self.success(data=data)

                payload = await quart.request.get_json(silent=True) or {}
                scope = await self.validate_scope(from_query=False, payload=payload)
                data = await self.ap.broadcast_service.create_template(scope, payload)
                return self.success(data=data)
            except BroadcastError as exc:
                return self._broadcast_error_response(exc)

        @self.route('/templates/<int:template_id>', methods=['PUT', 'DELETE'], auth_type=group.AuthType.USER_TOKEN)
        async def template_detail(template_id: int) -> str:
            try:
                if quart.request.method == 'DELETE':
                    scope = await self.validate_scope(from_query=True)
                    data = await self.ap.broadcast_service.delete_template(template_id, scope)
                    return self.success(data=data)

                payload = await quart.request.get_json(silent=True) or {}
                scope = await self.validate_scope(from_query=False, payload=payload)
                data = await self.ap.broadcast_service.update_template(template_id, scope, payload)
                return self.success(data=data)
            except BroadcastError as exc:
                return self._broadcast_error_response(exc)

        @self.route('/templates/render', methods=['POST'], auth_type=group.AuthType.USER_TOKEN)
        async def render_template() -> str:
            payload = await quart.request.get_json(silent=True) or {}
            try:
                scope = await self.validate_scope(from_query=False, payload=payload)
                data = await self.ap.broadcast_service.render_template(scope, payload)
                return self.success(data=data)
            except BroadcastError as exc:
                return self._broadcast_error_response(exc)

        @self.route('/variable-profile', methods=['GET', 'PUT'], auth_type=group.AuthType.USER_TOKEN)
        async def variable_profile() -> str:
            try:
                if quart.request.method == 'GET':
                    scope = await self.validate_scope(from_query=True)
                    data = await self.ap.broadcast_service.get_variable_profile(scope)
                    return self.success(data=data)

                payload = await quart.request.get_json(silent=True) or {}
                scope = await self.validate_scope(from_query=False, payload=payload)
                data = await self.ap.broadcast_service.save_variable_profile(scope, payload)
                return self.success(data=data)
            except BroadcastError as exc:
                return self._broadcast_error_response(exc)

        @self.route('/group-rules', methods=['GET', 'POST'], auth_type=group.AuthType.USER_TOKEN)
        async def group_rules() -> str:
            try:
                if quart.request.method == 'GET':
                    scope = await self.validate_scope(from_query=True)
                    data = await self.ap.broadcast_service.list_group_rules(scope)
                    return self.success(data=data)

                payload = await quart.request.get_json(silent=True) or {}
                scope = await self.validate_scope(from_query=False, payload=payload)
                data = await self.ap.broadcast_service.create_group_rule(scope, payload)
                return self.success(data=data)
            except BroadcastError as exc:
                return self._broadcast_error_response(exc)

        @self.route('/group-rules/<int:rule_id>', methods=['PUT', 'DELETE'], auth_type=group.AuthType.USER_TOKEN)
        async def group_rule_detail(rule_id: int) -> str:
            try:
                if quart.request.method == 'DELETE':
                    scope = await self.validate_scope(from_query=True)
                    data = await self.ap.broadcast_service.delete_group_rule(rule_id, scope)
                    return self.success(data=data)

                payload = await quart.request.get_json(silent=True) or {}
                scope = await self.validate_scope(from_query=False, payload=payload)
                data = await self.ap.broadcast_service.update_group_rule(rule_id, scope, payload)
                return self.success(data=data)
            except BroadcastError as exc:
                return self._broadcast_error_response(exc)

        @self.route('/group-rules/match', methods=['POST'], auth_type=group.AuthType.USER_TOKEN)
        async def match_group_rule() -> str:
            payload = await quart.request.get_json(silent=True) or {}
            try:
                scope = await self.validate_scope(from_query=False, payload=payload)
                data = await self.ap.broadcast_service.match_group_rule(scope, payload)
                return self.success(data=data)
            except BroadcastError as exc:
                return self._broadcast_error_response(exc)

        @self.route('/group-names', methods=['GET', 'POST'], auth_type=group.AuthType.USER_TOKEN)
        async def group_names() -> str:
            try:
                if quart.request.method == 'GET':
                    scope = await self.validate_scope(from_query=True)
                    data = await self.ap.broadcast_service.list_group_names(scope)
                    return self.success(data=data)

                payload = await quart.request.get_json(silent=True) or {}
                scope = await self.validate_scope(from_query=False, payload=payload)
                data = await self.ap.broadcast_service.create_group_names(scope, payload)
                return self.success(data=data)
            except BroadcastError as exc:
                return self._broadcast_error_response(exc)

        @self.route('/group-names/<int:group_name_id>', methods=['DELETE'], auth_type=group.AuthType.USER_TOKEN)
        async def group_name_detail(group_name_id: int) -> str:
            try:
                scope = await self.validate_scope(from_query=True)
                data = await self.ap.broadcast_service.delete_group_name(group_name_id, scope)
                return self.success(data=data)
            except BroadcastError as exc:
                return self._broadcast_error_response(exc)

    async def validate_scope(
        self,
        *,
        from_query: bool,
        payload: dict | None = None,
    ) -> dict[str, str]:
        if from_query:
            scope = {
                'bot_uuid': str(quart.request.args.get('bot_uuid') or '').strip(),
                'connector_id': str(quart.request.args.get('connector_id') or '').strip(),
            }
        else:
            body = payload or {}
            scope = {
                'bot_uuid': str(body.get('bot_uuid') or '').strip(),
                'connector_id': str(body.get('connector_id') or '').strip(),
            }
        return await self.ap.broadcast_service.validate_scope(scope)

    def _broadcast_error_response(self, error: BroadcastError):
        response = quart.jsonify(
            {
                'code': -1,
                'msg': error.code,
                'message': error.message,
                'details': error.details,
            }
        )
        return response, self._broadcast_http_status(error.code)

    @staticmethod
    def _broadcast_http_status(code: str) -> int:
        if code in {
            BROADCAST_SCOPE_REQUIRED,
            BROADCAST_TEMPLATE_CONTENT_REQUIRED,
            BROADCAST_VARIABLE_PROFILE_INVALID,
            BROADCAST_GROUP_RULE_REGEX_INVALID,
            TEMPLATE_RENDER_INPUT_INVALID,
        }:
            return 400
        if code in {
            BROADCAST_TEMPLATE_NOT_FOUND,
            BROADCAST_GROUP_RULE_NOT_FOUND,
            BROADCAST_GROUP_NAME_NOT_FOUND,
        }:
            return 404
        if code in {
            BROADCAST_TEMPLATE_NAME_DUPLICATE,
            BROADCAST_GROUP_RULE_DUPLICATE,
            BROADCAST_GROUP_NAME_DUPLICATE,
        }:
            return 409
        return 400
