from __future__ import annotations

import sys
import types
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import quart
from werkzeug.datastructures import FileStorage

core_app_stub = types.ModuleType('langbot.pkg.core.app')
core_app_stub.Application = object
_previous_core_app_module = sys.modules.get('langbot.pkg.core.app')
sys.modules['langbot.pkg.core.app'] = core_app_stub

from langbot.pkg.api.http.controller.groups.broadcast import (  # noqa: E402
    BroadcastRouterGroup,
)
from langbot.pkg.broadcast.errors import (  # noqa: E402
    BROADCAST_DRAFT_INVALID_CONFIRM_FORBIDDEN,
    BROADCAST_IMPORT_GROUP_FIELD_CONFIRMATION_REQUIRED,
    BROADCAST_IMPORT_GROUP_RULE_BULK_ASSIGN_FAILED,
    BATCH_VALIDATION_FAILED,
    BroadcastError,
)

if _previous_core_app_module is not None:
    sys.modules['langbot.pkg.core.app'] = _previous_core_app_module
else:
    sys.modules.pop('langbot.pkg.core.app', None)


pytestmark = pytest.mark.asyncio


async def _make_client():
    app = quart.Quart(__name__)
    ap = SimpleNamespace(
        instance_config=SimpleNamespace(data={'api': {'global_api_key': ''}}),
        user_service=SimpleNamespace(
            verify_jwt_token=AsyncMock(return_value='user@example.com'),
            get_user_by_email=AsyncMock(return_value=SimpleNamespace(user='user@example.com')),
            get_first_user=AsyncMock(return_value=SimpleNamespace(user='user@example.com')),
        ),
        broadcast_service=SimpleNamespace(
            validate_scope=AsyncMock(
                side_effect=lambda scope: {
                    'bot_uuid': scope['bot_uuid'],
                    'connector_id': scope['connector_id'],
                }
            ),
            list_templates=AsyncMock(return_value=[]),
            create_template=AsyncMock(
                return_value={
                    'id': 1,
                    'name': 'Arrival Reminder',
                    'content': 'Hello {{name}}',
                    'variables': ['name'],
                    'enabled': True,
                }
            ),
            update_template=AsyncMock(
                return_value={
                    'id': 1,
                    'name': 'Arrival Reminder v2',
                    'content': 'Hi {{name}}',
                    'variables': ['name'],
                    'enabled': False,
                }
            ),
            delete_template=AsyncMock(return_value={'deleted': True}),
            render_template=AsyncMock(
                return_value={
                    'rendered_text': 'Hello Acme',
                    'required_variables': ['name'],
                    'missing_variables': [],
                    'valid': True,
                }
            ),
            get_variable_profile=AsyncMock(return_value={'group_field': None, 'mapping_rules': []}),
            save_variable_profile=AsyncMock(return_value={'group_field': 'customer_name', 'mapping_rules': []}),
            list_group_rules=AsyncMock(return_value=[]),
            create_group_rule=AsyncMock(
                return_value={
                    'id': 1,
                    'source_value': 'Acme',
                    'match_type': 'exact',
                    'match_expression': 'Acme',
                    'target_conversation_name': 'Acme Group',

                    'target_conversation_id': 'Acme Group',
                    'priority': 1,
                    'enabled': True,
                }
            ),
            update_group_rule=AsyncMock(
                return_value={
                    'id': 1,
                    'source_value': 'Acme',
                    'match_type': 'exact',
                    'match_expression': 'Acme',
                    'target_conversation_name': 'Acme Group',

                    'target_conversation_id': 'Acme Group',
                    'priority': 2,
                    'enabled': False,
                }
            ),
            delete_group_rule=AsyncMock(return_value={'deleted': True}),
            match_group_rule=AsyncMock(
                return_value={
                    'matched': True,
                    'rule_id': 1,
                    'target_conversation_name': 'Acme Group',

                    'target_conversation_id': 'Acme Group',
                    'match_type': 'exact',
                }
            ),
            list_group_names=AsyncMock(return_value=[]),
            create_group_names=AsyncMock(return_value={'group_names': []}),
            sync_group_names_from_conversations=AsyncMock(
                return_value={
                    'scanned': 1,
                    'inserted': 1,
                    'updated': 0,
                    'unchanged': 0,
                    'skipped': 0,
                    'errors': [],
                }
            ),
            delete_group_name=AsyncMock(return_value={'deleted': True}),
            upload_import=AsyncMock(
                return_value={
                    'id': 11,
                    'original_file_name': 'customers.csv',
                    'file_type': 'csv',
                    'worksheet_name': None,
                    'status': 'imported',
                    'drafts_stale': False,
                    'total_rows': 3,
                    'valid_rows': 2,
                    'invalid_rows': 1,
                    'matched_rows': 1,
                    'unmatched_rows': 1,
                    'created_at': '2026-07-04T00:00:00',
                    'updated_at': '2026-07-04T00:00:00',
                }
            ),
            list_import_batches=AsyncMock(return_value=[]),
            list_import_groups=AsyncMock(
                return_value={
                    'page': 1,
                    'page_size': 50,
                    'total': 1,
                    'total_pages': 1,
                    'raw_row_total': 1,
                    'group_total': 1,
                    'matched_group_total': 1,
                    'unmatched_group_total': 0,
                    'invalid_group_total': 0,
                    'conflict_group_total': 0,
                    'order_number_field_configured': False,
                    'groups': [],
                }
            ),
            list_group_rule_candidates=AsyncMock(
                return_value={
                    'import_batch_id': 11,
                    'group_field_used': '客户名称',
                    'raw_row_total': 5,
                    'unique_customer_total': 5,
                    'stats': {
                        'new_count': 1,
                        'configured_count': 1,
                        'needs_repair_count': 1,
                        'conflict_count': 1,
                        'invalid_count': 1,
                    },
                    'items': [],
                    'page': 1,
                    'page_size': 50,
                    'total': 1,
                    'total_pages': 1,
                }
            ),
            upsert_import_group_template_assignments=AsyncMock(
                return_value={
                    'items': [
                        {
                            'group_key': 'group-a',
                            'template_id': 12,
                        }
                    ]
                }
            ),
            bulk_assign_import_group_rules=AsyncMock(
                return_value={
                    'created_count': 1,
                    'group_field_used': '瀹㈡埛鍚嶇О',
                    'group_field_source': 'configured',
                    'items': [
                        {
                            'group_key': 'group-a',
                            'customer_name': 'Acme',
                            'rule_id': 31,
                            'target_conversation_id': 'group-1',
                            'target_conversation_name': 'Acme Group',
                        }
                    ],
                }
            ),
            get_import_detail=AsyncMock(
                return_value={
                    'id': 11,
                    'original_file_name': 'customers.csv',
                    'file_type': 'csv',
                    'worksheet_name': None,
                    'status': 'imported',
                    'drafts_stale': False,
                    'total_rows': 3,
                    'valid_rows': 2,
                    'invalid_rows': 1,
                    'matched_rows': 1,
                    'unmatched_rows': 1,
                    'created_at': '2026-07-04T00:00:00',
                    'updated_at': '2026-07-04T00:00:00',
                    'rows': [],
                    'page': 1,
                    'page_size': 20,
                    'total': 3,
                    'total_pages': 1,
                }
            ),
            delete_import=AsyncMock(return_value={'deleted': True}),
            rematch_import=AsyncMock(
                return_value={
                    'id': 11,
                    'original_file_name': 'customers.csv',
                    'file_type': 'csv',
                    'worksheet_name': None,
                    'status': 'matched',
                    'drafts_stale': True,
                    'total_rows': 3,
                    'valid_rows': 2,
                    'invalid_rows': 1,
                    'matched_rows': 1,
                    'unmatched_rows': 1,
                    'created_at': '2026-07-04T00:00:00',
                    'updated_at': '2026-07-04T00:00:00',
                    'rows': [],
                    'page': 1,
                    'page_size': 50,
                    'total': 3,
                    'total_pages': 1,
                }
            ),
            generate_import_drafts=AsyncMock(
                return_value={
                    'total_group_count': 2,
                    'pending_review_count': 1,
                    'invalid_count': 1,
                    'unmatched_group_count': 1,
                }
            ),
            list_drafts=AsyncMock(return_value=[]),
            get_draft_detail=AsyncMock(return_value={'id': 21, 'status': 'pending_review'}),
            update_draft_text=AsyncMock(
                return_value={'id': 21, 'status': 'pending_review', 'draft_text': 'Updated', 'message': None}
            ),
            update_draft_statuses=AsyncMock(return_value={'updated_count': 1}),
            create_execution_batch=AsyncMock(
                return_value={
                    'id': 301,
                    'mode': 'paste_only',
                    'status': 'created',
                    'total_tasks': 1,
                    'pending_tasks': 1,
                    'tasks': [
                        {
                            'id': 401,
                            'draft_id': 21,
                            'status': 'pending',
                            'action': 'paste_draft',
                        }
                    ],
                }
            ),
            list_execution_batches=AsyncMock(return_value=[]),
            get_execution_batch_detail=AsyncMock(return_value={'id': 301, 'tasks': []}),
            get_execution_task_detail=AsyncMock(return_value={'id': 401, 'status': 'pending'}),
            start_execution_task=AsyncMock(return_value={'id': 401, 'status': 'succeeded'}),
            cancel_execution_task=AsyncMock(return_value={'id': 401, 'status': 'cancelled'}),
            retry_execution_task=AsyncMock(return_value={'id': 401, 'status': 'pending'}),
            list_execution_attempts=AsyncMock(return_value=[{'id': 501, 'status': 'succeeded'}]),
            get_execution_attempt_detail=AsyncMock(return_value={'id': 501, 'status': 'succeeded'}),
            get_execution_evidence=AsyncMock(return_value={'execution_attempt_id': 501, 'send_triggered': False}),
        ),
    )
    router = BroadcastRouterGroup(ap, app)
    await router.initialize()
    return app.test_client(), ap


async def test_get_templates_uses_query_scope_and_validates_once():
    client, ap = await _make_client()

    response = await client.get(
        '/api/v1/broadcast/templates?bot_uuid=bot-1&connector_id=wxwork-local',
        headers={'Authorization': 'Bearer valid-user-token'},
    )
    payload = await response.get_json()

    assert response.status_code == 200
    assert payload['code'] == 0
    ap.broadcast_service.validate_scope.assert_awaited_once_with(
        {
            'bot_uuid': 'bot-1',
            'connector_id': 'wxwork-local',
        }
    )
    ap.broadcast_service.list_templates.assert_awaited_once()


async def test_render_template_uses_body_scope():
    client, ap = await _make_client()

    response = await client.post(
        '/api/v1/broadcast/templates/render',
        headers={'Authorization': 'Bearer valid-user-token'},
        json={
            'bot_uuid': 'bot-1',
            'connector_id': 'wxwork-local',
            'content': 'Hello {{name}}',
            'variables': {'name': 'Acme'},
        },
    )
    payload = await response.get_json()

    assert response.status_code == 200
    assert payload['data']['rendered_text'] == 'Hello Acme'
    ap.broadcast_service.validate_scope.assert_awaited_once_with(
        {
            'bot_uuid': 'bot-1',
            'connector_id': 'wxwork-local',
        }
    )


async def test_invalid_scope_returns_400_without_a_scope_required_error():
    client, ap = await _make_client()
    ap.broadcast_service.validate_scope = AsyncMock(side_effect=BroadcastError(BATCH_VALIDATION_FAILED))

    response = await client.get(
        '/api/v1/broadcast/templates',
        headers={'Authorization': 'Bearer valid-user-token'},
    )
    payload = await response.get_json()

    assert response.status_code == 400
    assert payload['msg'] == BATCH_VALIDATION_FAILED


async def test_variable_profile_error_returns_code_and_chinese_message_details():
    client, ap = await _make_client()
    ap.broadcast_service.save_variable_profile = AsyncMock(
        side_effect=BroadcastError(
            'BROADCAST_VARIABLE_PROFILE_INVALID',
            '变量配置填写不完整，请检查后重试',
            ['请填写分组字段', '第 2 条规则缺少消息变量'],
        )
    )

    response = await client.put(
        '/api/v1/broadcast/variable-profile',
        headers={'Authorization': 'Bearer valid-user-token'},
        json={
            'bot_uuid': 'bot-1',
            'connector_id': 'wxwork-local',
            'group_field': '',
            'mapping_rules': [],
        },
    )
    payload = await response.get_json()

    assert response.status_code == 400
    assert payload['msg'] == 'BROADCAST_VARIABLE_PROFILE_INVALID'
    assert payload['message'] == '变量配置填写不完整，请检查后重试'
    assert payload['details'] == ['请填写分组字段', '第 2 条规则缺少消息变量']


async def test_get_variable_profile_returns_empty_config_not_404():
    client, ap = await _make_client()

    response = await client.get(
        '/api/v1/broadcast/variable-profile?bot_uuid=bot-1&connector_id=wxwork-local',
        headers={'Authorization': 'Bearer valid-user-token'},
    )
    payload = await response.get_json()

    assert response.status_code == 200
    assert payload['data'] == {'group_field': None, 'mapping_rules': []}


async def test_post_template_uses_body_scope():
    client, ap = await _make_client()

    response = await client.post(
        '/api/v1/broadcast/templates',
        headers={'Authorization': 'Bearer valid-user-token'},
        json={
            'bot_uuid': 'bot-1',
            'connector_id': 'wxwork-local',
            'name': 'Arrival Reminder',
            'content': 'Hello {{name}}',
            'enabled': True,
        },
    )
    payload = await response.get_json()

    assert response.status_code == 200
    assert payload['data']['name'] == 'Arrival Reminder'
    ap.broadcast_service.create_template.assert_awaited_once()


async def test_delete_template_uses_query_scope():
    client, ap = await _make_client()

    response = await client.delete(
        '/api/v1/broadcast/templates/1?bot_uuid=bot-1&connector_id=wxwork-local',
        headers={'Authorization': 'Bearer valid-user-token'},
    )
    payload = await response.get_json()

    assert response.status_code == 200
    assert payload['data'] == {'deleted': True}
    ap.broadcast_service.delete_template.assert_awaited_once_with(
        1,
        {'bot_uuid': 'bot-1', 'connector_id': 'wxwork-local'},
    )


async def test_upload_import_uses_multipart_and_body_scope():
    client, ap = await _make_client()

    response = await client.post(
        '/api/v1/broadcast/imports',
        headers={'Authorization': 'Bearer valid-user-token'},
        form={
            'bot_uuid': 'bot-1',
            'connector_id': 'wxwork-local',
        },
        files={
            'file': FileStorage(
                stream=BytesIO('客户名称,订单号\nAcme,SO-001\n'.encode('utf-8')),
                filename='customers.csv',
            ),
        },
    )
    payload = await response.get_json()

    assert response.status_code == 200
    assert payload['data']['id'] == 11
    assert 'rows' not in payload['data']
    ap.broadcast_service.validate_scope.assert_awaited_once_with(
        {'bot_uuid': 'bot-1', 'connector_id': 'wxwork-local'}
    )
    ap.broadcast_service.upload_import.assert_awaited_once()


async def test_upload_import_passes_group_field_override_from_form():
    client, ap = await _make_client()

    response = await client.post(
        '/api/v1/broadcast/imports',
        headers={'Authorization': 'Bearer valid-user-token'},
        form={
            'bot_uuid': 'bot-1',
            'connector_id': 'wxwork-local',
            'group_field_override': '用户名',
        },
        files={
            'file': FileStorage(
                stream=BytesIO('客户名称,订单号\nAcme,SO-001\n'.encode('utf-8')),
                filename='customers.csv',
            ),
        },
    )

    assert response.status_code == 200
    ap.broadcast_service.upload_import.assert_awaited_once_with(
        {'bot_uuid': 'bot-1', 'connector_id': 'wxwork-local'},
        {
            'filename': 'customers.csv',
            'body': '客户名称,订单号\nAcme,SO-001\n'.encode('utf-8'),
            'content_type': '',
            'group_field_override': '用户名',
        },
    )


async def test_sync_group_names_uses_query_scope():
    client, ap = await _make_client()

    response = await client.post(
        '/api/v1/broadcast/group-names/sync?bot_uuid=bot-1&connector_id=wxwork-local',
        headers={'Authorization': 'Bearer valid-user-token'},
    )
    payload = await response.get_json()

    assert response.status_code == 200
    assert payload['data']['inserted'] == 1
    ap.broadcast_service.sync_group_names_from_conversations.assert_awaited_once_with(
        {'bot_uuid': 'bot-1', 'connector_id': 'wxwork-local'}
    )


async def test_get_import_detail_uses_query_scope_and_filters():
    client, ap = await _make_client()

    response = await client.get(
        '/api/v1/broadcast/imports/11?bot_uuid=bot-1&connector_id=wxwork-local&match_status=matched&keyword=Acme&page=1&page_size=20',
        headers={'Authorization': 'Bearer valid-user-token'},
    )
    payload = await response.get_json()

    assert response.status_code == 200
    assert payload['data']['id'] == 11
    assert payload['data']['page'] == 1
    assert payload['data']['page_size'] == 20
    assert payload['data']['total'] == 3
    assert payload['data']['total_pages'] == 1
    ap.broadcast_service.get_import_detail.assert_awaited_once_with(
        11,
        {'bot_uuid': 'bot-1', 'connector_id': 'wxwork-local'},
        {'match_status': 'matched', 'keyword': 'Acme', 'page': 1, 'page_size': 20},
    )


async def test_get_group_rule_candidates_defaults_status_to_new():
    client, ap = await _make_client()

    response = await client.get(
        '/api/v1/broadcast/imports/11/group-rule-candidates?bot_uuid=bot-1&connector_id=wxwork-local',
        headers={'Authorization': 'Bearer valid-user-token'},
    )
    payload = await response.get_json()

    assert response.status_code == 200
    assert payload['data']['import_batch_id'] == 11
    ap.broadcast_service.list_group_rule_candidates.assert_awaited_once_with(
        11,
        {'bot_uuid': 'bot-1', 'connector_id': 'wxwork-local'},
        {'status': 'new', 'keyword': None, 'page': None, 'page_size': None},
    )


async def test_get_group_rule_candidates_uses_query_filters():
    client, ap = await _make_client()

    response = await client.get(
        '/api/v1/broadcast/imports/11/group-rule-candidates?bot_uuid=bot-1&connector_id=wxwork-local&status=conflict&keyword=Acme&page=2&page_size=10',
        headers={'Authorization': 'Bearer valid-user-token'},
    )
    payload = await response.get_json()

    assert response.status_code == 200
    assert payload['data']['page'] == 1
    ap.broadcast_service.list_group_rule_candidates.assert_awaited_once_with(
        11,
        {'bot_uuid': 'bot-1', 'connector_id': 'wxwork-local'},
        {'status': 'conflict', 'keyword': 'Acme', 'page': 2, 'page_size': 10},
    )


async def test_get_group_rule_candidates_rejects_non_numeric_pagination():
    client, ap = await _make_client()

    response = await client.get(
        '/api/v1/broadcast/imports/11/group-rule-candidates?bot_uuid=bot-1&connector_id=wxwork-local&page=abc',
        headers={'Authorization': 'Bearer valid-user-token'},
    )
    payload = await response.get_json()

    assert response.status_code == 400
    assert payload['msg'] == 'BROADCAST_IMPORT_FILE_INVALID'
    ap.broadcast_service.list_group_rule_candidates.assert_not_awaited()


async def test_import_error_keeps_chinese_message_and_details():
    client, ap = await _make_client()
    ap.broadcast_service.upload_import = AsyncMock(
        side_effect=BroadcastError(
            'BROADCAST_IMPORT_FIELDS_MISSING',
            '导入文件缺少以下字段：客户名称、订单号',
            ['客户名称', '订单号'],
        )
    )

    response = await client.post(
        '/api/v1/broadcast/imports',
        headers={'Authorization': 'Bearer valid-user-token'},
        form={
            'bot_uuid': 'bot-1',
            'connector_id': 'wxwork-local',
        },
        files={
            'file': FileStorage(
                stream=BytesIO('订单号\nSO-001\n'.encode('utf-8')),
                filename='customers.csv',
            ),
        },
    )
    payload = await response.get_json()

    assert response.status_code == 400
    assert payload['msg'] == 'BROADCAST_IMPORT_FIELDS_MISSING'
    assert payload['message'] == '导入文件缺少以下字段：客户名称、订单号'
    assert payload['details'] == ['客户名称', '订单号']


async def test_import_group_field_confirmation_error_keeps_object_details_shape():
    client, ap = await _make_client()
    ap.broadcast_service.upload_import = AsyncMock(
        side_effect=BroadcastError(
            'BROADCAST_IMPORT_GROUP_FIELD_CONFIRMATION_REQUIRED',
            '无法唯一确定客户分组字段，请确认后继续导入',
            {
                'headers': ['用户名', '客户名称', '运单号'],
                'candidates': ['用户名', '客户名称'],
                'configured_group_field': '客户',
                'original_file_name': 'customers.csv',
            },
        )
    )

    response = await client.post(
        '/api/v1/broadcast/imports',
        headers={'Authorization': 'Bearer valid-user-token'},
        form={
            'bot_uuid': 'bot-1',
            'connector_id': 'wxwork-local',
        },
        files={
            'file': FileStorage(
                stream=BytesIO('运单号\nSO-001\n'.encode('utf-8')),
                filename='customers.csv',
            ),
        },
    )
    payload = await response.get_json()

    assert response.status_code == 400
    assert payload['msg'] == 'BROADCAST_IMPORT_GROUP_FIELD_CONFIRMATION_REQUIRED'
    assert payload['details'] == {
        'headers': ['用户名', '客户名称', '运单号'],
        'candidates': ['用户名', '客户名称'],
        'configured_group_field': '客户',
        'original_file_name': 'customers.csv',
    }


async def test_import_group_field_override_invalid_error_keeps_object_details_shape():
    client, ap = await _make_client()
    ap.broadcast_service.upload_import = AsyncMock(
        side_effect=BroadcastError(
            'BROADCAST_IMPORT_GROUP_FIELD_OVERRIDE_INVALID',
            '指定的客户分组字段不存在：用户名',
            {
                'group_field_override': '用户名',
                'headers': ['客户名称', '运单号'],
                'original_file_name': 'customers.csv',
            },
        )
    )

    response = await client.post(
        '/api/v1/broadcast/imports',
        headers={'Authorization': 'Bearer valid-user-token'},
        form={
            'bot_uuid': 'bot-1',
            'connector_id': 'wxwork-local',
            'group_field_override': '用户名',
        },
        files={
            'file': FileStorage(
                stream=BytesIO('运单号\nSO-001\n'.encode('utf-8')),
                filename='customers.csv',
            ),
        },
    )
    payload = await response.get_json()

    assert response.status_code == 400
    assert payload['msg'] == 'BROADCAST_IMPORT_GROUP_FIELD_OVERRIDE_INVALID'
    assert payload['details'] == {
        'group_field_override': '用户名',
        'headers': ['客户名称', '运单号'],
        'original_file_name': 'customers.csv',
    }




async def test_import_group_field_confirmation_error_preserves_structured_details():
    client, ap = await _make_client()
    ap.broadcast_service.upload_import = AsyncMock(
        side_effect=BroadcastError(
            BROADCAST_IMPORT_GROUP_FIELD_CONFIRMATION_REQUIRED,
            '无法唯一确定客户分组字段，请确认后继续导入',
            {
                'headers': ['客户', '姓名', '订单号'],
                'candidates': ['客户', '姓名'],
                'configured_group_field': '历史客户字段',
                'original_file_name': 'customers.csv',
            },
        )
    )

    response = await client.post(
        '/api/v1/broadcast/imports',
        headers={'Authorization': 'Bearer valid-user-token'},
        form={
            'bot_uuid': 'bot-1',
            'connector_id': 'wxwork-local',
        },
        files={
            'file': FileStorage(
                stream=BytesIO('客户,姓名,订单号\nAcme,张三,SO-001\n'.encode('utf-8')),
                filename='customers.csv',
            ),
        },
    )
    payload = await response.get_json()

    assert response.status_code == 400
    assert payload['msg'] == BROADCAST_IMPORT_GROUP_FIELD_CONFIRMATION_REQUIRED
    assert isinstance(payload['details'], dict)
    assert payload['details']['headers'] == ['客户', '姓名', '订单号']
    assert payload['details']['candidates'] == ['客户', '姓名']
    assert payload['details']['configured_group_field'] == '历史客户字段'
    assert payload['details']['original_file_name'] == 'customers.csv'

async def test_get_and_put_draft_routes_use_scope_and_payload():
    client, ap = await _make_client()

    detail_response = await client.get(
        '/api/v1/broadcast/drafts/21?bot_uuid=bot-1&connector_id=wxwork-local',
        headers={'Authorization': 'Bearer valid-user-token'},
    )
    assert detail_response.status_code == 200
    ap.broadcast_service.get_draft_detail.assert_awaited_once_with(
        21,
        {'bot_uuid': 'bot-1', 'connector_id': 'wxwork-local'},
    )

    update_response = await client.put(
        '/api/v1/broadcast/drafts/21',
        headers={'Authorization': 'Bearer valid-user-token'},
        json={
            'bot_uuid': 'bot-1',
            'connector_id': 'wxwork-local',
            'draft_text': 'Updated draft',
        },
    )
    assert update_response.status_code == 200
    ap.broadcast_service.update_draft_text.assert_awaited_once_with(
        21,
        {'bot_uuid': 'bot-1', 'connector_id': 'wxwork-local'},
        {
            'bot_uuid': 'bot-1',
            'connector_id': 'wxwork-local',
            'draft_text': 'Updated draft',
        },
    )


async def test_batch_update_draft_status_route_preserves_chinese_error():
    client, ap = await _make_client()
    ap.broadcast_service.update_draft_statuses = AsyncMock(
        side_effect=BroadcastError(
            BROADCAST_DRAFT_INVALID_CONFIRM_FORBIDDEN,
            '当前草稿生成失败，不能直接确认，请修复配置后重新生成',
        )
    )

    response = await client.post(
        '/api/v1/broadcast/drafts/batch-status',
        headers={'Authorization': 'Bearer valid-user-token'},
        json={
            'bot_uuid': 'bot-1',
            'connector_id': 'wxwork-local',
            'draft_ids': [21],
            'status': 'ready',
        },
    )
    payload = await response.get_json()

    assert response.status_code == 400
    assert payload['msg'] == BROADCAST_DRAFT_INVALID_CONFIRM_FORBIDDEN
    assert payload['message'] == '当前草稿生成失败，不能直接确认，请修复配置后重新生成'


async def test_create_and_get_execution_routes_use_scope_and_payload():
    client, ap = await _make_client()

    create_response = await client.post(
        '/api/v1/broadcast/executions',
        headers={'Authorization': 'Bearer valid-user-token'},
        json={
            'bot_uuid': 'bot-1',
            'connector_id': 'wxwork-local',
            'draft_ids': [21],
            'mode': 'paste_only',
            'operator': 'tester@example.com',
        },
    )
    create_payload = await create_response.get_json()
    assert create_response.status_code == 200
    assert create_payload['data']['id'] == 301
    ap.broadcast_service.create_execution_batch.assert_awaited_once_with(
        {'bot_uuid': 'bot-1', 'connector_id': 'wxwork-local'},
        {
            'bot_uuid': 'bot-1',
            'connector_id': 'wxwork-local',
            'draft_ids': [21],
            'mode': 'paste_only',
            'operator': 'tester@example.com',
        },
    )

    list_response = await client.get(
        '/api/v1/broadcast/executions?bot_uuid=bot-1&connector_id=wxwork-local',
        headers={'Authorization': 'Bearer valid-user-token'},
    )
    assert list_response.status_code == 200
    ap.broadcast_service.list_execution_batches.assert_awaited_once_with(
        {'bot_uuid': 'bot-1', 'connector_id': 'wxwork-local'}
    )

    detail_response = await client.get(
        '/api/v1/broadcast/executions/301?bot_uuid=bot-1&connector_id=wxwork-local',
        headers={'Authorization': 'Bearer valid-user-token'},
    )
    assert detail_response.status_code == 200
    ap.broadcast_service.get_execution_batch_detail.assert_awaited_once_with(
        301,
        {'bot_uuid': 'bot-1', 'connector_id': 'wxwork-local'},
    )


async def test_execution_task_routes_use_scope_and_map_service_calls():
    client, ap = await _make_client()

    task_response = await client.get(
        '/api/v1/broadcast/execution-tasks/401?bot_uuid=bot-1&connector_id=wxwork-local',
        headers={'Authorization': 'Bearer valid-user-token'},
    )
    assert task_response.status_code == 200
    ap.broadcast_service.get_execution_task_detail.assert_awaited_once_with(
        401,
        {'bot_uuid': 'bot-1', 'connector_id': 'wxwork-local'},
    )

    start_response = await client.post(
        '/api/v1/broadcast/execution-tasks/401/start',
        headers={'Authorization': 'Bearer valid-user-token'},
        json={'bot_uuid': 'bot-1', 'connector_id': 'wxwork-local'},
    )
    assert start_response.status_code == 200
    ap.broadcast_service.start_execution_task.assert_awaited_once_with(
        401,
        {'bot_uuid': 'bot-1', 'connector_id': 'wxwork-local'},
        {'bot_uuid': 'bot-1', 'connector_id': 'wxwork-local'},
    )

    cancel_response = await client.post(
        '/api/v1/broadcast/execution-tasks/401/cancel',
        headers={'Authorization': 'Bearer valid-user-token'},
        json={'bot_uuid': 'bot-1', 'connector_id': 'wxwork-local'},
    )
    assert cancel_response.status_code == 200
    ap.broadcast_service.cancel_execution_task.assert_awaited_once_with(
        401,
        {'bot_uuid': 'bot-1', 'connector_id': 'wxwork-local'},
        {'bot_uuid': 'bot-1', 'connector_id': 'wxwork-local'},
    )

    retry_response = await client.post(
        '/api/v1/broadcast/execution-tasks/401/retry',
        headers={'Authorization': 'Bearer valid-user-token'},
        json={'bot_uuid': 'bot-1', 'connector_id': 'wxwork-local'},
    )
    assert retry_response.status_code == 200
    ap.broadcast_service.retry_execution_task.assert_awaited_once_with(
        401,
        {'bot_uuid': 'bot-1', 'connector_id': 'wxwork-local'},
        {'bot_uuid': 'bot-1', 'connector_id': 'wxwork-local'},
    )


async def test_execution_attempt_and_evidence_routes_use_scope_and_map_service_calls():
    client, ap = await _make_client()

    attempts_response = await client.get(
        '/api/v1/broadcast/execution-tasks/401/attempts?bot_uuid=bot-1&connector_id=wxwork-local',
        headers={'Authorization': 'Bearer valid-user-token'},
    )
    assert attempts_response.status_code == 200
    ap.broadcast_service.list_execution_attempts.assert_awaited_once_with(
        401,
        {'bot_uuid': 'bot-1', 'connector_id': 'wxwork-local'},
    )

    attempt_response = await client.get(
        '/api/v1/broadcast/execution-attempts/501?bot_uuid=bot-1&connector_id=wxwork-local',
        headers={'Authorization': 'Bearer valid-user-token'},
    )
    assert attempt_response.status_code == 200
    ap.broadcast_service.get_execution_attempt_detail.assert_awaited_once_with(
        501,
        {'bot_uuid': 'bot-1', 'connector_id': 'wxwork-local'},
    )

    evidence_response = await client.get(
        '/api/v1/broadcast/execution-attempts/501/evidence?bot_uuid=bot-1&connector_id=wxwork-local',
        headers={'Authorization': 'Bearer valid-user-token'},
    )
    assert evidence_response.status_code == 200
    ap.broadcast_service.get_execution_evidence.assert_awaited_once_with(
        501,
        {'bot_uuid': 'bot-1', 'connector_id': 'wxwork-local'},
    )


async def test_upload_import_reads_bytes_from_file_stream_when_filestorage_has_no_read():
    stream = BytesIO('客户,运单号\n小满,TEST-20260704-001\n'.encode('utf-8'))
    pseudo_file = SimpleNamespace(
        filename='customers.csv',
        stream=stream,
    )

    payload = BroadcastRouterGroup._build_upload_file_payload(pseudo_file)

    assert payload['filename'] == 'customers.csv'
    assert payload['body'] == '客户,运单号\n小满,TEST-20260704-001\n'.encode('utf-8')


async def test_put_import_group_template_assignments_uses_body_scope():
    client, ap = await _make_client()

    response = await client.put(
        '/api/v1/broadcast/imports/11/group-template-assignments',
        headers={'Authorization': 'Bearer valid-user-token'},
        json={
            'bot_uuid': 'bot-1',
            'connector_id': 'wxwork-local',
            'items': [{'group_key': 'group-a', 'template_id': 12}],
        },
    )
    payload = await response.get_json()

    assert response.status_code == 200
    assert payload['data']['items'][0]['group_key'] == 'group-a'
    ap.broadcast_service.upsert_import_group_template_assignments.assert_awaited_once_with(
        11,
        {'bot_uuid': 'bot-1', 'connector_id': 'wxwork-local'},
        {
            'bot_uuid': 'bot-1',
            'connector_id': 'wxwork-local',
            'items': [{'group_key': 'group-a', 'template_id': 12}],
        },
    )


async def test_put_import_group_template_assignments_accepts_null_template_id():
    client, ap = await _make_client()

    response = await client.put(
        '/api/v1/broadcast/imports/11/group-template-assignments',
        headers={'Authorization': 'Bearer valid-user-token'},
        json={
            'bot_uuid': 'bot-1',
            'connector_id': 'wxwork-local',
            'items': [{'group_key': 'group-a', 'template_id': None}],
        },
    )
    payload = await response.get_json()

    assert response.status_code == 200
    assert payload['data']['items'][0]['template_id'] == 12
    ap.broadcast_service.upsert_import_group_template_assignments.assert_awaited_once_with(
        11,
        {'bot_uuid': 'bot-1', 'connector_id': 'wxwork-local'},
        {
            'bot_uuid': 'bot-1',
            'connector_id': 'wxwork-local',
            'items': [{'group_key': 'group-a', 'template_id': None}],
        },
    )


async def test_post_import_group_rule_bulk_assign_uses_body_scope():
    client, ap = await _make_client()

    response = await client.post(
        '/api/v1/broadcast/imports/11/group-rules/bulk-assign',
        headers={'Authorization': 'Bearer valid-user-token'},
        json={
            'bot_uuid': 'bot-1',
            'connector_id': 'wxwork-local',
            'items': [
                {
                    'group_key': 'group-a',
                    'target_conversation_id': 'group-1',
                }
            ],
        },
    )
    payload = await response.get_json()

    assert response.status_code == 200
    assert payload['data']['created_count'] == 1
    ap.broadcast_service.bulk_assign_import_group_rules.assert_awaited_once_with(
        11,
        {'bot_uuid': 'bot-1', 'connector_id': 'wxwork-local'},
        {
            'bot_uuid': 'bot-1',
            'connector_id': 'wxwork-local',
            'items': [
                {
                    'group_key': 'group-a',
                    'target_conversation_id': 'group-1',
                }
            ],
        },
    )


async def test_post_import_group_rule_bulk_assign_preserves_structured_error_details():
    client, ap = await _make_client()
    ap.broadcast_service.bulk_assign_import_group_rules = AsyncMock(
        side_effect=BroadcastError(
            BROADCAST_IMPORT_GROUP_RULE_BULK_ASSIGN_FAILED,
            '部分分组规则分配失败，请按明细修正后重试',
            {
                'items': [
                    {
                        'code': 'BROADCAST_GROUP_NAME_NOT_FOUND',
                        'message': '目标群聊不存在或未同步稳定 ID',
                        'group_key': 'group-a',
                        'customer_name': 'Acme',
                    }
                ]
            },
        )
    )

    response = await client.post(
        '/api/v1/broadcast/imports/11/group-rules/bulk-assign',
        headers={'Authorization': 'Bearer valid-user-token'},
        json={
            'bot_uuid': 'bot-1',
            'connector_id': 'wxwork-local',
            'items': [
                {
                    'group_key': 'group-a',
                    'target_conversation_id': 'group-404',
                }
            ],
        },
    )
    payload = await response.get_json()

    assert response.status_code == 400
    assert payload['msg'] == BROADCAST_IMPORT_GROUP_RULE_BULK_ASSIGN_FAILED
    assert payload['details']['items'][0]['group_key'] == 'group-a'


async def test_generate_import_drafts_route_passes_group_keys_payload():
    client, ap = await _make_client()

    response = await client.post(
        '/api/v1/broadcast/imports/11/generate-drafts',
        headers={'Authorization': 'Bearer valid-user-token'},
        json={
            'bot_uuid': 'bot-1',
            'connector_id': 'wxwork-local',
            'group_keys': ['group-b', 'group-a'],
            'overwrite_existing': False,
        },
    )

    assert response.status_code == 200
    ap.broadcast_service.generate_import_drafts.assert_awaited_once_with(
        11,
        {'bot_uuid': 'bot-1', 'connector_id': 'wxwork-local'},
        {
            'bot_uuid': 'bot-1',
            'connector_id': 'wxwork-local',
            'group_keys': ['group-b', 'group-a'],
            'overwrite_existing': False,
        },
    )
