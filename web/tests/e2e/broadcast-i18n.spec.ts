import { expect, test } from '@playwright/test';

import enUS from '../../src/i18n/locales/en-US';
import jaJP from '../../src/i18n/locales/ja-JP';
import zhHans from '../../src/i18n/locales/zh-Hans';

function flattenKeys(
  value: unknown,
  prefix = '',
  output: string[] = [],
): string[] {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    output.push(prefix);
    return output;
  }

  for (const [key, nestedValue] of Object.entries(value)) {
    flattenKeys(nestedValue, prefix ? `${prefix}.${key}` : key, output);
  }

  return output;
}

function flattenStringValues(
  value: unknown,
  prefix = '',
  output: Array<{ key: string; value: string }> = [],
): Array<{ key: string; value: string }> {
  if (typeof value === 'string') {
    output.push({ key: prefix, value });
    return output;
  }

  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return output;
  }

  for (const [key, nestedValue] of Object.entries(value)) {
    flattenStringValues(nestedValue, prefix ? `${prefix}.${key}` : key, output);
  }

  return output;
}
const groupNameActionKeys = ['addGroupNames', 'refreshGroupNames'];
const groupNameRuleKeys = [
  'groupNameDirectory',
  'groupNameDirectoryDescription',
  'groupNamesMaintained',
  'noGroupNames',
  'groupNameSourceManual',
  'groupNameSourceSynced',
  'groupNameStableIdReady',
  'groupNameStableIdPending',
  'groupNameSelectableResolved',
  'groupNameSelectableDeferred',
];
const groupNameToastKeys = [
  'groupNamesSaved',
  'groupNameAdded',
  'groupNameExists',
  'groupNameRequired',
  'groupNameReloadMissing',
  'groupNamesSynced',
  'groupNameDeleted',
];

function pickGroupNameTranslations(locale: any) {
  const broadcast = locale.broadcast as Record<string, any>;
  return {
    actions: Object.fromEntries(
      groupNameActionKeys.map((key) => [key, broadcast.actions[key]]),
    ),
    rules: Object.fromEntries(
      groupNameRuleKeys.map((key) => [key, broadcast.rules[key]]),
    ),
    toasts: Object.fromEntries(
      groupNameToastKeys.map((key) => [key, broadcast.toasts[key]]),
    ),
    groupRule: {
      targetResolution: {
        deferred: broadcast.groupRule.targetResolution.deferred,
      },
    },
  };
}

function placeholders(value: string): string[] {
  return [...value.matchAll(/{{\s*([^{}]+?)\s*}}/g)]
    .map((match) => match[1])
    .sort();
}

test.describe('broadcast i18n', () => {
  test('keeps broadcast locale trees aligned and free of placeholder corruption', () => {
    const zhBroadcast = zhHans.broadcast as Record<string, any>;
    const enBroadcast = enUS.broadcast as Record<string, any>;

    expect(flattenKeys(zhBroadcast).sort()).toEqual(
      flattenKeys(enBroadcast).sort(),
    );
    expect(flattenKeys(zhBroadcast.drafts).sort()).toEqual(
      flattenKeys(enBroadcast.drafts).sort(),
    );

    const zhGroupNames = pickGroupNameTranslations(zhHans);
    const enGroupNames = pickGroupNameTranslations(enUS);
    const jaGroupNames = pickGroupNameTranslations(jaJP);

    expect(flattenKeys(zhGroupNames).sort()).toEqual(
      flattenKeys(enGroupNames).sort(),
    );
    expect(flattenKeys(zhGroupNames).sort()).toEqual(
      flattenKeys(jaGroupNames).sort(),
    );

    for (const locale of [zhGroupNames, enGroupNames, jaGroupNames]) {
      expect(JSON.stringify(locale)).not.toMatch(/\?{3,}/);
    }

    const zhStrings = Object.fromEntries(
      flattenStringValues(zhGroupNames).map(({ key, value }) => [key, value]),
    );
    const enStrings = Object.fromEntries(
      flattenStringValues(enGroupNames).map(({ key, value }) => [key, value]),
    );
    const jaStrings = Object.fromEntries(
      flattenStringValues(jaGroupNames).map(({ key, value }) => [key, value]),
    );
    for (const [key, value] of Object.entries(zhStrings)) {
      expect(placeholders(value)).toEqual(placeholders(enStrings[key]));
      expect(placeholders(value)).toEqual(placeholders(jaStrings[key]));
    }

    expect(zhBroadcast.scope.selectBot).toBe('选择 Bot');
    expect(zhBroadcast.scope.selectConnector).toBe('选择 Connector');
    expect(enBroadcast.scope.selectBot).toBe('Select Bot');
    expect(enBroadcast.scope.selectConnector).toBe('Select Connector');

    expect(zhBroadcast.groupRule.customerName).toBe('客户名称');
    expect(zhBroadcast.groupRule.targetConversationSearchPlaceholder).toBe(
      '搜索目标群聊名称',
    );
    expect(zhBroadcast.groupRule.targetConversationSelectPlaceholder).toBe(
      '请选择带稳定 ID 的目标群聊',
    );
    expect(zhBroadcast.groupRule.targetConversationSelectionRequired).toBe(
      '请先从候选列表中选择目标群聊',
    );
    expect(zhBroadcast.groupRule.targetConversationLegacyReselect).toBe(
      '该历史规则缺少稳定目标群聊 ID，请重新选择。',
    );
    expect(zhBroadcast.groupRule.preview.empty).toBe(
      '输入客户名称并执行匹配预览。',
    );

    expect(enBroadcast.groupRule.customerName).toBe('Customer name');
    expect(enBroadcast.groupRule.targetConversationSearchPlaceholder).toBe(
      'Search target conversation name',
    );
    expect(enBroadcast.groupRule.targetConversationSelectPlaceholder).toBe(
      'Select a target conversation with a stable ID',
    );
    expect(enBroadcast.groupRule.targetConversationSelectionRequired).toBe(
      'Select a target conversation from the candidate list first.',
    );
    expect(enBroadcast.groupRule.targetConversationLegacyReselect).toBe(
      'This legacy rule is missing a stable target conversation ID. Please reselect it.',
    );
    expect(enBroadcast.groupRule.preview.empty).toBe(
      'Enter a customer name and run the match preview.',
    );

    expect(zhBroadcast.bulkGroupAssignment.title).toBe('批量分配群聊');
    expect(zhBroadcast.bulkGroupAssignment.customerName).toBe('客户名称');
    expect(zhBroadcast.bulkGroupAssignment.rawRowCount).toBe('原始行数');
    expect(zhBroadcast.bulkGroupAssignment.targetConversation).toBe('目标群聊');
    expect(zhBroadcast.bulkGroupAssignment.searchConversation).toBe(
      '搜索目标群聊名称',
    );

    expect(enBroadcast.bulkGroupAssignment.title).toBe(
      'Bulk assign conversations',
    );
    expect(enBroadcast.bulkGroupAssignment.customerName).toBe('Customer name');
    expect(enBroadcast.bulkGroupAssignment.rawRowCount).toBe('Raw rows');
    expect(enBroadcast.bulkGroupAssignment.targetConversation).toBe(
      'Target conversation',
    );
    expect(enBroadcast.bulkGroupAssignment.searchConversation).toBe(
      'Search target conversation name',
    );

    expect(zhBroadcast.drafts.batchWriteConfirmTitle).toBe(
      '\u5c06\u9009\u4e2d\u8349\u7a3f\u5199\u5165\u8f93\u5165\u6846',
    );
    expect(zhBroadcast.drafts.batchWriteConfirmDescription).toBe(
      '\u672c\u6b21\u5c06\u5199\u5165 {{draftCount}} \u6761\u8349\u7a3f\uff0c\u6d89\u53ca {{conversationCount}} \u4e2a\u76ee\u6807\u7fa4\u804a\uff0c\u5305\u542b {{attachmentCount}} \u4e2a\u9644\u4ef6\uff1b\u91cd\u590d\u76ee\u6807\u7fa4\u804a {{duplicateTargetCount}} \u4e2a\u3002\u6267\u884c\u671f\u95f4\u8bf7\u52ff\u5207\u6362\u7a97\u53e3\uff0c\u4e5f\u4e0d\u8981\u64cd\u4f5c\u9f20\u6807\u548c\u952e\u76d8\u3002',
    );
    expect(enBroadcast.drafts.batchWriteConfirmTitle).toBe(
      'Write selected drafts to the input box',
    );
    expect(enBroadcast.drafts.batchWriteConfirmDescription).toBe(
      'This will submit {{draftCount}} draft(s) for {{conversationCount}} target conversation(s), including {{attachmentCount}} attachment(s). Duplicate targets: {{duplicateTargetCount}}. During execution, do not switch windows or use the mouse and keyboard.',
    );
  });
});
