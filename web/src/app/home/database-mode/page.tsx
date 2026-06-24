import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import {
  DatabaseModeConversation,
  DatabaseModeMessage,
  DatabaseModeConversationStats,
  LocalConnectorStatus,
} from '@/app/infra/entities/api';
import { httpClient } from '@/app/infra/http/HttpClient';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Checkbox } from '@/components/ui/checkbox';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { ScrollArea } from '@/components/ui/scroll-area';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Separator } from '@/components/ui/separator';
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from '@/components/ui/sheet';
import { Textarea } from '@/components/ui/textarea';
import { toast } from 'sonner';
import {
  ArrowRight,
  CheckCheck,
  Database,
  Loader2,
  Menu,
  RefreshCcw,
  SkipForward,
  Trash2,
  WandSparkles,
} from 'lucide-react';

const CONVERSATION_STATUS_OPTIONS = ['all', 'pending', 'draft_ready', 'failed', 'processed', 'skipped'] as const;
const MESSAGE_STATUS_OPTIONS = ['all', 'pending', 'draft_ready', 'failed', 'processed', 'skipped'] as const;

function statusTone(status: string): string {
  switch (status) {
    case 'pending':
      return 'border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-900/70 dark:bg-amber-950/40 dark:text-amber-300';
    case 'draft_ready':
      return 'border-sky-200 bg-sky-50 text-sky-700 dark:border-sky-900/70 dark:bg-sky-950/40 dark:text-sky-300';
    case 'failed':
      return 'border-red-200 bg-red-50 text-red-700 dark:border-red-900/70 dark:bg-red-950/40 dark:text-red-300';
    case 'processed':
      return 'border-green-200 bg-green-50 text-green-700 dark:border-green-900/70 dark:bg-green-950/40 dark:text-green-300';
    case 'skipped':
      return 'border-muted-foreground/30 bg-muted text-muted-foreground';
    default:
      return 'border-muted-foreground/20 bg-muted text-muted-foreground';
  }
}

function EmptyState({
  title,
  description,
  action,
}: {
  title: string;
  description: string;
  action?: React.ReactNode;
}) {
  return (
    <Card className="mx-auto max-w-2xl">
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        <CardDescription>{description}</CardDescription>
      </CardHeader>
      {action ? <CardContent>{action}</CardContent> : null}
    </Card>
  );
}

function StatsCards({
  stats,
  t,
}: {
  stats: DatabaseModeConversationStats | null;
  t: (key: string) => string;
}) {
  const items = [
    ['pending', t('databaseMode.statusPending')],
    ['draft_ready', t('databaseMode.statusDraftReady')],
    ['failed', t('databaseMode.statusFailed')],
    ['processed', t('databaseMode.statusProcessed')],
    ['skipped', t('databaseMode.statusSkipped')],
  ] as const;
  return (
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
      {items.map(([key, label]) => (
        <Card key={key}>
          <CardContent className="flex items-center justify-between p-4">
            <div>
              <p className="text-xs uppercase tracking-wide text-muted-foreground">
                {label}
              </p>
              <p className="mt-1 text-2xl font-semibold">{stats?.[key] ?? 0}</p>
            </div>
            <Badge variant="outline" className={statusTone(key)}>
              {key}
            </Badge>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

export default function DatabaseModePage() {
  const { t } = useTranslation();
  const [connector, setConnector] = useState<LocalConnectorStatus | null>(null);
  const [conversations, setConversations] = useState<DatabaseModeConversation[]>([]);
  const [selectedConversation, setSelectedConversation] = useState<{
    id: number;
    connector_id: string;
    source: string;
    external_conversation_id: string;
    conversation_name: string;
    conversation_type: string;
    last_message_at?: string | null;
    created_at?: string | null;
    updated_at?: string | null;
    stats: DatabaseModeConversationStats;
    latest_customer: string;
  } | null>(null);
  const [selectedConversationId, setSelectedConversationId] = useState<number | null>(null);
  const [messages, setMessages] = useState<DatabaseModeMessage[]>([]);
  const [stats, setStats] = useState<DatabaseModeConversationStats | null>(null);
  const [selectedMessageIds, setSelectedMessageIds] = useState<number[]>([]);
  const [draftEdits, setDraftEdits] = useState<Record<number, string>>({});
  const [keyword, setKeyword] = useState('');
  const [conversationStatus, setConversationStatus] = useState('all');
  const [messageStatus, setMessageStatus] = useState('all');
  const [loading, setLoading] = useState(true);
  const [busyKey, setBusyKey] = useState<string | null>(null);
  const [error, setError] = useState('');
  const [detailsMessage, setDetailsMessage] = useState<DatabaseModeMessage | null>(null);

  const connectorDetailHref = useMemo(
    () => `/home/mcp?id=${encodeURIComponent(connector?.name ?? '浼佷笟寰俊')}`,
    [connector?.name],
  );
  const connectorConfigured = useMemo(
    () => connector?.status !== 'not_configured' && connector?.status !== 'unsupported_platform',
    [connector?.status],
  );

  const loadConnector = useCallback(async () => {
    const response = await httpClient.getLocalConnectorStatus('wxwork-local');
    setConnector(response.connector);
  }, []);

  const loadConversations = useCallback(async () => {
    const response = await httpClient.getDatabaseModeConversations({
      keyword,
      status: conversationStatus,
      page: 1,
      page_size: 100,
    });
    setConversations(response.conversations);
    if (
      response.conversations.length > 0 &&
      !response.conversations.some((item) => item.id === selectedConversationId)
    ) {
      setSelectedConversationId(response.conversations[0].id);
    }
    if (response.conversations.length === 0) {
      setSelectedConversationId(null);
      setSelectedConversation(null);
      setMessages([]);
      setStats(null);
    }
  }, [conversationStatus, keyword, selectedConversationId]);

  const loadMessages = useCallback(
    async (conversationId: number) => {
      const [conversationResp, messagesResp] = await Promise.all([
        httpClient.getDatabaseModeConversation(conversationId),
        httpClient.getDatabaseModeMessages(conversationId, {
          status: messageStatus,
          page: 1,
          page_size: 200,
        }),
      ]);
      setSelectedConversation(conversationResp.conversation);
      setMessages(messagesResp.messages);
      setStats(messagesResp.stats);
      setSelectedMessageIds((current) =>
        current.filter((messageId) =>
          messagesResp.messages.some((message) => message.id === messageId),
        ),
      );
    },
    [messageStatus],
  );

  const reloadAll = useCallback(async () => {
    setError('');
    setLoading(true);
    try {
      await loadConnector();
      await loadConversations();
    } catch (err) {
      setError((err as { msg?: string }).msg || t('databaseMode.loadFailed'));
    } finally {
      setLoading(false);
    }
  }, [loadConnector, loadConversations, t]);

  useEffect(() => {
    reloadAll().catch(() => undefined);
  }, [reloadAll]);

  useEffect(() => {
    if (!selectedConversationId) {
      return;
    }
    loadMessages(selectedConversationId).catch((err) => {
      setError((err as { msg?: string }).msg || t('databaseMode.loadFailed'));
    });
  }, [loadMessages, selectedConversationId, t]);

  useEffect(() => {
    if (!connector?.monitor?.enabled) {
      return;
    }
    const timer = window.setInterval(() => {
      loadConnector().catch(() => undefined);
    }, 5000);
    return () => window.clearInterval(timer);
  }, [connector?.monitor?.enabled, loadConnector]);

  const withBusy = useCallback(
    async (key: string, action: () => Promise<void>) => {
      setBusyKey(key);
      try {
        await action();
      } catch (err) {
        toast.error((err as { msg?: string }).msg || t('databaseMode.operationFailed'));
      } finally {
        setBusyKey(null);
      }
    },
    [t],
  );

  const refreshSelection = useCallback(async () => {
    await loadConversations();
    await loadConnector();
    if (selectedConversationId) {
      await loadMessages(selectedConversationId);
    }
  }, [loadConversations, loadConnector, loadMessages, selectedConversationId]);

  const conversationList = (
    <div className="flex h-full flex-col gap-3">
      <div className="space-y-3">
        <Input
          value={keyword}
          onChange={(event) => setKeyword(event.target.value)}
          placeholder={t('databaseMode.searchPlaceholder')}
        />
        <Select value={conversationStatus} onValueChange={setConversationStatus}>
          <SelectTrigger>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {CONVERSATION_STATUS_OPTIONS.map((status) => (
              <SelectItem key={status} value={status}>
                {t(`databaseMode.filter.${status}`)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <ScrollArea className="min-h-0 flex-1 rounded-lg border">
        <div className="space-y-2 p-2">
          {conversations.map((conversation) => (
            <button
              key={conversation.id}
              type="button"
              onClick={() => setSelectedConversationId(conversation.id)}
              className={`w-full rounded-lg border p-3 text-left transition-colors ${
                conversation.id === selectedConversationId
                  ? 'border-blue-500 bg-blue-50 dark:bg-blue-950/30'
                  : 'hover:bg-muted/60'
              }`}
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="truncate font-medium">{conversation.conversation_name}</p>
                  <p className="truncate text-xs text-muted-foreground">
                    {conversation.latest_customer || t('databaseMode.noCustomer')}
                  </p>
                </div>
                <Badge variant="outline">{conversation.pending_count}</Badge>
              </div>
              <p className="mt-2 line-clamp-2 text-sm text-muted-foreground">
                {conversation.latest_message_summary || t('databaseMode.noMessages')}
              </p>
              <div className="mt-3 flex items-center justify-between text-xs text-muted-foreground">
                <span>{conversation.last_message_at || '--'}</span>
                <span>
                  {t('databaseMode.failedShort')}: {conversation.failed_count}
                </span>
              </div>
            </button>
          ))}
        </div>
      </ScrollArea>
    </div>
  );

  if (loading && !connector) {
    return (
      <div className="flex h-full items-center justify-center text-muted-foreground">
        <Loader2 className="mr-2 size-5 animate-spin" />
        {t('databaseMode.loading')}
      </div>
    );
  }

  if (error) {
    return (
      <EmptyState
        title={t('databaseMode.loadFailed')}
        description={error}
        action={
          <Button variant="outline" onClick={() => reloadAll().catch(() => undefined)}>
            <RefreshCcw className="mr-2 size-4" />
            {t('common.retry')}
          </Button>
        }
      />
    );
  }

  if (!connectorConfigured) {
    return (
      <EmptyState
        title={t('databaseMode.notConfiguredTitle')}
        description={t('databaseMode.notConfiguredDescription')}
        action={
          <Button asChild>
            <Link to={connectorDetailHref}>
              <ArrowRight className="mr-2 size-4" />
              {t('databaseMode.goToConnector')}
            </Link>
          </Button>
        }
      />
    );
  }

  const monitor = connector?.monitor;

  if (!monitor?.enabled || !monitor.owned) {
    return (
      <EmptyState
        title={t('databaseMode.monitorStoppedTitle')}
        description={t('databaseMode.monitorStoppedDescription')}
        action={
          <div className="flex flex-wrap gap-2">
            <Button
              onClick={() =>
                withBusy('start-monitor', async () => {
                  await httpClient.startLocalConnectorMonitor();
                  await refreshSelection();
                })
              }
            >
              {busyKey === 'start-monitor' ? (
                <Loader2 className="mr-2 size-4 animate-spin" />
              ) : (
                <Database className="mr-2 size-4" />
              )}
              {t('databaseMode.startMonitor')}
            </Button>
            <Button variant="outline" asChild>
              <Link to={connectorDetailHref}>{t('databaseMode.goToConnector')}</Link>
            </Button>
          </div>
        }
      />
    );
  }

  if (
    monitor.running_status === 'warming_up' ||
    !monitor.warmup_completed
  ) {
    return (
      <EmptyState
        title={t('databaseMode.warmupTitle')}
        description={t('databaseMode.warmupDescription')}
      />
    );
  }

  if (monitor.running_status === 'error') {
    return (
      <EmptyState
        title={t('databaseMode.monitorErrorTitle')}
        description={t('databaseMode.monitorErrorDescription')}
        action={
          <Button variant="outline" asChild>
            <Link to={connectorDetailHref}>{t('databaseMode.goToConnector')}</Link>
          </Button>
        }
      />
    );
  }

  return (
    <div className="flex h-full min-h-0 gap-4">
      <aside className="hidden w-[320px] shrink-0 md:block">{conversationList}</aside>

      <div className="flex min-w-0 flex-1 flex-col gap-4">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h1 className="text-xl font-semibold">{t('databaseMode.title')}</h1>
            <p className="text-sm text-muted-foreground">
              {t('databaseMode.workspaceDescription')}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Sheet>
              <SheetTrigger asChild>
                <Button variant="outline" size="icon" className="md:hidden">
                  <Menu className="size-4" />
                </Button>
              </SheetTrigger>
              <SheetContent side="left" className="w-[340px] p-4">
                <SheetHeader>
                  <SheetTitle>{t('databaseMode.conversations')}</SheetTitle>
                </SheetHeader>
                <div className="mt-4 h-[calc(100%-2rem)]">{conversationList}</div>
              </SheetContent>
            </Sheet>
            <Button variant="outline" onClick={() => refreshSelection().catch(() => undefined)}>
              <RefreshCcw className="mr-2 size-4" />
              {t('common.refresh')}
            </Button>
          </div>
        </div>

        {conversations.length === 0 ? (
          <EmptyState
            title={t('databaseMode.emptyTitle')}
            description={t('databaseMode.emptyDescription')}
          />
        ) : selectedConversation == null ? (
          <EmptyState
            title={t('databaseMode.selectConversationTitle')}
            description={t('databaseMode.selectConversationDescription')}
          />
        ) : (
          <>
            <Card>
              <CardHeader className="gap-3">
                <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
                  <div>
                    <CardTitle>{selectedConversation.conversation_name}</CardTitle>
                    <CardDescription>
                      {t('databaseMode.latestCustomer')}: {selectedConversation.latest_customer || '--'}
                    </CardDescription>
                  </div>
                  <div className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
                    <span>
                      {t('databaseMode.totalMessages')}: {selectedConversation.stats.total}
                    </span>
                    <Separator orientation="vertical" className="hidden h-4 lg:block" />
                    <span>{selectedConversation.last_message_at || '--'}</span>
                  </div>
                </div>
              </CardHeader>
            </Card>

            <StatsCards stats={stats} t={t} />

            <Card>
              <CardContent className="flex flex-col gap-3 p-4 lg:flex-row lg:items-center lg:justify-between">
                <div className="flex flex-wrap items-center gap-2">
                  <Button
                    variant="outline"
                    onClick={() =>
                      setSelectedMessageIds(messages.map((message) => message.id))
                    }
                  >
                    {t('databaseMode.selectAllCurrentConversation')}
                  </Button>
                  <Select value={messageStatus} onValueChange={setMessageStatus}>
                    <SelectTrigger className="w-[200px]">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {MESSAGE_STATUS_OPTIONS.map((status) => (
                        <SelectItem key={status} value={status}>
                          {t(`databaseMode.filter.${status}`)}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="flex flex-wrap gap-2">
                  <Button
                    variant="outline"
                    disabled={selectedMessageIds.length === 0}
                    onClick={() =>
                      withBusy('batch-process', async () => {
                        await httpClient.batchProcessDatabaseModeMessages(selectedMessageIds);
                        await refreshSelection();
                      })
                    }
                  >
                    <CheckCheck className="mr-2 size-4" />
                    {t('databaseMode.batchProcess')}
                  </Button>
                  <Button
                    variant="outline"
                    disabled={selectedMessageIds.length === 0}
                    onClick={() =>
                      withBusy('batch-skip', async () => {
                        await httpClient.batchSkipDatabaseModeMessages(selectedMessageIds);
                        await refreshSelection();
                      })
                    }
                  >
                    <SkipForward className="mr-2 size-4" />
                    {t('databaseMode.batchSkip')}
                  </Button>
                  <Button
                    variant="destructive"
                    disabled={selectedMessageIds.length === 0}
                    onClick={() => {
                      if (!window.confirm(t('databaseMode.confirmBatchDelete'))) {
                        return;
                      }
                      withBusy('batch-delete', async () => {
                        await httpClient.batchDeleteDatabaseModeMessages(selectedMessageIds);
                        await refreshSelection();
                      }).catch(() => undefined);
                    }}
                  >
                    <Trash2 className="mr-2 size-4" />
                    {t('databaseMode.batchDelete')}
                  </Button>
                </div>
              </CardContent>
            </Card>

            <ScrollArea className="min-h-0 flex-1 rounded-lg border">
              <div className="space-y-4 p-4">
                {messages.map((message) => {
                  const draftValue =
                    draftEdits[message.id] ?? message.draft_text ?? '';
                  return (
                    <Card key={message.id}>
                      <CardContent className="space-y-4 p-4">
                        <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                          <div className="flex items-start gap-3">
                            <Checkbox
                              checked={selectedMessageIds.includes(message.id)}
                              onCheckedChange={(checked) =>
                                setSelectedMessageIds((current) =>
                                  checked
                                    ? [...current, message.id]
                                    : current.filter((id) => id !== message.id),
                                )
                              }
                            />
                            <div>
                              <div className="flex flex-wrap items-center gap-2">
                                <p className="font-medium">{message.sender_name}</p>
                                <Badge variant="outline" className={statusTone(message.status)}>
                                  {t(`databaseMode.status.${message.status}`)}
                                </Badge>
                              </div>
                              <p className="mt-1 text-xs text-muted-foreground">
                                {selectedConversation.conversation_name} | {message.sent_at}
                              </p>
                            </div>
                          </div>
                          <div className="flex flex-wrap gap-2">
                            <Button
                              variant="outline"
                              onClick={() =>
                                withBusy(`draft-${message.id}`, async () => {
                                  await httpClient.generateDatabaseModeDraft(message.id);
                                  await refreshSelection();
                                })
                              }
                            >
                              {busyKey === `draft-${message.id}` ? (
                                <Loader2 className="mr-2 size-4 animate-spin" />
                              ) : (
                                <WandSparkles className="mr-2 size-4" />
                              )}
                              {message.draft_text
                                ? t('databaseMode.regenerateDraft')
                                : t('databaseMode.generateDraft')}
                            </Button>
                            <Button
                              variant="outline"
                              onClick={() =>
                                withBusy(`process-${message.id}`, async () => {
                                  await httpClient.processDatabaseModeMessage(message.id);
                                  await refreshSelection();
                                })
                              }
                            >
                              <CheckCheck className="mr-2 size-4" />
                              {t('databaseMode.markProcessed')}
                            </Button>
                            <Button
                              variant="outline"
                              onClick={() =>
                                withBusy(`skip-${message.id}`, async () => {
                                  await httpClient.skipDatabaseModeMessage(message.id);
                                  await refreshSelection();
                                })
                              }
                            >
                              <SkipForward className="mr-2 size-4" />
                              {t('databaseMode.skip')}
                            </Button>
                            <Button
                              variant="outline"
                              onClick={() => setDetailsMessage(message)}
                            >
                              {t('databaseMode.viewDetails')}
                            </Button>
                            <Button
                              variant="destructive"
                              onClick={() => {
                                if (!window.confirm(t('databaseMode.confirmDelete'))) {
                                  return;
                                }
                                withBusy(`delete-${message.id}`, async () => {
                                  await httpClient.deleteDatabaseModeMessage(message.id);
                                  await refreshSelection();
                                }).catch(() => undefined);
                              }}
                            >
                              <Trash2 className="mr-2 size-4" />
                              {t('databaseMode.delete')}
                            </Button>
                          </div>
                        </div>

                        <div className="rounded-lg border bg-muted/40 p-3">
                          <p className="text-xs uppercase tracking-wide text-muted-foreground">
                            {t('databaseMode.customerMessage')}
                          </p>
                          <p className="mt-2 whitespace-pre-wrap text-sm">{message.content}</p>
                        </div>

                        <div className="grid gap-3 xl:grid-cols-2">
                          <div className="space-y-2">
                            <p className="text-xs uppercase tracking-wide text-muted-foreground">
                              {t('databaseMode.currentDraft')}
                            </p>
                            <Textarea
                              value={draftValue}
                              onChange={(event) =>
                                setDraftEdits((current) => ({
                                  ...current,
                                  [message.id]: event.target.value,
                                }))
                              }
                              rows={5}
                            />
                            <Button
                              onClick={() =>
                                withBusy(`save-${message.id}`, async () => {
                                  await httpClient.updateDatabaseModeDraft(message.id, {
                                    draft_text: draftValue,
                                    draft_source: 'manual',
                                  });
                                  await refreshSelection();
                                })
                              }
                            >
                              {t('databaseMode.saveDraft')}
                            </Button>
                          </div>
                          <div className="space-y-2">
                            <p className="text-xs uppercase tracking-wide text-muted-foreground">
                              {t('databaseMode.aiSuggestedReply')}
                            </p>
                            <div className="min-h-[132px] rounded-lg border bg-background p-3 text-sm text-muted-foreground">
                              {message.ai_suggested_reply || message.draft_text || t('databaseMode.noDraftYet')}
                            </div>
                          </div>
                        </div>

                        {message.last_error ? (
                          <p className="text-sm text-red-600 dark:text-red-400">
                            {message.last_error}
                          </p>
                        ) : null}
                      </CardContent>
                    </Card>
                  );
                })}
              </div>
            </ScrollArea>
          </>
        )}
      </div>

      <Dialog open={!!detailsMessage} onOpenChange={(open) => !open && setDetailsMessage(null)}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>{t('databaseMode.messageDetails')}</DialogTitle>
          </DialogHeader>
          {detailsMessage ? (
            <div className="space-y-3 text-sm">
              <div className="grid gap-2 sm:grid-cols-2">
                <div>
                  <p className="text-muted-foreground">{t('databaseMode.sender')}</p>
                  <p>{detailsMessage.sender_name}</p>
                </div>
                <div>
                  <p className="text-muted-foreground">{t('databaseMode.receivedAt')}</p>
                  <p>{detailsMessage.observed_at}</p>
                </div>
                <div>
                  <p className="text-muted-foreground">{t('databaseMode.messageType')}</p>
                  <p>{detailsMessage.message_type}</p>
                </div>
                <div>
                  <p className="text-muted-foreground">{t('databaseMode.statusLabel')}</p>
                  <p>{t(`databaseMode.status.${detailsMessage.status}`)}</p>
                </div>
              </div>
              <Separator />
              <div>
                <p className="text-muted-foreground">{t('databaseMode.customerMessage')}</p>
                <p className="mt-1 whitespace-pre-wrap">{detailsMessage.content}</p>
              </div>
              <div>
                <p className="text-muted-foreground">{t('databaseMode.currentDraft')}</p>
                <p className="mt-1 whitespace-pre-wrap">
                  {detailsMessage.draft_text || t('databaseMode.noDraftYet')}
                </p>
              </div>
            </div>
          ) : null}
        </DialogContent>
      </Dialog>
    </div>
  );
}
