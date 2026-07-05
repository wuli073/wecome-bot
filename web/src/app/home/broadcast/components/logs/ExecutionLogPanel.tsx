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
import { Button } from '@/components/ui/button';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';

import type {
  BroadcastExecutionBatchSummary,
  BroadcastExecutionLog,
  BroadcastExecutionTaskSummary,
  BroadcastExecutorCapability,
  BroadcastExecutorHealth,
} from '../../types';

interface ExecutionLogPanelProps {
  logs: BroadcastExecutionLog[];
  latestBatch?: BroadcastExecutionBatchSummary | null;
  executorCapability?: BroadcastExecutorCapability | null;
  executorHealth?: BroadcastExecutorHealth | null;
  pasteVerificationAvailable?: boolean;
  pasteVerificationMethod?: 'windows_uia' | 'unavailable';
  requiresManualConversationOpen?: boolean;
  pasteActionDisabledReason?: string | null;
  busy?: boolean;
  onStartBatch?: () => void;
  onPauseBatch?: () => void;
  onResumeBatch?: () => void;
  onCancelBatch?: () => void;
  onRetryTask?: (taskId: number) => void;
}

function formatTimestamp(value: string) {
  return new Date(value).toLocaleString();
}

function isRetryableTask(task: BroadcastExecutionTaskSummary) {
  return task.status === 'failed' || task.status === 'interrupted';
}

function isBatchTerminal(status: string) {
  return [
    'completed',
    'partially_failed',
    'failed',
    'cancelled',
    'interrupted',
  ].includes(status);
}

function getLogStatusLabel(
  log: BroadcastExecutionLog,
  t: ReturnType<typeof useTranslation>['t'],
) {
  if (log.taskStatus === 'succeeded_with_warning') {
    return t('broadcast.logs.statusWarning');
  }
  if (log.action === 'send_message' && log.sendTriggered) {
    return t('broadcast.logs.statusSendTriggered');
  }
  if (log.contentVerified) {
    return t('broadcast.logs.statusPasteVerified');
  }
  if (log.draftWritten && !log.sendTriggered) {
    return t('broadcast.logs.statusDraftWritten');
  }
  return log.taskStatus;
}

function getLogBadgeVariant(
  log: BroadcastExecutionLog,
): 'outline' | 'secondary' {
  return log.taskStatus === 'succeeded_with_warning' ? 'secondary' : 'outline';
}

function getBooleanLabel(
  value: boolean | undefined,
  t: ReturnType<typeof useTranslation>['t'],
) {
  return value ? t('broadcast.logs.booleanYes') : t('broadcast.logs.booleanNo');
}

function getAttachmentNames(log: BroadcastExecutionLog) {
  return (log.attachmentNames || []).filter((item) => item.trim().length > 0);
}

function hasAttachmentSection(log: BroadcastExecutionLog) {
  return (log.attachmentCount || 0) > 0 || getAttachmentNames(log).length > 0;
}

function renderLogEvidence(
  log: BroadcastExecutionLog,
  t: ReturnType<typeof useTranslation>['t'],
) {
  const items: Array<{ label: string; value: string }> = [];
  if (hasAttachmentSection(log)) {
    items.push({
      label: t('broadcast.logs.fields.attachmentCount'),
      value: String(log.attachmentCount || 0),
    });
    const names = getAttachmentNames(log);
    if (names.length > 0) {
      items.push({
        label: t('broadcast.logs.fields.attachmentNames'),
        value: names.join(', '),
      });
    }
  }
  items.push({
    label: t('broadcast.logs.fields.textContentVerified'),
    value: getBooleanLabel(log.textContentVerified, t),
  });
  items.push({
    label: t('broadcast.logs.fields.attachmentsPrepared'),
    value: getBooleanLabel(log.attachmentsPrepared, t),
  });
  items.push({
    label: t('broadcast.logs.fields.attachmentPasteRequested'),
    value: getBooleanLabel(log.attachmentPasteRequested, t),
  });
  items.push({
    label: t('broadcast.logs.fields.attachmentsVerified'),
    value: getBooleanLabel(log.attachmentsVerified, t),
  });
  if (log.warning) {
    items.push({
      label: t('broadcast.logs.fields.warning'),
      value: t(`broadcast.logs.warningCodes.${log.warning}`, log.warning),
    });
  }
  if (log.errorCode) {
    items.push({
      label: t('broadcast.logs.fields.errorCode'),
      value: t(`broadcast.logs.errorCodes.${log.errorCode}`, log.errorCode),
    });
  }
  if (log.stage) {
    items.push({
      label: t('broadcast.logs.fields.stage'),
      value: log.stage,
    });
  }

  return (
    <div className="mt-2 space-y-1 text-xs text-muted-foreground">
      {items.map((item) => (
        <div key={`${item.label}-${item.value}`} className="break-all">
          <span className="font-medium text-foreground">{item.label}: </span>
          <span>{item.value}</span>
        </div>
      ))}
    </div>
  );
}

export default function ExecutionLogPanel({
  logs,
  latestBatch,
  executorCapability,
  executorHealth,
  pasteVerificationAvailable = false,
  pasteVerificationMethod: _pasteVerificationMethod = 'unavailable',
  requiresManualConversationOpen: _requiresManualConversationOpen = false,
  pasteActionDisabledReason = null,
  busy = false,
  onStartBatch,
  onPauseBatch,
  onResumeBatch,
  onCancelBatch,
  onRetryTask,
}: ExecutionLogPanelProps) {
  const { t } = useTranslation();

  const columns = useMemo<ColumnDef<BroadcastExecutionLog>[]>(
    () => [
      {
        accessorKey: 'timestamp',
        header: t('broadcast.fields.timestamp'),
        cell: ({ row }) => formatTimestamp(row.original.timestamp),
      },
      {
        accessorKey: 'customerName',
        header: t('broadcast.fields.customer'),
      },
      {
        accessorKey: 'conversationName',
        header: t('broadcast.fields.conversation'),
      },
      {
        accessorKey: 'action',
        header: t('broadcast.fields.action'),
      },
      {
        accessorKey: 'message',
        header: t('broadcast.fields.message'),
      },
      {
        accessorKey: 'taskStatus',
        header: t('broadcast.fields.status'),
        cell: ({ row }) => (
          <Badge variant={getLogBadgeVariant(row.original)}>
            {getLogStatusLabel(row.original, t)}
          </Badge>
        ),
      },
    ],
    [t],
  );

  const table = useReactTable({
    data: logs,
    columns,
    getCoreRowModel: getCoreRowModel(),
  });

  const batchStatus = latestBatch?.status || '';
  const canRunLatestPasteBatch =
    latestBatch?.mode === 'paste_only' ? pasteVerificationAvailable : true;
  const canStart =
    Boolean(onStartBatch) &&
    latestBatch != null &&
    ['created', 'paused'].includes(batchStatus) &&
    canRunLatestPasteBatch;
  const canPause =
    Boolean(onPauseBatch) &&
    latestBatch != null &&
    ['queued', 'running'].includes(batchStatus);
  const canResume =
    Boolean(onResumeBatch) &&
    latestBatch != null &&
    ['paused', 'partially_failed', 'interrupted'].includes(batchStatus) &&
    canRunLatestPasteBatch;
  const canCancel =
    Boolean(onCancelBatch) &&
    latestBatch != null &&
    !isBatchTerminal(batchStatus);

  return (
    <Card className="gap-4">
      <CardHeader>
        <CardTitle>{t('broadcast.logs.title')}</CardTitle>
        <CardDescription>{t('broadcast.logs.description')}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div
          className="grid gap-4 xl:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]"
          data-testid="broadcast-executor-status-cards"
        >
          <div
            className="rounded-xl border bg-muted/10 p-4"
            data-testid="broadcast-executor-capability-card"
          >
            <div className="text-sm font-medium">
              {t('broadcast.logs.executorCapabilitiesTitle')}
            </div>
            <div className="mt-3 flex flex-wrap gap-2 text-xs">
              <Badge variant="outline">
                {t('broadcast.logs.capabilityPaste')}:{' '}
                {executorCapability?.supports_paste
                  ? t('broadcast.logs.capabilityBooleanYes')
                  : t('broadcast.logs.capabilityBooleanNo')}
              </Badge>
              <Badge
                variant="outline"
                data-testid="broadcast-executor-send-capability"
              >
                {t('broadcast.logs.capabilitySend')}:{' '}
                {executorCapability?.supports_send
                  ? t('broadcast.logs.capabilityBooleanYes')
                  : t('broadcast.logs.capabilityBooleanNo')}
              </Badge>
              <Badge variant="outline">
                {t('broadcast.logs.capabilityCancel')}:{' '}
                {executorCapability?.supports_cancel
                  ? t('broadcast.logs.capabilityBooleanYes')
                  : t('broadcast.logs.capabilityBooleanNo')}
              </Badge>
              <Badge variant="outline">
                {t('broadcast.logs.capabilityStatusQuery')}:{' '}
                {executorCapability?.supports_status_query
                  ? t('broadcast.logs.capabilityBooleanYes')
                  : t('broadcast.logs.capabilityBooleanNo')}
              </Badge>
              <Badge variant="outline">
                {t('broadcast.logs.capabilityPasteVerification')}:{' '}
                {t('broadcast.logs.capabilityBooleanNo')}
              </Badge>
              <Badge variant="outline">
                {t('broadcast.logs.capabilityConversationLocator')}:{' '}
                {t('broadcast.logs.conversationLocatorKeyboardSearch')}
              </Badge>
              <Badge variant="outline">
                {t('broadcast.logs.pasteVerificationMethod')}:{' '}
                {t('broadcast.logs.pasteVerificationUnavailable')}
              </Badge>
              <Badge
                variant={pasteVerificationAvailable ? 'outline' : 'secondary'}
                data-testid="broadcast-executor-paste-verification-status"
              >
                {t('broadcast.logs.pasteVerificationStatus')}:{' '}
                {t('broadcast.logs.pasteVerificationUnavailable')}
              </Badge>
            </div>
            <div className="mt-3 text-xs text-muted-foreground">
              {t('broadcast.logs.executorVersion')}:{' '}
              {executorCapability?.executor_version || '-'} ·
              {` ${t('broadcast.logs.runtimeMinVersion')}: ${executorCapability?.runtime_min_version || '-'}`}
            </div>
          </div>

          <div
            className="rounded-xl border bg-muted/10 p-4"
            data-testid="broadcast-executor-health-card"
          >
            <div className="text-sm font-medium">
              {t('broadcast.logs.executorHealthTitle')}
            </div>
            <div className="mt-3 flex items-center gap-2">
              <Badge
                variant="outline"
                data-testid="broadcast-executor-health-status"
              >
                {executorHealth?.status || 'unknown'}
              </Badge>
              <span className="text-xs text-muted-foreground">
                {t('broadcast.logs.runtimeVersion')}:{' '}
                {executorHealth?.runtime_version || '-'}
              </span>
            </div>
            <div className="mt-3 text-xs text-muted-foreground">
              {t('broadcast.logs.protocolVersion')}:{' '}
              {executorHealth?.protocol_version || '-'}
            </div>
          </div>
        </div>

        {latestBatch ? (
          <div
            className="rounded-xl border bg-muted/10 p-4"
            data-testid="broadcast-latest-execution-batch"
          >
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="space-y-1">
                <div className="text-sm font-medium">
                  {t('broadcast.logs.latestBatchTitle', { id: latestBatch.id })}
                </div>
                <div className="text-xs text-muted-foreground">
                  {t('broadcast.logs.batchSummary', {
                    status: latestBatch.status,
                    mode: latestBatch.mode,
                    pending: latestBatch.pendingTasks,
                    running: latestBatch.runningTasks,
                    succeeded: latestBatch.succeededTasks,
                    failed: latestBatch.failedTasks,
                    cancelled: latestBatch.cancelledTasks,
                    interrupted: latestBatch.interruptedTasks,
                  })}
                </div>
              </div>
              <div className="flex flex-wrap gap-2">
                <Button
                  size="sm"
                  data-testid="broadcast-batch-start-button"
                  onClick={onStartBatch}
                  disabled={busy || !canStart}
                >
                  {t('broadcast.logs.startBatch')}
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  data-testid="broadcast-batch-pause-button"
                  onClick={onPauseBatch}
                  disabled={busy || !canPause}
                >
                  {t('broadcast.logs.pauseBatch')}
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  data-testid="broadcast-batch-resume-button"
                  onClick={onResumeBatch}
                  disabled={busy || !canResume}
                >
                  {t('broadcast.logs.resumeBatch')}
                </Button>
                <Button
                  size="sm"
                  variant="destructive"
                  data-testid="broadcast-batch-cancel-button"
                  onClick={onCancelBatch}
                  disabled={busy || !canCancel}
                >
                  {t('broadcast.logs.cancelBatch')}
                </Button>
              </div>
            </div>

            {latestBatch.mode === 'paste_only' && pasteActionDisabledReason ? (
              <div className="mt-3 rounded-lg border border-amber-300 bg-amber-50 p-3 text-xs text-amber-800">
                {pasteActionDisabledReason}
              </div>
            ) : null}

            <div
              className="mt-4 overflow-x-auto"
              data-testid="broadcast-latest-execution-tasks"
            >
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>{t('broadcast.logs.taskId')}</TableHead>
                    <TableHead>{t('broadcast.fields.action')}</TableHead>
                    <TableHead>{t('broadcast.fields.conversation')}</TableHead>
                    <TableHead>{t('broadcast.fields.status')}</TableHead>
                    <TableHead>{t('broadcast.logs.attemptCount')}</TableHead>
                    <TableHead className="text-right">
                      {t('broadcast.logs.taskActions')}
                    </TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {latestBatch.tasks.map((task) => (
                    <TableRow
                      key={task.id}
                      data-testid={`broadcast-execution-task-row-${task.id}`}
                    >
                      <TableCell>#{task.id}</TableCell>
                      <TableCell>{task.action}</TableCell>
                      <TableCell>{task.targetConversationSnapshot}</TableCell>
                      <TableCell>
                        <Badge variant="outline">{task.status}</Badge>
                      </TableCell>
                      <TableCell>{task.attemptCount}</TableCell>
                      <TableCell className="text-right">
                        {isRetryableTask(task) ? (
                          <Button
                            size="sm"
                            variant="outline"
                            data-testid={`broadcast-execution-task-retry-${task.id}`}
                            disabled={busy || !onRetryTask}
                            onClick={() => onRetryTask?.(task.id)}
                          >
                            {t('broadcast.logs.retryTask')}
                          </Button>
                        ) : (
                          <span className="text-xs text-muted-foreground">
                            —
                          </span>
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </div>
        ) : null}

        <div data-testid="broadcast-execution-logs-table">
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
              {table.getRowModel().rows.length > 0 ? (
                table.getRowModel().rows.map((row) => (
                  <TableRow key={row.id}>
                    {row.getVisibleCells().map((cell) => (
                      <TableCell key={cell.id}>
                        {cell.column.id === 'message' ? (
                          <div>
                            {cell.column.columnDef.cell
                              ? flexRender(
                                  cell.column.columnDef.cell,
                                  cell.getContext(),
                                )
                              : String(cell.getValue() ?? '')}
                            {renderLogEvidence(row.original, t)}
                          </div>
                        ) : cell.column.columnDef.cell ? (
                          flexRender(
                            cell.column.columnDef.cell,
                            cell.getContext(),
                          )
                        ) : (
                          String(cell.getValue() ?? '')
                        )}
                      </TableCell>
                    ))}
                  </TableRow>
                ))
              ) : (
                <TableRow>
                  <TableCell
                    colSpan={columns.length}
                    className="text-center text-muted-foreground"
                  >
                    {t('broadcast.logs.empty')}
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </div>
      </CardContent>
    </Card>
  );
}
