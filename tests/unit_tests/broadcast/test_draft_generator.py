from __future__ import annotations


def _mapping_rules() -> list[dict[str, object]]:
    return [
        {
            'source_field': '客户名称',
            'variable_key': 'customer_name',
            'merge_mode': 'first',
            'order': 1,
        },
        {
            'source_field': '订单号',
            'variable_key': 'order_numbers',
            'merge_mode': 'lines',
            'order': 2,
        },
        {
            'source_field': '联系人',
            'variable_key': 'contacts',
            'merge_mode': 'unique_commas',
            'order': 3,
        },
        {
            'source_field': '备注',
            'variable_key': 'notes',
            'merge_mode': 'unique_lines',
            'order': 4,
        },
        {
            'source_field': '标签',
            'variable_key': 'tags',
            'merge_mode': 'commas',
            'order': 5,
        },
    ]


def test_build_render_variables_supports_all_five_merge_modes_and_variable_key_keys():
    from langbot.pkg.broadcast.draft_generator import build_render_variables

    render_variables = build_render_variables(
        rows=[
            {
                'raw_data': {
                    '客户名称': ' Acme ',
                    '订单号': 'SO-001',
                    '联系人': '张三',
                    '备注': '  首次联系  ',
                    '标签': 'VIP',
                }
            },
            {
                'raw_data': {
                    '客户名称': 'Northwind',
                    '订单号': 'SO-002',
                    '联系人': '张三',
                    '备注': '首次联系',
                    '标签': '重点',
                }
            },
            {
                'raw_data': {
                    '客户名称': 'Ignored',
                    '订单号': 'SO-003',
                    '联系人': '李四',
                    '备注': '复购',
                    '标签': 'VIP',
                }
            },
        ],
        mapping_rules=_mapping_rules(),
    )

    assert render_variables == {
        'customer_name': 'Acme',
        'order_numbers': 'SO-001\nSO-002\nSO-003',
        'contacts': '张三,李四',
        'notes': '首次联系\n复购',
        'tags': 'VIP,重点,VIP',
    }
    assert '客户名称' not in render_variables


def test_generate_draft_returns_pending_review_when_match_and_render_are_valid():
    from langbot.pkg.broadcast.draft_generator import generate_group_draft

    draft = generate_group_draft(
        group_value='Acme',
        rows=[
            {
                'raw_data': {
                    '客户名称': 'Acme',
                    '订单号': 'SO-001',
                    '联系人': '张三',
                    '备注': '首次联系',
                    '标签': 'VIP',
                }
            }
        ],
        mapping_rules=_mapping_rules(),
        matched_conversation_name='Acme Group',
        template_name='Arrival Reminder',
        template_content='您好 {{customer_name}}，订单：{{order_numbers}}，联系人：{{contacts}}',
        render_template=lambda template, variables: {
            'rendered_text': template.replace('{{customer_name}}', variables['customer_name'])
            .replace('{{order_numbers}}', variables['order_numbers'])
            .replace('{{contacts}}', variables['contacts']),
            'missing_variables': [],
            'valid': True,
        },
    )

    assert draft['status'] == 'pending_review'
    assert draft['target_conversation_name'] == 'Acme Group'
    assert draft['error_message'] is None
    assert draft['draft_text'] == '您好 Acme，订单：SO-001，联系人：张三'


def test_generate_draft_keeps_preview_text_for_unmatched_group_invalid_draft():
    from langbot.pkg.broadcast.draft_generator import generate_group_draft

    draft = generate_group_draft(
        group_value='Acme',
        rows=[
            {
                'raw_data': {
                    '客户名称': 'Acme',
                    '订单号': 'SO-001',
                    '联系人': '张三',
                    '备注': '首次联系',
                    '标签': 'VIP',
                }
            }
        ],
        mapping_rules=_mapping_rules(),
        matched_conversation_name=None,
        template_name='Arrival Reminder',
        template_content='您好 {{customer_name}}，订单：{{order_numbers}}',
        render_template=lambda template, variables: {
            'rendered_text': template.replace('{{customer_name}}', variables['customer_name']).replace(
                '{{order_numbers}}',
                variables['order_numbers'],
            ),
            'missing_variables': [],
            'valid': True,
        },
    )

    assert draft['status'] == 'invalid'
    assert draft['target_conversation_name'] is None
    assert draft['error_message'] == '未匹配到群聊'
    assert draft['draft_text'] == '您好 Acme，订单：SO-001'


def test_generate_draft_keeps_preview_text_when_variables_are_missing():
    from langbot.pkg.broadcast.draft_generator import generate_group_draft

    draft = generate_group_draft(
        group_value='Acme',
        rows=[
            {
                'raw_data': {
                    '客户名称': 'Acme',
                    '订单号': '',
                    '联系人': '张三',
                    '备注': '',
                    '标签': '',
                }
            }
        ],
        mapping_rules=_mapping_rules(),
        matched_conversation_name='Acme Group',
        template_name='Arrival Reminder',
        template_content='您好 {{customer_name}}，订单：{{order_numbers}}，联系人：{{contacts}}',
        render_template=lambda template, variables: {
            'rendered_text': '您好 Acme，订单：{{order_numbers}}，联系人：张三',
            'missing_variables': ['order_numbers'],
            'valid': False,
        },
    )

    assert draft['status'] == 'invalid'
    assert draft['error_message'] == '模板缺少以下变量值：order_numbers'
    assert draft['draft_text'] == '您好 Acme，订单：{{order_numbers}}，联系人：张三'


def test_generate_draft_keeps_preview_text_when_placeholders_remain_after_render():
    from langbot.pkg.broadcast.draft_generator import generate_group_draft

    draft = generate_group_draft(
        group_value='Acme',
        rows=[
            {
                'raw_data': {
                    '客户名称': 'Acme',
                    '订单号': 'SO-001',
                    '联系人': '张三',
                    '备注': '',
                    '标签': '',
                }
            }
        ],
        mapping_rules=_mapping_rules(),
        matched_conversation_name='Acme Group',
        template_name='Arrival Reminder',
        template_content='您好 {{customer_name}}，订单：{{order_numbers}}，备注：{{notes}}',
        render_template=lambda template, variables: {
            'rendered_text': '您好 Acme，订单：SO-001，备注：{{notes}}',
            'missing_variables': [],
            'valid': False,
        },
    )

    assert draft['status'] == 'invalid'
    assert draft['error_message'] == '草稿中仍存在未替换内容，请检查变量配置后重新生成'
    assert draft['draft_text'] == '您好 Acme，订单：SO-001，备注：{{notes}}'


def test_generate_draft_allows_empty_text_only_when_render_fails_completely():
    from langbot.pkg.broadcast.draft_generator import generate_group_draft

    draft = generate_group_draft(
        group_value='Acme',
        rows=[
            {
                'raw_data': {
                    '客户名称': 'Acme',
                    '订单号': 'SO-001',
                    '联系人': '张三',
                    '备注': '',
                    '标签': '',
                }
            }
        ],
        mapping_rules=_mapping_rules(),
        matched_conversation_name='Acme Group',
        template_name='Arrival Reminder',
        template_content='您好 {{customer_name}}',
        render_template=lambda template, variables: {
            'rendered_text': '',
            'missing_variables': [],
            'valid': False,
            'error_message': '模板渲染失败',
        },
    )

    assert draft['status'] == 'invalid'
    assert draft['draft_text'] == ''
    assert draft['error_message'] == '模板渲染失败'
