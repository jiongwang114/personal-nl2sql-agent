# WP-06: First-Level SQL Agents

## Status

- state: complete
- depends_on: [WP-04, WP-05]

## Objective

实现五个隔离的一级 SQL 子 Agent。

## Deliverables

- `.pi/agents/schema-analyst.md`
- `.pi/agents/sql-generator.md`
- `.pi/agents/sql-debugger.md`
- `.pi/agents/sql-reviewer.md`
- `.pi/agents/result-interpreter.md`
- `.pi/extensions/sql-agents/index.ts`

## Boundaries

- 每个角色拥有最小工具集。
- 每个角色必须返回 JSON envelope。
- 子进程设置 `PI_SQL_CHILD=1`，不注册 `sql_subagent`，禁止递归。
- Agent 名称必须来自代码白名单。

## Verification

- TypeScript strict check passed。
- 完整模型调用需要有效模型凭据。
