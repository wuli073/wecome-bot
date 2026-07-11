# 数据库机器人会话监控 UI 改造设计

## 背景

当前企业微信数据库模式机器人的“会话监控”界面在右侧聊天区中常驻显示整块 AI 操作卡片和大面积 Reply Draft 卡片。该结构占用较多纵向空间，和参考交互不一致，也弱化了“消息时间线 + 底部输入区”的主工作流。

本次改造目标是保留现有 Bot-scoped API、SSE、消息处理与草稿数据流，只重构数据库模式会话监控的前端交互形态：

- 移除常驻 AI 操作卡片区
- 引入贴底 Composer
- 通过魔法棒按钮弹出 AI 操作面板
- 将草稿展示改为 Composer 上方的紧凑预览卡
- 保持普通机器人会话监控完全不受影响

## 范围与非目标

### 范围

- 修改 `web/src/app/home/bots/components/bot-session/components/DatabaseBotSessionMonitor.tsx`
- 允许新增数据库模式专用 UI 子组件
- 允许补充对应前端测试

### 非目标

- 不修改后端 API、SSE 单例机制、DataSource 接口
- 不修改普通机器人 `BotSessionMonitor`
- 不实现真实发送
- 不实现除“智能回复”以外的其他 5 个 AI 功能
- 不引入新的 UI 框架

## 用户确认后的交互结论

### 当前消息选择规则

- 默认动作目标是当前会话中最后一条可处理消息
- 用户点击某条消息后，该消息成为显式当前消息
- 之后“智能回复”优先作用于显式当前消息
- 切换会话后清空显式当前消息，重新回到默认规则

### 草稿呈现规则

- 采用接近参考视频的交互
- 生成草稿后，不再使用独立的大型 Reply Draft 卡片
- 草稿显示为 Composer 上方的紧凑预览卡
- 底部输入框继续保留为轻量输入区

## 推荐方案

采用“右侧三段式工作区 + Composer 壳层”方案：

1. 会话头部
2. 消息滚动区
3. 底部 Composer

AI 操作通过 Composer 右侧魔法棒按钮触发 `Popover`，草稿通过 Composer 上方的紧凑卡片承载。

选择该方案的原因：

- 最贴近参考视频
- 消息区可获得更多高度
- 不需要碰后端或实时事件机制
- 可以把新增复杂度收敛到数据库模式专用组件中

## 组件设计

### 1. `DatabaseBotSessionMonitor`

职责：

- 保留页面级状态和数据请求编排
- 管理会话列表、消息列表、批量勾选、当前消息、草稿、生成状态、弹层状态、删除确认框
- 调用现有 `dataSource` 方法：
  - `listConversations`
  - `listMessages`
  - `generateDraft`
  - `updateDraft`
  - `processMessage`
  - `skipMessage`
  - `deleteMessage`
  - `batchProcess`
  - `batchSkip`
  - `batchDelete`

新增核心状态：

- `explicitSelectedMessageId: number | null`
- `aiPopoverOpen: boolean`
- `draftEditorOpen: boolean`
- `draftSaving: boolean`

派生状态：

- `defaultActionMessage`: 当前会话最后一条可处理消息
- `activeActionMessage`: 显式当前消息优先，否则回退到 `defaultActionMessage`

### 2. `DatabaseAiActionPopover`

职责：

- 展示 6 个 AI 操作入口
- 只负责 UI 和禁用态，不直接请求 API
- 通过回调把“智能回复”事件交回父组件处理

输入：

- `open`
- `onOpenChange`
- `botEnabled`
- `generatingDraft`
- `activeActionMessage`
- `onGenerateSmartReply`

行为：

- `智能回复` 为唯一可用项
- 其余 5 项保持禁用
- 5 个禁用项 Tooltip 固定显示 `暂未开放`
- 未选中目标消息且没有默认目标时，`智能回复` 禁用并显示 `请先选择一条待处理消息`
- Bot 禁用时，`智能回复` 禁用并显示 `请先启用机器人`

### 3. `DatabaseChatComposer`

职责：

- 承载紧凑草稿预览卡
- 承载底部轻量输入区
- 承载魔法棒按钮和禁用发送按钮

结构：

1. 草稿预览卡
   - 仅在存在活动草稿或生成中状态时显示
   - 展示来源、版本、更新时间
   - 默认显示正文预览
   - 进入编辑态后，正文区原地切换为 `Textarea`

2. 轻量 Composer
   - 左侧附件图标占位，不接真实功能
   - 中间多行输入框用于轻量输入与无草稿占位
   - 右侧为魔法棒按钮与禁用发送按钮

卡片右侧操作：

- `复制`
- `重新生成`
- `编辑`
- `保存`
- `取消`
- `标记已处理`
- `发送`（禁用）

## 页面布局

右侧区域改为：

```text
会话标题
消息时间线（独立滚动）
底部 Composer（固定或粘性停靠）
```

布局要求：

- 消息区占主要高度
- Composer 不随消息区一起滚走
- Popover 从 Composer 上方向上弹出
- 移除常驻 AI 卡片和空白 Draft 卡片后，消息区获得更多空间
- 不破坏现有复选框、process、skip、delete、批量操作

## 数据与状态流转

### 进入会话

- 拉取消息列表
- 从消息列表恢复当前 active draft
- 清空 `explicitSelectedMessageId`
- 计算 `defaultActionMessage`
- 关闭 AI Popover

### 用户点击消息

- 更新 `explicitSelectedMessageId`
- 仅改变 AI 操作目标消息
- 不影响现有批量复选框集合

### 用户点击“智能回复”

前置条件：

- 存在 `activeActionMessage`
- 目标消息允许生成草稿
- Bot 已启用
- 当前没有同一轮生成进行中

执行过程：

- 调用现有 Bot-scoped `generate-draft` API
- 保持既有正式 Pipeline 链路
- 显示生成中状态

成功后：

- 把返回的草稿渲染到紧凑预览卡
- 同步本地草稿内容与元数据
- 关闭 AI Popover

失败后：

- 保留当前输入与草稿编辑内容
- 显示错误提示
- 不触发真实发送

### SSE 更新

- 继续复用现有数据库模式事件订阅
- 不创建第二个 `EventSource`
- 收到消息更新后重新同步消息和活动草稿
- 若显式选中的消息失效，则回退到默认动作目标

### 切换会话

- 关闭 AI Popover
- 清空显式当前消息
- 重置编辑态、复制态、局部 loading 状态
- 装载新会话草稿
- 不把旧会话草稿带入新会话

## 可访问性与稳定性

必须满足：

- 所有关键按钮提供 `aria-label`
- 支持 Tab 聚焦
- `Enter` / `Space` 可触发魔法棒按钮
- `Esc` 关闭 Popover
- 焦点状态有清晰 `focus-visible`
- 禁用项不可通过键盘触发

实现约束：

- `PopoverTrigger`、`TooltipTrigger` 与 `Button` 组合时使用 `asChild`
- 不手写全局 document click 监听
- 不引入会导致重复渲染环的状态联动

重点避免的问题：

- `<button> cannot contain a nested <button>`
- `Maximum update depth exceeded`
- conversations/messages 重复请求
- 多开 SSE 连接

## 测试设计

至少覆盖以下断言：

1. 默认不显示常驻 AI 操作卡片
2. 点击魔法棒显示 Popover
3. 再次点击魔法棒关闭 Popover
4. 点击外部关闭 Popover
5. 按 `Esc` 关闭 Popover
6. 六项操作文案正确
7. 五个未开放功能保持禁用
8. 默认动作目标为最后一条可处理消息
9. 用户点击消息后切换为显式当前消息
10. Bot 禁用时“智能回复”不可用
11. 智能回复成功后显示紧凑草稿预览卡
12. 智能回复失败后保留当前输入
13. 发送按钮始终禁用
14. 切换会话后关闭 Popover 且不串草稿
15. 普通机器人不会渲染数据库模式 Composer
16. 不产生嵌套 button 结构

## 实施顺序

1. 从 `DatabaseBotSessionMonitor` 中移除常驻 AI 卡片和大型 Draft 卡片
2. 提取 `DatabaseAiActionPopover`
3. 提取 `DatabaseChatComposer`
4. 增加“当前消息”单独高亮逻辑
5. 把智能回复结果改接到紧凑草稿预览卡
6. 补测试并执行前端校验

## 风险与控制

### 风险 1：草稿状态和 SSE 回流重复覆盖

控制：

- 以当前会话为边界同步草稿
- 本地编辑态下避免无条件覆盖输入内容

### 风险 2：当前消息选择与批量勾选互相干扰

控制：

- 显式当前消息和批量勾选维持两套独立状态

### 风险 3：Popover / Tooltip / Button 组合引入非法 DOM

控制：

- 新组件统一采用 `asChild`
- 在测试中覆盖相关结构

## 验收结果定义

实现完成后应满足：

- 右侧界面呈现“消息时间线 + 底部 Composer”主结构
- AI 操作仅通过魔法棒弹出
- 草稿以紧凑预览卡展示
- 智能回复仍走原有 Bot-scoped API
- 普通机器人界面无回归
- ESLint、TypeScript、Build 通过
