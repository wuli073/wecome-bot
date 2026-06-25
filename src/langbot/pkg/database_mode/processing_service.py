from __future__ import annotations

import asyncio
import datetime
import traceback
from types import SimpleNamespace

import sqlalchemy
from sqlalchemy.exc import IntegrityError

import langbot_plugin.api.entities.builtin.platform.events as platform_events
import langbot_plugin.api.entities.builtin.platform.message as platform_message
import langbot_plugin.api.entities.builtin.provider.session as provider_session

from ..entity.persistence import database_mode as persistence_database_mode


RUN_STATUS_PROCESSING = 'processing'
RUN_STATUS_SUCCEEDED = 'succeeded'
RUN_STATUS_FAILED = 'failed'

DRAFT_STATUS_ACTIVE = 'active'
DRAFT_STATUS_SUPERSEDED = 'superseded'

DRAFT_SOURCE_PIPELINE = 'pipeline'
DRAFT_SOURCE_MANUAL = 'manual'

MESSAGE_STATUS_PENDING = 'pending'
MESSAGE_STATUS_DRAFT_READY = 'draft_ready'
MESSAGE_STATUS_PROCESSING = 'processing'
MESSAGE_STATUS_FAILED = 'failed'


class DatabaseModeProcessingService:
    """Unified processing service for database mode messages via formal RuntimeBot/Pipeline."""

    def __init__(self, ap) -> None:
        self.ap = ap
        self._processing_locks = {}
        self._lock_creation_lock = asyncio.Lock()

    async def _get_message_lock(self, message_id: int, bot_uuid: str) -> asyncio.Lock:
        key = f'{message_id}:{bot_uuid}'
        async with self._lock_creation_lock:
            if key not in self._processing_locks:
                self._processing_locks[key] = asyncio.Lock()
            return self._processing_locks[key]

    async def generate_draft(self, message_id: int, bot_uuid: str, *, trigger: str = 'manual') -> dict:
        """Generate draft for a database message using formal RuntimeBot/Pipeline path."""
        lock = await self._get_message_lock(message_id, bot_uuid)
        async with lock:
            return await self._generate_draft_impl(message_id, bot_uuid, trigger=trigger)

    async def _generate_draft_impl(self, message_id: int, bot_uuid: str, trigger: str) -> dict:
        message = await self._require_message(message_id)
        conversation = await self._require_conversation(int(message.conversation_id))
        bot = await self._require_bot(bot_uuid)

        if bot.adapter != 'wxwork_database':
            raise ValueError(f'Bot {bot_uuid} is not a wxwork_database bot')

        channel_account = await self._get_channel_account_for_bot(bot_uuid)
        if channel_account is None:
            raise ValueError(f'No channel account bound to bot {bot_uuid}')

        # Verify conversation belongs to this channel account's connector
        # connector_id format: "wxwork-local" or similar, channel_account links to it
        # For now, skip strict validation since connector_id structure varies

        binding = await self._get_bot_channel_binding(bot_uuid, int(channel_account.id))
        if binding is None:
            raise ValueError(f'Bot {bot_uuid} is not bound to the channel account')

        if not bot.enable:
            raise ValueError(f'Bot {bot_uuid} is disabled')

        if not binding.enabled:
            raise ValueError(f'Binding for bot {bot_uuid} is disabled')

        run_id = None
        try:
            run_id = await self._atomic_claim_processing(message_id, bot_uuid, trigger)
            if run_id is None:
                existing_run = await self._get_latest_run(message_id, bot_uuid)
                if existing_run and existing_run.status == RUN_STATUS_SUCCEEDED:
                    existing_draft = await self._get_active_draft(message_id, bot_uuid)
                    if existing_draft:
                        return {
                            'status': 'already_succeeded',
                            'draft': self._serialize_draft(existing_draft),
                            'run': self._serialize_run(existing_run),
                        }
                return {'status': 'processing', 'message': 'Another processing is in progress'}

            await self._emit_event('database-processing-started', {
                'message_id': message_id,
                'bot_uuid': bot_uuid,
                'run_id': run_id,
                'trigger': trigger,
            })

            runtime_bot = await self._get_runtime_bot(bot_uuid)
            if runtime_bot is None:
                raise ValueError(f'RuntimeBot {bot_uuid} not found in platform manager')

            launcher_type = 'person' if conversation.conversation_type == 'direct' else 'group'
            launcher_id = conversation.external_conversation_id

            pipeline_uuid, routed_by_rule = runtime_bot.resolve_pipeline_uuid(
                launcher_type=launcher_type,
                launcher_id=launcher_id,
                message_text=message.content,
                message_element_types=['Plain'],
            )

            if pipeline_uuid is None:
                raise ValueError(f'No pipeline configured for bot {bot_uuid}')

            await self._update_run_pipeline(run_id, pipeline_uuid)

            message_chain = platform_message.MessageChain([
                platform_message.Plain(text=message.content)
            ])

            if conversation.conversation_type == 'direct':
                message_event = platform_events.FriendMessage(
                    sender={
                        'id': message.sender_id,
                        'nickname': message.sender_name,
                        'remark': '',
                    },
                    message_chain=message_chain,
                )
            else:
                message_event = platform_events.GroupMessage(
                    sender={
                        'id': message.sender_id,
                        'member_name': message.sender_name,
                        'special_title': '',
                        'permission': 'MEMBER',
                        'join_timestamp': 0,
                        'last_speak_timestamp': 0,
                        'mute_time_remaining': 0,
                        'group': {'id': conversation.external_conversation_id, 'name': conversation.conversation_name, 'permission': 'MEMBER'},
                    },
                    message_chain=message_chain,
                )

            query = await self.ap.query_pool.add_query(
                bot_uuid=bot_uuid,
                launcher_type=provider_session.LauncherTypes.PERSON if launcher_type == 'person' else provider_session.LauncherTypes.GROUP,
                launcher_id=launcher_id,
                sender_id=message.sender_id,
                message_event=message_event,
                message_chain=message_chain,
                adapter=runtime_bot.adapter,
                pipeline_uuid=pipeline_uuid,
                routed_by_rule=routed_by_rule,
            )

            pipeline = await self.ap.pipeline_mgr.get_pipeline_by_uuid(pipeline_uuid)
            if pipeline is None:
                raise ValueError(f'Pipeline {pipeline_uuid} not found')

            await pipeline.run(query)

            draft_text = self._extract_response_text(query)
            if not draft_text:
                raise ValueError('Pipeline produced no response content')

            draft_id = await self._save_draft(
                run_id=run_id,
                message_id=message_id,
                bot_uuid=bot_uuid,
                content=draft_text,
                source=DRAFT_SOURCE_PIPELINE,
            )

            await self._mark_run_succeeded(run_id)
            await self._update_message_draft_ready(message_id, draft_text, DRAFT_SOURCE_PIPELINE)

            await self.ap.persistence_mgr.commit_transaction()

            await self._emit_event('database-message-updated', {
                'message_id': message_id,
                'conversation_id': int(message.conversation_id),
                'status': MESSAGE_STATUS_DRAFT_READY,
            })

            draft = await self._require_draft(draft_id)
            run = await self._require_run(run_id)

            return {
                'status': 'succeeded',
                'draft': self._serialize_draft(draft),
                'run': self._serialize_run(run),
            }

        except Exception as exc:
            if run_id is not None:
                await self._mark_run_failed(run_id, str(exc))
                await self._update_message_failed(message_id, str(exc))
                try:
                    await self.ap.persistence_mgr.commit_transaction()
                except Exception:
                    pass

            await self._emit_event('database-processing-failed', {
                'message_id': message_id,
                'bot_uuid': bot_uuid,
                'run_id': run_id,
                'error': str(exc),
            })

            raise

    def _extract_response_text(self, query) -> str:
        if hasattr(query, 'resp_message_chain') and query.resp_message_chain:
            parts = []
            for component in query.resp_message_chain:
                if isinstance(component, platform_message.Plain):
                    parts.append(component.text)
                elif hasattr(component, 'text'):
                    parts.append(str(component.text))
                else:
                    parts.append(str(component))
            return '\n'.join(p.strip() for p in parts if p).strip()

        if hasattr(query, 'resp_messages') and query.resp_messages:
            parts = []
            for msg in query.resp_messages:
                if hasattr(msg, 'content'):
                    parts.append(str(msg.content))
                else:
                    parts.append(str(msg))
            return '\n'.join(p.strip() for p in parts if p).strip()

        return ''

    async def _atomic_claim_processing(self, message_id: int, bot_uuid: str, trigger: str) -> int | None:
        try:
            result = await self.ap.persistence_mgr.execute_async(
                sqlalchemy.insert(persistence_database_mode.MessageProcessingRun).values({
                    'message_id': message_id,
                    'bot_uuid': bot_uuid,
                    'pipeline_uuid': None,
                    'trigger': trigger,
                    'status': RUN_STATUS_PROCESSING,
                    'attempt_count': 1,
                    'started_at': datetime.datetime.utcnow(),
                    'completed_at': None,
                    'last_error': None,
                })
            )
            await self.ap.persistence_mgr.commit_transaction()
            return result.inserted_primary_key[0] if hasattr(result, 'inserted_primary_key') else result.lastrowid

        except IntegrityError:
            await self.ap.persistence_mgr.rollback_transaction()
            return None

    async def _update_run_pipeline(self, run_id: int, pipeline_uuid: str) -> None:
        await self.ap.persistence_mgr.execute_async(
            sqlalchemy.update(persistence_database_mode.MessageProcessingRun)
            .where(persistence_database_mode.MessageProcessingRun.id == run_id)
            .values({'pipeline_uuid': pipeline_uuid})
        )

    async def _mark_run_succeeded(self, run_id: int) -> None:
        await self.ap.persistence_mgr.execute_async(
            sqlalchemy.update(persistence_database_mode.MessageProcessingRun)
            .where(persistence_database_mode.MessageProcessingRun.id == run_id)
            .values({
                'status': RUN_STATUS_SUCCEEDED,
                'completed_at': datetime.datetime.utcnow(),
                'last_error': None,
            })
        )

    async def _mark_run_failed(self, run_id: int, error: str) -> None:
        safe_error = (error or '')[:5000]
        await self.ap.persistence_mgr.execute_async(
            sqlalchemy.update(persistence_database_mode.MessageProcessingRun)
            .where(persistence_database_mode.MessageProcessingRun.id == run_id)
            .values({
                'status': RUN_STATUS_FAILED,
                'completed_at': datetime.datetime.utcnow(),
                'last_error': safe_error,
            })
        )

    async def _save_draft(self, run_id: int, message_id: int, bot_uuid: str, content: str, source: str) -> int:
        await self.ap.persistence_mgr.execute_async(
            sqlalchemy.update(persistence_database_mode.ReplyDraft)
            .where(
                persistence_database_mode.ReplyDraft.message_id == message_id,
                persistence_database_mode.ReplyDraft.bot_uuid == bot_uuid,
                persistence_database_mode.ReplyDraft.status == DRAFT_STATUS_ACTIVE,
            )
            .values({'status': DRAFT_STATUS_SUPERSEDED})
        )

        max_version_result = await self.ap.persistence_mgr.execute_async(
            sqlalchemy.select(sqlalchemy.func.max(persistence_database_mode.ReplyDraft.version))
            .where(
                persistence_database_mode.ReplyDraft.message_id == message_id,
                persistence_database_mode.ReplyDraft.bot_uuid == bot_uuid,
            )
        )
        max_version = max_version_result.scalar() or 0
        new_version = max_version + 1

        result = await self.ap.persistence_mgr.execute_async(
            sqlalchemy.insert(persistence_database_mode.ReplyDraft).values({
                'processing_run_id': run_id,
                'message_id': message_id,
                'bot_uuid': bot_uuid,
                'content': content,
                'source': source,
                'version': new_version,
                'status': DRAFT_STATUS_ACTIVE,
            })
        )
        return result.inserted_primary_key[0] if hasattr(result, 'inserted_primary_key') else result.lastrowid

    async def _update_message_draft_ready(self, message_id: int, draft_text: str, draft_source: str) -> None:
        await self.ap.persistence_mgr.execute_async(
            sqlalchemy.update(persistence_database_mode.DatabaseMessage)
            .where(persistence_database_mode.DatabaseMessage.id == message_id)
            .values({
                'status': MESSAGE_STATUS_DRAFT_READY,
                'draft_text': draft_text,
                'draft_source': draft_source,
                'last_error': None,
            })
        )

    async def _update_message_failed(self, message_id: int, error: str) -> None:
        safe_error = (error or '')[:5000]
        await self.ap.persistence_mgr.execute_async(
            sqlalchemy.update(persistence_database_mode.DatabaseMessage)
            .where(persistence_database_mode.DatabaseMessage.id == message_id)
            .values({
                'status': MESSAGE_STATUS_FAILED,
                'last_error': safe_error,
            })
        )

    async def _get_latest_run(self, message_id: int, bot_uuid: str):
        result = await self.ap.persistence_mgr.execute_async(
            sqlalchemy.select(persistence_database_mode.MessageProcessingRun)
            .where(
                persistence_database_mode.MessageProcessingRun.message_id == message_id,
                persistence_database_mode.MessageProcessingRun.bot_uuid == bot_uuid,
            )
            .order_by(persistence_database_mode.MessageProcessingRun.id.desc())
            .limit(1)
        )
        return result.scalars().first()

    async def _get_active_draft(self, message_id: int, bot_uuid: str):
        result = await self.ap.persistence_mgr.execute_async(
            sqlalchemy.select(persistence_database_mode.ReplyDraft)
            .where(
                persistence_database_mode.ReplyDraft.message_id == message_id,
                persistence_database_mode.ReplyDraft.bot_uuid == bot_uuid,
                persistence_database_mode.ReplyDraft.status == DRAFT_STATUS_ACTIVE,
            )
        )
        return result.scalars().first()

    async def _require_message(self, message_id: int):
        result = await self.ap.persistence_mgr.execute_async(
            sqlalchemy.select(persistence_database_mode.DatabaseMessage)
            .where(persistence_database_mode.DatabaseMessage.id == message_id)
        )
        message = result.scalars().first()
        if message is None:
            raise ValueError(f'Message {message_id} not found')
        return message

    async def _require_conversation(self, conversation_id: int):
        result = await self.ap.persistence_mgr.execute_async(
            sqlalchemy.select(persistence_database_mode.DatabaseConversation)
            .where(persistence_database_mode.DatabaseConversation.id == conversation_id)
        )
        conversation = result.scalars().first()
        if conversation is None:
            raise ValueError(f'Conversation {conversation_id} not found')
        return conversation

    async def _require_bot(self, bot_uuid: str):
        # Try bot_service first (supports mocking in tests)
        if hasattr(self.ap, 'bot_service') and self.ap.bot_service:
            try:
                bot_dict = await self.ap.bot_service.get_bot(bot_uuid, include_secret=False)
                if bot_dict:
                    # Convert dict to object-like structure
                    return SimpleNamespace(**bot_dict)
            except Exception:
                pass

        # Fallback to direct database query
        from ..entity.persistence import bot as persistence_bot
        result = await self.ap.persistence_mgr.execute_async(
            sqlalchemy.select(persistence_bot.Bot).where(persistence_bot.Bot.uuid == bot_uuid)
        )
        bot = result.scalars().first()
        if bot is None:
            raise ValueError(f'Bot {bot_uuid} not found')
        return bot

    async def _get_channel_account_for_bot(self, bot_uuid: str):
        result = await self.ap.persistence_mgr.execute_async(
            sqlalchemy.select(persistence_database_mode.ChannelAccount)
            .join(
                persistence_database_mode.BotChannelBinding,
                persistence_database_mode.BotChannelBinding.channel_account_id == persistence_database_mode.ChannelAccount.id,
            )
            .where(persistence_database_mode.BotChannelBinding.bot_uuid == bot_uuid)
        )
        return result.scalars().first()

    async def _get_bot_channel_binding(self, bot_uuid: str, channel_account_id: int):
        result = await self.ap.persistence_mgr.execute_async(
            sqlalchemy.select(persistence_database_mode.BotChannelBinding)
            .where(
                persistence_database_mode.BotChannelBinding.bot_uuid == bot_uuid,
                persistence_database_mode.BotChannelBinding.channel_account_id == channel_account_id,
            )
        )
        return result.scalars().first()

    async def _get_runtime_bot(self, bot_uuid: str):
        if not hasattr(self.ap, 'platform_mgr') or self.ap.platform_mgr is None:
            return None
        for runtime_bot in self.ap.platform_mgr.bots:
            if runtime_bot.bot_entity.uuid == bot_uuid:
                return runtime_bot
        return None

    async def _require_draft(self, draft_id: int):
        result = await self.ap.persistence_mgr.execute_async(
            sqlalchemy.select(persistence_database_mode.ReplyDraft)
            .where(persistence_database_mode.ReplyDraft.id == draft_id)
        )
        draft = result.scalars().first()
        if draft is None:
            raise ValueError(f'Draft {draft_id} not found')
        return draft

    async def _require_run(self, run_id: int):
        result = await self.ap.persistence_mgr.execute_async(
            sqlalchemy.select(persistence_database_mode.MessageProcessingRun)
            .where(persistence_database_mode.MessageProcessingRun.id == run_id)
        )
        run = result.scalars().first()
        if run is None:
            raise ValueError(f'Run {run_id} not found')
        return run

    def _serialize_draft(self, draft) -> dict:
        return self.ap.persistence_mgr.serialize_model(persistence_database_mode.ReplyDraft, draft)

    def _serialize_run(self, run) -> dict:
        return self.ap.persistence_mgr.serialize_model(persistence_database_mode.MessageProcessingRun, run)

    async def _emit_event(self, event_type: str, payload: dict) -> None:
        if hasattr(self.ap, 'database_mode_event_bus') and self.ap.database_mode_event_bus:
            await self.ap.database_mode_event_bus.emit(event_type, payload)
