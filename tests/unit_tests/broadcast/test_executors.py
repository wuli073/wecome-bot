from __future__ import annotations

import pytest


pytestmark = pytest.mark.asyncio


class _FakeGateway:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def assert_force_disable_send(self) -> None:
        return None

    async def create_paste_task(self, **kwargs):
        self.calls.append(('paste', kwargs))
        return {
            'id': 'runtime-task-1',
            'status': 'succeeded_with_warning',
            'stage': 'text_pasted_unverified',
            'action': 'paste_draft',
            'result': {
                'messageSent': False,
                'clipboardRestoreFailed': False,
                'warning': 'PASTE_RESULT_NOT_VERIFIED',
                'contentVerified': False,
                'draftWritten': True,
                'inputLocated': False,
                'draftPasteCount': 1,
                'searchShortcutCount': 1,
                'conversationPasteCount': 1,
                'conversationConfirmEnterCount': 1,
                'sendKeyCount': 0,
                'observationAvailable': False,
            },
        }

    async def create_send_task(self, **kwargs):
        self.calls.append(('send', kwargs))
        return {
            'id': 'runtime-task-2',
            'status': 'succeeded',
            'stage': 'message_sent',
            'action': 'send_draft',
            'result': {'messageSent': True, 'clipboardRestoreFailed': False},
        }

    async def cancel_task(self, runtime_task_id: str):
        return {'id': runtime_task_id, 'status': 'cancelled'}

    async def query_task(self, runtime_task_id: str):
        return {'id': runtime_task_id, 'status': 'succeeded'}


async def test_wecom_executor_exposes_capabilities_and_normalizes_paste_evidence():
    from langbot.pkg.broadcast.executors.wecom import WeComDraftExecutor

    executor = WeComDraftExecutor(_FakeGateway())
    capability = executor.validate_capability('paste_draft')

    assert capability['supports_paste'] is True
    assert capability['supports_send'] is True
    assert capability['supports_paste_verification'] is False
    assert capability['supports_attachment_send'] is True
    assert capability['supports_post_send_verification'] is False
    assert capability['post_send_verification'] == 'unavailable'
    assert capability['requires_manual_conversation_open'] is False

    result = await executor.paste_draft(
        conversation_name='Acme Group',
        draft_text='Hello Acme',
        idempotency_key='broadcast:1:1',
        request_digest='digest-1',
    )
    evidence = executor.normalize_evidence(result)
    assert evidence['action'] == 'paste_draft'
    assert evidence['send_triggered'] is False
    assert evidence['draft_written'] is True
    assert evidence['content_verified'] is False
    assert evidence['evidence_summary'] == '已粘贴，未发送'
    assert evidence['technical_details']['warning'] == 'PASTE_RESULT_NOT_VERIFIED'
    assert evidence['technical_details']['search_shortcut_count'] == 1
    assert evidence['technical_details']['conversation_confirm_enter_count'] == 1


async def test_wecom_executor_supports_isolated_send_message_path():
    from langbot.pkg.broadcast.executors.wecom import WeComDraftExecutor

    gateway = _FakeGateway()
    executor = WeComDraftExecutor(gateway)

    result = await executor.send_message(
        conversation_name='Acme Group',
        message_text='Hello Acme',
        idempotency_key='broadcast:1:2',
        request_digest='digest-2',
        attachment_root='C:/runtime/broadcast_attachments',
        attachments=[
            {
                'relativePath': 'bot-1/drafts/1/quote.pdf',
                'filename': 'quote.pdf',
                'size': 8,
                'sha256': 'digest-quote',
            }
        ],
    )
    evidence = executor.normalize_evidence(result)

    assert gateway.calls == [
        (
            'send',
            {
                'conversation_name': 'Acme Group',
                'message_text': 'Hello Acme',
                'idempotency_key': 'broadcast:1:2',
                'request_digest': 'digest-2',
                'attachment_root': 'C:/runtime/broadcast_attachments',
                'attachments': [
                    {
                        'relativePath': 'bot-1/drafts/1/quote.pdf',
                        'filename': 'quote.pdf',
                        'size': 8,
                        'sha256': 'digest-quote',
                    }
                ],
            },
        )
    ]
    assert evidence['action'] == 'send_message'
    assert evidence['send_triggered'] is True


async def test_wecom_executor_accepts_unverified_paste_only_success_with_warning():
    from langbot.pkg.broadcast.executors.wecom import WeComDraftExecutor

    gateway = _FakeGateway()
    executor = WeComDraftExecutor(gateway)

    result = {
        'id': 'runtime-task-1',
        'status': 'succeeded_with_warning',
        'stage': 'text_pasted_unverified',
        'action': 'paste_draft',
        'result': {
            'messageSent': False,
            'clipboardRestoreFailed': False,
            'warning': 'PASTE_RESULT_NOT_VERIFIED',
            'contentVerified': False,
            'draftWritten': True,
            'inputLocated': False,
            'searchShortcutCount': 1,
            'conversationPasteCount': 1,
            'conversationConfirmEnterCount': 1,
            'draftPasteCount': 1,
            'sendKeyCount': 0,
        },
    }

    evidence = executor.normalize_evidence(result)

    assert evidence['input_located'] is False
    assert evidence['draft_written'] is True
    assert evidence['content_verified'] is False
    assert evidence['send_triggered'] is False
    assert evidence['technical_details']['warning'] == 'PASTE_RESULT_NOT_VERIFIED'


async def test_wecom_executor_includes_window_candidate_diagnostics():
    from langbot.pkg.broadcast.executors.wecom import WeComDraftExecutor

    executor = WeComDraftExecutor(_FakeGateway())
    evidence = executor.normalize_evidence(
        {
            'id': 'runtime-task-ambiguous',
            'status': 'blocked',
            'stage': 'activating_window',
            'action': 'paste_draft',
            'errorCode': 'TARGET_WINDOW_AMBIGUOUS',
            'result': {
                'messageSent': False,
                'clipboardRestoreFailed': False,
                'contentVerified': False,
                'draftWritten': False,
                'inputLocated': False,
                'candidateCountBeforeFilter': 3,
                'candidateCountAfterFilter': 2,
                'canonicalCandidateCount': 2,
                'rejectedCandidateCount': 1,
                'selectedWindow': None,
                'candidates': [
                    {
                        'hwnd': '1769682',
                        'rootHwnd': '1769682',
                        'ownerHwnd': '0',
                        'processId': 5516,
                        'processName': 'wxwork.exe',
                        'executableName': 'wxwork.exe',
                        'title': '企业微信',
                        'className': 'Qt51514QWindowIcon',
                        'visible': True,
                        'minimized': False,
                        'source': 'node-window-manager',
                        'accepted': True,
                        'rejectionReason': None,
                    }
                ],
                'rejectionReasons': [{'reason': 'empty_title', 'count': 1}],
            },
        }
    )

    technical_details = evidence['technical_details']
    assert technical_details['candidate_count_before_filter'] == 3
    assert technical_details['candidate_count_after_filter'] == 2
    assert technical_details['canonical_candidate_count'] == 2
    assert technical_details['rejected_candidate_count'] == 1
    assert technical_details['candidates'][0]['hwnd'] == '1769682'


async def test_wecom_executor_normalizes_failed_attachment_helper_evidence_without_paths():
    from langbot.pkg.broadcast.executors.wecom import WeComDraftExecutor

    executor = WeComDraftExecutor(_FakeGateway())
    evidence = executor.normalize_evidence(
        {
            'id': 'runtime-task-attachment-helper-failed',
            'status': 'failed',
            'stage': 'pasting_attachments',
            'action': 'paste_draft',
            'errorCode': 'FILE_CLIPBOARD_HELPER_TIMEOUT',
            'result': {
                'messageSent': False,
                'clipboardRestoreFailed': False,
                'contentVerified': False,
                'draftWritten': True,
                'inputLocated': False,
                'attachmentsPrepared': False,
                'attachmentPasteRequested': False,
                'attachmentsVerified': False,
                'attachmentCount': 2,
                'sanitizedMessage': 'Unable to prepare the file clipboard',
                'attachmentRoot': 'C:/secret/runtime/broadcast_attachments',
                'resolvedPath': 'C:/secret/runtime/broadcast_attachments/report.xlsx',
                'sendKeyCount': 0,
            },
        }
    )

    technical_details = evidence['technical_details']
    assert technical_details['error_code'] == 'FILE_CLIPBOARD_HELPER_TIMEOUT'
    assert technical_details['attachment_count'] == 2
    assert technical_details['attachments_prepared'] is False
    assert technical_details['attachment_paste_requested'] is False
    assert technical_details['send_key_count'] == 0
    assert 'attachmentRoot' not in technical_details
    assert 'resolvedPath' not in technical_details


async def test_wecom_executor_and_desktop_automation_share_runtime_decoder():
    from langbot.pkg.broadcast.executors.wecom import WeComDraftExecutor
    from langbot.pkg.desktop_automation.runtime_task_decoder import decode_runtime_task

    result = {
        'id': 'runtime-task-shared-decoder',
        'status': 'succeeded_with_warning',
        'stage': 'attachments_pasted_unverified',
        'action': 'paste_draft',
        'result': {
            'draftWritten': True,
            'draftPasteCount': 1,
            'searchShortcutCount': 1,
            'conversationPasteCount': 1,
            'conversationConfirmEnterCount': 1,
            'attachmentsPrepared': True,
            'attachmentPasteRequested': True,
            'attachmentsVerified': False,
            'attachmentCount': 1,
            'warning': 'PASTE_RESULT_NOT_VERIFIED',
            'messageSent': False,
            'clipboardRestoreFailed': False,
        },
    }

    decoded = decode_runtime_task(result)
    evidence = WeComDraftExecutor(_FakeGateway()).normalize_evidence(result)

    assert decoded['result_evidence']['draftPasteCount'] == 1
    assert decoded['result_evidence']['attachmentsVerified'] is False
    assert evidence['draft_written'] is True
    assert evidence['technical_details']['draft_paste_count'] == decoded['result_evidence']['draftPasteCount']
    assert evidence['technical_details']['search_shortcut_count'] == decoded['result_evidence']['searchShortcutCount']
    assert evidence['technical_details']['conversation_confirm_enter_count'] == decoded['result_evidence']['conversationConfirmEnterCount']
    assert evidence['technical_details']['attachments_verified'] == decoded['result_evidence']['attachmentsVerified']
