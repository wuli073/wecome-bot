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
import { Separator } from '@/components/ui/separator';

import type { BroadcastDraft } from '../../types';

interface DraftDetailProps {
  draft: BroadcastDraft | null;
  editingDraftId: number | null;
  draftEditorText: string;
  busy?: boolean;
  onStartEdit: (draft: BroadcastDraft) => void;
  onDraftEditorTextChange: (value: string) => void;
  onSaveDraft: () => void;
  onCancelEdit: () => void;
  onConfirmDraft: () => void;
  onRevokeDraft: () => void;
}

export default function DraftDetail({
  draft,
  editingDraftId,
  draftEditorText,
  busy = false,
  onStartEdit,
  onDraftEditorTextChange,
  onSaveDraft,
  onCancelEdit,
  onConfirmDraft,
  onRevokeDraft,
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

  const confirmDisabled = draft.status !== 'pending_review' || Boolean(draft.draftsStale);
  const revokeDisabled = draft.status !== 'ready';

  return (
    <Card className="gap-4" data-testid="broadcast-draft-detail">
      <CardHeader>
        <div className="flex items-start justify-between gap-3">
          <div>
            <CardTitle>{draft.customerName}</CardTitle>
            <CardDescription>{draft.conversationName}</CardDescription>
          </div>
          <Badge variant="outline">
            {draft.status === 'pending_review'
              ? '待审核'
              : draft.status === 'ready'
                ? '已确认'
                : '无效'}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-3 md:grid-cols-2">
          <div className="rounded-xl border bg-muted/20 p-4">
            <div className="text-xs text-muted-foreground">模板</div>
            <div className="mt-2 font-medium">{draft.templateName}</div>
          </div>
          <div className="rounded-xl border bg-muted/20 p-4">
            <div className="text-xs text-muted-foreground">群聊</div>
            <div className="mt-2 font-medium">{draft.conversationName || '-'}</div>
          </div>
        </div>

        {draft.draftsStale ? (
          <div className="rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-800">
            草稿已过期，请重新生成
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
              disabled={busy}
            >
              {t('broadcast.drafts.editDraft')}
            </Button>
          ) : (
            <>
              <Button data-testid="broadcast-draft-save-button" onClick={onSaveDraft} disabled={busy}>
                {t('broadcast.drafts.saveDraft')}
              </Button>
              <Button variant="outline" onClick={onCancelEdit} disabled={busy}>
                {t('broadcast.drafts.cancelEdit')}
              </Button>
            </>
          )}
          <Button
            data-testid="broadcast-draft-confirm-button"
            onClick={onConfirmDraft}
            disabled={confirmDisabled || busy}
          >
            确认草稿
          </Button>
          <Button
            data-testid="broadcast-draft-revoke-button"
            variant="outline"
            onClick={onRevokeDraft}
            disabled={revokeDisabled || busy}
          >
            撤回确认
          </Button>
        </div>

        <div className="space-y-2">
          <div className="text-sm font-medium">草稿正文</div>
          {isEditing ? (
            <Textarea
              aria-label={t('broadcast.drafts.editor')}
              className="min-h-[220px]"
              value={draftEditorText}
              onChange={(event) => onDraftEditorTextChange(event.target.value)}
            />
          ) : (
            <pre className="whitespace-pre-wrap rounded-xl border bg-muted/10 p-4 text-sm leading-6">
              {draft.draftText}
            </pre>
          )}
        </div>

        <Separator />

        <div className="rounded-xl border bg-muted/10 p-4 text-sm text-muted-foreground">
          本阶段仅支持草稿生成、编辑、确认与撤回，发送执行功能保持关闭。
        </div>
      </CardContent>
    </Card>
  );
}
