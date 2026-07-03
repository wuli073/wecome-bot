export type BroadcastTopTab = 'rules' | 'import' | 'drafts' | 'logs';

export type BroadcastRulesTab = 'variables' | 'templates' | 'groups';

export type BroadcastStatus = 'pending' | 'pasted' | 'failed' | 'completed';

export type BroadcastStatusFilter = 'all' | BroadcastStatus;

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
  customerName: string;
  conversationName: string;
  templateName: string;
  variableSummary: string;
  status: BroadcastStatus;
  matchedRule: string;
}

export interface BroadcastDraft {
  id: number;
  botUuid: string;
  connectorId: string;
  customerName: string;
  conversationName: string;
  templateName: string;
  status: BroadcastStatus;
  draftText: string;
  progressLabel: string;
  updatedAt: string;
  operator: string;
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
