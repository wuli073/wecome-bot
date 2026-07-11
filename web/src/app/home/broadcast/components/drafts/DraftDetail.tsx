import { useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
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
  canSendDraft?: boolean;
  sendDisabledReason?: string | null;
  onStartEdit: (draft: BroadcastDraft) => void;
  onDraftEditorTextChange: (value: string) => void;
  onSaveDraft: () => void;
  onCancelEdit: () => void;
  onMarkSent: () => void;
  onRestorePending: () => void;
  onPasteDraft: () => void;
  onSendDraft: () => void;
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
  canSendDraft = false,
  sendDisabledReason = null,
  onStartEdit,
  onDraftEditorTextChange,
  onSaveDraft,
  onCancelEdit,
  onMarkSent,
  onRestorePending,
  onPasteDraft,
  onSendDraft,
  onUploadAttachments,
  onDeleteAttachment,
}: DraftDetailProps) {
  const { t } = useTranslation();
  const attachmentUploadRef = useRef<HTMLInputElement | null>(null);
  const [sendDialogOpen, setSendDialogOpen] = useState(false);
  const [restorePendingRiskDialogOpen, setRestorePendingRiskDialogOpen] =
    useState(false);

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
  const isUnknown = draft.status === 'unknown';
  const pasteDisabled =
    !canPasteDraft ||
    !draft.conversationName.trim() ||
    !draft.draftText.trim() ||
    busy;
  const sendDisabled =
    !canSendDraft ||
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
              : isUnknown
                ? t('broadcast.drafts.statusUnknown')
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

          <Button
            data-testid="broadcast-draft-send-button"
            variant="destructive"
            onClick={() => setSendDialogOpen(true)}
            disabled={sendDisabled}
            title={sendDisabled ? (sendDisabledReason ?? undefined) : undefined}
          >
            {t('broadcast.drafts.realSend')}
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
          ) : isUnknown ? (
            <>
              <Button
                data-testid="broadcast-draft-mark-sent-button"
                variant="outline"
                onClick={onMarkSent}
                disabled={busy}
              >
                {t('broadcast.drafts.markSent')}
              </Button>
              <Button
                data-testid="broadcast-draft-restore-pending-button"
                variant="outline"
                onClick={() => setRestorePendingRiskDialogOpen(true)}
                disabled={busy}
              >
                {t('broadcast.drafts.restorePending')}
              </Button>
            </>
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
        {sendDisabled && sendDisabledReason ? (
          <div className="text-sm text-muted-foreground">
            {sendDisabledReason}
          </div>
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
      <AlertDialog open={sendDialogOpen} onOpenChange={setSendDialogOpen}>
        <AlertDialogContent data-testid="broadcast-draft-send-confirm-dialog">
          <AlertDialogHeader>
            <AlertDialogTitle>
              {t('broadcast.drafts.sendDialogTitle')}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {t('broadcast.drafts.sendDialogDescription')}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <div className="grid gap-2 rounded-lg border bg-muted/20 p-3 text-sm">
            <div>
              {t('broadcast.drafts.sendDialogCustomer', {
                customer: draft.customerName,
              })}
            </div>
            <div>
              {t('broadcast.drafts.sendDialogConversation', {
                conversation: draft.conversationName,
              })}
            </div>
            <div>
              {t('broadcast.drafts.sendDialogAttachmentCount', {
                count: draft.attachments?.length ?? 0,
              })}
            </div>
          </div>
          <div className="rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-800">
            {t('broadcast.drafts.sendWarning')}
          </div>
          <AlertDialogFooter>
            <AlertDialogCancel data-testid="broadcast-draft-send-cancel-button">
              {t('common.cancel')}
            </AlertDialogCancel>
            <AlertDialogAction
              data-testid="broadcast-draft-send-confirm-button"
              onClick={(event) => {
                event.preventDefault();
                onSendDraft();
                setSendDialogOpen(false);
              }}
            >
              {t('broadcast.drafts.confirmSendAction')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
      <AlertDialog
        open={restorePendingRiskDialogOpen}
        onOpenChange={setRestorePendingRiskDialogOpen}
      >
        <AlertDialogContent data-testid="broadcast-draft-restore-pending-risk-dialog">
          <AlertDialogHeader>
            <AlertDialogTitle>
              {t('broadcast.drafts.restorePendingRiskTitle')}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {t('broadcast.drafts.restorePendingRiskDescription')}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel data-testid="broadcast-draft-restore-pending-risk-cancel-button">
              {t('common.cancel')}
            </AlertDialogCancel>
            <AlertDialogAction
              data-testid="broadcast-draft-restore-pending-risk-confirm-button"
              onClick={(event) => {
                event.preventDefault();
                onRestorePending();
                setRestorePendingRiskDialogOpen(false);
              }}
            >
              {t('broadcast.drafts.restorePending')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Card>
  );
}
