import { useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  type ColumnDef,
  flexRender,
  getCoreRowModel,
  useReactTable,
} from '@tanstack/react-table';

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
  BroadcastImportBatch,
  BroadcastImportDetail,
  BroadcastImportMatchStatus,
  BroadcastImportPreviewRow,
  BroadcastMessageTemplate,
} from '../../types';
import { markBroadcastRender } from '../../diagnostics';

const EMPTY_IMPORT_ROWS: BroadcastImportPreviewRow[] = [];

interface ImportMatchingPanelProps {
  batches: BroadcastImportBatch[];
  selectedBatchId: number | null;
  detail: BroadcastImportDetail | null;
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
}

export default function ImportMatchingPanel({
  batches,
  selectedBatchId,
  detail,
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
}: ImportMatchingPanelProps) {
  markBroadcastRender('ImportMatchingPanel');
  const { t } = useTranslation();
  const uploadRef = useRef<HTMLInputElement | null>(null);
  const [selectedTemplateId, setSelectedTemplateId] = useState<string>('');
  const rows = detail?.rows ?? EMPTY_IMPORT_ROWS;

  const columns = useMemo<ColumnDef<BroadcastImportPreviewRow>[]>(() => {
    const matchStatusLabels: Record<BroadcastImportMatchStatus, string> = {
      matched: t('broadcast.import.statusLabels.matched'),
      unmatched: t('broadcast.import.statusLabels.unmatched'),
      invalid: t('broadcast.import.statusLabels.invalid'),
    };

    return [
      {
        accessorKey: 'sourceRowNumber',
        header: t('broadcast.import.tableHeaders.sourceRowNumber'),
      },
      {
        accessorKey: 'groupValue',
        header: t('broadcast.import.tableHeaders.groupValue'),
        cell: ({ row }) => row.original.groupValue || '-',
      },
      {
        accessorKey: 'matchedConversationName',
        header: t('broadcast.import.tableHeaders.matchedConversationName'),
        cell: ({ row }) => row.original.matchedConversationName || '-',
      },
      {
        accessorKey: 'matchStatus',
        header: t('broadcast.import.tableHeaders.matchStatus'),
        cell: ({ row }) => (
          <Badge variant="outline">
            {matchStatusLabels[row.original.matchStatus]}
          </Badge>
        ),
      },
      {
        accessorKey: 'errorMessage',
        header: t('broadcast.import.tableHeaders.errorMessage'),
        cell: ({ row }) => row.original.errorMessage || '-',
      },
    ];
  }, [t]);

  const table = useReactTable({
    data: rows,
    columns,
    getCoreRowModel: getCoreRowModel(),
  });

  const matchedCount = detail?.matchedRows ?? 0;
  const unmatchedCount = detail?.unmatchedRows ?? 0;
  const invalidCount = detail?.invalidRows ?? 0;

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
                if (input) {
                  input.value = '';
                }
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
          <div className="grid gap-3 md:grid-cols-4">
            <div className="rounded-xl border bg-muted/20 p-4">
              <div className="text-sm text-muted-foreground">
                {t('broadcast.import.stats.totalRows')}
              </div>
              <div className="mt-2 text-2xl font-semibold">
                {detail?.totalRows ?? 0}
              </div>
            </div>
            <div className="rounded-xl border bg-muted/20 p-4">
              <div className="text-sm text-muted-foreground">
                {t('broadcast.import.stats.matchedRows')}
              </div>
              <div className="mt-2 text-2xl font-semibold">{matchedCount}</div>
            </div>
            <div className="rounded-xl border bg-muted/20 p-4">
              <div className="text-sm text-muted-foreground">
                {t('broadcast.import.stats.unmatchedRows')}
              </div>
              <div className="mt-2 text-2xl font-semibold">
                {unmatchedCount}
              </div>
            </div>
            <div className="rounded-xl border bg-muted/20 p-4">
              <div className="text-sm text-muted-foreground">
                {t('broadcast.import.stats.invalidRows')}
              </div>
              <div className="mt-2 text-2xl font-semibold">{invalidCount}</div>
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
                {table.getHeaderGroups().map((headerGroup) => (
                  <TableRow key={headerGroup.id}>
                    {headerGroup.headers.map((header) => (
                      <TableHead key={header.id}>
                        {header.isPlaceholder
                          ? null
                          : flexRender(
                              header.column.columnDef.header,
                              header.getContext(),
                            )}
                      </TableHead>
                    ))}
                  </TableRow>
                ))}
              </TableHeader>
              <TableBody>
                {table.getRowModel().rows.map((row) => (
                  <TableRow key={row.id}>
                    {row.getVisibleCells().map((cell) => (
                      <TableCell key={cell.id}>
                        {cell.column.columnDef.cell
                          ? flexRender(
                              cell.column.columnDef.cell,
                              cell.getContext(),
                            )
                          : String(cell.getValue() ?? '')}
                      </TableCell>
                    ))}
                  </TableRow>
                ))}
                {rows.length === 0 ? (
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
          <div className="flex items-center justify-between gap-3 text-sm">
            <div
              className="text-muted-foreground"
              data-testid="broadcast-import-total-items"
            >
              {t('broadcast.import.pagination.totalItems', {
                total: detail?.total ?? 0,
              })}
            </div>
            <div className="flex items-center gap-3">
              <Button
                data-testid="broadcast-import-prev-page"
                variant="outline"
                size="sm"
                disabled={loading || busy || !detail || detail.page <= 1}
                onClick={() => {
                  if (!detail) {
                    return;
                  }
                  void onPageChange(detail.page - 1);
                }}
              >
                {t('broadcast.import.pagination.previous')}
              </Button>
              <span data-testid="broadcast-import-pagination">
                {t('broadcast.import.pagination.pageStatus', {
                  page: detail?.page ?? 0,
                  totalPages: detail?.totalPages ?? 0,
                })}
              </span>
              <Button
                data-testid="broadcast-import-next-page"
                variant="outline"
                size="sm"
                disabled={
                  loading ||
                  busy ||
                  !detail ||
                  detail.totalPages === 0 ||
                  detail.page >= detail.totalPages
                }
                onClick={() => {
                  if (!detail) {
                    return;
                  }
                  void onPageChange(detail.page + 1);
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
