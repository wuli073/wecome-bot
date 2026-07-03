import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';

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
  BroadcastDraftStatus,
  BroadcastStatusFilter,
} from '../../types';

interface DraftQueueProps {
  drafts: Array<{ status: BroadcastDraftStatus; drafts: BroadcastDraft[] }>;
  importBatches: BroadcastImportBatch[];
  selectedImportId: number | null;
  searchTerm: string;
  statusFilter: BroadcastStatusFilter;
  selectedDraftId: number | null;
  selectedDraftIds: number[];
  busy?: boolean;
  onImportBatchChange: (importBatchId: number | null) => void;
  onSearchTermChange: (value: string) => void;
  onStatusFilterChange: (value: BroadcastStatusFilter) => void;
  onSelectDraft: (draftId: number) => void;
  onToggleDraftSelection: (draftId: number, checked: boolean) => void;
  onBatchConfirm: () => void;
  onCreateExecutionBatch: () => void;
}

function getStatusLabel(
  status: BroadcastDraftStatus,
  t: ReturnType<typeof useTranslation>['t'],
) {
  if (status === 'pending_review') {
    return t('broadcast.drafts.statusPendingReview');
  }
  if (status === 'ready') {
    return t('broadcast.drafts.statusReady');
  }
  return t('broadcast.drafts.statusInvalid');
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
  onImportBatchChange,
  onSearchTermChange,
  onStatusFilterChange,
  onSelectDraft,
  onToggleDraftSelection,
  onBatchConfirm,
  onCreateExecutionBatch,
}: DraftQueueProps) {
  const { t } = useTranslation();

  const selectableDraftIds = useMemo(
    () =>
      drafts
        .flatMap((group) => group.drafts)
        .filter((draft) => draft.status !== 'invalid' && !draft.draftsStale)
        .map((draft) => draft.id),
    [drafts],
  );

  const eligibleSelectedCount = selectedDraftIds.filter((draftId) =>
    selectableDraftIds.includes(draftId),
  ).length;

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
              <SelectItem value="all">{t('broadcast.drafts.allBatches')}</SelectItem>
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
              <SelectItem value="all">{t('broadcast.drafts.allStatuses')}</SelectItem>
              <SelectItem value="pending_review">
                {t('broadcast.drafts.statusPendingReview')}
              </SelectItem>
              <SelectItem value="ready">{t('broadcast.drafts.statusReady')}</SelectItem>
              <SelectItem value="invalid">{t('broadcast.drafts.statusInvalid')}</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <div className="rounded-xl border bg-muted/20 p-4">
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
                  <div className="text-sm font-medium">{t('broadcast.drafts.batchToolbar')}</div>
                  <div className="text-xs text-muted-foreground">
                    {t('broadcast.drafts.selectedCount', {
                      count: eligibleSelectedCount,
                    })}
                  </div>
                </div>
              </div>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button
                data-testid="broadcast-draft-batch-confirm-button"
                onClick={onBatchConfirm}
                disabled={eligibleSelectedCount === 0 || busy}
              >
                {t('broadcast.drafts.batchConfirm')}
              </Button>
              <Button
                data-testid="broadcast-draft-create-execution-batch-button"
                variant="outline"
                onClick={onCreateExecutionBatch}
                disabled={eligibleSelectedCount === 0 || busy}
              >
                {t('broadcast.drafts.createExecutionBatch')}
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
                    const selectionDisabled =
                      draft.status === 'invalid' || Boolean(draft.draftsStale);
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
                            aria-label={t('broadcast.drafts.selectDraft', { id: draft.id })}
                            checked={selectedDraftIds.includes(draft.id)}
                            disabled={selectionDisabled || busy}
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
                            <div className="truncate font-medium">{draft.customerName}</div>
                            <div className="truncate text-xs text-muted-foreground">
                              {draft.conversationName}
                            </div>
                            <div className="mt-2 text-xs text-muted-foreground">
                              {getStatusLabel(draft.status as BroadcastDraftStatus, t)}
                              {draft.draftsStale ? ` · ${t('broadcast.drafts.staleBadge')}` : ''}
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
    </Card>
  );
}
