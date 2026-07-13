"""repair broadcast attachment relative_path for already-applied 0017 databases

Revision ID: 0018_attach_relpath
Revises: 0017_broadcast_attach
Create Date: 2026-07-06
"""

from __future__ import annotations

import os
from pathlib import Path

import sqlalchemy as sa
from alembic import op

revision = '0018_attach_relpath'
down_revision = '0017_broadcast_attach'
branch_labels = None
depends_on = None


def _table_names(inspector) -> set[str]:
    return set(inspector.get_table_names())


def _column_names(inspector, table_name: str) -> set[str]:
    if table_name not in _table_names(inspector):
        return set()
    return {column['name'] for column in inspector.get_columns(table_name)}


def _attachments_root() -> Path:
    return Path(__file__).resolve().parents[6] / 'runtime' / 'broadcast_attachments'


def _to_relative_path(stored_path: str | None, *, root: Path) -> str | None:
    path_text = str(stored_path or '').strip()
    if not path_text:
        return None
    try:
        canonical_root = Path(os.path.realpath(str(root)))
        canonical_target = Path(os.path.realpath(path_text))
    except (OSError, ValueError):
        return None
    if not canonical_target.exists() or not canonical_target.is_file():
        return None
    try:
        relative = os.path.relpath(str(canonical_target), str(canonical_root))
    except ValueError:
        return None
    if relative.startswith('..') or os.path.isabs(relative):
        return None
    return Path(relative).as_posix().strip() or None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    table_name = 'broadcast_attachment_assets'
    if table_name not in _table_names(inspector):
        return

    columns = _column_names(inspector, table_name)
    if 'relative_path' not in columns:
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.add_column(sa.Column('relative_path', sa.Text(), nullable=True))

    asset_table = sa.table(
        table_name,
        sa.column('id', sa.Integer()),
        sa.column('stored_path', sa.Text()),
        sa.column('relative_path', sa.Text()),
    )
    root = _attachments_root()
    rows = conn.execute(
        sa.select(
            asset_table.c.id,
            asset_table.c.stored_path,
            asset_table.c.relative_path,
        )
    ).mappings()

    for row in rows:
        if str(row.get('relative_path') or '').strip():
            continue
        relative_path = _to_relative_path(row.get('stored_path'), root=root)
        if relative_path is None:
            continue
        conn.execute(
            sa.update(asset_table)
            .where(asset_table.c.id == int(row['id']))
            .values(relative_path=relative_path)
        )


def downgrade() -> None:
    pass
