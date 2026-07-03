from __future__ import annotations

import datetime

import pytest
import sqlalchemy
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

from langbot.pkg.entity.persistence import broadcast as persistence_broadcast


pytestmark = pytest.mark.asyncio


class _RawConnectionPersistenceManager:
    def __init__(self) -> None:
        self.engine = create_async_engine('sqlite+aiosqlite:///:memory:')
        sqlalchemy.event.listen(self.engine.sync_engine, 'connect', self._enable_sqlite_foreign_keys)

    @staticmethod
    def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute('PRAGMA foreign_keys=ON')
        cursor.close()

    async def initialize(self) -> None:
        async with self.engine.begin() as conn:
            await conn.run_sync(persistence_broadcast.BroadcastTemplate.__table__.create)
            await conn.run_sync(persistence_broadcast.BroadcastVariableProfile.__table__.create)
            await conn.run_sync(persistence_broadcast.BroadcastGroupRule.__table__.create)
            await conn.run_sync(persistence_broadcast.BroadcastGroupName.__table__.create)
            await conn.run_sync(persistence_broadcast.BroadcastImportBatch.__table__.create)
            await conn.run_sync(persistence_broadcast.BroadcastImportRow.__table__.create)
            await conn.run_sync(persistence_broadcast.BroadcastDraft.__table__.create)

    async def dispose(self) -> None:
        await self.engine.dispose()

    async def execute_async(self, *args, conn: AsyncConnection | None = None, **kwargs):
        if conn is not None:
            return await conn.execute(*args, **kwargs)

        async with self.engine.connect() as standalone_conn:
            result = await standalone_conn.execute(*args, **kwargs)
            await standalone_conn.commit()
            return result

    def serialize_model(self, model, data, masked_columns=None):
        masked_columns = masked_columns or []
        return {
            column.name: getattr(data, column.name)
            if not isinstance(getattr(data, column.name), datetime.datetime)
            else getattr(data, column.name).isoformat()
            for column in model.__table__.columns
            if column.name not in masked_columns
        }


class _NoForeignKeysPersistenceManager(_RawConnectionPersistenceManager):
    def __init__(self) -> None:
        self.engine = create_async_engine('sqlite+aiosqlite:///:memory:')


@pytest.fixture
async def repository_fixture():
    from langbot.pkg.broadcast.repository import BroadcastRepository

    persistence_mgr = _RawConnectionPersistenceManager()
    await persistence_mgr.initialize()
    try:
        yield BroadcastRepository(persistence_mgr), persistence_mgr
    finally:
        await persistence_mgr.dispose()


@pytest.fixture
async def repository_without_foreign_keys_fixture():
    from langbot.pkg.broadcast.repository import BroadcastRepository

    persistence_mgr = _NoForeignKeysPersistenceManager()
    await persistence_mgr.initialize()
    try:
        yield BroadcastRepository(persistence_mgr), persistence_mgr
    finally:
        await persistence_mgr.dispose()


def _scope(bot_uuid: str = 'bot-1', connector_id: str = 'wxwork-local') -> dict[str, str]:
    return {
        'bot_uuid': bot_uuid,
        'connector_id': connector_id,
    }


async def test_template_crud_is_scoped_by_bot_and_connector(repository_fixture):
    repository, persistence_mgr = repository_fixture

    async with persistence_mgr.engine.begin() as conn:
        template_id = await repository.create_template(
            conn,
            {
                **_scope(),
                'name': 'Arrival Reminder',
                'content': 'Hello {{customer_name}}',
                'variables': ['customer_name'],
                'enabled': True,
            },
        )
        await repository.create_template(
            conn,
            {
                **_scope(bot_uuid='bot-2'),
                'name': 'Arrival Reminder',
                'content': 'Hello {{customer_name}}',
                'variables': ['customer_name'],
                'enabled': True,
            },
        )

    templates = await repository.list_templates(**_scope())
    assert [template.name for template in templates] == ['Arrival Reminder']

    updated = await repository.update_template(
        template_id,
        bot_uuid='bot-1',
        connector_id='wxwork-local',
        updates={
            'name': 'Arrival Reminder v2',
            'content': 'Hi {{customer_name}}',
            'variables': ['customer_name'],
            'enabled': False,
        },
    )
    assert updated is not None
    assert updated.name == 'Arrival Reminder v2'
    assert updated.enabled is False

    missing = await repository.update_template(
        template_id,
        bot_uuid='bot-1',
        connector_id='other-connector',
        updates={'name': 'should-not-update'},
    )
    assert missing is None

    deleted = await repository.delete_template(
        template_id,
        bot_uuid='bot-1',
        connector_id='wxwork-local',
    )
    assert deleted is True
    assert await repository.list_templates(**_scope()) == []


async def test_variable_profile_upsert_is_unique_per_scope(repository_fixture):
    repository, persistence_mgr = repository_fixture

    async with persistence_mgr.engine.begin() as conn:
        profile_id = await repository.upsert_variable_profile(
            conn,
            {
                **_scope(),
                'group_field': 'customer_name',
                'mapping_rules': [
                    {
                        'source_field': 'Customer Name',
                        'variable_key': 'customer_name',
                        'merge_mode': 'first',
                        'order': 1,
                    }
                ],
            },
        )
        second_profile_id = await repository.upsert_variable_profile(
            conn,
            {
                **_scope(),
                'group_field': 'conversation_name',
                'mapping_rules': [
                    {
                        'source_field': 'Conversation',
                        'variable_key': 'conversation_name',
                        'merge_mode': 'first',
                        'order': 1,
                    }
                ],
            },
        )

    assert second_profile_id == profile_id
    profile = await repository.get_variable_profile(**_scope())
    assert profile is not None
    assert profile.group_field == 'conversation_name'
    assert profile.mapping_rules == [
        {
            'source_field': 'Conversation',
            'variable_key': 'conversation_name',
            'merge_mode': 'first',
            'order': 1,
        }
    ]


async def test_group_rules_are_ordered_by_priority_desc_then_id_desc(repository_fixture):
    repository, persistence_mgr = repository_fixture

    async with persistence_mgr.engine.begin() as conn:
        await repository.create_group_rule(
            conn,
            {
                **_scope(),
                'source_value': 'Acme',
                'match_type': 'exact',
                'match_expression': 'Acme',
                'target_conversation_name': 'Acme Group',
                'priority': 10,
                'enabled': True,
            },
        )
        await repository.create_group_rule(
            conn,
            {
                **_scope(),
                'source_value': 'Globex',
                'match_type': 'contains',
                'match_expression': 'Globex',
                'target_conversation_name': 'Globex Group',
                'priority': 10,
                'enabled': True,
            },
        )
        await repository.create_group_rule(
            conn,
            {
                **_scope(),
                'source_value': 'Northwind',
                'match_type': 'regex',
                'match_expression': '^North',
                'target_conversation_name': 'Northwind Group',
                'priority': 5,
                'enabled': False,
            },
        )

    rules = await repository.list_group_rules(**_scope())
    assert [rule.source_value for rule in rules] == ['Globex', 'Acme', 'Northwind']


async def test_group_name_delete_is_scoped_by_id_and_scope(repository_fixture):
    repository, persistence_mgr = repository_fixture

    async with persistence_mgr.engine.begin() as conn:
        group_name_id = await repository.create_group_name(
            conn,
            {
                **_scope(),
                'name': 'Acme Ops Group',
            },
        )
        await repository.create_group_name(
            conn,
            {
                **_scope(bot_uuid='bot-2'),
                'name': 'Acme Ops Group',
            },
        )

    assert await repository.delete_group_name(group_name_id, bot_uuid='bot-1', connector_id='other') is False
    assert await repository.delete_group_name(
        group_name_id,
        bot_uuid='bot-1',
        connector_id='wxwork-local',
    ) is True
    remaining = await repository.list_group_names(bot_uuid='bot-2', connector_id='wxwork-local')
    assert [group_name.name for group_name in remaining] == ['Acme Ops Group']


async def test_import_batch_crud_is_scoped_and_uses_passed_connection(repository_fixture):
    repository, persistence_mgr = repository_fixture

    conn = await persistence_mgr.engine.connect()
    tx = await conn.begin()
    try:
        batch_id = await repository.create_import_batch(
            conn,
            {
                **_scope(),
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
            },
        )
        await repository.create_import_batch(
            conn,
            {
                **_scope(bot_uuid='bot-2'),
                'original_file_name': 'other.csv',
                'file_type': 'csv',
                'worksheet_name': None,
                'status': 'imported',
                'drafts_stale': False,
                'total_rows': 1,
                'valid_rows': 1,
                'invalid_rows': 0,
                'matched_rows': 1,
                'unmatched_rows': 0,
            },
        )
        batch = await repository.get_import_batch(
            batch_id,
            bot_uuid='bot-1',
            connector_id='wxwork-local',
            conn=conn,
        )
        assert batch is not None
        assert batch.original_file_name == 'customers.csv'
    finally:
        await tx.rollback()
        await conn.close()

    assert await repository.list_import_batches(**_scope()) == []


async def test_update_template_and_group_rule_return_uncommitted_values_within_transaction(repository_fixture):
    repository, persistence_mgr = repository_fixture

    conn = await persistence_mgr.engine.connect()
    tx = await conn.begin()
    try:
        template_id = await repository.create_template(
            conn,
            {
                **_scope(),
                'name': 'Arrival Reminder',
                'content': 'Hello {{customer_name}}',
                'variables': ['customer_name'],
                'enabled': True,
            },
        )
        rule_id = await repository.create_group_rule(
            conn,
            {
                **_scope(),
                'source_value': 'Acme',
                'match_type': 'exact',
                'match_expression': 'Acme',
                'target_conversation_name': 'Acme Group',
                'priority': 10,
                'enabled': True,
            },
        )

        updated_template = await repository.update_template(
            template_id,
            bot_uuid='bot-1',
            connector_id='wxwork-local',
            updates={
                'name': 'Arrival Reminder v2',
                'content': 'Hi {{customer_name}}',
                'variables': ['customer_name'],
                'enabled': False,
            },
            conn=conn,
        )
        updated_rule = await repository.update_group_rule(
            rule_id,
            bot_uuid='bot-1',
            connector_id='wxwork-local',
            updates={
                'target_conversation_name': 'Acme Group Updated',
                'enabled': False,
            },
            conn=conn,
        )

        assert updated_template is not None
        assert updated_template.name == 'Arrival Reminder v2'
        assert updated_template.enabled is False
        assert updated_rule is not None
        assert updated_rule.target_conversation_name == 'Acme Group Updated'
        assert updated_rule.enabled is False
    finally:
        await tx.rollback()
        await conn.close()


async def test_import_rows_can_be_rebuilt_and_filtered_by_batch_and_status(repository_fixture):
    repository, persistence_mgr = repository_fixture

    async with persistence_mgr.engine.begin() as conn:
        batch_id = await repository.create_import_batch(
            conn,
            {
                **_scope(),
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
            },
        )
        await repository.replace_import_rows(
            conn,
            import_batch_id=batch_id,
            rows=[
                {
                    'source_row_number': 2,
                    'raw_data': {'客户名称': 'Acme', '订单号': 'SO-001'},
                    'group_value': 'Acme',
                    'matched_conversation_name': 'Acme Group',
                    'matched_rule_id': None,
                    'match_status': 'matched',
                    'error_message': None,
                },
                {
                    'source_row_number': 3,
                    'raw_data': {'客户名称': 'Northwind', '订单号': 'SO-002'},
                    'group_value': 'Northwind',
                    'matched_conversation_name': None,
                    'matched_rule_id': None,
                    'match_status': 'unmatched',
                    'error_message': '未匹配到群聊',
                },
            ],
        )
        await repository.replace_import_rows(
            conn,
            import_batch_id=batch_id,
            rows=[
                {
                    'source_row_number': 4,
                    'raw_data': {'客户名称': '', '订单号': 'SO-003'},
                    'group_value': None,
                    'matched_conversation_name': None,
                    'matched_rule_id': None,
                    'match_status': 'invalid',
                    'error_message': None,
                }
            ],
        )

    rows = await repository.list_import_rows(
        import_batch_id=batch_id,
        bot_uuid='bot-1',
        connector_id='wxwork-local',
    )
    assert [row.source_row_number for row in rows] == [4]

    filtered_rows = await repository.list_import_rows(
        import_batch_id=batch_id,
        bot_uuid='bot-1',
        connector_id='wxwork-local',
        match_status='invalid',
    )
    assert [row.match_status for row in filtered_rows] == ['invalid']


async def test_import_batch_detail_queries_support_keyword_and_pagination(repository_fixture):
    repository, persistence_mgr = repository_fixture

    async with persistence_mgr.engine.begin() as conn:
        batch_id = await repository.create_import_batch(
            conn,
            {
                **_scope(),
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
            },
        )
        await repository.replace_import_rows(
            conn,
            import_batch_id=batch_id,
            rows=[
                {
                    'source_row_number': 2,
                    'raw_data': {'客户名称': 'Acme', '订单号': 'SO-001'},
                    'group_value': 'Acme',
                    'matched_conversation_name': 'Acme Group',
                    'matched_rule_id': None,
                    'match_status': 'matched',
                    'error_message': None,
                },
                {
                    'source_row_number': 3,
                    'raw_data': {'客户名称': 'Northwind', '订单号': 'SO-002'},
                    'group_value': 'Northwind',
                    'matched_conversation_name': None,
                    'matched_rule_id': None,
                    'match_status': 'unmatched',
                    'error_message': '未匹配到群聊',
                },
                {
                    'source_row_number': 4,
                    'raw_data': {'客户名称': 'Globex', '订单号': 'SO-003'},
                    'group_value': 'Globex',
                    'matched_conversation_name': 'Globex Group',
                    'matched_rule_id': None,
                    'match_status': 'matched',
                    'error_message': None,
                },
            ],
        )

    page = await repository.list_import_rows(
        import_batch_id=batch_id,
        bot_uuid='bot-1',
        connector_id='wxwork-local',
        keyword='Group',
        page=2,
        page_size=1,
    )
    assert [row.matched_conversation_name for row in page] == ['Globex Group']


async def test_drafts_can_be_rebuilt_queried_updated_and_deleted_in_scope(repository_fixture):
    repository, persistence_mgr = repository_fixture

    async with persistence_mgr.engine.begin() as conn:
        template_id = await repository.create_template(
            conn,
            {
                **_scope(),
                'name': 'Arrival Reminder',
                'content': 'Hello {{customer_name}}',
                'variables': ['customer_name'],
                'enabled': True,
            },
        )
        batch_id = await repository.create_import_batch(
            conn,
            {
                **_scope(),
                'original_file_name': 'customers.csv',
                'file_type': 'csv',
                'worksheet_name': None,
                'status': 'matched',
                'drafts_stale': False,
                'total_rows': 2,
                'valid_rows': 2,
                'invalid_rows': 0,
                'matched_rows': 1,
                'unmatched_rows': 1,
            },
        )
        await repository.replace_drafts(
            conn,
            import_batch_id=batch_id,
            bot_uuid='bot-1',
            connector_id='wxwork-local',
            drafts=[
                {
                    'bot_uuid': 'bot-1',
                    'connector_id': 'wxwork-local',
                    'import_batch_id': batch_id,
                    'group_value': 'Acme',
                    'target_conversation_name': 'Acme Group',
                    'template_id': template_id,
                    'template_name_snapshot': 'Arrival Reminder',
                    'template_content_snapshot': 'Hello {{customer_name}}',
                    'render_variables': {'customer_name': 'Acme'},
                    'draft_text': 'Hello Acme',
                    'status': 'pending_review',
                    'error_message': None,
                },
                {
                    'bot_uuid': 'bot-1',
                    'connector_id': 'wxwork-local',
                    'import_batch_id': batch_id,
                    'group_value': 'Northwind',
                    'target_conversation_name': None,
                    'template_id': template_id,
                    'template_name_snapshot': 'Arrival Reminder',
                    'template_content_snapshot': 'Hello {{customer_name}}',
                    'render_variables': {'customer_name': 'Northwind'},
                    'draft_text': 'Hello Northwind',
                    'status': 'invalid',
                    'error_message': '未匹配到群聊',
                },
            ],
        )

    drafts = await repository.list_drafts(
        bot_uuid='bot-1',
        connector_id='wxwork-local',
        import_batch_id=batch_id,
    )
    assert [draft.group_value for draft in drafts] == ['Acme', 'Northwind']

    invalid_drafts = await repository.list_drafts(
        bot_uuid='bot-1',
        connector_id='wxwork-local',
        import_batch_id=batch_id,
        status='invalid',
        keyword='North',
    )
    assert [draft.group_value for draft in invalid_drafts] == ['Northwind']

    updated = await repository.update_draft(
        drafts[0].id,
        bot_uuid='bot-1',
        connector_id='wxwork-local',
        updates={'draft_text': 'Hello Acme Updated', 'status': 'ready'},
    )
    assert updated is not None
    assert updated.draft_text == 'Hello Acme Updated'
    assert updated.status == 'ready'

    deleted = await repository.delete_import_batch(
        batch_id,
        bot_uuid='bot-1',
        connector_id='wxwork-local',
    )
    assert deleted is True
    assert await repository.list_drafts(bot_uuid='bot-1', connector_id='wxwork-local') == []


async def test_batch_update_draft_statuses_is_scoped_and_atomic(repository_fixture):
    repository, persistence_mgr = repository_fixture

    async with persistence_mgr.engine.begin() as conn:
        template_id = await repository.create_template(
            conn,
            {
                **_scope(),
                'name': 'Arrival Reminder',
                'content': 'Hello {{customer_name}}',
                'variables': ['customer_name'],
                'enabled': True,
            },
        )
        batch_id = await repository.create_import_batch(
            conn,
            {
                **_scope(),
                'original_file_name': 'customers.csv',
                'file_type': 'csv',
                'worksheet_name': None,
                'status': 'drafts_generated',
                'drafts_stale': False,
                'total_rows': 2,
                'valid_rows': 2,
                'invalid_rows': 0,
                'matched_rows': 2,
                'unmatched_rows': 0,
            },
        )
        await repository.replace_drafts(
            conn,
            import_batch_id=batch_id,
            bot_uuid='bot-1',
            connector_id='wxwork-local',
            drafts=[
                {
                    'bot_uuid': 'bot-1',
                    'connector_id': 'wxwork-local',
                    'import_batch_id': batch_id,
                    'group_value': 'Acme',
                    'target_conversation_name': 'Acme Group',
                    'template_id': template_id,
                    'template_name_snapshot': 'Arrival Reminder',
                    'template_content_snapshot': 'Hello {{customer_name}}',
                    'render_variables': {'customer_name': 'Acme'},
                    'draft_text': 'Hello Acme',
                    'status': 'pending_review',
                    'error_message': None,
                },
                {
                    'bot_uuid': 'bot-1',
                    'connector_id': 'wxwork-local',
                    'import_batch_id': batch_id,
                    'group_value': 'Globex',
                    'target_conversation_name': 'Globex Group',
                    'template_id': template_id,
                    'template_name_snapshot': 'Arrival Reminder',
                    'template_content_snapshot': 'Hello {{customer_name}}',
                    'render_variables': {'customer_name': 'Globex'},
                    'draft_text': 'Hello Globex',
                    'status': 'pending_review',
                    'error_message': None,
                },
            ],
        )
        other_batch_id = await repository.create_import_batch(
            conn,
            {
                **_scope(bot_uuid='bot-2'),
                'original_file_name': 'other.csv',
                'file_type': 'csv',
                'worksheet_name': None,
                'status': 'drafts_generated',
                'drafts_stale': False,
                'total_rows': 1,
                'valid_rows': 1,
                'invalid_rows': 0,
                'matched_rows': 1,
                'unmatched_rows': 0,
            },
        )
        await repository.replace_drafts(
            conn,
            import_batch_id=other_batch_id,
            bot_uuid='bot-2',
            connector_id='wxwork-local',
            drafts=[
                {
                    'bot_uuid': 'bot-2',
                    'connector_id': 'wxwork-local',
                    'import_batch_id': other_batch_id,
                    'group_value': 'Other',
                    'target_conversation_name': 'Other Group',
                    'template_id': template_id,
                    'template_name_snapshot': 'Arrival Reminder',
                    'template_content_snapshot': 'Hello {{customer_name}}',
                    'render_variables': {'customer_name': 'Other'},
                    'draft_text': 'Hello Other',
                    'status': 'pending_review',
                    'error_message': None,
                }
            ],
        )

    drafts = await repository.list_drafts(
        bot_uuid='bot-1',
        connector_id='wxwork-local',
        import_batch_id=batch_id,
    )
    updated_count = await repository.update_draft_statuses(
        draft_ids=[drafts[0].id, drafts[1].id],
        bot_uuid='bot-1',
        connector_id='wxwork-local',
        status='ready',
    )
    assert updated_count == 2

    cross_scope_count = await repository.update_draft_statuses(
        draft_ids=[drafts[0].id, drafts[1].id, drafts[1].id + 1],
        bot_uuid='bot-1',
        connector_id='wxwork-local',
        status='pending_review',
    )
    assert cross_scope_count == 0


async def test_delete_operations_preserve_phase3_semantics_without_sqlite_foreign_keys(
    repository_without_foreign_keys_fixture,
):
    repository, persistence_mgr = repository_without_foreign_keys_fixture

    async with persistence_mgr.engine.begin() as conn:
        template_id = await repository.create_template(
            conn,
            {
                **_scope(),
                'name': 'Arrival Reminder',
                'content': 'Hello {{customer_name}}',
                'variables': ['customer_name'],
                'enabled': True,
            },
        )
        rule_id = await repository.create_group_rule(
            conn,
            {
                **_scope(),
                'source_value': 'Acme',
                'match_type': 'exact',
                'match_expression': 'Acme',
                'target_conversation_name': 'Acme Group',
                'priority': 10,
                'enabled': True,
            },
        )
        batch_id = await repository.create_import_batch(
            conn,
            {
                **_scope(),
                'original_file_name': 'customers.csv',
                'file_type': 'csv',
                'worksheet_name': None,
                'status': 'drafts_generated',
                'drafts_stale': False,
                'total_rows': 1,
                'valid_rows': 1,
                'invalid_rows': 0,
                'matched_rows': 1,
                'unmatched_rows': 0,
            },
        )
        await repository.replace_import_rows(
            conn,
            import_batch_id=batch_id,
            rows=[
                {
                    'source_row_number': 2,
                    'raw_data': {'Customer Name': 'Acme'},
                    'group_value': 'Acme',
                    'matched_conversation_name': 'Acme Group',
                    'matched_rule_id': rule_id,
                    'match_status': 'matched',
                    'error_message': None,
                }
            ],
        )
        await repository.replace_drafts(
            conn,
            import_batch_id=batch_id,
            bot_uuid='bot-1',
            connector_id='wxwork-local',
            drafts=[
                {
                    'bot_uuid': 'bot-1',
                    'connector_id': 'wxwork-local',
                    'import_batch_id': batch_id,
                    'group_value': 'Acme',
                    'target_conversation_name': 'Acme Group',
                    'template_id': template_id,
                    'template_name_snapshot': 'Arrival Reminder',
                    'template_content_snapshot': 'Hello {{customer_name}}',
                    'render_variables': {'customer_name': 'Acme'},
                    'draft_text': 'Hello Acme',
                    'status': 'pending_review',
                    'error_message': None,
                }
            ],
        )

    deleted_rule = await repository.delete_group_rule(
        rule_id,
        bot_uuid='bot-1',
        connector_id='wxwork-local',
    )
    assert deleted_rule is True
    rows_after_rule_delete = await repository.list_import_rows(
        import_batch_id=batch_id,
        bot_uuid='bot-1',
        connector_id='wxwork-local',
    )
    assert len(rows_after_rule_delete) == 1
    assert rows_after_rule_delete[0].matched_rule_id is None

    deleted_template = await repository.delete_template(
        template_id,
        bot_uuid='bot-1',
        connector_id='wxwork-local',
    )
    assert deleted_template is True
    drafts_after_template_delete = await repository.list_drafts(
        bot_uuid='bot-1',
        connector_id='wxwork-local',
        import_batch_id=batch_id,
    )
    assert len(drafts_after_template_delete) == 1
    assert drafts_after_template_delete[0].template_id is None

    deleted_batch = await repository.delete_import_batch(
        batch_id,
        bot_uuid='bot-1',
        connector_id='wxwork-local',
    )
    assert deleted_batch is True
    assert await repository.list_import_rows(
        import_batch_id=batch_id,
        bot_uuid='bot-1',
        connector_id='wxwork-local',
    ) == []
    assert await repository.list_drafts(
        bot_uuid='bot-1',
        connector_id='wxwork-local',
        import_batch_id=batch_id,
    ) == []


async def test_delete_operations_do_not_mutate_other_scope_when_sqlite_foreign_keys_are_disabled(
    repository_without_foreign_keys_fixture,
):
    repository, persistence_mgr = repository_without_foreign_keys_fixture

    async with persistence_mgr.engine.begin() as conn:
        template_id = await repository.create_template(
            conn,
            {
                **_scope(),
                'name': 'Arrival Reminder',
                'content': 'Hello {{customer_name}}',
                'variables': ['customer_name'],
                'enabled': True,
            },
        )
        rule_id = await repository.create_group_rule(
            conn,
            {
                **_scope(),
                'source_value': 'Acme',
                'match_type': 'exact',
                'match_expression': 'Acme',
                'target_conversation_name': 'Acme Group',
                'priority': 10,
                'enabled': True,
            },
        )
        batch_id = await repository.create_import_batch(
            conn,
            {
                **_scope(),
                'original_file_name': 'customers.csv',
                'file_type': 'csv',
                'worksheet_name': None,
                'status': 'drafts_generated',
                'drafts_stale': False,
                'total_rows': 1,
                'valid_rows': 1,
                'invalid_rows': 0,
                'matched_rows': 1,
                'unmatched_rows': 0,
            },
        )
        await repository.replace_import_rows(
            conn,
            import_batch_id=batch_id,
            rows=[
                {
                    'source_row_number': 2,
                    'raw_data': {'Customer Name': 'Acme'},
                    'group_value': 'Acme',
                    'matched_conversation_name': 'Acme Group',
                    'matched_rule_id': rule_id,
                    'match_status': 'matched',
                    'error_message': None,
                }
            ],
        )
        await repository.replace_drafts(
            conn,
            import_batch_id=batch_id,
            bot_uuid='bot-1',
            connector_id='wxwork-local',
            drafts=[
                {
                    'bot_uuid': 'bot-1',
                    'connector_id': 'wxwork-local',
                    'import_batch_id': batch_id,
                    'group_value': 'Acme',
                    'target_conversation_name': 'Acme Group',
                    'template_id': template_id,
                    'template_name_snapshot': 'Arrival Reminder',
                    'template_content_snapshot': 'Hello {{customer_name}}',
                    'render_variables': {'customer_name': 'Acme'},
                    'draft_text': 'Hello Acme',
                    'status': 'pending_review',
                    'error_message': None,
                }
            ],
        )

    deleted_rule = await repository.delete_group_rule(
        rule_id,
        bot_uuid='bot-2',
        connector_id='wxwork-local',
    )
    deleted_template = await repository.delete_template(
        template_id,
        bot_uuid='bot-2',
        connector_id='wxwork-local',
    )
    deleted_batch = await repository.delete_import_batch(
        batch_id,
        bot_uuid='bot-2',
        connector_id='wxwork-local',
    )

    assert deleted_rule is False
    assert deleted_template is False
    assert deleted_batch is False

    rows = await repository.list_import_rows(
        import_batch_id=batch_id,
        bot_uuid='bot-1',
        connector_id='wxwork-local',
    )
    drafts = await repository.list_drafts(
        bot_uuid='bot-1',
        connector_id='wxwork-local',
        import_batch_id=batch_id,
    )
    assert len(rows) == 1
    assert rows[0].matched_rule_id == rule_id
    assert len(drafts) == 1
    assert drafts[0].template_id == template_id
