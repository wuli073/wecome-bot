import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { httpClient } from '@/app/infra/http/HttpClient';
import type {
  MCPServer,
  LocalConnectorJob,
  LocalConnectorStatus,
} from '@/app/infra/entities/api';
import {
  Bot,
  Database,
  Loader2,
  RefreshCcw,
  Server,
  ShieldCheck,
  Terminal,
  Wrench,
} from 'lucide-react';
import { toast } from 'sonner';

const ACTIVE_STAGES = new Set([
  'detecting',
  'extracting_key',
  'decrypting',
  'starting_mcp',
  'testing_mcp',
  'enabling_mcp',
]);

function StatusBadge({
  label,
  tone,
}: {
  label: string;
  tone: 'default' | 'success' | 'warning' | 'danger';
}) {
  const className =
    tone === 'success'
      ? 'border-green-200 bg-green-50 text-green-700 dark:border-green-900/70 dark:bg-green-950/40 dark:text-green-300'
      : tone === 'warning'
        ? 'border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-900/70 dark:bg-amber-950/40 dark:text-amber-300'
        : tone === 'danger'
          ? 'border-red-200 bg-red-50 text-red-700 dark:border-red-900/70 dark:bg-red-950/40 dark:text-red-300'
          : 'border-muted-foreground/20 bg-muted text-muted-foreground';

  return (
    <Badge variant="outline" className={`gap-1.5 ${className}`}>
      {label}
    </Badge>
  );
}

export default function BuiltinConnectorDetail({
  serverName,
  connectorId,
}: {
  serverName: string;
  connectorId: string;
}) {
  const { t } = useTranslation();
  const [server, setServer] = useState<MCPServer | null>(null);
  const [connector, setConnector] = useState<LocalConnectorStatus | null>(null);
  const [job, setJob] = useState<LocalConnectorJob | null>(null);
  const [logs, setLogs] = useState('');
  const [loading, setLoading] = useState(true);
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [showLogs, setShowLogs] = useState(false);

  const loadData = useCallback(async () => {
    const [serverResp, connectorResp, logsResp] = await Promise.all([
      httpClient.getMCPServer(serverName),
      httpClient.getLocalConnectorStatus(connectorId),
      httpClient.getLocalConnectorLogs(connectorId),
    ]);

    const nextServer = serverResp.server ?? serverResp;
    const nextConnector = connectorResp.connector;
    setServer(nextServer);
    setConnector(nextConnector);
    setLogs(logsResp.logs ?? '');

    if (nextConnector.job_id) {
      const jobResp = await httpClient.getLocalConnectorJob(nextConnector.job_id);
      setJob(jobResp.job);
    } else {
      setJob(null);
    }
  }, [connectorId, serverName]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    loadData()
      .catch((error) => {
        console.error('Failed to load builtin connector detail:', error);
        toast.error(t('mcp.loadFailed'));
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [loadData, t]);

  const isBusy = !!busyAction;
  const activeJob = connector?.job_status === 'running' || (job && ACTIVE_STAGES.has(job.stage));

  useEffect(() => {
    if (!activeJob) {
      return;
    }
    const timer = window.setInterval(() => {
      loadData().catch((error) => {
        console.error('Failed to refresh builtin connector detail:', error);
      });
    }, 2000);
    return () => window.clearInterval(timer);
  }, [activeJob, loadData]);

  const withAction = useCallback(
    async (action: string, runner: () => Promise<unknown>, successMessage: string) => {
      setBusyAction(action);
      try {
        await runner();
        toast.success(successMessage);
        await loadData();
      } catch (error) {
        console.error(`Builtin connector action failed: ${action}`, error);
        const message = (error as { msg?: string; message?: string }).msg || (error as Error).message || '';
        toast.error(message || t('mcp.modifyFailed'));
      } finally {
        setBusyAction(null);
      }
    },
    [loadData, t],
  );

  const runtimeTone = useMemo(() => {
    if (!server?.enable) return 'default';
    if (server.runtime_info?.status === 'connected') return 'success';
    if (server.runtime_info?.status === 'connecting') return 'warning';
    if (server.runtime_info?.status === 'error') return 'danger';
    return 'default';
  }, [server]);

  const connectorTone = useMemo(() => {
    if (!connector) return 'default';
    if (connector.status === 'connected') return 'success';
    if (connector.status === 'unsupported_platform') return 'danger';
    if (connector.status === 'port_in_use' || connector.status.endsWith('_failed')) return 'danger';
    if (ACTIVE_STAGES.has(connector.status)) return 'warning';
    return 'default';
  }, [connector]);

  const monitorTone = useMemo(() => {
    if (!connector?.monitor?.enabled) return 'default';
    if (connector.monitor.running_status === 'error') return 'danger';
    if (!connector.monitor.warmup_completed) return 'warning';
    if (connector.monitor.owned) return 'success';
    return 'default';
  }, [connector]);

  const formatConnectorStatus = (value?: string | null) => {
    if (!value) return t('mcp.statusDisconnected');
    const map: Record<string, string> = {
      unsupported_platform: t('mcp.unsupportedPlatform'),
      not_configured: t('mcp.notConfigured'),
      client_not_running: t('mcp.clientNotRunning'),
      data_path_not_found: t('mcp.dataPathNotFound'),
      permission_required: t('mcp.permissionRequired'),
      port_in_use: t('mcp.portInUse'),
      decrypt_failed: t('mcp.decryptFailed'),
      start_failed: t('mcp.startFailed'),
      runtime_error: t('mcp.runtimeError'),
      stopped: t('mcp.workerStopped'),
      connected: t('mcp.statusConnected'),
      detecting: t('mcp.stageDetecting'),
      extracting_key: t('mcp.stageExtractingKey'),
      decrypting: t('mcp.stageDecrypting'),
      starting_mcp: t('mcp.stageStartingMcp'),
      testing_mcp: t('mcp.stageTestingMcp'),
      enabling_mcp: t('mcp.stageEnablingMcp'),
    };
    return map[value] ?? value;
  };

  const formatJobStatus = (value?: string | null) => {
    if (!value) return t('mcp.statusDisconnected');
    const map: Record<string, string> = {
      pending: t('mcp.jobPending'),
      running: t('mcp.jobRunning'),
      succeeded: t('mcp.jobSucceeded'),
      failed: t('mcp.jobFailed'),
      cancelled: t('mcp.jobCancelled'),
    };
    return map[value] ?? value;
  };

  if (loading || !server || !connector) {
    return (
      <div className="flex h-full items-center justify-center text-muted-foreground">
        <Loader2 className="mr-2 size-5 animate-spin" />
        {t('mcp.loading')}
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col gap-4 overflow-y-auto pb-6">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div className="space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-xl font-semibold">{server.name}</h1>
            <Badge variant="outline" className="gap-1.5 text-[0.7rem]">
              <ShieldCheck className="size-3.5" />
              {t('mcp.builtin')}
            </Badge>
            <StatusBadge
              label={formatConnectorStatus(connector.status)}
              tone={connectorTone}
            />
            <StatusBadge
              label={
                server.enable
                  ? server.runtime_info?.status === 'connected'
                    ? t('mcp.statusConnected')
                    : server.runtime_info?.status === 'connecting'
                      ? t('mcp.connecting')
                      : server.runtime_info?.status === 'error'
                        ? t('mcp.statusError')
                        : t('mcp.statusDisconnected')
                  : t('mcp.statusDisabled')
              }
              tone={runtimeTone}
            />
          </div>
          <p className="text-sm text-muted-foreground">
            {t('mcp.builtinLockedHint')}
          </p>
        </div>

        <div className="flex flex-wrap gap-2">
          <Button
            variant="outline"
            disabled={isBusy}
            onClick={() =>
              withAction(
                'detect',
                () => httpClient.detectLocalConnector(connectorId),
                t('mcp.refreshSuccess'),
              )
            }
          >
            {busyAction === 'detect' ? (
              <Loader2 className="mr-2 size-4 animate-spin" />
            ) : (
              <Bot className="mr-2 size-4" />
            )}
            {t('mcp.detectClient')}
          </Button>
          <Button
            variant="outline"
            disabled={isBusy || !connector.keys_file}
            onClick={() =>
              withAction(
                'refresh',
                () => httpClient.refreshLocalConnector(connectorId),
                t('mcp.refreshSuccess'),
              )
            }
          >
            {busyAction === 'refresh' ? (
              <Loader2 className="mr-2 size-4 animate-spin" />
            ) : (
              <Database className="mr-2 size-4" />
            )}
            {t('mcp.refreshDatabase')}
          </Button>
          <Button
            disabled={isBusy}
            onClick={() =>
              withAction(
                'setup',
                () => httpClient.setupLocalConnector(connectorId),
                t('mcp.saveSuccess'),
              )
            }
          >
            {busyAction === 'setup' ? (
              <Loader2 className="mr-2 size-4 animate-spin" />
            ) : (
              <Wrench className="mr-2 size-4" />
            )}
            {connector.keys_file ? t('mcp.reconfigure') : t('mcp.oneClickSetup')}
          </Button>
        </div>
      </div>

      <div className="grid gap-4 xl:grid-cols-[1.2fr_0.8fr]">
        <Card>
          <CardHeader>
            <CardTitle>{t('mcp.connectorStatusTitle')}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-center justify-between rounded-md border p-3">
              <div>
                <Label htmlFor="builtin-enable-switch">{t('common.enable')}</Label>
                <p className="text-sm text-muted-foreground">
                  {t('mcp.localConnector')}
                </p>
              </div>
              <Switch
                id="builtin-enable-switch"
                checked={!!server.enable}
                disabled={isBusy}
                onCheckedChange={(checked) =>
                  withAction(
                    'toggle-enable',
                    () => httpClient.toggleMCPServer(server.name, checked),
                    t('mcp.saveSuccess'),
                  )
                }
              />
            </div>

            <div className="grid gap-3 md:grid-cols-2">
              <div className="rounded-md border p-3">
                <div className="text-sm text-muted-foreground">{t('mcp.jobStatus')}</div>
                <div className="mt-1 font-medium">{formatJobStatus(job?.status ?? connector.job_status)}</div>
              </div>
              <div className="rounded-md border p-3">
                <div className="text-sm text-muted-foreground">{t('mcp.jobStage')}</div>
                <div className="mt-1 font-medium">{formatConnectorStatus(job?.stage ?? connector.status)}</div>
              </div>
              <div className="rounded-md border p-3">
                <div className="text-sm text-muted-foreground">{t('mcp.toolCount', { count: connector.tool_count })}</div>
                <div className="mt-1 font-medium">
                  {connector.tool_count} / {connector.expected_tool_count}
                </div>
              </div>
              <div className="rounded-md border p-3">
                <div className="text-sm text-muted-foreground">{t('mcp.worker')}</div>
                <div className="mt-1 font-medium">
                  {connector.worker.owned
                    ? `PID ${connector.worker.pid} / ${connector.worker.port}`
                    : t('mcp.workerStopped')}
                </div>
              </div>
            </div>

            {(job || connector.last_error_code || connector.last_error_message) && (
              <div className="rounded-md border border-red-200 bg-red-50/60 p-3 text-sm dark:border-red-900/60 dark:bg-red-950/30">
                {job?.progress ? (
                  <div className="mb-2 font-medium">
                    {t('mcp.jobProgress', { progress: job.progress })}
                  </div>
                ) : null}
                {connector.last_error_code && (
                  <div className="font-medium">{connector.last_error_code}</div>
                )}
                {connector.last_error_message && (
                  <div className="mt-1 text-muted-foreground">
                    {connector.last_error_message}
                  </div>
                )}
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>{t('mcp.workerControl')}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="flex flex-wrap gap-2">
              <Button
                variant="outline"
                disabled={isBusy || connector.worker.owned}
                onClick={() =>
                  withAction(
                    'start-worker',
                    () => httpClient.startLocalConnectorWorker(connectorId),
                    t('mcp.saveSuccess'),
                  )
                }
              >
                <Server className="mr-2 size-4" />
                {t('mcp.startWorker')}
              </Button>
              <Button
                variant="outline"
                disabled={isBusy || !connector.worker.owned}
                onClick={() =>
                  withAction(
                    'stop-worker',
                    () => httpClient.stopLocalConnectorWorker(connectorId),
                    t('mcp.saveSuccess'),
                  )
                }
              >
                <Server className="mr-2 size-4" />
                {t('mcp.stopWorker')}
              </Button>
              <Button
                variant="outline"
                disabled={isBusy}
                onClick={() => {
                  setShowLogs((value) => !value);
                  if (!showLogs) {
                    loadData().catch(() => {});
                  }
                }}
              >
                <Terminal className="mr-2 size-4" />
                {showLogs ? t('mcp.hideLogs') : t('mcp.viewLogs')}
              </Button>
            </div>
            <div className="text-sm text-muted-foreground">
              {connector.status === 'unsupported_platform'
                ? t('mcp.unsupportedPlatformHint')
                : t('mcp.builtinConnectorDescription')}
            </div>
          </CardContent>
        </Card>
      </div>

      {connectorId === 'wxwork-local' && connector.monitor && (
        <Card>
          <CardHeader>
            <CardTitle>{t('databaseMode.monitorPanelTitle')}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex flex-wrap items-center gap-2">
              <StatusBadge
                label={
                  connector.monitor.enabled
                    ? connector.monitor.warmup_completed
                      ? connector.monitor.owned
                        ? t('databaseMode.monitorRunning')
                        : t('databaseMode.monitorStopped')
                      : t('databaseMode.warmupTitle')
                    : t('databaseMode.monitorStoppedTitle')
                }
                tone={monitorTone}
              />
              {connector.monitor.last_error ? (
                <Badge variant="outline" className="border-red-200 bg-red-50 text-red-700 dark:border-red-900/70 dark:bg-red-950/40 dark:text-red-300">
                  {t('databaseMode.monitorErrorShort')}
                </Badge>
              ) : null}
            </div>

            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
              <div className="rounded-md border p-3">
                <div className="text-sm text-muted-foreground">{t('databaseMode.monitorRunning')}</div>
                <div className="mt-1 font-medium">
                  {connector.monitor.owned ? `PID ${connector.monitor.pid}` : t('databaseMode.monitorStopped')}
                </div>
              </div>
              <div className="rounded-md border p-3">
                <div className="text-sm text-muted-foreground">{t('databaseMode.warmupTitle')}</div>
                <div className="mt-1 font-medium">
                  {connector.monitor.warmup_completed
                    ? t('databaseMode.warmupCompleted')
                    : t('databaseMode.warmupPending')}
                </div>
              </div>
              <div className="rounded-md border p-3">
                <div className="text-sm text-muted-foreground">{t('databaseMode.monitorPollSeconds')}</div>
                <div className="mt-1 font-medium">{connector.monitor.poll_seconds ?? '--'}</div>
              </div>
              <div className="rounded-md border p-3">
                <div className="text-sm text-muted-foreground">{t('databaseMode.monitorOutboxPending')}</div>
                <div className="mt-1 font-medium">{connector.monitor.outbox_pending}</div>
              </div>
              <div className="rounded-md border p-3">
                <div className="text-sm text-muted-foreground">{t('databaseMode.monitorLastScan')}</div>
                <div className="mt-1 text-sm">{connector.monitor.last_scan_at || '--'}</div>
              </div>
              <div className="rounded-md border p-3">
                <div className="text-sm text-muted-foreground">{t('databaseMode.monitorLastChange')}</div>
                <div className="mt-1 text-sm">{connector.monitor.last_change_at || '--'}</div>
              </div>
              <div className="rounded-md border p-3">
                <div className="text-sm text-muted-foreground">{t('databaseMode.monitorLastEvent')}</div>
                <div className="mt-1 text-sm">{connector.monitor.last_event_at || '--'}</div>
              </div>
              <div className="rounded-md border p-3">
                <div className="text-sm text-muted-foreground">{t('databaseMode.monitorErrorLabel')}</div>
                <div className="mt-1 text-sm">{connector.monitor.last_error || '--'}</div>
              </div>
            </div>

            <div className="flex flex-wrap gap-2">
              <Button
                variant="outline"
                disabled={isBusy || !connector.keys_file || connector.monitor.owned}
                onClick={() =>
                  withAction(
                    'start-monitor',
                    () => httpClient.startLocalConnectorMonitor(),
                    t('mcp.saveSuccess'),
                  )
                }
              >
                <Database className="mr-2 size-4" />
                {t('databaseMode.startMonitor')}
              </Button>
              <Button
                variant="outline"
                disabled={isBusy || !connector.monitor.owned}
                onClick={() =>
                  withAction(
                    'stop-monitor',
                    () => httpClient.stopLocalConnectorMonitor(),
                    t('mcp.saveSuccess'),
                  )
                }
              >
                <Database className="mr-2 size-4" />
                {t('databaseMode.stopMonitor')}
              </Button>
              <Button
                variant="outline"
                disabled={isBusy || !connector.keys_file}
                onClick={() =>
                  withAction(
                    'restart-monitor',
                    () => httpClient.restartLocalConnectorMonitor(),
                    t('mcp.saveSuccess'),
                  )
                }
              >
                <RefreshCcw className="mr-2 size-4" />
                {t('databaseMode.restartMonitor')}
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {showLogs && (
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle>{t('mcp.logs')}</CardTitle>
            <Button
              variant="ghost"
              size="sm"
              disabled={isBusy}
              onClick={() =>
                withAction('refresh-logs', async () => loadData(), t('mcp.refreshSuccess'))
              }
            >
              <RefreshCcw className="mr-2 size-4" />
              {t('monitoring.refreshData')}
            </Button>
          </CardHeader>
          <CardContent>
            <pre className="max-h-[360px] overflow-auto rounded-md bg-muted p-3 text-xs whitespace-pre-wrap break-all">
              {logs || t('mcp.noLogs')}
            </pre>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
