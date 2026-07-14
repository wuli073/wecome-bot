import { IDynamicFormItemSchema } from '@/app/infra/entities/form/dynamic';
import { PipelineConfigTab } from '@/app/infra/entities/pipeline';
import { I18nObject } from '@/app/infra/entities/common';
import { Message } from '@/app/infra/entities/message';
import { Plugin, PluginV4 } from '@/app/infra/entities/plugin';

export interface ApiResponse<T> {
  code: number;
  data: T;
  msg: string;
}

export interface AsyncTaskCreatedResp {
  task_id: number;
}

export interface ApiRespProviderRequesters {
  requesters: Requester[];
}

export interface ApiRespProviderRequester {
  requester: Requester;
}

export interface Requester {
  name: string;
  label: I18nObject;
  description: I18nObject;
  icon?: string;
  spec: {
    config: IDynamicFormItemSchema[];
    provider_category: string;
    support_type?: string[];
    alias?: string;
  };
}

export interface ApiRespProviderLLMModels {
  models: LLMModel[];
}

export interface ApiRespProviderLLMModel {
  model: LLMModel;
}

export interface ModelProvider {
  uuid: string;
  name: string;
  requester: string;
  base_url: string;
  api_keys: string[];
  llm_count?: number;
  embedding_count?: number;
  rerank_count?: number;
  created_at?: string;
  updated_at?: string;
}

export interface ApiRespModelProviders {
  providers: ModelProvider[];
}

export interface ApiRespModelProvider {
  provider: ModelProvider;
}

export interface ScannedProviderModel {
  id: string;
  name: string;
  type: 'llm' | 'embedding';
  abilities?: string[];
  display_name?: string;
  description?: string;
  context_length?: number | null;
  owned_by?: string;
  input_modalities?: string[];
  output_modalities?: string[];
  already_added: boolean;
}

export interface ProviderScanDebugInfo {
  request?: {
    method?: string;
    url?: string;
    headers?: Record<string, string>;
  };
  response?: unknown;
}

export interface ApiRespScannedProviderModels {
  models: ScannedProviderModel[];
  debug?: ProviderScanDebugInfo;
}

export interface LLMModel {
  uuid: string;
  name: string;
  provider_uuid: string;
  provider?: ModelProvider;
  abilities?: string[];
  context_length?: number | null;
  extra_args?: object;
}

export interface ApiRespProviderEmbeddingModels {
  models: EmbeddingModel[];
}

export interface ApiRespProviderEmbeddingModel {
  model: EmbeddingModel;
}

export interface EmbeddingModel {
  uuid: string;
  name: string;
  provider_uuid: string;
  provider?: ModelProvider;
  extra_args?: object;
}

export interface ApiRespProviderRerankModels {
  models: RerankModel[];
}

export interface ApiRespProviderRerankModel {
  model: RerankModel;
}

export interface RerankModel {
  uuid: string;
  name: string;
  provider_uuid: string;
  provider?: ModelProvider;
  extra_args?: object;
}

export interface ApiRespPipelines {
  pipelines: Pipeline[];
}

export interface Pipeline {
  uuid?: string;
  name: string;
  description: string;
  for_version?: string;
  config: object;
  stages?: string[];
  is_default?: boolean;
  created_at?: string;
  updated_at?: string;
  emoji?: string;
}

export interface ApiRespPlatformAdapters {
  adapters: Adapter[];
}

export interface ApiRespPlatformAdapter {
  adapter: Adapter;
}

export interface Adapter {
  name: string;
  label: I18nObject;
  description: I18nObject;
  icon?: string;
  spec: {
    categories?: string[];
    help_links?: Record<string, string>;
    config: IDynamicFormItemSchema[];
  };
}

export interface ApiRespPlatformBots {
  bots: Bot[];
}

export interface ApiRespPlatformBot {
  bot: Bot;
}

export interface Bot {
  uuid?: string;
  name: string;
  description: string;
  enable?: boolean;
  adapter: string;
  adapter_config: object;
  use_pipeline_name?: string;
  use_pipeline_uuid?: string;
  pipeline_routing_rules?: PipelineRoutingRule[];
  created_at?: string;
  updated_at?: string;
  adapter_runtime_values?: object;
}

export type RoutingRuleOperator =
  | 'eq'
  | 'neq'
  | 'contains'
  | 'not_contains'
  | 'starts_with'
  | 'regex';

export interface PipelineRoutingRule {
  type:
    | 'launcher_type'
    | 'launcher_id'
    | 'message_content'
    | 'message_has_element';
  operator: RoutingRuleOperator;
  value: string;
  pipeline_uuid: string;
}

export interface ApiRespKnowledgeBases {
  bases: KnowledgeBase[];
}

export interface ApiRespKnowledgeBase {
  base: KnowledgeBase;
}

export interface KnowledgeBase {
  uuid?: string;
  name: string;
  description: string;
  created_at?: string;
  updated_at?: string;
  emoji?: string;
  // New unified fields
  knowledge_engine_plugin_id?: string;
  creation_settings?: Record<string, unknown>;
  retrieval_settings?: Record<string, unknown>;
  knowledge_engine?: KnowledgeEngineInfo;
}

// Knowledge Engine types
export interface KnowledgeEngineInfo {
  plugin_id: string | null;
  name: I18nObject;
  capabilities: string[];
}

export interface KnowledgeEngine {
  plugin_id: string;
  name: I18nObject;
  description?: I18nObject;
  capabilities: string[];
  // Schema format: Array of form field definitions (IDynamicFormItemSchema-like)
  // Each item: { name, label, type, required, default, description?, options? }
  creation_schema?: unknown[];
  retrieval_schema?: unknown[];
}

export interface ApiRespKnowledgeEngines {
  engines: KnowledgeEngine[];
}

export interface ParserInfo {
  plugin_id: string;
  name: I18nObject;
  description?: I18nObject;
  supported_mime_types: string[];
}

export interface ApiRespParsers {
  parsers: ParserInfo[];
}

export interface ApiRespKnowledgeBaseFiles {
  files: KnowledgeBaseFile[];
}

export interface KnowledgeBaseFile {
  uuid: string;
  file_name: string;
  status: string;
}

// plugins
export interface ApiRespPlugins {
  plugins: Plugin[];
}

export type ExtensionItem =
  | { type: 'plugin'; plugin: Plugin }
  | { type: 'mcp'; server: MCPServer }
  | { type: 'skill'; skill: Skill };

export interface ApiRespExtensions {
  extensions: ExtensionItem[];
}

export interface ApiRespPlugin {
  plugin: Plugin;
}

// export interface Plugin {
//   author: string;
//   name: string;
//   description: I18nLabel;
//   label: I18nLabel;
//   version: string;
//   enabled: boolean;
//   priority: number;
//   status: string;
//   tools: object[];
//   event_handlers: object;
//   main_file: string;
//   pkg_path: string;
//   repository: string;
//   config_schema: IDynamicFormItemSchema[];
// }

export interface ApiRespPluginConfig {
  config: object;
}

export interface PluginReorderElement {
  author: string;
  name: string;
  priority: number;
}

// system
export interface SystemLimitation {
  max_bots: number;
  max_pipelines: number;
  max_extensions: number;
  /** When non-empty, every pipeline is forced to this Box sandbox-scope
   *  template (e.g. ``{global}``) and the per-pipeline "Sandbox Scope"
   *  selector is locked. Used by SaaS deployments. Empty = no restriction. */
  force_box_session_id_template?: string;
}

export interface WizardProgress {
  step: number;
  selected_adapter: string | null;
  created_bot_uuid: string | null;
  bot_saved: boolean;
  selected_runner: string | null;
}

export interface ApiRespSystemInfo {
  debug: boolean;
  version: string;
  edition: string;
  cloud_service_url: string;
  enable_marketplace: boolean;
  allow_modify_login_info: boolean;
  disable_models_service: boolean;
  limitation: SystemLimitation;
  /** Public outbound IPs of the deployment (``system.outbound_ips`` in
   *  config.yaml). Shown on adapter config forms whose platform requires
   *  trusted-IP / IP-whitelist settings. Empty = not configured. */
  outbound_ips: string[];
  wizard_status: string; // 'none' | 'skipped' | 'completed'
  wizard_progress: WizardProgress | null;
}

export interface RagMigrationStatusResp {
  needed: boolean;
  internal_kb_count: number;
  external_kb_count: number;
}

export interface ApiRespPluginSystemStatus {
  is_enable: boolean;
  is_connected: boolean;
  plugin_connector_error: string;
}

export interface ApiRespBoxStatus {
  available: boolean;
  /** Whether ``box.enabled`` is true in config. When false, the sandbox
   * is deliberately disabled — distinct from "configured but failed". */
  enabled?: boolean;
  profile: string;
  recent_error_count: number;
  connector_error?: string;
  backend?: {
    name: string;
    available: boolean;
  };
  active_sessions?: number;
  managed_processes?: number;
  session_ttl_sec?: number;
}

export interface BoxSessionInfo {
  session_id: string;
  backend_name: string;
  image: string;
  network: string;
  host_path: string | null;
  host_path_mode: string;
  mount_path: string;
  cpus: number;
  memory_mb: number;
  created_at: string;
  last_used_at: string;
}

export interface ApiRespAsyncTasks {
  tasks: AsyncTask[];
}

export interface AsyncTaskRuntimeInfo {
  done: boolean;
  exception?: string;
  result?: object;
  state: string;
}

export interface AsyncTaskTaskContext {
  current_action: string;
  log: string;
  metadata?: Record<string, unknown>;
}

export interface AsyncTask {
  id: number;
  kind: string;
  name: string;
  label: string;
  task_type: string; // system or user
  runtime: AsyncTaskRuntimeInfo;
  task_context: AsyncTaskTaskContext;
}

export interface ApiRespMarketplacePlugins {
  plugins: PluginV4[];
  total: number;
}

export interface ApiRespMarketplacePluginDetail {
  plugin: PluginV4;
}

interface GetPipelineConfig {
  ai: object;
  output: object;
  safety: object;
  trigger: object;
}

interface GetPipeline {
  config: GetPipelineConfig;
  created_at: string;
  description: string;
  for_version: string;
  is_default: boolean;
  name: string;
  stages: string[];
  updated_at: string;
  uuid: string;
  emoji?: string;
}

export interface GetPipelineResponseData {
  pipeline: GetPipeline;
}

export interface GetPipelineMetadataResponseData {
  configs: PipelineConfigTab[];
}

export interface ApiRespWebChatMessage {
  message: Message;
}

export interface ApiRespWebChatMessages {
  messages: Message[];
}

export interface RetrieveResultContent {
  type: 'text' | 'image_url' | 'image_base64' | 'file_url';
  text?: string;
  file_name?: string;
  file_url?: string;
  image_url?: string;
  image_base64?: string;
}

export interface RetrieveResult {
  id: string;
  content?: RetrieveResultContent[];
  metadata: {
    file_id?: string;
    text?: string;
    uuid?: string;
    [key: string]: unknown;
  };
  distance: number;
}

export interface ApiRespKnowledgeBaseRetrieve {
  results: RetrieveResult[];
}

// MCP
export interface ApiRespMCPServers {
  servers: MCPServer[];
}

export interface ApiRespMCPServer {
  server: MCPServer;
}

export interface MCPServerExtraArgsSSE {
  url: string;
  headers: Record<string, string>;
  timeout: number;
  ssereadtimeout: number;
}

export interface MCPServerExtraArgsStdio {
  command: string;
  args: string[];
  env: Record<string, string>;
}

export interface MCPServerExtraArgsHttp {
  url: string;
  headers: Record<string, string>;
  timeout: number;
}

// "remote" mode: the user only supplies a URL; the backend auto-detects the
// transport (Streamable HTTP first, falling back to legacy SSE). headers /
// timeout are optional advanced settings.
export interface MCPServerExtraArgsRemote {
  url: string;
  headers?: Record<string, string>;
  timeout?: number;
}

export enum MCPSessionStatus {
  CONNECTING = 'connecting',
  CONNECTED = 'connected',
  ERROR = 'error',
}

export interface MCPServerRuntimeInfo {
  status: MCPSessionStatus;
  error_message?: string;
  /** Stage at which the session failed. Frontends key off this to render
   *  a localized actionable message instead of the raw ``error_message``.
   *  Notable values: ``box_unavailable`` (stdio MCP refused because Box is
   *  disabled / unreachable). See ``MCPSessionErrorPhase`` (backend). */
  error_phase?: string;
  retry_count?: number;
  tool_count: number;
  tools: MCPTool[];
  /** Optional ``box_session_id`` / ``box_enabled`` set when this stdio
   *  server runs inside Box. Absent when Box is unavailable. */
  box_session_id?: string;
  box_enabled?: boolean;
}

interface MCPServerCommon<
  TMode extends 'sse' | 'http' | 'remote' | 'stdio',
  TExtraArgs,
> {
  uuid?: string;
  name: string;
  mode: TMode;
  enable: boolean;
  extra_args: TExtraArgs;
  runtime_info?: MCPServerRuntimeInfo;
  readme?: string;
  created_at?: string;
  updated_at?: string;
  builtin?: boolean;
  locked?: boolean;
  managed_by?: string | null;
  connector_id?: string | null;
}

export type MCPServer =
  | MCPServerCommon<'sse', MCPServerExtraArgsSSE>
  | MCPServerCommon<'http', MCPServerExtraArgsHttp>
  | MCPServerCommon<'remote', MCPServerExtraArgsRemote>
  | MCPServerCommon<'stdio', MCPServerExtraArgsStdio>;

export interface MCPTool {
  name: string;
  description: string;
  parameters?: object;
}

export interface LocalConnectorWorker {
  owned: boolean;
  pid?: number | null;
  port: number;
  started_at?: number | null;
}

export interface LocalConnectorMonitorStatus {
  enabled: boolean;
  owned: boolean;
  pid?: number | null;
  started_at?: number | null;
  running_status: string;
  warmup_completed: boolean;
  poll_seconds?: number | null;
  last_scan_at?: string | null;
  last_change_at?: string | null;
  last_event_at?: string | null;
  outbox_pending: number;
  last_error?: string | null;
}

export interface LocalConnectorStatus {
  connector_id: string;
  name: string;
  builtin: boolean;
  locked: boolean;
  managed_by: string;
  expected_tool_count: number;
  status: string;
  job_status?: string | null;
  job_id?: string | null;
  last_error_code?: string | null;
  last_error_message?: string | null;
  db_dir?: string | null;
  keys_file?: string | null;
  decrypted_dir?: string | null;
  tool_count: number;
  updated_at: number;
  worker: LocalConnectorWorker;
  monitor?: LocalConnectorMonitorStatus;
}

export interface LocalConnectorJob {
  job_id: string;
  connector_id: string;
  status: string;
  stage: string;
  progress: number;
  message: string;
  error_code?: string | null;
  error_message?: string | null;
  created_at: number;
  updated_at: number;
}

export interface ApiRespLocalConnectors {
  connectors: LocalConnectorStatus[];
}

export interface ApiRespLocalConnector {
  connector: LocalConnectorStatus;
}

export interface ApiRespLocalConnectorJob {
  job: LocalConnectorJob | null;
}

export interface ApiRespLocalConnectorMonitor {
  monitor: LocalConnectorMonitorStatus;
}

export interface DatabaseModeConversationStats {
  draft_ready: number;
  failed: number;
  pending: number;
  processed: number;
  processing: number;
  skipped: number;
  total: number;
}

export interface DatabaseModeConversation {
  id: number;
  source: string;
  conversation_name: string;
  conversation_type: string;
  last_message_at?: string | null;
  pending_count: number;
  failed_count: number;
  latest_customer: string;
  latest_message_summary: string;
}

export interface DatabaseModeMessage {
  id: number;
  event_id: string;
  message_key: string;
  conversation_id: number;
  external_message_id?: string | null;
  sender_id: string;
  sender_name: string;
  content: string;
  content_preview: string;
  message_type: string;
  sent_at: string;
  observed_at: string;
  status: string;
  draft_text?: string | null;
  draft_source?: string | null;
  ai_suggested_reply?: string | null;
  attempt_count: number;
  last_error?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  processed_at?: string | null;
}

export interface ApiRespDatabaseModeConversations {
  conversations: DatabaseModeConversation[];
  total: number;
  page: number;
  page_size: number;
}

export interface ApiRespDatabaseModeConversation {
  conversation: {
    id: number;
    connector_id: string;
    source: string;
    external_conversation_id: string;
    conversation_name: string;
    conversation_type: string;
    last_message_at?: string | null;
    created_at?: string | null;
    updated_at?: string | null;
    stats: DatabaseModeConversationStats;
    latest_customer: string;
  };
}

export interface ApiRespDatabaseModeMessages {
  messages: DatabaseModeMessage[];
  total: number;
  page: number;
  page_size: number;
  stats: DatabaseModeConversationStats;
}

export interface ApiRespDatabaseModeMessage {
  message: DatabaseModeMessage;
}

export interface ApiBroadcastScope {
  bot_uuid: string;
  connector_id: string;
}

export interface ApiBroadcastTemplate {
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

export interface ApiBroadcastVariableMappingRule {
  source_field: string;
  variable_key: string;
  merge_mode: 'first' | 'lines' | 'unique_lines' | 'commas' | 'unique_commas';
  order: number;
}

export interface ApiBroadcastVariableProfile {
  group_field: string | null;
  mapping_rules: ApiBroadcastVariableMappingRule[];
}

export interface ApiBroadcastTemplateRenderResult {
  rendered_text: string;
  required_variables: string[];
  missing_variables: string[];
  valid: boolean;
}

export interface ApiBroadcastGroupRule {
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
  invalid_legacy?: boolean;
  invalid_reason?: string | null;
  target_resolution_status?: 'deferred' | 'resolved' | 'unresolved' | 'ambiguous';
  created_at: string;
  updated_at: string;
}

export interface ApiBroadcastGroupMatchResult {
  matched: boolean;
  rule_id: number | null;
  matched_rule_id?: number | null;
  source_value?: string;
  target_conversation_id?: string | null;
  target_conversation_name: string | null;
  target_resolution_status?: 'deferred';
  match_type: 'exact' | 'contains' | 'regex' | null;
  candidate_count?: number;
  candidate_rules?: ApiBroadcastGroupRule[];
  conflict?: boolean;
  reason?: string | null;
}

export interface ApiBroadcastGroupName {
  id: number;
  bot_uuid: string;
  connector_id: string;
  name: string;
  external_conversation_id?: string | null;
  created_at: string;
  updated_at: string;
}

export interface ApiBroadcastGroupNamesResponse {
  group_names: ApiBroadcastGroupName[];
}

export interface ApiBroadcastGroupNameSyncResult {
  scanned: number;
  inserted: number;
  updated: number;
  unchanged: number;
  skipped: number;
  errors: string[];
}

export type ApiBroadcastImportBatchStatus =
  | 'imported'
  | 'matched'
  | 'drafts_generated';

export type ApiBroadcastImportMatchStatus = 'matched' | 'unmatched' | 'invalid';

export type ApiBroadcastImportGroupMatchStatus =
  | ApiBroadcastImportMatchStatus
  | 'conflict';

export type ApiBroadcastImportGroupFieldSource =
  | 'configured'
  | 'auto_detected'
  | 'user_confirmed'
  | 'legacy_fallback';

export interface ApiBroadcastImportBatch {
  id: number;
  bot_uuid: string;
  connector_id: string;
  original_file_name: string;
  file_type: string;
  worksheet_name: string | null;
  status: ApiBroadcastImportBatchStatus;
  drafts_stale: boolean;
  total_rows: number;
  valid_rows: number;
  invalid_rows: number;
  matched_rows: number;
  unmatched_rows: number;
  group_field_used?: string | null;
  group_field_source?: ApiBroadcastImportGroupFieldSource | null;
  created_at: string;
  updated_at: string;
}

export interface ApiBroadcastImportRow {
  id: number;
  import_batch_id: number;
  source_row_number: number;
  raw_data: Record<string, string>;
  group_value: string | null;
  matched_conversation_id?: string | null;
  matched_conversation_name: string | null;
  matched_rule_id: number | null;
  match_status: ApiBroadcastImportMatchStatus;
  error_message: string | null;
  created_at: string;
}

export interface ApiBroadcastImportDetail extends ApiBroadcastImportBatch {
  rows: ApiBroadcastImportRow[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
}

export interface ApiBroadcastAttachment {
  id: number;
  attachment_asset_id: number;
  original_name?: string;
  original_name_snapshot?: string;
  size_bytes?: number;
  size_bytes_snapshot?: number;
  sha256?: string;
  sha256_snapshot?: string;
  extension: string;
  mime_type: string;
  sort_order: number;
}

export interface ApiBroadcastImportGroupSummary {
  group_key: string;
  group_value: string;
  raw_row_count: number;
  distinct_order_number_count: number;
  matched_conversation_id?: string | null;
  matched_conversation_name: string | null;
  match_status: ApiBroadcastImportGroupMatchStatus;
  reason: string | null;
  attachment_count: number;
  expandable: boolean;
  first_source_row_number: number;
  template_id?: number | null;
  template_name?: string | null;
  template_enabled?: boolean | null;
}

export interface ApiBroadcastImportGroupsResponse {
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
  raw_row_total: number;
  group_total: number;
  matched_group_total: number;
  unmatched_group_total: number;
  invalid_group_total: number;
  conflict_group_total: number;
  order_number_field_configured: boolean;
  groups: ApiBroadcastImportGroupSummary[];
}

export type ApiBroadcastGroupRuleCandidateStatus =
  | 'new'
  | 'configured'
  | 'needs_repair'
  | 'conflict'
  | 'invalid';

export interface ApiBroadcastGroupRuleCandidateItem {
  group_key: string;
  customer_name: string;
  raw_row_count: number;
  status: ApiBroadcastGroupRuleCandidateStatus;
  reason: string | null;
  existing_rule_ids: number[];
  existing_rules: ApiBroadcastGroupRule[];
  current_matched_rule: ApiBroadcastGroupRule | null;
  current_target_conversation_id?: string | null;
  current_target_conversation_name: string | null;
  current_match_type: 'exact' | 'contains' | 'regex' | null;
}

export interface ApiBroadcastImportGroupRuleCandidatesResponse {
  import_batch_id: number;
  group_field_used: string;
  group_field_source: ApiBroadcastImportGroupFieldSource;
  raw_row_total: number;
  unique_customer_total: number;
  stats: {
    new_count: number;
    configured_count: number;
    needs_repair_count: number;
    conflict_count: number;
    invalid_count: number;
  };
  items: ApiBroadcastGroupRuleCandidateItem[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
}

export interface ApiBroadcastBulkAssignResultItem {
  group_key: string;
  customer_name: string;
  rule_id: number;
  target_conversation_id: string;
  target_conversation_name: string;
}

export interface ApiBroadcastBulkAssignResult {
  created_count: number;
  group_field_used: string;
  group_field_source: ApiBroadcastImportGroupFieldSource;
  items: ApiBroadcastBulkAssignResultItem[];
}

export interface ApiBroadcastImportGroupRowsResponse {
  group_key: string;
  group_value: string | null;
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
  rows: ApiBroadcastImportRow[];
}

export type ApiBroadcastDraftSendStatus = 'pending' | 'sent' | 'unknown';
export type ApiBroadcastDraftStatus =
  | 'pending_review'
  | 'ready'
  | 'invalid'
  | ApiBroadcastDraftSendStatus;

export interface ApiBroadcastDraft {
  id: number;
  bot_uuid: string;
  connector_id: string;
  import_batch_id: number;
  group_value: string;
  target_conversation_id?: string | null;
  target_conversation_name: string | null;
  template_id: number | null;
  template_name_snapshot: string;
  template_content_snapshot: string;
  render_variables: Record<string, string>;
  draft_text: string;
  status: ApiBroadcastDraftStatus;
  send_status?: ApiBroadcastDraftSendStatus | null;
  sent_at?: string | null;
  legacy_status?: 'pending_review' | 'ready' | 'invalid' | null;
  error_message: string | null;
  drafts_stale: boolean;
  attachments_stale?: boolean;
  attachments?: ApiBroadcastAttachment[];
  created_at: string;
  updated_at: string;
  message?: string | null;
}

export interface ApiBroadcastImportDraftGenerationItem {
  group_key: string;
  draft_id: number;
  operation: 'created' | 'updated';
  modified_fields: string[];
}

export interface ApiBroadcastImportDraftGenerationResult {
  total_group_count: number;
  pending_review_count: number;
  invalid_count: number;
  unmatched_group_count: number;
  created_count?: number;
  updated_count?: number;
  generated_group_keys?: string[];
  draft_ids?: number[];
  draft_results?: ApiBroadcastImportDraftGenerationItem[];
}

export interface ApiBroadcastImportGroupTemplateAssignment {
  group_key: string;
  template_id: number | null;
}

export interface ApiBroadcastDraftStatusUpdateResult {
  updated_count: number;
}

export interface ApiBroadcastExecutionTask {
  id: number;
  execution_batch_id: number;
  draft_id: number | null;
  draft_text_snapshot: string;
  target_conversation_snapshot: string;
  channel: string;
  action: string;
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
  attachments?: ApiBroadcastAttachment[];
}

export interface ApiBroadcastExecutionBatch {
  id: number;
  bot_uuid: string;
  connector_id: string;
  channel: string;
  mode: string;
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
  tasks?: ApiBroadcastExecutionTask[];
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

export interface ApiBroadcastExecutionAttempt {
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

export interface ApiBroadcastExecutionEvidence {
  id: number;
  execution_attempt_id: number;
  window_title: string | null;
  target_conversation: string | null;
  action: string;
  input_located: boolean;
  draft_written: boolean;
  send_triggered: boolean;
  clipboard_restored: boolean;
  runtime_state: string | null;
  evidence_summary: string | null;
  technical_details: Record<string, unknown> | null;
  created_at: string;
}

export type DatabaseModeRealtimeEventType =
  | 'database-message-created'
  | 'database-message-updated'
  | 'database-message-deleted'
  | 'database-conversation-updated'
  | 'database-mode-invalidated'
  | 'ready';

export interface DatabaseModeRealtimeEvent {
  type: DatabaseModeRealtimeEventType;
  event_id?: string;
  conversation_id?: number | null;
  message_id?: number | null;
  occurred_at?: string | null;
  metadata?: {
    desktop_run_id?: number | null;
    desktop_status?: string | null;
    desktop_stage?: string | null;
    desktop_error_code?: string | null;
    draft_id?: number | null;
    bot_uuid?: string | null;
    action?: string | null;
    timings?: {
      file_change_detected_at?: string | null;
      stability_completed_at?: string | null;
      decrypt_started_at?: string | null;
      decrypt_completed_at?: string | null;
      scan_completed_at?: string | null;
      outbox_created_at?: string | null;
      delivery_succeeded_at?: string | null;
      langbot_ingested_at?: string | null;
      sse_published_at?: string | null;
    };
  };
}

export interface PluginTool {
  name: string;
  description: string;
  human_desc: string;
  parameters: object;
}

export interface ApiRespTools {
  tools: PluginTool[];
}

export interface ApiRespToolDetail {
  tool: PluginTool;
}

// Skills
export interface Skill {
  name: string;
  display_name?: string;
  description: string;
  instructions?: string;
  package_root?: string;
  is_builtin?: boolean;
  created_at?: string;
  updated_at?: string;
}

export interface ApiRespSkills {
  skills: Skill[];
}

export interface ApiRespSkill {
  skill: Skill;
}

// Re-export Bot-scoped Database Mode API types
export * from './bot-database';
