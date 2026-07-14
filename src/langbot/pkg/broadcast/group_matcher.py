from __future__ import annotations

import re
from typing import Any, Callable


def match_group(
    *,
    group_value: str,
    rules: list[dict[str, Any]],
    group_names: list[dict[str, Any] | str],
    compile_regex: Callable[[str], re.Pattern[str]] | None = None,
) -> dict[str, Any]:
    return match_groups(
        rows=[{'group_value': group_value}],
        rules=rules,
        group_names=group_names,
        compile_regex=compile_regex,
    )[0]


def match_groups(
    *,
    rows: list[dict[str, Any]],
    rules: list[dict[str, Any]],
    group_names: list[dict[str, Any] | str],
    compile_regex: Callable[[str], re.Pattern[str]] | None = None,
) -> list[dict[str, Any]]:
    regex_compiler = compile_regex or re.compile
    regex_cache: dict[str, re.Pattern[str]] = {}
    normalized_group_names: dict[str, list[str]] = {}
    for item in group_names:
        if isinstance(item, dict):
            name = str(item.get('name') or '').strip()
            if not name:
                continue
            normalized_group_names.setdefault(name, [])
            external_id = str(item.get('external_conversation_id') or '').strip()
            if external_id:
                normalized_group_names[name].append(external_id)
            continue
        name = str(item).strip()
        if name:
            normalized_group_names.setdefault(name, [])
    ordered_rules = sorted(
        (rule for rule in rules if bool(rule.get('enabled'))),
        key=lambda item: (-int(item.get('priority') or 0), int(item.get('id') or 0)),
    )

    results: list[dict[str, Any]] = []
    for row in rows:
        group_value = str(row.get('group_value') or '')
        matched = {
            'matched': False,
            'matched_conversation_id': None,
            'matched_conversation_name': None,
            'matched_rule_id': None,
            'target_resolution_status': None,
        }

        for rule in ordered_rules:
            if _rule_matches(group_value, rule, regex_cache, regex_compiler):
                target_id, resolution_status = _resolve_target_conversation(
                    target_name=str(rule.get('target_conversation_name') or '').strip(),
                    target_id=str(rule.get('target_conversation_id') or '').strip(),
                    group_names=normalized_group_names,
                )
                matched = {
                    'matched': True,
                    'matched_conversation_id': target_id,
                    'matched_conversation_name': rule.get('target_conversation_name'),
                    'matched_rule_id': rule.get('id'),
                    'target_resolution_status': resolution_status,
                }
                break

        if not matched['matched'] and group_value in normalized_group_names:
            target_id, resolution_status = _resolve_target_conversation(
                target_name=group_value,
                target_id='',
                group_names=normalized_group_names,
            )
            matched = {
                'matched': True,
                'matched_conversation_id': target_id,
                'matched_conversation_name': group_value,
                'matched_rule_id': None,
                'target_resolution_status': resolution_status,
            }

        results.append(matched)

    return results


def _resolve_target_conversation(
    *,
    target_name: str,
    target_id: str,
    group_names: dict[str, list[str]],
) -> tuple[str | None, str]:
    if target_id:
        return target_id, 'resolved'
    candidates = group_names.get(target_name, [])
    if len(candidates) == 1:
        return candidates[0], 'resolved'
    if len(candidates) > 1:
        return None, 'ambiguous'
    return None, 'unresolved'


def _rule_matches(
    group_value: str,
    rule: dict[str, Any],
    regex_cache: dict[str, re.Pattern[str]],
    regex_compiler: Callable[[str], re.Pattern[str]],
) -> bool:
    match_type = str(rule.get('match_type') or '').strip()
    expression = str(rule.get('match_expression') or '')

    if match_type == 'exact':
        return group_value == expression
    if match_type == 'contains':
        return expression in group_value
    if match_type == 'regex':
        pattern = regex_cache.get(expression)
        if pattern is None:
            pattern = regex_compiler(expression)
            regex_cache[expression] = pattern
        return pattern.search(group_value) is not None
    return False
