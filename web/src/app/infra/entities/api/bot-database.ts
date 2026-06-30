/**
 * Bot-scoped Database Mode API Types
 * These types correspond to /api/v1/bots/{bot_id}/* endpoints
 */

export interface BotConversation {
  id: number;
  connector_id: string;
  source: string;
  external_conversation_id: string;
  conversation_name: string;
  conversation_type: 'direct' | 'group';
  last_message_at: string;
  pending_count: number;
  draft_ready_count: number;
  processed_count: number;
  failed_count: number;
  latest_customer?: string;
  latest_message_summary?: string;
  created_at: string;
  updated_at: string;
}

export interface ApiRespBotConversations {
  conversations: BotConversation[];
  total: number;
  page: number;
  page_size: number;
}

export interface ApiRespBotConversation {
  conversation: BotConversation;
}

export interface BotMessage {
  id: number;
  event_id: string;
  message_key: string;
  conversation_id: number;
  sender_id: string;
  sender_name: string;
  content: string;
  message_type: string;
  sent_at: string;
  observed_at: string;
  status:
    | 'pending'
    | 'processing'
    | 'draft_ready'
    | 'processed'
    | 'skipped'
    | 'failed';
  draft_text?: string;
  draft_source?: 'pipeline' | 'manual';
  draft_id?: number;
  draft_version?: number;
  draft_updated_at?: string;
  last_error?: string;
  attempt_count: number;
  processed_at?: string;
  created_at: string;
  updated_at: string;
}

export interface BotMessageStats {
  pending_count: number;
  draft_ready_count: number;
  processed_count: number;
  failed_count: number;
}

export interface ApiRespBotMessages {
  messages: BotMessage[];
  total: number;
  page: number;
  page_size: number;
  stats: BotMessageStats;
}

export interface ApiRespBotMessage {
  message: BotMessage;
}

export interface ReplyDraft {
  id: number;
  processing_run_id?: number;
  message_id: number;
  bot_uuid: string;
  content: string;
  source: 'pipeline' | 'manual';
  version: number;
  status: 'active' | 'superseded';
  created_at: string;
  updated_at: string;
}

export interface MessageProcessingRun {
  id: number;
  message_id: number;
  bot_uuid: string;
  pipeline_uuid?: string;
  trigger: 'manual' | 'automatic';
  status: 'processing' | 'succeeded' | 'failed';
  attempt_count: number;
  started_at?: string;
  completed_at?: string;
  last_error?: string;
}

export interface ApiRespGenerateDraft {
  status: 'succeeded' | 'already_succeeded' | 'processing' | 'claim_conflict';
  draft?: ReplyDraft;
  run?: MessageProcessingRun;
  message?: string;
  message_id?: number;
}

export interface ApiRespUpdateDraft {
  message: BotMessage;
}

export interface ApiRespBatchOperation {
  messages: BotMessage[];
  succeeded: number;
  failed: number;
}

export interface DesktopAutomationRun {
  id: number;
  bot_uuid: string;
  connector_id: string;
  conversation_id: number;
  message_id: number;
  draft_id: number;
  action:
    | 'paste_current_wecom_draft'
    | 'paste_draft'
    | 'send_draft'
    | 'send_draft_dry_run'
    | 'diagnose';
  execution_mode:
    | 'paste_only'
    | 'auto_send'
    | 'user_confirmed_send'
    | 'send_dry_run'
    | 'diagnose';
  runtime_task_id?: string | null;
  status:
    | 'queued'
    | 'starting'
    | 'running'
    | 'waiting_manual'
    | 'succeeded'
    | 'succeeded_with_warning'
    | 'blocked'
    | 'failed'
    | 'cancelled'
    | 'timed_out';
  stage?: string | null;
  attempt_count: number;
  request_digest: string;
  draft_content_hash: string;
  target_snapshot?: Record<string, unknown>;
  result_evidence?: Record<string, unknown> | null;
  last_error_code?: string | null;
  last_error_message?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
  created_at: string;
  updated_at: string;
}

export interface DesktopRuntimeStatus {
  status:
    | 'unsupported'
    | 'disabled'
    | 'not_configured'
    | 'starting'
    | 'ready'
    | 'failed'
    | 'stopped';
  host?: string;
  port?: number;
  runtimeVersion?: string;
  protocolVersion?: string;
  error?: string;
  runtime_configured?: boolean;
  runtime_startable?: boolean;
  runtime_reachable?: boolean;
  send_enabled?: boolean;
}
