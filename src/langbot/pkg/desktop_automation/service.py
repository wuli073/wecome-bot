from __future__ import annotations

import asyncio
import hashlib
from typing import Any

from .runtime_task_decoder import decode_runtime_task
from .errors import (
    DesktopAutomationError,
    DRAFT_ALREADY_SENT,
    DRAFT_CHANGED,
    DRAFT_NOT_ACTIVE,
    DRAFT_NOT_FOUND,
    DRAFT_TEXT_REQUIRED,
    CONVERSATION_NAME_NOT_UNIQUE,
    CONVERSATION_NAME_REQUIRED,
    IDEMPOTENCY_KEY_REQUIRED,
    RPA_RUNTIME_NOT_AVAILABLE,
    RUN_NOT_FOUND,
    TASK_CANCELLED,
    TASK_TIMEOUT,
)


TERMINAL_STATUSES = {'succeeded', 'succeeded_with_warning', 'blocked', 'failed', 'cancelled', 'timed_out'}
TASK_POLL_INTERVAL_SECONDS = 0.05
TASK_CANCEL_GRACE_POLLS = 10


class DesktopAutomationService:
    def __init__(
        self,
        ap,
        *,
        repository,
        runtime_client=None,
        runtime_process_manager=None,
        runtime_client_factory=None,
    ) -> None:
        self.ap = ap
        self.repository = repository
        self.runtime_client = runtime_client
        self.runtime_process_manager = runtime_process_manager
        self.runtime_client_factory = runtime_client_factory

    async def create_send_draft_run(
        self,
        bot_uuid: str,
        message_id: int,
        draft_id: int,
        *,
        explicit_frontend_send: bool = False,
        python_authorized: bool = False,
        send_strategy: str | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        if self.runtime_client is None and (
            self.runtime_process_manager is None or not hasattr(self.runtime_process_manager, 'ensure_started')
        ):
            raise DesktopAutomationError(RPA_RUNTIME_NOT_AVAILABLE, 'RPA runtime is not integrated yet')
        if not explicit_frontend_send or not python_authorized:
            raise DesktopAutomationError(
                'AUTO_SEND_NOT_AUTHORIZED', 'auto_send is disabled until explicitly authorized'
            )
        if send_strategy not in {'enter', 'ctrl_enter', 'click_send_button'}:
            raise DesktopAutomationError('SEND_STRATEGY_REQUIRED', 'send strategy is required')
        return await self._create_runtime_run(
            bot_uuid,
            message_id,
            draft_id,
            action='send_draft',
            execution_mode='auto_send',
            runtime_action='send_draft',
            extra_request={
                'sendAuthorized': True,
                'allowAutoSend': True,
                'sendStrategy': send_strategy,
            },
            idempotency_key=idempotency_key,
        )

    async def create_diagnose_run(self, bot_uuid: str, message_id: int, draft_id: int) -> dict[str, Any]:
        return await self._create_runtime_run(
            bot_uuid,
            message_id,
            draft_id,
            action='diagnose',
            execution_mode='diagnose',
            runtime_action='diagnose',
        )

    async def create_conversation_search_run(
        self,
        bot_uuid: str,
        message_id: int,
        draft_id: int,
        *,
        query_text: str,
    ) -> dict[str, Any]:
        return await self._create_runtime_run(
            bot_uuid,
            message_id,
            draft_id,
            action='conversation_search',
            execution_mode='conversation_search',
            runtime_action='conversation_search',
            extra_request={'queryText': query_text},
        )

    async def create_history_search_run(
        self,
        bot_uuid: str,
        message_id: int,
        draft_id: int,
        *,
        query_text: str,
    ) -> dict[str, Any]:
        return await self._create_runtime_run(
            bot_uuid,
            message_id,
            draft_id,
            action='history_search',
            execution_mode='history_search',
            runtime_action='history_search',
            extra_request={'queryText': query_text},
        )

    async def create_quote_reply_run(
        self,
        bot_uuid: str,
        message_id: int,
        draft_id: int,
        *,
        query_text: str,
    ) -> dict[str, Any]:
        return await self._create_runtime_run(
            bot_uuid,
            message_id,
            draft_id,
            action='quote_reply',
            execution_mode='quote_reply',
            runtime_action='quote_reply',
            extra_request={'queryText': query_text, 'sendAuthorized': False, 'allowAutoSend': False},
        )

    async def create_send_draft_dry_run(
        self,
        bot_uuid: str,
        message_id: int,
        draft_id: int,
    ) -> dict[str, Any]:
        raise DesktopAutomationError(RPA_RUNTIME_NOT_AVAILABLE, 'send dry-run is no longer supported')

    async def create_paste_draft_run(
        self,
        bot_uuid: str,
        message_id: int,
        draft_id: int,
        *,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        if not idempotency_key or not idempotency_key.strip():
            raise DesktopAutomationError(IDEMPOTENCY_KEY_REQUIRED, 'Idempotency-Key header is required')
        return await self._create_runtime_run(
            bot_uuid,
            message_id,
            draft_id,
            action='paste_draft',
            execution_mode='paste_only',
            runtime_action='paste_draft',
            extra_request={
                'idempotencyKey': idempotency_key.strip(),
            },
            idempotency_key=idempotency_key.strip(),
        )

    async def get_run(self, bot_uuid: str | None, run_id: int) -> dict[str, Any] | None:
        run = (
            await self.repository.get_run_for_bot(run_id, bot_uuid)
            if bot_uuid is not None
            else await self.repository.get_run(run_id)
        )
        if run is None:
            raise DesktopAutomationError(RUN_NOT_FOUND, 'desktop automation run not found')
        return self._serialize_run(run)

    async def cancel_run(self, bot_uuid: str | None, run_id: int) -> dict[str, Any] | None:
        run = (
            await self.repository.get_run_for_bot(run_id, bot_uuid)
            if bot_uuid
            else await self.repository.get_run(run_id)
        )
        if run is None:
            raise DesktopAutomationError(RUN_NOT_FOUND, 'desktop automation run not found')
        runtime_task_id = (
            getattr(run, 'runtime_task_id', None) if not isinstance(run, dict) else run.get('runtime_task_id')
        )
        if runtime_task_id:
            if self.runtime_client is None and (
                self.runtime_process_manager is None or not hasattr(self.runtime_process_manager, 'ensure_started')
            ):
                raise DesktopAutomationError(RPA_RUNTIME_NOT_AVAILABLE, 'RPA runtime is not integrated yet')
            client = await self._get_runtime_client()
            cancelled_task = await self._request_task_cancellation(
                str(runtime_task_id),
                client=client,
                task=None,
                cancel_error_code=TASK_CANCELLED,
            )
            return await self._apply_runtime_task_result(run_id, cancelled_task)
        updated = await self.repository.update_run_status(
            run_id,
            status='cancelled',
            stage='cancelled',
            last_error_code=TASK_CANCELLED,
            last_error_message=TASK_CANCELLED,
        )
        return self._serialize_run(updated)

    async def reconcile_stale_runs(self) -> list[Any]:
        stale_seconds = int(self.ap.instance_config.data.get('desktop_automation', {}).get('stale_run_seconds', 300))
        return await self.repository.reconcile_stale_runs(stale_seconds)

    async def get_runtime_status(self) -> dict[str, Any]:
        if self.runtime_process_manager is not None and hasattr(self.runtime_process_manager, 'get_status'):
            return await self.runtime_process_manager.get_status()
        return {
            'status': 'not_available',
            'errorCode': RPA_RUNTIME_NOT_AVAILABLE,
            'runtime_configured': False,
            'runtime_startable': False,
            'runtime_reachable': False,
            'send_enabled': False,
        }

    async def ensure_runtime_client(self):
        if self.runtime_client is not None:
            return self.runtime_client
        if self.runtime_process_manager is None or not hasattr(self.runtime_process_manager, 'ensure_started'):
            raise DesktopAutomationError(RPA_RUNTIME_NOT_AVAILABLE, 'RPA runtime is not configured')
        runtime_info = await self.runtime_process_manager.ensure_started()
        runtime_client = getattr(self.runtime_process_manager, 'client', None)
        if runtime_client is None:
            if self.runtime_client_factory is None:
                raise DesktopAutomationError(RPA_RUNTIME_NOT_AVAILABLE, 'RPA runtime client factory is not configured')
            runtime_client = self.runtime_client_factory(runtime_info)
            if hasattr(self.runtime_process_manager, 'client'):
                self.runtime_process_manager.client = runtime_client
        self.runtime_client = runtime_client
        return runtime_client

    async def get_runtime_client(self):
        return await self.ensure_runtime_client()

    async def runtime_health(self) -> dict[str, Any]:
        client = await self.ensure_runtime_client()
        return await client.health()

    async def runtime_capabilities(self) -> dict[str, Any]:
        client = await self.ensure_runtime_client()
        return await client.capabilities()

    async def runtime_create_task(self, request: dict[str, Any]) -> dict[str, Any]:
        client = await self.ensure_runtime_client()
        return await client.create_task(request=request)

    async def runtime_get_task(self, runtime_task_id: str) -> dict[str, Any]:
        client = await self.ensure_runtime_client()
        return await client.get_task(runtime_task_id)

    async def runtime_cancel_task(self, runtime_task_id: str) -> dict[str, Any]:
        client = await self.ensure_runtime_client()
        return await client.cancel_task(runtime_task_id)

    async def shutdown(self) -> None:
        if self.runtime_process_manager is not None and hasattr(self.runtime_process_manager, 'stop'):
            await self.runtime_process_manager.stop()

    def close(self) -> None:
        if self.runtime_process_manager is not None and hasattr(self.runtime_process_manager, 'close'):
            self.runtime_process_manager.close()

    async def _create_runtime_run(
        self,
        bot_uuid: str,
        message_id: int,
        draft_id: int,
        *,
        action: str,
        execution_mode: str,
        runtime_action: str,
        extra_request: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        if not hasattr(self.repository, 'get_message_context'):
            raise DesktopAutomationError(RPA_RUNTIME_NOT_AVAILABLE, 'RPA runtime is not integrated yet')
        context = await self.repository.get_message_context(bot_uuid, message_id, draft_id)
        self._validate_context(context, draft_id)
        if action == 'paste_draft':
            await self._validate_paste_context(context)
        request_digest = self._build_request_digest(context, action, idempotency_key=idempotency_key)
        existing = await self.repository.find_run_by_request_digest(request_digest)
        if existing is not None:
            return self._serialize_run(existing)
        idempotency_key = idempotency_key or request_digest
        draft_text = str(context['draft']['content'])
        run = await self.repository.create_run(
            {
                'bot_uuid': bot_uuid,
                'connector_id': context['conversation']['connector_id'],
                'conversation_id': int(context['conversation']['id']),
                'message_id': message_id,
                'draft_id': draft_id,
                'action': action,
                'execution_mode': execution_mode,
                'runtime_task_id': None,
                'status': 'queued',
                'stage': 'queued',
                'attempt_count': 1,
                'request_digest': request_digest,
                'draft_content_hash': self._hash_text(draft_text),
                'target_snapshot': {
                    'conversationId': context['conversation']['id'],
                    'conversationName': context['conversation']['conversation_name'],
                    'connectorId': context['conversation']['connector_id'],
                },
                'result_evidence': None,
                'last_error_code': None,
                'last_error_message': None,
            }
        )
        run_id = int(getattr(run, 'id', run.get('id') if isinstance(run, dict) else 0))
        client = await self._get_runtime_client()
        task = await client.create_task(
            request={
                'action': runtime_action,
                'idempotencyKey': idempotency_key,
                'requestDigest': request_digest,
                'conversationName': str(context['conversation']['conversation_name']).strip(),
                'draftText': draft_text,
                **(extra_request or {}),
            }
        )
        task = await self._wait_for_task_terminal(task)
        return await self._apply_runtime_task_result(run_id, task)

    async def _apply_runtime_task_result(self, run_id: int, task: dict[str, Any]) -> dict[str, Any]:
        decoded = self._decode_runtime_task(task)
        changes = {
            'runtime_task_id': str(decoded['id'] or ''),
            'status': decoded['status'],
            'stage': decoded['stage'],
            'result_evidence': decoded['result_evidence'],
            'last_error_code': decoded['error_code'],
            'last_error_message': decoded['error_code'],
        }
        updated = await self.repository.update_run_status(run_id, **changes)
        return self._serialize_run(updated)

    async def _get_runtime_client(self):
        return await self.ensure_runtime_client()

    def _validate_context(self, context: dict[str, Any], draft_id: int) -> None:
        draft = context.get('draft')
        if draft is None:
            raise DesktopAutomationError(DRAFT_NOT_FOUND, 'Draft not found')
        if int(draft.get('id')) != int(draft_id):
            raise DesktopAutomationError(DRAFT_CHANGED, 'Draft changed')
        if draft.get('status') != 'active':
            raise DesktopAutomationError(DRAFT_NOT_ACTIVE, 'Draft is not active')
        if not str(draft.get('content') or '').strip():
            raise DesktopAutomationError(DRAFT_TEXT_REQUIRED, 'Draft text is required')
        latest_send = context.get('latest_succeeded_send_run')
        if latest_send is not None:
            raise DesktopAutomationError(DRAFT_ALREADY_SENT, 'Draft was already sent')

    async def _validate_paste_context(self, context: dict[str, Any]) -> None:
        conversation = context.get('conversation') or {}
        connector_id = str(conversation.get('connector_id') or '')
        conversation_name = str(conversation.get('conversation_name') or '').strip()
        if not conversation_name:
            raise DesktopAutomationError(CONVERSATION_NAME_REQUIRED, 'Conversation name is required')
        if hasattr(self.repository, 'count_conversations_by_name'):
            count = await self.repository.count_conversations_by_name(connector_id, conversation_name)
        else:
            count = int(context.get('conversation_name_count') or 1)
        if count != 1:
            raise DesktopAutomationError(
                CONVERSATION_NAME_NOT_UNIQUE,
                'Conversation name is only proven unique within the local bot/channel scope, and this local scope is not unique',
            )

    def _build_request_digest(self, context: dict[str, Any], action: str, *, idempotency_key: str | None = None) -> str:
        draft_text = str(context['draft']['content'])
        raw = '|'.join(
            [
                str(context['draft']['bot_uuid']),
                str(context['conversation']['connector_id']),
                action,
                str(context['draft']['id']),
                self._hash_text(draft_text),
                str(context['conversation']['external_conversation_id']),
                str(idempotency_key or ''),
            ]
        )
        return self._hash_text(raw)

    @staticmethod
    def _hash_text(text: str) -> str:
        return hashlib.sha256(text.encode('utf-8')).hexdigest()

    async def _wait_for_task_terminal(self, task: dict[str, Any]) -> dict[str, Any]:
        decoded = self._decode_runtime_task(task)
        if decoded['status'] in TERMINAL_STATUSES:
            return task

        runtime_task_id = str(decoded['id'] or '').strip()
        if not runtime_task_id:
            return task

        timeout_seconds = max(
            0,
            int(self.ap.instance_config.data.get('desktop_automation', {}).get('task_timeout_seconds', 120)),
        )
        deadline = asyncio.get_running_loop().time() + timeout_seconds
        client = await self._get_runtime_client()
        current_task = task
        while True:
            if timeout_seconds == 0 or asyncio.get_running_loop().time() > deadline:
                return await self._request_task_cancellation(
                    runtime_task_id,
                    client=client,
                    task=current_task,
                    cancel_error_code=TASK_TIMEOUT,
                )

            await asyncio.sleep(TASK_POLL_INTERVAL_SECONDS)
            polled = await client.get_task(runtime_task_id)
            decoded = self._decode_runtime_task(polled)
            current_task = polled
            if decoded['status'] in TERMINAL_STATUSES:
                return polled

    async def _request_task_cancellation(
        self,
        runtime_task_id: str,
        *,
        client,
        task: dict[str, Any] | None,
        cancel_error_code: str,
    ) -> dict[str, Any]:
        current_task = task or {
            'id': runtime_task_id,
            'status': 'running',
            'stage': 'running',
        }
        current_decoded = self._decode_runtime_task(current_task)
        if task is not None and current_decoded['status'] in TERMINAL_STATUSES:
            return current_task

        cancel_result = await client.cancel_task(runtime_task_id)
        cancel_decoded = self._decode_runtime_task(cancel_result)
        if cancel_decoded['status'] in TERMINAL_STATUSES:
            return self._annotate_terminal_cancellation(cancel_result, cancel_error_code=cancel_error_code)

        current_task = cancel_result or current_task
        for _ in range(TASK_CANCEL_GRACE_POLLS):
            await asyncio.sleep(TASK_POLL_INTERVAL_SECONDS)
            polled = await client.get_task(runtime_task_id)
            polled_decoded = self._decode_runtime_task(polled)
            current_task = polled
            if polled_decoded['status'] in TERMINAL_STATUSES:
                return self._annotate_terminal_cancellation(polled, cancel_error_code=cancel_error_code)

        return self._build_cancel_requested_task(current_task, cancel_error_code=cancel_error_code)

    def _build_cancel_requested_task(
        self,
        task: dict[str, Any] | None,
        *,
        cancel_error_code: str,
    ) -> dict[str, Any]:
        decoded = self._decode_runtime_task(task or {})
        result_payload = dict(decoded['result_payload'] or {})
        result_payload['stage'] = 'cancel_requested'
        result_payload['errorCode'] = cancel_error_code
        envelope = dict(task or {})
        envelope.update(
            {
                'id': str(decoded['id'] or envelope.get('id') or ''),
                'status': 'running',
                'stage': 'cancel_requested',
                'errorCode': cancel_error_code,
                'idempotencyKey': decoded['idempotency_key'],
                'requestDigest': decoded['request_digest'],
                'result': result_payload,
            }
        )
        return envelope

    def _annotate_terminal_cancellation(
        self,
        task: dict[str, Any],
        *,
        cancel_error_code: str,
    ) -> dict[str, Any]:
        decoded = self._decode_runtime_task(task)
        if decoded['status'] not in {'cancelled', 'timed_out'} or decoded['error_code']:
            return task

        envelope = dict(task)
        result_payload = dict(decoded['result_payload'] or {})
        result_payload.setdefault('errorCode', cancel_error_code)
        envelope['errorCode'] = cancel_error_code
        envelope['result'] = result_payload
        return envelope

    def _decode_runtime_task(self, task: dict[str, Any]) -> dict[str, Any]:
        return decode_runtime_task(task)

    def _serialize_run(self, run) -> dict[str, Any]:
        if hasattr(run, '__table__'):
            return self.ap.persistence_mgr.serialize_model(type(run), run)
        if isinstance(run, dict):
            return dict(run)
        return dict(vars(run))
