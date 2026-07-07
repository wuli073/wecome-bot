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

test.describe('broadcast group summary and attachments', () => {
  test('groups repeated customer rows, expands raw rows, and marks ready drafts stale after group attachment changes', async ({
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
      id: 77,
      bot_uuid: 'bot-1',
      connector_id: 'wxwork-local',
      original_file_name: 'group-summary.csv',
      file_type: 'csv',
      worksheet_name: null,
      status: 'drafts_generated',
      drafts_stale: false,
      total_rows: 3,
      valid_rows: 3,
      invalid_rows: 0,
      matched_rows: 2,
      unmatched_rows: 1,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    };

    const rawRows = [
      {
        id: 701,
        import_batch_id: 77,
        source_row_number: 2,
        raw_data: {
          客户: '小满',
          运单号: 'WB-001',
        },
        group_value: '小满',
        matched_conversation_name: '小满',
        matched_rule_id: 1,
        match_status: 'matched',
        error_message: null,
        created_at: new Date().toISOString(),
      },
      {
        id: 702,
        import_batch_id: 77,
        source_row_number: 3,
        raw_data: {
          客户: '小满',
          运单号: 'WB-001',
        },
        group_value: '小满',
        matched_conversation_name: '小满',
        matched_rule_id: 1,
        match_status: 'matched',
        error_message: null,
        created_at: new Date().toISOString(),
      },
      {
        id: 703,
        import_batch_id: 77,
        source_row_number: 4,
        raw_data: {
          客户: '北景',
          运单号: 'WB-002',
        },
        group_value: '北景',
        matched_conversation_name: null,
        matched_rule_id: null,
        match_status: 'unmatched',
        error_message: null,
        created_at: new Date().toISOString(),
      },
    ];

    const groupsResponse = {
      page: 1,
      page_size: 50,
      total: 2,
      total_pages: 1,
      raw_row_total: 3,
      group_total: 2,
      matched_group_total: 1,
      unmatched_group_total: 1,
      invalid_group_total: 0,
      conflict_group_total: 0,
      order_number_field_configured: true,
      groups: [
        {
          group_key: 'group-xiaoman',
          group_value: '小满',
          raw_row_count: 2,
          distinct_order_number_count: 1,
          matched_conversation_name: '小满',
          match_status: 'matched',
          reason: null,
          attachment_count: 0,
          attachments: [],
          expandable: true,
          first_source_row_number: 2,
        },
        {
          group_key: 'group-beijing',
          group_value: '北景',
          raw_row_count: 1,
          distinct_order_number_count: 1,
          matched_conversation_name: null,
          match_status: 'unmatched',
          reason: null,
          attachment_count: 0,
          attachments: [],
          expandable: true,
          first_source_row_number: 4,
        },
      ],
    };

    let currentGroupAttachments: Array<{
      id: number;
      attachment_asset_id: number;
      original_name: string;
      size_bytes: number;
      sha256: string;
      extension: string;
      mime_type: string;
      sort_order: number;
    }> = [];

    let draftStatus: 'pending_review' | 'ready' = 'ready';
    let draftMessage: string | null = null;
    let attachmentsStale = false;

    await page.route('**/api/v1/broadcast/imports', async (route) => {
      const url = new URL(route.request().url());
      if (route.request().method() === 'GET') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(ok([batch])),
        });
        return;
      }
      if (
        route.request().method() === 'POST' &&
        url.pathname.endsWith('/imports')
      ) {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(ok(batch)),
        });
        return;
      }
      await route.fallback();
    });

    await page.route('**/api/v1/broadcast/imports/77**', async (route) => {
      const request = route.request();
      const url = new URL(request.url());
      if (request.method() !== 'GET' && request.method() !== 'POST') {
        await route.fallback();
        return;
      }
      if (url.pathname === '/api/v1/broadcast/imports/77') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(
            ok({
              ...batch,
              rows: rawRows,
              page: 1,
              page_size: 50,
              total: 3,
              total_pages: 1,
            }),
          ),
        });
        return;
      }
      if (url.pathname === '/api/v1/broadcast/imports/77/groups') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(
            ok({
              ...groupsResponse,
              groups: groupsResponse.groups.map((group) =>
                group.group_key === 'group-xiaoman'
                  ? {
                      ...group,
                      attachment_count: currentGroupAttachments.length,
                      attachments: currentGroupAttachments,
                    }
                  : group,
              ),
            }),
          ),
        });
        return;
      }
      if (
        url.pathname ===
        '/api/v1/broadcast/imports/77/groups/group-xiaoman/rows'
      ) {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(
            ok({
              group_key: 'group-xiaoman',
              group_value: '小满',
              page: 1,
              page_size: 50,
              total: 2,
              total_pages: 1,
              rows: rawRows.slice(0, 2),
            }),
          ),
        });
        return;
      }
      if (
        request.method() === 'POST' &&
        url.pathname ===
          '/api/v1/broadcast/imports/77/groups/group-xiaoman/attachments'
      ) {
        currentGroupAttachments = [
          {
            id: 1,
            attachment_asset_id: 9001,
            original_name: 'proof.pdf',
            size_bytes: 2048,
            sha256: 'sha256:fixture-1',
            extension: '.pdf',
            mime_type: 'application/pdf',
            sort_order: 1,
          },
        ];
        draftStatus = 'pending_review';
        draftMessage =
          'Draft attachments changed, please confirm again before execution.';
        attachmentsStale = true;
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(ok(currentGroupAttachments)),
        });
        return;
      }
      await route.fallback();
    });

    await page.route('**/api/v1/broadcast/drafts**', async (route) => {
      if (route.request().method() !== 'GET') {
        await route.fallback();
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(
          ok([
            {
              id: 201,
              bot_uuid: 'bot-1',
              connector_id: 'wxwork-local',
              import_batch_id: 77,
              group_value: '小满',
              target_conversation_name: '小满',
              template_id: 1,
              template_name_snapshot: 'Arrival Reminder',
              template_content_snapshot: 'Hello {{customer_name}}',
              render_variables: {
                customer_name: '小满',
              },
              draft_text: 'Hello 小满',
              status: draftStatus,
              error_message: null,
              drafts_stale: false,
              attachments_stale: attachmentsStale,
              attachments: currentGroupAttachments,
              created_at: new Date().toISOString(),
              updated_at: new Date().toISOString(),
              message: draftMessage,
            },
          ]),
        ),
      });
    });

    await page.route(
      '**/api/v1/broadcast/executors/capabilities*',
      async (route) => {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(
            ok({
              channel: 'wxwork_database',
              supports_paste: true,
              supports_paste_verification: true,
              requires_manual_conversation_open: true,
              supports_send: false,
              supports_cancel: true,
              supports_status_query: true,
              supports_clipboard_restore: true,
              supports_evidence: true,
              executor_version: 'fixture-phase7',
              runtime_min_version: '1.0.0',
            }),
          ),
        });
      },
    );

    await page.route('**/api/v1/broadcast/executors/health*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(
          ok({
            channel: 'wxwork_database',
            status: 'ready',
            protocol_version: '1.0.0',
            runtime_version: '1.0.0',
            capability: {
              channel: 'wxwork_database',
              supports_paste: true,
              supports_paste_verification: true,
              requires_manual_conversation_open: true,
              supports_send: false,
              supports_cancel: true,
              supports_status_query: true,
              supports_clipboard_restore: true,
              supports_evidence: true,
              executor_version: 'fixture-phase7',
              runtime_min_version: '1.0.0',
            },
            runtime_status: {
              pasteVerification: {
                available: true,
                reason: null,
                method: 'windows_uia',
                requiresManualConversationOpen: true,
                supportedErrorCodes: [
                  'TARGET_WINDOW_CHANGED',
                  'CONVERSATION_MISMATCH',
                  'INPUT_NOT_LOCATED',
                  'PASTE_CONTENT_MISMATCH',
                  'PASTE_VERIFICATION_UNAVAILABLE',
                ],
              },
            },
          }),
        ),
      });
    });

    await page.goto('/home/broadcast');
    await expect(page).toHaveURL(/\/home\/broadcast$/);

    await page.getByRole('tab', { name: '导入匹配' }).click();
    await page.getByTestId('broadcast-import-upload-input').setInputFiles({
      name: 'group-summary.csv',
      mimeType: 'text/csv',
      buffer: Buffer.from(
        '客户,运单号\n小满,WB-001\n小满,WB-001\n北景,WB-002\n',
        'utf-8',
      ),
    });
    await expect(
      page.getByTestId('broadcast-import-total-items'),
    ).toContainText('2');
    await expect(
      page.locator('[data-testid="broadcast-import-table"] tbody tr'),
    ).toHaveCount(2);
    await expect(
      page.locator('[data-testid="broadcast-import-table"]'),
    ).toContainText('小满');
    await expect(
      page.locator('[data-testid="broadcast-import-table"]'),
    ).toContainText('2');
    await expect(
      page.locator('[data-testid="broadcast-import-table"]'),
    ).toContainText('1');

    await page
      .locator('[data-testid="broadcast-import-table"] tbody tr')
      .first()
      .getByRole('button')
      .click();
    await expect(page.locator('body')).toContainText('WB-001');

    const attachmentInput = page
      .locator('tbody tr input[type=\"file\"]')
      .first();
    await attachmentInput.setInputFiles({
      name: 'proof.pdf',
      mimeType: 'application/pdf',
      buffer: Buffer.from('fixture-pdf', 'utf-8'),
    });

    await expect(page.locator('body')).toContainText('proof.pdf');

    await page.locator('[role="tab"]').nth(2).click();
    await expect(
      page.getByTestId('broadcast-draft-paste-button'),
    ).toBeDisabled();
    await expect(
      page.getByTestId('broadcast-draft-batch-write-button'),
    ).toBeDisabled();
  });
});
