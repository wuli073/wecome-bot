import { useEffect, useMemo, useState } from 'react';
import { toast } from 'sonner';
import { useTranslation } from 'react-i18next';
import { Tabs, TabsContent } from '@/components/ui/tabs';
import { backendClient } from '@/app/infra/http';
import type { Bot } from '@/app/infra/entities/api';

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
  createBroadcastDataSource,
} from '../datasources/BroadcastDataSource';
import type {
  BroadcastDraft,
  BroadcastExecutionBatchSummary,
  BroadcastExecutionLog,
  BroadcastExecutorCapability,
  BroadcastExecutorHealth,
  BroadcastImportBatch,
  BroadcastImportDetail,
  BroadcastRulesTab,
  BroadcastScope,
  BroadcastStatusFilter,
  BroadcastTopTab,
} from '../types';

const draftStatusOrder = ['pending_review', 'ready', 'invalid'] as const;
const OPERATOR_EMAIL = 'tester@example.com';
const EXECUTION_TERMINAL_STATUSES = new Set([
  'completed',
  'partially_failed',
  'failed',
  'cancelled',
  'interrupted',
]);

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

function isBroadcastDatabaseBot(bot: Bot): boolean {
  if (!bot.uuid || !bot.enable || bot.adapter !== 'wxwork_database') {
    return false;
  }
  return Boolean(getConnectorId(bot.adapter_config));
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
  const [statusFilter, setStatusFilter] = useState<BroadcastStatusFilter>('all');
  const [draftImportBatchId, setDraftImportBatchId] = useState<number | null>(null);
  const [selectedDraftId, setSelectedDraftId] = useState<number | null>(
    snapshot.drafts[0]?.id ?? null,
  );
  const [selectedDraftIds, setSelectedDraftIds] = useState<number[]>([]);
  const [editingDraftId, setEditingDraftId] = useState<number | null>(null);
  const [draftEditorText, setDraftEditorText] = useState('');
  const [rulesLoading, setRulesLoading] = useState(false);
  const [rulesSaving, setRulesSaving] = useState(false);
  const [rulesError, setRulesError] = useState<string | null>(null);
  const [importBatches, setImportBatches] = useState<BroadcastImportBatch[]>([]);
  const [selectedImportId, setSelectedImportId] = useState<number | null>(null);
  const [selectedImportDetail, setSelectedImportDetail] =
    useState<BroadcastImportDetail | null>(null);
  const [importBusy, setImportBusy] = useState(false);
  const [draftBusy, setDraftBusy] = useState(false);
  const [sendBusy, setSendBusy] = useState(false);
  const [scopeOptions, setScopeOptions] = useState<
    Array<{ botUuid: string; botName: string; connectorId: string }>
  >([]);
  const [executionLogs, setExecutionLogs] = useState<BroadcastExecutionLog[]>([]);
  const [latestExecutionBatch, setLatestExecutionBatch] =
    useState<BroadcastExecutionBatchSummary | null>(null);
  const [executorCapability, setExecutorCapability] =
    useState<BroadcastExecutorCapability | null>(null);
  const [executorHealth, setExecutorHealth] =
    useState<BroadcastExecutorHealth | null>(null);
  const [pasteRequestInFlight, setPasteRequestInFlight] = useState(false);

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
      const matchesImportBatch =
        draftImportBatchId == null ? true : draft.importBatchId === draftImportBatchId;
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
      return matchesImportBatch && matchesStatus && matchesSearch;
    });
  }, [draftImportBatchId, searchTerm, snapshot.drafts, statusFilter]);

  const activeDraft = useMemo(
    () =>
      filteredDrafts.find((draft) => draft.id === selectedDraftId) ??
      filteredDrafts[0] ??
      null,
    [filteredDrafts, selectedDraftId],
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
        snapshot.drafts.some(
          (draft) =>
            draft.id === draftId &&
            draft.status !== 'invalid' &&
            !draft.draftsStale,
        ),
      ),
    );
  }, [snapshot.drafts]);

  useEffect(() => {
    if (
      draftImportBatchId != null &&
      !importBatches.some((batch) => batch.id === draftImportBatchId)
    ) {
      setDraftImportBatchId(null);
    }
  }, [draftImportBatchId, importBatches]);

  useEffect(() => {
    if (snapshot.drafts.length > 0 && !snapshot.drafts.some((draft) => draft.id === selectedDraftId)) {
      setSelectedDraftId(snapshot.drafts[0].id);
    }
  }, [selectedDraftId, snapshot.drafts]);

  const refreshExecutorState = async (nextScope: BroadcastScope = scope) => {
    try {
      const [capability, health] = await Promise.all([
        dataSource.getExecutorCapabilities(nextScope),
        dataSource.getExecutorHealth(nextScope),
      ]);
      setExecutorCapability(capability);
      setExecutorHealth(health);
    } catch {
      setExecutorCapability(null);
      setExecutorHealth(null);
    }
  };

  const refreshRules = async (nextScope: BroadcastScope = scope) => {
    const rulesData = await dataSource.loadRulesData(nextScope);
    setScope(nextScope);
    setSnapshot((current) => applyRulesDataToSnapshot(current, rulesData));
  };

  const refreshImports = async (nextScope: BroadcastScope = scope) => {
    const batches = await dataSource.listImportBatches(nextScope);
    setImportBatches(batches);

    const nextImportId =
      selectedImportId && batches.some((item) => item.id === selectedImportId)
        ? selectedImportId
        : batches[0]?.id ?? null;
    setSelectedImportId(nextImportId);

    if (nextImportId) {
      const detail = await dataSource.getImportDetail(nextScope, nextImportId);
      setSelectedImportDetail(detail);
    } else {
      setSelectedImportDetail(null);
    }
  };

  const refreshDrafts = async (
    nextScope: BroadcastScope = scope,
    focusImportBatchId?: number | null,
  ) => {
    const drafts = await dataSource.listDrafts(nextScope, {
      status: statusFilter === 'all' ? 'all' : statusFilter,
      keyword: searchTerm || undefined,
    });
    setSnapshot((current) => ({
      ...current,
      drafts,
    }));

    if (focusImportBatchId !== undefined) {
      setDraftImportBatchId(focusImportBatchId);
      setSelectedDraftId(
        drafts.find((draft) => draft.importBatchId === focusImportBatchId)?.id ??
          drafts[0]?.id ??
          null,
      );
      return;
    }

    setSelectedDraftId((current) =>
      drafts.some((draft) => draft.id === current) ? current : drafts[0]?.id ?? null,
    );
  };

  const refreshExecutionState = async (nextScope: BroadcastScope = scope) => {
    const drafts = await dataSource.listDrafts(nextScope, {
      status: statusFilter === 'all' ? 'all' : statusFilter,
      keyword: searchTerm || undefined,
    });
    setSnapshot((current) => ({
      ...current,
      drafts,
    }));

    const batchSummaries = await dataSource.listExecutionBatches(nextScope);
    const latestBatchSummary =
      [...batchSummaries].sort((left, right) => right.id - left.id)[0] ?? null;
    if (latestBatchSummary) {
      setLatestExecutionBatch(
        await dataSource.getExecutionBatchDetail(nextScope, latestBatchSummary.id),
      );
    } else {
      setLatestExecutionBatch(null);
    }

    try {
      const logs = await dataSource.listExecutionLogs(nextScope, drafts);
      setExecutionLogs(logs);
    } catch {
      setExecutionLogs([]);
    }
  };

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
        const batches = await dataSource.listImportBatches(resolvedScope);
        if (cancelled) {
          return;
        }
        setImportBatches(batches);
        const nextImportId = batches[0]?.id ?? null;
        setSelectedImportId(nextImportId);
        if (nextImportId) {
          const detail = await dataSource.getImportDetail(resolvedScope, nextImportId);
          if (cancelled) {
            return;
          }
          setSelectedImportDetail(detail);
          const drafts = await dataSource.listDrafts(resolvedScope);
          if (!cancelled) {
            setDraftImportBatchId(nextImportId);
            setSnapshot((current) => ({
              ...current,
              drafts,
            }));
          }
        } else {
          setSelectedImportDetail(null);
          setDraftImportBatchId(null);
          setSnapshot((current) => ({
            ...current,
            drafts: [],
          }));
        }

        if (!cancelled) {
          await refreshExecutionState(resolvedScope);
          await refreshExecutorState(resolvedScope);
        }
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
        const databaseBots = response.bots.filter(isBroadcastDatabaseBot);
        const nextScopeOptions = databaseBots
          .map((bot) => {
            const connectorId = getConnectorId(bot.adapter_config);
            if (!bot.uuid || !connectorId) {
              return null;
            }
            return {
              botUuid: bot.uuid,
              botName: bot.name,
              connectorId,
            };
          })
          .filter((option): option is NonNullable<typeof option> => option != null);

        if (!cancelled) {
          setScopeOptions(nextScopeOptions);
        }

        const databaseBot = databaseBots[0];
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

  useEffect(() => {
    if (
      topTab !== 'logs' ||
      !latestExecutionBatch ||
      EXECUTION_TERMINAL_STATUSES.has(latestExecutionBatch.status)
    ) {
      return;
    }

    const timer = window.setInterval(() => {
      void refreshExecutionState(scope);
    }, 2000);

    return () => {
      window.clearInterval(timer);
    };
  }, [latestExecutionBatch, scope, topTab]);

  const handleCreateExecutionBatch = async () => {
    const targetDraftIds =
      selectedDraftIds.length > 0 ? selectedDraftIds : activeDraft ? [activeDraft.id] : [];
    if (targetDraftIds.length === 0) {
      toast.error(t('broadcast.toasts.noDraftSelected'));
      return;
    }
    setDraftBusy(true);
    try {
      const batch = await dataSource.createExecutionBatch(
        scope,
        targetDraftIds,
        'paste_only',
        OPERATOR_EMAIL,
      );
      setLatestExecutionBatch(batch);
      await refreshExecutionState(scope);
      setTopTab('logs');
      toast.success(t('broadcast.toasts.executionBatchCreated'));
    } catch (error) {
      toast.error(getErrorMessage(error, t('common.error')));
    } finally {
      setDraftBusy(false);
    }
  };

  const handleBatchAction = async (action: 'start' | 'pause' | 'resume' | 'cancel') => {
    if (!latestExecutionBatch) {
      return;
    }
    setDraftBusy(true);
    try {
      const batch =
        action === 'start'
          ? await dataSource.startExecutionBatch(scope, latestExecutionBatch.id, OPERATOR_EMAIL)
          : action === 'pause'
            ? await dataSource.pauseExecutionBatch(scope, latestExecutionBatch.id, OPERATOR_EMAIL)
            : action === 'resume'
              ? await dataSource.resumeExecutionBatch(scope, latestExecutionBatch.id, OPERATOR_EMAIL)
              : await dataSource.cancelExecutionBatch(scope, latestExecutionBatch.id, OPERATOR_EMAIL);
      setLatestExecutionBatch(batch);
      await refreshExecutionState(scope);
      toast.success(
        action === 'start'
          ? t('broadcast.toasts.executionBatchStarted')
          : action === 'pause'
            ? t('broadcast.toasts.executionBatchPaused')
            : action === 'resume'
              ? t('broadcast.toasts.executionBatchResumed')
              : t('broadcast.toasts.executionBatchCancelled'),
      );
    } catch (error) {
      toast.error(getErrorMessage(error, t('common.error')));
    } finally {
      setDraftBusy(false);
    }
  };

  const handleRetryExecutionTask = async (taskId: number) => {
    setDraftBusy(true);
    try {
      await dataSource.retryExecutionTask(scope, taskId, OPERATOR_EMAIL);
      await refreshExecutionState(scope);
      toast.success(t('broadcast.toasts.executionTaskRetried'));
    } catch (error) {
      toast.error(getErrorMessage(error, t('common.error')));
    } finally {
      setDraftBusy(false);
    }
  };

  const handlePasteDraft = async (draft: BroadcastDraft) => {
    if (pasteRequestInFlight) {
      return;
    }
    setPasteRequestInFlight(true);
    setDraftBusy(true);
    try {
      const batch = await dataSource.createExecutionBatch(
        scope,
        [draft.id],
        'paste_only',
        OPERATOR_EMAIL,
      );
      setLatestExecutionBatch(batch);
      await dataSource.startExecutionBatch(scope, batch.id, OPERATOR_EMAIL);
      await refreshExecutionState(scope);
      setTopTab('logs');
      toast.success(t('broadcast.toasts.pasteSubmitted'));
    } catch (error) {
      toast.error(getErrorMessage(error, t('common.error')));
    } finally {
      setDraftBusy(false);
      setPasteRequestInFlight(false);
    }
  };

  const handleRealSendDraft = async (draft: BroadcastDraft) => {
    setSendBusy(true);
    try {
      const batch = await dataSource.createExecutionBatch(
        scope,
        [draft.id],
        'send',
        OPERATOR_EMAIL,
      );
      setLatestExecutionBatch(batch);
      setTopTab('logs');
      const taskId = batch.tasks[0]?.id;
      if (!taskId) {
        throw new Error(t('broadcast.logs.missingSendTask'));
      }
      const confirmation = await dataSource.createSendConfirmation(
        scope,
        taskId,
        OPERATOR_EMAIL,
      );
      await dataSource.sendExecutionTask(scope, taskId, confirmation.token, OPERATOR_EMAIL);
      await refreshExecutionState(scope);
      toast.success(t('broadcast.toasts.sendSubmitted'));
    } catch (error) {
      toast.error(getErrorMessage(error, t('common.error')));
    } finally {
      setSendBusy(false);
    }
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

  const handleSaveDraft = async () => {
    if (!editingDraftId) {
      return;
    }

    setDraftBusy(true);
    try {
      const updated = await dataSource.updateDraftText(
        scope,
        editingDraftId,
        draftEditorText,
      );
      setSnapshot((current) => ({
        ...current,
        drafts: current.drafts.map((draft) =>
          draft.id === updated.id ? updated : draft,
        ),
      }));
      setEditingDraftId(null);
      toast.success(updated.message || t('broadcast.toasts.draftSaved'));
    } catch (error) {
      toast.error(getErrorMessage(error, t('common.error')));
    } finally {
      setDraftBusy(false);
    }
  };

  const handleStartEdit = (draft: BroadcastDraft) => {
    setEditingDraftId(draft.id);
    setDraftEditorText(draft.draftText);
  };

  const handleCancelEdit = () => {
    setEditingDraftId(null);
    setDraftEditorText('');
  };

  const handleBatchConfirm = async () => {
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
    setDraftBusy(true);
    try {
      await dataSource.updateDraftStatuses(scope, targetDraftIds, 'ready');
      await refreshDrafts();
      toast.success(t('broadcast.toasts.draftsConfirmed'));
    } catch (error) {
      toast.error(getErrorMessage(error, t('common.error')));
    } finally {
      setDraftBusy(false);
    }
  };

  const handleUpdateSingleDraftStatus = async (
    draftId: number,
    status: 'ready' | 'pending_review',
    successMessage: string,
  ) => {
    setDraftBusy(true);
    try {
      await dataSource.updateDraftStatuses(scope, [draftId], status);
      await refreshDrafts();
      toast.success(successMessage);
    } catch (error) {
      toast.error(getErrorMessage(error, t('common.error')));
    } finally {
      setDraftBusy(false);
    }
  };

  const handleScopeChange = async (botUuid: string) => {
    const nextScope = scopeOptions.find((option) => option.botUuid === botUuid);
    if (!nextScope) {
      return;
    }

    setSelectedDraftIds([]);
    setEditingDraftId(null);
    setDraftEditorText('');
    setSelectedDraftId(null);
    setDraftImportBatchId(null);
    setSelectedImportId(null);
    setSelectedImportDetail(null);
    setLatestExecutionBatch(null);
    setExecutionLogs([]);

    setRulesLoading(true);
    setRulesError(null);
    try {
      await refreshRules(nextScope);
      await refreshImports(nextScope);
      await refreshDrafts(nextScope);
      await refreshExecutionState(nextScope);
      await refreshExecutorState(nextScope);
    } catch (error) {
      const message = getErrorMessage(error, t('common.error'));
      setRulesError(message);
      toast.error(message);
    } finally {
      setRulesLoading(false);
    }
  };

  return (
    <div className="flex min-h-full flex-col gap-4 pb-4">
      <BroadcastHeader
        snapshot={snapshot}
        scope={scope}
        scopeOptions={scopeOptions}
        loading={rulesLoading}
        onScopeChange={(botUuid) => void handleScopeChange(botUuid)}
      />

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
          <ImportMatchingPanel
            batches={importBatches}
            selectedBatchId={selectedImportId}
            detail={selectedImportDetail}
            templates={snapshot.templates}
            loading={rulesLoading}
            busy={importBusy}
            onUpload={async (file) => {
              setImportBusy(true);
              try {
                const detail = await dataSource.uploadImport(scope, file);
                await refreshImports();
                await refreshDrafts(scope, detail.id);
                setSelectedImportId(detail.id);
                setSelectedImportDetail(detail);
                toast.success(
                  t('broadcast.toasts.importUploaded', {
                    fileName: detail.originalFileName,
                  }),
                );
              } catch (error) {
                toast.error(getErrorMessage(error, t('common.error')));
              } finally {
                setImportBusy(false);
              }
            }}
            onSelectBatch={async (batchId) => {
              setSelectedImportId(batchId);
              try {
                const detail = await dataSource.getImportDetail(scope, batchId);
                setSelectedImportDetail(detail);
                await refreshDrafts(scope, batchId);
              } catch (error) {
                toast.error(getErrorMessage(error, t('common.error')));
              }
            }}
            onDeleteBatch={async (batchId) => {
              setImportBusy(true);
              try {
                await dataSource.deleteImport(scope, batchId);
                await refreshImports();
                await refreshDrafts();
                toast.success(t('broadcast.toasts.importDeleted'));
              } catch (error) {
                toast.error(getErrorMessage(error, t('common.error')));
              } finally {
                setImportBusy(false);
              }
            }}
            onRematch={async (batchId) => {
              setImportBusy(true);
              try {
                const detail = await dataSource.rematchImport(scope, batchId);
                await refreshImports();
                await refreshDrafts(scope, batchId);
                setSelectedImportDetail(detail);
                toast.success(t('broadcast.toasts.importRematched'));
              } catch (error) {
                toast.error(getErrorMessage(error, t('common.error')));
              } finally {
                setImportBusy(false);
              }
            }}
            onGenerateDrafts={async (batchId, templateId) => {
              setImportBusy(true);
              try {
                const result = await dataSource.generateImportDrafts(
                  scope,
                  batchId,
                  templateId,
                );
                await refreshImports();
                await refreshDrafts(scope, batchId);
                toast.success(
                  t('broadcast.toasts.draftsGenerated', {
                    count: result.totalGroupCount,
                  }),
                );
              } catch (error) {
                toast.error(getErrorMessage(error, t('common.error')));
              } finally {
                setImportBusy(false);
              }
            }}
          />
        </TabsContent>

        <TabsContent value="drafts" className="mt-0">
          <div className="grid gap-4 xl:grid-cols-[360px_minmax(0,1fr)]">
            <DraftQueue
              drafts={groupedDrafts}
              importBatches={importBatches}
              selectedImportId={draftImportBatchId}
              searchTerm={searchTerm}
              statusFilter={statusFilter}
              selectedDraftId={selectedDraftId}
              selectedDraftIds={selectedDraftIds}
              busy={draftBusy || sendBusy}
              onImportBatchChange={setDraftImportBatchId}
              onSearchTermChange={setSearchTerm}
              onStatusFilterChange={setStatusFilter}
              onSelectDraft={handleSelectDraft}
              onToggleDraftSelection={handleToggleDraftSelection}
              onBatchConfirm={() => void handleBatchConfirm()}
              onCreateExecutionBatch={() => void handleCreateExecutionBatch()}
            />
            <DraftDetail
              draft={activeDraft}
              editingDraftId={editingDraftId}
              draftEditorText={draftEditorText}
              busy={draftBusy}
              canRealSend={Boolean(executorCapability?.supports_send)}
              sendBusy={sendBusy}
              onStartEdit={handleStartEdit}
              onDraftEditorTextChange={setDraftEditorText}
              onSaveDraft={() => void handleSaveDraft()}
              onCancelEdit={handleCancelEdit}
              onConfirmDraft={() =>
                activeDraft &&
                void handleUpdateSingleDraftStatus(
                  activeDraft.id,
                  'ready',
                  t('broadcast.toasts.draftsConfirmed'),
                )
              }
              onRevokeDraft={() =>
                activeDraft &&
                void handleUpdateSingleDraftStatus(
                  activeDraft.id,
                  'pending_review',
                  t('broadcast.toasts.draftConfirmationRevoked'),
                )
              }
              onPasteDraft={() =>
                activeDraft && void handlePasteDraft(activeDraft)
              }
              onSendDraft={() =>
                activeDraft && void handleRealSendDraft(activeDraft)
              }
            />
          </div>
        </TabsContent>

        <TabsContent value="logs" className="mt-0">
          <ExecutionLogPanel
            logs={executionLogs}
            latestBatch={latestExecutionBatch}
            executorCapability={executorCapability}
            executorHealth={executorHealth}
            busy={draftBusy || sendBusy}
            onStartBatch={() => void handleBatchAction('start')}
            onPauseBatch={() => void handleBatchAction('pause')}
            onResumeBatch={() => void handleBatchAction('resume')}
            onCancelBatch={() => void handleBatchAction('cancel')}
            onRetryTask={(taskId) => void handleRetryExecutionTask(taskId)}
          />
        </TabsContent>
      </Tabs>
    </div>
  );
}
