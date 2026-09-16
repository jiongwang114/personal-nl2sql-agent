# WP-08: Debugger And Reviewer

## Status

- state: complete
- depends_on: [WP-07]

## Objective

将异常修复和 SQL 审查拆成权限受限的独立角色。

## Debugger

- 仅从 `execution_failed` 进入。
- 可刷新 Schema 并调用 `validate_sql`。
- 不能执行 SQL。
- 返回修复 SQL、错误分类、原因和变更。

## Reviewer

- 仅从 `guard_passed` 进入。
- 返回 `pass`、`warn` 或 `block`。
- 检查语义、Join、聚合、过滤、性能和可维护性。
- 不能执行 SQL；程序 Guard 优先级更高。

## Retry Policy

共享状态契约限制 `repair_attempts <= 2`。Orchestrator prompt 同时声明该限制。
