# Legacy 下线清单

> 目标：产品只保留 Single Agent 与 Multi Agent。此文档只处理运行时下线和相关契约，不处理无关的历史兼容代码。

## 1. 盘点与分类

- [x] 搜索 `legacy`、`runtime_variant`、旧聊天服务入口和旧 benchmark 标签，建立引用表：文件、符号、调用方、是否仍被 Single/Multi 使用。
- [x] 将引用分成三类：运行时路径、公开契约/产品文案、非运行时历史兼容。第三类不得仅凭文件名直接删除。
- [x] 冻结删除前基线：Single/Multi API 直测、前端脚本语法、相关单测和当前 benchmark 数据快照。

## 2. 后端和契约

- [x] 将 `runtime_variant` 的公开类型、默认值、OpenAPI schema、请求示例统一为 `single | multi`；缺失值默认 `single` 或由接口明确拒绝，不能回退到 Legacy。
- [x] 删除聊天路由、服务分发器和执行器中仅服务 Legacy 的分支；Single/Multi 继续共用统一错误、会话和 SSE 协议。
- [x] 删除只为 Legacy 存在的配置项、环境变量、启动参数和旧服务调用；保留仍被配置加载、认证或历史数据读取依赖的兼容逻辑，并记录理由。
- [x] 更新 `contracts/`、`contracts/openapi.json`、请求/响应模型和 API 文档，禁止 schema 继续宣传 Legacy。
- [x] 增加回归测试：`single`、`multi` 正常；`legacy` 请求返回稳定的参数错误；省略运行模式时行为与默认约定一致。

## 3. 前端

- [x] 删除顶部运行时按钮、上下文下拉项、默认值、localStorage 旧值迁移和所有 Legacy toast/文案。
- [x] 发送请求始终传 `single` 或 `multi`；不存在模式时阻止发送并显示真实配置错误，不使用隐式 Legacy 回退。
- [x] Single/Multi 切换时明确处理会话边界：运行中的请求不能被新模式污染；新建会话或下一轮请求使用新模式。
- [x] 删除只给 Legacy 展示的流程节点、示例会话和静态数据；事件展示以 Pi runtime 的真实 SSE 为准。
- [x] 设置页、帮助文案、空状态、截图和前端测试中移除 Legacy。

## 4. 评测和文档

- [x] benchmark 执行器和参数只生成 Single/Multi；历史 `case-N:legacy` 标签不再参与当前汇总。
- [x] 更新 `docs/frontend-testing-plan.md`、`docs/frontend-product-rebuild-plan.md`、`docs/frontend-interaction-inventory.md` 中仍把 Legacy 当作现行能力的内容。
- [x] 在变更记录中列出保留的“legacy”字样及其理由，避免后续误删真正的认证或数据迁移兼容逻辑。

## 通过标准

- [x] `rg -n "legacy" frontend-static dataengineer/api dataengineer/agent contracts tests docs` 的每一条剩余结果都有明确保留理由。
- [x] 前端不显示 Legacy，API schema 不暴露 Legacy，Legacy 请求不会启动任何 Agent。
- [x] Single/Multi 的真实聊天、会话历史、刷新恢复、错误提示和移动端布局回归通过。
- [x] `git diff --check`、Node 语法检查、定向 Python 测试和 OpenAPI 生成/校验通过。

## 交付证据

- 引用分类表：`reports/legacy-removal-inventory.md`
- 定向测试结果：`reports/legacy-removal-tests.md`
- 当前 Single/Multi 截图：`reports/legacy-removal-1440.png`、`reports/legacy-removal-320.png`
- 删除前后关键 API schema 对比和最终 `rg` 结果
