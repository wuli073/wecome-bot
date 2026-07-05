import { type MouseEvent, useEffect, useMemo, useRef, useState } from 'react';
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
  BroadcastTemplateDraft,
  BroadcastTemplateRenderResult,
  BroadcastVariableMapping,
} from '../../types';
import { markBroadcastRender } from '../../diagnostics';

interface TemplatePanelProps {
  templates: BroadcastMessageTemplate[];
  mappings: BroadcastVariableMapping[];
  loading: boolean;
  saving: boolean;
  error: string | null;
  onCreate: (draft: BroadcastTemplateDraft) => Promise<void>;
  onUpdate: (
    templateId: number,
    draft: BroadcastTemplateDraft,
  ) => Promise<void>;
  onDelete: (templateId: number) => Promise<void>;
  onRenderPreview: (payload: {
    templateId?: number;
    content?: string;
  }) => Promise<BroadcastTemplateRenderResult>;
}

function toDraft(
  template: BroadcastMessageTemplate | null,
): BroadcastTemplateDraft {
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
  markBroadcastRender('TemplatePanel');
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
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const pendingCursorRef = useRef<number | null>(null);
  const selectionRef = useRef<{ start: number; end: number } | null>(null);

  const variableValues = useMemo(
    () =>
      mappings.reduce<Record<string, string>>((acc, mapping) => {
        acc[mapping.variableKey] = mapping.sampleValue;
        return acc;
      }, {}),
    [mappings],
  );
  const mappingsByKey = useMemo(
    () => new Map(mappings.map((mapping) => [mapping.variableKey, mapping])),
    [mappings],
  );
  const variableCards = useMemo(() => {
    const orderedKeys: string[] = [];
    const seen = new Set<string>();

    for (const mapping of mappings) {
      if (seen.has(mapping.variableKey)) {
        continue;
      }
      seen.add(mapping.variableKey);
      orderedKeys.push(mapping.variableKey);
    }

    for (const variableKey of preview?.requiredVariables ?? []) {
      if (seen.has(variableKey)) {
        continue;
      }
      seen.add(variableKey);
      orderedKeys.push(variableKey);
    }

    return orderedKeys.map((variableKey) => {
      const mapping = mappingsByKey.get(variableKey) ?? null;
      const badgeVariant: 'destructive' | 'outline' | 'secondary' = !mapping
        ? 'destructive'
        : mapping.sampleState === 'ready'
          ? 'outline'
          : 'secondary';
      const badgeLabel = !mapping
        ? t('broadcast.labels.missing')
        : mapping.sampleState === 'ready'
          ? t('broadcast.labels.ready')
          : mapping.sampleState === 'no_value'
            ? t('broadcast.labels.noValidValue')
            : t('broadcast.labels.configured');
      const sampleText = !mapping
        ? t('broadcast.labels.noSampleValue')
        : variableValues[variableKey] ||
          (mapping.sampleState === 'no_value'
            ? t('broadcast.labels.noValidValue')
            : t('broadcast.labels.noSampleValue'));

      return {
        variableKey,
        badgeVariant,
        badgeLabel,
        sampleText,
      };
    });
  }, [mappings, mappingsByKey, preview?.requiredVariables, t, variableValues]);

  const activeTemplate =
    activeTemplateId === 'new'
      ? null
      : (templates.find((template) => template.id === activeTemplateId) ??
        null);

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
        const result = await onRenderPreview({ content: draft.body });
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

  useEffect(() => {
    const nextCursor = pendingCursorRef.current;
    const textarea = textareaRef.current;
    if (nextCursor == null || !textarea) {
      return;
    }

    pendingCursorRef.current = null;
    const animationFrameId = window.requestAnimationFrame(() => {
      textarea.focus();
      textarea.setSelectionRange(nextCursor, nextCursor);
      selectionRef.current = {
        start: nextCursor,
        end: nextCursor,
      };
    });

    return () => {
      window.cancelAnimationFrame(animationFrameId);
    };
  }, [draft.body]);

  const rememberSelection = (
    target: HTMLTextAreaElement | EventTarget | null,
  ) => {
    if (!(target instanceof HTMLTextAreaElement)) {
      return;
    }
    selectionRef.current = {
      start: target.selectionStart ?? 0,
      end: target.selectionEnd ?? 0,
    };
  };

  const handleInsertVariable = (variableKey: string) => {
    const token = `{{${variableKey}}}`;
    const textarea = textareaRef.current;
    const body = draft.body;
    const hasFocusedSelection =
      textarea != null &&
      document.activeElement === textarea &&
      selectionRef.current != null;
    const start = hasFocusedSelection
      ? Math.min(selectionRef.current?.start ?? 0, body.length)
      : body.length;
    const end = hasFocusedSelection
      ? Math.min(selectionRef.current?.end ?? start, body.length)
      : start;
    const nextBody = body.slice(0, start) + token + body.slice(end);
    const nextCursor = start + token.length;

    pendingCursorRef.current = nextCursor;
    setDraft((current) => ({
      ...current,
      body: nextBody,
    }));
  };

  const handleVariableMouseDown = (event: MouseEvent<HTMLButtonElement>) => {
    event.preventDefault();
  };

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
                  isActive ? 'border-blue-500 bg-blue-50' : 'hover:bg-muted/40'
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
              ref={textareaRef}
              data-testid="broadcast-template-body"
              value={draft.body}
              onChange={(event) =>
                setDraft((current) => ({
                  ...current,
                  body: event.target.value,
                }))
              }
              onSelect={(event) => rememberSelection(event.target)}
              onClick={(event) => rememberSelection(event.target)}
              onKeyUp={(event) => rememberSelection(event.target)}
              onFocus={(event) => rememberSelection(event.target)}
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
            <Button
              type="button"
              disabled={saving}
              onClick={() => void handleSave()}
            >
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
                {preview?.renderedText ||
                  t('broadcast.rules.templatePreviewHint')}
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
          {variableCards.map(
            ({ badgeLabel, badgeVariant, sampleText, variableKey }) => (
              <button
                key={variableKey}
                type="button"
                data-testid={`broadcast-template-variable-${variableKey}`}
                aria-label={t('broadcast.rules.insertVariableAria', {
                  name: variableKey,
                })}
                className="w-full rounded-lg border p-3 text-left transition-colors hover:bg-muted/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                onMouseDown={handleVariableMouseDown}
                onClick={() => handleInsertVariable(variableKey)}
              >
                <div className="flex items-center justify-between gap-2">
                  <Badge variant="secondary">{variableKey}</Badge>
                  <Badge variant={badgeVariant}>{badgeLabel}</Badge>
                </div>
                <div className="mt-2 text-xs text-muted-foreground">
                  {`{{${variableKey}}}`} · {sampleText}
                </div>
              </button>
            ),
          )}
        </CardContent>
      </Card>
    </div>
  );
}
