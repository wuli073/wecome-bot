import { BaseHttpClient, RequestConfig } from './BaseHttpClient';
import axios from 'axios';
import {
  ApiRespProviderRequesters,
  ApiRespProviderRequester,
  ApiRespProviderLLMModels,
  ApiRespProviderLLMModel,
  LLMModel,
  ApiRespPipelines,
  Pipeline,
  ApiRespPlatformAdapters,
  ApiRespPlatformAdapter,
  ApiRespPlatformBots,
  ApiRespPlatformBot,
  Bot,
  ApiRespPlugins,
  ApiRespPlugin,
  ApiRespPluginConfig,
  ApiRespExtensions,
  AsyncTaskCreatedResp,
  ApiRespSystemInfo,
  ApiRespAsyncTasks,
  GetPipelineResponseData,
  GetPipelineMetadataResponseData,
  AsyncTask,
  ApiRespWebChatMessages,
  ApiRespKnowledgeBases,
  ApiRespKnowledgeBase,
  KnowledgeBase,
  ApiRespKnowledgeBaseFiles,
  ApiRespKnowledgeBaseRetrieve,
  ApiRespProviderEmbeddingModels,
  ApiRespProviderEmbeddingModel,
  EmbeddingModel,
  ApiRespProviderRerankModels,
  ApiRespProviderRerankModel,
  RerankModel,
  ApiRespPluginSystemStatus,
  ApiRespBoxStatus,
  BoxSessionInfo,
  ApiRespMCPServers,
  ApiRespMCPServer,
  MCPServer,
  ApiRespLocalConnectors,
  ApiRespLocalConnector,
  ApiRespLocalConnectorJob,
  ApiRespLocalConnectorMonitor,
  ApiRespModelProviders,
  ApiRespModelProvider,
  ApiRespScannedProviderModels,
  ModelProvider,
  ApiRespKnowledgeEngines,
  ApiRespParsers,
  RagMigrationStatusResp,
  ApiRespTools,
  ApiRespToolDetail,
  Skill,
  ApiRespSkills,
  ApiRespSkill,
  ApiRespDatabaseModeConversation,
  ApiRespDatabaseModeConversations,
  ApiRespDatabaseModeMessage,
  ApiRespDatabaseModeMessages,
  ApiBroadcastGroupMatchResult,
  ApiBroadcastGroupName,
  ApiBroadcastGroupNameCreateResult,
  ApiBroadcastGroupNamesResponse,
  ApiBroadcastGroupNameSyncResult,
  ApiBroadcastGroupRule,
  ApiBroadcastDraft,
  ApiBroadcastDraftStatus,
  ApiBroadcastDraftStatusUpdateResult,
  ApiBroadcastExecutionAttempt,
  ApiBroadcastExecutionBatch,
  ApiBroadcastExecutionEvidence,
  ApiBroadcastExecutionTask,
  ApiBroadcastBulkAssignResult,
  ApiBroadcastImportGroupRowsResponse,
  ApiBroadcastImportGroupsResponse,
  ApiBroadcastImportGroupRuleCandidatesResponse,
  ApiBroadcastImportBatch,
  ApiBroadcastImportDetail,
  ApiBroadcastImportDraftGenerationResult,
  ApiBroadcastImportGroupTemplateAssignment,
  ApiBroadcastScope,
  ApiBroadcastTemplate,
  ApiBroadcastTemplateRenderResult,
  ApiBroadcastVariableProfile,
} from '@/app/infra/entities/api';
import { Plugin } from '@/app/infra/entities/plugin';
import type { PluginLogEntry } from '@/app/infra/entities/plugin';
import type { I18nObject } from '@/app/infra/entities/common';
import { GetBotLogsRequest } from '@/app/infra/http/requestParam/bots/GetBotLogsRequest';
import { GetBotLogsResponse } from '@/app/infra/http/requestParam/bots/GetBotLogsResponse';

/**
 * 后端服务客户端
 * 负责与后端 API 的所有交互
 */
export class BackendClient extends BaseHttpClient {
  constructor(baseURL: string) {
    super(baseURL, false);
  }

  private toSearchParams(
    params: Record<string, string | number | boolean | null | undefined>,
  ): string {
    const searchParams = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value === undefined || value === null) {
        return;
      }
      searchParams.set(key, String(value));
    });
    return searchParams.toString();
  }

  private async requestBroadcast<T>(config: RequestConfig): Promise<T> {
    const token =
      typeof window !== 'undefined' && !this.disableToken
        ? this.getSessionSync()
        : null;
    const headers = {
      ...this.instance.defaults.headers.common,
      ...(config.headers ?? {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    };

    if (
      typeof FormData !== 'undefined' &&
      config.data instanceof FormData
    ) {
      delete headers['Content-Type'];
    }
    try {
      const response = await axios.request<{
        code: number;
        message: string;
        data: T;
        timestamp: number;
      }>({
        baseURL: this.instance.defaults.baseURL,
        timeout: this.instance.defaults.timeout,
        ...config,
        headers,
      });
      return response.data.data;
    } catch (error) {
      if (axios.isAxiosError(error) && error.response) {
        const responseData = error.response.data as
          | {
              code?: unknown;
              msg?: unknown;
              message?: unknown;
              details?: unknown;
            }
          | undefined;
        throw {
          code: responseData?.code ?? error.response.status,
          msg: String(responseData?.msg ?? error.message),
          data: {
            message:
              typeof responseData?.message === 'string' &&
              responseData.message.trim()
                ? responseData.message
                : String(responseData?.msg ?? error.message),
            details: responseData?.details ?? [],
          },
        };
      }
      throw error;
    }
  }

  // ============ Provider API ============
  public getProviderRequesters(
    model_type?: string,
  ): Promise<ApiRespProviderRequesters> {
    return this.get('/api/v1/provider/requesters', { type: model_type });
  }

  public getProviderRequester(name: string): Promise<ApiRespProviderRequester> {
    return this.get(`/api/v1/provider/requesters/${name}`);
  }

  public getProviderRequesterIconURL(name: string): string {
    if (this.instance.defaults.baseURL === '/') {
      const url = window.location.href;
      const baseURL = url.split('/').slice(0, 3).join('/');
      return `${baseURL}/api/v1/provider/requesters/${name}/icon`;
    }
    return (
      this.instance.defaults.baseURL +
      `/api/v1/provider/requesters/${name}/icon`
    );
  }

  // ============ Model Providers ============
  public getModelProviders(): Promise<ApiRespModelProviders> {
    return this.get('/api/v1/provider/providers');
  }

  public getModelProvider(uuid: string): Promise<ApiRespModelProvider> {
    return this.get(`/api/v1/provider/providers/${uuid}`);
  }

  public createModelProvider(
    provider: Omit<ModelProvider, 'uuid'>,
  ): Promise<{ uuid: string }> {
    return this.post('/api/v1/provider/providers', provider);
  }

  public updateModelProvider(
    uuid: string,
    provider: Partial<ModelProvider>,
  ): Promise<object> {
    return this.put(`/api/v1/provider/providers/${uuid}`, provider);
  }

  public deleteModelProvider(uuid: string): Promise<object> {
    return this.delete(`/api/v1/provider/providers/${uuid}`);
  }

  public scanProviderModels(
    uuid: string,
    modelType?: 'llm' | 'embedding' | 'rerank',
  ): Promise<ApiRespScannedProviderModels> {
    const params = modelType ? { type: modelType } : {};
    return this.get(`/api/v1/provider/providers/${uuid}/scan-models`, params);
  }

  // ============ Provider Model LLM ============
  public getProviderLLMModels(
    providerUuid?: string,
  ): Promise<ApiRespProviderLLMModels> {
    const params = providerUuid ? { provider_uuid: providerUuid } : {};
    return this.get('/api/v1/provider/models/llm', params);
  }

  public getProviderLLMModel(uuid: string): Promise<ApiRespProviderLLMModel> {
    return this.get(`/api/v1/provider/models/llm/${uuid}`);
  }

  public createProviderLLMModel(model: LLMModel): Promise<object> {
    return this.post('/api/v1/provider/models/llm', model);
  }

  public deleteProviderLLMModel(uuid: string): Promise<object> {
    return this.delete(`/api/v1/provider/models/llm/${uuid}`);
  }

  public updateProviderLLMModel(
    uuid: string,
    model: LLMModel,
  ): Promise<object> {
    return this.put(`/api/v1/provider/models/llm/${uuid}`, model);
  }

  public testLLMModel(uuid: string, model: LLMModel): Promise<object> {
    return this.post(`/api/v1/provider/models/llm/${uuid}/test`, model);
  }

  // ============ Provider Model Embedding ============
  public getProviderEmbeddingModels(
    providerUuid?: string,
  ): Promise<ApiRespProviderEmbeddingModels> {
    const params = providerUuid ? { provider_uuid: providerUuid } : {};
    return this.get('/api/v1/provider/models/embedding', params);
  }

  public getProviderEmbeddingModel(
    uuid: string,
  ): Promise<ApiRespProviderEmbeddingModel> {
    return this.get(`/api/v1/provider/models/embedding/${uuid}`);
  }

  public createProviderEmbeddingModel(model: EmbeddingModel): Promise<object> {
    return this.post('/api/v1/provider/models/embedding', model);
  }

  public deleteProviderEmbeddingModel(uuid: string): Promise<object> {
    return this.delete(`/api/v1/provider/models/embedding/${uuid}`);
  }

  public updateProviderEmbeddingModel(
    uuid: string,
    model: EmbeddingModel,
  ): Promise<object> {
    return this.put(`/api/v1/provider/models/embedding/${uuid}`, model);
  }

  public testEmbeddingModel(
    uuid: string,
    model: EmbeddingModel,
  ): Promise<object> {
    return this.post(`/api/v1/provider/models/embedding/${uuid}/test`, model);
  }

  // ============ Provider Model Rerank ============
  public getProviderRerankModels(
    providerUuid?: string,
  ): Promise<ApiRespProviderRerankModels> {
    const params = providerUuid ? { provider_uuid: providerUuid } : {};
    return this.get('/api/v1/provider/models/rerank', params);
  }

  public getProviderRerankModel(
    uuid: string,
  ): Promise<ApiRespProviderRerankModel> {
    return this.get(`/api/v1/provider/models/rerank/${uuid}`);
  }

  public createProviderRerankModel(model: RerankModel): Promise<object> {
    return this.post('/api/v1/provider/models/rerank', model);
  }

  public deleteProviderRerankModel(uuid: string): Promise<object> {
    return this.delete(`/api/v1/provider/models/rerank/${uuid}`);
  }

  public updateProviderRerankModel(
    uuid: string,
    model: RerankModel,
  ): Promise<object> {
    return this.put(`/api/v1/provider/models/rerank/${uuid}`, model);
  }

  public testRerankModel(uuid: string, model: RerankModel): Promise<object> {
    return this.post(`/api/v1/provider/models/rerank/${uuid}/test`, model);
  }

  // ============ Pipeline API ============
  public getGeneralPipelineMetadata(): Promise<GetPipelineMetadataResponseData> {
    // as designed, this method will be deprecated, and only for developer to check the prefered config schema
    return this.get('/api/v1/pipelines/_/metadata');
  }

  public getPipelines(
    sortBy?: string,
    sortOrder?: string,
  ): Promise<ApiRespPipelines> {
    const params = new URLSearchParams();
    if (sortBy) params.append('sort_by', sortBy);
    if (sortOrder) params.append('sort_order', sortOrder);
    const queryString = params.toString();
    return this.get(`/api/v1/pipelines${queryString ? `?${queryString}` : ''}`);
  }

  public getPipeline(uuid: string): Promise<GetPipelineResponseData> {
    return this.get(`/api/v1/pipelines/${uuid}`);
  }

  public createPipeline(pipeline: Pipeline): Promise<{
    uuid: string;
  }> {
    return this.post('/api/v1/pipelines', pipeline);
  }

  public updatePipeline(uuid: string, pipeline: Pipeline): Promise<object> {
    return this.put(`/api/v1/pipelines/${uuid}`, pipeline);
  }

  public deletePipeline(uuid: string): Promise<object> {
    return this.delete(`/api/v1/pipelines/${uuid}`);
  }

  public copyPipeline(uuid: string): Promise<{ uuid: string }> {
    return this.post(`/api/v1/pipelines/${uuid}/copy`);
  }

  public getPipelineExtensions(uuid: string): Promise<{
    enable_all_plugins: boolean;
    enable_all_mcp_servers: boolean;
    enable_all_skills: boolean;
    bound_plugins: Array<{ author: string; name: string }>;
    available_plugins: Plugin[];
    bound_mcp_servers: string[];
    available_mcp_servers: MCPServer[];
    bound_skills: string[];
    available_skills: Skill[];
  }> {
    return this.get(`/api/v1/pipelines/${uuid}/extensions`);
  }

  public updatePipelineExtensions(
    uuid: string,
    bound_plugins: Array<{ author: string; name: string }>,
    bound_mcp_servers: string[],
    enable_all_plugins: boolean = true,
    enable_all_mcp_servers: boolean = true,
    bound_skills: string[] = [],
    enable_all_skills: boolean = true,
  ): Promise<object> {
    return this.put(`/api/v1/pipelines/${uuid}/extensions`, {
      bound_plugins,
      bound_mcp_servers,
      enable_all_plugins,
      enable_all_mcp_servers,
      bound_skills,
      enable_all_skills,
    });
  }

  // ============ WebSocket Chat API ============
  public getWebSocketHistoryMessages(
    pipelineId: string,
    sessionType: string,
  ): Promise<ApiRespWebChatMessages> {
    return this.get(
      `/api/v1/pipelines/${pipelineId}/ws/messages/${sessionType}`,
    );
  }

  public async uploadWebSocketImage(
    pipelineId: string,
    imageFile: File,
  ): Promise<{ file_key: string }> {
    const formData = new FormData();
    formData.append('file', imageFile);

    return this.postFile(`/api/v1/files/images`, formData);
  }

  public resetWebSocketSession(
    pipelineId: string,
    sessionType: string,
  ): Promise<{ message: string }> {
    return this.post(`/api/v1/pipelines/${pipelineId}/ws/reset/${sessionType}`);
  }

  public getWebSocketConnections(pipelineId: string): Promise<{
    stats: {
      total_connections: number;
      pipelines: number;
      connections_by_pipeline: Record<string, number>;
      connections_by_session_type: Record<string, number>;
    };
    connections: Array<{
      connection_id: string;
      session_type: string;
      created_at: string;
      last_active: string;
      is_active: boolean;
    }>;
  }> {
    return this.get(`/api/v1/pipelines/${pipelineId}/ws/connections`);
  }

  public broadcastWebSocketMessage(
    pipelineId: string,
    message: string,
  ): Promise<{ message: string }> {
    return this.post(`/api/v1/pipelines/${pipelineId}/ws/broadcast`, {
      message,
    });
  }

  // ============ Platform API ============
  public getAdapters(): Promise<ApiRespPlatformAdapters> {
    return this.get('/api/v1/platform/adapters');
  }

  public getAdapter(name: string): Promise<ApiRespPlatformAdapter> {
    return this.get(`/api/v1/platform/adapters/${name}`);
  }

  public getAdapterIconURL(name: string): string {
    if (this.instance.defaults.baseURL === '/') {
      // 获取用户访问的URL
      const url = window.location.href;
      const baseURL = url.split('/').slice(0, 3).join('/');
      return `${baseURL}/api/v1/platform/adapters/${name}/icon`;
    }
    return (
      this.instance.defaults.baseURL + `/api/v1/platform/adapters/${name}/icon`
    );
  }

  // ============ Platform Bots ============
  public getBots(): Promise<ApiRespPlatformBots> {
    return this.get('/api/v1/platform/bots');
  }

  public getBot(uuid: string): Promise<ApiRespPlatformBot> {
    return this.get(`/api/v1/platform/bots/${uuid}`);
  }

  public createBot(bot: Bot): Promise<{ uuid: string }> {
    return this.post('/api/v1/platform/bots', bot);
  }

  public updateBot(uuid: string, bot: Bot): Promise<object> {
    return this.put(`/api/v1/platform/bots/${uuid}`, bot);
  }

  public deleteBot(uuid: string): Promise<object> {
    return this.delete(`/api/v1/platform/bots/${uuid}`);
  }

  public getBotLogs(
    botId: string,
    request: GetBotLogsRequest,
  ): Promise<GetBotLogsResponse> {
    return this.post(`/api/v1/platform/bots/${botId}/logs`, request);
  }

  public getBotSessions(
    botId: string,
    limit: number = 100,
    offset: number = 0,
  ): Promise<{
    sessions: Array<{
      session_id: string;
      bot_id: string;
      bot_name: string;
      pipeline_id: string;
      pipeline_name: string;
      message_count: number;
      start_time: string;
      last_activity: string;
      is_active: boolean;
      platform: string | null;
      user_id: string | null;
      user_name: string | null;
    }>;
    total: number;
  }> {
    const queryParams = new URLSearchParams();
    queryParams.append('botId', botId);
    queryParams.append('limit', limit.toString());
    queryParams.append('offset', offset.toString());
    return this.get(`/api/v1/monitoring/sessions?${queryParams.toString()}`);
  }

  public getSessionMessages(
    sessionId: string,
    limit: number = 200,
    offset: number = 0,
  ): Promise<{
    messages: Array<{
      id: string;
      timestamp: string;
      bot_id: string;
      bot_name: string;
      pipeline_id: string;
      pipeline_name: string;
      message_content: string;
      session_id: string;
      status: string;
      level: string;
      platform: string | null;
      user_id: string | null;
      user_name: string | null;
      runner_name: string | null;
      variables: string | null;
      role: string | null;
    }>;
    total: number;
  }> {
    const queryParams = new URLSearchParams();
    queryParams.append('sessionId', sessionId);
    queryParams.append('limit', limit.toString());
    queryParams.append('offset', offset.toString());
    return this.get(`/api/v1/monitoring/messages?${queryParams.toString()}`);
  }

  // ============ File management API ============
  public uploadDocumentFile(file: File): Promise<{ file_id: string }> {
    const formData = new FormData();
    formData.append('file', file);

    return this.request<{ file_id: string }>({
      method: 'post',
      url: '/api/v1/files/documents',
      data: formData,
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
  }

  // ============ Knowledge Base API ============
  public getKnowledgeBases(): Promise<ApiRespKnowledgeBases> {
    return this.get('/api/v1/knowledge/bases');
  }

  public getKnowledgeBase(uuid: string): Promise<ApiRespKnowledgeBase> {
    return this.get(`/api/v1/knowledge/bases/${uuid}`);
  }

  public createKnowledgeBase(base: KnowledgeBase): Promise<{ uuid: string }> {
    return this.post('/api/v1/knowledge/bases', base);
  }

  public updateKnowledgeBase(
    uuid: string,
    base: KnowledgeBase,
  ): Promise<{ uuid: string }> {
    return this.put(`/api/v1/knowledge/bases/${uuid}`, base);
  }

  public uploadKnowledgeBaseFile(
    uuid: string,
    file_id: string,
    parserPluginId?: string,
  ): Promise<object> {
    return this.post(`/api/v1/knowledge/bases/${uuid}/files`, {
      file_id,
      parser_plugin_id: parserPluginId,
    });
  }

  public getKnowledgeBaseFiles(
    uuid: string,
  ): Promise<ApiRespKnowledgeBaseFiles> {
    return this.get(`/api/v1/knowledge/bases/${uuid}/files`);
  }

  public deleteKnowledgeBaseFile(
    uuid: string,
    file_id: string,
  ): Promise<object> {
    return this.delete(`/api/v1/knowledge/bases/${uuid}/files/${file_id}`);
  }

  public deleteKnowledgeBase(uuid: string): Promise<object> {
    return this.delete(`/api/v1/knowledge/bases/${uuid}`);
  }

  public retrieveKnowledgeBase(
    uuid: string,
    query: string,
    retrievalSettings?: Record<string, unknown>,
  ): Promise<ApiRespKnowledgeBaseRetrieve> {
    return this.post(`/api/v1/knowledge/bases/${uuid}/retrieve`, {
      query,
      retrieval_settings: retrievalSettings ?? {},
    });
  }

  // ============ Knowledge Engines API ============
  public getKnowledgeEngines(): Promise<ApiRespKnowledgeEngines> {
    return this.get('/api/v1/knowledge/engines');
  }

  // ============ Parsers API ============
  public listParsers(mimeType?: string): Promise<ApiRespParsers> {
    const params = mimeType ? `?mime_type=${encodeURIComponent(mimeType)}` : '';
    return this.get(`/api/v1/knowledge/parsers${params}`);
  }

  // ============ Extensions API ============
  public getExtensions(): Promise<ApiRespExtensions> {
    return this.get('/api/v1/extensions');
  }

  // ============ Plugins API ============
  public getPlugins(): Promise<ApiRespPlugins> {
    return this.get('/api/v1/plugins');
  }

  public getPlugin(author: string, name: string): Promise<ApiRespPlugin> {
    return this.get(`/api/v1/plugins/${author}/${name}`);
  }

  public getPluginConfig(
    author: string,
    name: string,
  ): Promise<ApiRespPluginConfig> {
    return this.get(`/api/v1/plugins/${author}/${name}/config`);
  }

  public updatePluginConfig(
    author: string,
    name: string,
    config: object,
  ): Promise<object> {
    return this.put(`/api/v1/plugins/${author}/${name}/config`, config);
  }

  public uploadPluginConfigFile(file: File): Promise<{ file_key: string }> {
    const formData = new FormData();
    formData.append('file', file);

    return this.request<{ file_key: string }>({
      method: 'post',
      url: '/api/v1/plugins/config-files',
      data: formData,
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
  }

  public deletePluginConfigFile(
    fileKey: string,
  ): Promise<{ deleted: boolean }> {
    return this.delete(`/api/v1/plugins/config-files/${fileKey}`);
  }

  public getPluginReadme(
    author: string,
    name: string,
    language: string = 'en',
  ): Promise<{ readme: string }> {
    return this.get(
      `/api/v1/plugins/${author}/${name}/readme?language=${language}`,
    );
  }

  public getPluginLogs(
    author: string,
    name: string,
    limit: number = 200,
    level?: string,
  ): Promise<{ logs: PluginLogEntry[] }> {
    const params = new URLSearchParams();
    params.set('limit', String(limit));
    if (level) {
      params.set('level', level);
    }
    return this.get(
      `/api/v1/plugins/${author}/${name}/logs?${params.toString()}`,
    );
  }

  public getPluginAssetURL(
    author: string,
    name: string,
    filepath: string,
  ): string {
    if (this.instance.defaults.baseURL === '/') {
      return `${window.location.origin}/api/v1/plugins/${author}/${name}/assets/${filepath}`;
    }
    return (
      this.instance.defaults.baseURL +
      `/api/v1/plugins/${author}/${name}/assets/${filepath}`
    );
  }

  public async pluginPageApi(
    author: string,
    name: string,
    pageId: string,
    endpoint: string,
    method: string = 'POST',
    body?: unknown,
  ): Promise<unknown> {
    const resp = await this.instance.request({
      url: `/api/v1/plugins/${author}/${name}/page-api`,
      method: 'POST',
      data: {
        page_id: pageId,
        endpoint,
        method,
        body,
      },
    });
    return resp.data?.data;
  }

  public getPluginIconURL(author: string, name: string): string {
    if (this.instance.defaults.baseURL === '/') {
      const url = window.location.href;
      const baseURL = url.split('/').slice(0, 3).join('/');
      return `${baseURL}/api/v1/plugins/${author}/${name}/icon`;
    }
    return (
      this.instance.defaults.baseURL + `/api/v1/plugins/${author}/${name}/icon`
    );
  }

  public installPluginFromGithub(
    assetUrl: string,
    owner: string,
    repo: string,
    releaseTag: string,
  ): Promise<AsyncTaskCreatedResp> {
    return this.post('/api/v1/plugins/install/github', {
      asset_url: assetUrl,
      owner,
      repo,
      release_tag: releaseTag,
    });
  }

  public getGithubReleases(repoUrl: string): Promise<{
    releases: Array<{
      id: number;
      tag_name: string;
      name: string;
      published_at: string;
      prerelease: boolean;
      draft: boolean;
      source_type?: 'release' | 'tag' | 'branch';
      archive_url?: string;
    }>;
    owner: string;
    repo: string;
    source_subdir?: string;
  }> {
    return this.post('/api/v1/plugins/github/releases', { repo_url: repoUrl });
  }

  public getGithubReleaseAssets(
    owner: string,
    repo: string,
    releaseId: number,
    releaseTag?: string,
    sourceType?: 'release' | 'tag' | 'branch',
    archiveUrl?: string,
  ): Promise<{
    assets: Array<{
      id: number;
      name: string;
      size: number;
      download_url: string;
      content_type: string;
    }>;
  }> {
    return this.post('/api/v1/plugins/github/release-assets', {
      owner,
      repo,
      release_id: releaseId,
      release_tag: releaseTag,
      source_type: sourceType,
      archive_url: archiveUrl,
    });
  }

  public installPluginFromLocal(file: File): Promise<AsyncTaskCreatedResp> {
    const formData = new FormData();
    formData.append('file', file);
    return this.postFile('/api/v1/plugins/install/local', formData);
  }

  public previewPluginInstallFromLocal(file: File): Promise<{
    filename: string;
    size: number;
    manifest: Record<string, unknown>;
    metadata: {
      author?: string;
      name?: string;
      version?: string;
      label?: I18nObject;
      description?: I18nObject;
      repository?: string;
    };
    component_types: string[];
    component_counts: Record<string, number>;
    requirements: string[];
    file_count: number;
  }> {
    const formData = new FormData();
    formData.append('file', file);
    return this.postFile('/api/v1/plugins/install/local/preview', formData);
  }

  // ============ Skill Install API ============
  public installSkillFromGithub(
    assetUrl: string,
    owner: string,
    repo: string,
    releaseTag: string,
    sourcePaths?: string[],
    sourceSubdir?: string,
  ): Promise<ApiRespSkills> {
    return this.post('/api/v1/skills/install/github', {
      asset_url: assetUrl,
      owner,
      repo,
      release_tag: releaseTag,
      source_paths: sourcePaths,
      source_subdir: sourceSubdir,
    });
  }

  public previewSkillInstallFromGithub(
    assetUrl: string,
    owner: string,
    repo: string,
    releaseTag: string,
    sourceSubdir?: string,
  ): Promise<{ skills: Skill[] }> {
    return this.post('/api/v1/skills/install/github/preview', {
      asset_url: assetUrl,
      owner,
      repo,
      release_tag: releaseTag,
      source_subdir: sourceSubdir,
    });
  }

  public previewSkillInstallFromUpload(
    file: File,
  ): Promise<{ skills: Skill[] }> {
    const formData = new FormData();
    formData.append('file', file);
    return this.postFile('/api/v1/skills/install/upload/preview', formData);
  }

  public installSkillFromUpload(
    file: File,
    sourcePaths?: string[],
  ): Promise<ApiRespSkills> {
    const formData = new FormData();
    formData.append('file', file);
    for (const sourcePath of sourcePaths || []) {
      formData.append('source_paths', sourcePath);
    }
    return this.postFile('/api/v1/skills/install/upload', formData);
  }

  public installPluginFromMarketplace(
    author: string,
    name: string,
    version: string,
  ): Promise<AsyncTaskCreatedResp> {
    return this.post('/api/v1/plugins/install/marketplace', {
      plugin_author: author,
      plugin_name: name,
      plugin_version: version,
    });
  }

  public removePlugin(
    author: string,
    name: string,
    deleteData: boolean = false,
  ): Promise<AsyncTaskCreatedResp> {
    return this.delete(
      `/api/v1/plugins/${author}/${name}?delete_data=${deleteData}`,
    );
  }

  public upgradePlugin(
    author: string,
    name: string,
  ): Promise<AsyncTaskCreatedResp> {
    return this.post(`/api/v1/plugins/${author}/${name}/upgrade`);
  }

  // ============ MCP API ============
  public getMCPServers(): Promise<ApiRespMCPServers> {
    return this.get('/api/v1/mcp/servers');
  }

  // ========== Tools ==========

  public getTools(): Promise<ApiRespTools> {
    return this.get('/api/v1/tools');
  }

  public getToolDetail(toolName: string): Promise<ApiRespToolDetail> {
    return this.get(`/api/v1/tools/${toolName}`);
  }

  public getMCPServer(serverName: string): Promise<ApiRespMCPServer> {
    return this.get(`/api/v1/mcp/servers/${encodeURIComponent(serverName)}`);
  }

  public createMCPServer(server: MCPServer): Promise<AsyncTaskCreatedResp> {
    return this.post('/api/v1/mcp/servers', server);
  }

  public updateMCPServer(
    serverName: string,
    server: Partial<MCPServer>,
  ): Promise<AsyncTaskCreatedResp> {
    return this.put(
      `/api/v1/mcp/servers/${encodeURIComponent(serverName)}`,
      server,
    );
  }

  public deleteMCPServer(serverName: string): Promise<AsyncTaskCreatedResp> {
    return this.delete(`/api/v1/mcp/servers/${encodeURIComponent(serverName)}`);
  }

  public toggleMCPServer(
    serverName: string,
    target_enabled: boolean,
  ): Promise<AsyncTaskCreatedResp> {
    return this.put(`/api/v1/mcp/servers/${encodeURIComponent(serverName)}`, {
      enable: target_enabled,
    });
  }

  public testMCPServer(
    serverName: string,
    serverData: object,
  ): Promise<AsyncTaskCreatedResp> {
    return this.post(
      `/api/v1/mcp/servers/${encodeURIComponent(serverName)}/test`,
      serverData,
    );
  }

  public installMCPServerFromGithub(
    source: string,
  ): Promise<AsyncTaskCreatedResp> {
    return this.post('/api/v1/mcp/install/github', { source });
  }

  public installMCPServerFromSSE(
    source: object,
  ): Promise<AsyncTaskCreatedResp> {
    return this.post('/api/v1/mcp/servers', { source });
  }

  // ============ Local Connector API ============
  public getLocalConnectors(): Promise<ApiRespLocalConnectors> {
    return this.get('/api/v1/local-connectors');
  }

  public getLocalConnectorStatus(
    connectorId: string,
  ): Promise<ApiRespLocalConnector> {
    return this.get(`/api/v1/local-connectors/${connectorId}/status`);
  }

  public detectLocalConnector(
    connectorId: string,
  ): Promise<ApiRespLocalConnector> {
    return this.post(`/api/v1/local-connectors/${connectorId}/detect`);
  }

  public setupLocalConnector(
    connectorId: string,
  ): Promise<{ job_id: string; status: string; stage: string }> {
    return this.post(`/api/v1/local-connectors/${connectorId}/setup`);
  }

  public refreshLocalConnector(
    connectorId: string,
  ): Promise<ApiRespLocalConnector> {
    return this.post(`/api/v1/local-connectors/${connectorId}/refresh`);
  }

  public startLocalConnectorWorker(
    connectorId: string,
  ): Promise<ApiRespLocalConnector> {
    return this.post(`/api/v1/local-connectors/${connectorId}/start`);
  }

  public stopLocalConnectorWorker(
    connectorId: string,
  ): Promise<ApiRespLocalConnector> {
    return this.post(`/api/v1/local-connectors/${connectorId}/stop`);
  }

  public restartLocalConnectorWorker(
    connectorId: string,
  ): Promise<ApiRespLocalConnector> {
    return this.post(`/api/v1/local-connectors/${connectorId}/restart`);
  }

  public getLocalConnectorLogs(
    connectorId: string,
  ): Promise<{ connector_id: string; logs: string }> {
    return this.get(`/api/v1/local-connectors/${connectorId}/logs`);
  }

  public getLocalConnectorJob(
    jobId: string,
  ): Promise<ApiRespLocalConnectorJob> {
    return this.get(`/api/v1/local-connectors/jobs/${jobId}`);
  }

  public getLocalConnectorMonitorStatus(): Promise<ApiRespLocalConnectorMonitor> {
    return this.get('/api/v1/local-connectors/wxwork-local/monitor/status');
  }

  public startLocalConnectorMonitor(): Promise<ApiRespLocalConnector> {
    return this.post('/api/v1/local-connectors/wxwork-local/monitor/start');
  }

  public stopLocalConnectorMonitor(): Promise<ApiRespLocalConnector> {
    return this.post('/api/v1/local-connectors/wxwork-local/monitor/stop');
  }

  public restartLocalConnectorMonitor(): Promise<ApiRespLocalConnector> {
    return this.post('/api/v1/local-connectors/wxwork-local/monitor/restart');
  }

  // ============ Database Mode API ============
  public getDatabaseModeConversations(params?: {
    status?: string;
    keyword?: string;
    page?: number;
    page_size?: number;
  }): Promise<ApiRespDatabaseModeConversations> {
    return this.get('/api/v1/database-mode/conversations', params);
  }

  public getDatabaseModeConversation(
    conversationId: number,
  ): Promise<ApiRespDatabaseModeConversation> {
    return this.get(`/api/v1/database-mode/conversations/${conversationId}`);
  }

  public getDatabaseModeMessages(
    conversationId: number,
    params?: {
      status?: string;
      page?: number;
      page_size?: number;
    },
  ): Promise<ApiRespDatabaseModeMessages> {
    return this.get(
      `/api/v1/database-mode/conversations/${conversationId}/messages`,
      params,
    );
  }

  public generateDatabaseModeDraft(
    messageId: number,
  ): Promise<ApiRespDatabaseModeMessage> {
    return this.post(
      `/api/v1/database-mode/messages/${messageId}/generate-draft`,
    );
  }

  public updateDatabaseModeDraft(
    messageId: number,
    payload: {
      draft_text: string;
      draft_source?: string;
    },
  ): Promise<ApiRespDatabaseModeMessage> {
    return this.put(
      `/api/v1/database-mode/messages/${messageId}/draft`,
      payload,
    );
  }

  public deleteDatabaseModeDraft(
    messageId: number,
  ): Promise<ApiRespDatabaseModeMessage> {
    return this.delete(`/api/v1/database-mode/messages/${messageId}/draft`);
  }

  public processDatabaseModeMessage(
    messageId: number,
  ): Promise<ApiRespDatabaseModeMessage> {
    return this.post(`/api/v1/database-mode/messages/${messageId}/process`);
  }

  public skipDatabaseModeMessage(
    messageId: number,
  ): Promise<ApiRespDatabaseModeMessage> {
    return this.post(`/api/v1/database-mode/messages/${messageId}/skip`);
  }

  public deleteDatabaseModeMessage(messageId: number): Promise<void> {
    return this.delete(`/api/v1/database-mode/messages/${messageId}`);
  }

  public batchProcessDatabaseModeMessages(
    message_ids: number[],
  ): Promise<{ messages: unknown[] }> {
    return this.post('/api/v1/database-mode/messages/batch-process', {
      message_ids,
    });
  }

  public batchSkipDatabaseModeMessages(
    message_ids: number[],
  ): Promise<{ messages: unknown[] }> {
    return this.post('/api/v1/database-mode/messages/batch-skip', {
      message_ids,
    });
  }

  public batchDeleteDatabaseModeMessages(
    message_ids: number[],
  ): Promise<{ deleted_ids: number[] }> {
    return this.post('/api/v1/database-mode/messages/batch-delete', {
      message_ids,
    });
  }

  public async createDatabaseModeEventSession(
    config?: RequestConfig,
  ): Promise<void> {
    await this.instance.request({
      method: 'post',
      url: '/api/v1/database-mode/events/session',
      withCredentials: true,
      ...config,
    });
  }

  // ============ System API ============
  public getSystemInfo(): Promise<ApiRespSystemInfo> {
    return this.get('/api/v1/system/info');
  }

  public updateWizardStatus(status: 'skipped' | 'completed'): Promise<void> {
    return this.post('/api/v1/system/wizard/completed', { status });
  }

  public saveWizardProgress(progress: {
    step: number;
    selected_adapter: string | null;
    created_bot_uuid: string | null;
    bot_saved: boolean;
    selected_runner: string | null;
  }): Promise<void> {
    return this.put('/api/v1/system/wizard/progress', progress);
  }

  public getAsyncTasks(params?: {
    type?: string;
    kind?: string;
  }): Promise<ApiRespAsyncTasks> {
    const query = new URLSearchParams();
    if (params?.type) query.set('type', params.type);
    if (params?.kind) query.set('kind', params.kind);
    const qs = query.toString();
    return this.get(`/api/v1/system/tasks${qs ? `?${qs}` : ''}`);
  }

  public getAsyncTask(id: number): Promise<AsyncTask> {
    return this.get(`/api/v1/system/tasks/${id}`);
  }

  public getPluginSystemStatus(): Promise<ApiRespPluginSystemStatus> {
    return this.get('/api/v1/system/status/plugin-system');
  }

  // ============ RAG Migration API ============
  public getRagMigrationStatus(): Promise<RagMigrationStatusResp> {
    return this.get('/api/v1/knowledge/migration/status');
  }

  public executeRagMigration(
    installPlugin: boolean = true,
  ): Promise<AsyncTaskCreatedResp> {
    return this.post('/api/v1/knowledge/migration/execute', {
      install_plugin: installPlugin,
    });
  }

  public dismissRagMigration(): Promise<object> {
    return this.post('/api/v1/knowledge/migration/dismiss');
  }

  public getPluginDebugInfo(): Promise<{
    debug_url: string;
    plugin_debug_key: string;
  }> {
    return this.get('/api/v1/plugins/debug-info');
  }

  public getBoxStatus(): Promise<ApiRespBoxStatus> {
    return this.get('/api/v1/box/status');
  }

  public getBoxSessions(): Promise<BoxSessionInfo[]> {
    return this.get('/api/v1/box/sessions');
  }

  // ============ User API ============
  public checkIfInited(): Promise<{ initialized: boolean }> {
    return this.get('/api/v1/user/init');
  }

  public initUser(user: string, password: string): Promise<object> {
    return this.post('/api/v1/user/init', { user, password });
  }

  public resetPassword(
    user: string,
    recoveryKey: string,
    newPassword: string,
  ): Promise<{ user: string }> {
    return this.post('/api/v1/user/reset-password', {
      user,
      recovery_key: recoveryKey,
      new_password: newPassword,
    });
  }

  public changePassword(
    currentPassword: string,
    newPassword: string,
  ): Promise<{ user: string }> {
    return this.post('/api/v1/user/change-password', {
      current_password: currentPassword,
      new_password: newPassword,
    });
  }

  public getUserInfo(): Promise<{
    user: string;
    account_type: 'local' | 'space';
    has_password: boolean;
  }> {
    return this.get('/api/v1/user/info');
  }

  public getSpaceCredits(): Promise<{ credits: number | null }> {
    return this.get('/api/v1/user/space-credits');
  }

  public setPassword(
    newPassword: string,
    currentPassword?: string,
  ): Promise<{ user: string }> {
    return this.post('/api/v1/user/set-password', {
      new_password: newPassword,
      current_password: currentPassword,
    });
  }

  public async bindSpaceAccount(
    code: string,
    state: string,
  ): Promise<{
    token: string;
    user: string;
    account_type: 'local' | 'space';
  }> {
    const response = await this.instance.post('/api/v1/user/bind-space', {
      code,
      state,
    });
    if (response.data.code !== 0) {
      throw {
        code: response.data.code,
        msg: response.data.msg || 'Unknown error',
      };
    }
    return response.data.data;
  }

  // ============ Space OAuth API (Redirect Flow) ============
  public getSpaceAuthorizeUrl(
    redirectUri: string,
    state?: string,
  ): Promise<{
    authorize_url: string;
  }> {
    const params: Record<string, string> = { redirect_uri: redirectUri };
    if (state) {
      params.state = state;
    }
    return this.get('/api/v1/user/space/authorize-url', params);
  }

  public async exchangeSpaceOAuthCode(code: string): Promise<{
    token: string;
    user: string;
  }> {
    const response = await this.instance.post('/api/v1/user/space/callback', {
      code,
    });
    if (response.data.code !== 0) {
      throw {
        code: response.data.code,
        msg: response.data.msg || 'Unknown error',
      };
    }
    return response.data.data;
  }

  // ============ Monitoring API ============
  public getMonitoringData(params: {
    botId?: string[];
    pipelineId?: string[];
    startTime?: string;
    endTime?: string;
    limit?: number;
  }): Promise<{
    overview: {
      total_messages: number;
      llm_calls: number;
      embedding_calls: number;
      model_calls: number;
      success_rate: number;
      active_sessions: number;
    };
    messages: Array<{
      id: string;
      timestamp: string;
      bot_id: string;
      bot_name: string;
      pipeline_id: string;
      pipeline_name: string;
      message_content: string;
      session_id: string;
      status: string;
      level: string;
      platform?: string;
      user_id?: string;
      runner_name?: string;
      variables?: string;
    }>;
    llmCalls: Array<{
      id: string;
      timestamp: string;
      model_name: string;
      input_tokens: number;
      output_tokens: number;
      total_tokens: number;
      duration: number;
      cost?: number;
      status: string;
      bot_id: string;
      bot_name: string;
      pipeline_id: string;
      pipeline_name: string;
      error_message?: string;
      message_id?: string;
    }>;
    embeddingCalls: Array<{
      id: string;
      timestamp: string;
      model_name: string;
      prompt_tokens: number;
      total_tokens: number;
      duration: number;
      input_count: number;
      status: string;
      error_message?: string;
      knowledge_base_id?: string;
      query_text?: string;
      session_id?: string;
      message_id?: string;
      call_type?: string;
    }>;
    sessions: Array<{
      session_id: string;
      bot_id: string;
      bot_name: string;
      pipeline_id: string;
      pipeline_name: string;
      message_count: number;
      last_activity: string;
      start_time: string;
      platform?: string;
      user_id?: string;
    }>;
    errors: Array<{
      id: string;
      timestamp: string;
      error_type: string;
      error_message: string;
      bot_id: string;
      bot_name: string;
      pipeline_id: string;
      pipeline_name: string;
      session_id?: string;
      stack_trace?: string;
      message_id?: string;
    }>;
    totalCount: {
      messages: number;
      llmCalls: number;
      embeddingCalls: number;
      sessions: number;
      errors: number;
    };
  }> {
    const queryParams = new URLSearchParams();
    if (params.botId) {
      params.botId.forEach((id) => queryParams.append('botId', id));
    }
    if (params.pipelineId) {
      params.pipelineId.forEach((id) => queryParams.append('pipelineId', id));
    }
    if (params.startTime) {
      queryParams.append('startTime', params.startTime);
    }
    if (params.endTime) {
      queryParams.append('endTime', params.endTime);
    }
    if (params.limit) {
      queryParams.append('limit', params.limit.toString());
    }

    return this.get(`/api/v1/monitoring/data?${queryParams.toString()}`);
  }

  public getMonitoringOverview(params: {
    botId?: string[];
    pipelineId?: string[];
    startTime?: string;
    endTime?: string;
  }): Promise<{
    total_messages: number;
    llm_calls: number;
    success_rate: number;
    active_sessions: number;
  }> {
    const queryParams = new URLSearchParams();
    if (params.botId) {
      params.botId.forEach((id) => queryParams.append('botId', id));
    }
    if (params.pipelineId) {
      params.pipelineId.forEach((id) => queryParams.append('pipelineId', id));
    }
    if (params.startTime) {
      queryParams.append('startTime', params.startTime);
    }
    if (params.endTime) {
      queryParams.append('endTime', params.endTime);
    }

    return this.get(`/api/v1/monitoring/overview?${queryParams.toString()}`);
  }

  public getTokenStatistics(params: {
    botId?: string[];
    pipelineId?: string[];
    startTime?: string;
    endTime?: string;
    bucket?: 'hour' | 'day';
  }): Promise<{
    summary: {
      total_calls: number;
      success_calls: number;
      error_calls: number;
      total_input_tokens: number;
      total_output_tokens: number;
      total_tokens: number;
      total_cost: number;
      avg_tokens_per_call: number;
      avg_duration_ms: number;
      avg_tokens_per_second: number;
      zero_token_success_calls: number;
    };
    by_model: Array<{
      model_name: string;
      calls: number;
      error_calls: number;
      input_tokens: number;
      output_tokens: number;
      total_tokens: number;
      cost: number;
      avg_tokens_per_call: number;
      avg_duration_ms: number;
    }>;
    timeseries: Array<{
      bucket: string;
      input_tokens: number;
      output_tokens: number;
      total_tokens: number;
      calls: number;
    }>;
    bucket: string;
  }> {
    const queryParams = new URLSearchParams();
    if (params.botId) {
      params.botId.forEach((id) => queryParams.append('botId', id));
    }
    if (params.pipelineId) {
      params.pipelineId.forEach((id) => queryParams.append('pipelineId', id));
    }
    if (params.startTime) {
      queryParams.append('startTime', params.startTime);
    }
    if (params.endTime) {
      queryParams.append('endTime', params.endTime);
    }
    if (params.bucket) {
      queryParams.append('bucket', params.bucket);
    }

    return this.get(
      `/api/v1/monitoring/token-statistics?${queryParams.toString()}`,
    );
  }

  // ============ Survey API ============
  public getSurveyPending(): Promise<{
    survey: {
      survey_id: string;
      version: number;
      title: Record<string, string>;
      description: Record<string, string>;
      questions: SurveyQuestion[];
    } | null;
  }> {
    return this.get('/api/v1/survey/pending');
  }

  public submitSurveyResponse(
    surveyId: string,
    answers: Record<string, unknown>,
    completed: boolean = true,
  ): Promise<object> {
    return this.post('/api/v1/survey/respond', {
      survey_id: surveyId,
      answers,
      completed,
    });
  }

  public dismissSurvey(surveyId: string): Promise<object> {
    return this.post('/api/v1/survey/dismiss', { survey_id: surveyId });
  }

  // ============ Skills API ============

  public getSkills(): Promise<ApiRespSkills> {
    return this.get('/api/v1/skills');
  }

  public getSkill(name: string): Promise<ApiRespSkill> {
    return this.get(`/api/v1/skills/${name}`);
  }

  public createSkill(
    skill: Omit<Skill, 'name'> & { name: string },
  ): Promise<ApiRespSkill> {
    return this.post('/api/v1/skills', skill);
  }

  public updateSkill(
    name: string,
    skill: Partial<Skill>,
  ): Promise<ApiRespSkill> {
    return this.put(`/api/v1/skills/${name}`, skill);
  }

  public deleteSkill(name: string): Promise<object> {
    return this.delete(`/api/v1/skills/${name}`);
  }

  public previewSkill(name: string): Promise<{ instructions: string }> {
    return this.get(`/api/v1/skills/${name}/preview`);
  }

  public getSkillIndex(pipelineUuid?: string): Promise<{ index: string }> {
    const params = pipelineUuid ? { pipeline_uuid: pipelineUuid } : {};
    return this.get('/api/v1/skills/index', params);
  }

  public scanSkillDirectory(path: string): Promise<{
    package_root: string;
    name: string;
    display_name?: string;
    description: string;
    instructions: string;
  }> {
    return this.get('/api/v1/skills/scan', { path });
  }

  public listSkillFiles(
    skillName: string,
    path: string = '.',
    includeHidden: boolean = false,
  ): Promise<{
    skill: { name: string };
    base_path: string;
    entries: Array<{
      path: string;
      name: string;
      is_dir: boolean;
      size: number | null;
    }>;
    truncated: boolean;
  }> {
    return this.get(`/api/v1/skills/${skillName}/files`, {
      path,
      include_hidden: includeHidden,
    });
  }

  public readSkillFile(
    skillName: string,
    filePath: string,
  ): Promise<{
    skill: { name: string };
    path: string;
    content: string;
  }> {
    return this.get(`/api/v1/skills/${skillName}/files/${filePath}`);
  }

  public writeSkillFile(
    skillName: string,
    filePath: string,
    content: string,
  ): Promise<{
    skill: { name: string };
    path: string;
    bytes_written: number;
  }> {
    return this.put(`/api/v1/skills/${skillName}/files/${filePath}`, {
      content,
    });
  }

  // ============ Bot-scoped Database Mode API ============

  /**
   * List conversations for a specific bot
   */
  public listBotConversations(
    botId: string,
    params?: {
      status?: string;
      keyword?: string;
      page?: number;
      page_size?: number;
    },
  ): Promise<import('@/app/infra/entities/api').ApiRespBotConversations> {
    const query: Record<string, string> = {};
    if (params?.status) query.status = params.status;
    if (params?.keyword) query.keyword = params.keyword;
    if (params?.page) query.page = params.page.toString();
    if (params?.page_size) query.page_size = params.page_size.toString();

    return this.get(`/api/v1/bots/${botId}/conversations`, query);
  }

  /**
   * Get a specific conversation for a bot
   */
  public getBotConversation(
    botId: string,
    conversationId: string,
  ): Promise<import('@/app/infra/entities/api').ApiRespBotConversation> {
    return this.get(`/api/v1/bots/${botId}/conversations/${conversationId}`);
  }

  /**
   * List messages in a bot conversation
   */
  public listBotMessages(
    botId: string,
    conversationId: string,
    params?: {
      status?: string;
      page?: number;
      page_size?: number;
    },
  ): Promise<import('@/app/infra/entities/api').ApiRespBotMessages> {
    const query: Record<string, string> = {};
    if (params?.status) query.status = params.status;
    if (params?.page) query.page = params.page.toString();
    if (params?.page_size) query.page_size = params.page_size.toString();

    return this.get(
      `/api/v1/bots/${botId}/conversations/${conversationId}/messages`,
      query,
    );
  }

  /**
   * Generate a draft reply for a message
   */
  public generateBotDraft(
    botId: string,
    messageId: string,
  ): Promise<import('@/app/infra/entities/api').ApiRespGenerateDraft> {
    return this.post(
      `/api/v1/bots/${botId}/messages/${messageId}/generate-draft`,
      {},
    );
  }

  /**
   * Update a draft reply
   */
  public updateBotDraft(
    botId: string,
    draftId: string,
    content: string,
  ): Promise<import('@/app/infra/entities/api').ApiRespUpdateDraft> {
    return this.put(`/api/v1/bots/${botId}/drafts/${draftId}`, { content });
  }

  /**
   * Delete a persisted draft reply
   */
  public deleteBotDraft(
    botId: string,
    draftId: string,
  ): Promise<import('@/app/infra/entities/api').ApiRespUpdateDraft> {
    return this.delete(`/api/v1/bots/${botId}/drafts/${draftId}`);
  }

  /**
   * Paste the current persisted draft into the verified WeCom input box.
   */
  public pasteBotDraft(
    botId: string,
    messageId: string,
    draftId: string,
    idempotencyKey: string,
  ): Promise<import('@/app/infra/entities/api').DesktopAutomationRun> {
    return this.post(
      `/api/v1/bots/${botId}/messages/${messageId}/paste-draft`,
      { draft_id: Number(draftId) },
      { headers: { 'Idempotency-Key': idempotencyKey } },
    );
  }

  /**
   * Explicitly send a persisted draft through the desktop runtime. Disabled unless the backend/runtime gates allow it.
   */
  public sendBotDraft(
    botId: string,
    messageId: string,
    draftId: string,
    sendStrategy: 'enter' | 'ctrl_enter' | 'click_send_button',
    idempotencyKey?: string,
  ): Promise<import('@/app/infra/entities/api').DesktopAutomationRun> {
    return this.post(`/api/v1/bots/${botId}/messages/${messageId}/send-draft`, {
      draft_id: Number(draftId),
      explicit_send_action: true,
      python_authorized: true,
      send_strategy: sendStrategy,
      ...(idempotencyKey ? { idempotency_key: idempotencyKey } : {}),
    });
  }

  /**
   * Get a bot-scoped desktop automation run.
   */
  public getBotDesktopAutomationRun(
    botId: string,
    runId: string,
  ): Promise<import('@/app/infra/entities/api').DesktopAutomationRun> {
    return this.get(`/api/v1/bots/${botId}/desktop-automation/runs/${runId}`);
  }

  /**
   * Cancel a bot-scoped desktop automation run.
   */
  public cancelBotDesktopAutomationRun(
    botId: string,
    runId: string,
  ): Promise<import('@/app/infra/entities/api').DesktopAutomationRun> {
    return this.post(
      `/api/v1/bots/${botId}/desktop-automation/runs/${runId}/cancel`,
      {},
    );
  }

  /**
   * Get the desktop runtime status without starting the runtime.
   */
  public getDesktopAutomationRuntimeStatus(): Promise<
    import('@/app/infra/entities/api').DesktopRuntimeStatus
  > {
    return this.get('/api/v1/desktop-automation/runtime/status');
  }

  /**
   * Mark a message as processed
   */
  public processBotMessage(botId: string, messageId: string): Promise<void> {
    return this.post(`/api/v1/bots/${botId}/messages/${messageId}/process`, {});
  }

  /**
   * Skip a message
   */
  public skipBotMessage(botId: string, messageId: string): Promise<void> {
    return this.post(`/api/v1/bots/${botId}/messages/${messageId}/skip`, {});
  }

  /**
   * Delete a message
   */
  public deleteBotMessage(botId: string, messageId: string): Promise<void> {
    return this.delete(`/api/v1/bots/${botId}/messages/${messageId}`);
  }

  /**
   * Batch process messages
   */
  public batchProcessBotMessages(
    botId: string,
    messageIds: string[],
  ): Promise<import('@/app/infra/entities/api').ApiRespBatchOperation> {
    return this.post(`/api/v1/bots/${botId}/messages/batch-process`, {
      message_ids: messageIds,
    });
  }

  /**
   * Batch skip messages
   */
  public batchSkipBotMessages(
    botId: string,
    messageIds: string[],
  ): Promise<import('@/app/infra/entities/api').ApiRespBatchOperation> {
    return this.post(`/api/v1/bots/${botId}/messages/batch-skip`, {
      message_ids: messageIds,
    });
  }

  /**
   * Batch delete messages
   */
  public batchDeleteBotMessages(
    botId: string,
    messageIds: string[],
  ): Promise<import('@/app/infra/entities/api').ApiRespBatchOperation> {
    return this.post(`/api/v1/bots/${botId}/messages/batch-delete`, {
      message_ids: messageIds,
    });
  }

  // ============ Broadcast API ============
  public getBroadcastTemplates(
    scope: ApiBroadcastScope,
  ): Promise<ApiBroadcastTemplate[]> {
    return this.get('/api/v1/broadcast/templates', scope);
  }

  public createBroadcastTemplate(
    scope: ApiBroadcastScope,
    payload: {
      name: string;
      content: string;
      enabled: boolean;
    },
  ): Promise<ApiBroadcastTemplate> {
    return this.requestBroadcast<ApiBroadcastTemplate>({
      method: 'post',
      url: '/api/v1/broadcast/templates',
      data: {
        ...scope,
        ...payload,
      },
    });
  }

  public updateBroadcastTemplate(
    scope: ApiBroadcastScope,
    templateId: number,
    payload: {
      name: string;
      content: string;
      enabled: boolean;
    },
  ): Promise<ApiBroadcastTemplate> {
    return this.requestBroadcast<ApiBroadcastTemplate>({
      method: 'put',
      url: `/api/v1/broadcast/templates/${templateId}`,
      data: {
        ...scope,
        ...payload,
      },
    });
  }

  public deleteBroadcastTemplate(
    scope: ApiBroadcastScope,
    templateId: number,
  ): Promise<{ deleted: boolean }> {
    return this.delete(
      `/api/v1/broadcast/templates/${templateId}?${this.toSearchParams({
        bot_uuid: scope.bot_uuid,
        connector_id: scope.connector_id,
      })}`,
    );
  }

  public renderBroadcastTemplate(
    scope: ApiBroadcastScope,
    payload:
      | {
          templateId: number;
          variables: Record<string, string>;
        }
      | {
          content: string;
          variables: Record<string, string>;
        },
  ): Promise<ApiBroadcastTemplateRenderResult> {
    const body =
      'templateId' in payload
        ? {
            ...scope,
            template_id: payload.templateId,
            variables: payload.variables,
          }
        : {
            ...scope,
            content: payload.content,
            variables: payload.variables,
          };
    return this.requestBroadcast<ApiBroadcastTemplateRenderResult>({
      method: 'post',
      url: '/api/v1/broadcast/templates/render',
      data: body,
    });
  }

  public getBroadcastVariableProfile(
    scope: ApiBroadcastScope,
  ): Promise<ApiBroadcastVariableProfile> {
    return this.get('/api/v1/broadcast/variable-profile', scope);
  }

  public saveBroadcastVariableProfile(
    scope: ApiBroadcastScope,
    payload: ApiBroadcastVariableProfile,
  ): Promise<ApiBroadcastVariableProfile> {
    return this.requestBroadcast<ApiBroadcastVariableProfile>({
      method: 'put',
      url: '/api/v1/broadcast/variable-profile',
      data: {
        ...scope,
        ...payload,
      },
    });
  }

  public getBroadcastGroupRules(
    scope: ApiBroadcastScope,
  ): Promise<ApiBroadcastGroupRule[]> {
    return this.get('/api/v1/broadcast/group-rules', scope);
  }

  public createBroadcastGroupRule(
    scope: ApiBroadcastScope,
    payload: {
      source_value: string;
      match_type: 'exact' | 'contains' | 'regex';
      match_expression: string;
      target_conversation_id?: string;
      target_conversation_name: string;
      priority: number;
      enabled: boolean;
    },
  ): Promise<ApiBroadcastGroupRule> {
    return this.requestBroadcast<ApiBroadcastGroupRule>({
      method: 'post',
      url: '/api/v1/broadcast/group-rules',
      data: {
        ...scope,
        ...payload,
      },
    });
  }

  public updateBroadcastGroupRule(
    scope: ApiBroadcastScope,
    ruleId: number,
    payload: {
      source_value: string;
      match_type: 'exact' | 'contains' | 'regex';
      match_expression: string;
      target_conversation_id?: string;
      target_conversation_name: string;
      priority: number;
      enabled: boolean;
    },
  ): Promise<ApiBroadcastGroupRule> {
    return this.requestBroadcast<ApiBroadcastGroupRule>({
      method: 'put',
      url: `/api/v1/broadcast/group-rules/${ruleId}`,
      data: {
        ...scope,
        ...payload,
      },
    });
  }

  public deleteBroadcastGroupRule(
    scope: ApiBroadcastScope,
    ruleId: number,
  ): Promise<{ deleted: boolean }> {
    return this.delete(
      `/api/v1/broadcast/group-rules/${ruleId}?${this.toSearchParams({
        bot_uuid: scope.bot_uuid,
        connector_id: scope.connector_id,
      })}`,
    );
  }

  public matchBroadcastGroupRule(
    scope: ApiBroadcastScope,
    sourceValue: string,
  ): Promise<ApiBroadcastGroupMatchResult> {
    return this.requestBroadcast<ApiBroadcastGroupMatchResult>({
      method: 'post',
      url: '/api/v1/broadcast/group-rules/match',
      data: {
        ...scope,
        source_value: sourceValue,
      },
    });
  }

  public getBroadcastGroupNames(
    scope: ApiBroadcastScope,
  ): Promise<ApiBroadcastGroupName[]> {
    return this.get('/api/v1/broadcast/group-names', scope);
  }

  public createBroadcastGroupName(
    scope: ApiBroadcastScope,
    groupName: string,
  ): Promise<ApiBroadcastGroupNameCreateResult> {
    return this.requestBroadcast<ApiBroadcastGroupNameCreateResult>({
      method: 'post',
      url: '/api/v1/broadcast/group-names',
      data: {
        ...scope,
        group_name: groupName,
      },
    });
  }

  public syncBroadcastGroupNames(
    scope: ApiBroadcastScope,
  ): Promise<ApiBroadcastGroupNameSyncResult> {
    return this.requestBroadcast<ApiBroadcastGroupNameSyncResult>({
      method: 'post',
      url: `/api/v1/broadcast/group-names/sync?${this.toSearchParams({
        bot_uuid: scope.bot_uuid,
        connector_id: scope.connector_id,
      })}`,
    });
  }

  public deleteBroadcastGroupName(
    scope: ApiBroadcastScope,
    groupNameId: number,
  ): Promise<{ deleted: boolean }> {
    return this.delete(
      `/api/v1/broadcast/group-names/${groupNameId}?${this.toSearchParams({
        bot_uuid: scope.bot_uuid,
        connector_id: scope.connector_id,
      })}`,
    );
  }

  public uploadBroadcastImport(
    scope: ApiBroadcastScope,
    file: File,
    options?: {
      group_field_override?: string;
    },
  ): Promise<ApiBroadcastImportBatch> {
    const formData = new FormData();
    formData.append('bot_uuid', scope.bot_uuid);
    formData.append('connector_id', scope.connector_id);
    formData.append('file', file);
    if (options?.group_field_override) {
      formData.append('group_field_override', options.group_field_override);
    }
    return this.requestBroadcast<ApiBroadcastImportBatch>({
      method: 'post',
      url: '/api/v1/broadcast/imports',
      data: formData,
    });
  }

  public getBroadcastImportGroupRuleCandidates(
    scope: ApiBroadcastScope,
    importId: number,
    filters?: {
      status?:
        | 'new'
        | 'configured'
        | 'needs_repair'
        | 'conflict'
        | 'invalid'
        | 'all';
      keyword?: string;
      page?: number;
      page_size?: number;
    },
  ): Promise<ApiBroadcastImportGroupRuleCandidatesResponse> {
    return this.requestBroadcast<ApiBroadcastImportGroupRuleCandidatesResponse>(
      {
        method: 'get',
        url: `/api/v1/broadcast/imports/${importId}/group-rule-candidates?${this.toSearchParams(
          {
            bot_uuid: scope.bot_uuid,
            connector_id: scope.connector_id,
            status: filters?.status,
            keyword: filters?.keyword,
            page: filters?.page,
            page_size: filters?.page_size,
          },
        )}`,
      },
    );
  }

  public getBroadcastImportBatches(
    scope: ApiBroadcastScope,
  ): Promise<ApiBroadcastImportBatch[]> {
    return this.get('/api/v1/broadcast/imports', scope);
  }

  public getBroadcastImportDetail(
    scope: ApiBroadcastScope,
    importId: number,
    filters?: {
      match_status?: 'matched' | 'unmatched' | 'invalid';
      keyword?: string;
      page?: number;
      page_size?: number;
    },
  ): Promise<ApiBroadcastImportDetail> {
    return this.get(`/api/v1/broadcast/imports/${importId}`, {
      ...scope,
      ...filters,
    });
  }

  public getBroadcastImportGroups(
    scope: ApiBroadcastScope,
    importId: number,
    filters?: {
      match_status?: 'matched' | 'unmatched' | 'invalid' | 'conflict';
      keyword?: string;
      page?: number;
      page_size?: number;
    },
  ): Promise<ApiBroadcastImportGroupsResponse> {
    return this.get(`/api/v1/broadcast/imports/${importId}/groups`, {
      ...scope,
      ...filters,
    });
  }

  public getBroadcastImportGroupRows(
    scope: ApiBroadcastScope,
    importId: number,
    groupKey: string,
    filters?: {
      page?: number;
      page_size?: number;
    },
  ): Promise<ApiBroadcastImportGroupRowsResponse> {
    return this.get(
      `/api/v1/broadcast/imports/${importId}/groups/${groupKey}/rows`,
      {
        ...scope,
        ...filters,
      },
    );
  }

  public updateBroadcastImportGroupTemplateAssignments(
    scope: ApiBroadcastScope,
    importId: number,
    items: ApiBroadcastImportGroupTemplateAssignment[],
  ): Promise<{ items: ApiBroadcastImportGroupTemplateAssignment[] }> {
    return this.requestBroadcast({
      method: 'put',
      url: `/api/v1/broadcast/imports/${importId}/group-template-assignments`,
      data: {
        ...scope,
        items,
      },
    });
  }

  public uploadBroadcastImportGroupAttachments(
    scope: ApiBroadcastScope,
    importId: number,
    groupKey: string,
    files: File[],
  ): Promise<ApiBroadcastDraft['attachments']> {
    const formData = new FormData();
    formData.append('bot_uuid', scope.bot_uuid);
    formData.append('connector_id', scope.connector_id);
    files.forEach((file) => formData.append('files', file));
    return this.requestBroadcast<ApiBroadcastDraft['attachments']>({
      method: 'post',
      url: `/api/v1/broadcast/imports/${importId}/groups/${groupKey}/attachments`,
      data: formData,
    });
  }

  public deleteBroadcastImportGroupAttachment(
    scope: ApiBroadcastScope,
    importId: number,
    groupKey: string,
    attachmentId: number,
  ): Promise<ApiBroadcastDraft['attachments']> {
    return this.delete(
      `/api/v1/broadcast/imports/${importId}/groups/${groupKey}/attachments/${attachmentId}?${this.toSearchParams(
        {
          bot_uuid: scope.bot_uuid,
          connector_id: scope.connector_id,
        },
      )}`,
    );
  }

  public deleteBroadcastImport(
    scope: ApiBroadcastScope,
    importId: number,
  ): Promise<{ deleted: boolean }> {
    return this.delete(
      `/api/v1/broadcast/imports/${importId}?${this.toSearchParams({
        bot_uuid: scope.bot_uuid,
        connector_id: scope.connector_id,
      })}`,
    );
  }

  public rematchBroadcastImport(
    scope: ApiBroadcastScope,
    importId: number,
  ): Promise<ApiBroadcastImportDetail> {
    return this.requestBroadcast<ApiBroadcastImportDetail>({
      method: 'post',
      url: `/api/v1/broadcast/imports/${importId}/rematch`,
      data: scope,
    });
  }

  public bulkAssignBroadcastImportGroupRules(
    scope: ApiBroadcastScope,
    importId: number,
    items: Array<{
      group_key: string;
      target_conversation_id: string;
      target_conversation_name: string;
    }>,
  ): Promise<ApiBroadcastBulkAssignResult> {
    return this.requestBroadcast<ApiBroadcastBulkAssignResult>({
      method: 'post',
      url: `/api/v1/broadcast/imports/${importId}/group-rules/bulk-assign`,
      data: {
        ...scope,
        items,
      },
    });
  }

  public generateBroadcastImportDrafts(
    scope: ApiBroadcastScope,
    importId: number,
    payload: {
      template_id?: number;
      group_keys?: string[];
      overwrite_existing?: boolean;
    },
  ): Promise<ApiBroadcastImportDraftGenerationResult> {
    return this.requestBroadcast<ApiBroadcastImportDraftGenerationResult>({
      method: 'post',
      url: `/api/v1/broadcast/imports/${importId}/generate-drafts`,
      data: {
        ...scope,
        ...payload,
      },
    });
  }

  public getBroadcastDrafts(
    scope: ApiBroadcastScope,
    filters?: {
      import_batch_id?: number;
      status?: ApiBroadcastDraftStatus;
      keyword?: string;
    },
  ): Promise<ApiBroadcastDraft[]> {
    return this.get('/api/v1/broadcast/drafts', {
      ...scope,
      ...filters,
    });
  }

  public getBroadcastDraftDetail(
    scope: ApiBroadcastScope,
    draftId: number,
  ): Promise<ApiBroadcastDraft> {
    return this.get(`/api/v1/broadcast/drafts/${draftId}`, scope);
  }

  public uploadBroadcastDraftAttachments(
    scope: ApiBroadcastScope,
    draftId: number,
    files: File[],
  ): Promise<ApiBroadcastDraft> {
    const formData = new FormData();
    formData.append('bot_uuid', scope.bot_uuid);
    formData.append('connector_id', scope.connector_id);
    files.forEach((file) => formData.append('files', file));
    return this.requestBroadcast<ApiBroadcastDraft>({
      method: 'post',
      url: `/api/v1/broadcast/drafts/${draftId}/attachments`,
      data: formData,
    });
  }

  public deleteBroadcastDraftAttachment(
    scope: ApiBroadcastScope,
    draftId: number,
    attachmentId: number,
  ): Promise<ApiBroadcastDraft> {
    return this.delete(
      `/api/v1/broadcast/drafts/${draftId}/attachments/${attachmentId}?${this.toSearchParams(
        {
          bot_uuid: scope.bot_uuid,
          connector_id: scope.connector_id,
        },
      )}`,
    );
  }

  public updateBroadcastDraftText(
    scope: ApiBroadcastScope,
    draftId: number,
    draftText: string,
  ): Promise<ApiBroadcastDraft> {
    return this.requestBroadcast<ApiBroadcastDraft>({
      method: 'put',
      url: `/api/v1/broadcast/drafts/${draftId}`,
      data: {
        ...scope,
        draft_text: draftText,
      },
    });
  }

  public updateBroadcastDraftStatuses(
    scope: ApiBroadcastScope,
    draftIds: number[],
    status: ApiBroadcastDraftStatus,
  ): Promise<ApiBroadcastDraftStatusUpdateResult> {
    return this.requestBroadcast<ApiBroadcastDraftStatusUpdateResult>({
      method: 'post',
      url: '/api/v1/broadcast/drafts/batch-status',
      data: {
        ...scope,
        draft_ids: draftIds,
        status,
      },
    });
  }

  public createBroadcastExecutionBatch(
    scope: ApiBroadcastScope,
    payload: {
      draft_ids: number[];
      mode: 'paste_only' | 'send';
      operator: string;
      allow_sent_rewrite?: boolean;
    },
  ): Promise<ApiBroadcastExecutionBatch> {
    return this.requestBroadcast<ApiBroadcastExecutionBatch>({
      method: 'post',
      url: '/api/v1/broadcast/executions',
      data: {
        ...scope,
        ...payload,
      },
    });
  }

  public getBroadcastExecutionBatches(
    scope: ApiBroadcastScope,
  ): Promise<ApiBroadcastExecutionBatch[]> {
    return this.get('/api/v1/broadcast/executions', scope);
  }

  public clearBroadcastTerminalExecutionBatches(
    scope: ApiBroadcastScope,
  ): Promise<{
    deleted_batches: number;
    deleted_tasks: number;
    preserved_active_batches: number;
  }> {
    return this.delete(
      `/api/v1/broadcast/executions/terminal?${this.toSearchParams({
        bot_uuid: scope.bot_uuid,
        connector_id: scope.connector_id,
      })}`,
    );
  }
  public getBroadcastExecutionBatchDetail(
    scope: ApiBroadcastScope,
    batchId: number,
  ): Promise<ApiBroadcastExecutionBatch> {
    return this.get(`/api/v1/broadcast/executions/${batchId}`, scope);
  }

  public getBroadcastExecutionTaskDetail(
    scope: ApiBroadcastScope,
    taskId: number,
  ): Promise<ApiBroadcastExecutionTask> {
    return this.get(`/api/v1/broadcast/execution-tasks/${taskId}`, scope);
  }

  public startBroadcastExecutionBatch(
    scope: ApiBroadcastScope,
    batchId: number,
    operator: string,
  ): Promise<ApiBroadcastExecutionBatch> {
    return this.requestBroadcast<ApiBroadcastExecutionBatch>({
      method: 'post',
      url: `/api/v1/broadcast/executions/${batchId}/start`,
      data: {
        ...scope,
        operator,
      },
    });
  }

  public pauseBroadcastExecutionBatch(
    scope: ApiBroadcastScope,
    batchId: number,
    operator: string,
  ): Promise<ApiBroadcastExecutionBatch> {
    return this.requestBroadcast<ApiBroadcastExecutionBatch>({
      method: 'post',
      url: `/api/v1/broadcast/executions/${batchId}/pause`,
      data: {
        ...scope,
        operator,
      },
    });
  }

  public resumeBroadcastExecutionBatch(
    scope: ApiBroadcastScope,
    batchId: number,
    operator: string,
  ): Promise<ApiBroadcastExecutionBatch> {
    return this.requestBroadcast<ApiBroadcastExecutionBatch>({
      method: 'post',
      url: `/api/v1/broadcast/executions/${batchId}/resume`,
      data: {
        ...scope,
        operator,
      },
    });
  }

  public cancelBroadcastExecutionBatch(
    scope: ApiBroadcastScope,
    batchId: number,
    operator: string,
  ): Promise<ApiBroadcastExecutionBatch> {
    return this.requestBroadcast<ApiBroadcastExecutionBatch>({
      method: 'post',
      url: `/api/v1/broadcast/executions/${batchId}/cancel`,
      data: {
        ...scope,
        operator,
      },
    });
  }

  public startBroadcastExecutionTask(
    scope: ApiBroadcastScope,
    taskId: number,
    operator: string,
  ): Promise<ApiBroadcastExecutionTask> {
    return this.requestBroadcast<ApiBroadcastExecutionTask>({
      method: 'post',
      url: `/api/v1/broadcast/execution-tasks/${taskId}/start`,
      data: {
        ...scope,
        operator,
      },
    });
  }

  public retryBroadcastExecutionTask(
    scope: ApiBroadcastScope,
    taskId: number,
    operator: string,
  ): Promise<ApiBroadcastExecutionTask> {
    return this.requestBroadcast<ApiBroadcastExecutionTask>({
      method: 'post',
      url: `/api/v1/broadcast/execution-tasks/${taskId}/retry`,
      data: {
        ...scope,
        operator,
      },
    });
  }

  public getBroadcastExecutionAttempts(
    scope: ApiBroadcastScope,
    taskId: number,
  ): Promise<ApiBroadcastExecutionAttempt[]> {
    return this.get(
      `/api/v1/broadcast/execution-tasks/${taskId}/attempts`,
      scope,
    );
  }

  public getBroadcastExecutionAttemptDetail(
    scope: ApiBroadcastScope,
    attemptId: number,
  ): Promise<ApiBroadcastExecutionAttempt> {
    return this.get(`/api/v1/broadcast/execution-attempts/${attemptId}`, scope);
  }

  public getBroadcastExecutionEvidence(
    scope: ApiBroadcastScope,
    attemptId: number,
  ): Promise<ApiBroadcastExecutionEvidence> {
    return this.get(
      `/api/v1/broadcast/execution-attempts/${attemptId}/evidence`,
      scope,
    );
  }

  public getBroadcastExecutorCapabilities(
    scope: ApiBroadcastScope,
  ): Promise<Record<string, unknown>> {
    return this.get('/api/v1/broadcast/executors/capabilities', scope);
  }

  public getBroadcastExecutorHealth(
    scope: ApiBroadcastScope,
  ): Promise<Record<string, unknown>> {
    return this.get('/api/v1/broadcast/executors/health', scope);
  }
}

export interface SurveyQuestion {
  id: string;
  type: 'single_select' | 'multi_select' | 'text';
  title: Record<string, string>;
  subtitle?: Record<string, string>;
  required: boolean;
  options?: SurveyOption[];
  placeholder?: Record<string, string>;
  max_length?: number;
}

export interface SurveyOption {
  id: string;
  label: Record<string, string>;
  has_input?: boolean;
}
