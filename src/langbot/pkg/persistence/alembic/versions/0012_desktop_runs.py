"""add desktop automation runs

Revision ID: 0012_desktop_runs
Revises: 0011_processing_run_uniq
Create Date: 2026-06-27
"""

from __future__ import annotations

import datetime

import sqlalchemy as sa
from alembic import op

revision = '0012_desktop_runs'
down_revision = '0011_processing_run_uniq'
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

    if 'desktop_automation_runs' not in tables:
        op.create_table(
            'desktop_automation_runs',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('bot_uuid', sa.String(length=255), nullable=False),
            sa.Column('connector_id', sa.String(length=255), nullable=False),
            sa.Column('conversation_id', sa.Integer(), nullable=False),
            sa.Column('message_id', sa.Integer(), nullable=False),
            sa.Column('draft_id', sa.Integer(), nullable=False),
            sa.Column('action', sa.String(length=50), nullable=False),
            sa.Column('execution_mode', sa.String(length=50), nullable=False),
            sa.Column('runtime_task_id', sa.String(length=255), nullable=True),
            sa.Column('status', sa.String(length=50), nullable=False),
            sa.Column('stage', sa.String(length=50), nullable=False),
            sa.Column('attempt_count', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('request_digest', sa.String(length=255), nullable=False),
            sa.Column('draft_content_hash', sa.String(length=255), nullable=False),
            sa.Column('target_snapshot', sa.JSON(), nullable=False, server_default='{}'),
            sa.Column('result_evidence', sa.JSON(), nullable=True),
            sa.Column('last_error_code', sa.String(length=255), nullable=True),
            sa.Column('last_error_message', sa.Text(), nullable=True),
            sa.Column('started_at', sa.DateTime(), nullable=True),
            sa.Column('completed_at', sa.DateTime(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )

    inspector = sa.inspect(conn)
    indexes = _index_names(inspector, 'desktop_automation_runs')
    if 'desktop_automation_runs' in tables:
        now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
        conn.execute(
            sa.text(
                """
                WITH ranked AS (
                    SELECT
                        id,
                        ROW_NUMBER() OVER (
                            PARTITION BY message_id, draft_id
                            ORDER BY
                                COALESCE(started_at, created_at) DESC,
                                created_at DESC,
                                id DESC
                        ) AS rn
                    FROM desktop_automation_runs
                    WHERE status IN ('queued', 'starting', 'running')
                )
                UPDATE desktop_automation_runs
                SET
                    status = 'failed',
                    stage = 'failed',
                    last_error_code = 'TASK_CONFLICT',
                    last_error_message = 'Recovered duplicate active desktop automation run before adding unique index',
                    completed_at = COALESCE(completed_at, :completed_at),
                    updated_at = :updated_at
                WHERE id IN (SELECT id FROM ranked WHERE rn > 1)
                """
            ),
            {
                'completed_at': now,
                'updated_at': now,
            },
        )

    for index_name, columns in [
        ('ix_desktop_automation_runs_bot_uuid', ['bot_uuid']),
        ('ix_desktop_automation_runs_connector_id', ['connector_id']),
        ('ix_desktop_automation_runs_conversation_id', ['conversation_id']),
        ('ix_desktop_automation_runs_message_id', ['message_id']),
        ('ix_desktop_automation_runs_draft_id', ['draft_id']),
        ('ix_desktop_automation_runs_action', ['action']),
        ('ix_desktop_automation_runs_execution_mode', ['execution_mode']),
        ('ix_desktop_automation_runs_runtime_task_id', ['runtime_task_id']),
        ('ix_desktop_automation_runs_status', ['status']),
        ('ix_desktop_automation_runs_stage', ['stage']),
        ('ix_desktop_automation_runs_request_digest', ['request_digest']),
        ('ix_desktop_automation_runs_draft_content_hash', ['draft_content_hash']),
        ('ix_desktop_automation_runs_last_error_code', ['last_error_code']),
    ]:
        if index_name not in indexes:
            op.create_index(index_name, 'desktop_automation_runs', columns)

    unique_index = 'ux_desktop_automation_runs_active'
    inspector = sa.inspect(conn)
    indexes = _index_names(inspector, 'desktop_automation_runs')
    if unique_index not in indexes:
        if conn.dialect.name == 'sqlite':
            op.create_index(
                unique_index,
                'desktop_automation_runs',
                ['message_id', 'draft_id'],
                unique=True,
                sqlite_where=sa.text("status IN ('queued', 'starting', 'running')"),
            )
        elif conn.dialect.name == 'postgresql':
            op.execute(
                sa.text(
                    "CREATE UNIQUE INDEX ux_desktop_automation_runs_active "
                    "ON desktop_automation_runs (message_id, draft_id) "
                    "WHERE status IN ('queued', 'starting', 'running')"
                )
            )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if 'desktop_automation_runs' not in _table_names(inspector):
        return

    for index_name in [
        'ux_desktop_automation_runs_active',
        'ix_desktop_automation_runs_last_error_code',
        'ix_desktop_automation_runs_draft_content_hash',
        'ix_desktop_automation_runs_request_digest',
        'ix_desktop_automation_runs_stage',
        'ix_desktop_automation_runs_status',
        'ix_desktop_automation_runs_runtime_task_id',
        'ix_desktop_automation_runs_execution_mode',
        'ix_desktop_automation_runs_action',
        'ix_desktop_automation_runs_draft_id',
        'ix_desktop_automation_runs_message_id',
        'ix_desktop_automation_runs_conversation_id',
        'ix_desktop_automation_runs_connector_id',
        'ix_desktop_automation_runs_bot_uuid',
    ]:
        try:
            op.drop_index(index_name, table_name='desktop_automation_runs')
        except Exception:
            pass
    op.drop_table('desktop_automation_runs')
