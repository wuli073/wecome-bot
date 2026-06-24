from __future__ import annotations

import datetime
from dataclasses import dataclass

import sqlalchemy
from sqlalchemy import func

from langbot_plugin.api.entities.builtin.provider import message as provider_message

from ..core import app
from ..entity.persistence import database_mode as persistence_database_mode


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

        source = str(payload.get('source') or 'wxwork').strip() or 'wxwork'
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
            return EventIngestResult(accepted=True, duplicate=True, event_id=event_id)

        existing_message = await self._fetch_optional_model(
            persistence_database_mode.DatabaseMessage,
            sqlalchemy.select(persistence_database_mode.DatabaseMessage).where(
                persistence_database_mode.DatabaseMessage.message_key == message_key
            ),
        )
        if existing_message is not None:
            await self.ap.persistence_mgr.execute_async(
                sqlalchemy.insert(persistence_database_mode.LocalConnectorEvent).values(
                    {
                        'event_id': event_id,
                        'connector_id': connector_id,
                        'message_key': message_key,
                        'status': MESSAGE_STATUS_PROCESSED,
                        'received_at': observed_at,
                        'processed_at': datetime.datetime.utcnow(),
                    }
                )
            )
            return EventIngestResult(accepted=True, duplicate=True, event_id=event_id)

        await self.ap.persistence_mgr.execute_async(
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
            )

            await self.ap.persistence_mgr.execute_async(
                sqlalchemy.insert(persistence_database_mode.DatabaseMessage).values(
                    {
                        'event_id': event_id,
                        'message_key': message_key,
                        'conversation_id': conversation['id'],
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
            await self.ap.persistence_mgr.execute_async(
                sqlalchemy.update(persistence_database_mode.LocalConnectorEvent)
                .where(persistence_database_mode.LocalConnectorEvent.event_id == event_id)
                .values(
                    {
                        'status': MESSAGE_STATUS_PROCESSED,
                        'processed_at': datetime.datetime.utcnow(),
                        'last_error': None,
                    }
                )
            )
        except Exception as exc:
            await self.ap.persistence_mgr.execute_async(
                sqlalchemy.update(persistence_database_mode.LocalConnectorEvent)
                .where(persistence_database_mode.LocalConnectorEvent.event_id == event_id)
                .values(
                    {
                        'status': MESSAGE_STATUS_FAILED,
                        'last_error': str(exc),
                    }
                )
            )
            raise

        return EventIngestResult(accepted=True, duplicate=False, event_id=event_id)

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
        message = await self._require_message(message_id)
        model = self.ap.model_mgr.llm_models[0] if getattr(self.ap.model_mgr, 'llm_models', None) else None
        if model is None:
            raise ValueError('No LLM model is available')

        conversation = await self.get_conversation(int(message.conversation_id))
        prompt_messages = [
            provider_message.Message(
                role='system',
                content=(
                    'You are assisting a human operator handling enterprise chat messages. '
                    'Write a concise, polite reply draft in the same language as the customer message. '
                    'Do not mention automation.'
                ),
            ),
            provider_message.Message(
                role='user',
                content=(
                    f"Conversation: {conversation.get('conversation_name', '')}\n"
                    f"Sender: {message.sender_name}\n"
                    f"Customer message:\n{message.content}"
                ),
            ),
        ]
        result = await model.provider.invoke_llm(
            query=None,
            model=model,
            messages=prompt_messages,
            funcs=[],
            extra_args={},
        )
        draft_text = self._message_content_to_text(result.content)
        await self.ap.persistence_mgr.execute_async(
            sqlalchemy.update(persistence_database_mode.DatabaseMessage)
            .where(persistence_database_mode.DatabaseMessage.id == message_id)
            .values(
                {
                    'status': MESSAGE_STATUS_DRAFT_READY,
                    'draft_text': draft_text,
                    'draft_source': 'ai',
                    'last_error': None,
                    'updated_at': datetime.datetime.utcnow(),
                }
            )
        )
        return await self.get_message(message_id)

    async def update_draft(self, message_id: int, draft_text: str, draft_source: str | None = None) -> dict:
        if not str(draft_text or '').strip():
            raise ValueError('draft_text is required')
        await self._require_message(message_id)
        await self.ap.persistence_mgr.execute_async(
            sqlalchemy.update(persistence_database_mode.DatabaseMessage)
            .where(persistence_database_mode.DatabaseMessage.id == message_id)
            .values(
                {
                    'status': MESSAGE_STATUS_DRAFT_READY,
                    'draft_text': draft_text,
                    'draft_source': draft_source or 'manual',
                    'last_error': None,
                    'updated_at': datetime.datetime.utcnow(),
                }
            )
        )
        return await self.get_message(message_id)

    async def process_message(self, message_id: int) -> dict:
        message = await self._require_message(message_id)
        await self._set_message_status(
            message_id,
            MESSAGE_STATUS_PROCESSED,
            processed_at=datetime.datetime.utcnow(),
            attempt_count=int(message.attempt_count or 0) + 1,
            last_error=None,
        )
        return await self.get_message(message_id)

    async def skip_message(self, message_id: int) -> dict:
        await self._require_message(message_id)
        await self._set_message_status(
            message_id,
            MESSAGE_STATUS_SKIPPED,
            processed_at=datetime.datetime.utcnow(),
            last_error=None,
        )
        return await self.get_message(message_id)

    async def delete_message(self, message_id: int) -> None:
        await self._require_message(message_id)
        await self.ap.persistence_mgr.execute_async(
            sqlalchemy.delete(persistence_database_mode.DatabaseMessage).where(
                persistence_database_mode.DatabaseMessage.id == message_id
            )
        )

    async def batch_process(self, message_ids: list[int]) -> dict:
        normalized_ids = self._normalize_message_ids(message_ids)
        results = []
        for message_id in normalized_ids:
            results.append(await self.process_message(message_id))
        return {'messages': results}

    async def batch_skip(self, message_ids: list[int]) -> dict:
        normalized_ids = self._normalize_message_ids(message_ids)
        results = []
        for message_id in normalized_ids:
            results.append(await self.skip_message(message_id))
        return {'messages': results}

    async def batch_delete(self, message_ids: list[int]) -> dict:
        normalized_ids = self._normalize_message_ids(message_ids)
        for message_id in normalized_ids:
            await self.delete_message(message_id)
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
    ) -> dict:
        existing = await self._fetch_optional_model(
            persistence_database_mode.DatabaseConversation,
            sqlalchemy.select(persistence_database_mode.DatabaseConversation).where(
                persistence_database_mode.DatabaseConversation.connector_id == connector_id,
                persistence_database_mode.DatabaseConversation.external_conversation_id == external_conversation_id,
            ),
        )
        if existing is None:
            await self.ap.persistence_mgr.execute_async(
                sqlalchemy.insert(persistence_database_mode.DatabaseConversation).values(
                    {
                        'connector_id': connector_id,
                        'source': source,
                        'external_conversation_id': external_conversation_id,
                        'conversation_name': conversation_name,
                        'conversation_type': conversation_type,
                        'last_message_at': last_message_at,
                    }
                )
            )
        else:
            await self.ap.persistence_mgr.execute_async(
                sqlalchemy.update(persistence_database_mode.DatabaseConversation)
                .where(persistence_database_mode.DatabaseConversation.id == existing.id)
                .values(
                    {
                        'conversation_name': conversation_name,
                        'conversation_type': conversation_type,
                        'last_message_at': last_message_at,
                        'updated_at': datetime.datetime.utcnow(),
                    }
                )
            )

        refreshed = await self._fetch_required_model(
            persistence_database_mode.DatabaseConversation,
            sqlalchemy.select(persistence_database_mode.DatabaseConversation).where(
                persistence_database_mode.DatabaseConversation.connector_id == connector_id,
                persistence_database_mode.DatabaseConversation.external_conversation_id == external_conversation_id,
            ),
            error_message='Conversation not found after upsert',
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

    async def _require_message(self, message_id: int):
        return await self._fetch_required_model(
            persistence_database_mode.DatabaseMessage,
            sqlalchemy.select(persistence_database_mode.DatabaseMessage).where(
                persistence_database_mode.DatabaseMessage.id == message_id
            ),
            error_message='Message not found',
        )

    async def _set_message_status(self, message_id: int, status: str, **changes) -> None:
        await self.ap.persistence_mgr.execute_async(
            sqlalchemy.update(persistence_database_mode.DatabaseMessage)
            .where(persistence_database_mode.DatabaseMessage.id == message_id)
            .values({'status': status, 'updated_at': datetime.datetime.utcnow(), **changes})
        )

    async def _fetch_optional_model(self, model, stmt):
        result = await self.ap.persistence_mgr.execute_async(stmt)
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

    async def _fetch_required_model(self, model, stmt, *, error_message: str):
        instance = await self._fetch_optional_model(model, stmt)
        if instance is None:
            raise ValueError(error_message)
        return instance

    def _serialize_model(self, model, instance) -> dict:
        return self.ap.persistence_mgr.serialize_model(model, instance)

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
            return datetime.datetime.utcnow()
        normalized = text[:-1] + '+00:00' if text.endswith('Z') else text
        parsed = datetime.datetime.fromisoformat(normalized)
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone(datetime.timezone.utc).replace(tzinfo=None)
        return parsed

    @staticmethod
    def _to_iso(value: object) -> str | None:
        if isinstance(value, datetime.datetime):
            return value.isoformat()
        return None

    @staticmethod
    def _string_or_none(value: object) -> str | None:
        text = str(value or '').strip()
        return text or None

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
