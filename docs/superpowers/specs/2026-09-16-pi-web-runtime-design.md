# Pi Web Runtime 与基准测试设计

> Historical design record. Legacy references below are retained for traceability and are not a current runtime option.

## 状态

- 已于 2026-09-16 在对话中确认设计。
- 用户审阅本文档后开始实施。
- 凭据完成轮换且基准测试达到门槛之前，不切换生产流量。

## 问题

当前仓库同时包含旧版 Python Agent workflow 和 Pi SQL Runtime，但现有 Web 聊天始终使用旧版 workflow。用户需要在同一页面选择并比较旧版、单 Agent 和多 Agent 三种运行方式。基准测试必须走与 Web 请求相同的运行路径，确保测试结果能够代表生产行为。

## 范围

本次改动包括：

1. 在现有 Web 页面加入可见的 `legacy / single / multi` 选择器。
2. 在聊天请求契约中加入 `runtime_variant`。
3. `legacy` 请求保持使用现有 `ChatService`，不改变原有执行逻辑。
4. `single` 和 `multi` 请求通过 Pi 运行，模型使用 `custom/gpt-5.5`。
5. 将 Pi 输出和错误转换为现有 SSE 响应格式。
6. 新增基准测试运行器，通过同一应用服务调用三种 Runtime。
7. 达到切换条件之前，生产默认值保持为 `legacy`。

本次改动不会替换外部聊天组件、增加递归子 Agent，也不会自动切换生产流量。

## 方案比较

### 采用方案：每个请求启动独立 Pi 进程

Python API 为每个 `single` 或 `multi` 请求启动一个 Pi 进程。该进程不保留持久 Pi session，并在请求取消时终止。

优点：

- 与现有 Pi Extension 和 Agent 定义一致。
- 请求状态和故障彼此隔离。
- 取消与回滚行为明确。
- 第一版不需要额外部署常驻服务。

代价是进程启动会增加延迟。未来可以在不修改 Web 请求契约的情况下，将内部实现替换为常驻 Pi 服务。

### 延后方案：常驻 Pi Sidecar

常驻 TypeScript 服务可以降低启动延迟，并支持更细粒度的 token 流式输出，但会引入服务发现、健康检查、部署和 session 所有权问题。第一轮生产对比不需要承担这些复杂度。

### 不采用方案：在 Python 中重新实现 Pi 编排

这种方式可以减少进程边界，但会重复实现 Agent 循环和状态机，也违背已经确定的职责划分：Pi 负责 Agent 编排，Python 负责数据库、RAG、校验和执行能力。

## 请求契约

`StreamChatInput` 新增：

```json
{
  "runtime_variant": "legacy | single | multi"
}
```

该字段默认值为 `legacy`，因此现有客户端行为不变。非法取值由请求模型直接拒绝。

Web 选择器将当前模式保存在浏览器本地存储中。页面在初始化外部聊天组件之前包装 `window.fetch`。该包装器只复制并修改发送到 `/api/v1/chat/stream` 的 JSON 请求体，为其加入 `runtime_variant`；其他请求原样转发。后端 API 契约不依赖这个页面适配方式。

## Runtime 组件

### Runtime Router

API 路由将请求交给 Runtime Router：

- `legacy`：调用现有 `ChatService.stream_chat`。
- `single`：使用 baseline 工具白名单启动 Pi。
- `multi`：使用 Orchestrator 和 `sql_subagent` 工具启动 Pi。

Router 只负责选择 Runtime，不负责生成 SQL、校验 SQL 或访问数据库。

### Pi 进程运行器

运行器负责：

- 使用项目本地安装的 Pi；
- 选择 `custom/gpt-5.5`；
- 根据 `single` 或 `multi` 使用对应工具白名单；
- 传入用户问题和已配置的数据源；
- 读取 Pi JSON 事件；
- 提取最终 Assistant 消息和用量信息；
- 在请求取消时终止进程；
- 设置明确的执行超时；
- 不记录提示词、SQL 结果行、凭据或环境变量值。

Pi 继续通过现有 MCP bridge 调用 Python 能力。SQL 只能通过 `execute_readonly_sql` 执行。

### SSE 适配器

Pi 输出会转换为现有 SSE 模型，因此聊天组件不需要另一套渲染系统。第一版保证返回完整最终消息和终止错误；逐 token 输出不是第一版的必要条件。

每个响应都要标明请求的 Runtime 和实际执行的 Runtime。Pi 失败时返回明确的 SSE 错误，不自动改用 legacy 重跑。静默回退会污染基准测试结果，也可能造成数据库请求重复执行。

## Web 交互

现有页面顶部加入紧凑的三段式选择器：

- 旧版
- 单 Agent
- 多 Agent

初始值为 `legacy`，选择结果保存在浏览器本地存储。切换只影响之后发送的消息，不重新解释已有 session 历史。请求运行期间始终显示当前模式。

该控件支持键盘操作和响应式布局，并复用页面现有的黑白设计变量。

## 基准测试

基准测试运行器读取带版本的测试用例文件。每条记录至少包含：

```json
{"task_id":"case-1","question":"...","datasource":"demo"}
```

运行器使用相同测试用例分别调用 `legacy`、`single` 和 `multi`。Pi 版本统一使用 `custom/gpt-5.5` 和固定运行参数。结果分别追加到 JSONL 文件，再交给现有对比脚本汇总。

必须记录以下指标：

- 最终结果正确率；
- 首次生成 SQL 的可执行率；
- 修复成功率；
- 危险 SQL 拦截率；
- 延迟；
- 工具调用次数；
- 人工介入次数。

只有模型服务返回了足够的用量和价格信息时才记录 token 成本；否则明确标记为不可用，不进行推测。

第一次真实运行先使用小规模、有代表性的测试子集，用于验证测试框架并限制意外费用。验证通过后再运行完整测试集。

正确性根据测试用例中的期望结果，或者 gold SQL 的执行结果进行判定。无法机器判定的用例标记为需要人工审阅，不计入自动正确率。

## 安全与生产切换

满足以下全部条件前，生产环境保持使用 `legacy`：

- 已经撤销并替换曾暴露的模型和数据库凭据；
- 危险 SQL 拦截率为 100%；
- 多 Agent 最终正确率不低于 legacy；
- 延迟和成本已被接受；
- 取消操作能够从 Web 请求传递到 Pi 子进程；
- Pi 健康检查失败清晰可见，并且用户仍可手动选择 legacy。

凭据轮换属于上线前的运维操作，不由应用代码自动执行。

## 错误处理

- Runtime 值非法：返回 HTTP 请求校验错误。
- Pi 可执行文件或模型不存在：返回明确的 SSE 配置错误。
- Pi 超时：终止进程并返回超时事件。
- 客户端取消：终止 Pi 进程并停止发送事件。
- Pi 协议输出非法：返回协议错误，但不泄露可能包含敏感信息的原始 stderr。
- SQL Guard 拒绝：保留安全失败结果，任何路径都不得绕过 Guard。

## 测试

测试范围包括：

- 请求模型默认值和 Runtime 值校验；
- 三种 Runtime 的 Router 选择；
- 不启动付费模型的 Pi 命令构造测试；
- Pi JSON 事件解析和最终消息转换；
- 取消和超时后的进程清理；
- SSE 成功及错误映射；
- 基准测试用例加载、断点续跑和指标汇总；
- Web 选择器在桌面和移动宽度下的布局与请求参数注入。

确定性测试全部通过后，才运行真实模型的小规模 Benchmark。生产切换是独立操作，需要在基准测试审阅和凭据轮换完成后单独执行。
