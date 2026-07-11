from __future__ import annotations

import datetime
from types import SimpleNamespace
from typing import Any

import sqlalchemy
from sqlalchemy.exc import IntegrityError

from ..entity.persistence import database_mode as persistence_database_mode
from .errors import DesktopAutomationError, TASK_CONFLICT


ACTIVE_DESKTOP_RUN_STATUSES = ('queued', 'starting', 'running')


class DesktopAutomationRepository:
    def __init__(self, persistence_mgr) -> None:
        self.persistence_mgr = persistence_mgr

    async def get_message_context(self, bot_uuid: str, message_id: int, draft_id: int) -> dict[str, Any]:
        from ..entity.persistence import bot as persistence_bot

        bot_result = await self.persistence_mgr.execute_async(
            sqlalchemy.select(persistence_bot.Bot).where(persistence_bot.Bot.uuid == bot_uuid)
        )
        bot = self._first_model(bot_result)

        message_result = await self.persistence_mgr.execute_async(
            sqlalchemy.select(persistence_database_mode.DatabaseMessage).where(
                persistence_database_mode.DatabaseMessage.id == message_id
            )
        )
        message = self._first_model(message_result)
        if message is None:
            raise ValueError('Message not found')

        conversation_result = await self.persistence_mgr.execute_async(
            sqlalchemy.select(persistence_database_mode.DatabaseConversation).where(
                persistence_database_mode.DatabaseConversation.id == message.conversation_id
            )
        )
        conversation = self._first_model(conversation_result)
        if conversation is None:
            raise ValueError('Conversation not found')

        draft_result = await self.persistence_mgr.execute_async(
            sqlalchemy.select(persistence_database_mode.ReplyDraft).where(
                persistence_database_mode.ReplyDraft.id == draft_id
            )
        )
        draft = self._first_model(draft_result)
        if draft is None:
            raise ValueError('Draft not found')

        channel_account_result = await self.persistence_mgr.execute_async(
            sqlalchemy.select(persistence_database_mode.ChannelAccount)
            .join(
                persistence_database_mode.BotChannelBinding,
                persistence_database_mode.BotChannelBinding.channel_account_id
                == persistence_database_mode.ChannelAccount.id,
            )
            .where(persistence_database_mode.BotChannelBinding.bot_uuid == bot_uuid)
            .limit(1)
        )
        channel_account = self._first_model(channel_account_result)
        if channel_account is None:
            raise ValueError('Channel account not found')

        binding_result = await self.persistence_mgr.execute_async(
            sqlalchemy.select(persistence_database_mode.BotChannelBinding).where(
                persistence_database_mode.BotChannelBinding.bot_uuid == bot_uuid,
                persistence_database_mode.BotChannelBinding.channel_account_id == int(channel_account.id),
            )
        )
        binding = self._first_model(binding_result)

        active_draft_result = await self.persistence_mgr.execute_async(
            sqlalchemy.select(persistence_database_mode.ReplyDraft)
            .where(
                persistence_database_mode.ReplyDraft.message_id == message_id,
                persistence_database_mode.ReplyDraft.bot_uuid == bot_uuid,
                persistence_database_mode.ReplyDraft.status == 'active',
            )
            .order_by(persistence_database_mode.ReplyDraft.id.desc())
        )
        active_draft_rows = self._all_models(active_draft_result)
        active_draft = active_draft_rows[0] if active_draft_rows else None

        active_run_result = await self.persistence_mgr.execute_async(
            sqlalchemy.select(persistence_database_mode.DesktopAutomationRun)
            .where(
                persistence_database_mode.DesktopAutomationRun.message_id == message_id,
                persistence_database_mode.DesktopAutomationRun.draft_id == draft_id,
                persistence_database_mode.DesktopAutomationRun.status.in_(ACTIVE_DESKTOP_RUN_STATUSES),
            )
            .order_by(persistence_database_mode.DesktopAutomationRun.id.desc())
            .limit(1)
        )
        latest_succeeded_send_run_result = await self.persistence_mgr.execute_async(
            sqlalchemy.select(persistence_database_mode.DesktopAutomationRun)
            .where(
                persistence_database_mode.DesktopAutomationRun.message_id == message_id,
                persistence_database_mode.DesktopAutomationRun.draft_id == draft_id,
                persistence_database_mode.DesktopAutomationRun.action == 'send_draft',
                persistence_database_mode.DesktopAutomationRun.status == 'succeeded',
            )
            .order_by(persistence_database_mode.DesktopAutomationRun.id.desc())
            .limit(1)
        )

        return {
            'bot': self._serialize_optional(persistence_bot.Bot, bot),
            'message': self._serialize_optional(persistence_database_mode.DatabaseMessage, message),
            'conversation': self._serialize_optional(persistence_database_mode.DatabaseConversation, conversation),
            'draft': self._serialize_optional(persistence_database_mode.ReplyDraft, draft),
            'channel_account': self._serialize_optional(persistence_database_mode.ChannelAccount, channel_account),
            'binding': self._serialize_optional(persistence_database_mode.BotChannelBinding, binding),
            'active_draft': self._serialize_optional(persistence_database_mode.ReplyDraft, active_draft),
            'active_draft_count': len(active_draft_rows),
            'active_run': self._serialize_optional(
                persistence_database_mode.DesktopAutomationRun,
                self._first_model(active_run_result),
            ),
            'latest_succeeded_send_run': self._serialize_optional(
                persistence_database_mode.DesktopAutomationRun,
                self._first_model(latest_succeeded_send_run_result),
            ),
        }

    async def create_run(self, payload: dict[str, Any]):
        try:
            result = await self.persistence_mgr.execute_async(
                sqlalchemy.insert(persistence_database_mode.DesktopAutomationRun).values(payload)
            )
        except IntegrityError as exc:
            raise DesktopAutomationError(TASK_CONFLICT, 'an active desktop automation run already exists') from exc
        run_id = int((getattr(result, 'inserted_primary_key', None) or [result.lastrowid])[0])
        return await self._require_run(run_id)

    async def update_run_status(self, run_id: int, **changes):
        values = dict(changes)
        values.setdefault('updated_at', self._utcnow())
        if values.get('status') in {'waiting_manual', 'blocked', 'failed', 'cancelled', 'timed_out', 'succeeded'}:
            values.setdefault('completed_at', self._utcnow())
        if values.get('status') == 'running':
            values.setdefault('started_at', self._utcnow())
        await self.persistence_mgr.execute_async(
            sqlalchemy.update(persistence_database_mode.DesktopAutomationRun)
            .where(persistence_database_mode.DesktopAutomationRun.id == run_id)
            .values(values)
        )
        return await self._require_run(run_id)

    async def get_run_for_bot(self, run_id: int, bot_uuid: str):
        result = await self.persistence_mgr.execute_async(
            sqlalchemy.select(persistence_database_mode.DesktopAutomationRun).where(
                persistence_database_mode.DesktopAutomationRun.id == run_id,
                persistence_database_mode.DesktopAutomationRun.bot_uuid == bot_uuid,
            )
        )
        return self._first_model(result)

    async def count_conversations_by_name(self, connector_id: str, conversation_name: str) -> int:
        result = await self.persistence_mgr.execute_async(
            sqlalchemy.select(sqlalchemy.func.count(persistence_database_mode.DatabaseConversation.id)).where(
                persistence_database_mode.DatabaseConversation.connector_id == connector_id,
                persistence_database_mode.DatabaseConversation.conversation_name == conversation_name,
            )
        )
        scalar = getattr(result, 'scalar', None)
        value = scalar() if callable(scalar) else 0
        return int(value or 0)

    async def get_run(self, run_id: int):
        result = await self.persistence_mgr.execute_async(
            sqlalchemy.select(persistence_database_mode.DesktopAutomationRun).where(
                persistence_database_mode.DesktopAutomationRun.id == run_id
            )
        )
        return self._first_model(result)

    async def find_run_by_request_digest(self, request_digest: str):
        result = await self.persistence_mgr.execute_async(
            sqlalchemy.select(persistence_database_mode.DesktopAutomationRun)
            .where(persistence_database_mode.DesktopAutomationRun.request_digest == request_digest)
            .order_by(persistence_database_mode.DesktopAutomationRun.id.desc())
            .limit(1)
        )
        return self._first_model(result)

    async def reconcile_stale_runs(self, stale_seconds: int):
        cutoff = self._utcnow() - datetime.timedelta(seconds=stale_seconds)
        await self.persistence_mgr.execute_async(
            sqlalchemy.update(persistence_database_mode.DesktopAutomationRun)
            .where(
                persistence_database_mode.DesktopAutomationRun.status.in_(ACTIVE_DESKTOP_RUN_STATUSES),
                sqlalchemy.func.coalesce(
                    persistence_database_mode.DesktopAutomationRun.started_at,
                    persistence_database_mode.DesktopAutomationRun.created_at,
                )
                < cutoff,
            )
            .values(
                {
                    'status': 'failed',
                    'stage': 'failed',
                    'last_error_code': 'STALE_RUN_RECOVERED',
                    'last_error_message': 'Stale desktop automation run recovered after timeout',
                    'completed_at': self._utcnow(),
                    'updated_at': self._utcnow(),
                }
            )
        )
        return []

    async def get_bot_connector_id(self, bot_uuid: str) -> str | None:
        result = await self.persistence_mgr.execute_async(
            sqlalchemy.select(persistence_database_mode.ChannelAccount.connector_id)
            .join(
                persistence_database_mode.BotChannelBinding,
                persistence_database_mode.BotChannelBinding.channel_account_id
                == persistence_database_mode.ChannelAccount.id,
            )
            .where(persistence_database_mode.BotChannelBinding.bot_uuid == bot_uuid)
            .limit(1)
        )
        scalar = getattr(result, 'scalar', None)
        connector_id = scalar() if callable(scalar) else None
        return str(connector_id) if connector_id is not None else None

    async def _require_run(self, run_id: int):
        result = await self.persistence_mgr.execute_async(
            sqlalchemy.select(persistence_database_mode.DesktopAutomationRun).where(
                persistence_database_mode.DesktopAutomationRun.id == run_id
            )
        )
        run = self._first_model(result)
        if run is None:
            raise ValueError(f'Run {run_id} not found')
        return run

    def _serialize_optional(self, model, instance):
        if instance is None:
            return None
        if hasattr(instance, '__table__'):
            return self.persistence_mgr.serialize_model(model, instance)
        if isinstance(instance, SimpleNamespace):
            return vars(instance)
        return self.persistence_mgr.serialize_model(model, instance)

    @staticmethod
    def _first_model(result):
        first = getattr(result, 'first', None)
        row = first() if callable(first) else None
        return DesktopAutomationRepository._coerce_row(row)

    @staticmethod
    def _all_models(result):
        all_rows = getattr(result, 'all', None)
        rows = all_rows() if callable(all_rows) else list(result)
        return [DesktopAutomationRepository._coerce_row(row) for row in rows]

    @staticmethod
    def _coerce_row(row):
        if row is None:
            return None
        if hasattr(row, '__table__') or isinstance(row, SimpleNamespace):
            return row
        mapping = getattr(row, '_mapping', None)
        if mapping is not None:
            values = dict(mapping)
            if len(values) == 1:
                first_value = next(iter(values.values()))
                if hasattr(first_value, '__table__') or isinstance(first_value, SimpleNamespace):
                    return first_value
                return first_value
            return SimpleNamespace(**values)
        if isinstance(row, tuple) and len(row) == 1:
            return row[0]
        return row

    @staticmethod
    def _utcnow() -> datetime.datetime:
        return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
