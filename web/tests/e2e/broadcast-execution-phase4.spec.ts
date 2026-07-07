import { expect, test, type Page } from '@playwright/test';

import zhHans from '../../src/i18n/locales/zh-Hans';
import { installLangBotApiMocks } from './fixtures/langbot-api';

async function prepareDraftReview(page: Page) {
  await page.goto('/home/broadcast');
  await page.locator('[role="tab"]').nth(1).click();
  await page.getByTestId('broadcast-import-upload-input').setInputFiles({
    name: 'customers.csv',
    mimeType: 'text/csv',
    buffer: Buffer.from('customers', 'utf-8'),
  });
  await page.getByTestId('broadcast-import-select-all-checkbox').click();
  await page.getByTestId('broadcast-import-template-select').selectOption('1');
  await page.getByTestId('broadcast-import-apply-template-button').click();
  await expect(
    page.getByTestId('broadcast-import-generate-drafts-button'),
  ).toBeEnabled();
  await page.getByTestId('broadcast-import-generate-drafts-button').click();
  await page
    .getByTestId('broadcast-import-generate-drafts-confirm-button')
    .click();
  await page.locator('[role="tab"]').nth(2).click();
}

function ok(data: unknown) {
  return {
    code: 0,
    message: 'ok',
    data,
    timestamp: Date.now(),
  };
}

test.describe('broadcast execution phase 4', () => {
  test('shows business execution statuses, recovery advice, and retry-failed-items flow', async ({
    page,
  }) => {
    await installLangBotApiMocks(page, {
      authenticated: true,
      storage: {
        langbot_language: 'zh-Hans',
      },
    });

    const batchState = {
      id: 900,
      status: 'partially_failed',
      mode: 'paste_only',
      total_tasks: 3,
      pending_tasks: 0,
      running_tasks: 0,
      succeeded_tasks: 1,
      failed_tasks: 1,
      cancelled_tasks: 0,
      interrupted_tasks: 1,
      created_by: 'tester@example.com',
      last_action_by: 'tester@example.com',
      created_at: '2026-07-07T10:00:00.000Z',
      started_at: '2026-07-07T10:00:30.000Z',
      finished_at: '2026-07-07T10:02:00.000Z',
      tasks: [
        {
          id: 9001,
          execution_batch_id: 900,
          draft_id: 1,
          target_conversation_snapshot: 'Acme Freight Ops',
          draft_text_snapshot: 'Draft 1',
          action: 'paste_draft',
          status: 'failed',
          attempt_count: 1,
          idempotency_key: 'broadcast:9001:1',
          runtime_task_id: 'runtime-9001',
          error_code: 'TARGET_WINDOW_NOT_FOUND',
          error_message: 'Target window not found',
          created_at: '2026-07-07T10:00:00.000Z',
          started_at: '2026-07-07T10:00:30.000Z',
          finished_at: '2026-07-07T10:00:50.000Z',
          updated_at: '2026-07-07T10:00:50.000Z',
          attachments: [],
        },
        {
          id: 9002,
          execution_batch_id: 900,
          draft_id: 2,
          target_conversation_snapshot: 'Northwind Service Group',
          draft_text_snapshot: 'Draft 2',
          action: 'paste_draft',
          status: 'interrupted',
          attempt_count: 1,
          idempotency_key: 'broadcast:9002:1',
          runtime_task_id: 'runtime-9002',
          error_code: 'WINDOW_ACTIVATION_FAILED',
          error_message: 'Window activation failed',
          created_at: '2026-07-07T10:00:00.000Z',
          started_at: '2026-07-07T10:00:40.000Z',
          finished_at: '2026-07-07T10:00:55.000Z',
          updated_at: '2026-07-07T10:00:55.000Z',
          attachments: [],
        },
        {
          id: 9003,
          execution_batch_id: 900,
          draft_id: 3,
          target_conversation_snapshot: 'Zenith Support',
          draft_text_snapshot: 'Draft 3',
          action: 'paste_draft',
          status: 'succeeded_with_warning',
          attempt_count: 1,
          idempotency_key: 'broadcast:9003:1',
          runtime_task_id: 'runtime-9003',
          error_code: null,
          error_message: null,
          created_at: '2026-07-07T10:00:00.000Z',
          started_at: '2026-07-07T10:01:00.000Z',
          finished_at: '2026-07-07T10:01:20.000Z',
          updated_at: '2026-07-07T10:01:20.000Z',
          attachments: [],
        },
      ],
    };

    const attemptsByTaskId: Record<number, unknown[]> = {
      9001: [
        {
          id: 9101,
          execution_task_id: 9001,
          attempt_no: 1,
          idempotency_key: 'broadcast:9001:1',
          request_digest: 'digest-9001',
          runtime_task_id: 'runtime-9001',
          request_summary: '{"action":"paste_draft"}',
          response_summary: '{"status":"failed"}',
          status: 'failed',
          error_code: 'TARGET_WINDOW_NOT_FOUND',
          error_message: 'Target window not found',
          started_at: '2026-07-07T10:00:30.000Z',
          finished_at: '2026-07-07T10:00:50.000Z',
        },
      ],
      9002: [
        {
          id: 9102,
          execution_task_id: 9002,
          attempt_no: 1,
          idempotency_key: 'broadcast:9002:1',
          request_digest: 'digest-9002',
          runtime_task_id: 'runtime-9002',
          request_summary: '{"action":"paste_draft"}',
          response_summary: '{"status":"interrupted"}',
          status: 'interrupted',
          error_code: 'WINDOW_ACTIVATION_FAILED',
          error_message: 'Window activation failed',
          started_at: '2026-07-07T10:00:40.000Z',
          finished_at: '2026-07-07T10:00:55.000Z',
        },
      ],
      9003: [
        {
          id: 9103,
          execution_task_id: 9003,
          attempt_no: 1,
          idempotency_key: 'broadcast:9003:1',
          request_digest: 'digest-9003',
          runtime_task_id: 'runtime-9003',
          request_summary: '{"action":"paste_draft"}',
          response_summary: '{"status":"succeeded_with_warning"}',
          status: 'succeeded_with_warning',
          error_code: null,
          error_message: null,
          started_at: '2026-07-07T10:01:00.000Z',
          finished_at: '2026-07-07T10:01:20.000Z',
        },
      ],
    };

    const evidenceByAttemptId: Record<number, unknown> = {
      9101: {
        id: 9201,
        execution_attempt_id: 9101,
        window_title: 'WeCom',
        target_conversation: 'Acme Freight Ops',
        action: 'paste_draft',
        input_located: false,
        draft_written: false,
        send_triggered: false,
        clipboard_restored: true,
        runtime_state: 'failed',
        evidence_summary: 'Target window not found',
        technical_details: {
          error_code: 'TARGET_WINDOW_NOT_FOUND',
          stage: 'locate_window',
        },
        created_at: '2026-07-07T10:00:50.000Z',
      },
      9102: {
        id: 9202,
        execution_attempt_id: 9102,
        window_title: 'WeCom',
        target_conversation: 'Northwind Service Group',
        action: 'paste_draft',
        input_located: true,
        draft_written: false,
        send_triggered: false,
        clipboard_restored: true,
        runtime_state: 'interrupted',
        evidence_summary: 'Window activation failed',
        technical_details: {
          error_code: 'WINDOW_ACTIVATION_FAILED',
          stage: 'activate_window',
        },
        created_at: '2026-07-07T10:00:55.000Z',
      },
      9103: {
        id: 9203,
        execution_attempt_id: 9103,
        window_title: 'WeCom',
        target_conversation: 'Zenith Support',
        action: 'paste_draft',
        input_located: true,
        draft_written: true,
        send_triggered: false,
        clipboard_restored: true,
        runtime_state: 'pasted_to_input',
        evidence_summary: 'Draft written but not auto-verified',
        technical_details: {
          content_verified: false,
          warning: 'PASTE_RESULT_NOT_VERIFIED',
          stage: 'verify_input',
        },
        created_at: '2026-07-07T10:01:20.000Z',
      },
    };

    const retriedTaskIds: number[] = [];

    await page.route('**/api/v1/broadcast/executions*', async (route) => {
      const url = new URL(route.request().url());
      if (
        route.request().method() !== 'GET' ||
        url.pathname !== '/api/v1/broadcast/executions'
      ) {
        await route.fallback();
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(
          ok([
            {
              ...batchState,
              tasks: [],
            },
          ]),
        ),
      });
    });

    await page.route('**/api/v1/broadcast/executions/900*', async (route) => {
      if (route.request().method() !== 'GET') {
        await route.fallback();
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(ok(batchState)),
      });
    });

    await page.route(
      '**/api/v1/broadcast/execution-tasks/*/attempts',
      async (route) => {
        const taskId = Number(
          route
            .request()
            .url()
            .match(/execution-tasks\/(\d+)/)?.[1] ?? '0',
        );
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(ok(attemptsByTaskId[taskId] ?? [])),
        });
      },
    );

    await page.route(
      '**/api/v1/broadcast/execution-attempts/*/evidence',
      async (route) => {
        const attemptId = Number(
          route
            .request()
            .url()
            .match(/execution-attempts\/(\d+)/)?.[1] ?? '0',
        );
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(ok(evidenceByAttemptId[attemptId] ?? null)),
        });
      },
    );

    await page.route(
      '**/api/v1/broadcast/execution-tasks/*/retry',
      async (route) => {
        const taskId = Number(
          route
            .request()
            .url()
            .match(/execution-tasks\/(\d+)/)?.[1] ?? '0',
        );
        retriedTaskIds.push(taskId);
        const task = batchState.tasks.find((item) => item.id === taskId);
        if (task) {
          task.status = 'pending';
          task.error_code = null;
          task.error_message = null;
        }
        batchState.status = 'queued';
        batchState.pending_tasks = 2;
        batchState.failed_tasks = 0;
        batchState.interrupted_tasks = 0;
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(ok(task ?? null)),
        });
      },
    );

    await page.goto('/home/broadcast');
    await page.locator('[role="tab"]').nth(3).click();

    await expect(
      page.getByTestId('broadcast-batch-retry-failed-button'),
    ).toBeVisible();
    await expect(page.getByTestId('broadcast-batch-start-button')).toHaveCount(
      0,
    );
    await expect(page.getByTestId('broadcast-batch-pause-button')).toHaveCount(
      0,
    );
    await expect(page.getByTestId('broadcast-batch-cancel-button')).toHaveCount(
      0,
    );

    await expect(
      page.getByTestId('broadcast-execution-task-retry-9001'),
    ).toBeVisible();
    await expect(
      page.getByTestId('broadcast-execution-task-retry-9002'),
    ).toBeVisible();
    await expect(
      page.getByTestId('broadcast-execution-task-retry-9003'),
    ).toHaveCount(0);

    await expect(
      page.getByTestId('broadcast-execution-task-status-9003'),
    ).toContainText(zhHans.broadcast.logs.statusWarning);
    await expect(page.locator('body')).toContainText(
      zhHans.broadcast.logs.errorSuggestions.TARGET_WINDOW_NOT_FOUND,
    );
    await expect(page.locator('body')).toContainText(
      zhHans.broadcast.logs.errorSuggestions.WINDOW_ACTIVATION_FAILED,
    );
    await expect(page.locator('body')).toContainText(
      zhHans.broadcast.logs.errorSuggestions.PASTE_RESULT_NOT_VERIFIED,
    );

    await page.getByTestId('broadcast-batch-retry-failed-button').click();
    await expect(
      page.getByTestId('broadcast-batch-retry-failed-confirm-dialog'),
    ).toBeVisible();
    await page
      .getByTestId('broadcast-batch-retry-failed-confirm-button')
      .click();

    await expect
      .poll(() => retriedTaskIds.slice().sort((a, b) => a - b))
      .toEqual([9001, 9002]);
    await expect(page.locator('body')).toContainText(
      zhHans.broadcast.toasts.executionFailedTasksRetried
        .replace('{{successCount}}', '2')
        .replace('{{failedCount}}', '0'),
    );
  });

  test('hides meaningless batch controls for completed execution batches', async ({
    page,
  }) => {
    await installLangBotApiMocks(page, {
      authenticated: true,
      storage: {
        langbot_language: 'zh-Hans',
      },
    });

    const completedBatch = {
      id: 901,
      status: 'completed',
      mode: 'paste_only',
      total_tasks: 1,
      pending_tasks: 0,
      running_tasks: 0,
      succeeded_tasks: 1,
      failed_tasks: 0,
      cancelled_tasks: 0,
      interrupted_tasks: 0,
      created_by: 'tester@example.com',
      last_action_by: 'tester@example.com',
      created_at: '2026-07-07T10:00:00.000Z',
      started_at: '2026-07-07T10:00:30.000Z',
      finished_at: '2026-07-07T10:00:40.000Z',
      tasks: [
        {
          id: 9011,
          execution_batch_id: 901,
          draft_id: 1,
          target_conversation_snapshot: 'Acme Freight Ops',
          draft_text_snapshot: 'Draft 1',
          action: 'paste_draft',
          status: 'succeeded',
          attempt_count: 1,
          idempotency_key: 'broadcast:9011:1',
          runtime_task_id: 'runtime-9011',
          error_code: null,
          error_message: null,
          created_at: '2026-07-07T10:00:00.000Z',
          started_at: '2026-07-07T10:00:30.000Z',
          finished_at: '2026-07-07T10:00:40.000Z',
          updated_at: '2026-07-07T10:00:40.000Z',
          attachments: [],
        },
      ],
    };

    await page.route('**/api/v1/broadcast/executions*', async (route) => {
      const url = new URL(route.request().url());
      if (
        route.request().method() !== 'GET' ||
        url.pathname !== '/api/v1/broadcast/executions'
      ) {
        await route.fallback();
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(
          ok([
            {
              ...completedBatch,
              tasks: [],
            },
          ]),
        ),
      });
    });

    await page.route('**/api/v1/broadcast/executions/901*', async (route) => {
      if (route.request().method() !== 'GET') {
        await route.fallback();
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(ok(completedBatch)),
      });
    });

    await page.route(
      '**/api/v1/broadcast/execution-tasks/*/attempts',
      async (route) => {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(
            ok([
              {
                id: 9111,
                execution_task_id: 9011,
                attempt_no: 1,
                idempotency_key: 'broadcast:9011:1',
                request_digest: 'digest-9011',
                runtime_task_id: 'runtime-9011',
                request_summary: '{"action":"paste_draft"}',
                response_summary: '{"status":"succeeded"}',
                status: 'succeeded',
                error_code: null,
                error_message: null,
                started_at: '2026-07-07T10:00:30.000Z',
                finished_at: '2026-07-07T10:00:40.000Z',
              },
            ]),
          ),
        });
      },
    );

    await page.route(
      '**/api/v1/broadcast/execution-attempts/*/evidence',
      async (route) => {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(
            ok({
              id: 9211,
              execution_attempt_id: 9111,
              window_title: 'WeCom',
              target_conversation: 'Acme Freight Ops',
              action: 'paste_draft',
              input_located: true,
              draft_written: true,
              send_triggered: false,
              clipboard_restored: true,
              runtime_state: 'pasted_to_input',
              evidence_summary: 'Draft written to input',
              technical_details: {
                content_verified: true,
              },
              created_at: '2026-07-07T10:00:40.000Z',
            }),
          ),
        });
      },
    );

    await page.goto('/home/broadcast');
    await page.locator('[role="tab"]').nth(3).click();

    await expect(page.getByTestId('broadcast-batch-start-button')).toHaveCount(
      0,
    );
    await expect(page.getByTestId('broadcast-batch-pause-button')).toHaveCount(
      0,
    );
    await expect(page.getByTestId('broadcast-batch-resume-button')).toHaveCount(
      0,
    );
    await expect(page.getByTestId('broadcast-batch-cancel-button')).toHaveCount(
      0,
    );
    await expect(
      page.getByTestId('broadcast-batch-retry-failed-button'),
    ).toHaveCount(0);
  });

  test('uses exact zh-Hans paste verification copy without mojibake', async ({
    page,
  }) => {
    expect(zhHans.broadcast.drafts.pasteHint).toBe(
      '系统将自动搜索并进入目标群聊，然后把正文和附件粘贴到输入框。系统不会自动发送，请人工确认后发送。',
    );
    expect(zhHans.broadcast.logs.capabilityPasteVerification).toBe('内容验证');
    expect(zhHans.broadcast.logs.conversationLocatorExternalId).toBe(
      '外部会话 ID',
    );
    expect(zhHans.broadcast.logs.pasteVerificationMethod).toBe('验证方式');
    expect(zhHans.broadcast.logs.pasteVerificationMethodManual).toBe(
      '人工确认',
    );
    expect(zhHans.broadcast.logs.pasteVerificationStatus).toBe('验证状态');
    expect(zhHans.broadcast.logs.pasteVerificationAvailable).toBe('可用');
    expect(zhHans.broadcast.logs.pasteVerificationUnavailable).toBe('未启用');
    expect(zhHans.broadcast.logs.pasteVerificationUnavailableHint).toBe(
      '内容验证：未启用',
    );
    expect(zhHans.broadcast.logs.statusPasteVerified).toBe('已写入并验证');
    expect(zhHans.broadcast.toasts.pasteSubmitted).toBe('写入任务已提交');

    await installLangBotApiMocks(page, {
      authenticated: true,
      storage: {
        langbot_language: 'zh-Hans',
      },
    });

    await prepareDraftReview(page);
    await page.getByTestId('broadcast-draft-paste-button').click();
    await expect(
      page.getByTestId('broadcast-draft-paste-confirm-dialog'),
    ).toHaveCount(0);

    await expect(
      page.getByTestId('broadcast-execution-logs-table'),
    ).toBeVisible();
    await expect(page.locator('body')).toContainText(
      zhHans.broadcast.logs.capabilityPasteVerification,
    );
    await expect(page.locator('body')).toContainText(
      zhHans.broadcast.logs.pasteVerificationMethod,
    );
    await expect(page.locator('body')).toContainText(
      zhHans.broadcast.logs.pasteVerificationStatus,
    );
    await expect(page.locator('body')).toContainText('Windows UI Automation');
    await expect(page.locator('body')).toContainText(
      zhHans.broadcast.logs.pasteVerificationAvailable,
    );
    await expect(page.locator('body')).toContainText(
      zhHans.broadcast.logs.statusPasteVerified,
    );
    await expect(page.locator('body')).not.toContainText(/锟|鏀|楠岃瘉鏂瑰紡/);
  });

  test('shows backend conversation locator and manual verification labels faithfully', async ({
    page,
  }) => {
    await installLangBotApiMocks(page, {
      authenticated: true,
      storage: {
        langbot_language: 'zh-Hans',
      },
    });

    await page.route(
      '**/api/v1/broadcast/executors/capabilities*',
      async (route) => {
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
            data: {
              channel: 'wxwork_database',
              supports_paste: true,
              supports_paste_verification: false,
              requires_manual_conversation_open: false,
              conversation_locator: 'external_id',
              content_verification: 'manual',
              supports_send: false,
              supports_cancel: true,
              supports_status_query: true,
              supports_clipboard_restore: true,
              supports_evidence: true,
              executor_version: 'fixture-phase7',
              runtime_min_version: '1.0.0',
            },
            timestamp: Date.now(),
          }),
        });
      },
    );

    await page.route('**/api/v1/broadcast/executors/health*', async (route) => {
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
          data: {
            channel: 'wxwork_database',
            status: 'ready',
            protocol_version: '1.0.0',
            runtime_version: '1.0.0',
            capability: {
              channel: 'wxwork_database',
              supports_paste: true,
              supports_paste_verification: false,
              requires_manual_conversation_open: false,
              conversation_locator: 'external_id',
              content_verification: 'manual',
              supports_send: false,
              supports_cancel: true,
              supports_status_query: true,
              supports_clipboard_restore: true,
              supports_evidence: true,
              executor_version: 'fixture-phase7',
              runtime_min_version: '1.0.0',
            },
            runtime_status: {},
          },
          timestamp: Date.now(),
        }),
      });
    });

    await page.goto('/home/broadcast');
    await page.locator('[role="tab"]').nth(3).click();

    await expect(page.locator('body')).toContainText(
      zhHans.broadcast.logs.conversationLocatorExternalId,
    );
    await expect(page.locator('body')).toContainText(
      zhHans.broadcast.logs.pasteVerificationMethodManual,
    );
  });

  test('writes a single pending draft into the input box without sending', async ({
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

    await prepareDraftReview(page);
    await page.getByTestId('broadcast-draft-paste-button').click();
    await expect(
      page.getByTestId('broadcast-draft-paste-confirm-dialog'),
    ).toHaveCount(0);
    await expect(
      page.getByTestId('broadcast-execution-logs-table'),
    ).toBeVisible();

    await page.locator('[role="tab"]').nth(3).click();
    await expect(
      page.getByRole('cell', { name: 'Acme Freight', exact: true }),
    ).toBeVisible();
    await expect(
      page.locator('[data-testid="broadcast-execution-logs-table"] tbody tr'),
    ).toHaveCount(1);

    expect(requestPaths).toContain('/api/v1/broadcast/executions');
    expect(
      requestPaths.some((path) =>
        /\/api\/v1\/broadcast\/executions\/\d+\/start$/.test(path),
      ),
    ).toBeTruthy();
    expect(
      requestPaths.some((path) => path.includes('/attempts')),
    ).toBeTruthy();
    expect(
      requestPaths.some((path) => path.includes('/evidence')),
    ).toBeTruthy();
    expect(
      requestPaths.some((path) => path.includes('send-message')),
    ).toBeFalsy();
    expect(
      requestPaths.some((path) => path.includes('send-draft')),
    ).toBeFalsy();
  });

  test('prevents duplicate execution requests during a slow double click flow', async ({
    page,
  }) => {
    await installLangBotApiMocks(page, {
      authenticated: true,
      storage: {
        langbot_language: 'zh-Hans',
      },
    });

    let executionsCount = 0;
    let startCount = 0;
    let releaseExecutionResponse: (() => void) | undefined;

    await page.route('**/api/v1/broadcast/executions', async (route) => {
      if (route.request().method() !== 'POST') {
        await route.fallback();
        return;
      }
      executionsCount += 1;
      await new Promise<void>((resolve) => {
        releaseExecutionResponse = resolve;
      });
      await route.fallback();
    });

    page.on('request', (request) => {
      const url = new URL(request.url());
      if (
        request.method() === 'POST' &&
        /\/api\/v1\/broadcast\/executions\/\d+\/start$/.test(url.pathname)
      ) {
        startCount += 1;
      }
    });

    await prepareDraftReview(page);
    await page.getByTestId('broadcast-draft-paste-button').click();
    await expect(
      page.getByTestId('broadcast-draft-paste-button'),
    ).toBeDisabled();
    await page
      .getByTestId('broadcast-draft-paste-button')
      .click({ force: true });

    expect(executionsCount).toBe(1);
    expect(startCount).toBe(0);

    releaseExecutionResponse?.();

    await expect
      .poll(() => executionsCount, {
        timeout: 5000,
      })
      .toBe(1);
    await expect
      .poll(() => startCount, {
        timeout: 5000,
      })
      .toBe(1);
  });

  test('keeps paste-only actions available when paste verification is unavailable', async ({
    page,
  }) => {
    await installLangBotApiMocks(page, {
      authenticated: true,
      storage: {
        langbot_language: 'zh-Hans',
      },
    });

    await page.route(
      '**/api/v1/broadcast/executors/capabilities*',
      async (route) => {
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
            data: {
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
            timestamp: Date.now(),
          }),
        });
      },
    );

    await page.route('**/api/v1/broadcast/executors/health*', async (route) => {
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
          data: {
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
                available: false,
                reason: 'PASTE_VERIFICATION_UNAVAILABLE',
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
          },
          timestamp: Date.now(),
        }),
      });
    });

    const requestRecords: Array<{ method: string; path: string }> = [];
    page.on('request', (request) => {
      const url = new URL(request.url());
      if (url.pathname.startsWith('/api/v1/')) {
        requestRecords.push({
          method: request.method(),
          path: url.pathname,
        });
      }
    });

    await prepareDraftReview(page);
    await page.getByTestId('broadcast-draft-select-all-checkbox').click();

    await expect(
      page.getByTestId('broadcast-draft-paste-button'),
    ).toBeEnabled();
    await expect(
      page.getByTestId('broadcast-draft-batch-write-button'),
    ).toBeEnabled();
    await expect(page.locator('body')).toContainText(
      zhHans.broadcast.logs.pasteVerificationUnavailableHint,
    );

    await page.getByTestId('broadcast-draft-batch-write-button').click();
    await page
      .getByTestId('broadcast-draft-batch-write-confirm-button')
      .click();

    await page.locator('[role="tab"]').nth(3).click();
    await expect(
      page.getByTestId('broadcast-execution-logs-table'),
    ).toBeVisible();
    await expect(page.locator('body')).toContainText(
      zhHans.broadcast.logs.capabilityPasteVerification,
    );
    await expect(page.locator('body')).toContainText(
      zhHans.broadcast.logs.pasteVerificationMethod,
    );
    await expect(page.locator('body')).toContainText(
      zhHans.broadcast.logs.pasteVerificationStatus,
    );
    await expect(page.locator('body')).toContainText('Windows UI Automation');
    await expect(page.locator('body')).toContainText(
      zhHans.broadcast.logs.pasteVerificationUnavailable,
    );

    expect(
      requestRecords.some(
        ({ method, path }) =>
          method === 'POST' && path === '/api/v1/broadcast/executions',
      ),
    ).toBeTruthy();
    expect(
      requestRecords.some(
        ({ method, path }) =>
          method === 'POST' &&
          /\/api\/v1\/broadcast\/executions\/\d+\/start$/.test(path),
      ),
    ).toBeTruthy();
  });

  test('stops polling execution history after the latest paste-only batch becomes terminal', async ({
    page,
  }) => {
    await installLangBotApiMocks(page, {
      authenticated: true,
      storage: {
        langbot_language: 'en-US',
      },
    });

    await page.goto('/home/broadcast');
    await expect(page).toHaveURL(/\/home\/broadcast$/);

    const counters = {
      batches: 0,
      batchDetails: 0,
      attempts: 0,
      evidence: 0,
    };
    page.on('request', (request) => {
      const url = new URL(request.url());
      if (!url.pathname.startsWith('/api/v1/broadcast/')) {
        return;
      }
      if (
        url.pathname === '/api/v1/broadcast/executions' &&
        request.method() === 'GET'
      ) {
        counters.batches += 1;
        return;
      }
      if (/^\/api\/v1\/broadcast\/executions\/\d+$/.test(url.pathname)) {
        counters.batchDetails += 1;
        return;
      }
      if (url.pathname.includes('/attempts')) {
        counters.attempts += 1;
        return;
      }
      if (url.pathname.includes('/evidence')) {
        counters.evidence += 1;
      }
    });

    await prepareDraftReview(page);
    await page.getByTestId('broadcast-draft-paste-button').click();

    await expect(
      page.getByTestId('broadcast-execution-logs-table'),
    ).toBeVisible();
    await expect(
      page.locator('[data-testid="broadcast-execution-logs-table"] tbody tr'),
    ).toHaveCount(1);

    await expect
      .poll(() => ({
        attempts: counters.attempts,
        evidence: counters.evidence,
      }))
      .toEqual({
        attempts: 1,
        evidence: 1,
      });

    const snapshot = { ...counters };
    await page.waitForTimeout(3500);

    expect(counters).toEqual(snapshot);
  });
});
