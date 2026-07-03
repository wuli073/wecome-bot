"""add broadcast phase 3 tables

Revision ID: 0014_broadcast_phase3
Revises: 0013_broadcast_rules
Create Date: 2026-07-03
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = '0014_broadcast_phase3'
down_revision = '0013_broadcast_rules'
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

    if 'broadcast_import_batches' not in tables:
        op.create_table(
            'broadcast_import_batches',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('bot_uuid', sa.String(length=255), nullable=False),
            sa.Column('connector_id', sa.String(length=255), nullable=False),
            sa.Column('original_file_name', sa.String(length=255), nullable=False),
            sa.Column('file_type', sa.String(length=32), nullable=False),
            sa.Column('worksheet_name', sa.String(length=255), nullable=True),
            sa.Column('status', sa.String(length=32), nullable=False),
            sa.Column('drafts_stale', sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column('total_rows', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('valid_rows', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('invalid_rows', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('matched_rows', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('unmatched_rows', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )

    if 'broadcast_import_rows' not in tables:
        op.create_table(
            'broadcast_import_rows',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('import_batch_id', sa.Integer(), nullable=False),
            sa.Column('source_row_number', sa.Integer(), nullable=False),
            sa.Column('raw_data', sa.JSON(), nullable=False),
            sa.Column('group_value', sa.String(length=255), nullable=True),
            sa.Column('matched_conversation_name', sa.String(length=255), nullable=True),
            sa.Column('matched_rule_id', sa.Integer(), nullable=True),
            sa.Column('match_status', sa.String(length=32), nullable=False),
            sa.Column('error_message', sa.Text(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.ForeignKeyConstraint(
                ['import_batch_id'],
                ['broadcast_import_batches.id'],
                ondelete='CASCADE',
            ),
            sa.ForeignKeyConstraint(
                ['matched_rule_id'],
                ['broadcast_group_rules.id'],
                ondelete='SET NULL',
            ),
            sa.UniqueConstraint(
                'import_batch_id',
                'source_row_number',
                name='uq_broadcast_import_rows_batch_row_number',
            ),
        )

    if 'broadcast_drafts' not in tables:
        op.create_table(
            'broadcast_drafts',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('bot_uuid', sa.String(length=255), nullable=False),
            sa.Column('connector_id', sa.String(length=255), nullable=False),
            sa.Column('import_batch_id', sa.Integer(), nullable=False),
            sa.Column('group_value', sa.String(length=255), nullable=False),
            sa.Column('target_conversation_name', sa.String(length=255), nullable=True),
            sa.Column('template_id', sa.Integer(), nullable=True),
            sa.Column('template_name_snapshot', sa.String(length=255), nullable=False),
            sa.Column('template_content_snapshot', sa.Text(), nullable=False),
            sa.Column('render_variables', sa.JSON(), nullable=False),
            sa.Column('draft_text', sa.Text(), nullable=False),
            sa.Column('status', sa.String(length=32), nullable=False),
            sa.Column('error_message', sa.Text(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.ForeignKeyConstraint(
                ['import_batch_id'],
                ['broadcast_import_batches.id'],
                ondelete='CASCADE',
            ),
            sa.ForeignKeyConstraint(
                ['template_id'],
                ['broadcast_templates.id'],
                ondelete='SET NULL',
            ),
            sa.UniqueConstraint(
                'import_batch_id',
                'group_value',
                name='uq_broadcast_drafts_batch_group_value',
            ),
        )

    inspector = sa.inspect(conn)
    index_specs = [
        ('broadcast_import_batches', 'ix_broadcast_import_batches_bot_uuid', ['bot_uuid']),
        ('broadcast_import_batches', 'ix_broadcast_import_batches_connector_id', ['connector_id']),
        ('broadcast_import_batches', 'ix_broadcast_import_batches_scope', ['bot_uuid', 'connector_id']),
        ('broadcast_import_batches', 'ix_broadcast_import_batches_created_at', ['created_at']),
        ('broadcast_import_rows', 'ix_broadcast_import_rows_import_batch_id', ['import_batch_id']),
        ('broadcast_import_rows', 'ix_broadcast_import_rows_match_status', ['match_status']),
        ('broadcast_import_rows', 'ix_broadcast_import_rows_group_value', ['group_value']),
        ('broadcast_drafts', 'ix_broadcast_drafts_bot_uuid', ['bot_uuid']),
        ('broadcast_drafts', 'ix_broadcast_drafts_connector_id', ['connector_id']),
        ('broadcast_drafts', 'ix_broadcast_drafts_scope', ['bot_uuid', 'connector_id']),
        ('broadcast_drafts', 'ix_broadcast_drafts_import_batch_id', ['import_batch_id']),
        ('broadcast_drafts', 'ix_broadcast_drafts_status', ['status']),
        ('broadcast_drafts', 'ix_broadcast_drafts_updated_at', ['updated_at']),
    ]
    for table_name, index_name, columns in index_specs:
        if index_name not in _index_names(inspector, table_name):
            op.create_index(index_name, table_name, columns)


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = _table_names(inspector)

    drop_specs = {
        'broadcast_drafts': [
            'ix_broadcast_drafts_updated_at',
            'ix_broadcast_drafts_status',
            'ix_broadcast_drafts_import_batch_id',
            'ix_broadcast_drafts_scope',
            'ix_broadcast_drafts_connector_id',
            'ix_broadcast_drafts_bot_uuid',
        ],
        'broadcast_import_rows': [
            'ix_broadcast_import_rows_group_value',
            'ix_broadcast_import_rows_match_status',
            'ix_broadcast_import_rows_import_batch_id',
        ],
        'broadcast_import_batches': [
            'ix_broadcast_import_batches_created_at',
            'ix_broadcast_import_batches_scope',
            'ix_broadcast_import_batches_connector_id',
            'ix_broadcast_import_batches_bot_uuid',
        ],
    }

    for table_name, index_names in drop_specs.items():
        if table_name not in tables:
            continue
        for index_name in index_names:
            if index_name in _index_names(inspector, table_name):
                op.drop_index(index_name, table_name=table_name)

    for table_name in ['broadcast_drafts', 'broadcast_import_rows', 'broadcast_import_batches']:
        if table_name in tables:
            op.drop_table(table_name)
