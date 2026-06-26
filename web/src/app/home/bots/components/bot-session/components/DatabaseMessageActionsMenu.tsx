import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { cn } from '@/lib/utils';
import {
  CheckCheck,
  MoreHorizontal,
  SkipForward,
  Sparkles,
  Trash2,
} from 'lucide-react';

interface DatabaseMessageActionsMenuProps {
  className?: string;
  disabled?: boolean;
  messageId: number;
  onDelete: () => void;
  onGenerateSmartReply: () => void;
  onMarkProcessed: () => void;
  onSetCurrentMessage: () => void;
  onSkip: () => void;
  setCurrentMessageDisabled?: boolean;
  smartReplyDisabled?: boolean;
  processDisabled?: boolean;
  skipDisabled?: boolean;
}

export function DatabaseMessageActionsMenu({
  className,
  disabled,
  messageId,
  onDelete,
  onGenerateSmartReply,
  onMarkProcessed,
  onSetCurrentMessage,
  onSkip,
  setCurrentMessageDisabled,
  smartReplyDisabled,
  processDisabled,
  skipDisabled,
}: DatabaseMessageActionsMenuProps) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          type="button"
          size="icon"
          variant="ghost"
          disabled={disabled}
          aria-label={`消息 ${messageId} 更多操作`}
          className={cn(
            'size-7 shrink-0 rounded-full text-muted-foreground transition-opacity hover:text-foreground',
            className,
          )}
        >
          <MoreHorizontal className="size-4" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-48">
        <DropdownMenuItem
          disabled={setCurrentMessageDisabled}
          onClick={onSetCurrentMessage}
        >
          设为当前消息
        </DropdownMenuItem>
        <DropdownMenuItem
          disabled={smartReplyDisabled}
          onClick={onGenerateSmartReply}
        >
          <Sparkles className="mr-2 size-4" />
          智能回复
        </DropdownMenuItem>
        <DropdownMenuItem disabled={processDisabled} onClick={onMarkProcessed}>
          <CheckCheck className="mr-2 size-4" />
          标记已处理
        </DropdownMenuItem>
        <DropdownMenuItem disabled={skipDisabled} onClick={onSkip}>
          <SkipForward className="mr-2 size-4" />
          跳过
        </DropdownMenuItem>
        <DropdownMenuItem
          className="text-destructive focus:text-destructive"
          onClick={onDelete}
        >
          <Trash2 className="mr-2 size-4" />
          删除
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
