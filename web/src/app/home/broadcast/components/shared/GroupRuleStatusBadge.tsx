import { useTranslation } from 'react-i18next';

import { Badge } from '@/components/ui/badge';

type GroupRuleStatus = 'matched' | 'conflict' | 'no_match';

interface GroupRuleStatusBadgeProps {
  status: GroupRuleStatus;
}

export default function GroupRuleStatusBadge({
  status,
}: GroupRuleStatusBadgeProps) {
  const { t } = useTranslation();

  if (status === 'conflict') {
    return (
      <Badge variant="destructive">
        {t('broadcast.groupRule.preview.conflictBadge')}
      </Badge>
    );
  }
  if (status === 'matched') {
    return (
      <Badge variant="secondary">
        {t('broadcast.groupRule.preview.matchedBadge')}
      </Badge>
    );
  }
  return (
    <Badge variant="outline">
      {t('broadcast.groupRule.preview.noMatchBadge')}
    </Badge>
  );
}
