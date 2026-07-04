import { backendClient } from '@/app/infra/http';
import type {
  ApiBroadcastDraft,
  ApiBroadcastExecutionAttempt,
  ApiBroadcastExecutionBatch,
  ApiBroadcastExecutionEvidence,
  ApiBroadcastExecutionTask,
  ApiBroadcastGroupMatchResult,
  ApiBroadcastGroupName,
  ApiBroadcastGroupNameSyncResult,
  ApiBroadcastGroupRule,
  ApiBroadcastImportBatch,
  ApiBroadcastImportDetail,
  ApiBroadcastImportDraftGenerationResult,
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
  BroadcastDraft,
  BroadcastDraftDetail,
  BroadcastExecutionBatchSummary,
  BroadcastExecutorCapability,
  BroadcastExecutorHealth,
  BroadcastExecutionLog,
  BroadcastSendConfirmation,
  BroadcastExecutionTaskSummary,
  BroadcastDraftFilters,
  BroadcastDraftStatus,
  BroadcastDraftStatusUpdateResult,
  BroadcastGroupMatchResult,
  BroadcastGroupName,
  BroadcastGroupNameSyncResult,
  BroadcastGroupRule,
  BroadcastGroupRuleDraft,
  BroadcastImportBatch,
  BroadcastImportDetail,
  BroadcastImportDraftGenerationResult,
  BroadcastImportFilters,
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

function fromApiTemplate(template: ApiBroadcastTemplate): BroadcastMessageTemplate {
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
    targetConversationName: result.target_conversation_name,
    matchType: result.match_type,
  };
}

function fromApiGroupName(groupName: ApiBroadcastGroupName): BroadcastGroupName {
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

function fromApiImportBatch(batch: ApiBroadcastImportBatch): BroadcastImportBatch {
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
    createdAt: batch.created_at,
    updatedAt: batch.updated_at,
  };
}

function fromApiImportDetail(detail: ApiBroadcastImportDetail): BroadcastImportDetail {
  return {
    ...fromApiImportBatch(detail),
    rows: detail.rows.map(fromApiImportRow),
  };
}

function fromApiDraft(draft: ApiBroadcastDraft): BroadcastDraftDetail {
  return {
    id: draft.id,
    botUuid: draft.bot_uuid,
    connectorId: draft.connector_id,
    importBatchId: draft.import_batch_id,
    groupValue: draft.group_value,
    customerName: draft.group_value,
    conversationName: draft.target_conversation_name ?? '',
    templateId: draft.template_id,
    templateName: draft.template_name_snapshot,
    templateContentSnapshot: draft.template_content_snapshot,
    renderVariables: draft.render_variables,
    draftText: draft.draft_text,
    status: draft.status,
    errorMessage: draft.error_message,
    draftsStale: draft.drafts_stale,
    updatedAt: draft.updated_at,
    createdAt: draft.created_at,
    message: draft.message ?? null,
    progressLabel: BROADCAST_STATUS_LABELS[draft.status],
    operator: '',
  };
}

function fromApiExecutionTask(task: ApiBroadcastExecutionTask): BroadcastExecutionTaskSummary {
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
  };
}

function fromApiExecutionBatch(batch: ApiBroadcastExecutionBatch): BroadcastExecutionBatchSummary {
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
  };
}

function fromApiExecutorCapability(payload: Record<string, unknown>): BroadcastExecutorCapability {
  return {
    channel: String(payload.channel || 'wxwork_database'),
    supports_paste: Boolean(payload.supports_paste),
    supports_send: Boolean(payload.supports_send),
    supports_cancel: Boolean(payload.supports_cancel),
    supports_status_query: Boolean(payload.supports_status_query),
    supports_clipboard_restore: Boolean(payload.supports_clipboard_restore),
    supports_evidence: Boolean(payload.supports_evidence),
    executor_version: String(payload.executor_version || ''),
    runtime_min_version: String(payload.runtime_min_version || ''),
  };
}

function fromApiExecutorHealth(payload: Record<string, unknown>): BroadcastExecutorHealth {
  return {
    channel: String(payload.channel || 'wxwork_database'),
    status: String(payload.status || 'unknown'),
    protocol_version: payload.protocol_version ? String(payload.protocol_version) : null,
    runtime_version: payload.runtime_version ? String(payload.runtime_version) : null,
    capability: fromApiExecutorCapability((payload.capability as Record<string, unknown>) || {}),
    runtime_status: (payload.runtime_status as Record<string, unknown>) || null,
  };
}

function fromApiSendConfirmation(
  payload: { id: number; token: string; expires_at: string | null; execution_task_id: number },
): BroadcastSendConfirmation {
  return {
    id: payload.id,
    token: payload.token,
    expiresAt: payload.expires_at,
    executionTaskId: payload.execution_task_id,
  };
}

function toExecutionLog(
  batch: BroadcastExecutionBatchSummary,
  task: BroadcastExecutionTaskSummary,
  attempt: ApiBroadcastExecutionAttempt,
  evidence: ApiBroadcastExecutionEvidence | null,
  draft?: BroadcastDraft | null,
): BroadcastExecutionLog {
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
    message: evidence?.evidence_summary || task.errorMessage || attempt.error_message || task.status,
    runtimeState: evidence?.runtime_state || null,
    sendTriggered: evidence?.send_triggered || false,
    inputLocated: evidence?.input_located || false,
    draftWritten: evidence?.draft_written || false,
    clipboardRestored: evidence?.clipboard_restored || false,
    technicalDetails: evidence?.technical_details || null,
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
  listImportBatches: (
    scope: BroadcastScope,
  ) => Promise<BroadcastImportBatch[]>;
  uploadImport: (
    scope: BroadcastScope,
    file: File,
  ) => Promise<BroadcastImportDetail>;
  getImportDetail: (
    scope: BroadcastScope,
    importId: number,
    filters?: BroadcastImportFilters,
  ) => Promise<BroadcastImportDetail>;
  deleteImport: (scope: BroadcastScope, importId: number) => Promise<void>;
  rematchImport: (
    scope: BroadcastScope,
    importId: number,
  ) => Promise<BroadcastImportDetail>;
  generateImportDrafts: (
    scope: BroadcastScope,
    importId: number,
    templateId: number,
  ) => Promise<BroadcastImportDraftGenerationResult>;
  listDrafts: (
    scope: BroadcastScope,
    filters?: BroadcastDraftFilters,
  ) => Promise<BroadcastDraft[]>;
  getDraftDetail: (
    scope: BroadcastScope,
    draftId: number,
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
  sendExecutionTask: (
    scope: BroadcastScope,
    taskId: number,
    confirmationToken: string,
    operator: string,
  ) => Promise<BroadcastExecutionTaskSummary>;
  getExecutorCapabilities: (
    scope: BroadcastScope,
  ) => Promise<BroadcastExecutorCapability>;
  getExecutorHealth: (
    scope: BroadcastScope,
  ) => Promise<BroadcastExecutorHealth>;
  createSendConfirmation: (
    scope: BroadcastScope,
    taskId: number,
    operator: string,
  ) => Promise<BroadcastSendConfirmation>;
  getExecutionBatchDetail: (
    scope: BroadcastScope,
    batchId: number,
  ) => Promise<BroadcastExecutionBatchSummary>;
  getExecutionTaskDetail: (
    scope: BroadcastScope,
    taskId: number,
  ) => Promise<BroadcastExecutionTaskSummary>;
  listExecutionLogs: (
    scope: BroadcastScope,
    drafts: BroadcastDraft[],
  ) => Promise<BroadcastExecutionLog[]>;
}

export function createBroadcastDataSource(): BroadcastDataSource {
  const seed = createBroadcastWorkspaceSnapshot();

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
        await backendClient.updateBroadcastTemplate(toApiScope(scope), templateId, {
          name: template.name,
          content: template.body,
          enabled: template.enabled,
        }),
      ),
    deleteTemplate: async (scope, templateId) => {
      await backendClient.deleteBroadcastTemplate(toApiScope(scope), templateId);
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
      (
        await backendClient.getBroadcastImportBatches(toApiScope(scope))
      ).map(fromApiImportBatch),
    uploadImport: async (scope, file) =>
      fromApiImportDetail(
        await backendClient.uploadBroadcastImport(toApiScope(scope), file),
      ),
    getImportDetail: async (scope, importId, filters) =>
      fromApiImportDetail(
        await backendClient.getBroadcastImportDetail(toApiScope(scope), importId, {
          match_status:
            filters?.matchStatus && filters.matchStatus !== 'all'
              ? filters.matchStatus
              : undefined,
          keyword: filters?.keyword,
          page: filters?.page,
          page_size: filters?.pageSize,
        }),
      ),
    deleteImport: async (scope, importId) => {
      await backendClient.deleteBroadcastImport(toApiScope(scope), importId);
    },
    rematchImport: async (scope, importId) =>
      fromApiImportDetail(
        await backendClient.rematchBroadcastImport(toApiScope(scope), importId),
      ),
    generateImportDrafts: async (scope, importId, templateId) => {
      const response = await backendClient.generateBroadcastImportDrafts(
        toApiScope(scope),
        importId,
        templateId,
      );
      return {
        totalGroupCount: response.total_group_count,
        pendingReviewCount: response.pending_review_count,
        invalidCount: response.invalid_count,
        unmatchedGroupCount: response.unmatched_group_count,
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
    createExecutionBatch: async (scope, draftIds, mode, operator) =>
      fromApiExecutionBatch(
        await backendClient.createBroadcastExecutionBatch(toApiScope(scope), {
          draft_ids: draftIds,
          mode,
          operator,
        }),
      ),
    startExecutionBatch: async (scope, batchId, operator) =>
      fromApiExecutionBatch(
        await backendClient.startBroadcastExecutionBatch(toApiScope(scope), batchId, operator),
      ),
    pauseExecutionBatch: async (scope, batchId, operator) =>
      fromApiExecutionBatch(
        await backendClient.pauseBroadcastExecutionBatch(toApiScope(scope), batchId, operator),
      ),
    resumeExecutionBatch: async (scope, batchId, operator) =>
      fromApiExecutionBatch(
        await backendClient.resumeBroadcastExecutionBatch(toApiScope(scope), batchId, operator),
      ),
    cancelExecutionBatch: async (scope, batchId, operator) =>
      fromApiExecutionBatch(
        await backendClient.cancelBroadcastExecutionBatch(toApiScope(scope), batchId, operator),
      ),
    listExecutionBatches: async (scope) =>
      (
        await backendClient.getBroadcastExecutionBatches(toApiScope(scope))
      ).map(fromApiExecutionBatch),
    startExecutionTask: async (scope, taskId, operator) =>
      fromApiExecutionTask(
        await backendClient.startBroadcastExecutionTask(toApiScope(scope), taskId, operator),
      ),
    retryExecutionTask: async (scope, taskId, operator) =>
      fromApiExecutionTask(
        await backendClient.retryBroadcastExecutionTask(toApiScope(scope), taskId, operator),
      ),
    sendExecutionTask: async (scope, taskId, confirmationToken, operator) =>
      fromApiExecutionTask(
        await backendClient.sendBroadcastExecutionTask(toApiScope(scope), taskId, {
          confirmation_token: confirmationToken,
          operator,
        }),
      ),
    getExecutorCapabilities: async (scope) =>
      fromApiExecutorCapability(
        await backendClient.getBroadcastExecutorCapabilities(toApiScope(scope)),
      ),
    getExecutorHealth: async (scope) =>
      fromApiExecutorHealth(
        await backendClient.getBroadcastExecutorHealth(toApiScope(scope)),
      ),
    createSendConfirmation: async (scope, taskId, operator) =>
      fromApiSendConfirmation(
        await backendClient.createBroadcastSendConfirmation(toApiScope(scope), {
          execution_task_id: taskId,
          operator,
        }),
      ),
    getExecutionBatchDetail: async (scope, batchId) =>
      fromApiExecutionBatch(
        await backendClient.getBroadcastExecutionBatchDetail(toApiScope(scope), batchId),
      ),
    getExecutionTaskDetail: async (scope, taskId) =>
      fromApiExecutionTask(
        await backendClient.getBroadcastExecutionTaskDetail(toApiScope(scope), taskId),
      ),
    listExecutionLogs: async (scope, drafts) => {
      const batchSummaries = await backendClient.getBroadcastExecutionBatches(toApiScope(scope));
      const batches = await Promise.all(
        batchSummaries.map(async (batch) =>
          fromApiExecutionBatch(
            await backendClient.getBroadcastExecutionBatchDetail(toApiScope(scope), batch.id),
          ),
        ),
      );
      const logs = await Promise.all(
        batches.flatMap((batch) =>
          batch.tasks.map(async (task) => {
            const attempts = await backendClient.getBroadcastExecutionAttempts(
              toApiScope(scope),
              task.id,
            );
            return Promise.all(
              attempts.map(async (attempt) => {
                let evidence: ApiBroadcastExecutionEvidence | null = null;
                try {
                  evidence = await backendClient.getBroadcastExecutionEvidence(
                    toApiScope(scope),
                    attempt.id,
                  );
                } catch {
                  evidence = null;
                }
                const draft = drafts.find((item) => item.id === task.draftId) ?? null;
                return toExecutionLog(batch, task, attempt, evidence, draft);
              }),
            );
          }),
        ),
      );
      return logs.flat(2).sort((left, right) =>
        right.timestamp.localeCompare(left.timestamp),
      );
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
