import { expect, test } from '@playwright/test';

import zhHans from '../../src/i18n/locales/zh-Hans';
import { installLangBotApiMocks } from './fixtures/langbot-api';

test.describe('broadcast workflow', () => {
  test('bulk assigns new customers for a username-detected batch', async ({
    page,
  }) => {
    await installLangBotApiMocks(page, {
      authenticated: true,
      storage: {
        langbot_language: 'en-US',
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

    let bulkAssignBody:
      | {
          items?: Array<{
            group_key?: string;
            target_conversation_id?: string;
          }>;
        }
      | undefined;
    await page.route(
      '**/api/v1/broadcast/imports/*/group-rules/bulk-assign',
      async (route) => {
        if (route.request().method() === 'POST') {
          bulkAssignBody = route
            .request()
            .postDataJSON() as typeof bulkAssignBody;
        }
        await route.fallback();
      },
    );

    await page.goto('/home/broadcast');
    await expect(page).toHaveURL(/\/home\/broadcast$/);
    await page.locator('[role="tab"]').nth(1).click();
    await page.getByTestId('broadcast-import-upload-input').setInputFiles({
      name: 'username-import.xlsx',
      mimeType:
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      buffer: Buffer.from('username-import', 'utf-8'),
    });

    await expect(page.locator('body')).toContainText(
      /Detected customer field for this batch:\s*用户名/,
    );
    await expect(
      page.getByTestId('broadcast-import-bulk-assign-open-button'),
    ).toContainText('(1)');

    await page.getByTestId('broadcast-import-bulk-assign-open-button').click();
    const dialog = page.getByTestId('broadcast-import-bulk-assign-dialog');
    await expect(dialog).toBeVisible();
    await expect(dialog).toContainText('northwind_user');
    await expect(
      dialog.getByRole('button', { name: /Apply to selected customers/ }),
    ).toContainText('(1)');
    await dialog
      .getByRole('button', { name: 'Northwind Service Group' })
      .click();
    await dialog
      .getByRole('button', { name: /Apply to selected customers/ })
      .click();
    await dialog
      .getByRole('button', { name: /Create rules and rematch/ })
      .click();

    await expect(dialog).toHaveCount(0);

    expect(bulkAssignBody).toMatchObject({
      items: [
        {
          target_conversation_id: 'northwind-service-group',
        },
      ],
    });

    const northwindRow = page
      .locator('[data-testid="broadcast-import-table"] tbody tr')
      .filter({
        hasText: 'northwind_user',
      });
    await expect(northwindRow).toContainText('Northwind Service Group');
    await expect(
      page.getByTestId('broadcast-import-bulk-assign-open-button'),
    ).toContainText('(0)');
  });

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
    const templateAssignmentBodies: Array<{
      items?: Array<{ group_key?: string; template_id?: number | null }>;
    }> = [];
    page.on('request', (request) => {
      const url = new URL(request.url());
      if (url.pathname.startsWith('/api/v1/')) {
        requestPaths.push(url.pathname);
      }
      if (
        url.pathname.includes('/group-template-assignments') &&
        request.method() === 'PUT'
      ) {
        templateAssignmentBodies.push(
          (request.postDataJSON() as {
            items?: Array<{ group_key?: string; template_id?: number | null }>;
          }) ?? {},
        );
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
    await page.getByTestId('broadcast-import-select-all-checkbox').click();
    await page
      .getByTestId('broadcast-import-template-select')
      .selectOption({ label: 'Arrival Reminder' });
    await page.getByTestId('broadcast-import-apply-template-button').click();
    await expect(
      page.getByTestId('broadcast-import-apply-template-unassigned-button'),
    ).toBeDisabled();
    await page
      .locator('[data-testid^="broadcast-import-group-clear-template-button-"]')
      .first()
      .click();
    await page.getByTestId('broadcast-import-clear-templates-button').click();
    await expect(
      page.getByTestId('broadcast-import-clear-templates-confirm-dialog'),
    ).toBeVisible();
    await page
      .getByTestId('broadcast-import-clear-templates-confirm-button')
      .click();
    await expect(
      page.getByTestId('broadcast-import-clear-templates-confirm-dialog'),
    ).toHaveCount(0);
    await page
      .getByTestId('broadcast-import-template-select')
      .selectOption({ label: 'Arrival Reminder' });
    await page
      .getByTestId('broadcast-import-apply-template-unassigned-button')
      .click();
    await expect(
      page.getByTestId('broadcast-import-generate-drafts-button'),
    ).toBeEnabled();
    await page.getByTestId('broadcast-import-generate-drafts-button').click();
    await page
      .getByTestId('broadcast-import-generate-drafts-confirm-button')
      .click();

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
    expect(
      templateAssignmentBodies.some((body) =>
        (body.items ?? []).some((item) => item.template_id === 0),
      ),
    ).toBeFalsy();
    expect(
      templateAssignmentBodies.some((body) =>
        (body.items ?? []).some((item) => item.template_id === null),
      ),
    ).toBeTruthy();
  });

  test('creates an exact match rule directly from an unmatched import group', async ({
    page,
  }) => {
    await installLangBotApiMocks(page, {
      authenticated: true,
      storage: {
        langbot_language: 'zh-Hans',
      },
    });

    let exactRuleSaved = false;
    let savedRuleBody:
      | {
          source_value?: string;
          match_type?: string;
          match_expression?: string;
          target_conversation_id?: string;
          target_conversation_name?: string;
          enabled?: boolean;
        }
      | undefined;

    const buildGroupsPayload = () => ({
      page: 1,
      page_size: 50,
      total: 2,
      total_pages: 1,
      raw_row_total: 2,
      group_total: 2,
      matched_group_total: exactRuleSaved ? 2 : 1,
      unmatched_group_total: exactRuleSaved ? 0 : 1,
      invalid_group_total: 0,
      conflict_group_total: 0,
      order_number_field_configured: true,
      groups: [
        {
          group_key: 'group-acme',
          group_value: 'Acme Freight',
          raw_row_count: 1,
          distinct_order_number_count: 1,
          matched_conversation_name: 'Acme Freight Ops',
          matched_conversation_id: 'acme-freight-ops',
          match_status: 'matched',
          reason: null,
          attachment_count: 0,
          attachments: [],
          template_id: null,
          template_name: null,
          template_enabled: null,
          expandable: true,
          first_source_row_number: 2,
        },
        {
          group_key: 'group-northwind',
          group_value: 'Northwind Service Group',
          raw_row_count: 1,
          distinct_order_number_count: 1,
          matched_conversation_name: exactRuleSaved
            ? 'Northwind Service Group'
            : null,
          matched_conversation_id: exactRuleSaved
            ? 'northwind-service-group'
            : null,
          match_status: exactRuleSaved ? 'matched' : 'unmatched',
          reason: exactRuleSaved ? null : '未匹配到群聊',
          attachment_count: 0,
          attachments: [],
          template_id: null,
          template_name: null,
          template_enabled: null,
          expandable: true,
          first_source_row_number: 3,
        },
      ],
    });

    page.route('**/api/v1/broadcast/group-rules**', async (route) => {
      if (route.request().method() === 'GET') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            code: 0,
            message: 'ok',
            data: exactRuleSaved
              ? [
                  {
                    id: 2,
                    bot_uuid: 'bot-1',
                    connector_id: 'wxwork-local',
                    source_value: 'Northwind Service Group',
                    match_type: 'exact',
                    match_expression: 'Northwind Service Group',
                    target_conversation_id: 'northwind-service-group',
                    target_conversation_name: 'Northwind Service Group',
                    priority: 0,
                    enabled: true,
                    invalid_legacy: false,
                    invalid_reason: null,
                    created_at: new Date().toISOString(),
                    updated_at: new Date().toISOString(),
                  },
                ]
              : [],
            timestamp: Date.now(),
          }),
        });
        return;
      }

      if (route.request().method() === 'POST') {
        savedRuleBody = route.request().postDataJSON() as typeof savedRuleBody;
        exactRuleSaved = true;
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            code: 0,
            message: 'ok',
            data: {
              id: 2,
              bot_uuid: 'bot-1',
              connector_id: 'wxwork-local',
              source_value: 'Northwind Service Group',
              match_type: 'exact',
              match_expression: 'Northwind Service Group',
              target_conversation_id: 'northwind-service-group',
              target_conversation_name: 'Northwind Service Group',
              priority: 0,
              enabled: true,
              invalid_legacy: false,
              invalid_reason: null,
              created_at: new Date().toISOString(),
              updated_at: new Date().toISOString(),
            },
            timestamp: Date.now(),
          }),
        });
        return;
      }

      await route.fallback();
    });

    page.route('**/api/v1/broadcast/group-names**', async (route) => {
      if (route.request().method() !== 'GET') {
        await route.fallback();
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          code: 0,
          message: 'ok',
          data: [
            {
              id: 1,
              bot_uuid: 'bot-1',
              connector_id: 'wxwork-local',
              name: 'Northwind Service Group',
              external_conversation_id: 'northwind-service-group',
              created_at: new Date().toISOString(),
              updated_at: new Date().toISOString(),
            },
            {
              id: 2,
              bot_uuid: 'bot-1',
              connector_id: 'wxwork-local',
              name: 'Legacy Temporary Group',
              external_conversation_id: null,
              created_at: new Date().toISOString(),
              updated_at: new Date().toISOString(),
            },
          ],
          timestamp: Date.now(),
        }),
      });
    });

    page.route('**/api/v1/broadcast/imports/1/groups**', async (route) => {
      if (route.request().method() !== 'GET') {
        await route.fallback();
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          code: 0,
          message: 'ok',
          data: buildGroupsPayload(),
          timestamp: Date.now(),
        }),
      });
    });

    page.route('**/api/v1/broadcast/imports/1/rematch', async (route) => {
      if (route.request().method() !== 'POST') {
        await route.fallback();
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          code: 0,
          message: 'ok',
          data: {
            id: 1,
            bot_uuid: 'bot-1',
            connector_id: 'wxwork-local',
            original_file_name: 'customers.csv',
            file_type: 'csv',
            worksheet_name: null,
            status: 'matched',
            drafts_stale: false,
            total_rows: 2,
            valid_rows: 2,
            invalid_rows: 0,
            matched_rows: 2,
            unmatched_rows: 0,
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString(),
            rows: [],
            page: 1,
            page_size: 50,
            total: 2,
            total_pages: 1,
          },
          timestamp: Date.now(),
        }),
      });
    });

    await page.goto('/home/broadcast');
    await page.locator('[role="tab"]').nth(1).click();
    await page.getByTestId('broadcast-import-upload-input').setInputFiles({
      name: 'customers.csv',
      mimeType: 'text/csv',
      buffer: Buffer.from('customers', 'utf-8'),
    });

    await page
      .getByTestId(
        'broadcast-import-group-select-conversation-button-group-northwind',
      )
      .click();
    await expect(
      page.getByTestId('broadcast-import-inline-match-dialog'),
    ).toBeVisible();
    await page.getByPlaceholder('输入群聊名称').fill('');
    await expect(page.locator('body')).toContainText(
      '缺少稳定 external_conversation_id',
    );
    await page.getByRole('button', { name: 'Northwind Service Group' }).click();
    await page.getByTestId('broadcast-import-inline-match-save-button').click();

    await expect(
      page.getByTestId(
        'broadcast-import-group-select-conversation-button-group-northwind',
      ),
    ).toHaveCount(0);
    await expect(page.locator('body')).toContainText('已匹配');

    expect(savedRuleBody).toMatchObject({
      source_value: 'Northwind Service Group',
      match_type: 'exact',
      match_expression: 'Northwind Service Group',
      target_conversation_id: 'northwind-service-group',
      target_conversation_name: 'Northwind Service Group',
      enabled: true,
    });
  });

  test('shows confirmation dialogs and sticky action areas for high-impact actions', async ({
    page,
  }) => {
    await installLangBotApiMocks(page, {
      authenticated: true,
      storage: {
        langbot_language: 'zh-Hans',
      },
    });

    let rematchRequests = 0;
    page.on('request', (request) => {
      const url = new URL(request.url());
      if (
        request.method() === 'POST' &&
        url.pathname.endsWith('/broadcast/imports/1/rematch')
      ) {
        rematchRequests += 1;
      }
    });

    await page.goto('/home/broadcast');

    await expect(page.getByTestId('broadcast-primary-tabs')).toHaveCSS(
      'position',
      'relative',
    );
    await expect(page.getByTestId('broadcast-secondary-tabs')).toHaveCSS(
      'position',
      'relative',
    );

    await page.getByRole('tab', { name: '消息模板' }).click();
    await page.getByTestId('broadcast-template-delete-button').click();
    await expect(
      page.getByTestId('broadcast-template-delete-confirm-dialog'),
    ).toBeVisible();
    await page.getByTestId('broadcast-template-delete-cancel-button').click();
    await expect(
      page.getByTestId('broadcast-template-delete-confirm-dialog'),
    ).toHaveCount(0);

    await page.locator('[role="tab"]').nth(1).click();
    await page.getByTestId('broadcast-import-upload-input').setInputFiles({
      name: 'customers.csv',
      mimeType: 'text/csv',
      buffer: Buffer.from('customers', 'utf-8'),
    });
    await expect(page.getByTestId('broadcast-import-sticky-actions')).toHaveCSS(
      'position',
      'sticky',
    );

    await page.getByTestId('broadcast-import-rematch-button').click();
    await expect(
      page.getByTestId('broadcast-import-rematch-confirm-dialog'),
    ).toBeVisible();
    await page.getByTestId('broadcast-import-rematch-cancel-button').click();
    await expect(rematchRequests).toBe(0);

    await page
      .getByTestId('broadcast-import-template-select')
      .selectOption({ label: 'Arrival Reminder' });
    await page.getByTestId('broadcast-import-select-all-checkbox').click();
    await page.getByTestId('broadcast-import-apply-template-button').click();

    await page.getByTestId('broadcast-import-generate-drafts-button').click();
    await expect(
      page.getByTestId('broadcast-import-generate-drafts-confirm-dialog'),
    ).toBeVisible();
    await page
      .getByTestId('broadcast-import-generate-drafts-confirm-button')
      .click();

    await page.locator('[role="tab"]').nth(2).click();
    await expect(page.getByTestId('broadcast-draft-sticky-actions')).toHaveCSS(
      'position',
      'sticky',
    );
    await page.getByTestId('broadcast-draft-select-all-checkbox').click();
    await page.getByTestId('broadcast-draft-batch-write-button').click();
    await expect(
      page.getByTestId('broadcast-draft-batch-write-confirm-dialog'),
    ).toBeVisible();
    await page.getByTestId('broadcast-draft-batch-write-cancel-button').click();
    await expect(
      page.getByTestId('broadcast-draft-batch-write-confirm-dialog'),
    ).toHaveCount(0);
  });
});
