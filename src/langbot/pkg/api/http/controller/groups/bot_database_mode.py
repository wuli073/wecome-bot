from __future__ import annotations

import quart

from .. import group
from .....utils import paths
from .....desktop_automation.errors import (
    BOT_ADAPTER_UNSUPPORTED,
    BOT_CHANNEL_UNBOUND,
    BOT_DISABLED,
    BOT_NOT_FOUND,
    CONVERSATION_NAME_NOT_UNIQUE,
    CONVERSATION_NAME_REQUIRED,
    DRAFT_ALREADY_SENT,
    DRAFT_CHANGED,
    DRAFT_EMPTY,
    DRAFT_NOT_ACTIVE,
    DRAFT_NOT_FOUND,
    DRAFT_NOT_OWNED,
    DRAFT_TEXT_REQUIRED,
    DesktopAutomationError,
    IDEMPOTENCY_KEY_REQUIRED,
    INVALID_STATE_TRANSITION,
    MESSAGE_NOT_FOUND,
    MESSAGE_NOT_OWNED,
    RPA_RUNTIME_NOT_AVAILABLE,
    RUN_NOT_FOUND,
    RUNTIME_DISABLED,
    RUNTIME_NOT_CONFIGURED,
    RUNTIME_PROTOCOL_MISMATCH,
    RUNTIME_UNAVAILABLE,
    TASK_CONFLICT,
    TASK_TIMEOUT,
    UNSUPPORTED_PLATFORM,
)


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

        @self.route(
            '/<bot_id>/conversations/<int:conversation_id>', methods=['GET'], auth_type=group.AuthType.USER_TOKEN
        )
        async def get_bot_conversation(bot_id: str, conversation_id: int) -> str:
            connector_id_or_response = await self._get_bot_connector_id_or_response(bot_id)
            if not isinstance(connector_id_or_response, str):
                return connector_id_or_response
            connector_id = connector_id_or_response
            conversation = await self.ap.database_mode_service.get_conversation(
                conversation_id, connector_id=connector_id
            )
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
                bot_uuid=bot_id,
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
                    logger.exception(f'database_generate_draft_failed bot_id={bot_id} message_id={message_id}')

                return self.http_status(
                    500,
                    -2,
                    f'{type(exc).__name__}: {exc}',
                )

        @self.route(
            '/<bot_id>/messages/<int:message_id>/paste-draft',
            methods=['POST'],
            auth_type=group.AuthType.USER_TOKEN,
        )
        async def paste_bot_draft(bot_id: str, message_id: int) -> str:
            connector_id_or_response = await self._get_bot_connector_id_or_response(bot_id, allow_disabled=False)
            if not isinstance(connector_id_or_response, str):
                return connector_id_or_response
            connector_id = connector_id_or_response
            if await self._message_belongs_to_connector(message_id, connector_id) is False:
                return self.http_status(404, -1, 'Message does not belong to bot')

            if not hasattr(self.ap, 'desktop_automation_service') or self.ap.desktop_automation_service is None:
                return self.http_status(503, -1, 'Desktop automation service unavailable')

            payload = await quart.request.get_json(silent=True) or {}
            if set(payload.keys()) != {'draft_id'}:
                return self.http_status(400, -1, 'paste-draft body must contain only draft_id')
            if 'draft_id' not in payload:
                return self.http_status(400, -1, 'draft_id is required')
            try:
                draft_id = int(payload.get('draft_id'))
            except (TypeError, ValueError):
                return self.http_status(400, -1, 'draft_id must be a positive integer')
            if draft_id <= 0:
                return self.http_status(400, -1, 'draft_id must be a positive integer')
            idempotency_key = str(quart.request.headers.get('Idempotency-Key') or '').strip()
            if not idempotency_key:
                return self.http_status(400, -1, IDEMPOTENCY_KEY_REQUIRED)

            try:
                run = await self.ap.desktop_automation_service.create_paste_draft_run(
                    bot_id,
                    message_id,
                    draft_id,
                    idempotency_key=idempotency_key,
                )
            except DesktopAutomationError as exc:
                return self._desktop_automation_error_response(exc)
            except Exception as exc:
                return self.http_status(500, -2, f'{type(exc).__name__}: {exc}')
            return self.success(data=run)

        @self.route(
            '/<bot_id>/messages/<int:message_id>/send-draft',
            methods=['POST'],
            auth_type=group.AuthType.USER_TOKEN,
        )
        async def send_bot_draft(bot_id: str, message_id: int) -> str:
            connector_id_or_response = await self._get_bot_connector_id_or_response(bot_id, allow_disabled=False)
            if not isinstance(connector_id_or_response, str):
                return connector_id_or_response
            connector_id = connector_id_or_response
            if await self._message_belongs_to_connector(message_id, connector_id) is False:
                return self.http_status(404, -1, 'Message does not belong to bot')

            if not hasattr(self.ap, 'desktop_automation_service') or self.ap.desktop_automation_service is None:
                return self.http_status(503, -1, 'Desktop automation service unavailable')

            payload = await quart.request.get_json(silent=True) or {}
            if 'draft_id' not in payload:
                return self.http_status(400, -1, 'draft_id is required')
            try:
                draft_id = int(payload.get('draft_id'))
            except (TypeError, ValueError):
                return self.http_status(400, -1, 'draft_id must be a positive integer')
            if draft_id <= 0:
                return self.http_status(400, -1, 'draft_id must be a positive integer')
            try:
                run = await self.ap.desktop_automation_service.create_send_draft_run(
                    bot_id,
                    message_id,
                    draft_id,
                    explicit_frontend_send=bool(payload.get('explicit_send_action')),
                    python_authorized=bool(payload.get('python_authorized')),
                    send_strategy=payload.get('send_strategy'),
                    idempotency_key=payload.get('idempotency_key'),
                )
            except DesktopAutomationError as exc:
                return self._desktop_automation_error_response(exc)
            except Exception as exc:
                return self.http_status(500, -2, f'{type(exc).__name__}: {exc}')
            return self.success(data=run)

        @self.route(
            '/<bot_id>/desktop-automation/diagnose',
            methods=['POST'],
            auth_type=group.AuthType.USER_TOKEN,
        )
        async def diagnose_bot_desktop_automation(bot_id: str) -> str:
            if not hasattr(self.ap, 'desktop_automation_service') or self.ap.desktop_automation_service is None:
                return self.http_status(503, -1, 'Desktop automation service unavailable')
            payload = await quart.request.get_json(silent=True) or {}
            try:
                message_id = int(payload.get('message_id'))
                draft_id = int(payload.get('draft_id'))
            except (TypeError, ValueError):
                return self.http_status(400, -1, 'message_id and draft_id are required')
            if message_id <= 0 or draft_id <= 0:
                return self.http_status(400, -1, 'message_id and draft_id are required')
            try:
                run = await self.ap.desktop_automation_service.create_diagnose_run(bot_id, message_id, draft_id)
            except DesktopAutomationError as exc:
                return self._desktop_automation_error_response(exc)
            return self.success(data=run)

        @self.route(
            '/<bot_id>/messages/<int:message_id>/conversation-search',
            methods=['POST'],
            auth_type=group.AuthType.USER_TOKEN,
        )
        async def conversation_search_bot_draft(bot_id: str, message_id: int) -> str:
            connector_id_or_response = await self._get_bot_connector_id_or_response(bot_id, allow_disabled=False)
            if not isinstance(connector_id_or_response, str):
                return connector_id_or_response
            connector_id = connector_id_or_response
            if await self._message_belongs_to_connector(message_id, connector_id) is False:
                return self.http_status(404, -1, 'Message does not belong to bot')
            if not hasattr(self.ap, 'desktop_automation_service') or self.ap.desktop_automation_service is None:
                return self.http_status(503, -1, 'Desktop automation service unavailable')
            payload = await quart.request.get_json(silent=True) or {}
            try:
                draft_id = int(payload.get('draft_id'))
            except (TypeError, ValueError):
                return self.http_status(400, -1, 'draft_id must be a positive integer')
            query_text = str(payload.get('query_text') or '').strip()
            if not query_text:
                return self.http_status(400, -1, 'query_text is required')
            try:
                run = await self.ap.desktop_automation_service.create_conversation_search_run(
                    bot_id, message_id, draft_id, query_text=query_text
                )
            except DesktopAutomationError as exc:
                return self._desktop_automation_error_response(exc)
            except Exception as exc:
                return self.http_status(500, -2, f'{type(exc).__name__}: {exc}')
            return self.success(data=run)

        @self.route(
            '/<bot_id>/messages/<int:message_id>/history-search',
            methods=['POST'],
            auth_type=group.AuthType.USER_TOKEN,
        )
        async def history_search_bot_draft(bot_id: str, message_id: int) -> str:
            connector_id_or_response = await self._get_bot_connector_id_or_response(bot_id, allow_disabled=False)
            if not isinstance(connector_id_or_response, str):
                return connector_id_or_response
            connector_id = connector_id_or_response
            if await self._message_belongs_to_connector(message_id, connector_id) is False:
                return self.http_status(404, -1, 'Message does not belong to bot')
            if not hasattr(self.ap, 'desktop_automation_service') or self.ap.desktop_automation_service is None:
                return self.http_status(503, -1, 'Desktop automation service unavailable')
            payload = await quart.request.get_json(silent=True) or {}
            try:
                draft_id = int(payload.get('draft_id'))
            except (TypeError, ValueError):
                return self.http_status(400, -1, 'draft_id must be a positive integer')
            query_text = str(payload.get('query_text') or '').strip()
            if not query_text:
                return self.http_status(400, -1, 'query_text is required')
            try:
                run = await self.ap.desktop_automation_service.create_history_search_run(
                    bot_id, message_id, draft_id, query_text=query_text
                )
            except DesktopAutomationError as exc:
                return self._desktop_automation_error_response(exc)
            except Exception as exc:
                return self.http_status(500, -2, f'{type(exc).__name__}: {exc}')
            return self.success(data=run)

        @self.route(
            '/<bot_id>/messages/<int:message_id>/quote-reply',
            methods=['POST'],
            auth_type=group.AuthType.USER_TOKEN,
        )
        async def quote_reply_bot_draft(bot_id: str, message_id: int) -> str:
            connector_id_or_response = await self._get_bot_connector_id_or_response(bot_id, allow_disabled=False)
            if not isinstance(connector_id_or_response, str):
                return connector_id_or_response
            connector_id = connector_id_or_response
            if await self._message_belongs_to_connector(message_id, connector_id) is False:
                return self.http_status(404, -1, 'Message does not belong to bot')
            if not hasattr(self.ap, 'desktop_automation_service') or self.ap.desktop_automation_service is None:
                return self.http_status(503, -1, 'Desktop automation service unavailable')
            payload = await quart.request.get_json(silent=True) or {}
            try:
                draft_id = int(payload.get('draft_id'))
            except (TypeError, ValueError):
                return self.http_status(400, -1, 'draft_id must be a positive integer')
            query_text = str(payload.get('query_text') or '').strip()
            if not query_text:
                return self.http_status(400, -1, 'query_text is required')
            try:
                run = await self.ap.desktop_automation_service.create_quote_reply_run(
                    bot_id, message_id, draft_id, query_text=query_text
                )
            except DesktopAutomationError as exc:
                return self._desktop_automation_error_response(exc)
            except Exception as exc:
                return self.http_status(500, -2, f'{type(exc).__name__}: {exc}')
            return self.success(data=run)

        @self.route(
            '/<bot_id>/desktop-automation/runs/<int:run_id>',
            methods=['GET'],
            auth_type=group.AuthType.USER_TOKEN,
        )
        async def get_bot_scoped_run(bot_id: str, run_id: int) -> str:
            if not hasattr(self.ap, 'desktop_automation_service') or self.ap.desktop_automation_service is None:
                return self.http_status(503, -1, 'Desktop automation service unavailable')
            try:
                run = await self.ap.desktop_automation_service.get_run(bot_id, run_id)
            except DesktopAutomationError as exc:
                return self._desktop_automation_error_response(exc)
            return self.success(data=run)

        @self.route(
            '/<bot_id>/desktop-automation/runs/<int:run_id>/cancel',
            methods=['POST'],
            auth_type=group.AuthType.USER_TOKEN,
        )
        async def cancel_bot_scoped_run(bot_id: str, run_id: int) -> str:
            if not hasattr(self.ap, 'desktop_automation_service') or self.ap.desktop_automation_service is None:
                return self.http_status(503, -1, 'Desktop automation service unavailable')
            try:
                run = await self.ap.desktop_automation_service.cancel_run(bot_id, run_id)
            except DesktopAutomationError as exc:
                return self._desktop_automation_error_response(exc)
            return self.success(data=run)

        @self.route(
            '/<bot_id>/drafts/<int:draft_id>',
            methods=['PUT', 'DELETE'],
            auth_type=group.AuthType.USER_TOKEN,
        )
        async def bot_draft_detail(bot_id: str, draft_id: int) -> str:
            connector_id_or_response = await self._get_bot_connector_id_or_response(bot_id)
            if not isinstance(connector_id_or_response, str):
                return connector_id_or_response
            try:
                await self._validate_draft_belongs_to_bot(bot_id, draft_id)
            except ValueError as exc:
                return self.http_status(404, -1, str(exc))

            draft = await self._get_draft(draft_id)
            if draft is None:
                return self.http_status(404, -1, 'Draft not found')

            if quart.request.method == 'DELETE':
                message = await self.ap.database_mode_service.delete_draft(
                    int(draft.message_id),
                    draft_id=draft_id,
                )
                return self.success(data={'message': message})

            # Update the active ReplyDraft content and keep the message draft_text
            # in sync for compatibility with existing message list hydration.
            payload = await quart.request.get_json(silent=True) or {}
            draft_content = str(payload.get('content') or '').strip()
            if not draft_content:
                return self.http_status(400, -1, 'Draft content is required')

            message = await self.ap.database_mode_service.update_draft(
                int(draft.message_id),
                draft_text=draft_content,
                draft_source='manual',
                draft_id=draft_id,
            )
            return self.success(data={'message': message})

        @self.route(
            '/<bot_id>/messages/<int:message_id>/process', methods=['POST'], auth_type=group.AuthType.USER_TOKEN
        )
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

    async def _get_bot_connector_id_or_response(
        self, bot_uuid: str, allow_disabled: bool = True
    ) -> str | quart.Response:
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
                persistence_database_mode.BotChannelBinding.channel_account_id
                == persistence_database_mode.ChannelAccount.id,
            )
            .where(persistence_database_mode.BotChannelBinding.bot_uuid == bot_uuid)
        )
        connector_id = result.scalar()
        if connector_id is None:
            raise ValueError(f'Bot {bot_uuid} has no channel account binding')
        return str(connector_id)

    async def _validate_conversation_belongs_to_bot(self, bot_uuid: str, conversation_id: int) -> None:
        connector_id = await self._get_bot_connector_id(bot_uuid)
        if not await self._conversation_belongs_to_connector(conversation_id, connector_id):
            raise ValueError(f'Conversation {conversation_id} does not belong to bot {bot_uuid}')

    async def _conversation_belongs_to_connector(self, conversation_id: int, connector_id: str) -> bool:
        from .....entity.persistence import database_mode as persistence_database_mode
        import sqlalchemy

        conv_result = await self.ap.persistence_mgr.execute_async(
            sqlalchemy.select(persistence_database_mode.DatabaseConversation.id).where(
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
                persistence_database_mode.DatabaseMessage.conversation_id
                == persistence_database_mode.DatabaseConversation.id,
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
            sqlalchemy.select(persistence_database_mode.DatabaseMessage.conversation_id).where(
                persistence_database_mode.DatabaseMessage.id == message_id
            )
        )
        conversation_id = result.scalar()
        if conversation_id is None:
            raise ValueError(f'Message {message_id} not found')

        await self._validate_conversation_belongs_to_bot(bot_uuid, conversation_id)

    async def _validate_draft_belongs_to_bot(self, bot_uuid: str, draft_id: int) -> None:
        from .....entity.persistence import database_mode as persistence_database_mode
        import sqlalchemy

        result = await self.ap.persistence_mgr.execute_async(
            sqlalchemy.select(persistence_database_mode.ReplyDraft.bot_uuid).where(
                persistence_database_mode.ReplyDraft.id == draft_id
            )
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
            sqlalchemy.select(*persistence_database_mode.ReplyDraft.__table__.columns).where(
                persistence_database_mode.ReplyDraft.id == draft_id
            )
        )
        row = result.mappings().first()
        if row is None:
            return None
        draft = persistence_database_mode.ReplyDraft()
        for column_name, value in dict(row).items():
            setattr(draft, column_name, value)
        return draft

    def _desktop_automation_error_response(self, error: DesktopAutomationError):
        code = error.code
        status_code = self._desktop_automation_http_status(code)
        return self.http_status(status_code, -1, code)

    @staticmethod
    def _desktop_automation_http_status(code: str) -> int:
        if code in {
            DRAFT_NOT_FOUND,
            DRAFT_NOT_ACTIVE,
            DRAFT_CHANGED,
            DRAFT_EMPTY,
            DRAFT_TEXT_REQUIRED,
            CONVERSATION_NAME_REQUIRED,
            IDEMPOTENCY_KEY_REQUIRED,
        }:
            return 400
        if code in {BOT_DISABLED, BOT_ADAPTER_UNSUPPORTED, MESSAGE_NOT_OWNED, DRAFT_NOT_OWNED}:
            return 403
        if code in {BOT_NOT_FOUND, MESSAGE_NOT_FOUND, RUN_NOT_FOUND}:
            return 404
        if code in {TASK_CONFLICT, INVALID_STATE_TRANSITION, DRAFT_ALREADY_SENT, CONVERSATION_NAME_NOT_UNIQUE}:
            return 409
        if code in {'AUTO_SEND_NOT_AUTHORIZED', 'SEND_STRATEGY_REQUIRED'}:
            return 403
        if code == RPA_RUNTIME_NOT_AVAILABLE:
            return 503
        if code in {
            RUNTIME_DISABLED,
            RUNTIME_NOT_CONFIGURED,
            RUNTIME_UNAVAILABLE,
            RUNTIME_PROTOCOL_MISMATCH,
            UNSUPPORTED_PLATFORM,
            BOT_CHANNEL_UNBOUND,
        }:
            return 503
        if code == TASK_TIMEOUT:
            return 504
        return 500


@group.group_class('desktop_automation', '/api/v1/desktop-automation')
class DesktopAutomationRouterGroup(group.RouterGroup):
    async def initialize(self) -> None:
        @self.route('/runs/<int:run_id>', methods=['GET'], auth_type=group.AuthType.USER_TOKEN)
        async def get_run(run_id: int) -> str:
            return self.http_status(404, -1, 'Use bot-scoped desktop automation run endpoints')

        @self.route('/runs/<int:run_id>/cancel', methods=['POST'], auth_type=group.AuthType.USER_TOKEN)
        async def cancel_run(run_id: int) -> str:
            return self.http_status(404, -1, 'Use bot-scoped desktop automation run endpoints')

        runtime_status_auth_type = group.AuthType.NONE if paths.is_packaged_mode() else group.AuthType.USER_TOKEN

        @self.route('/runtime/status', methods=['GET'], auth_type=runtime_status_auth_type)
        async def runtime_status() -> str:
            # Task 1 packaged startup interface contract:
            # launcher observes backend-owned Desktop RPA readiness only through
            # GET /api/v1/desktop-automation/runtime/status.
            if not hasattr(self.ap, 'desktop_automation_service') or self.ap.desktop_automation_service is None:
                return self.http_status(503, -1, 'Desktop automation service unavailable')
            status = await self.ap.desktop_automation_service.get_runtime_status()
            return self.success(data=status)
