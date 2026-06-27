from __future__ import annotations

import asyncio
import datetime
import uuid
from urllib.parse import urlparse

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
DATABASE_MODE_SSE_CORS_ALLOWED_METHODS = 'POST, GET, OPTIONS'
DATABASE_MODE_SSE_CORS_ALLOWED_HEADERS = 'Authorization, Content-Type'


def _get_int_arg(name: str, default: int) -> int:
    raw = quart.request.args.get(name, default)
    return int(raw)


@group.group_class('database_mode', '/api/v1/database-mode')
class DatabaseModeRouterGroup(group.RouterGroup):
    async def initialize(self) -> None:
        @self.quart_app.before_request
        async def validate_database_mode_sse_origin():
            if not self._is_sse_request():
                return None

            origin = self._get_request_origin_header()
            if origin is None or self._is_allowed_sse_origin(origin):
                return None

            response = quart.Response('Origin not allowed', status=403)
            response.vary.add('Origin')
            setattr(response, '_QUART_CORS_APPLIED', True)
            return response

        @self.quart_app.after_request
        async def apply_database_mode_sse_cors(response: quart.Response):
            if not self._is_sse_request():
                return response

            response.vary.add('Origin')

            origin = self._get_request_origin_header()
            if origin is not None and self._is_allowed_sse_origin(origin):
                response.headers['Access-Control-Allow-Origin'] = origin
                response.headers['Access-Control-Allow-Credentials'] = 'true'
                if quart.request.method == 'OPTIONS':
                    response.headers['Access-Control-Allow-Methods'] = DATABASE_MODE_SSE_CORS_ALLOWED_METHODS
                    response.headers['Access-Control-Allow-Headers'] = DATABASE_MODE_SSE_CORS_ALLOWED_HEADERS

            setattr(response, '_QUART_CORS_APPLIED', True)
            return response

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
            self._log_sse_event(
                'sse_subscriber_added',
                connection_id=subscriber.subscriber_id,
                event_bus_instance_id=getattr(self.ap.database_mode_event_bus, 'instance_id', None),
                subscriber_count=getattr(self.ap.database_mode_event_bus, 'subscriber_count', None),
            )
            self._log_sse_event(
                'subscriber_added',
                connection_id=subscriber.subscriber_id,
                event_bus_instance_id=getattr(self.ap.database_mode_event_bus, 'instance_id', None),
                subscriber_count=getattr(self.ap.database_mode_event_bus, 'subscriber_count', None),
            )

            async def event_stream():
                exit_reason = 'unknown'
                try:
                    ready_event = DatabaseModeEvent(
                        type=DatabaseModeEventType.READY,
                        occurred_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    )
                    yield serialize_sse_event(ready_event).encode('utf-8')
                    self._log_sse_event(
                        'sse_ready_written',
                        connection_id=subscriber.subscriber_id,
                        event_id=ready_event.event_id,
                        event_bus_instance_id=getattr(self.ap.database_mode_event_bus, 'instance_id', None),
                        subscriber_count=getattr(self.ap.database_mode_event_bus, 'subscriber_count', None),
                    )
                    self._log_sse_event(
                        'sse_event_written',
                        connection_id=subscriber.subscriber_id,
                        event_id=ready_event.event_id,
                        event_type=ready_event.type.value,
                        event_bus_instance_id=getattr(self.ap.database_mode_event_bus, 'instance_id', None),
                        subscriber_count=getattr(self.ap.database_mode_event_bus, 'subscriber_count', None),
                    )

                    while True:
                        try:
                            item = await asyncio.wait_for(
                                subscriber.queue.get(),
                                timeout=DATABASE_MODE_SSE_HEARTBEAT_INTERVAL_SECONDS,
                            )
                        except asyncio.TimeoutError:
                            yield b': heartbeat\n\n'
                            self._log_sse_event(
                                'sse_heartbeat_written',
                                connection_id=subscriber.subscriber_id,
                                event_bus_instance_id=getattr(self.ap.database_mode_event_bus, 'instance_id', None),
                                subscriber_count=getattr(self.ap.database_mode_event_bus, 'subscriber_count', None),
                            )
                            continue

                        if item is DATABASE_MODE_EVENT_SENTINEL:
                            exit_reason = 'application-shutdown'
                            break

                        if isinstance(item, DatabaseModeEvent):
                            yield serialize_sse_event(item).encode('utf-8')
                            self._log_sse_event(
                                'sse_business_event_written',
                                connection_id=subscriber.subscriber_id,
                                event_id=item.event_id,
                                event_type=item.type.value,
                                event_bus_instance_id=getattr(self.ap.database_mode_event_bus, 'instance_id', None),
                                subscriber_count=getattr(self.ap.database_mode_event_bus, 'subscriber_count', None),
                            )
                            self._log_sse_event(
                                'sse_event_written',
                                connection_id=subscriber.subscriber_id,
                                event_id=item.event_id,
                                event_type=item.type.value,
                                event_bus_instance_id=getattr(self.ap.database_mode_event_bus, 'instance_id', None),
                                subscriber_count=getattr(self.ap.database_mode_event_bus, 'subscriber_count', None),
                            )
                except asyncio.CancelledError:
                    exit_reason = 'client-disconnected'
                    self._log_sse_event(
                        'sse_client_disconnected',
                        connection_id=subscriber.subscriber_id,
                        exit_reason=exit_reason,
                    )
                    self._log_sse_event(
                        'sse_generator_cancelled',
                        connection_id=subscriber.subscriber_id,
                        exit_reason=exit_reason,
                    )
                    raise
                except Exception as exc:
                    exit_reason = exc.__class__.__name__
                    self._log_sse_event(
                        'sse_generator_failed',
                        connection_id=subscriber.subscriber_id,
                        exit_reason=exit_reason,
                    )
                    raise
                finally:
                    self.ap.database_mode_event_bus.unsubscribe(subscriber.subscriber_id)
                    self._log_sse_event(
                        'sse_subscriber_removed',
                        connection_id=subscriber.subscriber_id,
                        exit_reason=exit_reason,
                        event_bus_instance_id=getattr(self.ap.database_mode_event_bus, 'instance_id', None),
                        subscriber_count=getattr(self.ap.database_mode_event_bus, 'subscriber_count', None),
                    )

            response = quart.Response(event_stream(), content_type='text/event-stream')
            response.timeout = None
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

        @self.route(
            '/messages/<int:message_id>/draft',
            methods=['PUT', 'DELETE'],
            auth_type=group.AuthType.USER_TOKEN,
        )
        async def draft_detail(message_id: int) -> str:
            if quart.request.method == 'DELETE':
                message = await self.ap.database_mode_service.delete_draft(message_id)
                return self.success(data={'message': message})

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

    def _is_sse_request(self) -> bool:
        return quart.request.path in {
            f'{self.path}/events',
            f'{self.path}/events/session',
        }

    def _get_request_origin_header(self) -> str | None:
        origin = quart.request.headers.get('Origin', '').strip()
        return origin or None

    def _get_public_request_origin(self) -> str:
        forwarded_proto = quart.request.headers.get('X-Forwarded-Proto', '').split(',')[0].strip()
        forwarded_host = quart.request.headers.get('X-Forwarded-Host', '').split(',')[0].strip()

        scheme = forwarded_proto or quart.request.scheme
        host = forwarded_host or quart.request.host
        return f'{scheme}://{host}'

    def _is_allowed_sse_origin(self, origin: str) -> bool:
        parsed_origin = urlparse(origin)
        parsed_request_origin = urlparse(self._get_public_request_origin())

        if parsed_origin.scheme not in {'http', 'https'} or not parsed_origin.hostname:
            return False

        return (
            parsed_origin.scheme == parsed_request_origin.scheme
            and parsed_origin.hostname == parsed_request_origin.hostname
        )

    def _log_sse_event(self, event_name: str, **payload) -> None:
        logger = getattr(self.ap, 'logger', None)
        if logger is None:
            return
        details = ' '.join(
            f'{key}={value}'
            for key, value in payload.items()
            if value is not None
        )
        logger.info(f'{event_name}{(" " + details) if details else ""}')
