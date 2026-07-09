from __future__ import annotations

from typing import Any


RUNTIME_TASK_EVIDENCE_KEYS = {
    'stage',
    'sendAuthorized',
    'messageSent',
    'clipboardRestoreFailed',
    'searchShortcutCount',
    'conversationPasteCount',
    'conversationConfirmEnterCount',
    'draftPasteCount',
    'sendKeyCount',
    'idempotencyKey',
    'requestDigest',
    'taskId',
    'warningCode',
    'draftWritten',
    'attachmentsPrepared',
    'attachmentPasteRequested',
    'attachmentsVerified',
    'attachmentCount',
    'warning',
    'errorCode',
    'contentVerified',
    'inputLocated',
    'verificationFailed',
    'observationAvailable',
    'actualTextLength',
    'actualCodePointCount',
    'actualDigest',
    'actualLineCount',
    'actualCrCount',
    'actualLfCount',
    'expectedTextLength',
    'expectedCodePointCount',
    'expectedDigest',
    'expectedLineCount',
    'expectedCrCount',
    'expectedLfCount',
    'selectedWindow',
    'candidates',
    'rejectionReasons',
    'candidateCountBeforeFilter',
    'candidateCountAfterFilter',
    'canonicalCandidateCount',
    'rejectedCandidateCount',
    'verificationMethod',
    'providerInstanceId',
    'verificationErrorCode',
    'diagnosticCode',
    'diagnosticStage',
    'sanitizedMessage',
    'usedCachedCapability',
    'capabilityRefreshRequested',
    'capabilityRefreshExecuted',
    'capabilityCheckedAt',
    'capabilityExpiresAt',
    'capabilityAgeMs',
    'capabilityProbeCountBeforeTask',
    'capabilityProbeCountAfterTask',
    'capabilityProbeSpawnCountBeforeTask',
    'capabilityProbeSpawnCountAfterTask',
    'lastCapabilityDiagnosticCode',
    'capabilityProbeDiagnostic',
    'taskVerificationDiagnostic',
    'clipboardRoundtripVerified',
    'windowTitle',
    'attachments',
    'outcome',
    'enterDispatched',
    'enter_dispatched',
    'postSendVerified',
    'post_send_verified',
    'verificationResult',
    'verification_result',
    'errorMessage',
    'error_message',
    'evidence',
}


def decode_runtime_task(task: dict[str, Any] | None) -> dict[str, Any]:
    envelope = dict(task or {})
    result = envelope.get('result')
    result_payload = result if isinstance(result, dict) else {}
    status = str(envelope.get('status') or 'failed')
    stage = str(envelope.get('stage') or status)

    result_evidence = {key: result_payload.get(key) for key in RUNTIME_TASK_EVIDENCE_KEYS if key in result_payload}
    for key in RUNTIME_TASK_EVIDENCE_KEYS:
        if key in envelope and key not in result_evidence:
            result_evidence[key] = envelope.get(key)

    result_evidence.setdefault('stage', stage)
    result_evidence.setdefault('sendAuthorized', bool(result_payload.get('sendAuthorized', envelope.get('sendAuthorized', False))))
    result_evidence.setdefault('messageSent', bool(result_payload.get('messageSent', envelope.get('messageSent', False))))
    result_evidence.setdefault(
        'clipboardRestoreFailed',
        bool(result_payload.get('clipboardRestoreFailed', envelope.get('clipboardRestoreFailed', False))),
    )

    return {
        'id': str(envelope.get('id') or ''),
        'status': status,
        'stage': stage,
        'error_code': envelope.get('errorCode') or result_payload.get('errorCode'),
        'idempotency_key': envelope.get('idempotencyKey') or result_payload.get('idempotencyKey'),
        'request_digest': envelope.get('requestDigest') or result_payload.get('requestDigest'),
        'result_payload': result_payload,
        'result_evidence': result_evidence,
    }
