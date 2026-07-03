import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Separator } from '@/components/ui/separator';
import { Switch } from '@/components/ui/switch';
import { Textarea } from '@/components/ui/textarea';

import type {
  BroadcastMessageTemplate,
  BroadcastScope,
  BroadcastTemplateDraft,
  BroadcastTemplateRenderResult,
  BroadcastVariableMapping,
} from '../../types';

interface TemplatePanelProps {
  scope: BroadcastScope;
  templates: BroadcastMessageTemplate[];
  mappings: BroadcastVariableMapping[];
  loading: boolean;
  saving: boolean;
  error: string | null;
  onCreate: (draft: BroadcastTemplateDraft) => Promise<void>;
  onUpdate: (templateId: number, draft: BroadcastTemplateDraft) => Promise<void>;
  onDelete: (templateId: number) => Promise<void>;
  onRenderPreview: (payload: {
    templateId?: number;
    content?: string;
  }) => Promise<BroadcastTemplateRenderResult>;
}

function toDraft(template: BroadcastMessageTemplate | null): BroadcastTemplateDraft {
  if (!template) {
    return {
      name: '',
      body: '',
      enabled: true,
    };
  }
  return {
    id: template.id,
    name: template.name,
    body: template.body,
    enabled: template.enabled,
  };
}

export default function TemplatePanel({
  scope,
  templates,
  mappings,
  loading,
  saving,
  error,
  onCreate,
  onUpdate,
  onDelete,
  onRenderPreview,
}: TemplatePanelProps) {
  const { t } = useTranslation();
  const [activeTemplateId, setActiveTemplateId] = useState<number | 'new'>(
    templates[0]?.id ?? 'new',
  );
  const [draft, setDraft] = useState<BroadcastTemplateDraft>(
    toDraft(templates[0] ?? null),
  );
  const [preview, setPreview] = useState<BroadcastTemplateRenderResult | null>(
    null,
  );
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [deleteConfirm, setDeleteConfirm] = useState(false);

  const variableValues = useMemo(
    () =>
      mappings.reduce<Record<string, string>>((acc, mapping) => {
        acc[mapping.variableKey] = mapping.sampleValue;
        return acc;
      }, {}),
    [mappings],
  );

  const activeTemplate =
    activeTemplateId === 'new'
      ? null
      : templates.find((template) => template.id === activeTemplateId) ?? null;

  useEffect(() => {
    if (activeTemplateId === 'new') {
      setDraft({
        name: '',
        body: '',
        enabled: true,
      });
      setPreview(null);
      setPreviewError(null);
      return;
    }

    setDraft(toDraft(activeTemplate));
    setPreview(null);
    setPreviewError(null);
    setDeleteConfirm(false);
  }, [activeTemplate, activeTemplateId]);

  useEffect(() => {
    let cancelled = false;

    const runPreview = async () => {
      if (!draft.body.trim()) {
        setPreview(null);
        setPreviewError(null);
        return;
      }

      try {
        const result = activeTemplate
          ? await onRenderPreview({ templateId: activeTemplate.id })
          : await onRenderPreview({ content: draft.body });
        if (!cancelled) {
          setPreview(result);
          setPreviewError(null);
        }
      } catch (err) {
        if (!cancelled) {
          const message =
            err && typeof err === 'object' && 'msg' in err
              ? String((err as { msg: unknown }).msg)
              : t('common.error');
          setPreview(null);
          setPreviewError(message);
        }
      }
    };

    void runPreview();

    return () => {
      cancelled = true;
    };
  }, [activeTemplate, draft.body, onRenderPreview, t]);

  const handleSave = async () => {
    if (activeTemplate) {
      await onUpdate(activeTemplate.id, draft);
      return;
    }
    await onCreate(draft);
  };

  return (
    <div
      className="grid gap-4 xl:grid-cols-[260px_minmax(0,1fr)_320px]"
      data-testid="broadcast-template-panel"
    >
      <Card className="gap-4">
        <CardHeader>
          <CardTitle>{t('broadcast.rules.templates.title')}</CardTitle>
          <CardDescription>
            {t('broadcast.rules.templates.description')}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-2">
          <Button
            type="button"
            variant={activeTemplateId === 'new' ? 'default' : 'outline'}
            className="w-full"
            onClick={() => setActiveTemplateId('new')}
          >
            {t('broadcast.actions.newTemplate')}
          </Button>
          {templates.map((template) => {
            const isActive = template.id === activeTemplate?.id;
            return (
              <button
                type="button"
                key={template.id}
                onClick={() => setActiveTemplateId(template.id)}
                className={`w-full rounded-xl border p-3 text-left transition-colors ${
                  isActive
                    ? 'border-blue-500 bg-blue-50'
                    : 'hover:bg-muted/40'
                }`}
              >
                <div className="flex items-center justify-between gap-2">
                  <div className="font-medium">{template.name}</div>
                  <Badge variant={template.enabled ? 'secondary' : 'outline'}>
                    {template.enabled
                      ? t('broadcast.labels.enabled')
                      : t('broadcast.labels.disabled')}
                  </Badge>
                </div>
                <div className="mt-1 text-xs text-muted-foreground">
                  {template.updatedAt}
                </div>
              </button>
            );
          })}
        </CardContent>
      </Card>

      <Card className="gap-4">
        <CardHeader>
          <CardTitle>
            {activeTemplate
              ? t('broadcast.actions.editTemplate')
              : t('broadcast.actions.newTemplate')}
          </CardTitle>
          <CardDescription>
            {t('broadcast.rules.templates.editorDescription')}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {loading ? (
            <div className="text-sm text-muted-foreground">
              {t('common.loading')}
            </div>
          ) : null}
          {error ? (
            <Alert variant="destructive">
              <AlertTitle>{t('common.error')}</AlertTitle>
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          ) : null}

          <div className="space-y-2">
            <Label htmlFor="broadcast-template-name">
              {t('broadcast.fields.templateName')}
            </Label>
            <Input
              id="broadcast-template-name"
              value={draft.name}
              onChange={(event) =>
                setDraft((current) => ({
                  ...current,
                  name: event.target.value,
                }))
              }
              placeholder={t('broadcast.placeholders.templateName')}
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="broadcast-template-body">
              {t('broadcast.fields.templateBody')}
            </Label>
            <Textarea
              id="broadcast-template-body"
              value={draft.body}
              onChange={(event) =>
                setDraft((current) => ({
                  ...current,
                  body: event.target.value,
                }))
              }
              className="min-h-48"
            />
          </div>

          <div className="flex items-center justify-between rounded-lg border p-3">
            <div>
              <div className="text-sm font-medium">
                {t('broadcast.fields.enabled')}
              </div>
              <div className="text-xs text-muted-foreground">
                {t('broadcast.hints.templateEnabled')}
              </div>
            </div>
            <Switch
              checked={draft.enabled}
              onCheckedChange={(checked) =>
                setDraft((current) => ({
                  ...current,
                  enabled: checked,
                }))
              }
            />
          </div>

          <div className="flex flex-wrap gap-2">
            <Button type="button" disabled={saving} onClick={() => void handleSave()}>
              {activeTemplate
                ? t('broadcast.actions.saveTemplate')
                : t('broadcast.actions.createTemplate')}
            </Button>
            {activeTemplate ? (
              <Button
                type="button"
                variant={deleteConfirm ? 'destructive' : 'outline'}
                disabled={saving}
                onClick={() => {
                  if (!deleteConfirm) {
                    setDeleteConfirm(true);
                    return;
                  }
                  void onDelete(activeTemplate.id);
                  setDeleteConfirm(false);
                }}
              >
                {deleteConfirm
                  ? t('broadcast.actions.confirmDeleteTemplate')
                  : t('broadcast.actions.deleteTemplate')}
              </Button>
            ) : null}
          </div>

          <Separator />
          <div className="space-y-2">
            <div className="text-sm font-medium">
              {t('broadcast.rules.templatePreview')}
            </div>
            {previewError ? (
              <Alert variant="destructive">
                <AlertDescription>{previewError}</AlertDescription>
              </Alert>
            ) : (
              <pre className="whitespace-pre-wrap rounded-lg border bg-muted/20 p-4 text-sm leading-6">
                {preview?.renderedText || t('broadcast.rules.templatePreviewHint')}
              </pre>
            )}
          </div>
        </CardContent>
      </Card>

      <Card className="gap-4">
        <CardHeader>
          <CardTitle>{t('broadcast.rules.availableVariables')}</CardTitle>
          <CardDescription>
            {t('broadcast.rules.availableVariablesDescription')}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {(preview?.requiredVariables ?? []).map((variableKey) => (
            <div key={variableKey} className="rounded-lg border p-3">
              <div className="flex items-center justify-between gap-2">
                <Badge variant="secondary">{variableKey}</Badge>
                <Badge
                  variant={
                    preview?.missingVariables.includes(variableKey)
                      ? 'destructive'
                      : 'outline'
                  }
                >
                  {preview?.missingVariables.includes(variableKey)
                    ? t('broadcast.labels.missing')
                    : t('broadcast.labels.ready')}
                </Badge>
              </div>
              <div className="mt-2 text-xs text-muted-foreground">
                {`{{${variableKey}}}`} → {variableValues[variableKey] || '暂无示例值'}
              </div>
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}
