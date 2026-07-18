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
  BroadcastGroupRuleCandidateList,
  BroadcastExecutionBatchSummary,
  BroadcastExecutionLog,
  BroadcastExecutorCapability,
  BroadcastExecutorHealth,
  BroadcastImportBatch,
  BroadcastImportDetail,
  BroadcastImportGroupFieldConfirmationDetails,
  BroadcastImportGroupList,
  BroadcastImportGroupRowsPage,
  BroadcastRulesData,
  BroadcastRulesTab,
  BroadcastScope,
  BroadcastStatusFilter,
  BroadcastTopTab,
  BroadcastVariableMapping,
  BroadcastVariableProfile,
  BroadcastMessageTemplate,
} from '../types';
import { getRetryableExecutionTasks } from '../statusPresentation';

const draftStatusOrder = ['pending', 'unknown', 'sent'] as const;
const OPERATOR_EMAIL = 'tester@example.com';
const EXECUTION_TERMINAL_STATUSES = new Set([
  'completed',
  'partially_failed',
  'failed',
  'cancelled',
  'interrupted',
]);

type BackendErrorPayload = {
  msg?: unknown;
  data?: {
    message?: unknown;
    details?: unknown;
  };
};

type PendingImportConfirmation = {
  file: File;
  details: BroadcastImportGroupFieldConfirmationDetails;
};

function getBackendErrorPayload(error: unknown): BackendErrorPayload | null {
  if (!error || typeof error !== 'object') {
    return null;
  }
  return error as BackendErrorPayload;
}

function isBackendErrorCode(error: unknown, code: string): boolean {
  const payload = getBackendErrorPayload(error);
  return typeof payload?.msg === 'string' && payload.msg === code;
}

function readImportGroupFieldConfirmationDetails(
  error: unknown,
): BroadcastImportGroupFieldConfirmationDetails | null {
  const payload = getBackendErrorPayload(error);
  const details = payload?.data?.details;
  if (!details || typeof details !== 'object' || Array.isArray(details)) {
    return null;
  }
  const record = details as Record<string, unknown>;
  if (
    !Array.isArray(record.headers) ||
    !Array.isArray(record.candidates) ||
    typeof record.original_file_name !== 'string'
  ) {
    return null;
  }
  return {
    headers: record.headers
      .filter((item): item is string => typeof item === 'string')
      .map((item) => item.trim()),
    candidates: record.candidates
      .filter((item): item is string => typeof item === 'string')
      .map((item) => item.trim()),
    configuredGroupField:
      typeof record.configured_group_field === 'string'
        ? record.configured_group_field
        : null,
    originalFileName: record.original_file_name,
  };
}

function getErrorMessage(error: unknown, fallback: string): string {
  const payload = getBackendErrorPayload(error);
  if (payload?.data && typeof payload.data === 'object') {
    const details = payload.data;
    if (typeof details.message === 'string' && details.message.trim()) {
      return details.message;
    }
    if (Array.isArray(details.details) && details.details.length > 0) {
      return String(details.details[0]);
    }
  }
  if (typeof payload?.msg === 'string') {
    return payload.msg;
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

function isSameScope(left: BroadcastScope, right: BroadcastScope): boolean {
  return (
    left.botUuid === right.botUuid && left.connectorId === right.connectorId
  );
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
    ['pending', 'unknown', 'sent'].includes(draft.status) &&
    !draft.attachmentsStale &&
    !draft.draftsStale &&
    draft.draftText.trim() &&
    hasWritableTargetConversation(draft),
  );
}

function canSendDraftForReal(draft: BroadcastDraft | null): boolean {
  return Boolean(
    draft && draft.status === 'pending' && canWriteDraftToInput(draft),
  );
}

function getDraftWriteDisabledReason(
  draft: BroadcastDraft | null,
  fallbackReason: string | null,
  t: (key: string, options?: Record<string, unknown>) => string,
): string | null {
  if (fallbackReason) {
    return fallbackReason;
  }
  if (!draft) {
    return t('broadcast.drafts.noDraftSelectedReason');
  }
  if (!draft.conversationName.trim()) {
    return t('broadcast.drafts.pasteMissingConversation');
  }
  if (!draft.draftText.trim()) {
    return t('broadcast.drafts.pasteMissingBody');
  }
  if (draft.attachmentsStale) {
    return t('broadcast.drafts.attachmentsStaleWarning');
  }
  if (draft.draftsStale) {
    return t('broadcast.drafts.staleWarning');
  }
  return null;
}

function getDraftSendDisabledReason(
  draft: BroadcastDraft | null,
  fallbackReason: string | null,
  t: (key: string, options?: Record<string, unknown>) => string,
): string | null {
  if (fallbackReason) {
    return fallbackReason;
  }
  if (!draft) {
    return t('broadcast.drafts.noDraftSelectedReason');
  }
  if (draft.status === 'sent') {
    return t('broadcast.drafts.sendAlreadySent');
  }
  if (draft.status === 'unknown') {
    return t('broadcast.drafts.sendRequiresReview');
  }
  return getDraftWriteDisabledReason(draft, null, t);
}

function getPasteVerificationRuntimeState(
  executorHealth: BroadcastExecutorHealth | null,
): Record<string, unknown> | null {
  const runtimeStatus = executorHealth?.runtime_status;
  if (!runtimeStatus || typeof runtimeStatus !== 'object') {
    return null;
  }

  const pasteVerification = (runtimeStatus as Record<string, unknown>)
    .pasteVerification;
  if (!pasteVerification || typeof pasteVerification !== 'object') {
    return null;
  }

  return pasteVerification as Record<string, unknown>;
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
  const [groupRuleCandidates, setGroupRuleCandidates] =
    useState<BroadcastGroupRuleCandidateList | null>(null);
  const [groupRowsByKey, setGroupRowsByKey] = useState<
    Record<string, BroadcastImportGroupRowsPage | undefined>
  >({});
  const [importError, setImportError] = useState<string | null>(null);
  const [importBusyCount, setImportBusyCount] = useState(0);
  const [groupRuleCandidatesLoading, setGroupRuleCandidatesLoading] =
    useState(false);
  const [pendingImportConfirmation, setPendingImportConfirmation] =
    useState<PendingImportConfirmation | null>(null);
  const [pendingImportConfirmationBusy, setPendingImportConfirmationBusy] =
    useState(false);
  const [draftBusy, setDraftBusy] = useState(false);
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
  const [executorStateLoading, setExecutorStateLoading] = useState(true);
  const [executorHealth, setExecutorHealth] =
    useState<BroadcastExecutorHealth | null>(null);
  const [pasteRequestInFlight, setPasteRequestInFlight] = useState(false);
  const importPageSize = 50;
  const importRequestGenerationRef = useRef(0);
  const importDetailGenerationRef = useRef(0);
  const bootstrapRequestGenerationRef = useRef(0);
  const isMountedRef = useRef(true);
  const scopeRef = useRef(scope);
  const executorHealthRef = useRef<BroadcastExecutorHealth | null>(null);
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
  const completedExecutionBatchIdsRef = useRef(new Set<number>());
  const importBusy = importBusyCount > 0;

  const pasteVerificationState =
    getPasteVerificationRuntimeState(executorHealth);
  const executorRuntimeAvailable = executorHealth?.available === true;
  const runtimeReady =
    executorRuntimeAvailable && executorHealth?.status === 'ready';
  const executorOwnershipConflict =
    executorHealth?.error_code === 'RUNTIME_OWNERSHIP_CONFLICT';
  const pasteSupported = Boolean(executorCapability?.supports_paste);
  const sendSupported = Boolean(executorCapability?.supports_send);
  const pasteVerificationSupported = Boolean(
    executorCapability?.supports_paste_verification,
  );
  const pasteExecutionAvailable = runtimeReady && pasteSupported;
  const sendExecutionAvailable = runtimeReady && sendSupported;
  const pasteVerificationAvailable =
    runtimeReady &&
    pasteSupported &&
    pasteVerificationSupported &&
    (pasteVerificationState ? pasteVerificationState.available === true : true);
  const pasteVerificationMethod =
    pasteVerificationState?.method === 'windows_uia'
      ? 'windows_uia'
      : (executorCapability?.content_verification ?? 'unknown');
  const requiresManualConversationOpen = Boolean(
    pasteVerificationState?.requiresManualConversationOpen ??
    executorCapability?.requires_manual_conversation_open,
  );
  const executorUnavailableReason = useMemo(() => {
    if (executorOwnershipConflict) {
      return (
        executorHealth?.error_message ||
        t('broadcast.executor.runtimeOwnershipConflict')
      );
    }
    if (!executorRuntimeAvailable) {
      return (
        executorHealth?.error_message ||
        t('broadcast.executor.runtimeUnavailable')
      );
    }
    return null;
  }, [
    executorHealth?.error_message,
    executorOwnershipConflict,
    executorRuntimeAvailable,
    t,
  ]);
  const pasteExecutionDisabledReason = useMemo(() => {
    if (executorStateLoading) {
      return t('common.loading');
    }
    if (executorUnavailableReason) {
      return executorUnavailableReason;
    }
    if (!pasteSupported) {
      return t('broadcast.drafts.pasteUnavailable');
    }
    return null;
  }, [executorStateLoading, executorUnavailableReason, pasteSupported, t]);
  const sendExecutionDisabledReason = useMemo(() => {
    if (executorStateLoading) {
      return t('common.loading');
    }
    if (executorUnavailableReason) {
      return executorUnavailableReason;
    }
    if (!sendSupported) {
      return t('broadcast.drafts.sendUnavailable');
    }
    return null;
  }, [executorStateLoading, executorUnavailableReason, sendSupported, t]);
  const executorHealthMessage = useMemo(() => {
    if (executorStateLoading) {
      return t('common.loading');
    }
    if (executorUnavailableReason) {
      return executorUnavailableReason;
    }
    if (!sendSupported) {
      return t('broadcast.executor.sendUnsupported');
    }
    if (runtimeReady) {
      return t('broadcast.executor.realSendReady');
    }
    return t('broadcast.executor.runtimeUnavailable');
  }, [
    executorStateLoading,
    executorUnavailableReason,
    runtimeReady,
    sendSupported,
    t,
  ]);
  const pasteVerificationHint =
    pasteExecutionAvailable &&
    (!pasteVerificationSupported || !pasteVerificationAvailable)
      ? t('broadcast.logs.pasteVerificationUnavailableHint')
      : null;

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

  const selectedDrafts = useMemo(
    () =>
      selectedDraftIds
        .map(
          (draftId) =>
            snapshot.drafts.find((draft) => draft.id === draftId) ?? null,
        )
        .filter((draft): draft is BroadcastDraft => draft != null),
    [selectedDraftIds, snapshot.drafts],
  );

  const pasteActionDisabledReason = useMemo(
    () =>
      getDraftWriteDisabledReason(activeDraft, pasteExecutionDisabledReason, t),
    [activeDraft, pasteExecutionDisabledReason, t],
  );
  const sendActionDisabledReason = useMemo(
    () =>
      getDraftSendDisabledReason(activeDraft, sendExecutionDisabledReason, t),
    [activeDraft, sendExecutionDisabledReason, t],
  );

  const batchWriteDisabledReason = useMemo(() => {
    if (pasteExecutionDisabledReason) {
      return pasteExecutionDisabledReason;
    }
    if (selectedDrafts.length === 0) {
      return t('broadcast.drafts.batchWriteNoSelection');
    }
    if (selectedDrafts.some((draft) => draft.status !== 'pending')) {
      return t('broadcast.toasts.batchWritePendingOnly');
    }
    for (const draft of selectedDrafts) {
      const reason = getDraftWriteDisabledReason(draft, null, t);
      if (reason) {
        return reason;
      }
    }
    return null;
  }, [pasteExecutionDisabledReason, selectedDrafts, t]);
  const batchSendDisabledReason = useMemo(() => {
    if (sendExecutionDisabledReason) {
      return sendExecutionDisabledReason;
    }
    if (selectedDrafts.length === 0) {
      return t('broadcast.drafts.batchSendNoSelection');
    }
    if (selectedDrafts.some((draft) => draft.status !== 'pending')) {
      return t('broadcast.toasts.batchSendPendingOnly');
    }
    for (const draft of selectedDrafts) {
      const reason = getDraftSendDisabledReason(draft, null, t);
      if (reason) {
        return reason;
      }
    }
    return null;
  }, [selectedDrafts, sendExecutionDisabledReason, t]);
  const selectedDraftStatuses = useMemo(
    () => Array.from(new Set(selectedDrafts.map((draft) => draft.status))),
    [selectedDrafts],
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

  const clearPendingImportConfirmation = useCallback(() => {
    setPendingImportConfirmation(null);
    setPendingImportConfirmationBusy(false);
  }, []);

  const loadImportGroupRuleCandidates = useCallback(
    async (
      nextScope: BroadcastScope,
      importId: number,
      options?: {
        requestGeneration?: number;
      },
    ) => {
      setGroupRuleCandidatesLoading(true);
      try {
        const candidateList = await dataSource.getImportGroupRuleCandidates(
          nextScope,
          importId,
          {
            status: 'all',
            page: 1,
            pageSize: 200,
          },
        );
        if (
          !isMountedRef.current ||
          (options?.requestGeneration != null &&
            options.requestGeneration !== importRequestGenerationRef.current)
        ) {
          return null;
        }
        setGroupRuleCandidates(candidateList);
        return candidateList;
      } finally {
        if (isMountedRef.current) {
          setGroupRuleCandidatesLoading(false);
        }
      }
    },
    [dataSource],
  );

  const isImportRequestGenerationCurrent = (generation: number) =>
    isMountedRef.current && generation === importRequestGenerationRef.current;

  const refreshExecutorState = useCallback(
    async (
      nextScope?: BroadcastScope,
      options: { showLoading?: boolean } = {},
    ) => {
      const resolvedScope = nextScope ?? scopeRef.current;
      const showLoading =
        options.showLoading ?? executorHealthRef.current == null;
      if (showLoading) {
        setExecutorStateLoading(true);
      }
      try {
        const [capability, health] = await Promise.all([
          dataSource.getExecutorCapabilities(resolvedScope),
          dataSource.getExecutorHealth(resolvedScope),
        ]);
        setExecutorCapability(capability);
        executorHealthRef.current = health;
        setExecutorHealth(health);
      } catch {
        setExecutorCapability(null);
        executorHealthRef.current = null;
        setExecutorHealth(null);
      } finally {
        if (isMountedRef.current && showLoading) {
          setExecutorStateLoading(false);
        }
      }
    },
    [dataSource],
  );

  const refreshRules = async (
    nextScope: BroadcastScope = scopeRef.current,
  ): Promise<BroadcastRulesData> => {
    const rulesData = await dataSource.loadRulesData(nextScope);
    if (!isMountedRef.current || !isSameScope(scopeRef.current, nextScope)) {
      return rulesData;
    }
    setScope(nextScope);
    setSnapshot((current) =>
      applyRulesDataToSnapshot(
        current,
        rulesData,
        selectedImportDetailRef.current,
      ),
    );
    return rulesData;
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
        try {
          await loadImportGroupRuleCandidates(nextScope, nextImportId, {
            requestGeneration,
          });
        } catch {
          if (isImportRequestGenerationCurrent(requestGeneration)) {
            setGroupRuleCandidates(null);
          }
        }
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
      setGroupRuleCandidates(null);
      setGroupRowsByKey({});
      setImportError(null);
      clearPendingImportConfirmation();
    },
    [
      applyImportDetail,
      applyImportGroupsDetail,
      clearPendingImportConfirmation,
      setSelectedImportIdState,
    ],
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
    const timer = window.setInterval(() => {
      void refreshExecutorState(scope, { showLoading: false });
    }, 5000);

    return () => {
      window.clearInterval(timer);
    };
  }, [refreshExecutorState, scope]);

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

  useEffect(() => {
    if (
      !latestExecutionBatch ||
      latestExecutionBatch.mode !== 'send' ||
      !EXECUTION_TERMINAL_STATUSES.has(latestExecutionBatch.status) ||
      completedExecutionBatchIdsRef.current.has(latestExecutionBatch.id)
    ) {
      return;
    }
    completedExecutionBatchIdsRef.current.add(latestExecutionBatch.id);
    const sentCount =
      latestExecutionBatch.sentCount ?? latestExecutionBatch.succeededTasks;
    const failedCount =
      latestExecutionBatch.failedCount ?? latestExecutionBatch.failedTasks;
    const unknownCount =
      latestExecutionBatch.unknownCount ??
      latestExecutionBatch.unknownTasks ??
      0;
    if (unknownCount > 0) {
      toast.warning(
        t('broadcast.toasts.realSendCompletedWithUnknown', {
          sentCount,
          failedCount,
          unknownCount,
        }),
      );
    } else if (failedCount > 0) {
      toast.warning(
        t('broadcast.toasts.realSendCompletedWithFailures', {
          sentCount,
          failedCount,
        }),
      );
    } else {
      toast.success(t('broadcast.toasts.realSendCompleted', { sentCount }));
    }
  }, [latestExecutionBatch, t]);

  const resolveTargetDrafts = useCallback(() => {
    if (selectedDrafts.length > 0) {
      return selectedDrafts;
    }
    return activeDraft ? [activeDraft] : [];
  }, [activeDraft, selectedDrafts]);

  const handleCreateExecutionBatch = async () => {
    if (!pasteExecutionAvailable) {
      toast.error(
        pasteExecutionDisabledReason ?? t('broadcast.drafts.pasteUnavailable'),
      );
      return;
    }
    const targetDrafts = resolveTargetDrafts();
    if (targetDrafts.length === 0) {
      toast.error(t('broadcast.toasts.noDraftSelected'));
      return;
    }
    if (
      targetDrafts.some(
        (draft) => draft.status !== 'pending' || !canWriteDraftToInput(draft),
      )
    ) {
      toast.error(t('broadcast.toasts.batchWritePendingOnly'));
      return;
    }
    setDraftBusy(true);
    try {
      const batch = await dataSource.createExecutionBatch(
        scope,
        targetDrafts.map((draft) => draft.id),
        'paste_only',
        OPERATOR_EMAIL,
      );
      setTopTab('logs');
      setLatestExecutionBatch(batch);
      try {
        const started = await dataSource.startExecutionBatch(
          scope,
          batch.id,
          OPERATOR_EMAIL,
        );
        setLatestExecutionBatch(started);
        await refreshExecutionState(scope);
        toast.success(t('broadcast.toasts.executionBatchStarted'));
      } catch (error) {
        await refreshExecutionState(scope, { refreshLatestLogsOnly: true });
        toast.error(getErrorMessage(error, t('common.error')));
      }
    } catch (error) {
      toast.error(getErrorMessage(error, t('common.error')));
    } finally {
      setDraftBusy(false);
    }
  };

  const handleCreateSendBatch = async (targetDrafts: BroadcastDraft[]) => {
    if (!sendExecutionAvailable) {
      toast.error(
        sendExecutionDisabledReason ?? t('broadcast.drafts.sendUnavailable'),
      );
      return;
    }
    if (targetDrafts.length === 0) {
      toast.error(t('broadcast.toasts.noDraftSelected'));
      return;
    }
    if (targetDrafts.some((draft) => !canSendDraftForReal(draft))) {
      toast.error(t('broadcast.toasts.batchSendPendingOnly'));
      return;
    }
    setDraftBusy(true);
    try {
      const batch = await dataSource.createExecutionBatch(
        scope,
        targetDrafts.map((draft) => draft.id),
        'send',
        OPERATOR_EMAIL,
      );
      setTopTab('logs');
      setLatestExecutionBatch(batch);
      await refreshDrafts();
      await refreshExecutionState(scope, { refreshAllLogs: true });
      toast.success(t('broadcast.toasts.executionBatchStarted'));
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
      !pasteExecutionAvailable
    ) {
      toast.error(
        pasteExecutionDisabledReason ?? t('broadcast.drafts.pasteUnavailable'),
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

  const handleRetryFailedExecutionTasks = async () => {
    if (!latestExecutionBatch) {
      return;
    }
    const retryableTaskIds = Array.from(
      new Set(
        getRetryableExecutionTasks(latestExecutionBatch).map((task) => task.id),
      ),
    );
    if (retryableTaskIds.length === 0) {
      toast.error(t('broadcast.toasts.executionFailedTasksRetryNoop'));
      return;
    }
    let successCount = 0;
    let failedCount = 0;
    setDraftBusy(true);
    try {
      for (const taskId of retryableTaskIds) {
        try {
          await dataSource.retryExecutionTask(scope, taskId, OPERATOR_EMAIL);
          successCount += 1;
        } catch {
          failedCount += 1;
        }
      }
      await refreshExecutionState(scope);
      if (successCount > 0) {
        toast.success(
          t('broadcast.toasts.executionFailedTasksRetried', {
            successCount,
            failedCount,
          }),
        );
      } else {
        toast.error(t('broadcast.toasts.executionFailedTasksRetryNoop'));
      }
    } finally {
      setDraftBusy(false);
    }
  };

  const handlePasteDraft = async (draft: BroadcastDraft) => {
    if (pasteRequestInFlight) {
      return;
    }
    if (!pasteExecutionAvailable) {
      toast.error(
        pasteExecutionDisabledReason ?? t('broadcast.drafts.pasteUnavailable'),
      );
      return;
    }
    if (!canWriteDraftToInput(draft)) {
      toast.error(
        getDraftWriteDisabledReason(draft, null, t) ??
          t('broadcast.drafts.pasteUnavailable'),
      );
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
        {
          allowSentRewrite: draft.status === 'sent',
        },
      );
      setTopTab('logs');
      setLatestExecutionBatch(batch);
      try {
        const started = await dataSource.startExecutionBatch(
          scope,
          batch.id,
          OPERATOR_EMAIL,
        );
        setLatestExecutionBatch(started);
        await refreshExecutionState(scope);
        toast.success(t('broadcast.toasts.pasteSubmitted'));
      } catch (error) {
        await refreshExecutionState(scope, { refreshLatestLogsOnly: true });
        toast.error(getErrorMessage(error, t('common.error')));
      }
    } catch (error) {
      toast.error(getErrorMessage(error, t('common.error')));
    } finally {
      setDraftBusy(false);
      setPasteRequestInFlight(false);
    }
  };

  const runRulesMutation = async <T,>(
    action: () => Promise<T>,
    options: {
      successMessage?: string;
      refreshScope?: BroadcastScope;
      afterRefresh?: (result: T, rulesData: BroadcastRulesData) => void;
    } = {},
  ): Promise<T> => {
    const refreshScope = options.refreshScope ?? {
      botUuid: scope.botUuid,
      connectorId: scope.connectorId,
    };

    setRulesSaving(true);
    setRulesError(null);

    try {
      const result = await action();
      const rulesData = await refreshRules(refreshScope);
      options.afterRefresh?.(result, rulesData);
      if (options.successMessage) {
        toast.success(options.successMessage);
      }
      return result;
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
      toast.success(t('broadcast.toasts.draftSaved'));
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

  const handleUpdateDraftStatuses = async (
    draftIds: number[],
    status: 'pending' | 'sent',
    successMessage: string,
  ) => {
    if (draftIds.length === 0) {
      toast.error(t('broadcast.toasts.noDraftSelected'));
      return;
    }
    setDraftBusy(true);
    try {
      await dataSource.updateDraftStatuses(scope, draftIds, status);
      await refreshDrafts();
      toast.success(successMessage);
    } catch (error) {
      toast.error(getErrorMessage(error, t('common.error')));
    } finally {
      setDraftBusy(false);
    }
  };

  const handleBatchMarkSent = async () => {
    const targetDrafts = resolveTargetDrafts();
    if (targetDrafts.length === 0) {
      toast.error(t('broadcast.toasts.noDraftSelected'));
      return;
    }
    const currentStatuses = Array.from(
      new Set(targetDrafts.map((draft) => draft.status)),
    );
    if (
      currentStatuses.length !== 1 ||
      !['pending', 'unknown'].includes(currentStatuses[0] ?? '')
    ) {
      toast.error(t('broadcast.toasts.batchMarkSentResolvableOnly'));
      return;
    }
    await handleUpdateDraftStatuses(
      targetDrafts.map((draft) => draft.id),
      'sent',
      t('broadcast.toasts.draftsMarkedSent'),
    );
  };

  const handleBatchRestorePending = async () => {
    const targetDrafts = resolveTargetDrafts();
    if (targetDrafts.length === 0) {
      toast.error(t('broadcast.toasts.noDraftSelected'));
      return;
    }
    const currentStatuses = Array.from(
      new Set(targetDrafts.map((draft) => draft.status)),
    );
    if (
      currentStatuses.length !== 1 ||
      !['sent', 'unknown'].includes(currentStatuses[0] ?? '')
    ) {
      toast.error(t('broadcast.toasts.batchRestorePendingResolvableOnly'));
      return;
    }
    await handleUpdateDraftStatuses(
      targetDrafts.map((draft) => draft.id),
      'pending',
      t('broadcast.toasts.draftsRestoredPending'),
    );
  };

  const handleScopeChange = async (botUuid: string) => {
    const nextScope = scopeOptions.find((option) => option.botUuid === botUuid);
    if (!nextScope) {
      return;
    }

    const resolvedNextScope: BroadcastScope = {
      botUuid: nextScope.botUuid,
      connectorId: nextScope.connectorId,
    };
    scopeRef.current = resolvedNextScope;
    setScope(resolvedNextScope);

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
      await refreshRules(resolvedNextScope);
      await refreshImports(resolvedNextScope);
      await refreshDrafts(resolvedNextScope);
      await refreshExecutionState(resolvedNextScope);
      await refreshExecutorState(resolvedNextScope);
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
        <BroadcastTabs
          options={topTabOptions}
          testId="broadcast-primary-tabs"
        />

        <TabsContent value="rules" className="mt-0 min-h-0">
          <Tabs
            value={rulesTab}
            onValueChange={(value) => setRulesTab(value as BroadcastRulesTab)}
            className="flex min-h-0 flex-col gap-4"
          >
            <BroadcastTabs
              options={rulesTabOptions}
              size="compact"
              testId="broadcast-secondary-tabs"
            />
            <TabsContent value="variables" className="mt-0 min-h-0">
              <VariableMappingPanel
                variableProfile={snapshot.variableProfile}
                templates={snapshot.templates}
                importDetail={selectedImportDetail}
                loading={rulesLoading}
                saving={rulesSaving}
                error={rulesError}
                onSave={(profile) =>
                  runRulesMutation(
                    async () => {
                      await dataSource.saveVariableProfile(scope, profile);
                    },
                    { successMessage: t('broadcast.toasts.rulesSaved') },
                  )
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
                  runRulesMutation(
                    async () => {
                      await dataSource.createTemplate(scope, draft);
                    },
                    { successMessage: t('broadcast.toasts.templateSaved') },
                  )
                }
                onUpdate={(templateId, draft) =>
                  runRulesMutation(
                    async () => {
                      await dataSource.updateTemplate(scope, templateId, draft);
                    },
                    { successMessage: t('broadcast.toasts.templateSaved') },
                  )
                }
                onDelete={(templateId) =>
                  runRulesMutation(
                    async () => {
                      await dataSource.deleteTemplate(scope, templateId);
                    },
                    { successMessage: t('broadcast.toasts.templateDeleted') },
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
            <TabsContent value="groups" className="mt-0 min-h-0">
              <GroupMatchingPanel
                scope={scope}
                rules={snapshot.groupRules}
                groupNames={snapshot.groupNames}
                batches={importBatches}
                selectedBatchId={selectedImportId}
                selectedBatch={
                  importBatches.find(
                    (batch) => batch.id === selectedImportId,
                  ) ?? null
                }
                groupRuleCandidates={groupRuleCandidates}
                groupRuleCandidatesLoading={groupRuleCandidatesLoading}
                loading={rulesLoading}
                saving={rulesSaving}
                error={rulesError}
                onSelectBatch={async (batchId) => {
                  const requestGeneration =
                    ++importRequestGenerationRef.current;
                  const detailGeneration = ++importDetailGenerationRef.current;
                  const releaseImportBusy = beginImportBusy();
                  setSelectedImportIdState(batchId);
                  clearPendingImportConfirmation();
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
                    try {
                      await loadImportGroupRuleCandidates(scope, batchId, {
                        requestGeneration,
                      });
                    } catch {
                      if (isImportRequestGenerationCurrent(requestGeneration)) {
                        setGroupRuleCandidates(null);
                      }
                    }
                    await refreshDrafts(scope, batchId);
                  } catch (error) {
                    const message = getErrorMessage(error, t('common.error'));
                    setImportError(message);
                    toast.error(message);
                  } finally {
                    releaseImportBusy();
                  }
                }}
                onOpenBulkAssignDialog={async () => {
                  if (!selectedImportIdRef.current) {
                    setGroupRuleCandidates(null);
                    return;
                  }
                  try {
                    await loadImportGroupRuleCandidates(
                      scope,
                      selectedImportIdRef.current,
                      {
                        requestGeneration: importRequestGenerationRef.current,
                      },
                    );
                  } catch (error) {
                    const message = getErrorMessage(error, t('common.error'));
                    setImportError(message);
                    toast.error(message);
                  }
                }}
                onBulkAssignGroupRules={async (batchId, items) => {
                  const requestGeneration =
                    ++importRequestGenerationRef.current;
                  const currentGroupPage =
                    selectedImportGroupsDetailRef.current?.page ?? 1;
                  const releaseImportBusy = beginImportBusy();
                  setImportError(null);
                  try {
                    const result = await dataSource.bulkAssignImportGroupRules(
                      scope,
                      batchId,
                      items,
                    );
                    await refreshRules(scope);
                    await refreshImports(scope, {
                      preferredImportId: batchId,
                      requestGeneration,
                      variableProfile: latestRulesRef.current.variableProfile,
                      templates: latestRulesRef.current.templates,
                    });
                    await refreshDrafts(scope, batchId);
                    await loadImportGroupsPage(
                      scope,
                      batchId,
                      currentGroupPage,
                      {
                        requestGeneration,
                      },
                    );
                    try {
                      await loadImportGroupRuleCandidates(scope, batchId, {
                        requestGeneration,
                      });
                    } catch {
                      if (isImportRequestGenerationCurrent(requestGeneration)) {
                        setGroupRuleCandidates(null);
                      }
                    }
                    setGroupRowsByKey({});
                    toast.success(
                      t('broadcast.toasts.importBulkAssignCompleted', {
                        count: result.items.length,
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
                onCreateRule={(draft) =>
                  runRulesMutation(
                    async () => {
                      await dataSource.createGroupRule(scope, draft);
                    },
                    { successMessage: t('broadcast.toasts.groupRuleSaved') },
                  )
                }
                onUpdateRule={(ruleId, draft) =>
                  runRulesMutation(
                    async () => {
                      await dataSource.updateGroupRule(scope, ruleId, draft);
                    },
                    { successMessage: t('broadcast.toasts.groupRuleSaved') },
                  )
                }
                onDeleteRule={(ruleId) =>
                  runRulesMutation(
                    async () => {
                      await dataSource.deleteGroupRule(scope, ruleId);
                    },
                    { successMessage: t('broadcast.toasts.groupRuleDeleted') },
                  )
                }
                onMatchRule={(sourceValue) =>
                  dataSource.matchGroupRule(scope, sourceValue)
                }
                onCreateGroupName={(groupName) => {
                  const mutationScope: BroadcastScope = {
                    botUuid: scope.botUuid,
                    connectorId: scope.connectorId,
                  };
                  return runRulesMutation(
                    async () =>
                      await dataSource.createGroupName(
                        mutationScope,
                        groupName,
                      ),
                    {
                      refreshScope: mutationScope,
                      afterRefresh: (result, rulesData) => {
                        if (!isSameScope(scopeRef.current, mutationScope)) {
                          return;
                        }
                        const persistedGroup =
                          rulesData.groupNames.find(
                            (item) => item.id === result.group.id,
                          ) ?? null;
                        if (!persistedGroup) {
                          throw new Error(
                            t('broadcast.toasts.groupNameReloadMissing', {
                              name: result.group.name,
                            }),
                          );
                        }
                        if (result.status === 'created') {
                          toast.success(
                            t('broadcast.toasts.groupNameAdded', {
                              name: persistedGroup.name,
                            }),
                          );
                          return;
                        }
                        toast.error(
                          t('broadcast.toasts.groupNameExists', {
                            name: persistedGroup.name,
                          }),
                        );
                      },
                    },
                  );
                }}
                onSyncGroupNames={async () => {
                  const mutationScope: BroadcastScope = {
                    botUuid: scope.botUuid,
                    connectorId: scope.connectorId,
                  };
                  await runRulesMutation(
                    async () => await dataSource.syncGroupNames(mutationScope),
                    {
                      refreshScope: mutationScope,
                      afterRefresh: (result) => {
                        if (!isSameScope(scopeRef.current, mutationScope)) {
                          return;
                        }
                        toast.success(
                          t('broadcast.toasts.groupNamesSynced', {
                            scanned: result.scanned,
                            inserted: result.inserted,
                            updated: result.updated,
                            unchanged: result.unchanged,
                          }),
                        );
                      },
                    },
                  );
                }}
                onDeleteGroupName={(groupNameId) =>
                  runRulesMutation(
                    async () => {
                      await dataSource.deleteGroupName(scope, groupNameId);
                    },
                    { successMessage: t('broadcast.toasts.groupNameDeleted') },
                  )
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
            groupRules={snapshot.groupRules}
            groupNames={snapshot.groupNames}
            groupRuleCandidates={groupRuleCandidates}
            selectedBatchDraftCount={
              selectedImportId != null
                ? snapshot.drafts.filter(
                    (draft) => draft.importBatchId === selectedImportId,
                  ).length
                : 0
            }
            loading={rulesLoading}
            busy={importBusy}
            groupRuleCandidatesLoading={groupRuleCandidatesLoading}
            confirmationBusy={pendingImportConfirmationBusy}
            error={importError}
            pendingImportConfirmation={
              pendingImportConfirmation?.details ?? null
            }
            onUpload={async (file) => {
              const requestGeneration = ++importRequestGenerationRef.current;
              const detailGeneration = ++importDetailGenerationRef.current;
              const releaseImportBusy = beginImportBusy();
              clearPendingImportConfirmation();
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
                try {
                  await loadImportGroupRuleCandidates(scope, batch.id, {
                    requestGeneration,
                  });
                } catch {
                  if (isImportRequestGenerationCurrent(requestGeneration)) {
                    setGroupRuleCandidates(null);
                  }
                }
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
                if (
                  isBackendErrorCode(
                    error,
                    'BROADCAST_IMPORT_GROUP_FIELD_CONFIRMATION_REQUIRED',
                  )
                ) {
                  const details =
                    readImportGroupFieldConfirmationDetails(error);
                  if (details) {
                    setPendingImportConfirmation({
                      file,
                      details,
                    });
                    return;
                  }
                }
                const message = getErrorMessage(error, t('common.error'));
                setImportError(message);
                toast.error(message);
              } finally {
                releaseImportBusy();
              }
            }}
            onConfirmImportGroupField={async (groupField) => {
              if (!pendingImportConfirmation) {
                return;
              }
              const requestGeneration = ++importRequestGenerationRef.current;
              const detailGeneration = ++importDetailGenerationRef.current;
              const releaseImportBusy = beginImportBusy();
              setPendingImportConfirmationBusy(true);
              setImportError(null);
              try {
                const batch = await dataSource.uploadImport(
                  scope,
                  pendingImportConfirmation.file,
                  {
                    groupFieldOverride: groupField,
                  },
                );
                clearPendingImportConfirmation();
                if (
                  !isMountedRef.current ||
                  requestGeneration !== importRequestGenerationRef.current
                ) {
                  return;
                }
                setImportBatches((current) => [
                  batch,
                  ...current.filter((item) => item.id !== batch.id),
                ]);
                setSelectedImportIdState(batch.id);
                applyImportDetail(
                  createPlaceholderImportDetail(batch, importPageSize),
                  latestRulesRef.current.variableProfile,
                  latestRulesRef.current.templates,
                );
                applyImportGroupsDetail(null);
                setGroupRuleCandidates(null);
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
                try {
                  await loadImportGroupRuleCandidates(scope, batch.id, {
                    requestGeneration,
                  });
                } catch {
                  if (isImportRequestGenerationCurrent(requestGeneration)) {
                    setGroupRuleCandidates(null);
                  }
                }
                toast.success(
                  t('broadcast.toasts.importUploaded', {
                    fileName: batch.originalFileName,
                  }),
                );
              } catch (error) {
                if (
                  isBackendErrorCode(
                    error,
                    'BROADCAST_IMPORT_GROUP_FIELD_CONFIRMATION_REQUIRED',
                  )
                ) {
                  const details =
                    readImportGroupFieldConfirmationDetails(error);
                  if (details) {
                    setPendingImportConfirmation({
                      file: pendingImportConfirmation.file,
                      details,
                    });
                    return;
                  }
                }
                const message = getErrorMessage(error, t('common.error'));
                setImportError(message);
                toast.error(message);
              } finally {
                setPendingImportConfirmationBusy(false);
                releaseImportBusy();
              }
            }}
            onCancelImportGroupField={clearPendingImportConfirmation}
            onSelectBatch={async (batchId) => {
              const requestGeneration = ++importRequestGenerationRef.current;
              const detailGeneration = ++importDetailGenerationRef.current;
              const releaseImportBusy = beginImportBusy();
              setSelectedImportIdState(batchId);
              clearPendingImportConfirmation();
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
                try {
                  await loadImportGroupRuleCandidates(scope, batchId, {
                    requestGeneration,
                  });
                } catch {
                  if (isImportRequestGenerationCurrent(requestGeneration)) {
                    setGroupRuleCandidates(null);
                  }
                }
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
              const requestGeneration = ++importRequestGenerationRef.current;
              ++importDetailGenerationRef.current;
              const releaseImportBusy = beginImportBusy();
              setImportError(null);
              try {
                await loadImportGroupsPage(
                  scope,
                  selectedImportIdRef.current,
                  page,
                  { requestGeneration },
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
              clearPendingImportConfirmation();
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
                try {
                  await loadImportGroupRuleCandidates(scope, batchId, {
                    requestGeneration,
                  });
                } catch {
                  if (isImportRequestGenerationCurrent(requestGeneration)) {
                    setGroupRuleCandidates(null);
                  }
                }
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
            onOpenBulkAssignDialog={async () => {
              if (!selectedImportIdRef.current) {
                setGroupRuleCandidates(null);
                return;
              }
              try {
                await loadImportGroupRuleCandidates(
                  scope,
                  selectedImportIdRef.current,
                  {
                    requestGeneration: importRequestGenerationRef.current,
                  },
                );
              } catch (error) {
                const message = getErrorMessage(error, t('common.error'));
                setImportError(message);
                toast.error(message);
              }
            }}
            onBulkAssignGroupRules={async (batchId, items) => {
              const requestGeneration = ++importRequestGenerationRef.current;
              const currentGroupPage =
                selectedImportGroupsDetailRef.current?.page ?? 1;
              const releaseImportBusy = beginImportBusy();
              setImportError(null);
              try {
                const result = await dataSource.bulkAssignImportGroupRules(
                  scope,
                  batchId,
                  items,
                );
                await refreshRules(scope);
                await refreshImports(scope, {
                  preferredImportId: batchId,
                  requestGeneration,
                  variableProfile: latestRulesRef.current.variableProfile,
                  templates: latestRulesRef.current.templates,
                });
                await refreshDrafts(scope, batchId);
                await loadImportGroupsPage(scope, batchId, currentGroupPage, {
                  requestGeneration,
                });
                try {
                  await loadImportGroupRuleCandidates(scope, batchId, {
                    requestGeneration,
                  });
                } catch {
                  if (isImportRequestGenerationCurrent(requestGeneration)) {
                    setGroupRuleCandidates(null);
                  }
                }
                setGroupRowsByKey({});
                toast.success(
                  t('broadcast.toasts.importBulkAssignCompleted', {
                    count: result.items.length,
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
            onUpdateGroupTemplateAssignments={async (batchId, items) => {
              const requestGeneration = ++importRequestGenerationRef.current;
              const currentGroupPage =
                selectedImportGroupsDetailRef.current?.page ?? 1;
              const releaseImportBusy = beginImportBusy();
              setImportError(null);
              try {
                await dataSource.updateImportGroupTemplateAssignments(
                  scope,
                  batchId,
                  items,
                );
                await refreshImports(scope, {
                  preferredImportId: batchId,
                  requestGeneration,
                  variableProfile: latestRulesRef.current.variableProfile,
                  templates: latestRulesRef.current.templates,
                });
                await loadImportGroupsPage(scope, batchId, currentGroupPage, {
                  requestGeneration,
                });
              } catch (error) {
                const message = getErrorMessage(error, t('common.error'));
                setImportError(message);
                toast.error(message);
              } finally {
                releaseImportBusy();
              }
            }}
            onSaveExactMatchRule={async (payload) => {
              const requestGeneration = ++importRequestGenerationRef.current;
              const currentGroupPage =
                selectedImportGroupsDetailRef.current?.page ?? 1;
              const releaseImportBusy = beginImportBusy();
              setImportError(null);
              try {
                const ruleDraft = {
                  sourceValue: payload.groupValue,
                  matchType: 'exact' as const,
                  matchExpression: payload.groupValue,
                  targetConversationId: payload.targetConversationId,
                  targetConversationName: payload.targetConversationName,
                  priority: payload.existingRulePriority ?? 0,
                  enabled: true,
                };
                if (payload.existingRuleId != null) {
                  await dataSource.updateGroupRule(
                    scope,
                    payload.existingRuleId,
                    ruleDraft,
                  );
                } else {
                  await dataSource.createGroupRule(scope, ruleDraft);
                }
                await refreshRules(scope);
                const detail = await dataSource.rematchImport(
                  scope,
                  payload.batchId,
                );
                await refreshImports(scope, {
                  preferredImportId: payload.batchId,
                  requestGeneration,
                  variableProfile: latestRulesRef.current.variableProfile,
                  templates: latestRulesRef.current.templates,
                });
                await refreshDrafts(scope, payload.batchId);
                applyImportDetail(
                  detail,
                  latestRulesRef.current.variableProfile,
                  latestRulesRef.current.templates,
                );
                await loadImportGroupsPage(
                  scope,
                  payload.batchId,
                  currentGroupPage,
                  {
                    requestGeneration,
                  },
                );
                setGroupRowsByKey({});
                toast.success(t('broadcast.toasts.importInlineMatchSaved'));
              } catch (error) {
                const message = getErrorMessage(error, t('common.error'));
                setImportError(message);
                toast.error(message);
                throw error;
              } finally {
                releaseImportBusy();
              }
            }}
            onNavigateToGroupMatching={() => {
              setTopTab('rules');
              setRulesTab('groups');
            }}
            onGenerateDrafts={async (batchId, groupKeys) => {
              const requestGeneration = ++importRequestGenerationRef.current;
              const releaseImportBusy = beginImportBusy();
              setImportError(null);
              try {
                const result = await dataSource.generateImportDrafts(
                  scope,
                  batchId,
                  {
                    groupKeys,
                    overwriteExisting: true,
                  },
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
                    count:
                      result.generatedGroupKeys?.length ??
                      result.totalGroupCount,
                    createdCount: result.createdCount ?? 0,
                    updatedCount: result.updatedCount ?? 0,
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
              busy={draftBusy}
              canBatchWrite={
                pasteExecutionAvailable &&
                selectedDrafts.length > 0 &&
                selectedDrafts.every(
                  (draft) =>
                    draft.status === 'pending' && canWriteDraftToInput(draft),
                )
              }
              batchWriteDisabledReason={batchWriteDisabledReason}
              canBatchSend={
                sendExecutionAvailable &&
                selectedDrafts.length > 0 &&
                selectedDrafts.every((draft) => canSendDraftForReal(draft))
              }
              batchSendDisabledReason={batchSendDisabledReason}
              canBatchMarkSent={
                selectedDrafts.length > 0 &&
                selectedDraftStatuses.length === 1 &&
                ['pending', 'unknown'].includes(selectedDraftStatuses[0] ?? '')
              }
              canBatchRestorePending={
                selectedDrafts.length > 0 &&
                selectedDraftStatuses.length === 1 &&
                ['sent', 'unknown'].includes(selectedDraftStatuses[0] ?? '')
              }
              onImportBatchChange={setDraftImportBatchId}
              onSearchTermChange={setSearchTerm}
              onStatusFilterChange={setStatusFilter}
              onSelectDraft={handleSelectDraft}
              onToggleDraftSelection={handleToggleDraftSelection}
              onBatchWrite={() => void handleCreateExecutionBatch()}
              onBatchSend={() => void handleCreateSendBatch(selectedDrafts)}
              onBatchMarkSent={() => void handleBatchMarkSent()}
              onBatchRestorePending={() => void handleBatchRestorePending()}
            />
            <DraftDetail
              draft={activeDraft}
              editingDraftId={editingDraftId}
              draftEditorText={draftEditorText}
              busy={draftBusy}
              canPasteDraft={
                pasteExecutionAvailable && canWriteDraftToInput(activeDraft)
              }
              pasteDisabledReason={pasteActionDisabledReason}
              pasteHint={pasteVerificationHint}
              canSendDraft={
                sendExecutionAvailable && canSendDraftForReal(activeDraft)
              }
              sendDisabledReason={sendActionDisabledReason}
              onStartEdit={handleStartEdit}
              onDraftEditorTextChange={setDraftEditorText}
              onSaveDraft={() => void handleSaveDraft()}
              onCancelEdit={handleCancelEdit}
              onMarkSent={() =>
                activeDraft &&
                void handleUpdateDraftStatuses(
                  [activeDraft.id],
                  'sent',
                  t('broadcast.toasts.draftsMarkedSent'),
                )
              }
              onRestorePending={() =>
                activeDraft &&
                void handleUpdateDraftStatuses(
                  [activeDraft.id],
                  'pending',
                  t('broadcast.toasts.draftsRestoredPending'),
                )
              }
              onPasteDraft={() =>
                activeDraft && void handlePasteDraft(activeDraft)
              }
              onSendDraft={() =>
                activeDraft && void handleCreateSendBatch([activeDraft])
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
            executorHealthLoading={executorStateLoading}
            executorHealthMessage={executorHealthMessage}
            pasteExecutionAvailable={pasteExecutionAvailable}
            pasteVerificationAvailable={pasteVerificationAvailable}
            pasteVerificationMethod={pasteVerificationMethod}
            requiresManualConversationOpen={requiresManualConversationOpen}
            pasteActionDisabledReason={pasteExecutionDisabledReason}
            pasteVerificationHint={pasteVerificationHint}
            busy={draftBusy}
            onRecheckExecutorHealth={() => void refreshExecutorState(scope)}
            onClearTerminalRecords={() =>
              void (async () => {
                try {
                  setDraftBusy(true);
                  const result =
                    await dataSource.clearTerminalExecutionBatches(scope);
                  executionBatchCacheRef.current.clear();
                  executionLogCacheRef.current.clear();
                  executionLogsHydratedRef.current = false;
                  await refreshExecutionState(scope, { refreshAllLogs: true });
                  if (result.deletedBatches === 0) {
                    toast.success(t('broadcast.logs.clearTerminalEmpty'));
                  } else if (result.preservedActiveBatches > 0) {
                    toast.success(
                      t('broadcast.logs.clearTerminalSuccessWithActive', {
                        count: result.deletedBatches,
                        active: result.preservedActiveBatches,
                      }),
                    );
                  } else {
                    toast.success(
                      t('broadcast.logs.clearTerminalSuccess', {
                        count: result.deletedBatches,
                      }),
                    );
                  }
                } catch (error) {
                  toast.error(getErrorMessage(error, t('common.error')));
                } finally {
                  setDraftBusy(false);
                }
              })()
            }
            onStartBatch={() => void handleBatchAction('start')}
            onPauseBatch={() => void handleBatchAction('pause')}
            onResumeBatch={() => void handleBatchAction('resume')}
            onCancelBatch={() => void handleBatchAction('cancel')}
            onRetryTask={(taskId) => void handleRetryExecutionTask(taskId)}
            onRetryFailedTasks={() => void handleRetryFailedExecutionTasks()}
          />
        </TabsContent>
      </Tabs>
    </div>
  );
}
