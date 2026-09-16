# WP-01 Result: Domain Tool Inventory

## Summary

现有项目已经具备可复用的数据库工具、Schema/RAG、动态 MCP Server、固定 workflow、AgenticNode、子 Agent 调度和 benchmark。Pi 重构不应复制这些领域能力，而应：

1. 复用现有 Python MCP Server 暴露领域工具。
2. 用 Pi 替换现有 Agent Runtime 和顶层编排。
3. 保留旧 workflow 作为回归基线。
4. 新增 SQL Guard、统一状态契约和缺失的诊断工具。

## Current Runtime And Call Chain

当前 SQL 主路径由配置选择 workflow，并由 `WorkflowRunner` 顺序运行节点：

```text
request
  -> WorkflowRunner
  -> generate_workflow
  -> schema_linking
  -> generate_sql
  -> execute_sql (部分 workflow)
  -> reflect/fix (部分 workflow)
  -> output
```

主要证据：

- `dataengineer/agent/workflow_runner.py`
- `dataengineer/agent/workflow.py`
- `dataengineer/agent/workflow.yml`
- `dataengineer/agent/plan.py`
- `conf/agent_baseline.yml`

`Workflow` 保存顺序节点、当前节点、共享 `Context`、SQL 上下文和反思轮次。该层与未来 Pi 状态机职责重叠，迁移期间只能保留一方作为单次请求的顶层编排器。

## Existing MCP Boundary

项目已有可直接运行的动态和静态 MCP Server：

- `dataengineer/mcp_server.py`
- `dataengineer/tools/mcp_tools/`
- `dataengineer/utils/mcp_decorators.py`

工具通过 `@mcp_tool_class` 和 `@mcp_tool` 自动注册。动态 Server 按 datasource/subagent 建立并缓存工具上下文，适合作为 Pi 的第一版 Python 接口，不需要重新设计一套 HTTP 包装。

## Reusable Deterministic Tools

| Target capability | Existing implementation | Current MCP tool | Decision |
|---|---|---|---|
| Search schema | `DBFuncTool.search_table` and Schema RAG | `search_table` | Reuse; expose to Schema Analyst |
| List databases | `DBFuncTool.list_databases` | `list_databases` | Reuse |
| List schemas | `DBFuncTool.list_schemas` | `list_schemas` | Reuse |
| List tables | `DBFuncTool.list_tables` | `list_tables` | Reuse |
| Describe table | `DBFuncTool.describe_table` | `describe_table` | Reuse |
| Read table DDL | `DBFuncTool.get_table_ddl` | `get_table_ddl` | Reuse |
| Execute read query | `DBFuncTool.read_query` | `read_query` | Reuse behind SQL Guard |
| Search metrics | semantic/context tools and `SearchMetricsNode` | Existing registry-dependent tools | Adapt and give one stable contract |
| Search reference SQL | `ReferenceTemplateTools` | Existing registry-dependent tools | Adapt and give one stable contract |

`DBFuncTool` is located at `dataengineer/tools/func_tool/database.py`. It supports multiple datasource adapters and datasource-scoped instances.

## Existing Agent Or LLM Capabilities

These are not deterministic tools and should become Pi agents or remain baseline implementations:

| Capability | Existing implementation | Pi target |
|---|---|---|
| Schema linking | `MatchSchemaTool`, `SchemaLinkingNode` | `schema-analyst` using deterministic retrieval tools |
| SQL generation | `GenerateSQLNode.generate_sql` | `sql-generator` |
| SQL repair | `autofix_sql`, `FixNode` | `sql-debugger` |
| Reflection | `ReflectNode` | Replace with explicit Guard/Reviewer outcomes |
| Result summary | SQL summary/output nodes | `result-interpreter` |
| General subagent task | `SubAgentTaskTool` | Keep only as old-system baseline; Pi owns new dispatch |

The existing SQL generator already consumes Schema, values, metrics, prior SQL contexts, external knowledge and documents. Those fields should inform the new shared state contract rather than being discarded.

## Safety And Side Effects

### Confirmed protections

- `read_query` is the intended read-only execution entry point.
- Adapter integration tests verify rejection of DML through `read_query`.
- Adapter integration tests verify rejection of multiple statements.
- `scoped_tables` is tested for table visibility restrictions.
- Separate write and DDL methods exist and are not decorated as general MCP tools in the inspected database tool surface.

### Gaps

- No standalone cross-dialect SQL AST Guard was identified as the mandatory entry point before `read_query`.
- No stable `validate_sql` MCP contract was identified for query SQL; `validate_ddl` is DDL-specific.
- No stable `explain_sql` MCP tool was identified.
- Database errors are returned, but no stable `classify_sql_error` contract was identified.
- Query timeout, scan budget and result-row limits are adapter-dependent and need one enforced gateway policy.
- Agent prompts must not be treated as a security boundary.
- A checked-in runtime configuration contains credential material. Rotate exposed credentials and keep only environment-variable references before further integration.

## Test And Benchmark Evidence

Relevant coverage already exists:

- `tests/integration/tools/test_mcp_server.py`
- `tests/integration/tools/test_func_tools_db.py`
- `tests/integration/adapters/test_clickhouse.py`
- `tests/integration/adapters/test_greenplum.py`
- `tests/integration/adapters/test_starrocks.py`
- `tests/unit_tests/benchmark/test_schema_recall_metrics.py`
- `tests/regression/`
- `benchmark/scripts/`

The MCP tests cover discovery and execution of `list_tables`, `describe_table` and `read_query` across configured datasources. Existing benchmark code can remain the common evaluator for old workflow, single-Agent Pi and multi-Agent Pi variants.

## Proposed Stable MCP Surface

### Reuse without semantic change

```text
search_table
list_databases
list_schemas
list_tables
describe_table
get_table_ddl
read_query
```

### Add or normalize before multi-Agent implementation

```text
search_metrics
search_reference_sql
find_join_paths
validate_sql
explain_sql
execute_readonly_sql
classify_sql_error
```

`execute_readonly_sql` may initially wrap `read_query`, but it must return a stable envelope containing datasource, dialect, columns, rows, row count, truncation, elapsed time and structured error information.

## Pi Ownership Boundary

```text
Pi:
  conversation and model loop
  orchestrator
  five first-level agents
  legal state transitions
  retry ceiling
  tool permission sets
  trace correlation

Python:
  datasource configuration
  database adapters
  Schema and value RAG
  metrics/reference SQL retrieval
  SQL validation primitives
  read-only execution gateway
  benchmark datasets and scoring
```

Pi must not invoke the old `WorkflowRunner` inside the new production path. Doing so would create two competing orchestrators. The old runner remains available only for baseline evaluation during migration.

## Blockers For WP-02 And WP-03

1. Define one shared SQL task state and tool result envelope.
2. Decide the concrete SQL parser/AST library and supported dialect set.
3. Normalize metrics and reference-SQL retrieval into stable MCP contracts.
4. Add stable validation, EXPLAIN and error-classification contracts.
5. Define timeout, row limit, scan budget and datasource scope policy.
6. Remove or rotate checked-in credentials before running external integrations.

## Recommendation

WP-02 should now specify the target architecture and migration boundary. WP-03 should define contracts before any Pi Extension or agent Markdown is implemented. The first executable milestone should use the existing MCP Server and a single Pi agent; multi-Agent behavior should be added only after the common baseline works.
