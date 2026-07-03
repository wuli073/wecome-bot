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
