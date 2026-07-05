import { expect, test } from '@playwright/test';

import { installLangBotApiMocks } from './fixtures/langbot-api';

type BroadcastDiagnosticsSnapshot = {
  importBusyChanges?: Array<{ value?: boolean }>;
  renderCounts?: Record<string, number>;
};

function ok(data: unknown) {
  return {
    code: 0,
    message: 'ok',
    data,
    timestamp: Date.now(),
  };
}

function makeImportPage<T extends Record<string, unknown>>(
  batch: T,
  rows: unknown[],
  page = 1,
  pageSize = 50,
) {
  const total = Number(batch.total_rows ?? rows.length);
  return {
    ...batch,
    rows,
    page,
    page_size: pageSize,
    total,
    total_pages: total === 0 ? 0 : Math.ceil(total / pageSize),
  };
}

function makeGroupPage<T extends Record<string, unknown>>(
  batch: T,
  rows: Array<{
    id: number;
    source_row_number: number;
    group_value: string | null;
    matched_conversation_name: string | null;
    match_status: string;
    error_message: string | null;
    raw_data: Record<string, string>;
  }>,
  page = 1,
  pageSize = 50,
) {
  const groups = rows.map((row) => ({
    group_key: `group-${row.id}`,
    group_value: row.group_value ?? `invalid-${row.id}`,
    raw_row_count: 1,
    distinct_order_number_count: 1,
    matched_conversation_name: row.matched_conversation_name,
    match_status: row.match_status,
    reason: row.error_message,
    attachment_count: 0,
    attachments: [],
    expandable: true,
    first_source_row_number: row.source_row_number,
  }));
  const total = Number(batch.total_rows ?? groups.length);
  return {
    page,
    page_size: pageSize,
    total,
    total_pages: total === 0 ? 0 : Math.ceil(total / pageSize),
    raw_row_total: Number(batch.total_rows ?? rows.length),
    group_total: Number(batch.total_rows ?? rows.length),
    matched_group_total: Number(batch.matched_rows ?? 0),
    unmatched_group_total: Number(batch.unmatched_rows ?? 0),
    invalid_group_total: Number(batch.invalid_rows ?? 0),
    conflict_group_total: 0,
    order_number_field_configured: true,
    groups,
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
    await expect(
      page.getByRole('button', { name: '上传 CSV / XLSX' }),
    ).toBeEnabled();
    await page.getByTestId('broadcast-import-upload-input').setInputFiles({
      name: 'customers.xlsx',
      mimeType:
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      buffer: Buffer.from('fake xlsx', 'utf-8'),
    });

    await expect(page.locator('body')).toContainText(/工作表：Sheet1/);
  });

  test('shows chinese upload error instead of internal error code', async ({
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

    await expect(page.locator('body')).toContainText(
      '文件已损坏，请重新导出后再上传',
    );
    await expect(page.locator('body')).not.toContainText(
      'BROADCAST_IMPORT_FILE_INVALID',
    );
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
      ...makeImportPage(batch, [
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
      ]),
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
      if (
        request.method() === 'POST' &&
        url.pathname === '/api/v1/broadcast/imports'
      ) {
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
    await expect(
      page.getByRole('button', { name: '上传 CSV / XLSX' }),
    ).toBeEnabled();
    await expect(page.locator('body')).toContainText('existing.csv');
    await expect(page.locator('body')).toContainText('共 1 行 / 已匹配 1');

    const input = page.getByTestId('broadcast-import-upload-input');
    await input.setInputFiles({
      name: 'bad.csv',
      mimeType: 'text/csv',
      buffer: Buffer.from('客户\n小满\n', 'utf-8'),
    });

    await expect(page.locator('body')).toContainText(
      '导入文件缺少以下字段：运单号',
    );
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

    await expect(page.locator('body')).toContainText(
      '导入文件缺少以下字段：运单号',
    );
    expect(postCount).toBe(2);
  });

  test('paginates 155-row upload and ignores stale page responses', async ({
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
    const importDetailRequests: Array<{ page: number; pageSize: number }> = [];
    page.on('pageerror', (error) => {
      pageErrors.push(String(error));
    });
    page.on('console', (message) => {
      consoleMessages.push(message.text());
    });

    const rows = Array.from({ length: 155 }, (_, index) => ({
      id: index + 1,
      import_batch_id: 9,
      source_row_number: index + 2,
      raw_data: {
        user_name: `user-${index + 1}`,
        order_no: `WB-${String(index + 1).padStart(4, '0')}`,
      },
      group_value: `user-${index + 1}`,
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
    const detailByPage = new Map(
      [1, 2, 3, 4].map((pageNumber) => [
        pageNumber,
        makeImportPage(
          batch,
          rows.slice((pageNumber - 1) * 50, pageNumber * 50),
          pageNumber,
          50,
        ),
      ]),
    );

    let uploaded = false;
    let postCount = 0;
    let deleteCount = 0;

    await page.route('**/api/v1/broadcast/imports/9**', async (route) => {
      if (route.request().method() !== 'GET') {
        await route.fallback();
        return;
      }
      const url = new URL(route.request().url());
      if (url.pathname === '/api/v1/broadcast/imports/9/groups') {
        const pageNumber = Number(url.searchParams.get('page') || '1');
        const pageSize = Number(url.searchParams.get('page_size') || '50');
        importDetailRequests.push({ page: pageNumber, pageSize });
        if (pageNumber === 3) {
          await new Promise((resolve) => setTimeout(resolve, 250));
        } else if (pageNumber === 1 && importDetailRequests.length > 3) {
          await new Promise((resolve) => setTimeout(resolve, 25));
        }
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(
            ok(
              makeGroupPage(
                batch,
                rows.slice((pageNumber - 1) * 50, pageNumber * 50),
                pageNumber,
                50,
              ),
            ),
          ),
        });
        return;
      }
      const pageNumber = Number(url.searchParams.get('page') || '1');
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(
          ok(detailByPage.get(pageNumber) ?? detailByPage.get(1)),
        ),
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

      if (
        request.method() === 'GET' &&
        url.pathname === '/api/v1/broadcast/imports'
      ) {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(ok(uploaded ? [batch] : [])),
        });
        return;
      }

      if (
        request.method() === 'POST' &&
        url.pathname === '/api/v1/broadcast/imports'
      ) {
        uploaded = true;
        postCount += 1;
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(ok(batch)),
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
    const uploadResponsePromise = page.waitForResponse((response) => {
      const url = new URL(response.url());
      return (
        response.request().method() === 'POST' &&
        url.pathname === '/api/v1/broadcast/imports'
      );
    });
    const firstPageRequestPromise = page.waitForRequest((request) => {
      const url = new URL(request.url());
      return (
        request.method() === 'GET' &&
        url.pathname === '/api/v1/broadcast/imports/9/groups' &&
        url.searchParams.get('page') === '1' &&
        url.searchParams.get('page_size') === '50'
      );
    });
    await uploadInput.setInputFiles({
      name: 'customers-155.xlsx',
      mimeType:
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      buffer: Buffer.from('fake-xlsx-content', 'utf-8'),
    });
    const uploadResponse = await uploadResponsePromise;
    const uploadJson = (await uploadResponse.json()) as {
      data?: Record<string, unknown>;
    };
    expect(uploadJson.data?.rows).toBeUndefined();
    await firstPageRequestPromise;

    await expect(page.locator('body')).toContainText('customers-155.xlsx');
    await expect(page.locator('body')).toContainText('Sheet1');
    await expect(page.locator('body')).toContainText('155');
    await expect(page.getByTestId('broadcast-import-pagination')).toContainText(
      /1\s*\/\s*4/,
    );
    await expect(page.locator('body')).toContainText(/155\s*?/);
    await expect(
      page.locator('[data-testid="broadcast-import-table"] tbody tr'),
    ).toHaveCount(50);
    await expect(
      page.locator('[data-testid="broadcast-import-table"]'),
    ).toContainText('user-1');
    await expect(
      page.locator('[data-testid="broadcast-import-table"]'),
    ).toContainText('user-50');

    const pagination = page.getByTestId('broadcast-import-pagination');
    const nextPageButton = pagination.locator(
      'xpath=following-sibling::button[1]',
    );

    const page2RequestPromise = page.waitForRequest((request) => {
      const url = new URL(request.url());
      return (
        request.method() === 'GET' &&
        url.pathname === '/api/v1/broadcast/imports/9/groups' &&
        url.searchParams.get('page') === '2' &&
        url.searchParams.get('page_size') === '50'
      );
    });
    await nextPageButton.dispatchEvent('click');
    await page2RequestPromise;
    await expect(page.getByTestId('broadcast-import-pagination')).toContainText(
      /2\s*\/\s*4/,
    );
    await expect(
      page.locator('[data-testid="broadcast-import-table"] tbody tr'),
    ).toHaveCount(50);
    await expect(
      page.locator('[data-testid="broadcast-import-table"]'),
    ).toContainText('user-51');
    await expect(
      page.locator('[data-testid="broadcast-import-table"]'),
    ).toContainText('user-100');

    const page3RequestPromise = page.waitForRequest((request) => {
      const url = new URL(request.url());
      return (
        request.method() === 'GET' &&
        url.pathname === '/api/v1/broadcast/imports/9/groups' &&
        url.searchParams.get('page') === '3' &&
        url.searchParams.get('page_size') === '50'
      );
    });
    const page1FromPage2RequestPromise = page.waitForRequest((request) => {
      const url = new URL(request.url());
      return (
        request.method() === 'GET' &&
        url.pathname === '/api/v1/broadcast/imports/9/groups' &&
        url.searchParams.get('page') === '1' &&
        url.searchParams.get('page_size') === '50'
      );
    });
    await page.evaluate(() => {
      const pagination = document.querySelector(
        '[data-testid="broadcast-import-pagination"]',
      );
      if (!pagination) {
        throw new Error('broadcast import pagination not found');
      }
      const previousButton =
        pagination.previousElementSibling as HTMLButtonElement | null;
      const nextButton =
        pagination.nextElementSibling as HTMLButtonElement | null;
      if (!previousButton || !nextButton) {
        throw new Error('broadcast import pagination buttons not found');
      }
      nextButton.click();
      previousButton.click();
    });
    await page3RequestPromise;
    await page1FromPage2RequestPromise;

    await expect(page.getByTestId('broadcast-import-pagination')).toContainText(
      /1\s*\/\s*4/,
    );
    await expect(
      page.locator('[data-testid="broadcast-import-table"] tbody tr'),
    ).toHaveCount(50);
    await expect(
      page.locator('[data-testid="broadcast-import-table"]'),
    ).toContainText('user-1');
    await expect(
      page.locator('[data-testid="broadcast-import-table"]'),
    ).not.toContainText('user-151');

    expect(postCount).toBe(1);
    expect(deleteCount).toBe(0);
    expect(pageErrors).toEqual([]);
    expect(
      consoleMessages.some((message) =>
        /Maximum update depth|unhandled rejection|Uncaught/i.test(message),
      ),
    ).toBeFalsy();
    expect(importDetailRequests).toEqual([
      { page: 1, pageSize: 50 },
      { page: 2, pageSize: 50 },
      { page: 3, pageSize: 50 },
      { page: 1, pageSize: 50 },
    ]);
  });

  test('reloads first page for a new batch after deleting the only batch', async ({
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

    const batchA = {
      id: 9,
      bot_uuid: 'bot-1',
      connector_id: 'wxwork-local',
      original_file_name: 'batch-a.xlsx',
      file_type: 'xlsx',
      worksheet_name: 'SheetA',
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
    const batchB = {
      id: 12,
      bot_uuid: 'bot-1',
      connector_id: 'wxwork-local',
      original_file_name: 'batch-b.xlsx',
      file_type: 'xlsx',
      worksheet_name: 'Sheet1',
      status: 'imported',
      drafts_stale: false,
      total_rows: 155,
      valid_rows: 155,
      invalid_rows: 0,
      matched_rows: 1,
      unmatched_rows: 154,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    };
    const batchADetail = makeImportPage(batchA, [
      {
        id: 901,
        import_batch_id: 9,
        source_row_number: 2,
        raw_data: {
          customer_name: 'alpha',
          order_no: 'A-001',
        },
        group_value: 'alpha',
        matched_conversation_name: 'alpha',
        matched_rule_id: 1,
        match_status: 'matched',
        error_message: null,
        created_at: new Date().toISOString(),
      },
    ]);
    const batchBRows = Array.from({ length: 155 }, (_, index) => ({
      id: 1201 + index,
      import_batch_id: 12,
      source_row_number: index + 2,
      raw_data: {
        customer_name: `customer-${index + 1}`,
        order_no: `B-${String(index + 1).padStart(3, '0')}`,
      },
      group_value: `customer-${index + 1}`,
      matched_conversation_name: index === 0 ? 'customer-1' : null,
      matched_rule_id: index === 0 ? 2 : null,
      match_status: index === 0 ? 'matched' : 'unmatched',
      error_message: null,
      created_at: new Date().toISOString(),
    }));
    const batchBDetailByPage = new Map(
      [1, 2, 3, 4].map((pageNumber) => [
        pageNumber,
        makeImportPage(
          batchB,
          batchBRows.slice((pageNumber - 1) * 50, pageNumber * 50),
          pageNumber,
          50,
        ),
      ]),
    );

    const batchesState: Array<typeof batchA | typeof batchB> = [batchA];
    let broadcastApiRequestCount = 0;
    let importListRequestsAfterUpload = 0;
    let postResponseBatchId: number | null = null;
    const detailRequestLog: Array<{ importId: number; page: number }> = [];

    await page.route('**/api/v1/broadcast/imports/9**', async (route) => {
      const request = route.request();
      const url = new URL(request.url());
      if (
        request.method() === 'GET' &&
        url.pathname === '/api/v1/broadcast/imports/9'
      ) {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(ok(batchADetail)),
        });
        return;
      }
      if (
        request.method() === 'DELETE' &&
        url.pathname === '/api/v1/broadcast/imports/9'
      ) {
        batchesState.splice(0, batchesState.length);
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(ok({ deleted: true })),
        });
        return;
      }
      await route.fallback();
    });

    await page.route('**/api/v1/broadcast/imports/12**', async (route) => {
      const request = route.request();
      if (request.method() !== 'GET') {
        await route.fallback();
        return;
      }
      broadcastApiRequestCount += 1;
      const url = new URL(request.url());
      if (url.pathname === '/api/v1/broadcast/imports/12/groups') {
        const pageNumber = Number(url.searchParams.get('page') || '1');
        detailRequestLog.push({ importId: 12, page: pageNumber });
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(
            ok(
              makeGroupPage(
                batchB,
                batchBRows.slice((pageNumber - 1) * 50, pageNumber * 50),
                pageNumber,
                50,
              ),
            ),
          ),
        });
        return;
      }
      const pageNumber = Number(url.searchParams.get('page') || '1');
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(
          ok(batchBDetailByPage.get(pageNumber) ?? batchBDetailByPage.get(1)),
        ),
      });
    });

    await page.route('**/api/v1/broadcast/imports*', async (route) => {
      const request = route.request();
      const url = new URL(request.url());
      broadcastApiRequestCount += 1;

      if (
        request.method() === 'GET' &&
        url.pathname === '/api/v1/broadcast/imports'
      ) {
        if (postResponseBatchId === batchB.id) {
          importListRequestsAfterUpload += 1;
        }
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(ok([...batchesState])),
        });
        return;
      }

      if (
        request.method() === 'POST' &&
        url.pathname === '/api/v1/broadcast/imports'
      ) {
        await new Promise((resolve) => setTimeout(resolve, 50));
        batchesState.splice(0, batchesState.length, batchB);
        postResponseBatchId = batchB.id;
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(ok(batchB)),
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
    await page.locator('[role="tab"]').nth(1).click();

    await expect(page.locator('body')).toContainText('batch-a.xlsx');
    await expect(page.locator('body')).toContainText('SheetA');
    const importPanelRenderCountBefore = await page.evaluate(() => {
      return (
        window.__BROADCAST_DIAGNOSTICS__?.getSnapshot()?.renderCounts
          ?.ImportMatchingPanel ?? 0
      );
    });

    const deleteResponsePromise = page.waitForResponse((response) => {
      const url = new URL(response.url());
      return (
        response.request().method() === 'DELETE' &&
        url.pathname === '/api/v1/broadcast/imports/9'
      );
    });
    const deleteRefreshRequestPromise = page.waitForRequest((request) => {
      const url = new URL(request.url());
      return (
        request.method() === 'GET' &&
        url.pathname === '/api/v1/broadcast/imports'
      );
    });
    const uploadResponsePromise = page.waitForResponse((response) => {
      const url = new URL(response.url());
      return (
        response.request().method() === 'POST' &&
        url.pathname === '/api/v1/broadcast/imports'
      );
    });
    const newBatchPageRequestPromise = page.waitForRequest((request) => {
      const url = new URL(request.url());
      return (
        request.method() === 'GET' &&
        url.pathname === `/api/v1/broadcast/imports/${batchB.id}/groups` &&
        url.searchParams.get('page') === '1' &&
        url.searchParams.get('page_size') === '50'
      );
    });

    await page.getByTestId('broadcast-import-delete-batch-button').click();

    await deleteResponsePromise;
    await deleteRefreshRequestPromise;
    await expect(page.locator('body')).toContainText('暂无导入批次');
    await expect(
      page.locator('[data-broadcast-import-busy-count]'),
    ).toHaveAttribute('data-broadcast-import-busy-count', '0');
    await expect(
      page.getByTestId('broadcast-import-upload-button'),
    ).toBeEnabled();

    await page.getByTestId('broadcast-import-upload-input').setInputFiles({
      name: 'batch-b.xlsx',
      mimeType:
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      buffer: Buffer.from('fake-xlsx-content', 'utf-8'),
    });

    const uploadResponse = await uploadResponsePromise;

    const uploadJson = (await uploadResponse.json()) as {
      data?: { id?: number };
    };
    const uploadedBatchId = uploadJson.data?.id ?? null;
    expect(uploadedBatchId).toBe(batchB.id);

    const newBatchPageRequest = await newBatchPageRequestPromise;
    expect(new URL(newBatchPageRequest.url()).pathname).toBe(
      `/api/v1/broadcast/imports/${postResponseBatchId}/groups`,
    );

    await expect(page.locator('body')).toContainText('batch-b.xlsx');
    await expect(page.locator('body')).toContainText('Sheet1');
    await expect(
      page.getByTestId('broadcast-import-total-items'),
    ).toContainText('155');
    await expect(page.getByTestId('broadcast-import-pagination')).toContainText(
      /1\s*\/\s*4/,
    );
    await expect(
      page.locator('[data-testid="broadcast-import-table"]'),
    ).toContainText('customer-1');
    await expect(
      page.locator('[data-testid="broadcast-import-table"]'),
    ).toContainText('customer-50');
    await expect(
      page.locator('[data-testid="broadcast-import-table"] tbody tr'),
    ).toHaveCount(50);
    await expect(
      page.getByTestId('broadcast-import-upload-button'),
    ).toBeEnabled();
    await expect(page.getByRole('tab').nth(0)).toBeEnabled();
    await expect(page.getByTestId('broadcast-import-next-page')).toBeEnabled();

    await expect
      .poll(async () => page.evaluate(() => 1 + 1), {
        timeout: 1000,
      })
      .toBe(2);

    await page.getByRole('tab', { name: '规则配置' }).click();
    await expect(page.getByRole('tab', { name: '消息模板' })).toBeVisible();
    await page.getByRole('tab', { name: '导入匹配' }).click();

    const page2RequestPromise = page.waitForRequest((request) => {
      const url = new URL(request.url());
      return (
        request.method() === 'GET' &&
        url.pathname === `/api/v1/broadcast/imports/${batchB.id}/groups` &&
        url.searchParams.get('page') === '2' &&
        url.searchParams.get('page_size') === '50'
      );
    });
    await page.getByTestId('broadcast-import-next-page').click();
    await page2RequestPromise;
    await expect(page.getByTestId('broadcast-import-pagination')).toContainText(
      /2\s*\/\s*4/,
    );
    await expect(
      page.locator('[data-testid="broadcast-import-table"]'),
    ).toContainText('customer-51');

    expect(detailRequestLog).toEqual([
      { importId: batchB.id, page: 1 },
      { importId: batchB.id, page: 2 },
    ]);

    const diagnostics = await page.evaluate<BroadcastDiagnosticsSnapshot>(
      () => {
        return (
          window.__BROADCAST_DIAGNOSTICS__?.getSnapshot() ?? {
            importBusyChanges: [],
            renderCounts: {},
          }
        );
      },
    );
    expect(diagnostics.importBusyChanges?.at(-1)?.value).toBe(false);
    await expect(
      page.locator('[data-broadcast-import-busy-count]'),
    ).toHaveAttribute('data-broadcast-import-busy-count', '0');
    const importMatchingPanelRenderCount =
      diagnostics.renderCounts?.ImportMatchingPanel ?? 0;
    expect(importMatchingPanelRenderCount).toBeLessThan(
      importPanelRenderCountBefore + 50,
    );

    const importListRequestsAfterUploadBaseline = importListRequestsAfterUpload;
    const broadcastApiRequestCountBaseline = broadcastApiRequestCount;
    await expect
      .poll(() => importListRequestsAfterUpload, {
        timeout: 5000,
        intervals: [250, 500, 1000],
      })
      .toBeLessThanOrEqual(importListRequestsAfterUploadBaseline + 1);
    await expect
      .poll(() => broadcastApiRequestCount, {
        timeout: 5000,
        intervals: [250, 500, 1000],
      })
      .toBeLessThanOrEqual(broadcastApiRequestCountBaseline + 1);
    await expect(page.locator('body')).not.toContainText('暂无导入批次');
  });

  test('successful upload loads detail without runtime page errors', async ({
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
    page.on('pageerror', (error) => {
      pageErrors.push(String(error));
    });

    const batch = {
      id: 21,
      bot_uuid: 'bot-1',
      connector_id: 'wxwork-local',
      original_file_name: 'uploaded.xlsx',
      file_type: 'xlsx',
      worksheet_name: 'Sheet1',
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
    const detail = makeImportPage(
      batch,
      [
        {
          id: 2101,
          import_batch_id: 21,
          source_row_number: 2,
          raw_data: {
            customer_name: 'Acme',
          },
          group_value: 'Acme',
          matched_conversation_name: 'Acme Group',
          matched_rule_id: 1,
          match_status: 'matched',
          error_message: null,
          created_at: new Date().toISOString(),
        },
      ],
      1,
      50,
    );
    const groups = makeGroupPage(
      batch,
      [
        {
          id: 2101,
          source_row_number: 2,
          group_value: 'Acme',
          matched_conversation_name: 'Acme Group',
          match_status: 'matched',
          error_message: null,
          raw_data: { customer_name: 'Acme' },
        },
      ],
      1,
      50,
    );

    await page.route('**/api/v1/broadcast/imports*', async (route) => {
      const request = route.request();
      const url = new URL(request.url());
      if (
        request.method() === 'POST' &&
        url.pathname === '/api/v1/broadcast/imports'
      ) {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(ok(batch)),
        });
        return;
      }
      if (
        request.method() === 'GET' &&
        url.pathname === '/api/v1/broadcast/imports'
      ) {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(ok([batch])),
        });
        return;
      }
      if (
        request.method() === 'GET' &&
        url.pathname === '/api/v1/broadcast/imports/21'
      ) {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(ok(detail)),
        });
        return;
      }
      if (
        request.method() === 'GET' &&
        url.pathname === '/api/v1/broadcast/imports/21/groups'
      ) {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(ok(groups)),
        });
        return;
      }
      await route.fallback();
    });

    await page.goto('/home/broadcast');
    await expect(page).toHaveURL(/\/home\/broadcast$/);
    await page.locator('[role="tab"]').nth(1).click();
    await page.getByTestId('broadcast-import-upload-input').setInputFiles({
      name: 'uploaded.xlsx',
      mimeType:
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      buffer: Buffer.from('uploaded-xlsx', 'utf-8'),
    });

    await expect(page.locator('body')).toContainText('uploaded.xlsx');
    await expect(page.locator('body')).toContainText('Sheet1');
    expect(pageErrors).toEqual([]);
  });
});
