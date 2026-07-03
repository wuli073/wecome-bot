from __future__ import annotations

from typing import Any, Callable


PLACEHOLDER_REMAINED_MESSAGE = '草稿中仍存在未替换内容，请检查变量配置后重新生成'


def build_render_variables(
    *,
    rows: list[dict[str, Any]],
    mapping_rules: list[dict[str, Any]],
) -> dict[str, str]:
    render_variables: dict[str, str] = {}
    for rule in sorted(mapping_rules, key=lambda item: int(item.get('order') or 0)):
        source_field = str(rule.get('source_field') or '').strip()
        variable_key = str(rule.get('variable_key') or '').strip()
        merge_mode = str(rule.get('merge_mode') or '').strip()
        if not source_field or not variable_key:
            continue

        values = [_normalize_value(row.get('raw_data', {}).get(source_field)) for row in rows]
        values = [value for value in values if value]
        render_variables[variable_key] = _merge_values(values, merge_mode)

    return render_variables


def generate_group_draft(
    *,
    group_value: str,
    rows: list[dict[str, Any]],
    mapping_rules: list[dict[str, Any]],
    matched_conversation_name: str | None,
    template_name: str,
    template_content: str,
    render_template: Callable[[str, dict[str, str]], dict[str, Any]],
) -> dict[str, Any]:
    render_variables = build_render_variables(rows=rows, mapping_rules=mapping_rules)
    render_result = render_template(template_content, render_variables)
    rendered_text = str(render_result.get('rendered_text') or '')
    missing_variables = [str(item) for item in (render_result.get('missing_variables') or []) if str(item)]

    status = 'pending_review'
    error_message: str | None = None
    target_conversation_name = matched_conversation_name

    if missing_variables:
        status = 'invalid'
        error_message = f'模板缺少以下变量值：{"、".join(missing_variables)}'
    elif '{{' in rendered_text or '}}' in rendered_text:
        status = 'invalid'
        error_message = PLACEHOLDER_REMAINED_MESSAGE
    elif not matched_conversation_name:
        status = 'invalid'
        target_conversation_name = None
        error_message = '未匹配到群聊'
    elif not bool(render_result.get('valid', False)) and not rendered_text:
        status = 'invalid'
        error_message = str(render_result.get('error_message') or '模板渲染失败')
    elif not bool(render_result.get('valid', False)):
        status = 'invalid'
        error_message = str(render_result.get('error_message') or PLACEHOLDER_REMAINED_MESSAGE)

    return {
        'group_value': group_value,
        'target_conversation_name': target_conversation_name,
        'template_name_snapshot': template_name,
        'template_content_snapshot': template_content,
        'render_variables': render_variables,
        'draft_text': rendered_text,
        'status': status,
        'error_message': error_message,
    }


def _merge_values(values: list[str], merge_mode: str) -> str:
    if merge_mode == 'first':
        return values[0] if values else ''
    if merge_mode == 'lines':
        return '\n'.join(values)
    if merge_mode == 'unique_lines':
        return '\n'.join(_dedupe_keep_order(values))
    if merge_mode == 'commas':
        return ','.join(values)
    if merge_mode == 'unique_commas':
        return ','.join(_dedupe_keep_order(values))
    return values[0] if values else ''


def _dedupe_keep_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped


def _normalize_value(value: Any) -> str:
    normalized = str(value or '').strip()
    if normalized.lower() in {'none', 'null'}:
        return ''
    return normalized
