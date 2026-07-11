"""add broadcast execution tables

Revision ID: 0015_broadcast_execution
Revises: 0014_broadcast_phase3
Create Date: 2026-07-03
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = '0015_broadcast_execution'
down_revision = '0014_broadcast_phase3'
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

    if 'broadcast_execution_batches' not in tables:
        op.create_table(
            'broadcast_execution_batches',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('bot_uuid', sa.String(length=255), nullable=False),
            sa.Column('connector_id', sa.String(length=255), nullable=False),
            sa.Column('channel', sa.String(length=64), nullable=False),
            sa.Column('mode', sa.String(length=32), nullable=False),
            sa.Column('status', sa.String(length=32), nullable=False),
            sa.Column('total_tasks', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('pending_tasks', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('running_tasks', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('succeeded_tasks', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('failed_tasks', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('cancelled_tasks', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('interrupted_tasks', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('created_by', sa.String(length=255), nullable=False),
            sa.Column('last_action_by', sa.String(length=255), nullable=True),
            sa.Column('error_message', sa.Text(), nullable=True),
            sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column('started_at', sa.DateTime(), nullable=True),
            sa.Column('paused_at', sa.DateTime(), nullable=True),
            sa.Column('finished_at', sa.DateTime(), nullable=True),
            sa.Column('cancelled_at', sa.DateTime(), nullable=True),
        )

    if 'broadcast_execution_tasks' not in tables:
        op.create_table(
            'broadcast_execution_tasks',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('execution_batch_id', sa.Integer(), nullable=False),
            sa.Column('draft_id', sa.Integer(), nullable=True),
            sa.Column('draft_text_snapshot', sa.Text(), nullable=False),
            sa.Column('target_conversation_snapshot', sa.Text(), nullable=False),
            sa.Column('channel', sa.String(length=64), nullable=False),
            sa.Column('action', sa.String(length=32), nullable=False),
            sa.Column('status', sa.String(length=32), nullable=False),
            sa.Column('sequence_no', sa.Integer(), nullable=False),
            sa.Column('attempt_count', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('max_attempts', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('idempotency_key', sa.String(length=255), nullable=False),
            sa.Column('request_digest', sa.String(length=64), nullable=False),
            sa.Column('runtime_task_id', sa.String(length=255), nullable=True),
            sa.Column('error_code', sa.String(length=255), nullable=True),
            sa.Column('error_message', sa.Text(), nullable=True),
            sa.Column('operator_note', sa.Text(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column('started_at', sa.DateTime(), nullable=True),
            sa.Column('finished_at', sa.DateTime(), nullable=True),
            sa.Column('cancelled_at', sa.DateTime(), nullable=True),
            sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.ForeignKeyConstraint(
                ['execution_batch_id'],
                ['broadcast_execution_batches.id'],
                ondelete='CASCADE',
            ),
            sa.ForeignKeyConstraint(
                ['draft_id'],
                ['broadcast_drafts.id'],
                ondelete='SET NULL',
            ),
            sa.UniqueConstraint(
                'execution_batch_id',
                'sequence_no',
                name='uq_broadcast_execution_tasks_batch_sequence',
            ),
        )

    if 'broadcast_execution_attempts' not in tables:
        op.create_table(
            'broadcast_execution_attempts',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('execution_task_id', sa.Integer(), nullable=False),
            sa.Column('attempt_no', sa.Integer(), nullable=False),
            sa.Column('idempotency_key', sa.String(length=255), nullable=False),
            sa.Column('request_digest', sa.String(length=64), nullable=False),
            sa.Column('runtime_task_id', sa.String(length=255), nullable=True),
            sa.Column('request_summary', sa.Text(), nullable=True),
            sa.Column('response_summary', sa.Text(), nullable=True),
            sa.Column('status', sa.String(length=32), nullable=False),
            sa.Column('error_code', sa.String(length=255), nullable=True),
            sa.Column('error_message', sa.Text(), nullable=True),
            sa.Column('started_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column('finished_at', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(
                ['execution_task_id'],
                ['broadcast_execution_tasks.id'],
                ondelete='CASCADE',
            ),
            sa.UniqueConstraint(
                'execution_task_id',
                'attempt_no',
                name='uq_broadcast_execution_attempts_task_attempt',
            ),
            sa.UniqueConstraint(
                'idempotency_key',
                name='uq_broadcast_execution_attempts_idempotency_key',
            ),
            sa.UniqueConstraint(
                'runtime_task_id',
                name='uq_broadcast_execution_attempts_runtime_task_id',
            ),
        )

    if 'broadcast_execution_evidence' not in tables:
        op.create_table(
            'broadcast_execution_evidence',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('execution_attempt_id', sa.Integer(), nullable=False),
            sa.Column('window_title', sa.String(length=255), nullable=True),
            sa.Column('target_conversation', sa.String(length=255), nullable=True),
            sa.Column('action', sa.String(length=32), nullable=False),
            sa.Column('input_located', sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column('draft_written', sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column('send_triggered', sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column('clipboard_restored', sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column('runtime_state', sa.String(length=64), nullable=True),
            sa.Column('evidence_summary', sa.Text(), nullable=True),
            sa.Column('technical_details', sa.Text(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.ForeignKeyConstraint(
                ['execution_attempt_id'],
                ['broadcast_execution_attempts.id'],
                ondelete='CASCADE',
            ),
        )

    if 'broadcast_send_confirmations' not in tables:
        op.create_table(
            'broadcast_send_confirmations',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('execution_task_id', sa.Integer(), nullable=False),
            sa.Column('confirmation_token_hash', sa.String(length=255), nullable=False),
            sa.Column('issued_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column('expires_at', sa.DateTime(), nullable=True),
            sa.Column('used_at', sa.DateTime(), nullable=True),
            sa.Column('issued_by', sa.String(length=255), nullable=False),
            sa.Column('used_by', sa.String(length=255), nullable=True),
            sa.Column('status', sa.String(length=32), nullable=False),
            sa.ForeignKeyConstraint(
                ['execution_task_id'],
                ['broadcast_execution_tasks.id'],
                ondelete='CASCADE',
            ),
            sa.UniqueConstraint(
                'confirmation_token_hash',
                name='uq_broadcast_send_confirmations_token_hash',
            ),
        )

    inspector = sa.inspect(conn)
    index_specs = [
        ('broadcast_execution_batches', 'ix_broadcast_execution_batches_bot_uuid', ['bot_uuid']),
        ('broadcast_execution_batches', 'ix_broadcast_execution_batches_connector_id', ['connector_id']),
        ('broadcast_execution_batches', 'ix_broadcast_execution_batches_scope', ['bot_uuid', 'connector_id']),
        ('broadcast_execution_batches', 'ix_broadcast_execution_batches_status', ['status']),
        ('broadcast_execution_batches', 'ix_broadcast_execution_batches_created_at', ['created_at']),
        ('broadcast_execution_tasks', 'ix_broadcast_execution_tasks_execution_batch_id', ['execution_batch_id']),
        ('broadcast_execution_tasks', 'ix_broadcast_execution_tasks_status', ['status']),
        ('broadcast_execution_tasks', 'ix_broadcast_execution_tasks_sequence_no', ['sequence_no']),
        ('broadcast_execution_attempts', 'ix_broadcast_execution_attempts_execution_task_id', ['execution_task_id']),
        ('broadcast_execution_attempts', 'ix_broadcast_execution_attempts_runtime_task_id', ['runtime_task_id']),
        ('broadcast_execution_evidence', 'ix_broadcast_execution_evidence_execution_attempt_id', ['execution_attempt_id']),
        ('broadcast_send_confirmations', 'ix_broadcast_send_confirmations_execution_task_id', ['execution_task_id']),
    ]
    for table_name, index_name, columns in index_specs:
        if index_name not in _index_names(inspector, table_name):
            op.create_index(index_name, table_name, columns)


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = _table_names(inspector)

    drop_specs = {
        'broadcast_send_confirmations': [
            'ix_broadcast_send_confirmations_execution_task_id',
        ],
        'broadcast_execution_evidence': [
            'ix_broadcast_execution_evidence_execution_attempt_id',
        ],
        'broadcast_execution_attempts': [
            'ix_broadcast_execution_attempts_runtime_task_id',
            'ix_broadcast_execution_attempts_execution_task_id',
        ],
        'broadcast_execution_tasks': [
            'ix_broadcast_execution_tasks_sequence_no',
            'ix_broadcast_execution_tasks_status',
            'ix_broadcast_execution_tasks_execution_batch_id',
        ],
        'broadcast_execution_batches': [
            'ix_broadcast_execution_batches_created_at',
            'ix_broadcast_execution_batches_status',
            'ix_broadcast_execution_batches_scope',
            'ix_broadcast_execution_batches_connector_id',
            'ix_broadcast_execution_batches_bot_uuid',
        ],
    }

    for table_name, index_names in drop_specs.items():
        if table_name not in tables:
            continue
        for index_name in index_names:
            if index_name in _index_names(inspector, table_name):
                op.drop_index(index_name, table_name=table_name)

    for table_name in [
        'broadcast_send_confirmations',
        'broadcast_execution_evidence',
        'broadcast_execution_attempts',
        'broadcast_execution_tasks',
        'broadcast_execution_batches',
    ]:
        if table_name in tables:
            op.drop_table(table_name)
