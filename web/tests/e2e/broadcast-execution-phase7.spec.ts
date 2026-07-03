import { expect, test } from '@playwright/test';

import { installLangBotApiMocks } from './fixtures/langbot-api';

async function prepareDraft(page: import('@playwright/test').Page) {
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
}

test.describe('broadcast execution phase 7', () => {
  test('hides real send when backend flags are disabled', async ({ page }) => {
    await installLangBotApiMocks(page, {
      authenticated: true,
      storage: {
        langbot_language: 'en-US',
      },
      broadcastSendEnabled: false,
    });

    await prepareDraft(page);
    await expect(page.getByTestId('broadcast-draft-send-button')).toHaveCount(0);
  });

  test('shows real send confirmation and uses dedicated send endpoints', async ({ page }) => {
    await installLangBotApiMocks(page, {
      authenticated: true,
      storage: {
        langbot_language: 'en-US',
      },
      broadcastSendEnabled: true,
    });

    const requestPaths: string[] = [];
    page.on('request', (request) => {
      const url = new URL(request.url());
      if (url.pathname.startsWith('/api/v1/')) {
        requestPaths.push(url.pathname);
      }
    });

    await prepareDraft(page);

    await expect(page.getByTestId('broadcast-draft-send-button')).toBeVisible();
    await page.getByTestId('broadcast-draft-send-button').click();
    await expect(page.getByTestId('broadcast-draft-send-confirm-dialog')).toBeVisible();
    await expect(page.getByTestId('broadcast-draft-send-confirm-action')).toBeDisabled();
    await page.waitForTimeout(3200);
    await page.getByTestId('broadcast-draft-send-acknowledge').click();
    await expect(page.getByTestId('broadcast-draft-send-confirm-action')).toBeEnabled();
    await page.getByTestId('broadcast-draft-send-confirm-action').click();

    await expect(page.getByTestId('broadcast-latest-execution-batch')).toBeVisible();
    await expect(page.getByTestId('broadcast-execution-logs-table')).toBeVisible();

    expect(requestPaths).toContain('/api/v1/broadcast/send-confirmations');
    expect(requestPaths.some((path) => /\/api\/v1\/broadcast\/execution-tasks\/\d+\/send$/.test(path))).toBeTruthy();
    expect(requestPaths.some((path) => /\/api\/v1\/broadcast\/executions$/.test(path))).toBeTruthy();
    expect(requestPaths.some((path) => /\/api\/v1\/broadcast\/executions\/\d+\/start$/.test(path))).toBeFalsy();
  });
});
