from __future__ import annotations

import pytest


def _profile(
    *,
    group_field: str | None = '客户名称',
    mapping_rules: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    return {
        'group_field': group_field,
        'mapping_rules': mapping_rules
        if mapping_rules is not None
        else [
            {
                'source_field': '客户名称',
                'variable_key': 'customer_name',
                'merge_mode': 'first',
                'order': 1,
            },
            {
                'source_field': '订单号',
                'variable_key': 'order_no',
                'merge_mode': 'lines',
                'order': 2,
            },
        ],
    }


def test_validate_import_headers_rejects_missing_group_field_configuration():
    from langbot.pkg.broadcast.import_processor import (
        BroadcastImportProcessorError,
        validate_import_headers,
    )

    with pytest.raises(BroadcastImportProcessorError) as exc_info:
        validate_import_headers(
            headers=['客户名称', '订单号'],
            variable_profile=_profile(group_field=None),
        )

    assert exc_info.value.message == '请先设置客户分组字段后再导入文件'


def test_validate_import_headers_rejects_missing_required_fields():
    from langbot.pkg.broadcast.import_processor import (
        BroadcastImportProcessorError,
        validate_import_headers,
    )

    with pytest.raises(BroadcastImportProcessorError) as exc_info:
        validate_import_headers(
            headers=['客户名称'],
            variable_profile=_profile(),
        )

    assert exc_info.value.message == '导入文件缺少以下字段：订单号'


def test_validate_rematch_headers_uses_latest_variable_profile_and_rejects_whole_batch():
    from langbot.pkg.broadcast.import_processor import (
        BroadcastImportProcessorError,
        validate_rematch_headers,
    )

    with pytest.raises(BroadcastImportProcessorError) as exc_info:
        validate_rematch_headers(
            headers=['历史客户名称', '订单号'],
            variable_profile=_profile(
                group_field='最新客户名称',
                mapping_rules=[
                    {
                        'source_field': '最新客户名称',
                        'variable_key': 'customer_name',
                        'merge_mode': 'first',
                        'order': 1,
                    },
                    {
                        'source_field': '最新联系人',
                        'variable_key': 'contacts',
                        'merge_mode': 'unique_commas',
                        'order': 2,
                    },
                ],
            ),
        )

    assert exc_info.value.message == '当前导入数据缺少以下字段，无法重新匹配：最新客户名称、最新联系人'


def test_classify_import_rows_uses_latest_group_field_trim_and_empty_to_invalid():
    from langbot.pkg.broadcast.import_processor import classify_import_rows

    classified_rows = classify_import_rows(
        rows=[
            {
                'source_row_number': 2,
                'raw_data': {
                    '历史客户名称': '',
                    '最新客户名称': '  Acme  ',
                    '订单号': 'SO-001',
                },
            },
            {
                'source_row_number': 3,
                'raw_data': {
                    '历史客户名称': 'Legacy',
                    '最新客户名称': '   ',
                    '订单号': 'SO-002',
                },
            },
        ],
        group_field='最新客户名称',
        match_resolver=lambda group_value: (
            {
                'matched': True,
                'matched_conversation_name': 'Acme Group',
                'matched_rule_id': 9,
            }
            if group_value == 'Acme'
            else {
                'matched': False,
                'matched_conversation_name': None,
                'matched_rule_id': None,
            }
        ),
    )

    assert classified_rows[0]['group_value'] == 'Acme'
    assert classified_rows[0]['match_status'] == 'matched'
    assert classified_rows[0]['matched_conversation_name'] == 'Acme Group'
    assert classified_rows[0]['matched_rule_id'] == 9

    assert classified_rows[1]['group_value'] is None
    assert classified_rows[1]['match_status'] == 'invalid'
    assert classified_rows[1]['matched_conversation_name'] is None
    assert classified_rows[1]['matched_rule_id'] is None


def test_classify_import_rows_produces_unmatched_rows_without_double_counting():
    from langbot.pkg.broadcast.import_processor import (
        calculate_batch_stats,
        classify_import_rows,
    )

    classified_rows = classify_import_rows(
        rows=[
            {
                'source_row_number': 2,
                'raw_data': {'客户名称': 'Acme', '订单号': 'SO-001'},
            },
            {
                'source_row_number': 3,
                'raw_data': {'客户名称': 'Northwind', '订单号': 'SO-002'},
            },
            {
                'source_row_number': 4,
                'raw_data': {'客户名称': '   ', '订单号': 'SO-003'},
            },
        ],
        group_field='客户名称',
        match_resolver=lambda group_value: (
            {
                'matched': True,
                'matched_conversation_name': 'Acme Group',
                'matched_rule_id': 1,
            }
            if group_value == 'Acme'
            else {
                'matched': False,
                'matched_conversation_name': None,
                'matched_rule_id': None,
            }
        ),
    )

    assert [row['match_status'] for row in classified_rows] == ['matched', 'unmatched', 'invalid']
    assert classified_rows[1]['error_message'] == '未匹配到群聊'

    stats = calculate_batch_stats(classified_rows)

    assert stats == {
        'total_rows': 3,
        'valid_rows': 2,
        'invalid_rows': 1,
        'matched_rows': 1,
        'unmatched_rows': 1,
    }
    assert stats['valid_rows'] + stats['invalid_rows'] == stats['total_rows']
    assert stats['matched_rows'] + stats['unmatched_rows'] + stats['invalid_rows'] == stats['total_rows']


def test_resolve_upload_group_field_uses_override_when_header_exists():
    from langbot.pkg.broadcast.import_processor import resolve_upload_group_field

    result = resolve_upload_group_field(
        headers=['客户名称', '订单号'],
        variable_profile=_profile(group_field='客户'),
        group_field_override='客户名称',
    )

    assert result['group_field'] == '客户名称'
    assert result['source'] == 'user_confirmed'


def test_resolve_upload_group_field_prefers_username_header():
    from langbot.pkg.broadcast.import_processor import resolve_upload_group_field

    result = resolve_upload_group_field(
        headers=['用户名', '客户名称', '订单号'],
        variable_profile=_profile(group_field='客户名称'),
    )

    assert result['group_field'] == '用户名'
    assert result['source'] == 'auto_detected'


def test_resolve_upload_group_field_uses_configured_field_when_present():
    from langbot.pkg.broadcast.import_processor import resolve_upload_group_field

    result = resolve_upload_group_field(
        headers=['最新客户名称', '订单号'],
        variable_profile=_profile(group_field='最新客户名称'),
    )

    assert result['group_field'] == '最新客户名称'
    assert result['source'] == 'configured'


def test_resolve_upload_group_field_uses_single_alias_hit():
    from langbot.pkg.broadcast.import_processor import resolve_upload_group_field

    result = resolve_upload_group_field(
        headers=['昵称', '订单号'],
        variable_profile=_profile(group_field='不存在的字段'),
    )

    assert result['group_field'] == '昵称'
    assert result['source'] == 'auto_detected'


def test_resolve_upload_group_field_requires_confirmation_for_ambiguous_aliases():
    from langbot.pkg.broadcast.import_processor import (
        BROADCAST_IMPORT_GROUP_FIELD_CONFIRMATION_REQUIRED,
        BroadcastImportProcessorError,
        resolve_upload_group_field,
    )

    with pytest.raises(BroadcastImportProcessorError) as exc_info:
        resolve_upload_group_field(
            headers=['\u5ba2\u6237', '\u59d3\u540d', '\u8ba2\u5355\u53f7'],
            variable_profile=_profile(group_field='\u4e0d\u5b58\u5728\u7684\u5b57\u6bb5'),
        )

    assert exc_info.value.code == BROADCAST_IMPORT_GROUP_FIELD_CONFIRMATION_REQUIRED
    details = exc_info.value.details
    assert isinstance(details, dict)
    assert details['headers'] == ['\u5ba2\u6237', '\u59d3\u540d', '\u8ba2\u5355\u53f7']
    assert details['candidates'] == ['\u5ba2\u6237', '\u59d3\u540d']
    assert details['configured_group_field'] == '\u4e0d\u5b58\u5728\u7684\u5b57\u6bb5'
    assert details['original_file_name'] is None

def test_resolve_upload_group_field_requires_confirmation_when_no_alias_candidates_found():
    from langbot.pkg.broadcast.import_processor import (
        BROADCAST_IMPORT_GROUP_FIELD_CONFIRMATION_REQUIRED,
        BroadcastImportProcessorError,
        resolve_upload_group_field,
    )

    with pytest.raises(BroadcastImportProcessorError) as exc_info:
        resolve_upload_group_field(
            headers=['\u8ba2\u5355\u53f7', '\u8054\u7cfb\u4eba\u624b\u673a\u53f7'],
            variable_profile=_profile(group_field='\u4e0d\u5b58\u5728\u7684\u5b57\u6bb5'),
        )

    assert exc_info.value.code == BROADCAST_IMPORT_GROUP_FIELD_CONFIRMATION_REQUIRED
    details = exc_info.value.details
    assert isinstance(details, dict)
    assert details['headers'] == ['\u8ba2\u5355\u53f7', '\u8054\u7cfb\u4eba\u624b\u673a\u53f7']
    assert details['candidates'] == []
    assert details['configured_group_field'] == '\u4e0d\u5b58\u5728\u7684\u5b57\u6bb5'
    assert details['original_file_name'] is None
    assert exc_info.value.message == '\u672a\u8bc6\u522b\u5230\u53ef\u552f\u4e00\u786e\u5b9a\u7684\u5ba2\u6237\u5206\u7ec4\u5b57\u6bb5\uff0c\u8bf7\u7528\u6237\u786e\u8ba4\u540e\u7ee7\u7eed'

def test_resolve_upload_group_field_rejects_invalid_override():
    from langbot.pkg.broadcast.import_processor import (
        BROADCAST_IMPORT_GROUP_FIELD_OVERRIDE_INVALID,
        BroadcastImportProcessorError,
        resolve_upload_group_field,
    )

    with pytest.raises(BroadcastImportProcessorError) as exc_info:
        resolve_upload_group_field(
            headers=['\u5ba2\u6237\u540d\u79f0', '\u8ba2\u5355\u53f7'],
            variable_profile=_profile(group_field='\u5ba2\u6237\u540d\u79f0'),
            group_field_override='\u7528\u6237\u540d',
        )

    assert exc_info.value.code == BROADCAST_IMPORT_GROUP_FIELD_OVERRIDE_INVALID
    details = exc_info.value.details
    assert isinstance(details, dict)
    assert details['group_field_override'] == '\u7528\u6237\u540d'
    assert details['headers'] == ['\u5ba2\u6237\u540d\u79f0', '\u8ba2\u5355\u53f7']
    assert details['original_file_name'] is None
