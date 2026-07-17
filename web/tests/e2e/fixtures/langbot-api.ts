import { Page, Route } from '@playwright/test';

type JsonRecord = Record<string, unknown>;
type BroadcastImportGroupFieldSource =
  | 'configured'
  | 'auto_detected'
  | 'user_confirmed'
  | 'legacy_fallback';

interface SkillMock {
  name: string;
  display_name: string;
  description: string;
  instructions: string;
  package_root: string;
  updated_at: string;
}

interface PipelineMock {
  uuid: string;
  name: string;
  description: string;
  config: JsonRecord;
  emoji: string;
  is_default: boolean;
  updated_at: string;
}

interface KnowledgeBaseMock {
  uuid: string;
  name: string;
  description: string;
  emoji: string;
  knowledge_engine_plugin_id: string;
  creation_settings: JsonRecord;
  retrieval_settings: JsonRecord;
  knowledge_engine: {
    plugin_id: string;
    name: {
      en_US: string;
      zh_Hans: string;
    };
    capabilities: string[];
  };
  updated_at: string;
}

interface MCPServerMock {
  name: string;
  mode: 'sse' | 'stdio' | 'http';
  enable: boolean;
  extra_args: JsonRecord;
  runtime_info: {
    status: 'connected';
    tool_count: number;
    tools: unknown[];
  };
  readme: string;
  updated_at: string;
}

interface BotMock {
  uuid: string;
  name: string;
  description: string;
  enable: boolean;
  adapter: string;
  adapter_config: JsonRecord;
  use_pipeline_uuid?: string;
  pipeline_routing_rules: unknown[];
  adapter_runtime_values: JsonRecord;
  updated_at: string;
}

export interface InstallLangBotApiMockBot {
  uuid: string;
  name: string;
  description?: string;
  enable?: boolean;
  adapter?: string;
  adapter_config?: JsonRecord;
  use_pipeline_uuid?: string;
  pipeline_routing_rules?: unknown[];
  adapter_runtime_values?: JsonRecord;
  updated_at?: string;
}

interface BroadcastTemplateMock {
  id: number;
  bot_uuid: string;
  connector_id: string;
  name: string;
  content: string;
  variables: string[];
  enabled: boolean;
  created_at: string;
  updated_at: string;
}

interface BroadcastVariableProfileMock {
  group_field: string | null;
  mapping_rules: Array<{
    source_field: string;
    variable_key: string;
    merge_mode: 'first' | 'lines' | 'unique_lines' | 'commas' | 'unique_commas';
    order: number;
  }>;
}

interface BroadcastGroupRuleMock {
  id: number;
  bot_uuid: string;
  connector_id: string;
  source_value: string;
  match_type: 'exact' | 'contains' | 'regex';
  match_expression: string;
  target_conversation_id?: string | null;
  target_conversation_name: string;
  priority: number;
  enabled: boolean;
  created_at: string;
  updated_at: string;
}

interface BroadcastGroupNameMock {
  id: number;
  bot_uuid: string;
  connector_id: string;
  name: string;
  external_conversation_id?: string | null;
  created_at: string;
  updated_at: string;
}

interface BroadcastImportBatchMock {
  id: number;
  bot_uuid: string;
  connector_id: string;
  original_file_name: string;
  file_type: string;
  worksheet_name: string | null;
  status: 'imported' | 'matched' | 'drafts_generated';
  drafts_stale: boolean;
  total_rows: number;
  valid_rows: number;
  invalid_rows: number;
  matched_rows: number;
  unmatched_rows: number;
  group_field_used?: string | null;
  group_field_source?: BroadcastImportGroupFieldSource | null;
  created_at: string;
  updated_at: string;
}

interface BroadcastImportRowMock {
  id: number;
  import_batch_id: number;
  source_row_number: number;
  raw_data: Record<string, string>;
  group_value: string | null;
  matched_conversation_name: string | null;
  matched_rule_id: number | null;
  match_status: 'matched' | 'unmatched' | 'invalid';
  error_message: string | null;
  created_at: string;
}

interface BroadcastAttachmentMock {
  id: number;
  attachment_asset_id: number;
  original_name: string;
  size_bytes: number;
  sha256: string;
  extension: string;
  mime_type: string;
  sort_order: number;
}

interface BroadcastDraftMock {
  id: number;
  bot_uuid: string;
  connector_id: string;
  import_batch_id: number;
  group_value: string;
  target_conversation_name: string | null;
  template_id: number | null;
  template_name_snapshot: string;
  template_content_snapshot: string;
  render_variables: Record<string, string>;
  draft_text: string;
  status: 'pending_review' | 'ready' | 'invalid';
  legacy_status?: 'pending_review' | 'ready' | 'invalid';
  send_status: 'pending' | 'sent' | 'unknown';
  sent_at?: string | null;
  error_message: string | null;
  drafts_stale: boolean;
  attachments_stale?: boolean;
  attachments?: BroadcastAttachmentMock[];
  created_at: string;
  updated_at: string;
  message?: string | null;
}

interface BroadcastExecutionBatchMock {
  id: number;
  bot_uuid: string;
  connector_id: string;
  channel: string;
  mode: 'paste_only' | 'send';
  status: string;
  total_tasks: number;
  pending_tasks: number;
  running_tasks: number;
  succeeded_tasks: number;
  failed_tasks: number;
  cancelled_tasks: number;
  interrupted_tasks: number;
  created_by: string;
  last_action_by: string | null;
  error_message: string | null;
  version: number;
  created_at: string;
  started_at: string | null;
  paused_at: string | null;
  finished_at: string | null;
  cancelled_at: string | null;
  scripted_failure_emitted?: boolean;
  total_count?: number;
  sent_count?: number;
  failed_count?: number;
  unknown_count?: number;
  skipped_count?: number;
  duplicate_target_count?: number;
  items?: Array<{
    draft_id: number | null;
    outcome: 'sent' | 'failed' | 'unknown' | 'skipped';
    error_code: string | null;
    error_message: string | null;
    enter_dispatched: boolean | null;
    message_sent?: boolean | null;
    terminal_confirmed?: boolean | null;
    terminal_source?: string | null;
    started_at: string | null;
    completed_at: string | null;
  }>;
}

interface BroadcastExecutionTaskMock {
  id: number;
  execution_batch_id: number;
  draft_id: number | null;
  draft_text_snapshot: string;
  target_conversation_snapshot: string;
  channel: string;
  action: 'paste_draft' | 'send_message';
  status: string;
  sequence_no: number;
  attempt_count: number;
  max_attempts: number;
  idempotency_key: string;
  request_digest: string;
  runtime_task_id: string | null;
  error_code: string | null;
  error_message: string | null;
  operator_note: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  cancelled_at: string | null;
  updated_at: string;
  retry_allowed?: boolean;
  send_outcome?: 'sent' | 'failed' | 'unknown' | 'skipped' | null;
  enter_dispatched?: boolean | null;
  message_sent?: boolean | null;
  terminal_confirmed?: boolean | null;
  terminal_source?: string | null;
  attachments?: BroadcastAttachmentMock[];
}

interface BroadcastExecutionAttemptMock {
  id: number;
  execution_task_id: number;
  attempt_no: number;
  idempotency_key: string;
  request_digest: string;
  runtime_task_id: string | null;
  request_summary: string | null;
  response_summary: string | null;
  status: string;
  error_code: string | null;
  error_message: string | null;
  started_at: string;
  finished_at: string | null;
}

interface BroadcastExecutionEvidenceMock {
  id: number;
  execution_attempt_id: number;
  window_title: string | null;
  target_conversation: string | null;
  action: 'paste_draft' | 'send_message';
  input_located: boolean;
  draft_written: boolean;
  send_triggered: boolean;
  clipboard_restored: boolean;
  runtime_state: string | null;
  evidence_summary: string | null;
  technical_details: Record<string, unknown> | null;
  created_at: string;
}

interface LangBotApiMockState {
  bots: BotMock[];
  broadcastExecutorCapability?: Record<string, unknown> | null;
  broadcastExecutorHealth?: Record<string, unknown> | null;
  broadcastExecutorHealthDelayMs?: number;
  broadcastDrafts: BroadcastDraftMock[];
  broadcastExecutionAttempts: BroadcastExecutionAttemptMock[];
  broadcastExecutionBatches: BroadcastExecutionBatchMock[];
  broadcastExecutionEvidence: BroadcastExecutionEvidenceMock[];
  broadcastExecutionTasks: BroadcastExecutionTaskMock[];
  broadcastGroupAttachments: Record<string, BroadcastAttachmentMock[]>;
  broadcastGroupTemplateAssignments: Record<string, number>;
  broadcastGroupNames: BroadcastGroupNameMock[];
  broadcastGroupRules: BroadcastGroupRuleMock[];
  broadcastImportBatches: BroadcastImportBatchMock[];
  broadcastImportRows: BroadcastImportRowMock[];
  broadcastTemplates: BroadcastTemplateMock[];
  broadcastSendEnabled: boolean;
  broadcastVariableProfile: BroadcastVariableProfileMock;
  counters: Record<string, number>;
  knowledgeBases: KnowledgeBaseMock[];
  mcpServers: MCPServerMock[];
  pipelines: PipelineMock[];
  skills: SkillMock[];
}

function ok(data: unknown) {
  return {
    code: 0,
    message: 'ok',
    data,
    timestamp: Date.now(),
  };
}

async function fulfillJson(route: Route, data: unknown) {
  await route.fulfill({
    status: 200,
    contentType: 'application/json',
    headers: {
      'cache-control': 'no-store',
    },
    body: JSON.stringify(ok(data)),
  });
}

async function fulfillError(
  route: Route,
  status: number,
  msg: string,
  message: string,
  details: unknown = [],
) {
  await route.fulfill({
    status,
    contentType: 'application/json',
    headers: {
      'cache-control': 'no-store',
    },
    body: JSON.stringify({
      code: -1,
      msg,
      message,
      details,
      data: null,
      timestamp: Date.now(),
    }),
  });
}

function routePath(route: Route) {
  return new URL(route.request().url()).pathname;
}

function parseJsonBody(route: Route): JsonRecord {
  return JSON.parse(route.request().postData() || '{}') as JsonRecord;
}

function parseMultipartTextField(body: string, fieldName: string) {
  const normalizedFieldName = fieldName.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const pattern = new RegExp(
    `name=\"${normalizedFieldName}\"\\r\\n\\r\\n([\\s\\S]*?)\\r\\n--`,
    'i',
  );
  const match = body.match(pattern);
  return match?.[1]?.trim() || null;
}

function now() {
  return new Date().toISOString();
}

function nextId(state: LangBotApiMockState, prefix: string) {
  state.counters[prefix] = (state.counters[prefix] || 0) + 1;
  return `${prefix}-${state.counters[prefix]}`;
}

function tryParseJson(value: unknown) {
  if (typeof value !== 'string' || value.trim().length === 0) {
    return null;
  }
  try {
    return JSON.parse(value) as JsonRecord;
  } catch {
    return null;
  }
}

function makeGroupKey(importId: number, groupValue: string) {
  return Buffer.from(`${importId}:${groupValue}`, 'utf-8')
    .toString('base64')
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/g, '');
}

function findOrderField(profile: BroadcastVariableProfileMock) {
  return (
    profile.mapping_rules.find((rule) =>
      ['运单号', 'order_no', 'shipment_no'].includes(rule.variable_key),
    )?.source_field || null
  );
}

function normalizeOrderValue(value: string | undefined) {
  const trimmed = String(value || '').trim();
  return trimmed.length > 0 ? trimmed : null;
}

function inferGroupMatchStatus(rows: BroadcastImportRowMock[]) {
  const statuses = new Set(rows.map((row) => row.match_status));
  const conversations = new Set(
    rows
      .map((row) => row.matched_conversation_name)
      .filter((value): value is string => Boolean(value)),
  );
  if (statuses.size > 1 || conversations.size > 1) {
    return 'conflict' as const;
  }
  return rows[0]?.match_status || 'invalid';
}

function inferGroupReason(rows: BroadcastImportRowMock[], status: string) {
  if (status === 'conflict') {
    return 'Multiple match outcomes found in the same group';
  }
  return rows.find((row) => row.error_message)?.error_message || null;
}

function groupAttachmentMapKey(importId: number, groupKey: string) {
  return `${importId}:${groupKey}`;
}

function groupTemplateAssignmentMapKey(importId: number, groupKey: string) {
  return `${importId}:${groupKey}`;
}

function cloneAttachment(
  attachment: BroadcastAttachmentMock,
): BroadcastAttachmentMock {
  return JSON.parse(JSON.stringify(attachment)) as BroadcastAttachmentMock;
}

function createAttachment(
  state: LangBotApiMockState,
  originalName: string,
  sortOrder: number,
): BroadcastAttachmentMock {
  const attachmentId = Number(
    nextId(state, 'broadcast-attachment').split('-').pop(),
  );
  const attachmentAssetId = Number(
    nextId(state, 'broadcast-attachment-asset').split('-').pop(),
  );
  const extensionMatch = /\.([^.]+)$/.exec(originalName);
  const extension = extensionMatch ? `.${extensionMatch[1].toLowerCase()}` : '';
  const sizeBytes = Math.max(1, Buffer.byteLength(originalName, 'utf-8') * 128);
  return {
    id: attachmentId,
    attachment_asset_id: attachmentAssetId,
    original_name: originalName,
    size_bytes: sizeBytes,
    sha256: `sha256:${attachmentAssetId}:${originalName}`,
    extension,
    mime_type: extension === '.pdf' ? 'application/pdf' : 'image/png',
    sort_order: sortOrder,
  };
}

function serializeDraft(draft: BroadcastDraftMock): BroadcastDraftMock {
  return {
    ...draft,
    legacy_status: draft.status,
    attachments_stale: draft.attachments_stale ?? false,
    attachments: (draft.attachments ?? []).map(cloneAttachment),
  };
}

function buildImportGroupsResponse(
  state: LangBotApiMockState,
  importId: number,
  filters: {
    matchStatus?: string | null;
    keyword?: string;
    page: number;
    pageSize: number;
  },
) {
  const batch =
    state.broadcastImportBatches.find((item) => item.id === importId) || null;
  const rows = state.broadcastImportRows
    .filter((item) => item.import_batch_id === importId)
    .sort((left, right) => left.source_row_number - right.source_row_number);
  const orderField = findOrderField(state.broadcastVariableProfile);
  const grouped = new Map<string, BroadcastImportRowMock[]>();
  for (const row of rows) {
    const key = row.group_value ?? `__invalid__:${row.id}`;
    const current = grouped.get(key) ?? [];
    current.push(row);
    grouped.set(key, current);
  }

  const allGroups = Array.from(grouped.entries())
    .map(([groupValue, groupRows]) => {
      const matchStatus = inferGroupMatchStatus(groupRows);
      const groupKey = makeGroupKey(importId, groupValue);
      const attachmentKey = groupAttachmentMapKey(importId, groupKey);
      const distinctOrders = new Set(
        groupRows
          .map((row) =>
            orderField ? normalizeOrderValue(row.raw_data[orderField]) : null,
          )
          .filter((value): value is string => value != null),
      );
      const attachments = (
        state.broadcastGroupAttachments[attachmentKey] ?? []
      ).map(cloneAttachment);
      const matchedRule =
        matchStatus === 'conflict'
          ? null
          : (state.broadcastGroupRules.find(
              (item) => item.id === (groupRows[0]?.matched_rule_id ?? null),
            ) ?? null);
      const matchedConversationId =
        matchedRule?.target_conversation_id ??
        (matchStatus === 'conflict' || !batch
          ? null
          : (state.broadcastGroupNames.find(
              (item) =>
                item.bot_uuid === batch.bot_uuid &&
                item.connector_id === batch.connector_id &&
                item.name === (groupRows[0]?.matched_conversation_name ?? ''),
            )?.external_conversation_id ?? null));
      const templateId =
        state.broadcastGroupTemplateAssignments[
          groupTemplateAssignmentMapKey(importId, groupKey)
        ] ?? null;
      const template =
        templateId != null
          ? (state.broadcastTemplates.find((item) => item.id === templateId) ??
            null)
          : null;
      return {
        group_key: groupKey,
        group_value: groupValue,
        raw_row_count: groupRows.length,
        distinct_order_number_count: distinctOrders.size,
        matched_conversation_name:
          matchStatus === 'conflict'
            ? null
            : (groupRows[0]?.matched_conversation_name ?? null),
        matched_conversation_id:
          matchStatus === 'conflict' ? null : matchedConversationId,
        match_status: matchStatus,
        reason: inferGroupReason(groupRows, matchStatus),
        attachment_count: attachments.length,
        attachments,
        template_id: templateId,
        template_name: template?.name ?? null,
        template_enabled: template?.enabled ?? null,
        expandable: true,
        first_source_row_number: Math.min(
          ...groupRows.map((row) => row.source_row_number),
        ),
      };
    })
    .sort((left, right) => {
      if (left.first_source_row_number !== right.first_source_row_number) {
        return left.first_source_row_number - right.first_source_row_number;
      }
      return left.group_value.localeCompare(right.group_value);
    });

  const keyword = (filters.keyword || '').trim().toLowerCase();
  const filteredGroups = allGroups.filter((group) => {
    if (filters.matchStatus && group.match_status !== filters.matchStatus) {
      return false;
    }
    if (!keyword) {
      return true;
    }
    return [
      group.group_value,
      group.matched_conversation_name || '',
      group.reason || '',
    ]
      .join(' ')
      .toLowerCase()
      .includes(keyword);
  });

  const offset = (filters.page - 1) * filters.pageSize;
  return {
    page: filters.page,
    page_size: filters.pageSize,
    total: filteredGroups.length,
    total_pages:
      filteredGroups.length === 0
        ? 0
        : Math.ceil(filteredGroups.length / filters.pageSize),
    raw_row_total: rows.length,
    group_total: allGroups.length,
    matched_group_total: allGroups.filter(
      (group) => group.match_status === 'matched',
    ).length,
    unmatched_group_total: allGroups.filter(
      (group) => group.match_status === 'unmatched',
    ).length,
    invalid_group_total: allGroups.filter(
      (group) => group.match_status === 'invalid',
    ).length,
    conflict_group_total: allGroups.filter(
      (group) => group.match_status === 'conflict',
    ).length,
    order_number_field_configured: Boolean(orderField),
    groups: filteredGroups.slice(offset, offset + filters.pageSize),
  };
}

function buildImportGroupRuleCandidatesResponse(
  state: LangBotApiMockState,
  importId: number,
  filters: {
    status?: string | null;
    keyword?: string;
    page: number;
    pageSize: number;
  },
) {
  const batch =
    state.broadcastImportBatches.find((item) => item.id === importId) || null;
  if (!batch) {
    return null;
  }

  const groupsResponse = buildImportGroupsResponse(state, importId, {
    matchStatus: null,
    keyword: '',
    page: 1,
    pageSize: Number.MAX_SAFE_INTEGER,
  });
  const rows = state.broadcastImportRows.filter(
    (item) => item.import_batch_id === importId,
  );
  const groupRowsByKey = new Map<string, BroadcastImportRowMock[]>();
  for (const row of rows) {
    const groupKey = makeGroupKey(
      importId,
      row.group_value ?? `__invalid__:${row.id}`,
    );
    const current = groupRowsByKey.get(groupKey) ?? [];
    current.push(row);
    groupRowsByKey.set(groupKey, current);
  }

  const allItems = groupsResponse.groups.map((group) => {
    const customerName = String(group.group_value ?? '').trim();
    const currentRows = groupRowsByKey.get(group.group_key) ?? [];
    const existingRules = state.broadcastGroupRules
      .filter(
        (rule) =>
          rule.bot_uuid === batch.bot_uuid &&
          rule.connector_id === batch.connector_id &&
          customerName.length > 0 &&
          matchBroadcastRule(rule, customerName),
      )
      .sort((left, right) =>
        right.priority === left.priority
          ? left.id - right.id
          : right.priority - left.priority,
      );
    const currentMatchedRule =
      state.broadcastGroupRules.find(
        (rule) => rule.id === (currentRows[0]?.matched_rule_id ?? null),
      ) ?? null;

    let status: 'new' | 'configured' | 'needs_repair' | 'conflict' | 'invalid' =
      'new';
    if (!customerName || group.match_status === 'invalid') {
      status = 'invalid';
    } else if (group.match_status === 'conflict' || existingRules.length > 1) {
      status = 'conflict';
    } else if (currentMatchedRule) {
      status = 'configured';
    } else if (existingRules.length === 1) {
      status = 'needs_repair';
    }

    return {
      group_key: group.group_key,
      customer_name: customerName,
      raw_row_count: group.raw_row_count,
      status,
      reason: group.reason,
      existing_rule_ids: existingRules.map((rule) => rule.id),
      existing_rules: existingRules,
      current_matched_rule: currentMatchedRule,
      current_target_conversation_id:
        group.matched_conversation_id ??
        currentMatchedRule?.target_conversation_id ??
        null,
      current_target_conversation_name: group.matched_conversation_name,
      current_match_type: currentMatchedRule?.match_type ?? null,
      first_source_row_number: group.first_source_row_number,
    };
  });

  const keyword = (filters.keyword || '').trim().toLowerCase();
  const filteredItems = allItems.filter((item) => {
    if (
      filters.status &&
      filters.status !== 'all' &&
      item.status !== filters.status
    ) {
      return false;
    }
    if (!keyword) {
      return true;
    }
    return [
      item.customer_name,
      item.current_target_conversation_name || '',
      item.reason || '',
    ]
      .join(' ')
      .toLowerCase()
      .includes(keyword);
  });

  const offset = (filters.page - 1) * filters.pageSize;
  return {
    import_batch_id: importId,
    group_field_used:
      batch.group_field_used ??
      state.broadcastVariableProfile.group_field ??
      'Customer Name',
    group_field_source:
      batch.group_field_source ??
      ('legacy_fallback' as BroadcastImportGroupFieldSource),
    raw_row_total: rows.length,
    unique_customer_total: allItems.length,
    stats: {
      new_count: allItems.filter((item) => item.status === 'new').length,
      configured_count: allItems.filter((item) => item.status === 'configured')
        .length,
      needs_repair_count: allItems.filter(
        (item) => item.status === 'needs_repair',
      ).length,
      conflict_count: allItems.filter((item) => item.status === 'conflict')
        .length,
      invalid_count: allItems.filter((item) => item.status === 'invalid')
        .length,
    },
    items: filteredItems.slice(offset, offset + filters.pageSize),
    page: filters.page,
    page_size: filters.pageSize,
    total: filteredItems.length,
    total_pages:
      filteredItems.length === 0
        ? 0
        : Math.ceil(filteredItems.length / filters.pageSize),
  };
}

function refreshDraftMessage(
  draft: BroadcastDraftMock,
  statusMessage: string | null = null,
) {
  draft.updated_at = now();
  draft.message = statusMessage;
}

function markDraftAttachmentsChanged(draft: BroadcastDraftMock) {
  refreshDraftMessage(draft, null);
}

function markGroupAttachmentsChanged(
  state: LangBotApiMockState,
  importId: number,
  groupValue: string,
) {
  state.broadcastDrafts = state.broadcastDrafts.map((draft) => {
    if (
      draft.import_batch_id !== importId ||
      draft.group_value !== groupValue
    ) {
      return draft;
    }
    const nextDraft = {
      ...draft,
      attachments_stale: true,
    };
    markDraftAttachmentsChanged(nextDraft);
    return nextDraft;
  });
}

function emptyMonitoringData() {
  return {
    overview: {
      total_messages: 0,
      llm_calls: 0,
      embedding_calls: 0,
      model_calls: 0,
      success_rate: 0,
      active_sessions: 0,
    },
    messages: [],
    llmCalls: [],
    embeddingCalls: [],
    sessions: [],
    errors: [],
    totalCount: {
      messages: 0,
      llmCalls: 0,
      embeddingCalls: 0,
      sessions: 0,
      errors: 0,
    },
  };
}

function emptyTokenStatistics() {
  return {
    summary: {
      total_calls: 0,
      success_calls: 0,
      error_calls: 0,
      total_input_tokens: 0,
      total_output_tokens: 0,
      total_tokens: 0,
      total_cost: 0,
      avg_tokens_per_call: 0,
      avg_duration_ms: 0,
      avg_tokens_per_second: 0,
      zero_token_success_calls: 0,
    },
    by_model: [],
    timeseries: [],
    bucket: 'day',
  };
}

function makeSkill(data: JsonRecord): SkillMock {
  return {
    name: String(data.name || ''),
    display_name: String(data.display_name || ''),
    description: String(data.description || ''),
    instructions: String(data.instructions || ''),
    package_root: String(data.package_root || ''),
    updated_at: new Date().toISOString(),
  };
}

function makePipeline(
  state: LangBotApiMockState,
  data: JsonRecord,
  uuid = nextId(state, 'pipeline'),
): PipelineMock {
  return {
    uuid,
    name: String(data.name || ''),
    description: String(data.description || ''),
    config: (data.config as JsonRecord | undefined) || {
      ai: {},
      trigger: {},
      safety: {},
      output: {},
    },
    emoji: String(data.emoji || '⚙️'),
    is_default: false,
    updated_at: now(),
  };
}

function knowledgeEngine() {
  return {
    plugin_id: 'builtin/minimal-knowledge',
    name: {
      en_US: 'Minimal Knowledge Engine',
      zh_Hans: '最小知识库引擎',
    },
    description: {
      en_US: 'Minimal mocked engine for frontend smoke tests.',
      zh_Hans: '用于前端冒烟测试的最小模拟引擎。',
    },
    capabilities: ['text_retrieval'],
    creation_schema: [],
    retrieval_schema: [],
  };
}

function makeKnowledgeBase(
  state: LangBotApiMockState,
  data: JsonRecord,
  uuid = nextId(state, 'knowledge'),
): KnowledgeBaseMock {
  const engine = knowledgeEngine();
  return {
    uuid,
    name: String(data.name || ''),
    description: String(data.description || ''),
    emoji: String(data.emoji || '📚'),
    knowledge_engine_plugin_id: String(
      data.knowledge_engine_plugin_id || engine.plugin_id,
    ),
    creation_settings: (data.creation_settings as JsonRecord | undefined) || {},
    retrieval_settings:
      (data.retrieval_settings as JsonRecord | undefined) || {},
    knowledge_engine: {
      plugin_id: engine.plugin_id,
      name: engine.name,
      capabilities: engine.capabilities,
    },
    updated_at: now(),
  };
}

function makeMCPServer(data: JsonRecord): MCPServerMock {
  return {
    name: String(data.name || ''),
    mode: (data.mode as MCPServerMock['mode']) || 'sse',
    enable: data.enable !== false,
    extra_args: (data.extra_args as JsonRecord | undefined) || {},
    runtime_info: {
      status: 'connected',
      tool_count: 0,
      tools: [],
    },
    readme: '',
    updated_at: now(),
  };
}

function makeBot(
  state: LangBotApiMockState,
  data: JsonRecord,
  uuid = nextId(state, 'bot'),
): BotMock {
  return {
    uuid,
    name: String(data.name || ''),
    description: String(data.description || ''),
    enable: data.enable !== false,
    adapter: String(data.adapter || 'playwright-adapter'),
    adapter_config: (data.adapter_config as JsonRecord | undefined) || {},
    use_pipeline_uuid: data.use_pipeline_uuid
      ? String(data.use_pipeline_uuid)
      : undefined,
    pipeline_routing_rules:
      (data.pipeline_routing_rules as unknown[] | undefined) || [],
    adapter_runtime_values: {
      webhook_full_url: `https://playwright.test/bots/${uuid}/webhook`,
      extra_webhook_full_url: '',
    },
    updated_at: now(),
  };
}

function extractTemplateVariables(content: string): string[] {
  const matches = content.matchAll(/{{\s*([A-Za-z0-9_\-\u4e00-\u9fff]+)\s*}}/g);
  return Array.from(new Set(Array.from(matches, (match) => match[1])));
}

function renderBroadcastTemplate(
  content: string,
  variables: Record<string, unknown>,
) {
  const required_variables = extractTemplateVariables(content);
  const rendered_text = content.replace(
    /{{\s*([A-Za-z0-9_\-\u4e00-\u9fff]+)\s*}}/g,
    (token, key: string) => {
      const value = variables[key];
      return value === undefined || value === null || value === ''
        ? token
        : String(value);
    },
  );
  const missing_variables = required_variables.filter((key) => {
    const value = variables[key];
    return value === undefined || value === null || value === '';
  });
  return {
    rendered_text,
    required_variables,
    missing_variables,
    valid: missing_variables.length === 0,
  };
}

function matchBroadcastRule(
  rule: BroadcastGroupRuleMock,
  sourceValue: string,
): boolean {
  if (!rule.enabled) {
    return false;
  }

  if (rule.match_type === 'exact') {
    return sourceValue === rule.match_expression;
  }

  if (rule.match_type === 'contains') {
    return sourceValue.includes(rule.match_expression);
  }

  try {
    return new RegExp(rule.match_expression).test(sourceValue);
  } catch {
    return false;
  }
}

function resolveImportMatch(
  state: LangBotApiMockState,
  botUuid: string,
  connectorId: string,
  groupValue: string,
) {
  const matchedRule =
    state.broadcastGroupRules
      .filter(
        (rule) =>
          rule.bot_uuid === botUuid &&
          rule.connector_id === connectorId &&
          matchBroadcastRule(rule, groupValue),
      )
      .sort((left, right) =>
        right.priority === left.priority
          ? left.id - right.id
          : right.priority - left.priority,
      )[0] || null;

  if (matchedRule) {
    return {
      match_status: 'matched' as const,
      matched_conversation_name: matchedRule.target_conversation_name,
      matched_rule_id: matchedRule.id,
      error_message: null,
    };
  }

  const fallback = state.broadcastGroupNames.find(
    (item) =>
      item.bot_uuid === botUuid &&
      item.connector_id === connectorId &&
      item.name === groupValue,
  );
  if (fallback) {
    return {
      match_status: 'matched' as const,
      matched_conversation_name: fallback.name,
      matched_rule_id: null,
      error_message: null,
    };
  }

  return {
    match_status: 'unmatched' as const,
    matched_conversation_name: null,
    matched_rule_id: null,
    error_message: null,
  };
}

function syncDraftStaleFlags(
  state: LangBotApiMockState,
  importBatchId: number,
) {
  const batch = state.broadcastImportBatches.find(
    (item) => item.id === importBatchId,
  );
  if (!batch) {
    return;
  }
  state.broadcastDrafts = state.broadcastDrafts.map((draft) =>
    draft.import_batch_id === importBatchId
      ? {
          ...draft,
          drafts_stale: batch.drafts_stale,
          attachments_stale: draft.attachments_stale ?? false,
          attachments: draft.attachments ?? [],
        }
      : draft,
  );
}

function syncImportBatchCounts(
  state: LangBotApiMockState,
  importBatchId: number,
) {
  const batch = state.broadcastImportBatches.find(
    (item) => item.id === importBatchId,
  );
  if (!batch) {
    return null;
  }
  const rows = state.broadcastImportRows.filter(
    (item) => item.import_batch_id === importBatchId,
  );
  batch.valid_rows = rows.filter(
    (item) => item.match_status !== 'invalid',
  ).length;
  batch.invalid_rows = rows.filter(
    (item) => item.match_status === 'invalid',
  ).length;
  batch.matched_rows = rows.filter(
    (item) => item.match_status === 'matched',
  ).length;
  batch.unmatched_rows = rows.filter(
    (item) => item.match_status === 'unmatched',
  ).length;
  batch.updated_at = now();
  return {
    batch,
    rows,
  };
}

function findExecutionBatch(state: LangBotApiMockState, batchId: number) {
  return (
    state.broadcastExecutionBatches.find((item) => item.id === batchId) || null
  );
}

function getLatestExecutionAttempt(state: LangBotApiMockState, taskId: number) {
  return (
    state.broadcastExecutionAttempts
      .filter((item) => item.execution_task_id === taskId)
      .sort((left, right) => left.attempt_no - right.attempt_no)
      .at(-1) || null
  );
}

function getExecutionEvidenceForAttempt(
  state: LangBotApiMockState,
  attemptId: number,
) {
  return (
    state.broadcastExecutionEvidence.find(
      (item) => item.execution_attempt_id === attemptId,
    ) || null
  );
}

function getSendTerminalFlag(
  payload: JsonRecord,
  ...keys: string[]
): boolean | null {
  for (const key of keys) {
    if (!(key in payload)) {
      continue;
    }
    const value = payload[key];
    if (typeof value === 'boolean' || value === null) {
      return value;
    }
    if (typeof value === 'number') {
      return value !== 0;
    }
    if (typeof value === 'string') {
      const normalized = value.trim().toLowerCase();
      if (['true', '1', 'yes'].includes(normalized)) {
        return true;
      }
      if (['false', '0', 'no'].includes(normalized)) {
        return false;
      }
    }
  }
  return null;
}

function deriveSendTaskState(
  state: LangBotApiMockState,
  task: BroadcastExecutionTaskMock,
) {
  const attempt = getLatestExecutionAttempt(state, task.id);
  const responseSummary = attempt
    ? tryParseJson(attempt.response_summary)
    : null;
  if (task.action !== 'send_message') {
    const responseStatus = String(responseSummary?.status || '')
      .trim()
      .toLowerCase();
    const resultPayload =
      responseSummary &&
      responseSummary.result &&
      typeof responseSummary.result === 'object'
        ? (responseSummary.result as JsonRecord)
        : {};
    const terminalConfirmedRaw = resultPayload.terminalConfirmed;
    const terminalConfirmed =
      typeof terminalConfirmedRaw === 'boolean'
        ? terminalConfirmedRaw
        : responseSummary
          ? [
              'succeeded',
              'succeeded_with_warning',
              'blocked',
              'failed',
              'cancelled',
              'interrupted',
              'timed_out',
            ].includes(responseStatus) && responseStatus !== 'unknown'
          : null;
    const hasTerminalAttempt = Boolean(responseSummary) || terminalConfirmed === true;
    return {
      retry_allowed: task.status === 'failed' || task.status === 'interrupted',
      send_outcome: null,
      enter_dispatched: hasTerminalAttempt ? false : null,
      message_sent: hasTerminalAttempt ? false : null,
      terminal_confirmed: terminalConfirmed,
      terminal_source: hasTerminalAttempt
        ? typeof resultPayload.terminalSource === 'string'
          ? String(resultPayload.terminalSource)
          : 'runtime'
        : null,
    };
  }
  const evidence = attempt
    ? getExecutionEvidenceForAttempt(state, attempt.id)
    : null;
  const technicalDetails =
    evidence &&
    evidence.technical_details &&
    !Array.isArray(evidence.technical_details)
      ? evidence.technical_details
      : {};
  const resultPayload =
    responseSummary &&
    responseSummary.result &&
    typeof responseSummary.result === 'object'
      ? (responseSummary.result as JsonRecord)
      : {};
  let enterDispatched = getSendTerminalFlag(
    resultPayload,
    'enterDispatched',
    'enter_dispatched',
  );
  if (enterDispatched === null) {
    enterDispatched = getSendTerminalFlag(
      technicalDetails as JsonRecord,
      'enter_dispatched',
      'enterDispatched',
    );
  }
  let messageSent = getSendTerminalFlag(
    resultPayload,
    'messageSent',
    'message_sent',
  );
  if (messageSent === null) {
    messageSent = getSendTerminalFlag(
      technicalDetails as JsonRecord,
      'message_sent',
      'messageSent',
    );
  }
  const responseStatus = String(responseSummary?.status || '')
    .trim()
    .toLowerCase();
  const terminalConfirmedRaw = resultPayload.terminalConfirmed;
  const terminalConfirmed =
    typeof terminalConfirmedRaw === 'boolean'
      ? terminalConfirmedRaw
      : [
          'succeeded',
          'succeeded_with_warning',
          'blocked',
          'failed',
          'cancelled',
          'interrupted',
          'timed_out',
        ].includes(responseStatus) && responseStatus !== 'unknown';
  if (enterDispatched === null && messageSent === true && terminalConfirmed) {
    enterDispatched = true;
  }
  const terminalSource =
    typeof resultPayload.terminalSource === 'string'
      ? resultPayload.terminalSource
      : typeof (technicalDetails as JsonRecord).terminal_source === 'string'
        ? String((technicalDetails as JsonRecord).terminal_source)
        : responseSummary
          ? 'runtime'
          : null;

  let sendOutcome: 'sent' | 'failed' | 'unknown' | 'skipped';
  if (task.status === 'succeeded') {
    sendOutcome = 'sent';
  } else if (task.status === 'cancelled') {
    sendOutcome = 'skipped';
  } else if (
    task.status === 'interrupted' ||
    task.status === 'succeeded_with_warning'
  ) {
    sendOutcome = 'unknown';
  } else if (enterDispatched === null || enterDispatched === true) {
    sendOutcome = 'unknown';
  } else {
    sendOutcome = 'failed';
  }

  const retryAllowed =
    task.status === 'failed' &&
    !['', 'queued', 'running'].includes(responseStatus) &&
    terminalConfirmed === true &&
    enterDispatched === false &&
    sendOutcome === 'failed';

  return {
    retry_allowed: retryAllowed,
    send_outcome: sendOutcome,
    enter_dispatched: enterDispatched,
    message_sent: messageSent,
    terminal_confirmed: terminalConfirmed,
    terminal_source: terminalSource,
  };
}

function syncTaskDerivedState(
  state: LangBotApiMockState,
  task: BroadcastExecutionTaskMock,
) {
  const derived = deriveSendTaskState(state, task);
  task.retry_allowed = derived.retry_allowed;
  task.send_outcome = derived.send_outcome;
  task.enter_dispatched = derived.enter_dispatched;
  task.message_sent = derived.message_sent;
  task.terminal_confirmed = derived.terminal_confirmed;
  task.terminal_source = derived.terminal_source;
  return task;
}

function serializeExecutionTask(
  state: LangBotApiMockState,
  task: BroadcastExecutionTaskMock,
) {
  return {
    ...syncTaskDerivedState(state, task),
  };
}

function findExecutionTask(state: LangBotApiMockState, taskId: number) {
  return (
    state.broadcastExecutionTasks.find((item) => item.id === taskId) || null
  );
}

function syncExecutionBatchCounts(state: LangBotApiMockState, batchId: number) {
  const batch = findExecutionBatch(state, batchId);
  if (!batch) {
    return null;
  }
  const tasks = state.broadcastExecutionTasks.filter(
    (item) => item.execution_batch_id === batchId,
  );
  batch.total_tasks = tasks.length;
  batch.pending_tasks = tasks.filter(
    (item) => item.status === 'pending',
  ).length;
  batch.running_tasks = tasks.filter(
    (item) => item.status === 'running',
  ).length;
  batch.succeeded_tasks = tasks.filter(
    (item) => item.status === 'succeeded',
  ).length;
  batch.failed_tasks = tasks.filter((item) => item.status === 'failed').length;
  batch.cancelled_tasks = tasks.filter(
    (item) => item.status === 'cancelled',
  ).length;
  batch.interrupted_tasks = tasks.filter(
    (item) => item.status === 'interrupted',
  ).length;

  if (batch.running_tasks > 0) {
    batch.status = 'running';
  } else if (
    tasks.length > 0 &&
    batch.pending_tasks === tasks.length &&
    batch.paused_at
  ) {
    batch.status = 'paused';
  } else if (
    batch.pending_tasks > 0 &&
    batch.succeeded_tasks === 0 &&
    batch.failed_tasks === 0
  ) {
    batch.status = batch.started_at ? 'queued' : 'created';
  } else if (
    batch.pending_tasks === 0 &&
    batch.failed_tasks === 0 &&
    batch.interrupted_tasks === 0
  ) {
    batch.status = 'completed';
    batch.finished_at = batch.finished_at || now();
  } else if (
    batch.pending_tasks > 0 &&
    (batch.failed_tasks > 0 || batch.interrupted_tasks > 0)
  ) {
    batch.status = 'partially_failed';
  } else if (
    batch.pending_tasks === 0 &&
    batch.succeeded_tasks === 0 &&
    batch.cancelled_tasks > 0
  ) {
    batch.status = 'cancelled';
  } else if (
    batch.pending_tasks === 0 &&
    batch.failed_tasks > 0 &&
    batch.succeeded_tasks === 0
  ) {
    batch.status = 'failed';
  } else if (
    batch.pending_tasks === 0 &&
    batch.interrupted_tasks > 0 &&
    batch.succeeded_tasks === 0
  ) {
    batch.status = 'interrupted';
  } else if (batch.failed_tasks > 0 || batch.interrupted_tasks > 0) {
    batch.status = 'partially_failed';
  }

  return batch;
}

function buildSendBatchSummary(
  state: LangBotApiMockState,
  batch: BroadcastExecutionBatchMock,
) {
  const tasks = state.broadcastExecutionTasks
    .filter((item) => item.execution_batch_id === batch.id)
    .sort((left, right) => left.sequence_no - right.sequence_no);
  let sentCount = 0;
  let failedCount = 0;
  let unknownCount = 0;
  let skippedCount = 0;
  const seenTargets = new Set<string>();
  let duplicateTargetCount = 0;
  const items = tasks.map((task) => {
    const target = String(task.target_conversation_snapshot || '').trim();
    if (target) {
      if (seenTargets.has(target)) {
        duplicateTargetCount += 1;
      } else {
        seenTargets.add(target);
      }
    }
    const derived = deriveSendTaskState(state, task);
    const outcome = derived.send_outcome ?? 'failed';
    if (outcome === 'sent') {
      sentCount += 1;
    } else if (outcome === 'failed') {
      failedCount += 1;
    } else if (outcome === 'unknown') {
      unknownCount += 1;
    } else {
      skippedCount += 1;
    }
    return {
      draft_id: task.draft_id,
      outcome,
      error_code: task.error_code,
      error_message: task.error_message,
      enter_dispatched: derived.enter_dispatched,
      message_sent: derived.message_sent,
      terminal_confirmed: derived.terminal_confirmed,
      terminal_source: derived.terminal_source,
      started_at: task.started_at,
      completed_at: task.finished_at,
    };
  });
  return {
    total_count: tasks.length,
    sent_count: sentCount,
    failed_count: failedCount,
    unknown_count: unknownCount,
    skipped_count: skippedCount,
    duplicate_target_count: duplicateTargetCount,
    items,
  };
}

function inferSendSimulationOutcome(
  draft: BroadcastDraftMock,
): 'sent' | 'failed' | 'unknown' {
  const haystack = [
    draft.group_value,
    draft.target_conversation_name || '',
    draft.draft_text,
  ]
    .join(' ')
    .toLowerCase();
  if (
    haystack.includes('[send:unknown]') ||
    haystack.includes('__send_unknown__')
  ) {
    return 'unknown';
  }
  if (
    haystack.includes('[send:failed]') ||
    haystack.includes('__send_failed__')
  ) {
    return 'failed';
  }
  return 'sent';
}

function simulateSendBatch(
  state: LangBotApiMockState,
  batch: BroadcastExecutionBatchMock,
  tasks: BroadcastExecutionTaskMock[],
  drafts: BroadcastDraftMock[],
) {
  batch.status = 'running';
  batch.started_at = batch.started_at || now();
  batch.paused_at = null;
  const draftById = new Map(drafts.map((draft) => [draft.id, draft] as const));
  for (const task of tasks) {
    const draft = draftById.get(task.draft_id ?? -1);
    if (!draft) {
      createExecutionAttempt(state, task, {
        status: 'failed',
        action: 'send_message',
        runtime_state: 'failed',
        send_triggered: false,
        evidence_summary: 'Draft not found during send simulation',
        error_code: 'BROADCAST_DRAFT_NOT_FOUND',
        error_message: 'Draft not found',
        response_summary: {
          id: `runtime-${task.id}`,
          status: 'failed',
          stage: 'draft_lookup_failed',
          result: {
            enterDispatched: false,
            messageSent: false,
            terminalConfirmed: true,
            terminalSource: 'runtime',
          },
        },
        technical_details: {
          enter_dispatched: false,
          message_sent: false,
        },
      });
      continue;
    }
    const outcome = inferSendSimulationOutcome(draft);
    if (outcome === 'failed') {
      createExecutionAttempt(state, task, {
        status: 'failed',
        action: 'send_message',
        runtime_state: 'failed',
        send_triggered: false,
        evidence_summary: 'Send failed before pressing Enter',
        error_code: 'BROADCAST_PRE_SEND_VERIFICATION_FAILED',
        error_message: 'Unable to verify the prepared message before sending',
        response_summary: {
          id: `runtime-${task.id}`,
          status: 'failed',
          stage: 'pre_send_verification_failed',
          result: {
            enterDispatched: false,
            messageSent: false,
            terminalConfirmed: true,
            terminalSource: 'runtime',
          },
        },
        technical_details: {
          enter_dispatched: false,
          message_sent: false,
        },
      });
      draft.send_status = 'pending';
      draft.sent_at = null;
      draft.error_message =
        'Unable to verify the prepared message before sending';
      draft.updated_at = now();
      continue;
    }
    if (outcome === 'unknown') {
      createExecutionAttempt(state, task, {
        status: 'interrupted',
        action: 'send_message',
        runtime_state: 'sent_unconfirmed',
        send_triggered: true,
        evidence_summary: '已执行发送操作，请人工检查目标会话',
        error_code: 'BROADCAST_SEND_RESULT_UNKNOWN',
        error_message: '已执行发送操作，请人工检查目标会话',
        response_summary: {
          id: `runtime-${task.id}`,
          status: 'succeeded_with_warning',
          stage: 'sent_unconfirmed',
          result: {
            enterDispatched: true,
            messageSent: null,
            terminalConfirmed: true,
            terminalSource: 'runtime',
            retryAllowed: false,
          },
        },
        technical_details: {
          enter_dispatched: true,
          message_sent: null,
          terminal_source: 'runtime',
        },
      });
      draft.send_status = 'unknown';
      draft.sent_at = null;
      draft.error_message = '已执行发送操作，请人工检查目标会话';
      draft.updated_at = now();
      continue;
    }
    createExecutionAttempt(state, task, {
      status: 'succeeded',
      action: 'send_message',
      runtime_state: 'send_verified',
      send_triggered: true,
      evidence_summary: 'Message sent',
      response_summary: {
        id: `runtime-${task.id}`,
        status: 'succeeded',
        stage: 'message_sent',
        result: {
          enterDispatched: true,
          messageSent: true,
          terminalConfirmed: true,
          terminalSource: 'runtime',
        },
      },
      technical_details: {
        enter_dispatched: true,
        message_sent: true,
      },
    });
    draft.send_status = 'sent';
    draft.sent_at = now();
    draft.error_message = null;
    draft.updated_at = now();
  }
  syncExecutionBatchCounts(state, batch.id);
}

function createExecutionAttempt(
  state: LangBotApiMockState,
  task: BroadcastExecutionTaskMock,
  payload: {
    status: string;
    action: 'paste_draft' | 'send_message';
    runtime_state: string;
    send_triggered: boolean;
    evidence_summary: string;
    error_code?: string | null;
    error_message?: string | null;
    response_summary?: JsonRecord | null;
    technical_details?: JsonRecord | null;
  },
) {
  const timestamp = now();
  const attemptId = Number(
    nextId(state, 'broadcast-execution-attempt').split('-').pop(),
  );
  const evidenceId = Number(
    nextId(state, 'broadcast-execution-evidence').split('-').pop(),
  );
  const nextAttemptNo = task.attempt_count + 1;
  task.attempt_count = nextAttemptNo;
  task.runtime_task_id = `runtime-${attemptId}`;
  task.idempotency_key = `broadcast:${task.id}:${nextAttemptNo}`;
  task.started_at = task.started_at || timestamp;
  task.finished_at = timestamp;
  task.updated_at = timestamp;
  task.error_code = payload.error_code || null;
  task.error_message = payload.error_message || null;
  task.status = payload.status;

  const attempt: BroadcastExecutionAttemptMock = {
    id: attemptId,
    execution_task_id: task.id,
    attempt_no: nextAttemptNo,
    idempotency_key: task.idempotency_key,
    request_digest: task.request_digest,
    runtime_task_id: task.runtime_task_id,
    request_summary: JSON.stringify({ action: payload.action }),
    response_summary: JSON.stringify(
      payload.response_summary ?? { status: payload.status },
    ),
    status: payload.status,
    error_code: payload.error_code || null,
    error_message: payload.error_message || null,
    started_at: timestamp,
    finished_at: timestamp,
  };

  const evidence: BroadcastExecutionEvidenceMock = {
    id: evidenceId,
    execution_attempt_id: attemptId,
    window_title: 'WeCom Test Window',
    target_conversation: task.target_conversation_snapshot,
    action: payload.action,
    input_located: true,
    draft_written: true,
    send_triggered: payload.send_triggered,
    clipboard_restored: true,
    runtime_state: payload.runtime_state,
    evidence_summary: payload.evidence_summary,
    technical_details:
      payload.action === 'paste_draft'
        ? {
            content_verified: payload.status === 'succeeded',
            verification_method: 'windows_uia',
            verification_error_code: payload.error_code || null,
          }
        : (payload.technical_details ?? null),
    created_at: timestamp,
  };

  state.broadcastExecutionAttempts = [
    ...state.broadcastExecutionAttempts.filter((item) => item.id !== attemptId),
    attempt,
  ];
  state.broadcastExecutionEvidence = [
    ...state.broadcastExecutionEvidence.filter(
      (item) => item.id !== evidenceId,
    ),
    evidence,
  ];
  syncTaskDerivedState(state, task);
}

function seedBroadcastState(): Pick<
  LangBotApiMockState,
  | 'broadcastTemplates'
  | 'broadcastVariableProfile'
  | 'broadcastGroupRules'
  | 'broadcastGroupNames'
> {
  const timestamp = now();
  return {
    broadcastTemplates: [
      {
        id: 1,
        bot_uuid: 'bot-1',
        connector_id: 'wxwork-local',
        name: 'Arrival Reminder',
        content:
          'Hello {{customer_name}},\nShipment {{shipment_no}} is expected to arrive on {{eta_date}}.',
        variables: ['customer_name', 'shipment_no', 'eta_date'],
        enabled: true,
        created_at: timestamp,
        updated_at: timestamp,
      },
      {
        id: 2,
        bot_uuid: 'bot-1',
        connector_id: 'wxwork-local',
        name: 'Payment Notice',
        content:
          'Hi {{customer_name}},\nInvoice {{invoice_no}} is awaiting confirmation.',
        variables: ['customer_name', 'invoice_no'],
        enabled: true,
        created_at: timestamp,
        updated_at: timestamp,
      },
    ],
    broadcastVariableProfile: {
      group_field: 'Customer Name',
      mapping_rules: [
        {
          source_field: 'Customer Name',
          variable_key: 'customer_name',
          merge_mode: 'first',
          order: 1,
        },
        {
          source_field: 'Shipment No',
          variable_key: 'shipment_no',
          merge_mode: 'first',
          order: 2,
        },
        {
          source_field: 'ETA Date',
          variable_key: 'eta_date',
          merge_mode: 'first',
          order: 3,
        },
      ],
    },
    broadcastGroupRules: [
      {
        id: 1,
        bot_uuid: 'bot-1',
        connector_id: 'wxwork-local',
        source_value: 'Acme Freight',
        match_type: 'exact',
        match_expression: 'Acme Freight',
        target_conversation_id: 'acme-freight-ops',
        target_conversation_name: 'Acme Freight Ops',
        priority: 30,
        enabled: true,
        created_at: timestamp,
        updated_at: timestamp,
      },
    ],
    broadcastGroupNames: [
      {
        id: 1,
        bot_uuid: 'bot-1',
        connector_id: 'wxwork-local',
        name: 'Acme Freight Ops',
        external_conversation_id: 'acme-freight-ops',
        created_at: timestamp,
        updated_at: timestamp,
      },
      {
        id: 2,
        bot_uuid: 'bot-1',
        connector_id: 'wxwork-local',
        name: 'Northwind Service Group',
        external_conversation_id: 'northwind-service-group',
        created_at: timestamp,
        updated_at: timestamp,
      },
    ],
  };
}

function getMockImportScenario(
  state: LangBotApiMockState,
  fileName: string,
): {
  headers: string[];
  rows: Array<Record<string, string>>;
  groupFieldUsed?: string | null;
  groupFieldSource?: BroadcastImportGroupFieldSource;
  confirmationCandidates?: string[];
} {
  if (/field-confirmation/i.test(fileName)) {
    return {
      headers: ['客户名称', '客户', '运单号'],
      rows: [
        {
          客户名称: 'Acme Freight',
          客户: 'Acme Alias',
          运单号: 'SO-100',
        },
        {
          客户名称: 'Northwind Service Group',
          客户: 'Northwind Alias',
          运单号: 'SO-101',
        },
      ],
      confirmationCandidates: ['客户名称', '客户'],
    };
  }

  if (/username-import/i.test(fileName)) {
    return {
      headers: ['用户名', '客户名称', '运单号'],
      rows: [
        {
          用户名: 'Acme Freight',
          客户名称: 'Acme Freight',
          运单号: 'SO-100',
        },
        {
          用户名: 'northwind_user',
          客户名称: 'Northwind Service Group',
          运单号: 'SO-101',
        },
      ],
      groupFieldUsed: '用户名',
      groupFieldSource: 'auto_detected',
    };
  }

  const groupField =
    state.broadcastVariableProfile.group_field || 'Customer Name';
  return {
    headers: [groupField, 'Shipment No', 'ETA Date'],
    rows: [
      {
        [groupField]: 'Acme Freight',
        'Shipment No': 'SO-100',
        'ETA Date': '2026-07-05',
      },
      {
        [groupField]: 'Northwind Service Group',
        'Shipment No': 'SO-101',
        'ETA Date': '2026-07-06',
      },
      { [groupField]: '', 'Shipment No': 'SO-102', 'ETA Date': '2026-07-07' },
    ],
    groupFieldUsed: groupField,
    groupFieldSource: 'configured',
  };
}

function mockAdapters() {
  return [
    {
      name: 'playwright-adapter',
      label: {
        en_US: 'Playwright Adapter',
        zh_Hans: 'Playwright 适配器',
      },
      description: {
        en_US: 'Minimal adapter for frontend E2E tests.',
        zh_Hans: '用于前端 E2E 测试的最小适配器。',
      },
      spec: {
        categories: ['testing'],
        config: [],
      },
    },
  ];
}

async function handleBackendApi(
  route: Route,
  state: LangBotApiMockState,
  seedDefaultDrafts: boolean,
) {
  const request = route.request();
  const url = new URL(request.url());
  const path = url.pathname;
  const method = request.method();

  if (path === '/api/v1/system/info') {
    return fulfillJson(route, {
      debug: false,
      version: 'frontend-smoke',
      edition: 'community',
      cloud_service_url: 'https://space.langbot.app',
      enable_marketplace: true,
      allow_modify_login_info: true,
      disable_models_service: false,
      limitation: {
        max_bots: -1,
        max_pipelines: -1,
        max_extensions: -1,
      },
      outbound_ips: [],
      wizard_status: 'completed',
      wizard_progress: null,
    });
  }

  if (path === '/api/v1/user/info') {
    return fulfillJson(route, {
      user: 'admin@example.com',
      account_type: 'local',
      has_password: true,
    });
  }

  if (path === '/api/v1/user/space-credits') {
    return fulfillJson(route, { credits: null });
  }

  if (path === '/api/v1/platform/adapters') {
    return fulfillJson(route, { adapters: mockAdapters() });
  }

  if (path === '/api/v1/platform/bots') {
    if (method === 'POST') {
      const bot = makeBot(state, parseJsonBody(route));
      state.bots = [
        ...state.bots.filter((item) => item.uuid !== bot.uuid),
        bot,
      ];
      return fulfillJson(route, { uuid: bot.uuid });
    }

    return fulfillJson(route, { bots: state.bots });
  }

  if (path === '/api/v1/broadcast/templates') {
    const botUuid = url.searchParams.get('bot_uuid');
    const connectorId = url.searchParams.get('connector_id');

    if (method === 'GET') {
      const templates = state.broadcastTemplates.filter(
        (template) =>
          template.bot_uuid === botUuid &&
          template.connector_id === connectorId,
      );
      return fulfillJson(route, templates);
    }

    if (method === 'POST') {
      const body = parseJsonBody(route);
      const content = String(body.content || '');
      const template: BroadcastTemplateMock = {
        id: Number(nextId(state, 'broadcast-template').split('-').pop()),
        bot_uuid: String(body.bot_uuid || ''),
        connector_id: String(body.connector_id || ''),
        name: String(body.name || ''),
        content,
        variables: extractTemplateVariables(content),
        enabled: body.enabled !== false,
        created_at: now(),
        updated_at: now(),
      };
      state.broadcastTemplates = [
        ...state.broadcastTemplates.filter((item) => item.id !== template.id),
        template,
      ];
      return fulfillJson(route, template);
    }
  }

  const templateDetailMatch = path.match(
    /^\/api\/v1\/broadcast\/templates\/(\d+)$/,
  );
  if (templateDetailMatch) {
    const templateId = Number(templateDetailMatch[1]);
    const botUuid = url.searchParams.get('bot_uuid');
    const connectorId = url.searchParams.get('connector_id');

    if (method === 'PUT') {
      const body = parseJsonBody(route);
      const content = String(body.content || '');
      const existing = state.broadcastTemplates.find(
        (item) => item.id === templateId,
      );
      const template: BroadcastTemplateMock = {
        id: templateId,
        bot_uuid: String(body.bot_uuid || existing?.bot_uuid || ''),
        connector_id: String(body.connector_id || existing?.connector_id || ''),
        name: String(body.name || existing?.name || ''),
        content,
        variables: extractTemplateVariables(content),
        enabled: body.enabled !== false,
        created_at: existing?.created_at || now(),
        updated_at: now(),
      };
      state.broadcastTemplates = [
        ...state.broadcastTemplates.filter((item) => item.id !== templateId),
        template,
      ];
      return fulfillJson(route, template);
    }

    if (method === 'DELETE') {
      state.broadcastTemplates = state.broadcastTemplates.filter(
        (item) =>
          !(
            item.id === templateId &&
            item.bot_uuid === botUuid &&
            item.connector_id === connectorId
          ),
      );
      return fulfillJson(route, { deleted: true });
    }
  }

  if (path === '/api/v1/broadcast/templates/render' && method === 'POST') {
    const body = parseJsonBody(route);
    const templateId = Number(body.template_id || 0);
    const variables =
      (body.variables as Record<string, unknown> | undefined) || {};
    const template =
      templateId > 0
        ? state.broadcastTemplates.find((item) => item.id === templateId)
        : null;
    const content = template ? template.content : String(body.content || '');
    return fulfillJson(route, renderBroadcastTemplate(content, variables));
  }

  if (path === '/api/v1/broadcast/variable-profile') {
    if (method === 'GET') {
      return fulfillJson(route, state.broadcastVariableProfile);
    }

    if (method === 'PUT') {
      const body = parseJsonBody(route);
      const groupField = String(body.group_field || '').trim();
      const mappingRules = Array.isArray(body.mapping_rules)
        ? (body.mapping_rules as BroadcastVariableProfileMock['mapping_rules'])
        : [];
      const issues: string[] = [];
      const seenKeys = new Set<string>();

      if (!groupField) {
        issues.push('请填写分组字段');
      }

      mappingRules.forEach((rule, index) => {
        const row = index + 1;
        const sourceField = String(rule.source_field || '').trim();
        const variableKey = String(rule.variable_key || '').trim();
        if (sourceField && !variableKey) {
          issues.push(`第 ${row} 条规则缺少消息变量`);
        }
        if (!sourceField && variableKey) {
          issues.push(`第 ${row} 条规则缺少表格字段`);
        }
        if (
          (sourceField.includes('{{') || sourceField.includes('}}')) &&
          sourceField
        ) {
          issues.push(
            `请填写“${sourceField.replace(/[{}]/g, '')}”，不要填写“${sourceField}”`,
          );
        }
        if (
          (variableKey.includes('{{') || variableKey.includes('}}')) &&
          variableKey
        ) {
          issues.push(
            `请填写“${sourceField || '消息变量'}”，不要填写“${variableKey}”`,
          );
        }
        if (
          ![
            'first',
            'lines',
            'unique_lines',
            'commas',
            'unique_commas',
          ].includes(String(rule.merge_mode || ''))
        ) {
          issues.push(`第 ${row} 条规则的多条数据处理方式无效`);
        }
        if (variableKey) {
          if (seenKeys.has(variableKey)) {
            issues.push(`消息变量“${variableKey}”重复`);
          } else {
            seenKeys.add(variableKey);
          }
        }
      });

      if (issues.length > 0) {
        const message =
          issues.some((item) => item.includes('缺少')) ||
          issues.includes('请填写分组字段')
            ? '变量配置填写不完整，请检查后重试'
            : '变量配置填写有误，请按提示修改';
        return fulfillError(
          route,
          400,
          'BROADCAST_VARIABLE_PROFILE_INVALID',
          message,
          issues,
        );
      }

      state.broadcastVariableProfile = {
        group_field:
          typeof body.group_field === 'string' ? body.group_field : null,
        mapping_rules: Array.isArray(body.mapping_rules)
          ? (body.mapping_rules as BroadcastVariableProfileMock['mapping_rules'])
          : [],
      };
      return fulfillJson(route, state.broadcastVariableProfile);
    }
  }

  if (path === '/api/v1/broadcast/group-rules') {
    const botUuid = url.searchParams.get('bot_uuid');
    const connectorId = url.searchParams.get('connector_id');

    if (method === 'GET') {
      const rules = state.broadcastGroupRules
        .filter(
          (rule) =>
            rule.bot_uuid === botUuid && rule.connector_id === connectorId,
        )
        .sort((left, right) => right.priority - left.priority);
      return fulfillJson(route, rules);
    }

    if (method === 'POST') {
      const body = parseJsonBody(route);
      const rule: BroadcastGroupRuleMock = {
        id: Number(nextId(state, 'broadcast-group-rule').split('-').pop()),
        bot_uuid: String(body.bot_uuid || ''),
        connector_id: String(body.connector_id || ''),
        source_value: String(body.source_value || ''),
        match_type:
          (body.match_type as BroadcastGroupRuleMock['match_type']) || 'exact',
        match_expression: String(body.match_expression || ''),
        target_conversation_id:
          typeof body.target_conversation_id === 'string'
            ? body.target_conversation_id
            : null,
        target_conversation_name: String(body.target_conversation_name || ''),
        priority: Number(body.priority || 0),
        enabled: body.enabled !== false,
        created_at: now(),
        updated_at: now(),
      };
      state.broadcastGroupRules = [
        ...state.broadcastGroupRules.filter((item) => item.id !== rule.id),
        rule,
      ];
      return fulfillJson(route, rule);
    }
  }

  const groupRuleDetailMatch = path.match(
    /^\/api\/v1\/broadcast\/group-rules\/(\d+)$/,
  );
  if (groupRuleDetailMatch) {
    const ruleId = Number(groupRuleDetailMatch[1]);
    const botUuid = url.searchParams.get('bot_uuid');
    const connectorId = url.searchParams.get('connector_id');

    if (method === 'PUT') {
      const body = parseJsonBody(route);
      const existing = state.broadcastGroupRules.find(
        (item) => item.id === ruleId,
      );
      const rule: BroadcastGroupRuleMock = {
        id: ruleId,
        bot_uuid: String(body.bot_uuid || existing?.bot_uuid || ''),
        connector_id: String(body.connector_id || existing?.connector_id || ''),
        source_value: String(body.source_value || existing?.source_value || ''),
        match_type:
          (body.match_type as BroadcastGroupRuleMock['match_type']) ||
          existing?.match_type ||
          'exact',
        match_expression: String(
          body.match_expression || existing?.match_expression || '',
        ),
        target_conversation_id:
          typeof body.target_conversation_id === 'string'
            ? body.target_conversation_id
            : (existing?.target_conversation_id ?? null),
        target_conversation_name: String(
          body.target_conversation_name ||
            existing?.target_conversation_name ||
            '',
        ),
        priority: Number(body.priority ?? existing?.priority ?? 0),
        enabled: body.enabled !== false,
        created_at: existing?.created_at || now(),
        updated_at: now(),
      };
      state.broadcastGroupRules = [
        ...state.broadcastGroupRules.filter((item) => item.id !== ruleId),
        rule,
      ];
      return fulfillJson(route, rule);
    }

    if (method === 'DELETE') {
      state.broadcastGroupRules = state.broadcastGroupRules.filter(
        (item) =>
          !(
            item.id === ruleId &&
            item.bot_uuid === botUuid &&
            item.connector_id === connectorId
          ),
      );
      return fulfillJson(route, { deleted: true });
    }
  }

  if (path === '/api/v1/broadcast/group-rules/match' && method === 'POST') {
    const body = parseJsonBody(route);
    const botUuid = String(body.bot_uuid || '');
    const connectorId = String(body.connector_id || '');
    const sourceValue = String(body.source_value || '');
    const matchedRule =
      state.broadcastGroupRules
        .filter(
          (rule) =>
            rule.bot_uuid === botUuid &&
            rule.connector_id === connectorId &&
            matchBroadcastRule(rule, sourceValue),
        )
        .sort((left, right) => right.priority - left.priority)[0] || null;

    return fulfillJson(route, {
      matched: Boolean(matchedRule),
      rule_id: matchedRule?.id || null,
      target_conversation_name: matchedRule?.target_conversation_name || null,
      match_type: matchedRule?.match_type || null,
    });
  }

  if (path === '/api/v1/broadcast/group-names') {
    const botUuid = url.searchParams.get('bot_uuid');
    const connectorId = url.searchParams.get('connector_id');

    if (method === 'GET') {
      const names = state.broadcastGroupNames.filter(
        (item) =>
          item.bot_uuid === botUuid && item.connector_id === connectorId,
      );
      return fulfillJson(route, names);
    }

    if (method === 'POST') {
      const body = parseJsonBody(route);
      const bot_uuid = String(body.bot_uuid || '');
      const connector_id = String(body.connector_id || '');
      const singleGroupName = String(body.group_name || '').trim();
      if (singleGroupName) {
        const existing =
          state.broadcastGroupNames.find(
            (item) =>
              item.bot_uuid === bot_uuid &&
              item.connector_id === connector_id &&
              item.name === singleGroupName,
          ) ?? null;
        if (existing) {
          return fulfillJson(route, {
            status: 'already_exists',
            group: existing,
          });
        }
        const created = {
          id: Number(nextId(state, 'broadcast-group-name').split('-').pop()),
          bot_uuid,
          connector_id,
          name: singleGroupName,
          external_conversation_id: null,
          created_at: now(),
          updated_at: now(),
        };
        state.broadcastGroupNames = [...state.broadcastGroupNames, created];
        return fulfillJson(route, {
          status: 'created',
          group: created,
        });
      }
      const rawNames = Array.isArray(body.names)
        ? body.names
        : body.name
          ? [body.name]
          : [];
      const uniqueNames = Array.from(
        new Set(rawNames.map((item) => String(item).trim()).filter(Boolean)),
      ).filter(
        (name) =>
          !state.broadcastGroupNames.some(
            (item) =>
              item.bot_uuid === bot_uuid &&
              item.connector_id === connector_id &&
              item.name === name,
          ),
      );
      const created = uniqueNames.map((name) => ({
        id: Number(nextId(state, 'broadcast-group-name').split('-').pop()),
        bot_uuid,
        connector_id,
        name,
        external_conversation_id: null,
        created_at: now(),
        updated_at: now(),
      }));
      state.broadcastGroupNames = [...state.broadcastGroupNames, ...created];
      return fulfillJson(route, { group_names: created });
    }
  }

  const groupNameDetailMatch = path.match(
    /^\/api\/v1\/broadcast\/group-names\/(\d+)$/,
  );
  if (groupNameDetailMatch && method === 'DELETE') {
    const groupNameId = Number(groupNameDetailMatch[1]);
    const botUuid = url.searchParams.get('bot_uuid');
    const connectorId = url.searchParams.get('connector_id');
    state.broadcastGroupNames = state.broadcastGroupNames.filter(
      (item) =>
        !(
          item.id === groupNameId &&
          item.bot_uuid === botUuid &&
          item.connector_id === connectorId
        ),
    );
    return fulfillJson(route, { deleted: true });
  }

  if (path === '/api/v1/broadcast/imports') {
    const botUuid = url.searchParams.get('bot_uuid');
    const connectorId = url.searchParams.get('connector_id');

    if (method === 'GET') {
      const batches = state.broadcastImportBatches.filter(
        (item) =>
          item.bot_uuid === botUuid && item.connector_id === connectorId,
      );
      return fulfillJson(route, batches);
    }

    if (method === 'POST') {
      const form = request.postDataBuffer()?.toString('utf-8') || '';
      const fileNameMatch = form.match(/filename=\"([^\"]+)\"/);
      const fileName = fileNameMatch?.[1] || 'customers.csv';
      const uploadBotUuid =
        parseMultipartTextField(form, 'bot_uuid') || botUuid || 'bot-1';
      const uploadConnectorId =
        parseMultipartTextField(form, 'connector_id') ||
        connectorId ||
        'wxwork-local';
      const groupFieldOverride = parseMultipartTextField(
        form,
        'group_field_override',
      );
      const scenario = getMockImportScenario(state, fileName);

      if (scenario.confirmationCandidates && !groupFieldOverride) {
        return fulfillError(
          route,
          409,
          'BROADCAST_IMPORT_GROUP_FIELD_CONFIRMATION_REQUIRED',
          'The customer grouping field could not be determined uniquely. Confirm the field and upload again.',
          {
            headers: scenario.headers,
            candidates: scenario.confirmationCandidates,
            configured_group_field: state.broadcastVariableProfile.group_field,
            original_file_name: fileName,
          },
        );
      }

      if (
        groupFieldOverride &&
        !scenario.headers.includes(groupFieldOverride)
      ) {
        return fulfillError(
          route,
          400,
          'BROADCAST_IMPORT_GROUP_FIELD_OVERRIDE_INVALID',
          'The selected customer field does not exist in the uploaded file headers.',
          {
            group_field_override: groupFieldOverride,
            headers: scenario.headers,
            original_file_name: fileName,
          },
        );
      }

      const groupFieldUsed =
        groupFieldOverride ||
        scenario.groupFieldUsed ||
        state.broadcastVariableProfile.group_field ||
        scenario.headers[0] ||
        'Customer Name';
      const groupFieldSource = groupFieldOverride
        ? ('user_confirmed' as BroadcastImportGroupFieldSource)
        : (scenario.groupFieldSource ?? 'configured');

      const parsedRows: BroadcastImportRowMock[] = scenario.rows.map(
        (rawRow, index) => {
          const groupValue = String(rawRow[groupFieldUsed] || '').trim();
          if (!groupValue) {
            return {
              id: Number(
                nextId(state, 'broadcast-import-row').split('-').pop(),
              ),
              import_batch_id: 0,
              source_row_number: index + 2,
              raw_data: rawRow,
              group_value: null,
              matched_conversation_name: null,
              matched_rule_id: null,
              match_status: 'invalid',
              error_message: '客户分组字段为空',
              created_at: now(),
            };
          }
          const resolved = resolveImportMatch(
            state,
            uploadBotUuid,
            uploadConnectorId,
            groupValue,
          );
          return {
            id: Number(nextId(state, 'broadcast-import-row').split('-').pop()),
            import_batch_id: 0,
            source_row_number: index + 2,
            raw_data: rawRow,
            group_value: groupValue,
            matched_conversation_name: resolved.matched_conversation_name,
            matched_rule_id: resolved.matched_rule_id,
            match_status: resolved.match_status,
            error_message: resolved.error_message,
            created_at: now(),
          };
        },
      );

      const batchId = Number(
        nextId(state, 'broadcast-import-batch').split('-').pop(),
      );
      const boundRows = parsedRows.map((row) => ({
        ...row,
        import_batch_id: batchId,
      }));
      const batch: BroadcastImportBatchMock = {
        id: batchId,
        bot_uuid: uploadBotUuid,
        connector_id: uploadConnectorId,
        original_file_name: fileName,
        file_type: fileName.endsWith('.xlsx') ? 'xlsx' : 'csv',
        worksheet_name: fileName.endsWith('.xlsx') ? 'Sheet1' : null,
        status: 'imported',
        drafts_stale: false,
        total_rows: boundRows.length,
        valid_rows: boundRows.filter((row) => row.match_status !== 'invalid')
          .length,
        invalid_rows: boundRows.filter((row) => row.match_status === 'invalid')
          .length,
        matched_rows: boundRows.filter((row) => row.match_status === 'matched')
          .length,
        unmatched_rows: boundRows.filter(
          (row) => row.match_status === 'unmatched',
        ).length,
        group_field_used: groupFieldUsed,
        group_field_source: groupFieldSource,
        created_at: now(),
        updated_at: now(),
      };
      state.broadcastImportBatches = [batch, ...state.broadcastImportBatches];
      state.broadcastImportRows = [...boundRows, ...state.broadcastImportRows];
      const initialGroups = buildImportGroupsResponse(state, batchId, {
        matchStatus: null,
        keyword: '',
        page: 1,
        pageSize: Math.max(1, boundRows.length),
      }).groups;
      for (const group of initialGroups) {
        const key = groupAttachmentMapKey(batchId, group.group_key);
        state.broadcastGroupAttachments[key] =
          state.broadcastGroupAttachments[key] ?? [];
      }
      return fulfillJson(route, batch);
    }
  }

  const importDetailMatch = path.match(
    /^\/api\/v1\/broadcast\/imports\/(\d+)$/,
  );
  if (importDetailMatch) {
    const importId = Number(importDetailMatch[1]);
    if (method === 'GET') {
      const batch = state.broadcastImportBatches.find(
        (item) => item.id === importId,
      );
      if (!batch) {
        return fulfillError(
          route,
          404,
          'BROADCAST_IMPORT_NOT_FOUND',
          '当前导入批次不存在或已被删除',
        );
      }
      const page = Math.max(1, Number(url.searchParams.get('page') || '1'));
      const pageSize = Math.min(
        200,
        Math.max(1, Number(url.searchParams.get('page_size') || '50')),
      );
      const rows = state.broadcastImportRows.filter(
        (item) => item.import_batch_id === importId,
      );
      const offset = (page - 1) * pageSize;
      return fulfillJson(route, {
        ...batch,
        rows: rows.slice(offset, offset + pageSize),
        page,
        page_size: pageSize,
        total: rows.length,
        total_pages: rows.length === 0 ? 0 : Math.ceil(rows.length / pageSize),
      });
    }

    if (method === 'DELETE') {
      state.broadcastImportBatches = state.broadcastImportBatches.filter(
        (item) => item.id !== importId,
      );
      state.broadcastImportRows = state.broadcastImportRows.filter(
        (item) => item.import_batch_id !== importId,
      );
      state.broadcastDrafts = state.broadcastDrafts.filter(
        (item) => item.import_batch_id !== importId,
      );
      Object.keys(state.broadcastGroupAttachments).forEach((key) => {
        if (key.startsWith(`${importId}:`)) {
          delete state.broadcastGroupAttachments[key];
        }
      });
      return fulfillJson(route, { deleted: true });
    }
  }

  const importGroupsMatch = path.match(
    /^\/api\/v1\/broadcast\/imports\/(\d+)\/groups$/,
  );
  if (importGroupsMatch && method === 'GET') {
    const importId = Number(importGroupsMatch[1]);
    const page = Math.max(1, Number(url.searchParams.get('page') || '1'));
    const pageSize = Math.min(
      200,
      Math.max(1, Number(url.searchParams.get('page_size') || '50')),
    );
    return fulfillJson(
      route,
      buildImportGroupsResponse(state, importId, {
        matchStatus: url.searchParams.get('match_status'),
        keyword: url.searchParams.get('keyword') || '',
        page,
        pageSize,
      }),
    );
  }

  const importGroupRuleCandidatesMatch = path.match(
    /^\/api\/v1\/broadcast\/imports\/(\d+)\/group-rule-candidates$/,
  );
  if (importGroupRuleCandidatesMatch && method === 'GET') {
    const importId = Number(importGroupRuleCandidatesMatch[1]);
    const page = Math.max(1, Number(url.searchParams.get('page') || '1'));
    const pageSize = Math.min(
      200,
      Math.max(1, Number(url.searchParams.get('page_size') || '50')),
    );
    const response = buildImportGroupRuleCandidatesResponse(state, importId, {
      status: url.searchParams.get('status'),
      keyword: url.searchParams.get('keyword') || '',
      page,
      pageSize,
    });
    if (!response) {
      return fulfillError(
        route,
        404,
        'BROADCAST_IMPORT_NOT_FOUND',
        'Current import batch was not found.',
      );
    }
    return fulfillJson(route, response);
  }

  const importGroupRowsMatch = path.match(
    /^\/api\/v1\/broadcast\/imports\/(\d+)\/groups\/([^/]+)\/rows$/,
  );
  if (importGroupRowsMatch && method === 'GET') {
    const importId = Number(importGroupRowsMatch[1]);
    const groupKey = decodeURIComponent(importGroupRowsMatch[2]);
    const page = Math.max(1, Number(url.searchParams.get('page') || '1'));
    const pageSize = Math.min(
      200,
      Math.max(1, Number(url.searchParams.get('page_size') || '50')),
    );
    const groups = buildImportGroupsResponse(state, importId, {
      matchStatus: null,
      keyword: '',
      page: 1,
      pageSize: Number.MAX_SAFE_INTEGER,
    }).groups;
    const group = groups.find((item) => item.group_key === groupKey);
    if (!group) {
      return fulfillError(
        route,
        404,
        'BROADCAST_IMPORT_GROUP_NOT_FOUND',
        'Current broadcast import group was not found.',
      );
    }
    const rows = state.broadcastImportRows
      .filter((item) => item.import_batch_id === importId)
      .filter(
        (item) =>
          makeGroupKey(
            importId,
            item.group_value ?? `__invalid__:${item.id}`,
          ) === groupKey,
      )
      .sort((left, right) => left.source_row_number - right.source_row_number);
    const offset = (page - 1) * pageSize;
    return fulfillJson(route, {
      group_key: groupKey,
      group_value: group.group_value,
      page,
      page_size: pageSize,
      total: rows.length,
      total_pages: rows.length === 0 ? 0 : Math.ceil(rows.length / pageSize),
      rows: rows.slice(offset, offset + pageSize),
    });
  }

  const importGroupAttachmentsMatch = path.match(
    /^\/api\/v1\/broadcast\/imports\/(\d+)\/groups\/([^/]+)\/attachments$/,
  );
  if (importGroupAttachmentsMatch && method === 'POST') {
    const importId = Number(importGroupAttachmentsMatch[1]);
    const groupKey = decodeURIComponent(importGroupAttachmentsMatch[2]);
    const groups = buildImportGroupsResponse(state, importId, {
      matchStatus: null,
      keyword: '',
      page: 1,
      pageSize: Number.MAX_SAFE_INTEGER,
    }).groups;
    const group = groups.find((item) => item.group_key === groupKey);
    if (!group) {
      return fulfillError(
        route,
        404,
        'BROADCAST_IMPORT_GROUP_NOT_FOUND',
        'Current broadcast import group was not found.',
      );
    }
    const form = request.postDataBuffer()?.toString('utf-8') || '';
    const fileNames = Array.from(form.matchAll(/filename=\"([^\"]+)\"/g)).map(
      (match) => match[1],
    );
    const key = groupAttachmentMapKey(importId, groupKey);
    const current = state.broadcastGroupAttachments[key] ?? [];
    state.broadcastGroupAttachments[key] = [
      ...current,
      ...fileNames.map((name, index) =>
        createAttachment(state, name, current.length + index + 1),
      ),
    ];
    markGroupAttachmentsChanged(state, importId, group.group_value);
    return fulfillJson(
      route,
      (state.broadcastGroupAttachments[key] ?? []).map(cloneAttachment),
    );
  }

  const importGroupAttachmentDetailMatch = path.match(
    /^\/api\/v1\/broadcast\/imports\/(\d+)\/groups\/([^/]+)\/attachments\/(\d+)$/,
  );
  if (importGroupAttachmentDetailMatch && method === 'DELETE') {
    const importId = Number(importGroupAttachmentDetailMatch[1]);
    const groupKey = decodeURIComponent(importGroupAttachmentDetailMatch[2]);
    const attachmentId = Number(importGroupAttachmentDetailMatch[3]);
    const key = groupAttachmentMapKey(importId, groupKey);
    const groups = buildImportGroupsResponse(state, importId, {
      matchStatus: null,
      keyword: '',
      page: 1,
      pageSize: Number.MAX_SAFE_INTEGER,
    }).groups;
    const group = groups.find((item) => item.group_key === groupKey);
    state.broadcastGroupAttachments[key] = (
      state.broadcastGroupAttachments[key] ?? []
    ).filter((item) => item.id !== attachmentId);
    if (group) {
      markGroupAttachmentsChanged(state, importId, group.group_value);
    }
    return fulfillJson(
      route,
      (state.broadcastGroupAttachments[key] ?? []).map(cloneAttachment),
    );
  }

  const rematchMatch = path.match(
    /^\/api\/v1\/broadcast\/imports\/(\d+)\/rematch$/,
  );
  if (rematchMatch && method === 'POST') {
    const importId = Number(rematchMatch[1]);
    const batch = state.broadcastImportBatches.find(
      (item) => item.id === importId,
    );
    if (!batch) {
      return fulfillError(
        route,
        404,
        'BROADCAST_IMPORT_NOT_FOUND',
        '当前导入批次不存在或已被删除',
      );
    }
    state.broadcastImportRows = state.broadcastImportRows.map((row) => {
      if (row.import_batch_id !== importId || !row.group_value?.trim()) {
        return row;
      }
      const nextMatch = resolveImportMatch(
        state,
        batch.bot_uuid,
        batch.connector_id,
        row.group_value,
      );
      return {
        ...row,
        matched_conversation_name: nextMatch.matched_conversation_name,
        matched_rule_id: nextMatch.matched_rule_id,
        match_status: nextMatch.match_status,
        error_message: nextMatch.error_message,
      };
    });
    const syncResult = syncImportBatchCounts(state, importId);
    const rows = syncResult?.rows ?? [];
    batch.status = 'matched';
    batch.drafts_stale = true;
    syncDraftStaleFlags(state, importId);
    return fulfillJson(route, {
      ...batch,
      rows,
      page: 1,
      page_size: rows.length || 50,
      total: rows.length,
      total_pages: rows.length === 0 ? 0 : 1,
    });
  }

  const bulkAssignMatch = path.match(
    /^\/api\/v1\/broadcast\/imports\/(\d+)\/group-rules\/bulk-assign$/,
  );
  if (bulkAssignMatch && method === 'POST') {
    const importId = Number(bulkAssignMatch[1]);
    const batch = state.broadcastImportBatches.find(
      (item) => item.id === importId,
    );
    if (!batch) {
      return fulfillError(
        route,
        404,
        'BROADCAST_IMPORT_NOT_FOUND',
        'Current import batch was not found.',
      );
    }

    const body = parseJsonBody(route);
    const items = Array.isArray(body.items)
      ? (body.items as Array<JsonRecord>)
      : [];
    const groupsResponse = buildImportGroupsResponse(state, importId, {
      matchStatus: null,
      keyword: '',
      page: 1,
      pageSize: Number.MAX_SAFE_INTEGER,
    });
    const groupByKey = new Map(
      groupsResponse.groups.map((group) => [group.group_key, group] as const),
    );
    const groupNamesByStableId = new Map(
      state.broadcastGroupNames
        .filter(
          (groupName) =>
            groupName.bot_uuid === batch.bot_uuid &&
            groupName.connector_id === batch.connector_id &&
            Boolean(groupName.external_conversation_id?.trim()),
        )
        .map(
          (groupName) =>
            [groupName.external_conversation_id ?? '', groupName] as const,
        ),
    );

    const createdItems: Array<{
      group_key: string;
      customer_name: string;
      rule_id: number;
      target_conversation_id: string;
      target_conversation_name: string;
    }> = [];

    for (const item of items) {
      const groupKey = String(item.group_key || '').trim();
      const targetConversationId = String(
        item.target_conversation_id || '',
      ).trim();
      const group = groupByKey.get(groupKey);
      const targetConversation = groupNamesByStableId.get(targetConversationId);
      if (!group || !targetConversation || !group.group_value?.trim()) {
        return fulfillError(
          route,
          400,
          'BROADCAST_IMPORT_GROUP_RULE_BULK_ASSIGN_FAILED',
          'One or more bulk assignment items are invalid.',
          {
            items: items.map((entry) => ({
              group_key: String((entry as JsonRecord).group_key || ''),
              target_conversation_id: String(
                (entry as JsonRecord).target_conversation_id || '',
              ),
              code: 'BROADCAST_GROUP_RULE_DUPLICATE',
              message: 'Invalid group or conversation selection.',
            })),
          },
        );
      }

      const existingRule =
        state.broadcastGroupRules.find(
          (rule) =>
            rule.bot_uuid === batch.bot_uuid &&
            rule.connector_id === batch.connector_id &&
            rule.match_type === 'exact' &&
            rule.match_expression === group.group_value,
        ) ?? null;
      const ruleId =
        existingRule?.id ??
        Number(nextId(state, 'broadcast-group-rule').split('-').pop());
      const rule: BroadcastGroupRuleMock = {
        id: ruleId,
        bot_uuid: batch.bot_uuid,
        connector_id: batch.connector_id,
        source_value: group.group_value,
        match_type: 'exact',
        match_expression: group.group_value,
        target_conversation_id: targetConversation.external_conversation_id,
        target_conversation_name: targetConversation.name,
        priority: existingRule?.priority ?? 100,
        enabled: true,
        created_at: existingRule?.created_at ?? now(),
        updated_at: now(),
      };
      state.broadcastGroupRules = [
        ...state.broadcastGroupRules.filter((entry) => entry.id !== ruleId),
        rule,
      ];
      createdItems.push({
        group_key: groupKey,
        customer_name: group.group_value,
        rule_id: rule.id,
        target_conversation_id:
          targetConversation.external_conversation_id ?? '',
        target_conversation_name: targetConversation.name,
      });
    }

    state.broadcastImportRows = state.broadcastImportRows.map((row) => {
      if (row.import_batch_id !== importId || !row.group_value?.trim()) {
        return row;
      }
      const nextMatch = resolveImportMatch(
        state,
        batch.bot_uuid,
        batch.connector_id,
        row.group_value,
      );
      return {
        ...row,
        matched_conversation_name: nextMatch.matched_conversation_name,
        matched_rule_id: nextMatch.matched_rule_id,
        match_status: nextMatch.match_status,
        error_message: nextMatch.error_message,
      };
    });
    syncImportBatchCounts(state, importId);
    batch.status = 'matched';
    batch.drafts_stale = true;
    syncDraftStaleFlags(state, importId);

    return fulfillJson(route, {
      created_count: createdItems.length,
      group_field_used:
        batch.group_field_used ??
        state.broadcastVariableProfile.group_field ??
        'Customer Name',
      group_field_source:
        batch.group_field_source ??
        ('legacy_fallback' as BroadcastImportGroupFieldSource),
      items: createdItems,
    });
  }

  const templateAssignmentMatch = path.match(
    /^\/api\/v1\/broadcast\/imports\/(\d+)\/group-template-assignments$/,
  );
  if (templateAssignmentMatch && method === 'PUT') {
    const importId = Number(templateAssignmentMatch[1]);
    const body = parseJsonBody(route);
    const batch = state.broadcastImportBatches.find(
      (item) => item.id === importId,
    );
    if (!batch) {
      return fulfillError(
        route,
        404,
        'BROADCAST_IMPORT_NOT_FOUND',
        'Current import batch was not found',
      );
    }
    const items = Array.isArray(body.items) ? body.items : [];
    if (items.length === 0) {
      return fulfillError(
        route,
        400,
        'DRAFT_GENERATION_VALIDATION_FAILED',
        'Select at least one group template assignment',
      );
    }
    const groupsResponse = buildImportGroupsResponse(state, importId, {
      page: 1,
      pageSize: 1000,
      keyword: '',
      matchStatus: null,
    });
    const groupByKey = new Map(
      groupsResponse.groups.map((group) => [group.group_key, group] as const),
    );
    const seenGroupKeys = new Set<string>();
    const normalizedItems: Array<{
      group_key: string;
      template_id: number | null;
    }> = [];
    for (const item of items) {
      const groupKey = String((item as JsonRecord)?.group_key || '').trim();
      if (!groupKey || !groupByKey.has(groupKey)) {
        return fulfillError(
          route,
          404,
          'BROADCAST_IMPORT_GROUP_NOT_FOUND',
          'Selected group was not found',
        );
      }
      if (seenGroupKeys.has(groupKey)) {
        return fulfillError(
          route,
          400,
          'BATCH_VALIDATION_FAILED',
          'Duplicate group assignment in the same request is not allowed',
        );
      }
      seenGroupKeys.add(groupKey);

      const rawTemplateId = (item as JsonRecord)?.template_id;
      if (rawTemplateId == null) {
        normalizedItems.push({
          group_key: groupKey,
          template_id: null,
        });
        continue;
      }

      const templateId = Number(rawTemplateId);
      if (!Number.isFinite(templateId) || templateId <= 0) {
        return fulfillError(
          route,
          400,
          'BATCH_VALIDATION_FAILED',
          'Template assignment is invalid',
        );
      }
      const template = state.broadcastTemplates.find(
        (candidate) => candidate.id === templateId,
      );
      if (!template) {
        return fulfillError(
          route,
          404,
          'BROADCAST_TEMPLATE_NOT_FOUND',
          'Selected template was not found',
        );
      }
      if (!template.enabled) {
        return fulfillError(
          route,
          400,
          'BATCH_VALIDATION_FAILED',
          'Disabled templates cannot be assigned to new drafts',
        );
      }
      normalizedItems.push({
        group_key: groupKey,
        template_id: template.id,
      });
    }

    for (const item of normalizedItems) {
      const assignmentKey = groupTemplateAssignmentMapKey(
        importId,
        item.group_key,
      );
      if (item.template_id == null) {
        delete state.broadcastGroupTemplateAssignments[assignmentKey];
        continue;
      }
      state.broadcastGroupTemplateAssignments[assignmentKey] = item.template_id;
    }
    return fulfillJson(route, { items: normalizedItems });
  }

  const generateDraftsMatch = path.match(
    /^\/api\/v1\/broadcast\/imports\/(\d+)\/generate-drafts$/,
  );
  if (generateDraftsMatch && method === 'POST') {
    const importId = Number(generateDraftsMatch[1]);
    const body = parseJsonBody(route);
    const batch = state.broadcastImportBatches.find(
      (item) => item.id === importId,
    );
    if (!batch) {
      return fulfillError(
        route,
        404,
        'BROADCAST_IMPORT_NOT_FOUND',
        'Current import batch was not found',
      );
    }

    const groupsResponse = buildImportGroupsResponse(state, importId, {
      page: 1,
      pageSize: 1000,
      keyword: '',
      matchStatus: null,
    });
    const groupByKey = new Map(
      groupsResponse.groups.map((group) => [group.group_key, group] as const),
    );
    const selectedGroupKeys = Array.isArray(body.group_keys)
      ? body.group_keys
          .map((item) => String(item || '').trim())
          .filter((item) => item.length > 0)
      : groupsResponse.groups.map((group) => group.group_key);
    const fallbackTemplateId = Number(body.template_id || 0) || null;
    const overwriteExisting = Boolean(body.overwrite_existing);

    if (selectedGroupKeys.length === 0) {
      return fulfillError(
        route,
        400,
        'NO_GROUP_SELECTED',
        'Select at least one group before generating drafts',
      );
    }

    const validationErrors: string[] = [];
    const selectedGroups = selectedGroupKeys.map((groupKey) => {
      const group = groupByKey.get(groupKey) || null;
      if (!group) {
        validationErrors.push(`${groupKey}: group not found`);
        return null;
      }
      return group;
    });
    if (validationErrors.length > 0) {
      return fulfillError(
        route,
        400,
        'DRAFT_GENERATION_VALIDATION_FAILED',
        'Selected groups failed validation',
        validationErrors,
      );
    }

    const selectedMatchedGroups = selectedGroups.filter(
      (group): group is NonNullable<typeof group> => group != null,
    );
    for (const group of selectedMatchedGroups) {
      if (
        group.match_status !== 'matched' ||
        !group.matched_conversation_name
      ) {
        validationErrors.push(
          `${group.group_value}: ${group.reason || 'group is not eligible for draft generation'}`,
        );
        continue;
      }
    }

    const modifiedFields = [
      'template_id',
      'template_name_snapshot',
      'template_content_snapshot',
      'render_variables',
      'draft_text',
      'target_conversation_id',
      'target_conversation_name',
      'attachment_snapshots',
      'status',
      'error_message',
      'attachments_stale',
      'updated_at',
    ];
    const draftOperations: Array<{
      group: (typeof selectedMatchedGroups)[number];
      draft: BroadcastDraftMock;
      existingDraft: BroadcastDraftMock | null;
    }> = [];
    for (const group of selectedMatchedGroups) {
      const templateId =
        fallbackTemplateId ??
        state.broadcastGroupTemplateAssignments[
          groupTemplateAssignmentMapKey(importId, group.group_key)
        ] ??
        null;
      if (!templateId) {
        validationErrors.push(`${group.group_value}: template not selected`);
        continue;
      }
      const template = state.broadcastTemplates.find(
        (item) => item.id === templateId,
      );
      if (!template) {
        validationErrors.push(`${group.group_value}: template not found`);
        continue;
      }
      if (!template.enabled) {
        validationErrors.push(`${group.group_value}: template disabled`);
        continue;
      }

      const existingDraft = state.broadcastDrafts.find(
        (item) =>
          item.import_batch_id === importId &&
          item.group_value === group.group_value,
      );
      if (existingDraft && existingDraft.send_status === 'sent') {
        validationErrors.push(
          `${group.group_value}: sent draft cannot be overwritten, restore it to pending first`,
        );
        continue;
      }
      if (existingDraft && !overwriteExisting) {
        validationErrors.push(`${group.group_value}: draft already exists`);
        continue;
      }

      const timestamp = now();
      draftOperations.push({
        group,
        existingDraft: existingDraft ?? null,
        draft: {
          id:
            existingDraft?.id ??
            Number(nextId(state, 'broadcast-draft').split('-').pop()),
          bot_uuid: batch.bot_uuid,
          connector_id: batch.connector_id,
          import_batch_id: importId,
          group_value: group.group_value,
          target_conversation_name: group.matched_conversation_name,
          template_id: template.id,
          template_name_snapshot: template.name,
          template_content_snapshot: template.content,
          render_variables: {
            customer_name: group.group_value,
          },
          draft_text: template.content.replace(
            '{{customer_name}}',
            group.group_value,
          ),
          status: 'pending_review',
          legacy_status: 'pending_review',
          send_status: existingDraft?.send_status ?? 'pending',
          sent_at: existingDraft?.sent_at ?? null,
          error_message: null,
          drafts_stale: false,
          attachments_stale: false,
          attachments: (
            state.broadcastGroupAttachments[
              groupAttachmentMapKey(importId, group.group_key)
            ] ?? []
          ).map(cloneAttachment),
          created_at: existingDraft?.created_at ?? timestamp,
          updated_at: timestamp,
        },
      });
    }

    if (validationErrors.length > 0) {
      return fulfillError(
        route,
        400,
        'BATCH_VALIDATION_FAILED',
        validationErrors.length === 1
          ? validationErrors[0]
          : 'Selected groups failed validation',
        validationErrors,
      );
    }

    const createdDrafts = draftOperations
      .filter((item) => item.existingDraft == null)
      .map((item) => item.draft);
    const updatedDrafts = draftOperations.filter(
      (item) => item.existingDraft != null,
    );
    if (updatedDrafts.length > 0) {
      const updatedDraftMap = new Map(
        updatedDrafts.map((item) => [item.draft.id, item.draft] as const),
      );
      state.broadcastDrafts = state.broadcastDrafts.map(
        (item) => updatedDraftMap.get(item.id) ?? item,
      );
    }
    if (createdDrafts.length > 0) {
      state.broadcastDrafts = [...createdDrafts, ...state.broadcastDrafts];
    }
    batch.status = 'drafts_generated';
    batch.drafts_stale = false;
    batch.updated_at = now();
    return fulfillJson(route, {
      total_group_count: selectedMatchedGroups.length,
      pending_review_count: draftOperations.length,
      invalid_count: 0,
      unmatched_group_count: 0,
      created_count: createdDrafts.length,
      updated_count: updatedDrafts.length,
      generated_group_keys: selectedMatchedGroups.map(
        (group) => group.group_key,
      ),
      draft_ids: draftOperations.map((item) => item.draft.id),
      draft_results: draftOperations.map((item) => ({
        group_key: item.group.group_key,
        draft_id: item.draft.id,
        operation: item.existingDraft ? 'updated' : 'created',
        modified_fields: modifiedFields,
      })),
    });
  }

  if (path === '/api/v1/broadcast/executions') {
    const botUuid = url.searchParams.get('bot_uuid');
    const connectorId = url.searchParams.get('connector_id');

    if (method === 'GET') {
      const batches = state.broadcastExecutionBatches
        .filter(
          (item) =>
            item.bot_uuid === botUuid && item.connector_id === connectorId,
        )
        .sort((left, right) => right.id - left.id);
      return fulfillJson(route, batches);
    }

    if (method === 'POST') {
      const body = parseJsonBody(route);
      const draftIds = Array.isArray(body.draft_ids)
        ? body.draft_ids
            .map((item) => Number(item))
            .filter((item) => Number.isFinite(item))
        : [];
      const drafts = draftIds
        .map(
          (draftId) =>
            state.broadcastDrafts.find((item) => item.id === draftId) || null,
        )
        .filter((draft): draft is BroadcastDraftMock => draft != null);
      if (drafts.length === 0 || drafts.length !== draftIds.length) {
        return fulfillError(
          route,
          404,
          'BROADCAST_DRAFT_NOT_FOUND',
          '????????????',
        );
      }
      const modeValue = String(body.mode || '').trim();
      if (!['paste_only', 'send'].includes(modeValue)) {
        return fulfillError(
          route,
          400,
          'BROADCAST_EXECUTION_MODE_INVALID',
          'Invalid broadcast execution mode',
        );
      }
      const mode = modeValue as 'paste_only' | 'send';
      const allowSentRewrite = Boolean(body.allow_sent_rewrite);
      if (mode === 'paste_only') {
        const sendStatuses = new Set(drafts.map((draft) => draft.send_status));
        if (sendStatuses.size > 1) {
          return fulfillError(
            route,
            400,
            'MIXED_SEND_STATUS',
            'Mixed send status selection is not allowed',
          );
        }
        if (
          drafts.some(
            (draft) =>
              draft.status === 'invalid' ||
              !draft.target_conversation_name ||
              !draft.draft_text.trim(),
          )
        ) {
          return fulfillError(
            route,
            400,
            'BROADCAST_EXECUTION_DRAFT_NOT_READY',
            'Draft is not ready for paste-only execution',
          );
        }
        if (
          drafts.some((draft) => draft.send_status === 'sent') &&
          !(allowSentRewrite && drafts.length === 1)
        ) {
          return fulfillError(
            route,
            400,
            'INVALID_SEND_STATUS',
            'Sent drafts cannot be included in bulk write',
          );
        }
        const duplicateTargets = drafts
          .map((draft) => String(draft.target_conversation_name || '').trim())
          .filter(
            (target, index, allTargets) =>
              target && allTargets.indexOf(target) !== index,
          );
        if (duplicateTargets.length > 0) {
          return fulfillError(
            route,
            409,
            'DUPLICATE_TARGET_CONVERSATION',
            'Duplicate target conversations are not allowed in one batch',
          );
        }
      }
      if (mode === 'send') {
        if (!state.broadcastSendEnabled) {
          return fulfillError(
            route,
            409,
            'EXECUTOR_SEND_UNSUPPORTED',
            'Real send is not available for the current executor',
          );
        }
        if (
          drafts.some(
            (draft) =>
              draft.status === 'invalid' ||
              !draft.target_conversation_name ||
              !draft.draft_text.trim(),
          )
        ) {
          return fulfillError(
            route,
            400,
            'BROADCAST_DRAFT_NOT_SENDABLE',
            'Draft is not ready for real send execution',
          );
        }
        if (drafts.some((draft) => draft.send_status === 'sent')) {
          return fulfillError(
            route,
            400,
            'BROADCAST_DRAFT_ALREADY_SENT',
            'Sent drafts cannot be sent again',
          );
        }
        if (drafts.some((draft) => draft.send_status === 'unknown')) {
          return fulfillError(
            route,
            400,
            'BROADCAST_SEND_RESULT_UNKNOWN_REQUIRES_REVIEW',
            'Draft send result is still pending manual review',
          );
        }
      }
      const timestamp = now();
      const batchId = Number(
        nextId(state, 'broadcast-execution-batch').split('-').pop(),
      );
      const batch: BroadcastExecutionBatchMock = {
        id: batchId,
        bot_uuid: String(body.bot_uuid || ''),
        connector_id: String(body.connector_id || ''),
        channel: 'wxwork_database',
        mode,
        status: 'created',
        total_tasks: drafts.length,
        pending_tasks: drafts.length,
        running_tasks: 0,
        succeeded_tasks: 0,
        failed_tasks: 0,
        cancelled_tasks: 0,
        interrupted_tasks: 0,
        created_by: String(body.operator || 'tester@example.com'),
        last_action_by: String(body.operator || 'tester@example.com'),
        error_message: null,
        version: 1,
        created_at: timestamp,
        started_at: null,
        paused_at: null,
        finished_at: null,
        cancelled_at: null,
      };
      const tasks = drafts.map((draft, index) => {
        const taskId = Number(
          nextId(state, 'broadcast-execution-task').split('-').pop(),
        );
        const task: BroadcastExecutionTaskMock = {
          id: taskId,
          execution_batch_id: batchId,
          draft_id: draft.id,
          draft_text_snapshot: draft.draft_text,
          target_conversation_snapshot: draft.target_conversation_name || '',
          channel: 'wxwork_database',
          action: mode === 'send' ? 'send_message' : 'paste_draft',
          status: 'pending',
          sequence_no: index + 1,
          attempt_count: 0,
          max_attempts: 3,
          idempotency_key: `broadcast:${taskId}:1`,
          request_digest: `fixture-digest-${taskId}`,
          runtime_task_id: null,
          error_code: null,
          error_message: null,
          operator_note: null,
          created_at: timestamp,
          started_at: null,
          finished_at: null,
          cancelled_at: null,
          updated_at: timestamp,
          attachments: (draft.attachments ?? []).map(cloneAttachment),
        };
        return task;
      });
      state.broadcastExecutionBatches = [
        batch,
        ...state.broadcastExecutionBatches.filter(
          (item) => item.id !== batchId,
        ),
      ];
      state.broadcastExecutionTasks = [
        ...tasks,
        ...state.broadcastExecutionTasks.filter(
          (item) => !tasks.some((task) => task.id === item.id),
        ),
      ];
      if (mode === 'send') {
        simulateSendBatch(state, batch, tasks, drafts);
      }
      return fulfillJson(route, {
        ...batch,
        ...(mode === 'send' ? buildSendBatchSummary(state, batch) : {}),
        tasks: tasks.map((task) => serializeExecutionTask(state, task)),
      });
    }
  }

  if (path === '/api/v1/broadcast/group-names/sync' && method === 'POST') {
    return fulfillJson(route, {
      scanned: 1,
      inserted: 1,
      updated: 0,
      unchanged: 0,
      skipped: 0,
      errors: [],
    });
  }

  const executionDetailMatch = path.match(
    /^\/api\/v1\/broadcast\/executions\/(\d+)$/,
  );
  if (executionDetailMatch && method === 'GET') {
    const batchId = Number(executionDetailMatch[1]);
    const batch = state.broadcastExecutionBatches.find(
      (item) => item.id === batchId,
    );
    if (!batch) {
      return fulfillError(
        route,
        404,
        'BROADCAST_EXECUTION_BATCH_NOT_FOUND',
        '??????????????',
      );
    }
    const tasks = state.broadcastExecutionTasks.filter(
      (item) => item.execution_batch_id === batchId,
    );
    return fulfillJson(route, {
      ...batch,
      ...(batch.mode === 'send' ? buildSendBatchSummary(state, batch) : {}),
      tasks: tasks.map((task) => serializeExecutionTask(state, task)),
    });
  }

  const executionBatchActionMatch = path.match(
    /^\/api\/v1\/broadcast\/executions\/(\d+)\/(start|pause|resume|cancel)$/,
  );
  if (executionBatchActionMatch && method === 'POST') {
    const batchId = Number(executionBatchActionMatch[1]);
    const action = executionBatchActionMatch[2];
    const batch = findExecutionBatch(state, batchId);
    if (!batch) {
      return fulfillError(
        route,
        404,
        'BROADCAST_EXECUTION_BATCH_NOT_FOUND',
        '??????????????',
      );
    }
    const body = parseJsonBody(route);
    const tasks = state.broadcastExecutionTasks
      .filter((item) => item.execution_batch_id === batchId)
      .sort((left, right) => left.sequence_no - right.sequence_no);
    const timestamp = now();
    batch.last_action_by = String(
      body.operator || batch.last_action_by || 'tester@example.com',
    );

    if (action === 'start') {
      batch.started_at = batch.started_at || timestamp;
      batch.paused_at = null;
      if (batch.mode === 'paste_only' && tasks.length === 1) {
        createExecutionAttempt(state, tasks[0], {
          status: 'succeeded',
          action: 'paste_draft',
          runtime_state: 'pasted_to_input',
          send_triggered: false,
          evidence_summary: 'Draft written to input',
        });
      } else {
        batch.status = 'running';
      }
      syncExecutionBatchCounts(state, batchId);
    }

    if (action === 'pause') {
      batch.status = 'paused';
      batch.paused_at = timestamp;
    }

    if (action === 'resume') {
      batch.paused_at = null;
      batch.status = 'running';
      if (!batch.scripted_failure_emitted) {
        const task = tasks.find((item) => item.status === 'pending');
        if (task) {
          createExecutionAttempt(state, task, {
            status: 'failed',
            action: task.action,
            runtime_state: 'failed',
            send_triggered: false,
            evidence_summary: 'Scripted failure for retry flow',
            error_code: 'SCRIPTED_FAILURE',
            error_message: 'Scripted failure for retry flow',
          });
          batch.scripted_failure_emitted = true;
        }
      }
      syncExecutionBatchCounts(state, batchId);
    }

    if (action === 'cancel') {
      for (const task of tasks.filter((item) => item.status === 'pending')) {
        task.status = 'cancelled';
        task.cancelled_at = timestamp;
        task.finished_at = timestamp;
        task.updated_at = timestamp;
      }
      batch.cancelled_at = timestamp;
      syncExecutionBatchCounts(state, batchId);
      batch.status = 'cancelled';
    }

    return fulfillJson(route, {
      ...batch,
      tasks: state.broadcastExecutionTasks
        .filter((item) => item.execution_batch_id === batchId)
        .map((task) => serializeExecutionTask(state, task)),
    });
  }

  const executionTaskAttemptsMatch = path.match(
    /^\/api\/v1\/broadcast\/execution-tasks\/(\d+)\/attempts$/,
  );
  if (executionTaskAttemptsMatch && method === 'GET') {
    const taskId = Number(executionTaskAttemptsMatch[1]);
    return fulfillJson(
      route,
      state.broadcastExecutionAttempts.filter(
        (item) => item.execution_task_id === taskId,
      ),
    );
  }

  const executionTaskDetailMatch = path.match(
    /^\/api\/v1\/broadcast\/execution-tasks\/(\d+)$/,
  );
  if (executionTaskDetailMatch && method === 'GET') {
    const taskId = Number(executionTaskDetailMatch[1]);
    const task = findExecutionTask(state, taskId);
    if (!task) {
      return fulfillError(
        route,
        404,
        'BROADCAST_EXECUTION_TASK_NOT_FOUND',
        '??????????????',
      );
    }
    return fulfillJson(route, serializeExecutionTask(state, task));
  }

  const executionTaskStartMatch = path.match(
    /^\/api\/v1\/broadcast\/execution-tasks\/(\d+)\/start$/,
  );
  if (executionTaskStartMatch && method === 'POST') {
    const taskId = Number(executionTaskStartMatch[1]);
    const task = findExecutionTask(state, taskId);
    if (!task) {
      return fulfillError(
        route,
        404,
        'BROADCAST_EXECUTION_TASK_NOT_FOUND',
        '??????????????',
      );
    }
    const batch = findExecutionBatch(state, task.execution_batch_id);
    if (!batch) {
      return fulfillError(
        route,
        404,
        'BROADCAST_EXECUTION_BATCH_NOT_FOUND',
        '??????????????',
      );
    }
    batch.started_at = batch.started_at || now();
    createExecutionAttempt(state, task, {
      status: 'succeeded',
      action: task.action,
      runtime_state:
        task.action === 'send_message' ? 'send_verified' : 'pasted_to_input',
      send_triggered: task.action === 'send_message',
      evidence_summary:
        task.action === 'send_message'
          ? 'Message sent'
          : 'Draft written to input',
    });
    syncExecutionBatchCounts(state, batch.id);
    return fulfillJson(route, serializeExecutionTask(state, task));
  }

  const executionTaskRetryMatch = path.match(
    /^\/api\/v1\/broadcast\/execution-tasks\/(\d+)\/retry$/,
  );
  if (executionTaskRetryMatch && method === 'POST') {
    const taskId = Number(executionTaskRetryMatch[1]);
    const task = findExecutionTask(state, taskId);
    if (!task) {
      return fulfillError(
        route,
        404,
        'BROADCAST_EXECUTION_TASK_NOT_FOUND',
        '??????????????',
      );
    }
    const taskState = syncTaskDerivedState(state, task);
    if (task.action === 'send_message' && taskState.retry_allowed !== true) {
      return fulfillError(
        route,
        409,
        'BROADCAST_RETRY_SEND_RESULT_UNKNOWN',
        'Current send result cannot be confirmed; only failures confirmed before Enter can be retried',
      );
    }
    task.status = 'pending';
    task.error_code = null;
    task.error_message = null;
    task.finished_at = null;
    task.cancelled_at = null;
    task.updated_at = now();
    const batch = findExecutionBatch(state, task.execution_batch_id);
    if (batch) {
      batch.finished_at = null;
      batch.cancelled_at = null;
      batch.paused_at = null;
      batch.status = 'queued';
      syncExecutionBatchCounts(state, batch.id);
    }
    return fulfillJson(route, serializeExecutionTask(state, task));
  }

  if (path === '/api/v1/broadcast/executors/capabilities' && method === 'GET') {
    return fulfillJson(
      route,
      state.broadcastExecutorCapability ?? {
        channel: 'wxwork_database',
        supports_paste: true,
        supports_paste_verification: true,
        requires_manual_conversation_open: true,
        conversation_locator: 'keyboard_search',
        content_verification: 'windows_uia',
        supports_send: state.broadcastSendEnabled,
        supports_cancel: true,
        supports_status_query: true,
        supports_clipboard_restore: true,
        supports_evidence: true,
        executor_version: 'fixture-phase7',
        runtime_min_version: '1.0.0',
      },
    );
  }

  if (path === '/api/v1/broadcast/executors/health' && method === 'GET') {
    if ((state.broadcastExecutorHealthDelayMs ?? 0) > 0) {
      await new Promise((resolve) =>
        setTimeout(resolve, state.broadcastExecutorHealthDelayMs),
      );
    }
    return fulfillJson(
      route,
      state.broadcastExecutorHealth ?? {
        available: true,
        channel: 'wxwork_database',
        status: 'ready',
        protocol_version: '1.0.0',
        runtime_version: '1.0.0',
        capability: {
          channel: 'wxwork_database',
          supports_paste: true,
          supports_paste_verification: true,
          requires_manual_conversation_open: true,
          conversation_locator: 'keyboard_search',
          content_verification: 'windows_uia',
          supports_send: state.broadcastSendEnabled,
          supports_cancel: true,
          supports_status_query: true,
          supports_clipboard_restore: true,
          supports_evidence: true,
          executor_version: 'fixture-phase7',
          runtime_min_version: '1.0.0',
        },
        runtime_status: {
          pasteVerification: {
            available: true,
            reason: null,
            method: 'windows_uia',
            requiresManualConversationOpen: true,
            supportedErrorCodes: [
              'TARGET_WINDOW_CHANGED',
              'CONVERSATION_MISMATCH',
              'INPUT_NOT_LOCATED',
              'PASTE_CONTENT_MISMATCH',
              'PASTE_VERIFICATION_UNAVAILABLE',
            ],
          },
          runtimeAutoSendEnabled: state.broadcastSendEnabled,
        },
      },
    );
  }

  const executionAttemptDetailMatch = path.match(
    /^\/api\/v1\/broadcast\/execution-attempts\/(\d+)$/,
  );
  if (executionAttemptDetailMatch && method === 'GET') {
    const attemptId = Number(executionAttemptDetailMatch[1]);
    const attempt = state.broadcastExecutionAttempts.find(
      (item) => item.id === attemptId,
    );
    if (!attempt) {
      return fulfillError(
        route,
        404,
        'BROADCAST_EXECUTION_TASK_NOT_FOUND',
        '??????????????',
      );
    }
    return fulfillJson(route, attempt);
  }

  const executionEvidenceMatch = path.match(
    /^\/api\/v1\/broadcast\/execution-attempts\/(\d+)\/evidence$/,
  );
  if (executionEvidenceMatch && method === 'GET') {
    const attemptId = Number(executionEvidenceMatch[1]);
    const evidence = state.broadcastExecutionEvidence.find(
      (item) => item.execution_attempt_id === attemptId,
    );
    if (!evidence) {
      return fulfillError(
        route,
        404,
        'BROADCAST_EXECUTION_TASK_NOT_FOUND',
        '??????????????',
      );
    }
    return fulfillJson(route, evidence);
  }

  if (path === '/api/v1/broadcast/drafts' && method === 'GET') {
    const importBatchId = Number(url.searchParams.get('import_batch_id') || 0);
    const status = url.searchParams.get('status');
    const keyword = (url.searchParams.get('keyword') || '')
      .trim()
      .toLowerCase();
    const seededDrafts =
      state.broadcastDrafts.length > 0
        ? state.broadcastDrafts
        : seedDefaultDrafts
          ? [
            {
              id: 1,
              bot_uuid: 'bot-1',
              connector_id: 'wxwork-local',
              import_batch_id: importBatchId || 1,
              group_value: 'Acme',
              target_conversation_name: 'Acme Group',
              template_id: 1,
              template_name_snapshot: 'Arrival Reminder',
              template_content_snapshot: 'Hello {{customer_name}}',
              render_variables: { customer_name: 'Acme' },
              draft_text: 'Hello Acme',
              status: 'pending_review' as const,
              send_status: 'pending' as const,
              sent_at: null,
              error_message: null,
              drafts_stale: false,
              attachments_stale: false,
              attachments: [],
              created_at: now(),
              updated_at: now(),
            },
            {
              id: 2,
              bot_uuid: 'bot-1',
              connector_id: 'wxwork-local',
              import_batch_id: importBatchId || 1,
              group_value: 'Northwind Team',
              target_conversation_name: 'Northwind Team',
              template_id: 1,
              template_name_snapshot: 'Arrival Reminder',
              template_content_snapshot: 'Hello {{customer_name}}',
              render_variables: { customer_name: 'Northwind Team' },
              draft_text: 'Hello Northwind Team',
              status: 'pending_review' as const,
              send_status: 'pending' as const,
              sent_at: null,
              error_message: null,
              drafts_stale: false,
              attachments_stale: false,
              attachments: [],
              created_at: now(),
              updated_at: now(),
            },
            {
              id: 3,
              bot_uuid: 'bot-1',
              connector_id: 'wxwork-local',
              import_batch_id: importBatchId || 1,
              group_value: 'invalid-4',
              target_conversation_name: null,
              template_id: 1,
              template_name_snapshot: 'Arrival Reminder',
              template_content_snapshot: 'Hello {{customer_name}}',
              render_variables: {},
              draft_text: '',
              status: 'invalid' as const,
              send_status: 'pending' as const,
              sent_at: null,
              error_message: '未匹配到群聊',
              drafts_stale: false,
              created_at: now(),
              updated_at: now(),
            },
          ]
          : [];
    if (state.broadcastDrafts.length === 0 && seedDefaultDrafts) {
      state.broadcastDrafts = seededDrafts;
    }
    const draftSource =
      state.broadcastDrafts.length > 0 ? state.broadcastDrafts : seededDrafts;
    const drafts = draftSource.filter((item) => {
      if (importBatchId && item.import_batch_id !== importBatchId) {
        return false;
      }
      if (!status || status === 'all') {
        if (item.status === 'invalid') {
          return false;
        }
      } else if (
        status === 'pending' ||
        status === 'sent' ||
        status === 'unknown'
      ) {
        if (item.status === 'invalid' || item.send_status !== status) {
          return false;
        }
      } else if (item.status !== status) {
        return false;
      }
      if (keyword) {
        return [
          item.group_value,
          item.target_conversation_name || '',
          item.draft_text,
        ]
          .join(' ')
          .toLowerCase()
          .includes(keyword);
      }
      return true;
    });
    return fulfillJson(route, drafts);
  }

  const draftDetailMatch = path.match(/^\/api\/v1\/broadcast\/drafts\/(\d+)$/);
  if (draftDetailMatch) {
    const draftId = Number(draftDetailMatch[1]);
    const draft = state.broadcastDrafts.find((item) => item.id === draftId);
    if (!draft) {
      return fulfillError(
        route,
        404,
        'BROADCAST_DRAFT_NOT_FOUND',
        '当前草稿不存在或已被删除',
      );
    }
    if (method === 'GET') {
      return fulfillJson(route, serializeDraft(draft));
    }
    if (method === 'PUT') {
      const body = parseJsonBody(route);
      const nextText = String(body.draft_text || '');
      draft.draft_text = nextText;
      draft.updated_at = now();
      return fulfillJson(route, {
        ...draft,
        message: null,
      });
    }
  }

  if (path === '/api/v1/broadcast/drafts/batch-status' && method === 'POST') {
    const body = parseJsonBody(route);
    const draftIds = Array.isArray(body.draft_ids)
      ? body.draft_ids.map((item) => Number(item))
      : [];
    const status = String(body.status || '');
    const selectedDrafts = state.broadcastDrafts.filter((draft) =>
      draftIds.includes(draft.id),
    );
    if (selectedDrafts.length !== draftIds.length) {
      return fulfillError(
        route,
        404,
        'BROADCAST_DRAFT_NOT_FOUND',
        'Draft not found',
      );
    }
    if (status === 'pending' || status === 'sent') {
      const sendStatuses = new Set(
        selectedDrafts.map((draft) => draft.send_status),
      );
      if (sendStatuses.size !== 1) {
        return fulfillError(
          route,
          400,
          'MIXED_SEND_STATUS',
          'Mixed send status selection is not allowed',
        );
      }
      const expectedSources =
        status === 'sent'
          ? new Set(['pending', 'unknown'])
          : new Set(['sent', 'unknown']);
      if (
        selectedDrafts.some(
          (draft) =>
            draft.status === 'invalid' ||
            !expectedSources.has(draft.send_status),
        )
      ) {
        return fulfillError(
          route,
          400,
          'INVALID_SEND_STATUS',
          'Selected drafts are not eligible for this send-status transition',
        );
      }
    }
    let updatedCount = 0;
    state.broadcastDrafts = state.broadcastDrafts.map((draft) => {
      if (!draftIds.includes(draft.id)) {
        return draft;
      }
      updatedCount += 1;
      const nextDraft: BroadcastDraftMock = {
        ...draft,
        attachments_stale: false,
        updated_at: now(),
        message: null,
      };
      if (status === 'pending' || status === 'sent') {
        nextDraft.send_status = status;
        nextDraft.sent_at = status === 'sent' ? now() : null;
      } else {
        nextDraft.status = status as BroadcastDraftMock['status'];
      }
      return nextDraft;
    });
    return fulfillJson(route, { updated_count: updatedCount });
  }

  const botLogsMatch = path.match(/^\/api\/v1\/platform\/bots\/([^/]+)\/logs$/);
  if (botLogsMatch) {
    return fulfillJson(route, { logs: [], total: 0 });
  }

  const botMatch = path.match(/^\/api\/v1\/platform\/bots\/([^/]+)$/);
  if (botMatch) {
    const botId = decodeURIComponent(botMatch[1]);

    if (method === 'PUT') {
      const bot = makeBot(state, parseJsonBody(route), botId);
      state.bots = [...state.bots.filter((item) => item.uuid !== botId), bot];
      return fulfillJson(route, {});
    }

    if (method === 'DELETE') {
      state.bots = state.bots.filter((item) => item.uuid !== botId);
      return fulfillJson(route, {});
    }

    const bot = state.bots.find((item) => item.uuid === botId);
    return fulfillJson(route, {
      bot: bot || makeBot(state, { name: botId }, botId),
    });
  }

  if (path === '/api/v1/pipelines/_/metadata') {
    return fulfillJson(route, { configs: [] });
  }

  if (path === '/api/v1/pipelines') {
    if (method === 'POST') {
      const pipeline = makePipeline(state, parseJsonBody(route));
      state.pipelines = [
        ...state.pipelines.filter((item) => item.uuid !== pipeline.uuid),
        pipeline,
      ];
      return fulfillJson(route, { uuid: pipeline.uuid });
    }

    return fulfillJson(route, { pipelines: state.pipelines });
  }

  const pipelineMatch = path.match(/^\/api\/v1\/pipelines\/([^/]+)$/);
  if (pipelineMatch) {
    const pipelineId = decodeURIComponent(pipelineMatch[1]);

    if (method === 'PUT') {
      const pipeline = makePipeline(state, parseJsonBody(route), pipelineId);
      state.pipelines = [
        ...state.pipelines.filter((item) => item.uuid !== pipelineId),
        pipeline,
      ];
      return fulfillJson(route, {});
    }

    if (method === 'DELETE') {
      state.pipelines = state.pipelines.filter(
        (item) => item.uuid !== pipelineId,
      );
      return fulfillJson(route, {});
    }

    const pipeline = state.pipelines.find((item) => item.uuid === pipelineId);
    return fulfillJson(route, {
      pipeline:
        pipeline || makePipeline(state, { name: pipelineId }, pipelineId),
    });
  }

  const pipelineExtensionsMatch = path.match(
    /^\/api\/v1\/pipelines\/([^/]+)\/extensions$/,
  );
  if (pipelineExtensionsMatch) {
    return fulfillJson(route, {
      enable_all_plugins: true,
      enable_all_mcp_servers: true,
      enable_all_skills: true,
      bound_plugins: [],
      available_plugins: [],
      bound_mcp_servers: [],
      available_mcp_servers: state.mcpServers,
      bound_skills: [],
      available_skills: state.skills,
    });
  }

  if (path === '/api/v1/knowledge/bases') {
    if (method === 'POST') {
      const base = makeKnowledgeBase(state, parseJsonBody(route));
      state.knowledgeBases = [
        ...state.knowledgeBases.filter((item) => item.uuid !== base.uuid),
        base,
      ];
      return fulfillJson(route, { uuid: base.uuid });
    }

    return fulfillJson(route, { bases: state.knowledgeBases });
  }

  const knowledgeBaseFilesMatch = path.match(
    /^\/api\/v1\/knowledge\/bases\/([^/]+)\/files$/,
  );
  if (knowledgeBaseFilesMatch) {
    return fulfillJson(route, { files: [] });
  }

  const knowledgeBaseMatch = path.match(
    /^\/api\/v1\/knowledge\/bases\/([^/]+)$/,
  );
  if (knowledgeBaseMatch) {
    const baseId = decodeURIComponent(knowledgeBaseMatch[1]);

    if (method === 'PUT') {
      const base = makeKnowledgeBase(state, parseJsonBody(route), baseId);
      state.knowledgeBases = [
        ...state.knowledgeBases.filter((item) => item.uuid !== baseId),
        base,
      ];
      return fulfillJson(route, { uuid: base.uuid });
    }

    if (method === 'DELETE') {
      state.knowledgeBases = state.knowledgeBases.filter(
        (item) => item.uuid !== baseId,
      );
      return fulfillJson(route, {});
    }

    const base = state.knowledgeBases.find((item) => item.uuid === baseId);
    return fulfillJson(route, {
      base: base || makeKnowledgeBase(state, { name: baseId }, baseId),
    });
  }

  if (path === '/api/v1/knowledge/engines') {
    return fulfillJson(route, { engines: [knowledgeEngine()] });
  }

  if (path === '/api/v1/knowledge/migration/status') {
    return fulfillJson(route, {
      needed: false,
      internal_kb_count: 0,
      external_kb_count: 0,
    });
  }

  if (path === '/api/v1/plugins') {
    return fulfillJson(route, { plugins: [] });
  }

  if (path === '/api/v1/extensions') {
    return fulfillJson(route, { extensions: [] });
  }

  if (path === '/api/v1/mcp/servers') {
    if (method === 'POST') {
      const server = makeMCPServer(parseJsonBody(route));
      state.mcpServers = [
        ...state.mcpServers.filter((item) => item.name !== server.name),
        server,
      ];
      return fulfillJson(route, { task_id: nextId(state, 'task') });
    }

    return fulfillJson(route, { servers: state.mcpServers });
  }

  const mcpTestMatch = path.match(/^\/api\/v1\/mcp\/servers\/([^/]+)\/test$/);
  if (mcpTestMatch) {
    return fulfillJson(route, {
      runtime_info: {
        status: 'connected',
        tool_count: 0,
        tools: [],
      },
    });
  }

  const mcpServerMatch = path.match(/^\/api\/v1\/mcp\/servers\/([^/]+)$/);
  if (mcpServerMatch) {
    const serverName = decodeURIComponent(mcpServerMatch[1]);

    if (method === 'PUT') {
      const existing = state.mcpServers.find(
        (item) => item.name === serverName,
      );
      const server = makeMCPServer({
        ...(existing || {}),
        ...parseJsonBody(route),
        name: serverName,
      });
      state.mcpServers = [
        ...state.mcpServers.filter((item) => item.name !== serverName),
        server,
      ];
      return fulfillJson(route, { task_id: nextId(state, 'task') });
    }

    if (method === 'DELETE') {
      state.mcpServers = state.mcpServers.filter(
        (item) => item.name !== serverName,
      );
      return fulfillJson(route, { task_id: nextId(state, 'task') });
    }

    const server = state.mcpServers.find((item) => item.name === serverName);
    return fulfillJson(route, {
      server: server || makeMCPServer({ name: serverName }),
    });
  }

  if (path === '/api/v1/skills') {
    if (method === 'POST') {
      const skill = makeSkill(
        JSON.parse(request.postData() || '{}') as JsonRecord,
      );
      state.skills = [
        ...state.skills.filter((item) => item.name !== skill.name),
        skill,
      ];
      return fulfillJson(route, { skill });
    }

    return fulfillJson(route, { skills: state.skills });
  }

  const skillFileMatch = path.match(
    /^\/api\/v1\/skills\/([^/]+)\/files\/(.+)$/,
  );
  if (skillFileMatch) {
    const skillName = decodeURIComponent(skillFileMatch[1]);
    const filePath = decodeURIComponent(skillFileMatch[2]);
    const skill = state.skills.find((item) => item.name === skillName);
    return fulfillJson(route, {
      skill: { name: skillName },
      path: filePath,
      content: skill?.instructions || '',
    });
  }

  const skillFilesMatch = path.match(/^\/api\/v1\/skills\/([^/]+)\/files$/);
  if (skillFilesMatch) {
    const skillName = decodeURIComponent(skillFilesMatch[1]);
    return fulfillJson(route, {
      skill: { name: skillName },
      base_path: '.',
      entries: [
        {
          path: 'SKILL.md',
          name: 'SKILL.md',
          is_dir: false,
          size: null,
        },
      ],
      truncated: false,
    });
  }

  const skillMatch = path.match(/^\/api\/v1\/skills\/([^/]+)$/);
  if (skillMatch) {
    const skillName = decodeURIComponent(skillMatch[1]);
    if (method === 'PUT') {
      const skill = makeSkill({
        ...parseJsonBody(route),
        name: skillName,
      });
      state.skills = [
        ...state.skills.filter((item) => item.name !== skillName),
        skill,
      ];
      return fulfillJson(route, { skill });
    }

    if (method === 'DELETE') {
      state.skills = state.skills.filter((item) => item.name !== skillName);
      return fulfillJson(route, {});
    }

    const skill = state.skills.find((item) => item.name === skillName) || {
      name: skillName,
      display_name: '',
      description: '',
      instructions: '',
      package_root: '',
      updated_at: new Date().toISOString(),
    };
    return fulfillJson(route, { skill });
  }

  if (path === '/api/v1/system/status/plugin-system') {
    return fulfillJson(route, {
      is_enable: true,
      is_connected: true,
      plugin_connector_error: '',
    });
  }

  if (path === '/api/v1/plugins/debug-info') {
    return fulfillJson(route, {
      debug_url: 'ws://127.0.0.1:5300/plugin/debug',
      plugin_debug_key: 'test-debug-key',
    });
  }

  if (path === '/api/v1/box/status') {
    return fulfillJson(route, {
      available: true,
      enabled: true,
      profile: 'playwright',
      recent_error_count: 0,
      active_sessions: 0,
      managed_processes: 0,
      session_ttl_sec: 3600,
      backend: {
        name: 'playwright',
        available: true,
      },
    });
  }

  if (path === '/api/v1/box/sessions') {
    return fulfillJson(route, []);
  }

  if (path === '/api/v1/monitoring/data') {
    return fulfillJson(route, emptyMonitoringData());
  }

  if (path === '/api/v1/monitoring/overview') {
    return fulfillJson(route, emptyMonitoringData().overview);
  }

  if (path === '/api/v1/monitoring/token-statistics') {
    return fulfillJson(route, emptyTokenStatistics());
  }

  if (path === '/api/v1/monitoring/feedback/stats') {
    return fulfillJson(route, {
      total_feedback: 0,
      total_likes: 0,
      total_dislikes: 0,
      satisfaction_rate: 0,
    });
  }

  if (path === '/api/v1/monitoring/feedback') {
    return fulfillJson(route, { feedback: [], total: 0 });
  }

  if (path === '/api/v1/survey/pending') {
    return fulfillJson(route, { survey: null });
  }

  if (path === '/api/v1/system/tasks') {
    return fulfillJson(route, { tasks: [] });
  }

  if (path === '/api/v1/local-connectors/wxwork-local/status') {
    return fulfillJson(route, {
      connector: {
        connector_id: 'wxwork-local',
        name: 'WeCom Local Connector',
        description: 'Mocked WeCom connector',
        managed_by: 'builtin',
        expected_tool_count: 5,
        status: 'not_configured',
        tool_count: 0,
        updated_at: Date.now(),
        worker: {
          owned: false,
          port: 5681,
          started_at: null,
        },
        monitor: {
          enabled: false,
          owned: false,
          running_status: 'stopped',
          warmup_completed: false,
          outbox_pending: 0,
        },
      },
    });
  }

  if (path === '/api/v1/database-mode/conversations') {
    return fulfillJson(route, {
      conversations: [],
      total: 0,
      page: 1,
      page_size: 100,
    });
  }

  if (
    path === '/api/v1/marketplace/plugins' ||
    path === '/api/v1/marketplace/plugins/search' ||
    path === '/api/v1/marketplace/extensions/search' ||
    path === '/api/v1/marketplace/mcps/search' ||
    path === '/api/v1/marketplace/skills/search'
  ) {
    return fulfillJson(route, { plugins: [], total: 0 });
  }

  if (path === '/api/v1/marketplace/tags') {
    return fulfillJson(route, { tags: [] });
  }

  if (path === '/api/v1/marketplace/recommendation-lists') {
    return fulfillJson(route, { lists: [] });
  }

  if (path === '/api/v1/dist/info/releases') {
    return fulfillJson(route, []);
  }

  if (path === '/api/v1/dist/info/repo') {
    return fulfillJson(route, {
      repo: {
        stargazers_count: 0,
        forks_count: 0,
        open_issues_count: 0,
      },
      contributors: [],
    });
  }

  await fulfillJson(route, {});
}

async function handleCloudApi(route: Route) {
  const path = routePath(route);

  if (
    path === '/api/v1/marketplace/plugins' ||
    path === '/api/v1/marketplace/plugins/search' ||
    path === '/api/v1/marketplace/extensions/search' ||
    path === '/api/v1/marketplace/mcps/search' ||
    path === '/api/v1/marketplace/skills/search'
  ) {
    return fulfillJson(route, { plugins: [], total: 0 });
  }

  if (path === '/api/v1/marketplace/tags') {
    return fulfillJson(route, { tags: [] });
  }

  if (path === '/api/v1/marketplace/recommendation-lists') {
    return fulfillJson(route, { lists: [] });
  }

  if (path === '/api/v1/dist/info/releases') {
    return fulfillJson(route, []);
  }

  if (path === '/api/v1/dist/info/repo') {
    return fulfillJson(route, {
      repo: {
        stargazers_count: 0,
        forks_count: 0,
        open_issues_count: 0,
      },
      contributors: [],
    });
  }

  await fulfillJson(route, {});
}

export async function installLangBotApiMocks(
  page: Page,
  options: {
    authenticated?: boolean;
    storage?: JsonRecord;
    bots?: InstallLangBotApiMockBot[];
    seedDefaultDrafts?: boolean;
    broadcastSendEnabled?: boolean;
    broadcastExecutorCapability?: Record<string, unknown>;
    broadcastExecutorHealth?: Record<string, unknown>;
    broadcastExecutorHealthDelayMs?: number;
  } = {},
) {
  await page.goto('/', { waitUntil: 'domcontentloaded' });
  const {
    authenticated = false,
    storage = {},
    bots = [],
    seedDefaultDrafts = true,
    broadcastSendEnabled = false,
    broadcastExecutorCapability,
    broadcastExecutorHealth,
    broadcastExecutorHealthDelayMs = 0,
  } = options;
  const broadcastSeed = seedBroadcastState();
  const state: LangBotApiMockState = {
    bots: bots.map((bot) => ({
      uuid: bot.uuid,
      name: bot.name,
      description: bot.description || '',
      enable: bot.enable !== false,
      adapter: bot.adapter || 'playwright-adapter',
      adapter_config: bot.adapter_config || {},
      use_pipeline_uuid: bot.use_pipeline_uuid,
      pipeline_routing_rules: bot.pipeline_routing_rules || [],
      adapter_runtime_values: bot.adapter_runtime_values || {},
      updated_at: bot.updated_at || now(),
    })),
    broadcastExecutorCapability: broadcastExecutorCapability ?? null,
    broadcastExecutorHealth: broadcastExecutorHealth ?? null,
    broadcastExecutorHealthDelayMs,
    broadcastDrafts: [],
    broadcastExecutionAttempts: [],
    broadcastExecutionBatches: [],
    broadcastExecutionEvidence: [],
    broadcastExecutionTasks: [],
    broadcastGroupAttachments: {},
    broadcastGroupTemplateAssignments: {},
    broadcastGroupNames: broadcastSeed.broadcastGroupNames,
    broadcastGroupRules: broadcastSeed.broadcastGroupRules,
    broadcastImportBatches: [],
    broadcastImportRows: [],
    broadcastSendEnabled,
    broadcastTemplates: broadcastSeed.broadcastTemplates,
    broadcastVariableProfile: broadcastSeed.broadcastVariableProfile,
    counters: {
      'broadcast-draft': 0,
      'broadcast-execution-batch': 0,
      'broadcast-execution-task': 0,
      'broadcast-execution-attempt': 0,
      'broadcast-execution-evidence': 0,
      'broadcast-attachment': 0,
      'broadcast-attachment-asset': 0,
      'broadcast-template': broadcastSeed.broadcastTemplates.length,
      'broadcast-group-rule': broadcastSeed.broadcastGroupRules.length,
      'broadcast-group-name': broadcastSeed.broadcastGroupNames.length,
      'broadcast-import-batch': 0,
      'broadcast-import-row': 0,
    },
    knowledgeBases: [],
    mcpServers: [],
    pipelines: [],
    skills: [],
  };

  await page.addInitScript(
    ({ authenticated, storage }) => {
      localStorage.setItem('langbot_language', 'en-US');
      localStorage.setItem('extensions_group_by_type', 'false');

      if (authenticated) {
        localStorage.setItem('token', 'playwright-token');
        localStorage.setItem('userEmail', 'admin@example.com');
      } else {
        localStorage.removeItem('token');
        localStorage.removeItem('userEmail');
      }

      if (!storage.langbot_language) {
        localStorage.setItem('langbot_language', 'en-US');
      }

      for (const [key, value] of Object.entries(storage)) {
        localStorage.setItem(key, String(value));
      }
    },
    { authenticated, storage },
  );

  await page.route('**/api/v1/**', (route) =>
    handleBackendApi(route, state, seedDefaultDrafts),
  );
  await page.route('https://space.langbot.app/**', handleCloudApi);
}
