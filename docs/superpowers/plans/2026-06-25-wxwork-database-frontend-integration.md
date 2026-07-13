# 前端闭环任务：企业微信数据库模式接入机器人模块

## 任务状态

**创建时间**: 2026-06-25
**后端完成**: ✅ 已提交 `aea75b09`
**前端状态**: 📋 待执行
**预计工作量**: 3-5天
**优先级**: P0

---

## 执行前提

### 后端状态
```
分支：codex/integrate-wechat-decrypt
提交：aea75b09
提交说明：feat(wxwork): integrate database mode with bot pipeline
```

### 后端已完成能力
- ✅ `wxwork_database` Adapter 实现
- ✅ Bot-scoped API (`/api/v1/bots/{bot_id}/*`)
- ✅ 自动草稿 TaskManager 调度
- ✅ MessageProcessingRun 和 ReplyDraft 模型
- ✅ 数据库级并发控制（原子领取）
- ✅ 旧 `database_mode` API 兼容层
- ✅ SSE 实时事件 (database-message-*)
- ✅ 正式 RuntimeBot/Pipeline 链路

### 工作区保护规则
**禁止修改的本地文件**:
```
docs/superpowers/plans/2026-06-23-local-connectors-builtin-mcp.md
tests/vendor_wechat_decrypt/test_wxwork_message_monitor.py
vendor/wechat_decrypt/connector_runtime.py
vendor/wechat_decrypt/decrypt_wxwork_db.py
vendor/wechat_decrypt/wxwork_message_monitor.py
.claude/
docs/superpowers/plans/2026-06-25-wxwork-database-channel-bot-processing.md
```

**严格禁止**:
- `git reset/restore/stash/checkout`
- 切换分支
- 覆盖Connector本地修复
- `git add .`
- commit/push
- 修改SSE连接生命周期

---

## 目标架构

### 最终产品结构
```
机器人模块
└── 企业微信数据库模式机器人
    ├── 配置 (tab=config)
    │   ├── 基础配置（名称、描述、启用）
    │   ├── 流水线配置（默认流水线、条件路由）
    │   ├── 数据库模式专属配置
    │   │   ├── Connector: wxwork-local
    │   │   ├── Connector状态
    │   │   ├── Monitor状态
    │   │   ├── 自动生成草稿开关
    │   │   └── 生效时间（只读）
    │   └── 删除机器人
    ├── 日志 (tab=logs)
    │   └── 复用现有BotLogListComponent
    └── 会话监控 (tab=sessions)
        ├── 左侧：会话列表
        │   ├── 搜索
        │   ├── 状态筛选
        │   ├── 会话项（名称、头像、最后消息、时间、pending数）
        │   └── 空状态/加载/错误
        └── 右侧：聊天与草稿工作区
            ├── 标题区（会话名、类型、状态）
            ├── 消息时间线
            │   ├── 客户消息气泡
            │   ├── AI草稿气泡
            │   └── 处理状态
            ├── AI操作区（6个卡片）
            │   ├── ✅ 智能回复（唯一可用）
            │   └── ⛔ 其他5个（禁用，显示"暂未开放"）
            ├── 草稿编辑区
            │   ├── 编辑/保存/取消
            │   ├── 复制
            │   ├── 版本和来源显示
            │   └── 重新生成
            └── 发送区
                └── ⛔ 发送按钮（禁用，tooltip提示）
```

### URL设计
```
普通机器人:
/home/bots?id={bot_uuid}&tab=config
/home/bots?id={bot_uuid}&tab=logs
/home/bots?id={bot_uuid}&tab=sessions  (使用原session API)

数据库模式机器人:
/home/bots?id={bot_uuid}&tab=config
/home/bots?id={bot_uuid}&tab=logs
/home/bots?id={bot_uuid}&tab=sessions  (使用Bot-scoped API)

旧路由重定向:
/home/database-mode → /home/bots?id={唯一启用的wxwork_database_bot}&tab=sessions
```

---

## 核心技术方案

### 1. 双数据源架构

#### 数据源抽象接口
```typescript
// web/src/app/home/bots/components/bot-session/types.ts

interface BotSessionDataSource {
  // 会话
  listConversations(params: ListConversationsParams): Promise<ConversationsResponse>;
  getConversation(conversationId: string): Promise<ConversationResponse>;

  // 消息
  listMessages(conversationId: string, params: ListMessagesParams): Promise<MessagesResponse>;

  // 草稿操作
  generateDraft(messageId: string): Promise<DraftResponse>;
  updateDraft(draftId: string, content: string): Promise<DraftResponse>;

  // 消息操作
  processMessage(messageId: string): Promise<void>;
  skipMessage(messageId: string): Promise<void>;
  deleteMessage(messageId: string): Promise<void>;

  // 批量操作
  batchProcess(messageIds: string[]): Promise<BatchResponse>;
  batchSkip(messageIds: string[]): Promise<BatchResponse>;
  batchDelete(messageIds: string[]): Promise<BatchResponse>;
}

type SessionMonitorSource = 'runtime' | 'database';

interface BotSessionMonitorProps {
  botId: string;
  botAdapter: string;
  botEnabled: boolean;
  source: SessionMonitorSource; // 根据adapter自动推断
}
```

#### 数据源实现
```typescript
// web/src/app/home/bots/components/bot-session/datasources/RuntimeBotDataSource.ts
class RuntimeBotDataSource implements BotSessionDataSource {
  // 使用现有 session API
  async listConversations() {
    return httpClient.listBotSessions(this.botId, ...);
  }
}

// web/src/app/home/bots/components/bot-session/datasources/DatabaseBotDataSource.ts
class DatabaseBotDataSource implements BotSessionDataSource {
  // 使用 Bot-scoped API
  async listConversations(params) {
    return httpClient.listBotConversations(this.botId, params);
  }

  async generateDraft(messageId) {
    return httpClient.generateBotDraft(this.botId, messageId);
  }

  // ... 其他方法
}

// web/src/app/home/bots/components/bot-session/datasources/createDataSource.ts
export function createDataSource(botAdapter: string, botId: string): BotSessionDataSource {
  if (botAdapter === 'wxwork_database') {
    return new DatabaseBotDataSource(botId);
  }
  return new RuntimeBotDataSource(botId);
}
```

### 2. Bot-scoped API封装

#### API客户端扩展
```typescript
// web/src/app/infra/http/HttpClient.ts (扩展现有类)

class HttpClient {
  // 现有方法保持不变...

  // ========= Bot-scoped Database Mode API =========

  /**
   * 获取机器人会话列表
   */
  async listBotConversations(
    botId: string,
    params?: {
      status?: string;
      keyword?: string;
      page?: number;
      page_size?: number;
    }
  ): Promise<BotConversationsResponse> {
    const query = new URLSearchParams();
    if (params?.status) query.append('status', params.status);
    if (params?.keyword) query.append('keyword', params.keyword);
    if (params?.page) query.append('page', params.page.toString());
    if (params?.page_size) query.append('page_size', params.page_size.toString());

    const url = `/api/v1/bots/${botId}/conversations?${query}`;
    return this.get(url);
  }

  /**
   * 获取机器人会话详情
   */
  async getBotConversation(
    botId: string,
    conversationId: string
  ): Promise<BotConversationResponse> {
    return this.get(`/api/v1/bots/${botId}/conversations/${conversationId}`);
  }

  /**
   * 获取机器人会话消息列表
   */
  async listBotMessages(
    botId: string,
    conversationId: string,
    params?: {
      status?: string;
      page?: number;
      page_size?: number;
    }
  ): Promise<BotMessagesResponse> {
    const query = new URLSearchParams();
    if (params?.status) query.append('status', params.status);
    if (params?.page) query.append('page', params.page.toString());
    if (params?.page_size) query.append('page_size', params.page_size.toString());

    const url = `/api/v1/bots/${botId}/conversations/${conversationId}/messages?${query}`;
    return this.get(url);
  }

  /**
   * 生成草稿
   */
  async generateBotDraft(
    botId: string,
    messageId: string
  ): Promise<GenerateDraftResponse> {
    return this.post(`/api/v1/bots/${botId}/messages/${messageId}/generate-draft`, {});
  }

  /**
   * 更新草稿
   */
  async updateBotDraft(
    botId: string,
    draftId: string,
    content: string
  ): Promise<UpdateDraftResponse> {
    return this.put(`/api/v1/bots/${botId}/drafts/${draftId}`, { content });
  }

  /**
   * 标记消息为已处理
   */
  async processBotMessage(
    botId: string,
    messageId: string
  ): Promise<void> {
    return this.post(`/api/v1/bots/${botId}/messages/${messageId}/process`, {});
  }

  /**
   * 跳过消息
   */
  async skipBotMessage(
    botId: string,
    messageId: string
  ): Promise<void> {
    return this.post(`/api/v1/bots/${botId}/messages/${messageId}/skip`, {});
  }

  /**
   * 删除消息
   */
  async deleteBotMessage(
    botId: string,
    messageId: string
  ): Promise<void> {
    return this.delete(`/api/v1/bots/${botId}/messages/${messageId}`);
  }

  /**
   * 批量处理
   */
  async batchProcessBotMessages(
    botId: string,
    messageIds: string[]
  ): Promise<BatchOperationResponse> {
    return this.post(`/api/v1/bots/${botId}/messages/batch-process`, { message_ids: messageIds });
  }

  /**
   * 批量跳过
   */
  async batchSkipBotMessages(
    botId: string,
    messageIds: string[]
  ): Promise<BatchOperationResponse> {
    return this.post(`/api/v1/bots/${botId}/messages/batch-skip`, { message_ids: messageIds });
  }

  /**
   * 批量删除
   */
  async batchDeleteBotMessages(
    botId: string,
    messageIds: string[]
  ): Promise<BatchOperationResponse> {
    return this.post(`/api/v1/bots/${botId}/messages/batch-delete`, { message_ids: messageIds });
  }
}
```

#### TypeScript类型定义
```typescript
// web/src/app/infra/http/types/bot-database.ts

export interface BotConversation {
  id: number;
  connector_id: string;
  source: string;
  external_conversation_id: string;
  conversation_name: string;
  conversation_type: 'direct' | 'group';
  last_message_at: string;
  pending_count: number;
  draft_ready_count: number;
  processed_count: number;
  failed_count: number;
  created_at: string;
  updated_at: string;
}

export interface BotConversationsResponse {
  conversations: BotConversation[];
  total: number;
  page: number;
  page_size: number;
}

export interface BotMessage {
  id: number;
  event_id: string;
  message_key: string;
  conversation_id: number;
  sender_id: string;
  sender_name: string;
  content: string;
  message_type: string;
  sent_at: string;
  observed_at: string;
  status: 'pending' | 'processing' | 'draft_ready' | 'processed' | 'skipped' | 'failed';
  draft_text?: string;
  draft_source?: 'pipeline' | 'manual';
  last_error?: string;
  attempt_count: number;
  processed_at?: string;
  created_at: string;
  updated_at: string;
}

export interface BotMessagesResponse {
  messages: BotMessage[];
  total: number;
  page: number;
  page_size: number;
  stats: {
    pending_count: number;
    draft_ready_count: number;
    processed_count: number;
    failed_count: number;
  };
}

export interface ReplyDraft {
  id: number;
  processing_run_id?: number;
  message_id: number;
  bot_uuid: string;
  content: string;
  source: 'pipeline' | 'manual';
  version: number;
  status: 'active' | 'superseded';
  created_at: string;
  updated_at: string;
}

export interface MessageProcessingRun {
  id: number;
  message_id: number;
  bot_uuid: string;
  pipeline_uuid?: string;
  trigger: 'manual' | 'automatic';
  status: 'processing' | 'succeeded' | 'failed';
  attempt_count: number;
  started_at?: string;
  completed_at?: string;
  last_error?: string;
}

export interface GenerateDraftResponse {
  status: 'succeeded' | 'already_succeeded' | 'processing';
  draft?: ReplyDraft;
  run?: MessageProcessingRun;
  message?: string;
}

export interface UpdateDraftResponse {
  message: BotMessage;
}

export interface BatchOperationResponse {
  messages: BotMessage[];
  succeeded: number;
  failed: number;
}
```

### 3. SSE事件处理

#### 保持现有useDatabaseModeEvents
```typescript
// web/src/app/home/database-mode/hooks/useDatabaseModeEvents.ts
// 【不修改此文件】

// 新增：包装hook用于Bot会话监控
// web/src/app/home/bots/components/bot-session/hooks/useBotDatabaseEvents.ts

import { useEffect } from 'react';
import { useDatabaseModeEvents } from '@/app/home/database-mode/hooks/useDatabaseModeEvents';

interface UseBotDatabaseEventsProps {
  botId: string;
  onMessageCreated?: (event: DatabaseModeEvent) => void;
  onMessageUpdated?: (event: DatabaseModeEvent) => void;
  onProcessingStarted?: (event: DatabaseModeEvent) => void;
  onProcessingFailed?: (event: DatabaseModeEvent) => void;
}

export function useBotDatabaseEvents({
  botId,
  onMessageCreated,
  onMessageUpdated,
  onProcessingStarted,
  onProcessingFailed,
}: UseBotDatabaseEventsProps) {
  const { subscribe, unsubscribe } = useDatabaseModeEvents();

  useEffect(() => {
    const handlers = {
      'database-message-created': onMessageCreated,
      'database-message-updated': onMessageUpdated,
      'database-processing-started': onProcessingStarted,
      'database-processing-failed': onProcessingFailed,
    };

    Object.entries(handlers).forEach(([eventType, handler]) => {
      if (handler) {
        subscribe(eventType, handler);
      }
    });

    return () => {
      Object.keys(handlers).forEach((eventType) => {
        unsubscribe(eventType);
      });
    };
  }, [botId, onMessageCreated, onMessageUpdated, onProcessingStarted, onProcessingFailed]);
}
```

### 4. 页签路由集成

#### 扩展BotDetailContent
```typescript
// web/src/app/home/bots/BotDetailContent.tsx

import { useSearchParams } from 'react-router-dom';

export default function BotDetailContent({ id, isCreateMode, refreshBots }: Props) {
  const [searchParams, setSearchParams] = useSearchParams();
  const activeTab = searchParams.get('tab') || 'config';

  const [bot, setBot] = useState<Bot | null>(null);

  // 加载bot信息
  useEffect(() => {
    if (!isCreateMode && id) {
      httpClient.getBot(id).then(res => setBot(res.bot));
    }
  }, [id, isCreateMode]);

  const handleTabChange = (value: string) => {
    setSearchParams({ id, tab: value });
  };

  return (
    <Tabs value={activeTab} onValueChange={handleTabChange}>
      <TabsList>
        <TabsTrigger value="config">配置</TabsTrigger>
        <TabsTrigger value="logs">日志</TabsTrigger>
        <TabsTrigger value="sessions">会话监控</TabsTrigger>
      </TabsList>

      <TabsContent value="config">
        <BotForm
          id={id}
          isCreateMode={isCreateMode}
          onSubmit={handleFormSubmit}
        />
      </TabsContent>

      <TabsContent value="logs">
        <BotLogListComponent botId={id} />
      </TabsContent>

      <TabsContent value="sessions">
        <BotSessionMonitor
          botId={id}
          botAdapter={bot?.adapter || ''}
          botEnabled={bot?.enable ?? true}
        />
      </TabsContent>
    </Tabs>
  );
}
```

### 5. 路由迁移

#### 旧路由重定向
```typescript
// web/src/router.tsx

// 添加重定向组件
function DatabaseModeRedirect() {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function redirect() {
      try {
        // 查找唯一启用的wxwork_database机器人
        const res = await httpClient.listBots();
        const databaseBots = res.bots.filter(
          (b: Bot) => b.adapter === 'wxwork_database' && b.enable
        );

        if (databaseBots.length === 1) {
          // 重定向到该机器人的会话监控
          navigate(`/home/bots?id=${databaseBots[0].uuid}&tab=sessions`, { replace: true });
        } else {
          // 重定向到机器人列表
          navigate('/home/bots', { replace: true });
          toast.info('请创建或启用"企业微信数据库模式"机器人');
        }
      } catch (error) {
        navigate('/home/bots', { replace: true });
        toast.error('加载机器人信息失败');
      } finally {
        setLoading(false);
      }
    }

    redirect();
  }, [navigate]);

  if (loading) {
    return <div>加载中...</div>;
  }

  return null;
}

// 在路由配置中添加
{
  path: '/home/database-mode',
  element: <DatabaseModeRedirect />
}
```

#### 移除侧边栏入口
```typescript
// web/src/app/home/components/home-sidebar/HomeSidebar.tsx

// 移除"数据库模式"导航项
// 删除或注释掉类似以下的代码：
// {
//   name: '数据库模式',
//   path: '/home/database-mode',
//   icon: DatabaseIcon,
// }
```

---

## 关键实现细节

### 智能回复实现
```typescript
// web/src/app/home/bots/components/bot-session/components/AIActions.tsx

function SmartReplyAction({ botId, messageId, disabled, onSuccess }: Props) {
  const [loading, setLoading] = useState(false);

  const handleGenerate = async () => {
    if (disabled || loading) return;

    setLoading(true);
    try {
      const result = await httpClient.generateBotDraft(botId, messageId);
