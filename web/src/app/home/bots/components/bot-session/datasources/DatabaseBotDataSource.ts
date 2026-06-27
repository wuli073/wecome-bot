/**
 * Database Bot Data Source
 * Uses Bot-scoped API (/api/v1/bots/{bot_id}/*)
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
} from '../types';

export class DatabaseBotDataSource implements BotSessionDataSource {
  constructor(private botId: string) {}

  async listConversations(
    params?: ListConversationsParams,
  ): Promise<ConversationsResponse> {
    const response = await backendClient.listBotConversations(
      this.botId,
      params,
    );
    return {
      conversations: response.conversations,
      total: response.total,
      page: response.page,
      page_size: response.page_size,
    };
  }

  async getConversation(conversationId: string): Promise<ConversationResponse> {
    const response = await backendClient.getBotConversation(
      this.botId,
      conversationId,
    );
    return {
      conversation: response.conversation,
    };
  }

  async listMessages(
    conversationId: string,
    params?: ListMessagesParams,
  ): Promise<MessagesResponse> {
    const response = await backendClient.listBotMessages(
      this.botId,
      conversationId,
      params,
    );
    return {
      messages: response.messages,
      total: response.total,
      page: response.page,
      page_size: response.page_size,
      stats: response.stats,
    };
  }

  async generateDraft(messageId: string): Promise<DraftResponse> {
    const response = await backendClient.generateBotDraft(
      this.botId,
      messageId,
    );
    return {
      status: response.status,
      draft: response.draft,
      run: response.run,
      message: response.message,
    };
  }

  async updateDraft(
    messageId: string,
    content: string,
    draftId?: string | null,
  ): Promise<any> {
    if (draftId) {
      return backendClient.updateBotDraft(this.botId, draftId, content);
    }

    return backendClient.updateDatabaseModeDraft(Number(messageId), {
      draft_text: content,
      draft_source: 'manual',
    });
  }

  async deleteDraft(messageId: string, draftId?: string | null): Promise<any> {
    if (draftId) {
      return backendClient.deleteBotDraft(this.botId, draftId);
    }

    return backendClient.deleteDatabaseModeDraft(Number(messageId));
  }

  async processMessage(messageId: string): Promise<void> {
    await backendClient.processBotMessage(this.botId, messageId);
  }

  async skipMessage(messageId: string): Promise<void> {
    await backendClient.skipBotMessage(this.botId, messageId);
  }

  async deleteMessage(messageId: string): Promise<void> {
    await backendClient.deleteBotMessage(this.botId, messageId);
  }

  async batchProcess(messageIds: string[]): Promise<BatchResponse> {
    const response = await backendClient.batchProcessBotMessages(
      this.botId,
      messageIds,
    );
    return {
      messages: response.messages,
      succeeded: response.succeeded,
      failed: response.failed,
    };
  }

  async batchSkip(messageIds: string[]): Promise<BatchResponse> {
    const response = await backendClient.batchSkipBotMessages(
      this.botId,
      messageIds,
    );
    return {
      messages: response.messages,
      succeeded: response.succeeded,
      failed: response.failed,
    };
  }

  async batchDelete(messageIds: string[]): Promise<BatchResponse> {
    const response = await backendClient.batchDeleteBotMessages(
      this.botId,
      messageIds,
    );
    return {
      messages: response.messages,
      succeeded: response.succeeded,
      failed: response.failed,
    };
  }
}
