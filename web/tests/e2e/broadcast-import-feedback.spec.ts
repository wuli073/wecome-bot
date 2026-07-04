import { expect, test } from '@playwright/test';

import { installLangBotApiMocks } from './fixtures/langbot-api';

function ok(data: unknown) {
  return {
    code: 0,
    message: 'ok',
    data,
    timestamp: Date.now(),
  };
}

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

    await page.route('**/api/v1/broadcast/imports*', async (route) => {
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

    await expect(page.locator('body')).toContainText('文件已损坏，请重新导出后再上传');
    await expect(page.locator('body')).not.toContainText('BROADCAST_IMPORT_FILE_INVALID');
  });

  test('keeps page interactive and preserves previous batch after failed upload', async ({
    page,
  }) => {
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

    const batch = {
      id: 9,
      bot_uuid: 'bot-1',
      connector_id: 'wxwork-local',
      original_file_name: 'existing.csv',
      file_type: 'csv',
      worksheet_name: null,
      status: 'imported',
      drafts_stale: false,
      total_rows: 1,
      valid_rows: 1,
      invalid_rows: 0,
      matched_rows: 1,
      unmatched_rows: 0,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    };
    const detail = {
      ...batch,
      rows: [
        {
          id: 91,
          import_batch_id: 9,
          source_row_number: 2,
          raw_data: {
            客户: '小满',
            运单号: 'TEST-20260704-001',
          },
          group_value: '小满',
          matched_conversation_name: '小满',
          matched_rule_id: 1,
          match_status: 'matched',
          error_message: null,
          created_at: new Date().toISOString(),
        },
      ],
    };
    let postCount = 0;

    await page.route('**/api/v1/broadcast/imports*', async (route) => {
      const request = route.request();
      const url = new URL(request.url());
      if (request.method() === 'GET') {
        if (url.pathname === '/api/v1/broadcast/imports') {
          await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify(ok([batch])),
          });
          return;
        }
        if (url.pathname === '/api/v1/broadcast/imports/9') {
          await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify(ok(detail)),
          });
          return;
        }
      }
      if (request.method() === 'POST' && url.pathname === '/api/v1/broadcast/imports') {
        postCount += 1;
        await route.fulfill({
          status: 400,
          contentType: 'application/json',
          body: JSON.stringify({
            code: -1,
            msg: 'BROADCAST_IMPORT_FIELDS_MISSING',
            message: '导入文件缺少以下字段：运单号',
            details: ['运单号'],
          }),
        });
        return;
      }
      await route.fallback();
    });

    await page.goto('/home/broadcast');
    await expect(page).toHaveURL(/\/home\/broadcast$/);

    await page.locator('[role="tab"]').nth(1).click();
    await expect(page.locator('body')).toContainText('existing.csv');
    await expect(page.locator('body')).toContainText('共 1 行 / 已匹配 1');

    const input = page.getByTestId('broadcast-import-upload-input');
    await input.setInputFiles({
      name: 'bad.csv',
      mimeType: 'text/csv',
      buffer: Buffer.from('客户\n小满\n', 'utf-8'),
    });

    await expect(page.locator('body')).toContainText('导入文件缺少以下字段：运单号');
    await expect(page.locator('body')).toContainText('existing.csv');
    await expect(page.locator('body')).toContainText('共 1 行 / 已匹配 1');
    await expect(page.getByRole('tab', { name: '规则配置' })).toBeEnabled();
    await page.getByRole('tab', { name: '规则配置' }).click();
    await expect(page.getByRole('tab', { name: '消息模板' })).toBeVisible();

    await page.getByRole('tab', { name: '导入匹配' }).click();
    await input.setInputFiles({
      name: 'bad.csv',
      mimeType: 'text/csv',
      buffer: Buffer.from('客户\n小满\n', 'utf-8'),
    });

    await expect(page.locator('body')).toContainText('导入文件缺少以下字段：运单号');
    expect(postCount).toBe(2);
  });

  test('keeps page interactive after successful 155-row upload without implicit delete', async ({
    page,
  }) => {
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

    const pageErrors: string[] = [];
    const consoleMessages: string[] = [];
    const requestPaths: string[] = [];
    page.on('pageerror', (error) => {
      pageErrors.push(String(error));
    });
    page.on('console', (message) => {
      consoleMessages.push(message.text());
    });
    page.on('request', (request) => {
      requestPaths.push(`${request.method()} ${new URL(request.url()).pathname}`);
    });

    const rows = Array.from({ length: 155 }, (_, index) => ({
      id: index + 1,
      import_batch_id: 9,
      source_row_number: index + 2,
      raw_data: {
        用户名: `用户-${index + 1}`,
        运单号: `WB-${String(index + 1).padStart(4, '0')}`,
      },
      group_value: `用户-${index + 1}`,
      matched_conversation_name: null,
      matched_rule_id: null,
      match_status: 'unmatched',
      error_message: null,
      created_at: new Date().toISOString(),
    }));
    const batch = {
      id: 9,
      bot_uuid: 'bot-1',
      connector_id: 'wxwork-local',
      original_file_name: 'customers-155.xlsx',
      file_type: 'xlsx',
      worksheet_name: 'Sheet1',
      status: 'imported',
      drafts_stale: false,
      total_rows: 155,
      valid_rows: 155,
      invalid_rows: 0,
      matched_rows: 0,
      unmatched_rows: 155,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    };
    const detail = {
      ...batch,
      rows,
    };

    let uploaded = false;
    let postCount = 0;
    let deleteCount = 0;

    await page.route('**/api/v1/broadcast/imports/9**', async (route) => {
      if (route.request().method() !== 'GET') {
        await route.fallback();
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(ok(detail)),
      });
    });

    await page.route('**/api/v1/broadcast/imports*', async (route) => {
      const request = route.request();
      const url = new URL(request.url());

      if (request.method() === 'DELETE') {
        deleteCount += 1;
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(ok({ deleted: true })),
        });
        return;
      }

      if (request.method() === 'GET') {
        if (url.pathname === '/api/v1/broadcast/imports') {
          await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify(ok(uploaded ? [batch] : [])),
          });
          return;
        }
      }

      if (request.method() === 'POST' && url.pathname === '/api/v1/broadcast/imports') {
        uploaded = true;
        postCount += 1;
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(ok(detail)),
        });
        return;
      }

      await route.fallback();
    });

    await page.route('**/api/v1/broadcast/drafts*', async (route) => {
      if (route.request().method() !== 'GET') {
        await route.fallback();
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(ok([])),
      });
    });

    await page.goto('/home/broadcast');
    await expect(page).toHaveURL(/\/home\/broadcast$/);

    const topTabs = page.getByRole('tab');
    await topTabs.nth(1).click();

    const uploadInput = page.getByTestId('broadcast-import-upload-input');
    await uploadInput.setInputFiles({
      name: 'customers-155.xlsx',
      mimeType:
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      buffer: Buffer.from('fake-xlsx-content', 'utf-8'),
    });

    await expect(page.locator('body')).toContainText('customers-155.xlsx');
    await expect(page.locator('body')).toContainText('Sheet1');
    await expect(page.locator('body')).toContainText('总行数');
    await expect(page.locator('body')).toContainText('155');
    await expect(page.locator('body')).toContainText('未匹配');
    await expect(page.locator('body')).toContainText('无效');

    for (const index of [0, 1, 2, 3]) {
      await topTabs.nth(index).click();
      await expect(topTabs.nth(index)).toHaveAttribute('aria-selected', 'true');
    }

    await topTabs.nth(1).click();
    await uploadInput.setInputFiles({
      name: 'customers-155.xlsx',
      mimeType:
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      buffer: Buffer.from('fake-xlsx-content', 'utf-8'),
    });

    await expect(page.locator('body')).toContainText('customers-155.xlsx');
    expect(postCount).toBe(2);
    expect(deleteCount).toBe(0);
    expect(pageErrors).toEqual([]);
    expect(
      consoleMessages.some((message) =>
        /Maximum update depth|unhandled rejection|Uncaught/i.test(message),
      ),
    ).toBeFalsy();

    const importsRequestCount = requestPaths.filter(
      (path) => path === 'GET /api/v1/broadcast/imports',
    ).length;
    const draftsRequestCount = requestPaths.filter(
      (path) => path === 'GET /api/v1/broadcast/drafts',
    ).length;
    expect(importsRequestCount).toBeLessThanOrEqual(4);
    expect(draftsRequestCount).toBeLessThanOrEqual(4);
  });
});
