"""split broadcast draft send status from legacy draft status

Revision ID: 0019_bc_send_status
Revises: 0018_attach_relpath
Create Date: 2026-07-06
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = '0019_bc_send_status'
down_revision = '0018_attach_relpath'
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
    table_name = 'broadcast_drafts'
    if table_name not in _table_names(inspector):
        return

    columns = _column_names(inspector, table_name)
    with op.batch_alter_table(table_name) as batch_op:
        if 'send_status' not in columns:
            batch_op.add_column(sa.Column('send_status', sa.String(length=32), nullable=True))
        if 'sent_at' not in columns:
            batch_op.add_column(sa.Column('sent_at', sa.DateTime(), nullable=True))
    if 'ix_broadcast_drafts_send_status' not in _index_names(inspector, table_name):
        op.create_index('ix_broadcast_drafts_send_status', table_name, ['send_status'])

    draft_table = sa.table(
        table_name,
        sa.column('id', sa.Integer()),
        sa.column('status', sa.String()),
        sa.column('send_status', sa.String()),
    )
    rows = conn.execute(
        sa.select(
            draft_table.c.id,
            draft_table.c.status,
            draft_table.c.send_status,
        )
    ).mappings()

    for row in rows:
        if str(row.get('send_status') or '').strip():
            continue
        legacy_status = str(row.get('status') or '').strip().lower()
        mapped_send_status = None
        if legacy_status in {'sent', 'completed'}:
            mapped_send_status = 'sent'
        elif legacy_status in {'pending', 'pending_review', 'ready', 'pasted', 'failed'}:
            mapped_send_status = 'pending'
        if mapped_send_status is None:
            continue
        conn.execute(
            sa.update(draft_table)
            .where(draft_table.c.id == int(row['id']))
            .values(send_status=mapped_send_status)
        )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    table_name = 'broadcast_drafts'
    if table_name not in _table_names(inspector):
        return

    columns = _column_names(inspector, table_name)
    if {'status', 'send_status'} <= columns:
        draft_table = sa.table(
            table_name,
            sa.column('status', sa.String()),
            sa.column('send_status', sa.String()),
        )
        conn.execute(
            sa.update(draft_table)
            .where(
                draft_table.c.send_status == 'sent',
                draft_table.c.status != 'invalid',
            )
            .values(status='sent')
        )

    if 'ix_broadcast_drafts_send_status' in _index_names(inspector, table_name):
        op.drop_index('ix_broadcast_drafts_send_status', table_name=table_name)

    columns = _column_names(sa.inspect(conn), table_name)
    with op.batch_alter_table(table_name) as batch_op:
        if 'sent_at' in columns:
            batch_op.drop_column('sent_at')
        if 'send_status' in columns:
            batch_op.drop_column('send_status')
