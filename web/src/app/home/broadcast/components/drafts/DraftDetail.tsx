import { useEffect, useMemo, useRef, useState } from 'react';
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
import { Checkbox } from '@/components/ui/checkbox';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Separator } from '@/components/ui/separator';

import type { BroadcastDraft } from '../../types';

interface DraftDetailProps {
  draft: BroadcastDraft | null;
  editingDraftId: number | null;
  draftEditorText: string;
  busy?: boolean;
  canPasteDraft?: boolean;
  pasteDisabledReason?: string | null;
  canRealSend?: boolean;
  sendBusy?: boolean;
  onStartEdit: (draft: BroadcastDraft) => void;
  onDraftEditorTextChange: (value: string) => void;
  onSaveDraft: () => void;
  onCancelEdit: () => void;
  onConfirmDraft: () => void;
  onRevokeDraft: () => void;
  onPasteDraft: () => void;
  onSendDraft: () => void;
  onUploadAttachments: (files: File[]) => void;
  onDeleteAttachment: (attachmentId: number) => void;
}

const SEND_CONFIRM_SECONDS = 3;

export default function DraftDetail({
  draft,
  editingDraftId,
  draftEditorText,
  busy = false,
  canPasteDraft = true,
  pasteDisabledReason = null,
  canRealSend = false,
  sendBusy = false,
  onStartEdit,
  onDraftEditorTextChange,
  onSaveDraft,
  onCancelEdit,
  onConfirmDraft,
  onRevokeDraft,
  onPasteDraft,
  onSendDraft,
  onUploadAttachments,
  onDeleteAttachment,
}: DraftDetailProps) {
  const { t } = useTranslation();
  const attachmentUploadRef = useRef<HTMLInputElement | null>(null);
  const [pasteConfirmOpen, setPasteConfirmOpen] = useState(false);
  const [sendConfirmOpen, setSendConfirmOpen] = useState(false);
  const [sendAcknowledged, setSendAcknowledged] = useState(false);
  const [sendCountdown, setSendCountdown] = useState(SEND_CONFIRM_SECONDS);

  const isEditing = draft != null && editingDraftId === draft.id;

  useEffect(() => {
    if (!sendConfirmOpen) {
      setSendAcknowledged(false);
      setSendCountdown(SEND_CONFIRM_SECONDS);
      return;
    }

    if (sendCountdown <= 0) {
      return;
    }

    const timer = window.setTimeout(() => {
      setSendCountdown((current) => Math.max(current - 1, 0));
    }, 1000);

    return () => {
      window.clearTimeout(timer);
    };
  }, [sendConfirmOpen, sendCountdown]);

  const confirmDisabled =
    draft?.status !== 'pending_review' ||
    Boolean(draft?.draftsStale) ||
    Boolean(draft?.attachmentsStale);
  const revokeDisabled = draft?.status !== 'ready';
  const pasteDisabled =
    !draft ||
    draft.status !== 'ready' ||
    Boolean(draft.draftsStale) ||
    Boolean(draft.attachmentsStale) ||
    !draft.conversationName.trim() ||
    !draft.draftText.trim() ||
    !canPasteDraft ||
    busy;
  const sendDisabled =
    !draft ||
    draft.status !== 'ready' ||
    Boolean(draft.draftsStale) ||
    Boolean(draft.attachmentsStale) ||
    !draft.conversationName.trim() ||
    !draft.draftText.trim() ||
    busy ||
    sendBusy ||
    !canRealSend;

  const sendConfirmActionDisabled = useMemo(
    () => sendBusy || !sendAcknowledged || sendCountdown > 0,
    [sendAcknowledged, sendBusy, sendCountdown],
  );

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
    <>
      <Card className="gap-4" data-testid="broadcast-draft-detail">
        <CardHeader>
          <div className="flex items-start justify-between gap-3">
            <div>
              <CardTitle>{draft.customerName}</CardTitle>
              <CardDescription>{draft.conversationName}</CardDescription>
            </div>
            <Badge variant="outline">
              {draft.status === 'pending_review'
                ? t('broadcast.drafts.statusPendingReview')
                : draft.status === 'ready'
                  ? t('broadcast.drafts.statusReady')
                  : t('broadcast.drafts.statusInvalid')}
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

          <div className="flex flex-wrap items-center gap-2">
            {!isEditing ? (
              <Button
                data-testid="broadcast-draft-edit-button"
                onClick={() => onStartEdit(draft)}
                disabled={busy || sendBusy}
              >
                {t('broadcast.drafts.editDraft')}
              </Button>
            ) : (
              <>
                <Button
                  data-testid="broadcast-draft-save-button"
                  onClick={onSaveDraft}
                  disabled={busy || sendBusy}
                >
                  {t('broadcast.drafts.saveDraft')}
                </Button>
                <Button
                  variant="outline"
                  onClick={onCancelEdit}
                  disabled={busy || sendBusy}
                >
                  {t('broadcast.drafts.cancelEdit')}
                </Button>
              </>
            )}
            <Button
              data-testid="broadcast-draft-confirm-button"
              onClick={onConfirmDraft}
              disabled={confirmDisabled || busy || sendBusy}
            >
              {t('broadcast.drafts.confirmDraft')}
            </Button>
            <Button
              data-testid="broadcast-draft-revoke-button"
              variant="outline"
              onClick={onRevokeDraft}
              disabled={revokeDisabled || busy || sendBusy}
            >
              {t('broadcast.drafts.revokeConfirm')}
            </Button>
            <Button
              data-testid="broadcast-draft-paste-button"
              onClick={() => setPasteConfirmOpen(true)}
              disabled={pasteDisabled}
            >
              {busy
                ? t('broadcast.drafts.pasteLoading')
                : t('broadcast.drafts.pasteToInput')}
            </Button>
            {canRealSend ? (
              <Button
                data-testid="broadcast-draft-send-button"
                variant="destructive"
                onClick={() => setSendConfirmOpen(true)}
                disabled={sendDisabled}
              >
                {sendBusy
                  ? t('broadcast.drafts.sendLoading')
                  : t('broadcast.drafts.realSend')}
              </Button>
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

          <div className="space-y-3">
            <div className="flex items-center justify-between gap-2">
              <div className="text-sm font-medium">
                {t('broadcast.drafts.attachmentsTitle')}
              </div>
              <input
                ref={(node) => {
                  attachmentUploadRef.current = node;
                }}
                type="file"
                multiple
                className="hidden"
                onChange={(event) => {
                  const files = Array.from(event.target.files ?? []);
                  if (files.length > 0) {
                    onUploadAttachments(files);
                  }
                  event.target.value = '';
                }}
              />
              <Button
                variant="outline"
                size="sm"
                disabled={busy || sendBusy}
                onClick={() => attachmentUploadRef.current?.click()}
              >
                {t('broadcast.drafts.uploadAttachment')}
              </Button>
            </div>
            {draft.attachments && draft.attachments.length > 0 ? (
              <div className="flex flex-wrap gap-2">
                {draft.attachments.map((attachment) => (
                  <div
                    key={attachment.id}
                    className="flex items-center gap-2 rounded-lg border bg-muted/10 px-3 py-2 text-sm"
                  >
                    <span>{attachment.originalName}</span>
                    <Button
                      size="sm"
                      variant="ghost"
                      disabled={busy || sendBusy}
                      onClick={() => onDeleteAttachment(attachment.id)}
                    >
                      {t('broadcast.drafts.deleteAttachment')}
                    </Button>
                  </div>
                ))}
              </div>
            ) : (
              <div className="rounded-lg border border-dashed p-3 text-sm text-muted-foreground">
                {t('broadcast.drafts.emptyAttachments')}
              </div>
            )}
          </div>

          <Separator />

          <div className="rounded-xl border bg-muted/10 p-4 text-sm text-muted-foreground">
            {t('broadcast.drafts.pasteHint')}
          </div>
          {!canPasteDraft && pasteDisabledReason ? (
            <div className="rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-800">
              {pasteDisabledReason}
            </div>
          ) : null}
        </CardContent>
      </Card>

      <AlertDialog open={pasteConfirmOpen} onOpenChange={setPasteConfirmOpen}>
        <AlertDialogContent data-testid="broadcast-draft-paste-confirm-dialog">
          <AlertDialogHeader>
            <AlertDialogTitle>
              {t('broadcast.drafts.pasteDialogTitle')}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {t('broadcast.drafts.pasteDialogDescription')}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <div className="space-y-3 text-sm">
            <div>
              <div className="font-medium">
                {t('broadcast.drafts.conversationLabel')}
              </div>
              <div className="text-muted-foreground">
                {draft.conversationName}
              </div>
            </div>
            <div>
              <div className="font-medium">
                {t('broadcast.drafts.messagePreviewLabel')}
              </div>
              <pre className="max-h-52 overflow-auto whitespace-pre-wrap rounded-lg border bg-muted/10 p-3 text-xs">
                {draft.draftText}
              </pre>
            </div>
          </div>
          <AlertDialogFooter>
            <AlertDialogCancel>
              {t('broadcast.drafts.cancelAction')}
            </AlertDialogCancel>
            <AlertDialogAction
              data-testid="broadcast-draft-paste-confirm-action"
              disabled={busy}
              onClick={() => {
                setPasteConfirmOpen(false);
                onPasteDraft();
              }}
            >
              {busy
                ? t('common.loading')
                : t('broadcast.drafts.confirmPasteAction')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog open={sendConfirmOpen} onOpenChange={setSendConfirmOpen}>
        <AlertDialogContent data-testid="broadcast-draft-send-confirm-dialog">
          <AlertDialogHeader>
            <AlertDialogTitle>
              {t('broadcast.drafts.sendDialogTitle')}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {t('broadcast.drafts.sendDialogDescription')}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <div className="space-y-4 text-sm">
            <div>
              <div className="font-medium">
                {t('broadcast.drafts.conversationLabel')}
              </div>
              <div className="text-muted-foreground">
                {draft.conversationName}
              </div>
            </div>
            <div>
              <div className="font-medium">
                {t('broadcast.drafts.messagePreviewLabel')}
              </div>
              <pre className="max-h-52 overflow-auto whitespace-pre-wrap rounded-lg border bg-muted/10 p-3 text-xs">
                {draft.draftText}
              </pre>
            </div>
            <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">
              {t('broadcast.drafts.sendWarning')}
            </div>
            <div
              className="rounded-lg border bg-muted/20 p-3 text-sm"
              data-testid="broadcast-draft-send-countdown"
            >
              {t('broadcast.drafts.sendCountdown', { count: sendCountdown })}
            </div>
            <div className="flex items-start gap-3 rounded-lg border bg-muted/10 p-3">
              <Checkbox
                id="broadcast-send-acknowledge"
                checked={sendAcknowledged}
                disabled={sendBusy}
                data-testid="broadcast-draft-send-acknowledge"
                onCheckedChange={(checked) =>
                  setSendAcknowledged(Boolean(checked))
                }
              />
              <Label htmlFor="broadcast-send-acknowledge" className="leading-6">
                {t('broadcast.drafts.sendAcknowledge')}
              </Label>
            </div>
          </div>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={sendBusy}>
              {t('broadcast.drafts.cancelAction')}
            </AlertDialogCancel>
            <AlertDialogAction
              data-testid="broadcast-draft-send-confirm-action"
              disabled={sendConfirmActionDisabled}
              onClick={() => {
                setSendConfirmOpen(false);
                onSendDraft();
              }}
            >
              {sendBusy
                ? t('common.loading')
                : t('broadcast.drafts.confirmSendAction')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
