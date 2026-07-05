import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { toast } from 'sonner';
import { useTranslation } from 'react-i18next';
import { Tabs, TabsContent } from '@/components/ui/tabs';
import { backendClient } from '@/app/infra/http';
import type {
  ApiBroadcastExecutionAttempt,
  ApiBroadcastExecutionEvidence,
  Bot,
} from '@/app/infra/entities/api';

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
import {
  BROADCAST_DIAGNOSTICS_VERSION,
  getBroadcastDiagnostics,
  markBroadcastRender,
} from '../diagnostics';
import { buildVariableMappings } from '../utils';
import type {
  BroadcastDraft,
  BroadcastExecutionBatchSummary,
  BroadcastExecutionLog,
  BroadcastExecutorCapability,
  BroadcastExecutorHealth,
  BroadcastImportBatch,
  BroadcastImportDetail,
  BroadcastImportGroupList,
  BroadcastImportGroupRowsPage,
  BroadcastRulesTab,
  BroadcastScope,
  BroadcastStatusFilter,
  BroadcastTopTab,
  BroadcastVariableMapping,
  BroadcastVariableProfile,
  BroadcastMessageTemplate,
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
    const details = (
      error as { data: { details?: unknown; message?: unknown } }
    ).data;
    if (typeof details.message === 'string' && details.message.trim()) {
      return details.message;
    }
    if (Array.isArray(details.details) && details.details.length > 0) {
      return String(details.details[0]);
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

function buildMappingsForImport(
  variableProfile: BroadcastVariableProfile,
  templates: BroadcastMessageTemplate[],
  detail: BroadcastImportDetail | null,
): BroadcastVariableMapping[] {
  return buildVariableMappings(variableProfile, templates, detail);
}

function createPlaceholderImportDetail(
  batch: BroadcastImportBatch,
  pageSize: number,
): BroadcastImportDetail {
  return {
    ...batch,
    rows: [],
    page: 1,
    pageSize,
    total: batch.totalRows,
    totalPages:
      batch.totalRows === 0 ? 0 : Math.ceil(batch.totalRows / pageSize),
  };
}

function hasWritableTargetConversation(draft: BroadcastDraft | null): boolean {
  return Boolean(draft?.conversationName.trim());
}

function canWriteDraftToInput(draft: BroadcastDraft | null): boolean {
  return Boolean(
    draft &&
    draft.status === 'ready' &&
    !draft.attachmentsStale &&
    !draft.draftsStale &&
    draft.draftText.trim() &&
    hasWritableTargetConversation(draft),
  );
}

export default function BroadcastWorkspace() {
  markBroadcastRender('BroadcastWorkspace');
  const diagnostics = getBroadcastDiagnostics();
  const { t } = useTranslation();
  const dataSource = useMemo(() => createBroadcastDataSource(), []);
  const initialSnapshot = useMemo(
    () => dataSource.loadSnapshot(),
    [dataSource],
  );
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
  const [draftImportBatchId, setDraftImportBatchId] = useState<number | null>(
    null,
  );
  const [selectedDraftId, setSelectedDraftId] = useState<number | null>(
    snapshot.drafts[0]?.id ?? null,
  );
  const [selectedDraftIds, setSelectedDraftIds] = useState<number[]>([]);
  const [editingDraftId, setEditingDraftId] = useState<number | null>(null);
  const [draftEditorText, setDraftEditorText] = useState('');
  const [rulesLoading, setRulesLoading] = useState(false);
  const [rulesSaving, setRulesSaving] = useState(false);
  const [rulesError, setRulesError] = useState<string | null>(null);
  const [importBatches, setImportBatches] = useState<BroadcastImportBatch[]>(
    [],
  );
  const [selectedImportId, setSelectedImportId] = useState<number | null>(null);
  const [selectedImportDetail, setSelectedImportDetail] =
    useState<BroadcastImportDetail | null>(null);
  const [selectedImportGroupsDetail, setSelectedImportGroupsDetail] =
    useState<BroadcastImportGroupList | null>(null);
  const [groupRowsByKey, setGroupRowsByKey] = useState<
    Record<string, BroadcastImportGroupRowsPage | undefined>
  >({});
  const [importError, setImportError] = useState<string | null>(null);
  const [importBusyCount, setImportBusyCount] = useState(0);
  const [draftBusy, setDraftBusy] = useState(false);
  const [sendBusy, setSendBusy] = useState(false);
  const [scopeOptions, setScopeOptions] = useState<
    Array<{ botUuid: string; botName: string; connectorId: string }>
  >([]);
  const [executionLogs, setExecutionLogs] = useState<BroadcastExecutionLog[]>(
    [],
  );
  const [latestExecutionBatch, setLatestExecutionBatch] =
    useState<BroadcastExecutionBatchSummary | null>(null);
  const [executorCapability, setExecutorCapability] =
    useState<BroadcastExecutorCapability | null>(null);
  const [executorHealth, setExecutorHealth] =
    useState<BroadcastExecutorHealth | null>(null);
  const [pasteRequestInFlight, setPasteRequestInFlight] = useState(false);
  const importPageSize = 50;
  const importRequestGenerationRef = useRef(0);
  const importDetailGenerationRef = useRef(0);
  const bootstrapRequestGenerationRef = useRef(0);
  const isMountedRef = useRef(true);
  const scopeRef = useRef(scope);
  const latestRulesRef = useRef({
    variableProfile: initialSnapshot.variableProfile,
    templates: initialSnapshot.templates,
  });
  const selectedImportIdRef = useRef<number | null>(null);
  const selectedImportDetailRef = useRef<BroadcastImportDetail | null>(null);
  const selectedImportGroupsDetailRef = useRef<BroadcastImportGroupList | null>(
    null,
  );
  const commonErrorMessageRef = useRef(t('common.error'));
  const executionBatchCacheRef = useRef(
    new Map<number, BroadcastExecutionBatchSummary>(),
  );
  const executionLogCacheRef = useRef(
    new Map<number, BroadcastExecutionLog[]>(),
  );
  const executionAttemptsCacheRef = useRef(
    new Map<number, ApiBroadcastExecutionAttempt[]>(),
  );
  const executionEvidenceCacheRef = useRef(
    new Map<number, ApiBroadcastExecutionEvidence | null>(),
  );
  const executionLogsHydratedRef = useRef(false);
  const importBusy = importBusyCount > 0;

  const runtimeReady = executorHealth?.status === 'ready';
  const pasteSupported = Boolean(executorCapability?.supports_paste);
  const pasteVerificationAvailable = runtimeReady && pasteSupported;
  const pasteVerificationMethod = 'unavailable' as const;
  const requiresManualConversationOpen = false;
  const pasteActionDisabledReason = useMemo(() => {
    if (!runtimeReady) {
      return t('common.loading');
    }
    if (!pasteSupported) {
      return t('broadcast.drafts.pasteUnavailable');
    }
    return null;
  }, [pasteSupported, runtimeReady, t]);

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
        draftImportBatchId == null
          ? true
          : draft.importBatchId === draftImportBatchId;
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
          (draft) => draft.id === draftId && canWriteDraftToInput(draft),
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
    if (
      snapshot.drafts.length > 0 &&
      !snapshot.drafts.some((draft) => draft.id === selectedDraftId)
    ) {
      setSelectedDraftId(snapshot.drafts[0].id);
    }
  }, [selectedDraftId, snapshot.drafts]);

  useEffect(() => {
    diagnostics?.recordSelectedImportIdChange(selectedImportId);
  }, [diagnostics, selectedImportId]);

  useEffect(() => {
    scopeRef.current = scope;
  }, [scope]);

  useEffect(() => {
    diagnostics?.recordImportBusyChange(importBusy);
  }, [diagnostics, importBusy]);

  useEffect(() => {
    latestRulesRef.current = {
      variableProfile: snapshot.variableProfile,
      templates: snapshot.templates,
    };
  }, [snapshot.templates, snapshot.variableProfile]);

  useEffect(() => {
    commonErrorMessageRef.current = t('common.error');
  }, [t]);

  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
      importRequestGenerationRef.current += 1;
      importDetailGenerationRef.current += 1;
      bootstrapRequestGenerationRef.current += 1;
    };
  }, []);

  const setSelectedImportIdState = useCallback((importId: number | null) => {
    selectedImportIdRef.current = importId;
    setSelectedImportId(importId);
  }, []);

  const applyImportDetail = useCallback(
    (
      detail: BroadcastImportDetail | null,
      variableProfile: BroadcastVariableProfile,
      templates: BroadcastMessageTemplate[],
    ) => {
      selectedImportDetailRef.current = detail;
      setSelectedImportDetail(detail);
      setSnapshot((current) => ({
        ...current,
        variableMappings: buildMappingsForImport(
          variableProfile,
          templates,
          detail,
        ),
      }));
    },
    [],
  );

  const applyImportGroupsDetail = useCallback(
    (detail: BroadcastImportGroupList | null) => {
      selectedImportGroupsDetailRef.current = detail;
      setSelectedImportGroupsDetail(detail);
    },
    [],
  );

  const beginImportBusy = useCallback(() => {
    setImportBusyCount((count) => count + 1);

    let released = false;
    return () => {
      if (released) {
        return;
      }
      released = true;
      setImportBusyCount((count) => Math.max(0, count - 1));
    };
  }, []);

  const resetExecutionCaches = useCallback(() => {
    executionBatchCacheRef.current.clear();
    executionLogCacheRef.current.clear();
    executionAttemptsCacheRef.current.clear();
    executionEvidenceCacheRef.current.clear();
    executionLogsHydratedRef.current = false;
  }, []);

  const syncExecutionLogsFromCache = useCallback(() => {
    const nextLogs = Array.from(executionLogCacheRef.current.entries())
      .sort((left, right) => right[0] - left[0])
      .flatMap(([, logs]) => logs)
      .sort((left, right) => right.timestamp.localeCompare(left.timestamp));
    setExecutionLogs(nextLogs);
  }, []);

  const loadImportDetailPage = async (
    nextScope: BroadcastScope,
    importId: number,
    page: number,
    options?: {
      requestGeneration?: number;
      detailGeneration?: number;
      variableProfile?: BroadcastVariableProfile;
      templates?: BroadcastMessageTemplate[];
    },
  ) => {
    const detailGeneration =
      options?.detailGeneration ?? ++importDetailGenerationRef.current;
    const detail = await dataSource.getImportDetail(nextScope, importId, {
      page,
      pageSize: importPageSize,
    });
    if (
      !isMountedRef.current ||
      detailGeneration !== importDetailGenerationRef.current ||
      (options?.requestGeneration != null &&
        options.requestGeneration !== importRequestGenerationRef.current)
    ) {
      return null;
    }
    applyImportDetail(
      detail,
      options?.variableProfile ?? latestRulesRef.current.variableProfile,
      options?.templates ?? latestRulesRef.current.templates,
    );
    setImportError(null);
    return detail;
  };

  const loadImportGroupsPage = async (
    nextScope: BroadcastScope,
    importId: number,
    page: number,
    options?: {
      requestGeneration?: number;
    },
  ) => {
    const detail = await dataSource.getImportGroups(nextScope, importId, {
      page,
      pageSize: importPageSize,
    });
    if (
      !isMountedRef.current ||
      (options?.requestGeneration != null &&
        options.requestGeneration !== importRequestGenerationRef.current)
    ) {
      return null;
    }
    const existingAttachments =
      selectedImportGroupsDetailRef.current?.groups.reduce<
        Record<
          string,
          BroadcastImportGroupList['groups'][number]['attachments']
        >
      >((acc, group) => {
        acc[group.groupKey] = group.attachments;
        return acc;
      }, {}) ?? {};
    applyImportGroupsDetail({
      ...detail,
      groups: detail.groups.map((group) => ({
        ...group,
        attachments: existingAttachments[group.groupKey] ?? group.attachments,
      })),
    });
    return detail;
  };

  const isImportRequestGenerationCurrent = (generation: number) =>
    isMountedRef.current && generation === importRequestGenerationRef.current;

  const refreshExecutorState = useCallback(
    async (nextScope?: BroadcastScope) => {
      const resolvedScope = nextScope ?? scopeRef.current;
      try {
        const [capability, health] = await Promise.all([
          dataSource.getExecutorCapabilities(resolvedScope),
          dataSource.getExecutorHealth(resolvedScope),
        ]);
        setExecutorCapability(capability);
        setExecutorHealth(health);
      } catch {
        setExecutorCapability(null);
        setExecutorHealth(null);
      }
    },
    [dataSource],
  );

  const refreshRules = async (nextScope: BroadcastScope = scope) => {
    const rulesData = await dataSource.loadRulesData(nextScope);
    setScope(nextScope);
    setSnapshot((current) =>
      applyRulesDataToSnapshot(
        current,
        rulesData,
        selectedImportDetailRef.current,
      ),
    );
  };

  const refreshImports = async (
    nextScope: BroadcastScope = scope,
    options?: {
      preferredImportId?: number | null;
      requestGeneration?: number;
      detailGeneration?: number;
      variableProfile?: BroadcastVariableProfile;
      templates?: BroadcastMessageTemplate[];
    },
  ) => {
    const requestGeneration =
      options?.requestGeneration ?? ++importRequestGenerationRef.current;
    const execute = async () => {
      const batches = await dataSource.listImportBatches(nextScope);
      if (!isImportRequestGenerationCurrent(requestGeneration)) {
        return;
      }
      setImportBatches(batches);

      const nextImportId =
        options?.preferredImportId != null &&
        batches.some((item) => item.id === options.preferredImportId)
          ? options.preferredImportId
          : selectedImportIdRef.current &&
              batches.some((item) => item.id === selectedImportIdRef.current)
            ? selectedImportIdRef.current
            : (batches[0]?.id ?? null);
      setSelectedImportIdState(nextImportId);
      if (!isImportRequestGenerationCurrent(requestGeneration)) {
        return;
      }

      if (nextImportId) {
        setGroupRowsByKey({});
        await loadImportDetailPage(nextScope, nextImportId, 1, {
          requestGeneration,
          detailGeneration: options?.detailGeneration,
          variableProfile: options?.variableProfile,
          templates: options?.templates,
        });
        await loadImportGroupsPage(nextScope, nextImportId, 1, {
          requestGeneration,
        });
      } else {
        clearImportState(
          options?.variableProfile ?? latestRulesRef.current.variableProfile,
          options?.templates ?? latestRulesRef.current.templates,
        );
        setImportError(null);
      }
    };

    if (!diagnostics) {
      await execute();
      return;
    }

    await diagnostics.measure('refreshImports', execute, {
      timingBucket: 'refreshImports',
      stack: new Error().stack,
      meta: {
        preferredImportId: options?.preferredImportId,
        selectedImportId,
        botUuid: nextScope.botUuid,
        connectorId: nextScope.connectorId,
      },
    });
  };

  const refreshDrafts = async (
    nextScope: BroadcastScope = scope,
    focusImportBatchId?: number | null,
  ) => {
    const execute = async () => {
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
          drafts.find((draft) => draft.importBatchId === focusImportBatchId)
            ?.id ??
            drafts[0]?.id ??
            null,
        );
        return;
      }

      setSelectedDraftId((current) =>
        drafts.some((draft) => draft.id === current)
          ? current
          : (drafts[0]?.id ?? null),
      );
    };

    if (!diagnostics) {
      await execute();
      return;
    }

    await diagnostics.measure('refreshDrafts', execute, {
      timingBucket: 'refreshDrafts',
      stack: new Error().stack,
      meta: {
        focusImportBatchId,
        statusFilter,
        searchTerm,
        botUuid: nextScope.botUuid,
        connectorId: nextScope.connectorId,
      },
    });
  };

  const clearImportState = useCallback(
    (
      variableProfile: BroadcastVariableProfile,
      templates: BroadcastMessageTemplate[],
    ) => {
      setImportBatches([]);
      setSelectedImportIdState(null);
      applyImportDetail(null, variableProfile, templates);
      applyImportGroupsDetail(null);
      setGroupRowsByKey({});
      setImportError(null);
    },
    [applyImportDetail, applyImportGroupsDetail, setSelectedImportIdState],
  );

  const updateGroupAttachments = useCallback(
    (groupKey: string, attachments: BroadcastDraft['attachments']) => {
      applyImportGroupsDetail(
        selectedImportGroupsDetailRef.current
          ? {
              ...selectedImportGroupsDetailRef.current,
              groups: selectedImportGroupsDetailRef.current.groups.map(
                (group) =>
                  group.groupKey === groupKey
                    ? {
                        ...group,
                        attachments,
                        attachmentCount: attachments?.length ?? 0,
                      }
                    : group,
              ),
            }
          : null,
      );
    },
    [applyImportGroupsDetail],
  );

  const loadImportGroupRows = useCallback(
    async (groupKey: string, page = 1) => {
      if (!selectedImportIdRef.current) {
        return;
      }
      const rows = await dataSource.getImportGroupRows(
        scopeRef.current,
        selectedImportIdRef.current,
        groupKey,
        {
          page,
          pageSize: importPageSize,
        },
      );
      setGroupRowsByKey((current) => ({
        ...current,
        [groupKey]: rows,
      }));
    },
    [dataSource, importPageSize],
  );

  const refreshExecutionState = useCallback(
    async (
      nextScope: BroadcastScope = scope,
      options?: {
        refreshAllLogs?: boolean;
        refreshLatestLogsOnly?: boolean;
      },
    ) => {
      const drafts = await dataSource.listDrafts(nextScope, {
        status: statusFilter === 'all' ? 'all' : statusFilter,
        keyword: searchTerm || undefined,
      });
      setSnapshot((current) => ({
        ...current,
        drafts,
      }));

      const batchSummaries = await dataSource.listExecutionBatches(nextScope);
      const sortedBatchSummaries = [...batchSummaries].sort(
        (left, right) => right.id - left.id,
      );
      const availableBatchIds = new Set(
        sortedBatchSummaries.map((batch) => batch.id),
      );

      for (const batchId of Array.from(executionBatchCacheRef.current.keys())) {
        if (!availableBatchIds.has(batchId)) {
          executionBatchCacheRef.current.delete(batchId);
          executionLogCacheRef.current.delete(batchId);
        }
      }

      const latestBatchSummary = sortedBatchSummaries[0] ?? null;
      let latestBatchDetail: BroadcastExecutionBatchSummary | null = null;

      if (latestBatchSummary) {
        const cachedBatch = executionBatchCacheRef.current.get(
          latestBatchSummary.id,
        );
        const latestBatchSummaryDrifted =
          cachedBatch != null &&
          (cachedBatch.status !== latestBatchSummary.status ||
            cachedBatch.pendingTasks !== latestBatchSummary.pendingTasks ||
            cachedBatch.runningTasks !== latestBatchSummary.runningTasks ||
            cachedBatch.succeededTasks !== latestBatchSummary.succeededTasks ||
            cachedBatch.failedTasks !== latestBatchSummary.failedTasks ||
            cachedBatch.cancelledTasks !== latestBatchSummary.cancelledTasks ||
            cachedBatch.interruptedTasks !==
              latestBatchSummary.interruptedTasks);
        const shouldRefreshLatestBatch =
          options?.refreshLatestLogsOnly ||
          options?.refreshAllLogs ||
          !cachedBatch ||
          latestBatchSummaryDrifted ||
          !EXECUTION_TERMINAL_STATUSES.has(cachedBatch.status);

        latestBatchDetail = shouldRefreshLatestBatch
          ? await dataSource.getExecutionBatchDetail(
              nextScope,
              latestBatchSummary.id,
            )
          : cachedBatch;
        executionBatchCacheRef.current.set(
          latestBatchSummary.id,
          latestBatchDetail,
        );
      }

      setLatestExecutionBatch(latestBatchDetail);

      if (topTab === 'logs') {
        try {
          const shouldRefreshAllLogs =
            options?.refreshAllLogs || !executionLogsHydratedRef.current;
          const targetBatchIds = shouldRefreshAllLogs
            ? sortedBatchSummaries.map((batch) => batch.id)
            : latestBatchDetail
              ? [latestBatchDetail.id]
              : [];

          for (const batchId of targetBatchIds) {
            let batchDetail =
              batchId === latestBatchDetail?.id
                ? latestBatchDetail
                : (executionBatchCacheRef.current.get(batchId) ?? null);

            if (!batchDetail) {
              batchDetail = await dataSource.getExecutionBatchDetail(
                nextScope,
                batchId,
              );
              executionBatchCacheRef.current.set(batchId, batchDetail);
            }

            const forceRefresh =
              batchId === latestBatchDetail?.id &&
              !EXECUTION_TERMINAL_STATUSES.has(batchDetail.status);
            const logs = await dataSource.getExecutionLogsForBatch(
              nextScope,
              batchDetail,
              drafts,
              {
                attemptsCache: executionAttemptsCacheRef.current,
                evidenceCache: executionEvidenceCacheRef.current,
                forceRefresh,
              },
            );
            executionLogCacheRef.current.set(batchId, logs);
          }

          executionLogsHydratedRef.current = targetBatchIds.length > 0;
          syncExecutionLogsFromCache();
        } catch {
          setExecutionLogs([]);
        }
      }
    },
    [
      dataSource,
      scope,
      searchTerm,
      statusFilter,
      syncExecutionLogsFromCache,
      topTab,
    ],
  );

  useEffect(() => {
    let cancelled = false;

    const loadRules = async (resolvedScope: BroadcastScope) => {
      const generation = ++bootstrapRequestGenerationRef.current;
      const importGenerationAtStart = importRequestGenerationRef.current;
      setRulesLoading(true);
      setRulesError(null);

      try {
        const rulesData = await dataSource.loadRulesData(resolvedScope);
        if (cancelled || generation !== bootstrapRequestGenerationRef.current) {
          return;
        }
        setScope(resolvedScope);
        const batches = await dataSource.listImportBatches(resolvedScope);
        if (cancelled || generation !== bootstrapRequestGenerationRef.current) {
          return;
        }
        if (importGenerationAtStart !== importRequestGenerationRef.current) {
          setSnapshot((current) =>
            applyRulesDataToSnapshot(
              current,
              rulesData,
              selectedImportDetailRef.current,
            ),
          );
          return;
        }

        setImportBatches(batches);
        const nextImportId = batches[0]?.id ?? null;
        setSelectedImportIdState(nextImportId);
        if (nextImportId) {
          const detailGeneration = ++importDetailGenerationRef.current;
          const detail = await dataSource.getImportDetail(
            resolvedScope,
            nextImportId,
            {
              page: 1,
              pageSize: importPageSize,
            },
          );
          if (
            cancelled ||
            generation !== bootstrapRequestGenerationRef.current ||
            importGenerationAtStart !== importRequestGenerationRef.current ||
            detailGeneration !== importDetailGenerationRef.current
          ) {
            return;
          }
          const drafts = await dataSource.listDrafts(resolvedScope);
          if (
            !cancelled &&
            generation === bootstrapRequestGenerationRef.current &&
            importGenerationAtStart === importRequestGenerationRef.current
          ) {
            setDraftImportBatchId(nextImportId);
            setSnapshot((current) =>
              applyRulesDataToSnapshot(
                {
                  ...current,
                  drafts,
                },
                rulesData,
                detail,
              ),
            );
            applyImportDetail(
              detail,
              rulesData.variableProfile,
              rulesData.templates,
            );
          }
        } else {
          clearImportState(rulesData.variableProfile, rulesData.templates);
          setDraftImportBatchId(null);
          setSnapshot((current) =>
            applyRulesDataToSnapshot(
              {
                ...current,
                drafts: [],
              },
              rulesData,
              null,
            ),
          );
        }

        if (!cancelled) {
          await refreshExecutorState(resolvedScope);
        }
      } catch (error) {
        if (cancelled) {
          return;
        }
        setRulesError(getErrorMessage(error, commonErrorMessageRef.current));
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
          .filter(
            (option): option is NonNullable<typeof option> => option != null,
          );

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
  }, [
    applyImportDetail,
    clearImportState,
    dataSource,
    importPageSize,
    initialSnapshot.scope,
    refreshExecutorState,
    setSelectedImportIdState,
  ]);

  useEffect(() => {
    if (topTab !== 'logs') {
      return;
    }
    void refreshExecutionState(scope, {
      refreshAllLogs: !executionLogsHydratedRef.current,
    });
  }, [refreshExecutionState, scope, topTab]);

  useEffect(() => {
    if (
      topTab !== 'logs' ||
      !latestExecutionBatch ||
      EXECUTION_TERMINAL_STATUSES.has(latestExecutionBatch.status)
    ) {
      return;
    }

    const timer = window.setInterval(() => {
      void refreshExecutionState(scope, {
        refreshLatestLogsOnly: true,
      });
    }, 2000);

    return () => {
      window.clearInterval(timer);
    };
  }, [latestExecutionBatch, refreshExecutionState, scope, topTab]);

  const handleCreateExecutionBatch = async () => {
    if (!pasteVerificationAvailable) {
      toast.error(
        pasteActionDisabledReason ?? t('broadcast.drafts.pasteUnavailable'),
      );
      return;
    }
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

  const handleBatchAction = async (
    action: 'start' | 'pause' | 'resume' | 'cancel',
  ) => {
    if (!latestExecutionBatch) {
      return;
    }
    if (
      ['start', 'resume'].includes(action) &&
      latestExecutionBatch.mode === 'paste_only' &&
      !pasteVerificationAvailable
    ) {
      toast.error(
        pasteActionDisabledReason ?? t('broadcast.drafts.pasteUnavailable'),
      );
      return;
    }
    setDraftBusy(true);
    try {
      const batch =
        action === 'start'
          ? await dataSource.startExecutionBatch(
              scope,
              latestExecutionBatch.id,
              OPERATOR_EMAIL,
            )
          : action === 'pause'
            ? await dataSource.pauseExecutionBatch(
                scope,
                latestExecutionBatch.id,
                OPERATOR_EMAIL,
              )
            : action === 'resume'
              ? await dataSource.resumeExecutionBatch(
                  scope,
                  latestExecutionBatch.id,
                  OPERATOR_EMAIL,
                )
              : await dataSource.cancelExecutionBatch(
                  scope,
                  latestExecutionBatch.id,
                  OPERATOR_EMAIL,
                );
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
    if (!pasteVerificationAvailable) {
      toast.error(
        pasteActionDisabledReason ?? t('broadcast.drafts.pasteUnavailable'),
      );
      return;
    }
    if (!canWriteDraftToInput(draft)) {
      toast.error(t('broadcast.drafts.pasteMissingConversation'));
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
      await dataSource.sendExecutionTask(
        scope,
        taskId,
        confirmation.token,
        OPERATOR_EMAIL,
      );
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
    clearImportState(snapshot.variableProfile, snapshot.templates);
    setLatestExecutionBatch(null);
    setExecutionLogs([]);
    resetExecutionCaches();
    importRequestGenerationRef.current += 1;
    importDetailGenerationRef.current += 1;

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
    <div
      className="flex h-full min-h-0 flex-col gap-4 overflow-y-auto overflow-x-hidden overscroll-contain pb-4"
      data-testid="broadcast-workspace-scroll"
      data-broadcast-diagnostics={
        import.meta.env.DEV ? BROADCAST_DIAGNOSTICS_VERSION : undefined
      }
      data-broadcast-import-busy-count={
        import.meta.env.DEV ? String(importBusyCount) : undefined
      }
    >
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
        className="flex min-h-0 flex-col gap-4"
      >
        <BroadcastTabs options={topTabOptions} />

        <TabsContent value="rules" className="mt-0 min-h-0">
          <Tabs
            value={rulesTab}
            onValueChange={(value) => setRulesTab(value as BroadcastRulesTab)}
            className="flex min-h-0 flex-col gap-4"
          >
            <BroadcastTabs options={rulesTabOptions} size="compact" />
            <TabsContent value="variables" className="mt-0 min-h-0">
              <VariableMappingPanel
                variableProfile={snapshot.variableProfile}
                templates={snapshot.templates}
                importDetail={selectedImportDetail}
                loading={rulesLoading}
                saving={rulesSaving}
                error={rulesError}
                onSave={(profile) =>
                  runRulesMutation(async () => {
                    await dataSource.saveVariableProfile(scope, profile);
                  }, t('broadcast.toasts.rulesSaved'))
                }
              />
            </TabsContent>
            <TabsContent value="templates" className="mt-0 min-h-0">
              <TemplatePanel
                templates={snapshot.templates}
                mappings={snapshot.variableMappings}
                loading={rulesLoading}
                saving={rulesSaving}
                error={rulesError}
                onCreate={(draft) =>
                  runRulesMutation(async () => {
                    await dataSource.createTemplate(scope, draft);
                  }, t('broadcast.toasts.templateSaved'))
                }
                onUpdate={(templateId, draft) =>
                  runRulesMutation(async () => {
                    await dataSource.updateTemplate(scope, templateId, draft);
                  }, t('broadcast.toasts.templateSaved'))
                }
                onDelete={(templateId) =>
                  runRulesMutation(async () => {
                    await dataSource.deleteTemplate(scope, templateId);
                  }, t('broadcast.toasts.templateDeleted'))
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
            <TabsContent value="groups" className="mt-0 min-h-0">
              <GroupMatchingPanel
                scope={scope}
                rules={snapshot.groupRules}
                groupNames={snapshot.groupNames}
                loading={rulesLoading}
                saving={rulesSaving}
                error={rulesError}
                onCreateRule={(draft) =>
                  runRulesMutation(async () => {
                    await dataSource.createGroupRule(scope, draft);
                  }, t('broadcast.toasts.groupRuleSaved'))
                }
                onUpdateRule={(ruleId, draft) =>
                  runRulesMutation(async () => {
                    await dataSource.updateGroupRule(scope, ruleId, draft);
                  }, t('broadcast.toasts.groupRuleSaved'))
                }
                onDeleteRule={(ruleId) =>
                  runRulesMutation(async () => {
                    await dataSource.deleteGroupRule(scope, ruleId);
                  }, t('broadcast.toasts.groupRuleDeleted'))
                }
                onMatchRule={(sourceValue) =>
                  dataSource.matchGroupRule(scope, sourceValue)
                }
                onCreateGroupNames={(names) =>
                  runRulesMutation(async () => {
                    await dataSource.createGroupNames(scope, names);
                  }, t('broadcast.toasts.groupNamesSaved'))
                }
                onSyncGroupNames={() =>
                  runRulesMutation(async () => {
                    const result = await dataSource.syncGroupNames(scope);
                    toast.success(
                      t('broadcast.toasts.groupNamesSynced', {
                        scanned: result.scanned,
                        inserted: result.inserted,
                        updated: result.updated,
                        unchanged: result.unchanged,
                      }),
                    );
                  }, t('broadcast.toasts.groupNamesSaved'))
                }
                onDeleteGroupName={(groupNameId) =>
                  runRulesMutation(async () => {
                    await dataSource.deleteGroupName(scope, groupNameId);
                  }, t('broadcast.toasts.groupNameDeleted'))
                }
              />
            </TabsContent>
          </Tabs>
        </TabsContent>

        <TabsContent value="import" className="mt-0 min-h-0">
          <ImportMatchingPanel
            batches={importBatches}
            selectedBatchId={selectedImportId}
            detail={selectedImportDetail}
            groupsDetail={selectedImportGroupsDetail}
            groupRowsByKey={groupRowsByKey}
            templates={snapshot.templates}
            loading={rulesLoading}
            busy={importBusy}
            error={importError}
            onUpload={async (file) => {
              const requestGeneration = ++importRequestGenerationRef.current;
              const detailGeneration = ++importDetailGenerationRef.current;
              const releaseImportBusy = beginImportBusy();
              setImportError(null);
              try {
                const batch = await dataSource.uploadImport(scope, file);
                if (
                  !isMountedRef.current ||
                  requestGeneration !== importRequestGenerationRef.current
                ) {
                  return;
                }
                setImportBatches((current) => {
                  return [
                    batch,
                    ...current.filter((item) => item.id !== batch.id),
                  ];
                });
                setSelectedImportIdState(batch.id);
                applyImportDetail(
                  createPlaceholderImportDetail(batch, importPageSize),
                  latestRulesRef.current.variableProfile,
                  latestRulesRef.current.templates,
                );
                applyImportGroupsDetail(null);
                setGroupRowsByKey({});
                await loadImportDetailPage(scope, batch.id, 1, {
                  requestGeneration,
                  detailGeneration,
                  variableProfile: latestRulesRef.current.variableProfile,
                  templates: latestRulesRef.current.templates,
                });
                await loadImportGroupsPage(scope, batch.id, 1, {
                  requestGeneration,
                });
                if (
                  !isMountedRef.current ||
                  requestGeneration !== importRequestGenerationRef.current
                ) {
                  return;
                }
                toast.success(
                  t('broadcast.toasts.importUploaded', {
                    fileName: batch.originalFileName,
                  }),
                );
              } catch (error) {
                const message = getErrorMessage(error, t('common.error'));
                setImportError(message);
                toast.error(message);
              } finally {
                releaseImportBusy();
              }
            }}
            onSelectBatch={async (batchId) => {
              const requestGeneration = ++importRequestGenerationRef.current;
              const detailGeneration = ++importDetailGenerationRef.current;
              const releaseImportBusy = beginImportBusy();
              setSelectedImportIdState(batchId);
              setImportError(null);
              try {
                setGroupRowsByKey({});
                await loadImportDetailPage(scope, batchId, 1, {
                  requestGeneration,
                  detailGeneration,
                });
                await loadImportGroupsPage(scope, batchId, 1, {
                  requestGeneration,
                });
                await refreshDrafts(scope, batchId);
              } catch (error) {
                const message = getErrorMessage(error, t('common.error'));
                setImportError(message);
                toast.error(message);
              } finally {
                releaseImportBusy();
              }
            }}
            onPageChange={async (page) => {
              if (!selectedImportIdRef.current) {
                return;
              }
              ++importDetailGenerationRef.current;
              const releaseImportBusy = beginImportBusy();
              setImportError(null);
              try {
                await loadImportGroupsPage(
                  scope,
                  selectedImportIdRef.current,
                  page,
                  { requestGeneration: importRequestGenerationRef.current },
                );
              } catch (error) {
                const message = getErrorMessage(error, t('common.error'));
                setImportError(message);
                toast.error(message);
              } finally {
                releaseImportBusy();
              }
            }}
            onDeleteBatch={async (batchId) => {
              const requestGeneration = ++importRequestGenerationRef.current;
              importDetailGenerationRef.current += 1;
              const releaseImportBusy = beginImportBusy();
              setImportError(null);
              try {
                await dataSource.deleteImport(scope, batchId);

                const remainingBatches = importBatches.filter(
                  (batch) => batch.id !== batchId,
                );
                const nextImportId =
                  selectedImportIdRef.current === batchId
                    ? (remainingBatches[0]?.id ?? null)
                    : selectedImportIdRef.current;

                if (remainingBatches.length === 0) {
                  clearImportState(
                    latestRulesRef.current.variableProfile,
                    latestRulesRef.current.templates,
                  );
                  setDraftImportBatchId(null);
                } else {
                  setImportBatches(remainingBatches);
                  if (selectedImportIdRef.current === batchId) {
                    setSelectedImportIdState(nextImportId);
                    const nextBatch =
                      remainingBatches.find(
                        (batch) => batch.id === nextImportId,
                      ) ?? null;
                    applyImportDetail(
                      nextBatch
                        ? createPlaceholderImportDetail(
                            nextBatch,
                            importPageSize,
                          )
                        : null,
                      latestRulesRef.current.variableProfile,
                      latestRulesRef.current.templates,
                    );
                    applyImportGroupsDetail(null);
                    setGroupRowsByKey({});
                  }
                }

                await refreshImports(scope, {
                  preferredImportId: nextImportId,
                  requestGeneration,
                  variableProfile: latestRulesRef.current.variableProfile,
                  templates: latestRulesRef.current.templates,
                });
                await refreshDrafts(scope, nextImportId);
                toast.success(t('broadcast.toasts.importDeleted'));
              } catch (error) {
                const message = getErrorMessage(error, t('common.error'));
                setImportError(message);
                toast.error(message);
              } finally {
                releaseImportBusy();
              }
            }}
            onRematch={async (batchId) => {
              const requestGeneration = ++importRequestGenerationRef.current;
              const releaseImportBusy = beginImportBusy();
              setImportError(null);
              try {
                const detail = await dataSource.rematchImport(scope, batchId);
                await refreshImports(scope, {
                  preferredImportId: batchId,
                  requestGeneration,
                  variableProfile: latestRulesRef.current.variableProfile,
                  templates: latestRulesRef.current.templates,
                });
                await refreshDrafts(scope, batchId);
                applyImportDetail(
                  detail,
                  latestRulesRef.current.variableProfile,
                  latestRulesRef.current.templates,
                );
                await loadImportGroupsPage(scope, batchId, 1, {
                  requestGeneration,
                });
                setGroupRowsByKey({});
                toast.success(t('broadcast.toasts.importRematched'));
              } catch (error) {
                const message = getErrorMessage(error, t('common.error'));
                setImportError(message);
                toast.error(message);
              } finally {
                releaseImportBusy();
              }
            }}
            onGenerateDrafts={async (batchId, templateId) => {
              const requestGeneration = ++importRequestGenerationRef.current;
              const releaseImportBusy = beginImportBusy();
              setImportError(null);
              try {
                const result = await dataSource.generateImportDrafts(
                  scope,
                  batchId,
                  templateId,
                );
                await refreshImports(scope, {
                  preferredImportId: batchId,
                  requestGeneration,
                  variableProfile: latestRulesRef.current.variableProfile,
                  templates: latestRulesRef.current.templates,
                });
                await refreshDrafts(scope, batchId);
                toast.success(
                  t('broadcast.toasts.draftsGenerated', {
                    count: result.totalGroupCount,
                  }),
                );
              } catch (error) {
                const message = getErrorMessage(error, t('common.error'));
                setImportError(message);
                toast.error(message);
              } finally {
                releaseImportBusy();
              }
            }}
            onLoadGroupRows={(groupKey, page) =>
              loadImportGroupRows(groupKey, page)
            }
            onUploadGroupAttachments={async (groupKey, files) => {
              if (!selectedImportIdRef.current) {
                return;
              }
              const attachments = await dataSource.uploadImportGroupAttachments(
                scope,
                selectedImportIdRef.current,
                groupKey,
                files,
              );
              updateGroupAttachments(groupKey, attachments);
              await refreshDrafts(scope, draftImportBatchId);
              toast.success(t('broadcast.toasts.attachmentUploaded'));
            }}
            onDeleteGroupAttachment={async (groupKey, attachmentId) => {
              if (!selectedImportIdRef.current) {
                return;
              }
              const attachments = await dataSource.deleteImportGroupAttachment(
                scope,
                selectedImportIdRef.current,
                groupKey,
                attachmentId,
              );
              updateGroupAttachments(groupKey, attachments);
              await refreshDrafts(scope, draftImportBatchId);
              toast.success(t('broadcast.toasts.attachmentDeleted'));
            }}
          />
        </TabsContent>

        <TabsContent value="drafts" className="mt-0 min-h-0">
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
              canCreateExecutionBatch={pasteVerificationAvailable}
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
              canPasteDraft={
                pasteVerificationAvailable && canWriteDraftToInput(activeDraft)
              }
              pasteDisabledReason={pasteActionDisabledReason}
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
              onUploadAttachments={(files) => {
                if (!activeDraft) {
                  return;
                }
                void (async () => {
                  try {
                    setDraftBusy(true);
                    const updated = await dataSource.uploadDraftAttachments(
                      scope,
                      activeDraft.id,
                      files,
                    );
                    setSnapshot((current) => ({
                      ...current,
                      drafts: current.drafts.map((draft) =>
                        draft.id === updated.id ? updated : draft,
                      ),
                    }));
                    setSelectedDraftId(updated.id);
                    setDraftEditorText(updated.draftText);
                    toast.success(t('broadcast.toasts.attachmentUploaded'));
                  } catch (error) {
                    toast.error(getErrorMessage(error, t('common.error')));
                  } finally {
                    setDraftBusy(false);
                  }
                })();
              }}
              onDeleteAttachment={(attachmentId) => {
                if (!activeDraft) {
                  return;
                }
                void (async () => {
                  try {
                    setDraftBusy(true);
                    const updated = await dataSource.deleteDraftAttachment(
                      scope,
                      activeDraft.id,
                      attachmentId,
                    );
                    setSnapshot((current) => ({
                      ...current,
                      drafts: current.drafts.map((draft) =>
                        draft.id === updated.id ? updated : draft,
                      ),
                    }));
                    setSelectedDraftId(updated.id);
                    setDraftEditorText(updated.draftText);
                    toast.success(t('broadcast.toasts.attachmentDeleted'));
                  } catch (error) {
                    toast.error(getErrorMessage(error, t('common.error')));
                  } finally {
                    setDraftBusy(false);
                  }
                })();
              }}
            />
          </div>
        </TabsContent>

        <TabsContent value="logs" className="mt-0 min-h-0">
          <ExecutionLogPanel
            logs={executionLogs}
            latestBatch={latestExecutionBatch}
            executorCapability={executorCapability}
            executorHealth={executorHealth}
            pasteVerificationAvailable={pasteVerificationAvailable}
            pasteVerificationMethod={pasteVerificationMethod}
            requiresManualConversationOpen={requiresManualConversationOpen}
            pasteActionDisabledReason={pasteActionDisabledReason}
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
