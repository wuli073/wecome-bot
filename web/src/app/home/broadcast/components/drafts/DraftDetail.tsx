import { useTranslation } from 'react-i18next';

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible';
import { Textarea } from '@/components/ui/textarea';
import { Separator } from '@/components/ui/separator';

import type {
  BroadcastBatchState,
  BroadcastDraft,
  BroadcastPasteDraftRequest,
  BroadcastRuntimePasteDraftPayload,
} from '../../types';

interface DraftDetailProps {
  draft: BroadcastDraft | null;
  editingDraftId: number | null;
  draftEditorText: string;
  batchState: BroadcastBatchState;
  requestPreview: BroadcastPasteDraftRequest | null;
  runtimePreview: BroadcastRuntimePasteDraftPayload | null;
  onStartEdit: (draft: BroadcastDraft) => void;
  onDraftEditorTextChange: (value: string) => void;
  onSaveDraft: () => void;
  onCancelEdit: () => void;
}

export default function DraftDetail({
  draft,
  editingDraftId,
  draftEditorText,
  batchState,
  requestPreview,
  runtimePreview,
  onStartEdit,
  onDraftEditorTextChange,
  onSaveDraft,
  onCancelEdit,
}: DraftDetailProps) {
  const { t } = useTranslation();

  const isEditing = draft != null && editingDraftId === draft.id;

  if (!draft) {
    return (
      <Card className="justify-center" data-testid="broadcast-draft-detail">
        <CardContent className="py-12 text-center text-muted-foreground">
          {t('broadcast.drafts.emptyDetail')}
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="gap-4" data-testid="broadcast-draft-detail">
      <CardHeader>
        <div className="flex items-start justify-between gap-3">
          <div>
            <CardTitle>{draft.customerName}</CardTitle>
            <CardDescription>{draft.conversationName}</CardDescription>
          </div>
          <Badge variant="outline">{t(`broadcast.status.${draft.status}`)}</Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-3 md:grid-cols-2">
          <div className="rounded-xl border bg-muted/20 p-4">
            <div className="text-xs text-muted-foreground">
              {t('broadcast.fields.template')}
            </div>
            <div className="mt-2 font-medium">{draft.templateName}</div>
          </div>
          <div className="rounded-xl border bg-muted/20 p-4">
            <div className="text-xs text-muted-foreground">
              {t('broadcast.fields.operator')}
            </div>
            <div className="mt-2 font-medium">{draft.operator}</div>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {!isEditing ? (
            <Button onClick={() => onStartEdit(draft)}>
              {t('broadcast.drafts.editDraft')}
            </Button>
          ) : (
            <>
              <Button onClick={onSaveDraft}>
                {t('broadcast.drafts.saveDraft')}
              </Button>
              <Button variant="outline" onClick={onCancelEdit}>
                {t('broadcast.drafts.cancelEdit')}
              </Button>
            </>
          )}
          {batchState.phase === 'running' ? (
            <Badge variant="outline">{t('broadcast.drafts.batchRunning')}</Badge>
          ) : null}
        </div>

        <div className="space-y-2">
          <div className="text-sm font-medium">
            {t('broadcast.drafts.messageBody')}
          </div>
          {isEditing ? (
            <Textarea
              aria-label={t('broadcast.drafts.editor')}
              className="min-h-[220px]"
              value={draftEditorText}
              onChange={(event) =>
                onDraftEditorTextChange(event.target.value)
              }
            />
          ) : (
            <pre className="whitespace-pre-wrap rounded-xl border bg-muted/10 p-4 text-sm leading-6">
              {draft.draftText}
            </pre>
          )}
        </div>

        <Separator />

        <Collapsible className="space-y-3">
          <CollapsibleTrigger asChild>
            <Button type="button" variant="outline">
              {t('broadcast.contract.toggle')}
            </Button>
          </CollapsibleTrigger>
          <CollapsibleContent className="space-y-3">
            <div className="text-sm font-medium">
              {t('broadcast.contract.title')}
            </div>
            <div className="rounded-xl border bg-muted/10 p-4">
              <div className="text-xs text-muted-foreground">
                {t('broadcast.contract.request')}
              </div>
              <pre className="mt-3 overflow-x-auto text-xs leading-5">
                {JSON.stringify(requestPreview, null, 2)}
              </pre>
            </div>
            <div className="rounded-xl border bg-muted/10 p-4">
              <div className="text-xs text-muted-foreground">
                {t('broadcast.contract.runtimePayload')}
              </div>
              <pre className="mt-3 overflow-x-auto text-xs leading-5">
                {JSON.stringify(runtimePreview, null, 2)}
              </pre>
            </div>
          </CollapsibleContent>
        </Collapsible>
      </CardContent>
    </Card>
  );
}
