from __future__ import annotations

import sqlalchemy

from .base import Base


class BroadcastTemplate(Base):
    __tablename__ = 'broadcast_templates'
    __table_args__ = (
        sqlalchemy.UniqueConstraint(
            'bot_uuid',
            'connector_id',
            'name',
            name='uq_broadcast_templates_scope_name',
        ),
    )

    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True, autoincrement=True)
    bot_uuid = sqlalchemy.Column(sqlalchemy.String(255), nullable=False, index=True)
    connector_id = sqlalchemy.Column(sqlalchemy.String(255), nullable=False, index=True)
    name = sqlalchemy.Column(sqlalchemy.String(255), nullable=False, index=True)
    content = sqlalchemy.Column(sqlalchemy.Text, nullable=False)
    variables = sqlalchemy.Column(sqlalchemy.JSON, nullable=False, server_default='[]', default=list)
    enabled = sqlalchemy.Column(sqlalchemy.Boolean, nullable=False, server_default=sqlalchemy.true(), default=True)
    created_at = sqlalchemy.Column(sqlalchemy.DateTime, nullable=False, server_default=sqlalchemy.func.now())
    updated_at = sqlalchemy.Column(
        sqlalchemy.DateTime,
        nullable=False,
        server_default=sqlalchemy.func.now(),
        onupdate=sqlalchemy.func.now(),
    )


class BroadcastVariableProfile(Base):
    __tablename__ = 'broadcast_variable_profiles'
    __table_args__ = (
        sqlalchemy.UniqueConstraint(
            'bot_uuid',
            'connector_id',
            name='uq_broadcast_variable_profiles_scope',
        ),
    )

    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True, autoincrement=True)
    bot_uuid = sqlalchemy.Column(sqlalchemy.String(255), nullable=False, index=True)
    connector_id = sqlalchemy.Column(sqlalchemy.String(255), nullable=False, index=True)
    group_field = sqlalchemy.Column(sqlalchemy.String(255), nullable=True)
    mapping_rules = sqlalchemy.Column(sqlalchemy.JSON, nullable=False, server_default='[]', default=list)
    created_at = sqlalchemy.Column(sqlalchemy.DateTime, nullable=False, server_default=sqlalchemy.func.now())
    updated_at = sqlalchemy.Column(
        sqlalchemy.DateTime,
        nullable=False,
        server_default=sqlalchemy.func.now(),
        onupdate=sqlalchemy.func.now(),
    )


class BroadcastGroupRule(Base):
    __tablename__ = 'broadcast_group_rules'
    __table_args__ = (
        sqlalchemy.UniqueConstraint(
            'bot_uuid',
            'connector_id',
            'source_value',
            'match_type',
            'match_expression',
            'target_conversation_name',
            name='uq_broadcast_group_rules_scope_rule',
        ),
    )

    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True, autoincrement=True)
    bot_uuid = sqlalchemy.Column(sqlalchemy.String(255), nullable=False, index=True)
    connector_id = sqlalchemy.Column(sqlalchemy.String(255), nullable=False, index=True)
    source_value = sqlalchemy.Column(sqlalchemy.String(255), nullable=False, index=True)
    match_type = sqlalchemy.Column(sqlalchemy.String(50), nullable=False, index=True)
    match_expression = sqlalchemy.Column(sqlalchemy.String(1024), nullable=False)
    target_conversation_name = sqlalchemy.Column(sqlalchemy.String(255), nullable=False)
    priority = sqlalchemy.Column(sqlalchemy.Integer, nullable=False, index=True, server_default='0', default=0)
    enabled = sqlalchemy.Column(sqlalchemy.Boolean, nullable=False, server_default=sqlalchemy.true(), default=True)
    created_at = sqlalchemy.Column(sqlalchemy.DateTime, nullable=False, server_default=sqlalchemy.func.now())
    updated_at = sqlalchemy.Column(
        sqlalchemy.DateTime,
        nullable=False,
        server_default=sqlalchemy.func.now(),
        onupdate=sqlalchemy.func.now(),
    )


class BroadcastGroupName(Base):
    __tablename__ = 'broadcast_group_names'
    __table_args__ = (
        sqlalchemy.UniqueConstraint(
            'bot_uuid',
            'connector_id',
            'name',
            name='uq_broadcast_group_names_scope_name',
        ),
    )

    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True, autoincrement=True)
    bot_uuid = sqlalchemy.Column(sqlalchemy.String(255), nullable=False, index=True)
    connector_id = sqlalchemy.Column(sqlalchemy.String(255), nullable=False, index=True)
    name = sqlalchemy.Column(sqlalchemy.String(255), nullable=False, index=True)
    created_at = sqlalchemy.Column(sqlalchemy.DateTime, nullable=False, server_default=sqlalchemy.func.now())
    updated_at = sqlalchemy.Column(
        sqlalchemy.DateTime,
        nullable=False,
        server_default=sqlalchemy.func.now(),
        onupdate=sqlalchemy.func.now(),
    )
