import { expect, test } from '@playwright/test';

import { installLangBotApiMocks } from './fixtures/langbot-api';

async function installDatabaseModeApiMocks(
  page: Parameters<typeof installLangBotApiMocks>[0],
) {
  await installLangBotApiMocks(page, {
    authenticated: true,
    bots: [
      {
        uuid: 'database-mode-bot',
        name: 'Database Mode Bot',
        adapter: 'wxwork_database',
      },
    ],
  });
}

test('database mode refreshes after SSE ready and coalesces invalidation', async ({
  page,
}) => {
  await installDatabaseModeApiMocks(page);

  await page.addInitScript(() => {
    class FakeEventSource {
      static instances: FakeEventSource[] = [];
      static CONNECTING = 0;
      static OPEN = 1;
      static CLOSED = 2;
      url: string;
      withCredentials: boolean;
      onopen: ((event: Event) => void) | null = null;
      onerror: ((event: Event) => void) | null = null;
      listeners = new Map<string, Array<(event: MessageEvent) => void>>();
      readyState = FakeEventSource.CONNECTING;

      constructor(url: string, init?: EventSourceInit) {
        this.url = url;
        this.withCredentials = Boolean(init?.withCredentials);
        FakeEventSource.instances.push(this);
        (window as Window & { __fakeEventSourceInstances?: FakeEventSource[] }).__fakeEventSourceInstances =
          FakeEventSource.instances;
      }

      addEventListener(type: string, listener: (event: MessageEvent) => void) {
        const next = this.listeners.get(type) ?? [];
        next.push(listener);
        this.listeners.set(type, next);
      }

      close() {
        this.readyState = FakeEventSource.CLOSED;
      }

      emit(type: string, data: unknown) {
        for (const listener of this.listeners.get(type) ?? []) {
          listener(new MessageEvent(type, { data: JSON.stringify(data) }));
        }
      }
    }

    (window as Window & { EventSource: typeof EventSource }).EventSource =
      FakeEventSource as unknown as typeof EventSource;
  });

  let handshakeCount = 0;
  let conversationsCount = 0;
  let conversationRequests: number[] = [];
  let sessionCompletedAt = 0;

  await page.route('**/api/v1/local-connectors/wxwork-local/status', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        code: 0,
        msg: 'ok',
        data: {
          connector: {
            connector_id: 'wxwork-local',
            name: 'WeCom Local Connector',
            managed_by: 'builtin',
            expected_tool_count: 5,
            status: 'running',
            tool_count: 5,
            updated_at: Date.now(),
            worker: { owned: true, port: 5681, started_at: null },
            monitor: {
              enabled: true,
              owned: true,
              running_status: 'running',
              warmup_completed: true,
              outbox_pending: 0,
            },
          },
        },
      }),
    });
  });

  await page.route('**/api/v1/database-mode/events/session', async (route) => {
    handshakeCount += 1;
    expect(route.request().url()).toBe('http://127.0.0.1:4173/api/v1/database-mode/events/session');
    sessionCompletedAt = Date.now();
    await route.fulfill({
      status: 204,
      headers: {
        'Cache-Control': 'no-store',
        'Set-Cookie':
          'langbot_dbmode_sse=test; Path=/api/v1/database-mode/events; HttpOnly; SameSite=Strict',
      },
    });
  });

  await page.route('**/api/v1/bots/database-mode-bot/conversations', async (route) => {
    conversationsCount += 1;
    conversationRequests.push(Date.now());
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        code: 0,
        msg: 'ok',
        data: {
          conversations: [
            {
              id: 1,
              source: 'wxwork',
              conversation_name: 'Customer A',
              conversation_type: 'direct',
              last_message_at: '2026-06-24T10:00:00+00:00',
              pending_count: 1,
              failed_count: 0,
              latest_customer: 'Customer A',
              latest_message_summary: 'Need pricing details',
            },
          ],
          total: 1,
          page: 1,
          page_size: 100,
        },
      }),
    });
  });

  await page.route('**/api/v1/bots/database-mode-bot/conversations/1', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        code: 0,
        msg: 'ok',
        data: {
          conversation: {
            id: 1,
            connector_id: 'wxwork-local',
            source: 'wxwork',
            external_conversation_id: 'S:100_200',
            conversation_name: 'Customer A',
            conversation_type: 'direct',
            last_message_at: '2026-06-24T10:00:00+00:00',
            stats: {
              pending: 1,
              processing: 0,
              draft_ready: 0,
              failed: 0,
              processed: 0,
              skipped: 0,
              total: 1,
            },
            latest_customer: 'Customer A',
          },
        },
      }),
    });
  });

  await page.route('**/api/v1/bots/database-mode-bot/conversations/1/messages**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        code: 0,
        msg: 'ok',
        data: {
          messages: [
            {
              id: 7,
              event_id: 'evt-1',
              message_key: 'wxwork:key-1',
              conversation_id: 1,
              sender_id: '200',
              sender_name: 'Customer A',
              content: 'Need pricing details',
              content_preview: 'Need pricing details',
              message_type: 'text',
              sent_at: '2026-06-24T10:00:00+00:00',
              observed_at: '2026-06-24T10:00:02+00:00',
              status: 'pending',
              attempt_count: 0,
            },
          ],
          total: 1,
          page: 1,
          page_size: 200,
          stats: {
            pending: 1,
            processing: 0,
            draft_ready: 0,
            failed: 0,
            processed: 0,
            skipped: 0,
            total: 1,
          },
        },
      }),
    });
  });

  await page.goto('/home/database-mode');

  await expect(page).toHaveURL(/\/home\/bots\?id=database-mode-bot&tab=sessions$/);
  await expect.poll(() => handshakeCount).toBe(1);
  await expect
    .poll(async () =>
      page.evaluate(() => {
        const source = (
          window as Window & {
            __fakeEventSourceInstances?: Array<{
              url: string;
              withCredentials: boolean;
            }>;
          }
        ).__fakeEventSourceInstances?.[0];

        return source
          ? {
              url: source.url,
              withCredentials: source.withCredentials,
            }
          : null;
      }),
    )
    .toEqual({
      url: '/api/v1/database-mode/events',
      withCredentials: true,
    });

  await expect
    .poll(async () =>
      page.evaluate(
        () =>
          (
            window as Window & {
              __databaseModeEventLifecycleLogs?: Array<{ stage: string }>;
            }
          ).__databaseModeEventLifecycleLogs?.length ?? 0,
      ),
    )
    .toBeGreaterThan(0);

  const lifecycleLogs = await page.evaluate(
    () =>
      (
        window as Window & {
          __databaseModeEventLifecycleLogs?: Array<{
            stage: string;
            generation: number;
            source_id: string;
            elapsed_ms: number;
            close_reason: string | null;
          }>;
        }
      ).__databaseModeEventLifecycleLogs ?? [],
  );

  const latestGeneration = Math.max(...lifecycleLogs.map((entry) => entry.generation));
  const currentGenerationLogs = lifecycleLogs.filter((entry) => entry.generation === latestGeneration);
  const handshakeCompletedLog = currentGenerationLogs.find((entry) => entry.stage === 'handshake_completed');
  const sourceCreatedLog = currentGenerationLogs.find((entry) => entry.stage === 'event_source_created');
  expect(handshakeCompletedLog).toBeDefined();
  expect(sourceCreatedLog).toBeDefined();
  expect(sourceCreatedLog!.generation).toBe(handshakeCompletedLog!.generation);
  expect(sourceCreatedLog!.source_id).toBe(handshakeCompletedLog!.source_id);
  expect(sourceCreatedLog!.elapsed_ms - handshakeCompletedLog!.elapsed_ms).toBeLessThanOrEqual(500);
  expect(sessionCompletedAt).toBeGreaterThan(0);
  expect(currentGenerationLogs.filter((entry) => entry.stage === 'handshake_completed')).toHaveLength(1);
  expect(currentGenerationLogs.filter((entry) => entry.stage === 'event_source_created')).toHaveLength(1);

  await page.evaluate(() => {
    const source = (window as Window & { __fakeEventSourceInstances?: Array<{ onopen?: ((event: Event) => void) | null; emit: (type: string, data: unknown) => void }> }).__fakeEventSourceInstances?.[0];
    if (source) {
      (source as { readyState?: number }).readyState = 1;
    }
    source?.onopen?.(new Event('open'));
    source?.emit('ready', { type: 'ready' });
    source?.emit('database-mode-invalidated', { type: 'database-mode-invalidated' });
  });

  await expect.poll(() => conversationsCount).toBeGreaterThan(1);
  expect(conversationRequests[1] - conversationRequests[0]).toBeLessThan(1_500);
});

test('database mode creates one SSE stream immediately after session handshake and keeps it stable', async ({
  page,
}) => {
  test.setTimeout(45_000);
  await installDatabaseModeApiMocks(page);

  await page.addInitScript(() => {
    class FakeEventSource {
      static instances: FakeEventSource[] = [];
      static CONNECTING = 0;
      static OPEN = 1;
      static CLOSED = 2;
      url: string;
      withCredentials: boolean;
      onopen: ((event: Event) => void) | null = null;
      onerror: ((event: Event) => void) | null = null;
      listeners = new Map<string, Array<(event: MessageEvent) => void>>();
      readyState = FakeEventSource.CONNECTING;

      constructor(url: string, init?: EventSourceInit) {
        this.url = url;
        this.withCredentials = Boolean(init?.withCredentials);
        FakeEventSource.instances.push(this);
        (
          window as Window & {
            __fakeEventSourceInstances?: FakeEventSource[];
          }
        ).__fakeEventSourceInstances = FakeEventSource.instances;
      }

      addEventListener(type: string, listener: (event: MessageEvent) => void) {
        const next = this.listeners.get(type) ?? [];
        next.push(listener);
        this.listeners.set(type, next);
      }

      close() {
        this.readyState = FakeEventSource.CLOSED;
      }

      emit(type: string, data: unknown) {
        for (const listener of this.listeners.get(type) ?? []) {
          listener(new MessageEvent(type, { data: JSON.stringify(data) }));
        }
      }
    }

    (window as Window & { EventSource: typeof EventSource }).EventSource =
      FakeEventSource as unknown as typeof EventSource;
  });

  const sessionRequestTimes: number[] = [];
  const conversationsRequestTimes: number[] = [];
  const conversationRequestTimes: number[] = [];
  const messagesRequestTimes: number[] = [];

  await page.route('**/api/v1/local-connectors/wxwork-local/status', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        code: 0,
        msg: 'ok',
        data: {
          connector: {
            connector_id: 'wxwork-local',
            name: 'WeCom Local Connector',
            managed_by: 'builtin',
            expected_tool_count: 5,
            status: 'running',
            tool_count: 5,
            updated_at: Date.now(),
            worker: { owned: true, port: 5681, started_at: null },
            monitor: {
              enabled: true,
              owned: true,
              running_status: 'running',
              warmup_completed: true,
              outbox_pending: 0,
            },
          },
        },
      }),
    });
  });

  await page.route('**/api/v1/database-mode/events/session', async (route) => {
    sessionRequestTimes.push(Date.now());
    await route.fulfill({
      status: 204,
      headers: {
        'Cache-Control': 'no-store',
        'Set-Cookie':
          'langbot_dbmode_sse=test; Path=/api/v1/database-mode/events; HttpOnly; SameSite=Strict',
      },
    });
  });

  await page.route('**/api/v1/bots/database-mode-bot/conversations', async (route) => {
    conversationsRequestTimes.push(Date.now());
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        code: 0,
        msg: 'ok',
        data: {
          conversations: [
            {
              id: 1,
              source: 'wxwork',
              conversation_name: 'Customer A',
              conversation_type: 'direct',
              last_message_at: '2026-06-24T10:00:00+00:00',
              pending_count: 1,
              failed_count: 0,
              latest_customer: 'Customer A',
              latest_message_summary: 'Need pricing details',
            },
          ],
          total: 1,
          page: 1,
          page_size: 100,
        },
      }),
    });
  });

  await page.route('**/api/v1/bots/database-mode-bot/conversations/1', async (route) => {
    conversationRequestTimes.push(Date.now());
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        code: 0,
        msg: 'ok',
        data: {
          conversation: {
            id: 1,
            connector_id: 'wxwork-local',
            source: 'wxwork',
            external_conversation_id: 'S:100_200',
            conversation_name: 'Customer A',
            conversation_type: 'direct',
            last_message_at: '2026-06-24T10:00:00+00:00',
            stats: {
              pending: 1,
              processing: 0,
              draft_ready: 0,
              failed: 0,
              processed: 0,
              skipped: 0,
              total: 1,
            },
            latest_customer: 'Customer A',
          },
        },
      }),
    });
  });

  await page.route('**/api/v1/bots/database-mode-bot/conversations/1/messages**', async (route) => {
    messagesRequestTimes.push(Date.now());
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        code: 0,
        msg: 'ok',
        data: {
          messages: [
            {
              id: 7,
              event_id: 'evt-1',
              message_key: 'wxwork:key-1',
              conversation_id: 1,
              sender_id: '200',
              sender_name: 'Customer A',
              content: 'Need pricing details',
              content_preview: 'Need pricing details',
              message_type: 'text',
              sent_at: '2026-06-24T10:00:00+00:00',
              observed_at: '2026-06-24T10:00:02+00:00',
              status: 'pending',
              attempt_count: 0,
            },
          ],
          total: 1,
          page: 1,
          page_size: 200,
          stats: {
            pending: 1,
            processing: 0,
            draft_ready: 0,
            failed: 0,
            processed: 0,
            skipped: 0,
            total: 1,
          },
        },
      }),
    });
  });

  await page.goto('/home/database-mode');
  await expect(page).toHaveURL(/\/home\/bots\?id=database-mode-bot&tab=sessions$/);
  await expect.poll(() => sessionRequestTimes.length).toBe(1);
  await expect
    .poll(async () =>
      page.evaluate(
        () =>
          (
            window as Window & {
              __fakeEventSourceInstances?: Array<{ readyState: number; onopen?: ((event: Event) => void) | null }>;
            }
          ).__fakeEventSourceInstances?.length ?? 0,
      ),
    )
    .toBe(1);

  await page.evaluate(() => {
    const source = (
      window as Window & {
        __fakeEventSourceInstances?: Array<{
          readyState: number;
          onopen?: ((event: Event) => void) | null;
        }>;
      }
    ).__fakeEventSourceInstances?.[0];
    if (!source) {
      return;
    }

    source.readyState = 1;
    source.onopen?.(new Event('open'));
  });

  await expect
    .poll(async () =>
      page.evaluate(
        () =>
          (
            window as Window & {
              __databaseModeEventLifecycleLogs?: Array<{
                stage: string;
                generation: number;
                source_id: string;
                elapsed_ms: number;
                close_reason: string | null;
              }>;
            }
          ).__databaseModeEventLifecycleLogs ?? [],
      ),
    )
    .toContainEqual(
      expect.objectContaining({
        stage: 'event_source_created',
      }),
    );

  const lifecycleLogs = await page.evaluate(
    () =>
      (
        window as Window & {
          __databaseModeEventLifecycleLogs?: Array<{
            stage: string;
            generation: number;
            source_id: string;
            elapsed_ms: number;
            close_reason: string | null;
          }>;
        }
      ).__databaseModeEventLifecycleLogs ?? [],
  );

  const latestGeneration = Math.max(...lifecycleLogs.map((entry) => entry.generation));
  const currentGenerationLogs = lifecycleLogs.filter((entry) => entry.generation === latestGeneration);
  const handshakeStarted = currentGenerationLogs.find((entry) => entry.stage === 'handshake_started');
  const handshakeCompleted = currentGenerationLogs.find((entry) => entry.stage === 'handshake_completed');
  const sourceCreated = currentGenerationLogs.find((entry) => entry.stage === 'event_source_created');
  expect(handshakeStarted).toBeDefined();
  expect(handshakeCompleted).toBeDefined();
  expect(sourceCreated).toBeDefined();
  expect(handshakeCompleted!.generation).toBe(handshakeStarted!.generation);
  expect(sourceCreated!.generation).toBe(handshakeStarted!.generation);
  expect(handshakeCompleted!.source_id).toBe(handshakeStarted!.source_id);
  expect(sourceCreated!.source_id).toBe(handshakeStarted!.source_id);
  expect(sourceCreated!.elapsed_ms - handshakeCompleted!.elapsed_ms).toBeLessThanOrEqual(500);
  expect(currentGenerationLogs.filter((entry) => entry.stage === 'handshake_completed')).toHaveLength(1);
  expect(currentGenerationLogs.filter((entry) => entry.stage === 'event_source_created')).toHaveLength(1);

  await expect
    .poll(async () =>
      page.evaluate(
        () =>
          (
            window as Window & {
              __fakeEventSourceInstances?: Array<{ url: string; withCredentials: boolean }>;
            }
          ).__fakeEventSourceInstances?.length ?? 0,
      ),
    )
    .toBeGreaterThan(0);

  await page.evaluate(() => {
    const source = (
      window as Window & {
        __fakeEventSourceInstances?: Array<{
          readyState: number;
          emit: (type: string, data: unknown) => void;
        }>;
      }
    ).__fakeEventSourceInstances?.[0];
    if (!source) {
      return;
    }

    source.emit('ready', { type: 'ready' });
  });

  await expect
    .poll(async () =>
      page.evaluate(
        () =>
          (
            window as Window & {
              __databaseModeEventLifecycleLogs?: Array<{ stage: string }>;
            }
          ).__databaseModeEventLifecycleLogs?.filter((entry) => entry.stage === 'ready_received').length ?? 0,
      ),
    )
    .toBe(1);

  await expect.poll(() => conversationsRequestTimes.length).toBeGreaterThan(1);
  await expect.poll(() => messagesRequestTimes.length).toBeGreaterThan(1);

  const baseline = {
    conversations: conversationsRequestTimes.length,
    messages: messagesRequestTimes.length,
  };

  await page.evaluate(() => {
    const source = (
      window as Window & {
        __fakeEventSourceInstances?: Array<{
          emit: (type: string, data: unknown) => void;
        }>;
      }
    ).__fakeEventSourceInstances?.[0];
    source?.emit('database-message-created', {
      type: 'database-message-created',
      event_id: 'evt-business-1',
    });
  });

  await expect.poll(() => conversationsRequestTimes.length).toBeGreaterThan(baseline.conversations);
  await expect.poll(() => messagesRequestTimes.length).toBeGreaterThan(baseline.messages);

  await page.waitForTimeout(30_000);

  expect(sessionRequestTimes).toHaveLength(1);
  await expect
    .poll(async () =>
      page.evaluate(
        () =>
          (
            window as Window & {
              __fakeEventSourceInstances?: Array<unknown>;
            }
          ).__fakeEventSourceInstances?.length ?? 0,
      ),
    )
    .toBe(1);
});

test('database mode stays idle after SSE ready when no new events arrive', async ({
  page,
}) => {
  await installDatabaseModeApiMocks(page);

  await page.addInitScript(() => {
    class FakeEventSource {
      static instances: FakeEventSource[] = [];
      static CONNECTING = 0;
      static OPEN = 1;
      static CLOSED = 2;
      url: string;
      withCredentials: boolean;
      onopen: ((event: Event) => void) | null = null;
      onerror: ((event: Event) => void) | null = null;
      listeners = new Map<string, Array<(event: MessageEvent) => void>>();
      readyState = FakeEventSource.CONNECTING;

      constructor(url: string, init?: EventSourceInit) {
        this.url = url;
        this.withCredentials = Boolean(init?.withCredentials);
        FakeEventSource.instances.push(this);
        (window as Window & { __fakeEventSourceInstances?: FakeEventSource[] }).__fakeEventSourceInstances =
          FakeEventSource.instances;
      }

      addEventListener(type: string, listener: (event: MessageEvent) => void) {
        const next = this.listeners.get(type) ?? [];
        next.push(listener);
        this.listeners.set(type, next);
      }

      close() {
        this.readyState = FakeEventSource.CLOSED;
      }

      emit(type: string, data: unknown) {
        for (const listener of this.listeners.get(type) ?? []) {
          listener(new MessageEvent(type, { data: JSON.stringify(data) }));
        }
      }
    }

    (window as Window & { EventSource: typeof EventSource }).EventSource =
      FakeEventSource as unknown as typeof EventSource;
  });

  let handshakeCount = 0;
  const requestCounts = {
    conversations: 0,
    conversation: 0,
    messages: 0,
  };

  await page.route('**/api/v1/local-connectors/wxwork-local/status', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        code: 0,
        msg: 'ok',
        data: {
          connector: {
            connector_id: 'wxwork-local',
            name: 'WeCom Local Connector',
            managed_by: 'builtin',
            expected_tool_count: 5,
            status: 'running',
            tool_count: 5,
            updated_at: Date.now(),
            worker: { owned: true, port: 5681, started_at: null },
            monitor: {
              enabled: true,
              owned: true,
              running_status: 'running',
              warmup_completed: true,
              outbox_pending: 0,
            },
          },
        },
      }),
    });
  });

  await page.route('**/api/v1/database-mode/events/session', async (route) => {
    handshakeCount += 1;
    await route.fulfill({
      status: 204,
      headers: {
        'Cache-Control': 'no-store',
        'Set-Cookie':
          'langbot_dbmode_sse=test; Path=/api/v1/database-mode/events; HttpOnly; SameSite=Strict',
      },
    });
  });

  await page.route('**/api/v1/bots/database-mode-bot/**', async (route) => {
    const pathname = new URL(route.request().url()).pathname;

    if (pathname === '/api/v1/bots/database-mode-bot/conversations') {
      requestCounts.conversations += 1;
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          code: 0,
          msg: 'ok',
          data: {
            conversations: [
              {
                id: 1,
                source: 'wxwork',
                conversation_name: 'Customer A',
                conversation_type: 'direct',
                last_message_at: '2026-06-24T10:00:00+00:00',
                pending_count: 1,
                failed_count: 0,
                latest_customer: 'Customer A',
                latest_message_summary: 'Need pricing details',
              },
            ],
            total: 1,
            page: 1,
            page_size: 100,
          },
        }),
      });
      return;
    }

    if (pathname === '/api/v1/bots/database-mode-bot/conversations/1') {
      requestCounts.conversation += 1;
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          code: 0,
          msg: 'ok',
          data: {
            conversation: {
              id: 1,
              connector_id: 'wxwork-local',
              source: 'wxwork',
              external_conversation_id: 'S:100_200',
              conversation_name: 'Customer A',
              conversation_type: 'direct',
              last_message_at: '2026-06-24T10:00:00+00:00',
              stats: {
                pending: 1,
                processing: 0,
                draft_ready: 0,
                failed: 0,
                processed: 0,
                skipped: 0,
                total: 1,
              },
              latest_customer: 'Customer A',
            },
          },
        }),
      });
      return;
    }

    if (pathname === '/api/v1/bots/database-mode-bot/conversations/1/messages') {
      requestCounts.messages += 1;
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          code: 0,
          msg: 'ok',
          data: {
            messages: [
              {
                id: 7,
                event_id: 'evt-1',
                message_key: 'wxwork:key-1',
                conversation_id: 1,
                sender_id: '200',
                sender_name: 'Customer A',
                content: 'Need pricing details',
                content_preview: 'Need pricing details',
                message_type: 'text',
                sent_at: '2026-06-24T10:00:00+00:00',
                observed_at: '2026-06-24T10:00:02+00:00',
                status: 'pending',
                attempt_count: 0,
              },
            ],
            total: 1,
            page: 1,
            page_size: 200,
            stats: {
              pending: 1,
              processing: 0,
              draft_ready: 0,
              failed: 0,
              processed: 0,
              skipped: 0,
              total: 1,
            },
          },
        }),
      });
      return;
    }

    await route.fulfill({
      status: 404,
      contentType: 'application/json',
      body: JSON.stringify({ code: -1, msg: 'unexpected route', data: null }),
    });
  });

  await page.goto('/home/database-mode');
  await expect(page).toHaveURL(/\/home\/bots\?id=database-mode-bot&tab=sessions$/);
  await expect.poll(() => handshakeCount).toBe(1);
  await expect
    .poll(async () =>
      page.evaluate(
        () =>
          (
            window as Window & {
              __fakeEventSourceInstances?: Array<{
                readyState: number;
                onopen?: ((event: Event) => void) | null;
              }>;
            }
          ).__fakeEventSourceInstances?.length ?? 0,
      ),
    )
    .toBe(1);

  await page.evaluate(() => {
    const source = (window as Window & { __fakeEventSourceInstances?: Array<{ onopen?: ((event: Event) => void) | null; emit: (type: string, data: unknown) => void }> }).__fakeEventSourceInstances?.[0];
    if (source) {
      (source as { readyState?: number }).readyState = 1;
    }
    source?.onopen?.(new Event('open'));
    source?.emit('ready', { type: 'ready' });
  });

  await expect.poll(() => requestCounts.conversations).toBeGreaterThan(1);
  await expect.poll(() => requestCounts.messages).toBeGreaterThan(1);

  await page.waitForTimeout(2_000);
  const baseline = { ...requestCounts };

  await page.waitForTimeout(5_000);

  expect(requestCounts.conversations - baseline.conversations).toBe(0);
  expect(requestCounts.messages - baseline.messages).toBe(0);
});

test('database mode handles ready only once per EventSource connection', async ({
  page,
}) => {
  await installDatabaseModeApiMocks(page);

  await page.addInitScript(() => {
    class FakeEventSource {
      static instances: FakeEventSource[] = [];
      static CONNECTING = 0;
      static OPEN = 1;
      static CLOSED = 2;
      url: string;
      withCredentials: boolean;
      onopen: ((event: Event) => void) | null = null;
      onerror: ((event: Event) => void) | null = null;
      listeners = new Map<string, Array<(event: MessageEvent) => void>>();
      readyState = FakeEventSource.CONNECTING;

      constructor(url: string, init?: EventSourceInit) {
        this.url = url;
        this.withCredentials = Boolean(init?.withCredentials);
        FakeEventSource.instances.push(this);
        (window as Window & { __fakeEventSourceInstances?: FakeEventSource[] }).__fakeEventSourceInstances =
          FakeEventSource.instances;
      }

      addEventListener(type: string, listener: (event: MessageEvent) => void) {
        const next = this.listeners.get(type) ?? [];
        next.push(listener);
        this.listeners.set(type, next);
      }

      close() {
        this.readyState = FakeEventSource.CLOSED;
      }

      emit(type: string, data: unknown) {
        for (const listener of this.listeners.get(type) ?? []) {
          listener(new MessageEvent(type, { data: JSON.stringify(data) }));
        }
      }
    }

    (window as Window & { EventSource: typeof EventSource }).EventSource =
      FakeEventSource as unknown as typeof EventSource;
  });

  const requestCounts = {
    conversations: 0,
    conversation: 0,
    messages: 0,
  };

  await page.route('**/api/v1/local-connectors/wxwork-local/status', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        code: 0,
        msg: 'ok',
        data: {
          connector: {
            connector_id: 'wxwork-local',
            name: 'WeCom Local Connector',
            managed_by: 'builtin',
            expected_tool_count: 5,
            status: 'running',
            tool_count: 5,
            updated_at: Date.now(),
            worker: { owned: true, port: 5681, started_at: null },
            monitor: {
              enabled: true,
              owned: true,
              running_status: 'running',
              warmup_completed: true,
              outbox_pending: 0,
            },
          },
        },
      }),
    });
  });

  await page.route('**/api/v1/database-mode/events/session', async (route) => {
    await route.fulfill({
      status: 204,
      headers: {
        'Cache-Control': 'no-store',
        'Set-Cookie':
          'langbot_dbmode_sse=test; Path=/api/v1/database-mode/events; HttpOnly; SameSite=Strict',
      },
    });
  });

  await page.route('**/api/v1/bots/database-mode-bot/**', async (route) => {
    const pathname = new URL(route.request().url()).pathname;

    if (pathname === '/api/v1/bots/database-mode-bot/conversations') {
      requestCounts.conversations += 1;
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          code: 0,
          msg: 'ok',
          data: {
            conversations: [
              {
                id: 1,
                source: 'wxwork',
                conversation_name: 'Customer A',
                conversation_type: 'direct',
                last_message_at: '2026-06-24T10:00:00+00:00',
                pending_count: 1,
                failed_count: 0,
                latest_customer: 'Customer A',
                latest_message_summary: 'Need pricing details',
              },
            ],
            total: 1,
            page: 1,
            page_size: 100,
          },
        }),
      });
      return;
    }

    if (pathname === '/api/v1/bots/database-mode-bot/conversations/1') {
      requestCounts.conversation += 1;
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          code: 0,
          msg: 'ok',
          data: {
            conversation: {
              id: 1,
              connector_id: 'wxwork-local',
              source: 'wxwork',
              external_conversation_id: 'S:100_200',
              conversation_name: 'Customer A',
              conversation_type: 'direct',
              last_message_at: '2026-06-24T10:00:00+00:00',
              stats: {
                pending: 1,
                processing: 0,
                draft_ready: 0,
                failed: 0,
                processed: 0,
                skipped: 0,
                total: 1,
              },
              latest_customer: 'Customer A',
            },
          },
        }),
      });
      return;
    }

    if (pathname === '/api/v1/bots/database-mode-bot/conversations/1/messages') {
      requestCounts.messages += 1;
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          code: 0,
          msg: 'ok',
          data: {
            messages: [
              {
                id: 7,
                event_id: 'evt-1',
                message_key: 'wxwork:key-1',
                conversation_id: 1,
                sender_id: '200',
                sender_name: 'Customer A',
                content: 'Need pricing details',
                content_preview: 'Need pricing details',
                message_type: 'text',
                sent_at: '2026-06-24T10:00:00+00:00',
                observed_at: '2026-06-24T10:00:02+00:00',
                status: 'pending',
                attempt_count: 0,
              },
            ],
            total: 1,
            page: 1,
            page_size: 200,
            stats: {
              pending: 1,
              processing: 0,
              draft_ready: 0,
              failed: 0,
              processed: 0,
              skipped: 0,
              total: 1,
            },
          },
        }),
      });
      return;
    }

    await route.fulfill({
      status: 404,
      contentType: 'application/json',
      body: JSON.stringify({ code: -1, msg: 'unexpected route', data: null }),
    });
  });

  await page.goto('/home/database-mode');
  await expect(page).toHaveURL(/\/home\/bots\?id=database-mode-bot&tab=sessions$/);
  await expect.poll(() => requestCounts.conversations).toBeGreaterThan(0);
  await expect.poll(() => requestCounts.messages).toBeGreaterThan(0);
  await expect
    .poll(async () =>
      page.evaluate(
        () =>
          (
            window as Window & {
              __fakeEventSourceInstances?: Array<{
                readyState: number;
                onopen?: ((event: Event) => void) | null;
              }>;
            }
          ).__fakeEventSourceInstances?.length ?? 0,
      ),
    )
    .toBe(1);

  const initialCounts = {
    conversations: requestCounts.conversations,
    messages: requestCounts.messages,
  };

  await page.evaluate(() => {
    const source = (window as Window & { __fakeEventSourceInstances?: Array<{ onopen?: ((event: Event) => void) | null; emit: (type: string, data: unknown) => void }> }).__fakeEventSourceInstances?.[0];
    if (source) {
      (source as { readyState?: number }).readyState = 1;
    }
    source?.onopen?.(new Event('open'));
    source?.emit('ready', { type: 'ready' });
  });

  await expect
    .poll(() => requestCounts.conversations)
    .toBe(initialCounts.conversations + 1);
  await expect
    .poll(() => requestCounts.messages)
    .toBe(initialCounts.messages + 1);

  await page.waitForTimeout(1_000);
  await page.evaluate(() => {
    const source = (window as Window & { __fakeEventSourceInstances?: Array<{ emit: (type: string, data: unknown) => void }> }).__fakeEventSourceInstances?.[0];
    source?.emit('ready', { type: 'ready' });
  });

  await page.waitForTimeout(700);

  expect(requestCounts.conversations).toBe(initialCounts.conversations + 1);
  expect(requestCounts.messages).toBe(initialCounts.messages + 1);
});

test('database mode does not wait for 15s fallback after created event when SSE is connected', async ({
  page,
}) => {
  await installDatabaseModeApiMocks(page);

  await page.addInitScript(() => {
    class FakeEventSource {
      static instances: FakeEventSource[] = [];
      static CONNECTING = 0;
      static OPEN = 1;
      static CLOSED = 2;
      url: string;
      withCredentials: boolean;
      onopen: ((event: Event) => void) | null = null;
      listeners = new Map<string, Array<(event: MessageEvent) => void>>();
      readyState = FakeEventSource.CONNECTING;

      constructor(url: string, init?: EventSourceInit) {
        this.url = url;
        this.withCredentials = Boolean(init?.withCredentials);
        FakeEventSource.instances.push(this);
        (window as Window & { __fakeEventSourceInstances?: FakeEventSource[] }).__fakeEventSourceInstances =
          FakeEventSource.instances;
      }

      addEventListener(type: string, listener: (event: MessageEvent) => void) {
        const next = this.listeners.get(type) ?? [];
        next.push(listener);
        this.listeners.set(type, next);
      }

      close() {
        this.readyState = FakeEventSource.CLOSED;
      }

      emit(type: string, data: unknown) {
        for (const listener of this.listeners.get(type) ?? []) {
          listener(new MessageEvent(type, { data: JSON.stringify(data) }));
        }
      }
    }

    (window as Window & { EventSource: typeof EventSource }).EventSource =
      FakeEventSource as unknown as typeof EventSource;
  });

  let conversationsCount = 0;
  let handshakeCount = 0;

  await page.route('**/api/v1/local-connectors/wxwork-local/status', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        code: 0,
        msg: 'ok',
        data: {
          connector: {
            connector_id: 'wxwork-local',
            name: 'WeCom Local Connector',
            managed_by: 'builtin',
            expected_tool_count: 5,
            status: 'running',
            tool_count: 5,
            updated_at: Date.now(),
            worker: { owned: true, port: 5681, started_at: null },
            monitor: {
              enabled: true,
              owned: true,
              running_status: 'running',
              warmup_completed: true,
              outbox_pending: 0,
            },
          },
        },
      }),
    });
  });

  await page.route('**/api/v1/database-mode/events/session', async (route) => {
    handshakeCount += 1;
    await route.fulfill({
      status: 204,
      headers: {
        'Cache-Control': 'no-store',
        'Set-Cookie':
          'langbot_dbmode_sse=test; Path=/api/v1/database-mode/events; HttpOnly; SameSite=Strict',
      },
    });
  });

  await page.route('**/api/v1/bots/database-mode-bot/conversations', async (route) => {
    conversationsCount += 1;
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        code: 0,
        msg: 'ok',
        data: {
          conversations: [],
          total: 0,
          page: 1,
          page_size: 100,
        },
      }),
    });
  });

  await page.goto('/home/database-mode');
  await expect.poll(() => handshakeCount).toBe(1);
  await expect
    .poll(async () =>
      page.evaluate(
        () =>
          (
            window as Window & {
              __fakeEventSourceInstances?: Array<{
                readyState: number;
                onopen?: ((event: Event) => void) | null;
              }>;
            }
          ).__fakeEventSourceInstances?.length ?? 0,
      ),
    )
    .toBe(1);

  await page.evaluate(() => {
    const source = (window as Window & { __fakeEventSourceInstances?: Array<{ onopen?: ((event: Event) => void) | null; emit: (type: string, data: unknown) => void }> }).__fakeEventSourceInstances?.[0];
    if (source) {
      (source as { readyState?: number }).readyState = 1;
    }
    source?.onopen?.(new Event('open'));
    source?.emit('database-message-created', {
      type: 'database-message-created',
      event_id: 'evt-2',
      metadata: {
        timings: {
          sse_published_at: '2026-06-24T10:00:00.200000+00:00',
        },
      },
    });
  });

  await expect.poll(() => conversationsCount).toBeGreaterThan(1);
  await page.waitForTimeout(1_000);
  await expect(handshakeCount).toBe(1);
});

test('database mode retries handshake with a single reconnect flow', async ({
  page,
}) => {
  await installDatabaseModeApiMocks(page);

  await page.addInitScript(() => {
    class FakeEventSource {
      static instances: FakeEventSource[] = [];
      static CONNECTING = 0;
      static OPEN = 1;
      static CLOSED = 2;
      url: string;
      withCredentials: boolean;
      onopen: ((event: Event) => void) | null = null;
      onerror: ((event: Event) => void) | null = null;
      listeners = new Map<string, Array<(event: MessageEvent) => void>>();
      readyState = FakeEventSource.CONNECTING;

      constructor(url: string, init?: EventSourceInit) {
        this.url = url;
        this.withCredentials = Boolean(init?.withCredentials);
        FakeEventSource.instances.push(this);
        (window as Window & { __fakeEventSourceInstances?: FakeEventSource[] }).__fakeEventSourceInstances =
          FakeEventSource.instances;
      }

      addEventListener(type: string, listener: (event: MessageEvent) => void) {
        const next = this.listeners.get(type) ?? [];
        next.push(listener);
        this.listeners.set(type, next);
      }

      close() {
        this.readyState = FakeEventSource.CLOSED;
      }
    }

    (window as Window & { EventSource: typeof EventSource }).EventSource =
      FakeEventSource as unknown as typeof EventSource;
  });

  let handshakeCount = 0;
  let shouldFailHandshake = true;

  await page.route('**/api/v1/local-connectors/wxwork-local/status', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        code: 0,
        msg: 'ok',
        data: {
          connector: {
            connector_id: 'wxwork-local',
            name: 'WeCom Local Connector',
            managed_by: 'builtin',
            expected_tool_count: 5,
            status: 'running',
            tool_count: 5,
            updated_at: Date.now(),
            worker: { owned: true, port: 5681, started_at: null },
            monitor: {
              enabled: true,
              owned: true,
              running_status: 'running',
              warmup_completed: true,
              outbox_pending: 0,
            },
          },
        },
      }),
    });
  });

  await page.route('**/api/v1/database-mode/events/session', async (route) => {
    handshakeCount += 1;
    if (shouldFailHandshake) {
      await route.fulfill({
        status: 403,
        contentType: 'application/json',
        body: JSON.stringify({
          code: -1,
          msg: 'Origin not allowed',
          data: null,
        }),
      });
      return;
    }

    await route.fulfill({
      status: 204,
      headers: {
        'Cache-Control': 'no-store',
        'Set-Cookie':
          'langbot_dbmode_sse=test; Path=/api/v1/database-mode/events; HttpOnly; SameSite=Strict',
      },
    });
  });

  await page.route('**/api/v1/bots/database-mode-bot/conversations', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        code: 0,
        msg: 'ok',
        data: {
          conversations: [],
          total: 0,
          page: 1,
          page_size: 100,
        },
      }),
    });
  });

  await page.goto('/home/database-mode');
  await expect(page).toHaveURL(/\/home\/bots\?id=database-mode-bot&tab=sessions$/);
  await expect.poll(() => handshakeCount).toBe(1);

  await page.waitForTimeout(1200);
  await expect.poll(() => handshakeCount).toBe(2);

  await page.waitForTimeout(1200);
  await expect.poll(() => handshakeCount).toBe(2);

  shouldFailHandshake = false;
  await page.waitForTimeout(2200);

  await expect.poll(() => handshakeCount).toBe(3);
  await expect
    .poll(async () =>
      page.evaluate(
        () =>
          (
            window as Window & {
              __fakeEventSourceInstances?: Array<{ url: string; withCredentials: boolean }>;
            }
          ).__fakeEventSourceInstances?.length ?? 0,
      ),
    )
    .toBe(1);
});

test('database mode abandons a stuck EventSource and retries until a new connection opens', async ({
  page,
}) => {
  await installDatabaseModeApiMocks(page);

  await page.addInitScript(() => {
    class FakeEventSource {
      static instances: FakeEventSource[] = [];
      static CONNECTING = 0;
      static OPEN = 1;
      static CLOSED = 2;
      url: string;
      withCredentials: boolean;
      onopen: ((event: Event) => void) | null = null;
      onerror: ((event: Event) => void) | null = null;
      listeners = new Map<string, Array<(event: MessageEvent) => void>>();
      readyState = FakeEventSource.CONNECTING;

      constructor(url: string, init?: EventSourceInit) {
        this.url = url;
        this.withCredentials = Boolean(init?.withCredentials);
        FakeEventSource.instances.push(this);
        (
          window as Window & {
            __fakeEventSourceInstances?: FakeEventSource[];
          }
        ).__fakeEventSourceInstances = FakeEventSource.instances;
      }

      addEventListener(type: string, listener: (event: MessageEvent) => void) {
        const next = this.listeners.get(type) ?? [];
        next.push(listener);
        this.listeners.set(type, next);
      }

      close() {
        this.readyState = FakeEventSource.CLOSED;
      }

      emit(type: string, data: unknown) {
        for (const listener of this.listeners.get(type) ?? []) {
          listener(new MessageEvent(type, { data: JSON.stringify(data) }));
        }
      }
    }

    (window as Window & { EventSource: typeof EventSource }).EventSource =
      FakeEventSource as unknown as typeof EventSource;
  });

  let handshakeCount = 0;
  let conversationsCount = 0;

  await page.route('**/api/v1/local-connectors/wxwork-local/status', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        code: 0,
        msg: 'ok',
        data: {
          connector: {
            connector_id: 'wxwork-local',
            name: 'WeCom Local Connector',
            managed_by: 'builtin',
            expected_tool_count: 5,
            status: 'running',
            tool_count: 5,
            updated_at: Date.now(),
            worker: { owned: true, port: 5681, started_at: null },
            monitor: {
              enabled: true,
              owned: true,
              running_status: 'running',
              warmup_completed: true,
              outbox_pending: 0,
            },
          },
        },
      }),
    });
  });

  await page.route('**/api/v1/database-mode/events/session', async (route) => {
    handshakeCount += 1;
    await route.fulfill({
      status: 204,
      headers: {
        'Cache-Control': 'no-store',
        'Set-Cookie':
          'langbot_dbmode_sse=test; Path=/api/v1/database-mode/events; HttpOnly; SameSite=Strict',
      },
    });
  });

  await page.route('**/api/v1/bots/database-mode-bot/conversations', async (route) => {
    conversationsCount += 1;
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        code: 0,
        msg: 'ok',
        data: {
          conversations: [],
          total: 0,
          page: 1,
          page_size: 100,
        },
      }),
    });
  });

  await page.goto('/home/database-mode');
  await expect(page).toHaveURL(/\/home\/bots\?id=database-mode-bot&tab=sessions$/);
  await expect.poll(() => handshakeCount).toBe(1);

  await expect.poll(() => handshakeCount, { timeout: 4_000 }).toBe(2);
  await expect
    .poll(async () =>
      page.evaluate(
        () =>
          (
            window as Window & {
              __fakeEventSourceInstances?: Array<{ readyState: number }>;
            }
          ).__fakeEventSourceInstances?.map((instance) => instance.readyState) ?? [],
      ),
    )
    .toEqual([2, 0]);

  await page.evaluate(() => {
    const source = (
      window as Window & {
        __fakeEventSourceInstances?: Array<{
          readyState: number;
          onopen?: ((event: Event) => void) | null;
          emit: (type: string, data: unknown) => void;
        }>;
      }
    ).__fakeEventSourceInstances?.[1];
    if (source) {
      source.readyState = 1;
      source.onopen?.(new Event('open'));
      source.emit('database-message-created', {
        type: 'database-message-created',
        event_id: 'evt-recovered',
      });
    }
  });

  await expect.poll(() => conversationsCount).toBeGreaterThan(1);
});

test('database mode keeps a single EventSource alive across StrictMode remounts for 30 seconds', async ({
  page,
}) => {
  test.setTimeout(45_000);
  await installDatabaseModeApiMocks(page);

  await page.addInitScript(() => {
    class FakeEventSource {
      static instances: FakeEventSource[] = [];
      static CONNECTING = 0;
      static OPEN = 1;
      static CLOSED = 2;
      url: string;
      withCredentials: boolean;
      onopen: ((event: Event) => void) | null = null;
      onerror: ((event: Event) => void) | null = null;
      listeners = new Map<string, Array<(event: MessageEvent) => void>>();
      readyState = FakeEventSource.CONNECTING;
      closeCount = 0;

      constructor(url: string, init?: EventSourceInit) {
        this.url = url;
        this.withCredentials = Boolean(init?.withCredentials);
        FakeEventSource.instances.push(this);
        (window as Window & { __fakeEventSourceInstances?: FakeEventSource[] }).__fakeEventSourceInstances =
          FakeEventSource.instances;
      }

      addEventListener(type: string, listener: (event: MessageEvent) => void) {
        const next = this.listeners.get(type) ?? [];
        next.push(listener);
        this.listeners.set(type, next);
      }

      close() {
        this.closeCount += 1;
        this.readyState = FakeEventSource.CLOSED;
      }

      emit(type: string, data: unknown) {
        for (const listener of this.listeners.get(type) ?? []) {
          listener(new MessageEvent(type, { data: JSON.stringify(data) }));
        }
      }
    }

    (window as Window & { EventSource: typeof EventSource }).EventSource =
      FakeEventSource as unknown as typeof EventSource;
  });

  let handshakeCount = 0;
  let conversationsCount = 0;
  let conversationCount = 0;
  let messagesCount = 0;

  await page.route('**/api/v1/local-connectors/wxwork-local/status', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        code: 0,
        msg: 'ok',
        data: {
          connector: {
            connector_id: 'wxwork-local',
            name: 'WeCom Local Connector',
            managed_by: 'builtin',
            expected_tool_count: 5,
            status: 'running',
            tool_count: 5,
            updated_at: Date.now(),
            worker: { owned: true, port: 5681, started_at: null },
            monitor: {
              enabled: true,
              owned: true,
              running_status: 'running',
              warmup_completed: true,
              outbox_pending: 0,
            },
          },
        },
      }),
    });
  });

  await page.route('**/api/v1/database-mode/events/session', async (route) => {
    handshakeCount += 1;
    await route.fulfill({
      status: 204,
      headers: {
        'Cache-Control': 'no-store',
        'Set-Cookie':
          'langbot_dbmode_sse=test; Path=/api/v1/database-mode/events; HttpOnly; SameSite=Strict',
      },
    });
  });

  await page.route('**/api/v1/bots/database-mode-bot/conversations', async (route) => {
    conversationsCount += 1;
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        code: 0,
        msg: 'ok',
        data: {
          conversations: [
            {
              id: 1,
              source: 'wxwork',
              conversation_name: 'Customer A',
              conversation_type: 'direct',
              last_message_at: '2026-06-24T10:00:00+00:00',
              pending_count: 1,
              failed_count: 0,
              latest_customer: 'Customer A',
              latest_message_summary: 'Need pricing details',
            },
          ],
          total: 1,
          page: 1,
          page_size: 100,
        },
      }),
    });
  });

  await page.route('**/api/v1/bots/database-mode-bot/conversations/1', async (route) => {
    conversationCount += 1;
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        code: 0,
        msg: 'ok',
        data: {
          conversation: {
            id: 1,
            connector_id: 'wxwork-local',
            source: 'wxwork',
            external_conversation_id: 'S:100_200',
            conversation_name: 'Customer A',
            conversation_type: 'direct',
            last_message_at: '2026-06-24T10:00:00+00:00',
            stats: {
              pending: 1,
              processing: 0,
              draft_ready: 0,
              failed: 0,
              processed: 0,
              skipped: 0,
              total: 1,
            },
            latest_customer: 'Customer A',
          },
        },
      }),
    });
  });

  await page.route('**/api/v1/bots/database-mode-bot/conversations/1/messages**', async (route) => {
    messagesCount += 1;
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        code: 0,
        msg: 'ok',
        data: {
          messages: [
            {
              id: 7,
              event_id: 'evt-1',
              message_key: 'wxwork:key-1',
              conversation_id: 1,
              sender_id: '200',
              sender_name: 'Customer A',
              content: 'Need pricing details',
              content_preview: 'Need pricing details',
              message_type: 'text',
              sent_at: '2026-06-24T10:00:00+00:00',
              observed_at: '2026-06-24T10:00:02+00:00',
              status: 'pending',
              attempt_count: 0,
            },
          ],
          total: 1,
          page: 1,
          page_size: 200,
          stats: {
            pending: 1,
            processing: 0,
            draft_ready: 0,
            failed: 0,
            processed: 0,
            skipped: 0,
            total: 1,
          },
        },
      }),
    });
  });

  await page.goto('/home/database-mode');
  await expect(page).toHaveURL(/\/home\/bots\?id=database-mode-bot&tab=sessions$/);
  await expect.poll(() => handshakeCount).toBe(1);
  await expect.poll(() => conversationsCount).toBeGreaterThan(0);
  await expect
    .poll(async () =>
      page.evaluate(
        () =>
          (
            window as Window & {
              __fakeEventSourceInstances?: Array<{ readyState: number; onopen?: ((event: Event) => void) | null }>;
            }
          ).__fakeEventSourceInstances?.length ?? 0,
      ),
    )
    .toBe(1);

  await page.evaluate(() => {
    const source = (
      window as Window & {
        __fakeEventSourceInstances?: Array<{
          readyState: number;
          onopen?: ((event: Event) => void) | null;
          emit: (type: string, data: unknown) => void;
        }>;
      }
    ).__fakeEventSourceInstances?.[0];
    if (!source) {
      return;
    }

    source.readyState = 1;
    source.onopen?.(new Event('open'));
    source.emit('ready', { type: 'ready' });

    window.setTimeout(() => {
      source.emit('database-message-created', {
        type: 'database-message-created',
        event_id: 'evt-20s',
      });
    }, 20_000);
  });

  const baseline = {
    conversations: conversationsCount,
    messages: messagesCount,
  };

  await page.waitForTimeout(21_000);

  await expect.poll(() => conversationsCount).toBeGreaterThan(baseline.conversations);
  await expect.poll(() => messagesCount).toBeGreaterThan(baseline.messages);

  await page.waitForTimeout(10_000);

  await expect
    .poll(async () =>
      page.evaluate(() => {
        const instances = (
          window as Window & {
            __fakeEventSourceInstances?: Array<{
              readyState: number;
              closeCount: number;
            }>;
          }
        ).__fakeEventSourceInstances ?? [];

        return {
          count: instances.length,
          states: instances.map((instance) => instance.readyState),
          closeCounts: instances.map((instance) => instance.closeCount),
        };
      }),
    )
    .toEqual({
      count: 1,
      states: [1],
      closeCounts: [0],
    });
});

test('database mode does not let a stale cleanup timer close a quick remount connection', async ({
  page,
}) => {
  await installDatabaseModeApiMocks(page);

  await page.addInitScript(() => {
    class FakeEventSource {
      static instances: FakeEventSource[] = [];
      static CONNECTING = 0;
      static OPEN = 1;
      static CLOSED = 2;
      url: string;
      withCredentials: boolean;
      onopen: ((event: Event) => void) | null = null;
      onerror: ((event: Event) => void) | null = null;
      listeners = new Map<string, Array<(event: MessageEvent) => void>>();
      readyState = FakeEventSource.CONNECTING;
      closeCount = 0;

      constructor(url: string, init?: EventSourceInit) {
        this.url = url;
        this.withCredentials = Boolean(init?.withCredentials);
        FakeEventSource.instances.push(this);
        (window as Window & { __fakeEventSourceInstances?: FakeEventSource[] }).__fakeEventSourceInstances =
          FakeEventSource.instances;
      }

      addEventListener(type: string, listener: (event: MessageEvent) => void) {
        const next = this.listeners.get(type) ?? [];
        next.push(listener);
        this.listeners.set(type, next);
      }

      close() {
        this.closeCount += 1;
        this.readyState = FakeEventSource.CLOSED;
      }

      emit(type: string, data: unknown) {
        for (const listener of this.listeners.get(type) ?? []) {
          listener(new MessageEvent(type, { data: JSON.stringify(data) }));
        }
      }
    }

    (window as Window & { EventSource: typeof EventSource }).EventSource =
      FakeEventSource as unknown as typeof EventSource;
  });

  let handshakeCount = 0;

  await page.route('**/api/v1/local-connectors/wxwork-local/status', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        code: 0,
        msg: 'ok',
        data: {
          connector: {
            connector_id: 'wxwork-local',
            name: 'WeCom Local Connector',
            managed_by: 'builtin',
            expected_tool_count: 5,
            status: 'running',
            tool_count: 5,
            updated_at: Date.now(),
            worker: { owned: true, port: 5681, started_at: null },
            monitor: {
              enabled: true,
              owned: true,
              running_status: 'running',
              warmup_completed: true,
              outbox_pending: 0,
            },
          },
        },
      }),
    });
  });

  await page.route('**/api/v1/database-mode/events/session', async (route) => {
    handshakeCount += 1;
    await route.fulfill({
      status: 204,
      headers: {
        'Cache-Control': 'no-store',
        'Set-Cookie':
          'langbot_dbmode_sse=test; Path=/api/v1/database-mode/events; HttpOnly; SameSite=Strict',
      },
    });
  });

  await page.route('**/api/v1/bots/database-mode-bot/conversations', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        code: 0,
        msg: 'ok',
        data: {
          conversations: [],
          total: 0,
          page: 1,
          page_size: 100,
        },
      }),
    });
  });

  await page.goto('/home/database-mode');
  await expect.poll(() => handshakeCount).toBe(1);

  await page.evaluate(() => {
    const source = (
      window as Window & {
        __fakeEventSourceInstances?: Array<{
          readyState: number;
          onopen?: ((event: Event) => void) | null;
          emit: (type: string, data: unknown) => void;
        }>;
      }
    ).__fakeEventSourceInstances?.[0];
    if (!source) {
      return;
    }
    source.readyState = 1;
    source.onopen?.(new Event('open'));
    source.emit('ready', { type: 'ready' });
  });

  await page.getByText('Pipelines').first().click();
  await page.waitForTimeout(25);
  await page.getByText('Database Mode Bot').first().click();
  await page.getByRole('tab', { name: /Sessions/ }).click();
  await expect(page).toHaveURL(/\/home\/bots\?id=database-mode-bot&tab=sessions$/);

  await expect
    .poll(async () =>
      page.evaluate(() => {
        const instances = (
          window as Window & {
            __fakeEventSourceInstances?: Array<{
              readyState: number;
              closeCount: number;
            }>;
          }
        ).__fakeEventSourceInstances ?? [];

        return {
          handshakeCount: instances.length,
          states: instances.map((instance) => instance.readyState),
          closeCounts: instances.map((instance) => instance.closeCount),
        };
      }),
    )
    .toEqual({
      handshakeCount: 1,
      states: [1],
      closeCounts: [0],
    });

  expect(handshakeCount).toBe(1);
});
