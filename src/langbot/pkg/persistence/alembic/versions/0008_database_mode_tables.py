"""add database mode tables

Revision ID: 0008_database_mode_tables
Revises: 0007_builtin_local_connectors
Create Date: 2026-06-23
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = '0008_database_mode_tables'
down_revision = '0007_builtin_local_connectors'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = set(inspector.get_table_names())

    if 'local_connector_events' not in tables:
        op.create_table(
            'local_connector_events',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('event_id', sa.String(length=255), nullable=False),
            sa.Column('connector_id', sa.String(length=255), nullable=False),
            sa.Column('message_key', sa.String(length=255), nullable=False),
            sa.Column('status', sa.String(length=50), nullable=False),
            sa.Column('received_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column('processed_at', sa.DateTime(), nullable=True),
            sa.Column('last_error', sa.Text(), nullable=True),
            sa.UniqueConstraint('event_id', name='uq_local_connector_events_event_id'),
        )
        op.create_index('ix_local_connector_events_event_id', 'local_connector_events', ['event_id'], unique=True)
        op.create_index('ix_local_connector_events_connector_id', 'local_connector_events', ['connector_id'])
        op.create_index('ix_local_connector_events_message_key', 'local_connector_events', ['message_key'])

    if 'database_conversations' not in tables:
        op.create_table(
            'database_conversations',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('connector_id', sa.String(length=255), nullable=False),
            sa.Column('source', sa.String(length=50), nullable=False),
            sa.Column('external_conversation_id', sa.String(length=255), nullable=False),
            sa.Column('conversation_name', sa.String(length=255), nullable=False),
            sa.Column('conversation_type', sa.String(length=50), nullable=False),
            sa.Column('last_message_at', sa.DateTime(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint(
                'connector_id',
                'external_conversation_id',
                name='uq_database_conversations_connector_external_id',
            ),
        )
        op.create_index('ix_database_conversations_connector_id', 'database_conversations', ['connector_id'])
        op.create_index('ix_database_conversations_source', 'database_conversations', ['source'])
        op.create_index(
            'ix_database_conversations_external_conversation_id',
            'database_conversations',
            ['external_conversation_id'],
        )
        op.create_index('ix_database_conversations_last_message_at', 'database_conversations', ['last_message_at'])

    if 'database_messages' not in tables:
        op.create_table(
            'database_messages',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('event_id', sa.String(length=255), nullable=False),
            sa.Column('message_key', sa.String(length=255), nullable=False),
            sa.Column('conversation_id', sa.Integer(), nullable=False),
            sa.Column('external_message_id', sa.String(length=255), nullable=True),
            sa.Column('sender_id', sa.String(length=255), nullable=False),
            sa.Column('sender_name', sa.String(length=255), nullable=False),
            sa.Column('content', sa.Text(), nullable=False),
            sa.Column('message_type', sa.String(length=50), nullable=False),
            sa.Column('sent_at', sa.DateTime(), nullable=False),
            sa.Column('observed_at', sa.DateTime(), nullable=False),
            sa.Column('status', sa.String(length=50), nullable=False),
            sa.Column('draft_text', sa.Text(), nullable=True),
            sa.Column('draft_source', sa.String(length=50), nullable=True),
            sa.Column('attempt_count', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('last_error', sa.Text(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column('processed_at', sa.DateTime(), nullable=True),
            sa.UniqueConstraint('event_id', name='uq_database_messages_event_id'),
            sa.UniqueConstraint('message_key', name='uq_database_messages_message_key'),
        )
        op.create_index('ix_database_messages_event_id', 'database_messages', ['event_id'], unique=True)
        op.create_index('ix_database_messages_message_key', 'database_messages', ['message_key'], unique=True)
        op.create_index('ix_database_messages_conversation_id', 'database_messages', ['conversation_id'])
        op.create_index('ix_database_messages_external_message_id', 'database_messages', ['external_message_id'])
        op.create_index('ix_database_messages_sender_id', 'database_messages', ['sender_id'])
        op.create_index('ix_database_messages_message_type', 'database_messages', ['message_type'])
        op.create_index('ix_database_messages_sent_at', 'database_messages', ['sent_at'])
        op.create_index('ix_database_messages_observed_at', 'database_messages', ['observed_at'])
        op.create_index('ix_database_messages_status', 'database_messages', ['status'])


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = set(inspector.get_table_names())

    if 'database_messages' in tables:
        for index_name in [
            'ix_database_messages_status',
            'ix_database_messages_observed_at',
            'ix_database_messages_sent_at',
            'ix_database_messages_message_type',
            'ix_database_messages_sender_id',
            'ix_database_messages_external_message_id',
            'ix_database_messages_conversation_id',
            'ix_database_messages_message_key',
            'ix_database_messages_event_id',
        ]:
            try:
                op.drop_index(index_name, table_name='database_messages')
            except Exception:
                pass
        op.drop_table('database_messages')

    if 'database_conversations' in tables:
        for index_name in [
            'ix_database_conversations_last_message_at',
            'ix_database_conversations_external_conversation_id',
            'ix_database_conversations_source',
            'ix_database_conversations_connector_id',
        ]:
            try:
                op.drop_index(index_name, table_name='database_conversations')
            except Exception:
                pass
        op.drop_table('database_conversations')

    if 'local_connector_events' in tables:
        for index_name in [
            'ix_local_connector_events_message_key',
            'ix_local_connector_events_connector_id',
            'ix_local_connector_events_event_id',
        ]:
            try:
                op.drop_index(index_name, table_name='local_connector_events')
            except Exception:
                pass
        op.drop_table('local_connector_events')
