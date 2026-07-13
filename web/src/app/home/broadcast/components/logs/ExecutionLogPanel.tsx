import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  type ColumnDef,
  flexRender,
  getCoreRowModel,
  useReactTable,
} from '@tanstack/react-table';

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
import {
  getExecutionAdviceKey,
  getExecutionBatchActionVisibility,
  getExecutionBatchStatusKey,
  getExecutionLogAdviceCode,
  getExecutionLogStatusKey,
  getExecutionTaskAdviceKey,
  getExecutionTaskStatusKey,
  getRetryableExecutionTasks,
  isRetryableExecutionTask,
} from '../../statusPresentation';

interface ExecutionLogPanelProps {
  logs: BroadcastExecutionLog[];
  latestBatch?: BroadcastExecutionBatchSummary | null;
  executorCapability?: BroadcastExecutorCapability | null;
  executorHealth?: BroadcastExecutorHealth | null;
  executorHealthLoading?: boolean;
  executorHealthMessage?: string | null;
  pasteExecutionAvailable?: boolean;
  pasteVerificationAvailable?: boolean;
  pasteVerificationMethod?:
    | 'windows_uia'
    | 'manual'
    | 'disabled'
    | 'unknown'
    | 'unavailable';
  requiresManualConversationOpen?: boolean;
  pasteActionDisabledReason?: string | null;
  pasteVerificationHint?: string | null;
  busy?: boolean;
  onRecheckExecutorHealth?: () => void;
  onStartBatch?: () => void;
  onPauseBatch?: () => void;
  onResumeBatch?: () => void;
  onCancelBatch?: () => void;
  onRetryTask?: (taskId: number) => void;
  onRetryFailedTasks?: () => void;
}

function formatTimestamp(value: string) {
  return new Date(value).toLocaleString();
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
  const adviceKey = getExecutionAdviceKey(getExecutionLogAdviceCode(log));
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
  items.push({
    label: t('broadcast.logs.fields.batchStatus'),
    value: log.batchStatus,
  });
  items.push({
    label: t('broadcast.logs.fields.taskStatus'),
    value: log.taskStatus,
  });
  items.push({
    label: t('broadcast.logs.fields.attemptStatus'),
    value: log.attemptStatus,
  });
  if (log.runtimeState) {
    items.push({
      label: t('broadcast.logs.fields.runtimeState'),
      value: log.runtimeState,
    });
  }
  if (adviceKey) {
    items.push({
      label: t('broadcast.logs.fields.recoveryAdvice'),
      value: t(adviceKey),
    });
  }

  return (
    <div className="mt-2 space-y-1 text-xs text-muted-foreground">
      {items.map((item, index) => (
        <div key={`${item.label}-${item.value}-${index}`} className="break-all">
          <span className="font-medium text-foreground">{item.label}: </span>
          <span>{item.value}</span>
        </div>
      ))}
    </div>
  );
}

function renderTaskTechnicalDetails(
  task: BroadcastExecutionTaskSummary,
  t: ReturnType<typeof useTranslation>['t'],
) {
  const adviceKey = getExecutionTaskAdviceKey(task);
  return (
    <div className="space-y-1 text-xs text-muted-foreground">
      <div>
        <span className="font-medium text-foreground">
          {t('broadcast.logs.fields.taskStatus')}:
        </span>
        {task.status}
      </div>
      {task.errorCode ? (
        <div>
          <span className="font-medium text-foreground">
            {t('broadcast.logs.fields.errorCode')}:
          </span>
          {task.errorCode}
        </div>
      ) : null}
      {task.errorMessage ? <div>{task.errorMessage}</div> : null}
      {adviceKey ? (
        <div>
          <span className="font-medium text-foreground">
            {t('broadcast.logs.fields.recoveryAdvice')}:
          </span>
          {t(adviceKey)}
        </div>
      ) : null}
    </div>
  );
}

export default function ExecutionLogPanel({
  logs,
  latestBatch,
  executorCapability,
  executorHealth,
  executorHealthLoading = false,
  executorHealthMessage = null,
  pasteExecutionAvailable = false,
  pasteVerificationAvailable = false,
  pasteVerificationMethod = 'unavailable',
  requiresManualConversationOpen: _requiresManualConversationOpen = false,
  pasteActionDisabledReason = null,
  pasteVerificationHint = null,
  busy = false,
  onRecheckExecutorHealth,
  onStartBatch,
  onPauseBatch,
  onResumeBatch,
  onCancelBatch,
  onRetryTask,
  onRetryFailedTasks,
}: ExecutionLogPanelProps) {
  const { t } = useTranslation();
  const [retryFailedDialogOpen, setRetryFailedDialogOpen] = useState(false);
  const pasteVerificationMethodLabel =
    pasteVerificationMethod === 'windows_uia'
      ? t('broadcast.logs.pasteVerificationMethodWindowsUia')
      : pasteVerificationMethod === 'manual'
        ? t('broadcast.logs.pasteVerificationMethodManual')
        : pasteVerificationMethod === 'disabled'
          ? t('broadcast.logs.pasteVerificationMethodDisabled')
          : t('broadcast.logs.pasteVerificationMethodUnknown');
  const pasteVerificationStatusLabel = pasteVerificationAvailable
    ? t('broadcast.logs.pasteVerificationAvailable')
    : t('broadcast.logs.pasteVerificationUnavailable');
  const conversationLocatorLabel =
    executorCapability?.conversation_locator === 'external_id'
      ? t('broadcast.logs.conversationLocatorExternalId')
      : executorCapability?.conversation_locator === 'keyboard_search'
        ? t('broadcast.logs.conversationLocatorKeyboardSearch')
        : t('broadcast.logs.conversationLocatorUnknown');

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
          <Badge
            variant={getLogBadgeVariant(row.original)}
            data-testid={`broadcast-execution-log-status-${row.original.id}`}
          >
            {t(getExecutionLogStatusKey(row.original))}
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

  const canRunLatestPasteBatch =
    latestBatch?.mode === 'paste_only' ? pasteExecutionAvailable : true;
  const batchActions = getExecutionBatchActionVisibility(latestBatch);
  const retryableTasks = getRetryableExecutionTasks(latestBatch);
  const canStart =
    Boolean(onStartBatch) && batchActions.start && canRunLatestPasteBatch;
  const canPause = Boolean(onPauseBatch) && batchActions.pause;
  const canResume =
    Boolean(onResumeBatch) && batchActions.resume && canRunLatestPasteBatch;
  const canCancel = Boolean(onCancelBatch) && batchActions.cancel;
  const canRetryFailedTasks =
    Boolean(onRetryFailedTasks) && batchActions.retryFailed;

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
                {executorCapability?.supports_paste_verification
                  ? t('broadcast.logs.capabilityBooleanYes')
                  : t('broadcast.logs.capabilityBooleanNo')}
              </Badge>
              <Badge variant="outline">
                {t('broadcast.logs.capabilityConversationLocator')}:{' '}
                {conversationLocatorLabel}
              </Badge>
              <Badge variant="outline">
                {t('broadcast.logs.pasteVerificationMethod')}:{' '}
                {pasteVerificationMethodLabel}
              </Badge>
              <Badge
                variant={pasteVerificationAvailable ? 'outline' : 'secondary'}
                data-testid="broadcast-executor-paste-verification-status"
              >
                {t('broadcast.logs.pasteVerificationStatus')}:{' '}
                {pasteVerificationStatusLabel}
              </Badge>
            </div>
            <div className="mt-3 text-xs text-muted-foreground">
              {t('broadcast.logs.executorVersion')}:{' '}
              {executorCapability?.executor_version || '-'}
              {` ${t('broadcast.logs.runtimeMinVersion')}: ${executorCapability?.runtime_min_version || '-'}`}
            </div>
            {pasteActionDisabledReason ? (
              <div className="mt-3 text-xs text-muted-foreground">
                {pasteActionDisabledReason}
              </div>
            ) : null}
            {pasteVerificationHint ? (
              <div
                className="mt-2 text-xs text-muted-foreground"
                data-testid="broadcast-paste-verification-hint"
              >
                {pasteVerificationHint}
              </div>
            ) : null}
          </div>

          <div
            className="rounded-xl border bg-muted/10 p-4"
            data-testid="broadcast-executor-health-card"
          >
            <div className="flex items-center justify-between gap-3">
              <div className="text-sm font-medium">
                {t('broadcast.logs.executorHealthTitle')}
              </div>
              {onRecheckExecutorHealth ? (
                <Button
                  size="sm"
                  variant="outline"
                  data-testid="broadcast-executor-health-recheck-button"
                  disabled={busy || executorHealthLoading}
                  onClick={onRecheckExecutorHealth}
                >
                  {t('broadcast.executor.recheck')}
                </Button>
              ) : null}
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
            {executorHealthMessage ? (
              <div className="mt-3 text-xs text-muted-foreground">
                {executorHealthMessage}
              </div>
            ) : null}
          </div>
        </div>

        {latestBatch ? (
          <div
            className="sticky top-0 z-10 rounded-xl border bg-background/95 p-4 backdrop-blur supports-[backdrop-filter]:bg-background/80"
            data-testid="broadcast-latest-execution-batch"
          >
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="space-y-1">
                <div className="text-sm font-medium">
                  {t('broadcast.logs.latestBatchTitle', { id: latestBatch.id })}
                </div>
                <div className="text-xs text-muted-foreground">
                  {t('broadcast.logs.batchSummary', {
                    status: t(getExecutionBatchStatusKey(latestBatch.status)),
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
              <div
                className="flex flex-wrap gap-2"
                data-testid="broadcast-log-sticky-actions"
              >
                {batchActions.start ? (
                  <Button
                    size="sm"
                    data-testid="broadcast-batch-start-button"
                    onClick={onStartBatch}
                    disabled={busy || !canStart}
                  >
                    {t('broadcast.logs.startBatch')}
                  </Button>
                ) : null}
                {batchActions.pause ? (
                  <Button
                    size="sm"
                    variant="outline"
                    data-testid="broadcast-batch-pause-button"
                    onClick={onPauseBatch}
                    disabled={busy || !canPause}
                  >
                    {t('broadcast.logs.pauseBatch')}
                  </Button>
                ) : null}
                {batchActions.resume ? (
                  <Button
                    size="sm"
                    variant="outline"
                    data-testid="broadcast-batch-resume-button"
                    onClick={onResumeBatch}
                    disabled={busy || !canResume}
                  >
                    {t('broadcast.logs.resumeBatch')}
                  </Button>
                ) : null}
                {batchActions.cancel ? (
                  <Button
                    size="sm"
                    variant="destructive"
                    data-testid="broadcast-batch-cancel-button"
                    onClick={onCancelBatch}
                    disabled={busy || !canCancel}
                  >
                    {t('broadcast.logs.cancelBatch')}
                  </Button>
                ) : null}
                {batchActions.retryFailed ? (
                  <Button
                    size="sm"
                    variant="outline"
                    data-testid="broadcast-batch-retry-failed-button"
                    onClick={() => setRetryFailedDialogOpen(true)}
                    disabled={busy || !canRetryFailedTasks}
                  >
                    {t('broadcast.logs.retryFailedTasks')}
                  </Button>
                ) : null}
              </div>
            </div>

            <div className="mt-3 space-y-2">
              {latestBatch.mode === 'paste_only' &&
              pasteActionDisabledReason ? (
                <div className="rounded-lg border border-amber-300 bg-amber-50 p-3 text-xs text-amber-800">
                  {pasteActionDisabledReason}
                </div>
              ) : null}
              {latestBatch.mode === 'paste_only' && pasteVerificationHint ? (
                <div className="rounded-lg border bg-muted/20 p-3 text-xs text-muted-foreground">
                  {pasteVerificationHint}
                </div>
              ) : null}
            </div>

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
                        <div className="space-y-2">
                          <Badge
                            variant="outline"
                            data-testid={`broadcast-execution-task-status-${task.id}`}
                          >
                            {t(getExecutionTaskStatusKey(task.status))}
                          </Badge>
                          {renderTaskTechnicalDetails(task, t)}
                        </div>
                      </TableCell>
                      <TableCell>{task.attemptCount}</TableCell>
                      <TableCell className="text-right">
                        {isRetryableExecutionTask(task) ? (
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
                            ?
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
      <AlertDialog
        open={retryFailedDialogOpen}
        onOpenChange={setRetryFailedDialogOpen}
      >
        <AlertDialogContent data-testid="broadcast-batch-retry-failed-confirm-dialog">
          <AlertDialogHeader>
            <AlertDialogTitle>
              {t('broadcast.logs.retryFailedTasksConfirmTitle')}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {t('broadcast.logs.retryFailedTasksConfirmDescription', {
                count: retryableTasks.length,
              })}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('common.cancel')}</AlertDialogCancel>
            <AlertDialogAction
              data-testid="broadcast-batch-retry-failed-confirm-button"
              onClick={(event) => {
                event.preventDefault();
                onRetryFailedTasks?.();
                setRetryFailedDialogOpen(false);
              }}
            >
              {t('broadcast.logs.retryFailedTasks')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Card>
  );
}
