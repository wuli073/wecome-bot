export type BroadcastTopTab = 'rules' | 'import' | 'drafts' | 'logs';

export type BroadcastRulesTab = 'variables' | 'templates' | 'groups';

export type BroadcastImportBatchStatus =
  | 'imported'
  | 'matched'
  | 'drafts_generated';

export type BroadcastImportMatchStatus = 'matched' | 'unmatched' | 'invalid';

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

export interface BroadcastVariableMapping extends BroadcastVariableMappingRule {
  id: number;
  sampleValue: string;
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
  updatedAt: string;
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
}

export interface BroadcastImportFilters {
  matchStatus?: BroadcastImportMatchStatus | 'all';
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
  draftId: number;
  customerName: string;
  conversationName: string;
  status: BroadcastStatus;
  action: 'mock_prepare' | 'mock_paste' | 'mock_retry' | 'mock_review';
  message: string;
  timestamp: string;
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
