import { useRef } from 'react';
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
import { Textarea } from '@/components/ui/textarea';

import type { BroadcastDraft } from '../../types';

interface DraftDetailProps {
  draft: BroadcastDraft | null;
  editingDraftId: number | null;
  draftEditorText: string;
  busy?: boolean;
  canPasteDraft?: boolean;
  pasteDisabledReason?: string | null;
  pasteHint?: string | null;
  onStartEdit: (draft: BroadcastDraft) => void;
  onDraftEditorTextChange: (value: string) => void;
  onSaveDraft: () => void;
  onCancelEdit: () => void;
  onMarkSent: () => void;
  onRestorePending: () => void;
  onPasteDraft: () => void;
  onUploadAttachments: (files: File[]) => void;
  onDeleteAttachment: (attachmentId: number) => void;
}

export default function DraftDetail({
  draft,
  editingDraftId,
  draftEditorText,
  busy = false,
  canPasteDraft = true,
  pasteDisabledReason = null,
  pasteHint = null,
  onStartEdit,
  onDraftEditorTextChange,
  onSaveDraft,
  onCancelEdit,
  onMarkSent,
  onRestorePending,
  onPasteDraft,
  onUploadAttachments,
  onDeleteAttachment,
}: DraftDetailProps) {
  const { t } = useTranslation();
  const attachmentUploadRef = useRef<HTMLInputElement | null>(null);

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

  const isSent = draft.status === 'sent';
  const pasteDisabled =
    !canPasteDraft ||
    !draft.conversationName.trim() ||
    !draft.draftText.trim() ||
    busy;

  return (
    <Card className="gap-4" data-testid="broadcast-draft-detail">
      <CardHeader>
        <div className="flex items-start justify-between gap-3">
          <div>
            <CardTitle>{draft.customerName}</CardTitle>
            <CardDescription>{draft.conversationName}</CardDescription>
          </div>
          <Badge variant="outline">
            {isSent
              ? t('broadcast.drafts.statusSent')
              : t('broadcast.drafts.statusPending')}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-3 md:grid-cols-2">
          <div className="rounded-xl border bg-muted/20 p-4">
            <div className="text-xs text-muted-foreground">
              {t('broadcast.drafts.templateLabel')}
            </div>
            <div className="mt-2 font-medium">{draft.templateName}</div>
          </div>
          <div className="rounded-xl border bg-muted/20 p-4">
            <div className="text-xs text-muted-foreground">
              {t('broadcast.drafts.conversationLabel')}
            </div>
            <div className="mt-2 font-medium">
              {draft.conversationName || '-'}
            </div>
          </div>
        </div>

        {draft.draftsStale || draft.attachmentsStale ? (
          <div className="rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-800">
            {draft.attachmentsStale
              ? t('broadcast.drafts.attachmentsStaleWarning')
              : t('broadcast.drafts.staleWarning')}
          </div>
        ) : null}

        {draft.errorMessage ? (
          <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">
            {draft.errorMessage}
          </div>
        ) : null}

        <div
          className="sticky top-0 z-10 flex flex-wrap items-center gap-2 rounded-xl border bg-background/95 p-3 backdrop-blur supports-[backdrop-filter]:bg-background/80"
          data-testid="broadcast-draft-detail-sticky-actions"
        >
          {!isEditing ? (
            <Button
              data-testid="broadcast-draft-edit-button"
              onClick={() => onStartEdit(draft)}
              disabled={busy}
            >
              {t('broadcast.drafts.editDraft')}
            </Button>
          ) : (
            <>
              <Button
                data-testid="broadcast-draft-save-button"
                onClick={onSaveDraft}
                disabled={busy}
              >
                {t('broadcast.drafts.saveDraft')}
              </Button>
              <Button variant="outline" onClick={onCancelEdit} disabled={busy}>
                {t('broadcast.drafts.cancelAction')}
              </Button>
            </>
          )}

          <Button
            data-testid="broadcast-draft-paste-button"
            variant="outline"
            onClick={onPasteDraft}
            disabled={pasteDisabled}
            title={
              pasteDisabled ? (pasteDisabledReason ?? undefined) : undefined
            }
          >
            {isSent
              ? t('broadcast.drafts.rewriteToInput')
              : t('broadcast.drafts.pasteToInput')}
          </Button>

          {isSent ? (
            <Button
              data-testid="broadcast-draft-restore-pending-button"
              variant="outline"
              onClick={onRestorePending}
              disabled={busy}
            >
              {t('broadcast.drafts.restorePending')}
            </Button>
          ) : (
            <Button
              data-testid="broadcast-draft-mark-sent-button"
              variant="outline"
              onClick={onMarkSent}
              disabled={busy}
            >
              {t('broadcast.drafts.markSent')}
            </Button>
          )}
        </div>

        {pasteDisabled && pasteDisabledReason ? (
          <div className="text-sm text-muted-foreground">
            {pasteDisabledReason}
          </div>
        ) : null}

        {pasteHint ? (
          <div className="text-sm text-muted-foreground">{pasteHint}</div>
        ) : null}

        <div className="space-y-2">
          <div className="text-sm font-medium">
            {t('broadcast.drafts.messageBody')}
          </div>
          {isEditing ? (
            <Textarea
              aria-label={t('broadcast.drafts.editor')}
              value={draftEditorText}
              onChange={(event) => onDraftEditorTextChange(event.target.value)}
              rows={10}
            />
          ) : (
            <pre className="whitespace-pre-wrap rounded-xl border bg-muted/20 p-4 text-sm">
              {draft.draftText}
            </pre>
          )}
        </div>

        <div className="space-y-3">
          <div className="flex items-center justify-between gap-3">
            <div className="text-sm font-medium">
              {t('broadcast.drafts.attachmentsTitle')}
            </div>
            <input
              ref={attachmentUploadRef}
              type="file"
              multiple
              className="hidden"
              onChange={(event) => {
                const files = Array.from(event.target.files ?? []);
                if (files.length > 0) {
                  onUploadAttachments(files);
                }
                event.currentTarget.value = '';
              }}
            />
            <Button
              variant="outline"
              onClick={() => attachmentUploadRef.current?.click()}
              disabled={busy}
            >
              {t('broadcast.drafts.uploadAttachment')}
            </Button>
          </div>
          <div className="space-y-2">
            {(draft.attachments ?? []).length === 0 ? (
              <div className="rounded-xl border border-dashed p-4 text-sm text-muted-foreground">
                {t('broadcast.drafts.emptyAttachments')}
              </div>
            ) : (
              draft.attachments?.map((attachment) => (
                <div
                  key={attachment.id}
                  className="flex items-center justify-between gap-3 rounded-xl border p-3"
                >
                  <div className="min-w-0">
                    <div className="truncate text-sm font-medium">
                      {attachment.originalName}
                    </div>
                    <div className="text-xs text-muted-foreground">
                      {attachment.extension.toUpperCase()} ·{' '}
                      {Math.max(1, Math.round(attachment.sizeBytes / 1024))} KB
                    </div>
                  </div>
                  <Button
                    variant="ghost"
                    onClick={() => onDeleteAttachment(attachment.id)}
                    disabled={busy}
                  >
                    {t('broadcast.drafts.deleteAttachment')}
                  </Button>
                </div>
              ))
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
