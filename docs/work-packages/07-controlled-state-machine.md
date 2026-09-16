# WP-07: Controlled State Machine

## Status

- state: complete
- depends_on: [WP-06]

## Objective

阻止主 Agent 以非法顺序调用角色。

## Implemented Transitions

```text
classified       -> schema-analyst      -> schema_ready
schema_ready     -> sql-generator       -> sql_generated
guard_passed     -> sql-reviewer        -> reviewed
execution_failed -> sql-debugger        -> sql_repaired
executed         -> result-interpreter  -> interpreted
```

## Enforcement

- `sql_subagent` 在启动子进程前校验当前状态。
- 子 Agent 最终 JSON 的 `next_state` 必须匹配预期状态。
- `sql_subagent` 要求调用方传入 `repair_attempts`，达到 2 次后拒绝再次启动 `sql-debugger`。
- SQL 执行只有 `execute_readonly_sql` 一个公开入口。

## Deferred

跨进程持久状态恢复属于下一版；当前状态由每次工具调用显式携带并验证。
