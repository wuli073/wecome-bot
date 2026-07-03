import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Trash2 } from 'lucide-react';

import { Alert, AlertDescription } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';

import type {
  BroadcastMessageTemplate,
  BroadcastMergeMode,
  BroadcastVariableMappingRule,
  BroadcastVariableProfile,
} from '../../types';
import {
  BROADCAST_MERGE_MODE_LABELS,
  buildVariableMappings,
  buildTemplatePreviewVariables,
  reindexMappingRules,
  validateAndNormalizeVariableProfile,
} from '../../utils';

interface VariableMappingPanelProps {
  variableProfile: BroadcastVariableProfile;
  templates: BroadcastMessageTemplate[];
  loading: boolean;
  saving: boolean;
  error: string | null;
  onSave: (profile: BroadcastVariableProfile) => Promise<void>;
}

const mergeModeOptions: BroadcastMergeMode[] = [
  'first',
  'lines',
  'unique_lines',
  'commas',
  'unique_commas',
];

function nextRuleOrder(rules: BroadcastVariableMappingRule[]): number {
  return rules.length === 0
    ? 1
    : Math.max(...rules.map((rule) => rule.order)) + 1;
}

export default function VariableMappingPanel({
  variableProfile,
  templates,
  loading,
  saving,
  error,
  onSave,
}: VariableMappingPanelProps) {
  const { t } = useTranslation();
  const [draft, setDraft] = useState<BroadcastVariableProfile>(variableProfile);
  const [validationError, setValidationError] = useState<string | null>(null);

  useEffect(() => {
    setDraft(variableProfile);
    setValidationError(null);
  }, [variableProfile]);

  const mappings = useMemo(
    () => buildVariableMappings(draft, templates),
    [draft, templates],
  );

  const previewText = useMemo(() => {
    const firstTemplate = templates[0];
    if (!firstTemplate) {
      return '';
    }

    const variables = buildTemplatePreviewVariables(mappings);
    return firstTemplate.body.replaceAll(
      /{{\s*([A-Za-z0-9_\-\u4e00-\u9fff]+)\s*}}/g,
      (token, key: string) => variables[key] || token,
    );
  }, [mappings, templates]);

  const handleRuleChange = (
    index: number,
    key: keyof BroadcastVariableMappingRule,
    value: string | number,
  ) => {
    setValidationError(null);
    setDraft((current) => ({
      ...current,
      mappingRules: current.mappingRules.map((rule, ruleIndex) =>
        ruleIndex === index
          ? {
              ...rule,
              [key]: value,
            }
          : rule,
      ),
    }));
  };

  const handleAddRule = () => {
    setValidationError(null);
    setDraft((current) => ({
      ...current,
      mappingRules: [
        ...current.mappingRules,
        {
          sourceField: '',
          variableKey: '',
          mergeMode: 'first',
          order: nextRuleOrder(current.mappingRules),
        },
      ],
    }));
  };

  const handleDeleteRule = (index: number) => {
    setValidationError(null);
    setDraft((current) => ({
      ...current,
      mappingRules: reindexMappingRules(
        current.mappingRules.filter((_, ruleIndex) => ruleIndex !== index),
      ),
    }));
  };

  const handleSave = async () => {
    const result = validateAndNormalizeVariableProfile(draft);
    setDraft(result.cleanedProfile);
    if (result.issues.length > 0) {
      setValidationError(result.issues[0].message);
      return;
    }
    await onSave(result.cleanedProfile);
  };

  return (
    <div
      className="grid gap-4 xl:grid-cols-[minmax(0,1.4fr)_minmax(320px,0.8fr)] xl:items-start"
      data-testid="broadcast-variable-mapping-panel"
    >
      <Card className="gap-4">
        <CardHeader>
          <CardTitle>{t('broadcast.rules.variableMapping.title')}</CardTitle>
          <CardDescription>
            {t('broadcast.rules.variableMapping.description')}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {loading ? (
            <div className="text-sm text-muted-foreground">
              {t('common.loading')}
            </div>
          ) : null}
          {error ? (
            <Alert variant="destructive">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          ) : null}
          {validationError ? (
            <Alert variant="destructive">
              <AlertDescription>{validationError}</AlertDescription>
            </Alert>
          ) : null}

          <div className="space-y-2">
            <Label htmlFor="broadcast-group-field">
              {t('broadcast.fields.groupField')}
            </Label>
            <Input
              id="broadcast-group-field"
              value={draft.groupField ?? ''}
              onChange={(event) =>
                setDraft((current) => ({
                  ...current,
                  groupField: event.target.value,
                }))
              }
              placeholder={t('broadcast.placeholders.groupField')}
            />
          </div>

          <div className="space-y-3">
            {draft.mappingRules.map((rule, index) => (
              <div key={`${rule.order}-${index}`} className="rounded-lg border p-3">
                <div className="mb-3 flex items-center justify-between gap-3">
                  <div className="text-sm font-medium">{`第 ${index + 1} 条规则`}</div>
                  <Button
                    type="button"
                    size="sm"
                    variant="ghost"
                    aria-label={`删除第 ${index + 1} 条规则`}
                    onClick={() => handleDeleteRule(index)}
                  >
                    <Trash2 className="size-4" />
                  </Button>
                </div>
                <div className="grid gap-3 md:grid-cols-2">
                  <div className="space-y-2">
                    <Label htmlFor={`broadcast-mapping-source-field-${index}`}>
                      {t('broadcast.fields.sourceField')}
                    </Label>
                    <Input
                      id={`broadcast-mapping-source-field-${index}`}
                      aria-label={`第 ${index + 1} 条规则的表格字段`}
                      value={rule.sourceField}
                      onChange={(event) =>
                        handleRuleChange(index, 'sourceField', event.target.value)
                      }
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor={`broadcast-mapping-variable-key-${index}`}>
                      {t('broadcast.fields.variableKey')}
                    </Label>
                    <Input
                      id={`broadcast-mapping-variable-key-${index}`}
                      aria-label={`第 ${index + 1} 条规则的消息变量`}
                      value={rule.variableKey}
                      onChange={(event) =>
                        handleRuleChange(index, 'variableKey', event.target.value)
                      }
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor={`broadcast-mapping-merge-mode-${index}`}>
                      {t('broadcast.fields.mergeMode')}
                    </Label>
                    <Select
                      value={rule.mergeMode}
                      onValueChange={(value) =>
                        handleRuleChange(
                          index,
                          'mergeMode',
                          value as BroadcastMergeMode,
                        )
                      }
                    >
                      <SelectTrigger
                        id={`broadcast-mapping-merge-mode-${index}`}
                        aria-label={`第 ${index + 1} 条规则的多条数据处理方式`}
                      >
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {mergeModeOptions.map((mode) => (
                          <SelectItem key={mode} value={mode}>
                            {BROADCAST_MERGE_MODE_LABELS[mode]}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor={`broadcast-mapping-order-${index}`}>
                      {t('broadcast.fields.order')}
                    </Label>
                    <Input
                      id={`broadcast-mapping-order-${index}`}
                      aria-label={`第 ${index + 1} 条规则的显示顺序`}
                      type="number"
                      value={rule.order}
                      onChange={(event) =>
                        handleRuleChange(
                          index,
                          'order',
                          Number(event.target.value || '0'),
                        )
                      }
                    />
                  </div>
                </div>
              </div>
            ))}
          </div>

          <div className="flex flex-wrap gap-2">
            <Button type="button" variant="outline" onClick={handleAddRule}>
              {t('broadcast.actions.addMappingRule')}
            </Button>
            <Button type="button" disabled={saving} onClick={() => void handleSave()}>
              {t('broadcast.actions.saveVariableProfile')}
            </Button>
          </div>
        </CardContent>
      </Card>

      <div className="grid gap-4 xl:sticky xl:top-0">
        <Card className="gap-4">
          <CardHeader>
            <CardTitle>{t('broadcast.rules.variablePool')}</CardTitle>
            <CardDescription>
              {t('broadcast.rules.variablePoolDescription')}
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-wrap gap-2">
            {mappings.map((mapping) => (
              <Badge key={mapping.id} variant="secondary">
                {`{{${mapping.variableKey}}}`}
              </Badge>
            ))}
            {mappings.length === 0 ? (
              <span className="text-sm text-muted-foreground">
                {t('broadcast.rules.variablePoolEmpty')}
              </span>
            ) : null}
          </CardContent>
        </Card>

        <Card className="gap-4">
          <CardHeader>
            <CardTitle>{t('broadcast.rules.preview')}</CardTitle>
            <CardDescription>
              {t('broadcast.rules.previewDescription')}
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Textarea
              value={previewText}
              readOnly
              className="min-h-48 whitespace-pre-wrap"
            />
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
