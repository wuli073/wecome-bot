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
        sqlalchemy.UniqueConstraint(
            'bot_uuid',
            'connector_id',
            'external_conversation_id',
            name='uq_broadcast_group_names_scope_external_id',
        ),
    )

    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True, autoincrement=True)
    bot_uuid = sqlalchemy.Column(sqlalchemy.String(255), nullable=False, index=True)
    connector_id = sqlalchemy.Column(sqlalchemy.String(255), nullable=False, index=True)
    name = sqlalchemy.Column(sqlalchemy.String(255), nullable=False, index=True)
    external_conversation_id = sqlalchemy.Column(sqlalchemy.String(255), nullable=True, index=True)
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
    send_status = sqlalchemy.Column(sqlalchemy.String(32), nullable=True, index=True)
    sent_at = sqlalchemy.Column(sqlalchemy.DateTime, nullable=True)
    error_message = sqlalchemy.Column(sqlalchemy.Text, nullable=True)
    attachments_stale = sqlalchemy.Column(
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
        index=True,
    )


class BroadcastExecutionBatch(Base):
    __tablename__ = 'broadcast_execution_batches'
    __table_args__ = (
        sqlalchemy.Index('ix_broadcast_execution_batches_scope', 'bot_uuid', 'connector_id'),
    )

    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True, autoincrement=True)
    bot_uuid = sqlalchemy.Column(sqlalchemy.String(255), nullable=False, index=True)
    connector_id = sqlalchemy.Column(sqlalchemy.String(255), nullable=False, index=True)
    channel = sqlalchemy.Column(sqlalchemy.String(64), nullable=False)
    mode = sqlalchemy.Column(sqlalchemy.String(32), nullable=False)
    status = sqlalchemy.Column(sqlalchemy.String(32), nullable=False, index=True)
    total_tasks = sqlalchemy.Column(sqlalchemy.Integer, nullable=False, server_default='0', default=0)
    pending_tasks = sqlalchemy.Column(sqlalchemy.Integer, nullable=False, server_default='0', default=0)
    running_tasks = sqlalchemy.Column(sqlalchemy.Integer, nullable=False, server_default='0', default=0)
    succeeded_tasks = sqlalchemy.Column(sqlalchemy.Integer, nullable=False, server_default='0', default=0)
    failed_tasks = sqlalchemy.Column(sqlalchemy.Integer, nullable=False, server_default='0', default=0)
    cancelled_tasks = sqlalchemy.Column(sqlalchemy.Integer, nullable=False, server_default='0', default=0)
    interrupted_tasks = sqlalchemy.Column(sqlalchemy.Integer, nullable=False, server_default='0', default=0)
    created_by = sqlalchemy.Column(sqlalchemy.String(255), nullable=False)
    last_action_by = sqlalchemy.Column(sqlalchemy.String(255), nullable=True)
    error_message = sqlalchemy.Column(sqlalchemy.Text, nullable=True)
    version = sqlalchemy.Column(sqlalchemy.Integer, nullable=False, server_default='1', default=1)
    created_at = sqlalchemy.Column(sqlalchemy.DateTime, nullable=False, server_default=sqlalchemy.func.now(), index=True)
    started_at = sqlalchemy.Column(sqlalchemy.DateTime, nullable=True)
    paused_at = sqlalchemy.Column(sqlalchemy.DateTime, nullable=True)
    finished_at = sqlalchemy.Column(sqlalchemy.DateTime, nullable=True)
    cancelled_at = sqlalchemy.Column(sqlalchemy.DateTime, nullable=True)


class BroadcastExecutionTask(Base):
    __tablename__ = 'broadcast_execution_tasks'
    __table_args__ = (
        sqlalchemy.UniqueConstraint(
            'execution_batch_id',
            'sequence_no',
            name='uq_broadcast_execution_tasks_batch_sequence',
        ),
    )

    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True, autoincrement=True)
    execution_batch_id = sqlalchemy.Column(
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey('broadcast_execution_batches.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    draft_id = sqlalchemy.Column(
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey('broadcast_drafts.id', ondelete='SET NULL'),
        nullable=True,
    )
    draft_text_snapshot = sqlalchemy.Column(sqlalchemy.Text, nullable=False)
    target_conversation_snapshot = sqlalchemy.Column(sqlalchemy.Text, nullable=False)
    channel = sqlalchemy.Column(sqlalchemy.String(64), nullable=False)
    action = sqlalchemy.Column(sqlalchemy.String(32), nullable=False)
    status = sqlalchemy.Column(sqlalchemy.String(32), nullable=False, index=True)
    sequence_no = sqlalchemy.Column(sqlalchemy.Integer, nullable=False, index=True)
    attempt_count = sqlalchemy.Column(sqlalchemy.Integer, nullable=False, server_default='0', default=0)
    max_attempts = sqlalchemy.Column(sqlalchemy.Integer, nullable=False, server_default='0', default=0)
    idempotency_key = sqlalchemy.Column(sqlalchemy.String(255), nullable=False)
    request_digest = sqlalchemy.Column(sqlalchemy.String(64), nullable=False)
    runtime_task_id = sqlalchemy.Column(sqlalchemy.String(255), nullable=True)
    error_code = sqlalchemy.Column(sqlalchemy.String(255), nullable=True)
    error_message = sqlalchemy.Column(sqlalchemy.Text, nullable=True)
    operator_note = sqlalchemy.Column(sqlalchemy.Text, nullable=True)
    created_at = sqlalchemy.Column(sqlalchemy.DateTime, nullable=False, server_default=sqlalchemy.func.now())
    started_at = sqlalchemy.Column(sqlalchemy.DateTime, nullable=True)
    finished_at = sqlalchemy.Column(sqlalchemy.DateTime, nullable=True)
    cancelled_at = sqlalchemy.Column(sqlalchemy.DateTime, nullable=True)
    updated_at = sqlalchemy.Column(
        sqlalchemy.DateTime,
        nullable=False,
        server_default=sqlalchemy.func.now(),
        onupdate=sqlalchemy.func.now(),
    )


class BroadcastExecutionAttempt(Base):
    __tablename__ = 'broadcast_execution_attempts'
    __table_args__ = (
        sqlalchemy.UniqueConstraint(
            'execution_task_id',
            'attempt_no',
            name='uq_broadcast_execution_attempts_task_attempt',
        ),
        sqlalchemy.UniqueConstraint(
            'idempotency_key',
            name='uq_broadcast_execution_attempts_idempotency_key',
        ),
        sqlalchemy.UniqueConstraint(
            'runtime_task_id',
            name='uq_broadcast_execution_attempts_runtime_task_id',
        ),
    )

    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True, autoincrement=True)
    execution_task_id = sqlalchemy.Column(
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey('broadcast_execution_tasks.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    attempt_no = sqlalchemy.Column(sqlalchemy.Integer, nullable=False)
    idempotency_key = sqlalchemy.Column(sqlalchemy.String(255), nullable=False)
    request_digest = sqlalchemy.Column(sqlalchemy.String(64), nullable=False)
    runtime_task_id = sqlalchemy.Column(sqlalchemy.String(255), nullable=True, index=True)
    request_summary = sqlalchemy.Column(sqlalchemy.Text, nullable=True)
    response_summary = sqlalchemy.Column(sqlalchemy.Text, nullable=True)
    status = sqlalchemy.Column(sqlalchemy.String(32), nullable=False)
    error_code = sqlalchemy.Column(sqlalchemy.String(255), nullable=True)
    error_message = sqlalchemy.Column(sqlalchemy.Text, nullable=True)
    started_at = sqlalchemy.Column(sqlalchemy.DateTime, nullable=False, server_default=sqlalchemy.func.now())
    finished_at = sqlalchemy.Column(sqlalchemy.DateTime, nullable=True)


class BroadcastAttachmentAsset(Base):
    __tablename__ = 'broadcast_attachment_assets'
    __table_args__ = (
        sqlalchemy.Index('ix_broadcast_attachment_assets_scope', 'bot_uuid', 'connector_id'),
        sqlalchemy.UniqueConstraint(
            'sha256',
            'size_bytes',
            'stored_name',
            name='uq_broadcast_attachment_assets_storage',
        ),
    )

    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True, autoincrement=True)
    bot_uuid = sqlalchemy.Column(sqlalchemy.String(255), nullable=False, index=True)
    connector_id = sqlalchemy.Column(sqlalchemy.String(255), nullable=False, index=True)
    original_name = sqlalchemy.Column(sqlalchemy.String(255), nullable=False)
    stored_name = sqlalchemy.Column(sqlalchemy.String(255), nullable=False)
    stored_path = sqlalchemy.Column(sqlalchemy.Text, nullable=False)
    relative_path = sqlalchemy.Column(sqlalchemy.Text, nullable=True)
    size_bytes = sqlalchemy.Column(sqlalchemy.BigInteger, nullable=False)
    sha256 = sqlalchemy.Column(sqlalchemy.String(64), nullable=False, index=True)
    extension = sqlalchemy.Column(sqlalchemy.String(32), nullable=False)
    mime_type = sqlalchemy.Column(sqlalchemy.String(255), nullable=False)
    status = sqlalchemy.Column(sqlalchemy.String(32), nullable=False, server_default='ready', default='ready')
    created_at = sqlalchemy.Column(sqlalchemy.DateTime, nullable=False, server_default=sqlalchemy.func.now())


class BroadcastImportGroupAttachment(Base):
    __tablename__ = 'broadcast_import_group_attachments'
    __table_args__ = (
        sqlalchemy.Index(
            'ix_broadcast_import_group_attachments_batch_group',
            'batch_id',
            'group_key',
            'sort_order',
        ),
        sqlalchemy.UniqueConstraint(
            'batch_id',
            'group_key',
            'attachment_asset_id',
            name='uq_broadcast_import_group_attachments_group_asset',
        ),
    )

    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True, autoincrement=True)
    batch_id = sqlalchemy.Column(
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey('broadcast_import_batches.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    group_key = sqlalchemy.Column(sqlalchemy.String(128), nullable=False, index=True)
    group_value_snapshot = sqlalchemy.Column(sqlalchemy.String(255), nullable=True)
    attachment_asset_id = sqlalchemy.Column(
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey('broadcast_attachment_assets.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    sort_order = sqlalchemy.Column(sqlalchemy.Integer, nullable=False, server_default='0', default=0)
    created_at = sqlalchemy.Column(sqlalchemy.DateTime, nullable=False, server_default=sqlalchemy.func.now())


class BroadcastDraftAttachment(Base):
    __tablename__ = 'broadcast_draft_attachments'
    __table_args__ = (
        sqlalchemy.Index('ix_broadcast_draft_attachments_draft', 'draft_id', 'sort_order'),
        sqlalchemy.UniqueConstraint(
            'draft_id',
            'attachment_asset_id',
            name='uq_broadcast_draft_attachments_draft_asset',
        ),
    )

    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True, autoincrement=True)
    draft_id = sqlalchemy.Column(
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey('broadcast_drafts.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    attachment_asset_id = sqlalchemy.Column(
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey('broadcast_attachment_assets.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    original_name_snapshot = sqlalchemy.Column(sqlalchemy.String(255), nullable=False)
    size_bytes_snapshot = sqlalchemy.Column(sqlalchemy.BigInteger, nullable=False)
    sha256_snapshot = sqlalchemy.Column(sqlalchemy.String(64), nullable=False)
    sort_order = sqlalchemy.Column(sqlalchemy.Integer, nullable=False, server_default='0', default=0)
    created_at = sqlalchemy.Column(sqlalchemy.DateTime, nullable=False, server_default=sqlalchemy.func.now())


class BroadcastExecutionTaskAttachment(Base):
    __tablename__ = 'broadcast_execution_task_attachments'
    __table_args__ = (
        sqlalchemy.Index(
            'ix_broadcast_execution_task_attachments_task',
            'execution_task_id',
            'sort_order',
        ),
        sqlalchemy.UniqueConstraint(
            'execution_task_id',
            'attachment_asset_id',
            name='uq_broadcast_execution_task_attachments_task_asset',
        ),
    )

    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True, autoincrement=True)
    execution_task_id = sqlalchemy.Column(
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey('broadcast_execution_tasks.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    attachment_asset_id = sqlalchemy.Column(
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey('broadcast_attachment_assets.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    original_name_snapshot = sqlalchemy.Column(sqlalchemy.String(255), nullable=False)
    size_bytes_snapshot = sqlalchemy.Column(sqlalchemy.BigInteger, nullable=False)
    sha256_snapshot = sqlalchemy.Column(sqlalchemy.String(64), nullable=False)
    sort_order = sqlalchemy.Column(sqlalchemy.Integer, nullable=False, server_default='0', default=0)
    created_at = sqlalchemy.Column(sqlalchemy.DateTime, nullable=False, server_default=sqlalchemy.func.now())


class BroadcastExecutionEvidence(Base):
    __tablename__ = 'broadcast_execution_evidence'

    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True, autoincrement=True)
    execution_attempt_id = sqlalchemy.Column(
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey('broadcast_execution_attempts.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    window_title = sqlalchemy.Column(sqlalchemy.String(255), nullable=True)
    target_conversation = sqlalchemy.Column(sqlalchemy.String(255), nullable=True)
    action = sqlalchemy.Column(sqlalchemy.String(32), nullable=False)
    input_located = sqlalchemy.Column(sqlalchemy.Boolean, nullable=False, server_default=sqlalchemy.false(), default=False)
    draft_written = sqlalchemy.Column(sqlalchemy.Boolean, nullable=False, server_default=sqlalchemy.false(), default=False)
    send_triggered = sqlalchemy.Column(sqlalchemy.Boolean, nullable=False, server_default=sqlalchemy.false(), default=False)
    clipboard_restored = sqlalchemy.Column(
        sqlalchemy.Boolean, nullable=False, server_default=sqlalchemy.false(), default=False
    )
    runtime_state = sqlalchemy.Column(sqlalchemy.String(64), nullable=True)
    evidence_summary = sqlalchemy.Column(sqlalchemy.Text, nullable=True)
    technical_details = sqlalchemy.Column(sqlalchemy.Text, nullable=True)
    created_at = sqlalchemy.Column(sqlalchemy.DateTime, nullable=False, server_default=sqlalchemy.func.now())


class BroadcastSendConfirmation(Base):
    __tablename__ = 'broadcast_send_confirmations'
    __table_args__ = (
        sqlalchemy.UniqueConstraint(
            'confirmation_token_hash',
            name='uq_broadcast_send_confirmations_token_hash',
        ),
    )

    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True, autoincrement=True)
    execution_task_id = sqlalchemy.Column(
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey('broadcast_execution_tasks.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    confirmation_token_hash = sqlalchemy.Column(sqlalchemy.String(255), nullable=False)
    issued_at = sqlalchemy.Column(sqlalchemy.DateTime, nullable=False, server_default=sqlalchemy.func.now())
    expires_at = sqlalchemy.Column(sqlalchemy.DateTime, nullable=True)
    used_at = sqlalchemy.Column(sqlalchemy.DateTime, nullable=True)
    issued_by = sqlalchemy.Column(sqlalchemy.String(255), nullable=False)
    used_by = sqlalchemy.Column(sqlalchemy.String(255), nullable=True)
    status = sqlalchemy.Column(sqlalchemy.String(32), nullable=False)
