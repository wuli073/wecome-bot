from __future__ import annotations

import quart

from .. import group


def _get_int_arg(name: str, default: int) -> int:
    raw = quart.request.args.get(name, default)
    return int(raw)


@group.group_class('bot_database_mode', '/api/v1/bots')
class BotDatabaseModeRouterGroup(group.RouterGroup):
    """Bot-scoped API for database mode operations."""

    async def initialize(self) -> None:
        @self.route('/<bot_id>/conversations', methods=['GET'], auth_type=group.AuthType.USER_TOKEN)
        async def list_bot_conversations(bot_id: str) -> str:
            connector_id_or_response = await self._get_bot_connector_id_or_response(bot_id)
            if not isinstance(connector_id_or_response, str):
                return connector_id_or_response
            connector_id = connector_id_or_response

            data = await self.ap.database_mode_service.list_conversations(
                status=quart.request.args.get('status'),
                keyword=quart.request.args.get('keyword', ''),
                page=_get_int_arg('page', 1),
                page_size=_get_int_arg('page_size', 20),
                connector_id=connector_id,
            )
            return self.success(data=data)

        @self.route('/<bot_id>/conversations/<int:conversation_id>', methods=['GET'], auth_type=group.AuthType.USER_TOKEN)
        async def get_bot_conversation(bot_id: str, conversation_id: int) -> str:
            connector_id_or_response = await self._get_bot_connector_id_or_response(bot_id)
            if not isinstance(connector_id_or_response, str):
                return connector_id_or_response
            connector_id = connector_id_or_response
            conversation = await self.ap.database_mode_service.get_conversation(conversation_id, connector_id=connector_id)
            if conversation is None:
                return self.http_status(404, -1, 'Conversation does not belong to bot')
            return self.success(data={'conversation': conversation})

        @self.route(
            '/<bot_id>/conversations/<int:conversation_id>/messages',
            methods=['GET'],
            auth_type=group.AuthType.USER_TOKEN,
        )
        async def list_bot_messages(bot_id: str, conversation_id: int) -> str:
            connector_id_or_response = await self._get_bot_connector_id_or_response(bot_id)
            if not isinstance(connector_id_or_response, str):
                return connector_id_or_response
            connector_id = connector_id_or_response
            if await self._conversation_belongs_to_connector(conversation_id, connector_id) is False:
                return self.http_status(404, -1, 'Conversation does not belong to bot')

            data = await self.ap.database_mode_service.list_messages(
                conversation_id,
                status=quart.request.args.get('status'),
                page=_get_int_arg('page', 1),
                page_size=_get_int_arg('page_size', 50),
                connector_id=connector_id,
            )
            return self.success(data=data)

        @self.route(
            '/<bot_id>/messages/<int:message_id>/generate-draft',
            methods=['POST'],
            auth_type=group.AuthType.USER_TOKEN,
        )
        async def generate_bot_draft(bot_id: str, message_id: int) -> str:
            connector_id_or_response = await self._get_bot_connector_id_or_response(bot_id, allow_disabled=False)
            if not isinstance(connector_id_or_response, str):
                return connector_id_or_response
            connector_id = connector_id_or_response
            if await self._message_belongs_to_connector(message_id, connector_id) is False:
                return self.http_status(404, -1, 'Message does not belong to bot')

            if not hasattr(self.ap, 'database_mode_processing_service'):
                return self.http_status(503, -1, 'Processing service unavailable')

            try:
                result = await self.ap.database_mode_processing_service.generate_draft(
                    message_id,
                    bot_id,
                    trigger='manual',
                )

                return self.success(data=result)

            except Exception as exc:
                logger = getattr(self.ap, 'logger', None)
                if logger is not None and hasattr(logger, 'exception'):
                    logger.exception(
                        f'database_generate_draft_failed bot_id={bot_id} message_id={message_id}'
                    )

                return self.http_status(
                    500,
                    -2,
                    f'{type(exc).__name__}: {exc}',
                )

        @self.route('/<bot_id>/drafts/<int:draft_id>', methods=['PUT'], auth_type=group.AuthType.USER_TOKEN)
        async def update_bot_draft(bot_id: str, draft_id: int) -> str:
            connector_id_or_response = await self._get_bot_connector_id_or_response(bot_id)
            if not isinstance(connector_id_or_response, str):
                return connector_id_or_response
            try:
                await self._validate_draft_belongs_to_bot(bot_id, draft_id)
            except ValueError as exc:
                return self.http_status(404, -1, str(exc))

            payload = await quart.request.get_json(silent=True) or {}
            draft_content = str(payload.get('content') or '').strip()
            if not draft_content:
                return self.http_status(400, -1, 'Draft content is required')

            # Update via ReplyDraft (manual edit creates new version)
            # For now, we update the message's draft_text as compatibility
            draft = await self._get_draft(draft_id)
            if draft is None:
                return self.http_status(404, -1, 'Draft not found')

            message_id = int(draft.message_id)
            message = await self.ap.database_mode_service.update_draft(
                message_id,
                draft_text=draft_content,
                draft_source='manual',
            )
            return self.success(data={'message': message})

        @self.route('/<bot_id>/messages/<int:message_id>/process', methods=['POST'], auth_type=group.AuthType.USER_TOKEN)
        async def process_bot_message(bot_id: str, message_id: int) -> str:
            connector_id_or_response = await self._get_bot_connector_id_or_response(bot_id, allow_disabled=False)
            if not isinstance(connector_id_or_response, str):
                return connector_id_or_response
            connector_id = connector_id_or_response
            if await self._message_belongs_to_connector(message_id, connector_id) is False:
                return self.http_status(404, -1, 'Message does not belong to bot')

            message = await self.ap.database_mode_service.process_message(message_id)
            return self.success(data={'message': message})

        @self.route('/<bot_id>/messages/<int:message_id>/skip', methods=['POST'], auth_type=group.AuthType.USER_TOKEN)
        async def skip_bot_message(bot_id: str, message_id: int) -> str:
            connector_id_or_response = await self._get_bot_connector_id_or_response(bot_id, allow_disabled=False)
            if not isinstance(connector_id_or_response, str):
                return connector_id_or_response
            connector_id = connector_id_or_response
            if await self._message_belongs_to_connector(message_id, connector_id) is False:
                return self.http_status(404, -1, 'Message does not belong to bot')

            message = await self.ap.database_mode_service.skip_message(message_id)
            return self.success(data={'message': message})

        @self.route('/<bot_id>/messages/<int:message_id>', methods=['DELETE'], auth_type=group.AuthType.USER_TOKEN)
        async def delete_bot_message(bot_id: str, message_id: int) -> str:
            connector_id_or_response = await self._get_bot_connector_id_or_response(bot_id, allow_disabled=True)
            if not isinstance(connector_id_or_response, str):
                return connector_id_or_response
            connector_id = connector_id_or_response
            if await self._message_belongs_to_connector(message_id, connector_id) is False:
                return self.http_status(404, -1, 'Message does not belong to bot')

            await self.ap.database_mode_service.delete_message(message_id)
            return self.success()

        @self.route('/<bot_id>/messages/batch-process', methods=['POST'], auth_type=group.AuthType.USER_TOKEN)
        async def batch_process_bot_messages(bot_id: str) -> str:
            connector_id_or_response = await self._get_bot_connector_id_or_response(bot_id, allow_disabled=False)
            if not isinstance(connector_id_or_response, str):
                return connector_id_or_response
            connector_id = connector_id_or_response

            payload = await quart.request.get_json(silent=True) or {}
            message_ids = payload.get('message_ids') or []

            for message_id in message_ids:
                if await self._message_belongs_to_connector(message_id, connector_id) is False:
                    return self.http_status(404, -1, 'Message does not belong to bot')

            data = await self.ap.database_mode_service.batch_process(message_ids)
            return self.success(data=data)

        @self.route('/<bot_id>/messages/batch-skip', methods=['POST'], auth_type=group.AuthType.USER_TOKEN)
        async def batch_skip_bot_messages(bot_id: str) -> str:
            connector_id_or_response = await self._get_bot_connector_id_or_response(bot_id, allow_disabled=False)
            if not isinstance(connector_id_or_response, str):
                return connector_id_or_response
            connector_id = connector_id_or_response

            payload = await quart.request.get_json(silent=True) or {}
            message_ids = payload.get('message_ids') or []

            for message_id in message_ids:
                if await self._message_belongs_to_connector(message_id, connector_id) is False:
                    return self.http_status(404, -1, 'Message does not belong to bot')

            data = await self.ap.database_mode_service.batch_skip(message_ids)
            return self.success(data=data)

        @self.route('/<bot_id>/messages/batch-delete', methods=['POST'], auth_type=group.AuthType.USER_TOKEN)
        async def batch_delete_bot_messages(bot_id: str) -> str:
            connector_id_or_response = await self._get_bot_connector_id_or_response(bot_id, allow_disabled=True)
            if not isinstance(connector_id_or_response, str):
                return connector_id_or_response
            connector_id = connector_id_or_response

            payload = await quart.request.get_json(silent=True) or {}
            message_ids = payload.get('message_ids') or []

            for message_id in message_ids:
                if await self._message_belongs_to_connector(message_id, connector_id) is False:
                    return self.http_status(404, -1, 'Message does not belong to bot')

            data = await self.ap.database_mode_service.batch_delete(message_ids)
            return self.success(data=data)

    async def _validate_bot_access(self, bot_uuid: str, allow_disabled: bool = True) -> None:
        bot = await self.ap.bot_service.get_bot(bot_uuid, include_secret=False)
        if bot is None:
            raise ValueError(f'Bot {bot_uuid} not found')

        if bot.get('adapter') != 'wxwork_database':
            raise ValueError(f'Bot {bot_uuid} is not a wxwork_database bot')

        if not allow_disabled and not bot.get('enable', False):
            raise ValueError(f'Bot {bot_uuid} is disabled')

    async def _get_bot_connector_id_or_response(self, bot_uuid: str, allow_disabled: bool = True) -> str | quart.Response:
        try:
            await self._validate_bot_access(bot_uuid, allow_disabled=allow_disabled)
            return await self._get_bot_connector_id(bot_uuid)
        except ValueError as exc:
            message = str(exc)
            if 'disabled' in message or 'not a wxwork_database bot' in message:
                return self.http_status(403, -1, message)
            return self.http_status(404, -1, message)

    async def _get_bot_connector_id(self, bot_uuid: str) -> str:
        from .....entity.persistence import database_mode as persistence_database_mode
        import sqlalchemy

        result = await self.ap.persistence_mgr.execute_async(
            sqlalchemy.select(persistence_database_mode.ChannelAccount.connector_id)
            .join(
                persistence_database_mode.BotChannelBinding,
                persistence_database_mode.BotChannelBinding.channel_account_id == persistence_database_mode.ChannelAccount.id,
            )
            .where(persistence_database_mode.BotChannelBinding.bot_uuid == bot_uuid)
        )
        connector_id = result.scalar()
        if connector_id is None:
            raise ValueError(f'Bot {bot_uuid} has no channel account binding')
        return str(connector_id)

    async def _validate_conversation_belongs_to_bot(self, bot_uuid: str, conversation_id: int) -> None:
        from .....entity.persistence import database_mode as persistence_database_mode
        import sqlalchemy

        connector_id = await self._get_bot_connector_id(bot_uuid)
        if not await self._conversation_belongs_to_connector(conversation_id, connector_id):
            raise ValueError(f'Conversation {conversation_id} does not belong to bot {bot_uuid}')

    async def _conversation_belongs_to_connector(self, conversation_id: int, connector_id: str) -> bool:
        from .....entity.persistence import database_mode as persistence_database_mode
        import sqlalchemy

        conv_result = await self.ap.persistence_mgr.execute_async(
            sqlalchemy.select(persistence_database_mode.DatabaseConversation.id)
            .where(
                persistence_database_mode.DatabaseConversation.id == conversation_id,
                persistence_database_mode.DatabaseConversation.connector_id == connector_id,
            )
        )
        return conv_result.scalar() is not None

    async def _message_belongs_to_connector(self, message_id: int, connector_id: str) -> bool:
        from .....entity.persistence import database_mode as persistence_database_mode
        import sqlalchemy

        result = await self.ap.persistence_mgr.execute_async(
            sqlalchemy.select(persistence_database_mode.DatabaseMessage.id)
            .join(
                persistence_database_mode.DatabaseConversation,
                persistence_database_mode.DatabaseMessage.conversation_id == persistence_database_mode.DatabaseConversation.id,
            )
            .where(
                persistence_database_mode.DatabaseMessage.id == message_id,
                persistence_database_mode.DatabaseConversation.connector_id == connector_id,
            )
        )
        return result.scalar() is not None

    async def _validate_message_belongs_to_bot(self, bot_uuid: str, message_id: int) -> None:
        from .....entity.persistence import database_mode as persistence_database_mode
        import sqlalchemy

        result = await self.ap.persistence_mgr.execute_async(
            sqlalchemy.select(persistence_database_mode.DatabaseMessage.conversation_id)
            .where(persistence_database_mode.DatabaseMessage.id == message_id)
        )
        conversation_id = result.scalar()
        if conversation_id is None:
            raise ValueError(f'Message {message_id} not found')

        await self._validate_conversation_belongs_to_bot(bot_uuid, conversation_id)

    async def _validate_draft_belongs_to_bot(self, bot_uuid: str, draft_id: int) -> None:
        from .....entity.persistence import database_mode as persistence_database_mode
        import sqlalchemy

        result = await self.ap.persistence_mgr.execute_async(
            sqlalchemy.select(persistence_database_mode.ReplyDraft.bot_uuid)
            .where(persistence_database_mode.ReplyDraft.id == draft_id)
        )
        draft_bot_uuid = result.scalar()
        if draft_bot_uuid is None:
            raise ValueError(f'Draft {draft_id} not found')
        if draft_bot_uuid != bot_uuid:
            raise ValueError(f'Draft {draft_id} does not belong to bot {bot_uuid}')

    async def _get_draft(self, draft_id: int):
        from .....entity.persistence import database_mode as persistence_database_mode
        import sqlalchemy

        result = await self.ap.persistence_mgr.execute_async(
            sqlalchemy.select(persistence_database_mode.ReplyDraft)
            .where(persistence_database_mode.ReplyDraft.id == draft_id)
        )
        return result.scalars().first()
