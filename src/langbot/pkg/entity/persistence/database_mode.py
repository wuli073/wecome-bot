from __future__ import annotations

import sqlalchemy

from .base import Base


class LocalConnectorEvent(Base):
    __tablename__ = 'local_connector_events'

    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True, autoincrement=True)
    event_id = sqlalchemy.Column(sqlalchemy.String(255), nullable=False, unique=True, index=True)
    connector_id = sqlalchemy.Column(sqlalchemy.String(255), nullable=False, index=True)
    message_key = sqlalchemy.Column(sqlalchemy.String(255), nullable=False, index=True)
    status = sqlalchemy.Column(sqlalchemy.String(50), nullable=False)
    received_at = sqlalchemy.Column(sqlalchemy.DateTime, nullable=False, server_default=sqlalchemy.func.now())
    processed_at = sqlalchemy.Column(sqlalchemy.DateTime, nullable=True)
    last_error = sqlalchemy.Column(sqlalchemy.Text, nullable=True)


class DatabaseConversation(Base):
    __tablename__ = 'database_conversations'
    __table_args__ = (
        sqlalchemy.UniqueConstraint(
            'connector_id',
            'external_conversation_id',
            name='uq_database_conversations_connector_external_id',
        ),
    )

    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True, autoincrement=True)
    connector_id = sqlalchemy.Column(sqlalchemy.String(255), nullable=False, index=True)
    source = sqlalchemy.Column(sqlalchemy.String(50), nullable=False, index=True)
    external_conversation_id = sqlalchemy.Column(sqlalchemy.String(255), nullable=False, index=True)
    conversation_name = sqlalchemy.Column(sqlalchemy.String(255), nullable=False)
    conversation_type = sqlalchemy.Column(sqlalchemy.String(50), nullable=False)
    last_message_at = sqlalchemy.Column(sqlalchemy.DateTime, nullable=True, index=True)
    created_at = sqlalchemy.Column(sqlalchemy.DateTime, nullable=False, server_default=sqlalchemy.func.now())
    updated_at = sqlalchemy.Column(
        sqlalchemy.DateTime,
        nullable=False,
        server_default=sqlalchemy.func.now(),
        onupdate=sqlalchemy.func.now(),
    )


class DatabaseMessage(Base):
    __tablename__ = 'database_messages'

    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True, autoincrement=True)
    event_id = sqlalchemy.Column(sqlalchemy.String(255), nullable=False, unique=True, index=True)
    message_key = sqlalchemy.Column(sqlalchemy.String(255), nullable=False, unique=True, index=True)
    conversation_id = sqlalchemy.Column(sqlalchemy.Integer, nullable=False, index=True)
    external_message_id = sqlalchemy.Column(sqlalchemy.String(255), nullable=True, index=True)
    sender_id = sqlalchemy.Column(sqlalchemy.String(255), nullable=False, index=True)
    sender_name = sqlalchemy.Column(sqlalchemy.String(255), nullable=False)
    content = sqlalchemy.Column(sqlalchemy.Text, nullable=False)
    message_type = sqlalchemy.Column(sqlalchemy.String(50), nullable=False, index=True)
    sent_at = sqlalchemy.Column(sqlalchemy.DateTime, nullable=False, index=True)
    observed_at = sqlalchemy.Column(sqlalchemy.DateTime, nullable=False, index=True)
    status = sqlalchemy.Column(sqlalchemy.String(50), nullable=False, index=True)
    draft_text = sqlalchemy.Column(sqlalchemy.Text, nullable=True)
    draft_source = sqlalchemy.Column(sqlalchemy.String(50), nullable=True)
    attempt_count = sqlalchemy.Column(sqlalchemy.Integer, nullable=False, server_default='0', default=0)
    last_error = sqlalchemy.Column(sqlalchemy.Text, nullable=True)
    created_at = sqlalchemy.Column(sqlalchemy.DateTime, nullable=False, server_default=sqlalchemy.func.now())
    updated_at = sqlalchemy.Column(
        sqlalchemy.DateTime,
        nullable=False,
        server_default=sqlalchemy.func.now(),
        onupdate=sqlalchemy.func.now(),
    )
    processed_at = sqlalchemy.Column(sqlalchemy.DateTime, nullable=True)


class ChannelAccount(Base):
    __tablename__ = 'channel_accounts'
    __table_args__ = (
        sqlalchemy.UniqueConstraint(
            'connector_id',
            'channel_type',
            'external_account_id',
            name='uq_channel_accounts_connector_channel_external',
        ),
    )

    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True, autoincrement=True)
    connector_id = sqlalchemy.Column(sqlalchemy.String(255), nullable=False, index=True)
    channel_type = sqlalchemy.Column(sqlalchemy.String(255), nullable=False, index=True)
    external_account_id = sqlalchemy.Column(sqlalchemy.String(255), nullable=False, index=True)
    display_name = sqlalchemy.Column(sqlalchemy.String(255), nullable=False)
    enabled = sqlalchemy.Column(sqlalchemy.Boolean, nullable=False, server_default=sqlalchemy.true(), default=True)
    channel_metadata = sqlalchemy.Column('metadata', sqlalchemy.JSON, nullable=False, server_default='{}', default=dict)
    created_at = sqlalchemy.Column(sqlalchemy.DateTime, nullable=False, server_default=sqlalchemy.func.now())
    updated_at = sqlalchemy.Column(
        sqlalchemy.DateTime,
        nullable=False,
        server_default=sqlalchemy.func.now(),
        onupdate=sqlalchemy.func.now(),
    )


class BotChannelBinding(Base):
    __tablename__ = 'bot_channel_bindings'

    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True, autoincrement=True)
    bot_uuid = sqlalchemy.Column(sqlalchemy.String(255), nullable=False, index=True)
    channel_account_id = sqlalchemy.Column(sqlalchemy.Integer, nullable=False, index=True)
    enabled = sqlalchemy.Column(sqlalchemy.Boolean, nullable=False, server_default=sqlalchemy.false(), default=False)
    effective_from = sqlalchemy.Column(sqlalchemy.DateTime, nullable=True, index=True)
    auto_generate_draft = sqlalchemy.Column(
        sqlalchemy.Boolean,
        nullable=False,
        server_default=sqlalchemy.false(),
        default=False,
    )
    created_at = sqlalchemy.Column(sqlalchemy.DateTime, nullable=False, server_default=sqlalchemy.func.now())
    updated_at = sqlalchemy.Column(
        sqlalchemy.DateTime,
        nullable=False,
        server_default=sqlalchemy.func.now(),
        onupdate=sqlalchemy.func.now(),
    )


class MessageProcessingRun(Base):
    __tablename__ = 'message_processing_runs'

    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True, autoincrement=True)
    message_id = sqlalchemy.Column(sqlalchemy.Integer, nullable=False, index=True)
    bot_uuid = sqlalchemy.Column(sqlalchemy.String(255), nullable=False, index=True)
    pipeline_uuid = sqlalchemy.Column(sqlalchemy.String(255), nullable=True, index=True)
    trigger = sqlalchemy.Column(sqlalchemy.String(50), nullable=False, index=True)
    status = sqlalchemy.Column(sqlalchemy.String(50), nullable=False, index=True)
    attempt_count = sqlalchemy.Column(sqlalchemy.Integer, nullable=False, server_default='0', default=0)
    started_at = sqlalchemy.Column(sqlalchemy.DateTime, nullable=True)
    completed_at = sqlalchemy.Column(sqlalchemy.DateTime, nullable=True)
    last_error = sqlalchemy.Column(sqlalchemy.Text, nullable=True)
    created_at = sqlalchemy.Column(sqlalchemy.DateTime, nullable=False, server_default=sqlalchemy.func.now())
    updated_at = sqlalchemy.Column(
        sqlalchemy.DateTime,
        nullable=False,
        server_default=sqlalchemy.func.now(),
        onupdate=sqlalchemy.func.now(),
    )


class ReplyDraft(Base):
    __tablename__ = 'reply_drafts'

    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True, autoincrement=True)
    processing_run_id = sqlalchemy.Column(sqlalchemy.Integer, nullable=True, index=True)
    message_id = sqlalchemy.Column(sqlalchemy.Integer, nullable=False, index=True)
    bot_uuid = sqlalchemy.Column(sqlalchemy.String(255), nullable=False, index=True)
    content = sqlalchemy.Column(sqlalchemy.Text, nullable=False)
    source = sqlalchemy.Column(sqlalchemy.String(50), nullable=False, index=True)
    version = sqlalchemy.Column(sqlalchemy.Integer, nullable=False, server_default='1', default=1)
    status = sqlalchemy.Column(sqlalchemy.String(50), nullable=False, index=True)
    created_at = sqlalchemy.Column(sqlalchemy.DateTime, nullable=False, server_default=sqlalchemy.func.now())
    updated_at = sqlalchemy.Column(
        sqlalchemy.DateTime,
        nullable=False,
        server_default=sqlalchemy.func.now(),
        onupdate=sqlalchemy.func.now(),
    )
