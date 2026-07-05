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
            'supports_paste_verification': False,
            'supports_send': False,
            'supports_cancel': True,
            'supports_status_query': True,
            'supports_clipboard_restore': True,
            'supports_evidence': True,
            'requires_manual_conversation_open': False,
            'conversation_locator': 'keyboard_search',
            'content_verification': 'disabled',
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
        attachment_root: str | None = None,
        attachments: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        self.gateway.assert_force_disable_send()
        result = await self.gateway.create_paste_task(
            conversation_name=conversation_name,
            draft_text=draft_text,
            idempotency_key=idempotency_key,
            request_digest=request_digest,
            attachment_root=attachment_root,
            attachments=attachments or [],
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
        input_located = bool(payload.get('inputLocated', False))
        draft_written = bool(payload.get('draftWritten', False))
        attachments_prepared = bool(payload.get('attachmentsPrepared', False))
        attachment_paste_requested = bool(payload.get('attachmentPasteRequested', False))
        attachments_verified = bool(payload.get('attachmentsVerified', False))
        attachment_count = int(payload.get('attachmentCount', 0) or 0)
        attachment_names = [
            str(item.get('filename') or item.get('name') or '').strip()
            for item in (payload.get('attachments') or [])
            if isinstance(item, dict) and str(item.get('filename') or item.get('name') or '').strip()
        ]
        observation_available_raw = payload.get('observationAvailable')
        has_actual_metrics = any(
            payload.get(key) is not None
            for key in (
                'actualTextLength',
                'actualCodePointCount',
                'actualDigest',
                'actualLineCount',
                'actualCrCount',
                'actualLfCount',
            )
        )
        observation_available = (
            bool(observation_available_raw)
            if observation_available_raw is not None
            else bool(has_actual_metrics and (input_located or draft_written or content_verified))
        )
        if not observation_available:
            payload['actualTextLength'] = None
            payload['actualCodePointCount'] = None
            payload['actualDigest'] = None
            payload['actualLineCount'] = None
            payload['actualCrCount'] = None
            payload['actualLfCount'] = None
        verification_failed = bool(payload.get('verificationFailed', False))
        warning = str(payload.get('warning') or '').strip() or None
        evidence_summary = stage
        if status == 'succeeded_with_warning' and stage == 'attachments_pasted_unverified':
            evidence_summary = '已写入，附件待人工确认'
        elif status == 'succeeded_with_warning' and stage == 'text_pasted_unverified':
            evidence_summary = '已写入正文，待人工确认'
        window_title = (
            payload.get('windowTitle')
            or (payload.get('selectedWindow') or {}).get('title')
            or None
        )
        return {
            'window_title': window_title,
            'target_conversation': None,
            'action': normalized_action,
            'input_located': input_located,
            'draft_written': draft_written,
            'content_verified': content_verified,
            'verification_failed': verification_failed,
            'send_triggered': bool(payload.get('messageSent', False)) or stage in {'sent', 'message_sent'},
            'clipboard_restored': not bool(payload.get('clipboardRestoreFailed', False)),
            'runtime_state': stage,
            'evidence_summary': evidence_summary,
            'technical_details': {
                'stage': stage,
                'status': status,
                'warning': warning,
                'error_code': result.get('errorCode') or result.get('error_code'),
                'content_verified': content_verified,
                'verification_failed': verification_failed,
                'attachments_prepared': attachments_prepared,
                'attachment_paste_requested': attachment_paste_requested,
                'attachments_verified': attachments_verified,
                'attachment_count': attachment_count,
                'attachment_names': attachment_names,
                'search_shortcut_count': payload.get('searchShortcutCount'),
                'conversation_paste_count': payload.get('conversationPasteCount'),
                'conversation_confirm_enter_count': payload.get('conversationConfirmEnterCount'),
                'draft_paste_count': payload.get('draftPasteCount'),
                'send_key_count': payload.get('sendKeyCount'),
                'message_sent': payload.get('messageSent'),
                'candidate_count_before_filter': payload.get('candidateCountBeforeFilter'),
                'candidate_count_after_filter': payload.get('candidateCountAfterFilter'),
                'canonical_candidate_count': payload.get('canonicalCandidateCount'),
                'rejected_candidate_count': payload.get('rejectedCandidateCount'),
                'selected_window': payload.get('selectedWindow'),
                'candidates': payload.get('candidates'),
                'rejection_reasons': payload.get('rejectionReasons'),
                'verification_method': payload.get('verificationMethod'),
                'provider_instance_id': payload.get('providerInstanceId'),
                'verification_error_code': payload.get('verificationErrorCode'),
                'diagnostic_code': payload.get('diagnosticCode'),
                'diagnostic_stage': payload.get('diagnosticStage'),
                'sanitized_message': payload.get('sanitizedMessage'),
                'used_cached_capability': payload.get('usedCachedCapability'),
                'capability_refresh_requested': payload.get('capabilityRefreshRequested'),
                'capability_refresh_executed': payload.get('capabilityRefreshExecuted'),
                'capability_checked_at': payload.get('capabilityCheckedAt'),
                'capability_expires_at': payload.get('capabilityExpiresAt'),
                'capability_age_ms': payload.get('capabilityAgeMs'),
                'capability_probe_count_before_task': payload.get('capabilityProbeCountBeforeTask'),
                'capability_probe_count_after_task': payload.get('capabilityProbeCountAfterTask'),
                'capability_probe_spawn_count_before_task': payload.get('capabilityProbeSpawnCountBeforeTask'),
                'capability_probe_spawn_count_after_task': payload.get('capabilityProbeSpawnCountAfterTask'),
                'last_capability_diagnostic_code': payload.get('lastCapabilityDiagnosticCode'),
                'capability_probe_diagnostic': payload.get('capabilityProbeDiagnostic'),
                'task_verification_diagnostic': payload.get('taskVerificationDiagnostic'),
                'clipboard_roundtrip_verified': payload.get('clipboardRoundtripVerified'),
                'observation_available': observation_available,
                'expected_text_length': payload.get('expectedTextLength'),
                'actual_text_length': payload.get('actualTextLength'),
                'expected_code_point_count': payload.get('expectedCodePointCount'),
                'actual_code_point_count': payload.get('actualCodePointCount'),
                'expected_digest': payload.get('expectedDigest'),
                'actual_digest': payload.get('actualDigest'),
                'expected_line_count': payload.get('expectedLineCount'),
                'actual_line_count': payload.get('actualLineCount'),
                'expected_cr_count': payload.get('expectedCrCount'),
                'actual_cr_count': payload.get('actualCrCount'),
                'expected_lf_count': payload.get('expectedLfCount'),
                'actual_lf_count': payload.get('actualLfCount'),
            },
        }
