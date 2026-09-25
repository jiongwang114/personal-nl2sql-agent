# Pi Web Runtime 与基准测试实施计划

> Historical implementation plan. Its Legacy references describe the former rollout; current API and benchmark scope is Single/Multi per `docs/frontend-next-work-plan.md`.

## 目标

把已完成的 Pi SQL Runtime 接入现有 Web 聊天 API 和页面，并使用同一路径比较 `legacy`、`single`、`multi`。

## WP-11：请求契约与 Runtime Router

修改文件：

- `dataengineer/api/models/cli_models.py`
- `dataengineer/api/routes/chat_routes.py`
- `dataengineer/api/services/dataengineer_service.py`
- `tests/unit_tests/api/routes/test_chat_routes.py`

步骤：

1. 为 `StreamChatInput` 增加默认值为 `legacy` 的 `runtime_variant` Literal 字段。
2. 为 `DataEngineerService` 增加延迟加载的 Pi Runtime 服务。
3. 在聊天路由中把 `legacy` 交给原服务，把 `single/multi` 交给 Pi 服务。
4. 测试默认值、非法取值和三种路由分支。

## WP-12：Pi 进程与 SSE 适配

新增或修改文件：

- `dataengineer/api/services/pi_runtime_service.py`
- `tests/unit_tests/api/services/test_pi_runtime_service.py`

步骤：

1. 构造项目本地 Pi 命令，固定模型为 `custom/gpt-5.5`。
2. `single` 与 `multi` 使用不同工具白名单，并传入问题和 datasource。
3. 异步读取 JSONL 事件，提取最终 Assistant 文本和 usage。
4. 转换为现有 session、message、end SSE 事件。
5. 对缺少可执行文件、非零退出、协议错误、超时和取消返回安全错误。
6. 测试命令构造、事件解析、SSE 映射和进程清理，不调用真实模型。

## WP-13：Web 三档选择器

修改文件：

- `dataengineer/cli/web/templates/index.html`
- `tests/unit_tests/cli/web/test_chatbot.py`

步骤：

1. 在页头增加 `旧版 / 单 Agent / 多 Agent` 分段控件。
2. 默认选择 `legacy`，并使用 localStorage 保存选择。
3. 初始化聊天组件前包装 `window.fetch`，只为 chat stream JSON 请求加入 `runtime_variant`。
4. 增加移动端布局、键盘语义和静态 HTML 测试。

## WP-14：统一 Benchmark Runner

新增或修改文件：

- `scripts/run_pi_benchmark.py`
- `tests/unit_tests/scripts/test_run_pi_benchmark.py`
- `docs/work-packages/09-benchmark-comparison.md`

步骤：

1. 读取包含 `question/sql` 或 JSONL 等价字段的测试集。
2. 支持选择 variant、case 数量、输出目录和断点续跑。
3. 调用与 Web 相同的 Runtime 服务并记录 JSONL。
4. gold SQL 可执行时进行结果比较；不能自动判断时标记人工审阅。
5. 先运行 1 个 case 的 `single/multi` 烟雾测试，再决定是否扩大。

## 验证与提交

1. 运行所有新增或修改的定向测试。
2. 运行 Ruff check 和 format check。
3. 运行 `.pi` TypeScript check。
4. 运行 MCP bridge 烟雾测试。
5. 启动本地 Web 服务并检查桌面、移动页面与请求字段。
6. 使用 `custom/gpt-5.5` 运行小规模真实 Benchmark。
7. 汇总指标；凭据未轮换时不改变生产默认值。
8. 只暂存本次实现文件并创建提交，不包含现有 `README.md` 和“项目介绍”改动。
