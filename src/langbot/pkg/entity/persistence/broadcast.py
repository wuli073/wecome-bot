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


class BroadcastImportBatch(Base):
    __tablename__ = 'broadcast_import_batches'
    __table_args__ = (
        sqlalchemy.Index('ix_broadcast_import_batches_scope', 'bot_uuid', 'connector_id'),
    )

    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True, autoincrement=True)
    bot_uuid = sqlalchemy.Column(sqlalchemy.String(255), nullable=False, index=True)
    connector_id = sqlalchemy.Column(sqlalchemy.String(255), nullable=False, index=True)
    original_file_name = sqlalchemy.Column(sqlalchemy.String(255), nullable=False)
    file_type = sqlalchemy.Column(sqlalchemy.String(32), nullable=False)
    worksheet_name = sqlalchemy.Column(sqlalchemy.String(255), nullable=True)
    status = sqlalchemy.Column(sqlalchemy.String(32), nullable=False)
    drafts_stale = sqlalchemy.Column(
        sqlalchemy.Boolean,
        nullable=False,
        server_default=sqlalchemy.false(),
        default=False,
    )
    total_rows = sqlalchemy.Column(sqlalchemy.Integer, nullable=False, server_default='0', default=0)
    valid_rows = sqlalchemy.Column(sqlalchemy.Integer, nullable=False, server_default='0', default=0)
    invalid_rows = sqlalchemy.Column(sqlalchemy.Integer, nullable=False, server_default='0', default=0)
    matched_rows = sqlalchemy.Column(sqlalchemy.Integer, nullable=False, server_default='0', default=0)
    unmatched_rows = sqlalchemy.Column(sqlalchemy.Integer, nullable=False, server_default='0', default=0)
    created_at = sqlalchemy.Column(sqlalchemy.DateTime, nullable=False, server_default=sqlalchemy.func.now(), index=True)
    updated_at = sqlalchemy.Column(
        sqlalchemy.DateTime,
        nullable=False,
        server_default=sqlalchemy.func.now(),
        onupdate=sqlalchemy.func.now(),
    )


class BroadcastImportRow(Base):
    __tablename__ = 'broadcast_import_rows'
    __table_args__ = (
        sqlalchemy.UniqueConstraint(
            'import_batch_id',
            'source_row_number',
            name='uq_broadcast_import_rows_batch_row_number',
        ),
    )

    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True, autoincrement=True)
    import_batch_id = sqlalchemy.Column(
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey('broadcast_import_batches.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    source_row_number = sqlalchemy.Column(sqlalchemy.Integer, nullable=False)
    raw_data = sqlalchemy.Column(sqlalchemy.JSON, nullable=False)
    group_value = sqlalchemy.Column(sqlalchemy.String(255), nullable=True, index=True)
    matched_conversation_name = sqlalchemy.Column(sqlalchemy.String(255), nullable=True)
    matched_rule_id = sqlalchemy.Column(
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey('broadcast_group_rules.id', ondelete='SET NULL'),
        nullable=True,
    )
    match_status = sqlalchemy.Column(sqlalchemy.String(32), nullable=False, index=True)
    error_message = sqlalchemy.Column(sqlalchemy.Text, nullable=True)
    created_at = sqlalchemy.Column(sqlalchemy.DateTime, nullable=False, server_default=sqlalchemy.func.now())


class BroadcastDraft(Base):
    __tablename__ = 'broadcast_drafts'
    __table_args__ = (
        sqlalchemy.UniqueConstraint(
            'import_batch_id',
            'group_value',
            name='uq_broadcast_drafts_batch_group_value',
        ),
        sqlalchemy.Index('ix_broadcast_drafts_scope', 'bot_uuid', 'connector_id'),
    )

    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True, autoincrement=True)
    bot_uuid = sqlalchemy.Column(sqlalchemy.String(255), nullable=False, index=True)
    connector_id = sqlalchemy.Column(sqlalchemy.String(255), nullable=False, index=True)
    import_batch_id = sqlalchemy.Column(
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey('broadcast_import_batches.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    group_value = sqlalchemy.Column(sqlalchemy.String(255), nullable=False)
    target_conversation_name = sqlalchemy.Column(sqlalchemy.String(255), nullable=True)
    template_id = sqlalchemy.Column(
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey('broadcast_templates.id', ondelete='SET NULL'),
        nullable=True,
    )
    template_name_snapshot = sqlalchemy.Column(sqlalchemy.String(255), nullable=False)
    template_content_snapshot = sqlalchemy.Column(sqlalchemy.Text, nullable=False)
    render_variables = sqlalchemy.Column(sqlalchemy.JSON, nullable=False)
    draft_text = sqlalchemy.Column(sqlalchemy.Text, nullable=False)
    status = sqlalchemy.Column(sqlalchemy.String(32), nullable=False, index=True)
    error_message = sqlalchemy.Column(sqlalchemy.Text, nullable=True)
    created_at = sqlalchemy.Column(sqlalchemy.DateTime, nullable=False, server_default=sqlalchemy.func.now())
    updated_at = sqlalchemy.Column(
        sqlalchemy.DateTime,
        nullable=False,
        server_default=sqlalchemy.func.now(),
        onupdate=sqlalchemy.func.now(),
        index=True,
    )
