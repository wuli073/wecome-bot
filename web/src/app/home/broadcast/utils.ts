import type {
  BroadcastImportDetail,
  BroadcastGroupMatchType,
  BroadcastMessageTemplate,
  BroadcastMergeMode,
  BroadcastStatus,
  BroadcastVariableMapping,
  BroadcastVariableSampleState,
  BroadcastVariableMappingRule,
  BroadcastVariableProfile,
} from './types';
import { getBroadcastDiagnostics } from './diagnostics';

export const BROADCAST_MERGE_MODE_LABELS: Record<BroadcastMergeMode, string> = {
  first: '只取第一条',
  lines: '每条换行显示',
  unique_lines: '去重后换行显示',
  commas: '用逗号连接',
  unique_commas: '去重后用逗号连接',
};

export const BROADCAST_GROUP_MATCH_TYPE_LABELS: Record<
  BroadcastGroupMatchType,
  string
> = {
  exact: '完全一致',
  contains: '包含关键词',
  regex: '按规则匹配',
};

export const BROADCAST_STATUS_LABELS: Record<BroadcastStatus, string> = {
  pending: '待发送',
  pasted: '已写入输入框',
  failed: '处理失败',
  completed: '已完成',
  sent: '已发送',
  invalid: '无效',
};

export interface BroadcastValidationIssue {
  message: string;
}

export interface BroadcastVariableProfileValidationResult {
  cleanedProfile: BroadcastVariableProfile;
  issues: BroadcastValidationIssue[];
}

function normalizeWhitespace(value: string | null | undefined): string {
  return String(value ?? '').trim();
}

function normalizeFieldName(value: string | null | undefined): string {
  return normalizeWhitespace(value).replace(/^\uFEFF/, '');
}

function findRawFieldValue(
  row: { rawData: Record<string, string> },
  sourceField: string,
): string {
  const normalizedSourceField = normalizeFieldName(sourceField);
  for (const [key, value] of Object.entries(row.rawData || {})) {
    if (normalizeFieldName(key) === normalizedSourceField) {
      return normalizeWhitespace(value);
    }
  }
  return '';
}

export function reindexMappingRules(
  rules: BroadcastVariableMappingRule[],
): BroadcastVariableMappingRule[] {
  return rules.map((rule, index) => ({
    ...rule,
    order: index + 1,
  }));
}

export function getVisibleVariableKey(variableKey: string): string {
  const normalized = normalizeWhitespace(variableKey);
  return normalized || '未填写';
}

function hasBraceWrapper(value: string): boolean {
  return value.includes('{{') || value.includes('}}');
}

export function validateAndNormalizeVariableProfile(
  profile: BroadcastVariableProfile,
): BroadcastVariableProfileValidationResult {
  const normalizedGroupField = normalizeWhitespace(profile.groupField);
  const normalizedRules = profile.mappingRules.map((rule) => ({
    sourceField: normalizeWhitespace(rule.sourceField),
    variableKey: normalizeWhitespace(rule.variableKey),
    mergeMode: rule.mergeMode,
    order: Number.isInteger(rule.order) ? rule.order : Number(rule.order),
  }));

  const cleanedRules = reindexMappingRules(
    normalizedRules.filter(
      (rule) => !(rule.sourceField === '' && rule.variableKey === ''),
    ),
  );

  const issues: BroadcastValidationIssue[] = [];
  const seenVariableKeys = new Set<string>();

  if (!normalizedGroupField) {
    issues.push({ message: '请填写分组字段' });
  } else if (hasBraceWrapper(normalizedGroupField)) {
    issues.push({
      message: `请填写“客户名称”，不要填写“${normalizedGroupField}”`,
    });
  }

  if (cleanedRules.length === 0) {
    issues.push({ message: '请至少添加一条变量对应规则' });
  }

  cleanedRules.forEach((rule, index) => {
    const rowNumber = index + 1;
    if (!rule.sourceField && rule.variableKey) {
      issues.push({ message: `第 ${rowNumber} 条规则缺少表格字段` });
    }
    if (rule.sourceField && !rule.variableKey) {
      issues.push({ message: `第 ${rowNumber} 条规则缺少消息变量` });
    }

    if (rule.sourceField && hasBraceWrapper(rule.sourceField)) {
      const sourceLabel = rule.sourceField.replace(/[{}]/g, '') || '客户名称';
      issues.push({
        message: `请填写“${sourceLabel}”，不要填写“${rule.sourceField}”`,
      });
    }

    if (rule.variableKey && hasBraceWrapper(rule.variableKey)) {
      issues.push({
        message: `请填写“${rule.sourceField || '消息变量'}”，不要填写“${rule.variableKey}”`,
      });
    }

    if (!Object.hasOwn(BROADCAST_MERGE_MODE_LABELS, rule.mergeMode)) {
      issues.push({
        message: `第 ${rowNumber} 条规则的多条数据处理方式无效`,
      });
    }

    if (!Number.isInteger(rule.order) || rule.order <= 0) {
      issues.push({ message: `第 ${rowNumber} 条规则的显示顺序无效` });
    }

    if (rule.variableKey) {
      if (seenVariableKeys.has(rule.variableKey)) {
        issues.push({ message: `消息变量“${rule.variableKey}”重复` });
      } else {
        seenVariableKeys.add(rule.variableKey);
      }
    }
  });

  return {
    cleanedProfile: {
      groupField: normalizedGroupField || null,
      mappingRules: cleanedRules,
    },
    issues,
  };
}

export function buildVariableMappings(
  profile: BroadcastVariableProfile,
  templates: BroadcastMessageTemplate[],
  importDetail?: BroadcastImportDetail | null,
): BroadcastVariableMapping[] {
  const diagnostics = getBroadcastDiagnostics();
  const execute = () => {
    const requiredVariables = new Set(
      templates.flatMap((template) => template.variableKeys),
    );
    const rows = importDetail?.rows ?? [];

    return profile.mappingRules
      .slice()
      .sort((left, right) => left.order - right.order)
      .filter((rule) => normalizeWhitespace(rule.variableKey) !== '')
      .map((rule, index) => {
        const sampleValue = rows.reduce<string>((current, row) => {
          if (current) {
            return current;
          }
          return findRawFieldValue(row, rule.sourceField);
        }, '');

        const sampleState: BroadcastVariableSampleState =
          rows.length === 0 ? 'no_import' : sampleValue ? 'ready' : 'no_value';

        return {
          id: index + 1,
          sourceField: rule.sourceField,
          variableKey: rule.variableKey,
          mergeMode: rule.mergeMode,
          order: rule.order,
          sampleValue,
          sampleState,
          required: requiredVariables.has(rule.variableKey),
        };
      });
  };

  if (!diagnostics) {
    return execute();
  }

  let result: BroadcastVariableMapping[] = [];
  void diagnostics.measure(
    'buildVariableMappings',
    () => {
      result = execute();
      return result;
    },
    {
      timingBucket: 'buildVariableMappings',
      stack: new Error().stack,
      meta: {
        templateCount: templates.length,
        rowCount: importDetail?.rows?.length ?? 0,
        mappingRuleCount: profile.mappingRules.length,
      },
    },
  );
  return result;
}

export function buildTemplatePreviewVariables(
  mappings: BroadcastVariableMapping[],
): Record<string, string> {
  return mappings.reduce<Record<string, string>>((acc, mapping) => {
    if (!normalizeWhitespace(mapping.variableKey)) {
      return acc;
    }
    acc[mapping.variableKey] = mapping.sampleValue;
    return acc;
  }, {});
}
