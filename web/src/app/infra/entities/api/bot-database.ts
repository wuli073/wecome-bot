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
  status: 'succeeded' | 'already_succeeded' | 'processing';
  draft?: ReplyDraft;
  run?: MessageProcessingRun;
  message?: string;
}

export interface ApiRespUpdateDraft {
  message: BotMessage;
}

export interface ApiRespBatchOperation {
  messages: BotMessage[];
  succeeded: number;
  failed: number;
}
