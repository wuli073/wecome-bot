"""enforce unique bot/channel binding pairs

Revision ID: 0010_bot_channel_bindings_uniq
Revises: 0009_channel_bot_processing
Create Date: 2026-06-25
"""

from __future__ import annotations

from collections import defaultdict
import datetime

import sqlalchemy as sa
from alembic import op

revision = '0010_bot_channel_bindings_uniq'
down_revision = '0009_channel_bot_processing'
branch_labels = None
depends_on = None


UNIQUE_INDEX_NAME = 'ux_bot_channel_bindings_bot_channel'


def _table_names(inspector) -> set[str]:
    return set(inspector.get_table_names())


def _index_names(inspector, table_name: str) -> dict[str, dict]:
    if table_name not in _table_names(inspector):
        return {}
    return {index['name']: index for index in inspector.get_indexes(table_name)}


def _reflect_table(conn, table_name: str) -> sa.Table:
    metadata = sa.MetaData()
    return sa.Table(table_name, metadata, autoload_with=conn)


def _as_bool(value: object) -> bool:
    return bool(value)


def _auto_generate_draft_from_bot(adapter_config: object) -> bool | None:
    if isinstance(adapter_config, dict) and 'auto_generate_draft' in adapter_config:
        return _as_bool(adapter_config.get('auto_generate_draft'))
    return None


def _rank_binding(row: dict, desired_auto_generate_draft: bool | None) -> tuple:
    enabled_rank = 1 if _as_bool(row.get('enabled')) else 0
    effective_from = row.get('effective_from') or datetime.datetime.min
    updated_at = row.get('updated_at') or datetime.datetime.min
    auto_match_rank = 0
    if desired_auto_generate_draft is not None:
        auto_match_rank = 1 if _as_bool(row.get('auto_generate_draft')) == desired_auto_generate_draft else 0
    return enabled_rank, effective_from, updated_at, auto_match_rank, row.get('id', 0)


def _cleanup_duplicate_bindings(conn) -> None:
    binding_table = _reflect_table(conn, 'bot_channel_bindings')
    inspector = sa.inspect(conn)
    tables = _table_names(inspector)

    bot_auto_draft_map: dict[str, bool | None] = {}
    if 'bots' in tables:
        bot_table = _reflect_table(conn, 'bots')
        bot_rows = conn.execute(sa.select(bot_table.c.uuid, bot_table.c.adapter_config)).mappings().all()
        for row in bot_rows:
            bot_auto_draft_map[str(row['uuid'])] = _auto_generate_draft_from_bot(row.get('adapter_config'))

    binding_rows = conn.execute(
        sa.select(binding_table).order_by(
            binding_table.c.bot_uuid.asc(),
            binding_table.c.channel_account_id.asc(),
            binding_table.c.id.asc(),
        )
    ).mappings().all()

    grouped_rows: dict[tuple[str, int], list[dict]] = defaultdict(list)
    for row in binding_rows:
        grouped_rows[(str(row['bot_uuid']), int(row['channel_account_id']))].append(dict(row))

    rows_to_delete: list[int] = []
    rows_to_update: list[tuple[int, bool]] = []

    for (bot_uuid, _channel_account_id), rows in grouped_rows.items():
        desired_auto_generate_draft = bot_auto_draft_map.get(bot_uuid)
        winner = max(rows, key=lambda row: _rank_binding(row, desired_auto_generate_draft))

        if desired_auto_generate_draft is not None and _as_bool(winner.get('auto_generate_draft')) != desired_auto_generate_draft:
            rows_to_update.append((int(winner['id']), desired_auto_generate_draft))

        for row in rows:
            if int(row['id']) != int(winner['id']):
                rows_to_delete.append(int(row['id']))

    for row_id, auto_generate_draft in rows_to_update:
        conn.execute(
            binding_table.update()
            .where(binding_table.c.id == row_id)
            .values({'auto_generate_draft': auto_generate_draft})
        )

    if rows_to_delete:
        conn.execute(binding_table.delete().where(binding_table.c.id.in_(rows_to_delete)))


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = _table_names(inspector)
    if 'bot_channel_bindings' not in tables:
        return

    _cleanup_duplicate_bindings(conn)

    inspector = sa.inspect(conn)
    indexes = _index_names(inspector, 'bot_channel_bindings')
    if UNIQUE_INDEX_NAME not in indexes:
        op.create_index(
            UNIQUE_INDEX_NAME,
            'bot_channel_bindings',
            ['bot_uuid', 'channel_account_id'],
            unique=True,
        )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if 'bot_channel_bindings' not in _table_names(inspector):
        return

    indexes = _index_names(inspector, 'bot_channel_bindings')
    if UNIQUE_INDEX_NAME in indexes:
        op.drop_index(UNIQUE_INDEX_NAME, table_name='bot_channel_bindings')
