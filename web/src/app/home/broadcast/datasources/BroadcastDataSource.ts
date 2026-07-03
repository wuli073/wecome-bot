import { backendClient } from '@/app/infra/http';
import type {
  ApiBroadcastGroupMatchResult,
  ApiBroadcastGroupName,
  ApiBroadcastGroupRule,
  ApiBroadcastScope,
  ApiBroadcastTemplate,
  ApiBroadcastTemplateRenderResult,
  ApiBroadcastVariableProfile,
} from '@/app/infra/entities/api';

import { createBroadcastWorkspaceSnapshot } from '../mockData';
import {
  BROADCAST_STATUS_LABELS,
  buildTemplatePreviewVariables,
  buildVariableMappings,
} from '../utils';
import type {
  BroadcastDraft,
  BroadcastGroupMatchResult,
  BroadcastGroupName,
  BroadcastGroupRule,
  BroadcastGroupRuleDraft,
  BroadcastMessageTemplate,
  BroadcastPasteDraftRequest,
  BroadcastPasteOnlyAdapter,
  BroadcastRuntimePasteDraftPayload,
  BroadcastRulesData,
  BroadcastScope,
  BroadcastStatus,
  BroadcastTemplateDraft,
  BroadcastTemplateRenderResult,
  BroadcastVariableProfile,
  BroadcastWorkspaceSnapshot,
} from '../types';

function cloneValue<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

function toApiScope(scope: BroadcastScope): ApiBroadcastScope {
  return {
    bot_uuid: scope.botUuid,
    connector_id: scope.connectorId,
  };
}

function fromApiTemplate(template: ApiBroadcastTemplate): BroadcastMessageTemplate {
  return {
    id: template.id,
    name: template.name,
    updatedAt: template.updated_at,
    variableKeys: template.variables,
    body: template.content,
    enabled: template.enabled,
  };
}

function fromApiVariableProfile(
  profile: ApiBroadcastVariableProfile,
): BroadcastVariableProfile {
  return {
    groupField: profile.group_field,
    mappingRules: profile.mapping_rules.map((rule) => ({
      sourceField: rule.source_field,
      variableKey: rule.variable_key,
      mergeMode: rule.merge_mode,
      order: rule.order,
    })),
  };
}

function toApiVariableProfile(profile: BroadcastVariableProfile) {
  return {
    group_field: profile.groupField,
    mapping_rules: profile.mappingRules.map((rule) => ({
      source_field: rule.sourceField,
      variable_key: rule.variableKey,
      merge_mode: rule.mergeMode,
      order: rule.order,
    })),
  };
}

function fromApiTemplateRenderResult(
  result: ApiBroadcastTemplateRenderResult,
): BroadcastTemplateRenderResult {
  return {
    renderedText: result.rendered_text,
    requiredVariables: result.required_variables,
    missingVariables: result.missing_variables,
    valid: result.valid,
  };
}

function fromApiGroupRule(rule: ApiBroadcastGroupRule): BroadcastGroupRule {
  return {
    id: rule.id,
    sourceValue: rule.source_value,
    matchType: rule.match_type,
    matchExpression: rule.match_expression,
    targetConversationName: rule.target_conversation_name,
    priority: rule.priority,
    enabled: rule.enabled,
    updatedAt: rule.updated_at,
  };
}

function toApiGroupRuleDraft(draft: BroadcastGroupRuleDraft) {
  return {
    source_value: draft.sourceValue,
    match_type: draft.matchType,
    match_expression: draft.matchExpression,
    target_conversation_name: draft.targetConversationName,
    priority: draft.priority,
    enabled: draft.enabled,
  };
}

function fromApiGroupMatchResult(
  result: ApiBroadcastGroupMatchResult,
): BroadcastGroupMatchResult {
  return {
    matched: result.matched,
    ruleId: result.rule_id,
    targetConversationName: result.target_conversation_name,
    matchType: result.match_type,
  };
}

function fromApiGroupName(groupName: ApiBroadcastGroupName): BroadcastGroupName {
  return {
    id: groupName.id,
    name: groupName.name,
    updatedAt: groupName.updated_at,
  };
}

function updateDraftStatus(
  draft: BroadcastDraft,
  status: BroadcastStatus,
): BroadcastDraft {
  return {
    ...draft,
    status,
    progressLabel: BROADCAST_STATUS_LABELS[status],
    updatedAt: new Date().toISOString(),
  };
}

export interface BroadcastDataSource {
  loadSnapshot: () => BroadcastWorkspaceSnapshot;
  loadRulesData: (scope: BroadcastScope) => Promise<BroadcastRulesData>;
  saveVariableProfile: (
    scope: BroadcastScope,
    profile: BroadcastVariableProfile,
  ) => Promise<BroadcastVariableProfile>;
  createTemplate: (
    scope: BroadcastScope,
    template: BroadcastTemplateDraft,
  ) => Promise<BroadcastMessageTemplate>;
  updateTemplate: (
    scope: BroadcastScope,
    templateId: number,
    template: BroadcastTemplateDraft,
  ) => Promise<BroadcastMessageTemplate>;
  deleteTemplate: (scope: BroadcastScope, templateId: number) => Promise<void>;
  renderTemplate: (
    scope: BroadcastScope,
    payload:
      | { templateId: number; variables: Record<string, string> }
      | { content: string; variables: Record<string, string> },
  ) => Promise<BroadcastTemplateRenderResult>;
  createGroupRule: (
    scope: BroadcastScope,
    draft: BroadcastGroupRuleDraft,
  ) => Promise<BroadcastGroupRule>;
  updateGroupRule: (
    scope: BroadcastScope,
    ruleId: number,
    draft: BroadcastGroupRuleDraft,
  ) => Promise<BroadcastGroupRule>;
  deleteGroupRule: (scope: BroadcastScope, ruleId: number) => Promise<void>;
  matchGroupRule: (
    scope: BroadcastScope,
    sourceValue: string,
  ) => Promise<BroadcastGroupMatchResult>;
  createGroupNames: (
    scope: BroadcastScope,
    names: string[],
  ) => Promise<BroadcastGroupName[]>;
  deleteGroupName: (
    scope: BroadcastScope,
    groupNameId: number,
  ) => Promise<void>;
  saveDraftText: (
    snapshot: BroadcastWorkspaceSnapshot,
    draftId: number,
    draftText: string,
  ) => BroadcastWorkspaceSnapshot;
  applyDraftStatus: (
    snapshot: BroadcastWorkspaceSnapshot,
    draftIds: number[],
    status: BroadcastStatus,
  ) => BroadcastWorkspaceSnapshot;
  appendLogs: (
    snapshot: BroadcastWorkspaceSnapshot,
    entries: BroadcastWorkspaceSnapshot['executionLogs'],
  ) => BroadcastWorkspaceSnapshot;
}

export function createBroadcastDataSource(): BroadcastDataSource {
  const seed = createBroadcastWorkspaceSnapshot();

  return {
    loadSnapshot: () => cloneValue(seed),
    loadRulesData: async (scope) => {
      const apiScope = toApiScope(scope);
      const [templates, variableProfile, groupRules, groupNames] =
        await Promise.all([
          backendClient.getBroadcastTemplates(apiScope),
          backendClient.getBroadcastVariableProfile(apiScope),
          backendClient.getBroadcastGroupRules(apiScope),
          backendClient.getBroadcastGroupNames(apiScope),
        ]);

      const mappedTemplates = templates.map(fromApiTemplate);
      const mappedVariableProfile = fromApiVariableProfile(variableProfile);

      return {
        scope,
        templates: mappedTemplates,
        variableProfile: mappedVariableProfile,
        variableMappings: buildVariableMappings(
          mappedVariableProfile,
          mappedTemplates,
        ),
        groupRules: groupRules.map(fromApiGroupRule),
        groupNames: groupNames.map(fromApiGroupName),
      };
    },
    saveVariableProfile: async (scope, profile) =>
      fromApiVariableProfile(
        await backendClient.saveBroadcastVariableProfile(
          toApiScope(scope),
          toApiVariableProfile(profile),
        ),
      ),
    createTemplate: async (scope, template) =>
      fromApiTemplate(
        await backendClient.createBroadcastTemplate(toApiScope(scope), {
          name: template.name,
          content: template.body,
          enabled: template.enabled,
        }),
      ),
    updateTemplate: async (scope, templateId, template) =>
      fromApiTemplate(
        await backendClient.updateBroadcastTemplate(toApiScope(scope), templateId, {
          name: template.name,
          content: template.body,
          enabled: template.enabled,
        }),
      ),
    deleteTemplate: async (scope, templateId) => {
      await backendClient.deleteBroadcastTemplate(toApiScope(scope), templateId);
    },
    renderTemplate: async (scope, payload) => {
      const variables = payload.variables ?? {};
      if ('templateId' in payload) {
        return fromApiTemplateRenderResult(
          await backendClient.renderBroadcastTemplate(toApiScope(scope), {
            templateId: payload.templateId,
            variables,
          }),
        );
      }
      return fromApiTemplateRenderResult(
        await backendClient.renderBroadcastTemplate(toApiScope(scope), {
          content: payload.content,
          variables,
        }),
      );
    },
    createGroupRule: async (scope, draft) =>
      fromApiGroupRule(
        await backendClient.createBroadcastGroupRule(
          toApiScope(scope),
          toApiGroupRuleDraft(draft),
        ),
      ),
    updateGroupRule: async (scope, ruleId, draft) =>
      fromApiGroupRule(
        await backendClient.updateBroadcastGroupRule(
          toApiScope(scope),
          ruleId,
          toApiGroupRuleDraft(draft),
        ),
      ),
    deleteGroupRule: async (scope, ruleId) => {
      await backendClient.deleteBroadcastGroupRule(toApiScope(scope), ruleId);
    },
    matchGroupRule: async (scope, sourceValue) =>
      fromApiGroupMatchResult(
        await backendClient.matchBroadcastGroupRule(
          toApiScope(scope),
          sourceValue,
        ),
      ),
    createGroupNames: async (scope, names) => {
      const response = await backendClient.createBroadcastGroupNames(
        toApiScope(scope),
        names,
      );
      return response.group_names.map(fromApiGroupName);
    },
    deleteGroupName: async (scope, groupNameId) => {
      await backendClient.deleteBroadcastGroupName(
        toApiScope(scope),
        groupNameId,
      );
    },
    saveDraftText: (snapshot, draftId, draftText) => ({
      ...snapshot,
      drafts: snapshot.drafts.map((draft) =>
        draft.id === draftId
          ? {
              ...draft,
              draftText,
              updatedAt: new Date().toISOString(),
            }
          : draft,
      ),
    }),
    applyDraftStatus: (snapshot, draftIds, status) => ({
      ...snapshot,
      drafts: snapshot.drafts.map((draft) =>
        draftIds.includes(draft.id) ? updateDraftStatus(draft, status) : draft,
      ),
    }),
    appendLogs: (snapshot, entries) => ({
      ...snapshot,
      executionLogs: [...entries, ...snapshot.executionLogs],
    }),
  };
}

export const broadcastPasteOnlyAdapter: BroadcastPasteOnlyAdapter = {
  toRuntimePayload: (
    request: BroadcastPasteDraftRequest,
    requestDigest: string,
  ): BroadcastRuntimePasteDraftPayload => ({
    action: 'paste_draft',
    conversationName: request.conversationName,
    draftText: request.draftText,
    idempotencyKey: request.idempotencyKey,
    requestDigest,
  }),
};

export function applyRulesDataToSnapshot(
  snapshot: BroadcastWorkspaceSnapshot,
  rulesData: BroadcastRulesData,
): BroadcastWorkspaceSnapshot {
  const seedDraft = snapshot.drafts[0];
  const template = rulesData.templates[0];
  const variableMap = buildTemplatePreviewVariables(rulesData.variableMappings);

  const hydratedDrafts = snapshot.drafts.map((draft) => ({
    ...draft,
    botUuid: rulesData.scope.botUuid,
    connectorId: rulesData.scope.connectorId,
    templateName: template?.name ?? draft.templateName,
    draftText:
      draft.id === seedDraft?.id && template
        ? template.body.replaceAll(
            /{{\s*([A-Za-z0-9_\-\u4e00-\u9fff]+)\s*}}/g,
            (token, key: string) => variableMap[key] || token,
          )
        : draft.draftText,
  }));

  return {
    ...snapshot,
    scope: rulesData.scope,
    templates: rulesData.templates,
    variableProfile: rulesData.variableProfile,
    variableMappings: rulesData.variableMappings,
    groupRules: rulesData.groupRules,
    groupNames: rulesData.groupNames,
    drafts: hydratedDrafts,
  };
}
