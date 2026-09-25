# 聊天最终输出不显示排查说明

## 现象

聊天窗口能显示 `agent_start`、工具调用和 SQL 执行过程，但执行结束后没有最终回答；页面仍显示“已完成”。执行中曾短暂出现回答，说明 SSE 链路和后端输出能力基本正常。

## 原因

聊天 SSE 中，过程和最终回答是不同事件：

- 过程：`message` 事件中的 `progress`、`call-tool`、`call-tool-result` 等内容。
- 最终回答：`message` 事件中的非空 `markdown`/`text` 内容，通常位于 `payload.content`。
- 结束：`end` 只表示服务端流结束，不等于页面已经收到最终回答。

当前前端的完成判断只检查是否收到 `end`，没有检查 `state.hasAnswer`。因此最终回答事件缺失、为空或字段格式不兼容时，仍会显示“已完成”，形成“只有过程”的假成功。

另外，Web 服务启动时会把单文件前端读入内存。修改 `frontend-static/index.html` 或后端代码后不重启 8512，浏览器可能继续使用旧版本，造成代码与实际行为不一致。

## 最小修复要求

1. 前端在 `finishTurn()` 中要求本轮存在非空最终回答；只有 `end` 且 `state.hasAnswer === true` 才能标记“已完成”。否则显示明确错误或“结果缺失”，不能伪装成功。
2. 前端统一提取回答文本，兼容约定的 `part.payload.content`，必要时兼容后端明确支持的 `text` 字段；空文本不得设置 `hasAnswer`。
3. 后端在 `end` 前发送一个非空的最终 `markdown` 消息；保持 SSE 顺序为 `session -> process messages -> final message -> end`。
4. 修改前后端后重启 8512，再进行浏览器验收，避免旧进程快照干扰。

## 本次测试补充

- Windows 下 `asyncio.create_subprocess_exec()` 在当前服务事件循环中会抛出 `NotImplementedError`，导致 SSE 响应提前结束。Pi runtime 已改为线程化读取 `subprocess.Popen` stdout，仍按 JSON 行实时转发。
- Pi 的 `execute_readonly_sql` 结果位于 `call-tool-result.payload.result.details.execution`。前端已解包该 envelope，并继续兼容顶层 `compressed_data` 与 `rows`。
- 可恢复的单个工具失败只标记对应工具，不覆盖后续最终回答；整轮失败仍由 SSE `error` 或缺少最终回答决定。
- 长过程完成后在下一帧重新贴底，避免最终回答因新增块排版后落到可视区外。

## 验收标准

- 原始 SSE 在 `end` 前存在非空最终回答事件。
- 页面同时显示过程、SQL/结果和最终回答。
- 缺少最终回答时页面显示失败或结果缺失，而不是“已完成”。
- 重启 8512 后，`GET /` 返回的前端内容与磁盘版本一致。
- Single/Multi 真实请求均能显示工具过程、SQL、结果表和最终回答；移动视口无横向溢出。

相关实现：`frontend-static/index.html`、`dataengineer/api/services/pi_runtime_service.py`、`dataengineer/api/routes/chat_routes.py`。
