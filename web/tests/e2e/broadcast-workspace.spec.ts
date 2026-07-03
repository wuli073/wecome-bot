import { expect, test } from '@playwright/test';

import { installLangBotApiMocks } from './fixtures/langbot-api';

test.describe('broadcast workflow', () => {
  test('supports import and draft review without runtime calls', async ({ page }) => {
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
    await expect(page.getByText('pending_review')).toHaveCount(0);
    await expect(page.getByText('ready')).toHaveCount(0);
    await expect(page.getByTestId('broadcast-draft-batch-filter')).toBeVisible();
    await expect(page.getByTestId('broadcast-draft-confirm-button')).toBeVisible();
    await expect(page.getByTestId('broadcast-draft-revoke-button')).toBeVisible();
    await expect(page.getByTestId('broadcast-draft-batch-confirm-button')).toBeVisible();

    await page.getByTestId('broadcast-draft-confirm-button').click();
    await expect(page.getByText('草稿已确认')).toBeVisible();

    await page.getByTestId('broadcast-draft-edit-button').click();
    await page.getByLabel('草稿编辑器').fill('Updated ready draft');
    await page.getByTestId('broadcast-draft-save-button').click();
    await expect(page.getByText('草稿内容已修改，请重新确认')).toBeVisible();

    await page.getByRole('checkbox', { name: /选择草稿/ }).first().check();
    await expect(page.getByTestId('broadcast-draft-batch-confirm-button')).toBeEnabled();
    await expect(page.getByRole('checkbox', { name: /选择草稿 3/ })).toBeDisabled();

    await page.locator('[role="tab"]').nth(1).click();
    await page.getByTestId('broadcast-import-rematch-button').click();
    await page.locator('[role="tab"]').nth(2).click();
    await expect(page.getByText('草稿已过期，请重新生成')).toBeVisible();
    await expect(page.getByRole('checkbox', { name: /选择草稿 1/ })).toBeDisabled();
    await expect(page.getByTestId('broadcast-draft-confirm-button')).toBeDisabled();

    expect(requestPaths.some((path) => path.includes('paste-draft'))).toBeFalsy();
    expect(requestPaths.some((path) => path.includes('send-draft'))).toBeFalsy();
  });
});
