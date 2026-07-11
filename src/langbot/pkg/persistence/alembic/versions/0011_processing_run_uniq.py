"""enforce unique active processing run per message and bot

Revision ID: 0011_processing_run_uniq
Revises: 0010_bot_channel_bindings_uniq
Create Date: 2026-06-27
"""

from __future__ import annotations

import datetime

import sqlalchemy as sa
from alembic import op

revision = '0011_processing_run_uniq'
down_revision = '0010_bot_channel_bindings_uniq'
branch_labels = None
depends_on = None


UNIQUE_INDEX_NAME = 'ux_message_processing_runs_active'
DUPLICATE_RECOVERY_ERROR = 'Recovered duplicate processing run before adding unique index'


def _table_names(inspector) -> set[str]:
    return set(inspector.get_table_names())


def _index_names(inspector, table_name: str) -> dict[str, dict]:
    if table_name not in _table_names(inspector):
        return {}
    return {index['name']: index for index in inspector.get_indexes(table_name)}


def _reflect_table(conn, table_name: str) -> sa.Table:
    metadata = sa.MetaData()
    return sa.Table(table_name, metadata, autoload_with=conn)


def _cleanup_duplicate_processing_runs(conn) -> None:
    inspector = sa.inspect(conn)
    tables = _table_names(inspector)
    if 'message_processing_runs' not in tables:
        return

    run_table = _reflect_table(conn, 'message_processing_runs')
    grouped_rows: dict[tuple[int, str], list[dict]] = {}
    run_rows = conn.execute(
        sa.select(run_table).where(
            run_table.c.status == 'processing',
            run_table.c.completed_at.is_(None),
        ).order_by(
            run_table.c.message_id.asc(),
            run_table.c.bot_uuid.asc(),
            run_table.c.id.asc(),
        )
    ).mappings().all()

    for row in run_rows:
        key = (int(row['message_id']), str(row['bot_uuid']))
        grouped_rows.setdefault(key, []).append(dict(row))

    now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
    for _key, rows in grouped_rows.items():
        if len(rows) <= 1:
            continue
        winner = max(rows, key=lambda row: (row.get('started_at') or datetime.datetime.min, row.get('id', 0)))
        for row in rows:
            if int(row['id']) == int(winner['id']):
                continue
            conn.execute(
                run_table.update()
                .where(run_table.c.id == int(row['id']))
                .values(
                    {
                        'status': 'failed',
                        'completed_at': now,
                        'last_error': DUPLICATE_RECOVERY_ERROR,
                        'updated_at': now,
                    }
                )
            )


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if 'message_processing_runs' not in _table_names(inspector):
        return

    _cleanup_duplicate_processing_runs(conn)

    inspector = sa.inspect(conn)
    indexes = _index_names(inspector, 'message_processing_runs')
    if UNIQUE_INDEX_NAME not in indexes:
        if conn.dialect.name == 'sqlite':
            op.create_index(
                UNIQUE_INDEX_NAME,
                'message_processing_runs',
                ['message_id', 'bot_uuid'],
                unique=True,
                sqlite_where=sa.text("status = 'processing' AND completed_at IS NULL"),
            )
        elif conn.dialect.name == 'postgresql':
            op.execute(
                sa.text(
                    "CREATE UNIQUE INDEX ux_message_processing_runs_active "
                    "ON message_processing_runs (message_id, bot_uuid) "
                    "WHERE status = 'processing' AND completed_at IS NULL"
                )
            )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if 'message_processing_runs' not in _table_names(inspector):
        return

    indexes = _index_names(inspector, 'message_processing_runs')
    if UNIQUE_INDEX_NAME in indexes:
        op.drop_index(UNIQUE_INDEX_NAME, table_name='message_processing_runs')
