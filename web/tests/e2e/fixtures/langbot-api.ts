import { Page, Route } from '@playwright/test';

type JsonRecord = Record<string, unknown>;

interface SkillMock {
  name: string;
  display_name: string;
  description: string;
  instructions: string;
  package_root: string;
  updated_at: string;
}

interface PipelineMock {
  uuid: string;
  name: string;
  description: string;
  config: JsonRecord;
  emoji: string;
  is_default: boolean;
  updated_at: string;
}

interface KnowledgeBaseMock {
  uuid: string;
  name: string;
  description: string;
  emoji: string;
  knowledge_engine_plugin_id: string;
  creation_settings: JsonRecord;
  retrieval_settings: JsonRecord;
  knowledge_engine: {
    plugin_id: string;
    name: {
      en_US: string;
      zh_Hans: string;
    };
    capabilities: string[];
  };
  updated_at: string;
}

interface MCPServerMock {
  name: string;
  mode: 'sse' | 'stdio' | 'http';
  enable: boolean;
  extra_args: JsonRecord;
  runtime_info: {
    status: 'connected';
    tool_count: number;
    tools: unknown[];
  };
  readme: string;
  updated_at: string;
}

interface BotMock {
  uuid: string;
  name: string;
  description: string;
  enable: boolean;
  adapter: string;
  adapter_config: JsonRecord;
  use_pipeline_uuid?: string;
  pipeline_routing_rules: unknown[];
  adapter_runtime_values: JsonRecord;
  updated_at: string;
}

interface BroadcastTemplateMock {
  id: number;
  bot_uuid: string;
  connector_id: string;
  name: string;
  content: string;
  variables: string[];
  enabled: boolean;
  created_at: string;
  updated_at: string;
}

interface BroadcastVariableProfileMock {
  group_field: string | null;
  mapping_rules: Array<{
    source_field: string;
    variable_key: string;
    merge_mode:
      | 'first'
      | 'lines'
      | 'unique_lines'
      | 'commas'
      | 'unique_commas';
    order: number;
  }>;
}

interface BroadcastGroupRuleMock {
  id: number;
  bot_uuid: string;
  connector_id: string;
  source_value: string;
  match_type: 'exact' | 'contains' | 'regex';
  match_expression: string;
  target_conversation_name: string;
  priority: number;
  enabled: boolean;
  created_at: string;
  updated_at: string;
}

interface BroadcastGroupNameMock {
  id: number;
  bot_uuid: string;
  connector_id: string;
  name: string;
  created_at: string;
  updated_at: string;
}

interface LangBotApiMockState {
  bots: BotMock[];
  broadcastGroupNames: BroadcastGroupNameMock[];
  broadcastGroupRules: BroadcastGroupRuleMock[];
  broadcastTemplates: BroadcastTemplateMock[];
  broadcastVariableProfile: BroadcastVariableProfileMock;
  counters: Record<string, number>;
  knowledgeBases: KnowledgeBaseMock[];
  mcpServers: MCPServerMock[];
  pipelines: PipelineMock[];
  skills: SkillMock[];
}

function ok(data: unknown) {
  return {
    code: 0,
    message: 'ok',
    data,
    timestamp: Date.now(),
  };
}

async function fulfillJson(route: Route, data: unknown) {
  await route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify(ok(data)),
  });
}

async function fulfillError(
  route: Route,
  status: number,
  msg: string,
  message: string,
  details: string[] = [],
) {
  await route.fulfill({
    status,
    contentType: 'application/json',
    body: JSON.stringify({
      code: -1,
      msg,
      message,
      details,
      data: null,
      timestamp: Date.now(),
    }),
  });
}

function routePath(route: Route) {
  return new URL(route.request().url()).pathname;
}

function parseJsonBody(route: Route): JsonRecord {
  return JSON.parse(route.request().postData() || '{}') as JsonRecord;
}

function now() {
  return new Date().toISOString();
}

function nextId(state: LangBotApiMockState, prefix: string) {
  state.counters[prefix] = (state.counters[prefix] || 0) + 1;
  return `${prefix}-${state.counters[prefix]}`;
}

function emptyMonitoringData() {
  return {
    overview: {
      total_messages: 0,
      llm_calls: 0,
      embedding_calls: 0,
      model_calls: 0,
      success_rate: 0,
      active_sessions: 0,
    },
    messages: [],
    llmCalls: [],
    embeddingCalls: [],
    sessions: [],
    errors: [],
    totalCount: {
      messages: 0,
      llmCalls: 0,
      embeddingCalls: 0,
      sessions: 0,
      errors: 0,
    },
  };
}

function emptyTokenStatistics() {
  return {
    summary: {
      total_calls: 0,
      success_calls: 0,
      error_calls: 0,
      total_input_tokens: 0,
      total_output_tokens: 0,
      total_tokens: 0,
      total_cost: 0,
      avg_tokens_per_call: 0,
      avg_duration_ms: 0,
      avg_tokens_per_second: 0,
      zero_token_success_calls: 0,
    },
    by_model: [],
    timeseries: [],
    bucket: 'day',
  };
}

function makeSkill(data: JsonRecord): SkillMock {
  return {
    name: String(data.name || ''),
    display_name: String(data.display_name || ''),
    description: String(data.description || ''),
    instructions: String(data.instructions || ''),
    package_root: String(data.package_root || ''),
    updated_at: new Date().toISOString(),
  };
}

function makePipeline(
  state: LangBotApiMockState,
  data: JsonRecord,
  uuid = nextId(state, 'pipeline'),
): PipelineMock {
  return {
    uuid,
    name: String(data.name || ''),
    description: String(data.description || ''),
    config: (data.config as JsonRecord | undefined) || {
      ai: {},
      trigger: {},
      safety: {},
      output: {},
    },
    emoji: String(data.emoji || '⚙️'),
    is_default: false,
    updated_at: now(),
  };
}

function knowledgeEngine() {
  return {
    plugin_id: 'builtin/minimal-knowledge',
    name: {
      en_US: 'Minimal Knowledge Engine',
      zh_Hans: '最小知识库引擎',
    },
    description: {
      en_US: 'Minimal mocked engine for frontend smoke tests.',
      zh_Hans: '用于前端冒烟测试的最小模拟引擎。',
    },
    capabilities: ['text_retrieval'],
    creation_schema: [],
    retrieval_schema: [],
  };
}

function makeKnowledgeBase(
  state: LangBotApiMockState,
  data: JsonRecord,
  uuid = nextId(state, 'knowledge'),
): KnowledgeBaseMock {
  const engine = knowledgeEngine();
  return {
    uuid,
    name: String(data.name || ''),
    description: String(data.description || ''),
    emoji: String(data.emoji || '📚'),
    knowledge_engine_plugin_id: String(
      data.knowledge_engine_plugin_id || engine.plugin_id,
    ),
    creation_settings: (data.creation_settings as JsonRecord | undefined) || {},
    retrieval_settings:
      (data.retrieval_settings as JsonRecord | undefined) || {},
    knowledge_engine: {
      plugin_id: engine.plugin_id,
      name: engine.name,
      capabilities: engine.capabilities,
    },
    updated_at: now(),
  };
}

function makeMCPServer(data: JsonRecord): MCPServerMock {
  return {
    name: String(data.name || ''),
    mode: (data.mode as MCPServerMock['mode']) || 'sse',
    enable: data.enable !== false,
    extra_args: (data.extra_args as JsonRecord | undefined) || {},
    runtime_info: {
      status: 'connected',
      tool_count: 0,
      tools: [],
    },
    readme: '',
    updated_at: now(),
  };
}

function makeBot(
  state: LangBotApiMockState,
  data: JsonRecord,
  uuid = nextId(state, 'bot'),
): BotMock {
  return {
    uuid,
    name: String(data.name || ''),
    description: String(data.description || ''),
    enable: data.enable !== false,
    adapter: String(data.adapter || 'playwright-adapter'),
    adapter_config: (data.adapter_config as JsonRecord | undefined) || {},
    use_pipeline_uuid: data.use_pipeline_uuid
      ? String(data.use_pipeline_uuid)
      : undefined,
    pipeline_routing_rules:
      (data.pipeline_routing_rules as unknown[] | undefined) || [],
    adapter_runtime_values: {
      webhook_full_url: `https://playwright.test/bots/${uuid}/webhook`,
      extra_webhook_full_url: '',
    },
    updated_at: now(),
  };
}

function extractTemplateVariables(content: string): string[] {
  const matches = content.matchAll(/{{\s*([A-Za-z0-9_\-\u4e00-\u9fff]+)\s*}}/g);
  return Array.from(new Set(Array.from(matches, (match) => match[1])));
}

function renderBroadcastTemplate(
  content: string,
  variables: Record<string, unknown>,
) {
  const required_variables = extractTemplateVariables(content);
  const rendered_text = content.replace(
    /{{\s*([A-Za-z0-9_\-\u4e00-\u9fff]+)\s*}}/g,
    (token, key: string) => {
      const value = variables[key];
      return value === undefined || value === null || value === ''
        ? token
        : String(value);
    },
  );
  const missing_variables = required_variables.filter((key) => {
    const value = variables[key];
    return value === undefined || value === null || value === '';
  });
  return {
    rendered_text,
    required_variables,
    missing_variables,
    valid: missing_variables.length === 0,
  };
}

function matchBroadcastRule(
  rule: BroadcastGroupRuleMock,
  sourceValue: string,
): boolean {
  if (!rule.enabled) {
    return false;
  }

  if (rule.match_type === 'exact') {
    return sourceValue === rule.match_expression;
  }

  if (rule.match_type === 'contains') {
    return sourceValue.includes(rule.match_expression);
  }

  try {
    return new RegExp(rule.match_expression).test(sourceValue);
  } catch {
    return false;
  }
}

function seedBroadcastState(): Pick<
  LangBotApiMockState,
  | 'broadcastTemplates'
  | 'broadcastVariableProfile'
  | 'broadcastGroupRules'
  | 'broadcastGroupNames'
> {
  const timestamp = now();
  return {
    broadcastTemplates: [
      {
        id: 1,
        bot_uuid: 'bot-1',
        connector_id: 'wxwork-local',
        name: 'Arrival Reminder',
        content:
          'Hello {{customer_name}},\nShipment {{shipment_no}} is expected to arrive on {{eta_date}}.',
        variables: ['customer_name', 'shipment_no', 'eta_date'],
        enabled: true,
        created_at: timestamp,
        updated_at: timestamp,
      },
      {
        id: 2,
        bot_uuid: 'bot-1',
        connector_id: 'wxwork-local',
        name: 'Payment Notice',
        content:
          'Hi {{customer_name}},\nInvoice {{invoice_no}} is awaiting confirmation.',
        variables: ['customer_name', 'invoice_no'],
        enabled: true,
        created_at: timestamp,
        updated_at: timestamp,
      },
    ],
    broadcastVariableProfile: {
      group_field: 'Customer Name',
      mapping_rules: [
        {
          source_field: 'Customer Name',
          variable_key: 'customer_name',
          merge_mode: 'first',
          order: 1,
        },
        {
          source_field: 'Shipment No',
          variable_key: 'shipment_no',
          merge_mode: 'first',
          order: 2,
        },
        {
          source_field: 'ETA Date',
          variable_key: 'eta_date',
          merge_mode: 'first',
          order: 3,
        },
      ],
    },
    broadcastGroupRules: [
      {
        id: 1,
        bot_uuid: 'bot-1',
        connector_id: 'wxwork-local',
        source_value: 'Acme Freight',
        match_type: 'exact',
        match_expression: 'Acme Freight',
        target_conversation_name: 'Acme Freight Ops',
        priority: 30,
        enabled: true,
        created_at: timestamp,
        updated_at: timestamp,
      },
    ],
    broadcastGroupNames: [
      {
        id: 1,
        bot_uuid: 'bot-1',
        connector_id: 'wxwork-local',
        name: 'Acme Freight Ops',
        created_at: timestamp,
        updated_at: timestamp,
      },
      {
        id: 2,
        bot_uuid: 'bot-1',
        connector_id: 'wxwork-local',
        name: 'Northwind Service Group',
        created_at: timestamp,
        updated_at: timestamp,
      },
    ],
  };
}

function mockAdapters() {
  return [
    {
      name: 'playwright-adapter',
      label: {
        en_US: 'Playwright Adapter',
        zh_Hans: 'Playwright 适配器',
      },
      description: {
        en_US: 'Minimal adapter for frontend E2E tests.',
        zh_Hans: '用于前端 E2E 测试的最小适配器。',
      },
      spec: {
        categories: ['testing'],
        config: [],
      },
    },
  ];
}

async function handleBackendApi(route: Route, state: LangBotApiMockState) {
  const request = route.request();
  const url = new URL(request.url());
  const path = url.pathname;
  const method = request.method();

  if (path === '/api/v1/system/info') {
    return fulfillJson(route, {
      debug: false,
      version: 'frontend-smoke',
      edition: 'community',
      cloud_service_url: 'https://space.langbot.app',
      enable_marketplace: true,
      allow_modify_login_info: true,
      disable_models_service: false,
      limitation: {
        max_bots: -1,
        max_pipelines: -1,
        max_extensions: -1,
      },
      outbound_ips: [],
      wizard_status: 'completed',
      wizard_progress: null,
    });
  }

  if (path === '/api/v1/user/info') {
    return fulfillJson(route, {
      user: 'admin@example.com',
      account_type: 'local',
      has_password: true,
    });
  }

  if (path === '/api/v1/user/space-credits') {
    return fulfillJson(route, { credits: null });
  }

  if (path === '/api/v1/platform/adapters') {
    return fulfillJson(route, { adapters: mockAdapters() });
  }

  if (path === '/api/v1/platform/bots') {
    if (method === 'POST') {
      const bot = makeBot(state, parseJsonBody(route));
      state.bots = [
        ...state.bots.filter((item) => item.uuid !== bot.uuid),
        bot,
      ];
      return fulfillJson(route, { uuid: bot.uuid });
    }

    return fulfillJson(route, { bots: state.bots });
  }

  if (path === '/api/v1/broadcast/templates') {
    const botUuid = url.searchParams.get('bot_uuid');
    const connectorId = url.searchParams.get('connector_id');

    if (method === 'GET') {
      const templates = state.broadcastTemplates.filter(
        (template) =>
          template.bot_uuid === botUuid &&
          template.connector_id === connectorId,
      );
      return fulfillJson(route, templates);
    }

    if (method === 'POST') {
      const body = parseJsonBody(route);
      const content = String(body.content || '');
      const template: BroadcastTemplateMock = {
        id: Number(nextId(state, 'broadcast-template').split('-').pop()),
        bot_uuid: String(body.bot_uuid || ''),
        connector_id: String(body.connector_id || ''),
        name: String(body.name || ''),
        content,
        variables: extractTemplateVariables(content),
        enabled: body.enabled !== false,
        created_at: now(),
        updated_at: now(),
      };
      state.broadcastTemplates = [
        ...state.broadcastTemplates.filter((item) => item.id !== template.id),
        template,
      ];
      return fulfillJson(route, template);
    }
  }

  const templateDetailMatch = path.match(/^\/api\/v1\/broadcast\/templates\/(\d+)$/);
  if (templateDetailMatch) {
    const templateId = Number(templateDetailMatch[1]);
    const botUuid = url.searchParams.get('bot_uuid');
    const connectorId = url.searchParams.get('connector_id');

    if (method === 'PUT') {
      const body = parseJsonBody(route);
      const content = String(body.content || '');
      const existing = state.broadcastTemplates.find((item) => item.id === templateId);
      const template: BroadcastTemplateMock = {
        id: templateId,
        bot_uuid: String(body.bot_uuid || existing?.bot_uuid || ''),
        connector_id: String(body.connector_id || existing?.connector_id || ''),
        name: String(body.name || existing?.name || ''),
        content,
        variables: extractTemplateVariables(content),
        enabled: body.enabled !== false,
        created_at: existing?.created_at || now(),
        updated_at: now(),
      };
      state.broadcastTemplates = [
        ...state.broadcastTemplates.filter((item) => item.id !== templateId),
        template,
      ];
      return fulfillJson(route, template);
    }

    if (method === 'DELETE') {
      state.broadcastTemplates = state.broadcastTemplates.filter(
        (item) =>
          !(
            item.id === templateId &&
            item.bot_uuid === botUuid &&
            item.connector_id === connectorId
          ),
      );
      return fulfillJson(route, { deleted: true });
    }
  }

  if (path === '/api/v1/broadcast/templates/render' && method === 'POST') {
    const body = parseJsonBody(route);
    const templateId = Number(body.template_id || 0);
    const variables = (body.variables as Record<string, unknown> | undefined) || {};
    const template =
      templateId > 0
        ? state.broadcastTemplates.find((item) => item.id === templateId)
        : null;
    const content = template ? template.content : String(body.content || '');
    return fulfillJson(route, renderBroadcastTemplate(content, variables));
  }

  if (path === '/api/v1/broadcast/variable-profile') {
    if (method === 'GET') {
      return fulfillJson(route, state.broadcastVariableProfile);
    }

    if (method === 'PUT') {
      const body = parseJsonBody(route);
      const groupField = String(body.group_field || '').trim();
      const mappingRules = Array.isArray(body.mapping_rules)
        ? (body.mapping_rules as BroadcastVariableProfileMock['mapping_rules'])
        : [];
      const issues: string[] = [];
      const seenKeys = new Set<string>();

      if (!groupField) {
        issues.push('请填写分组字段');
      }

      mappingRules.forEach((rule, index) => {
        const row = index + 1;
        const sourceField = String(rule.source_field || '').trim();
        const variableKey = String(rule.variable_key || '').trim();
        if (sourceField && !variableKey) {
          issues.push(`第 ${row} 条规则缺少消息变量`);
        }
        if (!sourceField && variableKey) {
          issues.push(`第 ${row} 条规则缺少表格字段`);
        }
        if (
          (sourceField.includes('{{') || sourceField.includes('}}')) &&
          sourceField
        ) {
          issues.push(`请填写“${sourceField.replace(/[{}]/g, '')}”，不要填写“${sourceField}”`);
        }
        if (
          (variableKey.includes('{{') || variableKey.includes('}}')) &&
          variableKey
        ) {
          issues.push(`请填写“${sourceField || '消息变量'}”，不要填写“${variableKey}”`);
        }
        if (
          !['first', 'lines', 'unique_lines', 'commas', 'unique_commas'].includes(
            String(rule.merge_mode || ''),
          )
        ) {
          issues.push(`第 ${row} 条规则的多条数据处理方式无效`);
        }
        if (variableKey) {
          if (seenKeys.has(variableKey)) {
            issues.push(`消息变量“${variableKey}”重复`);
          } else {
            seenKeys.add(variableKey);
          }
        }
      });

      if (issues.length > 0) {
        const message =
          issues.some((item) => item.includes('缺少')) || issues.includes('请填写分组字段')
            ? '变量配置填写不完整，请检查后重试'
            : '变量配置填写有误，请按提示修改';
        return fulfillError(
          route,
          400,
          'BROADCAST_VARIABLE_PROFILE_INVALID',
          message,
          issues,
        );
      }

      state.broadcastVariableProfile = {
        group_field:
          typeof body.group_field === 'string' ? body.group_field : null,
        mapping_rules: Array.isArray(body.mapping_rules)
          ? (body.mapping_rules as BroadcastVariableProfileMock['mapping_rules'])
          : [],
      };
      return fulfillJson(route, state.broadcastVariableProfile);
    }
  }

  if (path === '/api/v1/broadcast/group-rules') {
    const botUuid = url.searchParams.get('bot_uuid');
    const connectorId = url.searchParams.get('connector_id');

    if (method === 'GET') {
      const rules = state.broadcastGroupRules
        .filter(
          (rule) =>
            rule.bot_uuid === botUuid && rule.connector_id === connectorId,
        )
        .sort((left, right) => right.priority - left.priority);
      return fulfillJson(route, rules);
    }

    if (method === 'POST') {
      const body = parseJsonBody(route);
      const rule: BroadcastGroupRuleMock = {
        id: Number(nextId(state, 'broadcast-group-rule').split('-').pop()),
        bot_uuid: String(body.bot_uuid || ''),
        connector_id: String(body.connector_id || ''),
        source_value: String(body.source_value || ''),
        match_type: (body.match_type as BroadcastGroupRuleMock['match_type']) || 'exact',
        match_expression: String(body.match_expression || ''),
        target_conversation_name: String(body.target_conversation_name || ''),
        priority: Number(body.priority || 0),
        enabled: body.enabled !== false,
        created_at: now(),
        updated_at: now(),
      };
      state.broadcastGroupRules = [
        ...state.broadcastGroupRules.filter((item) => item.id !== rule.id),
        rule,
      ];
      return fulfillJson(route, rule);
    }
  }

  const groupRuleDetailMatch = path.match(/^\/api\/v1\/broadcast\/group-rules\/(\d+)$/);
  if (groupRuleDetailMatch) {
    const ruleId = Number(groupRuleDetailMatch[1]);
    const botUuid = url.searchParams.get('bot_uuid');
    const connectorId = url.searchParams.get('connector_id');

    if (method === 'PUT') {
      const body = parseJsonBody(route);
      const existing = state.broadcastGroupRules.find((item) => item.id === ruleId);
      const rule: BroadcastGroupRuleMock = {
        id: ruleId,
        bot_uuid: String(body.bot_uuid || existing?.bot_uuid || ''),
        connector_id: String(body.connector_id || existing?.connector_id || ''),
        source_value: String(body.source_value || existing?.source_value || ''),
        match_type:
          (body.match_type as BroadcastGroupRuleMock['match_type']) ||
          existing?.match_type ||
          'exact',
        match_expression: String(
          body.match_expression || existing?.match_expression || '',
        ),
        target_conversation_name: String(
          body.target_conversation_name ||
            existing?.target_conversation_name ||
            '',
        ),
        priority: Number(body.priority ?? existing?.priority ?? 0),
        enabled: body.enabled !== false,
        created_at: existing?.created_at || now(),
        updated_at: now(),
      };
      state.broadcastGroupRules = [
        ...state.broadcastGroupRules.filter((item) => item.id !== ruleId),
        rule,
      ];
      return fulfillJson(route, rule);
    }

    if (method === 'DELETE') {
      state.broadcastGroupRules = state.broadcastGroupRules.filter(
        (item) =>
          !(
            item.id === ruleId &&
            item.bot_uuid === botUuid &&
            item.connector_id === connectorId
          ),
      );
      return fulfillJson(route, { deleted: true });
    }
  }

  if (path === '/api/v1/broadcast/group-rules/match' && method === 'POST') {
    const body = parseJsonBody(route);
    const botUuid = String(body.bot_uuid || '');
    const connectorId = String(body.connector_id || '');
    const sourceValue = String(body.source_value || '');
    const matchedRule =
      state.broadcastGroupRules
        .filter(
          (rule) =>
            rule.bot_uuid === botUuid &&
            rule.connector_id === connectorId &&
            matchBroadcastRule(rule, sourceValue),
        )
        .sort((left, right) => right.priority - left.priority)[0] || null;

    return fulfillJson(route, {
      matched: Boolean(matchedRule),
      rule_id: matchedRule?.id || null,
      target_conversation_name: matchedRule?.target_conversation_name || null,
      match_type: matchedRule?.match_type || null,
    });
  }

  if (path === '/api/v1/broadcast/group-names') {
    const botUuid = url.searchParams.get('bot_uuid');
    const connectorId = url.searchParams.get('connector_id');

    if (method === 'GET') {
      const names = state.broadcastGroupNames.filter(
        (item) =>
          item.bot_uuid === botUuid && item.connector_id === connectorId,
      );
      return fulfillJson(route, names);
    }

    if (method === 'POST') {
      const body = parseJsonBody(route);
      const bot_uuid = String(body.bot_uuid || '');
      const connector_id = String(body.connector_id || '');
      const rawNames = Array.isArray(body.names)
        ? body.names
        : body.name
          ? [body.name]
          : [];
      const uniqueNames = Array.from(
        new Set(
          rawNames
            .map((item) => String(item).trim())
            .filter(Boolean),
        ),
      );
      const created = uniqueNames.map((name) => ({
        id: Number(nextId(state, 'broadcast-group-name').split('-').pop()),
        bot_uuid,
        connector_id,
        name,
        created_at: now(),
        updated_at: now(),
      }));
      state.broadcastGroupNames = [
        ...state.broadcastGroupNames,
        ...created,
      ];
      return fulfillJson(route, { group_names: created });
    }
  }

  const groupNameDetailMatch = path.match(/^\/api\/v1\/broadcast\/group-names\/(\d+)$/);
  if (groupNameDetailMatch && method === 'DELETE') {
    const groupNameId = Number(groupNameDetailMatch[1]);
    const botUuid = url.searchParams.get('bot_uuid');
    const connectorId = url.searchParams.get('connector_id');
    state.broadcastGroupNames = state.broadcastGroupNames.filter(
      (item) =>
        !(
          item.id === groupNameId &&
          item.bot_uuid === botUuid &&
          item.connector_id === connectorId
        ),
    );
    return fulfillJson(route, { deleted: true });
  }

  const botLogsMatch = path.match(/^\/api\/v1\/platform\/bots\/([^/]+)\/logs$/);
  if (botLogsMatch) {
    return fulfillJson(route, { logs: [], total: 0 });
  }

  const botMatch = path.match(/^\/api\/v1\/platform\/bots\/([^/]+)$/);
  if (botMatch) {
    const botId = decodeURIComponent(botMatch[1]);

    if (method === 'PUT') {
      const bot = makeBot(state, parseJsonBody(route), botId);
      state.bots = [...state.bots.filter((item) => item.uuid !== botId), bot];
      return fulfillJson(route, {});
    }

    if (method === 'DELETE') {
      state.bots = state.bots.filter((item) => item.uuid !== botId);
      return fulfillJson(route, {});
    }

    const bot = state.bots.find((item) => item.uuid === botId);
    return fulfillJson(route, {
      bot: bot || makeBot(state, { name: botId }, botId),
    });
  }

  if (path === '/api/v1/pipelines/_/metadata') {
    return fulfillJson(route, { configs: [] });
  }

  if (path === '/api/v1/pipelines') {
    if (method === 'POST') {
      const pipeline = makePipeline(state, parseJsonBody(route));
      state.pipelines = [
        ...state.pipelines.filter((item) => item.uuid !== pipeline.uuid),
        pipeline,
      ];
      return fulfillJson(route, { uuid: pipeline.uuid });
    }

    return fulfillJson(route, { pipelines: state.pipelines });
  }

  const pipelineMatch = path.match(/^\/api\/v1\/pipelines\/([^/]+)$/);
  if (pipelineMatch) {
    const pipelineId = decodeURIComponent(pipelineMatch[1]);

    if (method === 'PUT') {
      const pipeline = makePipeline(state, parseJsonBody(route), pipelineId);
      state.pipelines = [
        ...state.pipelines.filter((item) => item.uuid !== pipelineId),
        pipeline,
      ];
      return fulfillJson(route, {});
    }

    if (method === 'DELETE') {
      state.pipelines = state.pipelines.filter(
        (item) => item.uuid !== pipelineId,
      );
      return fulfillJson(route, {});
    }

    const pipeline = state.pipelines.find((item) => item.uuid === pipelineId);
    return fulfillJson(route, {
      pipeline:
        pipeline || makePipeline(state, { name: pipelineId }, pipelineId),
    });
  }

  const pipelineExtensionsMatch = path.match(
    /^\/api\/v1\/pipelines\/([^/]+)\/extensions$/,
  );
  if (pipelineExtensionsMatch) {
    return fulfillJson(route, {
      enable_all_plugins: true,
      enable_all_mcp_servers: true,
      enable_all_skills: true,
      bound_plugins: [],
      available_plugins: [],
      bound_mcp_servers: [],
      available_mcp_servers: state.mcpServers,
      bound_skills: [],
      available_skills: state.skills,
    });
  }

  if (path === '/api/v1/knowledge/bases') {
    if (method === 'POST') {
      const base = makeKnowledgeBase(state, parseJsonBody(route));
      state.knowledgeBases = [
        ...state.knowledgeBases.filter((item) => item.uuid !== base.uuid),
        base,
      ];
      return fulfillJson(route, { uuid: base.uuid });
    }

    return fulfillJson(route, { bases: state.knowledgeBases });
  }

  const knowledgeBaseFilesMatch = path.match(
    /^\/api\/v1\/knowledge\/bases\/([^/]+)\/files$/,
  );
  if (knowledgeBaseFilesMatch) {
    return fulfillJson(route, { files: [] });
  }

  const knowledgeBaseMatch = path.match(
    /^\/api\/v1\/knowledge\/bases\/([^/]+)$/,
  );
  if (knowledgeBaseMatch) {
    const baseId = decodeURIComponent(knowledgeBaseMatch[1]);

    if (method === 'PUT') {
      const base = makeKnowledgeBase(state, parseJsonBody(route), baseId);
      state.knowledgeBases = [
        ...state.knowledgeBases.filter((item) => item.uuid !== baseId),
        base,
      ];
      return fulfillJson(route, { uuid: base.uuid });
    }

    if (method === 'DELETE') {
      state.knowledgeBases = state.knowledgeBases.filter(
        (item) => item.uuid !== baseId,
      );
      return fulfillJson(route, {});
    }

    const base = state.knowledgeBases.find((item) => item.uuid === baseId);
    return fulfillJson(route, {
      base: base || makeKnowledgeBase(state, { name: baseId }, baseId),
    });
  }

  if (path === '/api/v1/knowledge/engines') {
    return fulfillJson(route, { engines: [knowledgeEngine()] });
  }

  if (path === '/api/v1/knowledge/migration/status') {
    return fulfillJson(route, {
      needed: false,
      internal_kb_count: 0,
      external_kb_count: 0,
    });
  }

  if (path === '/api/v1/plugins') {
    return fulfillJson(route, { plugins: [] });
  }

  if (path === '/api/v1/extensions') {
    return fulfillJson(route, { extensions: [] });
  }

  if (path === '/api/v1/mcp/servers') {
    if (method === 'POST') {
      const server = makeMCPServer(parseJsonBody(route));
      state.mcpServers = [
        ...state.mcpServers.filter((item) => item.name !== server.name),
        server,
      ];
      return fulfillJson(route, { task_id: nextId(state, 'task') });
    }

    return fulfillJson(route, { servers: state.mcpServers });
  }

  const mcpTestMatch = path.match(/^\/api\/v1\/mcp\/servers\/([^/]+)\/test$/);
  if (mcpTestMatch) {
    return fulfillJson(route, {
      runtime_info: {
        status: 'connected',
        tool_count: 0,
        tools: [],
      },
    });
  }

  const mcpServerMatch = path.match(/^\/api\/v1\/mcp\/servers\/([^/]+)$/);
  if (mcpServerMatch) {
    const serverName = decodeURIComponent(mcpServerMatch[1]);

    if (method === 'PUT') {
      const existing = state.mcpServers.find(
        (item) => item.name === serverName,
      );
      const server = makeMCPServer({
        ...(existing || {}),
        ...parseJsonBody(route),
        name: serverName,
      });
      state.mcpServers = [
        ...state.mcpServers.filter((item) => item.name !== serverName),
        server,
      ];
      return fulfillJson(route, { task_id: nextId(state, 'task') });
    }

    if (method === 'DELETE') {
      state.mcpServers = state.mcpServers.filter(
        (item) => item.name !== serverName,
      );
      return fulfillJson(route, { task_id: nextId(state, 'task') });
    }

    const server = state.mcpServers.find((item) => item.name === serverName);
    return fulfillJson(route, {
      server: server || makeMCPServer({ name: serverName }),
    });
  }

  if (path === '/api/v1/skills') {
    if (method === 'POST') {
      const skill = makeSkill(
        JSON.parse(request.postData() || '{}') as JsonRecord,
      );
      state.skills = [
        ...state.skills.filter((item) => item.name !== skill.name),
        skill,
      ];
      return fulfillJson(route, { skill });
    }

    return fulfillJson(route, { skills: state.skills });
  }

  const skillFileMatch = path.match(
    /^\/api\/v1\/skills\/([^/]+)\/files\/(.+)$/,
  );
  if (skillFileMatch) {
    const skillName = decodeURIComponent(skillFileMatch[1]);
    const filePath = decodeURIComponent(skillFileMatch[2]);
    const skill = state.skills.find((item) => item.name === skillName);
    return fulfillJson(route, {
      skill: { name: skillName },
      path: filePath,
      content: skill?.instructions || '',
    });
  }

  const skillFilesMatch = path.match(/^\/api\/v1\/skills\/([^/]+)\/files$/);
  if (skillFilesMatch) {
    const skillName = decodeURIComponent(skillFilesMatch[1]);
    return fulfillJson(route, {
      skill: { name: skillName },
      base_path: '.',
      entries: [
        {
          path: 'SKILL.md',
          name: 'SKILL.md',
          is_dir: false,
          size: null,
        },
      ],
      truncated: false,
    });
  }

  const skillMatch = path.match(/^\/api\/v1\/skills\/([^/]+)$/);
  if (skillMatch) {
    const skillName = decodeURIComponent(skillMatch[1]);
    if (method === 'PUT') {
      const skill = makeSkill({
        ...parseJsonBody(route),
        name: skillName,
      });
      state.skills = [
        ...state.skills.filter((item) => item.name !== skillName),
        skill,
      ];
      return fulfillJson(route, { skill });
    }

    if (method === 'DELETE') {
      state.skills = state.skills.filter((item) => item.name !== skillName);
      return fulfillJson(route, {});
    }

    const skill = state.skills.find((item) => item.name === skillName) || {
      name: skillName,
      display_name: '',
      description: '',
      instructions: '',
      package_root: '',
      updated_at: new Date().toISOString(),
    };
    return fulfillJson(route, { skill });
  }

  if (path === '/api/v1/system/status/plugin-system') {
    return fulfillJson(route, {
      is_enable: true,
      is_connected: true,
      plugin_connector_error: '',
    });
  }

  if (path === '/api/v1/plugins/debug-info') {
    return fulfillJson(route, {
      debug_url: 'ws://127.0.0.1:5300/plugin/debug',
      plugin_debug_key: 'test-debug-key',
    });
  }

  if (path === '/api/v1/box/status') {
    return fulfillJson(route, {
      available: true,
      enabled: true,
      profile: 'playwright',
      recent_error_count: 0,
      active_sessions: 0,
      managed_processes: 0,
      session_ttl_sec: 3600,
      backend: {
        name: 'playwright',
        available: true,
      },
    });
  }

  if (path === '/api/v1/box/sessions') {
    return fulfillJson(route, []);
  }

  if (path === '/api/v1/monitoring/data') {
    return fulfillJson(route, emptyMonitoringData());
  }

  if (path === '/api/v1/monitoring/overview') {
    return fulfillJson(route, emptyMonitoringData().overview);
  }

  if (path === '/api/v1/monitoring/token-statistics') {
    return fulfillJson(route, emptyTokenStatistics());
  }

  if (path === '/api/v1/monitoring/feedback/stats') {
    return fulfillJson(route, {
      total_feedback: 0,
      total_likes: 0,
      total_dislikes: 0,
      satisfaction_rate: 0,
    });
  }

  if (path === '/api/v1/monitoring/feedback') {
    return fulfillJson(route, { feedback: [], total: 0 });
  }

  if (path === '/api/v1/survey/pending') {
    return fulfillJson(route, { survey: null });
  }

  if (path === '/api/v1/system/tasks') {
    return fulfillJson(route, { tasks: [] });
  }

  if (path === '/api/v1/local-connectors/wxwork-local/status') {
    return fulfillJson(route, {
      connector: {
        connector_id: 'wxwork-local',
        name: 'WeCom Local Connector',
        description: 'Mocked WeCom connector',
        managed_by: 'builtin',
        expected_tool_count: 5,
        status: 'not_configured',
        tool_count: 0,
        updated_at: Date.now(),
        worker: {
          owned: false,
          port: 5681,
          started_at: null,
        },
        monitor: {
          enabled: false,
          owned: false,
          running_status: 'stopped',
          warmup_completed: false,
          outbox_pending: 0,
        },
      },
    });
  }

  if (path === '/api/v1/database-mode/conversations') {
    return fulfillJson(route, {
      conversations: [],
      total: 0,
      page: 1,
      page_size: 100,
    });
  }

  if (
    path === '/api/v1/marketplace/plugins' ||
    path === '/api/v1/marketplace/plugins/search' ||
    path === '/api/v1/marketplace/extensions/search' ||
    path === '/api/v1/marketplace/mcps/search' ||
    path === '/api/v1/marketplace/skills/search'
  ) {
    return fulfillJson(route, { plugins: [], total: 0 });
  }

  if (path === '/api/v1/marketplace/tags') {
    return fulfillJson(route, { tags: [] });
  }

  if (path === '/api/v1/marketplace/recommendation-lists') {
    return fulfillJson(route, { lists: [] });
  }

  if (path === '/api/v1/dist/info/releases') {
    return fulfillJson(route, []);
  }

  if (path === '/api/v1/dist/info/repo') {
    return fulfillJson(route, {
      repo: {
        stargazers_count: 0,
        forks_count: 0,
        open_issues_count: 0,
      },
      contributors: [],
    });
  }

  await fulfillJson(route, {});
}

async function handleCloudApi(route: Route) {
  const path = routePath(route);

  if (
    path === '/api/v1/marketplace/plugins' ||
    path === '/api/v1/marketplace/plugins/search' ||
    path === '/api/v1/marketplace/extensions/search' ||
    path === '/api/v1/marketplace/mcps/search' ||
    path === '/api/v1/marketplace/skills/search'
  ) {
    return fulfillJson(route, { plugins: [], total: 0 });
  }

  if (path === '/api/v1/marketplace/tags') {
    return fulfillJson(route, { tags: [] });
  }

  if (path === '/api/v1/marketplace/recommendation-lists') {
    return fulfillJson(route, { lists: [] });
  }

  if (path === '/api/v1/dist/info/releases') {
    return fulfillJson(route, []);
  }

  if (path === '/api/v1/dist/info/repo') {
    return fulfillJson(route, {
      repo: {
        stargazers_count: 0,
        forks_count: 0,
        open_issues_count: 0,
      },
      contributors: [],
    });
  }

  await fulfillJson(route, {});
}

export async function installLangBotApiMocks(
  page: Page,
  options: { authenticated?: boolean; storage?: JsonRecord } = {},
) {
  const { authenticated = false, storage = {} } = options;
  const broadcastSeed = seedBroadcastState();
  const state: LangBotApiMockState = {
    bots: [],
    broadcastGroupNames: broadcastSeed.broadcastGroupNames,
    broadcastGroupRules: broadcastSeed.broadcastGroupRules,
    broadcastTemplates: broadcastSeed.broadcastTemplates,
    broadcastVariableProfile: broadcastSeed.broadcastVariableProfile,
    counters: {
      'broadcast-template': broadcastSeed.broadcastTemplates.length,
      'broadcast-group-rule': broadcastSeed.broadcastGroupRules.length,
      'broadcast-group-name': broadcastSeed.broadcastGroupNames.length,
    },
    knowledgeBases: [],
    mcpServers: [],
    pipelines: [],
    skills: [],
  };

  await page.addInitScript(
    ({ authenticated, storage }) => {
      localStorage.setItem('langbot_language', 'en-US');
      localStorage.setItem('extensions_group_by_type', 'false');

      if (authenticated) {
        localStorage.setItem('token', 'playwright-token');
        localStorage.setItem('userEmail', 'admin@example.com');
      } else {
        localStorage.removeItem('token');
        localStorage.removeItem('userEmail');
      }

      if (!storage.langbot_language) {
        localStorage.setItem('langbot_language', 'en-US');
      }

      for (const [key, value] of Object.entries(storage)) {
        localStorage.setItem(key, String(value));
      }
    },
    { authenticated, storage },
  );

  await page.route('**/api/v1/**', (route) => handleBackendApi(route, state));
  await page.route('https://space.langbot.app/**', handleCloudApi);
}
