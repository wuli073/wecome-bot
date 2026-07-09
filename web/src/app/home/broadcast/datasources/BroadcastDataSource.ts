import { backendClient } from '@/app/infra/http';
import type {
  ApiBroadcastAttachment,
  ApiBroadcastBulkAssignResult,
  ApiBroadcastDraft,
  ApiBroadcastExecutionAttempt,
  ApiBroadcastExecutionBatch,
  ApiBroadcastExecutionEvidence,
  ApiBroadcastExecutionTask,
  ApiBroadcastGroupMatchResult,
  ApiBroadcastGroupName,
  ApiBroadcastGroupRule,
  ApiBroadcastImportBatch,
  ApiBroadcastImportDetail,
  ApiBroadcastImportGroupRowsResponse,
  ApiBroadcastImportGroupRuleCandidatesResponse,
  ApiBroadcastImportGroupsResponse,
  ApiBroadcastImportGroupSummary,
  ApiBroadcastImportRow,
  ApiBroadcastScope,
  ApiBroadcastTemplate,
  ApiBroadcastTemplateRenderResult,
  ApiBroadcastVariableProfile,
} from '@/app/infra/entities/api';

import { createBroadcastWorkspaceSnapshot } from '../mockData';
import {
  BROADCAST_STATUS_LABELS,
  buildTemplatePreviewVariables,
  buildVariableMappings,
} from '../utils';
import type {
  BroadcastAttachment,
  BroadcastBulkAssignResult,
  BroadcastDraft,
  BroadcastDraftDetail,
  BroadcastExecutionBatchSummary,
  BroadcastExecutorCapability,
  BroadcastExecutorHealth,
  BroadcastExecutionLog,
  BroadcastSendBatchItem,
  BroadcastExecutionTaskSummary,
  BroadcastDraftFilters,
  BroadcastDraftStatus,
  BroadcastDraftStatusUpdateResult,
  BroadcastGroupMatchResult,
  BroadcastGroupName,
  BroadcastGroupNameSyncResult,
  BroadcastGroupRule,
  BroadcastGroupRuleDraft,
  BroadcastGroupRuleCandidateList,
  BroadcastImportBatch,
  BroadcastImportDetail,
  BroadcastImportDraftGenerationResult,
  BroadcastImportFilters,
  BroadcastImportGroupList,
  BroadcastImportGroupRowsPage,
  BroadcastImportGroupSummary,
  BroadcastMessageTemplate,
  BroadcastPasteDraftRequest,
  BroadcastPasteOnlyAdapter,
  BroadcastRuntimePasteDraftPayload,
  BroadcastRulesData,
  BroadcastScope,
  BroadcastStatus,
  BroadcastTemplateDraft,
  BroadcastTemplateRenderResult,
  BroadcastVariableProfile,
  BroadcastWorkspaceSnapshot,
} from '../types';

function cloneValue<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

function toApiScope(scope: BroadcastScope): ApiBroadcastScope {
  return {
    bot_uuid: scope.botUuid,
    connector_id: scope.connectorId,
  };
}

const TERMINAL_ATTEMPT_STATUSES = new Set([
  'succeeded',
  'succeeded_with_warning',
  'failed',
  'cancelled',
  'timed_out',
  'interrupted',
]);

function fromApiTemplate(
  template: ApiBroadcastTemplate,
): BroadcastMessageTemplate {
  return {
    id: template.id,
    name: template.name,
    updatedAt: template.updated_at,
    variableKeys: template.variables,
    body: template.content,
    enabled: template.enabled,
  };
}

function fromApiVariableProfile(
  profile: ApiBroadcastVariableProfile,
): BroadcastVariableProfile {
  return {
    groupField: profile.group_field,
    mappingRules: profile.mapping_rules.map((rule) => ({
      sourceField: rule.source_field,
      variableKey: rule.variable_key,
      mergeMode: rule.merge_mode,
      order: rule.order,
    })),
  };
}

function toApiVariableProfile(profile: BroadcastVariableProfile) {
  return {
    group_field: profile.groupField,
    mapping_rules: profile.mappingRules.map((rule) => ({
      source_field: rule.sourceField,
      variable_key: rule.variableKey,
      merge_mode: rule.mergeMode,
      order: rule.order,
    })),
  };
}

function fromApiTemplateRenderResult(
  result: ApiBroadcastTemplateRenderResult,
): BroadcastTemplateRenderResult {
  return {
    renderedText: result.rendered_text,
    requiredVariables: result.required_variables,
    missingVariables: result.missing_variables,
    valid: result.valid,
  };
}

function fromApiGroupRule(rule: ApiBroadcastGroupRule): BroadcastGroupRule {
  return {
    id: rule.id,
    sourceValue: rule.source_value,
    matchType: rule.match_type,
    matchExpression: rule.match_expression,
    targetConversationId: rule.target_conversation_id ?? null,
    targetConversationName: rule.target_conversation_name,
    priority: rule.priority,
    enabled: rule.enabled,
    invalidLegacy: rule.invalid_legacy ?? false,
    invalidReason: rule.invalid_reason ?? null,
    updatedAt: rule.updated_at,
  };
}

function toApiGroupRuleDraft(draft: BroadcastGroupRuleDraft) {
  return {
    source_value: draft.sourceValue,
    match_type: draft.matchType,
    match_expression: draft.matchExpression,
    target_conversation_id: draft.targetConversationId,
    target_conversation_name: draft.targetConversationName,
    priority: draft.priority,
    enabled: draft.enabled,
  };
}

function fromApiGroupMatchResult(
  result: ApiBroadcastGroupMatchResult,
): BroadcastGroupMatchResult {
  return {
    matched: result.matched,
    ruleId: result.rule_id,
    matchedRuleId: result.matched_rule_id ?? result.rule_id,
    sourceValue: result.source_value ?? '',
    targetConversationId: result.target_conversation_id ?? null,
    targetConversationName: result.target_conversation_name,
    matchType: result.match_type,
    candidateCount: result.candidate_count ?? 0,
    candidateRules: (result.candidate_rules ?? []).map(fromApiGroupRule),
    conflict: result.conflict ?? false,
    reason: result.reason ?? null,
  };
}

function fromApiGroupName(
  groupName: ApiBroadcastGroupName,
): BroadcastGroupName {
  return {
    id: groupName.id,
    name: groupName.name,
    externalConversationId: groupName.external_conversation_id ?? null,
    updatedAt: groupName.updated_at,
  };
}

function updateDraftStatus(
  draft: BroadcastDraft,
  status: BroadcastStatus,
): BroadcastDraft {
  return {
    ...draft,
    status: status as BroadcastDraftStatus,
    updatedAt: new Date().toISOString(),
  };
}

function fromApiImportRow(row: ApiBroadcastImportRow) {
  const customerName = row.group_value ?? '';
  const conversationName = row.matched_conversation_name ?? '';
  const statusMap: Record<string, BroadcastStatus> = {
    matched: 'completed',
    unmatched: 'pending',
    invalid: 'failed',
  };
  return {
    id: row.id,
    sourceRowNumber: row.source_row_number,
    groupValue: row.group_value,
    rawData: row.raw_data,
    matchedConversationName: row.matched_conversation_name,
    matchedRuleId: row.matched_rule_id,
    matchStatus: row.match_status,
    errorMessage: row.error_message,
    customerName,
    conversationName,
    templateName: '',
    variableSummary: `${Object.keys(row.raw_data ?? {}).length}`,
    status: statusMap[row.match_status] ?? 'pending',
    matchedRule:
      row.matched_rule_id != null
        ? `#${row.matched_rule_id}`
        : row.matched_conversation_name
          ? 'fallback'
          : '',
  };
}

function fromApiImportBatch(
  batch: ApiBroadcastImportBatch,
): BroadcastImportBatch {
  return {
    id: batch.id,
    originalFileName: batch.original_file_name,
    fileType: batch.file_type,
    worksheetName: batch.worksheet_name,
    status: batch.status,
    draftsStale: batch.drafts_stale,
    totalRows: batch.total_rows,
    validRows: batch.valid_rows,
    invalidRows: batch.invalid_rows,
    matchedRows: batch.matched_rows,
    unmatchedRows: batch.unmatched_rows,
    groupFieldUsed: batch.group_field_used ?? null,
    groupFieldSource: batch.group_field_source ?? null,
    createdAt: batch.created_at,
    updatedAt: batch.updated_at,
  };
}

function fromApiImportDetail(
  detail: ApiBroadcastImportDetail,
): BroadcastImportDetail {
  return {
    ...fromApiImportBatch(detail),
    rows: detail.rows.map(fromApiImportRow),
    page: detail.page,
    pageSize: detail.page_size,
    total: detail.total,
    totalPages: detail.total_pages,
  };
}

function fromApiAttachment(
  attachment: ApiBroadcastAttachment,
): BroadcastAttachment {
  return {
    id: attachment.id,
    attachmentAssetId: attachment.attachment_asset_id,
    originalName:
      attachment.original_name_snapshot ?? attachment.original_name ?? '',
    sizeBytes: attachment.size_bytes_snapshot ?? attachment.size_bytes ?? 0,
    sha256: attachment.sha256_snapshot ?? attachment.sha256 ?? '',
    extension: attachment.extension,
    mimeType: attachment.mime_type,
    sortOrder: attachment.sort_order,
  };
}

function fromApiImportGroupSummary(
  summary: ApiBroadcastImportGroupSummary,
): BroadcastImportGroupSummary {
  return {
    groupKey: summary.group_key,
    groupValue: summary.group_value,
    rawRowCount: summary.raw_row_count,
    distinctOrderNumberCount: summary.distinct_order_number_count,
    matchedConversationName: summary.matched_conversation_name,
    matchStatus: summary.match_status,
    reason: summary.reason,
    attachmentCount: summary.attachment_count,
    expandable: summary.expandable,
    firstSourceRowNumber: summary.first_source_row_number,
    templateId: summary.template_id ?? null,
    templateName: summary.template_name ?? null,
    templateEnabled: summary.template_enabled ?? null,
  };
}

function fromApiImportGroups(
  detail: ApiBroadcastImportGroupsResponse,
): BroadcastImportGroupList {
  return {
    page: detail.page,
    pageSize: detail.page_size,
    total: detail.total,
    totalPages: detail.total_pages,
    rawRowTotal: detail.raw_row_total,
    groupTotal: detail.group_total,
    matchedGroupTotal: detail.matched_group_total,
    unmatchedGroupTotal: detail.unmatched_group_total,
    invalidGroupTotal: detail.invalid_group_total,
    conflictGroupTotal: detail.conflict_group_total,
    orderNumberFieldConfigured: detail.order_number_field_configured,
    groups: detail.groups.map(fromApiImportGroupSummary),
  };
}

function fromApiImportGroupRuleCandidates(
  detail: ApiBroadcastImportGroupRuleCandidatesResponse,
): BroadcastGroupRuleCandidateList {
  return {
    importBatchId: detail.import_batch_id,
    groupFieldUsed: detail.group_field_used,
    groupFieldSource: detail.group_field_source,
    rawRowTotal: detail.raw_row_total,
    uniqueCustomerTotal: detail.unique_customer_total,
    stats: {
      newCount: detail.stats.new_count,
      configuredCount: detail.stats.configured_count,
      needsRepairCount: detail.stats.needs_repair_count,
      conflictCount: detail.stats.conflict_count,
      invalidCount: detail.stats.invalid_count,
    },
    items: detail.items.map((item) => ({
      groupKey: item.group_key,
      customerName: item.customer_name,
      rawRowCount: item.raw_row_count,
      status: item.status,
      reason: item.reason,
      existingRuleIds: item.existing_rule_ids,
      existingRules: item.existing_rules.map(fromApiGroupRule),
      currentMatchedRule: item.current_matched_rule
        ? fromApiGroupRule(item.current_matched_rule)
        : null,
      currentTargetConversationId: item.current_target_conversation_id ?? null,
      currentTargetConversationName: item.current_target_conversation_name,
      currentMatchType: item.current_match_type,
    })),
    page: detail.page,
    pageSize: detail.page_size,
    total: detail.total,
    totalPages: detail.total_pages,
  };
}

function fromApiBulkAssignResult(
  result: ApiBroadcastBulkAssignResult,
): BroadcastBulkAssignResult {
  return {
    createdCount: result.created_count,
    groupFieldUsed: result.group_field_used,
    groupFieldSource: result.group_field_source,
    items: result.items.map((item) => ({
      groupKey: item.group_key,
      customerName: item.customer_name,
      ruleId: item.rule_id,
      targetConversationId: item.target_conversation_id,
      targetConversationName: item.target_conversation_name,
    })),
  };
}

function fromApiImportGroupRows(
  detail: ApiBroadcastImportGroupRowsResponse,
): BroadcastImportGroupRowsPage {
  return {
    groupKey: detail.group_key,
    groupValue: detail.group_value,
    page: detail.page,
    pageSize: detail.page_size,
    total: detail.total,
    totalPages: detail.total_pages,
    rows: detail.rows.map(fromApiImportRow),
  };
}

function fromApiDraft(draft: ApiBroadcastDraft): BroadcastDraftDetail {
  const businessStatus =
    draft.send_status ??
    (draft.status === 'sent'
      ? 'sent'
      : draft.status === 'invalid'
        ? 'invalid'
        : 'pending');
  return {
    id: draft.id,
    botUuid: draft.bot_uuid,
    connectorId: draft.connector_id,
    importBatchId: draft.import_batch_id,
    groupValue: draft.group_value,
    customerName: draft.group_value,
    conversationId: draft.target_conversation_id ?? null,
    conversationName: draft.target_conversation_name ?? '',
    templateId: draft.template_id,
    templateName: draft.template_name_snapshot,
    templateContentSnapshot: draft.template_content_snapshot,
    renderVariables: draft.render_variables,
    draftText: draft.draft_text,
    status: businessStatus,
    sendStatus: businessStatus === 'invalid' ? undefined : businessStatus,
    sentAt: draft.sent_at ?? null,
    legacyStatus: draft.legacy_status ?? draft.status,
    errorMessage: draft.error_message,
    draftsStale: draft.drafts_stale,
    attachmentsStale: draft.attachments_stale ?? false,
    attachments: (draft.attachments ?? []).map(fromApiAttachment),
    updatedAt: draft.updated_at,
    createdAt: draft.created_at,
    message: draft.message ?? null,
    progressLabel: BROADCAST_STATUS_LABELS[businessStatus],
    operator: '',
  };
}

function fromApiExecutionTask(
  task: ApiBroadcastExecutionTask,
): BroadcastExecutionTaskSummary {
  return {
    id: task.id,
    executionBatchId: task.execution_batch_id,
    draftId: task.draft_id,
    targetConversationSnapshot: task.target_conversation_snapshot,
    draftTextSnapshot: task.draft_text_snapshot,
    action: task.action,
    status: task.status,
    attemptCount: task.attempt_count,
    idempotencyKey: task.idempotency_key,
    runtimeTaskId: task.runtime_task_id,
    errorCode: task.error_code,
    errorMessage: task.error_message,
    createdAt: task.created_at,
    startedAt: task.started_at,
    finishedAt: task.finished_at,
    updatedAt: task.updated_at,
    retryAllowed:
      typeof task.retry_allowed === 'boolean' ? task.retry_allowed : undefined,
    sendOutcome: task.send_outcome ?? null,
    enterDispatched:
      typeof task.enter_dispatched === 'boolean' ||
      task.enter_dispatched === null
        ? task.enter_dispatched
        : undefined,
    messageSent:
      typeof task.message_sent === 'boolean' || task.message_sent === null
        ? task.message_sent
        : undefined,
    terminalConfirmed:
      typeof task.terminal_confirmed === 'boolean' ||
      task.terminal_confirmed === null
        ? task.terminal_confirmed
        : undefined,
    terminalSource:
      typeof task.terminal_source === 'string' ? task.terminal_source : null,
    attachments: (task.attachments ?? []).map(fromApiAttachment),
  };
}

function fromApiExecutionBatch(
  batch: ApiBroadcastExecutionBatch,
): BroadcastExecutionBatchSummary {
  return {
    id: batch.id,
    status: batch.status,
    mode: batch.mode,
    totalTasks: batch.total_tasks,
    pendingTasks: batch.pending_tasks,
    runningTasks: batch.running_tasks,
    succeededTasks: batch.succeeded_tasks,
    failedTasks: batch.failed_tasks,
    cancelledTasks: batch.cancelled_tasks,
    interruptedTasks: batch.interrupted_tasks,
    createdBy: batch.created_by,
    lastActionBy: batch.last_action_by,
    createdAt: batch.created_at,
    startedAt: batch.started_at,
    finishedAt: batch.finished_at,
    tasks: (batch.tasks || []).map(fromApiExecutionTask),
    totalCount: batch.total_count,
    sentCount: batch.sent_count,
    failedCount: batch.failed_count,
    unknownCount: batch.unknown_count,
    skippedCount: batch.skipped_count,
    duplicateTargetCount: batch.duplicate_target_count,
    items: (batch.items || []).map(
      (item): BroadcastSendBatchItem => ({
        draftId: item.draft_id,
        outcome: item.outcome,
        errorCode: item.error_code,
        errorMessage: item.error_message,
        enterDispatched: item.enter_dispatched,
        messageSent:
          typeof item.message_sent === 'boolean' || item.message_sent === null
            ? item.message_sent
            : undefined,
        terminalConfirmed:
          typeof item.terminal_confirmed === 'boolean' ||
          item.terminal_confirmed === null
            ? item.terminal_confirmed
            : undefined,
        terminalSource:
          typeof item.terminal_source === 'string'
            ? item.terminal_source
            : null,
        startedAt: item.started_at,
        completedAt: item.completed_at,
      }),
    ),
  };
}

function fromApiExecutorCapability(
  payload: Record<string, unknown>,
): BroadcastExecutorCapability {
  const conversationLocator = String(payload.conversation_locator || '').trim();
  const contentVerification = String(payload.content_verification || '').trim();
  return {
    channel: String(payload.channel || 'wxwork_database'),
    supports_paste: Boolean(payload.supports_paste),
    supports_paste_verification: Boolean(payload.supports_paste_verification),
    supports_post_send_verification: Boolean(
      payload.supports_post_send_verification,
    ),
    supports_send: Boolean(payload.supports_send),
    supports_cancel: Boolean(payload.supports_cancel),
    supports_status_query: Boolean(payload.supports_status_query),
    supports_clipboard_restore: Boolean(payload.supports_clipboard_restore),
    supports_evidence: Boolean(payload.supports_evidence),
    requires_manual_conversation_open: Boolean(
      payload.requires_manual_conversation_open,
    ),
    executor_version: String(payload.executor_version || ''),
    runtime_min_version: String(payload.runtime_min_version || ''),
    conversation_locator:
      conversationLocator === 'keyboard_search' ||
      conversationLocator === 'external_id'
        ? (conversationLocator as 'keyboard_search' | 'external_id')
        : 'unknown',
    content_verification:
      contentVerification === 'disabled' ||
      contentVerification === 'manual' ||
      contentVerification === 'windows_uia'
        ? (contentVerification as 'disabled' | 'manual' | 'windows_uia')
        : 'unknown',
    post_send_verification:
      String(payload.post_send_verification || '').trim() === 'unavailable'
        ? 'unavailable'
        : String(payload.post_send_verification || '').trim() === 'available'
          ? 'available'
          : 'unknown',
  };
}

function fromApiExecutorHealth(
  payload: Record<string, unknown>,
): BroadcastExecutorHealth {
  const status = String(payload.status || 'unknown');
  return {
    available:
      typeof payload.available === 'boolean'
        ? payload.available
        : status === 'ready',
    channel: String(payload.channel || 'wxwork_database'),
    status,
    protocol_version: payload.protocol_version
      ? String(payload.protocol_version)
      : null,
    runtime_version: payload.runtime_version
      ? String(payload.runtime_version)
      : null,
    error_code:
      typeof payload.error_code === 'string' ? payload.error_code : null,
    error_message:
      typeof payload.error_message === 'string' ? payload.error_message : null,
    capability: fromApiExecutorCapability(
      (payload.capability as Record<string, unknown>) || {},
    ),
    runtime_status: (payload.runtime_status as Record<string, unknown>) || null,
  };
}

function toExecutionLog(
  batch: BroadcastExecutionBatchSummary,
  task: BroadcastExecutionTaskSummary,
  attempt: ApiBroadcastExecutionAttempt,
  evidence: ApiBroadcastExecutionEvidence | null,
  draft?: BroadcastDraft | null,
): BroadcastExecutionLog {
  const technicalDetails =
    evidence?.technical_details &&
    typeof evidence.technical_details === 'object'
      ? (evidence.technical_details as Record<string, unknown>)
      : null;
  const contentVerified =
    technicalDetails && 'content_verified' in technicalDetails
      ? Boolean(technicalDetails.content_verified)
      : false;
  return {
    id: attempt.id,
    batchId: batch.id,
    taskId: task.id,
    attemptId: attempt.id,
    draftId: task.draftId,
    customerName: draft?.customerName || draft?.groupValue || '',
    conversationName: task.targetConversationSnapshot,
    batchStatus: batch.status,
    taskStatus: task.status,
    attemptStatus: attempt.status,
    action: evidence?.action || task.action,
    message:
      evidence?.evidence_summary ||
      task.errorMessage ||
      attempt.error_message ||
      task.status,
    runtimeState: evidence?.runtime_state || null,
    sendTriggered: evidence?.send_triggered || false,
    inputLocated: evidence?.input_located || false,
    draftWritten: evidence?.draft_written || false,
    contentVerified,
    textContentVerified: contentVerified,
    clipboardRestored: evidence?.clipboard_restored || false,
    attachmentCount:
      technicalDetails && 'attachment_count' in technicalDetails
        ? Number(technicalDetails.attachment_count || 0)
        : 0,
    attachmentNames:
      technicalDetails && Array.isArray(technicalDetails.attachment_names)
        ? technicalDetails.attachment_names
            .map((item) => String(item))
            .filter((item) => item.trim().length > 0)
        : [],
    attachmentsPrepared:
      technicalDetails && 'attachments_prepared' in technicalDetails
        ? Boolean(technicalDetails.attachments_prepared)
        : false,
    attachmentPasteRequested:
      technicalDetails && 'attachment_paste_requested' in technicalDetails
        ? Boolean(technicalDetails.attachment_paste_requested)
        : false,
    attachmentsVerified:
      technicalDetails && 'attachments_verified' in technicalDetails
        ? Boolean(technicalDetails.attachments_verified)
        : false,
    warning:
      technicalDetails && 'warning' in technicalDetails
        ? technicalDetails.warning == null
          ? null
          : String(technicalDetails.warning)
        : null,
    errorCode:
      technicalDetails && 'error_code' in technicalDetails
        ? technicalDetails.error_code == null
          ? null
          : String(technicalDetails.error_code)
        : attempt.error_code || task.errorCode || null,
    stage:
      technicalDetails && 'stage' in technicalDetails
        ? technicalDetails.stage == null
          ? null
          : String(technicalDetails.stage)
        : evidence?.runtime_state || null,
    technicalDetails,
    timestamp: attempt.finished_at || attempt.started_at,
  };
}

export interface BroadcastDataSource {
  loadSnapshot: () => BroadcastWorkspaceSnapshot;
  loadRulesData: (scope: BroadcastScope) => Promise<BroadcastRulesData>;
  saveVariableProfile: (
    scope: BroadcastScope,
    profile: BroadcastVariableProfile,
  ) => Promise<BroadcastVariableProfile>;
  createTemplate: (
    scope: BroadcastScope,
    template: BroadcastTemplateDraft,
  ) => Promise<BroadcastMessageTemplate>;
  updateTemplate: (
    scope: BroadcastScope,
    templateId: number,
    template: BroadcastTemplateDraft,
  ) => Promise<BroadcastMessageTemplate>;
  deleteTemplate: (scope: BroadcastScope, templateId: number) => Promise<void>;
  renderTemplate: (
    scope: BroadcastScope,
    payload:
      | { templateId: number; variables: Record<string, string> }
      | { content: string; variables: Record<string, string> },
  ) => Promise<BroadcastTemplateRenderResult>;
  createGroupRule: (
    scope: BroadcastScope,
    draft: BroadcastGroupRuleDraft,
  ) => Promise<BroadcastGroupRule>;
  updateGroupRule: (
    scope: BroadcastScope,
    ruleId: number,
    draft: BroadcastGroupRuleDraft,
  ) => Promise<BroadcastGroupRule>;
  deleteGroupRule: (scope: BroadcastScope, ruleId: number) => Promise<void>;
  matchGroupRule: (
    scope: BroadcastScope,
    sourceValue: string,
  ) => Promise<BroadcastGroupMatchResult>;
  createGroupNames: (
    scope: BroadcastScope,
    names: string[],
  ) => Promise<BroadcastGroupName[]>;
  syncGroupNames: (
    scope: BroadcastScope,
  ) => Promise<BroadcastGroupNameSyncResult>;
  deleteGroupName: (
    scope: BroadcastScope,
    groupNameId: number,
  ) => Promise<void>;
  saveDraftText: (
    snapshot: BroadcastWorkspaceSnapshot,
    draftId: number,
    draftText: string,
  ) => BroadcastWorkspaceSnapshot;
  applyDraftStatus: (
    snapshot: BroadcastWorkspaceSnapshot,
    draftIds: number[],
    status: BroadcastStatus,
  ) => BroadcastWorkspaceSnapshot;
  appendLogs: (
    snapshot: BroadcastWorkspaceSnapshot,
    entries: BroadcastWorkspaceSnapshot['executionLogs'],
  ) => BroadcastWorkspaceSnapshot;
  listImportBatches: (scope: BroadcastScope) => Promise<BroadcastImportBatch[]>;
  uploadImport: (
    scope: BroadcastScope,
    file: File,
    options?: {
      groupFieldOverride?: string;
    },
  ) => Promise<BroadcastImportBatch>;
  getImportDetail: (
    scope: BroadcastScope,
    importId: number,
    filters?: BroadcastImportFilters,
  ) => Promise<BroadcastImportDetail>;
  getImportGroups: (
    scope: BroadcastScope,
    importId: number,
    filters?: BroadcastImportFilters,
  ) => Promise<BroadcastImportGroupList>;
  getImportGroupRuleCandidates: (
    scope: BroadcastScope,
    importId: number,
    filters?: {
      status?:
        | 'new'
        | 'configured'
        | 'needs_repair'
        | 'conflict'
        | 'invalid'
        | 'all';
      keyword?: string;
      page?: number;
      pageSize?: number;
    },
  ) => Promise<BroadcastGroupRuleCandidateList>;
  updateImportGroupTemplateAssignments: (
    scope: BroadcastScope,
    importId: number,
    items: Array<{ groupKey: string; templateId: number | null }>,
  ) => Promise<Array<{ groupKey: string; templateId: number | null }>>;
  getImportGroupRows: (
    scope: BroadcastScope,
    importId: number,
    groupKey: string,
    filters?: { page?: number; pageSize?: number },
  ) => Promise<BroadcastImportGroupRowsPage>;
  uploadImportGroupAttachments: (
    scope: BroadcastScope,
    importId: number,
    groupKey: string,
    files: File[],
  ) => Promise<BroadcastAttachment[]>;
  deleteImportGroupAttachment: (
    scope: BroadcastScope,
    importId: number,
    groupKey: string,
    attachmentId: number,
  ) => Promise<BroadcastAttachment[]>;
  deleteImport: (scope: BroadcastScope, importId: number) => Promise<void>;
  rematchImport: (
    scope: BroadcastScope,
    importId: number,
  ) => Promise<BroadcastImportDetail>;
  bulkAssignImportGroupRules: (
    scope: BroadcastScope,
    importId: number,
    items: Array<{ groupKey: string; targetConversationId: string }>,
  ) => Promise<BroadcastBulkAssignResult>;
  generateImportDrafts: (
    scope: BroadcastScope,
    importId: number,
    payload: {
      templateId?: number;
      groupKeys?: string[];
      overwriteExisting?: boolean;
    },
  ) => Promise<BroadcastImportDraftGenerationResult>;
  listDrafts: (
    scope: BroadcastScope,
    filters?: BroadcastDraftFilters,
  ) => Promise<BroadcastDraft[]>;
  getDraftDetail: (
    scope: BroadcastScope,
    draftId: number,
  ) => Promise<BroadcastDraftDetail>;
  uploadDraftAttachments: (
    scope: BroadcastScope,
    draftId: number,
    files: File[],
  ) => Promise<BroadcastDraftDetail>;
  deleteDraftAttachment: (
    scope: BroadcastScope,
    draftId: number,
    attachmentId: number,
  ) => Promise<BroadcastDraftDetail>;
  updateDraftText: (
    scope: BroadcastScope,
    draftId: number,
    draftText: string,
  ) => Promise<BroadcastDraftDetail>;
  updateDraftStatuses: (
    scope: BroadcastScope,
    draftIds: number[],
    status: BroadcastDraftStatus,
  ) => Promise<BroadcastDraftStatusUpdateResult>;
  createExecutionBatch: (
    scope: BroadcastScope,
    draftIds: number[],
    mode: 'paste_only' | 'send',
    operator: string,
    options?: {
      allowSentRewrite?: boolean;
    },
  ) => Promise<BroadcastExecutionBatchSummary>;
  startExecutionBatch: (
    scope: BroadcastScope,
    batchId: number,
    operator: string,
  ) => Promise<BroadcastExecutionBatchSummary>;
  pauseExecutionBatch: (
    scope: BroadcastScope,
    batchId: number,
    operator: string,
  ) => Promise<BroadcastExecutionBatchSummary>;
  resumeExecutionBatch: (
    scope: BroadcastScope,
    batchId: number,
    operator: string,
  ) => Promise<BroadcastExecutionBatchSummary>;
  cancelExecutionBatch: (
    scope: BroadcastScope,
    batchId: number,
    operator: string,
  ) => Promise<BroadcastExecutionBatchSummary>;
  listExecutionBatches: (
    scope: BroadcastScope,
  ) => Promise<BroadcastExecutionBatchSummary[]>;
  startExecutionTask: (
    scope: BroadcastScope,
    taskId: number,
    operator: string,
  ) => Promise<BroadcastExecutionTaskSummary>;
  retryExecutionTask: (
    scope: BroadcastScope,
    taskId: number,
    operator: string,
  ) => Promise<BroadcastExecutionTaskSummary>;
  getExecutorCapabilities: (
    scope: BroadcastScope,
  ) => Promise<BroadcastExecutorCapability>;
  getExecutorHealth: (
    scope: BroadcastScope,
  ) => Promise<BroadcastExecutorHealth>;
  getExecutionBatchDetail: (
    scope: BroadcastScope,
    batchId: number,
  ) => Promise<BroadcastExecutionBatchSummary>;
  getExecutionTaskDetail: (
    scope: BroadcastScope,
    taskId: number,
  ) => Promise<BroadcastExecutionTaskSummary>;
  getExecutionLogsForBatch: (
    scope: BroadcastScope,
    batch: BroadcastExecutionBatchSummary,
    drafts: BroadcastDraft[],
    options?: {
      attemptsCache?: Map<number, ApiBroadcastExecutionAttempt[]>;
      evidenceCache?: Map<number, ApiBroadcastExecutionEvidence | null>;
      forceRefresh?: boolean;
    },
  ) => Promise<BroadcastExecutionLog[]>;
  listExecutionLogs: (
    scope: BroadcastScope,
    drafts: BroadcastDraft[],
  ) => Promise<BroadcastExecutionLog[]>;
}

export function createBroadcastDataSource(): BroadcastDataSource {
  const seed = createBroadcastWorkspaceSnapshot();
  const getExecutionLogsForBatch = async (
    scope: BroadcastScope,
    batch: BroadcastExecutionBatchSummary,
    drafts: BroadcastDraft[],
    options?: {
      attemptsCache?: Map<number, ApiBroadcastExecutionAttempt[]>;
      evidenceCache?: Map<number, ApiBroadcastExecutionEvidence | null>;
      forceRefresh?: boolean;
    },
  ) => {
    const attemptsCache = options?.attemptsCache;
    const evidenceCache = options?.evidenceCache;
    const forceRefresh = options?.forceRefresh ?? false;

    const logs = await Promise.all(
      batch.tasks.map(async (task) => {
        const cachedAttempts = attemptsCache?.get(task.id);
        const attempts =
          cachedAttempts && !forceRefresh
            ? cachedAttempts
            : await backendClient.getBroadcastExecutionAttempts(
                toApiScope(scope),
                task.id,
              );
        attemptsCache?.set(task.id, attempts);

        return Promise.all(
          attempts.map(async (attempt) => {
            let evidence: ApiBroadcastExecutionEvidence | null = null;
            const hasCachedEvidence = evidenceCache?.has(attempt.id) ?? false;
            const attemptTerminal = TERMINAL_ATTEMPT_STATUSES.has(
              String(attempt.status || '').toLowerCase(),
            );

            if (hasCachedEvidence && !forceRefresh) {
              evidence = evidenceCache?.get(attempt.id) ?? null;
            } else if (!attemptTerminal) {
              evidence = null;
              evidenceCache?.set(attempt.id, null);
            } else {
              try {
                evidence = await backendClient.getBroadcastExecutionEvidence(
                  toApiScope(scope),
                  attempt.id,
                );
              } catch {
                evidence = null;
              }
              evidenceCache?.set(attempt.id, evidence);
            }

            const draft =
              drafts.find((item) => item.id === task.draftId) ?? null;
            return toExecutionLog(batch, task, attempt, evidence, draft);
          }),
        );
      }),
    );

    return logs
      .flat()
      .sort((left, right) => right.timestamp.localeCompare(left.timestamp));
  };

  return {
    loadSnapshot: () => cloneValue(seed),
    loadRulesData: async (scope) => {
      const apiScope = toApiScope(scope);
      const [templates, variableProfile, groupRules, groupNames] =
        await Promise.all([
          backendClient.getBroadcastTemplates(apiScope),
          backendClient.getBroadcastVariableProfile(apiScope),
          backendClient.getBroadcastGroupRules(apiScope),
          backendClient.getBroadcastGroupNames(apiScope),
        ]);

      const mappedTemplates = templates.map(fromApiTemplate);
      const mappedVariableProfile = fromApiVariableProfile(variableProfile);

      return {
        scope,
        templates: mappedTemplates,
        variableProfile: mappedVariableProfile,
        variableMappings: buildVariableMappings(
          mappedVariableProfile,
          mappedTemplates,
        ),
        groupRules: groupRules.map(fromApiGroupRule),
        groupNames: groupNames.map(fromApiGroupName),
      };
    },
    saveVariableProfile: async (scope, profile) =>
      fromApiVariableProfile(
        await backendClient.saveBroadcastVariableProfile(
          toApiScope(scope),
          toApiVariableProfile(profile),
        ),
      ),
    createTemplate: async (scope, template) =>
      fromApiTemplate(
        await backendClient.createBroadcastTemplate(toApiScope(scope), {
          name: template.name,
          content: template.body,
          enabled: template.enabled,
        }),
      ),
    updateTemplate: async (scope, templateId, template) =>
      fromApiTemplate(
        await backendClient.updateBroadcastTemplate(
          toApiScope(scope),
          templateId,
          {
            name: template.name,
            content: template.body,
            enabled: template.enabled,
          },
        ),
      ),
    deleteTemplate: async (scope, templateId) => {
      await backendClient.deleteBroadcastTemplate(
        toApiScope(scope),
        templateId,
      );
    },
    renderTemplate: async (scope, payload) => {
      const variables = payload.variables ?? {};
      if ('templateId' in payload) {
        return fromApiTemplateRenderResult(
          await backendClient.renderBroadcastTemplate(toApiScope(scope), {
            templateId: payload.templateId,
            variables,
          }),
        );
      }
      return fromApiTemplateRenderResult(
        await backendClient.renderBroadcastTemplate(toApiScope(scope), {
          content: payload.content,
          variables,
        }),
      );
    },
    createGroupRule: async (scope, draft) =>
      fromApiGroupRule(
        await backendClient.createBroadcastGroupRule(
          toApiScope(scope),
          toApiGroupRuleDraft(draft),
        ),
      ),
    updateGroupRule: async (scope, ruleId, draft) =>
      fromApiGroupRule(
        await backendClient.updateBroadcastGroupRule(
          toApiScope(scope),
          ruleId,
          toApiGroupRuleDraft(draft),
        ),
      ),
    deleteGroupRule: async (scope, ruleId) => {
      await backendClient.deleteBroadcastGroupRule(toApiScope(scope), ruleId);
    },
    matchGroupRule: async (scope, sourceValue) =>
      fromApiGroupMatchResult(
        await backendClient.matchBroadcastGroupRule(
          toApiScope(scope),
          sourceValue,
        ),
      ),
    createGroupNames: async (scope, names) => {
      const response = await backendClient.createBroadcastGroupNames(
        toApiScope(scope),
        names,
      );
      return response.group_names.map(fromApiGroupName);
    },
    syncGroupNames: async (scope) =>
      await backendClient.syncBroadcastGroupNames(toApiScope(scope)),
    deleteGroupName: async (scope, groupNameId) => {
      await backendClient.deleteBroadcastGroupName(
        toApiScope(scope),
        groupNameId,
      );
    },
    saveDraftText: (snapshot, draftId, draftText) => ({
      ...snapshot,
      drafts: snapshot.drafts.map((draft) =>
        draft.id === draftId
          ? {
              ...draft,
              draftText,
              updatedAt: new Date().toISOString(),
            }
          : draft,
      ),
    }),
    applyDraftStatus: (snapshot, draftIds, status) => ({
      ...snapshot,
      drafts: snapshot.drafts.map((draft) =>
        draftIds.includes(draft.id) ? updateDraftStatus(draft, status) : draft,
      ),
    }),
    appendLogs: (snapshot, entries) => ({
      ...snapshot,
      executionLogs: [...entries, ...snapshot.executionLogs],
    }),
    listImportBatches: async (scope) =>
      (await backendClient.getBroadcastImportBatches(toApiScope(scope))).map(
        fromApiImportBatch,
      ),
    uploadImport: async (scope, file, options) =>
      fromApiImportBatch(
        await backendClient.uploadBroadcastImport(toApiScope(scope), file, {
          group_field_override: options?.groupFieldOverride,
        }),
      ),
    getImportDetail: async (scope, importId, filters) =>
      fromApiImportDetail(
        await backendClient.getBroadcastImportDetail(
          toApiScope(scope),
          importId,
          {
            match_status:
              filters?.matchStatus &&
              filters.matchStatus !== 'all' &&
              filters.matchStatus !== 'conflict'
                ? filters.matchStatus
                : undefined,
            keyword: filters?.keyword,
            page: filters?.page,
            page_size: filters?.pageSize,
          },
        ),
      ),
    getImportGroups: async (scope, importId, filters) =>
      fromApiImportGroups(
        await backendClient.getBroadcastImportGroups(
          toApiScope(scope),
          importId,
          {
            match_status:
              filters?.matchStatus && filters.matchStatus !== 'all'
                ? filters.matchStatus
                : undefined,
            keyword: filters?.keyword,
            page: filters?.page,
            page_size: filters?.pageSize,
          },
        ),
      ),
    getImportGroupRuleCandidates: async (scope, importId, filters) =>
      fromApiImportGroupRuleCandidates(
        await backendClient.getBroadcastImportGroupRuleCandidates(
          toApiScope(scope),
          importId,
          {
            status: filters?.status,
            keyword: filters?.keyword,
            page: filters?.page,
            page_size: filters?.pageSize,
          },
        ),
      ),
    updateImportGroupTemplateAssignments: async (scope, importId, items) => {
      const response =
        await backendClient.updateBroadcastImportGroupTemplateAssignments(
          toApiScope(scope),
          importId,
          items.map((item) => ({
            group_key: item.groupKey,
            template_id: item.templateId,
          })),
        );
      return response.items.map((item) => ({
        groupKey: item.group_key,
        templateId: item.template_id,
      }));
    },
    getImportGroupRows: async (scope, importId, groupKey, filters) =>
      fromApiImportGroupRows(
        await backendClient.getBroadcastImportGroupRows(
          toApiScope(scope),
          importId,
          groupKey,
          {
            page: filters?.page,
            page_size: filters?.pageSize,
          },
        ),
      ),
    uploadImportGroupAttachments: async (scope, importId, groupKey, files) =>
      (
        (await backendClient.uploadBroadcastImportGroupAttachments(
          toApiScope(scope),
          importId,
          groupKey,
          files,
        )) ?? []
      ).map(fromApiAttachment),
    deleteImportGroupAttachment: async (
      scope,
      importId,
      groupKey,
      attachmentId,
    ) =>
      (
        (await backendClient.deleteBroadcastImportGroupAttachment(
          toApiScope(scope),
          importId,
          groupKey,
          attachmentId,
        )) ?? []
      ).map(fromApiAttachment),
    deleteImport: async (scope, importId) => {
      await backendClient.deleteBroadcastImport(toApiScope(scope), importId);
    },
    rematchImport: async (scope, importId) =>
      fromApiImportDetail(
        await backendClient.rematchBroadcastImport(toApiScope(scope), importId),
      ),
    bulkAssignImportGroupRules: async (scope, importId, items) =>
      fromApiBulkAssignResult(
        await backendClient.bulkAssignBroadcastImportGroupRules(
          toApiScope(scope),
          importId,
          items.map((item) => ({
            group_key: item.groupKey,
            target_conversation_id: item.targetConversationId,
          })),
        ),
      ),
    generateImportDrafts: async (scope, importId, payload) => {
      const response = await backendClient.generateBroadcastImportDrafts(
        toApiScope(scope),
        importId,
        {
          template_id: payload.templateId,
          group_keys: payload.groupKeys,
          overwrite_existing: payload.overwriteExisting,
        },
      );
      return {
        totalGroupCount: response.total_group_count,
        pendingReviewCount: response.pending_review_count,
        invalidCount: response.invalid_count,
        unmatchedGroupCount: response.unmatched_group_count,
        createdCount: response.created_count ?? 0,
        updatedCount: response.updated_count ?? 0,
        generatedGroupKeys: response.generated_group_keys ?? [],
        draftIds: response.draft_ids ?? [],
        draftResults: (response.draft_results ?? []).map((item) => ({
          groupKey: item.group_key,
          draftId: item.draft_id,
          operation: item.operation,
          modifiedFields: item.modified_fields ?? [],
        })),
      };
    },
    listDrafts: async (scope, filters) =>
      (
        await backendClient.getBroadcastDrafts(toApiScope(scope), {
          import_batch_id: filters?.importBatchId,
          status:
            filters?.status && filters.status !== 'all'
              ? filters.status
              : undefined,
          keyword: filters?.keyword,
        })
      ).map(fromApiDraft),
    getDraftDetail: async (scope, draftId) =>
      fromApiDraft(
        await backendClient.getBroadcastDraftDetail(toApiScope(scope), draftId),
      ),
    uploadDraftAttachments: async (scope, draftId, files) =>
      fromApiDraft(
        await backendClient.uploadBroadcastDraftAttachments(
          toApiScope(scope),
          draftId,
          files,
        ),
      ),
    deleteDraftAttachment: async (scope, draftId, attachmentId) =>
      fromApiDraft(
        await backendClient.deleteBroadcastDraftAttachment(
          toApiScope(scope),
          draftId,
          attachmentId,
        ),
      ),
    updateDraftText: async (scope, draftId, draftText) =>
      fromApiDraft(
        await backendClient.updateBroadcastDraftText(
          toApiScope(scope),
          draftId,
          draftText,
        ),
      ),
    updateDraftStatuses: async (scope, draftIds, status) => {
      const response = await backendClient.updateBroadcastDraftStatuses(
        toApiScope(scope),
        draftIds,
        status,
      );
      return {
        updatedCount: response.updated_count,
      };
    },
    createExecutionBatch: async (scope, draftIds, mode, operator, options) =>
      fromApiExecutionBatch(
        await backendClient.createBroadcastExecutionBatch(toApiScope(scope), {
          draft_ids: draftIds,
          mode,
          operator,
          allow_sent_rewrite: options?.allowSentRewrite,
        }),
      ),
    startExecutionBatch: async (scope, batchId, operator) =>
      fromApiExecutionBatch(
        await backendClient.startBroadcastExecutionBatch(
          toApiScope(scope),
          batchId,
          operator,
        ),
      ),
    pauseExecutionBatch: async (scope, batchId, operator) =>
      fromApiExecutionBatch(
        await backendClient.pauseBroadcastExecutionBatch(
          toApiScope(scope),
          batchId,
          operator,
        ),
      ),
    resumeExecutionBatch: async (scope, batchId, operator) =>
      fromApiExecutionBatch(
        await backendClient.resumeBroadcastExecutionBatch(
          toApiScope(scope),
          batchId,
          operator,
        ),
      ),
    cancelExecutionBatch: async (scope, batchId, operator) =>
      fromApiExecutionBatch(
        await backendClient.cancelBroadcastExecutionBatch(
          toApiScope(scope),
          batchId,
          operator,
        ),
      ),
    listExecutionBatches: async (scope) =>
      (await backendClient.getBroadcastExecutionBatches(toApiScope(scope))).map(
        fromApiExecutionBatch,
      ),
    startExecutionTask: async (scope, taskId, operator) =>
      fromApiExecutionTask(
        await backendClient.startBroadcastExecutionTask(
          toApiScope(scope),
          taskId,
          operator,
        ),
      ),
    retryExecutionTask: async (scope, taskId, operator) =>
      fromApiExecutionTask(
        await backendClient.retryBroadcastExecutionTask(
          toApiScope(scope),
          taskId,
          operator,
        ),
      ),
    getExecutorCapabilities: async (scope) =>
      fromApiExecutorCapability(
        await backendClient.getBroadcastExecutorCapabilities(toApiScope(scope)),
      ),
    getExecutorHealth: async (scope) =>
      fromApiExecutorHealth(
        await backendClient.getBroadcastExecutorHealth(toApiScope(scope)),
      ),
    getExecutionBatchDetail: async (scope, batchId) =>
      fromApiExecutionBatch(
        await backendClient.getBroadcastExecutionBatchDetail(
          toApiScope(scope),
          batchId,
        ),
      ),
    getExecutionTaskDetail: async (scope, taskId) =>
      fromApiExecutionTask(
        await backendClient.getBroadcastExecutionTaskDetail(
          toApiScope(scope),
          taskId,
        ),
      ),
    getExecutionLogsForBatch,
    listExecutionLogs: async (scope, drafts) => {
      const batchSummaries = await backendClient.getBroadcastExecutionBatches(
        toApiScope(scope),
      );
      const batches = await Promise.all(
        batchSummaries.map(async (batch) =>
          fromApiExecutionBatch(
            await backendClient.getBroadcastExecutionBatchDetail(
              toApiScope(scope),
              batch.id,
            ),
          ),
        ),
      );
      const attemptsCache = new Map<number, ApiBroadcastExecutionAttempt[]>();
      const evidenceCache = new Map<
        number,
        ApiBroadcastExecutionEvidence | null
      >();
      const logs = await Promise.all(
        batches.map((batch) =>
          getExecutionLogsForBatch(scope, batch, drafts, {
            attemptsCache,
            evidenceCache,
          }),
        ),
      );
      return logs
        .flat()
        .sort((left, right) => right.timestamp.localeCompare(left.timestamp));
    },
  };
}

export const broadcastPasteOnlyAdapter: BroadcastPasteOnlyAdapter = {
  toRuntimePayload: (
    request: BroadcastPasteDraftRequest,
    requestDigest: string,
  ): BroadcastRuntimePasteDraftPayload => ({
    action: 'paste_draft',
    conversationName: request.conversationName,
    draftText: request.draftText,
    idempotencyKey: request.idempotencyKey,
    requestDigest,
  }),
};

export function applyRulesDataToSnapshot(
  snapshot: BroadcastWorkspaceSnapshot,
  rulesData: BroadcastRulesData,
  importDetail?: BroadcastImportDetail | null,
): BroadcastWorkspaceSnapshot {
  const seedDraft = snapshot.drafts[0];
  const template = rulesData.templates[0];
  const variableMappings = buildVariableMappings(
    rulesData.variableProfile,
    rulesData.templates,
    importDetail,
  );
  const variableMap = buildTemplatePreviewVariables(variableMappings);

  const hydratedDrafts = snapshot.drafts.map((draft) => ({
    ...draft,
    botUuid: rulesData.scope.botUuid,
    connectorId: rulesData.scope.connectorId,
    templateName: template?.name ?? draft.templateName,
    draftText:
      draft.id === seedDraft?.id && template
        ? template.body.replaceAll(
            /{{\s*([A-Za-z0-9_\-\u4e00-\u9fff]+)\s*}}/g,
            (token, key: string) => variableMap[key] || token,
          )
        : draft.draftText,
  }));

  return {
    ...snapshot,
    scope: rulesData.scope,
    templates: rulesData.templates,
    variableProfile: rulesData.variableProfile,
    variableMappings,
    groupRules: rulesData.groupRules,
    groupNames: rulesData.groupNames,
    drafts: hydratedDrafts,
  };
}
