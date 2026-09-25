# 前后端接口联调结果

更新日期：2026-09-22

## 已接入接口

| 前端功能 | 后端接口 | 状态 |
| --- | --- | --- |
| 服务状态 | `GET /health` | 已接入 |
| 会话列表、历史、删除 | `GET /api/v1/chat/sessions`、`GET /api/v1/chat/history`、`DELETE /api/v1/chat/sessions/{id}` | 已接入请求层；列表和历史已在页面使用 |
| 流式聊天 | `POST /api/v1/chat/stream` | 已接入 Pi runtime SSE，仅支持 `single`、`multi`；缺省为 `single`，其他值返回 HTTP 422 |
| Single/Multi 停止与恢复 | SSE 请求中止；不支持恢复未完成的生成 | 停止关闭当前流，未完成回答不写入历史；TaskManager 的 stop/resume API 仅保留给独立兼容流程 |
| 用户补充输入 | `POST /api/v1/chat/user_interaction` | 已接入选项和文本表单 |
| Agent | `GET /api/v1/agent/list` | 已接入列表和聊天选择器 |
| 模型 | `GET /api/v1/models` | 已接入选择器 |
| 数据库资源 | `GET /api/v1/catalog/list` | 已接入数据库和表列表 |
| SQL 执行 | `POST /api/v1/sql/execute` | 已接入 JSON 结果表格 |
| 图表建议 | `POST /api/v1/data_visualization` | 已接入 SQL 结果图表建议 |
| 主题、指标和知识树 | `GET /api/v1/subject/list` | 已接入主题模型和知识库页面 |
| MCP Server | `GET /api/v1/mcp/servers` | 已接入列表 |
| 配置摘要 | `GET /api/v1/config/agent` | 已接入只读页面，敏感字段由后端脱敏 |

所有请求统一经过 `frontend/src/lib/api.ts`。生产构建默认同源请求；开发环境可用 Vite 代理，或通过 `VITE_API_BASE_URL` 指向其他后端。默认开源认证使用可选的 `X-Datus-User-Id`，由 `VITE_USER_ID` 提供；请求同时携带同源凭据以兼容自定义认证 Provider。

## 暂未开放

- 附件按钮保持禁用。后端没有已确认的浏览器附件上传接口。
- 系统设置只展示真实配置摘要。后端没有“工作区名称”和“全局只读模式”的统一更新接口。
- Agent、MCP、主题、指标和知识的创建/编辑后端接口虽然存在，但当前页面没有定义完整表单和确认流程，本次不猜测字段级业务交互。
- `user-interaction` 已支持单选和文本；后端 `multiSelect` 的浏览器交互仍待补充。
- 聊天回答反馈请求封装已存在，但当前页面设计没有反馈入口。
- `single` / `multi` 运行时只接受其运行时配置中已登记的数据源；选择仅存在于主 Agent 配置中的数据源时，后端会返回明确错误，前端保留错误与重试状态。

## 启动方式

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .

Set-Location frontend
npm install
npm test
npm run build
Set-Location ..

dataengineer --web --datasource demo --host 127.0.0.1 --port 8512
```

浏览器访问 `http://127.0.0.1:8512`。若该端口被占用，可换用其他端口；前后端同源部署不需要额外 CORS 配置。分离开发时后端通过 `DATAENGINEER_CORS_ORIGINS` 限制允许来源。

## 验证范围

- 前端 TypeScript 生产构建和 Vitest 单元测试。
- 后端 API 单元测试、Explorer/配置/SQL 回归测试及 Ruff 检查。
- 实际 FastAPI 启动、静态资源加载、核心 GET 接口、SQL `SELECT 1`、CORS 预检。
- Playwright 在 320、768、1024、1440 像素宽度检查页面、横向溢出和浏览器控制台错误。

聊天最终回答依赖本地配置的模型凭据；没有有效 Provider 凭据时，页面会显示后端错误状态，不会使用模拟回答。
模型选择器默认沿用后端活动模型；用户显式选择模型时，前端按聊天接口要求发送 `provider/model_id`。
