# WP-10: API And Feishu Migration Readiness

> Historical migration design. Its Legacy fallback and rollout fields are not current API behavior; see `docs/frontend-next-work-plan.md` for the active runtime contract.

## Status

- state: design_complete; cutover_blocked_by_benchmark
- depends_on: [WP-09]

## Objective

定义 API 和 Feishu 如何选择旧 workflow、单 Agent 或多 Agent Runtime，不提前切换生产流量。

## Adapter Contract

渠道请求增加内部路由字段：

```json
{
  "runtime_variant": "legacy | single | multi",
  "datasource": "demo",
  "question": "...",
  "request_id": "..."
}
```

渠道层只负责身份、传输、流式展示和人工确认，不实现 Agent 路由或 SQL 安全策略。

## Rollout

1. 默认 `legacy`。
2. 内部用户显式选择 `single` 或 `multi`。
3. 记录统一评测指标。
4. 达到验收线后对小比例请求启用 `multi`。
5. Pi/MCP 健康检查失败时回退 `legacy`。

## Cutover Gates

- 危险 SQL 拦截率 100%。
- 最终执行正确率不低于旧 workflow。
- 延迟和成本在已批准预算内。
- API/Feishu 支持取消和人工确认。
- 配置文件中的已暴露凭据完成轮换。

## Non-goal

本工作包不直接修改现有 API 或 Feishu 路由。真实 benchmark 未完成前切流不符合设计约束。
