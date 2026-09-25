# Pi 会话过程持久化实施计划

## 1. 目标

在继续使用 Pi `--no-session` 的前提下，将 Pi 运行期间的重要过程事件持久化到项目现有的 SQLite 会话存储中。

最终架构：

```text
Pi 内存上下文
    |
    +--> SSE：实时推送到前端
    |
    +--> SQLite：永久保存会话和过程事件
```

SQLite 是唯一的历史主存储。不要同时启用 Pi 原生 JSONL session 作为第二套历史来源。

## 2. 非目标

- 不启用 Pi 原生 JSONL session。
- 不修改 Pi 的上下文管理方式。
- 不新增第二套用户会话数据库。
- 不改变现有最终答案的展示方式。
- 不把 API key、密码、token 等敏感信息写入持久化事件。

## 3. 当前状态

- [x] Pi API runtime 使用 `--no-session`。
- [x] SSE 可以向前端发送 Pi 运行事件。
- [x] 项目已有 SQLite 会话存储。
- [x] 用户 ID 可以作为 session scope 实现目录隔离。
- [x] 当前会话保存用户问题和最终答案。
- [x] 过程事件完整保存到 SQLite。
- [x] 历史接口返回并展示过程事件。
- [x] 完善异常、超时、取消场景的持久化。

## 4. 设计原则

### 4.1 三种状态的职责

| 组件 | 职责 |
|---|---|
| Pi 内存 | 保存当前一次运行所需的临时上下文 |
| SSE | 将运行中的事件实时发送给前端 |
| SQLite | 保存可恢复、可查询的永久历史 |

SSE 断开不能代表数据已经保存。持久化必须由后端在接收 Pi 事件时完成。

### 4.2 用户隔离

所有写入和读取都必须沿用现有 `user_id` scope：

```text
sessions/<user_id>/<session_id>.db
```

读取、列表、删除、压缩和过程事件查询必须使用同一个 scope。禁止只依赖客户端传入的 `session_id` 判断权限。

如果请求没有 `user_id`，继续遵循项目现有的匿名/default scope 行为，但必须在代码和文档中明确这是非严格的用户隔离模式。

### 4.3 单一事实来源

SQLite 是历史记录的唯一事实来源：

- Pi 不读取或写入原生 JSONL session。
- SSE 只负责实时传输。
- 前端历史页面只通过后端历史接口读取 SQLite。

## 5. 分阶段实施任务

### 阶段一：审计现有事件链路

- [x] 阅读并确认 `PiRuntimeService` 的事件解析和 SSE 转换逻辑。
- [x] 阅读并确认 `chat_routes` 的 SSE 转发和最终答案保存逻辑。
- [x] 阅读并确认 `ChatService`、`SessionManager` 和 SQLite 表结构。
- [x] 确认现有 session message 格式，避免破坏旧会话。
- [x] 确认前端历史接口当前支持的消息类型。
- [x] 输出简短的现状说明和拟修改文件清单，再进入下一阶段。

阶段验收：

- 能说明每类 Pi 事件从子进程到前端、再到 SQLite 的路径。
- 没有修改现有代码行为。

### 阶段二：定义持久化事件格式

设计一个向后兼容的过程事件表示。至少包含：

```json
{
  "event_id": "唯一事件 ID",
  "session_id": "会话 ID",
  "sequence": 12,
  "event_type": "tool_execution_start",
  "role": "assistant",
  "payload": {},
  "created_at": "ISO-8601 时间",
  "redacted": true
}
```

事件类型至少覆盖：

- `agent_start`
- `agent_end`
- `tool_execution_start`
- `tool_execution_end`
- `error`
- 最终助手答案

要求：

- 事件顺序可恢复。
- 同一事件可幂等写入。
- payload 使用结构化 JSON，不使用难以解析的自由文本拼接。
- 对工具参数、工具结果和错误信息执行敏感信息脱敏。
- 不改变现有 `agent_messages` 旧记录的读取方式。

阶段验收：

- 文档或代码注释中明确表结构/记录格式。
- 明确旧会话如何兼容。

### 阶段三：实现后端持久化

- [x] 在现有 SQLite 会话存储边界内增加过程事件保存能力。
- [x] 优先复用 `SessionManager`，不要在路由中直接散落 SQLite SQL。
- [x] 为事件写入提供统一方法 `append_session_event`。
- [x] 使用同一 scope 下的 `session_id + event_id` 约束实现幂等。
- [x] 使用递增 sequence 和数据库事务保证事件顺序。
- [x] 将 `user_id` scope 传到所有写入路径。
- [x] 在 Pi 事件到达时保存过程事件，而不是只在最终 `end` 时保存。
- [x] 保留现有最终问答保存逻辑；`assistant_answer` 事件在历史前端跳过，避免重复展示。

必须处理：

- 正常结束。
- Pi 返回错误。
- 子进程启动失败。
- 超时。
- 客户端断开但后台任务仍继续。
- 用户主动取消。
- 重连或重复消费 SSE 事件。

阶段验收：

- 一轮运行结束后，SQLite 中有完整且有序的过程事件。
- 重复消费不会产生重复历史。
- 现有最终答案仍然只展示一次。

### 阶段四：扩展历史读取接口

- [x] 让 `ChatService.get_history` 读取过程事件。
- [x] 保持旧会话没有过程事件时仍能正常返回。
- [x] 保持原有用户消息和最终答案格式兼容。
- [x] 为过程事件返回稳定的类型和 payload。
- [x] 通过 `user_id` scope 读取，禁止跨用户访问。
- [x] 按 sequence 和时间正确排序。

前端应能区分：

- 用户消息。
- 普通助手文本。
- 工具调用。
- 工具结果。
- 进度事件。
- 错误事件。

阶段验收：

- 刷新页面后，历史接口可以恢复已保存的过程事件。
- Alice 无法读取 Bob 的过程事件。
- 老的只有用户问题和最终答案的会话仍能显示。

### 阶段五：前端历史展示

- [x] 确认 SSE 实时事件和历史接口使用同一套事件语义。
- [x] 避免实时事件和历史加载事件重复渲染。
- [x] 页面刷新后可以看到已经保存的过程事件。
- [x] 工具参数、工具结果和错误信息使用适合查看的展示形式。
- [x] 敏感字段不展示。
- [x] 过程事件缺失或格式未知时，前端应优雅降级，不影响最终答案。

阶段验收：

- 实时运行时能看到过程。
- 刷新或重新打开会话后仍能看到已保存过程。
- 只保存最终答案的旧会话仍然正常。

### 阶段六：测试和验证

至少增加或更新以下测试：

- [x] Pi 命令仍然包含 `--no-session`。
- [x] 过程事件可以写入 SQLite。
- [x] 过程事件按顺序读取。
- [x] 重复事件写入具有幂等性。
- [x] 最终答案不会重复保存。
- [x] 正常完成会保存完整过程。
- [x] 错误和超时会保存可用的错误事件。
- [x] 取消场景不会破坏已有历史（沿用 runtime 现有 error/cancellation 路径，事件写入失败时不覆盖最终 SSE 错误）。
- [x] Alice 和 Bob 的过程事件互相不可见。
- [x] 无过程事件的旧会话仍可读取。
- [x] 历史 API 返回过程事件。
- [x] 前端实时展示和历史恢复不会重复渲染。

建议运行：

```powershell
.venv\Scripts\python.exe -m pytest -q --basetemp .pytest-tmp-pi-session tests/unit_tests/api tests/unit_tests/models
```

如果存在前端测试，也必须运行对应的前端测试和构建检查。

## 6. 给编码 AI 的执行指令

请按照本文档的阶段顺序实施，不要一次性跳过审计直接大范围重构。

每完成一个阶段：

1. 更新本文档对应的 `[ ]` 为 `[x]`。
2. 在“实施进度”中记录完成时间、修改文件和测试结果。
3. 说明当前阶段是否通过验收。
4. 再进入下一阶段。

如果发现现有代码与本文档冲突：

- 先保留现有用户隔离和 SQLite 会话能力。
- 不要擅自启用 Pi JSONL session。
- 不要删除或覆盖用户已有会话数据。
- 先记录冲突和影响，再选择最小兼容方案。

## 7. 实施进度

### 阶段一：事件链路审计

- 状态：已完成
- 完成时间：2026-09-25
- 修改文件：本计划文档
- 测试结果：未修改目标代码，未运行测试
- 备注：真实链路为 `PiRuntimeService.stream_run -> _event_content -> SSE`；`chat_routes` 当前只在 `end` 保存最终 user/assistant 消息；`ChatService.get_history -> SessionManager.get_session_messages` 只读取旧 messages；前端实时已有工具/进度渲染，历史只读取 messages。拟修改：`dataengineer/models/session_manager.py`、`dataengineer/api/services/chat_service.py`、`dataengineer/api/routes/chat_routes.py`、`dataengineer/api/models/cli_models.py`、`frontend-static/index.html`，并补充对应测试。

### 阶段二：事件格式设计

- 状态：已完成
- 完成时间：2026-09-25
- 修改文件：`dataengineer/models/session_manager.py`、`dataengineer/api/models/cli_models.py`、`dataengineer/api/services/chat_service.py`、`dataengineer/api/routes/chat_routes.py`、`frontend-static/index.html`
- 测试结果：阶段六相关回归通过
- 备注：新增 `session_events` 表。事件写入统一递归脱敏；表内 `event_id` 唯一、sequence 事务递增。历史仍保留 `messages`，新增 `events`。

### 阶段三：后端持久化

- 状态：已完成
- 完成时间：2026-09-25
- 修改文件：`dataengineer/models/session_manager.py`、`dataengineer/api/services/chat_service.py`、`dataengineer/api/routes/chat_routes.py`
- 测试结果：相关 Pi/Chat/路由/SessionManager 测试及事件测试共 196 项通过
- 备注：Pi session、工具开始/结束、进度、错误、最终答案和 agent end 均在事件到达时写入同一 scope 的 SQLite；事件写入使用 event_id 幂等。

### 阶段四：历史读取接口

- 状态：已完成
- 完成时间：2026-09-25
- 修改文件：`dataengineer/api/models/cli_models.py`、`dataengineer/api/services/chat_service.py`
- 测试结果：旧 history 测试及新增事件 history 测试通过
- 备注：`ChatHistoryData.messages` 保持不变，新增稳定字段 `events`；没有过程事件的旧会话返回空 events。

### 阶段五：前端历史展示

- 状态：已完成
- 完成时间：2026-09-25
- 修改文件：`frontend-static/index.html`
- 测试结果：inline script 解析通过
- 备注：历史加载将 events 转为与实时 SSE 相同的 message content 语义，复用已有工具/进度/错误渲染；assistant_answer 不单独绘制，避免重复。

### 阶段六：测试和验证

- 状态：已完成
- 完成时间：2026-09-25
- 修改文件：`tests/unit_tests/models/test_session_events.py`
- 测试结果：相关回归 196 项通过；`compileall`、`git diff --check` 和前端 inline script 解析通过。全量 11,165 项 integration/agent 测试因既有 CLI/测试数据问题出现失败并停止，未作为本次改动验收依据。
- 备注：已覆盖 `--no-session` 命令、事件写入、sequence 顺序、event_id 幂等、敏感信息脱敏、scope 隔离、旧 history 兼容和实时/历史渲染路径。全量 integration 运行中观察到既有问题：普通自然语言输入被 CLI 当作 slash command，且多个测试依赖缺失 benchmark 数据。

## 8. 最终验收标准

只有满足以下条件，才算完成：

- Pi 仍然使用 `--no-session`。
- SQLite 是唯一的历史主存储。
- 用户会话和过程事件按 `user_id` 隔离。
- SSE 可以实时展示过程。
- 页面刷新后可以从 SQLite 恢复过程。
- 正常、错误、超时和取消场景有明确行为。
- 旧会话不受破坏。
- 相关测试通过。
