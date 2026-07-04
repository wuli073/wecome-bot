from __future__ import annotations

from typing import Any

from .base import ConversationDraftExecutor


class WeComDraftExecutor(ConversationDraftExecutor):
    channel = 'wxwork_database'

    def __init__(self, gateway) -> None:
        self.gateway = gateway

    def validate_capability(self, action: str) -> dict[str, Any]:
        return {
            'supports_paste': True,
            'supports_send': True,
            'supports_cancel': True,
            'supports_status_query': True,
            'supports_clipboard_restore': True,
            'supports_evidence': True,
            'executor_version': 'phase7',
            'runtime_min_version': '1',
        }

    async def health_check(self) -> dict[str, Any]:
        return await self.gateway.health_check()

    async def paste_draft(
        self,
        *,
        conversation_name: str,
        draft_text: str,
        idempotency_key: str,
        request_digest: str,
    ) -> dict[str, Any]:
        self.gateway.assert_force_disable_send()
        result = await self.gateway.create_paste_task(
            conversation_name=conversation_name,
            draft_text=draft_text,
            idempotency_key=idempotency_key,
            request_digest=request_digest,
        )
        return {
            **result,
            'action': 'paste_draft',
        }

    async def send_message(
        self,
        *,
        conversation_name: str,
        message_text: str,
        idempotency_key: str,
        request_digest: str,
        confirmation_token: str,
    ) -> dict[str, Any]:
        result = await self.gateway.create_send_task(
            conversation_name=conversation_name,
            message_text=message_text,
            idempotency_key=idempotency_key,
            request_digest=request_digest,
            confirmation_token=confirmation_token,
        )
        return {
            **result,
            'action': 'send_message',
        }

    async def cancel(self, runtime_task_id: str) -> dict[str, Any]:
        return await self.gateway.cancel_task(runtime_task_id)

    async def query_status(self, runtime_task_id: str) -> dict[str, Any]:
        return await self.gateway.query_task(runtime_task_id)

    def normalize_evidence(self, result: dict[str, Any]) -> dict[str, Any]:
        payload = dict(result.get('result') or {})
        status = str(result.get('status') or '')
        stage = str(result.get('stage') or status)
        action = str(result.get('action') or payload.get('action') or '')
        normalized_action = 'send_message' if action == 'send_message' or stage.startswith('sent') else 'paste_draft'
        content_verified = bool(payload.get('contentVerified', False))
        input_located = bool(payload.get('inputLocated', status in {'queued', 'running', 'succeeded', 'succeeded_with_warning'}))
        draft_written = bool(payload.get('draftWritten', content_verified))
        verification_failed = bool(payload.get('verificationFailed', not content_verified and normalized_action == 'paste_draft'))
        return {
            'window_title': None,
            'target_conversation': None,
            'action': normalized_action,
            'input_located': input_located,
            'draft_written': draft_written,
            'content_verified': content_verified,
            'verification_failed': verification_failed,
            'send_triggered': bool(payload.get('messageSent', False)) or stage in {'sent', 'message_sent'},
            'clipboard_restored': not bool(payload.get('clipboardRestoreFailed', False)),
            'runtime_state': stage,
            'evidence_summary': stage,
            'technical_details': {
                'stage': stage,
                'status': status,
                'content_verified': content_verified,
                'verification_failed': verification_failed,
                'verification_method': payload.get('verificationMethod'),
                'verification_error_code': payload.get('verificationErrorCode'),
                'clipboard_roundtrip_verified': payload.get('clipboardRoundtripVerified'),
                'expected_text_length': payload.get('expectedTextLength'),
                'actual_text_length': payload.get('actualTextLength'),
                'expected_digest': payload.get('expectedDigest'),
                'actual_digest': payload.get('actualDigest'),
                'expected_line_count': payload.get('expectedLineCount'),
                'actual_line_count': payload.get('actualLineCount'),
            },
        }
