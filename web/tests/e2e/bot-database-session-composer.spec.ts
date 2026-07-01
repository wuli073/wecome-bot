import { expect, test, type Page, type Route } from '@playwright/test';

import { installLangBotApiMocks } from './fixtures/langbot-api';

function ok(data: unknown) {
  return {
    code: 0,
    msg: 'ok',
    message: 'ok',
    data,
    timestamp: Date.now(),
  };
}

async function fulfillJson(route: Route, data: unknown) {
  await route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify(ok(data)),
  });
}

const BOT = {
  uuid: 'bot-db',
  name: 'Database Bot',
  description: 'WXWork database bot',
  enable: true,
  adapter: 'wxwork_database',
  adapter_config: {},
  use_pipeline_uuid: null,
  pipeline_routing_rules: [],
  adapter_runtime_values: {},
  updated_at: new Date().toISOString(),
};

const CONVERSATION = {
  id: 200,
  connector_id: 'wxwork-local',
  source: 'wxwork',
  external_conversation_id: 'conv-beta',
  conversation_name: 'Customer Beta',
  conversation_type: 'direct',
  latest_customer: 'Customer Beta',
  latest_message_summary: 'Hello from beta',
  last_message_at: new Date().toISOString(),
  pending_count: 1,
  draft_ready_count: 1,
  processed_count: 0,
  failed_count: 0,
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
};

const MESSAGE = {
  id: 2001,
  event_id: 'evt-2001',
  message_key: 'wxwork:2001',
  conversation_id: 200,
  sender_id: 'customer-beta',
  sender_name: 'Customer Beta',
  content: 'Hello from beta',
  message_type: 'text',
  sent_at: new Date().toISOString(),
  observed_at: new Date().toISOString(),
  status: 'draft_ready',
  draft_text: 'Reply from bot',
  draft_source: 'pipeline',
  draft_id: 9001,
  draft_version: 1,
  draft_updated_at: new Date().toISOString(),
  last_error: null,
  attempt_count: 0,
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
};

interface PasteOnlyMockState {
  desktopRunFetchCalls: number;
  forbiddenCalibrationCalls: number;
  forbiddenContextCalls: number;
  lastPasteDraftBody: Record<string, unknown> | null;
  lastPasteDraftIdempotencyKey: string | undefined;
  pasteDraftCalls: number;
}

const READY_RUNTIME_STATUS = {
  status: 'ready',
  errorCode: null,
  runtime_configured: true,
  runtime_startable: true,
  runtime_reachable: true,
  send_enabled: false,
};

async function installPasteOnlyDatabaseBotMocks(
  page: Page,
  options?: { holdPasteResponse?: boolean },
): Promise<PasteOnlyMockState & { releasePasteResponse: () => void }> {
  let releasePasteResponse: () => void = () => undefined;
  const pasteGate = options?.holdPasteResponse
    ? new Promise<void>((resolve) => {
        releasePasteResponse = resolve;
      })
    : Promise.resolve();
  const state: PasteOnlyMockState & { releasePasteResponse: () => void } = {
    desktopRunFetchCalls: 0,
    forbiddenCalibrationCalls: 0,
    forbiddenContextCalls: 0,
    lastPasteDraftBody: null,
    lastPasteDraftIdempotencyKey: undefined,
    pasteDraftCalls: 0,
    releasePasteResponse,
  };

  await installLangBotApiMocks(page, { authenticated: true });

  await page.route('**/api/v1/platform/bots', async (route) => {
    if (route.request().method() !== 'GET') {
      return route.fallback();
    }
    await fulfillJson(route, { bots: [BOT] });
  });

  await page.route('**/api/v1/platform/bots/bot-db', async (route) => {
    if (route.request().method() !== 'GET') {
      return route.fallback();
    }
    await fulfillJson(route, { bot: BOT });
  });

  await page.route('**/api/v1/bots/bot-db/conversations**', async (route) => {
    const pathname = new URL(route.request().url()).pathname;
    if (pathname.endsWith('/conversations/200/messages')) {
      await fulfillJson(route, {
        messages: [MESSAGE],
        total: 1,
        page: 1,
        page_size: 50,
        stats: {
          pending_count: 0,
          draft_ready_count: 1,
          processed_count: 0,
          failed_count: 0,
        },
      });
      return;
    }

    if (pathname.endsWith('/conversations/200')) {
      await fulfillJson(route, {
        conversation: CONVERSATION,
      });
      return;
    }

    if (pathname.endsWith('/conversations')) {
      await fulfillJson(route, {
        conversations: [CONVERSATION],
        total: 1,
        page: 1,
        page_size: 20,
      });
      return;
    }

    await route.fallback();
  });

  await page.route(
    '**/api/v1/desktop-automation/runtime/status',
    async (route) => {
      await fulfillJson(route, READY_RUNTIME_STATUS);
    },
  );

  await page.route(
    '**/api/v1/bots/bot-db/desktop-automation/**',
    async (route) => {
      const pathname = new URL(route.request().url()).pathname;
      if (pathname.includes('/runs/')) {
        state.desktopRunFetchCalls += 1;
        await fulfillJson(route, {});
        return;
      }
      if (pathname.includes('context-confirmations')) {
        state.forbiddenContextCalls += 1;
      } else {
        state.forbiddenCalibrationCalls += 1;
      }
      await route.fulfill({ status: 404, body: 'not found' });
    },
  );

  await page.route(
    '**/api/v1/bots/bot-db/messages/2001/paste-draft',
    async (route) => {
      state.pasteDraftCalls += 1;
      state.lastPasteDraftBody = JSON.parse(route.request().postData() || '{}');
      state.lastPasteDraftIdempotencyKey = route.request().headers()[
        'idempotency-key'
      ];
      await pasteGate;
      await fulfillJson(route, {
        id: 7001,
        bot_uuid: 'bot-db',
        connector_id: 'wxwork-local',
        conversation_id: 200,
        message_id: 2001,
        draft_id: 9001,
        action: 'paste_draft',
        execution_mode: 'paste_only',
        runtime_task_id: 'task-1',
        status: 'succeeded',
        stage: 'pasted_to_input',
        attempt_count: 1,
        request_digest: 'digest-1',
        draft_content_hash: 'hash-1',
        target_snapshot: {},
        result_evidence: {
          messageSent: false,
          sendKeyCount: 0,
        },
        last_error_code: null,
        last_error_message: null,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      });
    },
  );

  return state;
}

function sessionButton(page: Page) {
  return page.getByRole('button', { name: /Customer Beta/ });
}

function pasteDraftButton(page: Page) {
  return page.getByRole('button', { name: 'Paste to WeCom input box' });
}

async function openDatabaseSession(page: Page) {
  await page.goto('/home/bots?id=bot-db&tab=sessions');
  await expect(sessionButton(page)).toBeVisible();
  await sessionButton(page).click();
  await expect(page.getByText('Customer Beta').first()).toBeVisible();
  await expect(pasteDraftButton(page)).toBeVisible();
}

test('paste-only UI has no calibration entry and allows paste without calibration', async ({
  page,
}) => {
  await installPasteOnlyDatabaseBotMocks(page);
  await openDatabaseSession(page);

  await expect(
    page.getByRole('button', { name: /Calibrate|Recalibrate/i }),
  ).toHaveCount(0);
  await expect(
    page.getByText(/not calibrated|regions configured/i),
  ).toHaveCount(0);
  await expect(pasteDraftButton(page)).toBeEnabled();
});

test('send pastes immediately without opening manual confirmation dialog', async ({
  page,
}) => {
  const mockState = await installPasteOnlyDatabaseBotMocks(page);
  await openDatabaseSession(page);

  await pasteDraftButton(page).click();

  await expect(
    page
      .getByText('Draft pasted into the WeCom input box; it was not sent.')
      .first(),
  ).toBeVisible();
  await expect(page.getByRole('button', { name: 'Confirm and paste' })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Cancel' })).toHaveCount(0);
  expect(mockState.pasteDraftCalls).toBe(1);
  expect(mockState.lastPasteDraftBody).toEqual({ draft_id: 9001 });
  expect(Object.keys(mockState.lastPasteDraftBody ?? {})).toEqual(['draft_id']);
  expect(mockState.lastPasteDraftIdempotencyKey).toMatch(
    /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i,
  );
  expect(mockState.forbiddenCalibrationCalls).toBe(0);
  expect(mockState.forbiddenContextCalls).toBe(0);
});

test('repeated clicks during paste submission do not create duplicate requests', async ({
  page,
}) => {
  const mockState = await installPasteOnlyDatabaseBotMocks(page, {
    holdPasteResponse: true,
  });
  await openDatabaseSession(page);

  await pasteDraftButton(page).click();
  await expect(pasteDraftButton(page)).toBeDisabled();
  await pasteDraftButton(page).click({ force: true });

  expect(mockState.pasteDraftCalls).toBe(1);
  mockState.releasePasteResponse();
  await expect(
    page
      .getByText('Draft pasted into the WeCom input box; it was not sent.')
      .first(),
  ).toBeVisible();
  expect(mockState.pasteDraftCalls).toBe(1);
});

test('send saves unsaved composer text before pasting the draft', async ({ page }) => {
  const mockState = await installPasteOnlyDatabaseBotMocks(page);
  let updateDraftCalls = 0;
  let lastUpdateDraftBody: Record<string, unknown> | null = null;

  await page.route('**/api/v1/bots/bot-db/drafts/9001', async (route) => {
    if (route.request().method() !== 'PUT') {
      return route.fallback();
    }
    updateDraftCalls += 1;
    lastUpdateDraftBody = JSON.parse(route.request().postData() || '{}');
    await fulfillJson(route, {
      message: {
        ...MESSAGE,
        draft_text: String(lastUpdateDraftBody?.content ?? ''),
        draft_source: 'manual',
        draft_version: 2,
        draft_updated_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      },
    });
  });

  await openDatabaseSession(page);
  await page.getByLabel('Composer draft').fill('Reply from operator');

  await pasteDraftButton(page).click();

  await expect(
    page
      .getByText('Draft pasted into the WeCom input box; it was not sent.')
      .first(),
  ).toBeVisible();
  expect(updateDraftCalls).toBe(1);
  expect(lastUpdateDraftBody).toEqual({ content: 'Reply from operator' });
  expect(mockState.pasteDraftCalls).toBe(1);
});

test('send stops when saving unsaved composer text fails', async ({ page }) => {
  const mockState = await installPasteOnlyDatabaseBotMocks(page);

  await page.route('**/api/v1/bots/bot-db/drafts/9001', async (route) => {
    if (route.request().method() !== 'PUT') {
      return route.fallback();
    }
    await route.fulfill({
      status: 500,
      contentType: 'application/json',
      body: JSON.stringify({
        code: -1,
        msg: 'SAVE_FAILED',
        message: 'SAVE_FAILED',
        data: null,
        timestamp: Date.now(),
      }),
    });
  });

  await openDatabaseSession(page);
  await page.getByLabel('Composer draft').fill('Reply from operator');

  await pasteDraftButton(page).click();

  await expect(page.getByText('SAVE_FAILED').first()).toBeVisible();
  expect(mockState.pasteDraftCalls).toBe(0);
});

test('empty composer text keeps send disabled and does not submit paste', async ({ page }) => {
  const mockState = await installPasteOnlyDatabaseBotMocks(page);
  await openDatabaseSession(page);

  await page.getByRole('button', { name: 'Clear' }).click();
  await expect(pasteDraftButton(page)).toBeDisabled();
  expect(mockState.pasteDraftCalls).toBe(0);
});

test('ordinary draft status bar copy is hidden when there is no active send status or error', async ({
  page,
}) => {
  await installPasteOnlyDatabaseBotMocks(page);
  await openDatabaseSession(page);

  await expect(page.getByText(/Draft v1/)).toHaveCount(0);
  await expect(page.getByText('Current session has been manually confirmed, the window context is stable, and the input area is located')).toHaveCount(0);
});
