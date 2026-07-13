import { expect, test, type Page } from '@playwright/test';

import { installLangBotApiMocks } from './fixtures/langbot-api';

async function expectHomeShell(page: Page) {
  await expect(page).toHaveURL(/\/home\/monitoring$/);
  await expect(page.getByText('Home').first()).toBeVisible();
  await expect(page.getByRole('button', { name: 'Dashboard' })).toBeVisible();
  await expect(page.getByText('Total Messages').first()).toBeVisible();
  await expect(page.getByText('Unable to connect to server')).toHaveCount(0);
}

async function expectNoLocalLoginCopy(page: Page) {
  for (const text of [
    'Welcome',
    'Login with Space',
    'Login with password',
    'Forgot Password?',
  ]) {
    await expect(page.getByText(text)).toHaveCount(0);
  }
}

test('root route opens the authenticated home shell without local login', async ({
  page,
}) => {
  await installLangBotApiMocks(page);

  await page.goto('/');

  await expectHomeShell(page);
  await expectNoLocalLoginCopy(page);
});

test('/login redirects to the authenticated home shell without rendering login UI', async ({
  page,
}) => {
  await installLangBotApiMocks(page);

  await page.goto('/login');

  await expectHomeShell(page);
  await expectNoLocalLoginCopy(page);
});

test('clearing localStorage and sessionStorage still keeps the app on the home shell after reload', async ({
  page,
}) => {
  await installLangBotApiMocks(page);

  await page.goto('/home');
  await expectHomeShell(page);

  await page.evaluate(() => {
    localStorage.clear();
    sessionStorage.clear();
  });
  await page.reload();

  await expectHomeShell(page);
  await expectNoLocalLoginCopy(page);
});

test('direct /home/monitoring access works without token or userEmail gate', async ({
  page,
}) => {
  await installLangBotApiMocks(page);

  await page.goto('/home/monitoring');

  await expectHomeShell(page);
  await expectNoLocalLoginCopy(page);
});

test('home shell never renders removed local login copy', async ({ page }) => {
  await installLangBotApiMocks(page);

  await page.goto('/home/monitoring');

  await expectNoLocalLoginCopy(page);
});
