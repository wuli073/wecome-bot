import { useEffect, useMemo, useState } from 'react';
import { toast } from 'sonner';
import { useTranslation } from 'react-i18next';
import { Tabs, TabsContent } from '@/components/ui/tabs';
import { backendClient } from '@/app/infra/http';

import BroadcastHeader from './BroadcastHeader';
import BroadcastTabs from './BroadcastTabs';
import VariableMappingPanel from './rules/VariableMappingPanel';
import TemplatePanel from './rules/TemplatePanel';
import GroupMatchingPanel from './rules/GroupMatchingPanel';
import ImportMatchingPanel from './import/ImportMatchingPanel';
import DraftQueue from './drafts/DraftQueue';
import DraftDetail from './drafts/DraftDetail';
import ExecutionLogPanel from './logs/ExecutionLogPanel';
import {
  applyRulesDataToSnapshot,
  broadcastPasteOnlyAdapter,
  createBroadcastDataSource,
} from '../datasources/BroadcastDataSource';
import type {
  BroadcastBatchState,
  BroadcastDraft,
  BroadcastPasteDraftRequest,
  BroadcastScope,
  BroadcastRulesTab,
  BroadcastStatusFilter,
  BroadcastTopTab,
} from '../types';

const draftStatusOrder = ['pending', 'pasted', 'failed', 'completed'] as const;

function sleep(ms: number) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function getErrorMessage(error: unknown, fallback: string): string {
  if (
    error &&
    typeof error === 'object' &&
    'data' in error &&
    (error as { data?: unknown }).data &&
    typeof (error as { data?: unknown }).data === 'object'
  ) {
    const details = (error as { data: { details?: unknown; message?: unknown } }).data;
    if (Array.isArray(details.details) && details.details.length > 0) {
      return String(details.details[0]);
    }
    if (typeof details.message === 'string' && details.message.trim()) {
      return details.message;
    }
  }
  if (error && typeof error === 'object' && 'msg' in error) {
    return String((error as { msg: unknown }).msg);
  }
  if (error instanceof Error && error.message) {
    return error.message;
  }
  return fallback;
}

function getConnectorId(adapterConfig: object): string | null {
  const config = adapterConfig as Record<string, unknown>;
  const connectorId = config.connector_id ?? config.connectorId;
  return typeof connectorId === 'string' && connectorId.trim()
    ? connectorId.trim()
    : null;
}

export default function BroadcastWorkspace() {
  const { t } = useTranslation();
  const dataSource = useMemo(() => createBroadcastDataSource(), []);
  const initialSnapshot = useMemo(() => dataSource.loadSnapshot(), [dataSource]);
  const [snapshot, setSnapshot] = useState(initialSnapshot);
  const [scope, setScope] = useState<BroadcastScope>(() => ({
    botUuid: initialSnapshot.scope.botUuid,
    connectorId: initialSnapshot.scope.connectorId,
  }));
  const [topTab, setTopTab] = useState<BroadcastTopTab>('rules');
  const [rulesTab, setRulesTab] = useState<BroadcastRulesTab>('variables');
  const [searchTerm, setSearchTerm] = useState('');
  const [statusFilter, setStatusFilter] =
    useState<BroadcastStatusFilter>('all');
  const [selectedDraftId, setSelectedDraftId] = useState<number | null>(
    snapshot.drafts[0]?.id ?? null,
  );
  const [selectedDraftIds, setSelectedDraftIds] = useState<number[]>([]);
  const [editingDraftId, setEditingDraftId] = useState<number | null>(null);
  const [draftEditorText, setDraftEditorText] = useState('');
  const [batchState, setBatchState] = useState<BroadcastBatchState>({
    phase: 'idle',
    total: 0,
    completed: 0,
  });
  const [rulesLoading, setRulesLoading] = useState(false);
  const [rulesSaving, setRulesSaving] = useState(false);
  const [rulesError, setRulesError] = useState<string | null>(null);

  const topTabOptions = useMemo(
    () => [
      { value: 'rules' as const, label: t('broadcast.topTabs.rules') },
      { value: 'import' as const, label: t('broadcast.topTabs.import') },
      { value: 'drafts' as const, label: t('broadcast.topTabs.drafts') },
      { value: 'logs' as const, label: t('broadcast.topTabs.logs') },
    ],
    [t],
  );

  const rulesTabOptions = useMemo(
    () => [
      {
        value: 'variables' as const,
        label: t('broadcast.rulesTabs.variables'),
      },
      {
        value: 'templates' as const,
        label: t('broadcast.rulesTabs.templates'),
      },
      {
        value: 'groups' as const,
        label: t('broadcast.rulesTabs.groups'),
      },
    ],
    [t],
  );

  const filteredDrafts = useMemo(() => {
    const normalizedSearch = searchTerm.trim().toLowerCase();
    return snapshot.drafts.filter((draft) => {
      const matchesStatus =
        statusFilter === 'all' ? true : draft.status === statusFilter;
      const matchesSearch = normalizedSearch
        ? [
            draft.customerName,
            draft.conversationName,
            draft.templateName,
            draft.draftText,
          ]
            .join(' ')
            .toLowerCase()
            .includes(normalizedSearch)
        : true;
      return matchesStatus && matchesSearch;
    });
  }, [searchTerm, snapshot.drafts, statusFilter]);

  const activeDraft = useMemo(
    () =>
      snapshot.drafts.find((draft) => draft.id === selectedDraftId) ??
      filteredDrafts[0] ??
      null,
    [filteredDrafts, selectedDraftId, snapshot.drafts],
  );

  const groupedDrafts = useMemo(
    () =>
      draftStatusOrder.map((status) => ({
        status,
        drafts: filteredDrafts.filter((draft) => draft.status === status),
      })),
    [filteredDrafts],
  );

  useEffect(() => {
    if (activeDraft) {
      setSelectedDraftId(activeDraft.id);
      return;
    }

    if (filteredDrafts.length > 0) {
      setSelectedDraftId(filteredDrafts[0].id);
    }
  }, [activeDraft, filteredDrafts]);

  useEffect(() => {
    setSelectedDraftIds((current) =>
      current.filter((draftId) =>
        snapshot.drafts.some((draft) => draft.id === draftId),
      ),
    );
  }, [snapshot.drafts]);

  useEffect(() => {
    let cancelled = false;

    const loadRules = async (resolvedScope: BroadcastScope) => {
      setRulesLoading(true);
      setRulesError(null);

      try {
        const rulesData = await dataSource.loadRulesData(resolvedScope);
        if (cancelled) {
          return;
        }
        setScope(resolvedScope);
        setSnapshot((current) => applyRulesDataToSnapshot(current, rulesData));
      } catch (error) {
        if (cancelled) {
          return;
        }
        setRulesError(getErrorMessage(error, t('common.error')));
      } finally {
        if (!cancelled) {
          setRulesLoading(false);
        }
      }
    };

    const bootstrapRules = async () => {
      let resolvedScope = initialSnapshot.scope;

      try {
        const response = await backendClient.getBots();
        const databaseBot = response.bots.find((bot) => {
          if (!bot.uuid || !bot.enable || bot.adapter !== 'wxwork_database') {
            return false;
          }
          return Boolean(getConnectorId(bot.adapter_config));
        });

        if (databaseBot?.uuid) {
          const connectorId = getConnectorId(databaseBot.adapter_config);
          if (connectorId) {
            resolvedScope = {
              botUuid: databaseBot.uuid,
              connectorId,
            };
          }
        }
      } catch {
        // Fall back to the seeded mock scope when bot discovery is unavailable.
      }

      await loadRules(resolvedScope);
    };

    void bootstrapRules();

    return () => {
      cancelled = true;
    };
  }, [dataSource, initialSnapshot.scope, t]);

  const refreshRules = async (nextScope: BroadcastScope = scope) => {
    const rulesData = await dataSource.loadRulesData(nextScope);
    setScope(nextScope);
    setSnapshot((current) => applyRulesDataToSnapshot(current, rulesData));
  };

  const runRulesMutation = async (
    action: () => Promise<void>,
    successMessage: string,
  ) => {
    setRulesSaving(true);
    setRulesError(null);

    try {
      await action();
      await refreshRules();
      toast.success(successMessage);
    } catch (error) {
      const message = getErrorMessage(error, t('common.error'));
      setRulesError(message);
      toast.error(message);
      throw error;
    } finally {
      setRulesSaving(false);
    }
  };

  const handleSelectDraft = (draftId: number) => {
    setSelectedDraftId(draftId);
  };

  const handleToggleDraftSelection = (draftId: number, checked: boolean) => {
    setSelectedDraftIds((current) =>
      checked
        ? Array.from(new Set([...current, draftId]))
        : current.filter((item) => item !== draftId),
    );
  };

  const handleSaveDraft = () => {
    if (!editingDraftId) {
      return;
    }

    setSnapshot((current) =>
      dataSource.saveDraftText(current, editingDraftId, draftEditorText),
    );
    setEditingDraftId(null);
    toast.success(t('broadcast.toasts.draftSaved'));
  };

  const handleStartEdit = (draft: BroadcastDraft) => {
    setEditingDraftId(draft.id);
    setDraftEditorText(draft.draftText);
  };

  const handleCancelEdit = () => {
    setEditingDraftId(null);
    setDraftEditorText('');
  };

  const handleRunMockBatch = async () => {
    const targetDraftIds =
      selectedDraftIds.length > 0
        ? selectedDraftIds
        : activeDraft
          ? [activeDraft.id]
          : [];

    if (targetDraftIds.length === 0) {
      toast.error(t('broadcast.toasts.noDraftSelected'));
      return;
    }

    const targetDrafts = snapshot.drafts.filter((draft) =>
      targetDraftIds.includes(draft.id),
    );
    setBatchState({
      phase: 'running',
      total: targetDrafts.length,
      completed: 0,
      currentLabel: targetDrafts[0]?.customerName ?? '',
    });

    for (let index = 0; index < targetDrafts.length; index += 1) {
      const draft = targetDrafts[index];
      await sleep(120);
      setSnapshot((current) =>
        dataSource.applyDraftStatus(current, [draft.id], 'pasted'),
      );
      setBatchState({
        phase: 'running',
        total: targetDrafts.length,
        completed: index + 1,
        currentLabel: draft.customerName,
      });
    }

    const newLogs = targetDrafts.map((draft, index) => ({
      id:
        Math.max(0, ...snapshot.executionLogs.map((log) => log.id)) + index + 1,
      draftId: draft.id,
      customerName: draft.customerName,
      conversationName: draft.conversationName,
      status: 'pasted' as const,
      action: 'mock_paste' as const,
      message: `已为 ${draft.customerName} 准备写入内容，等待人工确认。`,
      timestamp: new Date(Date.now() + index).toISOString(),
    }));

    setSnapshot((current) => dataSource.appendLogs(current, newLogs));
    setBatchState({
      phase: 'completed',
      total: targetDrafts.length,
      completed: targetDrafts.length,
      currentLabel: targetDrafts[targetDrafts.length - 1]?.customerName,
    });
    toast.success(t('broadcast.toasts.batchCompleted'));
  };

  const requestPreview: BroadcastPasteDraftRequest | null = activeDraft
    ? {
        botUuid: activeDraft.botUuid,
        connectorId: activeDraft.connectorId,
        broadcastDraftId: activeDraft.id,
        conversationName: activeDraft.conversationName,
        draftText:
          editingDraftId === activeDraft.id
            ? draftEditorText
            : activeDraft.draftText,
        idempotencyKey: `broadcast-${activeDraft.id}-mock`,
      }
    : null;

  const runtimePreview = requestPreview
    ? broadcastPasteOnlyAdapter.toRuntimePayload(
        requestPreview,
        'sha256:mock-request-digest',
      )
    : null;

  return (
    <div className="flex min-h-full flex-col gap-4 pb-4">
      <BroadcastHeader snapshot={snapshot} />

      <Tabs
        value={topTab}
        onValueChange={(value) => setTopTab(value as BroadcastTopTab)}
        className="flex flex-col gap-4"
      >
        <BroadcastTabs options={topTabOptions} />

        <TabsContent value="rules" className="mt-0">
          <Tabs
            value={rulesTab}
            onValueChange={(value) => setRulesTab(value as BroadcastRulesTab)}
            className="flex flex-col gap-4"
          >
            <BroadcastTabs options={rulesTabOptions} size="compact" />
            <TabsContent value="variables" className="mt-0">
              <VariableMappingPanel
                variableProfile={snapshot.variableProfile}
                templates={snapshot.templates}
                loading={rulesLoading}
                saving={rulesSaving}
                error={rulesError}
                onSave={(profile) =>
                  runRulesMutation(
                    async () => {
                      await dataSource.saveVariableProfile(scope, profile);
                    },
                    t('broadcast.toasts.rulesSaved'),
                  )
                }
              />
            </TabsContent>
            <TabsContent value="templates" className="mt-0">
              <TemplatePanel
                scope={scope}
                templates={snapshot.templates}
                mappings={snapshot.variableMappings}
                loading={rulesLoading}
                saving={rulesSaving}
                error={rulesError}
                onCreate={(draft) =>
                  runRulesMutation(
                    async () => {
                      await dataSource.createTemplate(scope, draft);
                    },
                    t('broadcast.toasts.templateSaved'),
                  )
                }
                onUpdate={(templateId, draft) =>
                  runRulesMutation(
                    async () => {
                      await dataSource.updateTemplate(scope, templateId, draft);
                    },
                    t('broadcast.toasts.templateSaved'),
                  )
                }
                onDelete={(templateId) =>
                  runRulesMutation(
                    async () => {
                      await dataSource.deleteTemplate(scope, templateId);
                    },
                    t('broadcast.toasts.templateDeleted'),
                  )
                }
                onRenderPreview={async (payload) => {
                  const variables = snapshot.variableMappings.reduce<
                    Record<string, string>
                  >((acc, mapping) => {
                    acc[mapping.variableKey] = mapping.sampleValue;
                    return acc;
                  }, {});

                  if (payload.templateId) {
                    return dataSource.renderTemplate(scope, {
                      templateId: payload.templateId,
                      variables,
                    });
                  }

                  return dataSource.renderTemplate(scope, {
                    content: payload.content ?? '',
                    variables,
                  });
                }}
              />
            </TabsContent>
            <TabsContent value="groups" className="mt-0">
              <GroupMatchingPanel
                scope={scope}
                rules={snapshot.groupRules}
                groupNames={snapshot.groupNames}
                loading={rulesLoading}
                saving={rulesSaving}
                error={rulesError}
                onCreateRule={(draft) =>
                  runRulesMutation(
                    async () => {
                      await dataSource.createGroupRule(scope, draft);
                    },
                    t('broadcast.toasts.groupRuleSaved'),
                  )
                }
                onUpdateRule={(ruleId, draft) =>
                  runRulesMutation(
                    async () => {
                      await dataSource.updateGroupRule(scope, ruleId, draft);
                    },
                    t('broadcast.toasts.groupRuleSaved'),
                  )
                }
                onDeleteRule={(ruleId) =>
                  runRulesMutation(
                    async () => {
                      await dataSource.deleteGroupRule(scope, ruleId);
                    },
                    t('broadcast.toasts.groupRuleDeleted'),
                  )
                }
                onMatchRule={(sourceValue) =>
                  dataSource.matchGroupRule(scope, sourceValue)
                }
                onCreateGroupNames={(names) =>
                  runRulesMutation(
                    async () => {
                      await dataSource.createGroupNames(scope, names);
                    },
                    t('broadcast.toasts.groupNamesSaved'),
                  )
                }
                onDeleteGroupName={(groupNameId) =>
                  runRulesMutation(
                    async () => {
                      await dataSource.deleteGroupName(scope, groupNameId);
                    },
                    t('broadcast.toasts.groupNameDeleted'),
                  )
                }
              />
            </TabsContent>
          </Tabs>
        </TabsContent>

        <TabsContent value="import" className="mt-0">
          <ImportMatchingPanel rows={snapshot.importPreviewRows} />
        </TabsContent>

        <TabsContent value="drafts" className="mt-0">
          <div className="grid gap-4 xl:grid-cols-[360px_minmax(0,1fr)]">
            <DraftQueue
              drafts={groupedDrafts}
              searchTerm={searchTerm}
              statusFilter={statusFilter}
              selectedDraftId={selectedDraftId}
              selectedDraftIds={selectedDraftIds}
              batchState={batchState}
              onSearchTermChange={setSearchTerm}
              onStatusFilterChange={setStatusFilter}
              onSelectDraft={handleSelectDraft}
              onToggleDraftSelection={handleToggleDraftSelection}
              onRunMockBatch={() => void handleRunMockBatch()}
            />
            <DraftDetail
              draft={activeDraft}
              editingDraftId={editingDraftId}
              draftEditorText={draftEditorText}
              batchState={batchState}
              requestPreview={requestPreview}
              runtimePreview={runtimePreview}
              onStartEdit={handleStartEdit}
              onDraftEditorTextChange={setDraftEditorText}
              onSaveDraft={handleSaveDraft}
              onCancelEdit={handleCancelEdit}
            />
          </div>
        </TabsContent>

        <TabsContent value="logs" className="mt-0">
          <ExecutionLogPanel logs={snapshot.executionLogs} />
        </TabsContent>
      </Tabs>
    </div>
  );
}
