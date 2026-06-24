"""add builtin local connector metadata to mcp_servers

Revision ID: 0007_builtin_local_connectors
Revises: 0006_normalize_mcp_remote_mode
Create Date: 2026-06-23
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = '0007_builtin_local_connectors'
down_revision = '0006_normalize_mcp_remote_mode'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if 'mcp_servers' not in inspector.get_table_names():
        return

    columns = {col['name'] for col in inspector.get_columns('mcp_servers')}
    if 'builtin' not in columns:
        op.add_column('mcp_servers', sa.Column('builtin', sa.Boolean(), nullable=False, server_default=sa.false()))
    if 'locked' not in columns:
        op.add_column('mcp_servers', sa.Column('locked', sa.Boolean(), nullable=False, server_default=sa.false()))
    if 'managed_by' not in columns:
        op.add_column('mcp_servers', sa.Column('managed_by', sa.String(length=255), nullable=True))
    if 'connector_id' not in columns:
        op.add_column('mcp_servers', sa.Column('connector_id', sa.String(length=255), nullable=True))

    indexes = {index['name'] for index in inspector.get_indexes('mcp_servers')}
    if 'ix_mcp_servers_connector_id' not in indexes:
        op.create_index('ix_mcp_servers_connector_id', 'mcp_servers', ['connector_id'], unique=True)


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if 'mcp_servers' not in inspector.get_table_names():
        return

    indexes = {index['name'] for index in inspector.get_indexes('mcp_servers')}
    if 'ix_mcp_servers_connector_id' in indexes:
        op.drop_index('ix_mcp_servers_connector_id', table_name='mcp_servers')

    columns = {col['name'] for col in inspector.get_columns('mcp_servers')}
    for column in ['connector_id', 'managed_by', 'locked', 'builtin']:
        if column in columns:
            op.drop_column('mcp_servers', column)
