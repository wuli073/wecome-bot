import { expect, test, type Page } from '@playwright/test';

import zhHans from '../../src/i18n/locales/zh-Hans';
import { installLangBotApiMocks } from './fixtures/langbot-api';

const zhHansBroadcastDrafts = zhHans.broadcast.drafts as Record<string, string>;
const zhHansBroadcastToasts = zhHans.broadcast.toasts as Record<string, string>;
const zhHansBroadcastActions = zhHans.broadcast.actions as Record<string, string>;
const zhHansBroadcastGroupRule = ((zhHans.broadcast as Record<string, unknown>)
  .groupRule ?? {}) as {
  targetConversationSelectPlaceholder: string;
  targetResolution: {
    deferred: string;
  };
};
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

async function fulfillOk(
  route: import('@playwright/test').Route,
  data: unknown,
) {
  await route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({
      code: 0,
      message: 'ok',
      data,
      timestamp: Date.now(),
    }),
  });
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

  test('polls desktop runtime readiness every 5 seconds and updates action buttons without reloading', async ({
    page,
  }) => {
    await installLangBotApiMocks(page, {
      authenticated: true,
      storage: {
        langbot_language: 'zh-Hans',
      },
      broadcastSendEnabled: true,
    });

    const healthRequestTimes: number[] = [];
    let runtimePhase: 'unavailable' | 'ready' = 'unavailable';
    await page.route('**/api/v1/broadcast/executors/health*', async (route) => {
      if (route.request().method() !== 'GET') {
        await route.fallback();
        return;
      }
      healthRequestTimes.push(Date.now());
      if (runtimePhase === 'ready') {
        await fulfillOk(route, {
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
            supports_send: true,
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
        });
        return;
      }

      await fulfillOk(route, {
        available: false,
        channel: 'wxwork_database',
        status: 'unavailable',
        protocol_version: null,
        runtime_version: null,
        error_code: null,
        error_message: zhHansBroadcastExecutor.runtimeUnavailable,
        capability: {
          channel: 'wxwork_database',
          supports_paste: true,
          supports_paste_verification: true,
          requires_manual_conversation_open: true,
          conversation_locator: 'keyboard_search',
          content_verification: 'windows_uia',
          supports_send: true,
          supports_cancel: true,
          supports_status_query: true,
          supports_clipboard_restore: true,
          supports_evidence: true,
          executor_version: 'fixture-phase7',
          runtime_min_version: '1.0.0',
        },
        runtime_status: null,
      });
    });

    await prepareDraftReview(page);
    await expect(page.getByTestId('broadcast-draft-paste-button')).toBeDisabled();
    await expect(page.getByTestId('broadcast-draft-send-button')).toBeDisabled();

    const baselineRequestCount = healthRequestTimes.length;
    runtimePhase = 'ready';
    await expect
      .poll(() => healthRequestTimes.length, {
        timeout: 10_000,
      })
      .toBeGreaterThan(baselineRequestCount);
    await expect(page.getByTestId('broadcast-draft-paste-button')).toBeEnabled();
    await expect(page.getByTestId('broadcast-draft-send-button')).toBeEnabled();

    const readyRequestCount = healthRequestTimes.length;
    runtimePhase = 'unavailable';
    await expect
      .poll(() => healthRequestTimes.length, {
        timeout: 10_000,
      })
      .toBeGreaterThan(readyRequestCount);
    await expect(page.getByTestId('broadcast-draft-paste-button')).toBeDisabled();
    await expect(page.getByTestId('broadcast-draft-send-button')).toBeDisabled();
    await expect(page.getByTestId('broadcast-draft-detail')).toContainText(
      zhHansBroadcastExecutor.runtimeUnavailable,
    );

    const pollIntervals = healthRequestTimes
      .slice(1)
      .map((value, index) => value - healthRequestTimes[index]);
    expect(pollIntervals.some((intervalMs) => intervalMs >= 4_500)).toBeTruthy();
  });

  test('shows a clear runtime-unavailable message when runtime status refresh fails', async ({
    page,
  }) => {
    await installLangBotApiMocks(page, {
      authenticated: true,
      storage: {
        langbot_language: 'zh-Hans',
      },
      broadcastSendEnabled: true,
    });

    await page.route('**/api/v1/broadcast/executors/health*', async (route) => {
      if (route.request().method() !== 'GET') {
        await route.fallback();
        return;
      }
      await route.fulfill({
        status: 500,
        contentType: 'application/json',
        body: JSON.stringify({
          code: 500,
          message: 'runtime status fixture failed',
          data: null,
          timestamp: Date.now(),
        }),
      });
    });

    await prepareDraftReview(page);
    await expect(page.getByTestId('broadcast-draft-detail')).toContainText(
      zhHansBroadcastExecutor.runtimeUnavailable,
    );
    await expect(page.getByTestId('broadcast-draft-paste-button')).toBeDisabled();
    await expect(page.getByTestId('broadcast-draft-send-button')).toBeDisabled();
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

  test('accepts manually entered deferred target groups and keeps candidate selection working', async ({
    page,
  }) => {
    await installLangBotApiMocks(page, {
      authenticated: true,
      storage: {
        langbot_language: 'zh-Hans',
      },
      broadcastSendEnabled: true,
    });

    const timestamp = new Date().toISOString();
    const currentRules: Array<Record<string, unknown>> = [
      {
        id: 1,
        bot_uuid: 'bot-1',
        connector_id: 'wxwork-local',
        source_value: 'Acme Freight',
        match_type: 'exact',
        match_expression: 'Acme Freight',
        target_conversation_id: 'acme-freight-ops',
        target_conversation_name: 'Acme Freight Ops',
        target_resolution_status: 'resolved',
        priority: 30,
        enabled: true,
        created_at: timestamp,
        updated_at: timestamp,
      },
    ];
    let updatedRuleBody:
      | {
          source_value?: string;
          match_expression?: string;
          target_conversation_id?: string;
          target_conversation_name?: string;
        }
      | undefined;
    let createdRuleBody:
      | {
          source_value?: string;
          target_conversation_id?: string;
          target_conversation_name?: string;
        }
      | undefined;

    await page.route('**/api/v1/broadcast/group-rules**', async (route) => {
      const request = route.request();
      const url = new URL(request.url());
      if (
        request.method() === 'GET' &&
        url.pathname === '/api/v1/broadcast/group-rules'
      ) {
        await fulfillOk(route, currentRules);
        return;
      }
      if (
        request.method() === 'PUT' &&
        /^\/api\/v1\/broadcast\/group-rules\/\d+$/.test(url.pathname)
      ) {
        updatedRuleBody = request.postDataJSON() as typeof updatedRuleBody;
        currentRules[0] = {
          ...currentRules[0],
          source_value: updatedRuleBody?.source_value ?? currentRules[0].source_value,
          match_expression:
            updatedRuleBody?.match_expression ?? currentRules[0].match_expression,
          target_conversation_id:
            updatedRuleBody?.target_conversation_id?.trim() || null,
          target_conversation_name:
            updatedRuleBody?.target_conversation_name ??
            currentRules[0].target_conversation_name,
          target_resolution_status:
            updatedRuleBody?.target_conversation_id?.trim()?.length
              ? 'resolved'
              : 'deferred',
          updated_at: new Date().toISOString(),
        };
      }
      if (
        request.method() === 'POST' &&
        url.pathname === '/api/v1/broadcast/group-rules'
      ) {
        createdRuleBody = request.postDataJSON() as typeof createdRuleBody;
        currentRules.push({
          id: 99,
          bot_uuid: 'bot-1',
          connector_id: 'wxwork-local',
          source_value: createdRuleBody?.source_value ?? 'Northwind Candidate',
          match_type: 'exact',
          match_expression:
            createdRuleBody?.source_value ?? 'Northwind Candidate',
          target_conversation_id:
            createdRuleBody?.target_conversation_id?.trim() || null,
          target_conversation_name:
            createdRuleBody?.target_conversation_name ??
            'Northwind Service Group',
          target_resolution_status:
            createdRuleBody?.target_conversation_id?.trim()?.length
              ? 'resolved'
              : 'deferred',
          priority: 0,
          enabled: true,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        });
      }
      await route.fallback();
    });

    await page.goto('/home/broadcast');
    await page.locator('[role="tab"]').first().click();
    await page
      .getByTestId('broadcast-secondary-tabs')
      .locator('[role="tab"]')
      .nth(2)
      .click();
    await expect(
      page.getByTestId('broadcast-group-matching-panel'),
    ).toBeVisible();

    const manualConversationName = '发送时查找群聊';
    const targetConversationInput = page.getByTestId(
      'broadcast-group-rule-target-conversation-search',
    );
    await targetConversationInput.fill(manualConversationName);
    await expect(
      page.getByTestId('broadcast-group-rule-target-conversation-select'),
    ).toContainText(zhHansBroadcastGroupRule.targetConversationSelectPlaceholder);
    await targetConversationInput.press('Enter');
    await page.locator('#broadcast-group-rule-source-value').click();
    await expect(targetConversationInput).toHaveValue(manualConversationName);

    await page
      .getByRole('button', { name: zhHansBroadcastActions.saveGroupRule })
      .click();
    await expect
      .poll(() => updatedRuleBody ?? null)
      .not.toBeNull();
    expect(updatedRuleBody).toMatchObject({
      target_conversation_id: '',
      target_conversation_name: manualConversationName,
    });
    await expect(page.locator('body')).toContainText(
      zhHansBroadcastGroupRule.targetResolution.deferred,
    );

    await page
      .getByRole('button', { name: zhHansBroadcastActions.newGroupRule })
      .click();
    await page.locator('#broadcast-group-rule-source-value').fill(
      'Northwind Candidate',
    );
    await targetConversationInput.fill('Northwind');
    await page
      .getByTestId('broadcast-group-rule-target-conversation-select')
      .getByRole('button', { name: 'Northwind Service Group' })
      .click();
    await page
      .getByRole('button', { name: zhHansBroadcastActions.createGroupRule })
      .click();
    await expect
      .poll(() => createdRuleBody ?? null)
      .not.toBeNull();
    expect(createdRuleBody).toMatchObject({
      source_value: 'Northwind Candidate',
      target_conversation_id: 'northwind-service-group',
      target_conversation_name: 'Northwind Service Group',
    });
  });

  test('keeps deferred target-group failures hidden until real send reports them', async ({
    page,
  }) => {
    await installLangBotApiMocks(page, {
      authenticated: true,
      storage: {
        langbot_language: 'zh-Hans',
      },
      broadcastSendEnabled: true,
    });

    const timestamp = new Date().toISOString();
    const currentRules: Array<Record<string, unknown>> = [
      {
        id: 1,
        bot_uuid: 'bot-1',
        connector_id: 'wxwork-local',
        source_value: 'Acme Freight',
        match_type: 'exact',
        match_expression: 'Acme Freight',
        target_conversation_id: 'acme-freight-ops',
        target_conversation_name: 'Acme Freight Ops',
        target_resolution_status: 'resolved',
        priority: 30,
        enabled: true,
        created_at: timestamp,
        updated_at: timestamp,
      },
    ];
    let deferredRuleSaved = false;
    let capturedExecutionBody:
      | {
          draft_ids?: number[];
          mode?: string;
        }
      | undefined;
    let customSendBatch: Record<string, unknown> | null = null;
    const customTaskIds = new Set<number>();

    await page.route('**/api/v1/broadcast/group-rules**', async (route) => {
      const request = route.request();
      const url = new URL(request.url());
      if (
        request.method() === 'GET' &&
        url.pathname === '/api/v1/broadcast/group-rules'
      ) {
        await fulfillOk(route, currentRules);
        return;
      }
      if (
        request.method() === 'PUT' &&
        /^\/api\/v1\/broadcast\/group-rules\/\d+$/.test(url.pathname)
      ) {
        const body = request.postDataJSON() as {
          target_conversation_id?: string;
          target_conversation_name?: string;
        };
        currentRules[0] = {
          ...currentRules[0],
          target_conversation_id: body.target_conversation_id?.trim() || null,
          target_conversation_name:
            body.target_conversation_name ?? '发送时查找群聊',
          target_resolution_status:
            body.target_conversation_id?.trim()?.length ? 'resolved' : 'deferred',
          updated_at: new Date().toISOString(),
        };
        deferredRuleSaved = true;
      }
      await route.fallback();
    });

    await page.route('**/api/v1/broadcast/executions**', async (route) => {
      const request = route.request();
      const url = new URL(request.url());
      if (
        request.method() === 'POST' &&
        url.pathname === '/api/v1/broadcast/executions'
      ) {
        const body =
          (request.postDataJSON() as typeof capturedExecutionBody) ?? {};
        if (body.mode === 'send') {
          capturedExecutionBody = body;
          const draftIds = (body.draft_ids ?? []).map(Number);
          const taskDefinitions = [
            {
              taskId: 9101,
              draftId: draftIds[0] ?? 1,
              targetConversationSnapshot: '发送时查找群聊',
              errorCode: 'TARGET_GROUP_NOT_FOUND',
              errorMessage: '群聊未找到，请检查名称后重试',
            },
            {
              taskId: 9102,
              draftId: draftIds[1] ?? 2,
              targetConversationSnapshot: 'Northwind Service Group',
              errorCode: 'TARGET_GROUP_AMBIGUOUS',
              errorMessage: '存在多个同名群聊，请从候选列表中选择',
            },
          ];
          customTaskIds.clear();
          for (const definition of taskDefinitions) {
            customTaskIds.add(definition.taskId);
          }
          customSendBatch = {
            id: 901,
            bot_uuid: 'bot-1',
            connector_id: 'wxwork-local',
            channel: 'wxwork_database',
            mode: 'send',
            status: 'failed',
            total_tasks: taskDefinitions.length,
            pending_tasks: 0,
            running_tasks: 0,
            succeeded_tasks: 0,
            failed_tasks: taskDefinitions.length,
            cancelled_tasks: 0,
            interrupted_tasks: 0,
            created_by: 'tester@example.com',
            last_action_by: 'tester@example.com',
            error_message: null,
            version: 1,
            created_at: new Date().toISOString(),
            started_at: new Date().toISOString(),
            paused_at: null,
            finished_at: new Date().toISOString(),
            cancelled_at: null,
            total_count: taskDefinitions.length,
            sent_count: 0,
            failed_count: taskDefinitions.length,
            unknown_count: 0,
            skipped_count: 0,
            duplicate_target_count: 0,
            items: taskDefinitions.map((definition) => ({
              draft_id: definition.draftId,
              outcome: 'failed',
              error_code: definition.errorCode,
              error_message: definition.errorMessage,
              enter_dispatched: false,
              message_sent: false,
              terminal_confirmed: true,
              terminal_source: 'runtime',
              started_at: new Date().toISOString(),
              completed_at: new Date().toISOString(),
            })),
            tasks: taskDefinitions.map((definition, index) => ({
              id: definition.taskId,
              execution_batch_id: 901,
              draft_id: definition.draftId,
              draft_text_snapshot: `Draft ${definition.draftId}`,
              target_conversation_snapshot: definition.targetConversationSnapshot,
              channel: 'wxwork_database',
              action: 'send_message',
              status: 'failed',
              sequence_no: index + 1,
              attempt_count: 1,
              max_attempts: 1,
              idempotency_key: `broadcast:${definition.taskId}:1`,
              request_digest: `fixture-digest-${definition.taskId}`,
              runtime_task_id: `runtime-${definition.taskId}`,
              error_code: definition.errorCode,
              error_message: definition.errorMessage,
              operator_note: null,
              created_at: new Date().toISOString(),
              started_at: new Date().toISOString(),
              finished_at: new Date().toISOString(),
              cancelled_at: null,
              updated_at: new Date().toISOString(),
              retry_allowed: false,
              send_outcome: 'failed',
              enter_dispatched: false,
              message_sent: false,
              terminal_confirmed: true,
              terminal_source: 'runtime',
              attachments: [],
            })),
          };
          await fulfillOk(route, customSendBatch);
          return;
        }
      }
      if (
        request.method() === 'GET' &&
        url.pathname === '/api/v1/broadcast/executions' &&
        customSendBatch
      ) {
        await fulfillOk(route, [customSendBatch]);
        return;
      }
      if (
        request.method() === 'GET' &&
        url.pathname === '/api/v1/broadcast/executions/901' &&
        customSendBatch
      ) {
        await fulfillOk(route, customSendBatch);
        return;
      }
      await route.fallback();
    });

    await page.route(
      '**/api/v1/broadcast/execution-tasks/*/attempts**',
      async (route) => {
        const taskId = Number(route.request().url().split('/').slice(-2)[0]);
        if (customTaskIds.has(taskId)) {
          await fulfillOk(route, []);
          return;
        }
        await route.fallback();
      },
    );

    await page.goto('/home/broadcast');
    await page.locator('[role="tab"]').first().click();
    await page
      .getByTestId('broadcast-secondary-tabs')
      .locator('[role="tab"]')
      .nth(2)
      .click();
    await page
      .getByTestId('broadcast-group-rule-target-conversation-search')
      .fill('发送时查找群聊');
    await page
      .getByTestId('broadcast-group-rule-target-conversation-search')
      .press('Enter');
    await page
      .getByRole('button', { name: zhHansBroadcastActions.saveGroupRule })
      .click();
    await expect.poll(() => deferredRuleSaved).toBeTruthy();
    await expect(page.locator('body')).toContainText(
      zhHansBroadcastGroupRule.targetResolution.deferred,
    );

    await page.locator('[role="tab"]').nth(1).click();
    await page.getByTestId('broadcast-import-upload-input').setInputFiles({
      name: 'customers.csv',
      mimeType: 'text/csv',
      buffer: Buffer.from('customers', 'utf-8'),
    });
    await expect(page.locator('body')).toContainText('已匹配');
    await expect(page.locator('body')).not.toContainText(
      'TARGET_GROUP_NOT_FOUND',
    );
    await expect(page.locator('body')).not.toContainText(
      'TARGET_GROUP_AMBIGUOUS',
    );

    await page
      .getByTestId('broadcast-import-template-select')
      .selectOption({ label: 'Arrival Reminder' });
    await page.getByTestId('broadcast-import-select-all-checkbox').click();
    await page.getByTestId('broadcast-import-apply-template-button').click();
    await page.getByTestId('broadcast-import-generate-drafts-button').click();
    await page
      .getByTestId('broadcast-import-generate-drafts-confirm-button')
      .click();

    await page.locator('[role="tab"]').nth(2).click();
    await expect(page.getByTestId('broadcast-draft-detail')).toContainText(
      '发送时查找群聊',
    );
    await expect(page.locator('body')).not.toContainText(
      'TARGET_GROUP_NOT_FOUND',
    );
    await expect(page.locator('body')).not.toContainText(
      'TARGET_GROUP_AMBIGUOUS',
    );

    await page.getByTestId('broadcast-draft-select-all-checkbox').click();
    await page.getByTestId('broadcast-draft-batch-send-button').click();
    await page
      .getByTestId('broadcast-draft-batch-send-confirm-button')
      .click();

    await expect
      .poll(() => capturedExecutionBody ?? null)
      .not.toBeNull();
    expect(capturedExecutionBody).toMatchObject({
      mode: 'send',
      draft_ids: [1, 2],
    });
    await expect(
      page.getByTestId('broadcast-execution-task-row-9101'),
    ).toContainText('TARGET_GROUP_NOT_FOUND');
    await expect(
      page.getByTestId('broadcast-execution-task-row-9102'),
    ).toContainText('TARGET_GROUP_AMBIGUOUS');
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
