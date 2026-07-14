"""allow duplicate group names with distinct external conversation IDs

Revision ID: 0023_group_name_dupes
Revises: 0022_bc_import_group_field_used
Create Date: 2026-07-14
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = '0023_group_name_dupes'
down_revision = '0022_bc_import_group_field_used'
branch_labels = None
depends_on = None


def _has_constraint(inspector, table_name: str, constraint_name: str) -> bool:
    if table_name not in inspector.get_table_names():
        return False
    return any(
        constraint.get('name') == constraint_name
        for constraint in inspector.get_unique_constraints(table_name)
    )


def upgrade() -> None:
    table_name = 'broadcast_group_names'
    constraint_name = 'uq_broadcast_group_names_scope_name'
    if _has_constraint(sa.inspect(op.get_bind()), table_name, constraint_name):
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.drop_constraint(constraint_name, type_='unique')


def downgrade() -> None:
    table_name = 'broadcast_group_names'
    constraint_name = 'uq_broadcast_group_names_scope_name'
    if table_name not in sa.inspect(op.get_bind()).get_table_names():
        return
    with op.batch_alter_table(table_name) as batch_op:
        batch_op.create_unique_constraint(
            constraint_name,
            ['bot_uuid', 'connector_id', 'name'],
        )
