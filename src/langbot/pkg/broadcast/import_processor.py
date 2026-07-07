from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(slots=True)
class BroadcastImportProcessorError(Exception):
    message: str

    def __str__(self) -> str:
        return self.message


def validate_import_headers(*, headers: list[str], variable_profile: dict[str, Any]) -> None:
    group_field = _normalize_required_field(variable_profile.get('group_field'))
    if not group_field:
        raise BroadcastImportProcessorError('请先设置客户分组字段后再导入文件')

    missing_fields = _find_missing_fields(headers, variable_profile, include_group_field=True)
    if missing_fields:
        raise BroadcastImportProcessorError(f'导入文件缺少以下字段：{"、".join(missing_fields)}')


def validate_rematch_headers(*, headers: list[str], variable_profile: dict[str, Any]) -> None:
    group_field = _normalize_required_field(variable_profile.get('group_field'))
    if not group_field:
        raise BroadcastImportProcessorError('请先设置客户分组字段后再导入文件')

    missing_fields = _find_missing_fields(headers, variable_profile, include_group_field=True)
    if missing_fields:
        raise BroadcastImportProcessorError(
            f'当前导入数据缺少以下字段，无法重新匹配：{"、".join(missing_fields)}'
        )


def classify_import_rows(
    *,
    rows: list[dict[str, Any]],
    group_field: str,
    match_resolver: Callable[[str], dict[str, Any]],
) -> list[dict[str, Any]]:
    classified_rows: list[dict[str, Any]] = []
    normalized_group_field = _normalize_required_field(group_field)

    for row in rows:
        raw_data = dict(row['raw_data'])
        group_value = str(raw_data.get(normalized_group_field) or '').strip()
        classified_row = {
            'source_row_number': row['source_row_number'],
            'raw_data': raw_data,
            'group_value': group_value or None,
            'matched_conversation_id': None,
            'matched_conversation_name': None,
            'matched_rule_id': None,
            'match_status': 'invalid',
            'error_message': None,
        }

        if not group_value:
            classified_rows.append(classified_row)
            continue

        match_result = match_resolver(group_value)
        if bool(match_result.get('matched')):
            classified_row.update(
                {
                    'group_value': group_value,
                    'matched_conversation_id': match_result.get('matched_conversation_id'),
                    'matched_conversation_name': match_result.get('matched_conversation_name'),
                    'matched_rule_id': match_result.get('matched_rule_id'),
                    'match_status': 'matched',
                    'error_message': None,
                }
            )
        else:
            classified_row.update(
                {
                    'group_value': group_value,
                    'match_status': 'unmatched',
                    'error_message': '未匹配到群聊',
                }
            )

        classified_rows.append(classified_row)

    return classified_rows


def calculate_batch_stats(classified_rows: list[dict[str, Any]]) -> dict[str, int]:
    total_rows = len(classified_rows)
    invalid_rows = sum(1 for row in classified_rows if row['match_status'] == 'invalid')
    matched_rows = sum(1 for row in classified_rows if row['match_status'] == 'matched')
    unmatched_rows = sum(1 for row in classified_rows if row['match_status'] == 'unmatched')
    valid_rows = matched_rows + unmatched_rows

    return {
        'total_rows': total_rows,
        'valid_rows': valid_rows,
        'invalid_rows': invalid_rows,
        'matched_rows': matched_rows,
        'unmatched_rows': unmatched_rows,
    }


def _find_missing_fields(
    headers: list[str],
    variable_profile: dict[str, Any],
    *,
    include_group_field: bool,
) -> list[str]:
    normalized_headers = {_normalize_required_field(header) for header in headers}
    required_fields: list[str] = []

    if include_group_field:
        group_field = _normalize_required_field(variable_profile.get('group_field'))
        if group_field:
            required_fields.append(group_field)

    for rule in variable_profile.get('mapping_rules') or []:
        source_field = _normalize_required_field(rule.get('source_field'))
        if source_field:
            required_fields.append(source_field)

    missing_fields: list[str] = []
    seen: set[str] = set()
    for field in required_fields:
        if field in seen:
            continue
        seen.add(field)
        if field not in normalized_headers:
            missing_fields.append(field)

    return missing_fields


def _normalize_required_field(value: Any) -> str:
    return str(value or '').strip()
