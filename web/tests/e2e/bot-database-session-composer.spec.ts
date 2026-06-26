import { expect, test, type Page, type Route } from '@playwright/test';

import { installLangBotApiMocks } from './fixtures/langbot-api';

type MessageStatus =
  | 'pending'
  | 'processing'
  | 'draft_ready'
  | 'processed'
  | 'skipped'
  | 'failed';

interface DraftState {
  id: number;
  message_id: number;
  content: string;
  source: 'pipeline' | 'manual';
  status?: 'active' | 'superseded';
  processing_run_id?: number;
  version: number;
  updated_at: string;
  created_at?: string;
}

interface MessageState {
  id: number;
  sender_id: string;
  sender_name: string;
  content: string;
  sent_at: string;
  status: MessageStatus;
  draft_text?: string;
  draft_source?: 'pipeline' | 'manual';
  last_error?: string;
  deleted?: boolean;
}

interface ConversationState {
  id: number;
  name: string;
  type: 'direct' | 'group';
  messages: MessageState[];
  drafts: Record<number, DraftState>;
}

interface GenerateDraftMockConfig {
  delayMs?: number;
  dispatchSseEvent?: boolean;
  persistDraftToMessage?: boolean;
  persistedDraftContent?: string | null;
  persistedStatus?: MessageStatus;
  responseDraftContent?: string;
  responseIncludesDraft?: boolean;
  responseStatus?: 'succeeded' | 'already_succeeded' | 'processing';
}

interface InstallDatabaseBotSessionMockOptions {
  extraAlphaMessages?: MessageState[];
  generateDraftByMessageId?: Record<number, GenerateDraftMockConfig>;
}

interface MockMetrics {
  generateCalls: number[];
  processCalls: number[];
  skipCalls: number[];
  deleteCalls: number[];
  batchProcessCalls: number[][];
  batchSkipCalls: number[][];
  batchDeleteCalls: number[][];
}

function iso(offsetMinutes: number) {
  return new Date(Date.UTC(2026, 5, 26, 8, offsetMinutes, 0)).toISOString();
}

function cloneMessage(
  message: MessageState,
  conversationId: number,
  draft?: DraftState,
) {
  return {
    id: message.id,
    event_id: `evt-${message.id}`,
    message_key: `wxwork:${message.id}`,
    conversation_id: conversationId,
    sender_id: message.sender_id,
    sender_name: message.sender_name,
    content: message.content,
    message_type: 'text',
    sent_at: message.sent_at,
    observed_at: message.sent_at,
    status: message.status,
    draft_text: message.draft_text,
    draft_source: message.draft_source,
    draft_id: draft?.id,
    draft_version: draft?.version,
    draft_updated_at: draft?.updated_at,
    last_error: message.last_error,
    attempt_count: 0,
    created_at: message.sent_at,
    updated_at: message.sent_at,
  };
}

function buildDraft(
  draftId: number,
  messageId: number,
  content: string,
  updatedAt: string,
  version: number,
): DraftState {
  return {
    id: draftId,
    message_id: messageId,
    content,
    source: 'pipeline',
    status: 'active',
    processing_run_id: 1,
    version,
    updated_at: updatedAt,
    created_at: updatedAt,
  };
}

function draftCounts(messages: MessageState[]) {
  return messages.reduce(
    (acc, message) => {
      if (message.deleted) {
        return acc;
      }
      if (message.status === 'pending') {
        acc.pending_count += 1;
      }
      if (message.status === 'draft_ready') {
        acc.draft_ready_count += 1;
      }
      if (message.status === 'processed') {
        acc.processed_count += 1;
      }
      if (message.status === 'failed') {
        acc.failed_count += 1;
      }
      return acc;
    },
    {
      pending_count: 0,
      draft_ready_count: 0,
      processed_count: 0,
      failed_count: 0,
    },
  );
}

function buildConversationResponse(conversation: ConversationState) {
  const counts = draftCounts(conversation.messages);
  const latestMessage = [...conversation.messages]
    .filter((message) => !message.deleted)
    .at(-1);
  return {
    id: conversation.id,
    connector_id: 'wxwork-local',
    source: 'wxwork',
    external_conversation_id: `conv-${conversation.id}`,
    conversation_name: conversation.name,
    conversation_type: conversation.type,
    last_message_at: conversation.messages.at(-1)?.sent_at ?? iso(0),
    created_at: iso(0),
    updated_at: iso(0),
    pending_count: counts.pending_count,
    draft_ready_count: counts.draft_ready_count,
    processed_count: counts.processed_count,
    failed_count: counts.failed_count,
    latest_customer: latestMessage?.sender_name ?? '',
    latest_message_summary: latestMessage?.content ?? '',
  };
}

function buildMessagesResponse(conversation: ConversationState) {
  const visibleMessages = conversation.messages
    .filter((message) => !message.deleted)
    .map((message) => {
      const draft = Object.values(conversation.drafts).find(
        (item) => item.message_id === message.id && item.status !== 'superseded',
      );
      return cloneMessage(message, conversation.id, draft);
    });
  const counts = draftCounts(conversation.messages);
  return {
    messages: visibleMessages,
    total: visibleMessages.length,
    page: 1,
    page_size: 200,
    stats: counts,
  };
}

async function installDatabaseBotSessionMocks(
  page: Page,
  options: InstallDatabaseBotSessionMockOptions = {},
) {
  await installLangBotApiMocks(page, { authenticated: true });

  await page.addInitScript(() => {
    class FakeEventSource {
      static CONNECTING = 0;
      static OPEN = 1;
      static CLOSED = 2;
      url: string;
      withCredentials: boolean;
      readyState = FakeEventSource.CONNECTING;
      onopen: ((event: Event) => void) | null = null;
      onerror: ((event: Event) => void) | null = null;
      listeners = new Map<string, Array<(event: MessageEvent) => void>>();

      constructor(url: string, init?: EventSourceInit) {
        this.url = url;
        this.withCredentials = Boolean(init?.withCredentials);
        (
          window as Window & {
            __botDatabaseEventSources?: FakeEventSource[];
          }
        ).__botDatabaseEventSources = [
          ...((window as Window & {
            __botDatabaseEventSources?: FakeEventSource[];
          }).__botDatabaseEventSources ?? []),
          this,
        ];
        (
          window as Window & { __botDatabaseEventSourceCreations?: number }
        ).__botDatabaseEventSourceCreations =
          ((window as Window & { __botDatabaseEventSourceCreations?: number })
            .__botDatabaseEventSourceCreations ?? 0) + 1;
        window.setTimeout(() => {
          this.readyState = FakeEventSource.OPEN;
          this.onopen?.(new Event('open'));
        }, 0);
      }

      addEventListener(type: string, listener: (event: MessageEvent) => void) {
        const next = this.listeners.get(type) ?? [];
        next.push(listener);
        this.listeners.set(type, next);
      }

      emit(type: string, payload: unknown) {
        const event = {
          data: JSON.stringify(payload),
        } as MessageEvent;
        for (const listener of this.listeners.get(type) ?? []) {
          listener(event);
        }
      }

      close() {
        this.readyState = FakeEventSource.CLOSED;
      }
    }

    Object.defineProperty(window.navigator, 'clipboard', {
      configurable: true,
      value: {
        writeText: async () => undefined,
      },
    });

    (window as Window & { EventSource: typeof EventSource }).EventSource =
      FakeEventSource as unknown as typeof EventSource;

    (
      window as Window & {
        __emitBotDatabaseEvent?: (type: string, payload: unknown) => void;
      }
    ).__emitBotDatabaseEvent = (type: string, payload: unknown) => {
      const sources =
        (
          window as Window & {
            __botDatabaseEventSources?: FakeEventSource[];
          }
        ).__botDatabaseEventSources ?? [];
      for (const source of sources) {
        source.emit(type, payload);
      }
    };
  });

  const conversations = new Map<number, ConversationState>([
    [
      101,
      {
        id: 101,
        name: 'Customer Alpha',
        type: 'direct',
        drafts: {},
        messages: [
          {
            id: 1001,
            sender_id: 'customer-1',
            sender_name: 'Alice',
            content: 'Need onboarding steps',
            sent_at: iso(1),
            status: 'pending',
          },
          {
            id: 1002,
            sender_id: 'customer-1',
            sender_name: 'Alice',
            content: 'The previous reply failed',
            sent_at: iso(4),
            status: 'failed',
            last_error: 'pipeline timeout',
          },
          {
            id: 1003,
            sender_id: 'bot',
            sender_name: 'Sales Bot',
            content: 'I will follow up shortly.',
            sent_at: iso(5),
            status: 'processed',
          },
          ...(options.extraAlphaMessages ?? []),
        ],
      },
    ],
    [
      202,
      {
        id: 202,
        name: 'Customer Beta',
        type: 'direct',
        drafts: {
          9002: {
            id: 9002,
            message_id: 2001,
            content: 'Saved draft for beta conversation',
            source: 'manual',
            version: 3,
            updated_at: iso(13),
          },
        },
        messages: [
          {
            id: 2001,
            sender_id: 'customer-2',
            sender_name: 'Bob',
            content: 'Please share the contract',
            sent_at: iso(12),
            status: 'draft_ready',
            draft_text: 'Saved draft for beta conversation',
            draft_source: 'manual',
          },
        ],
      },
    ],
  ]);

  const generateCalls: number[] = [];
  const processCalls: number[] = [];
  const skipCalls: number[] = [];
  const deleteCalls: number[] = [];
  const batchProcessCalls: number[][] = [];
  const batchSkipCalls: number[][] = [];
  const batchDeleteCalls: number[][] = [];

  await page.route('**/api/v1/platform/bots', async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        code: 0,
        msg: 'ok',
        data: {
          bots: [
            {
              uuid: 'bot-db',
              name: 'Database Bot',
              description: 'bot session monitor',
              enable: true,
              adapter: 'wxwork_database',
              adapter_config: {},
              adapter_runtime_values: {},
              pipeline_routing_rules: [],
              updated_at: iso(0),
            },
          ],
        },
      }),
    });
  });

  await page.route('**/api/v1/platform/bots/bot-db', async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        code: 0,
        msg: 'ok',
        data: {
          bot: {
            uuid: 'bot-db',
            name: 'Database Bot',
            description: 'bot session monitor',
            enable: true,
            adapter: 'wxwork_database',
            adapter_config: {},
            adapter_runtime_values: {},
            pipeline_routing_rules: [],
            updated_at: iso(0),
          },
        },
      }),
    });
  });

  await page.route(
    '**/api/v1/database-mode/events/session',
    async (route: Route) => {
      await route.fulfill({
        status: 204,
        headers: {
          'Cache-Control': 'no-store',
          'Set-Cookie':
            'langbot_dbmode_sse=test; Path=/api/v1/database-mode/events; HttpOnly; SameSite=Strict',
        },
      });
    },
  );

  await page.route(
    '**/api/v1/bots/bot-db/conversations',
    async (route: Route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          code: 0,
          msg: 'ok',
          data: {
            conversations: Array.from(conversations.values()).map(
              buildConversationResponse,
            ),
            total: conversations.size,
            page: 1,
            page_size: 100,
          },
        }),
      });
    },
  );

  await page.route(
    '**/api/v1/bots/bot-db/conversations/*/messages',
    async (route: Route) => {
      const parts = new URL(route.request().url()).pathname.split('/');
      const conversationId = Number(parts[parts.length - 2]);
      const conversation = conversations.get(conversationId);

      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          code: 0,
          msg: 'ok',
          data: conversation
            ? buildMessagesResponse(conversation)
            : {
                messages: [],
                total: 0,
                page: 1,
                page_size: 200,
                stats: draftCounts([]),
              },
        }),
      });
    },
  );

  await page.route(
    '**/api/v1/bots/bot-db/messages/*/generate-draft',
    async (route: Route) => {
      const parts = new URL(route.request().url()).pathname.split('/');
      const messageId = Number(parts[parts.length - 2]);
      generateCalls.push(messageId);
      const scenario = options.generateDraftByMessageId?.[messageId];

      const conversation = Array.from(conversations.values()).find((item) =>
        item.messages.some((message) => message.id === messageId),
      );
      const message = conversation?.messages.find(
        (item) => item.id === messageId,
      );

      if (!conversation || !message) {
        await route.fulfill({
          status: 404,
          contentType: 'application/json',
          body: JSON.stringify({
            code: -1,
            msg: 'message not found',
            data: null,
          }),
        });
        return;
      }

      const draftId = 9000 + messageId;
      const responseStatus = scenario?.responseStatus ?? 'succeeded';
      const responseDraftContent =
        scenario?.responseDraftContent ?? `Draft for message ${messageId}`;
      const updatedAt = iso(20 + generateCalls.length);
      const nextVersion =
        Object.values(conversation.drafts).find(
          (existingDraft) => existingDraft.message_id === messageId,
        )?.version ?? 1;
      const draft = buildDraft(
        draftId,
        messageId,
        responseDraftContent,
        updatedAt,
        nextVersion + 1,
      );

      if (scenario?.delayMs) {
        await page.waitForTimeout(scenario.delayMs);
      }

      const persistDraftToMessage =
        scenario?.persistDraftToMessage ?? responseStatus !== 'processing';
      if (persistDraftToMessage) {
        const persistedDraftContent =
          scenario?.persistedDraftContent ?? responseDraftContent;
        conversation.drafts[draftId] = {
          ...draft,
          content: persistedDraftContent,
        };
        message.draft_text = persistedDraftContent;
        message.draft_source = draft.source;
        message.status = scenario?.persistedStatus ?? 'draft_ready';
      }

      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          code: 0,
          msg: 'ok',
          data: {
            status: responseStatus,
            ...(scenario?.responseIncludesDraft === false
              ? {}
              : { draft }),
            run: {
              id: 1,
              message_id: messageId,
              status: responseStatus === 'processing' ? 'processing' : 'succeeded',
              trigger: 'manual',
            },
            ...(responseStatus === 'processing'
              ? { message: 'Another processing is in progress' }
              : {}),
          },
        }),
      });

      if (scenario?.dispatchSseEvent) {
        await page.evaluate(
          ({ conversationId, messageId }) => {
            (
              window as Window & {
                __emitBotDatabaseEvent?: (type: string, payload: unknown) => void;
              }
            ).__emitBotDatabaseEvent?.('database-message-updated', {
              type: 'database-message-updated',
              conversation_id: conversationId,
              message_id: messageId,
            });
          },
          { conversationId: conversation.id, messageId },
        );
      }
    },
  );

  await page.route('**/api/v1/bots/bot-db/drafts/*', async (route: Route) => {
    const parts = new URL(route.request().url()).pathname.split('/');
    const draftId = Number(parts[parts.length - 1]);
    const payload = JSON.parse(route.request().postData() || '{}') as {
      content?: string;
    };

    const conversation = Array.from(conversations.values()).find((item) =>
      Object.prototype.hasOwnProperty.call(item.drafts, draftId),
    );
    const draft = conversation?.drafts[draftId];
    const message = conversation?.messages.find(
      (item) => item.id === draft?.message_id,
    );

    if (draft && conversation && message) {
      draft.content = payload.content ?? draft.content;
      draft.updated_at = iso(50);
      draft.version += 1;
      message.draft_text = draft.content;
      message.draft_source = draft.source;
    }

    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        code: 0,
        msg: 'ok',
        data: {
          message:
            message && conversation
              ? cloneMessage(message, conversation.id)
              : null,
        },
      }),
    });
  });

  await page.route(
    '**/api/v1/bots/bot-db/messages/*/process',
    async (route: Route) => {
      const parts = new URL(route.request().url()).pathname.split('/');
      const messageId = Number(parts[parts.length - 2]);
      processCalls.push(messageId);

      for (const conversation of conversations.values()) {
        const message = conversation.messages.find(
          (item) => item.id === messageId,
        );
        if (message) {
          message.status = 'processed';
          break;
        }
      }

      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          code: 0,
          msg: 'ok',
          data: null,
        }),
      });
    },
  );

  await page.route(
    '**/api/v1/bots/bot-db/messages/*/skip',
    async (route: Route) => {
      const parts = new URL(route.request().url()).pathname.split('/');
      const messageId = Number(parts[parts.length - 2]);
      skipCalls.push(messageId);

      for (const conversation of conversations.values()) {
        const message = conversation.messages.find(
          (item) => item.id === messageId,
        );
        if (message) {
          message.status = 'skipped';
          break;
        }
      }

      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          code: 0,
          msg: 'ok',
          data: null,
        }),
      });
    },
  );

  await page.route('**/api/v1/bots/bot-db/messages/*', async (route: Route) => {
    if (route.request().method() !== 'DELETE') {
      await route.fallback();
      return;
    }

    const parts = new URL(route.request().url()).pathname.split('/');
    const messageId = Number(parts[parts.length - 1]);
    deleteCalls.push(messageId);

    for (const conversation of conversations.values()) {
      const message = conversation.messages.find(
        (item) => item.id === messageId,
      );
      if (message) {
        message.deleted = true;
        break;
      }
    }

    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        code: 0,
        msg: 'ok',
        data: null,
      }),
    });
  });

  await page.route(
    '**/api/v1/bots/bot-db/messages/batch-process',
    async (route: Route) => {
      const payload = JSON.parse(route.request().postData() || '{}') as {
        message_ids?: string[];
      };
      const messageIds = (payload.message_ids ?? []).map((item) =>
        Number(item),
      );
      batchProcessCalls.push(messageIds);

      for (const conversation of conversations.values()) {
        for (const message of conversation.messages) {
          if (messageIds.includes(message.id)) {
            message.status = 'processed';
          }
        }
      }

      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          code: 0,
          msg: 'ok',
          data: {
            messages: [],
            succeeded: messageIds.length,
            failed: 0,
          },
        }),
      });
    },
  );

  await page.route(
    '**/api/v1/bots/bot-db/messages/batch-skip',
    async (route: Route) => {
      const payload = JSON.parse(route.request().postData() || '{}') as {
        message_ids?: string[];
      };
      const messageIds = (payload.message_ids ?? []).map((item) =>
        Number(item),
      );
      batchSkipCalls.push(messageIds);

      for (const conversation of conversations.values()) {
        for (const message of conversation.messages) {
          if (messageIds.includes(message.id)) {
            message.status = 'skipped';
          }
        }
      }

      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          code: 0,
          msg: 'ok',
          data: {
            messages: [],
            succeeded: messageIds.length,
            failed: 0,
          },
        }),
      });
    },
  );

  await page.route(
    '**/api/v1/bots/bot-db/messages/batch-delete',
    async (route: Route) => {
      const payload = JSON.parse(route.request().postData() || '{}') as {
        message_ids?: string[];
      };
      const messageIds = (payload.message_ids ?? []).map((item) =>
        Number(item),
      );
      batchDeleteCalls.push(messageIds);

      for (const conversation of conversations.values()) {
        for (const message of conversation.messages) {
          if (messageIds.includes(message.id)) {
            message.deleted = true;
          }
        }
      }

      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          code: 0,
          msg: 'ok',
          data: {
            messages: [],
            succeeded: messageIds.length,
            failed: 0,
          },
        }),
      });
    },
  );

  await page.exposeFunction('__botDatabaseMetrics', () => ({
    generateCalls,
    processCalls,
    skipCalls,
    deleteCalls,
    batchProcessCalls,
    batchSkipCalls,
    batchDeleteCalls,
  }));
}

async function getBotDatabaseMetrics(page: Page): Promise<MockMetrics> {
  return page.evaluate(async () => {
    const metrics = (
      window as Window & {
        __botDatabaseMetrics?: () => Promise<MockMetrics>;
      }
    ).__botDatabaseMetrics;
    return metrics
      ? metrics()
      : {
          generateCalls: [],
          processCalls: [],
          skipCalls: [],
          deleteCalls: [],
          batchProcessCalls: [],
          batchSkipCalls: [],
          batchDeleteCalls: [],
      };
  });
}

async function emitDatabaseMessageUpdated(
  page: Page,
  conversationId: number,
  messageId: number,
) {
  await page.evaluate(
    ({ conversationId, messageId }) => {
      (
        window as Window & {
          __emitBotDatabaseEvent?: (type: string, payload: unknown) => void;
        }
      ).__emitBotDatabaseEvent?.('database-message-updated', {
        type: 'database-message-updated',
        conversation_id: conversationId,
        message_id: messageId,
      });
    },
    { conversationId, messageId },
  );
}

async function triggerSmartReply(page: Page) {
  await page.getByRole('button', { name: 'AI actions' }).click();
  await page
    .locator('[data-radix-popper-content-wrapper]')
    .getByRole('button')
    .first()
    .click();
}

test('generate-draft keeps loading only until delayed success then fills composer', async ({
  page,
}) => {
  await installDatabaseBotSessionMocks(page, {
    generateDraftByMessageId: {
      1001: {
        delayMs: 1_200,
      },
    },
  });

  await page.goto('/home/bots?id=bot-db&tab=sessions');
  await page.getByRole('button', { name: /Customer Alpha/ }).first().click();

  const textarea = page.getByRole('textbox', { name: 'Composer draft' });

  await triggerSmartReply(page);

  await expect(page.getByText('草稿生成中...')).toBeVisible();
  await expect(textarea).toHaveValue('Draft for message 1001');
  await expect(page.getByText('草稿生成中...')).toHaveCount(0);
});

test('generate-draft restores composer from refreshed messages without SSE', async ({
  page,
}) => {
  await installDatabaseBotSessionMocks(page, {
    generateDraftByMessageId: {
      1001: {
        responseIncludesDraft: false,
        persistedDraftContent: 'Draft recovered from refreshed messages',
        dispatchSseEvent: false,
      },
    },
  });

  await page.goto('/home/bots?id=bot-db&tab=sessions');
  await page.getByRole('button', { name: /Customer Alpha/ }).first().click();

  const textarea = page.getByRole('textbox', { name: 'Composer draft' });
  await triggerSmartReply(page);

  await expect(textarea).toHaveValue('Draft recovered from refreshed messages');
  await expect(page.getByText('草稿生成中...')).toHaveCount(0);
});

test('generate-draft restores composer from already_succeeded response draft', async ({
  page,
}) => {
  await installDatabaseBotSessionMocks(page, {
    extraAlphaMessages: [
      {
        id: 1010,
        sender_id: 'customer-1',
        sender_name: 'Alice',
        content: 'Need the previous draft again',
        sent_at: iso(14),
        status: 'pending',
      },
    ],
    generateDraftByMessageId: {
      1010: {
        responseStatus: 'already_succeeded',
        responseDraftContent: 'Existing draft returned directly',
        persistedDraftContent: 'Existing draft returned directly',
      },
    },
  });

  await page.goto('/home/bots?id=bot-db&tab=sessions');
  await page.getByRole('button', { name: /Customer Alpha/ }).first().click();

  const textarea = page.getByRole('textbox', { name: 'Composer draft' });
  await triggerSmartReply(page);

  await expect(textarea).toHaveValue('Existing draft returned directly');
});

test('generate-draft does not write into another conversation during switch and restores after switching back', async ({
  page,
}) => {
  await installDatabaseBotSessionMocks(page, {
    generateDraftByMessageId: {
      1001: {
        delayMs: 1_000,
        persistedDraftContent: 'Draft stays with alpha conversation',
      },
    },
  });

  await page.goto('/home/bots?id=bot-db&tab=sessions');
  await page.getByRole('button', { name: /Customer Alpha/ }).first().click();

  const textarea = page.getByRole('textbox', { name: 'Composer draft' });
  await triggerSmartReply(page);

  await page.getByText('Customer Beta').click();
  await expect(textarea).toHaveValue('Saved draft for beta conversation');

  await page.getByText('Customer Alpha').click();
  await expect(textarea).toHaveValue('Draft stays with alpha conversation');
  await expect(page.getByText('草稿生成中...')).toHaveCount(0);
});

test('sse update does not override user edited composer text', async ({ page }) => {
  await installDatabaseBotSessionMocks(page);

  await page.goto('/home/bots?id=bot-db&tab=sessions');
  await page.getByRole('button', { name: /Customer Beta/ }).first().click();

  const textarea = page.getByRole('textbox', { name: 'Composer draft' });
  await textarea.fill('Local user edit should stay');

  await emitDatabaseMessageUpdated(page, 202, 2001);

  await expect(textarea).toHaveValue('Local user edit should stay');
});

test('database bot keeps chat mode as the default reading experience', async ({
  page,
}) => {
  await installDatabaseBotSessionMocks(page);

  await page.goto('/home/bots?id=bot-db&tab=sessions');

  const alphaConversation = page
    .getByRole('button', { name: /Customer Alpha/ })
    .first();
  await expect(alphaConversation).toBeVisible();
  await alphaConversation.click();

  await expect(page.getByText('Reply Draft')).toHaveCount(0);
  await expect(page.getByText('AI 鎿嶄綔')).toHaveCount(0);
  await expect(page.getByRole('button', { name: '批量操作' })).toBeVisible();
  await expect(page.getByLabel('选择消息 1001')).toHaveCount(0);
  await expect(page.getByText('已选择 0 条')).toHaveCount(0);

  const textarea = page.getByRole('textbox', { name: 'Composer draft' });
  await expect(textarea).toBeVisible();
  await expect(textarea).toHaveValue('');

  await expect(page.getByText('Alice').first()).toBeVisible();
  await expect(
    page.getByText('I will follow up shortly.').last(),
  ).toBeVisible();

  await page.getByRole('button', { name: 'AI actions' }).click();
  await page.getByRole('button', { name: '智能回复' }).click();

  await expect(textarea).toHaveValue('Draft for message 1001');
  await expect(page.getByText(/草稿 v2/i)).toBeVisible();
  await expect(page.getByRole('button', { name: '复制' })).toBeVisible();
  await expect(page.getByRole('button', { name: '保存' })).toBeVisible();
  await expect(page.getByRole('button', { name: '取消' })).toBeVisible();

  const metrics = await getBotDatabaseMetrics(page);
  expect(metrics.generateCalls).toEqual([1001]);

  await page.getByText('Customer Beta').click();
  await expect(textarea).toHaveValue('Saved draft for beta conversation');

  const eventSourceCreations = await page.evaluate(
    () =>
      (
        window as Window & {
          __botDatabaseEventSourceCreations?: number;
        }
      ).__botDatabaseEventSourceCreations ?? 0,
  );
  expect(eventSourceCreations).toBe(1);
});

test('database bot keeps single-message actions inside a more menu', async ({
  page,
}) => {
  await installDatabaseBotSessionMocks(page);

  await page.goto('/home/bots?id=bot-db&tab=sessions');

  await page
    .getByRole('button', { name: /Customer Alpha/ })
    .first()
    .click();
  await page.getByRole('button', { name: '消息 1002 更多操作' }).click();
  await page.getByRole('menuitem', { name: '设为当前消息' }).click();
  await expect(page.getByText('当前选择 #1002')).toBeVisible();

  await page.getByRole('button', { name: 'AI actions' }).click();
  await page.getByRole('button', { name: '智能回复' }).click();

  await page.getByRole('button', { name: '消息 1001 更多操作' }).click();
  await page.getByRole('menuitem', { name: '标记已处理' }).click();

  const metrics = await getBotDatabaseMetrics(page);
  expect(metrics.generateCalls).toEqual([1002]);
  expect(metrics.processCalls).toEqual([1001]);
});

test('database bot enters batch mode explicitly and clears selection on exit', async ({
  page,
}) => {
  await installDatabaseBotSessionMocks(page);

  await page.goto('/home/bots?id=bot-db&tab=sessions');

  await page
    .getByRole('button', { name: /Customer Alpha/ })
    .first()
    .click();

  await expect(page.getByLabel('选择消息 1001')).toHaveCount(0);

  await page.getByRole('button', { name: '批量操作' }).click();
  await expect(page.getByLabel('选择消息 1001')).toBeVisible();
  await expect(page.getByLabel('选择消息 1002')).toBeVisible();
  await expect(page.getByLabel('选择消息 1003')).toHaveCount(0);

  await page.getByRole('button', { name: '全选' }).click();
  await expect(page.getByText('已选择 2 条')).toBeVisible();

  await page.getByRole('button', { name: '跳过' }).click();

  const metrics = await getBotDatabaseMetrics(page);
  expect(metrics.batchSkipCalls).toEqual([[1001, 1002]]);

  await page.getByRole('button', { name: '退出批量模式' }).last().click();
  await expect(page.getByLabel('选择消息 1001')).toHaveCount(0);
  await expect(page.getByText('已选择 2 条')).toHaveCount(0);
});
