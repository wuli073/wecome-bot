import type { ReactNode } from 'react';
import { useLayoutEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';

import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Textarea } from '@/components/ui/textarea';
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import {
  Check,
  Copy,
  MoreHorizontal,
  Paperclip,
  RefreshCw,
  Send,
  Trash2,
} from 'lucide-react';

export interface ComposerDraftMeta {
  source: 'pipeline' | 'manual';
  updatedAt?: string;
  version: number;
}

interface DatabaseChatComposerProps {
  aiActions: ReactNode;
  canSaveDraft: boolean;
  composerText: string;
  copied: boolean;
  draftMeta: ComposerDraftMeta | null;
  draftSaving: boolean;
  generatingDraft: boolean;
  hasComposerContent: boolean;
  hasPersistedDraft: boolean;
  isClearedLocally: boolean;
  hasUnsavedChanges: boolean;
  sendButtonLabel: string;
  sendDisabledReason?: string | null;
  sendInProgress: boolean;
  sendStatusText?: string | null;
  showCancelSend: boolean;
  onCancelSend: () => void;
  onClear: () => void;
  onCopy: () => void;
  onComposerTextChange: (value: string) => void;
  onRegenerate: () => void;
  onRequestDeleteDraft: () => void;
  onSave: () => void;
  onSend: () => void;
  onUndoEdit: () => void;
}

const MIN_TEXTAREA_HEIGHT = 96;
const MAX_TEXTAREA_HEIGHT = 240;

export function DatabaseChatComposer({
  aiActions,
  canSaveDraft,
  composerText,
  copied,
  draftMeta,
  draftSaving,
  generatingDraft,
  hasComposerContent,
  hasPersistedDraft,
  isClearedLocally,
  hasUnsavedChanges,
  sendButtonLabel,
  sendDisabledReason,
  sendInProgress,
  sendStatusText,
  showCancelSend,
  onCancelSend,
  onClear,
  onCopy,
  onComposerTextChange,
  onRegenerate,
  onRequestDeleteDraft,
  onSave,
  onSend,
  onUndoEdit,
}: DatabaseChatComposerProps) {
  const { t } = useTranslation();
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const showFullToolbar = hasComposerContent;
  const showCompactToolbar = !hasComposerContent && isClearedLocally;
  const toolbarStatusText = sendStatusText;

  useLayoutEffect(() => {
    const textarea = textareaRef.current;
    if (!textarea) {
      return;
    }

    textarea.style.height = '0px';
    const nextHeight = Math.min(textarea.scrollHeight, MAX_TEXTAREA_HEIGHT);
    textarea.style.height = `${Math.max(MIN_TEXTAREA_HEIGHT, nextHeight)}px`;
    textarea.style.overflowY =
      textarea.scrollHeight > MAX_TEXTAREA_HEIGHT ? 'auto' : 'hidden';
  }, [composerText]);

  return (
    <div className="sticky bottom-0 z-10 border-t bg-background/95 px-4 py-3 backdrop-blur supports-[backdrop-filter]:bg-background/80">
      {showFullToolbar ? (
        <div
          className={`mb-3 flex flex-wrap items-center gap-2 rounded-xl border bg-muted/40 px-3 py-2 text-sm ${
            toolbarStatusText ? 'justify-between' : 'justify-end'
          }`}
        >
          {toolbarStatusText ? (
            <span className="text-muted-foreground">{toolbarStatusText}</span>
          ) : null}
          <div className="flex flex-wrap items-center gap-1">
            {showCancelSend ? (
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={onCancelSend}
              >
                {t('common.cancel')}
              </Button>
            ) : null}
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={onCopy}
              disabled={!composerText}
            >
              {copied ? (
                <Check className="mr-1 size-4" />
              ) : (
                <Copy className="mr-1 size-4" />
              )}
              {t('bots.sessionMonitor.databaseComposer.copy')}
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={onRegenerate}
              disabled={!draftMeta || generatingDraft}
            >
              <RefreshCw
                className={`mr-1 size-4 ${generatingDraft ? 'animate-spin' : ''}`}
              />
              {t('bots.sessionMonitor.databaseComposer.regenerate')}
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={onSave}
              disabled={
                !canSaveDraft ||
                !hasComposerContent ||
                !hasUnsavedChanges ||
                draftSaving
              }
            >
              {t('bots.sessionMonitor.databaseComposer.save')}
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={onUndoEdit}
              disabled={!hasUnsavedChanges}
            >
              {t('bots.sessionMonitor.databaseComposer.undoEdit')}
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={onClear}
              disabled={!composerText}
              aria-label={t('bots.sessionMonitor.databaseComposer.clear')}
            >
              {t('bots.sessionMonitor.databaseComposer.clear')}
            </Button>
            {hasPersistedDraft ? (
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    aria-label={t(
                      'bots.sessionMonitor.databaseComposer.moreActions',
                    )}
                  >
                    <MoreHorizontal className="size-4" />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end" className="w-40">
                  <DropdownMenuItem
                    className="text-destructive focus:text-destructive"
                    onClick={onRequestDeleteDraft}
                  >
                    <Trash2 className="mr-2 size-4" />
                    {t('bots.sessionMonitor.databaseComposer.deleteDraft')}
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            ) : null}
          </div>
        </div>
      ) : showCompactToolbar ? (
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2 rounded-xl border bg-muted/40 px-3 py-2 text-sm">
          <span className="text-muted-foreground">
            {t('bots.sessionMonitor.databaseComposer.clearedUnsaved')}
          </span>
          <Button type="button" variant="ghost" size="sm" onClick={onUndoEdit}>
            {t('bots.sessionMonitor.databaseComposer.undoEdit')}
          </Button>
        </div>
      ) : null}

      <div className="flex items-end gap-2">
        <Tooltip>
          <TooltipTrigger asChild>
            <span className="block">
              <Button
                type="button"
                size="icon"
                variant="outline"
                disabled
                aria-label={t(
                  'bots.sessionMonitor.databaseComposer.attachmentUnavailable',
                )}
              >
                <Paperclip className="size-4" />
              </Button>
            </span>
          </TooltipTrigger>
          <TooltipContent>
            {t('bots.sessionMonitor.databaseComposer.attachmentUnavailable')}
          </TooltipContent>
        </Tooltip>

        <Textarea
          ref={textareaRef}
          aria-label={t('bots.sessionMonitor.databaseComposer.ariaLabel')}
          value={composerText}
          onChange={(event) => onComposerTextChange(event.target.value)}
          placeholder={t('bots.sessionMonitor.databaseComposer.placeholder')}
          rows={4}
          className="min-h-24 max-h-60 resize-none"
        />

        {aiActions}

        <Tooltip>
          <TooltipTrigger asChild>
            <span className="block">
              <Button
                type="button"
                size="icon"
                disabled={sendInProgress || Boolean(sendDisabledReason)}
                onClick={onSend}
                aria-label={sendButtonLabel}
              >
                {sendInProgress ? (
                  <RefreshCw className="size-4 animate-spin" />
                ) : (
                  <Send className="size-4" />
                )}
              </Button>
            </span>
          </TooltipTrigger>
          <TooltipContent>
            {sendDisabledReason ?? sendButtonLabel}
          </TooltipContent>
        </Tooltip>
      </div>
    </div>
  );
}
