import { expect, test } from '@playwright/test';

import zhHans from '../../src/i18n/locales/zh-Hans';
import { installLangBotApiMocks } from './fixtures/langbot-api';

test.describe('broadcast execution phase 4', () => {
  test('uses exact zh-Hans paste verification copy without mojibake', async ({
    page,
  }) => {
    expect(zhHans.broadcast.drafts.pasteHint).toBe(
      '请先手动打开目标群聊。本操作只会将草稿写入输入框，不会自动发送消息。',
    );
    expect(zhHans.broadcast.logs.capabilityPasteVerification).toBe(
      '支持粘贴验证',
    );
    expect(zhHans.broadcast.logs.pasteVerificationMethod).toBe('验证方式');
    expect(zhHans.broadcast.logs.pasteVerificationStatus).toBe('验证状态');
    expect(zhHans.broadcast.logs.pasteVerificationAvailable).toBe('可用');
    expect(zhHans.broadcast.logs.pasteVerificationUnavailable).toBe('不可用');
    expect(zhHans.broadcast.logs.pasteVerificationUnavailableHint).toBe(
      '当前运行时缺少粘贴内容验证能力，无法执行“写入输入框”。',
    );
    expect(zhHans.broadcast.logs.statusPasteVerified).toBe('已写入并验证');
    expect(zhHans.broadcast.toasts.pasteSubmitted).toBe('写入任务已提交');

    await installLangBotApiMocks(page, {
      authenticated: true,
      storage: {
        langbot_language: 'zh-Hans',
      },
    });

    await page.goto('/home/broadcast');
    await page.locator('[role="tab"]').nth(1).click();
    await page.getByTestId('broadcast-import-upload-input').setInputFiles({
      name: 'customers.csv',
      mimeType: 'text/csv',
      buffer: Buffer.from('customers', 'utf-8'),
    });
    await page.getByTestId('broadcast-import-template-select').click();
    await page.getByRole('option', { name: 'Arrival Reminder' }).click();
    await page.getByTestId('broadcast-import-generate-drafts-button').click();

    await page.locator('[role="tab"]').nth(2).click();
    await page.getByTestId('broadcast-draft-confirm-button').click();
    await page.getByTestId('broadcast-draft-paste-button').click();
    await page.getByTestId('broadcast-draft-paste-confirm-action').click();

    await page.locator('[role="tab"]').nth(3).click();
    await expect(
      page.getByTestId('broadcast-execution-logs-table'),
    ).toBeVisible();
    await expect(page.locator('body')).toContainText('支持粘贴验证');
    await expect(page.locator('body')).toContainText('验证方式');
    await expect(page.locator('body')).toContainText('验证状态');
    await expect(page.locator('body')).toContainText('Windows UI Automation');
    await expect(page.locator('body')).toContainText('已写入并验证');
    await expect(page.locator('body')).not.toContainText(/锟|鐨|绔|鍏|鏀|鎵|�/);
  });

  test('writes a single ready draft into the input box without sending', async ({
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

    await page.goto('/home/broadcast');
    await page.locator('[role="tab"]').nth(1).click();
    await page.getByTestId('broadcast-import-upload-input').setInputFiles({
      name: 'customers.csv',
      mimeType: 'text/csv',
      buffer: Buffer.from('customers', 'utf-8'),
    });
    await page.getByTestId('broadcast-import-template-select').click();
    await page.getByRole('option', { name: 'Arrival Reminder' }).click();
    await page.getByTestId('broadcast-import-generate-drafts-button').click();

    await page.locator('[role="tab"]').nth(2).click();
    await page.getByTestId('broadcast-draft-confirm-button').click();
    await expect(
      page.getByTestId('broadcast-draft-revoke-button'),
    ).toBeEnabled();

    await page.getByTestId('broadcast-draft-paste-button').click();
    await expect(
      page.getByTestId('broadcast-draft-paste-confirm-dialog'),
    ).toBeVisible();
    await expect(
      page.getByTestId('broadcast-draft-paste-confirm-action'),
    ).toBeVisible();
    await page.getByTestId('broadcast-draft-paste-confirm-action').click();

    await expect(
      page.getByTestId('broadcast-execution-logs-table'),
    ).toBeVisible();

    await page.locator('[role="tab"]').nth(3).click();
    await expect(
      page.getByTestId('broadcast-execution-logs-table'),
    ).toBeVisible();
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

    await page.goto('/home/broadcast');
    await page.locator('[role="tab"]').nth(1).click();
    await page.getByTestId('broadcast-import-upload-input').setInputFiles({
      name: 'customers.csv',
      mimeType: 'text/csv',
      buffer: Buffer.from('customers', 'utf-8'),
    });
    await page.getByTestId('broadcast-import-template-select').click();
    await page.getByRole('option', { name: 'Arrival Reminder' }).click();
    await page.getByTestId('broadcast-import-generate-drafts-button').click();

    await page.locator('[role="tab"]').nth(2).click();
    await page.getByTestId('broadcast-draft-confirm-button').click();
    await page.getByTestId('broadcast-draft-paste-button').click();
    await page.getByTestId('broadcast-draft-paste-confirm-action').click();

    await expect(
      page.getByTestId('broadcast-draft-paste-button'),
    ).toBeDisabled();
    await page
      .getByTestId('broadcast-draft-paste-button')
      .click({ force: true });

    expect(executionsCount).toBe(1);
    expect(startCount).toBe(0);

    if (releaseExecutionResponse) {
      releaseExecutionResponse();
    }

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

  test('disables paste-only actions when paste verification is unavailable', async ({
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
            status: 'healthy',
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

    await page.goto('/home/broadcast');
    await page.locator('[role="tab"]').nth(1).click();
    await page.getByTestId('broadcast-import-upload-input').setInputFiles({
      name: 'customers.csv',
      mimeType: 'text/csv',
      buffer: Buffer.from('customers', 'utf-8'),
    });
    await page.getByTestId('broadcast-import-template-select').click();
    await page.getByRole('option', { name: 'Arrival Reminder' }).click();
    await page.getByTestId('broadcast-import-generate-drafts-button').click();

    await page.locator('[role="tab"]').nth(2).click();
    await page.getByTestId('broadcast-draft-confirm-button').click();
    await page.getByTestId('broadcast-draft-select-all-checkbox').click();

    await expect(
      page.getByTestId('broadcast-draft-paste-button'),
    ).toBeDisabled();
    await expect(
      page.getByTestId('broadcast-draft-create-execution-batch-button'),
    ).toBeDisabled();
    await expect(page.locator('body')).toContainText(
      '当前运行时缺少粘贴内容验证能力，无法执行“写入输入框”。',
    );

    await page.locator('[role="tab"]').nth(3).click();
    await expect(
      page.getByTestId('broadcast-execution-logs-table'),
    ).toBeVisible();
    await expect(page.locator('body')).toContainText('支持粘贴验证');
    await expect(page.locator('body')).toContainText('验证方式');
    await expect(page.locator('body')).toContainText('验证状态');
    await expect(page.locator('body')).toContainText('Windows UI Automation');
    await expect(page.locator('body')).toContainText('不可用');
    await expect(page.locator('body')).not.toContainText(/锟|鐨|绔|鍏|鏀|鎵|�/);

    expect(
      requestRecords.some(
        ({ method, path }) =>
          method === 'POST' && path === '/api/v1/broadcast/executions',
      ),
    ).toBeFalsy();
    expect(
      requestRecords.some(
        ({ method, path }) =>
          method === 'POST' &&
          /\/api\/v1\/broadcast\/executions\/\d+\/start$/.test(path),
      ),
    ).toBeFalsy();
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
    await page.locator('[role="tab"]').nth(1).click();
    await page.getByTestId('broadcast-import-upload-input').setInputFiles({
      name: 'customers.csv',
      mimeType: 'text/csv',
      buffer: Buffer.from('customers', 'utf-8'),
    });
    await page.getByTestId('broadcast-import-template-select').click();
    await page.getByRole('option', { name: 'Arrival Reminder' }).click();
    await page.getByTestId('broadcast-import-generate-drafts-button').click();

    await page.locator('[role="tab"]').nth(2).click();
    await page.getByTestId('broadcast-draft-confirm-button').click();
    await page.getByTestId('broadcast-draft-paste-button').click();
    await page.getByTestId('broadcast-draft-paste-confirm-action').click();

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
