"""add broadcast attachment tables

Revision ID: 0017_broadcast_attach
Revises: 0016_broadcast_group_sync
Create Date: 2026-07-05
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = '0017_broadcast_attach'
down_revision = '0016_broadcast_group_sync'
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
    tables = _table_names(inspector)

    draft_columns = _column_names(inspector, 'broadcast_drafts')
    with op.batch_alter_table('broadcast_drafts') as batch_op:
        if 'attachments_stale' not in draft_columns:
            batch_op.add_column(
                sa.Column(
                    'attachments_stale',
                    sa.Boolean(),
                    nullable=False,
                    server_default=sa.false(),
                )
            )

    if 'broadcast_attachment_assets' not in tables:
        op.create_table(
            'broadcast_attachment_assets',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('bot_uuid', sa.String(length=255), nullable=False),
            sa.Column('connector_id', sa.String(length=255), nullable=False),
            sa.Column('original_name', sa.String(length=255), nullable=False),
            sa.Column('stored_name', sa.String(length=255), nullable=False),
            sa.Column('stored_path', sa.Text(), nullable=False),
            sa.Column('relative_path', sa.Text(), nullable=True),
            sa.Column('size_bytes', sa.BigInteger(), nullable=False),
            sa.Column('sha256', sa.String(length=64), nullable=False),
            sa.Column('extension', sa.String(length=32), nullable=False),
            sa.Column('mime_type', sa.String(length=255), nullable=False),
            sa.Column('status', sa.String(length=32), nullable=False, server_default='ready'),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint(
                'sha256',
                'size_bytes',
                'stored_name',
                name='uq_broadcast_attachment_assets_storage',
            ),
        )
    else:
        attachment_columns = _column_names(inspector, 'broadcast_attachment_assets')
        if 'relative_path' not in attachment_columns:
            with op.batch_alter_table('broadcast_attachment_assets') as batch_op:
                batch_op.add_column(sa.Column('relative_path', sa.Text(), nullable=True))
            conn.exec_driver_sql(
                """
                UPDATE broadcast_attachment_assets
                SET relative_path = REPLACE(
                    SUBSTR(stored_path, INSTR(stored_path, 'broadcast_attachments') + LENGTH('broadcast_attachments') + 2),
                    '\\',
                    '/'
                )
                WHERE relative_path IS NULL
                  AND stored_path IS NOT NULL
                  AND INSTR(stored_path, 'broadcast_attachments') > 0
                """
            )

    if 'broadcast_import_group_attachments' not in tables:
        op.create_table(
            'broadcast_import_group_attachments',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('batch_id', sa.Integer(), nullable=False),
            sa.Column('group_key', sa.String(length=128), nullable=False),
            sa.Column('group_value_snapshot', sa.String(length=255), nullable=True),
            sa.Column('attachment_asset_id', sa.Integer(), nullable=False),
            sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.ForeignKeyConstraint(['batch_id'], ['broadcast_import_batches.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(
                ['attachment_asset_id'],
                ['broadcast_attachment_assets.id'],
                ondelete='CASCADE',
            ),
            sa.UniqueConstraint(
                'batch_id',
                'group_key',
                'attachment_asset_id',
                name='uq_broadcast_import_group_attachments_group_asset',
            ),
        )

    if 'broadcast_draft_attachments' not in tables:
        op.create_table(
            'broadcast_draft_attachments',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('draft_id', sa.Integer(), nullable=False),
            sa.Column('attachment_asset_id', sa.Integer(), nullable=False),
            sa.Column('original_name_snapshot', sa.String(length=255), nullable=False),
            sa.Column('size_bytes_snapshot', sa.BigInteger(), nullable=False),
            sa.Column('sha256_snapshot', sa.String(length=64), nullable=False),
            sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.ForeignKeyConstraint(['draft_id'], ['broadcast_drafts.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(
                ['attachment_asset_id'],
                ['broadcast_attachment_assets.id'],
                ondelete='CASCADE',
            ),
            sa.UniqueConstraint(
                'draft_id',
                'attachment_asset_id',
                name='uq_broadcast_draft_attachments_draft_asset',
            ),
        )

    if 'broadcast_execution_task_attachments' not in tables:
        op.create_table(
            'broadcast_execution_task_attachments',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('execution_task_id', sa.Integer(), nullable=False),
            sa.Column('attachment_asset_id', sa.Integer(), nullable=False),
            sa.Column('original_name_snapshot', sa.String(length=255), nullable=False),
            sa.Column('size_bytes_snapshot', sa.BigInteger(), nullable=False),
            sa.Column('sha256_snapshot', sa.String(length=64), nullable=False),
            sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.ForeignKeyConstraint(
                ['execution_task_id'],
                ['broadcast_execution_tasks.id'],
                ondelete='CASCADE',
            ),
            sa.ForeignKeyConstraint(
                ['attachment_asset_id'],
                ['broadcast_attachment_assets.id'],
                ondelete='CASCADE',
            ),
            sa.UniqueConstraint(
                'execution_task_id',
                'attachment_asset_id',
                name='uq_broadcast_execution_task_attachments_task_asset',
            ),
        )

    inspector = sa.inspect(conn)
    index_specs = [
        ('broadcast_attachment_assets', 'ix_broadcast_attachment_assets_bot_uuid', ['bot_uuid']),
        ('broadcast_attachment_assets', 'ix_broadcast_attachment_assets_connector_id', ['connector_id']),
        ('broadcast_attachment_assets', 'ix_broadcast_attachment_assets_scope', ['bot_uuid', 'connector_id']),
        ('broadcast_attachment_assets', 'ix_broadcast_attachment_assets_sha256', ['sha256']),
        ('broadcast_import_group_attachments', 'ix_broadcast_import_group_attachments_batch_id', ['batch_id']),
        (
            'broadcast_import_group_attachments',
            'ix_broadcast_import_group_attachments_batch_group',
            ['batch_id', 'group_key', 'sort_order'],
        ),
        ('broadcast_import_group_attachments', 'ix_broadcast_import_group_attachments_group_key', ['group_key']),
        (
            'broadcast_import_group_attachments',
            'ix_broadcast_import_group_attachments_attachment_asset_id',
            ['attachment_asset_id'],
        ),
        ('broadcast_draft_attachments', 'ix_broadcast_draft_attachments_draft_id', ['draft_id']),
        ('broadcast_draft_attachments', 'ix_broadcast_draft_attachments_attachment_asset_id', ['attachment_asset_id']),
        ('broadcast_draft_attachments', 'ix_broadcast_draft_attachments_draft', ['draft_id', 'sort_order']),
        (
            'broadcast_execution_task_attachments',
            'ix_broadcast_execution_task_attachments_execution_task_id',
            ['execution_task_id'],
        ),
        (
            'broadcast_execution_task_attachments',
            'ix_broadcast_execution_task_attachments_attachment_asset_id',
            ['attachment_asset_id'],
        ),
        (
            'broadcast_execution_task_attachments',
            'ix_broadcast_execution_task_attachments_task',
            ['execution_task_id', 'sort_order'],
        ),
    ]
    for table_name, index_name, columns in index_specs:
        if index_name not in _index_names(inspector, table_name):
            op.create_index(index_name, table_name, columns)


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = _table_names(inspector)

    drop_specs = {
        'broadcast_execution_task_attachments': [
            'ix_broadcast_execution_task_attachments_task',
            'ix_broadcast_execution_task_attachments_attachment_asset_id',
            'ix_broadcast_execution_task_attachments_execution_task_id',
        ],
        'broadcast_draft_attachments': [
            'ix_broadcast_draft_attachments_draft',
            'ix_broadcast_draft_attachments_attachment_asset_id',
            'ix_broadcast_draft_attachments_draft_id',
        ],
        'broadcast_import_group_attachments': [
            'ix_broadcast_import_group_attachments_attachment_asset_id',
            'ix_broadcast_import_group_attachments_group_key',
            'ix_broadcast_import_group_attachments_batch_group',
            'ix_broadcast_import_group_attachments_batch_id',
        ],
        'broadcast_attachment_assets': [
            'ix_broadcast_attachment_assets_sha256',
            'ix_broadcast_attachment_assets_scope',
            'ix_broadcast_attachment_assets_connector_id',
            'ix_broadcast_attachment_assets_bot_uuid',
        ],
    }

    for table_name, index_names in drop_specs.items():
        if table_name not in tables:
            continue
        for index_name in index_names:
            if index_name in _index_names(inspector, table_name):
                op.drop_index(index_name, table_name=table_name)

    for table_name in [
        'broadcast_execution_task_attachments',
        'broadcast_draft_attachments',
        'broadcast_import_group_attachments',
        'broadcast_attachment_assets',
    ]:
        if table_name in tables:
            op.drop_table(table_name)

    draft_columns = _column_names(sa.inspect(conn), 'broadcast_drafts')
    if 'attachments_stale' in draft_columns:
        with op.batch_alter_table('broadcast_drafts') as batch_op:
            batch_op.drop_column('attachments_stale')
