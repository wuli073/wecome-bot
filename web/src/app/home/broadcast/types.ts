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

export type BroadcastDraftStatus = 'pending_review' | 'ready' | 'invalid';

export type BroadcastStatus =
  | BroadcastDraftStatus
  | 'pending'
  | 'pasted'
  | 'failed'
  | 'completed';

export type BroadcastStatusFilter = 'all' | BroadcastDraftStatus;

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
  targetConversationName: string;
  priority: number;
  enabled: boolean;
  invalidLegacy?: boolean;
  invalidReason?: string | null;
  updatedAt: string;
}

export interface BroadcastGroupRuleDraft {
  id?: number;
  sourceValue: string;
  matchType: BroadcastGroupMatchType;
  matchExpression: string;
  targetConversationName: string;
  priority: number;
  enabled: boolean;
}

export interface BroadcastGroupMatchResult {
  matched: boolean;
  ruleId: number | null;
  targetConversationName: string | null;
  matchType: BroadcastGroupMatchType | null;
}

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
  conversationName: string;
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
  matchedConversationName: string | null;
  matchStatus: BroadcastImportGroupMatchStatus;
  reason: string | null;
  attachmentCount: number;
  expandable: boolean;
  firstSourceRowNumber: number;
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
}

export interface BroadcastDraft {
  id: number;
  botUuid: string;
  connectorId: string;
  importBatchId?: number;
  groupValue: string;
  customerName: string;
  conversationName: string;
  templateId?: number | null;
  templateName: string;
  templateContentSnapshot?: string;
  renderVariables?: Record<string, string>;
  status: BroadcastStatus;
  draftText: string;
  errorMessage?: string | null;
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
  status?: BroadcastDraftStatus | 'all';
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
  attachments: BroadcastAttachment[];
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
}

export interface BroadcastExecutorCapability {
  channel: string;
  supports_paste: boolean;
  supports_paste_verification?: boolean;
  supports_send: boolean;
  supports_cancel: boolean;
  supports_status_query: boolean;
  supports_clipboard_restore: boolean;
  supports_evidence: boolean;
  requires_manual_conversation_open?: boolean;
  executor_version: string;
  runtime_min_version: string;
  conversation_locator?: 'keyboard_search';
  content_verification?: 'disabled';
}

export interface BroadcastExecutorHealth {
  channel: string;
  status: string;
  protocol_version?: string | null;
  runtime_version?: string | null;
  capability: BroadcastExecutorCapability;
  runtime_status?: Record<string, unknown> | null;
}

export interface BroadcastSendConfirmation {
  id: number;
  token: string;
  expiresAt: string | null;
  executionTaskId: number;
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
