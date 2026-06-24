from __future__ import annotations

import asyncio
import datetime
import uuid

import jwt
import quart

from .. import group
from .....database_mode.events import (
    DATABASE_MODE_EVENT_SENTINEL,
    DatabaseModeEvent,
    DatabaseModeEventType,
    serialize_sse_event,
)


DATABASE_MODE_SSE_COOKIE_NAME = 'langbot_dbmode_sse'
DATABASE_MODE_SSE_COOKIE_PATH = '/api/v1/database-mode/events'
DATABASE_MODE_SSE_SESSION_VERSION = 1
DATABASE_MODE_SSE_SESSION_PURPOSE = 'database-mode-sse'
DATABASE_MODE_SSE_HEARTBEAT_INTERVAL_SECONDS = 15


def _get_int_arg(name: str, default: int) -> int:
    raw = quart.request.args.get(name, default)
    return int(raw)


@group.group_class('database_mode', '/api/v1/database-mode')
class DatabaseModeRouterGroup(group.RouterGroup):
    async def initialize(self) -> None:
        @self.route('/events/session', methods=['POST'], auth_type=group.AuthType.USER_TOKEN)
        async def create_event_session(user_email: str) -> quart.Response:
            now = datetime.datetime.now(datetime.timezone.utc)
            expires_at = now + datetime.timedelta(minutes=5)
            payload = {
                'sub': user_email,
                'version': DATABASE_MODE_SSE_SESSION_VERSION,
                'purpose': DATABASE_MODE_SSE_SESSION_PURPOSE,
                'issued_at': now.isoformat(),
                'expires_at': expires_at.isoformat(),
                'session_id': str(uuid.uuid4()),
            }
            token = jwt.encode(payload, self._get_jwt_secret(), algorithm='HS256')

            response = quart.Response(status=204)
            response.headers['Cache-Control'] = 'no-store'
            response.set_cookie(
                DATABASE_MODE_SSE_COOKIE_NAME,
                token,
                expires=expires_at,
                path=DATABASE_MODE_SSE_COOKIE_PATH,
                secure=quart.request.scheme == 'https',
                httponly=True,
                samesite='Strict',
            )
            return response

        @self.route('/events', methods=['GET'], auth_type=group.AuthType.NONE)
        async def stream_events():
            try:
                await self._verify_sse_session_cookie()
            except Exception as exc:
                return self.http_status(401, -1, str(exc))

            if self.ap.database_mode_event_bus is None:
                return self.http_status(503, -1, 'Database mode event bus is unavailable')

            subscriber = self.ap.database_mode_event_bus.subscribe()

            async def event_stream():
                try:
                    ready_event = DatabaseModeEvent(
                        type=DatabaseModeEventType.READY,
                        occurred_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    )
                    yield serialize_sse_event(ready_event).encode('utf-8')

                    while True:
                        try:
                            item = await asyncio.wait_for(
                                subscriber.queue.get(),
                                timeout=DATABASE_MODE_SSE_HEARTBEAT_INTERVAL_SECONDS,
                            )
                        except TimeoutError:
                            yield b': heartbeat\n\n'
                            continue

                        if item is DATABASE_MODE_EVENT_SENTINEL:
                            break

                        if isinstance(item, DatabaseModeEvent):
                            yield serialize_sse_event(item).encode('utf-8')
                finally:
                    self.ap.database_mode_event_bus.unsubscribe(subscriber.subscriber_id)

            response = quart.Response(event_stream(), content_type='text/event-stream')
            response.headers['Cache-Control'] = 'no-store'
            response.headers['Content-Encoding'] = 'identity'
            response.headers['X-Accel-Buffering'] = 'no'
            return response

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

    def _get_jwt_secret(self) -> str:
        return self.ap.instance_config.data['system']['jwt']['secret']

    async def _verify_sse_session_cookie(self) -> dict:
        token = quart.request.cookies.get(DATABASE_MODE_SSE_COOKIE_NAME, '')
        if not token:
            raise ValueError('Missing SSE session cookie')

        payload = jwt.decode(token, self._get_jwt_secret(), algorithms=['HS256'])
        if payload.get('version') != DATABASE_MODE_SSE_SESSION_VERSION:
            raise ValueError('Invalid SSE session version')
        if payload.get('purpose') != DATABASE_MODE_SSE_SESSION_PURPOSE:
            raise ValueError('Invalid SSE session purpose')

        user_email = str(payload.get('sub') or '').strip()
        if not user_email:
            raise ValueError('Missing SSE session subject')

        expires_at_raw = str(payload.get('expires_at') or '').strip()
        if not expires_at_raw:
            raise ValueError('Missing SSE session expiry')

        expires_at = datetime.datetime.fromisoformat(expires_at_raw)
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=datetime.timezone.utc)
        if expires_at <= datetime.datetime.now(datetime.timezone.utc):
            raise ValueError('SSE session expired')

        if not str(payload.get('session_id') or '').strip():
            raise ValueError('Missing SSE session id')

        user = await self.ap.user_service.get_user_by_email(user_email)
        if not user:
            raise ValueError('User not found')

        return payload
