import { useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  type ColumnDef,
  flexRender,
  getCoreRowModel,
  useReactTable,
} from '@tanstack/react-table';

import {
  Alert,
  AlertDescription,
} from '@/components/ui/alert';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
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
  onDeleteBatch: (batchId: number) => Promise<void>;
  onRematch: (batchId: number) => Promise<void>;
  onGenerateDrafts: (batchId: number, templateId: number) => Promise<void>;
}

const MATCH_STATUS_LABELS: Record<BroadcastImportMatchStatus, string> = {
  matched: '已匹配',
  unmatched: '未匹配',
  invalid: '无效',
};

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
  onDeleteBatch,
  onRematch,
  onGenerateDrafts,
}: ImportMatchingPanelProps) {
  markBroadcastRender('ImportMatchingPanel');
  const { t } = useTranslation();
  const uploadRef = useRef<HTMLInputElement | null>(null);
  const [selectedTemplateId, setSelectedTemplateId] = useState<string>('');
  const rows = detail?.rows ?? [];

  const columns = useMemo<ColumnDef<BroadcastImportPreviewRow>[]>(
    () => [
      {
        accessorKey: 'sourceRowNumber',
        header: '行号',
      },
      {
        accessorKey: 'groupValue',
        header: '客户/分组',
        cell: ({ row }) => row.original.groupValue || '-',
      },
      {
        accessorKey: 'matchedConversationName',
        header: '匹配群聊',
        cell: ({ row }) => row.original.matchedConversationName || '-',
      },
      {
        accessorKey: 'matchStatus',
        header: '结果',
        cell: ({ row }) => (
          <Badge variant="outline">
            {MATCH_STATUS_LABELS[row.original.matchStatus]}
          </Badge>
        ),
      },
      {
        accessorKey: 'errorMessage',
        header: '原因',
        cell: ({ row }) => row.original.errorMessage || '-',
      },
    ],
    [],
  );

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
          <Button onClick={() => uploadRef.current?.click()} disabled={busy}>
            上传 CSV / XLSX
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
                  onClick={() => void onSelectBatch(batch.id)}
                >
                  <div className="font-medium">{batch.originalFileName}</div>
                  <div className="mt-1 text-xs text-muted-foreground">
                    共 {batch.totalRows} 行 / 已匹配 {batch.matchedRows}
                  </div>
                </button>
              );
            })}
            {!loading && batches.length === 0 ? (
              <div className="rounded-lg border border-dashed p-4 text-sm text-muted-foreground">
                暂无导入批次
              </div>
            ) : null}
          </div>
        </CardContent>
      </Card>

      <Card className="gap-4">
        <CardHeader>
          <CardTitle>{detail?.originalFileName || '导入详情'}</CardTitle>
          <CardDescription>
            <div>上传成功后立即展示真实匹配结果，无需先点击重新匹配。</div>
            {detail?.worksheetName ? (
              <div className="mt-1">工作表：{detail.worksheetName}</div>
            ) : null}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-3 md:grid-cols-4">
            <div className="rounded-xl border bg-muted/20 p-4">
              <div className="text-sm text-muted-foreground">总行数</div>
              <div className="mt-2 text-2xl font-semibold">{detail?.totalRows ?? 0}</div>
            </div>
            <div className="rounded-xl border bg-muted/20 p-4">
              <div className="text-sm text-muted-foreground">已匹配</div>
              <div className="mt-2 text-2xl font-semibold">{matchedCount}</div>
            </div>
            <div className="rounded-xl border bg-muted/20 p-4">
              <div className="text-sm text-muted-foreground">未匹配</div>
              <div className="mt-2 text-2xl font-semibold">{unmatchedCount}</div>
            </div>
            <div className="rounded-xl border bg-muted/20 p-4">
              <div className="text-sm text-muted-foreground">无效</div>
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
              重新匹配
            </Button>
            <Button
              variant="outline"
              disabled={!selectedBatchId || busy}
              onClick={() => selectedBatchId && void onDeleteBatch(selectedBatchId)}
            >
              删除批次
            </Button>
            <Select value={selectedTemplateId} onValueChange={setSelectedTemplateId}>
              <SelectTrigger
                data-testid="broadcast-import-template-select"
                className="w-[220px]"
              >
                <SelectValue placeholder="选择模板" />
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
                void onGenerateDrafts(selectedBatchId, Number(selectedTemplateId))
              }
            >
              生成草稿
            </Button>
          </div>

          {detail?.draftsStale && detail.status === 'matched' ? (
            <div className="rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-800">
              草稿已过期，请重新生成
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
                          ? flexRender(cell.column.columnDef.cell, cell.getContext())
                          : String(cell.getValue() ?? '')}
                      </TableCell>
                    ))}
                  </TableRow>
                ))}
                {rows.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={5} className="text-center text-muted-foreground">
                      暂无导入明细
                    </TableCell>
                  </TableRow>
                ) : null}
              </TableBody>
            </Table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
