"""persist broadcast import batch group field metadata

Revision ID: 0022_bc_import_group_field_used
Revises: 0021_bc_target_conv_id
Create Date: 2026-07-07
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = '0022_bc_import_group_field_used'
down_revision = '0021_bc_target_conv_id'
branch_labels = None
depends_on = None


def _table_names(inspector) -> set[str]:
    return set(inspector.get_table_names())


def _column_names(inspector, table_name: str) -> set[str]:
    if table_name not in _table_names(inspector):
        return set()
    return {column['name'] for column in inspector.get_columns(table_name)}


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    if 'broadcast_import_batches' not in _table_names(inspector):
        return

    columns = _column_names(inspector, 'broadcast_import_batches')
    with op.batch_alter_table('broadcast_import_batches') as batch_op:
        if 'group_field_used' not in columns:
            batch_op.add_column(sa.Column('group_field_used', sa.String(length=255), nullable=True))
        if 'group_field_source' not in columns:
            batch_op.add_column(sa.Column('group_field_source', sa.String(length=32), nullable=True))


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    if 'broadcast_import_batches' not in _table_names(inspector):
        return

    columns = _column_names(inspector, 'broadcast_import_batches')
    with op.batch_alter_table('broadcast_import_batches') as batch_op:
        if 'group_field_source' in columns:
            batch_op.drop_column('group_field_source')
        if 'group_field_used' in columns:
            batch_op.drop_column('group_field_used')
