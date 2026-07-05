import { Fragment, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { Alert, AlertDescription } from '@/components/ui/alert';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
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
  BroadcastImportBatch,
  BroadcastImportDetail,
  BroadcastImportGroupList,
  BroadcastImportGroupMatchStatus,
  BroadcastImportGroupRowsPage,
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
  loading?: boolean;
  busy?: boolean;
  error?: string | null;
  onUpload: (file: File) => Promise<void>;
  onSelectBatch: (batchId: number) => Promise<void>;
  onPageChange: (page: number) => Promise<void>;
  onDeleteBatch: (batchId: number) => Promise<void>;
  onRematch: (batchId: number) => Promise<void>;
  onGenerateDrafts: (batchId: number, templateId: number) => Promise<void>;
  onLoadGroupRows: (groupKey: string, page?: number) => Promise<void>;
  onUploadGroupAttachments: (
    groupKey: string,
    files: File[],
  ) => Promise<void>;
  onDeleteGroupAttachment: (
    groupKey: string,
    attachmentId: number,
  ) => Promise<void>;
}

const EMPTY_ATTACHMENTS: BroadcastAttachment[] = [];

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
  loading = false,
  busy = false,
  error = null,
  onUpload,
  onSelectBatch,
  onPageChange,
  onDeleteBatch,
  onRematch,
  onGenerateDrafts,
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
  const [selectedTemplateId, setSelectedTemplateId] = useState<string>('');
  const [expandedGroupKeys, setExpandedGroupKeys] = useState<string[]>([]);

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

          <div className="flex flex-wrap gap-2">
            <Button
              data-testid="broadcast-import-rematch-button"
              variant="outline"
              disabled={!selectedBatchId || busy}
              onClick={() => selectedBatchId && void onRematch(selectedBatchId)}
            >
              {t('broadcast.import.rematchButton')}
            </Button>
            <Button
              data-testid="broadcast-import-delete-batch-button"
              variant="outline"
              disabled={!selectedBatchId || busy}
              onClick={() =>
                selectedBatchId && void onDeleteBatch(selectedBatchId)
              }
            >
              {t('broadcast.import.deleteBatchButton')}
            </Button>
            <Select
              value={selectedTemplateId}
              onValueChange={setSelectedTemplateId}
            >
              <SelectTrigger
                data-testid="broadcast-import-template-select"
                className="w-[220px]"
              >
                <SelectValue
                  placeholder={t('broadcast.import.templatePlaceholder')}
                />
              </SelectTrigger>
              <SelectContent>
                {templates.map((template) => (
                  <SelectItem key={template.id} value={String(template.id)}>
                    {template.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Button
              data-testid="broadcast-import-generate-drafts-button"
              disabled={!selectedBatchId || !selectedTemplateId || busy}
              onClick={() =>
                selectedBatchId &&
                selectedTemplateId &&
                void onGenerateDrafts(
                  selectedBatchId,
                  Number(selectedTemplateId),
                )
              }
            >
              {t('broadcast.import.generateDraftsButton')}
            </Button>
          </div>

          {detail?.draftsStale && detail.status === 'matched' ? (
            <div className="rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-800">
              {t('broadcast.import.draftsStale')}
            </div>
          ) : null}

          <div data-testid="broadcast-import-table">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{t('broadcast.import.tableHeaders.groupValue')}</TableHead>
                  <TableHead>{t('broadcast.import.tableHeaders.orderCount')}</TableHead>
                  <TableHead>{t('broadcast.import.tableHeaders.rawRowCount')}</TableHead>
                  <TableHead>
                    {t('broadcast.import.tableHeaders.matchedConversationName')}
                  </TableHead>
                  <TableHead>{t('broadcast.import.tableHeaders.matchStatus')}</TableHead>
                  <TableHead>{t('broadcast.import.tableHeaders.attachments')}</TableHead>
                  <TableHead>{t('broadcast.import.tableHeaders.errorMessage')}</TableHead>
                  <TableHead className="w-[120px] text-right">
                    {t('broadcast.import.tableHeaders.actions')}
                  </TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {(groupsDetail?.groups ?? []).map((group) => {
                  const expanded = expandedGroupKeys.includes(group.groupKey);
                  const groupRows = groupRowsByKey[group.groupKey];
                  const attachments = group.attachments ?? EMPTY_ATTACHMENTS;
                  return (
                    <Fragment key={group.groupKey}>
                      <TableRow key={group.groupKey}>
                        <TableCell className="font-medium">
                          {group.groupValue}
                        </TableCell>
                        <TableCell>{group.distinctOrderNumberCount}</TableCell>
                        <TableCell>{group.rawRowCount}</TableCell>
                        <TableCell>{group.matchedConversationName || '-'}</TableCell>
                        <TableCell>
                          <Badge variant="outline">
                            {renderMatchStatusLabel(group.matchStatus, t)}
                          </Badge>
                        </TableCell>
                        <TableCell>
                          <Badge variant="secondary">
                            {attachments.length || group.attachmentCount}
                          </Badge>
                        </TableCell>
                        <TableCell className="max-w-[260px] text-sm text-muted-foreground">
                          {group.reason || '-'}
                        </TableCell>
                        <TableCell className="text-right">
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
                        </TableCell>
                      </TableRow>
                      {expanded ? (
                        <TableRow>
                          <TableCell colSpan={8} className="bg-muted/10">
                            <div className="space-y-4 py-2">
                              <div className="flex flex-wrap items-center justify-between gap-2">
                                <div className="text-sm font-medium">
                                  {t('broadcast.import.groupAttachments')}
                                </div>
                                <div className="flex items-center gap-2">
                                  <input
                                    ref={(node) => {
                                      attachmentInputRefs.current[group.groupKey] =
                                        node;
                                    }}
                                    type="file"
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
                                          totalPages: groupRows?.totalPages ?? 0,
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
                {(groupsDetail?.groups.length ?? 0) === 0 ? (
                  <TableRow>
                    <TableCell
                      colSpan={8}
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
    </div>
  );
}
