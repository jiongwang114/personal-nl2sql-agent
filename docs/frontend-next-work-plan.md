# 前端重做下一阶段总清单

> 目标：只保留 Single Agent 与 Multi Agent；完成前端真实验收；补齐 Pi Agent 风格的模型、密钥、思考等级和本地数据库配置窗口；用可复现数据量化 Multi 相对 Single 的收益。
>
> 使用规则：按文档顺序逐篇执行。只有代码、测试和证据都完成后，才把 `[ ]` 改为 `[x]`。`D:\Agent任务的流程记录\DataEngineer-前端重做` 下的 01-10 文件是历史记录，本组文档是后续执行基线。

## 范围边界

- 保留：`single`、`multi`、Pi runtime、工具调用、SSE、会话、数据库查询和真实错误展示。
- 删除：面向用户和运行时契约中的 `legacy` 运行路径，以及只为该路径存在的前端分支、默认值、测试和文档。
- 不混删：名字带 `legacy` 的认证、历史数据迁移或兼容模型，先做引用分析；只有确认不再被 Single/Multi 或公开 API 使用，才删除或改名。
- 不伪造：没有后端能力的控件不显示为可用；配置保存、模型探测和数据库导入都必须有真实成功、失败、取消和重试状态。

## 执行顺序

| 顺序 | 文档 | 结果 |
| --- | --- | --- |
| 1 | [Legacy 下线清单](frontend-next-01-remove-legacy.md) | 运行时契约只接受 Single/Multi，旧路径和旧文档不再成为产品入口 |
| 2 | [前端真实验收清单](frontend-next-02-frontend-acceptance.md) | 证明现有前端核心功能在 Single/Multi 下可用，并留下可复核证据 |
| 3 | [Pi 设置与模型配置清单](frontend-next-03-pi-settings.md) | 用户可以选择 Provider/模型、输入密钥、选择思考等级并测试保存结果 |
| 4 | [数据库下载与导入清单](frontend-next-04-database-import.md) | 用户可以把本地下载的 SQLite/DuckDB 数据库加入数据源并直接查询 |
| 5 | [Single/Multi 量化评测清单](frontend-next-05-single-multi-benchmark.md) | 在同一题集、模型和数据库上量化两种运行时的准确率、稳定性、成本和延迟 |

## 总体验收门槛

- [x] `/api/v1/chat/stream` 的公开请求只允许 `runtime_variant: single | multi`，默认值为 `single`。
- [x] 页面首屏、设置页和聊天页不再提供 Legacy 选择。
- [x] Single 与 Multi 使用同一题目、同一模型、同一数据源时都能完成真实对话、SQL、结果和最终回答。
- [ ] 设置页保存的模型、密钥、思考等级会进入下一次真实请求；刷新后状态仍与后端一致，密钥不回显、不进 localStorage、不进日志。
- [x] 导入的本地数据库经过路径、扩展名、大小、读权限和连接测试后，出现在数据源选择器和 Catalog 中；SQLite/DuckDB 浏览器导入链路已回放。
- [ ] benchmark 报告只比较 Single/Multi；原 Legacy 历史结果保留为历史资料，不再进入当前结论。
- [x] 运行 `git diff --check`、前端脚本语法检查、定向 Python 测试和真实浏览器验收均通过。

## 阶段执行前已知基线

- 已有记录显示 Single/Multi 在 `deepseek/deepseek-flash` 与隔离 DuckDB 上完成过真实成功链路；`custom/gpt-6-luna` 曾因 Provider 周额度返回 403，这类外部配额失败不能判为前端通过。
- 阶段开始时 `frontend-static/index.html` 曾包含 Legacy 运行时按钮、下拉选项和默认回退；现已由第一阶段下线。
- 当前 Pi runtime 将 `--thinking` 写死为 `minimal`；设置页尚未把思考等级作为可验证请求参数。
- 当前配置接口支持模型/数据源全量保存和连通性测试，但缺少面向用户的安全密钥录入契约。
- 当前数据库 API 主要提供目录浏览，尚未形成“本地文件导入 -> 注册数据源 -> Catalog 刷新”的闭环。
