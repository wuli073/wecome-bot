import { Fragment, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
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
import { Checkbox } from '@/components/ui/checkbox';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';

import type {
  BroadcastAttachment,
  BroadcastGroupName,
  BroadcastGroupRule,
  BroadcastImportBatch,
  BroadcastImportDetail,
  BroadcastImportGroupFieldConfirmationDetails,
  BroadcastImportGroupList,
  BroadcastImportGroupMatchStatus,
  BroadcastImportGroupRowsPage,
  BroadcastImportGroupSummary,
  BroadcastGroupRuleCandidateList,
  BroadcastImportPreviewRow,
  BroadcastMessageTemplate,
} from '../../types';
import { markBroadcastRender } from '../../diagnostics';

interface ImportMatchingPanelProps {
  batches: BroadcastImportBatch[];
  selectedBatchId: number | null;
  detail: BroadcastImportDetail | null;
  groupsDetail: BroadcastImportGroupList | null;
  groupRowsByKey: Record<string, BroadcastImportGroupRowsPage | undefined>;
  templates: BroadcastMessageTemplate[];
  groupRules?: BroadcastGroupRule[];
  groupNames?: BroadcastGroupName[];
  groupRuleCandidates?: BroadcastGroupRuleCandidateList | null;
  selectedBatchDraftCount?: number;
  loading?: boolean;
  busy?: boolean;
  groupRuleCandidatesLoading?: boolean;
  confirmationBusy?: boolean;
  error?: string | null;
  onUpload: (file: File) => Promise<void>;
  pendingImportConfirmation: BroadcastImportGroupFieldConfirmationDetails | null;
  onConfirmImportGroupField: (groupField: string) => Promise<void>;
  onCancelImportGroupField: () => void;
  onSelectBatch: (batchId: number) => Promise<void>;
  onPageChange: (page: number) => Promise<void>;
  onDeleteBatch: (batchId: number) => Promise<void>;
  onRematch: (batchId: number) => Promise<void>;
  onOpenBulkAssignDialog?: () => Promise<void>;
  onBulkAssignGroupRules?: (
    batchId: number,
    items: Array<{ groupKey: string; targetConversationId: string }>,
  ) => Promise<void>;
  onGenerateDrafts: (batchId: number, groupKeys: string[]) => Promise<void>;
  onNavigateToGroupMatching: () => void;
  onUpdateGroupTemplateAssignments: (
    batchId: number,
    items: Array<{ groupKey: string; templateId: number | null }>,
  ) => Promise<void>;
  onSaveExactMatchRule?: (payload: {
    batchId: number;
    groupValue: string;
    targetConversationId: string;
    targetConversationName: string;
    existingRuleId?: number;
    existingRulePriority?: number;
  }) => Promise<void>;
  onLoadGroupRows: (groupKey: string, page?: number) => Promise<void>;
  onUploadGroupAttachments: (groupKey: string, files: File[]) => Promise<void>;
  onDeleteGroupAttachment: (
    groupKey: string,
    attachmentId: number,
  ) => Promise<void>;
}

const EMPTY_ATTACHMENTS: BroadcastAttachment[] = [];
const EMPTY_GROUPS: BroadcastImportGroupSummary[] = [];
const UNASSIGNED_TEMPLATE_OPTION = '__unassigned__';

function renderMatchStatusLabel(
  status: BroadcastImportGroupMatchStatus,
  t: ReturnType<typeof useTranslation>['t'],
) {
  if (status === 'matched') {
    return t('broadcast.import.statusLabels.matched');
  }
  if (status === 'unmatched') {
    return t('broadcast.import.statusLabels.unmatched');
  }
  if (status === 'conflict') {
    return t('broadcast.import.statusLabels.conflict');
  }
  return t('broadcast.import.statusLabels.invalid');
}

function renderRawRowSummary(row: BroadcastImportPreviewRow) {
  return Object.entries(row.rawData ?? {})
    .slice(0, 3)
    .map(([key, value]) => `${key}: ${value}`)
    .join(' / ');
}

export default function ImportMatchingPanel({
  batches,
  selectedBatchId,
  detail,
  groupsDetail,
  groupRowsByKey,
  templates,
  selectedBatchDraftCount = 0,
  loading = false,
  busy = false,
  confirmationBusy = false,
  error = null,
  onUpload,
  pendingImportConfirmation,
  onConfirmImportGroupField,
  onCancelImportGroupField,
  onSelectBatch,
  onPageChange,
  onDeleteBatch,
  onRematch,
  onGenerateDrafts,
  onNavigateToGroupMatching,
  onUpdateGroupTemplateAssignments,
  onLoadGroupRows,
  onUploadGroupAttachments,
  onDeleteGroupAttachment,
}: ImportMatchingPanelProps) {
  markBroadcastRender('ImportMatchingPanel');
  const { t } = useTranslation();
  const uploadRef = useRef<HTMLInputElement | null>(null);
  const attachmentInputRefs = useRef<Record<string, HTMLInputElement | null>>(
    {},
  );
  const [selectedGroupKeys, setSelectedGroupKeys] = useState<string[]>([]);
  const [bulkTemplateId, setBulkTemplateId] = useState<string>('');
  const [expandedGroupKeys, setExpandedGroupKeys] = useState<string[]>([]);
  const [assignmentBusy, setAssignmentBusy] = useState(false);
  const [clearSelectedDialogOpen, setClearSelectedDialogOpen] = useState(false);
  const [deleteBatchDialogOpen, setDeleteBatchDialogOpen] = useState(false);
  const [rematchDialogOpen, setRematchDialogOpen] = useState(false);
  const [generateDraftsDialogOpen, setGenerateDraftsDialogOpen] =
    useState(false);
  const [selectedGroupField, setSelectedGroupField] = useState('');

  const stats = useMemo(
    () => ({
      rawRowTotal: groupsDetail?.rawRowTotal ?? detail?.totalRows ?? 0,
      groupTotal: groupsDetail?.groupTotal ?? 0,
      matchedGroupTotal: groupsDetail?.matchedGroupTotal ?? 0,
      unmatchedGroupTotal: groupsDetail?.unmatchedGroupTotal ?? 0,
      invalidOrConflictTotal:
        (groupsDetail?.invalidGroupTotal ?? 0) +
        (groupsDetail?.conflictGroupTotal ?? 0),
    }),
    [detail?.totalRows, groupsDetail],
  );

  const enabledTemplates = useMemo(
    () => templates.filter((template) => template.enabled),
    [templates],
  );

  const pageGroups = groupsDetail?.groups ?? EMPTY_GROUPS;

  useEffect(() => {
    setSelectedGroupKeys([]);
    setExpandedGroupKeys([]);
    setBulkTemplateId('');
  }, [selectedBatchId, groupsDetail?.page]);

  useEffect(() => {
    const availableGroupKeys = new Set(
      pageGroups.map((group) => group.groupKey),
    );
    setSelectedGroupKeys((current) =>
      current.filter((groupKey) => availableGroupKeys.has(groupKey)),
    );
    setExpandedGroupKeys((current) =>
      current.filter((groupKey) => availableGroupKeys.has(groupKey)),
    );
  }, [pageGroups]);

  useEffect(() => {
    if (!pendingImportConfirmation) {
      setSelectedGroupField('');
      return;
    }
    const availableFields =
      pendingImportConfirmation.candidates.length > 0
        ? pendingImportConfirmation.candidates
        : pendingImportConfirmation.headers;
    setSelectedGroupField(
      availableFields.includes(selectedGroupField)
        ? selectedGroupField
        : (availableFields[0] ?? ''),
    );
  }, [pendingImportConfirmation, selectedGroupField]);

  const getConversationIdentity = (group: BroadcastImportGroupSummary) => {
    const conversationId = group.matchedConversationId?.trim();
    if (conversationId) {
      return `id:${conversationId}`;
    }
    const conversationName = group.matchedConversationName?.trim();
    return conversationName ? `name:${conversationName}` : null;
  };

  const getGroupSelectionDisabledReason = (
    group: BroadcastImportGroupSummary,
  ) => {
    if (group.matchStatus === 'invalid') {
      return group.reason || t('broadcast.import.selectionDisabled.invalid');
    }
    if (group.matchStatus === 'conflict') {
      return group.reason || t('broadcast.import.selectionDisabled.conflict');
    }
    return null;
  };

  const isGroupSelectable = (group: BroadcastImportGroupSummary) =>
    getGroupSelectionDisabledReason(group) == null;

  const selectableGroups = pageGroups.filter(
    (group) => getGroupSelectionDisabledReason(group) == null,
  );

  const selectedGroupsInPageOrder = useMemo(
    () =>
      selectableGroups.filter((group) =>
        selectedGroupKeys.includes(group.groupKey),
      ),
    [selectableGroups, selectedGroupKeys],
  );

  const selectedCount = selectedGroupsInPageOrder.length;
  const selectedBatch =
    batches.find((batch) => batch.id === selectedBatchId) ?? null;
  const duplicateConversationWarning = useMemo(() => {
    const mapping = new Map<string, string[]>();
    for (const group of selectedGroupsInPageOrder) {
      const identity = getConversationIdentity(group);
      if (!identity) {
        continue;
      }
      const current = mapping.get(identity) ?? [];
      current.push(group.groupValue);
      mapping.set(identity, current);
    }
    const duplicateCount = Array.from(mapping.values()).filter(
      (groups) => groups.length > 1,
    ).length;
    if (duplicateCount === 0) {
      return null;
    }
    return t('broadcast.import.generateWarnings.duplicateConversation');
  }, [selectedGroupsInPageOrder, t]);
  const allSelectableChecked =
    selectableGroups.length > 0 &&
    selectableGroups.every((group) =>
      selectedGroupKeys.includes(group.groupKey),
    );
  const someSelectableChecked =
    !allSelectableChecked && selectedGroupsInPageOrder.length > 0;

  const getTemplateOptions = (group: BroadcastImportGroupSummary) => {
    const currentTemplate =
      group.templateId != null
        ? (templates.find((template) => template.id === group.templateId) ??
          null)
        : null;
    if (
      currentTemplate &&
      !currentTemplate.enabled &&
      !enabledTemplates.some((template) => template.id === currentTemplate.id)
    ) {
      return [...enabledTemplates, currentTemplate];
    }
    return enabledTemplates;
  };

  const getTemplateLabel = (group: BroadcastImportGroupSummary) => {
    if (!group.templateId) {
      return null;
    }
    if (group.templateName?.trim()) {
      return group.templateEnabled === false
        ? `${group.templateName} (${t('broadcast.import.templateDisabledLabel')})`
        : group.templateName;
    }
    return String(group.templateId);
  };

  const bulkTemplateNumericId = bulkTemplateId ? Number(bulkTemplateId) : null;
  const selectedGroupsWithTemplate = selectedGroupsInPageOrder.filter(
    (group) => group.templateId != null,
  );
  const selectedGroupsWithoutTemplate = selectedGroupsInPageOrder.filter(
    (group) => group.templateId == null,
  );
  const selectedGroupsEligibleForApply = selectedGroupsInPageOrder.filter(
    (group) =>
      bulkTemplateNumericId != null &&
      group.templateId !== bulkTemplateNumericId,
  );
  const selectedGroupsBlockedForGeneration = selectedGroupsInPageOrder.filter(
    (group) =>
      group.matchStatus !== 'matched' || !group.matchedConversationName?.trim(),
  );

  const getGenerateDisabledReason = () => {
    if (!selectedBatchId) {
      return t('broadcast.import.generateDisabled.noBatch');
    }
    if (selectedCount === 0) {
      return t('broadcast.import.generateDisabled.noSelection');
    }
    if (selectedGroupsBlockedForGeneration.length > 0) {
      return t('broadcast.import.generateDisabled.matchUnavailable', {
        count: selectedGroupsBlockedForGeneration.length,
      });
    }
    const groupsWithoutTemplate = selectedGroupsInPageOrder.filter(
      (group) => !group.templateId,
    );
    if (groupsWithoutTemplate.length > 0) {
      return t('broadcast.import.generateDisabled.templateMissing', {
        count: groupsWithoutTemplate.length,
      });
    }
    const disabledTemplates = selectedGroupsInPageOrder.filter(
      (group) => group.templateId && group.templateEnabled === false,
    );
    if (disabledTemplates.length > 0) {
      return t('broadcast.import.generateDisabled.templateDisabled', {
        count: disabledTemplates.length,
      });
    }
    return null;
  };

  const getApplyTemplateDisabledReason = () => {
    if (!selectedBatchId) {
      return t('broadcast.import.applyTemplateDisabled.noBatch');
    }
    if (selectedCount === 0) {
      return t('broadcast.import.applyTemplateDisabled.noSelection');
    }
    if (!bulkTemplateId) {
      return t('broadcast.import.applyTemplateDisabled.noTemplate');
    }
    if (selectedGroupsEligibleForApply.length === 0) {
      return t('broadcast.import.applyTemplateDisabled.noProcessableSelection');
    }
    return null;
  };

  const getApplyUnassignedDisabledReason = () => {
    if (!selectedBatchId) {
      return t('broadcast.import.applyTemplateDisabled.noBatch');
    }
    if (selectedCount === 0) {
      return t('broadcast.import.applyTemplateDisabled.noSelection');
    }
    if (!bulkTemplateId) {
      return t('broadcast.import.applyTemplateDisabled.noTemplate');
    }
    if (selectedGroupsWithoutTemplate.length === 0) {
      return t('broadcast.import.applyTemplateDisabled.noUnassignedSelection');
    }
    return null;
  };

  const getClearTemplateDisabledReason = () => {
    if (!selectedBatchId) {
      return t('broadcast.import.clearTemplateDisabled.noBatch');
    }
    if (selectedCount === 0) {
      return t('broadcast.import.clearTemplateDisabled.noSelection');
    }
    if (selectedGroupsWithTemplate.length === 0) {
      return t('broadcast.import.clearTemplateDisabled.noAssignedSelection');
    }
    return null;
  };

  const generateDisabledReason = getGenerateDisabledReason();
  const applyTemplateDisabledReason = getApplyTemplateDisabledReason();
  const applyUnassignedDisabledReason = getApplyUnassignedDisabledReason();
  const clearTemplateDisabledReason = getClearTemplateDisabledReason();
  const mutateBusy = busy || assignmentBusy;

  const toggleGroup = async (groupKey: string) => {
    const isExpanded = expandedGroupKeys.includes(groupKey);
    if (isExpanded) {
      setExpandedGroupKeys((current) =>
        current.filter((item) => item !== groupKey),
      );
      return;
    }
    if (!groupRowsByKey[groupKey]) {
      await onLoadGroupRows(groupKey, 1);
    }
    setExpandedGroupKeys((current) => [...current, groupKey]);
  };

  const handleToggleSelection = (
    group: BroadcastImportGroupSummary,
    checked: boolean,
  ) => {
    if (!isGroupSelectable(group)) {
      return;
    }
    setSelectedGroupKeys((current) => {
      if (checked) {
        return current.includes(group.groupKey)
          ? current
          : [...current, group.groupKey];
      }
      return current.filter((item) => item !== group.groupKey);
    });
  };

  const handleSelectAllCurrentPage = (checked: boolean) => {
    if (!checked) {
      setSelectedGroupKeys([]);
      return;
    }
    setSelectedGroupKeys(selectableGroups.map((group) => group.groupKey));
  };

  const handleUpdateAssignments = async (
    items: Array<{ groupKey: string; templateId: number | null }>,
  ) => {
    if (!selectedBatchId || items.length === 0) {
      return false;
    }
    setAssignmentBusy(true);
    try {
      await onUpdateGroupTemplateAssignments(selectedBatchId, items);
      return true;
    } finally {
      setAssignmentBusy(false);
    }
  };

  const handleApplySelectedTemplates = async () => {
    if (bulkTemplateNumericId == null) {
      return;
    }
    const targetGroups = selectedGroupsInPageOrder.filter(
      (group) => group.templateId !== bulkTemplateNumericId,
    );
    const saved = await handleUpdateAssignments(
      targetGroups.map((group) => ({
        groupKey: group.groupKey,
        templateId: bulkTemplateNumericId,
      })),
    );
    if (!saved) {
      return;
    }
    const replacedCount = targetGroups.filter(
      (group) =>
        group.templateId != null && group.templateId !== bulkTemplateNumericId,
    ).length;
    toast.success(
      t('broadcast.toasts.groupTemplateAssignmentsApplied', {
        count: targetGroups.length,
        replacedCount,
      }),
    );
  };

  const handleApplyTemplatesToUnassigned = async () => {
    if (bulkTemplateNumericId == null) {
      return;
    }
    const saved = await handleUpdateAssignments(
      selectedGroupsWithoutTemplate.map((group) => ({
        groupKey: group.groupKey,
        templateId: bulkTemplateNumericId,
      })),
    );
    if (!saved) {
      return;
    }
    toast.success(
      t('broadcast.toasts.groupTemplateAssignmentsAppliedToUnassigned', {
        count: selectedGroupsWithoutTemplate.length,
      }),
    );
  };

  const handleClearRowTemplate = async (group: BroadcastImportGroupSummary) => {
    if (group.templateId == null) {
      return;
    }
    const saved = await handleUpdateAssignments([
      {
        groupKey: group.groupKey,
        templateId: null,
      },
    ]);
    if (!saved) {
      return;
    }
    toast.success(
      t('broadcast.toasts.groupTemplateAssignmentsCleared', {
        count: 1,
      }),
    );
  };

  const handleConfirmClearSelectedTemplates = async () => {
    const clearItems = selectedGroupsWithTemplate.map((group) => ({
      groupKey: group.groupKey,
      templateId: null,
    }));
    const saved = await handleUpdateAssignments(clearItems);
    if (!saved) {
      return;
    }
    setClearSelectedDialogOpen(false);
    toast.success(
      t('broadcast.toasts.groupTemplateAssignmentsCleared', {
        count: clearItems.length,
      }),
    );
  };

  return (
    <div className="grid gap-4 xl:grid-cols-[280px_minmax(0,1fr)]">
      <Card className="gap-4">
        <CardHeader>
          <CardTitle>{t('broadcast.import.title')}</CardTitle>
          <CardDescription>{t('broadcast.import.description')}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {error ? (
            <Alert variant="destructive">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          ) : null}
          <input
            ref={uploadRef}
            data-testid="broadcast-import-upload-input"
            type="file"
            accept=".csv,.xlsx"
            className="hidden"
            onChange={async (event) => {
              const file = event.target.files?.[0];
              if (!file) {
                return;
              }
              if (busy) {
                event.currentTarget.value = '';
                return;
              }
              const input = event.target;
              try {
                await onUpload(file);
              } finally {
                input.value = '';
              }
            }}
          />
          <Button
            data-testid="broadcast-import-upload-button"
            onClick={() => uploadRef.current?.click()}
            disabled={busy}
          >
            {t('broadcast.import.uploadButton')}
          </Button>

          <div data-testid="broadcast-import-batch-list" className="space-y-2">
            {batches.map((batch) => {
              const active = batch.id === selectedBatchId;
              return (
                <button
                  key={batch.id}
                  type="button"
                  className={`w-full rounded-lg border p-3 text-left ${
                    active ? 'border-blue-500 bg-blue-50' : 'bg-background'
                  }`}
                  disabled={busy}
                  onClick={() => void onSelectBatch(batch.id)}
                >
                  <div className="font-medium">{batch.originalFileName}</div>
                  <div
                    className="mt-1 text-xs text-muted-foreground"
                    data-testid={`broadcast-import-batch-summary-${batch.id}`}
                  >
                    {t('broadcast.import.batchSummary', {
                      totalRows: batch.totalRows,
                      matchedRows: batch.matchedRows,
                    })}
                  </div>
                </button>
              );
            })}
            {!loading && batches.length === 0 ? (
              <div className="rounded-lg border border-dashed p-4 text-sm text-muted-foreground">
                {t('broadcast.import.emptyBatches')}
              </div>
            ) : null}
          </div>
        </CardContent>
      </Card>

      <Card className="gap-4">
        <CardHeader>
          <CardTitle>
            {detail?.originalFileName || t('broadcast.import.detailTitle')}
          </CardTitle>
          <CardDescription>
            <div>{t('broadcast.import.detailHint')}</div>
            {detail?.groupFieldUsed ? (
              <div className="mt-1 text-emerald-700">
                {t('broadcast.import.groupFieldDetected', {
                  field: detail.groupFieldUsed,
                })}
              </div>
            ) : null}
            {detail?.worksheetName ? (
              <div
                className="mt-1"
                data-testid="broadcast-import-worksheet-name"
              >
                {t('broadcast.import.worksheetName', {
                  name: detail.worksheetName,
                })}
              </div>
            ) : null}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-3 md:grid-cols-5">
            <div className="rounded-xl border bg-muted/20 p-4">
              <div className="text-sm text-muted-foreground">
                {t('broadcast.import.stats.totalRows')}
              </div>
              <div className="mt-2 text-2xl font-semibold">
                {stats.rawRowTotal}
              </div>
            </div>
            <div className="rounded-xl border bg-muted/20 p-4">
              <div className="text-sm text-muted-foreground">
                {t('broadcast.import.stats.totalGroups')}
              </div>
              <div className="mt-2 text-2xl font-semibold">
                {stats.groupTotal}
              </div>
            </div>
            <div className="rounded-xl border bg-muted/20 p-4">
              <div className="text-sm text-muted-foreground">
                {t('broadcast.import.stats.matchedGroups')}
              </div>
              <div className="mt-2 text-2xl font-semibold">
                {stats.matchedGroupTotal}
              </div>
            </div>
            <div className="rounded-xl border bg-muted/20 p-4">
              <div className="text-sm text-muted-foreground">
                {t('broadcast.import.stats.unmatchedGroups')}
              </div>
              <div className="mt-2 text-2xl font-semibold">
                {stats.unmatchedGroupTotal}
              </div>
            </div>
            <div className="rounded-xl border bg-muted/20 p-4">
              <div className="text-sm text-muted-foreground">
                {t('broadcast.import.stats.invalidGroups')}
              </div>
              <div className="mt-2 text-2xl font-semibold">
                {stats.invalidOrConflictTotal}
              </div>
            </div>
          </div>

          <div
            className="sticky top-0 z-10 flex flex-wrap items-start gap-2 rounded-xl border bg-background/95 p-3 backdrop-blur supports-[backdrop-filter]:bg-background/80"
            data-testid="broadcast-import-sticky-actions"
          >
            <Button
              data-testid="broadcast-import-rematch-button"
              variant="outline"
              disabled={!selectedBatchId || busy}
              onClick={() => setRematchDialogOpen(true)}
            >
              {t('broadcast.import.rematchButton')}
            </Button>
            <Button
              data-testid="broadcast-import-delete-batch-button"
              variant="outline"
              disabled={!selectedBatchId || busy}
              onClick={() => setDeleteBatchDialogOpen(true)}
            >
              {t('broadcast.import.deleteBatchButton')}
            </Button>
            <select
              data-testid="broadcast-import-template-select"
              className="border-input bg-background h-9 w-[240px] rounded-md border px-3 py-2 text-sm"
              value={bulkTemplateId}
              onChange={(event) => setBulkTemplateId(event.target.value)}
            >
              <option value="">
                {t('broadcast.import.bulkTemplatePlaceholder')}
              </option>
              {enabledTemplates.map((template) => (
                <option key={template.id} value={String(template.id)}>
                  {template.name}
                </option>
              ))}
            </select>
            <Button
              data-testid="broadcast-import-apply-template-button"
              variant="outline"
              disabled={mutateBusy || Boolean(applyTemplateDisabledReason)}
              title={applyTemplateDisabledReason ?? undefined}
              onClick={() => void handleApplySelectedTemplates()}
            >
              {t('broadcast.import.applyTemplateButton')}
            </Button>
            <Button
              data-testid="broadcast-import-apply-template-unassigned-button"
              variant="outline"
              disabled={mutateBusy || Boolean(applyUnassignedDisabledReason)}
              title={applyUnassignedDisabledReason ?? undefined}
              onClick={() => void handleApplyTemplatesToUnassigned()}
            >
              {t('broadcast.import.applyTemplateToUnassignedButton')}
            </Button>
            <Button
              data-testid="broadcast-import-clear-templates-button"
              variant="outline"
              disabled={mutateBusy || Boolean(clearTemplateDisabledReason)}
              title={clearTemplateDisabledReason ?? undefined}
              onClick={() => setClearSelectedDialogOpen(true)}
            >
              {t('broadcast.import.clearTemplatesButton')}
            </Button>
            <Button
              data-testid="broadcast-import-generate-drafts-button"
              disabled={busy || Boolean(generateDisabledReason)}
              title={generateDisabledReason ?? undefined}
              onClick={() => setGenerateDraftsDialogOpen(true)}
            >
              {t('broadcast.import.generateDraftsButton')}
            </Button>
          </div>

          <div className="flex flex-wrap items-center gap-3 text-sm">
            <div
              className="font-medium"
              data-testid="broadcast-import-selected-count"
            >
              {t('broadcast.import.selectedGroupCount', {
                count: selectedCount,
              })}
            </div>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              disabled={selectedCount === 0}
              onClick={() => setSelectedGroupKeys([])}
            >
              {t('broadcast.import.clearSelection')}
            </Button>
          </div>
          {duplicateConversationWarning ? (
            <div
              className="rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-800"
              data-testid="broadcast-import-duplicate-warning"
            >
              {duplicateConversationWarning}
            </div>
          ) : null}

          {detail?.draftsStale && detail.status === 'matched' ? (
            <div className="rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-800">
              {t('broadcast.import.draftsStale')}
            </div>
          ) : null}

          <div data-testid="broadcast-import-table">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-[56px]">
                    <Checkbox
                      aria-label={t('broadcast.import.tableHeaders.selection')}
                      data-testid="broadcast-import-select-all-checkbox"
                      checked={
                        allSelectableChecked
                          ? true
                          : someSelectableChecked
                            ? 'indeterminate'
                            : false
                      }
                      disabled={mutateBusy || selectableGroups.length === 0}
                      onCheckedChange={(checked) =>
                        handleSelectAllCurrentPage(Boolean(checked))
                      }
                    />
                  </TableHead>
                  <TableHead>
                    {t('broadcast.import.tableHeaders.groupValue')}
                  </TableHead>
                  <TableHead>
                    {t('broadcast.import.tableHeaders.orderCount')}
                  </TableHead>
                  <TableHead>
                    {t('broadcast.import.tableHeaders.messageTemplate')}
                  </TableHead>
                  <TableHead>
                    {t('broadcast.import.tableHeaders.matchedConversationName')}
                  </TableHead>
                  <TableHead>
                    {t('broadcast.import.tableHeaders.matchStatus')}
                  </TableHead>
                  <TableHead>
                    {t('broadcast.import.tableHeaders.attachments')}
                  </TableHead>
                  <TableHead>
                    {t('broadcast.import.tableHeaders.errorMessage')}
                  </TableHead>
                  <TableHead className="w-[120px] text-right">
                    {t('broadcast.import.tableHeaders.actions')}
                  </TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {pageGroups.map((group) => {
                  const expanded = expandedGroupKeys.includes(group.groupKey);
                  const groupRows = groupRowsByKey[group.groupKey];
                  const attachments = group.attachments ?? EMPTY_ATTACHMENTS;
                  const selectionDisabledReason =
                    getGroupSelectionDisabledReason(group);
                  const rowTemplateOptions = getTemplateOptions(group);
                  const rowTemplateLabel = getTemplateLabel(group);
                  const rowTemplateDisabled =
                    mutateBusy || !isGroupSelectable(group);
                  return (
                    <Fragment key={group.groupKey}>
                      <TableRow key={group.groupKey}>
                        <TableCell className="align-top">
                          <Checkbox
                            aria-label={t('broadcast.import.selectGroupAria', {
                              name: group.groupValue,
                            })}
                            data-testid={`broadcast-import-group-checkbox-${group.groupKey}`}
                            checked={selectedGroupKeys.includes(group.groupKey)}
                            disabled={rowTemplateDisabled}
                            onCheckedChange={(checked) =>
                              handleToggleSelection(group, Boolean(checked))
                            }
                          />
                        </TableCell>
                        <TableCell className="align-top">
                          <div className="font-medium">{group.groupValue}</div>
                          <div className="text-xs text-muted-foreground">
                            {t('broadcast.import.rawRowCountInline', {
                              count: group.rawRowCount,
                            })}
                          </div>
                        </TableCell>
                        <TableCell className="align-top">
                          {group.distinctOrderNumberCount}
                        </TableCell>
                        <TableCell className="align-top">
                          <div className="space-y-2">
                            <select
                              className="border-input bg-background h-9 w-[220px] rounded-md border px-3 py-2 text-sm"
                              data-testid={`broadcast-import-group-template-select-${group.groupKey}`}
                              value={
                                group.templateId != null
                                  ? String(group.templateId)
                                  : UNASSIGNED_TEMPLATE_OPTION
                              }
                              disabled={rowTemplateDisabled}
                              onChange={(event) => {
                                const nextTemplateId = Number(
                                  event.target.value,
                                );
                                if (!Number.isFinite(nextTemplateId)) {
                                  return;
                                }
                                void handleUpdateAssignments([
                                  {
                                    groupKey: group.groupKey,
                                    templateId: nextTemplateId,
                                  },
                                ]).then((saved) => {
                                  if (!saved) {
                                    return;
                                  }
                                  toast.success(
                                    t(
                                      'broadcast.toasts.groupTemplateAssignmentsApplied',
                                      {
                                        count: 1,
                                        replacedCount:
                                          group.templateId != null &&
                                          group.templateId !== nextTemplateId
                                            ? 1
                                            : 0,
                                      },
                                    ),
                                  );
                                });
                              }}
                            >
                              <option
                                value={UNASSIGNED_TEMPLATE_OPTION}
                                disabled
                              >
                                {t('broadcast.import.templatePlaceholder')}
                              </option>
                              {rowTemplateOptions.map((template) => (
                                <option
                                  key={template.id}
                                  value={String(template.id)}
                                >
                                  {template.enabled
                                    ? template.name
                                    : `${template.name} (${t('broadcast.import.templateDisabledLabel')})`}
                                </option>
                              ))}
                            </select>
                            {rowTemplateLabel &&
                            group.templateEnabled === false ? (
                              <div className="text-xs text-amber-700">
                                {rowTemplateLabel}
                              </div>
                            ) : null}
                            <Button
                              size="sm"
                              variant="ghost"
                              data-testid={`broadcast-import-group-clear-template-button-${group.groupKey}`}
                              disabled={mutateBusy || group.templateId == null}
                              onClick={() => void handleClearRowTemplate(group)}
                            >
                              {t('broadcast.import.clearRowTemplateButton')}
                            </Button>
                          </div>
                        </TableCell>
                        <TableCell className="align-top">
                          {group.matchedConversationName || '-'}
                        </TableCell>
                        <TableCell className="align-top">
                          <Badge variant="outline">
                            {renderMatchStatusLabel(group.matchStatus, t)}
                          </Badge>
                        </TableCell>
                        <TableCell className="align-top">
                          <Badge variant="secondary">
                            {attachments.length || group.attachmentCount}
                          </Badge>
                        </TableCell>
                        <TableCell className="max-w-[260px] align-top text-sm text-muted-foreground">
                          {selectionDisabledReason || group.reason || '-'}
                        </TableCell>
                        <TableCell className="text-right align-top">
                          <div className="flex flex-col items-end gap-2">
                            {group.matchStatus === 'unmatched' ? (
                              <Button
                                size="sm"
                                variant="outline"
                                data-testid={`broadcast-import-group-go-to-group-matching-button-${group.groupKey}`}
                                disabled={mutateBusy}
                                onClick={onNavigateToGroupMatching}
                              >
                                {t('broadcast.import.goToGroupMatching')}
                              </Button>
                            ) : null}
                            <Button
                              size="sm"
                              variant="outline"
                              disabled={busy}
                              onClick={() => void toggleGroup(group.groupKey)}
                            >
                              {expanded
                                ? t('broadcast.import.collapseGroup')
                                : t('broadcast.import.expandGroup')}
                            </Button>
                          </div>
                        </TableCell>
                      </TableRow>
                      {expanded ? (
                        <TableRow>
                          <TableCell colSpan={9} className="bg-muted/10">
                            <div className="space-y-4 py-2">
                              <div className="flex flex-wrap items-center justify-between gap-2">
                                <div className="text-sm font-medium">
                                  {t('broadcast.import.groupAttachments')}
                                </div>
                                <div className="flex items-center gap-2">
                                  <input
                                    ref={(node) => {
                                      attachmentInputRefs.current[
                                        group.groupKey
                                      ] = node;
                                    }}
                                    type="file"
                                    accept=".pdf,.xlsx,application/pdf,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                                    multiple
                                    className="hidden"
                                    onChange={async (event) => {
                                      const files = Array.from(
                                        event.target.files ?? [],
                                      );
                                      if (files.length === 0) {
                                        return;
                                      }
                                      try {
                                        await onUploadGroupAttachments(
                                          group.groupKey,
                                          files,
                                        );
                                      } finally {
                                        event.target.value = '';
                                      }
                                    }}
                                  />
                                  <Button
                                    size="sm"
                                    variant="outline"
                                    disabled={busy}
                                    onClick={() =>
                                      attachmentInputRefs.current[
                                        group.groupKey
                                      ]?.click()
                                    }
                                  >
                                    {t('broadcast.import.uploadAttachment')}
                                  </Button>
                                </div>
                              </div>

                              {attachments.length > 0 ? (
                                <div className="flex flex-wrap gap-2">
                                  {attachments.map((attachment) => (
                                    <div
                                      key={attachment.id}
                                      className="flex items-center gap-2 rounded-lg border bg-background px-3 py-2 text-sm"
                                    >
                                      <span>{attachment.originalName}</span>
                                      <Button
                                        size="sm"
                                        variant="ghost"
                                        disabled={busy}
                                        onClick={() =>
                                          void onDeleteGroupAttachment(
                                            group.groupKey,
                                            attachment.id,
                                          )
                                        }
                                      >
                                        {t('broadcast.import.deleteAttachment')}
                                      </Button>
                                    </div>
                                  ))}
                                </div>
                              ) : (
                                <div className="text-sm text-muted-foreground">
                                  {t('broadcast.import.emptyAttachments')}
                                </div>
                              )}

                              <div className="space-y-2">
                                <div className="text-sm font-medium">
                                  {t('broadcast.import.groupRowsTitle')}
                                </div>
                                <div className="rounded-lg border bg-background">
                                  <Table>
                                    <TableHeader>
                                      <TableRow>
                                        <TableHead>
                                          {t(
                                            'broadcast.import.tableHeaders.sourceRowNumber',
                                          )}
                                        </TableHead>
                                        <TableHead>
                                          {t(
                                            'broadcast.import.tableHeaders.matchStatus',
                                          )}
                                        </TableHead>
                                        <TableHead>
                                          {t(
                                            'broadcast.import.tableHeaders.matchedConversationName',
                                          )}
                                        </TableHead>
                                        <TableHead>
                                          {t(
                                            'broadcast.import.tableHeaders.errorMessage',
                                          )}
                                        </TableHead>
                                        <TableHead>
                                          {t(
                                            'broadcast.import.tableHeaders.rowPreview',
                                          )}
                                        </TableHead>
                                      </TableRow>
                                    </TableHeader>
                                    <TableBody>
                                      {(groupRows?.rows ?? []).map((row) => (
                                        <TableRow
                                          key={`${group.groupKey}-${row.id}`}
                                        >
                                          <TableCell>
                                            {row.sourceRowNumber}
                                          </TableCell>
                                          <TableCell>
                                            <Badge variant="outline">
                                              {renderMatchStatusLabel(
                                                row.matchStatus,
                                                t,
                                              )}
                                            </Badge>
                                          </TableCell>
                                          <TableCell>
                                            {row.matchedConversationName || '-'}
                                          </TableCell>
                                          <TableCell>
                                            {row.errorMessage || '-'}
                                          </TableCell>
                                          <TableCell className="max-w-[420px] truncate text-muted-foreground">
                                            {renderRawRowSummary(row)}
                                          </TableCell>
                                        </TableRow>
                                      ))}
                                      {(groupRows?.rows.length ?? 0) === 0 ? (
                                        <TableRow>
                                          <TableCell
                                            colSpan={5}
                                            className="text-center text-muted-foreground"
                                          >
                                            {t('broadcast.import.emptyRows')}
                                          </TableCell>
                                        </TableRow>
                                      ) : null}
                                    </TableBody>
                                  </Table>
                                </div>

                                <div className="flex items-center justify-between text-sm">
                                  <div className="text-muted-foreground">
                                    {t('broadcast.import.groupRowsTotal', {
                                      total: groupRows?.total ?? 0,
                                    })}
                                  </div>
                                  <div className="flex items-center gap-2">
                                    <Button
                                      size="sm"
                                      variant="outline"
                                      disabled={
                                        busy ||
                                        !groupRows ||
                                        groupRows.page <= 1
                                      }
                                      onClick={() =>
                                        void onLoadGroupRows(
                                          group.groupKey,
                                          (groupRows?.page ?? 1) - 1,
                                        )
                                      }
                                    >
                                      {t(
                                        'broadcast.import.pagination.previous',
                                      )}
                                    </Button>
                                    <span className="text-muted-foreground">
                                      {t(
                                        'broadcast.import.pagination.pageStatus',
                                        {
                                          page: groupRows?.page ?? 0,
                                          totalPages:
                                            groupRows?.totalPages ?? 0,
                                        },
                                      )}
                                    </span>
                                    <Button
                                      size="sm"
                                      variant="outline"
                                      disabled={
                                        busy ||
                                        !groupRows ||
                                        groupRows.totalPages === 0 ||
                                        groupRows.page >= groupRows.totalPages
                                      }
                                      onClick={() =>
                                        void onLoadGroupRows(
                                          group.groupKey,
                                          (groupRows?.page ?? 1) + 1,
                                        )
                                      }
                                    >
                                      {t('broadcast.import.pagination.next')}
                                    </Button>
                                  </div>
                                </div>
                              </div>
                            </div>
                          </TableCell>
                        </TableRow>
                      ) : null}
                    </Fragment>
                  );
                })}
                {pageGroups.length === 0 ? (
                  <TableRow>
                    <TableCell
                      colSpan={9}
                      className="text-center text-muted-foreground"
                    >
                      {t('broadcast.import.emptyRows')}
                    </TableCell>
                  </TableRow>
                ) : null}
              </TableBody>
            </Table>
          </div>

          <div className="flex items-center justify-between gap-3 text-sm">
            <div
              className="text-muted-foreground"
              data-testid="broadcast-import-total-items"
            >
              {t('broadcast.import.pagination.totalItems', {
                total: groupsDetail?.total ?? 0,
              })}
            </div>
            <div className="flex items-center gap-3">
              <Button
                data-testid="broadcast-import-prev-page"
                variant="outline"
                size="sm"
                disabled={
                  loading || busy || !groupsDetail || groupsDetail.page <= 1
                }
                onClick={() => {
                  if (!groupsDetail) {
                    return;
                  }
                  void onPageChange(groupsDetail.page - 1);
                }}
              >
                {t('broadcast.import.pagination.previous')}
              </Button>
              <span data-testid="broadcast-import-pagination">
                {t('broadcast.import.pagination.pageStatus', {
                  page: groupsDetail?.page ?? 0,
                  totalPages: groupsDetail?.totalPages ?? 0,
                })}
              </span>
              <Button
                data-testid="broadcast-import-next-page"
                variant="outline"
                size="sm"
                disabled={
                  loading ||
                  busy ||
                  !groupsDetail ||
                  groupsDetail.totalPages === 0 ||
                  groupsDetail.page >= groupsDetail.totalPages
                }
                onClick={() => {
                  if (!groupsDetail) {
                    return;
                  }
                  void onPageChange(groupsDetail.page + 1);
                }}
              >
                {t('broadcast.import.pagination.next')}
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>
      <AlertDialog
        open={deleteBatchDialogOpen}
        onOpenChange={setDeleteBatchDialogOpen}
      >
        <AlertDialogContent data-testid="broadcast-import-delete-batch-confirm-dialog">
          <AlertDialogHeader>
            <AlertDialogTitle>
              {t('broadcast.import.deleteBatchConfirmTitle')}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {t('broadcast.import.deleteBatchConfirmDescription', {
                fileName: selectedBatch?.originalFileName ?? '',
                totalRows: selectedBatch?.totalRows ?? 0,
                groupCount: groupsDetail?.groupTotal ?? 0,
                draftCount: selectedBatchDraftCount,
              })}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('common.cancel')}</AlertDialogCancel>
            <AlertDialogAction
              data-testid="broadcast-import-delete-batch-confirm-button"
              onClick={(event) => {
                event.preventDefault();
                if (!selectedBatchId) {
                  return;
                }
                void onDeleteBatch(selectedBatchId);
                setDeleteBatchDialogOpen(false);
              }}
            >
              {t('broadcast.import.deleteBatchButton')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
      <AlertDialog open={rematchDialogOpen} onOpenChange={setRematchDialogOpen}>
        <AlertDialogContent data-testid="broadcast-import-rematch-confirm-dialog">
          <AlertDialogHeader>
            <AlertDialogTitle>
              {t('broadcast.import.rematchConfirmTitle')}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {t('broadcast.import.rematchConfirmDescription')}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel data-testid="broadcast-import-rematch-cancel-button">
              {t('common.cancel')}
            </AlertDialogCancel>
            <AlertDialogAction
              data-testid="broadcast-import-rematch-confirm-button"
              onClick={(event) => {
                event.preventDefault();
                if (!selectedBatchId) {
                  return;
                }
                void onRematch(selectedBatchId);
                setRematchDialogOpen(false);
              }}
            >
              {t('broadcast.import.rematchButton')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
      <AlertDialog
        open={generateDraftsDialogOpen}
        onOpenChange={setGenerateDraftsDialogOpen}
      >
        <AlertDialogContent data-testid="broadcast-import-generate-drafts-confirm-dialog">
          <AlertDialogHeader>
            <AlertDialogTitle>
              {t('broadcast.import.generateDraftsConfirmTitle')}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {t('broadcast.import.generateDraftsConfirmDescription', {
                selectedCount,
                templatedCount: selectedGroupsInPageOrder.filter(
                  (group) => group.templateId != null,
                ).length,
                blockedCount: selectedGroupsBlockedForGeneration.length,
              })}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('common.cancel')}</AlertDialogCancel>
            <AlertDialogAction
              data-testid="broadcast-import-generate-drafts-confirm-button"
              onClick={(event) => {
                event.preventDefault();
                if (!selectedBatchId) {
                  return;
                }
                void onGenerateDrafts(
                  selectedBatchId,
                  selectedGroupsInPageOrder.map((group) => group.groupKey),
                );
                setGenerateDraftsDialogOpen(false);
              }}
            >
              {t('broadcast.import.generateDraftsButton')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
      <AlertDialog
        open={clearSelectedDialogOpen}
        onOpenChange={setClearSelectedDialogOpen}
      >
        <AlertDialogContent data-testid="broadcast-import-clear-templates-confirm-dialog">
          <AlertDialogHeader>
            <AlertDialogTitle>
              {t('broadcast.import.clearTemplatesConfirmTitle')}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {t('broadcast.import.clearTemplatesConfirmDescription', {
                count: selectedGroupsWithTemplate.length,
              })}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel data-testid="broadcast-import-clear-templates-cancel-button">
              {t('common.cancel')}
            </AlertDialogCancel>
            <AlertDialogAction
              data-testid="broadcast-import-clear-templates-confirm-button"
              onClick={(event) => {
                event.preventDefault();
                void handleConfirmClearSelectedTemplates();
              }}
            >
              {t('broadcast.import.clearTemplatesConfirmButton')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <Dialog
        open={pendingImportConfirmation != null}
        onOpenChange={(open) => {
          if (!open) {
            onCancelImportGroupField();
          }
        }}
      >
        <DialogContent data-testid="broadcast-import-group-field-dialog">
          <DialogHeader>
            <DialogTitle>
              {t('broadcast.import.groupFieldDialog.title')}
            </DialogTitle>
            <DialogDescription>
              {t('broadcast.import.groupFieldDialog.description', {
                fileName: pendingImportConfirmation?.originalFileName ?? '',
              })}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            {pendingImportConfirmation?.configuredGroupField ? (
              <div className="text-sm text-muted-foreground">
                {t('broadcast.import.groupFieldDialog.configuredField', {
                  field: pendingImportConfirmation.configuredGroupField,
                })}
              </div>
            ) : null}
            <div className="space-y-2">
              <div className="text-sm font-medium">
                {t('broadcast.import.groupFieldDialog.selectLabel')}
              </div>
              <select
                className="border-input bg-background h-9 w-full rounded-md border px-3 py-2 text-sm"
                value={selectedGroupField}
                disabled={confirmationBusy}
                onChange={(event) => setSelectedGroupField(event.target.value)}
              >
                {(pendingImportConfirmation?.candidates.length
                  ? pendingImportConfirmation.candidates
                  : (pendingImportConfirmation?.headers ?? [])
                ).map((header) => (
                  <option key={header} value={header}>
                    {header}
                  </option>
                ))}
              </select>
            </div>
            <div className="space-y-2">
              <div className="text-sm font-medium">
                {t('broadcast.import.groupFieldDialog.headersLabel')}
              </div>
              <div className="flex flex-wrap gap-2">
                {(pendingImportConfirmation?.headers ?? []).map((header) => (
                  <Badge key={header} variant="outline">
                    {header}
                  </Badge>
                ))}
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={onCancelImportGroupField}
            >
              {t('common.cancel')}
            </Button>
            <Button
              type="button"
              disabled={confirmationBusy || !selectedGroupField}
              onClick={() => void onConfirmImportGroupField(selectedGroupField)}
            >
              {t('broadcast.import.groupFieldDialog.confirmButton')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
