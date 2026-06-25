from __future__ import annotations

import hashlib
import datetime
from contextlib import asynccontextmanager
from dataclasses import dataclass

import sqlalchemy
from sqlalchemy import func

from langbot_plugin.api.entities.builtin.provider import message as provider_message

from ..core import app
from ..entity.persistence import database_mode as persistence_database_mode
from .events import DatabaseModeEvent, DatabaseModeEventType


MESSAGE_STATUS_PENDING = 'pending'
MESSAGE_STATUS_DRAFT_READY = 'draft_ready'
MESSAGE_STATUS_PROCESSING = 'processing'
MESSAGE_STATUS_FAILED = 'failed'
MESSAGE_STATUS_PROCESSED = 'processed'
MESSAGE_STATUS_SKIPPED = 'skipped'

MESSAGE_STATUSES = {
    MESSAGE_STATUS_PENDING,
    MESSAGE_STATUS_DRAFT_READY,
    MESSAGE_STATUS_PROCESSING,
    MESSAGE_STATUS_FAILED,
    MESSAGE_STATUS_PROCESSED,
    MESSAGE_STATUS_SKIPPED,
}


@dataclass(slots=True)
class EventIngestResult:
    accepted: bool
    duplicate: bool
    event_id: str
    timings: dict | None = None


class DatabaseModeService:
    ap: app.Application

    def __init__(self, ap: app.Application) -> None:
        self.ap = ap

    async def ingest_internal_event(self, payload: dict) -> EventIngestResult:
        connector_id = str(payload.get('connector_id') or '').strip()
        if connector_id != 'wxwork-local':
            raise ValueError('Only wxwork-local events are supported')

        event_id = str(payload.get('event_id') or '').strip()
        message_key = str(payload.get('message_key') or '').strip()
        if not event_id or not message_key:
            raise ValueError('event_id and message_key are required')
        message_key_hash = self._message_key_hash(message_key)
        self._log_event(
            'internal_event_received',
            event_id=event_id,
            message_key_hash=message_key_hash,
        )

        source = str(payload.get('source') or 'wxwork').strip() or 'wxwork'
        timings = payload.get('timings') if isinstance(payload.get('timings'), dict) else {}
        conversation_payload = payload.get('conversation') or {}
        message_payload = payload.get('message') or {}

        external_conversation_id = str(conversation_payload.get('external_conversation_id') or '').strip()
        if not external_conversation_id:
            raise ValueError('conversation.external_conversation_id is required')

        sender_id = str(message_payload.get('sender_id') or '').strip()
        sender_name = str(message_payload.get('sender_name') or '').strip()
        if not sender_id:
            raise ValueError('message.sender_id is required')
        if not sender_name:
            raise ValueError('message.sender_name is required')

        content = str(message_payload.get('content') or '').strip()
        if not content:
            raise ValueError('message.content is required')

        sent_at = self._parse_datetime(message_payload.get('sent_at'))
        observed_at = self._parse_datetime(message_payload.get('observed_at'))
        external_message_id = self._string_or_none(message_payload.get('external_message_id'))
        message_type = str(message_payload.get('message_type') or 'text').strip() or 'text'
        conversation_name = (
            str(conversation_payload.get('conversation_name') or '').strip() or sender_name or external_conversation_id
        )
        conversation_type = str(conversation_payload.get('conversation_type') or 'direct').strip() or 'direct'

        existing_event = await self._fetch_optional_model(
            persistence_database_mode.LocalConnectorEvent,
            sqlalchemy.select(persistence_database_mode.LocalConnectorEvent).where(
                persistence_database_mode.LocalConnectorEvent.event_id == event_id
            ),
        )
        if existing_event is not None:
            self._log_event(
                'duplicate_checked',
                event_id=event_id,
                message_key_hash=message_key_hash,
                duplicate=True,
            )
            return EventIngestResult(accepted=True, duplicate=True, event_id=event_id)

        created_message_id: int | None = None
        conversation_id: int | None = None
        duplicate_message = False
        async with self._transaction() as conn:
            existing_message = await self._fetch_optional_model(
                persistence_database_mode.DatabaseMessage,
                sqlalchemy.select(persistence_database_mode.DatabaseMessage).where(
                    persistence_database_mode.DatabaseMessage.message_key == message_key
                ),
                conn=conn,
            )
            if existing_message is not None:
                duplicate_message = True
                await conn.execute(
                    sqlalchemy.insert(persistence_database_mode.LocalConnectorEvent).values(
                        {
                            'event_id': event_id,
                            'connector_id': connector_id,
                            'message_key': message_key,
                            'status': MESSAGE_STATUS_PROCESSED,
                            'received_at': observed_at,
                            'processed_at': self._utcnow(),
                        }
                    )
                )
            else:
                await conn.execute(
                    sqlalchemy.insert(persistence_database_mode.LocalConnectorEvent).values(
                        {
                            'event_id': event_id,
                            'connector_id': connector_id,
                            'message_key': message_key,
                            'status': MESSAGE_STATUS_PROCESSING,
                            'received_at': observed_at,
                        }
                    )
                )
                try:
                    conversation = await self._get_or_create_conversation(
                        connector_id=connector_id,
                        source=source,
                        external_conversation_id=external_conversation_id,
                        conversation_name=conversation_name,
                        conversation_type=conversation_type,
                        last_message_at=sent_at,
                        conn=conn,
                    )
                    conversation_id = int(conversation['id'])
                    insert_result = await conn.execute(
                        sqlalchemy.insert(persistence_database_mode.DatabaseMessage).values(
                            {
                                'event_id': event_id,
                                'message_key': message_key,
                                'conversation_id': conversation_id,
                                'external_message_id': external_message_id,
                                'sender_id': sender_id,
                                'sender_name': sender_name,
                                'content': content,
                                'message_type': message_type,
                                'sent_at': sent_at,
                                'observed_at': observed_at,
                                'status': MESSAGE_STATUS_PENDING,
                                'draft_text': None,
                                'draft_source': None,
                                'attempt_count': 0,
                                'last_error': None,
                            }
                        )
                    )
                    inserted_primary_key = getattr(insert_result, 'inserted_primary_key', None) or ()
                    if inserted_primary_key:
                        created_message_id = int(inserted_primary_key[0])
                    await conn.execute(
                        sqlalchemy.update(persistence_database_mode.LocalConnectorEvent)
                        .where(persistence_database_mode.LocalConnectorEvent.event_id == event_id)
                        .values(
                            {
                                'status': MESSAGE_STATUS_PROCESSED,
                                'processed_at': self._utcnow(),
                                'last_error': None,
                            }
                        )
                    )
                except Exception:
                    # Keep ingest atomic: on any failure, the transaction rolls back the
                    # LocalConnectorEvent insert along with the conversation/message writes.
                    # Do not record a failed ingest outside the transaction in this path.
                    raise
        self._log_event(
            'database_commit_completed',
            event_id=event_id,
            message_key_hash=message_key_hash,
            duplicate=duplicate_message,
            conversation_id=conversation_id,
            message_id=created_message_id,
        )
        if duplicate_message:
            self._log_event(
                'duplicate_checked',
                event_id=event_id,
                message_key_hash=message_key_hash,
                duplicate=True,
            )
            await self._publish_event(DatabaseModeEventType.INVALIDATED)
            return EventIngestResult(accepted=True, duplicate=True, event_id=event_id)
        self._log_event(
            'duplicate_checked',
            event_id=event_id,
            message_key_hash=message_key_hash,
            duplicate=False,
        )

        if created_message_id is None:
            created_message = await self._fetch_required_model(
                persistence_database_mode.DatabaseMessage,
                sqlalchemy.select(persistence_database_mode.DatabaseMessage).where(
                    persistence_database_mode.DatabaseMessage.message_key == message_key
                ),
                error_message='Message not found after ingest',
            )
            created_message_id = int(created_message.id)
            conversation_id = int(created_message.conversation_id)

        published_timings = {
            key: str(value)
            for key, value in timings.items()
            if key and value
        }
        published_timings.setdefault('langbot_ingested_at', self._to_iso(self._utcnow()))
        published_timings = await self._publish_event(
            DatabaseModeEventType.MESSAGE_CREATED,
            conversation_id=conversation_id,
            message_id=created_message_id,
            metadata={'timings': published_timings},
        )

        # Trigger automatic draft generation if enabled
        await self._maybe_schedule_auto_draft(created_message_id, conversation_id)

        return EventIngestResult(
            accepted=True,
            duplicate=False,
            event_id=event_id,
            timings=published_timings.get('timings') if isinstance(published_timings, dict) else None,
        )

    async def list_conversations(
        self,
        *,
        status: str | None = None,
        keyword: str = '',
        page: int = 1,
        page_size: int = 20,
    ) -> dict:
        page, page_size = self._normalize_page(page, page_size)
        keyword = (keyword or '').strip()
        status = self._normalize_status_filter(status)

        pending_case = func.sum(
            sqlalchemy.case((persistence_database_mode.DatabaseMessage.status == MESSAGE_STATUS_PENDING, 1), else_=0)
        )
        failed_case = func.sum(
            sqlalchemy.case((persistence_database_mode.DatabaseMessage.status == MESSAGE_STATUS_FAILED, 1), else_=0)
        )
        latest_at = func.max(persistence_database_mode.DatabaseMessage.sent_at)
        stmt = (
            sqlalchemy.select(
                persistence_database_mode.DatabaseConversation.id,
                persistence_database_mode.DatabaseConversation.connector_id,
                persistence_database_mode.DatabaseConversation.source,
                persistence_database_mode.DatabaseConversation.external_conversation_id,
                persistence_database_mode.DatabaseConversation.conversation_name,
                persistence_database_mode.DatabaseConversation.conversation_type,
                persistence_database_mode.DatabaseConversation.last_message_at,
                pending_case.label('pending_count'),
                failed_case.label('failed_count'),
                latest_at.label('latest_at'),
            )
            .select_from(persistence_database_mode.DatabaseConversation)
            .join(
                persistence_database_mode.DatabaseMessage,
                persistence_database_mode.DatabaseMessage.conversation_id
                == persistence_database_mode.DatabaseConversation.id,
            )
        )

        if keyword:
            pattern = f'%{keyword}%'
            stmt = stmt.where(
                sqlalchemy.or_(
                    persistence_database_mode.DatabaseConversation.conversation_name.ilike(pattern),
                    persistence_database_mode.DatabaseMessage.sender_name.ilike(pattern),
                    persistence_database_mode.DatabaseMessage.content.ilike(pattern),
                )
            )
        if status:
            stmt = stmt.where(persistence_database_mode.DatabaseMessage.status == status)

        stmt = stmt.group_by(
            persistence_database_mode.DatabaseConversation.id,
            persistence_database_mode.DatabaseConversation.connector_id,
            persistence_database_mode.DatabaseConversation.source,
            persistence_database_mode.DatabaseConversation.external_conversation_id,
            persistence_database_mode.DatabaseConversation.conversation_name,
            persistence_database_mode.DatabaseConversation.conversation_type,
            persistence_database_mode.DatabaseConversation.last_message_at,
        ).order_by(latest_at.desc(), persistence_database_mode.DatabaseConversation.id.desc())

        total_stmt = sqlalchemy.select(func.count()).select_from(stmt.subquery())
        total = int((await self.ap.persistence_mgr.execute_async(total_stmt)).scalar() or 0)
        rows = (
            await self.ap.persistence_mgr.execute_async(
                stmt.offset((page - 1) * page_size).limit(page_size)
            )
        ).all()

        conversations = []
        for row in rows:
            latest_message = await self._get_latest_message_for_conversation(int(row.id))
            conversations.append(
                {
                    'id': int(row.id),
                    'connector_id': row.connector_id,
                    'source': row.source,
                    'external_conversation_id': row.external_conversation_id,
                    'conversation_name': row.conversation_name,
                    'conversation_type': row.conversation_type,
                    'last_message_at': self._to_iso(row.latest_at or row.last_message_at),
                    'pending_count': int(row.pending_count or 0),
                    'failed_count': int(row.failed_count or 0),
                    'latest_customer': latest_message.get('sender_name') if latest_message else '',
                    'latest_message_summary': self._summarize_text(latest_message.get('content') if latest_message else ''),
                }
            )

        return {
            'conversations': conversations,
            'total': total,
            'page': page,
            'page_size': page_size,
        }

    async def get_conversation(self, conversation_id: int) -> dict | None:
        conversation = await self._fetch_optional_model(
            persistence_database_mode.DatabaseConversation,
            sqlalchemy.select(persistence_database_mode.DatabaseConversation).where(
                persistence_database_mode.DatabaseConversation.id == conversation_id
            ),
        )
        if conversation is None:
            return None
        conversation_data = self._serialize_model(
            persistence_database_mode.DatabaseConversation,
            conversation,
        )
        stats = await self._get_conversation_stats(conversation_id)
        latest_message = await self._get_latest_message_for_conversation(conversation_id)
        return {
            **conversation_data,
            'stats': stats,
            'latest_customer': latest_message.get('sender_name') if latest_message else '',
        }

    async def list_messages(
        self,
        conversation_id: int,
        *,
        status: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> dict:
        page, page_size = self._normalize_page(page, page_size, max_page_size=200)
        status = self._normalize_status_filter(status)

        stmt = sqlalchemy.select(persistence_database_mode.DatabaseMessage).where(
            persistence_database_mode.DatabaseMessage.conversation_id == conversation_id
        )
        if status:
            stmt = stmt.where(persistence_database_mode.DatabaseMessage.status == status)

        total_stmt = sqlalchemy.select(func.count()).select_from(stmt.subquery())
        total = int((await self.ap.persistence_mgr.execute_async(total_stmt)).scalar() or 0)
        result = await self.ap.persistence_mgr.execute_async(
            stmt.order_by(
                persistence_database_mode.DatabaseMessage.sent_at.desc(),
                persistence_database_mode.DatabaseMessage.id.desc(),
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        rows = []
        for row in result.all():
            if hasattr(row, '_mapping'):
                mapped = row._mapping.get(persistence_database_mode.DatabaseMessage)
                rows.append(mapped if mapped is not None else row)
            else:
                rows.append(row)
        messages = [self._serialize_message(row) for row in rows]
        return {
            'messages': messages,
            'total': total,
            'page': page,
            'page_size': page_size,
            'stats': await self._get_conversation_stats(conversation_id),
        }

    async def generate_draft(self, message_id: int) -> dict:
        """Generate draft using unified processing service (delegates to formal pipeline)."""
        if not hasattr(self.ap, 'database_mode_processing_service') or self.ap.database_mode_processing_service is None:
            raise ValueError('Database mode processing service is unavailable')

        # Find the unique enabled bot for this message's connector
        message = await self._require_message(message_id)
        conversation = await self._fetch_required_model(
            persistence_database_mode.DatabaseConversation,
            sqlalchemy.select(persistence_database_mode.DatabaseConversation).where(
                persistence_database_mode.DatabaseConversation.id == message.conversation_id
            ),
            error_message='Conversation not found',
        )

        bot_uuid = await self._find_enabled_bot_for_connector(conversation.connector_id)
        if bot_uuid is None:
            raise ValueError(f'No enabled wxwork_database bot found for connector {conversation.connector_id}')

        result = await self.ap.database_mode_processing_service.generate_draft(
            message_id, bot_uuid, trigger='manual'
        )

        if result.get('status') == 'succeeded':
            return await self.get_message(message_id)
        elif result.get('status') == 'already_succeeded':
            return await self.get_message(message_id)
        elif result.get('status') == 'processing':
            raise ValueError('Message is already being processed')
        else:
            raise ValueError('Failed to generate draft')

    async def _find_enabled_bot_for_connector(self, connector_id: str) -> str | None:
        """Find the unique enabled wxwork_database bot for a connector."""
        # If bot_service is available, use it (supports both production and test scenarios)
        if hasattr(self.ap, 'bot_service') and self.ap.bot_service is not None:
            try:
                bots = await self.ap.bot_service.get_bots(include_secret=True)
                for bot in bots:
                    if (bot.get('adapter') == 'wxwork_database'
                        and bot.get('enable', False)
                        and bot.get('adapter_config', {}).get('connector_id') == connector_id):
                        return bot.get('uuid')
            except Exception:
                pass

        # Fallback: direct database query (production path when bot_service not mocked)
        from ..entity.persistence import bot as persistence_bot

        try:
            result = await self.ap.persistence_mgr.execute_async(
                sqlalchemy.select(persistence_bot.Bot.uuid, persistence_bot.Bot.adapter_config)
                .where(
                    persistence_bot.Bot.adapter == 'wxwork_database',
                    persistence_bot.Bot.enable == True,
                )
            )
            rows = result.all()
            for row in rows:
                config = row.adapter_config if hasattr(row, 'adapter_config') else row[1]
                if isinstance(config, dict) and config.get('connector_id') == connector_id:
                    return row.uuid if hasattr(row, 'uuid') else row[0]
        except Exception:
            pass

        return None


    async def update_draft(self, message_id: int, draft_text: str, draft_source: str | None = None) -> dict:
        if not str(draft_text or '').strip():
            raise ValueError('draft_text is required')
        message = await self._require_message(message_id)
        async with self._transaction() as conn:
            await conn.execute(
                sqlalchemy.update(persistence_database_mode.DatabaseMessage)
                .where(persistence_database_mode.DatabaseMessage.id == message_id)
                .values(
                    {
                        'status': MESSAGE_STATUS_DRAFT_READY,
                        'draft_text': draft_text,
                        'draft_source': draft_source or 'manual',
                        'last_error': None,
                        'updated_at': self._utcnow(),
                    }
                )
            )
        await self._publish_event(
            DatabaseModeEventType.MESSAGE_UPDATED,
            conversation_id=int(message.conversation_id),
            message_id=message_id,
        )
        return await self.get_message(message_id)

    async def process_message(self, message_id: int) -> dict:
        message = await self._require_message(message_id)
        async with self._transaction() as conn:
            await self._set_message_status(
                message_id,
                MESSAGE_STATUS_PROCESSED,
                conn=conn,
                processed_at=self._utcnow(),
                attempt_count=int(message.attempt_count or 0) + 1,
                last_error=None,
            )
        await self._publish_event(
            DatabaseModeEventType.MESSAGE_UPDATED,
            conversation_id=int(message.conversation_id),
            message_id=message_id,
        )
        return await self.get_message(message_id)

    async def skip_message(self, message_id: int) -> dict:
        message = await self._require_message(message_id)
        async with self._transaction() as conn:
            await self._set_message_status(
                message_id,
                MESSAGE_STATUS_SKIPPED,
                conn=conn,
                processed_at=self._utcnow(),
                last_error=None,
            )
        await self._publish_event(
            DatabaseModeEventType.MESSAGE_UPDATED,
            conversation_id=int(message.conversation_id),
            message_id=message_id,
        )
        return await self.get_message(message_id)

    async def delete_message(self, message_id: int) -> None:
        message = await self._require_message(message_id)
        async with self._transaction() as conn:
            await conn.execute(
                sqlalchemy.delete(persistence_database_mode.DatabaseMessage).where(
                    persistence_database_mode.DatabaseMessage.id == message_id
                )
            )
        await self._publish_event(
            DatabaseModeEventType.MESSAGE_DELETED,
            conversation_id=int(message.conversation_id),
            message_id=message_id,
        )

    async def batch_process(self, message_ids: list[int]) -> dict:
        normalized_ids = self._normalize_message_ids(message_ids)
        async with self._transaction() as conn:
            for message_id in normalized_ids:
                message = await self._require_message(message_id, conn=conn)
                await self._set_message_status(
                    message_id,
                    MESSAGE_STATUS_PROCESSED,
                    conn=conn,
                    processed_at=self._utcnow(),
                    attempt_count=int(message.attempt_count or 0) + 1,
                    last_error=None,
                )
        results = [await self.get_message(message_id) for message_id in normalized_ids]
        await self._publish_event(DatabaseModeEventType.INVALIDATED)
        return {'messages': results}

    async def batch_skip(self, message_ids: list[int]) -> dict:
        normalized_ids = self._normalize_message_ids(message_ids)
        async with self._transaction() as conn:
            for message_id in normalized_ids:
                await self._require_message(message_id, conn=conn)
                await self._set_message_status(
                    message_id,
                    MESSAGE_STATUS_SKIPPED,
                    conn=conn,
                    processed_at=self._utcnow(),
                    last_error=None,
                )
        results = [await self.get_message(message_id) for message_id in normalized_ids]
        await self._publish_event(DatabaseModeEventType.INVALIDATED)
        return {'messages': results}

    async def batch_delete(self, message_ids: list[int]) -> dict:
        normalized_ids = self._normalize_message_ids(message_ids)
        async with self._transaction() as conn:
            for message_id in normalized_ids:
                await self._require_message(message_id, conn=conn)
                await conn.execute(
                    sqlalchemy.delete(persistence_database_mode.DatabaseMessage).where(
                        persistence_database_mode.DatabaseMessage.id == message_id
                    )
                )
        await self._publish_event(DatabaseModeEventType.INVALIDATED)
        return {'deleted_ids': normalized_ids}

    async def get_message(self, message_id: int) -> dict:
        message = await self._require_message(message_id)
        return self._serialize_message(message)

    async def _get_or_create_conversation(
        self,
        *,
        connector_id: str,
        source: str,
        external_conversation_id: str,
        conversation_name: str,
        conversation_type: str,
        last_message_at: datetime.datetime,
        conn=None,
    ) -> dict:
        existing = await self._fetch_optional_model(
            persistence_database_mode.DatabaseConversation,
            sqlalchemy.select(persistence_database_mode.DatabaseConversation).where(
                persistence_database_mode.DatabaseConversation.connector_id == connector_id,
                persistence_database_mode.DatabaseConversation.external_conversation_id == external_conversation_id,
            ),
            conn=conn,
        )
        if existing is None:
            await self._execute(
                sqlalchemy.insert(persistence_database_mode.DatabaseConversation).values(
                    {
                        'connector_id': connector_id,
                        'source': source,
                        'external_conversation_id': external_conversation_id,
                        'conversation_name': conversation_name,
                        'conversation_type': conversation_type,
                        'last_message_at': last_message_at,
                    }
                ),
                conn=conn,
            )
        else:
            await self._execute(
                sqlalchemy.update(persistence_database_mode.DatabaseConversation)
                .where(persistence_database_mode.DatabaseConversation.id == existing.id)
                .values(
                    {
                        'conversation_name': conversation_name,
                        'conversation_type': conversation_type,
                        'last_message_at': last_message_at,
                        'updated_at': self._utcnow(),
                    }
                ),
                conn=conn,
            )

        refreshed = await self._fetch_required_model(
            persistence_database_mode.DatabaseConversation,
            sqlalchemy.select(persistence_database_mode.DatabaseConversation).where(
                persistence_database_mode.DatabaseConversation.connector_id == connector_id,
                persistence_database_mode.DatabaseConversation.external_conversation_id == external_conversation_id,
            ),
            error_message='Conversation not found after upsert',
            conn=conn,
        )
        return self._serialize_model(persistence_database_mode.DatabaseConversation, refreshed)

    async def _get_latest_message_for_conversation(self, conversation_id: int) -> dict | None:
        row = await self._fetch_optional_model(
            persistence_database_mode.DatabaseMessage,
            sqlalchemy.select(persistence_database_mode.DatabaseMessage)
            .where(persistence_database_mode.DatabaseMessage.conversation_id == conversation_id)
            .order_by(
                persistence_database_mode.DatabaseMessage.sent_at.desc(),
                persistence_database_mode.DatabaseMessage.id.desc(),
            )
            .limit(1),
        )
        if row is None:
            return None
        return self._serialize_message(row)

    async def _get_conversation_stats(self, conversation_id: int) -> dict:
        stmt = (
            sqlalchemy.select(
                persistence_database_mode.DatabaseMessage.status,
                func.count().label('count'),
            )
            .where(persistence_database_mode.DatabaseMessage.conversation_id == conversation_id)
            .group_by(persistence_database_mode.DatabaseMessage.status)
        )
        rows = (await self.ap.persistence_mgr.execute_async(stmt)).all()
        stats = {status: 0 for status in sorted(MESSAGE_STATUSES)}
        total = 0
        for row in rows:
            count = int(row.count or 0)
            stats[row.status] = count
            total += count
        stats['total'] = total
        return stats

    async def _require_message(self, message_id: int, conn=None):
        return await self._fetch_required_model(
            persistence_database_mode.DatabaseMessage,
            sqlalchemy.select(persistence_database_mode.DatabaseMessage).where(
                persistence_database_mode.DatabaseMessage.id == message_id
            ),
            error_message='Message not found',
            conn=conn,
        )

    async def _set_message_status(self, message_id: int, status: str, *, conn=None, **changes) -> None:
        await self._execute(
            sqlalchemy.update(persistence_database_mode.DatabaseMessage)
            .where(persistence_database_mode.DatabaseMessage.id == message_id)
            .values({'status': status, 'updated_at': self._utcnow(), **changes}),
            conn=conn,
        )

    async def _execute(self, stmt, *, conn=None):
        if conn is not None:
            return await conn.execute(stmt)
        return await self.ap.persistence_mgr.execute_async(stmt)

    async def _fetch_optional_model(self, model, stmt, conn=None):
        result = await self._execute(stmt, conn=conn)
        try:
            keys = list(result.keys())
        except Exception:
            keys = []
        if len(keys) == 1 and keys[0] == model.__name__:
            scalar_result = result.scalars()
            return scalar_result.first()
        row = result.first()
        if row is None:
            return None
        if hasattr(row, '_mapping'):
            mapped = row._mapping.get(model)
            if mapped is not None:
                return mapped
        return row

    async def _fetch_required_model(self, model, stmt, *, error_message: str, conn=None):
        instance = await self._fetch_optional_model(model, stmt, conn=conn)
        if instance is None:
            raise ValueError(error_message)
        return instance

    def _serialize_model(self, model, instance) -> dict:
        serialized = {}
        for column in model.__table__.columns:
            value = getattr(instance, column.name)
            if isinstance(value, datetime.datetime):
                serialized[column.name] = self._to_iso(value)
            else:
                serialized[column.name] = value
        return serialized

    def _serialize_message(self, message: object) -> dict:
        data = self._serialize_model(persistence_database_mode.DatabaseMessage, message)
        data['ai_suggested_reply'] = data.get('draft_text') or ''
        data['content_preview'] = self._summarize_text(data.get('content') or '')
        return data

    @staticmethod
    def _message_content_to_text(content: object) -> str:
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, dict) and item.get('text'):
                    parts.append(str(item['text']))
                else:
                    text = getattr(item, 'text', None)
                    if text:
                        parts.append(str(text))
            return '\n'.join(part.strip() for part in parts if part).strip()
        return str(content or '').strip()

    @staticmethod
    def _parse_datetime(value: object) -> datetime.datetime:
        if isinstance(value, datetime.datetime):
            return value.replace(tzinfo=None)
        text = str(value or '').strip()
        if not text:
            return DatabaseModeService._utcnow()
        normalized = text[:-1] + '+00:00' if text.endswith('Z') else text
        parsed = datetime.datetime.fromisoformat(normalized)
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone(datetime.timezone.utc).replace(tzinfo=None)
        return parsed

    @staticmethod
    def _to_iso(value: object) -> str | None:
        if isinstance(value, datetime.datetime):
            if value.tzinfo is None:
                value = value.replace(tzinfo=datetime.timezone.utc)
            else:
                value = value.astimezone(datetime.timezone.utc)
            return value.isoformat()
        return None

    async def _publish_event(
        self,
        event_type: DatabaseModeEventType,
        *,
        conversation_id: int | None = None,
        message_id: int | None = None,
        metadata: dict | None = None,
    ) -> dict | None:
        if getattr(self.ap, 'database_mode_event_bus', None) is None:
            return metadata
        bus = self.ap.database_mode_event_bus
        published_metadata = dict(metadata or {})
        timings = published_metadata.get('timings')
        if isinstance(timings, dict):
            timings = dict(timings)
            timings['sse_published_at'] = self._to_iso(self._utcnow())
            published_metadata['timings'] = timings
        event = DatabaseModeEvent(
            type=event_type,
            conversation_id=conversation_id,
            message_id=message_id,
            occurred_at=self._to_iso(self._utcnow()),
            metadata=published_metadata or None,
        )
        self._log_event(
            'database_event_publish_requested',
            event_id=event.event_id,
            event_type=event.type.value,
            conversation_id=conversation_id,
            message_id=message_id,
            event_bus_instance_id=getattr(bus, 'instance_id', None),
            subscriber_count=getattr(bus, 'subscriber_count', None),
        )
        await bus.publish(event)
        self._log_event(
            'database_event_published',
            event_id=event.event_id,
            event_type=event.type.value,
            conversation_id=conversation_id,
            message_id=message_id,
            event_bus_instance_id=getattr(bus, 'instance_id', None),
            subscriber_count=getattr(bus, 'subscriber_count', None),
        )
        self._log_event(
            'event_published',
            event_id=event.event_id,
            event_type=event.type.value,
            conversation_id=conversation_id,
            message_id=message_id,
            event_bus_instance_id=getattr(bus, 'instance_id', None),
            subscriber_count=getattr(bus, 'subscriber_count', None),
        )
        return published_metadata

    async def _maybe_schedule_auto_draft(self, message_id: int, conversation_id: int) -> None:
        """Schedule automatic draft generation if conditions are met."""
        try:
            # Get conversation to find connector_id
            conversation = await self._fetch_optional_model(
                persistence_database_mode.DatabaseConversation,
                sqlalchemy.select(persistence_database_mode.DatabaseConversation).where(
                    persistence_database_mode.DatabaseConversation.id == conversation_id
                ),
            )
            if conversation is None:
                return

            # Find enabled bot for this connector
            bot_uuid = await self._find_enabled_bot_for_connector(conversation.connector_id)
            if bot_uuid is None:
                self._log_event(
                    'auto_draft_skipped_no_bot',
                    message_id=message_id,
                    connector_id=conversation.connector_id,
                )
                return

            # Get bot and binding details
            from ..entity.persistence import bot as persistence_bot

            bot = await self._fetch_optional_model(
                persistence_bot.Bot,
                sqlalchemy.select(persistence_bot.Bot).where(persistence_bot.Bot.uuid == bot_uuid),
            )
            if bot is None or not bot.enable:
                return

            # Get channel account and binding
            channel_account_result = await self.ap.persistence_mgr.execute_async(
                sqlalchemy.select(persistence_database_mode.ChannelAccount.id)
                .join(
                    persistence_database_mode.BotChannelBinding,
                    persistence_database_mode.BotChannelBinding.channel_account_id == persistence_database_mode.ChannelAccount.id,
                )
                .where(persistence_database_mode.BotChannelBinding.bot_uuid == bot_uuid)
            )
            channel_account_id = channel_account_result.scalar()
            if channel_account_id is None:
                return

            binding_result = await self.ap.persistence_mgr.execute_async(
                sqlalchemy.select(persistence_database_mode.BotChannelBinding)
                .where(
                    persistence_database_mode.BotChannelBinding.bot_uuid == bot_uuid,
                    persistence_database_mode.BotChannelBinding.channel_account_id == channel_account_id,
                )
            )
            binding = binding_result.scalars().first()
            if binding is None or not binding.enabled or not binding.auto_generate_draft:
                self._log_event(
                    'auto_draft_skipped_disabled',
                    message_id=message_id,
                    bot_uuid=bot_uuid,
                    binding_enabled=binding.enabled if binding else None,
                    auto_generate=binding.auto_generate_draft if binding else None,
                )
                return

            # Check processing boundary
            message = await self._fetch_optional_model(
                persistence_database_mode.DatabaseMessage,
                sqlalchemy.select(persistence_database_mode.DatabaseMessage).where(
                    persistence_database_mode.DatabaseMessage.id == message_id
                ),
            )
            if message is None:
                return

            if binding.effective_from is not None and message.observed_at < binding.effective_from:
                self._log_event(
                    'auto_draft_skipped_boundary',
                    message_id=message_id,
                    bot_uuid=bot_uuid,
                    observed_at=self._to_iso(message.observed_at),
                    effective_from=self._to_iso(binding.effective_from),
                )
                return

            # Schedule the task
            if not hasattr(self.ap, 'task_mgr') or self.ap.task_mgr is None:
                self._log_event('auto_draft_skipped_no_task_mgr', message_id=message_id)
                return

            if not hasattr(self.ap, 'database_mode_processing_service') or self.ap.database_mode_processing_service is None:
                self._log_event('auto_draft_skipped_no_processing_service', message_id=message_id)
                return

            async def auto_draft_task():
                try:
                    self._log_event(
                        'auto_draft_started',
                        message_id=message_id,
                        bot_uuid=bot_uuid,
                    )
                    await self.ap.database_mode_processing_service.generate_draft(
                        message_id, bot_uuid, trigger='automatic'
                    )
                    self._log_event(
                        'auto_draft_succeeded',
                        message_id=message_id,
                        bot_uuid=bot_uuid,
                    )
                except Exception as exc:
                    self._log_event(
                        'auto_draft_failed',
                        message_id=message_id,
                        bot_uuid=bot_uuid,
                        error=str(exc)[:200],
                    )

            self.ap.task_mgr.create_task(
                auto_draft_task(),
                name=f'auto-draft-{message_id}',
                kind='database-mode-auto-draft',
            )
            self._log_event(
                'auto_draft_scheduled',
                message_id=message_id,
                bot_uuid=bot_uuid,
            )

        except Exception as exc:
            self._log_event(
                'auto_draft_schedule_error',
                message_id=message_id,
                error=str(exc)[:200],
            ) or None

    @asynccontextmanager
    async def _transaction(self):
        async with self.ap.persistence_mgr.get_db_engine().begin() as conn:
            yield conn

    def _log_event(self, event_name: str, **payload) -> None:
        logger = getattr(self.ap, 'logger', None)
        if logger is None:
            return
        details = ' '.join(
            f'{key}={value}'
            for key, value in payload.items()
            if value is not None
        )
        logger.info(f'{event_name}{(" " + details) if details else ""}')

    @staticmethod
    def _message_key_hash(message_key: str) -> str:
        return hashlib.sha256(message_key.encode('utf-8')).hexdigest()[:16]

    @staticmethod
    def _string_or_none(value: object) -> str | None:
        text = str(value or '').strip()
        return text or None

    @staticmethod
    def _utcnow() -> datetime.datetime:
        return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)

    @staticmethod
    def _normalize_page(page: int, page_size: int, *, max_page_size: int = 100) -> tuple[int, int]:
        page = max(1, int(page or 1))
        page_size = max(1, min(max_page_size, int(page_size or 20)))
        return page, page_size

    @staticmethod
    def _normalize_status_filter(status: str | None) -> str | None:
        value = (status or '').strip()
        if not value or value == 'all':
            return None
        if value not in MESSAGE_STATUSES:
            raise ValueError('Invalid status filter')
        return value

    @staticmethod
    def _normalize_message_ids(message_ids: list[int]) -> list[int]:
        if not isinstance(message_ids, list) or not message_ids:
            raise ValueError('message_ids is required')
        normalized = []
        for raw_id in message_ids:
            message_id = int(raw_id)
            if message_id <= 0:
                raise ValueError('message_ids must contain positive integers')
            normalized.append(message_id)
        return normalized

    @staticmethod
    def _summarize_text(text: str, limit: int = 80) -> str:
        normalized = ' '.join((text or '').split())
        if len(normalized) <= limit:
            return normalized
        return normalized[: limit - 3] + '...'
