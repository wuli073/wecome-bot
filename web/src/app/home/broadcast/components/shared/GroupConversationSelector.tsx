import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';

import { Input } from '@/components/ui/input';

import { getGroupTargetState } from '../../groupTargetState';
import type { BroadcastGroupName } from '../../types';

interface GroupConversationSelectorProps {
  groupNames: BroadcastGroupName[];
  value: string;
  keyword: string;
  onKeywordChange: (value: string) => void;
  onChange: (conversation: BroadcastGroupName | null) => void;
  onManualConfirm?: (value: string) => void;
  disabled?: boolean;
  searchLabel: string;
  searchPlaceholder: string;
  emptyLabel: string;
  missingStableIdLabel?: string;
  searchInputTestId?: string;
  listTestId?: string;
}

export default function GroupConversationSelector({
  groupNames,
  value,
  keyword,
  onKeywordChange,
  onChange,
  onManualConfirm,
  disabled = false,
  searchLabel,
  searchPlaceholder,
  emptyLabel,
  missingStableIdLabel,
  searchInputTestId,
  listTestId,
}: GroupConversationSelectorProps) {
  const { t } = useTranslation();

  const filteredGroupNames = useMemo(() => {
    const normalizedKeyword = keyword.trim().toLowerCase();
    return groupNames.filter((groupName) => {
      if (!normalizedKeyword) {
        return true;
      }
      return (
        groupName.name.toLowerCase().includes(normalizedKeyword) ||
        (groupName.externalConversationId ?? '')
          .toLowerCase()
          .includes(normalizedKeyword)
      );
    });
  }, [groupNames, keyword]);

  const normalizedSelectionName = keyword.trim();

  return (
    <div className="space-y-2">
      <div className="text-sm font-medium">{searchLabel}</div>
      <Input
        value={keyword}
        onChange={(event) => onKeywordChange(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === 'Enter') {
            event.preventDefault();
            onManualConfirm?.(keyword);
          }
        }}
        placeholder={searchPlaceholder}
        disabled={disabled}
        data-testid={searchInputTestId}
      />
      <div
        className="max-h-72 space-y-2 overflow-y-auto pr-1"
        data-testid={listTestId}
      >
        {filteredGroupNames.map((groupName) => {
          const targetState = getGroupTargetState(groupName);
          const hasStableExternalId =
            targetState.resolutionMode === 'stable_id';
          const selected =
            String(groupName.id) === value ||
            (hasStableExternalId
              ? groupName.externalConversationId === value
              : !value.trim() && groupName.name === normalizedSelectionName);
          return (
            <button
              key={groupName.id}
              type="button"
              className={`w-full rounded-lg border px-3 py-2 text-left text-sm ${
                selected ? 'border-blue-500 bg-blue-50' : 'bg-background'
              }`}
              disabled={disabled || !targetState.selectable}
              onClick={() => onChange(groupName)}
            >
              <div className="font-medium">{groupName.name}</div>
              <div className="mt-1 text-xs text-muted-foreground">
                {hasStableExternalId
                  ? t('broadcast.rules.groupTargetStates.stableIdReady')
                  : targetState.resolutionMode === 'name'
                    ? t('broadcast.rules.groupTargetStates.nameMatch')
                    : (missingStableIdLabel ??
                      t('broadcast.rules.groupTargetStates.invalid'))}
              </div>
            </button>
          );
        })}
        {filteredGroupNames.length === 0 ? (
          <div className="rounded-lg border border-dashed p-3 text-sm text-muted-foreground">
            {emptyLabel}
          </div>
        ) : null}
      </div>
    </div>
  );
}
