# DataEngineer 前端交互功能清单

本文档是重写网页前端的交互基线。它覆盖当前项目已经出现或后端已经明确支持的交互能力，并区分：

- **本地页面已实现**：当前 `index.html` 中可以直接确认。
- **后端已支持**：API 已存在，前端应提供相应入口。
- **外部聊天组件提供**：当前由 `@datus/web-chatbot` 提供，仓库中没有其源码。

## 1. 系统结构和入口

### 1.1 页面组成

```text
浏览器
├── 页面壳层：品牌栏、主题、运行模式
├── 聊天工作区：消息、输入、流式状态、工具结果
├── 会话侧栏：历史会话、新建、切换、删除
├── 配置/选择面板：Agent、数据库、模型
└── 专业面板：Explorer、知识库、可视化
        |
        v
FastAPI
├── Chat API
├── Agent API
├── Database / Model / Config API
├── Explorer / Knowledge Base API
└── Visualization API
```

### 1.2 页面入口

- 页面模板：`dataengineer/cli/web/templates/index.html`
- Web 服务：`dataengineer/cli/web/chatbot.py`
- 聊天组件：`@datus/web-chatbot`
- 默认根地址：`/`
- 启动示例：`dataengineer --web --datasource demo --host 127.0.0.1 --port 8512`

### 1.3 页面全局状态

| 状态 | 默认值 | 持久化 | 用途 |
|---|---|---|---|
| `theme` | `light` | `localStorage[data-engineer-theme]` | 亮色/暗色主题 |
| `runtime_variant` | `single` | 页面状态 / 每次聊天请求 | 选择 Single 或 Multi；切换时开始独立会话 |
| `session_id` | 空 | 由聊天服务返回 | 当前会话上下文 |
| `subagent_id` | 默认 chat | 会话/请求级 | 当前执行 Agent |
| `database` | 当前 datasource | 请求级 | 当前数据源或数据库 |
| `model` | 配置中的 active model | 配置级 | 当前大模型 |

## 2. 页面壳层交互

### 2.1 品牌栏

- 显示产品名称、版本、连接状态。
- 显示当前运行模式。
- 显示主题切换按钮。
- 移动端隐藏非核心文字，保留核心控件。

后端职责：无直接业务请求；连接状态可以由健康检查或聊天请求状态驱动。

### 2.2 亮色/暗色主题

交互：

1. 点击太阳/月亮按钮。
2. 在 `light` 和 `dark` 之间切换。
3. 更新页面、聊天区、消息气泡、输入框、侧栏、代码块和按钮颜色。
4. 刷新页面后恢复上次选择。

后端职责：无。属于浏览器本地状态。

### 2.3 两种运行模式

选项：

| 显示名称 | 值 | 后端执行路径 |
|---|---|---|
| 单 Agent | `single` | `svc.pi_runtime.stream_chat` |
| 多 Agent | `multi` | `svc.pi_runtime.stream_chat`，内部编排多个专业 Agent |

交互：

1. 点击模式按钮。
2. 更新选中状态和可访问性属性。
3. 下次发送聊天请求时加入当前 `runtime_variant`。
4. 切换模式会开始新会话；运行中的请求期间禁用切换。
5. 打开属于另一运行模式的历史会话后发送时，保留原历史并为当前模式新建会话。

请求：`POST /api/v1/chat/stream`。

缺省值为 `single`。不支持的模式值由请求校验拒绝，不会进入 Agent 执行。

后端职责：选择执行运行时。Multi 模式可包含 Schema Analyst、SQL Generator、SQL Debugger、SQL Reviewer、Result Interpreter 等角色。

## 3. 聊天工作区

### 3.1 消息输入

交互：

- 单行或多行输入。
- 发送按钮。
- Enter 发送，Shift+Enter 换行。
- 空输入禁止发送。
- 发送中禁用重复提交。
- 显示当前 Agent、数据库、模型等上下文。
- 可选支持 `@table`、`@metric`、`@sql` 等上下文引用。

请求：`POST /api/v1/chat/stream`。

典型请求字段：

```json
{
  "message": "用户问题",
  "session_id": "可选",
  "subagent_id": "可选",
  "database": "可选",
  "runtime_variant": "single | multi"
}
```

后端职责：创建或复用会话，启动 Agent，持续产生 SSE 事件。

### 3.2 流式消息展示

前端应区分显示：

- 用户消息。
- Assistant 最终回答。
- 思考/进度状态。
- 工具调用名称和参数摘要。
- 工具调用结果。
- SQL 代码块。
- 查询结果表格。
- 错误消息。
- 会话开始、完成、停止和失败状态。

传输：`text/event-stream`。

后端职责：按事件推送执行过程；前端不得把每个事件都当成普通文本拼接，应按事件类型渲染。

### 3.3 发送中控制

- 停止生成：中止当前 SSE 请求；未完成回答不会写入会话历史。
- Single/Multi 不支持恢复未完成的生成；重新发送会开始一轮新请求。
- TaskManager 的 `POST /api/v1/chat/stop` 与 `POST /api/v1/chat/resume` 保留给独立兼容流程，不属于当前聊天运行时。
- 连接状态：连接中、执行中、已完成、已停止、失败。

### 3.4 消息操作

建议支持：

- 复制回答。
- 复制 SQL。
- 展开/折叠思考过程。
- 展开/折叠工具调用。
- 展开/折叠代码和查询结果。
- 重新生成回答。
- 对回答点赞、点踩或填写反馈。

反馈请求：`POST /api/v1/chat/feedback`。

## 4. 会话侧栏和历史对话

### 4.1 侧栏显隐

交互：

- 展开左侧栏。
- 收起左侧栏。
- 移动端改为抽屉。
- 记住用户上次显隐状态。

后端职责：无直接显隐请求；侧栏内容来自会话 API。

### 4.2 会话列表

请求：`GET /api/v1/chat/sessions`。

显示：

- 会话标题或摘要。
- 最近更新时间。
- 当前会话标记。
- 所属 Agent 或子 Agent。
- 运行中标记。

交互：

- 新建会话。
- 点击切换会话。
- 搜索或按 Agent 筛选。
- 删除会话。
- 打开会话菜单。

### 4.3 会话历史

请求：`GET /api/v1/chat/history?session_id=...`。

功能：

- 加载完整消息。
- 恢复 SQL、结果和工具记录。
- 历史会话恢复消息；运行模式使用当前选择，若会话运行模式不同则新建会话。
- 长历史分页或虚拟滚动。

### 4.4 会话维护

- 删除：`DELETE /api/v1/chat/sessions/{session_id}`。
- 压缩上下文：`POST /api/v1/chat/sessions/{session_id}/compact`。
- Single/Multi 历史会话可继续发送；未完成生成不支持续传。

## 5. Agent 和子 Agent

### 5.1 Agent 选择

交互：

- 打开 Agent 选择器。
- 查看内置 Agent 和自定义 Agent。
- 查看 Agent 描述、能力和可用工具。
- 选择当前 Agent。
- 按 Agent 筛选历史会话。

接口：

- `GET /api/v1/agents`
- `GET /api/v1/agents/{id}` 或项目实际路由对应的 Agent 查询接口
- `GET /api/v1/agents/tools`

聊天请求使用：`subagent_id`。

后端职责：校验 Agent 是否存在，并将聊天任务路由到指定 Agent。

### 5.2 自定义 Agent 管理

交互：

- 创建自定义子 Agent。
- 编辑 Agent 名称、提示词、工具权限和模型配置。
- 查看可用工具类别和方法。
- 删除或停用自定义 Agent（若后端版本支持）。

接口：

- `POST /api/v1/agents`
- `POST /api/v1/agents/{id}`
- `GET /api/v1/agents/tools`

### 5.3 Multi-Agent 执行可视化

建议展示：

- 当前主 Agent。
- 当前正在运行的子 Agent。
- 子任务列表。
- 子任务成功/失败状态。
- 工具调用和审查节点。

后端职责：编排专业 Agent，并通过流式事件返回进度。

## 6. 数据库、数据源和 Schema 选择

### 6.1 数据源选择

交互：

- 打开数据源选择器。
- 选择数据库连接配置。
- 显示连接状态。
- 测试连接。
- 切换后刷新 catalog、database、schema 和 table。

接口：

- `GET /api/v1/database/catalogs`
- `POST /api/v1/config/datasources/probe`
- `PUT /api/v1/config/datasources`

### 6.2 层级浏览

层级：

```text
Datasource
└── Catalog
    └── Database
        └── Schema
            └── Table
                └── Column
```

交互：

- 展开/折叠层级。
- 搜索表和字段。
- 选择表或字段插入聊天输入。
- 查看字段类型和样例。
- 将表、字段作为上下文发送给 Agent。

后端职责：返回结构信息；Agent 使用这些信息进行 Schema Linking 和 SQL 生成。

### 6.3 数据库对聊天的影响

聊天请求中的 `database` 决定：

- 使用哪个 datasource。
- 查询哪个 Schema。
- 使用哪种 SQL 方言。
- SQL 实际执行到哪里。
- 结果从哪里读取。

## 7. 大模型和配置

### 7.1 模型选择

交互：

- 查看当前可用模型。
- 按 Provider 分组。
- 选择默认模型或运行时模型。
- 显示模型类型和名称。
- 测试模型连接。
- 显示连接失败原因。

接口：

- `GET /api/v1/models`
- `GET /api/v1/config`
- `PUT /api/v1/config/models`
- `POST /api/v1/config/models/probe`

后端职责：读取配置、校验凭据、测试连通性、更新当前模型目标。

### 7.2 配置编辑

配置页面可包含：

- Datasource 配置。
- Model 配置。
- 默认目标模型。
- Agentic node 配置。
- 调试和输出配置。

保存配置前应支持校验和连接测试，保存后应提示哪些新会话会使用新配置。

## 8. 弹窗和用户补充交互

### 8.1 Agent 请求用户输入

典型场景：

- 选择候选数据库。
- 选择候选表。
- 补充业务参数。
- 确认 SQL。
- 选择执行方案。
- 确认危险或高成本操作。

流程：

```text
Agent 暂停
  -> SSE 发送 interaction 事件
  -> 前端显示 Modal / Drawer / Inline Form
  -> 用户选择或填写
  -> POST /api/v1/chat/user_interaction
  -> Agent 恢复执行
```

请求字段至少包括：

- `session_id`
- `interaction_key`
- `input`

### 8.2 交互控件类型

前端应根据事件元数据渲染：

- 单选。
- 多选。
- 文本输入。
- 数字输入。
- 日期输入。
- 下拉菜单。
- SQL 确认框。
- 是/否确认框。
- 多字段表单。

### 8.3 Web 模式默认行为

旧的 Web 执行器支持自动提交默认交互答案，以避免后台任务永久阻塞。重写前端时应明确区分：

- 需要真实用户确认的交互。
- 可以安全使用默认值的交互。
- 不允许自动确认的危险操作。

## 9. 工具调用和浏览器参与的操作

### 9.1 工具调用展示

每个工具调用建议显示：

- 工具名称。
- 参数摘要。
- 执行中状态。
- 成功/失败状态。
- 返回结果摘要。
- 展开查看完整输入和输出。

### 9.2 工具结果回传

接口：`POST /api/v1/chat/tool_result`。

流程：

```text
Agent 请求工具
  -> 前端或浏览器执行工具
  -> 前端拿到结果
  -> 回传 session_id、call_tool_id、tool_result
  -> Agent 继续执行
```

前端必须处理工具执行超时、取消、失败和权限拒绝。

## 10. 反馈和评价

### 10.1 消息评价

交互：

- 点赞。
- 点踩。
- 选择反馈原因。
- 填写补充意见。
- 标记回答是否解决问题。

接口：`POST /api/v1/chat/feedback`。

请求可包含：

- `reaction_emoji`
- `reference_msg`
- `reaction_msg`
- `session_id`

后端可能把反馈路由给 `feedback` 子 Agent，并归档可复用知识。

### 10.2 UI 状态

- 未评价。
- 已点赞。
- 已点踩。
- 提交中。
- 提交成功。
- 提交失败可重试。

## 11. SQL 和查询结果

聊天结果区应支持：

- SQL 代码高亮。
- 一键复制 SQL。
- 展开/折叠 SQL。
- 结果表格。
- 列排序。
- 分页或虚拟滚动。
- 单元格复制。
- 空结果提示。
- 查询错误提示。
- 执行耗时和行数。
- 下载结果（若后端提供下载能力）。

后端职责：生成 SQL、执行 SQL、返回列信息、行数据、错误和执行元数据。

## 12. 数据可视化

接口：`POST /api/v1/data_visualization`。

交互：

- 从查询结果点击“可视化”。
- 选择或接受推荐图表类型。
- 选择 X 轴、Y 轴、分组字段和聚合方式。
- 切换图表类型。
- 查看图表和原始数据。
- 下载图片或配置（如果实现）。

后端职责：根据表格数据推荐图表配置；前端负责渲染和交互。

## 13. Explorer：语义模型、指标、Reference SQL 和知识

### 13.1 主题树

接口：Explorer routes。

交互：

- 展开/折叠目录树。
- 搜索主题。
- 新建目录。
- 重命名或移动节点。
- 删除节点。
- 查看节点详情。

接口能力：

- 获取主题树。
- 创建目录。
- 重命名/移动主题。
- 删除主题。

### 13.2 指标

交互：

- 创建指标。
- 查看指标 YAML 或结构化配置。
- 编辑指标。
- 将指标插入聊天上下文。

后端能力：创建、读取、编辑 Metric。

### 13.3 Reference SQL

交互：

- 创建参考 SQL。
- 查看摘要、注释和 SQL。
- 编辑参考 SQL。
- 将参考 SQL 作为聊天上下文。

后端能力：创建、读取、编辑 Reference SQL。

### 13.4 Knowledge

交互：

- 创建知识条目。
- 查看 `search_text` 和解释。
- 编辑知识条目。
- 删除知识条目。
- 从聊天反馈归档知识。

后端能力：创建、读取、编辑 Knowledge。

## 14. 知识库初始化和文档导入

### 14.1 知识库 Bootstrap

接口：

- `POST /api/v1/kb/bootstrap`
- `POST /api/v1/kb/bootstrap/cancel/{stream_id}`

交互：

- 选择输入路径或数据源。
- 开始导入。
- 查看 SSE 进度。
- 查看当前处理文件/阶段。
- 取消任务。
- 查看成功、跳过和失败数量。

### 14.2 平台文档 Bootstrap

接口：

- `POST /api/v1/kb/bootstrap/docs`
- `POST /api/v1/kb/bootstrap/docs/cancel/{stream_id}`

交互和状态与普通 Bootstrap 相同，但内容来源是平台文档。

## 15. 推荐的前端状态模型

```text
AppState
├── theme
├── runtimeVariant
├── connection
├── currentUser
├── currentSession
│   ├── id
│   ├── messages
│   ├── status
│   ├── lastEventId
│   ├── subagentId
│   ├── database
│   └── model
├── sessions
├── agents
├── datasources
├── catalogs / databases / schemas / tables
├── models
├── pendingInteraction
├── activeToolCalls
├── feedbackState
├── explorerTree
├── visualizationState
└── knowledgeBootstrapState
```

## 16. 重写前端时的优先级

### P0：核心可用

- 页面壳层。
- 聊天输入和发送。
- SSE 流式消息。
- 会话创建、切换、历史和删除。
- 停止任务。
- 三种运行模式。
- 数据库选择或请求级 database 参数。
- 错误、加载和断线状态。

### P1：完整 Agent 工作流

- 子 Agent 选择。
- 模型选择。
- 用户交互弹窗。
- 工具调用展示和工具结果回传。
- SQL 和结果展示。
- 点赞、点踩和反馈。
- 左侧栏折叠。
- 日夜主题。

### P2：专业能力

- 图表生成和图表交互。
- Explorer 主题树。
- 指标、Reference SQL、Knowledge 编辑。
- 知识库 Bootstrap 和进度取消。
- Multi-Agent 执行过程可视化。
- 配置编辑和连通性测试。

## 17. 每个交互的实现检查表

重写任何功能时，都应明确回答：

1. 用户看到的控件是什么？
2. 控件有哪些状态：初始、加载、成功、失败、禁用、取消？
3. 状态保存在组件、会话、浏览器还是服务端？
4. 请求方法、路径和请求体是什么？
5. 返回是 JSON 还是 SSE？
6. 是否需要携带 `session_id`、`subagent_id`、`database`、`runtime_variant`？
7. 失败后如何恢复或重试？
8. 是否需要权限、确认或危险操作拦截？
9. 页面刷新或断线后能否恢复？
10. 该功能是本项目实现，还是外部 `@datus/web-chatbot` 实现？
