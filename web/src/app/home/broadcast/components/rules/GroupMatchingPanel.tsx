import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';

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
import { Switch } from '@/components/ui/switch';

import GroupConversationSelector from '../shared/GroupConversationSelector';
import GroupMatchPreview from '../shared/GroupMatchPreview';
import type {
  BroadcastGroupMatchResult,
  BroadcastGroupMatchType,
  BroadcastGroupName,
  BroadcastGroupRule,
  BroadcastGroupRuleDraft,
  BroadcastScope,
} from '../../types';
import { BROADCAST_GROUP_MATCH_TYPE_LABELS } from '../../utils';

interface GroupMatchingPanelProps {
  scope: BroadcastScope;
  rules: BroadcastGroupRule[];
  groupNames: BroadcastGroupName[];
  loading: boolean;
  saving: boolean;
  error: string | null;
  onCreateRule: (draft: BroadcastGroupRuleDraft) => Promise<void>;
  onUpdateRule: (
    ruleId: number,
    draft: BroadcastGroupRuleDraft,
  ) => Promise<void>;
  onDeleteRule: (ruleId: number) => Promise<void>;
  onMatchRule: (sourceValue: string) => Promise<BroadcastGroupMatchResult>;
  onCreateGroupNames: (names: string[]) => Promise<void>;
  onSyncGroupNames: () => Promise<void>;
  onDeleteGroupName: (groupNameId: number) => Promise<void>;
}

function toRuleDraft(rule: BroadcastGroupRule | null): BroadcastGroupRuleDraft {
  if (!rule) {
    return {
      sourceValue: '',
      matchType: 'exact',
      matchExpression: '',
      targetConversationId: '',
      targetConversationName: '',
      priority: 0,
      enabled: true,
    };
  }

  return {
    id: rule.id,
    sourceValue: rule.sourceValue,
    matchType: rule.matchType,
    matchExpression: rule.matchExpression,
    targetConversationId: rule.targetConversationId ?? '',
    targetConversationName: rule.targetConversationName,
    priority: rule.priority,
    enabled: rule.enabled,
  };
}

export default function GroupMatchingPanel({
  scope: _scope,
  rules,
  groupNames,
  loading,
  saving,
  error,
  onCreateRule,
  onUpdateRule,
  onDeleteRule,
  onMatchRule,
  onCreateGroupNames,
  onSyncGroupNames,
  onDeleteGroupName,
}: GroupMatchingPanelProps) {
  const { t } = useTranslation();
  const [activeRuleId, setActiveRuleId] = useState<number | 'new'>(
    rules[0]?.id ?? 'new',
  );
  const [draft, setDraft] = useState<BroadcastGroupRuleDraft>(
    toRuleDraft(rules[0] ?? null),
  );
  const [matchInput, setMatchInput] = useState('');
  const [matchResult, setMatchResult] =
    useState<BroadcastGroupMatchResult | null>(null);
  const [groupNamesInput, setGroupNamesInput] = useState('');
  const [targetConversationKeyword, setTargetConversationKeyword] = useState(
    rules[0]?.targetConversationName ?? '',
  );
  const [selectionError, setSelectionError] = useState<string | null>(null);

  const activeRule =
    activeRuleId === 'new'
      ? null
      : (rules.find((rule) => rule.id === activeRuleId) ?? null);

  useEffect(() => {
    setDraft(toRuleDraft(activeRule));
    setTargetConversationKeyword(activeRule?.targetConversationName ?? '');
    setSelectionError(null);
  }, [activeRule]);

  const enabledRules = rules.filter((rule) => rule.enabled);
  const selectableGroupNames = groupNames.filter((item) =>
    Boolean(item.externalConversationId?.trim()),
  );
  const requiresTargetConversationReselect =
    Boolean(activeRule) &&
    !draft.targetConversationId.trim() &&
    Boolean(draft.targetConversationName.trim());

  const handleSaveRule = async () => {
    if (!draft.targetConversationId.trim()) {
      setSelectionError(
        t('broadcast.groupRule.targetConversationSelectionRequired'),
      );
      return;
    }
    setSelectionError(null);
    if (activeRule) {
      await onUpdateRule(activeRule.id, draft);
      return;
    }
    await onCreateRule(draft);
  };

  return (
    <div
      className="grid gap-4 xl:grid-cols-[300px_minmax(0,1fr)_320px]"
      data-testid="broadcast-group-matching-panel"
    >
      <Card className="gap-4">
        <CardHeader>
          <CardTitle>{t('broadcast.rules.groupMatching.title')}</CardTitle>
          <CardDescription>
            {t('broadcast.rules.groupMatching.description')}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <Button
            type="button"
            variant={activeRuleId === 'new' ? 'default' : 'outline'}
            className="w-full"
            onClick={() => setActiveRuleId('new')}
          >
            {t('broadcast.actions.newGroupRule')}
          </Button>
          {rules.map((rule) => (
            <button
              key={rule.id}
              type="button"
              className={`w-full rounded-xl border p-3 text-left transition-colors ${
                activeRule?.id === rule.id
                  ? 'border-blue-500 bg-blue-50'
                  : 'hover:bg-muted/40'
              }`}
              onClick={() => setActiveRuleId(rule.id)}
            >
              <div className="flex items-center justify-between gap-2">
                <div className="font-medium">{rule.sourceValue}</div>
                <Badge variant={rule.enabled ? 'secondary' : 'outline'}>
                  {BROADCAST_GROUP_MATCH_TYPE_LABELS[rule.matchType]}
                </Badge>
              </div>
              <div className="mt-1 text-xs text-muted-foreground">
                {rule.targetConversationName}
              </div>
              {rule.invalidLegacy ? (
                <div className="mt-1 text-xs text-amber-600">
                  {rule.invalidReason || '无效历史规则，不参与匹配。'}
                </div>
              ) : null}
            </button>
          ))}
        </CardContent>
      </Card>

      <Card className="gap-4">
        <CardHeader>
          <CardTitle>
            {activeRule
              ? t('broadcast.actions.editGroupRule')
              : t('broadcast.actions.newGroupRule')}
          </CardTitle>
          <CardDescription>
            {t('broadcast.rules.groupMatching.editorDescription')}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {loading ? (
            <div className="text-sm text-muted-foreground">
              {t('common.loading')}
            </div>
          ) : null}
          {error || selectionError ? (
            <Alert variant="destructive">
              <AlertDescription>{selectionError || error}</AlertDescription>
            </Alert>
          ) : null}

          <div className="grid gap-3 md:grid-cols-2">
            {draft.matchType === 'exact' ? (
              <div className="space-y-2">
                <Label htmlFor="broadcast-group-rule-source-value">
                  {t('broadcast.groupRule.customerName')}
                </Label>
                <Input
                  id="broadcast-group-rule-source-value"
                  value={draft.sourceValue}
                  onChange={(event) =>
                    setDraft((current) => ({
                      ...current,
                      sourceValue: event.target.value,
                      matchExpression: event.target.value,
                    }))
                  }
                />
              </div>
            ) : (
              <div className="space-y-2">
                <Label htmlFor="broadcast-group-rule-source-value">
                  {t('broadcast.fields.sourceValue')}
                </Label>
                <Input
                  id="broadcast-group-rule-source-value"
                  value={draft.sourceValue}
                  onChange={(event) =>
                    setDraft((current) => ({
                      ...current,
                      sourceValue: event.target.value,
                    }))
                  }
                />
              </div>
            )}
            <div className="space-y-2">
              <Label htmlFor="broadcast-group-rule-match-type">
                {t('broadcast.fields.matchType')}
              </Label>
              <Select
                value={draft.matchType}
                onValueChange={(value) =>
                  setDraft((current) => ({
                    ...current,
                    matchType: value as BroadcastGroupMatchType,
                  }))
                }
              >
                <SelectTrigger id="broadcast-group-rule-match-type">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="exact">完全一致</SelectItem>
                  <SelectItem value="contains">包含关键词</SelectItem>
                  <SelectItem value="regex">按规则匹配</SelectItem>
                </SelectContent>
              </Select>
            </div>
            {draft.matchType === 'exact' ? null : (
              <div className="space-y-2">
                <Label htmlFor="broadcast-group-rule-match-expression">
                  {t('broadcast.fields.matchExpression')}
                </Label>
                <Input
                  id="broadcast-group-rule-match-expression"
                  value={draft.matchExpression}
                  onChange={(event) =>
                    setDraft((current) => ({
                      ...current,
                      matchExpression: event.target.value,
                    }))
                  }
                />
              </div>
            )}
            <div className="space-y-2">
              <Label htmlFor="broadcast-group-rule-target-conversation-name">
                {t('broadcast.fields.targetConversationName')}
              </Label>
              <GroupConversationSelector
                groupNames={selectableGroupNames}
                value={draft.targetConversationId}
                keyword={targetConversationKeyword}
                onKeywordChange={(nextValue) => {
                  setTargetConversationKeyword(nextValue);
                  setSelectionError(null);
                  setDraft((current) => ({
                    ...current,
                    targetConversationId:
                      nextValue === current.targetConversationName
                        ? current.targetConversationId
                        : '',
                    targetConversationName: nextValue,
                  }));
                }}
                onChange={(conversation) => {
                  setSelectionError(null);
                  setDraft((current) => ({
                    ...current,
                    targetConversationId:
                      conversation?.externalConversationId ?? '',
                    targetConversationName: conversation?.name ?? '',
                  }));
                  setTargetConversationKeyword(conversation?.name ?? '');
                }}
                disabled={saving}
                searchLabel={t('broadcast.fields.targetConversationName')}
                searchPlaceholder={t(
                  'broadcast.groupRule.targetConversationSearchPlaceholder',
                )}
                emptyLabel={t(
                  'broadcast.groupRule.targetConversationSelectPlaceholder',
                )}
                searchInputTestId="broadcast-group-rule-target-conversation-search"
                listTestId="broadcast-group-rule-target-conversation-select"
              />
              {requiresTargetConversationReselect ? (
                <div className="text-xs text-amber-700">
                  {t('broadcast.groupRule.targetConversationLegacyReselect')}
                </div>
              ) : null}
            </div>
            <div className="space-y-2">
              <Label htmlFor="broadcast-group-rule-priority">
                {t('broadcast.fields.priority')}
              </Label>
              <Input
                id="broadcast-group-rule-priority"
                type="number"
                value={draft.priority}
                onChange={(event) =>
                  setDraft((current) => ({
                    ...current,
                    priority: Number(event.target.value || '0'),
                  }))
                }
              />
            </div>
            <div className="flex items-center justify-between rounded-lg border p-3">
              <div>
                <div className="text-sm font-medium">
                  {t('broadcast.fields.enabled')}
                </div>
              </div>
              <Switch
                checked={draft.enabled}
                onCheckedChange={(checked) =>
                  setDraft((current) => ({
                    ...current,
                    enabled: checked,
                  }))
                }
              />
            </div>
          </div>

          <div className="flex flex-wrap gap-2">
            <Button
              type="button"
              disabled={saving}
              onClick={() => void handleSaveRule()}
            >
              {activeRule
                ? t('broadcast.actions.saveGroupRule')
                : t('broadcast.actions.createGroupRule')}
            </Button>
            {activeRule ? (
              <Button
                type="button"
                variant="outline"
                disabled={saving}
                onClick={() => void onDeleteRule(activeRule.id)}
              >
                {t('broadcast.actions.deleteGroupRule')}
              </Button>
            ) : null}
          </div>

          <div className="space-y-2 rounded-lg border p-3">
            <Label htmlFor="broadcast-group-rule-match-preview">
              {t('broadcast.actions.matchPreview')}
            </Label>
            <div className="flex gap-2">
              <Input
                id="broadcast-group-rule-match-preview"
                value={matchInput}
                onChange={(event) => setMatchInput(event.target.value)}
                placeholder={t('broadcast.placeholders.matchSourceValue')}
              />
              <Button
                type="button"
                variant="outline"
                onClick={() =>
                  void onMatchRule(matchInput).then((result) => {
                    setMatchResult(result);
                  })
                }
              >
                {t('broadcast.actions.runMatchPreview')}
              </Button>
            </div>
            <GroupMatchPreview
              result={matchResult}
              emptyLabel={t('broadcast.groupRule.preview.empty')}
            />
          </div>
        </CardContent>
      </Card>

      <div className="grid gap-4">
        <Card className="gap-4">
          <CardHeader>
            <CardTitle>{t('broadcast.rules.ruleCoverage')}</CardTitle>
            <CardDescription>
              {t('broadcast.rules.ruleCoverageDescription')}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="rounded-xl border bg-muted/20 p-4">
              <div className="text-sm text-muted-foreground">
                {t('broadcast.summary.groupRules')}
              </div>
              <div className="mt-2 text-2xl font-semibold">{rules.length}</div>
            </div>
            <div className="rounded-xl border bg-muted/20 p-4">
              <div className="text-sm text-muted-foreground">
                {t('broadcast.rules.enabledRules')}
              </div>
              <div className="mt-2 text-2xl font-semibold">
                {enabledRules.length}
              </div>
            </div>
          </CardContent>
        </Card>

        <Card className="gap-4">
          <CardHeader>
            <CardTitle>{t('broadcast.rules.groupBuckets')}</CardTitle>
            <CardDescription>
              {t('broadcast.rules.groupBucketsDescription')}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="space-y-2">
              <Label htmlFor="broadcast-group-names-input">
                {t('broadcast.fields.groupNames')}
              </Label>
              <div className="flex gap-2">
                <Input
                  id="broadcast-group-names-input"
                  value={groupNamesInput}
                  onChange={(event) => setGroupNamesInput(event.target.value)}
                  placeholder={t('broadcast.placeholders.groupNames')}
                />
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => {
                    const names = groupNamesInput
                      .split('\n')
                      .map((item) => item.trim())
                      .filter(Boolean);
                    void onCreateGroupNames(names).then(() => {
                      setGroupNamesInput('');
                    });
                  }}
                >
                  {t('broadcast.actions.addGroupNames')}
                </Button>
                <Button
                  type="button"
                  variant="secondary"
                  disabled={saving}
                  onClick={() => void onSyncGroupNames()}
                >
                  {t('broadcast.actions.refreshGroupNames')}
                </Button>
              </div>
            </div>

            <div className="space-y-2">
              {groupNames.map((groupName) => (
                <div
                  key={groupName.id}
                  className="flex items-center justify-between rounded-lg border p-3"
                >
                  <span className="text-sm">{groupName.name}</span>
                  <Button
                    type="button"
                    size="sm"
                    variant="ghost"
                    onClick={() => void onDeleteGroupName(groupName.id)}
                  >
                    {t('common.delete')}
                  </Button>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
