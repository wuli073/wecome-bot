import { useTranslation } from 'react-i18next';

import type { BroadcastGroupMatchResult } from '../../types';
import GroupRuleStatusBadge from './GroupRuleStatusBadge';

interface GroupMatchPreviewProps {
  result: BroadcastGroupMatchResult | null;
  emptyLabel: string;
}

function getPreviewReasonLabel(
  reason: string | null,
  t: ReturnType<typeof useTranslation>['t'],
): string | null {
  if (reason === 'multiple_matching_rules') {
    return t('broadcast.groupRule.preview.conflict');
  }
  if (reason === 'no_matching_rule') {
    return t('broadcast.groupRule.preview.noMatch');
  }
  return null;
}

export default function GroupMatchPreview({
  result,
  emptyLabel,
}: GroupMatchPreviewProps) {
  const { t } = useTranslation();

  if (!result) {
    return <div className="text-sm text-muted-foreground">{emptyLabel}</div>;
  }

  const status = result.conflict
    ? 'conflict'
    : result.matched
      ? 'matched'
      : 'no_match';
  const reasonLabel = getPreviewReasonLabel(result.reason, t);

  return (
    <div className="space-y-3 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        <GroupRuleStatusBadge status={status} />
        {reasonLabel ? (
          <span className="text-muted-foreground">{reasonLabel}</span>
        ) : null}
      </div>

      {result.matched ? (
        <div className="space-y-1">
          <div>
            <span className="font-medium">
              {t('broadcast.groupRule.preview.currentRule')}
            </span>
            {': '}
            {result.matchType}
            {' → '}
            {result.targetConversationName}
          </div>
          {result.targetConversationId ? (
            <div className="text-muted-foreground">
              ID: {result.targetConversationId}
            </div>
          ) : null}
        </div>
      ) : (
        <div className="text-muted-foreground">
          {t('broadcast.groupRule.preview.noMatch')}
        </div>
      )}

      {result.candidateRules.length > 0 ? (
        <div className="space-y-2">
          <div className="font-medium">
            {t('broadcast.groupRule.preview.candidateRules')}
          </div>
          <div className="space-y-2">
            {result.candidateRules.map((rule) => (
              <div
                key={rule.id}
                className="rounded-lg border bg-muted/20 px-3 py-2"
              >
                <div className="font-medium">
                  {rule.matchType}
                  {' · '}
                  {rule.sourceValue}
                </div>
                <div className="text-muted-foreground">
                  {rule.targetConversationName}
                </div>
                {rule.targetConversationId ? (
                  <div className="text-xs text-muted-foreground">
                    ID: {rule.targetConversationId}
                  </div>
                ) : null}
              </div>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}
