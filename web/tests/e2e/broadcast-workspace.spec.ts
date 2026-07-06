import { expect, test } from '@playwright/test';

import zhHans from '../../src/i18n/locales/zh-Hans';
import { installLangBotApiMocks } from './fixtures/langbot-api';

test.describe('broadcast workflow', () => {
  test('supports import and draft review without runtime calls', async ({
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
    await expect(page).toHaveURL(/\/home\/broadcast$/);

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
    await expect(page.getByTestId('broadcast-draft-queue')).toBeVisible();
    await expect(page.getByTestId('broadcast-draft-detail')).toBeVisible();
    await expect(
      page.getByTestId('broadcast-draft-batch-filter'),
    ).toBeVisible();
    await expect(
      page.getByTestId('broadcast-draft-confirm-button'),
    ).toHaveCount(0);
    await expect(page.getByTestId('broadcast-draft-revoke-button')).toHaveCount(
      0,
    );
    await expect(
      page.getByTestId('broadcast-draft-batch-confirm-button'),
    ).toHaveCount(0);
    await expect(
      page.getByTestId('broadcast-draft-batch-write-button'),
    ).toBeVisible();
    await expect(
      page.getByTestId('broadcast-draft-mark-sent-button'),
    ).toBeVisible();
    await expect(
      page.getByTestId('broadcast-draft-restore-pending-button'),
    ).toHaveCount(0);
    await expect(
      page.locator(
        '[data-testid^="broadcast-draft-select-"]:not([data-testid="broadcast-draft-select-all-checkbox"])',
      ),
    ).toHaveCount(2);

    await page.getByTestId('broadcast-draft-edit-button').click();
    await page
      .getByLabel(zhHans.broadcast.drafts.editor)
      .fill('Updated pending draft');
    await page.getByTestId('broadcast-draft-save-button').click();
    await expect(page.locator('body')).toContainText(
      zhHans.broadcast.toasts.draftSaved,
    );

    await page.getByTestId('broadcast-draft-paste-button').click();
    await expect(
      page.getByTestId('broadcast-draft-paste-confirm-dialog'),
    ).toHaveCount(0);
    await expect(
      page.getByTestId('broadcast-execution-logs-table'),
    ).toBeVisible();
    await page.locator('[role="tab"]').nth(2).click();

    await page.getByTestId('broadcast-draft-mark-sent-button').click();
    await expect(page.locator('body')).toContainText(
      zhHans.broadcast.toasts.draftsMarkedSent,
    );
    await expect(
      page.getByTestId('broadcast-draft-restore-pending-button'),
    ).toBeVisible();

    await page.getByTestId('broadcast-draft-select-1').check();
    await expect(
      page.getByTestId('broadcast-draft-batch-write-button'),
    ).toBeDisabled();
    await expect(
      page.getByTestId('broadcast-draft-batch-restore-pending-button'),
    ).toBeEnabled();

    expect(
      requestPaths.some((path) => path.includes('paste-draft')),
    ).toBeFalsy();
    expect(
      requestPaths.some((path) => path.includes('send-draft')),
    ).toBeFalsy();
    expect(
      requestPaths.some((path) => path.includes('send-confirmations')),
    ).toBeFalsy();
  });
});
