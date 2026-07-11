import { expect, test, type Page } from '@playwright/test';

import zhHans from '../../src/i18n/locales/zh-Hans';
import { installLangBotApiMocks } from './fixtures/langbot-api';

const zhHansBroadcastDrafts = zhHans.broadcast.drafts as Record<string, string>;
const zhHansBroadcastToasts = zhHans.broadcast.toasts as Record<string, string>;
const zhHansBroadcastLogs = zhHans.broadcast.logs as unknown as {
  executorHealthTitle: string;
};
const zhHansBroadcastExecutor = ((zhHans.broadcast as Record<string, unknown>)
  .executor ?? {}) as {
  runtimeUnavailable: string;
  runtimeOwnershipConflict: string;
  sendUnsupported: string;
};
const zhHansCommon = zhHans.common as Record<string, string>;

async function prepareDraftReview(page: Page) {
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
    page.getByTestId('broadcast-import-generate-drafts-button'),
  ).toBeEnabled();
  await page.getByTestId('broadcast-import-generate-drafts-button').click();
  await page
    .getByTestId('broadcast-import-generate-drafts-confirm-button')
    .click();
  await page.locator('[role="tab"]').nth(2).click();
  await expect(page.getByTestId('broadcast-draft-queue')).toBeVisible();
  await expect(page.getByTestId('broadcast-draft-detail')).toBeVisible();
}

test.describe('broadcast workflow', () => {
  test('shows loading only while executor health is pending, then resolves to runtime unavailable', async ({
    page,
  }) => {
    await installLangBotApiMocks(page, {
      authenticated: true,
      storage: {
        langbot_language: 'zh-Hans',
      },
      broadcastExecutorHealth: {
        available: false,
        channel: 'wxwork_database',
        status: 'unavailable',
        error_code: null,
        error_message: null,
        protocol_version: null,
        runtime_version: null,
        capability: {
          channel: 'wxwork_database',
          supports_paste: true,
          supports_paste_verification: true,
          supports_send: false,
          supports_cancel: true,
          supports_status_query: true,
          supports_clipboard_restore: true,
          supports_evidence: true,
          executor_version: 'fixture-phase7',
          runtime_min_version: '1.0.0',
        },
        runtime_status: null,
      },
      broadcastExecutorHealthDelayMs: 4000,
    });

    await prepareDraftReview(page);
    await expect(page.getByTestId('broadcast-draft-detail')).toContainText(
      zhHansCommon.loading,
    );
    await expect(
      page.getByTestId('broadcast-draft-paste-button'),
    ).toBeDisabled();
    await expect(
      page.getByTestId('broadcast-draft-send-button'),
    ).toBeDisabled();

    await expect(page.getByTestId('broadcast-draft-detail')).toContainText(
      zhHansBroadcastExecutor.runtimeUnavailable,
      {
        timeout: 10000,
      },
    );
    await expect(page.getByTestId('broadcast-draft-detail')).not.toContainText(
      zhHansCommon.loading,
    );
    await expect(
      page.getByTestId('broadcast-draft-batch-write-button'),
    ).toBeDisabled();

    await page.locator('[role="tab"]').nth(3).click();
    await expect(
      page.getByTestId('broadcast-executor-health-card'),
    ).toContainText(zhHansBroadcastExecutor.runtimeUnavailable);
  });

  test('shows runtime ownership conflict explicitly after health resolves', async ({
    page,
  }) => {
    await installLangBotApiMocks(page, {
      authenticated: true,
      storage: {
        langbot_language: 'zh-Hans',
      },
      broadcastExecutorHealth: {
        available: false,
        channel: 'wxwork_database',
        status: 'unavailable',
        error_code: 'RUNTIME_OWNERSHIP_CONFLICT',
        error_message: zhHansBroadcastExecutor.runtimeOwnershipConflict,
        protocol_version: null,
        runtime_version: null,
        capability: {
          channel: 'wxwork_database',
          supports_paste: true,
          supports_paste_verification: true,
          supports_send: false,
          supports_cancel: true,
          supports_status_query: true,
          supports_clipboard_restore: true,
          supports_evidence: true,
          executor_version: 'fixture-phase7',
          runtime_min_version: '1.0.0',
        },
        runtime_status: null,
      },
    });

    await prepareDraftReview(page);
    await expect(page.getByTestId('broadcast-draft-detail')).toContainText(
      zhHansBroadcastExecutor.runtimeOwnershipConflict,
    );

    await page.locator('[role="tab"]').nth(3).click();
    await expect(
      page.getByTestId('broadcast-executor-health-card'),
    ).toContainText(zhHansBroadcastExecutor.runtimeOwnershipConflict);
    await expect(
      page.getByTestId('broadcast-executor-health-status'),
    ).not.toContainText(zhHansCommon.loading);
  });

  test('distinguishes send unsupported from runtime availability', async ({
    page,
  }) => {
    await installLangBotApiMocks(page, {
      authenticated: true,
      storage: {
        langbot_language: 'zh-Hans',
      },
      broadcastSendEnabled: false,
      broadcastExecutorCapability: {
        channel: 'wxwork_database',
        supports_paste: true,
        supports_paste_verification: true,
        requires_manual_conversation_open: true,
        conversation_locator: 'keyboard_search',
        content_verification: 'windows_uia',
        supports_send: false,
        supports_cancel: true,
        supports_status_query: true,
        supports_clipboard_restore: true,
        supports_evidence: true,
        executor_version: 'fixture-phase7',
        runtime_min_version: '1.0.0',
      },
      broadcastExecutorHealth: {
        available: true,
        channel: 'wxwork_database',
        status: 'ready',
        protocol_version: '1.0.0',
        runtime_version: '1.0.0',
        error_code: null,
        error_message: null,
        capability: {
          channel: 'wxwork_database',
          supports_paste: true,
          supports_paste_verification: true,
          requires_manual_conversation_open: true,
          conversation_locator: 'keyboard_search',
          content_verification: 'windows_uia',
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
          },
        },
      },
    });

    await prepareDraftReview(page);
    await expect(
      page.getByTestId('broadcast-draft-paste-button'),
    ).toBeEnabled();
    await expect(
      page.getByTestId('broadcast-draft-send-button'),
    ).toBeDisabled();
    await expect(page.getByTestId('broadcast-draft-detail')).toContainText(
      zhHansBroadcastExecutor.sendUnsupported,
    );

    await page.locator('[role="tab"]').nth(3).click();
    await expect(
      page.getByTestId('broadcast-executor-health-card'),
    ).toContainText(zhHansBroadcastExecutor.sendUnsupported);
  });

  test('enables real send when runtime is available and supports_send is true', async ({
    page,
  }) => {
    await installLangBotApiMocks(page, {
      authenticated: true,
      storage: {
        langbot_language: 'zh-Hans',
      },
      broadcastSendEnabled: true,
    });

    await prepareDraftReview(page);
    await expect(page.getByTestId('broadcast-draft-send-button')).toBeEnabled();

    await page.locator('[role="tab"]').nth(3).click();
    await expect(
      page.getByTestId('broadcast-executor-health-card'),
    ).toContainText(zhHansBroadcastLogs.executorHealthTitle);
  });

  test('moves new-customer assignment from import matching to group matching', async ({
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
      'Detected customer field for this batch:',
    );
    await expect(
      page.getByTestId('broadcast-import-bulk-assign-open-button'),
    ).toHaveCount(0);
    await expect(
      page.locator(
        '[data-testid^="broadcast-import-group-select-conversation-button-"]',
      ),
    ).toHaveCount(0);

    const goToGroupMatchingButton = page.locator(
      '[data-testid^="broadcast-import-group-go-to-group-matching-button-"]',
    );
    await expect(goToGroupMatchingButton.first()).toBeVisible();
    await goToGroupMatchingButton.first().click();

    await expect(
      page.getByTestId('broadcast-group-matching-panel'),
    ).toBeVisible();
    await expect(
      page.getByTestId('broadcast-group-matching-pending-customers'),
    ).toContainText('Customers pending configuration');
    await expect(
      page.getByTestId('broadcast-group-matching-batch-select'),
    ).toHaveValue('1');
    await expect(
      page.getByTestId('broadcast-group-matching-pending-customers'),
    ).toContainText('username-import.xlsx');
    await expect(
      page.getByTestId('broadcast-group-matching-bulk-assign-open-button'),
    ).toContainText('(1)');

    await page
      .getByTestId('broadcast-group-matching-bulk-assign-open-button')
      .click();
    const dialog = page.getByTestId(
      'broadcast-group-matching-bulk-assign-dialog',
    );
    await expect(dialog).toBeVisible();
    await expect(dialog).toContainText('northwind_user');
    await expect(
      dialog.getByTestId('broadcast-group-matching-bulk-assign-apply-button'),
    ).toContainText('(1)');
    await dialog
      .getByRole('button', { name: 'Northwind Service Group' })
      .click();
    await dialog
      .getByTestId('broadcast-group-matching-bulk-assign-apply-button')
      .click();
    await dialog
      .getByTestId('broadcast-group-matching-bulk-assign-submit-button')
      .click();
    await expect(
      page.getByTestId('broadcast-group-matching-bulk-assign-confirm-dialog'),
    ).toBeVisible();
    await page
      .getByTestId('broadcast-group-matching-bulk-assign-confirm-button')
      .click();
    await expect(dialog).toHaveCount(0);

    expect(bulkAssignBody).toMatchObject({
      items: [
        {
          target_conversation_id: 'northwind-service-group',
        },
      ],
    });
    await expect(
      page.getByTestId('broadcast-group-matching-bulk-assign-open-button'),
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

    await expect(page.getByTestId('broadcast-draft-paste-button')).toHaveText(
      zhHansBroadcastDrafts.pasteToInput,
    );
    await expect(page.getByTestId('broadcast-draft-send-button')).toHaveText(
      zhHansBroadcastDrafts.realSend,
    );
    await expect(
      page.getByTestId('broadcast-draft-batch-write-button'),
    ).toHaveText(zhHansBroadcastDrafts.batchWriteSelected);
    await expect(
      page.getByTestId('broadcast-draft-batch-send-button'),
    ).toHaveText(zhHansBroadcastDrafts.batchSendSelected);

    await page.getByTestId('broadcast-draft-paste-button').click();
    await expect(
      page.getByTestId('broadcast-draft-paste-confirm-dialog'),
    ).toHaveCount(0);
    await expect(
      page.getByTestId('broadcast-execution-logs-table'),
    ).toBeVisible();
    await expect(page.locator('body')).toContainText(
      zhHans.broadcast.logs.statusWarning,
    );
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

  test('shows only one target-conversation label in the group rule editor', async ({
    page,
  }) => {
    await installLangBotApiMocks(page, {
      authenticated: true,
      storage: {
        langbot_language: 'en-US',
      },
    });

    await page.goto('/home/broadcast');
    await page.getByRole('tab').first().click();
    await page
      .getByTestId('broadcast-secondary-tabs')
      .locator('[role="tab"]')
      .nth(2)
      .click();
    await expect(
      page.getByTestId('broadcast-group-matching-panel'),
    ).toBeVisible();
    await expect(
      page
        .getByTestId('broadcast-group-rule-editor')
        .getByText('Target conversation', { exact: true }),
    ).toHaveCount(1);
  });

  test('sends a single pending draft for real without triggering manual start flow', async ({
    page,
  }) => {
    await installLangBotApiMocks(page, {
      authenticated: true,
      storage: {
        langbot_language: 'zh-Hans',
      },
      broadcastSendEnabled: true,
    });

    const executionBodies: Array<{
      draft_ids?: number[];
      mode?: string;
    }> = [];
    const requestPaths: string[] = [];
    await page.route('**/api/v1/broadcast/executions', async (route) => {
      if (route.request().method() === 'POST') {
        executionBodies.push(
          (route.request().postDataJSON() as {
            draft_ids?: number[];
            mode?: string;
          }) ?? {},
        );
      }
      await route.fallback();
    });
    page.on('request', (request) => {
      const url = new URL(request.url());
      if (url.pathname.startsWith('/api/v1/')) {
        requestPaths.push(url.pathname);
      }
    });

    await prepareDraftReview(page);
    await expect(page.getByTestId('broadcast-draft-paste-button')).toHaveText(
      zhHansBroadcastDrafts.pasteToInput,
    );
    await expect(page.getByTestId('broadcast-draft-send-button')).toHaveText(
      zhHansBroadcastDrafts.realSend,
    );
    await expect(page.getByTestId('broadcast-draft-send-button')).toBeEnabled();

    await page.getByTestId('broadcast-draft-send-button').click();
    await expect(
      page.getByTestId('broadcast-draft-send-confirm-dialog'),
    ).toBeVisible();
    await page.getByTestId('broadcast-draft-send-confirm-button').click();

    await expect(page.locator('body')).toContainText(
      zhHansBroadcastToasts.realSendCompleted.replace('{{sentCount}}', '1'),
    );
    await page.locator('[role="tab"]').nth(2).click();
    await expect(page.getByTestId('broadcast-draft-detail')).toContainText(
      zhHans.broadcast.drafts.statusSent,
    );
    await expect(
      page.getByTestId('broadcast-draft-restore-pending-button'),
    ).toBeVisible();

    expect(executionBodies).toHaveLength(1);
    expect(executionBodies[0]).toMatchObject({
      draft_ids: [1],
      mode: 'send',
    });
    expect(
      requestPaths.some((path) =>
        /\/api\/v1\/broadcast\/executions\/\d+\/start$/.test(path),
      ),
    ).toBeFalsy();
  });

  test('keeps batch real send serial and surfaces unknown results for manual review', async ({
    page,
  }) => {
    await installLangBotApiMocks(page, {
      authenticated: true,
      storage: {
        langbot_language: 'zh-Hans',
      },
      broadcastSendEnabled: true,
    });

    const executionBodies: Array<{
      draft_ids?: number[];
      mode?: string;
    }> = [];
    await page.route('**/api/v1/broadcast/executions', async (route) => {
      if (route.request().method() === 'POST') {
        executionBodies.push(
          (route.request().postDataJSON() as {
            draft_ids?: number[];
            mode?: string;
          }) ?? {},
        );
      }
      await route.fallback();
    });

    await prepareDraftReview(page);

    await page.getByTestId('broadcast-draft-row-2').getByRole('button').click();
    await page.getByTestId('broadcast-draft-edit-button').click();
    await page
      .getByLabel(zhHans.broadcast.drafts.editor)
      .fill('Hello Northwind Team __send_unknown__');
    await page.getByTestId('broadcast-draft-save-button').click();

    await page.getByTestId('broadcast-draft-select-all-checkbox').click();
    await expect(
      page.getByTestId('broadcast-draft-batch-send-button'),
    ).toBeEnabled();

    await page.getByTestId('broadcast-draft-batch-send-button').click();
    await expect(
      page.getByTestId('broadcast-draft-batch-send-confirm-dialog'),
    ).toBeVisible();
    await page.getByTestId('broadcast-draft-batch-send-confirm-button').click();

    await expect(page.locator('body')).toContainText(
      zhHansBroadcastToasts.realSendCompletedWithUnknown
        .replace('{{sentCount}}', '1')
        .replace('{{failedCount}}', '0')
        .replace('{{unknownCount}}', '1'),
    );

    await page.locator('[role="tab"]').nth(2).click();
    await expect(page.locator('body')).toContainText(
      '已执行发送操作，请人工检查目标会话',
    );
    await expect(
      page.getByTestId('broadcast-batch-retry-failed-button'),
    ).toHaveCount(0);
    await expect(
      page.getByTestId('broadcast-execution-task-retry-1'),
    ).toHaveCount(0);
    await expect(
      page.getByTestId('broadcast-execution-task-retry-2'),
    ).toHaveCount(0);
    await page.getByTestId('broadcast-draft-row-2').getByRole('button').click();
    await expect(page.getByTestId('broadcast-draft-detail')).toContainText(
      zhHansBroadcastDrafts.statusUnknown,
    );
    await expect(
      page.getByTestId('broadcast-draft-mark-sent-button'),
    ).toBeVisible();
    await expect(
      page.getByTestId('broadcast-draft-restore-pending-button'),
    ).toBeVisible();
    await page.getByTestId('broadcast-draft-restore-pending-button').click();
    await expect(
      page.getByTestId('broadcast-draft-restore-pending-risk-dialog'),
    ).toBeVisible();
    await expect(
      page.getByTestId('broadcast-draft-restore-pending-risk-dialog'),
    ).toContainText(zhHansBroadcastDrafts.restorePendingRiskDescription);
    await page
      .getByTestId('broadcast-draft-restore-pending-risk-confirm-button')
      .click();
    await expect(page.locator('body')).toContainText(
      zhHansBroadcastToasts.draftsRestoredPending,
    );

    expect(executionBodies).toHaveLength(1);
    expect(executionBodies[0]).toMatchObject({
      draft_ids: [1, 2],
      mode: 'send',
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
    const batchWriteDialog = page.getByTestId(
      'broadcast-draft-batch-write-confirm-dialog',
    );
    await expect(batchWriteDialog).toBeVisible();
    await expect(batchWriteDialog).toContainText(
      '\u5c06\u9009\u4e2d\u8349\u7a3f\u5199\u5165\u8f93\u5165\u6846',
    );
    await expect(batchWriteDialog).toContainText(
      /\u672c\u6b21\u5c06\u5199\u5165\s*\d+\s*\u6761\u8349\u7a3f/,
    );
    await expect(batchWriteDialog).toContainText(
      /\u6d89\u53ca\s*\d+\s*\u4e2a\u76ee\u6807\u7fa4\u804a/,
    );
    await expect(batchWriteDialog).toContainText(
      /\u5305\u542b\s*\d+\s*\u4e2a\u9644\u4ef6/,
    );
    await expect(batchWriteDialog).toContainText(
      /\u91cd\u590d\u76ee\u6807\u7fa4\u804a\s*\d+\s*\u4e2a/,
    );
    await expect(batchWriteDialog).not.toContainText(
      'Write selected drafts to the input box',
    );
    await expect(batchWriteDialog).not.toContainText('This will submit');
    await expect(
      page.getByTestId('broadcast-draft-batch-write-cancel-button'),
    ).toHaveText('\u53d6\u6d88');
    await expect(
      page.getByTestId('broadcast-draft-batch-write-confirm-button'),
    ).toHaveText(zhHansBroadcastDrafts.batchWriteSelected);
    await page.getByTestId('broadcast-draft-batch-write-cancel-button').click();
    await expect(batchWriteDialog).toHaveCount(0);
  });
});
