import { expect, test } from '@playwright/test';

import { installLangBotApiMocks } from './fixtures/langbot-api';

const adapters = [
  {
    name: 'playwright-adapter',
    label: { en_US: 'Playwright Adapter', zh_Hans: 'Playwright Adapter' },
    description: { en_US: 'Test adapter', zh_Hans: 'Test adapter' },
    spec: { categories: [], config: [], help_links: [] },
  },
];

async function installReadyWizardRoutes(
  page: Parameters<typeof installLangBotApiMocks>[0],
  readyStatus = 200,
) {
  await page.route('**/readyz', async (route) => {
    await route.fulfill({
      status: readyStatus,
      contentType: 'application/json',
      body: JSON.stringify({
        status: readyStatus === 200 ? 'ready' : 'initializing',
      }),
    });
  });
  await page.route('**/api/v1/platform/adapters', async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({ code: 0, message: 'ok', data: { adapters } }),
    });
  });
  await page.route('**/api/v1/system/info', async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        code: 0,
        message: 'ok',
        data: {
          wizard_status: 'none',
          wizard_progress: null,
          cloud_service_url: '',
        },
      }),
    });
  });
}

test.describe('quick start wizard readiness', () => {
  test('does not load adapters or expose skip while the backend is initializing', async ({
    page,
  }) => {
    await installLangBotApiMocks(page);
    let adapterRequests = 0;
    await installReadyWizardRoutes(page, 503);
    await page.route('**/api/v1/platform/adapters', async (route) => {
      adapterRequests += 1;
      await route.abort();
    });

    await page.goto('/wizard');

    await expect(
      page.getByText('The service is initializing. Please wait.'),
    ).toBeVisible();
    await page.waitForTimeout(750);
    expect(adapterRequests).toBe(0);
    await expect(page.getByRole('button', { name: 'Skip' })).toBeHidden();
  });

  test('loads platforms after readiness and persists a skip only once', async ({
    page,
  }) => {
    await installLangBotApiMocks(page);
    await installReadyWizardRoutes(page);
    let wizardStatus: 'none' | 'skipped' = 'none';
    let completedRequests = 0;
    await page.route('**/api/v1/system/info', async (route) => {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          code: 0,
          message: 'ok',
          data: {
            wizard_status: wizardStatus,
            wizard_progress: null,
            cloud_service_url: '',
          },
        }),
      });
    });
    await page.route('**/api/v1/system/wizard/completed', async (route) => {
      completedRequests += 1;
      wizardStatus = 'skipped';
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({ code: 0, message: 'ok', data: {} }),
      });
    });

    await page.goto('/wizard');

    await expect(page.getByText('Select a Platform')).toBeVisible();
    await page.getByText('Playwright Adapter').click();
    await expect(
      page.getByRole('button', { name: 'Confirm, Create Bot' }),
    ).toBeEnabled();

    await page.getByRole('button', { name: 'Skip' }).click();
    await page.getByRole('dialog').getByRole('button', { name: 'OK' }).click();

    await expect(page).toHaveURL(/\/home\/monitoring$/);
    expect(completedRequests).toBe(1);
  });
});
