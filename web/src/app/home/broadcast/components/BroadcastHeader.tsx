import { Megaphone, ClipboardPaste, Files, FileText } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';

import type { BroadcastWorkspaceSnapshot } from '../types';

interface BroadcastHeaderProps {
  snapshot: BroadcastWorkspaceSnapshot;
}

export default function BroadcastHeader({
  snapshot,
}: BroadcastHeaderProps) {
  const { t } = useTranslation();

  const stats = [
    {
      key: 'templates',
      label: t('broadcast.summary.templates'),
      value: snapshot.templates.length,
      icon: Files,
    },
    {
      key: 'mappings',
      label: t('broadcast.summary.variableMappings'),
      value: snapshot.variableMappings.length,
      icon: FileText,
    },
    {
      key: 'drafts',
      label: t('broadcast.summary.reviewQueue'),
      value: snapshot.drafts.length,
      icon: Megaphone,
    },
    {
      key: 'logs',
      label: t('broadcast.summary.logs'),
      value: snapshot.executionLogs.length,
      icon: ClipboardPaste,
    },
  ];

  return (
    <Card className="gap-4 py-5">
      <CardHeader className="gap-3">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="space-y-2">
            <div className="flex items-center gap-2">
              <h1 className="text-2xl font-semibold">
                {t('broadcast.workspaceTitle')}
              </h1>
              <Badge variant="secondary">
                {t('broadcast.phaseBadge')}
              </Badge>
            </div>
            <CardDescription className="max-w-3xl">
              {t('broadcast.workspaceDescription')}
            </CardDescription>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          {stats.map((item) => {
            const Icon = item.icon;
            return (
              <div
                key={item.key}
                className="rounded-xl border bg-muted/30 p-4 shadow-sm"
              >
                <div className="flex items-center justify-between">
                  <span className="text-sm text-muted-foreground">
                    {item.label}
                  </span>
                  <Icon className="size-4 text-blue-500" />
                </div>
                <div className="mt-3 text-2xl font-semibold">{item.value}</div>
              </div>
            );
          })}
        </div>
      </CardContent>
    </Card>
  );
}
