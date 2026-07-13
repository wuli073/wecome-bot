from __future__ import annotations

from langbot.pkg.desktop_automation.runtime_task_decoder import decode_runtime_task


def test_decode_runtime_task_prefers_nested_result_fields_and_preserves_defaults():
    decoded = decode_runtime_task(
        {
            'id': 'task-1',
            'status': 'succeeded_with_warning',
            'stage': 'attachments_pasted_unverified',
            'requestDigest': 'digest-envelope',
            'draftWritten': False,
            'messageSent': True,
            'result': {
                'requestDigest': 'digest-result',
                'draftWritten': True,
                'draftPasteCount': 1,
                'attachmentPasteRequested': True,
                'attachmentsVerified': False,
                'messageSent': False,
                'clipboardRestoreFailed': True,
                'warning': 'PASTE_RESULT_NOT_VERIFIED',
            },
        }
    )

    assert decoded['id'] == 'task-1'
    assert decoded['status'] == 'succeeded_with_warning'
    assert decoded['stage'] == 'attachments_pasted_unverified'
    assert decoded['request_digest'] == 'digest-envelope'
    assert decoded['result_evidence']['draftWritten'] is True
    assert decoded['result_evidence']['draftPasteCount'] == 1
    assert decoded['result_evidence']['attachmentPasteRequested'] is True
    assert decoded['result_evidence']['attachmentsVerified'] is False
    assert decoded['result_evidence']['messageSent'] is False
    assert decoded['result_evidence']['clipboardRestoreFailed'] is True
    assert decoded['result_evidence']['warning'] == 'PASTE_RESULT_NOT_VERIFIED'


def test_decode_runtime_task_uses_legacy_envelope_fallback_without_overriding_nested_values():
    decoded = decode_runtime_task(
        {
            'id': 'task-legacy',
            'status': 'cancelled',
            'stage': 'cancelled',
            'errorCode': 'TASK_CANCELLED',
            'requestDigest': 'digest-legacy',
            'draftWritten': True,
            'draftPasteCount': 2,
            'messageSent': True,
            'clipboardRestoreFailed': True,
        }
    )

    assert decoded['error_code'] == 'TASK_CANCELLED'
    assert decoded['request_digest'] == 'digest-legacy'
    assert decoded['result_evidence']['draftWritten'] is True
    assert decoded['result_evidence']['draftPasteCount'] == 2
    assert decoded['result_evidence']['messageSent'] is True
    assert decoded['result_evidence']['clipboardRestoreFailed'] is True
    assert decoded['result_evidence']['stage'] == 'cancelled'


def test_decode_runtime_task_missing_fields_use_explicit_safe_defaults():
    decoded = decode_runtime_task({'id': 'task-empty'})

    assert decoded['status'] == 'failed'
    assert decoded['stage'] == 'failed'
    assert decoded['error_code'] is None
    assert decoded['result_evidence']['stage'] == 'failed'
    assert decoded['result_evidence']['sendAuthorized'] is False
    assert decoded['result_evidence']['messageSent'] is False
    assert decoded['result_evidence']['clipboardRestoreFailed'] is False
