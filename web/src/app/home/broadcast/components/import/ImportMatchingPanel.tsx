import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import {
  type ColumnDef,
  flexRender,
  getCoreRowModel,
  useReactTable,
} from '@tanstack/react-table';

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';

import type { BroadcastImportPreviewRow } from '../../types';

interface ImportMatchingPanelProps {
  rows: BroadcastImportPreviewRow[];
}

export default function ImportMatchingPanel({
  rows,
}: ImportMatchingPanelProps) {
  const { t } = useTranslation();

  const columns = useMemo<ColumnDef<BroadcastImportPreviewRow>[]>(
    () => [
      {
        accessorKey: 'customerName',
        header: t('broadcast.fields.customer'),
      },
      {
        accessorKey: 'conversationName',
        header: t('broadcast.fields.conversation'),
      },
      {
        accessorKey: 'templateName',
        header: t('broadcast.fields.template'),
      },
      {
        accessorKey: 'variableSummary',
        header: t('broadcast.fields.variables'),
      },
      {
        accessorKey: 'matchedRule',
        header: t('broadcast.fields.matchingRule'),
      },
      {
        accessorKey: 'status',
        header: t('broadcast.fields.status'),
        cell: ({ row }) => (
          <Badge variant="outline">
            {t(`broadcast.status.${row.original.status}`)}
          </Badge>
        ),
      },
    ],
    [t],
  );

  const table = useReactTable({
    data: rows,
    columns,
    getCoreRowModel: getCoreRowModel(),
  });

  return (
    <Card className="gap-4">
      <CardHeader>
        <CardTitle>{t('broadcast.import.title')}</CardTitle>
        <CardDescription>{t('broadcast.import.description')}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          {[
            ['rows', rows.length],
            ['ready', rows.filter((row) => row.status === 'completed').length],
            ['pending', rows.filter((row) => row.status === 'pending').length],
            ['attention', rows.filter((row) => row.status === 'failed').length],
          ].map(([key, value]) => (
            <div key={key} className="rounded-xl border bg-muted/20 p-4">
              <div className="text-sm text-muted-foreground">
                {t(`broadcast.import.summary.${key}`)}
              </div>
              <div className="mt-2 text-2xl font-semibold">{value}</div>
            </div>
          ))}
        </div>

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
            </TableBody>
          </Table>
        </div>
      </CardContent>
    </Card>
  );
}
