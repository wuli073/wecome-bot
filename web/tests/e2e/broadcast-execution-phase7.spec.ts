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
}

test.describe('broadcast execution phase 7', () => {
  test('shows disabled real send when backend flags are disabled', async ({
    page,
  }) => {
    await installLangBotApiMocks(page, {
      authenticated: true,
      storage: {
        langbot_language: 'en-US',
      },
      broadcastSendEnabled: false,
    });

    await prepareDraft(page);
    await expect(page.getByTestId('broadcast-draft-send-button')).toBeVisible();
    await expect(
      page.getByTestId('broadcast-draft-send-button'),
    ).toBeDisabled();
  });

  test('shows real send without using legacy confirmation routes', async ({
    page,
  }) => {
    await installLangBotApiMocks(page, {
      authenticated: true,
      storage: {
        langbot_language: 'en-US',
      },
      broadcastSendEnabled: true,
    });

    await prepareDraft(page);

    await expect(page.getByTestId('broadcast-draft-send-button')).toBeVisible();
    await expect(page.getByTestId('broadcast-draft-send-button')).toBeEnabled();
  });
});
