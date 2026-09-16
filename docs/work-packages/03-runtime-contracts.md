# WP-03: Runtime Contracts

## Status

- state: complete
- depends_on: [WP-02]

## Objective

为单 Agent 和多 Agent 定义同一套 SQL 任务状态与工具结果结构。

## Deliverables

- `contracts/sql-task-state.schema.json`
- `contracts/sql-tool-result.schema.json`

## Decisions

- 契约版本从 `1.0` 开始。
- 修复次数上限为 2。
- Guard 和执行结果使用独立定义并被任务状态引用。
- Agent 间传递 JSON，不依赖自由文本保存状态。

## Verification

- JSON 文件已重新读取并由后续代码使用。
- TypeScript Extension 检查通过。
