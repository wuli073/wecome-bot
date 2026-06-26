from __future__ import annotations

import asyncio
import datetime
import logging
from contextlib import asynccontextmanager
from types import SimpleNamespace

import sqlalchemy
from sqlalchemy.exc import IntegrityError

import langbot_plugin.api.entities.builtin.platform.events as platform_events
import langbot_plugin.api.entities.builtin.platform.message as platform_message
from ..entity.persistence import database_mode as persistence_database_mode
from .conversation_type import (
    CANONICAL_DIRECT_CONVERSATION_TYPE,
    normalize_conversation_type,
)
from .events import DatabaseModeEvent, DatabaseModeEventType
from ..platform.sources.wxwork_database import DraftCapture, WXWorkDatabaseAdapter


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

    @staticmethod
    def _select_model_columns(model):
        return sqlalchemy.select(*model.__table__.columns)

    async def _fetch_namespace_one(self, statement, *, error_message: str | None = None, conn=None):
        result = await self._execute(statement, conn=conn)
        row = result.mappings().first()
        if row is None:
            if error_message is None:
                return None
            raise ValueError(error_message)
        return SimpleNamespace(**dict(row))

    async def _execute(self, stmt, *, conn=None):
        if conn is not None:
            return await conn.execute(stmt)
        return await self.ap.persistence_mgr.execute_async(stmt)

    @asynccontextmanager
    async def _transaction(self):
        async with self.ap.persistence_mgr.get_db_engine().begin() as conn:
            yield conn

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
        normalized_conversation_type = normalize_conversation_type(conversation.conversation_type)
        is_private_conversation = normalized_conversation_type == CANONICAL_DIRECT_CONVERSATION_TYPE

        if bot.adapter != 'wxwork_database':
            raise ValueError(f'Bot {bot_uuid} is not a wxwork_database bot')

        channel_account = await self._get_channel_account_for_bot(bot_uuid)
        if channel_account is None:
            raise ValueError(f'No channel account bound to bot {bot_uuid}')

        binding = await self._get_bot_channel_binding(bot_uuid, int(channel_account.id))
        if binding is None:
            raise ValueError(f'Bot {bot_uuid} is not bound to the channel account')

        if not bot.enable:
            raise ValueError(f'Bot {bot_uuid} is disabled')

        if not binding.enabled:
            raise ValueError(f'Binding for bot {bot_uuid} is disabled')

        run_id = None
        pipeline_uuid = None
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

            await self._safe_publish_message_event(
                conversation_id=int(message.conversation_id),
                message_id=message_id,
                metadata={
                    'processing_status': MESSAGE_STATUS_PROCESSING,
                    'bot_uuid': bot_uuid,
                    'run_id': run_id,
                    'trigger': trigger,
                },
            )

            runtime_bot = await self._get_runtime_bot(bot_uuid)
            if runtime_bot is None:
                raise ValueError(f'RuntimeBot {bot_uuid} not found in platform manager')

            launcher_type = 'person' if is_private_conversation else 'group'
            launcher_id = conversation.external_conversation_id

            pipeline_uuid, routed_by_rule = runtime_bot.resolve_pipeline_uuid(
                launcher_type=launcher_type,
                launcher_id=launcher_id,
                message_text=message.content,
                message_element_types=['Plain'],
            )

            if pipeline_uuid is None:
                raise ValueError(f'No pipeline configured for bot {bot_uuid}')

            message_chain = platform_message.MessageChain([
                platform_message.Plain(text=message.content)
            ])

            if is_private_conversation:
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
                        'group': {
                            'id': conversation.external_conversation_id,
                            'name': conversation.conversation_name,
                            'permission': 'MEMBER',
                        },
                    },
                    message_chain=message_chain,
                )

            pipeline = await self.ap.pipeline_mgr.get_pipeline_by_uuid(pipeline_uuid)
            if pipeline is None:
                raise ValueError(f'Pipeline {pipeline_uuid} not found')

            pipeline_result = None
            adapter_capture = None
            query = None
            final_query = None

            if not self._can_use_formal_runtime_entry(runtime_bot):
                raise RuntimeError(
                    f'RuntimeBot {bot_uuid} does not support formal immediate processing for pipeline {pipeline_uuid}'
                )

            if isinstance(runtime_bot.adapter, WXWorkDatabaseAdapter):
                with runtime_bot.adapter.capture_draft_output(
                    run_id=run_id,
                    query_id=None,
                    message_id=message_id,
                ) as capture:
                    adapter_capture = capture
                    final_query = await runtime_bot.process_message_event_now(
                        message_event,
                        adapter=runtime_bot.adapter,
                        pipeline_uuid_override=pipeline_uuid,
                        routed_by_rule_override=routed_by_rule,
                    )
                    query = final_query
                    if query is None:
                        raise ValueError(f'Pipeline {pipeline_uuid} was skipped before query creation')
                    capture.query_id = getattr(query, 'query_id', None)
            else:
                final_query = await runtime_bot.process_message_event_now(
                    message_event,
                    adapter=runtime_bot.adapter,
                    pipeline_uuid_override=pipeline_uuid,
                    routed_by_rule_override=routed_by_rule,
                )
                query = final_query
                if query is None:
                    raise ValueError(f'Pipeline {pipeline_uuid} was skipped before query creation')

            final_query = self._resolve_pipeline_final_query(
                original_query=query,
                pipeline_result=pipeline_result,
                fallback_query=final_query,
            )
            self._log_pipeline_diagnostics(
                bot_uuid=bot_uuid,
                message_id=message_id,
                run_id=run_id,
                pipeline_uuid=pipeline_uuid,
                pipeline_result=pipeline_result,
                original_query=query,
                final_query=final_query,
                adapter_capture=adapter_capture,
                runtime_adapter=getattr(runtime_bot, 'adapter', None),
            )

            draft_text = self._resolve_pipeline_output(
                pipeline_uuid=pipeline_uuid,
                original_query=query,
                final_query=final_query,
                pipeline_result=pipeline_result,
                adapter_capture=adapter_capture,
            )
            if not draft_text:
                raise ValueError(f'Pipeline {pipeline_uuid} completed without a text response')

            async with self._transaction() as conn:
                draft_id = await self._save_draft(
                    run_id=run_id,
                    message_id=message_id,
                    bot_uuid=bot_uuid,
                    content=draft_text,
                    source=DRAFT_SOURCE_PIPELINE,
                    conn=conn,
                )
                await self._mark_run_succeeded(run_id, pipeline_uuid=pipeline_uuid, conn=conn)
                await self._update_message_draft_ready(
                    message_id,
                    draft_text,
                    DRAFT_SOURCE_PIPELINE,
                    conn=conn,
                )

            await self._safe_publish_message_event(
                conversation_id=int(message.conversation_id),
                message_id=message_id,
                metadata={
                    'processing_status': MESSAGE_STATUS_DRAFT_READY,
                    'bot_uuid': bot_uuid,
                    'run_id': run_id,
                    'draft_source': DRAFT_SOURCE_PIPELINE,
                },
            )

            draft = await self._require_draft(draft_id)
            run = await self._require_run(run_id)

            return {
                'status': 'succeeded',
                'draft': self._serialize_draft(draft),
                'run': self._serialize_run(run),
            }

        except Exception as exc:
            original_exc = exc
            if run_id is not None:
                try:
                    async with self._transaction() as conn:
                        await self._mark_run_failed(
                            run_id,
                            str(original_exc),
                            pipeline_uuid=pipeline_uuid,
                            conn=conn,
                        )
                        await self._update_message_failed(
                            message_id,
                            str(original_exc),
                            conn=conn,
                        )
                except Exception:
                    self._log_exception('Failed to persist database draft failure state')

            try:
                await self._publish_message_event(
                    conversation_id=int(message.conversation_id),
                    message_id=message_id,
                    metadata={
                        'processing_status': MESSAGE_STATUS_FAILED,
                        'bot_uuid': bot_uuid,
                        'run_id': run_id,
                        'last_error': self._safe_error_text(str(original_exc)),
                    },
                )
            except Exception:
                self._log_exception('Failed to publish database draft failure event')

            raise original_exc

    def _resolve_pipeline_final_query(self, *, original_query, pipeline_result, fallback_query=None):
        # Some direct/unit-tested pipeline implementations return a stage-like
        # object with new_query even though RuntimePipeline.run() returns None.
        if pipeline_result is not None:
            new_query = getattr(pipeline_result, 'new_query', None)
            if self._looks_like_query(new_query):
                return new_query
            if self._looks_like_query(pipeline_result):
                return pipeline_result
        if self._looks_like_query(fallback_query):
            return fallback_query
        return original_query

    def _resolve_pipeline_output(
        self,
        *,
        pipeline_uuid: str,
        original_query,
        final_query,
        pipeline_result,
        adapter_capture: DraftCapture | None,
    ) -> str:
        candidates = [
            getattr(pipeline_result, 'new_query', None) if pipeline_result is not None else None,
            pipeline_result,
            final_query,
            original_query,
        ]

        for candidate in candidates:
            text = self._extract_response_text(candidate)
            if text:
                return text

        if adapter_capture is not None and adapter_capture.text:
            return adapter_capture.text

        return ''

    def _can_use_formal_runtime_entry(self, runtime_bot) -> bool:
        return bool(
            runtime_bot is not None
            and hasattr(runtime_bot, 'process_message_event_now')
            and callable(getattr(runtime_bot, 'process_message_event_now'))
        )

    def _extract_response_text(self, query) -> str:
        if query is None:
            return ''

        if isinstance(query, str):
            return query.strip()

        if isinstance(query, platform_message.MessageChain):
            return self._extract_message_chain_text(query)

        if isinstance(query, list):
            return self._join_text_parts(self._extract_component_text(item) for item in query)

        if hasattr(query, 'resp_message_chain') and query.resp_message_chain:
            return self._join_text_parts(
                self._extract_component_text(component)
                for component in query.resp_message_chain
            )

        if hasattr(query, 'resp_messages') and query.resp_messages:
            return self._join_text_parts(
                self._extract_provider_message_text(message)
                for message in query.resp_messages
            )

        return self._extract_component_text(query)

    def _extract_provider_message_text(self, message) -> str:
        if message is None:
            return ''
        if isinstance(message, str):
            return message.strip()
        if hasattr(message, 'get_content_platform_message_chain'):
            try:
                chain = message.get_content_platform_message_chain()
            except Exception:
                chain = None
            text = self._extract_message_chain_text(chain)
            if text:
                return text
        for attr in ('all_content', 'content'):
            if hasattr(message, attr):
                text = self._extract_component_text(getattr(message, attr))
                if text:
                    return text
        return self._extract_component_text(message)

    def _extract_message_chain_text(self, chain) -> str:
        if chain is None:
            return ''
        return self._join_text_parts(self._extract_component_text(component) for component in chain)

    def _extract_component_text(self, component) -> str:
        if component is None:
            return ''
        if isinstance(component, str):
            return component.strip()
        if isinstance(component, platform_message.MessageChain):
            return self._extract_message_chain_text(component)
        if isinstance(component, list):
            return self._join_text_parts(self._extract_component_text(item) for item in component)
        if isinstance(component, platform_message.Plain):
            return (component.text or '').strip()
        if hasattr(component, 'text'):
            return str(getattr(component, 'text') or '').strip()
        return ''

    @staticmethod
    def _join_text_parts(parts) -> str:
        return '\n'.join(part.strip() for part in parts if isinstance(part, str) and part.strip()).strip()

    @staticmethod
    def _looks_like_query(candidate) -> bool:
        if candidate is None:
            return False
        return hasattr(candidate, 'resp_message_chain') or hasattr(candidate, 'resp_messages')

    def _log_pipeline_diagnostics(
        self,
        *,
        bot_uuid: str,
        message_id: int,
        run_id: int | None,
        pipeline_uuid: str | None,
        pipeline_result,
        original_query,
        final_query,
        adapter_capture: DraftCapture | None,
        runtime_adapter=None,
    ) -> None:
        logger = getattr(self.ap, 'logger', None)
        if logger is None:
            return

        payload = {
            'event': 'database_mode_pipeline_output',
            'bot_uuid': bot_uuid,
            'message_id': message_id,
            'run_id': run_id,
            'pipeline_uuid': pipeline_uuid,
            'original_query_id': getattr(original_query, 'query_id', None),
            'final_query_id': getattr(final_query, 'query_id', None),
            'pipeline_result_type': type(pipeline_result).__name__ if pipeline_result is not None else None,
            'pipeline_result_has_new_query': bool(getattr(pipeline_result, 'new_query', None))
            if pipeline_result is not None
            else False,
            'runtime_adapter_type': type(runtime_adapter).__name__ if runtime_adapter is not None else None,
            'runtime_adapter_id': id(runtime_adapter) if runtime_adapter is not None else None,
            'query_adapter_type': type(getattr(original_query, 'adapter', None)).__name__
            if getattr(original_query, 'adapter', None) is not None
            else None,
            'query_adapter_id': id(getattr(original_query, 'adapter', None))
            if getattr(original_query, 'adapter', None) is not None
            else None,
            'capture_adapter_type': type(runtime_adapter).__name__
            if adapter_capture is not None and runtime_adapter is not None
            else None,
            'capture_adapter_id': id(runtime_adapter)
            if adapter_capture is not None and runtime_adapter is not None
            else None,
            'capture_context_visible': bool(adapter_capture.context_visible) if adapter_capture else False,
            'original_query_has_resp_message_chain': bool(getattr(original_query, 'resp_message_chain', None)),
            'original_query_has_resp_messages': bool(getattr(original_query, 'resp_messages', None)),
            'final_query_type': type(final_query).__name__ if final_query is not None else None,
            'final_query_has_resp_message_chain': bool(getattr(final_query, 'resp_message_chain', None)),
            'final_query_has_resp_messages': bool(getattr(final_query, 'resp_messages', None)),
            'original_query_resp_message_count': self._resp_message_count(original_query),
            'final_query_resp_message_count': self._resp_message_count(final_query),
            'query_response_component_count': self._response_component_count(final_query),
            'adapter_reply_called': bool(adapter_capture.reply_called) if adapter_capture else False,
            'adapter_reply_chunk_called': bool(adapter_capture.reply_chunk_called) if adapter_capture else False,
            'adapter_chunk_count': int(adapter_capture.chunk_count) if adapter_capture else 0,
            'adapter_final_received': bool(adapter_capture.final_received) if adapter_capture else False,
            'adapter_captured_text_length': len(adapter_capture.text) if adapter_capture and adapter_capture.text else 0,
            'output_stage_entered': self._output_stage_entered(final_query) or self._output_stage_entered(original_query),
            'stage_trace': self._stage_trace(final_query) or self._stage_trace(original_query),
        }

        log_method = getattr(logger, 'info', None) or getattr(logger, 'debug', None)
        if callable(log_method):
            try:
                log_method(payload)
            except TypeError:
                log_method(str(payload))

    @staticmethod
    def _response_component_count(query) -> int:
        if query is None:
            return 0
        if hasattr(query, 'resp_message_chain') and query.resp_message_chain:
            return len(query.resp_message_chain)
        if hasattr(query, 'resp_messages') and query.resp_messages:
            return len(query.resp_messages)
        return 0

    @staticmethod
    def _resp_message_count(query) -> int:
        if query is None or not hasattr(query, 'resp_messages') or not query.resp_messages:
            return 0
        return len(query.resp_messages)

    @staticmethod
    def _output_stage_entered(query) -> bool:
        if query is None or not hasattr(query, 'variables') or not isinstance(query.variables, dict):
            return False
        return bool(query.variables.get('_output_stage_entered'))

    @staticmethod
    def _stage_trace(query) -> list[dict]:
        if query is None or not hasattr(query, 'variables') or not isinstance(query.variables, dict):
            return []
        trace = query.variables.get('_stage_trace')
        return trace if isinstance(trace, list) else []

    async def _atomic_claim_processing(self, message_id: int, bot_uuid: str, trigger: str) -> int | None:
        try:
            async with self._transaction() as conn:
                existing_run = await self._get_latest_run(message_id, bot_uuid, conn=conn)
                if existing_run is not None and existing_run.status in {
                    RUN_STATUS_PROCESSING,
                    RUN_STATUS_SUCCEEDED,
                }:
                    return None

                attempt_count = 1
                if existing_run is not None:
                    attempt_count = int(existing_run.attempt_count or 0) + 1

                result = await conn.execute(
                    sqlalchemy.insert(persistence_database_mode.MessageProcessingRun).values({
                        'message_id': message_id,
                        'bot_uuid': bot_uuid,
                        'pipeline_uuid': None,
                        'trigger': trigger,
                        'status': RUN_STATUS_PROCESSING,
                        'attempt_count': attempt_count,
                        'started_at': self._utcnow(),
                        'completed_at': None,
                        'last_error': None,
                    })
                )
                await self._update_message_processing(message_id, attempt_count=attempt_count, conn=conn)
                inserted_primary_key = getattr(result, 'inserted_primary_key', None) or ()
                if inserted_primary_key:
                    return int(inserted_primary_key[0])
                return int(result.lastrowid)
        except IntegrityError:
            return None

    async def _update_run_pipeline(self, run_id: int, pipeline_uuid: str, *, conn=None) -> None:
        await self._execute(
            sqlalchemy.update(persistence_database_mode.MessageProcessingRun)
            .where(persistence_database_mode.MessageProcessingRun.id == run_id)
            .values({
                'pipeline_uuid': pipeline_uuid,
                'updated_at': self._utcnow(),
            }),
            conn=conn,
        )

    async def _mark_run_succeeded(self, run_id: int, *, pipeline_uuid: str | None = None, conn=None) -> None:
        values = {
            'status': RUN_STATUS_SUCCEEDED,
            'completed_at': self._utcnow(),
            'last_error': None,
            'updated_at': self._utcnow(),
        }
        if pipeline_uuid is not None:
            values['pipeline_uuid'] = pipeline_uuid
        await self._execute(
            sqlalchemy.update(persistence_database_mode.MessageProcessingRun)
            .where(persistence_database_mode.MessageProcessingRun.id == run_id)
            .values(values),
            conn=conn,
        )

    async def _mark_run_failed(self, run_id: int, error: str, *, pipeline_uuid: str | None = None, conn=None) -> None:
        values = {
            'status': RUN_STATUS_FAILED,
            'completed_at': self._utcnow(),
            'last_error': self._safe_error_text(error),
            'updated_at': self._utcnow(),
        }
        if pipeline_uuid is not None:
            values['pipeline_uuid'] = pipeline_uuid
        await self._execute(
            sqlalchemy.update(persistence_database_mode.MessageProcessingRun)
            .where(persistence_database_mode.MessageProcessingRun.id == run_id)
            .values(values),
            conn=conn,
        )

    async def _supersede_active_drafts(self, message_id: int, bot_uuid: str, *, conn=None) -> None:
        await self._execute(
            sqlalchemy.update(persistence_database_mode.ReplyDraft)
            .where(
                persistence_database_mode.ReplyDraft.message_id == message_id,
                persistence_database_mode.ReplyDraft.bot_uuid == bot_uuid,
                persistence_database_mode.ReplyDraft.status == DRAFT_STATUS_ACTIVE,
            )
            .values({
                'status': DRAFT_STATUS_SUPERSEDED,
                'updated_at': self._utcnow(),
            }),
            conn=conn,
        )

    async def _create_reply_draft(
        self,
        run_id: int,
        message_id: int,
        bot_uuid: str,
        content: str,
        source: str,
        *,
        conn=None,
    ) -> int:
        max_version_result = await self._execute(
            sqlalchemy.select(sqlalchemy.func.max(persistence_database_mode.ReplyDraft.version))
            .where(
                persistence_database_mode.ReplyDraft.message_id == message_id,
                persistence_database_mode.ReplyDraft.bot_uuid == bot_uuid,
            ),
            conn=conn,
        )
        max_version = max_version_result.scalar() or 0
        new_version = int(max_version) + 1

        result = await self._execute(
            sqlalchemy.insert(persistence_database_mode.ReplyDraft).values({
                'processing_run_id': run_id,
                'message_id': message_id,
                'bot_uuid': bot_uuid,
                'content': content,
                'source': source,
                'version': new_version,
                'status': DRAFT_STATUS_ACTIVE,
            }),
            conn=conn,
        )
        inserted_primary_key = getattr(result, 'inserted_primary_key', None) or ()
        if inserted_primary_key:
            return int(inserted_primary_key[0])
        return int(result.lastrowid)

    async def _save_draft(
        self,
        run_id: int,
        message_id: int,
        bot_uuid: str,
        content: str,
        source: str,
        *,
        conn=None,
    ) -> int:
        await self._supersede_active_drafts(message_id, bot_uuid, conn=conn)
        return await self._create_reply_draft(
            run_id,
            message_id,
            bot_uuid,
            content,
            source,
            conn=conn,
        )

    async def _update_message_processing(self, message_id: int, *, attempt_count: int, conn=None) -> None:
        await self._execute(
            sqlalchemy.update(persistence_database_mode.DatabaseMessage)
            .where(persistence_database_mode.DatabaseMessage.id == message_id)
            .values({
                'status': MESSAGE_STATUS_PROCESSING,
                'attempt_count': attempt_count,
                'last_error': None,
                'updated_at': self._utcnow(),
            }),
            conn=conn,
        )

    async def _update_message_draft_ready(
        self,
        message_id: int,
        draft_text: str,
        draft_source: str,
        *,
        conn=None,
    ) -> None:
        await self._execute(
            sqlalchemy.update(persistence_database_mode.DatabaseMessage)
            .where(persistence_database_mode.DatabaseMessage.id == message_id)
            .values({
                'status': MESSAGE_STATUS_DRAFT_READY,
                'draft_text': draft_text,
                'draft_source': draft_source,
                'last_error': None,
                'updated_at': self._utcnow(),
            }),
            conn=conn,
        )

    async def _update_message_failed(self, message_id: int, error: str, *, conn=None) -> None:
        await self._execute(
            sqlalchemy.update(persistence_database_mode.DatabaseMessage)
            .where(persistence_database_mode.DatabaseMessage.id == message_id)
            .values({
                'status': MESSAGE_STATUS_FAILED,
                'last_error': self._safe_error_text(error),
                'updated_at': self._utcnow(),
            }),
            conn=conn,
        )

    async def _get_latest_run(self, message_id: int, bot_uuid: str, *, conn=None):
        return await self._fetch_namespace_one(
            self._select_model_columns(persistence_database_mode.MessageProcessingRun)
            .where(
                persistence_database_mode.MessageProcessingRun.message_id == message_id,
                persistence_database_mode.MessageProcessingRun.bot_uuid == bot_uuid,
            )
            .order_by(persistence_database_mode.MessageProcessingRun.id.desc())
            .limit(1),
            conn=conn,
        )

    async def _get_active_draft(self, message_id: int, bot_uuid: str, *, conn=None):
        return await self._fetch_namespace_one(
            self._select_model_columns(persistence_database_mode.ReplyDraft)
            .where(
                persistence_database_mode.ReplyDraft.message_id == message_id,
                persistence_database_mode.ReplyDraft.bot_uuid == bot_uuid,
                persistence_database_mode.ReplyDraft.status == DRAFT_STATUS_ACTIVE,
            )
            .limit(1),
            conn=conn,
        )

    async def _require_message(self, message_id: int, *, conn=None):
        return await self._fetch_namespace_one(
            self._select_model_columns(persistence_database_mode.DatabaseMessage).where(
                persistence_database_mode.DatabaseMessage.id == message_id
            ),
            error_message=f'Message {message_id} not found',
            conn=conn,
        )

    async def _require_conversation(self, conversation_id: int, *, conn=None):
        return await self._fetch_namespace_one(
            self._select_model_columns(persistence_database_mode.DatabaseConversation).where(
                persistence_database_mode.DatabaseConversation.id == conversation_id
            ),
            error_message=f'Conversation {conversation_id} not found',
            conn=conn,
        )

    async def _require_bot(self, bot_uuid: str):
        if hasattr(self.ap, 'bot_service') and self.ap.bot_service:
            try:
                bot_dict = await self.ap.bot_service.get_bot(bot_uuid, include_secret=False)
                if bot_dict:
                    return SimpleNamespace(**bot_dict)
            except Exception:
                pass

        from ..entity.persistence import bot as persistence_bot

        return await self._fetch_namespace_one(
            self._select_model_columns(persistence_bot.Bot).where(persistence_bot.Bot.uuid == bot_uuid),
            error_message=f'Bot {bot_uuid} not found',
        )

    async def _get_channel_account_for_bot(self, bot_uuid: str, *, conn=None):
        return await self._fetch_namespace_one(
            self._select_model_columns(persistence_database_mode.ChannelAccount)
            .join(
                persistence_database_mode.BotChannelBinding,
                persistence_database_mode.BotChannelBinding.channel_account_id
                == persistence_database_mode.ChannelAccount.id,
            )
            .where(persistence_database_mode.BotChannelBinding.bot_uuid == bot_uuid)
            .limit(1),
            conn=conn,
        )

    async def _get_bot_channel_binding(self, bot_uuid: str, channel_account_id: int, *, conn=None):
        return await self._fetch_namespace_one(
            self._select_model_columns(persistence_database_mode.BotChannelBinding)
            .where(
                persistence_database_mode.BotChannelBinding.bot_uuid == bot_uuid,
                persistence_database_mode.BotChannelBinding.channel_account_id == channel_account_id,
            )
            .limit(1),
            conn=conn,
        )

    async def _get_runtime_bot(self, bot_uuid: str):
        if not hasattr(self.ap, 'platform_mgr') or self.ap.platform_mgr is None:
            return None
        for runtime_bot in self.ap.platform_mgr.bots:
            if runtime_bot.bot_entity.uuid == bot_uuid:
                return runtime_bot
        return None

    async def _require_draft(self, draft_id: int, *, conn=None):
        return await self._fetch_namespace_one(
            self._select_model_columns(persistence_database_mode.ReplyDraft).where(
                persistence_database_mode.ReplyDraft.id == draft_id
            ),
            error_message=f'Draft {draft_id} not found',
            conn=conn,
        )

    async def _require_run(self, run_id: int, *, conn=None):
        return await self._fetch_namespace_one(
            self._select_model_columns(persistence_database_mode.MessageProcessingRun).where(
                persistence_database_mode.MessageProcessingRun.id == run_id
            ),
            error_message=f'Run {run_id} not found',
            conn=conn,
        )

    def _serialize_draft(self, draft) -> dict:
        return self.ap.persistence_mgr.serialize_model(persistence_database_mode.ReplyDraft, draft)

    def _serialize_run(self, run) -> dict:
        return self.ap.persistence_mgr.serialize_model(persistence_database_mode.MessageProcessingRun, run)

    async def _publish_message_event(
        self,
        *,
        conversation_id: int | None,
        message_id: int | None,
        metadata: dict | None = None,
    ) -> None:
        bus = getattr(self.ap, 'database_mode_event_bus', None)
        if bus is None:
            return
        event = DatabaseModeEvent(
            type=DatabaseModeEventType.MESSAGE_UPDATED,
            conversation_id=conversation_id,
            message_id=message_id,
            occurred_at=self._to_iso(self._utcnow()),
            metadata=metadata or None,
        )
        await bus.publish(event)

    async def _safe_publish_message_event(
        self,
        *,
        conversation_id: int | None,
        message_id: int | None,
        metadata: dict | None = None,
    ) -> None:
        try:
            await self._publish_message_event(
                conversation_id=conversation_id,
                message_id=message_id,
                metadata=metadata,
            )
        except Exception:
            self._log_exception('Failed to publish database draft event')

    def _log_exception(self, message: str) -> None:
        logger = getattr(self.ap, 'logger', None)
        if logger is None:
            return
        log_method = getattr(logger, 'exception', None)
        if callable(log_method):
            log_method(message)
            return
        log_method = getattr(logger, 'error', None)
        if callable(log_method):
            log_method(message)

    @staticmethod
    def _safe_error_text(error: str) -> str:
        return (error or '')[:5000]

    @staticmethod
    def _utcnow() -> datetime.datetime:
        return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)

    @staticmethod
    def _to_iso(value: object) -> str | None:
        if isinstance(value, datetime.datetime):
            if value.tzinfo is None:
                value = value.replace(tzinfo=datetime.timezone.utc)
            else:
                value = value.astimezone(datetime.timezone.utc)
            return value.isoformat()
        return None
