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
import { Progress } from '@/components/ui/progress';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';

import type {
  BroadcastBatchState,
  BroadcastDraft,
  BroadcastStatus,
  BroadcastStatusFilter,
} from '../../types';

interface DraftQueueProps {
  drafts: Array<{ status: BroadcastStatus; drafts: BroadcastDraft[] }>;
  searchTerm: string;
  statusFilter: BroadcastStatusFilter;
  selectedDraftId: number | null;
  selectedDraftIds: number[];
  batchState: BroadcastBatchState;
  onSearchTermChange: (value: string) => void;
  onStatusFilterChange: (value: BroadcastStatusFilter) => void;
  onSelectDraft: (draftId: number) => void;
  onToggleDraftSelection: (draftId: number, checked: boolean) => void;
  onRunMockBatch: () => void;
}

export default function DraftQueue({
  drafts,
  searchTerm,
  statusFilter,
  selectedDraftId,
  selectedDraftIds,
  batchState,
  onSearchTermChange,
  onStatusFilterChange,
  onSelectDraft,
  onToggleDraftSelection,
  onRunMockBatch,
}: DraftQueueProps) {
  const { t } = useTranslation();

  const totalVisibleDrafts = drafts.reduce(
    (sum, group) => sum + group.drafts.length,
    0,
  );
  const progressValue =
    batchState.total > 0
      ? Math.round((batchState.completed / batchState.total) * 100)
      : 0;

  return (
    <Card className="min-h-0 gap-4" data-testid="broadcast-draft-queue">
      <CardHeader>
        <CardTitle>{t('broadcast.drafts.title')}</CardTitle>
        <CardDescription>{t('broadcast.drafts.description')}</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <div className="grid gap-3">
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
                {t('broadcast.status.pending')}
              </SelectItem>
              <SelectItem value="pasted">
                {t('broadcast.status.pasted')}
              </SelectItem>
              <SelectItem value="failed">
                {t('broadcast.status.failed')}
              </SelectItem>
              <SelectItem value="completed">
                {t('broadcast.status.completed')}
              </SelectItem>
            </SelectContent>
          </Select>
        </div>

        <div className="rounded-xl border bg-muted/20 p-4">
          <div className="flex items-center justify-between gap-3">
            <div>
              <div className="text-sm font-medium">
                {batchState.phase === 'running'
                  ? t('broadcast.drafts.batchRunning')
                  : batchState.phase === 'completed'
                    ? t('broadcast.drafts.batchCompleted')
                    : t('broadcast.drafts.batchToolbar')}
              </div>
              <div className="text-xs text-muted-foreground">
                {t('broadcast.drafts.selectedCount', {
                  count: selectedDraftIds.length,
                })}
              </div>
            </div>
            <Button
              variant="default"
              onClick={onRunMockBatch}
              disabled={totalVisibleDrafts === 0 || batchState.phase === 'running'}
            >
              {t('broadcast.drafts.mockPasteSelected')}
            </Button>
          </div>
          <div className="mt-3 space-y-2">
            <Progress value={progressValue} />
            {batchState.phase !== 'idle' ? (
              <div className="text-xs text-muted-foreground">
                {`${batchState.completed} / ${batchState.total}`}
                {batchState.currentLabel ? ` · ${batchState.currentLabel}` : ''}
              </div>
            ) : null}
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
                    {t(`broadcast.status.${group.status}`)}
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
                      >
                        <div className="flex items-start gap-3">
                          <Checkbox
                            aria-label={`选择草稿 ${draft.id}`}
                            checked={selectedDraftIds.includes(draft.id)}
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
                              {draft.progressLabel}
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
