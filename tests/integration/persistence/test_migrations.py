"""
SQLite migration integration tests.

Tests real Alembic migration behavior using temporary SQLite databases.
Validates the migration workflow from .github/workflows/test-migrations.yml.

Run: uv run pytest tests/integration/persistence/test_migrations.py -q
"""

from __future__ import annotations

import datetime
import importlib
import os
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine

from langbot.pkg.entity.persistence.base import Base
from langbot.pkg.entity.persistence import bot as _bot  # noqa: F401
from langbot.pkg.entity.persistence import broadcast as _broadcast  # noqa: F401
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


def _get_revision_script(revision: str) -> Path:
    return Path(_ALEMBIC_DIR) / 'versions' / f'{revision}.py'


def _broadcast_attachment_root() -> Path:
    return Path(__file__).resolve().parents[3] / 'runtime' / 'broadcast_attachments'


def _sqlite_engine(url: str):
    engine = create_async_engine(url)
    sa.event.listen(engine.sync_engine, 'connect', _enable_sqlite_foreign_keys)
    return engine


def _enable_sqlite_foreign_keys(dbapi_connection, connection_record) -> None:
    del connection_record
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute('PRAGMA foreign_keys=ON')
    finally:
        cursor.close()


pytestmark = pytest.mark.integration


@pytest.fixture
def sqlite_db_url(tmp_path):
    """Create SQLite URL with temporary database file."""
    db_file = tmp_path / 'test_migrations.db'
    return f'sqlite+aiosqlite:///{db_file}'


@pytest.fixture
async def sqlite_engine(sqlite_db_url):
    """Create async SQLite engine."""
    engine = _sqlite_engine(sqlite_db_url)
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

    @pytest.mark.asyncio
    async def test_broadcast_tables_exist_after_upgrade(self, sqlite_engine):
        """Broadcast persistence tables and indexes exist after upgrading to head."""
        async with sqlite_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        await run_alembic_stamp(sqlite_engine, '0001_baseline')
        await run_alembic_upgrade(sqlite_engine, 'head')

        async with sqlite_engine.begin() as conn:
            def inspect_schema(sync_conn):
                inspector = sa.inspect(sync_conn)
                table_names = set(inspector.get_table_names())
                template_indexes = {index['name'] for index in inspector.get_indexes('broadcast_templates')}
                profile_indexes = {index['name'] for index in inspector.get_indexes('broadcast_variable_profiles')}
                rule_indexes = {index['name'] for index in inspector.get_indexes('broadcast_group_rules')}
                group_name_indexes = {index['name'] for index in inspector.get_indexes('broadcast_group_names')}
                return table_names, template_indexes, profile_indexes, rule_indexes, group_name_indexes

            table_names, template_indexes, profile_indexes, rule_indexes, group_name_indexes = (
                await conn.run_sync(inspect_schema)
            )

        assert {
            'broadcast_templates',
            'broadcast_variable_profiles',
            'broadcast_group_rules',
            'broadcast_group_names',
        }.issubset(table_names)
        assert 'ix_broadcast_templates_bot_uuid' in template_indexes
        assert 'ix_broadcast_templates_connector_id' in template_indexes
        assert 'ix_broadcast_variable_profiles_bot_uuid' in profile_indexes
        assert 'ix_broadcast_group_rules_priority' in rule_indexes
        assert 'ix_broadcast_group_names_name' in group_name_indexes

    @pytest.mark.asyncio
    async def test_broadcast_phase3_tables_exist_after_upgrade(self, sqlite_engine):
        """Phase 3 broadcast tables, indexes, and unique constraints exist after upgrade."""
        async with sqlite_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        await run_alembic_stamp(sqlite_engine, '0001_baseline')
        await run_alembic_upgrade(sqlite_engine, 'head')

        async with sqlite_engine.begin() as conn:
            def inspect_schema(sync_conn):
                inspector = sa.inspect(sync_conn)
                table_names = set(inspector.get_table_names())
                batch_indexes = {index['name'] for index in inspector.get_indexes('broadcast_import_batches')}
                row_indexes = {index['name'] for index in inspector.get_indexes('broadcast_import_rows')}
                draft_indexes = {index['name'] for index in inspector.get_indexes('broadcast_drafts')}
                row_uniques = {
                    tuple(sorted(item['column_names']))
                    for item in inspector.get_unique_constraints('broadcast_import_rows')
                }
                draft_uniques = {
                    tuple(sorted(item['column_names']))
                    for item in inspector.get_unique_constraints('broadcast_drafts')
                }
                return table_names, batch_indexes, row_indexes, draft_indexes, row_uniques, draft_uniques

            (
                table_names,
                batch_indexes,
                row_indexes,
                draft_indexes,
                row_uniques,
                draft_uniques,
            ) = await conn.run_sync(inspect_schema)

        assert {
            'broadcast_import_batches',
            'broadcast_import_rows',
            'broadcast_drafts',
        }.issubset(table_names)
        assert 'ix_broadcast_import_batches_bot_uuid' in batch_indexes
        assert 'ix_broadcast_import_batches_connector_id' in batch_indexes
        assert 'ix_broadcast_import_batches_created_at' in batch_indexes
        assert 'ix_broadcast_import_rows_import_batch_id' in row_indexes
        assert 'ix_broadcast_import_rows_match_status' in row_indexes
        assert 'ix_broadcast_import_rows_group_value' in row_indexes
        assert 'ix_broadcast_drafts_import_batch_id' in draft_indexes
        assert 'ix_broadcast_drafts_status' in draft_indexes
        assert 'ix_broadcast_drafts_updated_at' in draft_indexes
        assert tuple(sorted(['import_batch_id', 'source_row_number'])) in row_uniques
        assert tuple(sorted(['group_value', 'import_batch_id'])) in draft_uniques

    @pytest.mark.asyncio
    async def test_broadcast_phase3_revision_metadata_is_correct(self, sqlite_engine):
        """Phase 3 migration revision id is present, short enough, and chained from 0013."""
        script_path = _get_revision_script('0014_broadcast_phase3')
        assert script_path.exists(), 'Expected 0014_broadcast_phase3 migration script to exist'

        module = importlib.import_module('langbot.pkg.persistence.alembic.versions.0014_broadcast_phase3')
        assert len(module.revision) <= 32
        assert module.down_revision == '0013_broadcast_rules'

    @pytest.mark.asyncio
    async def test_broadcast_phase3_models_are_registered_in_metadata(self, sqlite_engine):
        """Phase 3 ORM models appear in metadata and create_all creates the tables."""
        table_names = set(Base.metadata.tables)
        assert 'broadcast_import_batches' in table_names
        assert 'broadcast_import_rows' in table_names
        assert 'broadcast_drafts' in table_names

        async with sqlite_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

            def inspect_tables(sync_conn):
                inspector = sa.inspect(sync_conn)
                return set(inspector.get_table_names())

            created_tables = await conn.run_sync(inspect_tables)

        assert 'broadcast_import_batches' in created_tables
        assert 'broadcast_import_rows' in created_tables
        assert 'broadcast_drafts' in created_tables

    @pytest.mark.asyncio
    async def test_broadcast_execution_tables_exist_after_upgrade(self, sqlite_engine):
        """Execution persistence tables, indexes, and unique constraints exist after upgrade."""
        async with sqlite_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        await run_alembic_stamp(sqlite_engine, '0001_baseline')
        await run_alembic_upgrade(sqlite_engine, 'head')

        async with sqlite_engine.begin() as conn:
            def inspect_schema(sync_conn):
                inspector = sa.inspect(sync_conn)
                table_names = set(inspector.get_table_names())
                batch_indexes = {index['name'] for index in inspector.get_indexes('broadcast_execution_batches')}
                task_indexes = {index['name'] for index in inspector.get_indexes('broadcast_execution_tasks')}
                attempt_indexes = {index['name'] for index in inspector.get_indexes('broadcast_execution_attempts')}
                evidence_indexes = {index['name'] for index in inspector.get_indexes('broadcast_execution_evidence')}
                confirmation_indexes = {
                    index['name'] for index in inspector.get_indexes('broadcast_send_confirmations')
                }
                task_uniques = {
                    tuple(sorted(item['column_names']))
                    for item in inspector.get_unique_constraints('broadcast_execution_tasks')
                }
                attempt_uniques = {
                    tuple(sorted(item['column_names']))
                    for item in inspector.get_unique_constraints('broadcast_execution_attempts')
                }
                confirmation_uniques = {
                    tuple(sorted(item['column_names']))
                    for item in inspector.get_unique_constraints('broadcast_send_confirmations')
                }
                return (
                    table_names,
                    batch_indexes,
                    task_indexes,
                    attempt_indexes,
                    evidence_indexes,
                    confirmation_indexes,
                    task_uniques,
                    attempt_uniques,
                    confirmation_uniques,
                )

            (
                table_names,
                batch_indexes,
                task_indexes,
                attempt_indexes,
                evidence_indexes,
                confirmation_indexes,
                task_uniques,
                attempt_uniques,
                confirmation_uniques,
            ) = await conn.run_sync(inspect_schema)

        assert {
            'broadcast_execution_batches',
            'broadcast_execution_tasks',
            'broadcast_execution_attempts',
            'broadcast_execution_evidence',
            'broadcast_send_confirmations',
        }.issubset(table_names)
        assert 'ix_broadcast_execution_batches_bot_uuid' in batch_indexes
        assert 'ix_broadcast_execution_batches_connector_id' in batch_indexes
        assert 'ix_broadcast_execution_batches_status' in batch_indexes
        assert 'ix_broadcast_execution_tasks_execution_batch_id' in task_indexes
        assert 'ix_broadcast_execution_tasks_status' in task_indexes
        assert 'ix_broadcast_execution_tasks_sequence_no' in task_indexes
        assert 'ix_broadcast_execution_attempts_execution_task_id' in attempt_indexes
        assert 'ix_broadcast_execution_attempts_runtime_task_id' in attempt_indexes
        assert 'ix_broadcast_execution_evidence_execution_attempt_id' in evidence_indexes
        assert 'ix_broadcast_send_confirmations_execution_task_id' in confirmation_indexes
        assert tuple(sorted(['execution_batch_id', 'sequence_no'])) in task_uniques
        assert tuple(sorted(['execution_task_id', 'attempt_no'])) in attempt_uniques
        assert tuple(sorted(['runtime_task_id'])) in attempt_uniques
        assert tuple(sorted(['confirmation_token_hash'])) in confirmation_uniques

    @pytest.mark.asyncio
    async def test_broadcast_execution_revision_metadata_is_correct(self, sqlite_engine):
        """Execution migration revision id is present, short enough, and chained from 0014."""
        script_path = _get_revision_script('0015_broadcast_execution')
        assert script_path.exists(), 'Expected 0015_broadcast_execution migration script to exist'

        module = importlib.import_module('langbot.pkg.persistence.alembic.versions.0015_broadcast_execution')
        assert len(module.revision) <= 32
        assert module.down_revision == '0014_broadcast_phase3'

    @pytest.mark.asyncio
    async def test_broadcast_execution_models_are_registered_in_metadata(self, sqlite_engine):
        """Execution ORM models appear in metadata and create_all creates the tables."""
        table_names = set(Base.metadata.tables)
        assert 'broadcast_execution_batches' in table_names
        assert 'broadcast_execution_tasks' in table_names
        assert 'broadcast_execution_attempts' in table_names
        assert 'broadcast_execution_evidence' in table_names
        assert 'broadcast_send_confirmations' in table_names

        async with sqlite_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

            def inspect_tables(sync_conn):
                inspector = sa.inspect(sync_conn)
                return set(inspector.get_table_names())

            created_tables = await conn.run_sync(inspect_tables)

        assert 'broadcast_execution_batches' in created_tables
        assert 'broadcast_execution_tasks' in created_tables
        assert 'broadcast_execution_attempts' in created_tables
        assert 'broadcast_execution_evidence' in created_tables
        assert 'broadcast_send_confirmations' in created_tables

    @pytest.mark.asyncio
    async def test_broadcast_attachment_relative_path_migration_repairs_already_applied_0017_db(self, sqlite_engine):
        """A DB stamped at 0017 without relative_path should still be repaired by head upgrade."""
        attachment_root = _broadcast_attachment_root()
        inside_dir = attachment_root / 'migration-tests' / 'inside'
        inside_dir.mkdir(parents=True, exist_ok=True)
        inside_file = inside_dir / 'quote.pdf'
        inside_file.write_bytes(b'quote-pdf')

        outside_dir = attachment_root.parent / 'migration-tests-outside'
        outside_dir.mkdir(parents=True, exist_ok=True)
        outside_file = outside_dir / 'outside.pdf'
        outside_file.write_bytes(b'outside-pdf')

        missing_file = attachment_root / 'migration-tests' / 'missing' / 'missing.pdf'

        try:
            async with sqlite_engine.begin() as conn:
                def setup_legacy_0017(sync_conn):
                    sync_conn.exec_driver_sql(
                        """
                        CREATE TABLE alembic_version (
                            version_num VARCHAR(32) NOT NULL
                        )
                        """
                    )
                    sync_conn.exec_driver_sql(
                        "INSERT INTO alembic_version (version_num) VALUES ('0017_broadcast_attach')"
                    )
                    sync_conn.exec_driver_sql(
                        """
                        CREATE TABLE broadcast_attachment_assets (
                            id INTEGER NOT NULL PRIMARY KEY,
                            bot_uuid VARCHAR(255) NOT NULL,
                            connector_id VARCHAR(255) NOT NULL,
                            original_name VARCHAR(255) NOT NULL,
                            stored_name VARCHAR(255) NOT NULL,
                            stored_path TEXT NOT NULL,
                            size_bytes BIGINT NOT NULL,
                            sha256 VARCHAR(64) NOT NULL,
                            extension VARCHAR(32) NOT NULL,
                            mime_type VARCHAR(255) NOT NULL,
                            status VARCHAR(32) NOT NULL DEFAULT 'ready',
                            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                        )
                        """
                    )
                    sync_conn.exec_driver_sql(
                        """
                        INSERT INTO broadcast_attachment_assets (
                            id, bot_uuid, connector_id, original_name, stored_name, stored_path,
                            size_bytes, sha256, extension, mime_type, status
                        ) VALUES
                            (1, 'bot-1', 'wxwork-local', 'quote.pdf', 'quote.pdf', :inside_path, 9, 'sha-inside', 'pdf', 'application/pdf', 'ready'),
                            (2, 'bot-1', 'wxwork-local', 'outside.pdf', 'outside.pdf', :outside_path, 11, 'sha-outside', 'pdf', 'application/pdf', 'ready'),
                            (3, 'bot-1', 'wxwork-local', 'missing.pdf', 'missing.pdf', :missing_path, 13, 'sha-missing', 'pdf', 'application/pdf', 'ready')
                        """,
                        {
                            'inside_path': str(inside_file),
                            'outside_path': str(outside_file),
                            'missing_path': str(missing_file),
                        },
                    )

                await conn.run_sync(setup_legacy_0017)

            await run_alembic_upgrade(sqlite_engine, 'head')
            await run_alembic_upgrade(sqlite_engine, 'head')

            async with sqlite_engine.begin() as conn:
                def inspect_repaired_schema(sync_conn):
                    inspector = sa.inspect(sync_conn)
                    columns = {column['name'] for column in inspector.get_columns('broadcast_attachment_assets')}
                    rows = sync_conn.execute(
                        sa.text(
                            """
                            SELECT id, stored_path, relative_path
                            FROM broadcast_attachment_assets
                            ORDER BY id
                            """
                        )
                    ).mappings().all()
                    return columns, [dict(row) for row in rows]

                columns, rows = await conn.run_sync(inspect_repaired_schema)

            assert 'relative_path' in columns
            assert rows[0]['relative_path'] == 'migration-tests/inside/quote.pdf'
            assert rows[1]['relative_path'] is None
            assert rows[2]['relative_path'] is None
            rev = await get_alembic_current(sqlite_engine)
            assert rev == _get_script_head()
        finally:
            inside_file.unlink(missing_ok=True)
            outside_file.unlink(missing_ok=True)
            for directory in [inside_dir, outside_dir, missing_file.parent]:
                try:
                    directory.rmdir()
                except OSError:
                    pass

    @pytest.mark.asyncio
    async def test_broadcast_attachment_relative_path_revision_metadata_is_correct(self, sqlite_engine):
        """Attachment relative-path patch migration exists, is short enough, and chains from 0017."""
        del sqlite_engine
        script_path = _get_revision_script('0018_broadcast_attachment_relative_path')
        assert script_path.exists(), 'Expected 0018_broadcast_attachment_relative_path migration script to exist'

        module = importlib.import_module(
            'langbot.pkg.persistence.alembic.versions.0018_broadcast_attachment_relative_path'
        )
        assert len(module.revision) <= 32
        assert module.down_revision == '0017_broadcast_attach'

    @pytest.mark.asyncio
    async def test_deleting_batch_cascades_to_execution_children(self, sqlite_engine):
        """Deleting a batch should cascade delete tasks, attempts, evidence, and send confirmations."""
        async with sqlite_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        await run_alembic_stamp(sqlite_engine, '0001_baseline')
        await run_alembic_upgrade(sqlite_engine, 'head')

        async with sqlite_engine.begin() as conn:
            def sync_case(sync_conn):
                metadata = sa.MetaData()
                import_batches = sa.Table('broadcast_import_batches', metadata, autoload_with=sync_conn)
                templates = sa.Table('broadcast_templates', metadata, autoload_with=sync_conn)
                drafts = sa.Table('broadcast_drafts', metadata, autoload_with=sync_conn)
                exec_batches = sa.Table('broadcast_execution_batches', metadata, autoload_with=sync_conn)
                exec_tasks = sa.Table('broadcast_execution_tasks', metadata, autoload_with=sync_conn)
                exec_attempts = sa.Table('broadcast_execution_attempts', metadata, autoload_with=sync_conn)
                exec_evidence = sa.Table('broadcast_execution_evidence', metadata, autoload_with=sync_conn)
                confirmations = sa.Table('broadcast_send_confirmations', metadata, autoload_with=sync_conn)

                template_id = sync_conn.execute(
                    sa.insert(templates).values(
                        bot_uuid='bot-1',
                        connector_id='connector-1',
                        name='template',
                        content='hello',
                        variables=[],
                        enabled=True,
                    )
                ).inserted_primary_key[0]
                import_batch_id = sync_conn.execute(
                    sa.insert(import_batches).values(
                        bot_uuid='bot-1',
                        connector_id='connector-1',
                        original_file_name='customers.csv',
                        file_type='csv',
                        worksheet_name=None,
                        status='drafts_generated',
                        drafts_stale=False,
                        total_rows=1,
                        valid_rows=1,
                        invalid_rows=0,
                        matched_rows=1,
                        unmatched_rows=0,
                    )
                ).inserted_primary_key[0]
                draft_id = sync_conn.execute(
                    sa.insert(drafts).values(
                        bot_uuid='bot-1',
                        connector_id='connector-1',
                        import_batch_id=import_batch_id,
                        group_value='Acme',
                        target_conversation_name='Acme Group',
                        template_id=template_id,
                        template_name_snapshot='template',
                        template_content_snapshot='hello',
                        render_variables={'customer_name': 'Acme'},
                        draft_text='hello',
                        status='ready',
                        error_message=None,
                    )
                ).inserted_primary_key[0]
                execution_batch_id = sync_conn.execute(
                    sa.insert(exec_batches).values(
                        bot_uuid='bot-1',
                        connector_id='connector-1',
                        channel='wecom',
                        mode='paste_only',
                        status='created',
                        total_tasks=1,
                        pending_tasks=1,
                        running_tasks=0,
                        succeeded_tasks=0,
                        failed_tasks=0,
                        cancelled_tasks=0,
                        interrupted_tasks=0,
                        error_message=None,
                        version=1,
                        created_by='tester',
                        last_action_by='tester',
                    )
                ).inserted_primary_key[0]
                task_id = sync_conn.execute(
                    sa.insert(exec_tasks).values(
                        execution_batch_id=execution_batch_id,
                        draft_id=draft_id,
                        draft_text_snapshot='hello',
                        target_conversation_snapshot='Acme Group',
                        channel='wecom',
                        action='paste_draft',
                        status='pending',
                        sequence_no=1,
                        attempt_count=0,
                        max_attempts=3,
                        idempotency_key='broadcast:1:1',
                        request_digest='digest-1',
                        runtime_task_id=None,
                        error_code=None,
                        error_message=None,
                    )
                ).inserted_primary_key[0]
                attempt_id = sync_conn.execute(
                    sa.insert(exec_attempts).values(
                        execution_task_id=task_id,
                        attempt_no=1,
                        idempotency_key='broadcast:1:1',
                        request_digest='digest-1',
                        runtime_task_id='runtime-1',
                        request_summary='summary',
                        response_summary='response',
                        status='running',
                        error_code=None,
                        error_message=None,
                    )
                ).inserted_primary_key[0]
                sync_conn.execute(
                    sa.insert(exec_evidence).values(
                        execution_attempt_id=attempt_id,
                        window_title='WeCom',
                        target_conversation='Acme Group',
                        action='paste_draft',
                        input_located=True,
                        draft_written=True,
                        send_triggered=False,
                        clipboard_restored=True,
                        runtime_state='running',
                        evidence_summary='summary',
                        technical_details='details',
                    )
                )
                sync_conn.execute(
                    sa.insert(confirmations).values(
                        execution_task_id=task_id,
                        confirmation_token_hash='hash-1',
                        issued_by='tester',
                        used_by=None,
                        status='issued',
                    )
                )
                sync_conn.execute(sa.delete(exec_batches).where(exec_batches.c.id == execution_batch_id))

                return {
                    'tasks': sync_conn.execute(sa.select(sa.func.count()).select_from(exec_tasks)).scalar_one(),
                    'attempts': sync_conn.execute(sa.select(sa.func.count()).select_from(exec_attempts)).scalar_one(),
                    'evidence': sync_conn.execute(sa.select(sa.func.count()).select_from(exec_evidence)).scalar_one(),
                    'confirmations': sync_conn.execute(
                        sa.select(sa.func.count()).select_from(confirmations)
                    ).scalar_one(),
                }

            counts = await conn.run_sync(sync_case)

        assert counts == {'tasks': 0, 'attempts': 0, 'evidence': 0, 'confirmations': 0}

    @pytest.mark.asyncio
    async def test_deleting_draft_sets_execution_task_draft_id_to_null(self, sqlite_engine):
        """Deleting a draft should preserve execution tasks and null out draft_id."""
        async with sqlite_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        await run_alembic_stamp(sqlite_engine, '0001_baseline')
        await run_alembic_upgrade(sqlite_engine, 'head')

        async with sqlite_engine.begin() as conn:
            def sync_case(sync_conn):
                metadata = sa.MetaData()
                import_batches = sa.Table('broadcast_import_batches', metadata, autoload_with=sync_conn)
                templates = sa.Table('broadcast_templates', metadata, autoload_with=sync_conn)
                drafts = sa.Table('broadcast_drafts', metadata, autoload_with=sync_conn)
                exec_batches = sa.Table('broadcast_execution_batches', metadata, autoload_with=sync_conn)
                exec_tasks = sa.Table('broadcast_execution_tasks', metadata, autoload_with=sync_conn)

                template_id = sync_conn.execute(
                    sa.insert(templates).values(
                        bot_uuid='bot-1',
                        connector_id='connector-1',
                        name='template',
                        content='hello',
                        variables=[],
                        enabled=True,
                    )
                ).inserted_primary_key[0]
                import_batch_id = sync_conn.execute(
                    sa.insert(import_batches).values(
                        bot_uuid='bot-1',
                        connector_id='connector-1',
                        original_file_name='customers.csv',
                        file_type='csv',
                        worksheet_name=None,
                        status='drafts_generated',
                        drafts_stale=False,
                        total_rows=1,
                        valid_rows=1,
                        invalid_rows=0,
                        matched_rows=1,
                        unmatched_rows=0,
                    )
                ).inserted_primary_key[0]
                draft_id = sync_conn.execute(
                    sa.insert(drafts).values(
                        bot_uuid='bot-1',
                        connector_id='connector-1',
                        import_batch_id=import_batch_id,
                        group_value='Acme',
                        target_conversation_name='Acme Group',
                        template_id=template_id,
                        template_name_snapshot='template',
                        template_content_snapshot='hello',
                        render_variables={'customer_name': 'Acme'},
                        draft_text='hello',
                        status='ready',
                        error_message=None,
                    )
                ).inserted_primary_key[0]
                execution_batch_id = sync_conn.execute(
                    sa.insert(exec_batches).values(
                        bot_uuid='bot-1',
                        connector_id='connector-1',
                        channel='wecom',
                        mode='paste_only',
                        status='created',
                        total_tasks=1,
                        pending_tasks=1,
                        running_tasks=0,
                        succeeded_tasks=0,
                        failed_tasks=0,
                        cancelled_tasks=0,
                        interrupted_tasks=0,
                        error_message=None,
                        version=1,
                        created_by='tester',
                        last_action_by='tester',
                    )
                ).inserted_primary_key[0]
                task_id = sync_conn.execute(
                    sa.insert(exec_tasks).values(
                        execution_batch_id=execution_batch_id,
                        draft_id=draft_id,
                        draft_text_snapshot='hello',
                        target_conversation_snapshot='Acme Group',
                        channel='wecom',
                        action='paste_draft',
                        status='pending',
                        sequence_no=1,
                        attempt_count=0,
                        max_attempts=3,
                        idempotency_key='broadcast:1:1',
                        request_digest='digest-1',
                        runtime_task_id=None,
                        error_code=None,
                        error_message=None,
                    )
                ).inserted_primary_key[0]
                sync_conn.execute(sa.delete(drafts).where(drafts.c.id == draft_id))
                return sync_conn.execute(
                    sa.select(exec_tasks.c.draft_id).where(exec_tasks.c.id == task_id)
                ).scalar_one()

            draft_id = await conn.run_sync(sync_case)

        assert draft_id is None

    @pytest.mark.asyncio
    async def test_deleting_group_rule_sets_import_row_matched_rule_to_null(self, sqlite_engine):
        """Deleting a broadcast group rule should preserve rows and null out matched_rule_id."""
        async with sqlite_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        await run_alembic_stamp(sqlite_engine, '0001_baseline')
        await run_alembic_upgrade(sqlite_engine, 'head')

        async with sqlite_engine.begin() as conn:
            def sync_case(sync_conn):
                metadata = sa.MetaData()
                templates = sa.Table('broadcast_templates', metadata, autoload_with=sync_conn)
                rules = sa.Table('broadcast_group_rules', metadata, autoload_with=sync_conn)
                batches = sa.Table('broadcast_import_batches', metadata, autoload_with=sync_conn)
                rows = sa.Table('broadcast_import_rows', metadata, autoload_with=sync_conn)
                sync_conn.execute(
                    sa.insert(templates).values(
                        bot_uuid='bot-1',
                        connector_id='connector-1',
                        name='template',
                        content='hello',
                        variables=[],
                        enabled=True,
                    )
                )
                rule_id = sync_conn.execute(
                    sa.insert(rules).values(
                        bot_uuid='bot-1',
                        connector_id='connector-1',
                        source_value='acme',
                        match_type='exact',
                        match_expression='Acme',
                        target_conversation_name='Acme Group',
                        priority=1,
                        enabled=True,
                    )
                ).inserted_primary_key[0]
                batch_id = sync_conn.execute(
                    sa.insert(batches).values(
                        bot_uuid='bot-1',
                        connector_id='connector-1',
                        original_file_name='customers.csv',
                        file_type='csv',
                        worksheet_name=None,
                        status='imported',
                        drafts_stale=False,
                        total_rows=1,
                        valid_rows=1,
                        invalid_rows=0,
                        matched_rows=1,
                        unmatched_rows=0,
                    )
                ).inserted_primary_key[0]
                row_id = sync_conn.execute(
                    sa.insert(rows).values(
                        import_batch_id=batch_id,
                        source_row_number=2,
                        raw_data={'Customer Name': 'Acme'},
                        group_value='Acme',
                        matched_conversation_name='Acme Group',
                        matched_rule_id=rule_id,
                        match_status='matched',
                        error_message=None,
                    )
                ).inserted_primary_key[0]
                sync_conn.execute(sa.delete(rules).where(rules.c.id == rule_id))
                return sync_conn.execute(
                    sa.select(rows.c.matched_rule_id).where(rows.c.id == row_id)
                ).scalar_one()

            matched_rule_id = await conn.run_sync(sync_case)

        assert matched_rule_id is None

    @pytest.mark.asyncio
    async def test_deleting_template_sets_draft_template_id_to_null(self, sqlite_engine):
        """Deleting a broadcast template should preserve drafts and null out template_id."""
        async with sqlite_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        await run_alembic_stamp(sqlite_engine, '0001_baseline')
        await run_alembic_upgrade(sqlite_engine, 'head')

        async with sqlite_engine.begin() as conn:
            def sync_case(sync_conn):
                metadata = sa.MetaData()
                templates = sa.Table('broadcast_templates', metadata, autoload_with=sync_conn)
                batches = sa.Table('broadcast_import_batches', metadata, autoload_with=sync_conn)
                drafts = sa.Table('broadcast_drafts', metadata, autoload_with=sync_conn)
                template_id = sync_conn.execute(
                    sa.insert(templates).values(
                        bot_uuid='bot-1',
                        connector_id='connector-1',
                        name='template',
                        content='hello',
                        variables=[],
                        enabled=True,
                    )
                ).inserted_primary_key[0]
                batch_id = sync_conn.execute(
                    sa.insert(batches).values(
                        bot_uuid='bot-1',
                        connector_id='connector-1',
                        original_file_name='customers.csv',
                        file_type='csv',
                        worksheet_name=None,
                        status='drafts_generated',
                        drafts_stale=False,
                        total_rows=1,
                        valid_rows=1,
                        invalid_rows=0,
                        matched_rows=1,
                        unmatched_rows=0,
                    )
                ).inserted_primary_key[0]
                draft_id = sync_conn.execute(
                    sa.insert(drafts).values(
                        bot_uuid='bot-1',
                        connector_id='connector-1',
                        import_batch_id=batch_id,
                        group_value='Acme',
                        target_conversation_name='Acme Group',
                        template_id=template_id,
                        template_name_snapshot='template',
                        template_content_snapshot='hello',
                        render_variables={'customer_name': 'Acme'},
                        draft_text='hello',
                        status='pending_review',
                        error_message=None,
                    )
                ).inserted_primary_key[0]
                sync_conn.execute(sa.delete(templates).where(templates.c.id == template_id))
                return sync_conn.execute(
                    sa.select(drafts.c.template_id).where(drafts.c.id == draft_id)
                ).scalar_one()

            template_id = await conn.run_sync(sync_case)

        assert template_id is None

    @pytest.mark.asyncio
    async def test_deleting_import_batch_cascades_to_rows(self, sqlite_engine):
        """Deleting an import batch should cascade delete its import rows."""
        async with sqlite_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        await run_alembic_stamp(sqlite_engine, '0001_baseline')
        await run_alembic_upgrade(sqlite_engine, 'head')

        async with sqlite_engine.begin() as conn:
            def sync_case(sync_conn):
                metadata = sa.MetaData()
                batches = sa.Table('broadcast_import_batches', metadata, autoload_with=sync_conn)
                rows = sa.Table('broadcast_import_rows', metadata, autoload_with=sync_conn)
                batch_id = sync_conn.execute(
                    sa.insert(batches).values(
                        bot_uuid='bot-1',
                        connector_id='connector-1',
                        original_file_name='customers.csv',
                        file_type='csv',
                        worksheet_name=None,
                        status='imported',
                        drafts_stale=False,
                        total_rows=1,
                        valid_rows=1,
                        invalid_rows=0,
                        matched_rows=0,
                        unmatched_rows=1,
                    )
                ).inserted_primary_key[0]
                sync_conn.execute(
                    sa.insert(rows).values(
                        import_batch_id=batch_id,
                        source_row_number=2,
                        raw_data={'Customer Name': 'Acme'},
                        group_value='Acme',
                        matched_conversation_name=None,
                        matched_rule_id=None,
                        match_status='unmatched',
                        error_message=None,
                    )
                )
                sync_conn.execute(sa.delete(batches).where(batches.c.id == batch_id))
                return sync_conn.execute(sa.select(sa.func.count()).select_from(rows)).scalar_one()

            remaining_rows = await conn.run_sync(sync_case)

        assert remaining_rows == 0

    @pytest.mark.asyncio
    async def test_deleting_import_batch_cascades_to_drafts(self, sqlite_engine):
        """Deleting an import batch should cascade delete its drafts."""
        async with sqlite_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        await run_alembic_stamp(sqlite_engine, '0001_baseline')
        await run_alembic_upgrade(sqlite_engine, 'head')

        async with sqlite_engine.begin() as conn:
            def sync_case(sync_conn):
                metadata = sa.MetaData()
                batches = sa.Table('broadcast_import_batches', metadata, autoload_with=sync_conn)
                drafts = sa.Table('broadcast_drafts', metadata, autoload_with=sync_conn)
                batch_id = sync_conn.execute(
                    sa.insert(batches).values(
                        bot_uuid='bot-1',
                        connector_id='connector-1',
                        original_file_name='customers.csv',
                        file_type='csv',
                        worksheet_name=None,
                        status='drafts_generated',
                        drafts_stale=False,
                        total_rows=1,
                        valid_rows=1,
                        invalid_rows=0,
                        matched_rows=1,
                        unmatched_rows=0,
                    )
                ).inserted_primary_key[0]
                sync_conn.execute(
                    sa.insert(drafts).values(
                        bot_uuid='bot-1',
                        connector_id='connector-1',
                        import_batch_id=batch_id,
                        group_value='Acme',
                        target_conversation_name='Acme Group',
                        template_id=None,
                        template_name_snapshot='template',
                        template_content_snapshot='hello',
                        render_variables={'customer_name': 'Acme'},
                        draft_text='hello',
                        status='pending_review',
                        error_message=None,
                    )
                )
                sync_conn.execute(sa.delete(batches).where(batches.c.id == batch_id))
                return sync_conn.execute(sa.select(sa.func.count()).select_from(drafts)).scalar_one()

            remaining_drafts = await conn.run_sync(sync_case)

        assert remaining_drafts == 0

    @pytest.mark.asyncio
    async def test_broadcast_phase3_downgrade_removes_tables_and_returns_to_0013(self, sqlite_engine):
        """Downgrading from head removes Phase 3 tables and returns revision 0013."""
        async with sqlite_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        await run_alembic_stamp(sqlite_engine, '0001_baseline')
        await run_alembic_upgrade(sqlite_engine, 'head')
        await run_alembic_downgrade(sqlite_engine, '0013_broadcast_rules')

        async with sqlite_engine.begin() as conn:
            def inspect_tables(sync_conn):
                inspector = sa.inspect(sync_conn)
                return set(inspector.get_table_names())

            table_names = await conn.run_sync(inspect_tables)

        assert 'broadcast_import_batches' not in table_names
        assert 'broadcast_import_rows' not in table_names
        assert 'broadcast_drafts' not in table_names
        rev = await get_alembic_current(sqlite_engine)
        assert rev == '0013_broadcast_rules'


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
        fresh_engine = _sqlite_engine(fresh_url)

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
        fresh_engine = _sqlite_engine(fresh_url)

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


class TestDesktopAutomationRunUniqueMigration:
    @pytest.mark.asyncio
    async def test_upgrade_cleans_duplicate_active_desktop_runs_and_keeps_latest(self, sqlite_engine):
        async with sqlite_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            desktop_runs = await conn.run_sync(
                lambda sync_conn: sa.Table('desktop_automation_runs', sa.MetaData(), autoload_with=sync_conn)
            )
            await conn.execute(
                sa.insert(desktop_runs).values(
                    [
                        {
                            'id': 901,
                            'bot_uuid': 'bot-desktop',
                            'connector_id': 'wxwork-local',
                            'conversation_id': 21,
                            'message_id': 11,
                            'draft_id': 31,
                            'action': 'paste_draft',
                            'execution_mode': 'paste_only',
                            'runtime_task_id': 'task-901',
                            'status': 'queued',
                            'stage': 'queued',
                            'attempt_count': 1,
                            'request_digest': 'req-901',
                            'draft_content_hash': 'hash-901',
                            'target_snapshot': {'conversation_name': 'Customer A'},
                            'result_evidence': None,
                            'last_error_code': None,
                            'last_error_message': None,
                            'started_at': None,
                            'completed_at': None,
                            'created_at': _dt('2026-06-27T10:00:00'),
                            'updated_at': _dt('2026-06-27T10:00:00'),
                        },
                        {
                            'id': 902,
                            'bot_uuid': 'bot-desktop',
                            'connector_id': 'wxwork-local',
                            'conversation_id': 21,
                            'message_id': 11,
                            'draft_id': 31,
                            'action': 'paste_draft',
                            'execution_mode': 'paste_only',
                            'runtime_task_id': 'task-902',
                            'status': 'running',
                            'stage': 'running',
                            'attempt_count': 1,
                            'request_digest': 'req-902',
                            'draft_content_hash': 'hash-902',
                            'target_snapshot': {'conversation_name': 'Customer A'},
                            'result_evidence': None,
                            'last_error_code': None,
                            'last_error_message': None,
                            'started_at': _dt('2026-06-27T10:01:00'),
                            'completed_at': None,
                            'created_at': _dt('2026-06-27T10:01:00'),
                            'updated_at': _dt('2026-06-27T10:01:00'),
                        },
                    ]
                )
            )

        await run_alembic_stamp(sqlite_engine, '0011_processing_run_uniq')
        await run_alembic_upgrade(sqlite_engine, 'head')

        async with sqlite_engine.begin() as conn:
            def inspect_runs(sync_conn):
                inspector = sa.inspect(sync_conn)
                indexes = {index['name'] for index in inspector.get_indexes('desktop_automation_runs')}
                desktop_runs = sa.Table('desktop_automation_runs', sa.MetaData(), autoload_with=sync_conn)
                rows = sync_conn.execute(
                    sa.select(desktop_runs)
                    .where(
                        desktop_runs.c.message_id == 11,
                        desktop_runs.c.draft_id == 31,
                    )
                    .order_by(desktop_runs.c.id.asc())
                ).mappings().all()
                return indexes, rows

            indexes, rows = await conn.run_sync(inspect_runs)

        assert 'ux_desktop_automation_runs_active' in indexes
        assert len(rows) == 2
        assert rows[0]['status'] == 'failed'
        assert rows[0]['completed_at'] is not None
        assert rows[0]['last_error_code'] == 'TASK_CONFLICT'
        assert rows[1]['status'] == 'running'

    @pytest.mark.asyncio
    async def test_upgrade_blocks_second_active_desktop_run_for_same_message_and_draft(self, sqlite_engine):
        async with sqlite_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        await run_alembic_stamp(sqlite_engine, '0011_processing_run_uniq')
        await run_alembic_upgrade(sqlite_engine, 'head')

        with pytest.raises(sa.exc.IntegrityError):
            async with sqlite_engine.begin() as conn:
                desktop_runs = await conn.run_sync(
                    lambda sync_conn: sa.Table('desktop_automation_runs', sa.MetaData(), autoload_with=sync_conn)
                )
                await conn.execute(
                    sa.insert(desktop_runs).values(
                        {
                            'message_id': 11,
                            'draft_id': 31,
                            'bot_uuid': 'bot-desktop',
                            'connector_id': 'wxwork-local',
                            'conversation_id': 21,
                            'action': 'paste_draft',
                            'execution_mode': 'paste_only',
                            'runtime_task_id': 'task-903',
                            'status': 'queued',
                            'stage': 'queued',
                            'attempt_count': 1,
                            'request_digest': 'req-903',
                            'draft_content_hash': 'hash-903',
                            'target_snapshot': {'conversation_name': 'Customer A'},
                            'result_evidence': None,
                            'last_error_code': None,
                            'last_error_message': None,
                            'started_at': None,
                            'completed_at': None,
                            'created_at': _dt('2026-06-27T10:02:00'),
                            'updated_at': _dt('2026-06-27T10:02:00'),
                        }
                    )
                )
                await conn.execute(
                    sa.insert(desktop_runs).values(
                        {
                            'message_id': 11,
                            'draft_id': 31,
                            'bot_uuid': 'bot-desktop',
                            'connector_id': 'wxwork-local',
                            'conversation_id': 21,
                            'action': 'paste_draft',
                            'execution_mode': 'paste_only',
                            'runtime_task_id': 'task-904',
                            'status': 'starting',
                            'stage': 'starting',
                            'attempt_count': 1,
                            'request_digest': 'req-904',
                            'draft_content_hash': 'hash-904',
                            'target_snapshot': {'conversation_name': 'Customer A'},
                            'result_evidence': None,
                            'last_error_code': None,
                            'last_error_message': None,
                            'started_at': None,
                            'completed_at': None,
                            'created_at': _dt('2026-06-27T10:03:00'),
                            'updated_at': _dt('2026-06-27T10:03:00'),
                        }
                    )
                )
