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
}: DraftQueueProps) {
  const { t } = useTranslation();
  const eligibleSelectedCount = selectedDraftIds.filter((draftId) =>
    drafts.some((group) =>
      group.drafts.some(
        (draft) =>
          draft.id === draftId &&
          draft.status !== 'invalid' &&
          !draft.draftsStale,
      ),
    ),
  ).length;

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
              aria-label="批次筛选"
              data-testid="broadcast-draft-batch-filter"
            >
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">全部批次</SelectItem>
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
              <SelectItem value="all">全部状态</SelectItem>
              <SelectItem value="pending_review">待审核</SelectItem>
              <SelectItem value="ready">已确认</SelectItem>
              <SelectItem value="invalid">无效</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <div className="rounded-xl border bg-muted/20 p-4">
          <div className="flex items-center justify-between gap-3">
            <div>
              <div className="text-sm font-medium">批量操作</div>
              <div className="text-xs text-muted-foreground">
                已选 {eligibleSelectedCount} 条草稿
              </div>
            </div>
            <Button
              data-testid="broadcast-draft-batch-confirm-button"
              onClick={onBatchConfirm}
              disabled={eligibleSelectedCount === 0 || busy}
            >
              批量确认
            </Button>
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
                    {group.status === 'pending_review'
                      ? '待审核'
                      : group.status === 'ready'
                        ? '已确认'
                        : '无效'}
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
                      >
                        <div className="flex items-start gap-3">
                          <Checkbox
                            aria-label={`选择草稿 ${draft.id}`}
                            checked={selectedDraftIds.includes(draft.id)}
                            disabled={selectionDisabled}
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
                              {draft.status === 'pending_review'
                                ? '待审核'
                                : draft.status === 'ready'
                                  ? '已确认'
                                  : '无效'}
                              {draft.draftsStale ? ' · 草稿已过期' : ''}
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
