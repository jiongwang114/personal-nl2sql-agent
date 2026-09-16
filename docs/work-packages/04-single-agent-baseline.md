# WP-04: Single-Agent Pi Baseline

## Status

- state: complete
- depends_on: [WP-03]

## Objective

建立一个拥有全部批准领域工具的单 Agent，作为多 Agent 的公平基线。

## Deliverables

- `.pi/agents/baseline-agent.md`
- `.pi/extensions/sql-tools/index.ts`
- `scripts/pi_mcp_bridge.py`
- `scripts/run_pi_sql.ps1 -Mode single`

## Constraints

- 与多 Agent 使用同一个 MCP Server、Guard 和执行工具。
- 不允许调用子 Agent。
- SQL 修复最多两次。

## Verification

- Python bridge 已通过真实 MCP stdio 调用 `validate_sql`。
- `.pi` TypeScript 检查通过。
- 完整模型 benchmark 需要有效模型凭据，结果不能在实现阶段伪造。
