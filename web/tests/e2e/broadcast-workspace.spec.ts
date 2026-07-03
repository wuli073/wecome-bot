import { expect, test } from '@playwright/test';

import { installLangBotApiMocks } from './fixtures/langbot-api';

test.describe('broadcast workspace usability', () => {
  test('shows Chinese UI, supports scrolling, validates variable mappings, and avoids runtime calls', async ({
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

    await page.goto('/home/broadcast');
    await expect(page).toHaveURL(/\/home\/broadcast$/);

    await expect(
      page.getByRole('button', { name: '群发消息' }),
    ).toBeVisible();
    await expect(
      page.getByRole('heading', { name: '群发消息工作台' }),
    ).toBeVisible();

    await expect(page.getByText('规则配置')).toBeVisible();
    await expect(page.getByText('导入匹配')).toBeVisible();
    await expect(page.getByText('审核发送')).toBeVisible();
    await expect(page.getByText('执行日志')).toBeVisible();

    await expect(page.getByText('Phase 2')).toHaveCount(0);
    await expect(page.getByText('Runtime Payload')).toHaveCount(0);
    await expect(page.getByText('Mock')).toHaveCount(0);
    await expect(page.getByText('paste-only')).toHaveCount(0);
    await expect(page.getByText('idempotencyKey')).toHaveCount(0);

    const scrollRoot = page.locator('main').nth(1);
    await scrollRoot.evaluate((node) => {
      node.scrollTo({ top: node.scrollHeight, behavior: 'instant' as ScrollBehavior });
    });
    const scrollMetrics = await scrollRoot.evaluate((node) => ({
      scrollTop: node.scrollTop,
      clientHeight: node.clientHeight,
      scrollHeight: node.scrollHeight,
    }));
    expect(scrollMetrics.scrollHeight).toBeGreaterThan(scrollMetrics.clientHeight);
    expect(scrollMetrics.scrollTop + scrollMetrics.clientHeight).toBeGreaterThanOrEqual(
      scrollMetrics.scrollHeight - 4,
    );
    await expect(page.getByRole('tab', { name: '执行日志' })).toBeVisible();

    await page.getByRole('tab', { name: '规则配置' }).click();
    await page.getByRole('tab', { name: '变量对应表' }).click();
    await expect(page.getByTestId('broadcast-variable-mapping-panel')).toBeVisible();

    await page.getByRole('button', { name: '添加映射规则' }).click();
    await page.getByRole('button', { name: '添加映射规则' }).click();

    await expect(
      page.getByRole('button', { name: '删除第 4 条规则' }),
    ).toBeVisible();
    await expect(
      page.getByRole('button', { name: '删除第 5 条规则' }),
    ).toBeVisible();

    await page.getByRole('button', { name: '删除第 5 条规则' }).click();
    await expect(
      page.getByRole('button', { name: '删除第 5 条规则' }),
    ).toHaveCount(0);
    await expect(
      page.getByRole('button', { name: '删除第 4 条规则' }),
    ).toBeVisible();

    await page.getByLabel('第 4 条规则的表格字段').fill('客户名称');
    await page.getByRole('button', { name: '保存变量配置' }).click();
    await expect(page.getByText('第 4 条规则缺少消息变量')).toBeVisible();

    await page.getByLabel('第 4 条规则的消息变量').fill('{{客户名称}}');
    await page.getByRole('button', { name: '保存变量配置' }).click();
    await expect(
      page.getByText('请填写“客户名称”，不要填写“{{客户名称}}”'),
    ).toBeVisible();

    await page.getByLabel('第 4 条规则的消息变量').fill('customer_name');
    await page.getByRole('button', { name: '保存变量配置' }).click();
    await expect(page.getByText('消息变量“customer_name”重复')).toBeVisible();

    await page.getByLabel('第 4 条规则的消息变量').fill('customer_alias');
    await page.getByRole('combobox', { name: '第 4 条规则的多条数据处理方式' }).click();
    await page.getByRole('option', { name: '去重后换行显示' }).click();
    await page.getByRole('button', { name: '保存变量配置' }).click();
    await expect(page.getByText('变量映射规则已保存')).toBeVisible();
    await expect(page.getByText('{{customer_alias}}')).toBeVisible();
    await expect(page.getByText('{{}}')).toHaveCount(0);
    await expect(page.getByText('只取第一条').first()).toBeVisible();
    await expect(page.getByText('去重后换行显示').first()).toBeVisible();

    await page.reload();
    await page.getByRole('tab', { name: '规则配置' }).click();
    await page.getByRole('tab', { name: '变量对应表' }).click();
    await expect(page.getByLabel('分组字段')).toHaveValue('Customer Name');
    await expect(page.getByLabel('第 4 条规则的消息变量')).toHaveValue(
      'customer_alias',
    );

    await page.getByRole('tab', { name: '消息模板' }).click();
    await expect(page.getByTestId('broadcast-template-panel')).toBeVisible();
    await expect(
      page.getByTestId('broadcast-template-panel').getByText('消息模板', {
        exact: true,
      }),
    ).toBeVisible();

    await page.getByRole('tab', { name: '群匹配' }).click();
    await expect(page.getByTestId('broadcast-group-matching-panel')).toBeVisible();
    await page.getByRole('combobox', { name: '匹配类型' }).click();
    await expect(page.getByRole('option', { name: '完全一致' })).toBeVisible();
    await expect(page.getByRole('option', { name: '包含关键词' })).toBeVisible();
    await expect(page.getByRole('option', { name: '按规则匹配' })).toBeVisible();
    await page.keyboard.press('Escape');

    await page.getByRole('tab', { name: '导入匹配' }).click();
    await expect(page.getByTestId('broadcast-import-table')).toBeVisible();
    await expect(page.getByRole('cell', { name: '华南物流', exact: true })).toBeVisible();

    await page.getByRole('tab', { name: '审核发送' }).click();
    const queue = page.getByTestId('broadcast-draft-queue');
    await expect(queue).toBeVisible();
    await expect(
      queue.getByRole('textbox', { name: '搜索草稿' }),
    ).toBeVisible();
    await expect(
      queue.getByRole('button', { name: '批量写入已选草稿' }),
    ).toBeVisible();

    await queue.getByRole('combobox', { name: '状态筛选' }).click();
    await expect(page.getByRole('option', { name: '待审核' })).toBeVisible();
    await expect(page.getByRole('option', { name: '已写入输入框' })).toBeVisible();
    await expect(page.getByRole('option', { name: '处理失败' })).toBeVisible();
    await expect(page.getByRole('option', { name: '已完成' })).toBeVisible();
    await page.keyboard.press('Escape');

    await queue.getByLabel('选择草稿 101').check();
    await queue.getByLabel('选择草稿 102').check();
    await page.getByRole('button', { name: '批量写入已选草稿' }).click();
    await expect(queue.getByText('正在批量写入')).toBeVisible();
    await expect(queue.getByText('批量写入完成')).toBeVisible();

    await page.getByTestId('broadcast-draft-detail').getByText('查看技术详情').click();
    await expect(
      page.getByTestId('broadcast-draft-detail').getByText('系统执行详情'),
    ).toBeVisible();

    await page.getByRole('tab', { name: '执行日志' }).click();
    await expect(page.getByTestId('broadcast-logs-table')).toBeVisible();
    await expect(page.getByText('处理失败')).toBeVisible();

    expect(
      requestPaths.filter((path) => path.startsWith('/api/v1/broadcast/')).length,
    ).toBeGreaterThan(0);
    expect(
      requestPaths.some((path) => path.includes('paste-draft')),
    ).toBeFalsy();
    expect(
      requestPaths.some((path) => path.includes('send-draft')),
    ).toBeFalsy();
  });
});
