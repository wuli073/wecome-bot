import type { ReactNode } from 'react';
import { useLayoutEffect, useRef } from 'react';

import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { Check, Copy, Paperclip, RefreshCw, Send } from 'lucide-react';

export interface ComposerDraftMeta {
  source: 'pipeline' | 'manual';
  updatedAt?: string;
  version: number;
}

interface DatabaseChatComposerProps {
  aiActions: ReactNode;
  copied: boolean;
  draftMeta: ComposerDraftMeta | null;
  draftSaving: boolean;
  draftText: string;
  generatingDraft: boolean;
  hasUnsavedChanges: boolean;
  onCancel: () => void;
  onCopy: () => void;
  onDraftTextChange: (value: string) => void;
  onRegenerate: () => void;
  onSave: () => void;
}

const MIN_TEXTAREA_HEIGHT = 96;
const MAX_TEXTAREA_HEIGHT = 240;

function formatUpdatedAt(updatedAt?: string) {
  if (!updatedAt) {
    return '更新时间未知';
  }

  return `更新时间 ${new Date(updatedAt).toLocaleString()}`;
}

function formatDraftMeta(draftMeta: ComposerDraftMeta) {
  const sourceLabel = draftMeta.source === 'pipeline' ? 'Pipeline' : 'Manual';
  return `草稿 v${draftMeta.version} · ${sourceLabel} · ${formatUpdatedAt(draftMeta.updatedAt)}`;
}

export function DatabaseChatComposer({
  aiActions,
  copied,
  draftMeta,
  draftSaving,
  draftText,
  generatingDraft,
  hasUnsavedChanges,
  onCancel,
  onCopy,
  onDraftTextChange,
  onRegenerate,
  onSave,
}: DatabaseChatComposerProps) {
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const showToolbar = generatingDraft || Boolean(draftMeta);

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
  }, [draftText]);

  return (
    <div className="sticky bottom-0 z-10 border-t bg-background/95 px-4 py-3 backdrop-blur supports-[backdrop-filter]:bg-background/80">
      {showToolbar ? (
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2 rounded-xl border bg-muted/40 px-3 py-2 text-sm">
          <span className="text-muted-foreground">
            {draftMeta ? formatDraftMeta(draftMeta) : '草稿生成中...'}
          </span>
          <div className="flex flex-wrap items-center gap-1">
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={onCopy}
              disabled={!draftText}
            >
              {copied ? (
                <Check className="mr-1 size-4" />
              ) : (
                <Copy className="mr-1 size-4" />
              )}
              复制
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
              重新生成
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={onSave}
              disabled={!draftMeta || !hasUnsavedChanges || draftSaving}
            >
              保存
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={onCancel}
              disabled={!hasUnsavedChanges}
            >
              取消
            </Button>
          </div>
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
                aria-label="附件功能暂未接入"
              >
                <Paperclip className="size-4" />
              </Button>
            </span>
          </TooltipTrigger>
          <TooltipContent>附件能力暂未接入</TooltipContent>
        </Tooltip>

        <Textarea
          ref={textareaRef}
          aria-label="Composer draft"
          value={draftText}
          onChange={(event) => onDraftTextChange(event.target.value)}
          placeholder="输入回复内容，或使用智能回复生成草稿"
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
                disabled
                aria-label="发送能力暂未接入"
              >
                <Send className="size-4" />
              </Button>
            </span>
          </TooltipTrigger>
          <TooltipContent>发送能力暂未接入</TooltipContent>
        </Tooltip>
      </div>
    </div>
  );
}
