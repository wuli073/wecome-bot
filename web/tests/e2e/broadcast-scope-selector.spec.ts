import { expect, test } from '@playwright/test';

import { installLangBotApiMocks } from './fixtures/langbot-api';

test.describe('broadcast scope selector', () => {
  test('shows bot and connector selectors when multiple database bots are available', async ({
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
            connector_id: 'wxwork-local-a',
          },
        },
        {
          uuid: 'bot-2',
          name: 'Broadcast Bot B',
          enable: true,
          adapter: 'wxwork_database',
          adapter_config: {
            connector_id: 'wxwork-local-b',
          },
        },
      ],
    });

    await page.goto('/home/broadcast');
    await expect(page).toHaveURL(/\/home\/broadcast$/);

    await expect(page.getByTestId('broadcast-bot-select')).toBeVisible();
    await expect(page.getByTestId('broadcast-connector-select')).toBeVisible();

    await expect(page.getByTestId('broadcast-bot-select')).toContainText(
      'Broadcast Bot A',
    );
    await expect(page.getByTestId('broadcast-connector-select')).toContainText(
      'wxwork-local-a',
    );

    await page.getByTestId('broadcast-bot-select').click();
    await page.getByRole('option', { name: 'Broadcast Bot B' }).click();

    await expect(page.getByTestId('broadcast-bot-select')).toContainText(
      'Broadcast Bot B',
    );
    await expect(page.getByTestId('broadcast-connector-select')).toContainText(
      'wxwork-local-b',
    );
  });
});
