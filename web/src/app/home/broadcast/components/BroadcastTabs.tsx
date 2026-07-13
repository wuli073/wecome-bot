import { TabsList, TabsTrigger } from '@/components/ui/tabs';

interface BroadcastTabsProps<T extends string> {
  options: Array<{ value: T; label: string }>;
  size?: 'default' | 'compact';
  testId?: string;
}

export default function BroadcastTabs<T extends string>({
  options,
  size = 'default',
  testId,
}: BroadcastTabsProps<T>) {
  return (
    <TabsList
      data-testid={testId}
      className={`relative w-full justify-start overflow-x-auto border ${
        size === 'compact'
          ? 'h-9 rounded-lg bg-muted/30 p-1 shadow-none'
          : 'h-11 rounded-xl bg-muted/60 p-1.5 shadow-sm'
      }`}
    >
      {options.map((option) => (
        <TabsTrigger
          key={option.value}
          value={option.value}
          className={`rounded-md ${
            size === 'compact'
              ? 'h-7 px-3 text-xs font-medium text-muted-foreground data-[state=active]:bg-background data-[state=active]:text-foreground data-[state=active]:shadow-sm'
              : 'h-8 px-4 text-sm font-semibold text-muted-foreground data-[state=active]:bg-background data-[state=active]:text-foreground data-[state=active]:shadow-md'
          }`}
        >
          {option.label}
        </TabsTrigger>
      ))}
    </TabsList>
  );
}
