/**
 * Runtime Bot Data Source
 * Uses existing session API for normal bots
 */

import { backendClient } from '@/app/infra/http';
import type {
  BotSessionDataSource,
  ListConversationsParams,
  ListMessagesParams,
  ConversationsResponse,
  ConversationResponse,
  MessagesResponse,
  DraftResponse,
  BatchResponse,
  SendDraftResponse,
} from '../types';
import type {
  BotConversation,
  BotMessage,
  DesktopAutomationRun,
  DesktopRuntimeStatus,
} from '@/app/infra/entities/api';

/**
 * RuntimeBotDataSource adapts the existing session API to the BotSessionDataSource interface
 * For normal bots (non-database mode), many operations are not supported
 */
export class RuntimeBotDataSource implements BotSessionDataSource {
  constructor(private botId: string) {}

  async listConversations(
    _params?: ListConversationsParams,
  ): Promise<ConversationsResponse> {
    // For runtime bots, we use the existing session API
    const response = await backendClient.getBotSessions(this.botId);

    // Map sessions to conversation format
    const conversations: BotConversation[] = (response.sessions || []).map(
      (session: any) => ({
        id: parseInt(session.session_id) || 0,
        connector_id: '',
        source: session.platform || 'unknown',
        external_conversation_id: session.session_id,
        conversation_name:
          session.user_name || session.user_id || session.session_id,
        conversation_type: session.session_id.startsWith('group_')
          ? 'group'
          : 'direct',
        last_message_at: session.last_activity,
        pending_count: 0,
        draft_ready_count: 0,
        processed_count: session.message_count || 0,
        failed_count: 0,
        created_at: session.start_time,
        updated_at: session.last_activity,
      }),
    );

    return {
      conversations,
      total: conversations.length,
      page: 1,
      page_size: conversations.length,
    };
  }

  async getConversation(conversationId: string): Promise<ConversationResponse> {
    // For runtime bots, return minimal conversation data
    const conversation: BotConversation = {
      id: parseInt(conversationId) || 0,
      connector_id: '',
      source: 'runtime',
      external_conversation_id: conversationId,
      conversation_name: conversationId,
      conversation_type: 'direct',
      last_message_at: new Date().toISOString(),
      pending_count: 0,
      draft_ready_count: 0,
      processed_count: 0,
      failed_count: 0,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    };

    return { conversation };
  }

  async listMessages(
    conversationId: string,
    _params?: ListMessagesParams,
  ): Promise<MessagesResponse> {
    // For runtime bots, use session messages API
    const response = await backendClient.getSessionMessages(conversationId);

    // Map session messages to BotMessage format
    const messages: BotMessage[] = (response.messages || []).map(
      (msg: any, index: number) => ({
        id: parseInt(msg.id) || index,
        event_id: msg.id,
        message_key: msg.id,
        conversation_id: parseInt(conversationId) || 0,
        sender_id: msg.user_id || 'system',
        sender_name: msg.user_id || 'System',
        content: msg.message_content || '',
        message_type: 'text',
        sent_at: msg.timestamp,
        observed_at: msg.timestamp,
        status: 'processed',
        draft_text: undefined,
        draft_source: undefined,
        last_error: undefined,
        attempt_count: 0,
        processed_at: msg.timestamp,
        created_at: msg.timestamp,
        updated_at: msg.timestamp,
      }),
    );

    return {
      messages,
      total: messages.length,
      page: 1,
      page_size: messages.length,
      stats: {
        pending_count: 0,
        draft_ready_count: 0,
        processed_count: messages.length,
        failed_count: 0,
      },
    };
  }

  async generateDraft(_messageId: string): Promise<DraftResponse> {
    throw new Error('Draft generation not supported for runtime bots');
  }

  async updateDraft(
    _messageId: string,
    _content: string,
    _draftId?: string | null,
  ): Promise<any> {
    throw new Error('Draft update not supported for runtime bots');
  }

  async deleteDraft(
    _messageId: string,
    _draftId?: string | null,
  ): Promise<any> {
    throw new Error('Draft deletion not supported for runtime bots');
  }

  async pasteDraft(
    _messageId: string,
    _draftId: string,
    _idempotencyKey: string,
  ): Promise<SendDraftResponse> {
    throw new Error('Desktop paste not supported for runtime bots');
  }

  async getDesktopRun(_runId: string): Promise<DesktopAutomationRun> {
    throw new Error('Desktop send not supported for runtime bots');
  }

  async cancelDesktopRun(_runId: string): Promise<DesktopAutomationRun> {
    throw new Error('Desktop send not supported for runtime bots');
  }

  async getDesktopRuntimeStatus(): Promise<DesktopRuntimeStatus> {
    return { status: 'unsupported' };
  }

  async processMessage(_messageId: string): Promise<void> {
    throw new Error('Message processing not supported for runtime bots');
  }

  async skipMessage(_messageId: string): Promise<void> {
    throw new Error('Message skipping not supported for runtime bots');
  }

  async deleteMessage(_messageId: string): Promise<void> {
    throw new Error('Message deletion not supported for runtime bots');
  }

  async batchProcess(_messageIds: string[]): Promise<BatchResponse> {
    throw new Error('Batch processing not supported for runtime bots');
  }

  async batchSkip(_messageIds: string[]): Promise<BatchResponse> {
    throw new Error('Batch skip not supported for runtime bots');
  }

  async batchDelete(_messageIds: string[]): Promise<BatchResponse> {
    throw new Error('Batch delete not supported for runtime bots');
  }
}
