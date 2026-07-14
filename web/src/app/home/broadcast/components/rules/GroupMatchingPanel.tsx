import { useEffect, useMemo, useState } from 'react';
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Switch } from '@/components/ui/switch';

import BulkGroupAssignmentDialog from './BulkGroupAssignmentDialog';
import GroupConversationSelector from '../shared/GroupConversationSelector';
import GroupMatchPreview from '../shared/GroupMatchPreview';
import type {
  BroadcastGroupMatchResult,
  BroadcastGroupMatchType,
  BroadcastGroupName,
  BroadcastGroupRule,
  BroadcastGroupRuleCandidateList,
  BroadcastGroupRuleDraft,
  BroadcastImportBatch,
  BroadcastScope,
} from '../../types';

interface GroupMatchingPanelProps {
  scope: BroadcastScope;
  rules: BroadcastGroupRule[];
  groupNames: BroadcastGroupName[];
  batches: BroadcastImportBatch[];
  selectedBatchId: number | null;
  selectedBatch: BroadcastImportBatch | null;
  groupRuleCandidates: BroadcastGroupRuleCandidateList | null;
  groupRuleCandidatesLoading: boolean;
  loading: boolean;
  saving: boolean;
  error: string | null;
  onSelectBatch: (batchId: number) => Promise<void>;
  onOpenBulkAssignDialog: () => Promise<void>;
  onBulkAssignGroupRules: (
    batchId: number,
    items: Array<{ groupKey: string; targetConversationId: string }>,
  ) => Promise<void>;
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
  batches,
  selectedBatchId,
  selectedBatch,
  groupRuleCandidates,
  groupRuleCandidatesLoading,
  loading,
  saving,
  error,
  onSelectBatch,
  onOpenBulkAssignDialog,
  onBulkAssignGroupRules,
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
  const [bulkAssignDialogOpen, setBulkAssignDialogOpen] = useState(false);

  const activeRule =
    activeRuleId === 'new'
      ? null
      : (rules.find((rule) => rule.id === activeRuleId) ?? null);

  useEffect(() => {
    if (
      activeRuleId !== 'new' &&
      !rules.some((rule) => rule.id === activeRuleId)
    ) {
      setActiveRuleId(rules[0]?.id ?? 'new');
    }
  }, [activeRuleId, rules]);

  useEffect(() => {
    setDraft(toRuleDraft(activeRule));
    setTargetConversationKeyword(activeRule?.targetConversationName ?? '');
    setSelectionError(null);
  }, [activeRule]);

  const enabledRules = rules.filter((rule) => rule.enabled);
  const pendingCustomerStats = groupRuleCandidates?.stats ?? null;
  const selectableGroupNames = groupNames;
  const matchTypeOptions = useMemo(
    () => [
      {
        value: 'exact' as const,
        label: t('broadcast.groupRule.matchTypeOptions.exact'),
      },
      {
        value: 'contains' as const,
        label: t('broadcast.groupRule.matchTypeOptions.contains'),
      },
      {
        value: 'regex' as const,
        label: t('broadcast.groupRule.matchTypeOptions.regex'),
      },
    ],
    [t],
  );

  const handleSaveRule = async () => {
    const normalizedTargetName = draft.targetConversationName.trim();
    if (!normalizedTargetName) {
      setSelectionError(
        t('broadcast.groupRule.targetConversationNameRequired'),
      );
      return;
    }
    const normalizedDraft = {
      ...draft,
      targetConversationId: draft.targetConversationId.trim(),
      targetConversationName: normalizedTargetName,
    };
    setSelectionError(null);
    if (activeRule) {
      await onUpdateRule(activeRule.id, normalizedDraft);
      return;
    }
    await onCreateRule(normalizedDraft);
  };

  return (
    <div className="space-y-4" data-testid="broadcast-group-matching-panel">
      <Card data-testid="broadcast-group-matching-pending-customers">
        <CardHeader className="gap-2">
          <CardTitle>{t('broadcast.groupRuleCandidates.title')}</CardTitle>
          <CardDescription>
            {t('broadcast.groupRuleCandidates.description')}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-3 lg:grid-cols-[minmax(0,260px)_1fr_auto] lg:items-end">
            <div className="space-y-2">
              <div className="text-sm font-medium">
                {t('broadcast.groupRuleCandidates.selectBatch')}
              </div>
              <select
                className="border-input bg-background h-9 w-full rounded-md border px-3 py-2 text-sm"
                data-testid="broadcast-group-matching-batch-select"
                value={selectedBatchId == null ? '' : String(selectedBatchId)}
                disabled={saving || loading || batches.length === 0}
                onChange={(event) => {
                  const value = Number(event.target.value);
                  if (!Number.isFinite(value)) {
                    return;
                  }
                  void onSelectBatch(value);
                }}
              >
                <option value="">
                  {t('broadcast.groupRuleCandidates.selectBatchPlaceholder')}
                </option>
                {batches.map((batch) => (
                  <option key={batch.id} value={String(batch.id)}>
                    {batch.originalFileName}
                  </option>
                ))}
              </select>
            </div>

            {selectedBatch ? (
              <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
                <div className="rounded-lg border bg-muted/20 p-3">
                  <div className="text-xs text-muted-foreground">
                    {t('broadcast.groupRuleCandidates.fileName')}
                  </div>
                  <div className="mt-1 text-sm font-medium break-all">
                    {selectedBatch.originalFileName}
                  </div>
                </div>
                <div className="rounded-lg border bg-muted/20 p-3">
                  <div className="text-xs text-muted-foreground">
                    {t('broadcast.groupRuleCandidates.detectedField')}
                  </div>
                  <div className="mt-1 text-sm font-medium">
                    {groupRuleCandidates?.groupFieldUsed ??
                      selectedBatch.groupFieldUsed ??
                      '-'}
                  </div>
                </div>
                <div className="rounded-lg border bg-muted/20 p-3">
                  <div className="text-xs text-muted-foreground">
                    {t('broadcast.groupRuleCandidates.rawRowCount')}
                  </div>
                  <div className="mt-1 text-sm font-medium">
                    {groupRuleCandidates?.rawRowTotal ??
                      selectedBatch.totalRows}
                  </div>
                </div>
                <div className="rounded-lg border bg-muted/20 p-3">
                  <div className="text-xs text-muted-foreground">
                    {t('broadcast.groupRuleCandidates.uniqueCustomerCount')}
                  </div>
                  <div className="mt-1 text-sm font-medium">
                    {groupRuleCandidates?.uniqueCustomerTotal ?? '-'}
                  </div>
                </div>
                <div className="rounded-lg border bg-muted/20 p-3">
                  <div className="text-xs text-muted-foreground">
                    {t('broadcast.groupRuleCandidates.newCount')}
                  </div>
                  <div className="mt-1 text-sm font-medium">
                    {pendingCustomerStats?.newCount ?? 0}
                  </div>
                </div>
                <div className="rounded-lg border bg-muted/20 p-3">
                  <div className="text-xs text-muted-foreground">
                    {t('broadcast.groupRuleCandidates.configuredCount')}
                  </div>
                  <div className="mt-1 text-sm font-medium">
                    {pendingCustomerStats?.configuredCount ?? 0}
                  </div>
                </div>
                <div className="rounded-lg border bg-muted/20 p-3">
                  <div className="text-xs text-muted-foreground">
                    {t('broadcast.groupRuleCandidates.needsRepairCount')}
                  </div>
                  <div className="mt-1 text-sm font-medium">
                    {pendingCustomerStats?.needsRepairCount ?? 0}
                  </div>
                </div>
                <div className="rounded-lg border bg-muted/20 p-3">
                  <div className="text-xs text-muted-foreground">
                    {t('broadcast.groupRuleCandidates.conflictCount')}
                  </div>
                  <div className="mt-1 text-sm font-medium">
                    {pendingCustomerStats?.conflictCount ?? 0}
                  </div>
                </div>
              </div>
            ) : (
              <div className="rounded-lg border border-dashed p-4 text-sm text-muted-foreground">
                {batches.length === 0
                  ? t('broadcast.groupRuleCandidates.noBatches')
                  : t('broadcast.groupRuleCandidates.noBatchSelected')}
              </div>
            )}

            <Button
              type="button"
              data-testid="broadcast-group-matching-bulk-assign-open-button"
              disabled={selectedBatchId == null || saving}
              onClick={() => {
                setBulkAssignDialogOpen(true);
                void onOpenBulkAssignDialog();
              }}
            >
              {t('broadcast.groupRuleCandidates.bulkAssignButton', {
                count: pendingCustomerStats?.newCount ?? 0,
              })}
            </Button>
          </div>
        </CardContent>
      </Card>

      <div className="grid gap-4 xl:grid-cols-[300px_minmax(0,1fr)_320px]">
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
                    {
                      matchTypeOptions.find(
                        (option) => option.value === rule.matchType,
                      )?.label
                    }
                  </Badge>
                </div>
                <div className="mt-1 text-xs text-muted-foreground">
                  {rule.targetConversationName}
                </div>
                <div className="mt-1 text-xs text-muted-foreground">
                  {rule.targetConversationId
                    ? rule.targetConversationId
                    : t(
                        `broadcast.groupRule.targetResolution.${rule.targetResolutionStatus ?? 'unresolved'}`,
                      )}
                </div>
                {rule.invalidLegacy ? (
                  <div className="mt-1 text-xs text-amber-600">
                    {rule.invalidReason ||
                      t('broadcast.groupRule.invalidLegacy')}
                  </div>
                ) : null}
              </button>
            ))}
          </CardContent>
        </Card>

        <Card className="gap-4" data-testid="broadcast-group-rule-editor">
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
              <div className="space-y-2">
                <div className="text-sm font-medium">
                  {draft.matchType === 'exact'
                    ? t('broadcast.groupRule.customerName')
                    : t('broadcast.fields.sourceValue')}
                </div>
                <Input
                  id="broadcast-group-rule-source-value"
                  value={draft.sourceValue}
                  onChange={(event) =>
                    setDraft((current) => ({
                      ...current,
                      sourceValue: event.target.value,
                      matchExpression:
                        current.matchType === 'exact'
                          ? event.target.value
                          : current.matchExpression,
                    }))
                  }
                />
              </div>

              <div className="space-y-2">
                <div className="text-sm font-medium">
                  {t('broadcast.fields.matchType')}
                </div>
                <Select
                  value={draft.matchType}
                  onValueChange={(value) =>
                    setDraft((current) => ({
                      ...current,
                      matchType: value as BroadcastGroupMatchType,
                      matchExpression:
                        value === 'exact'
                          ? current.sourceValue
                          : current.matchExpression,
                    }))
                  }
                >
                  <SelectTrigger id="broadcast-group-rule-match-type">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {matchTypeOptions.map((option) => (
                      <SelectItem key={option.value} value={option.value}>
                        {option.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              {draft.matchType === 'exact' ? null : (
                <div className="space-y-2">
                  <div className="text-sm font-medium">
                    {t('broadcast.fields.matchExpression')}
                  </div>
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
                  onManualConfirm={(value) => {
                    const normalizedValue = value.trim();
                    setTargetConversationKeyword(normalizedValue);
                    setDraft((current) => ({
                      ...current,
                      targetConversationId:
                        normalizedValue === current.targetConversationName
                          ? current.targetConversationId
                          : '',
                      targetConversationName: normalizedValue,
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
                  searchLabel={t(
                    'broadcast.bulkGroupAssignment.targetConversation',
                  )}
                  searchPlaceholder={t(
                    'broadcast.groupRule.targetConversationSearchPlaceholder',
                  )}
                  emptyLabel={t(
                    'broadcast.groupRule.targetConversationSelectPlaceholder',
                  )}
                  missingStableIdLabel={t(
                    'broadcast.groupRule.targetConversationMissingStableId',
                  )}
                  searchInputTestId="broadcast-group-rule-target-conversation-search"
                  listTestId="broadcast-group-rule-target-conversation-select"
                />
              </div>

              <div className="space-y-2">
                <div className="text-sm font-medium">
                  {t('broadcast.fields.priority')}
                </div>
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
                <div className="text-sm font-medium">
                  {t('broadcast.fields.enabled')}
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
              <div className="text-sm font-medium">
                {t('broadcast.actions.matchPreview')}
              </div>
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
                <div className="mt-2 text-2xl font-semibold">
                  {rules.length}
                </div>
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
                <div className="text-sm font-medium">
                  {t('broadcast.fields.groupNames')}
                </div>
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

      <BulkGroupAssignmentDialog
        open={bulkAssignDialogOpen}
        loading={groupRuleCandidatesLoading}
        submitting={saving}
        candidates={groupRuleCandidates}
        groupNames={groupNames}
        onOpenChange={setBulkAssignDialogOpen}
        onSubmit={async (items) => {
          if (!selectedBatchId) {
            return;
          }
          await onBulkAssignGroupRules(selectedBatchId, items);
          setBulkAssignDialogOpen(false);
        }}
      />
    </div>
  );
}
