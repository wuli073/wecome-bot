"""add broadcast group sync fields

Revision ID: 0016_broadcast_group_sync
Revises: 0015_broadcast_execution
Create Date: 2026-07-04
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = '0016_broadcast_group_sync'
down_revision = '0015_broadcast_execution'
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


def _unique_constraint_names(inspector, table_name: str) -> set[str]:
    if table_name not in _table_names(inspector):
        return set()
    return {constraint['name'] for constraint in inspector.get_unique_constraints(table_name) if constraint.get('name')}


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    table_name = 'broadcast_group_names'

    if table_name not in _table_names(inspector):
        return

    columns = _column_names(inspector, table_name)
    index_names = _index_names(inspector, table_name)
    unique_names = _unique_constraint_names(inspector, table_name)

    with op.batch_alter_table(table_name) as batch_op:
        if 'external_conversation_id' not in columns:
            batch_op.add_column(sa.Column('external_conversation_id', sa.String(length=255), nullable=True))
        if 'uq_broadcast_group_names_scope_external_id' not in unique_names:
            batch_op.create_unique_constraint(
                'uq_broadcast_group_names_scope_external_id',
                ['bot_uuid', 'connector_id', 'external_conversation_id'],
            )

    inspector = sa.inspect(conn)
    index_names = _index_names(inspector, table_name)
    if 'ix_broadcast_group_names_external_conversation_id' not in index_names:
        op.create_index(
            'ix_broadcast_group_names_external_conversation_id',
            table_name,
            ['external_conversation_id'],
        )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    table_name = 'broadcast_group_names'

    if table_name not in _table_names(inspector):
        return

    columns = _column_names(inspector, table_name)
    index_names = _index_names(inspector, table_name)
    unique_names = _unique_constraint_names(inspector, table_name)

    if 'ix_broadcast_group_names_external_conversation_id' in index_names:
        op.drop_index('ix_broadcast_group_names_external_conversation_id', table_name=table_name)

    with op.batch_alter_table(table_name) as batch_op:
        if 'uq_broadcast_group_names_scope_external_id' in unique_names:
            batch_op.drop_constraint('uq_broadcast_group_names_scope_external_id', type_='unique')
        if 'external_conversation_id' in columns:
            batch_op.drop_column('external_conversation_id')
