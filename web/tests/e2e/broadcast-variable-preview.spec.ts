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

test.describe('broadcast variable preview', () => {
  test('shows configured status instead of missing when mapping exists but no import batch exists', async ({
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

    const template = {
      id: 11,
      bot_uuid: 'bot-1',
      connector_id: 'wxwork-local',
      name: '查验通知',
      content: '查验通知：\n\n涉及单号如下：\n{{运单号}}',
      variables: ['运单号'],
      enabled: true,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    };
    const variableProfile = {
      group_field: '客户',
      mapping_rules: [
        {
          source_field: '运单号',
          variable_key: '运单号',
          merge_mode: 'first',
          order: 1,
        },
      ],
    };

    await page.route('**/api/v1/broadcast/templates*', async (route) => {
      if (route.request().method() !== 'GET') {
        await route.fallback();
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(ok([template])),
      });
    });

    await page.route('**/api/v1/broadcast/variable-profile*', async (route) => {
      if (route.request().method() !== 'GET') {
        await route.fallback();
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(ok(variableProfile)),
      });
    });

    await page.route('**/api/v1/broadcast/imports*', async (route) => {
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

    await page.route('**/api/v1/broadcast/templates/render', async (route) => {
      const body = route.request().postDataJSON() as {
        variables?: Record<string, string>;
      };
      const value = String(body.variables?.['运单号'] || '').trim();
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(
          ok({
            rendered_text: value
              ? `查验通知：\n\n涉及单号如下：\n${value}`
              : '查验通知：\n\n涉及单号如下：\n{{运单号}}',
            required_variables: ['运单号'],
            missing_variables: value ? [] : ['运单号'],
            valid: Boolean(value),
          }),
        ),
      });
    });

    await page.goto('/home/broadcast');
    await expect(page).toHaveURL(/\/home\/broadcast$/);

    await page.getByRole('tab', { name: '规则配置' }).click();
    await page.getByRole('tab', { name: '规则配置' }).click();
    await page.getByRole('tab', { name: '规则配置' }).click();
    await page.getByRole('tab', { name: '消息模板' }).click();

    const panel = page.getByTestId('broadcast-template-panel');
    await expect(panel).toContainText('运单号');
    await expect(panel).toContainText('已配置');
    await expect(panel).toContainText('{{运单号}}');
    await expect(panel).toContainText('暂无示例值');
    await expect(panel).not.toContainText('缺失');
  });

  test('updates variable sample and preview after successful import and keeps them after reload', async ({
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

    const template = {
      id: 11,
      bot_uuid: 'bot-1',
      connector_id: 'wxwork-local',
      name: '查验通知',
      content: '查验通知：\n\n涉及单号如下：\n{{运单号}}',
      variables: ['运单号'],
      enabled: true,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    };
    const variableProfile = {
      group_field: '客户',
      mapping_rules: [
        {
          source_field: '运单号',
          variable_key: '运单号',
          merge_mode: 'first',
          order: 1,
        },
      ],
    };
    const row = {
      id: 101,
      import_batch_id: 1,
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
    };
    const batch = {
      id: 1,
      bot_uuid: 'bot-1',
      connector_id: 'wxwork-local',
      original_file_name: 'customers.csv',
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
    let uploaded = false;

    await page.route('**/api/v1/broadcast/templates*', async (route) => {
      if (route.request().method() !== 'GET') {
        await route.fallback();
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(ok([template])),
      });
    });

    await page.route('**/api/v1/broadcast/variable-profile*', async (route) => {
      if (route.request().method() !== 'GET') {
        await route.fallback();
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(ok(variableProfile)),
      });
    });

    await page.route('**/api/v1/broadcast/imports*', async (route) => {
      const method = route.request().method();
      if (method === 'GET') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(ok(uploaded ? [batch] : [])),
        });
        return;
      }
      if (method === 'POST') {
        uploaded = true;
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(ok(batch)),
        });
        return;
      }
      await route.fallback();
    });

    await page.route('**/api/v1/broadcast/imports/1**', async (route) => {
      if (route.request().method() !== 'GET') {
        await route.fallback();
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(ok(makeImportPage(batch, [row]))),
      });
    });

    await page.route('**/api/v1/broadcast/templates/render', async (route) => {
      const body = route.request().postDataJSON() as {
        variables?: Record<string, string>;
      };
      const value = String(body.variables?.['运单号'] || '').trim();
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(
          ok({
            rendered_text: value
              ? `查验通知：\n\n涉及单号如下：\n${value}`
              : '查验通知：\n\n涉及单号如下：\n{{运单号}}',
            required_variables: ['运单号'],
            missing_variables: value ? [] : ['运单号'],
            valid: Boolean(value),
          }),
        ),
      });
    });

    await page.route(
      '**/api/v1/broadcast/imports/1/generate-drafts',
      async (route) => {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(
            ok({
              total_group_count: 1,
              pending_review_count: 1,
              invalid_count: 0,
              unmatched_group_count: 0,
            }),
          ),
        });
      },
    );

    await page.route('**/api/v1/broadcast/drafts**', async (route) => {
      if (route.request().method() !== 'GET') {
        await route.fallback();
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(
          ok(
            uploaded
              ? [
                  {
                    id: 201,
                    bot_uuid: 'bot-1',
                    connector_id: 'wxwork-local',
                    import_batch_id: 1,
                    group_value: '小满',
                    target_conversation_name: '小满',
                    template_id: 11,
                    template_name_snapshot: '查验通知',
                    template_content_snapshot: template.content,
                    render_variables: {
                      运单号: 'TEST-20260704-001',
                    },
                    draft_text:
                      '查验通知：\n\n涉及单号如下：\nTEST-20260704-001',
                    status: 'pending_review',
                    error_message: null,
                    drafts_stale: false,
                    created_at: new Date().toISOString(),
                    updated_at: new Date().toISOString(),
                  },
                ]
              : [],
          ),
        ),
      });
    });

    await page.goto('/home/broadcast');
    await expect(page).toHaveURL(/\/home\/broadcast$/);

    await page.getByRole('tab', { name: '导入匹配' }).click();
    await expect(
      page.getByRole('button', { name: '上传 CSV / XLSX' }),
    ).toBeEnabled();
    await page.getByTestId('broadcast-import-upload-input').setInputFiles({
      name: 'customers.csv',
      mimeType: 'text/csv',
      buffer: Buffer.from('客户,运单号\n小满,TEST-20260704-001\n', 'utf-8'),
    });

    await expect(page.locator('body')).toContainText('customers.csv');
    await expect(page.locator('body')).toContainText('共 1 行 / 已匹配 1');

    await page.getByRole('tab', { name: '规则配置' }).click();
    await expect(
      page.getByTestId('broadcast-variable-mapping-panel'),
    ).toContainText('TEST-20260704-001');
    await page.getByRole('tab', { name: '消息模板' }).click();
    const panel = page.getByTestId('broadcast-template-panel');
    await expect(panel).toContainText('{{运单号}}');
    await expect(panel).toContainText('TEST-20260704-001');
    await expect(panel).not.toContainText('缺失');
    await expect(panel.locator('pre')).toContainText(
      '涉及单号如下：\nTEST-20260704-001',
    );

    await page.getByRole('tab', { name: '导入匹配' }).click();
    await page.getByTestId('broadcast-import-template-select').click();
    await page.getByRole('option', { name: '查验通知' }).click();
    await page.getByTestId('broadcast-import-generate-drafts-button').click();

    await page.getByRole('tab', { name: '审核发送' }).click();
    await expect(page.locator('body')).toContainText('TEST-20260704-001');
    await expect(page.locator('body')).not.toContainText('{{运单号}}');

    await page.reload();
    await expect(page).toHaveURL(/\/home\/broadcast$/);
    await page.getByRole('tab', { name: '规则配置' }).click();
    await page.getByRole('tab', { name: '消息模板' }).click();
    await expect(page.getByTestId('broadcast-template-panel')).toContainText(
      'TEST-20260704-001',
    );
  });
});
