import { expect, test } from '@playwright/test';

import { installLangBotApiMocks } from './fixtures/langbot-api';

test.describe('broadcast import feedback', () => {
  test('shows worksheet name for uploaded xlsx batch', async ({ page }) => {
    await installLangBotApiMocks(page, {
      authenticated: true,
      storage: {
        langbot_language: 'zh-Hans',
      },
      bots: [
        {
          uuid: 'bot-1',
          name: 'Broadcast Bot A',
          enable: true,
          adapter: 'wxwork_database',
          adapter_config: {
            connector_id: 'wxwork-local',
          },
        },
      ],
    });

    await page.goto('/home/broadcast');
    await expect(page).toHaveURL(/\/home\/broadcast$/);

    await page.locator('[role="tab"]').nth(1).click();
    await page.getByTestId('broadcast-import-upload-input').setInputFiles({
      name: 'customers.xlsx',
      mimeType:
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      buffer: Buffer.from('fake xlsx', 'utf-8'),
    });

    await expect(page.locator('body')).toContainText(/工作表：Sheet1/);
  });

  test('shows chinese upload error instead of internal error code', async ({ page }) => {
    await installLangBotApiMocks(page, {
      authenticated: true,
      storage: {
        langbot_language: 'zh-Hans',
      },
      bots: [
        {
          uuid: 'bot-1',
          name: 'Broadcast Bot A',
          enable: true,
          adapter: 'wxwork_database',
          adapter_config: {
            connector_id: 'wxwork-local',
          },
        },
      ],
    });

    await page.route('**/api/v1/broadcast/imports', async (route) => {
      if (route.request().method() !== 'POST') {
        await route.fallback();
        return;
      }

      await route.fulfill({
        status: 400,
        contentType: 'application/json',
        body: JSON.stringify({
          code: -1,
          msg: 'BROADCAST_IMPORT_FILE_INVALID',
          message: '文件已损坏，请重新导出后再上传',
          details: [],
        }),
      });
    });

    await page.goto('/home/broadcast');
    await expect(page).toHaveURL(/\/home\/broadcast$/);

    await page.locator('[role="tab"]').nth(1).click();
    await page.getByTestId('broadcast-import-upload-input').setInputFiles({
      name: 'broken.xlsx',
      mimeType:
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      buffer: Buffer.from('broken', 'utf-8'),
    });

    await expect(page.locator('body')).toContainText(
      /文件已损坏，请重新导出后再上传/,
    );
    await expect(page.locator('body')).not.toContainText('BROADCAST_IMPORT_FILE_INVALID');
  });
});
