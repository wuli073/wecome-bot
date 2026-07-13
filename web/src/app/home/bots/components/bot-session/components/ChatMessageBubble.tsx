import type { ReactNode } from 'react';

import { AlertCircle } from 'lucide-react';

import { cn } from '@/lib/utils';

interface ChatMessageBubbleProps {
  actionMenu?: ReactNode;
  aside?: ReactNode;
  content: ReactNode;
  errorText?: string;
  interactive?: boolean;
  label?: string;
  meta: ReactNode;
  onClick?: () => void;
  side: 'customer' | 'assistant';
  stateTone?: 'default' | 'explicit' | 'muted';
}

export function ChatMessageBubble({
  actionMenu,
  aside,
  content,
  errorText,
  interactive = false,
  label,
  meta,
  onClick,
  side,
  stateTone = 'muted',
}: ChatMessageBubbleProps) {
  const bubbleTone =
    side === 'customer'
      ? 'bg-primary/10 text-foreground'
      : 'bg-muted/70 text-foreground';
  const selectionTone =
    stateTone === 'explicit'
      ? 'ring-2 ring-primary/60'
      : stateTone === 'default'
        ? 'ring-1 ring-primary/30'
        : '';

  return (
    <div
      className={cn(
        'group flex gap-2',
        side === 'customer' ? 'justify-end' : 'justify-start',
      )}
    >
      {side === 'assistant' && aside ? (
        <div className="pt-3">{aside}</div>
      ) : null}
      <div
        className={cn(
          'flex max-w-[72%] min-w-0 flex-col gap-1',
          side === 'customer' ? 'items-end' : 'items-start',
        )}
      >
        {label ? (
          <div className="px-1 text-[11px] font-medium text-muted-foreground">
            {label}
          </div>
        ) : null}
        <div
          className={cn(
            'flex min-w-0 gap-2',
            side === 'customer' ? 'flex-row-reverse' : 'flex-row',
          )}
        >
          {side === 'customer' && aside ? (
            <div className="pt-3">{aside}</div>
          ) : null}
          <div className="min-w-0">
            <div
              role={interactive ? 'button' : undefined}
              tabIndex={interactive ? 0 : undefined}
              onClick={onClick}
              onKeyDown={
                interactive && onClick
                  ? (event) => {
                      if (event.key === 'Enter' || event.key === ' ') {
                        event.preventDefault();
                        onClick();
                      }
                    }
                  : undefined
              }
              className={cn(
                'rounded-2xl px-4 py-3 shadow-sm transition-colors',
                side === 'customer' ? 'rounded-br-md' : 'rounded-bl-md',
                bubbleTone,
                selectionTone,
                interactive &&
                  'cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/60',
              )}
            >
              {content}
            </div>
            <div
              className={cn(
                'mt-1 flex min-h-6 items-center gap-2 px-1 text-[11px] text-muted-foreground',
                side === 'customer' ? 'justify-end' : 'justify-start',
              )}
            >
              <div className="min-w-0">{meta}</div>
              {actionMenu ? (
                <div className="opacity-0 transition-opacity group-hover:opacity-100 group-focus-within:opacity-100">
                  {actionMenu}
                </div>
              ) : null}
            </div>
            {errorText ? (
              <div className="mt-1 flex max-w-full items-start gap-1 px-1 text-[11px] text-destructive">
                <AlertCircle className="mt-0.5 size-3 shrink-0" />
                <span className="truncate" title={errorText}>
                  {errorText}
                </span>
              </div>
            ) : null}
          </div>
        </div>
      </div>
    </div>
  );
}
