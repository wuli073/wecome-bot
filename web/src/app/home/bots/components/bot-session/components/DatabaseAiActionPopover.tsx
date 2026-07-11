import { Button } from '@/components/ui/button';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover';
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { Sparkles, WandSparkles } from 'lucide-react';

interface DatabaseAiActionPopoverProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  disabledReason?: string;
  generatingDraft: boolean;
  onGenerateSmartReply: () => void;
}

const COMING_SOON_ACTIONS = [
  '语气调整',
  '跟进建议',
  '消息总结',
  '推荐附件',
  '状态更新',
] as const;

export function DatabaseAiActionPopover({
  open,
  onOpenChange,
  disabledReason,
  generatingDraft,
  onGenerateSmartReply,
}: DatabaseAiActionPopoverProps) {
  const smartReplyDisabled = Boolean(disabledReason) || generatingDraft;
  const smartReplyTooltip = generatingDraft
    ? '草稿生成中'
    : (disabledReason ?? '智能回复');

  return (
    <Popover open={open} onOpenChange={onOpenChange}>
      <PopoverTrigger asChild>
        <Button
          type="button"
          size="icon"
          variant="outline"
          aria-label="AI actions"
          className="shrink-0"
        >
          <WandSparkles className="size-4" />
        </Button>
      </PopoverTrigger>
      <PopoverContent
        side="top"
        align="end"
        sideOffset={8}
        className="w-72 p-3"
      >
        <div className="grid grid-cols-2 gap-2">
          <Tooltip>
            <TooltipTrigger asChild>
              <span className="block">
                <Button
                  type="button"
                  variant="default"
                  className="w-full justify-start"
                  disabled={smartReplyDisabled}
                  onClick={onGenerateSmartReply}
                >
                  <Sparkles className="mr-2 size-4" />
                  智能回复
                </Button>
              </span>
            </TooltipTrigger>
            <TooltipContent>{smartReplyTooltip}</TooltipContent>
          </Tooltip>

          {COMING_SOON_ACTIONS.map((label) => (
            <Tooltip key={label}>
              <TooltipTrigger asChild>
                <span className="block">
                  <Button
                    type="button"
                    variant="outline"
                    className="w-full justify-start"
                    disabled
                  >
                    {label}
                  </Button>
                </span>
              </TooltipTrigger>
              <TooltipContent>暂未开放</TooltipContent>
            </Tooltip>
          ))}
        </div>
      </PopoverContent>
    </Popover>
  );
}
