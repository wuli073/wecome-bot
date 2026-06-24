import {
  startTransition,
  useCallback,
  useEffect,
  useEffectEvent,
  useMemo,
  useRef,
  useState,
} from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import {
  DatabaseModeConversation,
  DatabaseModeConversationStats,
  DatabaseModeMessage,
  DatabaseModeRealtimeEvent,
  LocalConnectorStatus,
} from '@/app/infra/entities/api';
import { httpClient } from '@/app/infra/http';
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

import {
  useDatabaseModeEvents,
} from './hooks/useDatabaseModeEvents';
import {
  buildDatabaseModeQuerySignature,
  formatDatabaseModeDateTime,
} from './utils';

const CONVERSATION_STATUS_OPTIONS = [
  'all',
  'pending',
  'processing',
  'draft_ready',
  'failed',
  'processed',
  'skipped',
] as const;
const MESSAGE_STATUS_OPTIONS = [
  'all',
  'pending',
  'processing',
  'draft_ready',
  'failed',
  'processed',
  'skipped',
] as const;
const CONVERSATION_PAGE = 1;
const CONVERSATION_PAGE_SIZE = 100;
const MESSAGE_PAGE = 1;
const MESSAGE_PAGE_SIZE = 200;
const REFRESH_DEBOUNCE_MS = 200;
const BUSINESS_POLL_INTERVAL_MS = 15_000;
const CONNECTOR_POLL_INTERVAL_MS = 5_000;

type DatabaseModeConversationDetail = {
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
};

type RefreshIntent = 'conversations' | 'conversation' | 'messages' | 'all';
type RefreshIntents = {
  conversations: boolean;
  conversation: boolean;
  messages: boolean;
  all: boolean;
};
type DatabaseModeQueryContext = {
  selectedConversationId: number | null;
  conversationStatus: string;
  messageStatus: string;
  keyword: string;
  conversationPage: number;
  conversationPageSize: number;
  messagePage: number;
  messagePageSize: number;
};

function emptyRefreshIntents(): RefreshIntents {
  return {
    conversations: false,
    conversation: false,
    messages: false,
    all: false,
  };
}

function hasPendingRefreshIntents(intents: RefreshIntents): boolean {
  return (
    intents.all ||
    intents.conversations ||
    intents.conversation ||
    intents.messages
  );
}

function markRefreshIntent(intents: RefreshIntents, intent: RefreshIntent) {
  if (intent === 'all') {
    intents.all = true;
    intents.conversations = true;
    intents.conversation = true;
    intents.messages = true;
    return;
  }

  intents[intent] = true;
}

function statusTone(status: string): string {
  switch (status) {
    case 'pending':
      return 'border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-900/70 dark:bg-amber-950/40 dark:text-amber-300';
    case 'processing':
      return 'border-violet-200 bg-violet-50 text-violet-700 dark:border-violet-900/70 dark:bg-violet-950/40 dark:text-violet-300';
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

function mergeServerMessagesWithDrafts(
  nextMessages: DatabaseModeMessage[],
  draftEdits: Record<number, string>,
) {
  return nextMessages.map((serverMessage) => {
    const dirtyDraft = draftEdits[serverMessage.id];
    if (dirtyDraft == null) {
      return serverMessage;
    }

    return {
      ...serverMessage,
      draft_text: dirtyDraft,
      ai_suggested_reply: dirtyDraft,
    };
  });
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
    <Card className="mx-auto w-full min-w-0 max-w-2xl">
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
    ['processing', t('databaseMode.status.processing')],
    ['draft_ready', t('databaseMode.statusDraftReady')],
    ['failed', t('databaseMode.statusFailed')],
    ['processed', t('databaseMode.statusProcessed')],
    ['skipped', t('databaseMode.statusSkipped')],
  ] as const;

  return (
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-6">
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
  const [selectedConversation, setSelectedConversation] =
    useState<DatabaseModeConversationDetail | null>(null);
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
  const [lastToastEventId, setLastToastEventId] = useState<string | null>(null);
  const [isPageVisible, setIsPageVisible] = useState(
    () => document.visibilityState === 'visible',
  );

  const requestVersionRef = useRef(0);
  const refreshTimerRef = useRef<number | null>(null);
  const fallbackPollTimerRef = useRef<number | null>(null);
  const refreshRunningRef = useRef(false);
  const rerunRequestedRef = useRef(false);
  const pendingIntentsRef = useRef<RefreshIntents>(emptyRefreshIntents());
  const mountedRef = useRef(false);
  const hasLoadedOnceRef = useRef(false);
  const messagesViewportRef = useRef<HTMLDivElement | null>(null);
  const scrollTopRef = useRef(0);
  const draftEditsRef = useRef(draftEdits);
  const queryContextRef = useRef<DatabaseModeQueryContext>({
    selectedConversationId,
    conversationStatus,
    messageStatus,
    keyword,
    conversationPage: CONVERSATION_PAGE,
    conversationPageSize: CONVERSATION_PAGE_SIZE,
    messagePage: MESSAGE_PAGE,
    messagePageSize: MESSAGE_PAGE_SIZE,
  });

  draftEditsRef.current = draftEdits;
  queryContextRef.current = {
    selectedConversationId,
    conversationStatus,
    messageStatus,
    keyword,
    conversationPage: CONVERSATION_PAGE,
    conversationPageSize: CONVERSATION_PAGE_SIZE,
    messagePage: MESSAGE_PAGE,
    messagePageSize: MESSAGE_PAGE_SIZE,
  };

  const connectorDetailHref = useMemo(
    () => `/home/mcp?id=${encodeURIComponent(connector?.name ?? 'WeCom Local Connector')}`,
    [connector?.name],
  );
  const connectorConfigured = useMemo(
    () =>
      connector?.status !== 'not_configured' &&
      connector?.status !== 'unsupported_platform',
    [connector?.status],
  );

  const restoreScrollPosition = useEffectEvent(() => {
    if (messagesViewportRef.current != null) {
      messagesViewportRef.current.scrollTop = scrollTopRef.current;
    }
  });

  const captureScrollPosition = useEffectEvent(() => {
    if (messagesViewportRef.current != null) {
      scrollTopRef.current = messagesViewportRef.current.scrollTop;
    }
  });

  const getQuerySignature = useEffectEvent(() =>
    buildDatabaseModeQuerySignature(queryContextRef.current),
  );

  const isRequestCurrent = useEffectEvent(
    (requestVersion: number, querySignature: string) =>
      mountedRef.current &&
      requestVersion === requestVersionRef.current &&
      querySignature === getQuerySignature(),
  );

  const applyIfCurrent = useEffectEvent(
    (
      requestVersion: number,
      querySignature: string,
      apply: () => void,
    ) => {
      if (!isRequestCurrent(requestVersion, querySignature)) {
        return false;
      }

      startTransition(() => {
        apply();
      });
      return true;
    },
  );

  const loadConnector = useCallback(async () => {
    const response = await httpClient.getLocalConnectorStatus('wxwork-local');
    return response.connector;
  }, []);

  const refreshConversations = useCallback(
    async (context: DatabaseModeQueryContext) => {
      const response = await httpClient.getDatabaseModeConversations({
        keyword: context.keyword,
        status: context.conversationStatus,
        page: context.conversationPage,
        page_size: context.conversationPageSize,
      });

      const nextSelectedConversationId =
        context.selectedConversationId != null &&
        response.conversations.some(
          (item) => item.id === context.selectedConversationId,
        )
          ? context.selectedConversationId
          : response.conversations[0]?.id ?? null;

      return {
        conversations: response.conversations,
        nextSelectedConversationId,
      };
    },
    [],
  );

  const refreshCurrentConversation = useCallback(
    async (conversationId: number) =>
      httpClient.getDatabaseModeConversation(conversationId),
    [],
  );

  const refreshCurrentMessages = useCallback(
    async (conversationId: number, context: DatabaseModeQueryContext) =>
      httpClient.getDatabaseModeMessages(conversationId, {
        status: context.messageStatus,
        page: context.messagePage,
        page_size: context.messagePageSize,
      }),
    [],
  );

  const refreshAll = useCallback(
    async (
      requestVersion: number,
      querySignature: string,
      context: DatabaseModeQueryContext,
    ) => {
      captureScrollPosition();

      const [connectorResp, conversationsResp] = await Promise.all([
        loadConnector(),
        refreshConversations(context),
      ]);

      let conversationResp: Awaited<ReturnType<typeof refreshCurrentConversation>> | null = null;
      let messagesResp: Awaited<ReturnType<typeof refreshCurrentMessages>> | null = null;

      if (conversationsResp.nextSelectedConversationId != null) {
        [conversationResp, messagesResp] = await Promise.all([
          refreshCurrentConversation(conversationsResp.nextSelectedConversationId),
          refreshCurrentMessages(
            conversationsResp.nextSelectedConversationId,
            context,
          ),
        ]);
      }

      const didApply = applyIfCurrent(requestVersion, querySignature, () => {
        setConnector(connectorResp);
        setConversations(conversationsResp.conversations);

        if (conversationsResp.nextSelectedConversationId !== context.selectedConversationId) {
          setSelectedConversationId(conversationsResp.nextSelectedConversationId);
        }

        if (
          conversationsResp.nextSelectedConversationId == null ||
          conversationResp == null ||
          messagesResp == null
        ) {
          setSelectedConversation(null);
          setMessages([]);
          setStats(null);
          setSelectedMessageIds([]);
          setLoading(false);
          return;
        }

        setSelectedConversation(conversationResp.conversation);
        setStats(messagesResp.stats);
        setMessages(
          mergeServerMessagesWithDrafts(
            messagesResp.messages,
            draftEditsRef.current,
          ),
        );
        setSelectedMessageIds((current) =>
          current.filter((messageId) =>
            messagesResp.messages.some((message) => message.id === messageId),
          ),
        );
        setLoading(false);
      });

      if (didApply && messagesResp != null) {
        window.requestAnimationFrame(() => {
          restoreScrollPosition();
        });
      }

      if (didApply) {
        hasLoadedOnceRef.current = true;
      }
    },
    [
      applyIfCurrent,
      captureScrollPosition,
      loadConnector,
      refreshConversations,
      refreshCurrentConversation,
      refreshCurrentMessages,
      restoreScrollPosition,
    ],
  );

  const consumeRefreshIntents = useCallback(() => {
    const intents = pendingIntentsRef.current;
    pendingIntentsRef.current = emptyRefreshIntents();
    return intents.all
      ? {
          conversations: true,
          conversation: true,
          messages: true,
          all: true,
        }
      : intents;
  }, []);

  const executeRefresh = useCallback(
    async (intents: RefreshIntents) => {
      const context = { ...queryContextRef.current };
      const requestVersion = ++requestVersionRef.current;
      const querySignature = buildDatabaseModeQuerySignature(context);

      if (intents.all || intents.conversations) {
        await refreshAll(requestVersion, querySignature, context);
        return;
      }

      if (context.selectedConversationId == null) {
        const didApply = applyIfCurrent(requestVersion, querySignature, () => {
          setSelectedConversation(null);
          setMessages([]);
          setStats(null);
          setSelectedMessageIds([]);
          setLoading(false);
        });
        if (didApply) {
          hasLoadedOnceRef.current = true;
        }
        return;
      }

      captureScrollPosition();

      const [conversationResp, messagesResp] = await Promise.all([
        intents.conversation
          ? refreshCurrentConversation(context.selectedConversationId)
          : Promise.resolve(null),
        intents.messages
          ? refreshCurrentMessages(context.selectedConversationId, context)
          : Promise.resolve(null),
      ]);

      const didApply = applyIfCurrent(requestVersion, querySignature, () => {
        if (conversationResp != null) {
          setSelectedConversation(conversationResp.conversation);
        }

        if (messagesResp != null) {
          setStats(messagesResp.stats);
          setMessages(
            mergeServerMessagesWithDrafts(
              messagesResp.messages,
              draftEditsRef.current,
            ),
          );
          setSelectedMessageIds((current) =>
            current.filter((messageId) =>
              messagesResp.messages.some((message) => message.id === messageId),
            ),
          );
        }

        setLoading(false);
      });

      if (didApply && messagesResp != null) {
        window.requestAnimationFrame(() => {
          restoreScrollPosition();
        });
      }

      if (didApply) {
        hasLoadedOnceRef.current = true;
      }
    },
    [
      applyIfCurrent,
      captureScrollPosition,
      refreshAll,
      refreshCurrentConversation,
      refreshCurrentMessages,
      restoreScrollPosition,
    ],
  );

  const runRefreshCycle = useEffectEvent(async () => {
    if (!mountedRef.current || refreshRunningRef.current) {
      return;
    }

    refreshRunningRef.current = true;
    let shouldScheduleAnotherCycle = false;

    try {
      let runCount = 0;

      do {
        rerunRequestedRef.current = false;
        const intents = consumeRefreshIntents();
        if (!hasPendingRefreshIntents(intents)) {
          break;
        }

        await executeRefresh(intents);
        runCount += 1;

        if (rerunRequestedRef.current && runCount >= 2) {
          rerunRequestedRef.current = false;
          shouldScheduleAnotherCycle = true;
          break;
        }
      } while (rerunRequestedRef.current);
    } catch (err) {
      if (mountedRef.current) {
        setError((err as { msg?: string }).msg || t('databaseMode.loadFailed'));
        setLoading(false);
      }
    } finally {
      refreshRunningRef.current = false;

      if (shouldScheduleAnotherCycle && mountedRef.current) {
        markRefreshIntent(pendingIntentsRef.current, 'all');
        if (refreshTimerRef.current == null) {
          refreshTimerRef.current = window.setTimeout(() => {
            refreshTimerRef.current = null;
            void runRefreshCycle();
          }, REFRESH_DEBOUNCE_MS);
        }
      }
    }
  });

  const scheduleRefresh = useCallback(
    (intent: RefreshIntent) => {
      if (!mountedRef.current) {
        return;
      }

      markRefreshIntent(pendingIntentsRef.current, intent);

      if (refreshRunningRef.current) {
        rerunRequestedRef.current = true;
        return;
      }

      if (refreshTimerRef.current != null) {
        window.clearTimeout(refreshTimerRef.current);
      }

      refreshTimerRef.current = window.setTimeout(() => {
        refreshTimerRef.current = null;
        void runRefreshCycle();
      }, REFRESH_DEBOUNCE_MS);
    },
    [runRefreshCycle],
  );

  const requestRefresh = useEffectEvent((intent: RefreshIntent) => {
    scheduleRefresh(intent);
  });

  const withBusy = useEffectEvent(async (key: string, action: () => Promise<void>) => {
    setBusyKey(key);
    try {
      await action();
    } catch (err) {
      toast.error((err as { msg?: string }).msg || t('databaseMode.operationFailed'));
    } finally {
      setBusyKey(null);
    }
  });

  const handleRealtimeEvent = useEffectEvent((event: DatabaseModeRealtimeEvent) => {
    if (import.meta.env.DEV) {
      const publishedAt = event.metadata?.timings?.sse_published_at;
      if (publishedAt) {
        const latencyMs = Math.max(0, Date.now() - Date.parse(publishedAt));
        console.debug('[database-mode] sse-event', {
          type: event.type,
          eventId: event.event_id,
          latencyMs,
        });
      }
    }

    switch (event.type) {
      case 'ready':
        scheduleRefresh('all');
        return;
      case 'database-conversation-updated':
        scheduleRefresh('conversations');
        scheduleRefresh('conversation');
        return;
      case 'database-message-created':
        if (event.event_id && event.event_id !== lastToastEventId) {
          setLastToastEventId(event.event_id);
          toast.message(t('databaseMode.refreshing'));
        }
        scheduleRefresh('conversations');
        scheduleRefresh('conversation');
        scheduleRefresh('messages');
        return;
      case 'database-message-updated':
      case 'database-message-deleted':
        scheduleRefresh('conversations');
        scheduleRefresh('conversation');
        scheduleRefresh('messages');
        return;
      case 'database-mode-invalidated':
      default:
        scheduleRefresh('all');
    }
  });

  const { connectionState } = useDatabaseModeEvents({
    enabled: connectorConfigured,
    onEvent: handleRealtimeEvent,
  });

  useEffect(() => {
    mountedRef.current = true;

    return () => {
      mountedRef.current = false;
      rerunRequestedRef.current = false;
      pendingIntentsRef.current = emptyRefreshIntents();

      if (refreshTimerRef.current != null) {
        window.clearTimeout(refreshTimerRef.current);
        refreshTimerRef.current = null;
      }

      if (fallbackPollTimerRef.current != null) {
        window.clearInterval(fallbackPollTimerRef.current);
        fallbackPollTimerRef.current = null;
      }
    };
  }, []);

  useEffect(() => {
    setError('');
    if (!hasLoadedOnceRef.current) {
      setLoading(true);
    }
    requestRefresh('all');
  }, [conversationStatus, keyword, messageStatus]);

  useEffect(() => {
    const timer = window.setInterval(() => {
      loadConnector()
        .then((nextConnector) => {
          setConnector(nextConnector);
        })
        .catch(() => undefined);
    }, CONNECTOR_POLL_INTERVAL_MS);

    return () => {
      window.clearInterval(timer);
    };
  }, []);

  useEffect(() => {
    if (fallbackPollTimerRef.current != null) {
      window.clearInterval(fallbackPollTimerRef.current);
      fallbackPollTimerRef.current = null;

      if (import.meta.env.DEV) {
        console.debug('[database-mode] fallback-poll-stop');
      }
    }

    if (!mountedRef.current || connectionState !== 'disconnected' || !isPageVisible) {
      return;
    }

    fallbackPollTimerRef.current = window.setInterval(() => {
      requestRefresh('all');
    }, BUSINESS_POLL_INTERVAL_MS);

    if (import.meta.env.DEV) {
      console.debug('[database-mode] fallback-poll-start');
    }

    return () => {
      if (fallbackPollTimerRef.current != null) {
        window.clearInterval(fallbackPollTimerRef.current);
        fallbackPollTimerRef.current = null;

        if (import.meta.env.DEV) {
          console.debug('[database-mode] fallback-poll-stop');
        }
      }
    };
  }, [connectionState, isPageVisible]);

  useEffect(() => {
    const handleVisibilityChange = () => {
      const visible = document.visibilityState === 'visible';
      setIsPageVisible(visible);
      if (visible) {
        requestRefresh('all');
      }
    };

    document.addEventListener('visibilitychange', handleVisibilityChange);
    return () => {
      document.removeEventListener('visibilitychange', handleVisibilityChange);
    };
  }, []);

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
              onClick={() => {
                if (conversation.id === selectedConversationId) {
                  return;
                }

                setSelectedConversationId(conversation.id);
                scheduleRefresh('conversation');
                scheduleRefresh('messages');
              }}
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
                <span>{formatDatabaseModeDateTime(conversation.last_message_at)}</span>
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
          <Button variant="outline" onClick={() => scheduleRefresh('all')}>
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
                  scheduleRefresh('all');
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

  if (monitor.running_status === 'warming_up' || !monitor.warmup_completed) {
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
            <Button variant="outline" onClick={() => scheduleRefresh('all')}>
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
                      {t('databaseMode.latestCustomer')}:{' '}
                      {selectedConversation.latest_customer || '--'}
                    </CardDescription>
                  </div>
                  <div className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
                    <span>
                      {t('databaseMode.totalMessages')}: {selectedConversation.stats.total}
                    </span>
                    <Separator orientation="vertical" className="hidden h-4 lg:block" />
                    <span>{formatDatabaseModeDateTime(selectedConversation.last_message_at)}</span>
                    <Separator orientation="vertical" className="hidden h-4 lg:block" />
                    <span>{connectionState}</span>
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
                        scheduleRefresh('all');
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
                        scheduleRefresh('all');
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
                      void withBusy('batch-delete', async () => {
                        await httpClient.batchDeleteDatabaseModeMessages(selectedMessageIds);
                        scheduleRefresh('all');
                      });
                    }}
                  >
                    <Trash2 className="mr-2 size-4" />
                    {t('databaseMode.batchDelete')}
                  </Button>
                </div>
              </CardContent>
            </Card>

            <ScrollArea
              className="min-h-0 flex-1 rounded-lg border"
              viewportRef={messagesViewportRef}
            >
              <div className="space-y-4 p-4">
                {messages.map((message) => {
                  const draftValue = draftEdits[message.id] ?? message.draft_text ?? '';
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
                                {selectedConversation.conversation_name} |{' '}
                                {formatDatabaseModeDateTime(message.sent_at)}
                              </p>
                            </div>
                          </div>
                          <div className="flex flex-wrap gap-2">
                            <Button
                              variant="outline"
                              onClick={() =>
                                withBusy(`draft-${message.id}`, async () => {
                                  await httpClient.generateDatabaseModeDraft(message.id);
                                  scheduleRefresh('all');
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
                                  scheduleRefresh('all');
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
                                  scheduleRefresh('all');
                                })
                              }
                            >
                              <SkipForward className="mr-2 size-4" />
                              {t('databaseMode.skip')}
                            </Button>
                            <Button variant="outline" onClick={() => setDetailsMessage(message)}>
                              {t('databaseMode.viewDetails')}
                            </Button>
                            <Button
                              variant="destructive"
                              onClick={() => {
                                if (!window.confirm(t('databaseMode.confirmDelete'))) {
                                  return;
                                }
                                void withBusy(`delete-${message.id}`, async () => {
                                  await httpClient.deleteDatabaseModeMessage(message.id);
                                  scheduleRefresh('all');
                                });
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
                                  setDraftEdits((current) => {
                                    const next = { ...current };
                                    delete next[message.id];
                                    return next;
                                  });
                                  scheduleRefresh('all');
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
                              {message.ai_suggested_reply ||
                                message.draft_text ||
                                t('databaseMode.noDraftYet')}
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

      <Dialog
        open={!!detailsMessage}
        onOpenChange={(open) => !open && setDetailsMessage(null)}
      >
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
                  <p>{formatDatabaseModeDateTime(detailsMessage.observed_at)}</p>
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
                  {draftEdits[detailsMessage.id] ??
                    detailsMessage.draft_text ??
                    t('databaseMode.noDraftYet')}
                </p>
              </div>
            </div>
          ) : null}
        </DialogContent>
      </Dialog>
    </div>
  );
}
