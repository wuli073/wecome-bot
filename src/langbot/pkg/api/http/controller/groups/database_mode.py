from __future__ import annotations

import quart

from .. import group


def _get_int_arg(name: str, default: int) -> int:
    raw = quart.request.args.get(name, default)
    return int(raw)


@group.group_class('database_mode', '/api/v1/database-mode')
class DatabaseModeRouterGroup(group.RouterGroup):
    async def initialize(self) -> None:
        @self.route('/conversations', methods=['GET'], auth_type=group.AuthType.USER_TOKEN)
        async def list_conversations() -> str:
            data = await self.ap.database_mode_service.list_conversations(
                status=quart.request.args.get('status'),
                keyword=quart.request.args.get('keyword', ''),
                page=_get_int_arg('page', 1),
                page_size=_get_int_arg('page_size', 20),
            )
            return self.success(data=data)

        @self.route('/conversations/<int:conversation_id>', methods=['GET'], auth_type=group.AuthType.USER_TOKEN)
        async def get_conversation(conversation_id: int) -> str:
            conversation = await self.ap.database_mode_service.get_conversation(conversation_id)
            if conversation is None:
                return self.http_status(404, -1, 'conversation not found')
            return self.success(data={'conversation': conversation})

        @self.route(
            '/conversations/<int:conversation_id>/messages',
            methods=['GET'],
            auth_type=group.AuthType.USER_TOKEN,
        )
        async def list_messages(conversation_id: int) -> str:
            data = await self.ap.database_mode_service.list_messages(
                conversation_id,
                status=quart.request.args.get('status'),
                page=_get_int_arg('page', 1),
                page_size=_get_int_arg('page_size', 50),
            )
            return self.success(data=data)

        @self.route(
            '/messages/<int:message_id>/generate-draft',
            methods=['POST'],
            auth_type=group.AuthType.USER_TOKEN,
        )
        async def generate_draft(message_id: int) -> str:
            message = await self.ap.database_mode_service.generate_draft(message_id)
            return self.success(data={'message': message})

        @self.route('/messages/<int:message_id>/draft', methods=['PUT'], auth_type=group.AuthType.USER_TOKEN)
        async def update_draft(message_id: int) -> str:
            payload = await quart.request.get_json(silent=True) or {}
            message = await self.ap.database_mode_service.update_draft(
                message_id,
                draft_text=str(payload.get('draft_text') or ''),
                draft_source=payload.get('draft_source'),
            )
            return self.success(data={'message': message})

        @self.route('/messages/<int:message_id>/process', methods=['POST'], auth_type=group.AuthType.USER_TOKEN)
        async def process_message(message_id: int) -> str:
            message = await self.ap.database_mode_service.process_message(message_id)
            return self.success(data={'message': message})

        @self.route('/messages/<int:message_id>/skip', methods=['POST'], auth_type=group.AuthType.USER_TOKEN)
        async def skip_message(message_id: int) -> str:
            message = await self.ap.database_mode_service.skip_message(message_id)
            return self.success(data={'message': message})

        @self.route('/messages/<int:message_id>', methods=['DELETE'], auth_type=group.AuthType.USER_TOKEN)
        async def delete_message(message_id: int) -> str:
            await self.ap.database_mode_service.delete_message(message_id)
            return self.success()

        @self.route('/messages/batch-process', methods=['POST'], auth_type=group.AuthType.USER_TOKEN)
        async def batch_process() -> str:
            payload = await quart.request.get_json(silent=True) or {}
            data = await self.ap.database_mode_service.batch_process(payload.get('message_ids') or [])
            return self.success(data=data)

        @self.route('/messages/batch-skip', methods=['POST'], auth_type=group.AuthType.USER_TOKEN)
        async def batch_skip() -> str:
            payload = await quart.request.get_json(silent=True) or {}
            data = await self.ap.database_mode_service.batch_skip(payload.get('message_ids') or [])
            return self.success(data=data)

        @self.route('/messages/batch-delete', methods=['POST'], auth_type=group.AuthType.USER_TOKEN)
        async def batch_delete() -> str:
            payload = await quart.request.get_json(silent=True) or {}
            data = await self.ap.database_mode_service.batch_delete(payload.get('message_ids') or [])
            return self.success(data=data)
