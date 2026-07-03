from __future__ import annotations

import datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

from langbot.pkg.entity.persistence import broadcast as persistence_broadcast


pytestmark = pytest.mark.asyncio


class _RawConnectionPersistenceManager:
    def __init__(self) -> None:
        self.engine = create_async_engine('sqlite+aiosqlite:///:memory:')

    async def initialize(self) -> None:
        async with self.engine.begin() as conn:
            await conn.run_sync(persistence_broadcast.BroadcastTemplate.__table__.create)
            await conn.run_sync(persistence_broadcast.BroadcastVariableProfile.__table__.create)
            await conn.run_sync(persistence_broadcast.BroadcastGroupRule.__table__.create)
            await conn.run_sync(persistence_broadcast.BroadcastGroupName.__table__.create)

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


@pytest.fixture
async def repository_fixture():
    from langbot.pkg.broadcast.repository import BroadcastRepository

    persistence_mgr = _RawConnectionPersistenceManager()
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
