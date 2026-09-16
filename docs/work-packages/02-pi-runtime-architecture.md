# WP-02: Pi Runtime Architecture

## Status

- state: complete
- owner: pi-agent
- depends_on: [WP-01]
- scope: architecture design

## Objective

定义 Pi Runtime 重构的目标架构、职责边界、调用时序、迁移路径和失败边界。

## Inputs

- `01-domain-tool-inventory-result.md`
- 现有 `WorkflowRunner` 和节点实现
- 现有动态 MCP Server
- 现有 benchmark 和回归测试

## Deliverable

- `02-pi-runtime-architecture-design.md`

## Non-goals

- 不实现 Extension
- 不修改 Python 工具
- 不定义字段级 JSON Schema
- 不切换 API、CLI 或 Feishu 流量

## Acceptance Criteria

- 单 Agent 和多 Agent 使用相同工具、安全策略及评测集
- Pi 和 Python 的所有权边界唯一且明确
- 生产路径中只有一个顶层编排器
- 明确失败、重试、人工介入和终止条件
- 迁移过程可回滚到旧 workflow

## Verification

- test command: none; design-only work package
- benchmark command: none
- result: complete; see `02-pi-runtime-architecture-design.md`
