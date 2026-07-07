import { expect, test, type Page } from '@playwright/test';

import zhHans from '../../src/i18n/locales/zh-Hans';
import { installLangBotApiMocks } from './fixtures/langbot-api';

async function prepareDraftReview(page: Page) {
  await page.goto('/home/broadcast');
  await page.locator('[role="tab"]').nth(1).click();
  await page.getByTestId('broadcast-import-upload-input').setInputFiles({
    name: 'customers.csv',
    mimeType: 'text/csv',
    buffer: Buffer.from('customers', 'utf-8'),
  });
  await page.getByTestId('broadcast-import-select-all-checkbox').click();
  await page.getByTestId('broadcast-import-template-select').selectOption('1');
  await page.getByTestId('broadcast-import-apply-template-button').click();
  await expect(
    page.getByTestId('broadcast-import-generate-drafts-button'),
  ).toBeEnabled();
  await page.getByTestId('broadcast-import-generate-drafts-button').click();
  await page.locator('[role="tab"]').nth(2).click();
}

test.describe('broadcast execution phase 4', () => {
  test('uses exact zh-Hans paste verification copy without mojibake', async ({
    page,
  }) => {
    expect(zhHans.broadcast.drafts.pasteHint).toBe(
      '系统将自动搜索并进入目标群聊，然后把正文和附件粘贴到输入框。系统不会自动发送，请人工确认后发送。',
    );
    expect(zhHans.broadcast.logs.capabilityPasteVerification).toBe('内容验证');
    expect(zhHans.broadcast.logs.conversationLocatorExternalId).toBe(
      '外部会话 ID',
    );
    expect(zhHans.broadcast.logs.pasteVerificationMethod).toBe('验证方式');
    expect(zhHans.broadcast.logs.pasteVerificationMethodManual).toBe(
      '人工确认',
    );
    expect(zhHans.broadcast.logs.pasteVerificationStatus).toBe('验证状态');
    expect(zhHans.broadcast.logs.pasteVerificationAvailable).toBe('可用');
    expect(zhHans.broadcast.logs.pasteVerificationUnavailable).toBe('未启用');
    expect(zhHans.broadcast.logs.pasteVerificationUnavailableHint).toBe(
      '内容验证：未启用',
    );
    expect(zhHans.broadcast.logs.statusPasteVerified).toBe('已写入并验证');
    expect(zhHans.broadcast.toasts.pasteSubmitted).toBe('写入任务已提交');

    await installLangBotApiMocks(page, {
      authenticated: true,
      storage: {
        langbot_language: 'zh-Hans',
      },
    });

    await prepareDraftReview(page);
    await page.getByTestId('broadcast-draft-paste-button').click();
    await expect(
      page.getByTestId('broadcast-draft-paste-confirm-dialog'),
    ).toHaveCount(0);

    await expect(
      page.getByTestId('broadcast-execution-logs-table'),
    ).toBeVisible();
    await expect(page.locator('body')).toContainText(
      zhHans.broadcast.logs.capabilityPasteVerification,
    );
    await expect(page.locator('body')).toContainText(
      zhHans.broadcast.logs.pasteVerificationMethod,
    );
    await expect(page.locator('body')).toContainText(
      zhHans.broadcast.logs.pasteVerificationStatus,
    );
    await expect(page.locator('body')).toContainText('Windows UI Automation');
    await expect(page.locator('body')).toContainText(
      zhHans.broadcast.logs.pasteVerificationAvailable,
    );
    await expect(page.locator('body')).toContainText(
      zhHans.broadcast.logs.statusPasteVerified,
    );
    await expect(page.locator('body')).not.toContainText(/锟|鏀|楠岃瘉鏂瑰紡/);
  });

  test('shows backend conversation locator and manual verification labels faithfully', async ({
    page,
  }) => {
    await installLangBotApiMocks(page, {
      authenticated: true,
      storage: {
        langbot_language: 'zh-Hans',
      },
    });

    await page.route(
      '**/api/v1/broadcast/executors/capabilities*',
      async (route) => {
        if (route.request().method() !== 'GET') {
          await route.fallback();
          return;
        }
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            code: 0,
            message: 'ok',
            data: {
              channel: 'wxwork_database',
              supports_paste: true,
              supports_paste_verification: false,
              requires_manual_conversation_open: false,
              conversation_locator: 'external_id',
              content_verification: 'manual',
              supports_send: false,
              supports_cancel: true,
              supports_status_query: true,
              supports_clipboard_restore: true,
              supports_evidence: true,
              executor_version: 'fixture-phase7',
              runtime_min_version: '1.0.0',
            },
            timestamp: Date.now(),
          }),
        });
      },
    );

    await page.route('**/api/v1/broadcast/executors/health*', async (route) => {
      if (route.request().method() !== 'GET') {
        await route.fallback();
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          code: 0,
          message: 'ok',
          data: {
            channel: 'wxwork_database',
            status: 'ready',
            protocol_version: '1.0.0',
            runtime_version: '1.0.0',
            capability: {
              channel: 'wxwork_database',
              supports_paste: true,
              supports_paste_verification: false,
              requires_manual_conversation_open: false,
              conversation_locator: 'external_id',
              content_verification: 'manual',
              supports_send: false,
              supports_cancel: true,
              supports_status_query: true,
              supports_clipboard_restore: true,
              supports_evidence: true,
              executor_version: 'fixture-phase7',
              runtime_min_version: '1.0.0',
            },
            runtime_status: {},
          },
          timestamp: Date.now(),
        }),
      });
    });

    await page.goto('/home/broadcast');
    await page.locator('[role="tab"]').nth(3).click();

    await expect(page.locator('body')).toContainText(
      zhHans.broadcast.logs.conversationLocatorExternalId,
    );
    await expect(page.locator('body')).toContainText(
      zhHans.broadcast.logs.pasteVerificationMethodManual,
    );
  });

  test('writes a single pending draft into the input box without sending', async ({
    page,
  }) => {
    await installLangBotApiMocks(page, {
      authenticated: true,
      storage: {
        langbot_language: 'zh-Hans',
      },
    });

    const requestPaths: string[] = [];
    page.on('request', (request) => {
      const url = new URL(request.url());
      if (url.pathname.startsWith('/api/v1/')) {
        requestPaths.push(url.pathname);
      }
    });

    await prepareDraftReview(page);
    await page.getByTestId('broadcast-draft-paste-button').click();
    await expect(
      page.getByTestId('broadcast-draft-paste-confirm-dialog'),
    ).toHaveCount(0);
    await expect(
      page.getByTestId('broadcast-execution-logs-table'),
    ).toBeVisible();

    await page.locator('[role="tab"]').nth(3).click();
    await expect(
      page.getByRole('cell', { name: 'Acme Freight', exact: true }),
    ).toBeVisible();
    await expect(
      page.locator('[data-testid="broadcast-execution-logs-table"] tbody tr'),
    ).toHaveCount(1);

    expect(requestPaths).toContain('/api/v1/broadcast/executions');
    expect(
      requestPaths.some((path) =>
        /\/api\/v1\/broadcast\/executions\/\d+\/start$/.test(path),
      ),
    ).toBeTruthy();
    expect(
      requestPaths.some((path) => path.includes('/attempts')),
    ).toBeTruthy();
    expect(
      requestPaths.some((path) => path.includes('/evidence')),
    ).toBeTruthy();
    expect(
      requestPaths.some((path) => path.includes('send-message')),
    ).toBeFalsy();
    expect(
      requestPaths.some((path) => path.includes('send-draft')),
    ).toBeFalsy();
  });

  test('prevents duplicate execution requests during a slow double click flow', async ({
    page,
  }) => {
    await installLangBotApiMocks(page, {
      authenticated: true,
      storage: {
        langbot_language: 'zh-Hans',
      },
    });

    let executionsCount = 0;
    let startCount = 0;
    let releaseExecutionResponse: (() => void) | undefined;

    await page.route('**/api/v1/broadcast/executions', async (route) => {
      if (route.request().method() !== 'POST') {
        await route.fallback();
        return;
      }
      executionsCount += 1;
      await new Promise<void>((resolve) => {
        releaseExecutionResponse = resolve;
      });
      await route.fallback();
    });

    page.on('request', (request) => {
      const url = new URL(request.url());
      if (
        request.method() === 'POST' &&
        /\/api\/v1\/broadcast\/executions\/\d+\/start$/.test(url.pathname)
      ) {
        startCount += 1;
      }
    });

    await prepareDraftReview(page);
    await page.getByTestId('broadcast-draft-paste-button').click();
    await expect(
      page.getByTestId('broadcast-draft-paste-button'),
    ).toBeDisabled();
    await page
      .getByTestId('broadcast-draft-paste-button')
      .click({ force: true });

    expect(executionsCount).toBe(1);
    expect(startCount).toBe(0);

    releaseExecutionResponse?.();

    await expect
      .poll(() => executionsCount, {
        timeout: 5000,
      })
      .toBe(1);
    await expect
      .poll(() => startCount, {
        timeout: 5000,
      })
      .toBe(1);
  });

  test('keeps paste-only actions available when paste verification is unavailable', async ({
    page,
  }) => {
    await installLangBotApiMocks(page, {
      authenticated: true,
      storage: {
        langbot_language: 'zh-Hans',
      },
    });

    await page.route(
      '**/api/v1/broadcast/executors/capabilities*',
      async (route) => {
        if (route.request().method() !== 'GET') {
          await route.fallback();
          return;
        }
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            code: 0,
            message: 'ok',
            data: {
              channel: 'wxwork_database',
              supports_paste: true,
              supports_paste_verification: true,
              requires_manual_conversation_open: true,
              supports_send: false,
              supports_cancel: true,
              supports_status_query: true,
              supports_clipboard_restore: true,
              supports_evidence: true,
              executor_version: 'fixture-phase7',
              runtime_min_version: '1.0.0',
            },
            timestamp: Date.now(),
          }),
        });
      },
    );

    await page.route('**/api/v1/broadcast/executors/health*', async (route) => {
      if (route.request().method() !== 'GET') {
        await route.fallback();
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          code: 0,
          message: 'ok',
          data: {
            channel: 'wxwork_database',
            status: 'ready',
            protocol_version: '1.0.0',
            runtime_version: '1.0.0',
            capability: {
              channel: 'wxwork_database',
              supports_paste: true,
              supports_paste_verification: true,
              requires_manual_conversation_open: true,
              supports_send: false,
              supports_cancel: true,
              supports_status_query: true,
              supports_clipboard_restore: true,
              supports_evidence: true,
              executor_version: 'fixture-phase7',
              runtime_min_version: '1.0.0',
            },
            runtime_status: {
              pasteVerification: {
                available: false,
                reason: 'PASTE_VERIFICATION_UNAVAILABLE',
                method: 'windows_uia',
                requiresManualConversationOpen: true,
                supportedErrorCodes: [
                  'TARGET_WINDOW_CHANGED',
                  'CONVERSATION_MISMATCH',
                  'INPUT_NOT_LOCATED',
                  'PASTE_CONTENT_MISMATCH',
                  'PASTE_VERIFICATION_UNAVAILABLE',
                ],
              },
            },
          },
          timestamp: Date.now(),
        }),
      });
    });

    const requestRecords: Array<{ method: string; path: string }> = [];
    page.on('request', (request) => {
      const url = new URL(request.url());
      if (url.pathname.startsWith('/api/v1/')) {
        requestRecords.push({
          method: request.method(),
          path: url.pathname,
        });
      }
    });

    await prepareDraftReview(page);
    await page.getByTestId('broadcast-draft-select-all-checkbox').click();

    await expect(
      page.getByTestId('broadcast-draft-paste-button'),
    ).toBeEnabled();
    await expect(
      page.getByTestId('broadcast-draft-batch-write-button'),
    ).toBeEnabled();
    await expect(page.locator('body')).toContainText(
      zhHans.broadcast.logs.pasteVerificationUnavailableHint,
    );

    await page.getByTestId('broadcast-draft-batch-write-button').click();

    await page.locator('[role="tab"]').nth(3).click();
    await expect(
      page.getByTestId('broadcast-execution-logs-table'),
    ).toBeVisible();
    await expect(page.locator('body')).toContainText(
      zhHans.broadcast.logs.capabilityPasteVerification,
    );
    await expect(page.locator('body')).toContainText(
      zhHans.broadcast.logs.pasteVerificationMethod,
    );
    await expect(page.locator('body')).toContainText(
      zhHans.broadcast.logs.pasteVerificationStatus,
    );
    await expect(page.locator('body')).toContainText('Windows UI Automation');
    await expect(page.locator('body')).toContainText(
      zhHans.broadcast.logs.pasteVerificationUnavailable,
    );

    expect(
      requestRecords.some(
        ({ method, path }) =>
          method === 'POST' && path === '/api/v1/broadcast/executions',
      ),
    ).toBeTruthy();
    expect(
      requestRecords.some(
        ({ method, path }) =>
          method === 'POST' &&
          /\/api\/v1\/broadcast\/executions\/\d+\/start$/.test(path),
      ),
    ).toBeTruthy();
  });

  test('stops polling execution history after the latest paste-only batch becomes terminal', async ({
    page,
  }) => {
    await installLangBotApiMocks(page, {
      authenticated: true,
      storage: {
        langbot_language: 'en-US',
      },
    });

    await page.goto('/home/broadcast');
    await expect(page).toHaveURL(/\/home\/broadcast$/);

    const counters = {
      batches: 0,
      batchDetails: 0,
      attempts: 0,
      evidence: 0,
    };
    page.on('request', (request) => {
      const url = new URL(request.url());
      if (!url.pathname.startsWith('/api/v1/broadcast/')) {
        return;
      }
      if (
        url.pathname === '/api/v1/broadcast/executions' &&
        request.method() === 'GET'
      ) {
        counters.batches += 1;
        return;
      }
      if (/^\/api\/v1\/broadcast\/executions\/\d+$/.test(url.pathname)) {
        counters.batchDetails += 1;
        return;
      }
      if (url.pathname.includes('/attempts')) {
        counters.attempts += 1;
        return;
      }
      if (url.pathname.includes('/evidence')) {
        counters.evidence += 1;
      }
    });

    await prepareDraftReview(page);
    await page.getByTestId('broadcast-draft-paste-button').click();

    await expect(
      page.getByTestId('broadcast-execution-logs-table'),
    ).toBeVisible();
    await expect(
      page.locator('[data-testid="broadcast-execution-logs-table"] tbody tr'),
    ).toHaveCount(1);

    await expect
      .poll(() => ({
        attempts: counters.attempts,
        evidence: counters.evidence,
      }))
      .toEqual({
        attempts: 1,
        evidence: 1,
      });

    const snapshot = { ...counters };
    await page.waitForTimeout(3500);

    expect(counters).toEqual(snapshot);
  });
});
