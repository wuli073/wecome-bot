/**
 * Database Bot Session Monitor
 * Chat-style session monitor for wxwork_database bots.
 */

import React, {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from 'react';

import { MessageContentRenderer } from '@/app/home/monitoring/components/MessageContentRenderer';
import type {
  BotConversation,
  BotMessage,
  ReplyDraft,
} from '@/app/infra/entities/api';
import { copyToClipboard } from '@/app/utils/clipboard';
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
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Input } from '@/components/ui/input';
import { ScrollArea } from '@/components/ui/scroll-area';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { cn } from '@/lib/utils';
import {
  CheckCheck,
  RefreshCw,
  Search,
  SkipForward,
  Trash2,
} from 'lucide-react';
import { toast } from 'sonner';

import type { BotSessionMonitorHandle } from '../BotSessionMonitor';
import { createDataSource } from '../datasources';
import { useBotDatabaseEvents } from '../hooks/useBotDatabaseEvents';
import { ChatMessageBubble } from './ChatMessageBubble';
import { DatabaseAiActionPopover } from './DatabaseAiActionPopover';
import {
  DatabaseChatComposer,
  type ComposerDraftMeta,
} from './DatabaseChatComposer';
import { DatabaseMessageActionsMenu } from './DatabaseMessageActionsMenu';

interface DatabaseBotSessionMonitorProps {
  botId: string;
  botAdapter: string;
  botEnabled: boolean;
}

type MessageStatusFilter =
  | 'all'
  | 'pending'
  | 'processing'
  | 'draft_ready'
  | 'processed'
  | 'skipped'
  | 'failed';

interface DraftEditorState extends ComposerDraftMeta {
  conversationId: number;
  draftId: number | null;
  messageId: number;
}

interface LoadMessagesOptions {
  preserveDraftText?: boolean;
}

interface DraftRestoreOptions {
  force?: boolean;
}

const SCROLL_BOTTOM_THRESHOLD = 80;
const STATUS_OPTIONS: MessageStatusFilter[] = [
  'all',
  'pending',
  'processing',
  'draft_ready',
  'processed',
  'skipped',
  'failed',
];

function getTimestampValue(value?: string) {
  if (!value) {
    return 0;
  }

  const parsed = Date.parse(value);
  return Number.isNaN(parsed) ? 0 : parsed;
}

function sortMessages(messages: BotMessage[]) {
  return [...messages].sort((left, right) => {
    const timeDiff =
      getTimestampValue(left.sent_at) - getTimestampValue(right.sent_at);
    if (timeDiff !== 0) {
      return timeDiff;
    }
    return left.id - right.id;
  });
}

function isCustomerMessage(message: BotMessage) {
  return message.sender_id !== 'bot';
}

function canGenerateDraft(message: BotMessage) {
  return (
    isCustomerMessage(message) &&
    (message.status === 'pending' || message.status === 'failed')
  );
}

function canSelectActionTarget(message: BotMessage) {
  return (
    isCustomerMessage(message) &&
    message.status !== 'processed' &&
    message.status !== 'skipped'
  );
}

function canProcessMessage(message: BotMessage) {
  return (
    isCustomerMessage(message) &&
    message.status !== 'processed' &&
    message.status !== 'skipped'
  );
}

function canBatchSelectMessage(message: BotMessage) {
  return canProcessMessage(message);
}

function findDefaultActionMessage(messages: BotMessage[]) {
  const sorted = sortMessages(messages);
  const pendingMessages = sorted.filter(
    (message) => message.status === 'pending' && canGenerateDraft(message),
  );
  if (pendingMessages.length > 0) {
    return pendingMessages.at(-1) ?? null;
  }

  const failedMessages = sorted.filter(
    (message) => message.status === 'failed' && canGenerateDraft(message),
  );
  return failedMessages.at(-1) ?? null;
}

function findConversationDraftMessage(messages: BotMessage[]) {
  const sorted = sortMessages(messages);
  return (
    [...sorted]
      .reverse()
      .find(
        (message) => message.status === 'draft_ready' && message.draft_text,
      ) ??
    [...sorted].reverse().find((message) => message.draft_text) ??
    null
  );
}

function buildDraftState(
  message: BotMessage,
  conversationId: number,
  previousDraft: DraftEditorState | null,
): DraftEditorState {
  const sameDraft =
    previousDraft?.conversationId === conversationId &&
    previousDraft.messageId === message.id;

  return {
    conversationId,
    draftId:
      message.draft_id ?? (sameDraft ? (previousDraft?.draftId ?? null) : null),
    messageId: message.id,
    source: message.draft_source === 'manual' ? 'manual' : 'pipeline',
    updatedAt:
      message.draft_updated_at ??
      message.updated_at ??
      (sameDraft ? previousDraft?.updatedAt : undefined),
    version:
      message.draft_version ?? (sameDraft ? (previousDraft?.version ?? 1) : 1),
  };
}

function buildMessageFromReplyDraft(
  draft: ReplyDraft,
  messageId: number,
  conversationId: number,
): BotMessage {
  const timestamp = draft.updated_at ?? draft.created_at;
  return {
    id: messageId,
    event_id: '',
    message_key: '',
    conversation_id: conversationId,
    sender_id: '',
    sender_name: '',
    content: '',
    message_type: 'text',
    sent_at: timestamp,
    observed_at: timestamp,
    status: 'draft_ready',
    draft_text: draft.content,
    draft_source: draft.source,
    draft_id: draft.id,
    draft_version: draft.version,
    draft_updated_at: draft.updated_at,
    attempt_count: 0,
    created_at: timestamp,
    updated_at: timestamp,
  };
}

function getDraftTextFromMessage(message: BotMessage | null | undefined) {
  return message?.draft_text?.trim() ? message.draft_text : null;
}

function canRestoreDraftFromMessage(message: BotMessage | null | undefined) {
  return Boolean(
    message &&
    message.status === 'draft_ready' &&
    getDraftTextFromMessage(message),
  );
}

function formatConversationType(type: BotConversation['conversation_type']) {
  return type === 'group' ? '群聊' : '私聊';
}

function formatStatus(status: BotMessage['status']) {
  switch (status) {
    case 'pending':
      return '待处理';
    case 'processing':
      return '处理中';
    case 'draft_ready':
      return '草稿就绪';
    case 'processed':
      return '已处理';
    case 'skipped':
      return '已跳过';
    case 'failed':
      return '失败';
    default:
      return status;
  }
}

function formatDraftSource(source?: 'pipeline' | 'manual') {
  return source === 'manual' ? 'Manual' : 'Pipeline';
}

function formatRelativeTime(raw?: string) {
  if (!raw) {
    return '--';
  }

  const date = new Date(raw);
  if (Number.isNaN(date.getTime())) {
    return '--';
  }

  const now = Date.now();
  const diff = now - date.getTime();
  const minute = 60_000;
  const hour = 60 * minute;
  const day = 24 * hour;

  if (diff < minute) {
    return '刚刚';
  }
  if (diff < hour) {
    return `${Math.max(1, Math.floor(diff / minute))} 分钟前`;
  }
  if (diff < day) {
    return `${Math.max(1, Math.floor(diff / hour))} 小时前`;
  }
  return `${Math.max(1, Math.floor(diff / day))} 天前`;
}

function formatDateTime(raw?: string) {
  if (!raw) {
    return '--';
  }

  const date = new Date(raw);
  if (Number.isNaN(date.getTime())) {
    return '--';
  }

  return date.toLocaleString();
}

function statusTextClass(status: BotMessage['status']) {
  switch (status) {
    case 'pending':
      return 'text-amber-700 dark:text-amber-300';
    case 'processing':
      return 'text-sky-700 dark:text-sky-300';
    case 'draft_ready':
      return 'text-emerald-700 dark:text-emerald-300';
    case 'processed':
      return 'text-emerald-700 dark:text-emerald-300';
    case 'skipped':
      return 'text-muted-foreground';
    case 'failed':
      return 'text-destructive';
    default:
      return 'text-muted-foreground';
  }
}

export const DatabaseBotSessionMonitor = forwardRef<
  BotSessionMonitorHandle,
  DatabaseBotSessionMonitorProps
>(function DatabaseBotSessionMonitor({ botId, botAdapter, botEnabled }, ref) {
  const [conversations, setConversations] = useState<BotConversation[]>([]);
  const [selectedConversationId, setSelectedConversationId] = useState<
    number | null
  >(null);
  const [messages, setMessages] = useState<BotMessage[]>([]);
  const [loading, setLoading] = useState(false);
  const [messagesLoading, setMessagesLoading] = useState(false);
  const [searchKeyword, setSearchKeyword] = useState('');
  const [appliedKeyword, setAppliedKeyword] = useState('');
  const [statusFilter, setStatusFilter] = useState<MessageStatusFilter>('all');
  const [draftText, setDraftText] = useState('');
  const [originalDraftText, setOriginalDraftText] = useState('');
  const [currentDraft, setCurrentDraft] = useState<DraftEditorState | null>(
    null,
  );
  const [draftSaving, setDraftSaving] = useState(false);
  const [generatingDraft, setGeneratingDraft] = useState(false);
  const [copied, setCopied] = useState(false);
  const [isBatchMode, setIsBatchMode] = useState(false);
  const [selectedMessages, setSelectedMessages] = useState<Set<number>>(
    new Set(),
  );
  const [explicitSelectedMessageId, setExplicitSelectedMessageId] = useState<
    number | null
  >(null);
  const [aiPopoverOpen, setAiPopoverOpen] = useState(false);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [messageToDelete, setMessageToDelete] = useState<number | null>(null);
  const [batchDeleteDialogOpen, setBatchDeleteDialogOpen] = useState(false);
  const [batchBusyKey, setBatchBusyKey] = useState<
    'process' | 'skip' | 'delete' | null
  >(null);

  const messagesScrollAreaRef = useRef<HTMLDivElement | null>(null);
  const currentDraftRef = useRef<DraftEditorState | null>(null);
  const draftDirtyRef = useRef(false);
  const selectedConversationIdRef = useRef<number | null>(null);
  const autoScrollToBottomRef = useRef(true);
  const previousConversationIdRef = useRef<number | null>(null);
  const previousLastMessageIdRef = useRef<number | null>(null);

  const dataSource = useMemo(
    () => createDataSource(botAdapter, botId),
    [botAdapter, botId],
  );
  const selectedConversation = useMemo(
    () =>
      conversations.find(
        (conversation) => conversation.id === selectedConversationId,
      ) ?? null,
    [conversations, selectedConversationId],
  );
  const hasUnsavedDraftChanges = draftText !== originalDraftText;

  useEffect(() => {
    currentDraftRef.current = currentDraft;
  }, [currentDraft]);

  useEffect(() => {
    draftDirtyRef.current = hasUnsavedDraftChanges;
  }, [hasUnsavedDraftChanges]);

  useEffect(() => {
    selectedConversationIdRef.current = selectedConversationId;
  }, [selectedConversationId]);

  const getMessagesViewport = useCallback(() => {
    return messagesScrollAreaRef.current?.querySelector(
      '[data-radix-scroll-area-viewport]',
    ) as HTMLDivElement | null;
  }, []);

  const scrollToBottom = useCallback(
    (behavior: ScrollBehavior = 'auto') => {
      const viewport = getMessagesViewport();
      if (!viewport) {
        return;
      }

      viewport.scrollTo({ top: viewport.scrollHeight, behavior });
    },
    [getMessagesViewport],
  );

  const applyConversationDraft = useCallback(
    (
      nextMessages: BotMessage[],
      conversationId: number,
      options?: LoadMessagesOptions,
    ) => {
      const draftMessage = findConversationDraftMessage(nextMessages);
      const previousDraft = currentDraftRef.current;
      const preserveDraftText =
        Boolean(options?.preserveDraftText) &&
        draftDirtyRef.current &&
        previousDraft?.conversationId === conversationId;

      if (!draftMessage) {
        setCurrentDraft(null);
        if (!preserveDraftText) {
          setDraftText('');
          setOriginalDraftText('');
        }
        return;
      }

      const nextDraft = buildDraftState(
        draftMessage,
        conversationId,
        previousDraft,
      );
      setCurrentDraft(nextDraft);

      const sameDraft =
        previousDraft?.conversationId === conversationId &&
        previousDraft.messageId === nextDraft.messageId;
      if (preserveDraftText && sameDraft) {
        return;
      }

      const nextDraftText = draftMessage.draft_text ?? '';
      setDraftText(nextDraftText);
      setOriginalDraftText(nextDraftText);
    },
    [],
  );

  const loadConversations = useCallback(async () => {
    setLoading(true);
    try {
      const response = await dataSource.listConversations({
        keyword: appliedKeyword || undefined,
        status: statusFilter === 'all' ? undefined : statusFilter,
      });
      setConversations(response.conversations);
      setSelectedConversationId((currentId) => {
        if (response.conversations.length === 0) {
          return null;
        }
        if (
          currentId !== null &&
          response.conversations.some(
            (conversation) => conversation.id === currentId,
          )
        ) {
          return currentId;
        }
        return response.conversations[0]?.id ?? null;
      });
    } catch (error) {
      console.error('Failed to load conversations:', error);
      toast.error('加载会话失败');
    } finally {
      setLoading(false);
    }
  }, [appliedKeyword, dataSource, statusFilter]);

  const applySearch = useCallback(() => {
    const nextKeyword = searchKeyword.trim();
    if (nextKeyword === appliedKeyword) {
      void loadConversations();
      return;
    }
    setAppliedKeyword(nextKeyword);
  }, [appliedKeyword, loadConversations, searchKeyword]);

  const loadMessages = useCallback(
    async (conversationId: number, options?: LoadMessagesOptions) => {
      setMessagesLoading(true);
      try {
        const response = await dataSource.listMessages(
          conversationId.toString(),
        );
        setMessages(response.messages);
        applyConversationDraft(response.messages, conversationId, options);
      } catch (error) {
        console.error('Failed to load messages:', error);
        toast.error('加载消息失败');
      } finally {
        setMessagesLoading(false);
      }
    },
    [applyConversationDraft, dataSource],
  );

  const refreshConversationData = useCallback(async () => {
    const conversationId = selectedConversationIdRef.current;
    if (conversationId === null) {
      await loadConversations();
      return;
    }

    await Promise.all([
      loadConversations(),
      loadMessages(conversationId, { preserveDraftText: true }),
    ]);
  }, [loadConversations, loadMessages]);

  useImperativeHandle(
    ref,
    () => ({
      refreshSessions: refreshConversationData,
    }),
    [refreshConversationData],
  );

  useEffect(() => {
    void loadConversations();
  }, [loadConversations]);

  useEffect(() => {
    if (selectedConversationId === null) {
      setMessages([]);
      setDraftText('');
      setOriginalDraftText('');
      setCurrentDraft(null);
      setSelectedMessages(new Set());
      setExplicitSelectedMessageId(null);
      setAiPopoverOpen(false);
      setIsBatchMode(false);
      return;
    }

    setSelectedMessages(new Set());
    setExplicitSelectedMessageId(null);
    setAiPopoverOpen(false);
    setIsBatchMode(false);
    void loadMessages(selectedConversationId);
  }, [loadMessages, selectedConversationId]);

  useEffect(() => {
    if (!explicitSelectedMessageId) {
      return;
    }

    const selectedMessage =
      messages.find((message) => message.id === explicitSelectedMessageId) ??
      null;
    if (!selectedMessage || !canSelectActionTarget(selectedMessage)) {
      setExplicitSelectedMessageId(null);
    }
  }, [explicitSelectedMessageId, messages]);

  useEffect(() => {
    const viewport = getMessagesViewport();
    if (!viewport) {
      return;
    }

    const handleScroll = () => {
      const distance =
        viewport.scrollHeight - viewport.scrollTop - viewport.clientHeight;
      autoScrollToBottomRef.current = distance <= SCROLL_BOTTOM_THRESHOLD;
    };

    handleScroll();
    viewport.addEventListener('scroll', handleScroll, { passive: true });
    return () => viewport.removeEventListener('scroll', handleScroll);
  }, [getMessagesViewport, messagesLoading, selectedConversationId]);

  const sortedMessages = useMemo(() => sortMessages(messages), [messages]);

  useLayoutEffect(() => {
    if (selectedConversationId === null) {
      previousConversationIdRef.current = null;
      previousLastMessageIdRef.current = null;
      return;
    }

    const lastMessageId = sortedMessages.at(-1)?.id ?? null;
    const conversationChanged =
      previousConversationIdRef.current !== selectedConversationId;

    if (
      conversationChanged ||
      lastMessageId !== previousLastMessageIdRef.current
    ) {
      window.requestAnimationFrame(() => {
        if (conversationChanged || autoScrollToBottomRef.current) {
          scrollToBottom(conversationChanged ? 'auto' : 'smooth');
        }
      });
    }

    previousConversationIdRef.current = selectedConversationId;
    previousLastMessageIdRef.current = lastMessageId;
  }, [scrollToBottom, selectedConversationId, sortedMessages]);

  useBotDatabaseEvents({
    enabled: botEnabled,
    onMessageCreated: () => {
      void loadConversations();
      if (selectedConversationIdRef.current !== null) {
        void loadMessages(selectedConversationIdRef.current, {
          preserveDraftText: true,
        });
      }
    },
    onMessageUpdated: () => {
      void loadConversations();
      if (selectedConversationIdRef.current !== null) {
        void loadMessages(selectedConversationIdRef.current, {
          preserveDraftText: true,
        });
      }
    },
    onMessageDeleted: () => {
      void loadConversations();
      if (selectedConversationIdRef.current !== null) {
        void loadMessages(selectedConversationIdRef.current, {
          preserveDraftText: false,
        });
      }
    },
    onConversationUpdated: () => {
      void loadConversations();
    },
  });

  const defaultActionMessage = useMemo(
    () => findDefaultActionMessage(sortedMessages),
    [sortedMessages],
  );
  const explicitSelectedMessage =
    explicitSelectedMessageId === null
      ? null
      : (messages.find((message) => message.id === explicitSelectedMessageId) ??
        null);
  const activeActionMessage =
    explicitSelectedMessage && canGenerateDraft(explicitSelectedMessage)
      ? explicitSelectedMessage
      : defaultActionMessage;
  const actionDisabledReason = !botEnabled
    ? '请先启用机器人'
    : activeActionMessage
      ? undefined
      : '请先选择一条可处理的客户消息';
  const actionableMessages = useMemo(
    () => sortedMessages.filter(canBatchSelectMessage),
    [sortedMessages],
  );
  const selectedCount = selectedMessages.size;
  const allMessagesSelected =
    actionableMessages.length > 0 &&
    actionableMessages.every((message) => selectedMessages.has(message.id));

  const focusDraftMessage = useCallback((message: BotMessage) => {
    if (selectedConversationIdRef.current === null || !message.draft_text) {
      return;
    }

    setCurrentDraft((previousDraft) =>
      buildDraftState(
        message,
        selectedConversationIdRef.current as number,
        previousDraft,
      ),
    );
    setDraftText(message.draft_text);
    setOriginalDraftText(message.draft_text);
  }, []);

  const restoreDraftFromMessage = useCallback(
    (
      message: BotMessage,
      conversationId: number,
      options?: DraftRestoreOptions,
    ) => {
      const nextDraftText = getDraftTextFromMessage(message);
      if (!nextDraftText) {
        return false;
      }

      const previousDraft = currentDraftRef.current;
      setCurrentDraft(buildDraftState(message, conversationId, previousDraft));

      const shouldPreserveUserText =
        !options?.force &&
        draftDirtyRef.current &&
        previousDraft?.conversationId === conversationId;
      if (!shouldPreserveUserText) {
        setDraftText(nextDraftText);
        setOriginalDraftText(nextDraftText);
      }
      return true;
    },
    [],
  );

  const restoreDraftFromReplyDraft = useCallback(
    (
      draft: ReplyDraft,
      conversationId: number,
      messageId: number,
      options?: DraftRestoreOptions,
    ) => {
      const draftMessage = buildMessageFromReplyDraft(
        draft,
        messageId,
        conversationId,
      );
      return restoreDraftFromMessage(draftMessage, conversationId, options);
    },
    [restoreDraftFromMessage],
  );

  const handleGenerateDraftDeterministic = useCallback(
    async (messageId: number) => {
      if (!botEnabled) {
        toast.error('Please enable the bot first.');
        return;
      }

      const requestedConversationId = selectedConversationIdRef.current;
      if (requestedConversationId === null) {
        toast.error('璇峰厛閫夋嫨浼氳瘽');
        return;
      }

      setGeneratingDraft(true);
      try {
        const result = await dataSource.generateDraft(messageId.toString());
        const isStillViewingRequestedConversation =
          selectedConversationIdRef.current === requestedConversationId;

        const restoredFromDirectResponse =
          isStillViewingRequestedConversation && result.draft?.content
            ? restoreDraftFromReplyDraft(
                result.draft,
                requestedConversationId,
                result.draft.message_id ?? messageId,
                { force: true },
              )
            : false;

        if (result.status === 'processing') {
          toast.info('Draft generation is still processing.');
        } else if (result.status === 'already_succeeded') {
          toast.info('A draft already exists for this message.');
        }

        const refreshedMessages = await dataSource.listMessages(
          requestedConversationId.toString(),
        );
        const refreshedTargetMessage =
          refreshedMessages.messages.find(
            (message) => message.id === messageId,
          ) ?? null;

        if (isStillViewingRequestedConversation) {
          setMessages(refreshedMessages.messages);
        }

        const restoredFromRefreshedMessage =
          isStillViewingRequestedConversation &&
          refreshedTargetMessage &&
          canRestoreDraftFromMessage(refreshedTargetMessage)
            ? restoreDraftFromMessage(
                refreshedTargetMessage,
                requestedConversationId,
                { force: true },
              )
            : false;

        await loadConversations();

        if (isStillViewingRequestedConversation) {
          setAiPopoverOpen(false);
        }

        if (
          result.status !== 'processing' &&
          !restoredFromDirectResponse &&
          !restoredFromRefreshedMessage
        ) {
          console.warn('generateDraft response missing restorable draft', {
            messageId,
            requestedConversationId,
            responseStatus: result.status,
            hasResponseDraft: Boolean(result.draft?.content),
            refreshedMessageStatus: refreshedTargetMessage?.status ?? null,
            hasRefreshedDraftText: Boolean(refreshedTargetMessage?.draft_text),
          });
          toast.error(
            'Draft generation finished but no restorable draft was returned.',
          );
        } else if (
          result.status === 'succeeded' &&
          (restoredFromDirectResponse || restoredFromRefreshedMessage)
        ) {
          toast.success('鑽夌鐢熸垚鎴愬姛');
        }
      } catch (error: any) {
        console.error('Failed to generate draft:', error);
        toast.error(error?.message || '鑽夌鐢熸垚澶辫触');
      } finally {
        setGeneratingDraft(false);
      }
    },
    [
      botEnabled,
      dataSource,
      loadConversations,
      restoreDraftFromMessage,
      restoreDraftFromReplyDraft,
    ],
  );

  const handleSaveDraft = useCallback(async () => {
    if (!currentDraft) {
      toast.error('当前没有可保存的草稿');
      return;
    }

    if (!draftText.trim()) {
      toast.error('草稿内容不能为空');
      return;
    }

    setDraftSaving(true);
    try {
      await dataSource.updateDraft(
        currentDraft.messageId.toString(),
        draftText,
        currentDraft.draftId?.toString() ?? null,
      );
      setOriginalDraftText(draftText);
      setCurrentDraft((previousDraft) =>
        previousDraft
          ? {
              ...previousDraft,
              source: 'manual',
              updatedAt: new Date().toISOString(),
              version: previousDraft.version + 1,
            }
          : previousDraft,
      );
      toast.success('草稿已保存');
      if (selectedConversationIdRef.current !== null) {
        await loadMessages(selectedConversationIdRef.current, {
          preserveDraftText: true,
        });
      }
    } catch (error: any) {
      console.error('Failed to save draft:', error);
      toast.error(error?.message || '保存草稿失败');
    } finally {
      setDraftSaving(false);
    }
  }, [currentDraft, dataSource, draftText, loadMessages]);

  const handleCopyDraft = useCallback(() => {
    copyToClipboard(draftText)
      .then(() => {
        setCopied(true);
        window.setTimeout(() => setCopied(false), 2_000);
        toast.success('草稿已复制');
      })
      .catch(() => {
        toast.error('复制草稿失败');
      });
  }, [draftText]);

  const handleProcessMessage = useCallback(
    async (messageId: number) => {
      try {
        await dataSource.processMessage(messageId.toString());
        toast.success('消息已标记为已处理');
        await refreshConversationData();
      } catch (error) {
        console.error('Failed to process message:', error);
        toast.error('标记已处理失败');
      }
    },
    [dataSource, refreshConversationData],
  );

  const handleSkipMessage = useCallback(
    async (messageId: number) => {
      try {
        await dataSource.skipMessage(messageId.toString());
        toast.success('消息已跳过');
        await refreshConversationData();
      } catch (error) {
        console.error('Failed to skip message:', error);
        toast.error('跳过消息失败');
      }
    },
    [dataSource, refreshConversationData],
  );

  const handleDeleteMessage = useCallback(
    async (messageId: number) => {
      try {
        await dataSource.deleteMessage(messageId.toString());
        toast.success('消息已删除');
        setDeleteDialogOpen(false);
        setMessageToDelete(null);
        await refreshConversationData();
      } catch (error) {
        console.error('Failed to delete message:', error);
        toast.error('删除消息失败');
      }
    },
    [dataSource, refreshConversationData],
  );

  const runBatchAction = useCallback(
    async (
      key: 'process' | 'skip' | 'delete',
      action: () => Promise<{ succeeded: number; failed: number }>,
      successLabel: string,
    ) => {
      if (selectedMessages.size === 0 || batchBusyKey) {
        return;
      }

      setBatchBusyKey(key);
      try {
        const result = await action();
        toast.success(
          `${successLabel}：成功 ${result.succeeded} 条，失败 ${result.failed} 条`,
        );
        setSelectedMessages(new Set());
        await refreshConversationData();
      } catch (error) {
        console.error('Failed to run batch action:', error);
        toast.error('批量操作失败');
      } finally {
        setBatchBusyKey(null);
      }
    },
    [batchBusyKey, refreshConversationData, selectedMessages.size],
  );

  const handleBatchProcess = useCallback(async () => {
    await runBatchAction(
      'process',
      async () => {
        const result = await dataSource.batchProcess(
          Array.from(selectedMessages).map((messageId) => messageId.toString()),
        );
        return { succeeded: result.succeeded, failed: result.failed };
      },
      '批量标记已处理完成',
    );
  }, [dataSource, runBatchAction, selectedMessages]);

  const handleBatchSkip = useCallback(async () => {
    await runBatchAction(
      'skip',
      async () => {
        const result = await dataSource.batchSkip(
          Array.from(selectedMessages).map((messageId) => messageId.toString()),
        );
        return { succeeded: result.succeeded, failed: result.failed };
      },
      '批量跳过完成',
    );
  }, [dataSource, runBatchAction, selectedMessages]);

  const handleBatchDelete = useCallback(async () => {
    await runBatchAction(
      'delete',
      async () => {
        const result = await dataSource.batchDelete(
          Array.from(selectedMessages).map((messageId) => messageId.toString()),
        );
        return { succeeded: result.succeeded, failed: result.failed };
      },
      '批量删除完成',
    );
    setBatchDeleteDialogOpen(false);
  }, [dataSource, runBatchAction, selectedMessages]);

  const exitBatchMode = useCallback(() => {
    setIsBatchMode(false);
    setSelectedMessages(new Set());
  }, []);

  const toggleMessageSelection = useCallback((messageId: number) => {
    setSelectedMessages((currentSelection) => {
      const nextSelection = new Set(currentSelection);
      if (nextSelection.has(messageId)) {
        nextSelection.delete(messageId);
      } else {
        nextSelection.add(messageId);
      }
      return nextSelection;
    });
  }, []);

  const toggleSelectAll = useCallback(() => {
    if (allMessagesSelected) {
      setSelectedMessages(new Set());
      return;
    }

    setSelectedMessages(
      new Set(actionableMessages.map((message) => message.id)),
    );
  }, [actionableMessages, allMessagesSelected]);

  return (
    <div className="flex h-full gap-4">
      <div className="flex w-80 min-h-0 shrink-0 flex-col gap-2">
        <div className="flex gap-2">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={searchKeyword}
              onChange={(event) => setSearchKeyword(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter') {
                  applySearch();
                }
              }}
              placeholder="搜索会话"
              className="pl-9"
            />
          </div>
          <Button
            type="button"
            size="icon"
            variant="outline"
            onClick={applySearch}
            aria-label="刷新会话列表"
          >
            <RefreshCw className="size-4" />
          </Button>
        </div>

        <Select
          value={statusFilter}
          onValueChange={(value) =>
            setStatusFilter(value as MessageStatusFilter)
          }
        >
          <SelectTrigger>
            <SelectValue placeholder="按状态筛选" />
          </SelectTrigger>
          <SelectContent>
            {STATUS_OPTIONS.map((option) => (
              <SelectItem key={option} value={option}>
                {option === 'all'
                  ? '全部'
                  : formatStatus(option as BotMessage['status'])}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <ScrollArea className="min-h-0 flex-1 rounded-xl border">
          <div className="space-y-1 p-2">
            {loading && conversations.length === 0 ? (
              <div className="py-8 text-center text-sm text-muted-foreground">
                加载中...
              </div>
            ) : null}
            {!loading && conversations.length === 0 ? (
              <div className="py-8 text-center text-sm text-muted-foreground">
                暂无会话
              </div>
            ) : null}
            {conversations.map((conversation) => {
              const isSelected = selectedConversationId === conversation.id;
              return (
                <button
                  key={conversation.id}
                  type="button"
                  onClick={() => setSelectedConversationId(conversation.id)}
                  className={cn(
                    'w-full rounded-xl px-3 py-3 text-left transition-colors',
                    isSelected ? 'bg-accent' : 'hover:bg-accent/60',
                  )}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="truncate text-sm font-medium">
                        {conversation.conversation_name}
                      </div>
                      <div className="mt-0.5 truncate text-xs text-muted-foreground">
                        {formatConversationType(conversation.conversation_type)}
                        {conversation.latest_customer
                          ? ` · ${conversation.latest_customer}`
                          : ''}
                      </div>
                    </div>
                    <div className="text-[11px] text-muted-foreground">
                      {formatRelativeTime(conversation.last_message_at)}
                    </div>
                  </div>
                  <div className="mt-2 flex items-center justify-between gap-2">
                    <div className="line-clamp-1 min-w-0 text-xs text-muted-foreground">
                      {conversation.latest_message_summary || '暂无消息'}
                    </div>
                    <div className="flex shrink-0 items-center gap-1">
                      {conversation.pending_count > 0 ? (
                        <Badge
                          variant="secondary"
                          className="h-5 rounded-full px-2 text-[11px]"
                        >
                          {conversation.pending_count}
                        </Badge>
                      ) : null}
                      {conversation.failed_count > 0 ? (
                        <Badge
                          variant="destructive"
                          className="h-5 rounded-full px-2 text-[11px]"
                        >
                          {conversation.failed_count}
                        </Badge>
                      ) : null}
                    </div>
                  </div>
                </button>
              );
            })}
          </div>
        </ScrollArea>
      </div>

      <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden rounded-2xl border bg-background">
        {!selectedConversation ? (
          <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
            请选择一个会话
          </div>
        ) : (
          <>
            <div className="border-b px-4 py-3">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="truncate text-base font-semibold">
                    {selectedConversation.conversation_name}
                  </div>
                  <div className="mt-1 flex flex-wrap items-center gap-1 text-sm text-muted-foreground">
                    <span>
                      {formatConversationType(
                        selectedConversation.conversation_type,
                      )}
                    </span>
                    <span>·</span>
                    <span className="truncate">
                      {selectedConversation.external_conversation_id}
                    </span>
                  </div>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  {defaultActionMessage ? (
                    <Badge variant="outline">
                      默认目标 #{defaultActionMessage.id}
                    </Badge>
                  ) : null}
                  {explicitSelectedMessage ? (
                    <Badge variant="secondary">
                      当前选择 #{explicitSelectedMessage.id}
                    </Badge>
                  ) : null}
                  <Button
                    type="button"
                    size="sm"
                    variant={isBatchMode ? 'secondary' : 'outline'}
                    onClick={() => {
                      if (isBatchMode) {
                        exitBatchMode();
                      } else {
                        setIsBatchMode(true);
                      }
                    }}
                  >
                    {isBatchMode ? '退出批量模式' : '批量操作'}
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    variant="ghost"
                    onClick={() => void refreshConversationData()}
                  >
                    刷新
                  </Button>
                </div>
              </div>
            </div>

            {isBatchMode ? (
              <div className="border-b bg-muted/30 px-4 py-3">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-sm font-medium">
                    已选择 {selectedCount} 条
                  </span>
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    onClick={toggleSelectAll}
                  >
                    全选
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    disabled={selectedCount === 0 || batchBusyKey !== null}
                    onClick={() => void handleBatchProcess()}
                  >
                    <CheckCheck className="mr-1 size-4" />
                    标记已处理
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    disabled={selectedCount === 0 || batchBusyKey !== null}
                    onClick={() => void handleBatchSkip()}
                  >
                    <SkipForward className="mr-1 size-4" />
                    跳过
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    variant="destructive"
                    disabled={selectedCount === 0 || batchBusyKey !== null}
                    onClick={() => setBatchDeleteDialogOpen(true)}
                  >
                    <Trash2 className="mr-1 size-4" />
                    删除
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    variant="ghost"
                    onClick={exitBatchMode}
                  >
                    退出批量模式
                  </Button>
                </div>
              </div>
            ) : null}

            <div className="flex min-h-0 flex-1 flex-col">
              <ScrollArea
                ref={messagesScrollAreaRef}
                className="min-h-0 flex-1"
              >
                <div className="space-y-4 px-4 py-4">
                  {messagesLoading ? (
                    <div className="flex py-10 justify-center">
                      <RefreshCw className="size-5 animate-spin text-muted-foreground" />
                    </div>
                  ) : null}
                  {!messagesLoading && sortedMessages.length === 0 ? (
                    <div className="py-10 text-center text-sm text-muted-foreground">
                      当前会话暂无消息
                    </div>
                  ) : null}

                  {!messagesLoading
                    ? sortedMessages.map((message) => {
                        const isExplicitSelection =
                          explicitSelectedMessageId === message.id;
                        const isDefaultSelection =
                          !isExplicitSelection &&
                          !explicitSelectedMessage &&
                          defaultActionMessage?.id === message.id;
                        const bubbleStateTone = isExplicitSelection
                          ? 'explicit'
                          : isDefaultSelection
                            ? 'default'
                            : 'muted';
                        const draftMeta =
                          currentDraft?.messageId === message.id
                            ? currentDraft
                            : message.draft_text
                              ? buildDraftState(
                                  message,
                                  selectedConversation.id,
                                  null,
                                )
                              : null;
                        const showActionMenu =
                          isCustomerMessage(message) && !isBatchMode;

                        return (
                          <React.Fragment key={message.id}>
                            <ChatMessageBubble
                              side={
                                isCustomerMessage(message)
                                  ? 'customer'
                                  : 'assistant'
                              }
                              interactive={
                                canSelectActionTarget(message) && !isBatchMode
                              }
                              onClick={
                                canSelectActionTarget(message) && !isBatchMode
                                  ? () =>
                                      setExplicitSelectedMessageId(message.id)
                                  : undefined
                              }
                              stateTone={bubbleStateTone}
                              aside={
                                isBatchMode &&
                                canBatchSelectMessage(message) ? (
                                  <Checkbox
                                    checked={selectedMessages.has(message.id)}
                                    onCheckedChange={() =>
                                      toggleMessageSelection(message.id)
                                    }
                                    aria-label={`选择消息 ${message.id}`}
                                  />
                                ) : undefined
                              }
                              content={
                                <div className="min-w-0 text-sm leading-6">
                                  <MessageContentRenderer
                                    content={message.content}
                                    maxLines={0}
                                  />
                                </div>
                              }
                              meta={
                                <div className="flex flex-wrap items-center gap-1.5">
                                  <span>{message.sender_name}</span>
                                  <span>·</span>
                                  <span>{formatDateTime(message.sent_at)}</span>
                                  <span>·</span>
                                  <span
                                    className={cn(
                                      'inline-flex items-center gap-1',
                                      statusTextClass(message.status),
                                    )}
                                  >
                                    <span className="size-1.5 rounded-full bg-current" />
                                    {formatStatus(message.status)}
                                  </span>
                                </div>
                              }
                              errorText={message.last_error}
                              actionMenu={
                                showActionMenu ? (
                                  <DatabaseMessageActionsMenu
                                    messageId={message.id}
                                    onDelete={() => {
                                      setMessageToDelete(message.id);
                                      setDeleteDialogOpen(true);
                                    }}
                                    onGenerateSmartReply={() =>
                                      void handleGenerateDraftDeterministic(
                                        message.id,
                                      )
                                    }
                                    onMarkProcessed={() =>
                                      void handleProcessMessage(message.id)
                                    }
                                    onSetCurrentMessage={() =>
                                      setExplicitSelectedMessageId(message.id)
                                    }
                                    onSkip={() =>
                                      void handleSkipMessage(message.id)
                                    }
                                    setCurrentMessageDisabled={
                                      !canSelectActionTarget(message)
                                    }
                                    smartReplyDisabled={
                                      !botEnabled || !canGenerateDraft(message)
                                    }
                                    processDisabled={
                                      !canProcessMessage(message)
                                    }
                                    skipDisabled={!canProcessMessage(message)}
                                  />
                                ) : undefined
                              }
                            />

                            {message.draft_text ? (
                              <ChatMessageBubble
                                side="assistant"
                                interactive={!isBatchMode}
                                onClick={
                                  !isBatchMode
                                    ? () => focusDraftMessage(message)
                                    : undefined
                                }
                                label="AI 草稿"
                                content={
                                  <div className="min-w-0 text-sm leading-6">
                                    <MessageContentRenderer
                                      content={message.draft_text}
                                      maxLines={0}
                                    />
                                  </div>
                                }
                                meta={
                                  <div className="flex flex-wrap items-center gap-1.5">
                                    <span>未发送</span>
                                    <span>·</span>
                                    <span>
                                      {formatDraftSource(message.draft_source)}
                                    </span>
                                    {draftMeta?.version ? (
                                      <>
                                        <span>·</span>
                                        <span>v{draftMeta.version}</span>
                                      </>
                                    ) : null}
                                    <span>·</span>
                                    <span>
                                      {formatDateTime(
                                        draftMeta?.updatedAt ??
                                          message.updated_at,
                                      )}
                                    </span>
                                  </div>
                                }
                              />
                            ) : null}
                          </React.Fragment>
                        );
                      })
                    : null}
                </div>
              </ScrollArea>

              <DatabaseChatComposer
                aiActions={
                  <DatabaseAiActionPopover
                    open={aiPopoverOpen}
                    onOpenChange={setAiPopoverOpen}
                    disabledReason={actionDisabledReason}
                    generatingDraft={generatingDraft}
                    onGenerateSmartReply={() => {
                      if (!activeActionMessage) {
                        return;
                      }
                      void handleGenerateDraftDeterministic(
                        activeActionMessage.id,
                      );
                    }}
                  />
                }
                copied={copied}
                draftMeta={currentDraft}
                draftSaving={draftSaving}
                draftText={draftText}
                generatingDraft={generatingDraft}
                hasUnsavedChanges={hasUnsavedDraftChanges}
                onCancel={() => setDraftText(originalDraftText)}
                onCopy={handleCopyDraft}
                onDraftTextChange={setDraftText}
                onRegenerate={() => {
                  if (!currentDraft) {
                    return;
                  }
                  void handleGenerateDraftDeterministic(currentDraft.messageId);
                }}
                onSave={() => void handleSaveDraft()}
              />
            </div>
          </>
        )}
      </div>

      <AlertDialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>确认删除</AlertDialogTitle>
            <AlertDialogDescription>
              删除后无法恢复，确认继续吗？
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                if (messageToDelete !== null) {
                  void handleDeleteMessage(messageToDelete);
                }
              }}
            >
              删除
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog
        open={batchDeleteDialogOpen}
        onOpenChange={setBatchDeleteDialogOpen}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>确认批量删除</AlertDialogTitle>
            <AlertDialogDescription>
              将删除 {selectedCount} 条消息，删除后无法恢复。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction onClick={() => void handleBatchDelete()}>
              删除
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
});
