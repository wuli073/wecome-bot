from __future__ import annotations


def test_match_group_prefers_priority_desc_then_id_asc_for_exact_contains_and_regex():
    from langbot.pkg.broadcast.group_matcher import match_group

    result = match_group(
        group_value='Acme North',
        rules=[
            {
                'id': 20,
                'enabled': True,
                'priority': 5,
                'match_type': 'contains',
                'match_expression': 'Acme',
                'target_conversation_name': 'Contains Group',
            },
            {
                'id': 10,
                'enabled': True,
                'priority': 10,
                'match_type': 'regex',
                'match_expression': '^Acme North$',
                'target_conversation_name': 'Regex Group',
            },
            {
                'id': 5,
                'enabled': True,
                'priority': 10,
                'match_type': 'exact',
                'match_expression': 'Acme North',
                'target_conversation_name': 'Exact Group',
            },
        ],
        group_names=[],
    )

    assert result == {
        'matched': True,
        'matched_conversation_name': 'Exact Group',

        'matched_conversation_id': None,
        'matched_rule_id': 5,
        'target_resolution_status': 'deferred',
    }


def test_match_group_skips_disabled_rules():
    from langbot.pkg.broadcast.group_matcher import match_group

    result = match_group(
        group_value='Acme North',
        rules=[
            {
                'id': 1,
                'enabled': False,
                'priority': 100,
                'match_type': 'exact',
                'match_expression': 'Acme North',
                'target_conversation_name': 'Disabled Group',
            },
            {
                'id': 2,
                'enabled': True,
                'priority': 1,
                'match_type': 'contains',
                'match_expression': 'Acme',
                'target_conversation_name': 'Enabled Group',
            },
        ],
        group_names=[],
    )

    assert result == {
        'matched': True,
        'matched_conversation_name': 'Enabled Group',

        'matched_conversation_id': None,
        'matched_rule_id': 2,
        'target_resolution_status': 'deferred',
    }


def test_match_group_does_not_fall_back_to_cached_group_names_when_no_rule_matches():
    from langbot.pkg.broadcast.group_matcher import match_group

    result = match_group(
        group_value='Northwind Team',
        rules=[
            {
                'id': 1,
                'enabled': True,
                'priority': 1,
                'match_type': 'contains',
                'match_expression': 'Acme',
                'target_conversation_name': 'Acme Group',
            },
        ],
        group_names=[
            {'name': 'Northwind Team', 'external_conversation_id': None},
            {'name': 'Other Group', 'external_conversation_id': None},
        ],
    )

    assert result == {
        'matched': False,
        'matched_conversation_name': None,
        'matched_conversation_id': None,
        'matched_rule_id': None,
        'target_resolution_status': None,
    }


def test_match_group_ignores_cached_duplicate_names_when_no_rule_matches():
    from langbot.pkg.broadcast.group_matcher import match_group

    result = match_group(
        group_value='Northwind Team',
        rules=[],
        group_names=[
            {'name': 'Northwind Team', 'external_conversation_id': 'group-1'},
            {'name': 'Northwind Team', 'external_conversation_id': 'group-2'},
        ],
    )

    assert result == {
        'matched': False,
        'matched_conversation_name': None,
        'matched_conversation_id': None,
        'matched_rule_id': None,
        'target_resolution_status': None,
    }


def test_match_group_returns_unmatched_when_no_rule_or_same_name_group_matches():
    from langbot.pkg.broadcast.group_matcher import match_group

    result = match_group(
        group_value='Unknown Team',
        rules=[],
        group_names=['Northwind Team'],
    )

    assert result == {
        'matched': False,
        'matched_conversation_name': None,

        'matched_conversation_id': None,
        'matched_rule_id': None,
        'target_resolution_status': None,
    }


def test_match_group_caches_compiled_regex_within_one_matching_run():
    from langbot.pkg.broadcast.group_matcher import match_groups

    rows = [
        {'group_value': 'Acme-001'},
        {'group_value': 'Acme-002'},
    ]
    rules = [
        {
            'id': 1,
            'enabled': True,
            'priority': 10,
            'match_type': 'regex',
            'match_expression': r'^Acme-\d+$',
            'target_conversation_name': 'Acme Regex Group',
        }
    ]

    compiled_patterns: list[str] = []

    results = match_groups(
        rows=rows,
        rules=rules,
        group_names=[],
        compile_regex=lambda expression: compiled_patterns.append(expression) or __import__('re').compile(expression),
    )

    assert [item['matched_conversation_name'] for item in results] == ['Acme Regex Group', 'Acme Regex Group']
    assert compiled_patterns == [r'^Acme-\d+$']
