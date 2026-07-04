from __future__ import annotations

import quart
from werkzeug.exceptions import BadRequest

from .. import group
from .....broadcast.errors import (
    BROADCAST_DRAFT_BODY_EMPTY,
    BROADCAST_DRAFT_INVALID_CONFIRM_FORBIDDEN,
    BROADCAST_DRAFT_NOT_FOUND,
    BROADCAST_DRAFT_SCOPE_MISMATCH,
    BROADCAST_DRAFT_STALE_CONFIRM_FORBIDDEN,
    BROADCAST_DRAFT_STATUS_INVALID,
    BROADCAST_EXECUTION_BATCH_NOT_FOUND,
    BROADCAST_EXECUTION_BATCH_STATUS_INVALID,
    BROADCAST_EXECUTION_CONFIRMATION_EXPIRED,
    BROADCAST_EXECUTION_CONFIRMATION_INVALID,
    BROADCAST_EXECUTION_CONFIRMATION_REQUIRED,
    BROADCAST_EXECUTION_DRAFT_LIMIT_EXCEEDED,
    BROADCAST_EXECUTION_DRAFT_NOT_READY,
    BROADCAST_EXECUTION_DRAFT_STALE,
    BROADCAST_EXECUTION_MODE_INVALID,
    BROADCAST_EXECUTION_SEND_DISABLED,
    BROADCAST_EXECUTION_SCOPE_MISMATCH,
    BROADCAST_EXECUTION_TASK_NOT_FOUND,
    BROADCAST_EXECUTION_TASK_STATUS_INVALID,
    BROADCAST_IMPORT_FIELDS_MISSING,
    BROADCAST_IMPORT_FILE_INVALID,
    BROADCAST_IMPORT_GROUP_FIELD_REQUIRED,
    BROADCAST_IMPORT_NOT_FOUND,
    BROADCAST_IMPORT_READY_DRAFT_EXISTS,
    BROADCAST_IMPORT_REMATCH_FIELDS_MISSING,
    BROADCAST_IMPORT_VARIABLE_PROFILE_REQUIRED,
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

        @self.route('/imports', methods=['GET', 'POST'], auth_type=group.AuthType.USER_TOKEN)
        async def imports() -> str:
            try:
                if quart.request.method == 'GET':
                    scope = await self.validate_scope(from_query=True)
                    data = await self.ap.broadcast_service.list_import_batches(scope)
                    return self.success(data=data)

                form = await quart.request.form
                files = await quart.request.files
                scope = await self.ap.broadcast_service.validate_scope(
                    {
                        'bot_uuid': str(form.get('bot_uuid') or '').strip(),
                        'connector_id': str(form.get('connector_id') or '').strip(),
                    }
                )
                file = files.get('file')
                payload = self._build_upload_file_payload(file)
                data = await self.ap.broadcast_service.upload_import(scope, payload)
                return self.success(data=data)
            except BadRequest:
                return self._broadcast_error_response(
                    BroadcastError(
                        BROADCAST_IMPORT_FILE_INVALID,
                        '导入请求格式无效，请重新选择 CSV/XLSX 文件后重试。',
                    )
                )
            except BroadcastError as exc:
                return self._broadcast_error_response(exc)

        @self.route('/group-names/sync', methods=['POST'], auth_type=group.AuthType.USER_TOKEN)
        async def sync_group_names() -> str:
            try:
                scope = await self.validate_scope(from_query=True)
                data = await self.ap.broadcast_service.sync_group_names_from_conversations(scope)
                return self.success(data=data)
            except BroadcastError as exc:
                return self._broadcast_error_response(exc)

        @self.route('/imports/<int:import_id>', methods=['GET', 'DELETE'], auth_type=group.AuthType.USER_TOKEN)
        async def import_detail(import_id: int) -> str:
            try:
                if quart.request.method == 'DELETE':
                    scope = await self.validate_scope(from_query=True)
                    data = await self.ap.broadcast_service.delete_import(import_id, scope)
                    return self.success(data=data)

                scope = await self.validate_scope(from_query=True)
                filters = {
                    'match_status': str(quart.request.args.get('match_status') or '').strip() or None,
                    'keyword': str(quart.request.args.get('keyword') or '').strip() or None,
                    'page': int(quart.request.args.get('page')) if quart.request.args.get('page') else None,
                    'page_size': int(quart.request.args.get('page_size'))
                    if quart.request.args.get('page_size')
                    else None,
                }
                data = await self.ap.broadcast_service.get_import_detail(import_id, scope, filters)
                return self.success(data=data)
            except BroadcastError as exc:
                return self._broadcast_error_response(exc)

        @self.route('/imports/<int:import_id>/rematch', methods=['POST'], auth_type=group.AuthType.USER_TOKEN)
        async def rematch_import(import_id: int) -> str:
            payload = await quart.request.get_json(silent=True) or {}
            try:
                scope = await self.validate_scope(from_query=False, payload=payload)
                data = await self.ap.broadcast_service.rematch_import(import_id, scope)
                return self.success(data=data)
            except BroadcastError as exc:
                return self._broadcast_error_response(exc)

        @self.route('/imports/<int:import_id>/generate-drafts', methods=['POST'], auth_type=group.AuthType.USER_TOKEN)
        async def generate_import_drafts(import_id: int) -> str:
            payload = await quart.request.get_json(silent=True) or {}
            try:
                scope = await self.validate_scope(from_query=False, payload=payload)
                data = await self.ap.broadcast_service.generate_import_drafts(import_id, scope, payload)
                return self.success(data=data)
            except BroadcastError as exc:
                return self._broadcast_error_response(exc)

        @self.route('/drafts', methods=['GET'], auth_type=group.AuthType.USER_TOKEN)
        async def drafts() -> str:
            try:
                scope = await self.validate_scope(from_query=True)
                filters = {
                    'import_batch_id': int(quart.request.args.get('import_batch_id'))
                    if quart.request.args.get('import_batch_id')
                    else None,
                    'status': str(quart.request.args.get('status') or '').strip() or None,
                    'keyword': str(quart.request.args.get('keyword') or '').strip() or None,
                }
                data = await self.ap.broadcast_service.list_drafts(scope, filters)
                return self.success(data=data)
            except BroadcastError as exc:
                return self._broadcast_error_response(exc)

        @self.route('/drafts/<int:draft_id>', methods=['GET', 'PUT'], auth_type=group.AuthType.USER_TOKEN)
        async def draft_detail(draft_id: int) -> str:
            try:
                if quart.request.method == 'GET':
                    scope = await self.validate_scope(from_query=True)
                    data = await self.ap.broadcast_service.get_draft_detail(draft_id, scope)
                    return self.success(data=data)

                payload = await quart.request.get_json(silent=True) or {}
                scope = await self.validate_scope(from_query=False, payload=payload)
                data = await self.ap.broadcast_service.update_draft_text(draft_id, scope, payload)
                return self.success(data=data)
            except BroadcastError as exc:
                return self._broadcast_error_response(exc)

        @self.route('/drafts/batch-status', methods=['POST'], auth_type=group.AuthType.USER_TOKEN)
        async def draft_batch_status() -> str:
            payload = await quart.request.get_json(silent=True) or {}
            try:
                scope = await self.validate_scope(from_query=False, payload=payload)
                data = await self.ap.broadcast_service.update_draft_statuses(scope, payload)
                return self.success(data=data)
            except BroadcastError as exc:
                return self._broadcast_error_response(exc)

        @self.route('/executions', methods=['GET', 'POST'], auth_type=group.AuthType.USER_TOKEN)
        async def executions() -> str:
            try:
                if quart.request.method == 'GET':
                    scope = await self.validate_scope(from_query=True)
                    data = await self.ap.broadcast_service.list_execution_batches(scope)
                    return self.success(data=data)

                payload = await quart.request.get_json(silent=True) or {}
                scope = await self.validate_scope(from_query=False, payload=payload)
                data = await self.ap.broadcast_service.create_execution_batch(scope, payload)
                return self.success(data=data)
            except BroadcastError as exc:
                return self._broadcast_error_response(exc)

        @self.route('/executions/<int:batch_id>', methods=['GET'], auth_type=group.AuthType.USER_TOKEN)
        async def execution_detail(batch_id: int) -> str:
            try:
                scope = await self.validate_scope(from_query=True)
                data = await self.ap.broadcast_service.get_execution_batch_detail(batch_id, scope)
                return self.success(data=data)
            except BroadcastError as exc:
                return self._broadcast_error_response(exc)

        @self.route('/executions/<int:batch_id>/start', methods=['POST'], auth_type=group.AuthType.USER_TOKEN)
        async def execution_batch_start(batch_id: int) -> str:
            payload = await quart.request.get_json(silent=True) or {}
            try:
                scope = await self.validate_scope(from_query=False, payload=payload)
                data = await self.ap.broadcast_service.start_execution_batch(batch_id, scope, payload)
                return self.success(data=data)
            except BroadcastError as exc:
                return self._broadcast_error_response(exc)

        @self.route('/executions/<int:batch_id>/pause', methods=['POST'], auth_type=group.AuthType.USER_TOKEN)
        async def execution_batch_pause(batch_id: int) -> str:
            payload = await quart.request.get_json(silent=True) or {}
            try:
                scope = await self.validate_scope(from_query=False, payload=payload)
                data = await self.ap.broadcast_service.pause_execution_batch(batch_id, scope, payload)
                return self.success(data=data)
            except BroadcastError as exc:
                return self._broadcast_error_response(exc)

        @self.route('/executions/<int:batch_id>/resume', methods=['POST'], auth_type=group.AuthType.USER_TOKEN)
        async def execution_batch_resume(batch_id: int) -> str:
            payload = await quart.request.get_json(silent=True) or {}
            try:
                scope = await self.validate_scope(from_query=False, payload=payload)
                data = await self.ap.broadcast_service.resume_execution_batch(batch_id, scope, payload)
                return self.success(data=data)
            except BroadcastError as exc:
                return self._broadcast_error_response(exc)

        @self.route('/executions/<int:batch_id>/cancel', methods=['POST'], auth_type=group.AuthType.USER_TOKEN)
        async def execution_batch_cancel(batch_id: int) -> str:
            payload = await quart.request.get_json(silent=True) or {}
            try:
                scope = await self.validate_scope(from_query=False, payload=payload)
                data = await self.ap.broadcast_service.cancel_execution_batch(batch_id, scope, payload)
                return self.success(data=data)
            except BroadcastError as exc:
                return self._broadcast_error_response(exc)

        @self.route('/execution-tasks/<int:task_id>', methods=['GET'], auth_type=group.AuthType.USER_TOKEN)
        async def execution_task_detail(task_id: int) -> str:
            try:
                scope = await self.validate_scope(from_query=True)
                data = await self.ap.broadcast_service.get_execution_task_detail(task_id, scope)
                return self.success(data=data)
            except BroadcastError as exc:
                return self._broadcast_error_response(exc)

        @self.route('/execution-tasks/<int:task_id>/attempts', methods=['GET'], auth_type=group.AuthType.USER_TOKEN)
        async def execution_task_attempts(task_id: int) -> str:
            try:
                scope = await self.validate_scope(from_query=True)
                data = await self.ap.broadcast_service.list_execution_attempts(task_id, scope)
                return self.success(data=data)
            except BroadcastError as exc:
                return self._broadcast_error_response(exc)

        @self.route('/execution-attempts/<int:attempt_id>', methods=['GET'], auth_type=group.AuthType.USER_TOKEN)
        async def execution_attempt_detail(attempt_id: int) -> str:
            try:
                scope = await self.validate_scope(from_query=True)
                data = await self.ap.broadcast_service.get_execution_attempt_detail(attempt_id, scope)
                return self.success(data=data)
            except BroadcastError as exc:
                return self._broadcast_error_response(exc)

        @self.route('/execution-attempts/<int:attempt_id>/evidence', methods=['GET'], auth_type=group.AuthType.USER_TOKEN)
        async def execution_attempt_evidence(attempt_id: int) -> str:
            try:
                scope = await self.validate_scope(from_query=True)
                data = await self.ap.broadcast_service.get_execution_evidence(attempt_id, scope)
                return self.success(data=data)
            except BroadcastError as exc:
                return self._broadcast_error_response(exc)

        @self.route('/execution-tasks/<int:task_id>/start', methods=['POST'], auth_type=group.AuthType.USER_TOKEN)
        async def execution_task_start(task_id: int) -> str:
            payload = await quart.request.get_json(silent=True) or {}
            try:
                scope = await self.validate_scope(from_query=False, payload=payload)
                data = await self.ap.broadcast_service.start_execution_task(task_id, scope, payload)
                return self.success(data=data)
            except BroadcastError as exc:
                return self._broadcast_error_response(exc)

        @self.route('/execution-tasks/<int:task_id>/cancel', methods=['POST'], auth_type=group.AuthType.USER_TOKEN)
        async def execution_task_cancel(task_id: int) -> str:
            payload = await quart.request.get_json(silent=True) or {}
            try:
                scope = await self.validate_scope(from_query=False, payload=payload)
                data = await self.ap.broadcast_service.cancel_execution_task(task_id, scope, payload)
                return self.success(data=data)
            except BroadcastError as exc:
                return self._broadcast_error_response(exc)

        @self.route('/execution-tasks/<int:task_id>/retry', methods=['POST'], auth_type=group.AuthType.USER_TOKEN)
        async def execution_task_retry(task_id: int) -> str:
            payload = await quart.request.get_json(silent=True) or {}
            try:
                scope = await self.validate_scope(from_query=False, payload=payload)
                data = await self.ap.broadcast_service.retry_execution_task(task_id, scope, payload)
                return self.success(data=data)
            except BroadcastError as exc:
                return self._broadcast_error_response(exc)

        @self.route('/execution-tasks/<int:task_id>/send', methods=['POST'], auth_type=group.AuthType.USER_TOKEN)
        async def execution_task_send(task_id: int) -> str:
            payload = await quart.request.get_json(silent=True) or {}
            try:
                scope = await self.validate_scope(from_query=False, payload=payload)
                data = await self.ap.broadcast_service.send_execution_task(task_id, scope, payload)
                return self.success(data=data)
            except BroadcastError as exc:
                return self._broadcast_error_response(exc)

        @self.route('/executors/capabilities', methods=['GET'], auth_type=group.AuthType.USER_TOKEN)
        async def executor_capabilities() -> str:
            try:
                scope = await self.validate_scope(from_query=True)
                data = await self.ap.broadcast_service.get_executor_capabilities(scope)
                return self.success(data=data)
            except BroadcastError as exc:
                return self._broadcast_error_response(exc)

        @self.route('/executors/health', methods=['GET'], auth_type=group.AuthType.USER_TOKEN)
        async def executor_health() -> str:
            try:
                scope = await self.validate_scope(from_query=True)
                data = await self.ap.broadcast_service.get_executor_health(scope)
                return self.success(data=data)
            except BroadcastError as exc:
                return self._broadcast_error_response(exc)

        @self.route('/send-confirmations', methods=['POST'], auth_type=group.AuthType.USER_TOKEN)
        async def send_confirmations() -> str:
            payload = await quart.request.get_json(silent=True) or {}
            try:
                scope = await self.validate_scope(from_query=False, payload=payload)
                data = await self.ap.broadcast_service.issue_send_confirmation(scope, payload)
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
            BROADCAST_IMPORT_FILE_INVALID,
            BROADCAST_IMPORT_VARIABLE_PROFILE_REQUIRED,
            BROADCAST_IMPORT_GROUP_FIELD_REQUIRED,
            BROADCAST_IMPORT_FIELDS_MISSING,
            BROADCAST_IMPORT_REMATCH_FIELDS_MISSING,
            BROADCAST_IMPORT_READY_DRAFT_EXISTS,
            BROADCAST_DRAFT_BODY_EMPTY,
            BROADCAST_DRAFT_STATUS_INVALID,
            BROADCAST_DRAFT_INVALID_CONFIRM_FORBIDDEN,
            BROADCAST_DRAFT_STALE_CONFIRM_FORBIDDEN,
            BROADCAST_DRAFT_SCOPE_MISMATCH,
            BROADCAST_EXECUTION_DRAFT_NOT_READY,
            BROADCAST_EXECUTION_DRAFT_STALE,
            BROADCAST_EXECUTION_SCOPE_MISMATCH,
            BROADCAST_EXECUTION_MODE_INVALID,
            BROADCAST_EXECUTION_DRAFT_LIMIT_EXCEEDED,
            BROADCAST_EXECUTION_BATCH_STATUS_INVALID,
            BROADCAST_EXECUTION_TASK_STATUS_INVALID,
            BROADCAST_EXECUTION_CONFIRMATION_REQUIRED,
            BROADCAST_EXECUTION_CONFIRMATION_INVALID,
            BROADCAST_EXECUTION_CONFIRMATION_EXPIRED,
            BROADCAST_EXECUTION_SEND_DISABLED,
            BROADCAST_TEMPLATE_CONTENT_REQUIRED,
            BROADCAST_VARIABLE_PROFILE_INVALID,
            BROADCAST_GROUP_RULE_REGEX_INVALID,
            TEMPLATE_RENDER_INPUT_INVALID,
        }:
            return 400
        if code in {
            BROADCAST_DRAFT_NOT_FOUND,
            BROADCAST_IMPORT_NOT_FOUND,
            BROADCAST_TEMPLATE_NOT_FOUND,
            BROADCAST_GROUP_RULE_NOT_FOUND,
            BROADCAST_GROUP_NAME_NOT_FOUND,
            BROADCAST_EXECUTION_BATCH_NOT_FOUND,
            BROADCAST_EXECUTION_TASK_NOT_FOUND,
        }:
            return 404
        if code in {
            BROADCAST_TEMPLATE_NAME_DUPLICATE,
            BROADCAST_GROUP_RULE_DUPLICATE,
            BROADCAST_GROUP_NAME_DUPLICATE,
        }:
            return 409
        return 400

    @staticmethod
    def _build_upload_file_payload(file) -> dict[str, bytes | str]:
        if file is None:
            return {
                'filename': '',
                'body': b'',
            }

        stream = getattr(file, 'stream', None)
        if stream is not None:
            seek = getattr(stream, 'seek', None)
            if callable(seek):
                seek(0)
            body = stream.read()
        else:
            read = getattr(file, 'read', None)
            body = read() if callable(read) else b''

        if body is None:
            body = b''
        if isinstance(body, str):
            body = body.encode('utf-8')

        return {
            'filename': getattr(file, 'filename', ''),
            'body': body,
        }
