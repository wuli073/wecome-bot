"""add durable broadcast execution leases and send reservations

Revision ID: 0024_bc_exec_leases
Revises: 0023_group_name_dupes
Create Date: 2026-07-16
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = '0024_bc_exec_leases'
down_revision = '0023_group_name_dupes'
branch_labels = None
depends_on = None


def _columns(inspector, table: str) -> set[str]:
    if table not in inspector.get_table_names():
        return set()
    return {column['name'] for column in inspector.get_columns(table)}


def _indexes(inspector, table: str) -> set[str]:
    if table not in inspector.get_table_names():
        return set()
    return {index['name'] for index in inspector.get_indexes(table)}


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    draft_columns = _columns(inspector, 'broadcast_drafts')
    if draft_columns:
        with op.batch_alter_table('broadcast_drafts') as batch:
            if 'active_send_task_id' not in draft_columns:
                batch.add_column(sa.Column('active_send_task_id', sa.Integer(), nullable=True))
            if 'send_reserved_at' not in draft_columns:
                batch.add_column(sa.Column('send_reserved_at', sa.DateTime(), nullable=True))
    if draft_columns and 'ix_broadcast_drafts_active_send_task' not in _indexes(sa.inspect(conn), 'broadcast_drafts'):
        op.create_index('ix_broadcast_drafts_active_send_task', 'broadcast_drafts', ['active_send_task_id'])

    batch_columns = _columns(sa.inspect(conn), 'broadcast_execution_batches')
    if batch_columns:
        with op.batch_alter_table('broadcast_execution_batches') as batch:
            if 'warning_tasks' not in batch_columns:
                batch.add_column(sa.Column('warning_tasks', sa.Integer(), nullable=False, server_default='0'))
            if 'unknown_tasks' not in batch_columns:
                batch.add_column(sa.Column('unknown_tasks', sa.Integer(), nullable=False, server_default='0'))

    task_columns = _columns(sa.inspect(conn), 'broadcast_execution_tasks')
    if task_columns:
        with op.batch_alter_table('broadcast_execution_tasks') as batch:
            if 'claim_token' not in task_columns:
                batch.add_column(sa.Column('claim_token', sa.String(length=64), nullable=True))
            if 'claimed_by' not in task_columns:
                batch.add_column(sa.Column('claimed_by', sa.String(length=255), nullable=True))
            if 'claimed_at' not in task_columns:
                batch.add_column(sa.Column('claimed_at', sa.DateTime(), nullable=True))
            if 'lease_expires_at' not in task_columns:
                batch.add_column(sa.Column('lease_expires_at', sa.DateTime(), nullable=True))
    task_indexes = _indexes(sa.inspect(conn), 'broadcast_execution_tasks')
    if task_columns and 'ix_broadcast_execution_tasks_claim_token' not in task_indexes:
        op.create_index('ix_broadcast_execution_tasks_claim_token', 'broadcast_execution_tasks', ['claim_token'])
    if task_columns and 'ix_broadcast_execution_tasks_lease_expires_at' not in task_indexes:
        op.create_index('ix_broadcast_execution_tasks_lease_expires_at', 'broadcast_execution_tasks', ['lease_expires_at'])

    if 'broadcast_execution_lanes' not in sa.inspect(conn).get_table_names():
        op.create_table(
            'broadcast_execution_lanes',
            sa.Column('lane_key', sa.String(length=64), primary_key=True),
            sa.Column('owner_token', sa.String(length=64), nullable=True),
            sa.Column('owner_instance', sa.String(length=255), nullable=True),
            sa.Column('acquired_at', sa.DateTime(), nullable=True),
            sa.Column('lease_expires_at', sa.DateTime(), nullable=True),
            sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        )
        op.create_index('ix_broadcast_execution_lanes_owner_token', 'broadcast_execution_lanes', ['owner_token'])
        op.create_index('ix_broadcast_execution_lanes_lease_expires_at', 'broadcast_execution_lanes', ['lease_expires_at'])
        op.bulk_insert(
            sa.table('broadcast_execution_lanes', sa.column('lane_key', sa.String())),
            [{'lane_key': 'desktop_runtime'}],
        )


def downgrade() -> None:
    # Execution leases and draft reservations are durable operational state.
    # Roll back the application version and restore a database backup instead.
    raise RuntimeError(
        '0024_bc_exec_leases direct downgrade is not supported; restore a pre-0024 database backup'
    )
