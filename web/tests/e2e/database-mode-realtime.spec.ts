import { expect, test } from '@playwright/test';

import { installLangBotApiMocks } from './fixtures/langbot-api';

test('database mode refreshes after SSE ready and coalesces invalidation', async ({
  page,
}) => {
  await installLangBotApiMocks(page, { authenticated: true });

  await page.addInitScript(() => {
    class FakeEventSource {
      static instances: FakeEventSource[] = [];
      static CONNECTING = 0;
      static OPEN = 1;
      static CLOSED = 2;
      url: string;
      onopen: ((event: Event) => void) | null = null;
      onerror: ((event: Event) => void) | null = null;
      listeners = new Map<string, Array<(event: MessageEvent) => void>>();
      readyState = FakeEventSource.CONNECTING;

      constructor(url: string) {
        this.url = url;
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

  await page.route('**/api/v1/database-mode/conversations**', async (route) => {
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

  await page.route('**/api/v1/database-mode/conversations/1', async (route) => {
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

  await page.route('**/api/v1/database-mode/conversations/1/messages**', async (route) => {
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

  await expect(page.getByRole('heading', { name: 'Database Mode' })).toBeVisible();
  await expect.poll(() => handshakeCount).toBe(1);

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
});
