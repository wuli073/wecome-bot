# Broadcast Phase 3 Design

## 1. 背景与目标

Broadcast Phase 1 已完成前端工作区与页面结构，Phase 2 已完成变量配置、消息模板、群匹配规则、群名称及其真实持久化与基础模板渲染能力。Phase 3 的目标是在现有 Broadcast 域内继续扩展真实导入与真实草稿能力，将“导入匹配”和“审核发送”从示例数据切换为真实数据，并保持与当前 `(bot_uuid, connector_id)` 作用域隔离模型一致。

Phase 3 只负责：

- 文件导入与解析
- 导入数据持久化
- 按最新变量配置重新计算分组与匹配
- 真实草稿生成、重生成、编辑、确认与撤回确认
- 审核页展示真实草稿与失败项

Phase 3 不进入执行阶段，不调用任何桌面 Runtime，不写入企业微信输入框，不发送消息。

---

## 2. Phase 3 范围

### 2.1 包含范围

- 新增导入批次、导入行、群发草稿三类持久化实体
- 新增对应 Migration
- 新增 Imports 与 Drafts API
- 支持上传 `.csv` 与 `.xlsx`
- 支持重新匹配
- 支持按模板生成真实草稿
- 支持在审核页查看、编辑、确认、撤回确认草稿
- 支持 `drafts_stale` 过期标记与前端禁用
- 补齐单元、集成、Migration、E2E 测试

### 2.2 明确非目标

- 不调用 Runtime
- 不调用 `paste-draft`
- 不调用 `send-draft`
- 不进入 Phase 4 批量写入逻辑
- 不进入 Phase 5 执行队列
- 不进入 Phase 6 自动发送
- 不修改 MCP、skills、agent tools
- 不修改 `apps/desktop-rpa-runtime/**`
- 不修改 `src/langbot/pkg/desktop_automation/**`
- 不修改现有 `0013_broadcast_rules.py`
- 不进行与 Phase 3 无关的架构重构

---

## 3. 最终架构决策

Phase 3 继续扩展现有 Broadcast 域，不新建独立子系统，不引入新的全局执行链路。

职责固定如下：

- `repository.py`：只负责数据访问
- `service.py`：负责事务边界、流程编排、双层作用域校验与业务规则
- `file_parser.py`：只负责文件解析与基础清洗，不负责数据库事务
- `import_processor.py`：负责字段校验、行级分类、统计口径与重匹配计算
- `group_matcher.py`：负责群聊匹配
- `draft_generator.py`：负责分组聚合、五种变量合并、模板渲染结果与草稿生成计算
- `broadcast.py` Router：只负责收参与错误映射，不承载业务规则

---

## 4. 数据模型与字段

### 4.1 `BroadcastImportBatch`

用途：记录一次导入操作及其批次级统计信息。

字段：

- `id`: `Integer`, 主键
- `bot_uuid`: `String(255)`, 非空
- `connector_id`: `String(255)`, 非空
- `original_file_name`: `String(255)`, 非空
- `file_type`: `String(32)`, 非空，取值为 `csv` 或 `xlsx`
- `worksheet_name`: `String(255)`, 可空；CSV 为 `NULL`，XLSX 记录实际工作表名
- `status`: `String(32)`, 非空，取值固定为：
  - `imported`
  - `matched`
  - `drafts_generated`
- `drafts_stale`: `Boolean`, 非空，默认 `false`
- `total_rows`: `Integer`, 非空，默认 `0`
- `valid_rows`: `Integer`, 非空，默认 `0`
- `invalid_rows`: `Integer`, 非空，默认 `0`
- `matched_rows`: `Integer`, 非空，默认 `0`
- `unmatched_rows`: `Integer`, 非空，默认 `0`
- `created_at`: `DateTime`, 非空
- `updated_at`: `DateTime`, 非空

状态含义：

- `imported`：文件已导入并完成初次分类
- `matched`：已执行重新匹配流程；该状态表示匹配流程已执行，不表示所有数据都匹配成功
- `drafts_generated`：已成功生成当前批次草稿

`drafts_stale` 含义：

- `false`：当前批次没有待废弃旧草稿
- `true`：当前批次存在因重新匹配而过期的旧草稿，前端必须提示重新生成草稿

### 4.2 `BroadcastImportRow`

用途：保存导入文件中的每一条数据行及其最新匹配结果。

字段：

- `id`: `Integer`, 主键
- `import_batch_id`: `Integer`, 非空，外键到 `broadcast_import_batches.id`
- `source_row_number`: `Integer`, 非空，保留原始文件真实行号
- `raw_data`: `JSON`, 非空，保存清洗后的“表头 -> 值”映射
- `group_value`: `String(255)`, 可空，保存按当前 `group_field` 提取后的值
- `matched_conversation_name`: `String(255)`, 可空
- `matched_rule_id`: `Integer`, 可空，外键到 `broadcast_group_rules.id`
- `match_status`: `String(32)`, 非空，取值固定为：
  - `matched`
  - `unmatched`
  - `invalid`
- `error_message`: `Text`, 可空，面向用户的中文错误原因
- `created_at`: `DateTime`, 非空

### 4.3 `BroadcastDraft`

用途：保存按分组聚合后生成的真实草稿与失败项。

字段：

- `id`: `Integer`, 主键
- `bot_uuid`: `String(255)`, 非空
- `connector_id`: `String(255)`, 非空
- `import_batch_id`: `Integer`, 非空，外键到 `broadcast_import_batches.id`
- `group_value`: `String(255)`, 非空
- `target_conversation_name`: `String(255)`, 可空；未匹配分组生成失败草稿时必须允许为 `NULL`
- `template_id`: `Integer`, 可空，外键到 `broadcast_templates.id`
- `template_name_snapshot`: `String(255)`, 非空
- `template_content_snapshot`: `Text`, 非空
- `render_variables`: `JSON`, 非空，键必须使用用户配置的 `variable_key`
- `draft_text`: `Text`, 非空
- `status`: `String(32)`, 非空，取值固定为：
  - `pending_review`
  - `ready`
  - `invalid`
- `error_message`: `Text`, 可空
- `created_at`: `DateTime`, 非空
- `updated_at`: `DateTime`, 非空

`render_variables` 示例：

```json
{
  "客户名称": "某客户A",
  "订单号": "SO-001\nSO-002",
  "联系人": "张三,李四"
}
```

模板渲染必须基于 `variable_key`：

- `{{客户名称}}`
- `{{订单号}}`
- `{{联系人}}`

除非用户配置的 `variable_key` 本身就是 `customer_name`、`order_no` 等英文键，否则不得擅自改写键名。

---

## 5. 索引、唯一约束与外键删除行为

### 5.1 索引

`BroadcastImportBatch`：

- 索引：`bot_uuid`
- 索引：`connector_id`
- 组合索引：`(bot_uuid, connector_id)`
- 索引：`created_at`

`BroadcastImportRow`：

- 索引：`import_batch_id`
- 索引：`match_status`
- 索引：`group_value`

`BroadcastDraft`：

- 索引：`bot_uuid`
- 索引：`connector_id`
- 组合索引：`(bot_uuid, connector_id)`
- 索引：`import_batch_id`
- 索引：`status`
- 索引：`updated_at`

### 5.2 唯一约束

`BroadcastImportRow`：

- 唯一约束：`(import_batch_id, source_row_number)`

`BroadcastDraft`：

- 唯一约束：`(import_batch_id, group_value)`

该约束用于保证同一批次同一分组最多只生成一条草稿，避免重生成后产生重复草稿。

### 5.3 外键删除行为

- `BroadcastImportRow.import_batch_id -> BroadcastImportBatch.id`
  - `ON DELETE CASCADE`
- `BroadcastDraft.import_batch_id -> BroadcastImportBatch.id`
  - `ON DELETE CASCADE`
- `BroadcastImportRow.matched_rule_id -> BroadcastGroupRule.id`
  - `ON DELETE SET NULL`
- `BroadcastDraft.template_id -> BroadcastTemplate.id`
  - `ON DELETE SET NULL`

固定原因：

- 删除群匹配规则不能删除历史导入行，也不能阻止规则删除
- 删除模板不能删除历史草稿，因为草稿已保存模板名称快照、模板内容快照、渲染变量与最终正文
- 删除导入批次时，导入行和草稿必须自动级联清理，避免残留孤立数据

---

## 6. Migration 要求

- 新增独立 Phase 3 Migration，不修改现有 `0013_broadcast_rules.py`
- revision id 长度不得超过 32 字符
- 必须同时实现 `upgrade()` 与 `downgrade()`
- 新表必须注册进 ORM metadata
- 对 SQLite 与 PostgreSQL 都必须通过 Migration 测试
- 保持单一线性 head，不创建分叉
- 所有 `add_column`、`drop_column`、`create_table`、`drop_table` 操作都要做存在性防护
- 必须覆盖以下外键行为测试：
  - `matched_rule_id ON DELETE SET NULL`
  - `template_id ON DELETE SET NULL`
  - `import_batch -> import_rows ON DELETE CASCADE`
  - `import_batch -> drafts ON DELETE CASCADE`

---

## 7. 文件解析方案

### 7.1 支持格式

Phase 3 必须支持：

- `.csv`
- `.xlsx`

`.xls` 不在 Phase 3 范围内；除非项目中已存在安全、轻量且确认可用的解析依赖，否则不得为 `.xls` 单独新增重型依赖。

### 7.2 文件解析与数据库事务关系

关键决策：**文件解析在数据库写事务之外完成。**

固定流程：

1. 作用域校验
2. 文件大小校验
3. 文件类型校验
4. 文件解析
5. 表头与字段校验
6. 打开数据库写事务
7. 创建导入批次
8. 创建导入行
9. 更新统计
10. 提交事务

这样可以避免：

- 解析 CSV/XLSX 时长时间占用数据库连接
- 文件解析失败后仍遗留半批数据库数据

### 7.3 文件大小与行数限制

- 文件最大：`10MB`
- 最大数据行数：`10000`

“数据行数”定义为：去掉表头且忽略完全空白行后剩余的行数。

### 7.4 CSV 解析规则

- 支持 UTF-8
- 支持 UTF-8 BOM
- 第一行为表头
- 表头自动 `trim`
- 单元格值按普通文本读取
- 完全空白行忽略
- 不执行任何公式、宏或脚本

### 7.5 XLSX 解析规则

- 读取首个工作表
- 记录 `worksheet_name`
- 第一行为表头
- 表头自动 `trim`
- 单元格值按普通文本读取
- 完全空白行忽略
- 不执行任何公式、宏或脚本
- 文件损坏时返回明确中文错误

### 7.6 统一解析输出

`file_parser.py` 的输出必须是与数据库无关的中间结构：

```python
{
  "file_type": "csv" | "xlsx",
  "worksheet_name": str | None,
  "headers": list[str],
  "rows": [
    {
      "source_row_number": int,
      "raw_data": dict[str, str]
    }
  ]
}
```

`raw_data` 的键为清洗后的表头，值为清洗后的字符串值。

---

## 8. 表头与字段校验

### 8.1 表头校验

表头在 `trim` 后必须满足：

- 不允许空表头
- 不允许重复表头
- `trim` 后冲突也视为重复

例如以下两列表头：

- `客户名称`
- ` 客户名称 `

必须拒绝并返回：

`导入文件存在重复字段：客户名称`

这样可以避免 `raw_data` 在构建字典时静默覆盖。

### 8.2 上传时字段校验

上传文件时必须校验：

- 当前作用域下已存在变量对应配置
- 当前变量对应配置中已设置 `group_field`
- 导入文件包含当前 `group_field`
- 导入文件包含当前所有 `mapping_rules[].source_field`

上传阶段**不要求**必须选定模板；模板有效性在生成草稿时单独校验。

### 8.3 重新匹配时字段校验

重新匹配必须使用**当前最新变量配置**重新校验字段，并重新执行：

1. 读取当前 `group_field`
2. 从 `raw_data` 重新提取 `group_value`
3. 重新判断 `invalid / unmatched / matched`
4. 重新执行群聊匹配

若当前配置中的下列字段不在原始导入数据中：

- 当前 `group_field`
- 任一 `mapping_rules[].source_field`

则必须整批拒绝重新匹配，并明确提示缺少哪些字段，不能把整批数据静默改成 `invalid`。

---

## 9. 批次统计口径

固定统计公式如下：

- `total_rows = 排除表头和完全空白行后的数据行数`
- `valid_rows + invalid_rows = total_rows`
- `matched_rows + unmatched_rows + invalid_rows = total_rows`

其中：

- `valid_rows = matched_rows + unmatched_rows`
- 分组值为空的行记为 `invalid`
- 数据有效但未找到群聊的行记为 `unmatched`
- 成功确定目标群聊的行记为 `matched`

同一行不得同时计入多个统计类别。

---

## 10. 分组与五种变量合并算法

### 10.1 分组规则

草稿生成时，必须按当前变量对应配置中的 `group_field` 对当前批次导入行分组。

分组值计算规则：

1. 从 `raw_data[group_field]` 取值
2. 转成字符串
3. `trim`
4. 若为空，则该行记为 `invalid`
5. 若非空，则写入 `group_value`

分组要求：

- 只在当前批次内分组
- 不跨 bot
- 不跨 connector
- 同组内保持原文件顺序
- 保留真实 `source_row_number`

### 10.2 变量上下文键名

关键决策：**`render_variables` 必须使用用户配置的 `variable_key` 作为键。**

不得使用 `source_field` 作为键，也不得默认改写成英文键。

### 10.3 合并前预处理

对于分组内每个待合并值：

- 转成字符串
- `trim`
- 空字符串丢弃
- 不生成 `"None"`
- 不生成 `"null"`

### 10.4 五种合并模式

#### `first`

取第一条非空值。

#### `lines`

按原顺序用换行符 `\n` 连接所有非空值。

#### `unique_lines`

按原顺序去重后，用换行符 `\n` 连接。

#### `commas`

按原顺序用英文逗号 `,` 连接所有非空值。

#### `unique_commas`

按原顺序去重后，用英文逗号 `,` 连接。

### 10.5 去重规则

`unique_lines` 与 `unique_commas` 去重时，必须保留首次出现顺序。

### 10.6 合并输出

生成草稿时，变量上下文必须以 `variable_key -> 合并结果` 的形式输出。

---

## 11. 群聊匹配优先级与同名兜底

匹配时只使用当前作用域下启用的规则，顺序固定为：

1. 只使用 `enabled = true` 的规则
2. 按 `priority desc`
3. `priority` 相同时按 `id asc`
4. 命中第一条后立即停止

支持的匹配方式：

- `exact`
- `contains`
- `regex`

正则规则要求：

- 创建或更新规则时预先校验表达式合法性
- 同一次匹配流程内缓存编译结果，避免重复编译

若没有任何规则命中，则执行同名群聊兜底：

- 若 `group_value` 与已保存群名称完全一致，则直接匹配该群聊
- 否则记为 `unmatched`

---

## 12. 重新匹配规则

### 12.1 禁止条件

若该批次存在任意 `ready` 草稿，则禁止重新匹配，并返回固定中文提示：

`当前批次存在已确认草稿，请先撤回确认后再重新匹配。`

### 12.2 允许条件

若该批次不存在 `ready` 草稿，则允许重新匹配。

重新匹配必须使用最新配置重新执行：

- `group_field`
- 变量对应配置
- 群匹配规则
- 群名称列表

### 12.3 重新匹配后的批次状态

重新匹配成功后：

- `status = matched`

### 12.4 `drafts_stale` 规则

关键决策：**`drafts_stale` 仅在已有旧草稿时因重新匹配而置为 `true`。**

规则固定为：

- 若该批次在重新匹配前已存在 `pending_review` 或 `invalid` 草稿：
  - `drafts_stale = true`
- 若该批次从未生成过草稿：
  - `drafts_stale = false`

### 12.5 旧草稿处理方式

重新匹配成功后，不删除旧的 `pending_review` 或 `invalid` 草稿，但它们必须被视为过期：

- 前端不得继续确认
- 前端不得继续执行
- 前端必须明确提示：
  - `匹配结果已更新，请重新生成草稿。`

---

## 13. 草稿生成与重生成规则

### 13.1 生成前校验

生成草稿前必须校验：

- 当前批次属于当前 `(bot_uuid, connector_id)` 作用域
- 模板存在且属于当前作用域
- 当前作用域存在变量对应配置
- 当前 `group_field` 存在
- 当前批次不存在任意 `ready` 草稿

若存在任意 `ready` 草稿，则禁止重新生成，并返回固定中文提示：

`当前批次存在已确认草稿，请先撤回确认后再重新生成。`

### 13.2 草稿生成规则

对当前批次分组后，每个分组只生成一条草稿，对应唯一约束 `(import_batch_id, group_value)`。

每个分组的结果固定为：

所有 `invalid` 草稿的正文保存统一遵循以下规则：

- `draft_text` 数据库字段继续保持非空约束；
- 系统生成 `invalid` 草稿时允许 `draft_text = ''`；
- “草稿正文不能为空”只适用于用户通过 `PUT /api/v1/broadcast/drafts/{draft_id}` 主动编辑保存；
- 只要模板仍能产出可查看正文或预览正文，就必须写入 `draft_text`；
- 只有渲染完全失败、无法得到任何可查看正文时，才允许写入空字符串，并将明确中文原因写入 `error_message`。

#### 正常生成

满足以下条件时生成 `pending_review` 草稿：

- 已确定目标群聊
- 模板变量齐全
- 渲染后无占位符残留

#### 未匹配分组

关键决策：**未匹配分组生成 `invalid` 草稿。**

规则固定为：

- `target_conversation_name = NULL`
- `status = invalid`
- `error_message = 未匹配到群聊`
- 未匹配群聊但模板可渲染时，`draft_text` 仍保存当前分组的渲染正文

未匹配分组必须同时：

- 保留在导入结果中
- 出现在审核页失败项中
- 不允许确认
- 不进入执行链路

#### 缺少变量

若模板缺少变量值，则生成 `invalid` 草稿，并返回明确错误：

`模板缺少以下变量值：订单号、联系人`

缺少变量时仍必须：

- 在 `draft_text` 中保存可查看的预览正文；
- 允许预览正文保留尚未替换的 `{{变量}}` 占位符，供审核页查看；
- 不得因为缺少变量而将 `draft_text` 静默写成空字符串。

#### 渲染后残留占位符

若最终正文仍包含未替换的 `{{变量}}` 占位符，则生成 `invalid` 草稿，并且：

- `draft_text` 必须保存可查看的预览正文；
- 不得静默替换为空字符串。

#### 渲染完全失败

若模板渲染过程本身完全失败，且无法得到任何可查看的预览正文，则生成 `invalid` 草稿，并且：

- `draft_text = ''`
- `error_message` 写入明确中文原因

### 13.3 草稿统计

生成草稿接口返回的统计字段固定为：

- `total_group_count`
- `pending_review_count`
- `invalid_count`
- `unmatched_group_count`

不得使用语义模糊且同时混合成功与失败的 `generated_count`。

### 13.4 重生成策略

关键决策：**重生成在单事务内删除旧草稿并重建。**

固定流程：

1. 检查是否存在任意 `ready` 草稿
2. 若存在则拒绝
3. 若不存在，则在同一事务中删除该批次所有旧草稿
4. 重新生成整批草稿
5. 任一步失败则整体回滚
6. 成功后：
   - `status = drafts_generated`
   - `drafts_stale = false`

必须保证：

- 不保留半批数据
- 不产生重复草稿

---

## 14. 草稿状态与状态转换

草稿状态固定为：

- `pending_review`
- `ready`
- `invalid`

允许的状态转换固定为：

- `pending_review -> ready`
- `ready -> pending_review`

其中 `ready -> pending_review` 既可由“撤回确认”触发，也可由“编辑正文”触发。

不允许的状态转换：

- `invalid -> ready`
- `invalid -> pending_review`
- 任意未定义状态

关键决策：**`invalid` 草稿不可通过编辑正文后直接确认。**

即使用户手工编辑了 `draft_text`，也不得绕过生成错误直接将 `invalid` 草稿确认成 `ready`。

草稿编辑规则固定为：

- 编辑 `pending_review` 草稿后仍为 `pending_review`；
- 编辑 `ready` 草稿后自动退回 `pending_review`；
- 编辑 `ready` 草稿成功后，接口必须返回中文提示：`草稿内容已修改，请重新确认`；
- 编辑 `invalid` 草稿后仍为 `invalid`；
- `invalid` 草稿不能通过编辑正文绕过错误直接确认。

---

## 15. 事务边界与回滚要求

### 15.1 上传导入

数据库事务只覆盖：

- 创建批次
- 创建导入行
- 更新统计

文件解析、表头校验、字段校验都发生在事务外。

### 15.2 重新匹配

单事务覆盖：

- 校验批次归属
- 重新计算 `group_value`
- 重新分类 `invalid / unmatched / matched`
- 重新执行群聊匹配
- 更新导入行结果
- 更新批次 `status` 与 `drafts_stale`

### 15.3 生成或重生成草稿

单事务覆盖：

- 检查旧草稿状态
- 删除旧草稿
- 写入新草稿
- 更新批次状态

### 15.4 草稿批量状态更新

单事务覆盖：

- 校验所有 `draft_ids` 归属
- 校验所有状态变更合法
- 批量更新状态

### 15.5 删除导入批次

单事务覆盖：

- 删除批次
- 由数据库 `ON DELETE CASCADE` 清理导入行与草稿

### 15.6 回滚要求

所有上述事务必须满足：

- 任一步失败则整体回滚
- 不允许半批提交
- 捕获异常后不得继续提交
- 不混用不同连接对象执行同一事务

---

## 16. 双层作用域校验

Phase 3 继续使用双层作用域校验。

### 16.1 第一层：Scope 校验

统一复用 `BroadcastService.validate_scope()` 校验：

- `bot_uuid` 存在
- `connector_id` 存在
- bot 存在
- bot 类型为 `wxwork_database`
- connector 与 bot 绑定一致

### 16.2 第二层：资源归属校验

对每次资源操作必须再校验资源本身属于当前 `(bot_uuid, connector_id)`：

- import
- draft
- template
- rule

GET、POST、PUT、DELETE 均不得绕过作用域。

---

## 17. Imports 与 Drafts API

### 17.1 Imports API

#### `POST /api/v1/broadcast/imports`

用途：上传导入文件。

请求：

- `multipart/form-data`
- 字段：
  - `bot_uuid`
  - `connector_id`
  - `file`

返回：

- 批次信息
- 批次统计
- 首屏预览行

#### `GET /api/v1/broadcast/imports`

用途：查询当前作用域下导入批次列表。

查询参数：

- `bot_uuid`
- `connector_id`

#### `GET /api/v1/broadcast/imports/{import_id}`

用途：查询单个导入批次详情与预览。

查询参数可包含：

- `bot_uuid`
- `connector_id`
- `match_status`
- `keyword`
- `page`
- `page_size`

#### `DELETE /api/v1/broadcast/imports/{import_id}`

用途：删除导入批次及其关联导入行与草稿。

#### `POST /api/v1/broadcast/imports/{import_id}/rematch`

用途：使用最新变量配置、群规则和群名称重新匹配。

返回：

- 更新后的批次统计
- `drafts_stale`
- 预览数据摘要

#### `POST /api/v1/broadcast/imports/{import_id}/generate-drafts`

用途：为指定批次按指定模板生成或重生成草稿。

JSON 请求体：

- `bot_uuid`
- `connector_id`
- `template_id`

返回：

- `total_group_count`
- `pending_review_count`
- `invalid_count`
- `unmatched_group_count`

### 17.2 Drafts API

#### `GET /api/v1/broadcast/drafts`

用途：查询草稿列表。

查询参数：

- `bot_uuid`
- `connector_id`
- `import_batch_id`
- `status`
- `keyword`

#### `GET /api/v1/broadcast/drafts/{draft_id}`

用途：查询草稿详情。

返回内容包含：

- 正文
- 渲染变量
- 模板快照
- 目标群聊
- 错误原因

#### `PUT /api/v1/broadcast/drafts/{draft_id}`

用途：编辑草稿正文。

JSON 请求体：

- `bot_uuid`
- `connector_id`
- `draft_text`

规则：

- “草稿正文不能为空”仅适用于用户主动编辑保存
- 不允许只包含空格
- 编辑 `pending_review` 草稿后仍为 `pending_review`
- 编辑 `ready` 草稿后自动退回 `pending_review`
- 编辑 `ready` 草稿成功后，响应中必须返回中文提示：`草稿内容已修改，请重新确认`
- 编辑 `invalid` 草稿后仍为 `invalid`
- `invalid` 草稿不能通过编辑正文绕过错误直接确认

#### `POST /api/v1/broadcast/drafts/batch-status`

用途：批量确认或撤回确认草稿。

JSON 请求体：

- `bot_uuid`
- `connector_id`
- `draft_ids`
- `status`

仅允许：

- `pending_review -> ready`
- `ready -> pending_review`

---

## 18. 中文错误响应

响应结构固定为：

```json
{
  "code": -1,
  "msg": "ERROR_CODE",
  "message": "中文概述",
  "details": ["中文细节1", "中文细节2"]
}
```

### 18.1 必须覆盖的错误场景与中文提示

- 文件格式不支持：
  - `不支持的文件格式，请上传 CSV 或 XLSX 文件`
- 文件超过 10MB：
  - `文件大小超过限制，请上传 10MB 以内的文件`
- 超过 10000 行：
  - `导入数据超过 10000 行上限，请拆分后重试`
- 文件为空：
  - `导入文件为空，请检查文件内容`
- 文件损坏：
  - `导入文件已损坏，无法读取，请重新导出后再试`
- 工作表为空：
  - `导入文件没有可读取的数据`
- 空表头：
  - `导入文件存在空字段名，请检查表头后重试`
- 重复表头：
  - `导入文件存在重复字段：客户名称`
- 未配置变量对应表：
  - `请先配置变量对应关系后再导入文件`
- 未配置分组字段：
  - `请先设置客户分组字段后再导入文件`
- 导入缺少字段：
  - `导入文件缺少以下字段：客户名称、订单号`
- 重新匹配缺少字段：
  - `当前导入数据缺少以下字段，无法重新匹配：客户名称、订单号`
- 模板不存在或不属于当前作用域：
  - `当前模板不存在或已被删除`
- 存在 `ready` 草稿禁止重新匹配：
  - `当前批次存在已确认草稿，请先撤回确认后再重新匹配。`
- 存在 `ready` 草稿禁止重新生成：
  - `当前批次存在已确认草稿，请先撤回确认后再重新生成。`
- 草稿正文为空：
  - `草稿正文不能为空`
- 非法草稿状态：
  - `草稿状态无效，请刷新后重试`
- `invalid` 草稿尝试确认：
  - `当前草稿生成失败，不能直接确认，请修复配置后重新生成`
- `drafts_stale = true` 的草稿尝试确认：
  - `当前草稿已过期，请重新生成草稿后再确认`
- 未匹配到群聊：
  - `未匹配到群聊`
- 模板缺少变量：
  - `模板缺少以下变量值：订单号、联系人`
- 渲染残留占位符：
  - `草稿中仍存在未替换内容，请检查变量配置后重新生成`
- 批量状态更新包含非当前作用域 id：
  - `所选草稿中包含无权操作的数据，请刷新后重试`

所有 `message` 与 `details` 必须优先面向普通用户，不得直接暴露 Python 异常、SQLAlchemy 异常、内部错误码、原始请求结构。

---

## 19. 前端交互与按钮禁用规则

### 19.1 导入匹配页

必须提供：

- 文件选择或拖拽上传
- 文件名与大小展示
- 上传状态
- 导入批次列表
- 批次统计
- 导入数据预览
- 匹配状态筛选
- 模板选择
- 重新匹配
- 生成草稿

必须显示：

- 已匹配
- 未匹配
- 无效

不得静默隐藏失败项。

### 19.2 `drafts_stale` 提示

当：

- `status = matched`
- 且 `drafts_stale = true`

前端必须明确提示：

`匹配结果已更新，请重新生成草稿。`

若该批次从未生成过草稿，则 `drafts_stale = false`，不得显示误导性过期提示。

### 19.3 审核页

必须支持：

- 按导入批次筛选
- 按状态筛选
- 按客户或群聊名称搜索
- 查看草稿正文
- 查看渲染变量
- 查看目标群聊
- 查看模板名称
- 查看生成错误
- 编辑保存正文
- 确认草稿
- 撤回确认
- 批量确认

交互规则固定为：

- 编辑 `pending_review` 草稿后，列表与详情中的状态保持 `pending_review`；
- 编辑 `ready` 草稿后，列表与详情中的状态必须立即刷新为 `pending_review`；
- 编辑 `ready` 草稿成功后，前端必须展示中文提示：`草稿内容已修改，请重新确认`；
- 编辑 `invalid` 草稿后，列表与详情中的状态仍为 `invalid`；
- `invalid` 草稿保存后，确认按钮与批量确认入口继续保持禁用；
- 若当前筛选条件为“已确认”，则 `ready` 草稿保存成功后必须即时移出该筛选结果，或即时刷新为“待审核”状态。

### 19.4 按钮禁用规则

#### `invalid` 草稿

- 可查看错误原因
- 不允许确认
- 不允许批量确认
- 即使编辑正文后，也不能直接确认

#### `drafts_stale = true` 的草稿

- 不允许确认
- 不允许批量确认
- 必须提示重新生成

#### 执行相关按钮

当前阶段全部禁用，并显示：

`该功能将在下一阶段开放`

点击不得发送任何执行请求。

### 19.5 中文化约束

用户界面不得直接显示：

- API
- Payload
- Runtime
- Mock
- JSON 字段名
- 数据库枚举值
- Python 异常
- SQLAlchemy 异常
- 内部错误码

若需保留技术细节，只能放在默认收起的“查看技术详情”中。

---

## 20. 测试设计

### 20.1 单元测试

目录：

- `tests/unit_tests/broadcast/test_file_parser.py`
- `tests/unit_tests/broadcast/test_import_processor.py`
- `tests/unit_tests/broadcast/test_group_matcher.py`
- `tests/unit_tests/broadcast/test_draft_generator.py`
- `tests/unit_tests/broadcast/test_service.py`

覆盖要求：

#### 文件解析

- 正常 CSV
- 正常 XLSX
- UTF-8 CSV
- UTF-8 BOM CSV
- 空文件
- 无表头
- 空表头
- 重复表头
- `trim` 后重复表头
- 不支持格式
- 文件过大
- 超过最大行数
- 表头前后空格
- 完全空白行忽略
- 保留真实源文件行号

#### 分组与变量合并

- 使用最新 `group_field` 分组
- 分组值为空判为 `invalid`
- `render_variables` 使用 `variable_key` 作为键
- `first`
- `lines`
- `unique_lines`
- `commas`
- `unique_commas`
- 去重保留首次出现顺序
- 空值不产生 `"None"` / `"null"` / 多余空行 / 连续逗号

#### 群聊匹配

- `exact`
- `contains`
- `regex`
- `priority desc`
- 同优先级 `id asc`
- 禁用规则跳过
- 同名群聊兜底
- 未匹配
- 正则缓存不改变结果

#### 草稿生成

- 正常生成 `pending_review`
- 未匹配分组生成 `invalid`
- 未匹配群聊但模板可渲染时，`invalid.draft_text` 保存渲染正文
- 缺少变量生成 `invalid`
- 缺少变量时，`invalid.draft_text` 保存可查看的预览正文
- 残留占位符生成 `invalid`
- 残留占位符时，`invalid.draft_text` 保存可查看的预览正文
- 渲染完全失败时，`invalid.draft_text = ''` 且 `error_message` 有值
- `draft_text` 数据库字段非空，且系统生成 `invalid` 草稿时允许空字符串
- `target_conversation_name = NULL`
- 删除模板后历史草稿仍存在
- `(import_batch_id, group_value)` 不重复
- 存在 `ready` 草稿时拒绝重新生成
- 单事务删除旧草稿并重建
- `invalid` 草稿不能确认

#### Service 流程

- 上传文件成功
- 重新匹配成功
- 重新匹配时重新计算 `group_value`
- 重新匹配缺字段整批拒绝
- 存在 `ready` 草稿时拒绝重新匹配
- `drafts_stale` 设置条件正确
- 生成草稿成功
- 存在 `ready` 草稿时拒绝重新生成
- 编辑 `pending_review` 草稿后仍为 `pending_review`
- 编辑 `ready` 草稿后自动退回 `pending_review`
- 编辑 `ready` 草稿返回中文提示
- 编辑 `invalid` 草稿后仍为 `invalid`
- `invalid` 草稿编辑后仍不能确认
- 批量状态更新
- 非当前作用域 id 整批拒绝
- rollback 测试

### 20.2 集成测试

继续扩展：

- `tests/integration/api/test_broadcast.py`
- `tests/integration/persistence/test_migrations.py`
- `tests/integration/persistence/test_migrations_postgres.py`

覆盖要求：

1. 上传 CSV
2. 上传 XLSX
3. 查询导入批次列表
4. 查询导入批次详情
5. 重新匹配
6. 重新匹配后 `drafts_stale` 变化
7. 生成草稿
8. 查询草稿列表
9. 查询草稿详情
10. 编辑 `pending_review` 草稿
11. 编辑 `ready` 草稿后自动撤回确认并返回中文提示
12. 编辑 `invalid` 草稿后仍为 `invalid`
13. `invalid` 草稿不能确认
14. 系统生成 `invalid` 草稿正文保存规则
15. 刷新后数据仍存在
16. bot / connector 作用域隔离
17. 删除导入批次
18. Migration upgrade / downgrade
19. 外键删除行为：
   - 删除模板不删除历史草稿
   - 删除规则不删除导入行
   - 删除批次联动删除导入行与草稿

### 20.3 Migration 测试

必须覆盖：

- revision id 长度
- SQLite upgrade / downgrade
- PostgreSQL upgrade / downgrade
- 新表注册进 metadata
- `matched_rule_id ON DELETE SET NULL`
- `template_id ON DELETE SET NULL`
- `import_batch -> import_rows ON DELETE CASCADE`
- `import_batch -> drafts ON DELETE CASCADE`

### 20.4 前端 E2E

扩展：

- `web/tests/e2e/broadcast-workspace.spec.ts`
- `web/tests/e2e/fixtures/langbot-api.ts`

覆盖要求：

1. 上传 CSV
2. 上传 XLSX
3. 显示导入统计
4. 显示 `matched / unmatched / invalid`
5. 重新匹配
6. 重匹配后显示“匹配结果已更新，请重新生成草稿”
7. 选择模板
8. 生成真实草稿
9. 审核页显示真实草稿
10. 显示 `invalid` 草稿错误
11. 编辑 `pending_review` 正文并刷新保留
12. 编辑 `ready` 后显示“草稿内容已修改，请重新确认”并回到待审核
13. 编辑 `invalid` 后状态保持无效且确认按钮继续禁用
14. 确认草稿
15. 撤回确认
16. 批量确认
17. `invalid` 草稿确认按钮禁用
18. `drafts_stale = true` 时确认按钮禁用
19. 中文错误提示
20. 执行按钮禁用
21. 不调用 Runtime
22. 不调用 `paste-draft`
23. 不调用 `send-draft`
24. `1366x768` 下页面可正常滚动与操作

### 20.5 验收标准与测试映射

每项验收标准必须至少有一类对应测试：

- 文件导入与解析：单元 + 集成 + E2E
- 持久化与作用域隔离：集成 + Migration
- 五种变量合并：单元
- 群聊匹配顺序与兜底：单元 + 集成
- 重新匹配与 `drafts_stale`：单元 + 集成 + E2E
- 草稿生成与重生成：单元 + 集成 + E2E
- 状态转换限制：单元 + 集成 + E2E
- 外键删除行为：Migration + 集成
- 不调用 Runtime / `paste-draft` / `send-draft`：E2E

---

## 21. 安全与隐私约束

- 不在日志中输出完整客户数据、联系方式或原始文件内容
- 不持久化原始上传文件二进制内容
- 仅保存清洗后的结构化 `raw_data`
- 错误响应优先输出通俗中文，不暴露内部技术栈细节
- 不调用 Runtime
- 不调用 `paste-draft`
- 不调用 `send-draft`
- 不进入 Phase 4

---

## 22. 验收标准

Phase 3 完成后必须全部满足：

- 支持 CSV：是
- 支持 XLSX：是
- 文件解析在数据库写事务之外完成：是
- 导入批次持久化：是
- 导入行持久化：是
- 批次统计公式一致：是
- 表头空名称拒绝：是
- `trim` 后重复表头拒绝：是
- 重新匹配使用最新 `group_field` 重新计算 `group_value`：是
- `render_variables` 使用 `variable_key` 作为键：是
- 分组与五种变量合并正确：是
- 群规则按 `priority desc, id asc`：是
- 同名群聊兜底：是
- 存在任意 `ready` 草稿时禁止重新匹配：是
- 存在任意 `ready` 草稿时禁止重新生成：是
- `drafts_stale` 仅在已有旧草稿时因重新匹配而置为 `true`：是
- 未匹配分组生成 `invalid` 草稿：是
- 未匹配群聊但模板可渲染时保存渲染正文：是
- 缺少变量或残留占位符时保存可查看预览正文：是
- 渲染完全失败时 `draft_text = ''` 且 `error_message` 有值：是
- `draft_text` 数据库字段保持非空，且系统生成 `invalid` 草稿时允许空字符串：是
- “草稿正文不能为空”仅适用于用户主动编辑保存：是
- 编辑 `pending_review` 草稿后仍为 `pending_review`：是
- 编辑 `ready` 草稿后自动退回 `pending_review`：是
- 编辑 `ready` 草稿返回 `草稿内容已修改，请重新确认`：是
- 编辑 `invalid` 草稿后仍为 `invalid`：是
- `invalid` 草稿不可通过编辑正文后直接确认：是
- `matched_rule_id` 与 `template_id` 使用 `ON DELETE SET NULL`：是
- `import_batch` 与导入行、草稿使用 `ON DELETE CASCADE`：是
- 重生成在单事务内删除旧草稿并重建：是
- 事务失败完整回滚：是
- 双层作用域校验生效：是
- 前端显示中文错误提示：是
- 前端审核页显示真实草稿与失败项：是
- 不调用 Runtime：是
- 不调用 `paste-draft`：是
- 不调用 `send-draft`：是
- 不进入 Phase 4：是
