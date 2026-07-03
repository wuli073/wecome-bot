import { expect, test } from '@playwright/test';

import { installLangBotApiMocks } from './fixtures/langbot-api';

test.describe('broadcast execution phase 5', () => {
  test('creates a multi-draft batch and drives start pause resume cancel controls', async ({ page }) => {
    await installLangBotApiMocks(page, {
      authenticated: true,
      storage: {
        langbot_language: 'en-US',
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
    await page.getByTestId('broadcast-draft-select-all-checkbox').click();
    await page.getByTestId('broadcast-draft-batch-confirm-button').click();
    await page.getByTestId('broadcast-draft-create-execution-batch-button').click();

    await expect(page.getByTestId('broadcast-latest-execution-batch')).toBeVisible();
    await page.getByTestId('broadcast-batch-start-button').click();
    await page.getByTestId('broadcast-batch-pause-button').click();
    await expect(page.getByTestId('broadcast-batch-resume-button')).toBeEnabled();

    await page.reload();
    await page.locator('[role="tab"]').nth(3).click();
    await expect(page.getByTestId('broadcast-latest-execution-batch')).toBeVisible();
    await page.getByTestId('broadcast-batch-resume-button').click();

    const retryButton = page.locator('[data-testid^="broadcast-execution-task-retry-"]').first();
    await expect(retryButton).toBeVisible();
    await retryButton.click();
    await page.getByTestId('broadcast-batch-cancel-button').click();

    expect(requestPaths).toContain('/api/v1/broadcast/executions');
    expect(requestPaths.some((path) => /\/api\/v1\/broadcast\/executions\/\d+\/start$/.test(path))).toBeTruthy();
    expect(requestPaths.some((path) => /\/api\/v1\/broadcast\/executions\/\d+\/pause$/.test(path))).toBeTruthy();
    expect(requestPaths.some((path) => /\/api\/v1\/broadcast\/executions\/\d+\/resume$/.test(path))).toBeTruthy();
    expect(requestPaths.some((path) => /\/api\/v1\/broadcast\/executions\/\d+\/cancel$/.test(path))).toBeTruthy();
    expect(requestPaths.some((path) => /\/api\/v1\/broadcast\/execution-tasks\/\d+\/retry$/.test(path))).toBeTruthy();
  });
});
