import { expect, test } from '@playwright/test';

import { installLangBotApiMocks } from './fixtures/langbot-api';

test.describe('broadcast execution phase 4', () => {
  test('writes a single ready draft into the input box without sending', async ({ page }) => {
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
    await expect(page.getByTestId('broadcast-draft-revoke-button')).toBeEnabled();

    await page.getByTestId('broadcast-draft-paste-button').click();
    await expect(page.getByTestId('broadcast-draft-paste-confirm-dialog')).toBeVisible();
    await expect(page.getByTestId('broadcast-draft-paste-confirm-action')).toBeVisible();
    await page.getByTestId('broadcast-draft-paste-confirm-action').click();

    await expect(page.getByTestId('broadcast-execution-logs-table')).toBeVisible();

    await page.locator('[role="tab"]').nth(3).click();
    await expect(page.getByTestId('broadcast-execution-logs-table')).toBeVisible();
    await expect(page.getByRole('cell', { name: 'Acme Freight', exact: true })).toBeVisible();
    await expect(page.locator('[data-testid="broadcast-execution-logs-table"] tbody tr')).toHaveCount(1);

    expect(requestPaths).toContain('/api/v1/broadcast/executions');
    expect(requestPaths.some((path) => /\/api\/v1\/broadcast\/executions\/\d+\/start$/.test(path))).toBeTruthy();
    expect(requestPaths.some((path) => path.includes('/attempts'))).toBeTruthy();
    expect(requestPaths.some((path) => path.includes('/evidence'))).toBeTruthy();
    expect(requestPaths.some((path) => path.includes('send-message'))).toBeFalsy();
    expect(requestPaths.some((path) => path.includes('send-draft'))).toBeFalsy();
  });

  test('prevents duplicate execution requests during a slow double click flow', async ({ page }) => {
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

    await expect(page.getByTestId('broadcast-draft-paste-button')).toBeDisabled();
    await page.getByTestId('broadcast-draft-paste-button').click({ force: true });

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
});
