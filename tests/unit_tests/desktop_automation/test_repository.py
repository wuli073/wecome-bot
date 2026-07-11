from __future__ import annotations

import datetime

import pytest
import sqlalchemy
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

from langbot.pkg.desktop_automation.repository import DesktopAutomationRepository
from langbot.pkg.entity.persistence import bot as persistence_bot
from langbot.pkg.entity.persistence import database_mode as persistence_database_mode


pytestmark = pytest.mark.asyncio


class _RawConnectionPersistenceManager:
    def __init__(self) -> None:
        self.engine = create_async_engine('sqlite+aiosqlite:///:memory:')

    async def initialize(self) -> None:
        async with self.engine.begin() as conn:
            await conn.run_sync(persistence_bot.Bot.__table__.create)
            await conn.run_sync(persistence_database_mode.DatabaseConversation.__table__.create)
            await conn.run_sync(persistence_database_mode.DatabaseMessage.__table__.create)
            await conn.run_sync(persistence_database_mode.ChannelAccount.__table__.create)
            await conn.run_sync(persistence_database_mode.BotChannelBinding.__table__.create)
            await conn.run_sync(persistence_database_mode.ReplyDraft.__table__.create)
            await conn.run_sync(persistence_database_mode.DesktopAutomationRun.__table__.create)

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
    persistence_mgr = _RawConnectionPersistenceManager()
    await persistence_mgr.initialize()
    try:
        yield DesktopAutomationRepository(persistence_mgr), persistence_mgr
    finally:
        await persistence_mgr.dispose()


async def test_get_message_context_materializes_raw_connection_model_rows(repository_fixture):
    repository, persistence_mgr = repository_fixture

    async with persistence_mgr.engine.begin() as conn:
        await conn.execute(
            sqlalchemy.insert(persistence_bot.Bot).values(
                {
                    'uuid': 'bot-1',
                    'name': 'Bot 1',
                    'description': '',
                    'adapter': 'wxwork_database',
                    'adapter_config': {'connector_id': 'wxwork-local'},
                    'enable': True,
                }
            )
        )
        conversation_result = await conn.execute(
            sqlalchemy.insert(persistence_database_mode.DatabaseConversation).values(
                {
                    'connector_id': 'wxwork-local',
                    'source': 'wxwork',
                    'external_conversation_id': 'S:100_200',
                    'conversation_name': 'Customer A',
                    'conversation_type': 'direct',
                    'last_message_at': datetime.datetime.now(datetime.timezone.utc),
                }
            )
        )
        conversation_id = int(conversation_result.inserted_primary_key[0])
        message_result = await conn.execute(
            sqlalchemy.insert(persistence_database_mode.DatabaseMessage).values(
                {
                    'event_id': 'evt-1',
                    'message_key': 'key-1',
                    'conversation_id': conversation_id,
                    'external_message_id': '101',
                    'sender_id': '200',
                    'sender_name': 'Customer A',
                    'content': 'Need pricing details',
                    'message_type': 'text',
                    'sent_at': datetime.datetime.now(datetime.timezone.utc),
                    'observed_at': datetime.datetime.now(datetime.timezone.utc),
                    'status': 'draft_ready',
                    'draft_text': 'Persisted draft',
                    'draft_source': 'pipeline',
                }
            )
        )
        message_id = int(message_result.inserted_primary_key[0])
        channel_account_result = await conn.execute(
            sqlalchemy.insert(persistence_database_mode.ChannelAccount).values(
                {
                    'connector_id': 'wxwork-local',
                    'channel_type': 'wxwork',
                    'external_account_id': 'wxwork-local:default',
                    'display_name': 'WeCom Local',
                    'enabled': True,
                }
            )
        )
        channel_account_id = int(channel_account_result.inserted_primary_key[0])
        await conn.execute(
            sqlalchemy.insert(persistence_database_mode.BotChannelBinding).values(
                {
                    'bot_uuid': 'bot-1',
                    'channel_account_id': channel_account_id,
                    'enabled': True,
                    'auto_generate_draft': False,
                }
            )
        )
        draft_result = await conn.execute(
            sqlalchemy.insert(persistence_database_mode.ReplyDraft).values(
                {
                    'message_id': message_id,
                    'bot_uuid': 'bot-1',
                    'processing_run_id': None,
                    'content': 'Persisted draft',
                    'source': 'pipeline',
                    'status': 'active',
                    'version': 1,
                }
            )
        )
        draft_id = int(draft_result.inserted_primary_key[0])

    context = await repository.get_message_context('bot-1', message_id, draft_id)

    assert context['message']['id'] == message_id
    assert context['message']['conversation_id'] == conversation_id
    assert context['conversation']['id'] == conversation_id
    assert context['draft']['id'] == draft_id
    assert context['draft']['message_id'] == message_id
    assert context['active_draft_count'] == 1


async def test_count_conversations_by_name_counts_only_same_connector_and_name(repository_fixture):
    repository, persistence_mgr = repository_fixture

    async with persistence_mgr.engine.begin() as conn:
        await conn.execute(
            sqlalchemy.insert(persistence_database_mode.DatabaseConversation),
            [
                {
                    'connector_id': 'wxwork-local',
                    'source': 'wxwork',
                    'external_conversation_id': 'S:100_200',
                    'conversation_name': 'Customer A',
                    'conversation_type': 'direct',
                    'last_message_at': datetime.datetime.now(datetime.timezone.utc),
                },
                {
                    'connector_id': 'wxwork-local',
                    'source': 'wxwork',
                    'external_conversation_id': 'S:100_201',
                    'conversation_name': 'Customer A',
                    'conversation_type': 'direct',
                    'last_message_at': datetime.datetime.now(datetime.timezone.utc),
                },
                {
                    'connector_id': 'other-connector',
                    'source': 'wxwork',
                    'external_conversation_id': 'S:100_202',
                    'conversation_name': 'Customer A',
                    'conversation_type': 'direct',
                    'last_message_at': datetime.datetime.now(datetime.timezone.utc),
                },
                {
                    'connector_id': 'wxwork-local',
                    'source': 'wxwork',
                    'external_conversation_id': 'S:100_203',
                    'conversation_name': 'Customer B',
                    'conversation_type': 'direct',
                    'last_message_at': datetime.datetime.now(datetime.timezone.utc),
                },
            ],
        )

    assert await repository.count_conversations_by_name('wxwork-local', 'Customer A') == 2
    assert await repository.count_conversations_by_name('wxwork-local', 'Customer B') == 1
    assert await repository.count_conversations_by_name('wxwork-local', 'Missing') == 0
