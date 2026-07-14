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
    # Group-name snapshots are only a UI convenience. A rule match must not
    # depend on a connector's cached conversation list.
    del group_names
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
                matched = {
                    'matched': True,
                    'matched_conversation_id': str(rule.get('target_conversation_id') or '').strip() or None,
                    'matched_conversation_name': rule.get('target_conversation_name'),
                    'matched_rule_id': rule.get('id'),
                    'target_resolution_status': 'deferred',
                }
                break

        results.append(matched)

    return results


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
