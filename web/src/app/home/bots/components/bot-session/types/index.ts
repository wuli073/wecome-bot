/**
 * Data source abstraction for Bot Session Monitor
 * Allows switching between runtime bot sessions and database mode sessions
 */

import type {
  BotConversation,
  BotMessage,
  BotMessageStats,
} from '@/app/infra/entities/api';

export type SessionMonitorSource = 'runtime' | 'database';

export interface ListConversationsParams {
  status?: string;
  keyword?: string;
  page?: number;
  page_size?: number;
}

export interface ListMessagesParams {
  status?: string;
  page?: number;
  page_size?: number;
}

export interface ConversationsResponse {
  conversations: BotConversation[];
  total: number;
  page: number;
  page_size: number;
}

export interface ConversationResponse {
  conversation: BotConversation;
}

export interface MessagesResponse {
  messages: BotMessage[];
  total: number;
  page: number;
  page_size: number;
  stats: BotMessageStats;
}

export interface DraftResponse {
  status: 'succeeded' | 'already_succeeded' | 'processing' | 'claim_conflict';
  draft?: any;
  run?: any;
  message?: string;
  message_id?: number;
}

export interface BatchResponse {
  messages: BotMessage[];
  succeeded: number;
  failed: number;
}

/**
 * Abstract interface for bot session data sources
 */
export interface BotSessionDataSource {
  // Conversations
  listConversations(
    params?: ListConversationsParams,
  ): Promise<ConversationsResponse>;
  getConversation(conversationId: string): Promise<ConversationResponse>;

  // Messages
  listMessages(
    conversationId: string,
    params?: ListMessagesParams,
  ): Promise<MessagesResponse>;

  // Draft operations
  generateDraft(messageId: string): Promise<DraftResponse>;
  updateDraft(
    messageId: string,
    content: string,
    draftId?: string | null,
  ): Promise<any>;
  deleteDraft(messageId: string, draftId?: string | null): Promise<any>;

  // Message operations
  processMessage(messageId: string): Promise<void>;
  skipMessage(messageId: string): Promise<void>;
  deleteMessage(messageId: string): Promise<void>;

  // Batch operations
  batchProcess(messageIds: string[]): Promise<BatchResponse>;
  batchSkip(messageIds: string[]): Promise<BatchResponse>;
  batchDelete(messageIds: string[]): Promise<BatchResponse>;
}

export interface BotSessionMonitorProps {
  botId: string;
  botAdapter: string;
  botEnabled: boolean;
}
