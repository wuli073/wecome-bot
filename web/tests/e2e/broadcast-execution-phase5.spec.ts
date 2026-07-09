import { expect, test } from '@playwright/test';

import { installLangBotApiMocks } from './fixtures/langbot-api';

test.describe('broadcast execution phase 5', () => {
  test('creates a multi-draft batch and auto-starts bulk paste', async ({
    page,
  }) => {
    test.slow();

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
    await page.getByTestId('broadcast-import-select-all-checkbox').click();
    await page
      .getByTestId('broadcast-import-template-select')
      .selectOption({ label: 'Arrival Reminder' });
    await page.getByTestId('broadcast-import-apply-template-button').click();
    await page.getByTestId('broadcast-import-generate-drafts-button').click();
    await page
      .getByTestId('broadcast-import-generate-drafts-confirm-button')
      .click();

    await page.locator('[role="tab"]').nth(2).click();
    await page.getByTestId('broadcast-draft-select-all-checkbox').click();
    await page.getByTestId('broadcast-draft-batch-write-button').click();
    await page
      .getByTestId('broadcast-draft-batch-write-confirm-button')
      .click();

    await expect(
      page.getByTestId('broadcast-latest-execution-batch'),
    ).toBeVisible();
    await expect(
      page.getByTestId('broadcast-execution-logs-table'),
    ).toBeVisible();

    expect(requestPaths).toContain('/api/v1/broadcast/executions');
    expect(
      requestPaths.some((path) =>
        /\/api\/v1\/broadcast\/executions\/\d+\/start$/.test(path),
      ),
    ).toBeTruthy();
  });
});
