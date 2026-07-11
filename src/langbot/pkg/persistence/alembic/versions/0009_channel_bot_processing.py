"""add channel bot processing tables

Revision ID: 0009_channel_bot_processing
Revises: 0008_database_mode_tables
Create Date: 2026-06-25
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = '0009_channel_bot_processing'
down_revision = '0008_database_mode_tables'
branch_labels = None
depends_on = None


def _table_names(inspector) -> set[str]:
    return set(inspector.get_table_names())


def _index_names(inspector, table_name: str) -> set[str]:
    if table_name not in _table_names(inspector):
        return set()
    return {index['name'] for index in inspector.get_indexes(table_name)}


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = _table_names(inspector)

    if 'channel_accounts' not in tables:
        op.create_table(
            'channel_accounts',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('connector_id', sa.String(length=255), nullable=False),
            sa.Column('channel_type', sa.String(length=255), nullable=False),
            sa.Column('external_account_id', sa.String(length=255), nullable=False),
            sa.Column('display_name', sa.String(length=255), nullable=False),
            sa.Column('enabled', sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column('metadata', sa.JSON(), nullable=False, server_default='{}'),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint(
                'connector_id',
                'channel_type',
                'external_account_id',
                name='uq_channel_accounts_connector_channel_external',
            ),
        )
        op.create_index('ix_channel_accounts_connector_id', 'channel_accounts', ['connector_id'])
        op.create_index('ix_channel_accounts_channel_type', 'channel_accounts', ['channel_type'])
        op.create_index('ix_channel_accounts_external_account_id', 'channel_accounts', ['external_account_id'])

    inspector = sa.inspect(conn)
    tables = _table_names(inspector)
    if 'bot_channel_bindings' not in tables:
        op.create_table(
            'bot_channel_bindings',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('bot_uuid', sa.String(length=255), nullable=False),
            sa.Column('channel_account_id', sa.Integer(), nullable=False),
            sa.Column('enabled', sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column('effective_from', sa.DateTime(), nullable=True),
            sa.Column('auto_generate_draft', sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )
        op.create_index('ix_bot_channel_bindings_bot_uuid', 'bot_channel_bindings', ['bot_uuid'])
        op.create_index('ix_bot_channel_bindings_channel_account_id', 'bot_channel_bindings', ['channel_account_id'])
        op.create_index('ix_bot_channel_bindings_effective_from', 'bot_channel_bindings', ['effective_from'])

    inspector = sa.inspect(conn)
    tables = _table_names(inspector)
    if 'message_processing_runs' not in tables:
        op.create_table(
            'message_processing_runs',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('message_id', sa.Integer(), nullable=False),
            sa.Column('bot_uuid', sa.String(length=255), nullable=False),
            sa.Column('pipeline_uuid', sa.String(length=255), nullable=True),
            sa.Column('trigger', sa.String(length=50), nullable=False),
            sa.Column('status', sa.String(length=50), nullable=False),
            sa.Column('attempt_count', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('started_at', sa.DateTime(), nullable=True),
            sa.Column('completed_at', sa.DateTime(), nullable=True),
            sa.Column('last_error', sa.Text(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )
        op.create_index('ix_message_processing_runs_message_id', 'message_processing_runs', ['message_id'])
        op.create_index('ix_message_processing_runs_bot_uuid', 'message_processing_runs', ['bot_uuid'])
        op.create_index('ix_message_processing_runs_pipeline_uuid', 'message_processing_runs', ['pipeline_uuid'])
        op.create_index('ix_message_processing_runs_trigger', 'message_processing_runs', ['trigger'])
        op.create_index('ix_message_processing_runs_status', 'message_processing_runs', ['status'])

        dialect = conn.dialect.name
        if dialect == 'sqlite':
            op.create_index(
                'ix_message_processing_runs_atomic_claim',
                'message_processing_runs',
                ['message_id', 'bot_uuid'],
                unique=True,
                sqlite_where=sa.text("status = 'processing'")
            )
        elif dialect == 'postgresql':
            op.execute(
                sa.text(
                    "CREATE UNIQUE INDEX ix_message_processing_runs_atomic_claim "
                    "ON message_processing_runs (message_id, bot_uuid) "
                    "WHERE status = 'processing'"
                )
            )

    inspector = sa.inspect(conn)
    tables = _table_names(inspector)
    if 'reply_drafts' not in tables:
        op.create_table(
            'reply_drafts',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('processing_run_id', sa.Integer(), nullable=True),
            sa.Column('message_id', sa.Integer(), nullable=False),
            sa.Column('bot_uuid', sa.String(length=255), nullable=False),
            sa.Column('content', sa.Text(), nullable=False),
            sa.Column('source', sa.String(length=50), nullable=False),
            sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
            sa.Column('status', sa.String(length=50), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )
        op.create_index('ix_reply_drafts_processing_run_id', 'reply_drafts', ['processing_run_id'])
        op.create_index('ix_reply_drafts_message_id', 'reply_drafts', ['message_id'])
        op.create_index('ix_reply_drafts_bot_uuid', 'reply_drafts', ['bot_uuid'])
        op.create_index('ix_reply_drafts_source', 'reply_drafts', ['source'])
        op.create_index('ix_reply_drafts_status', 'reply_drafts', ['status'])

        # Ensure only one active draft per message+bot combination
        dialect = conn.dialect.name
        if dialect == 'sqlite':
            op.create_index(
                'ix_reply_drafts_active_unique',
                'reply_drafts',
                ['message_id', 'bot_uuid'],
                unique=True,
                sqlite_where=sa.text("status = 'active'")
            )
        elif dialect == 'postgresql':
            op.execute(
                sa.text(
                    "CREATE UNIQUE INDEX ix_reply_drafts_active_unique "
                    "ON reply_drafts (message_id, bot_uuid) "
                    "WHERE status = 'active'"
                )
            )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = _table_names(inspector)

    if 'reply_drafts' in tables:
        for index_name in [
            'ix_reply_drafts_active_unique',
            'ix_reply_drafts_status',
            'ix_reply_drafts_source',
            'ix_reply_drafts_bot_uuid',
            'ix_reply_drafts_message_id',
            'ix_reply_drafts_processing_run_id',
        ]:
            try:
                op.drop_index(index_name, table_name='reply_drafts')
            except Exception:
                pass
        op.drop_table('reply_drafts')

    if 'message_processing_runs' in tables:
        for index_name in [
            'ix_message_processing_runs_atomic_claim',
            'ix_message_processing_runs_status',
            'ix_message_processing_runs_trigger',
            'ix_message_processing_runs_pipeline_uuid',
            'ix_message_processing_runs_bot_uuid',
            'ix_message_processing_runs_message_id',
        ]:
            try:
                op.drop_index(index_name, table_name='message_processing_runs')
            except Exception:
                pass
        op.drop_table('message_processing_runs')

    if 'bot_channel_bindings' in tables:
        for index_name in [
            'ix_bot_channel_bindings_effective_from',
            'ix_bot_channel_bindings_channel_account_id',
            'ix_bot_channel_bindings_bot_uuid',
        ]:
            try:
                op.drop_index(index_name, table_name='bot_channel_bindings')
            except Exception:
                pass
        op.drop_table('bot_channel_bindings')

    if 'channel_accounts' in tables:
        for index_name in [
            'ix_channel_accounts_external_account_id',
            'ix_channel_accounts_channel_type',
            'ix_channel_accounts_connector_id',
        ]:
            try:
                op.drop_index(index_name, table_name='channel_accounts')
            except Exception:
                pass
        op.drop_table('channel_accounts')
