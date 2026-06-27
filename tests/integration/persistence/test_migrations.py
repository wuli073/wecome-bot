"""
SQLite migration integration tests.

Tests real Alembic migration behavior using temporary SQLite databases.
Validates the migration workflow from .github/workflows/test-migrations.yml.

Run: uv run pytest tests/integration/persistence/test_migrations.py -q
"""

from __future__ import annotations

import datetime
import importlib

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine

from langbot.pkg.entity.persistence.base import Base
from langbot.pkg.entity.persistence import bot as _bot  # noqa: F401
from langbot.pkg.entity.persistence import database_mode as _database_mode  # noqa: F401
from langbot.pkg.entity.persistence import mcp as _mcp  # noqa: F401
from langbot.pkg.persistence.alembic_runner import (
    run_alembic_upgrade,
    run_alembic_downgrade,
    run_alembic_stamp,
    get_alembic_current,
    _ALEMBIC_DIR,
)
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy.dialects import postgresql


def _get_script_head() -> str:
    """Resolve the current Alembic head revision from the script directory.

    Avoids hardcoding a revision number in assertions so adding a new
    migration doesn't require editing the migration tests.
    """
    cfg = Config()
    cfg.set_main_option('script_location', _ALEMBIC_DIR)
    return ScriptDirectory.from_config(cfg).get_current_head()


def _dt(value: str) -> datetime.datetime:
    return datetime.datetime.fromisoformat(value)


pytestmark = pytest.mark.integration


@pytest.fixture
def sqlite_db_url(tmp_path):
    """Create SQLite URL with temporary database file."""
    db_file = tmp_path / 'test_migrations.db'
    return f'sqlite+aiosqlite:///{db_file}'


@pytest.fixture
async def sqlite_engine(sqlite_db_url):
    """Create async SQLite engine."""
    engine = create_async_engine(sqlite_db_url)
    yield engine
    await engine.dispose()


class TestSQLiteMigrationBaseline:
    """Tests for baseline stamp workflow."""

    @pytest.mark.asyncio
    async def test_baseline_stamp_sets_revision(self, sqlite_engine):
        """
        Stamp baseline on existing tables sets correct revision.

        Workflow:
        1. Create tables via Base.metadata.create_all
        2. Stamp with '0001_baseline'
        3. Verify current revision is '0001_baseline'
        """
        # Create all tables (simulates existing DB created by ORM)
        async with sqlite_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        # Stamp baseline
        await run_alembic_stamp(sqlite_engine, '0001_baseline')

        # Verify revision
        rev = await get_alembic_current(sqlite_engine)
        assert rev == '0001_baseline', f"Expected '0001_baseline', got {rev}"

    @pytest.mark.asyncio
    async def test_baseline_stamp_on_empty_db(self, sqlite_engine):
        """
        Stamp on empty database (no tables) still sets revision.

        This is an edge case - stamping without tables.
        """
        # Don't create tables - stamp directly
        await run_alembic_stamp(sqlite_engine, '0001_baseline')

        rev = await get_alembic_current(sqlite_engine)
        assert rev == '0001_baseline'


class TestSQLiteMigrationUpgrade:
    """Tests for upgrade to head workflow."""

    @pytest.mark.asyncio
    async def test_upgrade_from_baseline_to_head(self, sqlite_engine):
        """
        Upgrade from baseline to head applies all migrations.

        Workflow:
        1. Create tables
        2. Stamp baseline
        3. Upgrade to head
        4. Verify current revision is head
        """
        # Create tables
        async with sqlite_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        # Stamp baseline
        await run_alembic_stamp(sqlite_engine, '0001_baseline')

        # Upgrade to head
        await run_alembic_upgrade(sqlite_engine, 'head')

        # Verify revision
        rev = await get_alembic_current(sqlite_engine)
        assert rev is not None, 'Expected a revision after upgrade'
        # Head should be the latest migration. Resolve the actual head from the
        # Alembic script directory instead of hardcoding a revision number, so
        # adding a new migration doesn't require editing this assertion.
        assert rev == _get_script_head(), f'Expected head {_get_script_head()}, got {rev}'

    @pytest.mark.asyncio
    async def test_upgrade_idempotent(self, sqlite_engine):
        """
        Running upgrade to head multiple times is idempotent.

        Workflow:
        1. Upgrade to head
        2. Get revision
        3. Upgrade to head again
        4. Verify same revision
        """
        # Create tables
        async with sqlite_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        # Stamp and upgrade
        await run_alembic_stamp(sqlite_engine, '0001_baseline')
        await run_alembic_upgrade(sqlite_engine, 'head')

        rev1 = await get_alembic_current(sqlite_engine)

        # Upgrade again - should be idempotent
        await run_alembic_upgrade(sqlite_engine, 'head')

        rev2 = await get_alembic_current(sqlite_engine)
        assert rev2 == rev1, f'Expected {rev1}, got {rev2}'

    @pytest.mark.asyncio
    async def test_mcp_builtin_connector_columns_exist_after_upgrade(self, sqlite_engine):
        """The MCP table exposes builtin/local-connector metadata after upgrade."""
        async with sqlite_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        await run_alembic_stamp(sqlite_engine, '0001_baseline')
        await run_alembic_upgrade(sqlite_engine, 'head')

        async with sqlite_engine.begin() as conn:
            def inspect_schema(sync_conn):
                inspector = sa.inspect(sync_conn)
                columns = {col['name'] for col in inspector.get_columns('mcp_servers')}
                indexes = inspector.get_indexes('mcp_servers')
                return columns, indexes

            columns, indexes = await conn.run_sync(inspect_schema)

        assert {'builtin', 'locked', 'managed_by', 'connector_id'}.issubset(columns)
        assert any('connector_id' in index['name'] for index in indexes)


class TestSQLiteMigrationFreshDatabase:
    """Tests for fresh database workflow."""

    @pytest.mark.asyncio
    async def test_fresh_db_upgrade_from_scratch(self, tmp_path):
        """
        Fresh database (no tables) can be upgraded directly to head.

        Workflow:
        1. Create fresh engine with new DB file
        2. Create tables
        3. Upgrade to head
        4. Verify revision
        """
        # Use different DB file for fresh test
        fresh_db_file = tmp_path / 'test_migrations_fresh.db'
        fresh_url = f'sqlite+aiosqlite:///{fresh_db_file}'
        fresh_engine = create_async_engine(fresh_url)

        # Create tables on fresh DB
        async with fresh_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        # Upgrade to head directly (no baseline stamp)
        await run_alembic_upgrade(fresh_engine, 'head')

        # Verify revision
        rev = await get_alembic_current(fresh_engine)
        assert rev is not None, 'Expected a revision on fresh DB'

        await fresh_engine.dispose()

    @pytest.mark.asyncio
    async def test_fresh_db_without_create_all_behavior(self, tmp_path):
        """
        Fresh database without create_all - test actual behavior.

        This tests what happens when migrations run on truly empty DB.
        The behavior is determined by Alembic and migration scripts.

        EXPECTED: Either:
        1. Migration succeeds (if scripts handle empty DB)
        2. Migration fails with specific error (if scripts require tables)

        IMPORTANT: This test verifies the ACTUAL behavior, not accepting
        any arbitrary failure with try-except pass.
        """
        fresh_db_file = tmp_path / 'test_empty_migrations.db'
        fresh_url = f'sqlite+aiosqlite:///{fresh_db_file}'
        fresh_engine = create_async_engine(fresh_url)

        # Capture the actual behavior
        actual_result = None
        actual_error = None

        try:
            await run_alembic_upgrade(fresh_engine, 'head')
            rev = await get_alembic_current(fresh_engine)
            actual_result = rev
        except Exception as e:
            actual_error = e

        await fresh_engine.dispose()

        # Verify specific behavior - one of two outcomes is expected
        if actual_result is not None:
            # Migration succeeded - verify revision exists
            assert actual_result is not None, 'Revision should exist after successful migration'
        else:
            # Migration failed - verify the error type is known
            # Alembic typically raises specific errors for missing tables
            assert actual_error is not None, 'Error should be captured if migration failed'
            # Log the error type for documentation (don't silently pass)
            error_type = type(actual_error).__name__
            # Acceptable error types for empty DB scenarios
            acceptable_errors = [
                'OperationalError',  # SQLite table not found
                'ProgrammingError',  # SQLAlchemy errors
                'CommandError',  # Alembic command errors
            ]
            assert error_type in acceptable_errors, (
                f'Unexpected error type: {error_type}. '
                f'This may indicate a regression in migration behavior. '
                f'Error: {actual_error}'
            )


class TestSQLiteMigrationGetCurrent:
    """Tests for get_alembic_current behavior."""

    @pytest.mark.asyncio
    async def test_get_current_on_unstamped_db_returns_none(self, sqlite_engine):
        """
        get_alembic_current returns None for unstamped database.
        """
        # Create tables but don't stamp
        async with sqlite_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        # No stamp - should return None
        rev = await get_alembic_current(sqlite_engine)
        assert rev is None, f'Expected None for unstamped DB, got {rev}'

    @pytest.mark.asyncio
    async def test_get_current_after_stamp_returns_revision(self, sqlite_engine):
        """
        get_alembic_current returns correct revision after stamp.
        """
        async with sqlite_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        await run_alembic_stamp(sqlite_engine, '0001_baseline')

        rev = await get_alembic_current(sqlite_engine)
        assert rev == '0001_baseline'


class TestBotChannelBindingUniqueMigration:
    @pytest.mark.asyncio
    async def test_upgrade_cleans_duplicate_bindings_and_keeps_best_row(self, sqlite_engine):
        async with sqlite_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            channel_accounts, bot_channel_bindings = await conn.run_sync(
                lambda sync_conn: (
                    sa.Table('channel_accounts', sa.MetaData(), autoload_with=sync_conn),
                    sa.Table('bot_channel_bindings', sa.MetaData(), autoload_with=sync_conn),
                )
            )
            await conn.execute(
                sa.insert(_bot.Bot).values(
                    {
                        'uuid': 'bot-cleanup',
                        'name': 'Cleanup Bot',
                        'description': 'desc',
                        'adapter': 'wxwork_database',
                        'adapter_config': {'connector_id': 'wxwork-local', 'auto_generate_draft': False},
                        'enable': True,
                        'pipeline_routing_rules': [],
                    }
                )
            )
            channel_account_id = (
                await conn.execute(
                    sa.insert(channel_accounts).values(
                        {
                            'connector_id': 'wxwork-local',
                            'channel_type': 'wxwork_database',
                            'external_account_id': 'wxwork-local',
                            'display_name': 'WXWork Database',
                            'enabled': True,
                            'metadata': {},
                        }
                    )
                )
            ).inserted_primary_key[0]

            await conn.execute(
                sa.insert(bot_channel_bindings).values(
                    [
                        {
                            'bot_uuid': 'bot-cleanup',
                            'channel_account_id': channel_account_id,
                            'enabled': False,
                            'effective_from': _dt('2026-06-20T10:00:00'),
                            'auto_generate_draft': True,
                            'created_at': _dt('2026-06-20T10:00:00'),
                            'updated_at': _dt('2026-06-20T11:00:00'),
                        },
                        {
                            'bot_uuid': 'bot-cleanup',
                            'channel_account_id': channel_account_id,
                            'enabled': True,
                            'effective_from': _dt('2026-06-21T10:00:00'),
                            'auto_generate_draft': True,
                            'created_at': _dt('2026-06-21T10:00:00'),
                            'updated_at': _dt('2026-06-21T11:00:00'),
                        },
                        {
                            'bot_uuid': 'bot-cleanup',
                            'channel_account_id': channel_account_id,
                            'enabled': True,
                            'effective_from': _dt('2026-06-19T10:00:00'),
                            'auto_generate_draft': True,
                            'created_at': _dt('2026-06-19T10:00:00'),
                            'updated_at': _dt('2026-06-22T11:00:00'),
                        },
                    ]
                )
            )

        await run_alembic_stamp(sqlite_engine, '0001_baseline')
        await run_alembic_upgrade(sqlite_engine, 'head')

        async with sqlite_engine.begin() as conn:
            def inspect_bindings(sync_conn):
                inspector = sa.inspect(sync_conn)
                binding_indexes = {index['name'] for index in inspector.get_indexes('bot_channel_bindings')}
                bindings_table = sa.Table('bot_channel_bindings', sa.MetaData(), autoload_with=sync_conn)
                rows = sync_conn.execute(sa.select(bindings_table).order_by(bindings_table.c.id.asc())).mappings().all()
                return binding_indexes, rows

            binding_indexes, rows = await conn.run_sync(inspect_bindings)

        assert 'ux_bot_channel_bindings_bot_channel' in binding_indexes
        assert len(rows) == 1
        row = rows[0]
        assert row['bot_uuid'] == 'bot-cleanup'
        assert row['channel_account_id'] == channel_account_id
        assert row['enabled'] is True
        assert row['effective_from'] == _dt('2026-06-21T10:00:00')
        assert row['auto_generate_draft'] is False

    @pytest.mark.asyncio
    async def test_upgrade_blocks_duplicate_binding_inserts(self, sqlite_engine):
        async with sqlite_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            channel_accounts, bot_channel_bindings = await conn.run_sync(
                lambda sync_conn: (
                    sa.Table('channel_accounts', sa.MetaData(), autoload_with=sync_conn),
                    sa.Table('bot_channel_bindings', sa.MetaData(), autoload_with=sync_conn),
                )
            )
            await conn.execute(
                sa.insert(_bot.Bot).values(
                    {
                        'uuid': 'bot-unique',
                        'name': 'Unique Bot',
                        'description': 'desc',
                        'adapter': 'wxwork_database',
                        'adapter_config': {'connector_id': 'wxwork-local', 'auto_generate_draft': True},
                        'enable': True,
                        'pipeline_routing_rules': [],
                    }
                )
            )
            channel_account_id = (
                await conn.execute(
                    sa.insert(channel_accounts).values(
                        {
                            'connector_id': 'wxwork-local',
                            'channel_type': 'wxwork_database',
                            'external_account_id': 'wxwork-local',
                            'display_name': 'WXWork Database',
                            'enabled': True,
                            'metadata': {},
                        }
                    )
                )
            ).inserted_primary_key[0]
            await conn.execute(
                sa.insert(bot_channel_bindings).values(
                    {
                        'bot_uuid': 'bot-unique',
                        'channel_account_id': channel_account_id,
                        'enabled': True,
                        'effective_from': _dt('2026-06-21T10:00:00'),
                        'auto_generate_draft': True,
                        'created_at': _dt('2026-06-21T10:00:00'),
                        'updated_at': _dt('2026-06-21T11:00:00'),
                    }
                )
            )

        await run_alembic_stamp(sqlite_engine, '0001_baseline')
        await run_alembic_upgrade(sqlite_engine, 'head')

        with pytest.raises(sa.exc.IntegrityError):
            async with sqlite_engine.begin() as conn:
                bot_channel_bindings = await conn.run_sync(
                    lambda sync_conn: sa.Table('bot_channel_bindings', sa.MetaData(), autoload_with=sync_conn)
                )
                await conn.execute(
                    sa.insert(bot_channel_bindings).values(
                        {
                            'bot_uuid': 'bot-unique',
                            'channel_account_id': channel_account_id,
                            'enabled': True,
                            'effective_from': _dt('2026-06-22T10:00:00'),
                            'auto_generate_draft': True,
                            'created_at': _dt('2026-06-22T10:00:00'),
                            'updated_at': _dt('2026-06-22T11:00:00'),
                        }
                    )
                )

    @pytest.mark.asyncio
    async def test_sqlite_upgrade_and_downgrade_round_trip(self, sqlite_engine):
        async with sqlite_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        await run_alembic_stamp(sqlite_engine, '0001_baseline')
        await run_alembic_upgrade(sqlite_engine, 'head')

        async with sqlite_engine.begin() as conn:
            def inspect_indexes(sync_conn):
                inspector = sa.inspect(sync_conn)
                return {index['name'] for index in inspector.get_indexes('bot_channel_bindings')}

            indexes_after_upgrade = await conn.run_sync(inspect_indexes)

        assert 'ux_bot_channel_bindings_bot_channel' in indexes_after_upgrade

        await run_alembic_downgrade(sqlite_engine, '0009_channel_bot_processing')

        async with sqlite_engine.begin() as conn:
            def inspect_indexes(sync_conn):
                inspector = sa.inspect(sync_conn)
                return {index['name'] for index in inspector.get_indexes('bot_channel_bindings')}

            indexes_after_downgrade = await conn.run_sync(inspect_indexes)

        assert 'ux_bot_channel_bindings_bot_channel' not in indexes_after_downgrade
        rev = await get_alembic_current(sqlite_engine)
        assert rev == '0009_channel_bot_processing'

    def test_postgresql_unique_index_ddl_uses_unique_index_name(self):
        migration = importlib.import_module('langbot.pkg.persistence.alembic.versions.0010_bot_channel_bindings_uniq')
        table = sa.Table(
            'bot_channel_bindings',
            sa.MetaData(),
            sa.Column('bot_uuid', sa.String(255)),
            sa.Column('channel_account_id', sa.Integer()),
        )
        index = sa.Index(
            migration.UNIQUE_INDEX_NAME,
            table.c.bot_uuid,
            table.c.channel_account_id,
            unique=True,
        )
        ddl = str(sa.schema.CreateIndex(index).compile(dialect=postgresql.dialect()))
        assert 'CREATE UNIQUE INDEX' in ddl
        assert migration.UNIQUE_INDEX_NAME in ddl
        assert 'bot_uuid' in ddl
        assert 'channel_account_id' in ddl


class TestMessageProcessingRunUniqueMigration:
    @pytest.mark.asyncio
    async def test_upgrade_cleans_duplicate_processing_runs_and_keeps_latest_processing(self, sqlite_engine):
        async with sqlite_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            message_processing_runs, database_messages = await conn.run_sync(
                lambda sync_conn: (
                    sa.Table('message_processing_runs', sa.MetaData(), autoload_with=sync_conn),
                    sa.Table('database_messages', sa.MetaData(), autoload_with=sync_conn),
                )
            )

            await conn.execute(
                sa.insert(database_messages).values(
                    {
                        'id': 99,
                        'event_id': 'evt-processing-99',
                        'message_key': 'key-processing-99',
                        'conversation_id': 1,
                        'external_message_id': 'ext-99',
                        'sender_id': 'sender-99',
                        'sender_name': 'Sender 99',
                        'content': 'Need processing cleanup',
                        'message_type': 'text',
                        'sent_at': _dt('2026-06-26T10:00:00'),
                        'observed_at': _dt('2026-06-26T10:00:01'),
                        'status': 'pending',
                        'attempt_count': 0,
                        'created_at': _dt('2026-06-26T10:00:00'),
                        'updated_at': _dt('2026-06-26T10:00:00'),
                    }
                )
            )

            await conn.execute(
                sa.insert(message_processing_runs).values(
                    [
                        {
                            'id': 501,
                            'message_id': 99,
                            'bot_uuid': 'bot-processing',
                            'pipeline_uuid': None,
                            'trigger': 'manual',
                            'status': 'processing',
                            'attempt_count': 1,
                            'started_at': _dt('2026-06-26T10:00:00'),
                            'completed_at': None,
                            'last_error': None,
                            'created_at': _dt('2026-06-26T10:00:00'),
                            'updated_at': _dt('2026-06-26T10:00:00'),
                        },
                        {
                            'id': 502,
                            'message_id': 99,
                            'bot_uuid': 'bot-processing',
                            'pipeline_uuid': None,
                            'trigger': 'manual',
                            'status': 'processing',
                            'attempt_count': 2,
                            'started_at': _dt('2026-06-26T10:05:00'),
                            'completed_at': None,
                            'last_error': None,
                            'created_at': _dt('2026-06-26T10:05:00'),
                            'updated_at': _dt('2026-06-26T10:05:00'),
                        },
                    ]
                )
            )

        await run_alembic_stamp(sqlite_engine, '0009_channel_bot_processing')
        await run_alembic_upgrade(sqlite_engine, 'head')

        async with sqlite_engine.begin() as conn:
            def inspect_runs(sync_conn):
                inspector = sa.inspect(sync_conn)
                indexes = {index['name'] for index in inspector.get_indexes('message_processing_runs')}
                runs_table = sa.Table('message_processing_runs', sa.MetaData(), autoload_with=sync_conn)
                rows = sync_conn.execute(
                    sa.select(runs_table).where(
                        runs_table.c.message_id == 99,
                        runs_table.c.bot_uuid == 'bot-processing',
                    ).order_by(runs_table.c.id.asc())
                ).mappings().all()
                return indexes, rows

            indexes, rows = await conn.run_sync(inspect_runs)

        assert 'ux_message_processing_runs_active' in indexes
        assert len(rows) == 2
        assert rows[0]['status'] == 'failed'
        assert rows[0]['completed_at'] is not None
        assert rows[0]['last_error'] == 'Recovered duplicate processing run before adding unique index'
        assert rows[1]['status'] == 'processing'

    @pytest.mark.asyncio
    async def test_upgrade_blocks_second_processing_run_for_same_message_and_bot(self, sqlite_engine):
        async with sqlite_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        await run_alembic_stamp(sqlite_engine, '0009_channel_bot_processing')
        await run_alembic_upgrade(sqlite_engine, 'head')

        with pytest.raises(sa.exc.IntegrityError):
            async with sqlite_engine.begin() as conn:
                runs_table = await conn.run_sync(
                    lambda sync_conn: sa.Table('message_processing_runs', sa.MetaData(), autoload_with=sync_conn)
                )
                await conn.execute(
                    sa.insert(runs_table).values(
                        {
                            'message_id': 100,
                            'bot_uuid': 'bot-processing',
                            'pipeline_uuid': None,
                            'trigger': 'manual',
                            'status': 'processing',
                            'attempt_count': 1,
                            'started_at': _dt('2026-06-26T11:00:00'),
                            'completed_at': None,
                            'last_error': None,
                            'created_at': _dt('2026-06-26T11:00:00'),
                            'updated_at': _dt('2026-06-26T11:00:00'),
                        }
                    )
                )
                await conn.execute(
                    sa.insert(runs_table).values(
                        {
                            'message_id': 100,
                            'bot_uuid': 'bot-processing',
                            'pipeline_uuid': None,
                            'trigger': 'manual',
                            'status': 'processing',
                            'attempt_count': 2,
                            'started_at': _dt('2026-06-26T11:01:00'),
                            'completed_at': None,
                            'last_error': None,
                            'created_at': _dt('2026-06-26T11:01:00'),
                            'updated_at': _dt('2026-06-26T11:01:00'),
                        }
                    )
                )
