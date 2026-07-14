export type BroadcastTopTab = 'rules' | 'import' | 'drafts' | 'logs';

export type BroadcastRulesTab = 'variables' | 'templates' | 'groups';

export type BroadcastImportBatchStatus =
  | 'imported'
  | 'matched'
  | 'drafts_generated';

export type BroadcastImportMatchStatus = 'matched' | 'unmatched' | 'invalid';
export type BroadcastImportGroupMatchStatus =
  | BroadcastImportMatchStatus
  | 'conflict';

export type BroadcastImportGroupFieldSource =
  | 'configured'
  | 'auto_detected'
  | 'user_confirmed'
  | 'legacy_fallback';

export type BroadcastDraftStatus = 'pending' | 'sent' | 'unknown' | 'invalid';

export type BroadcastStatus =
  | BroadcastDraftStatus
  | 'pending'
  | 'pasted'
  | 'failed'
  | 'completed';

export type BroadcastStatusFilter = 'all' | 'pending' | 'unknown' | 'sent';

export type BroadcastMergeMode =
  | 'first'
  | 'lines'
  | 'unique_lines'
  | 'commas'
  | 'unique_commas';

export type BroadcastGroupMatchType = 'exact' | 'contains' | 'regex';

export interface BroadcastScope {
  botUuid: string;
  connectorId: string;
}

export interface BroadcastVariableMappingRule {
  sourceField: string;
  variableKey: string;
  mergeMode: BroadcastMergeMode;
  order: number;
}

export interface BroadcastVariableProfile {
  groupField: string | null;
  mappingRules: BroadcastVariableMappingRule[];
}

export type BroadcastVariableSampleState = 'no_import' | 'no_value' | 'ready';

export interface BroadcastVariableMapping extends BroadcastVariableMappingRule {
  id: number;
  sampleValue: string;
  sampleState: BroadcastVariableSampleState;
  required: boolean;
}

export interface BroadcastMessageTemplate {
  id: number;
  name: string;
  updatedAt: string;
  variableKeys: string[];
  body: string;
  enabled: boolean;
}

export interface BroadcastTemplateDraft {
  id?: number;
  name: string;
  body: string;
  enabled: boolean;
}

export interface BroadcastTemplateRenderResult {
  renderedText: string;
  requiredVariables: string[];
  missingVariables: string[];
  valid: boolean;
}

export interface BroadcastGroupRule {
  id: number;
  sourceValue: string;
  matchType: BroadcastGroupMatchType;
  matchExpression: string;
  targetConversationId?: string | null;
  targetConversationName: string;
  priority: number;
  enabled: boolean;
  invalidLegacy?: boolean;
  invalidReason?: string | null;
  targetResolutionStatus?: 'deferred' | 'resolved' | 'unresolved' | 'ambiguous';
  updatedAt: string;
}

export interface BroadcastGroupRuleDraft {
  id?: number;
  sourceValue: string;
  matchType: BroadcastGroupMatchType;
  matchExpression: string;
  targetConversationId: string;
  targetConversationName: string;
  priority: number;
  enabled: boolean;
}

export interface BroadcastGroupMatchResult {
  matched: boolean;
  ruleId: number | null;
  matchedRuleId: number | null;
  sourceValue: string;
  targetConversationId?: string | null;
  targetConversationName: string | null;
  matchType: BroadcastGroupMatchType | null;
  candidateCount: number;
  candidateRules: BroadcastGroupRuleSummary[];
  conflict: boolean;
  reason: string | null;
}

export type BroadcastGroupRuleSummary = BroadcastGroupRule;

export interface BroadcastGroupName {
  id: number;
  name: string;
  externalConversationId?: string | null;
  updatedAt: string;
}

export interface BroadcastGroupNameSyncResult {
  scanned: number;
  inserted: number;
  updated: number;
  unchanged: number;
  skipped: number;
  errors: string[];
}

export interface BroadcastImportPreviewRow {
  id: number;
  sourceRowNumber: number;
  groupValue: string | null;
  rawData: Record<string, string>;
  matchedConversationName: string | null;
  matchedRuleId: number | null;
  matchStatus: BroadcastImportMatchStatus;
  errorMessage: string | null;
  customerName: string;
  conversationId?: string | null;
  conversationName: string;
  targetResolutionStatus?: 'deferred';
  templateName: string;
  variableSummary: string;
  status: BroadcastStatus;
  matchedRule: string;
}

export interface BroadcastImportBatch {
  id: number;
  originalFileName: string;
  fileType: string;
  worksheetName: string | null;
  status: BroadcastImportBatchStatus;
  draftsStale: boolean;
  totalRows: number;
  validRows: number;
  invalidRows: number;
  matchedRows: number;
  unmatchedRows: number;
  groupFieldUsed?: string | null;
  groupFieldSource?: BroadcastImportGroupFieldSource | null;
  createdAt: string;
  updatedAt: string;
}

export interface BroadcastImportDetail extends BroadcastImportBatch {
  rows: BroadcastImportPreviewRow[];
  page: number;
  pageSize: number;
  total: number;
  totalPages: number;
}

export interface BroadcastAttachment {
  id: number;
  attachmentAssetId: number;
  originalName: string;
  sizeBytes: number;
  sha256: string;
  extension: string;
  mimeType: string;
  sortOrder: number;
}

export interface BroadcastImportGroupSummary {
  groupKey: string;
  groupValue: string;
  rawRowCount: number;
  distinctOrderNumberCount: number;
  matchedConversationId?: string | null;
  matchedConversationName: string | null;
  matchStatus: BroadcastImportGroupMatchStatus;
  reason: string | null;
  attachmentCount: number;
  expandable: boolean;
  firstSourceRowNumber: number;
  templateId?: number | null;
  templateName?: string | null;
  templateEnabled?: boolean | null;
  attachments?: BroadcastAttachment[];
}

export interface BroadcastImportGroupRowsPage {
  groupKey: string;
  groupValue: string | null;
  page: number;
  pageSize: number;
  total: number;
  totalPages: number;
  rows: BroadcastImportPreviewRow[];
}

export interface BroadcastImportGroupList {
  page: number;
  pageSize: number;
  total: number;
  totalPages: number;
  rawRowTotal: number;
  groupTotal: number;
  matchedGroupTotal: number;
  unmatchedGroupTotal: number;
  invalidGroupTotal: number;
  conflictGroupTotal: number;
  orderNumberFieldConfigured: boolean;
  groups: BroadcastImportGroupSummary[];
}

export interface BroadcastImportGroupFieldConfirmationDetails {
  headers: string[];
  candidates: string[];
  configuredGroupField: string | null;
  originalFileName: string;
}

export type BroadcastGroupRuleCandidateStatus =
  | 'new'
  | 'configured'
  | 'needs_repair'
  | 'conflict'
  | 'invalid';

export interface BroadcastGroupRuleCandidateItem {
  groupKey: string;
  customerName: string;
  rawRowCount: number;
  status: BroadcastGroupRuleCandidateStatus;
  reason: string | null;
  existingRuleIds: number[];
  existingRules: BroadcastGroupRuleSummary[];
  currentMatchedRule: BroadcastGroupRuleSummary | null;
  currentTargetConversationId?: string | null;
  currentTargetConversationName: string | null;
  currentMatchType: BroadcastGroupMatchType | null;
}

export interface BroadcastGroupRuleCandidateList {
  importBatchId: number;
  groupFieldUsed: string;
  groupFieldSource: BroadcastImportGroupFieldSource;
  rawRowTotal: number;
  uniqueCustomerTotal: number;
  stats: {
    newCount: number;
    configuredCount: number;
    needsRepairCount: number;
    conflictCount: number;
    invalidCount: number;
  };
  items: BroadcastGroupRuleCandidateItem[];
  page: number;
  pageSize: number;
  total: number;
  totalPages: number;
}

export interface BroadcastBulkAssignResultItem {
  groupKey: string;
  customerName: string;
  ruleId: number;
  targetConversationId: string;
  targetConversationName: string;
}

export interface BroadcastBulkAssignResult {
  createdCount: number;
  groupFieldUsed: string;
  groupFieldSource: BroadcastImportGroupFieldSource;
  items: BroadcastBulkAssignResultItem[];
}

export interface BroadcastImportFilters {
  matchStatus?: BroadcastImportGroupMatchStatus | 'all';
  keyword?: string;
  page?: number;
  pageSize?: number;
}

export interface BroadcastImportDraftGenerationResult {
  totalGroupCount: number;
  pendingReviewCount: number;
  invalidCount: number;
  unmatchedGroupCount: number;
  createdCount?: number;
  updatedCount?: number;
  generatedGroupKeys?: string[];
  draftIds?: number[];
  draftResults?: BroadcastImportDraftGenerationItem[];
}

export interface BroadcastImportDraftGenerationItem {
  groupKey: string;
  draftId: number;
  operation: 'created' | 'updated';
  modifiedFields: string[];
}

export interface BroadcastDraft {
  id: number;
  botUuid: string;
  connectorId: string;
  importBatchId?: number;
  groupValue: string;
  customerName: string;
  conversationId?: string | null;
  conversationName: string;
  templateId?: number | null;
  templateName: string;
  templateContentSnapshot?: string;
  renderVariables?: Record<string, string>;
  status: BroadcastStatus;
  draftText: string;
  errorMessage?: string | null;
  sendStatus?: 'pending' | 'sent' | 'unknown';
  sentAt?: string | null;
  legacyStatus?: string | null;
  draftsStale?: boolean;
  attachmentsStale?: boolean;
  attachments?: BroadcastAttachment[];
  updatedAt: string;
  progressLabel: string;
  operator: string;
}

export interface BroadcastDraftDetail extends BroadcastDraft {
  createdAt?: string;
  message?: string | null;
}

export interface BroadcastDraftFilters {
  importBatchId?: number;
  status?: BroadcastStatusFilter;
  keyword?: string;
}

export interface BroadcastDraftStatusUpdateResult {
  updatedCount: number;
}

export interface BroadcastExecutionLog {
  id: number;
  batchId: number;
  taskId: number;
  attemptId: number;
  draftId: number | null;
  customerName: string;
  conversationId?: string | null;
  conversationName: string;
  batchStatus: string;
  taskStatus: string;
  attemptStatus: string;
  action: string;
  message: string;
  runtimeState: string | null;
  sendTriggered: boolean;
  inputLocated: boolean;
  draftWritten: boolean;
  contentVerified?: boolean;
  textContentVerified?: boolean;
  clipboardRestored: boolean;
  attachmentCount?: number;
  attachmentNames?: string[];
  attachmentsPrepared?: boolean;
  attachmentPasteRequested?: boolean;
  attachmentsVerified?: boolean;
  warning?: string | null;
  errorCode?: string | null;
  stage?: string | null;
  technicalDetails: Record<string, unknown> | null;
  timestamp: string;
}

export interface BroadcastExecutionTaskSummary {
  id: number;
  executionBatchId: number;
  draftId: number | null;
  targetConversationSnapshot: string;
  draftTextSnapshot: string;
  action: string;
  status: string;
  attemptCount: number;
  idempotencyKey: string;
  runtimeTaskId: string | null;
  errorCode: string | null;
  errorMessage: string | null;
  createdAt: string;
  startedAt: string | null;
  finishedAt: string | null;
  updatedAt: string;
  retryAllowed?: boolean;
  sendOutcome?: 'sent' | 'failed' | 'unknown' | 'skipped' | null;
  enterDispatched?: boolean | null;
  messageSent?: boolean | null;
  terminalConfirmed?: boolean | null;
  terminalSource?: string | null;
  attachments: BroadcastAttachment[];
}

export interface BroadcastSendBatchItem {
  draftId: number | null;
  outcome: 'sent' | 'failed' | 'unknown' | 'skipped';
  errorCode: string | null;
  errorMessage: string | null;
  enterDispatched: boolean | null;
  messageSent?: boolean | null;
  terminalConfirmed?: boolean | null;
  terminalSource?: string | null;
  startedAt: string | null;
  completedAt: string | null;
}

export interface BroadcastExecutionBatchSummary {
  id: number;
  status: string;
  mode: string;
  totalTasks: number;
  pendingTasks: number;
  runningTasks: number;
  succeededTasks: number;
  failedTasks: number;
  cancelledTasks: number;
  interruptedTasks: number;
  createdBy: string;
  lastActionBy: string | null;
  createdAt: string;
  startedAt: string | null;
  finishedAt: string | null;
  tasks: BroadcastExecutionTaskSummary[];
  totalCount?: number;
  sentCount?: number;
  failedCount?: number;
  unknownCount?: number;
  skippedCount?: number;
  duplicateTargetCount?: number;
  items?: BroadcastSendBatchItem[];
}

export interface BroadcastExecutorCapability {
  channel: string;
  supports_paste: boolean;
  supports_paste_verification?: boolean;
  supports_post_send_verification?: boolean;
  supports_send: boolean;
  supports_cancel: boolean;
  supports_status_query: boolean;
  supports_clipboard_restore: boolean;
  supports_evidence: boolean;
  requires_manual_conversation_open?: boolean;
  executor_version: string;
  runtime_min_version: string;
  conversation_locator?: 'keyboard_search' | 'external_id' | 'unknown';
  content_verification?: 'disabled' | 'manual' | 'windows_uia' | 'unknown';
  post_send_verification?: 'available' | 'unavailable' | 'unknown';
}

export interface BroadcastExecutorHealth {
  available: boolean;
  channel: string;
  status: string;
  protocol_version?: string | null;
  runtime_version?: string | null;
  error_code?: string | null;
  error_message?: string | null;
  capability: BroadcastExecutorCapability;
  runtime_status?: Record<string, unknown> | null;
}

export interface BroadcastExecutionRequestStats {
  executions: number;
  starts: number;
  retries: number;
}

export interface BroadcastWorkspaceSnapshot {
  scope: BroadcastScope;
  templates: BroadcastMessageTemplate[];
  variableProfile: BroadcastVariableProfile;
  variableMappings: BroadcastVariableMapping[];
  groupRules: BroadcastGroupRule[];
  groupNames: BroadcastGroupName[];
  importPreviewRows: BroadcastImportPreviewRow[];
  drafts: BroadcastDraft[];
  executionLogs: BroadcastExecutionLog[];
}

export interface BroadcastPasteDraftRequest {
  botUuid: string;
  connectorId: string;
  broadcastDraftId: number;
  conversationName: string;
  draftText: string;
  idempotencyKey: string;
}

export interface BroadcastRuntimePasteDraftPayload {
  action: 'paste_draft';
  conversationName: string;
  draftText: string;
  idempotencyKey: string;
  requestDigest: string;
}

export interface BroadcastPasteOnlyAdapter {
  toRuntimePayload: (
    request: BroadcastPasteDraftRequest,
    requestDigest: string,
  ) => BroadcastRuntimePasteDraftPayload;
}

export interface BroadcastRulesData {
  scope: BroadcastScope;
  templates: BroadcastMessageTemplate[];
  variableProfile: BroadcastVariableProfile;
  variableMappings: BroadcastVariableMapping[];
  groupRules: BroadcastGroupRule[];
  groupNames: BroadcastGroupName[];
}

export type BroadcastBatchState =
  | {
      phase: 'idle';
      total: number;
      completed: number;
      currentLabel?: string;
    }
  | {
      phase: 'running';
      total: number;
      completed: number;
      currentLabel: string;
    }
  | {
      phase: 'completed';
      total: number;
      completed: number;
      currentLabel?: string;
    };
