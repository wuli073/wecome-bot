import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

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
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Checkbox } from '@/components/ui/checkbox';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';

import type {
  BroadcastDraft,
  BroadcastImportBatch,
  BroadcastStatusFilter,
} from '../../types';

interface DraftQueueProps {
  drafts: Array<{
    status: 'pending' | 'unknown' | 'sent';
    drafts: BroadcastDraft[];
  }>;
  importBatches: BroadcastImportBatch[];
  selectedImportId: number | null;
  searchTerm: string;
  statusFilter: BroadcastStatusFilter;
  selectedDraftId: number | null;
  selectedDraftIds: number[];
  busy?: boolean;
  canBatchWrite?: boolean;
  batchWriteDisabledReason?: string | null;
  canBatchSend?: boolean;
  batchSendDisabledReason?: string | null;
  canBatchMarkSent?: boolean;
  canBatchRestorePending?: boolean;
  onImportBatchChange: (importBatchId: number | null) => void;
  onSearchTermChange: (value: string) => void;
  onStatusFilterChange: (value: BroadcastStatusFilter) => void;
  onSelectDraft: (draftId: number) => void;
  onToggleDraftSelection: (draftId: number, checked: boolean) => void;
  onBatchWrite: () => void;
  onBatchSend: () => void;
  onBatchMarkSent: () => void;
  onBatchRestorePending: () => void;
}

function getStatusLabel(
  status: 'pending' | 'unknown' | 'sent',
  t: ReturnType<typeof useTranslation>['t'],
) {
  if (status === 'unknown') {
    return t('broadcast.drafts.statusUnknown');
  }
  return status === 'sent'
    ? t('broadcast.drafts.statusSent')
    : t('broadcast.drafts.statusPending');
}

export default function DraftQueue({
  drafts,
  importBatches,
  selectedImportId,
  searchTerm,
  statusFilter,
  selectedDraftId,
  selectedDraftIds,
  busy = false,
  canBatchWrite = false,
  batchWriteDisabledReason = null,
  canBatchSend = false,
  batchSendDisabledReason = null,
  canBatchMarkSent = false,
  canBatchRestorePending = false,
  onImportBatchChange,
  onSearchTermChange,
  onStatusFilterChange,
  onSelectDraft,
  onToggleDraftSelection,
  onBatchWrite,
  onBatchSend,
  onBatchMarkSent,
  onBatchRestorePending,
}: DraftQueueProps) {
  const { t } = useTranslation();
  const [batchWriteDialogOpen, setBatchWriteDialogOpen] = useState(false);
  const [batchSendDialogOpen, setBatchSendDialogOpen] = useState(false);
  const [
    batchRestorePendingRiskDialogOpen,
    setBatchRestorePendingRiskDialogOpen,
  ] = useState(false);

  const selectableDraftIds = useMemo(
    () => drafts.flatMap((group) => group.drafts).map((draft) => draft.id),
    [drafts],
  );
  const selectedDrafts = useMemo(
    () =>
      drafts
        .flatMap((group) => group.drafts)
        .filter((draft) => selectedDraftIds.includes(draft.id)),
    [drafts, selectedDraftIds],
  );

  const selectedCount = selectedDraftIds.filter((draftId) =>
    selectableDraftIds.includes(draftId),
  ).length;
  const selectedConversationCount = new Set(
    selectedDrafts
      .map((draft) => draft.conversationName.trim())
      .filter((name) => name.length > 0),
  ).size;
  const selectedAttachmentCount = selectedDrafts.reduce(
    (total, draft) => total + (draft.attachments?.length ?? 0),
    0,
  );
  const selectedDuplicateConversationCount = Math.max(
    0,
    selectedDrafts.length - selectedConversationCount,
  );
  const selectedUnknownOnly =
    selectedDrafts.length > 0 &&
    selectedDrafts.every((draft) => draft.status === 'unknown');

  const allSelectableChecked =
    selectableDraftIds.length > 0 &&
    selectableDraftIds.every((draftId) => selectedDraftIds.includes(draftId));

  return (
    <Card className="min-h-0 gap-4" data-testid="broadcast-draft-queue">
      <CardHeader>
        <CardTitle>{t('broadcast.drafts.title')}</CardTitle>
        <CardDescription>{t('broadcast.drafts.description')}</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <div className="grid gap-3">
          <Select
            value={selectedImportId != null ? String(selectedImportId) : 'all'}
            onValueChange={(value) =>
              onImportBatchChange(value === 'all' ? null : Number(value))
            }
          >
            <SelectTrigger
              aria-label={t('broadcast.drafts.batchFilter')}
              data-testid="broadcast-draft-batch-filter"
            >
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">
                {t('broadcast.drafts.allBatches')}
              </SelectItem>
              {importBatches.map((batch) => (
                <SelectItem key={batch.id} value={String(batch.id)}>
                  {batch.originalFileName}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Input
            aria-label={t('broadcast.drafts.search')}
            placeholder={t('broadcast.drafts.searchPlaceholder')}
            value={searchTerm}
            onChange={(event) => onSearchTermChange(event.target.value)}
          />
          <Select
            value={statusFilter}
            onValueChange={(value) =>
              onStatusFilterChange(value as BroadcastStatusFilter)
            }
          >
            <SelectTrigger aria-label={t('broadcast.drafts.statusFilter')}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">
                {t('broadcast.drafts.allStatuses')}
              </SelectItem>
              <SelectItem value="pending">
                {t('broadcast.drafts.statusPending')}
              </SelectItem>
              <SelectItem value="unknown">
                {t('broadcast.drafts.statusUnknown')}
              </SelectItem>
              <SelectItem value="sent">
                {t('broadcast.drafts.statusSent')}
              </SelectItem>
            </SelectContent>
          </Select>
        </div>

        <div
          className="sticky top-0 z-10 rounded-xl border bg-background/95 p-4 backdrop-blur supports-[backdrop-filter]:bg-background/80"
          data-testid="broadcast-draft-sticky-actions"
        >
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="space-y-2">
              <div className="flex items-center gap-2">
                <Checkbox
                  aria-label={t('broadcast.drafts.selectAllEligible')}
                  checked={allSelectableChecked}
                  disabled={selectableDraftIds.length === 0 || busy}
                  data-testid="broadcast-draft-select-all-checkbox"
                  onCheckedChange={(checked) => {
                    for (const draftId of selectableDraftIds) {
                      onToggleDraftSelection(draftId, Boolean(checked));
                    }
                  }}
                />
                <div>
                  <div className="text-sm font-medium">
                    {t('broadcast.drafts.batchToolbar')}
                  </div>
                  <div className="text-xs text-muted-foreground">
                    {t('broadcast.drafts.selectedCount', {
                      count: selectedCount,
                    })}
                  </div>
                </div>
              </div>
            </div>
            <div className="flex flex-wrap gap-2">
              <div className="space-y-1">
                <Button
                  data-testid="broadcast-draft-batch-write-button"
                  onClick={() => setBatchWriteDialogOpen(true)}
                  disabled={selectedCount === 0 || busy || !canBatchWrite}
                  title={
                    !canBatchWrite && batchWriteDisabledReason
                      ? batchWriteDisabledReason
                      : undefined
                  }
                >
                  {t('broadcast.drafts.batchWriteSelected')}
                </Button>
                {!canBatchWrite && batchWriteDisabledReason ? (
                  <div className="text-xs text-muted-foreground">
                    {batchWriteDisabledReason}
                  </div>
                ) : null}
              </div>
              <div className="space-y-1">
                <Button
                  data-testid="broadcast-draft-batch-send-button"
                  variant="destructive"
                  onClick={() => setBatchSendDialogOpen(true)}
                  disabled={selectedCount === 0 || busy || !canBatchSend}
                  title={
                    !canBatchSend && batchSendDisabledReason
                      ? batchSendDisabledReason
                      : undefined
                  }
                >
                  {t('broadcast.drafts.batchSendSelected')}
                </Button>
                {!canBatchSend && batchSendDisabledReason ? (
                  <div className="text-xs text-muted-foreground">
                    {batchSendDisabledReason}
                  </div>
                ) : null}
              </div>
              <Button
                data-testid="broadcast-draft-batch-mark-sent-button"
                variant="outline"
                onClick={onBatchMarkSent}
                disabled={selectedCount === 0 || busy || !canBatchMarkSent}
              >
                {t('broadcast.drafts.markSent')}
              </Button>
              <Button
                data-testid="broadcast-draft-batch-restore-pending-button"
                variant="outline"
                onClick={() => {
                  if (selectedUnknownOnly) {
                    setBatchRestorePendingRiskDialogOpen(true);
                    return;
                  }
                  onBatchRestorePending();
                }}
                disabled={
                  selectedCount === 0 || busy || !canBatchRestorePending
                }
              >
                {t('broadcast.drafts.restorePending')}
              </Button>
            </div>
          </div>
        </div>

        <div className="space-y-4">
          {drafts.map((group) => {
            if (group.drafts.length === 0) {
              return null;
            }
            return (
              <section key={group.status} className="space-y-2">
                <div className="flex items-center justify-between">
                  <div className="text-sm font-medium">
                    {getStatusLabel(group.status, t)}
                  </div>
                  <Badge variant="outline">{group.drafts.length}</Badge>
                </div>
                <div className="space-y-2">
                  {group.drafts.map((draft) => {
                    const isActive = selectedDraftId === draft.id;
                    return (
                      <div
                        key={draft.id}
                        className={`rounded-xl border p-3 ${
                          isActive ? 'border-blue-500 bg-blue-50' : 'bg-card'
                        }`}
                        data-testid={`broadcast-draft-row-${draft.id}`}
                      >
                        <div className="flex items-start gap-3">
                          <Checkbox
                            aria-label={t('broadcast.drafts.selectDraft', {
                              id: draft.id,
                            })}
                            checked={selectedDraftIds.includes(draft.id)}
                            disabled={busy}
                            data-testid={`broadcast-draft-select-${draft.id}`}
                            onCheckedChange={(checked) =>
                              onToggleDraftSelection(draft.id, Boolean(checked))
                            }
                          />
                          <button
                            type="button"
                            className="min-w-0 flex-1 text-left"
                            onClick={() => onSelectDraft(draft.id)}
                          >
                            <div className="truncate font-medium">
                              {draft.customerName}
                            </div>
                            <div className="truncate text-xs text-muted-foreground">
                              {draft.conversationName}
                            </div>
                            <div className="mt-2 text-xs text-muted-foreground">
                              {getStatusLabel(group.status, t)}
                              {draft.draftsStale
                                ? ` · ${t('broadcast.drafts.staleBadge')}`
                                : draft.attachmentsStale
                                  ? ` · ${t('broadcast.drafts.attachmentsStaleBadge')}`
                                  : ''}
                            </div>
                          </button>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </section>
            );
          })}
        </div>
      </CardContent>
      <AlertDialog
        open={batchWriteDialogOpen}
        onOpenChange={setBatchWriteDialogOpen}
      >
        <AlertDialogContent data-testid="broadcast-draft-batch-write-confirm-dialog">
          <AlertDialogHeader>
            <AlertDialogTitle>
              {t('broadcast.drafts.batchWriteConfirmTitle')}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {t('broadcast.drafts.batchWriteConfirmDescription', {
                draftCount: selectedDrafts.length,
                conversationCount: selectedConversationCount,
                attachmentCount: selectedAttachmentCount,
                duplicateTargetCount: selectedDuplicateConversationCount,
              })}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel data-testid="broadcast-draft-batch-write-cancel-button">
              {t('common.cancel')}
            </AlertDialogCancel>
            <AlertDialogAction
              data-testid="broadcast-draft-batch-write-confirm-button"
              onClick={(event) => {
                event.preventDefault();
                onBatchWrite();
                setBatchWriteDialogOpen(false);
              }}
            >
              {t('broadcast.drafts.batchWriteSelected')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
      <AlertDialog
        open={batchSendDialogOpen}
        onOpenChange={setBatchSendDialogOpen}
      >
        <AlertDialogContent data-testid="broadcast-draft-batch-send-confirm-dialog">
          <AlertDialogHeader>
            <AlertDialogTitle>
              {t('broadcast.drafts.batchSendConfirmTitle')}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {t('broadcast.drafts.batchSendConfirmDescription', {
                draftCount: selectedDrafts.length,
                conversationCount: selectedConversationCount,
                attachmentCount: selectedAttachmentCount,
                duplicateTargetCount: selectedDuplicateConversationCount,
              })}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel data-testid="broadcast-draft-batch-send-cancel-button">
              {t('common.cancel')}
            </AlertDialogCancel>
            <AlertDialogAction
              data-testid="broadcast-draft-batch-send-confirm-button"
              onClick={(event) => {
                event.preventDefault();
                onBatchSend();
                setBatchSendDialogOpen(false);
              }}
            >
              {t('broadcast.drafts.batchSendSelected')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
      <AlertDialog
        open={batchRestorePendingRiskDialogOpen}
        onOpenChange={setBatchRestorePendingRiskDialogOpen}
      >
        <AlertDialogContent data-testid="broadcast-draft-batch-restore-pending-risk-dialog">
          <AlertDialogHeader>
            <AlertDialogTitle>
              {t('broadcast.drafts.restorePendingRiskTitle')}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {t('broadcast.drafts.restorePendingRiskDescription')}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel data-testid="broadcast-draft-batch-restore-pending-risk-cancel-button">
              {t('common.cancel')}
            </AlertDialogCancel>
            <AlertDialogAction
              data-testid="broadcast-draft-batch-restore-pending-risk-confirm-button"
              onClick={(event) => {
                event.preventDefault();
                onBatchRestorePending();
                setBatchRestorePendingRiskDialogOpen(false);
              }}
            >
              {t('broadcast.drafts.restorePending')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Card>
  );
}
