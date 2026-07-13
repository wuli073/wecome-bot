"""persist broadcast target conversation ids

Revision ID: 0021_bc_target_conv_id
Revises: 0020_bc_group_tpl
Create Date: 2026-07-07
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = '0021_bc_target_conv_id'
down_revision = '0020_bc_group_tpl'
branch_labels = None
depends_on = None


def _table_names(inspector) -> set[str]:
    return set(inspector.get_table_names())


def _column_names(inspector, table_name: str) -> set[str]:
    if table_name not in _table_names(inspector):
        return set()
    return {column['name'] for column in inspector.get_columns(table_name)}


def _index_names(inspector, table_name: str) -> set[str]:
    if table_name not in _table_names(inspector):
        return set()
    return {index['name'] for index in inspector.get_indexes(table_name)}


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    if 'broadcast_group_rules' in _table_names(inspector) and 'target_conversation_id' not in _column_names(
        inspector,
        'broadcast_group_rules',
    ):
        op.add_column(
            'broadcast_group_rules',
            sa.Column('target_conversation_id', sa.String(length=255), nullable=True),
        )
    if 'broadcast_import_rows' in _table_names(inspector) and 'matched_conversation_id' not in _column_names(
        inspector,
        'broadcast_import_rows',
    ):
        op.add_column(
            'broadcast_import_rows',
            sa.Column('matched_conversation_id', sa.String(length=255), nullable=True),
        )
    if 'broadcast_drafts' in _table_names(inspector) and 'target_conversation_id' not in _column_names(
        inspector,
        'broadcast_drafts',
    ):
        op.add_column(
            'broadcast_drafts',
            sa.Column('target_conversation_id', sa.String(length=255), nullable=True),
        )

    inspector = sa.inspect(conn)
    if 'broadcast_group_rules' in _table_names(inspector) and 'ix_broadcast_group_rules_target_conversation_id' not in _index_names(
        inspector,
        'broadcast_group_rules',
    ):
        op.create_index(
            'ix_broadcast_group_rules_target_conversation_id',
            'broadcast_group_rules',
            ['target_conversation_id'],
        )
    if 'broadcast_import_rows' in _table_names(inspector) and 'ix_broadcast_import_rows_matched_conversation_id' not in _index_names(
        inspector,
        'broadcast_import_rows',
    ):
        op.create_index(
            'ix_broadcast_import_rows_matched_conversation_id',
            'broadcast_import_rows',
            ['matched_conversation_id'],
        )
    if 'broadcast_drafts' in _table_names(inspector) and 'ix_broadcast_drafts_target_conversation_id' not in _index_names(
        inspector,
        'broadcast_drafts',
    ):
        op.create_index(
            'ix_broadcast_drafts_target_conversation_id',
            'broadcast_drafts',
            ['target_conversation_id'],
        )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    if 'broadcast_drafts' in _table_names(inspector) and 'ix_broadcast_drafts_target_conversation_id' in _index_names(
        inspector,
        'broadcast_drafts',
    ):
        op.drop_index('ix_broadcast_drafts_target_conversation_id', table_name='broadcast_drafts')
    if 'broadcast_import_rows' in _table_names(inspector) and 'ix_broadcast_import_rows_matched_conversation_id' in _index_names(
        inspector,
        'broadcast_import_rows',
    ):
        op.drop_index(
            'ix_broadcast_import_rows_matched_conversation_id',
            table_name='broadcast_import_rows',
        )
    if 'broadcast_group_rules' in _table_names(inspector) and 'ix_broadcast_group_rules_target_conversation_id' in _index_names(
        inspector,
        'broadcast_group_rules',
    ):
        op.drop_index(
            'ix_broadcast_group_rules_target_conversation_id',
            table_name='broadcast_group_rules',
        )

    inspector = sa.inspect(conn)
    if 'broadcast_drafts' in _table_names(inspector) and 'target_conversation_id' in _column_names(
        inspector,
        'broadcast_drafts',
    ):
        with op.batch_alter_table('broadcast_drafts') as batch_op:
            batch_op.drop_column('target_conversation_id')
    inspector = sa.inspect(conn)
    if 'broadcast_import_rows' in _table_names(inspector) and 'matched_conversation_id' in _column_names(
        inspector,
        'broadcast_import_rows',
    ):
        with op.batch_alter_table('broadcast_import_rows') as batch_op:
            batch_op.drop_column('matched_conversation_id')
    inspector = sa.inspect(conn)
    if 'broadcast_group_rules' in _table_names(inspector) and 'target_conversation_id' in _column_names(
        inspector,
        'broadcast_group_rules',
    ):
        with op.batch_alter_table('broadcast_group_rules') as batch_op:
            batch_op.drop_column('target_conversation_id')
