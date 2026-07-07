"""persist broadcast import group template assignments

Revision ID: 0020_bc_group_tpl
Revises: 0019_bc_send_status
Create Date: 2026-07-06
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = '0020_bc_group_tpl'
down_revision = '0019_bc_send_status'
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
    return {
        constraint['name']
        for constraint in inspector.get_unique_constraints(table_name)
        if constraint.get('name')
    }


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    table_name = 'broadcast_import_group_template_assignments'
    table_created = False
    if table_name not in _table_names(inspector):
        op.create_table(
            table_name,
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                'import_batch_id',
                sa.Integer(),
                sa.ForeignKey('broadcast_import_batches.id', ondelete='CASCADE'),
                nullable=False,
            ),
            sa.Column('group_key', sa.String(length=128), nullable=False),
            sa.Column(
                'template_id',
                sa.Integer(),
                sa.ForeignKey('broadcast_templates.id', ondelete='SET NULL'),
                nullable=True,
            ),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column(
                'updated_at',
                sa.DateTime(),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.UniqueConstraint(
                'import_batch_id',
                'group_key',
                name='uq_bc_imp_group_tpl_assign_batch_group',
            ),
        )
        table_created = True
        inspector = sa.inspect(conn)

    columns = _column_names(inspector, table_name)
    if 'import_batch_id' not in columns:
        op.add_column(table_name, sa.Column('import_batch_id', sa.Integer(), nullable=False))
    if 'group_key' not in columns:
        op.add_column(table_name, sa.Column('group_key', sa.String(length=128), nullable=False))
    if 'template_id' not in columns:
        op.add_column(table_name, sa.Column('template_id', sa.Integer(), nullable=True))
    if 'created_at' not in columns:
        op.add_column(
            table_name,
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )
    if 'updated_at' not in columns:
        op.add_column(
            table_name,
            sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )

    inspector = sa.inspect(conn)
    if 'ix_bc_imp_group_tpl_assign_batch' not in _index_names(inspector, table_name):
        op.create_index(
            'ix_bc_imp_group_tpl_assign_batch',
            table_name,
            ['import_batch_id', 'group_key'],
        )
    if 'ix_broadcast_import_group_template_assignments_import_batch_id' not in _index_names(inspector, table_name):
        op.create_index(
            'ix_broadcast_import_group_template_assignments_import_batch_id',
            table_name,
            ['import_batch_id'],
        )
    if 'ix_broadcast_import_group_template_assignments_group_key' not in _index_names(inspector, table_name):
        op.create_index(
            'ix_broadcast_import_group_template_assignments_group_key',
            table_name,
            ['group_key'],
        )
    if 'ix_broadcast_import_group_template_assignments_template_id' not in _index_names(inspector, table_name):
        op.create_index(
            'ix_broadcast_import_group_template_assignments_template_id',
            table_name,
            ['template_id'],
        )
    if (
        not table_created
        and 'uq_bc_imp_group_tpl_assign_batch_group'
        not in _unique_constraint_names(inspector, table_name)
    ):
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.create_unique_constraint(
                'uq_bc_imp_group_tpl_assign_batch_group',
                ['import_batch_id', 'group_key'],
            )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    table_name = 'broadcast_import_group_template_assignments'
    if table_name not in _table_names(inspector):
        return
    op.drop_table(table_name)
