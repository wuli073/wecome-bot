import { TabsList, TabsTrigger } from '@/components/ui/tabs';

interface BroadcastTabsProps<T extends string> {
  options: Array<{ value: T; label: string }>;
  size?: 'default' | 'compact';
}

export default function BroadcastTabs<T extends string>({
  options,
  size = 'default',
}: BroadcastTabsProps<T>) {
  return (
    <TabsList
      className={`w-full justify-start overflow-x-auto ${size === 'compact' ? 'h-8 rounded-md' : 'h-10 rounded-lg'}`}
    >
      {options.map((option) => (
        <TabsTrigger
          key={option.value}
          value={option.value}
          className={size === 'compact' ? 'text-xs' : 'text-sm'}
        >
          {option.label}
        </TabsTrigger>
      ))}
    </TabsList>
  );
}
