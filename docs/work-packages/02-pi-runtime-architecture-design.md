# Pi SQL Agent Runtime Architecture

## 1. Goal

将现有 Data Engineer Agent 的模型循环和顶层 workflow 逐步迁移到 Pi，同时保留已经成熟的 Python 数据领域能力。

目标产品面向数据工程师，覆盖：

- NL2SQL
- SQL 语法和方言检查
- SQL 异常定位与自动修复
- SQL 语义和性能审查
- 只读执行与结果解释

## 2. Architecture Principles

1. 单次请求只能有一个顶层编排器。
2. Agent 负责有歧义的推理，程序负责确定性校验和安全边界。
3. Python 是数据控制面；Pi 是 Agent Runtime。
4. 单 Agent 与多 Agent 必须共享模型、工具、安全策略和 benchmark。
5. 第一版只允许一级子 Agent，不允许递归委派。
6. 所有执行路径必须有次数、时间和结果大小上限。
7. 旧 workflow 在迁移期间只作为基线和回退路径。

## 3. System Context

```text
CLI / Web API / Feishu
          |
          v
Pi Orchestrator Session
          |
          +---- Pi Extensions
          |       |- SQL state machine
          |       |- SQL guard integration
          |       |- subagent dispatch
          |       `- trace and evaluation events
          |
          +---- Pi Agents
          |       |- baseline-agent
          |       |- schema-analyst
          |       |- sql-generator
          |       |- sql-debugger
          |       |- sql-reviewer
          |       `- result-interpreter
          |
          `---- MCP Client
                    |
                    v
          Existing Python MCP Server
                    |
                    +---- Schema / value RAG
                    +---- metrics / reference SQL
                    +---- database adapters
                    +---- SQL validation primitives
                    +---- read-only execution gateway
                    `---- benchmark artifacts
```

## 4. Ownership Boundaries

### 4.1 Pi owns

- Conversation history and model loop
- User intent routing
- Legal workflow transitions
- First-level subagent dispatch
- Agent tool allowlists
- Retry ceiling and termination
- Human confirmation requests
- Correlation IDs and Agent-level traces
- Single-Agent and multi-Agent runtime variants

### 4.2 Python owns

- Datasource credentials and connection lifecycle
- Database dialect and adapter behavior
- Schema metadata and value retrieval
- RAG indexes and retrieval
- Metrics and reference SQL stores
- SQL parsing and deterministic validation primitives
- Read-only query execution
- Timeout, row, scope and resource enforcement
- Benchmark datasets and scoring

### 4.3 Channels own

- Authentication and user identity
- Request/response transport
- Streaming presentation
- User confirmation UI

Channels must not contain Agent routing or SQL security rules.

## 5. Runtime Variants

### 5.1 Legacy workflow baseline

The existing `WorkflowRunner` remains unchanged and provides historical results.

```text
request -> legacy WorkflowRunner -> Python nodes -> result
```

It is not called from the new Pi production path.

### 5.2 Single-Agent Pi baseline

One Pi Agent receives all permitted domain tools:

```text
request
  -> baseline-agent
  -> schema tools
  -> SQL generation reasoning
  -> mandatory SQL Guard
  -> read-only execution
  -> repair, at most twice
  -> result explanation
```

This is the primary comparison baseline for multi-Agent evaluation.

### 5.3 Multi-Agent Pi path

```text
request
  -> orchestrator
  -> schema-analyst
  -> sql-generator
  -> mandatory SQL Guard
  -> sql-reviewer
  -> read-only execution
  -> result-interpreter
```

On execution failure:

```text
structured error
  -> sql-debugger
  -> mandatory SQL Guard
  -> optional review
  -> read-only execution
  -> at most two repair attempts total
```

## 6. Agent Responsibilities

### 6.1 Orchestrator

Responsibilities:

- Classify the request as NL2SQL, review, debug or knowledge question
- Select legal next states
- Dispatch first-level Agents
- Request clarification when business meaning is ambiguous
- Produce the final response from structured results

Restrictions:

- Cannot execute SQL directly
- Cannot bypass Guard
- Cannot create arbitrary Agent definitions during production requests
- Cannot dispatch recursive descendants

### 6.2 Schema Analyst

Inputs:

- User question
- Datasource and dialect
- Optional known tables or business domain

Outputs:

- Relevant tables and columns
- Join candidates and evidence
- Relevant metrics and reference SQL
- Retrieval sources and confidence
- Ambiguities requiring user clarification

Tools:

- `search_table`
- `list_schemas`
- `list_tables`
- `describe_table`
- `get_table_ddl`
- normalized metrics/reference retrieval tools

It cannot generate final SQL or execute queries.

### 6.3 SQL Generator

Inputs:

- User question
- Dialect
- Approved Schema context
- Metrics and reference SQL
- Previous SQL context when present

Outputs:

- One candidate SQL by default
- Up to three candidates only when business meaning or Join strategy differs
- Referenced tables and columns
- Short rationale and assumptions

It cannot execute SQL.

### 6.4 SQL Debugger

Inputs:

- Original question and SQL
- Dialect and Schema context
- Parser/Guard diagnostics
- Database error or EXPLAIN output
- Previous repair attempts

Outputs:

- Corrected SQL
- Error classification
- Correction rationale
- Whether user clarification is required

It cannot execute SQL or bypass Guard.

### 6.5 SQL Reviewer

Inputs:

- Question, Schema evidence and candidate SQL
- Guard result
- Optional EXPLAIN output

Outputs:

- `pass`, `warn` or `block`
- Semantic correctness findings
- Join, aggregation and filter risks
- Performance and maintainability findings
- Suggested correction

Programmatic Guard decisions override Reviewer decisions.

### 6.6 Result Interpreter

Inputs:

- Original question
- Executed SQL
- Structured result preview and metadata
- Warnings and assumptions

Outputs:

- Direct answer
- Evidence and limitations
- Optional `need_more_data` request

It cannot execute arbitrary SQL. Additional data requests return to the Orchestrator and re-enter the guarded path.

## 7. State Machine

Legal states:

```text
received
classified
schema_ready
sql_generated
guard_passed
reviewed
executed
interpreted
completed
needs_clarification
failed
```

Debug states:

```text
execution_failed
diagnosed
sql_repaired
guard_passed
executed
```

Mandatory rules:

- `sql_generated` cannot transition directly to `executed`.
- Every new or repaired SQL must pass Guard.
- A Guard `block` is terminal unless a new SQL candidate is generated.
- Repair attempts are capped at two.
- Result Interpreter cannot transition back to execution without Orchestrator approval.
- Sensitive data, high estimated cost or unresolved business ambiguity transitions to `needs_clarification`.

## 8. Extension Boundaries

### 8.1 `sql-tools-extension`

- Connect Pi to the existing Python MCP Server
- Select datasource context
- Normalize MCP errors for the Agent layer
- Expose only approved domain tools

It does not contain SQL workflow logic.

### 8.2 `sql-guard-extension`

- Invoke deterministic validation
- Enforce single-statement and read-only policy
- Require datasource and dialect
- Enforce timeout, row and scope policy
- Attach structured Guard results
- Prevent execution when validation fails

The Python gateway repeats enforcement at the execution boundary.

### 8.3 `sql-agents-extension`

- Register the Orchestrator-facing dispatch tool
- Discover the five project Agent definitions
- Enforce first-level-only delegation
- Validate Agent input and output contracts
- Maintain legal state transitions

### 8.4 `sql-observability-extension`

- Assign request and attempt correlation IDs
- Record transitions, tool calls, Agent calls and durations
- Record model and token usage
- Emit the common evaluation record

It cannot change routing decisions.

## 9. Security Model

### 9.1 Defense in depth

```text
Agent tool allowlist
  -> Pi Guard policy
  -> MCP input validation
  -> Python SQL AST validation
  -> datasource/table scope
  -> read-only database credential
  -> timeout and resource limits
```

Prompt instructions are guidance, not authorization.

### 9.2 Default execution policy

- Allow only one `SELECT` or supported read-only `EXPLAIN` statement.
- Reject DDL, DML, transaction control and multiple statements.
- Apply datasource and table scopes.
- Apply timeout and maximum result rows.
- Return a truncated preview plus full result metadata.
- Require human confirmation for sensitive columns or excessive estimated cost.

## 10. Failure And Recovery

| Failure | Owner | Behavior |
|---|---|---|
| MCP unavailable | Pi tools extension | Fail request with retryable infrastructure error |
| Schema retrieval empty | Schema Analyst | Broaden once, then ask for clarification |
| Invalid SQL syntax | Guard/Debugger | Diagnose and repair within retry budget |
| Unknown table/column | Debugger | Refresh Schema evidence before repair |
| Permission denied | Python gateway | Terminal; do not retry with broader scope |
| Timeout/resource limit | Python gateway | Terminal or require user-approved narrower query |
| Reviewer block | Orchestrator | Generate corrected candidate or ask user |
| Output contract invalid | Agent extension | One schema-correction retry, then fail |
| User cancellation | Pi Runtime | Abort active child process and MCP request |

## 11. Observability Contract

Every request records:

- Request, session and datasource IDs
- Runtime variant: legacy, single-Agent or multi-Agent
- Model and Agent identity
- State transitions
- Tool calls, durations and error classes
- Candidate and repair attempt counts
- Guard and Reviewer decisions
- Execution time and truncation
- Token usage and estimated cost
- Final benchmark labels when available

Secrets, credentials and unmasked sensitive row values must not be included.

## 12. Evaluation Design

Compare:

```text
legacy fixed workflow
single Pi Agent with all approved tools
multi-Agent Pi with controlled routing
```

Controlled variables:

- Same model and reasoning level
- Same dataset and question set
- Same MCP tools and retrieval indexes
- Same Guard and database policy
- Same timeout and retry budget

Primary metrics:

- Execution-result correctness
- First SQL executability
- Automatic repair success
- Schema Recall
- Dangerous SQL rejection
- Latency
- Token cost
- Tool calls
- Human intervention rate

## 13. Migration Plan

### Milestone 1: Contracts

- Define shared SQL task state
- Define normalized MCP envelopes
- Define Guard and error schemas

### Milestone 2: Single-Agent baseline

- Connect Pi to current MCP Server
- Implement Guard boundary
- Run existing evaluation set

### Milestone 3: Multi-Agent runtime

- Add five Agent definitions
- Add controlled dispatcher and state machine
- Keep recursive delegation disabled

### Milestone 4: Debug and review

- Add structured error classification
- Add repair loop and Reviewer
- Add EXPLAIN integration

### Milestone 5: Channel migration

- Integrate Web API
- Add Feishu adapter
- Retain legacy fallback until acceptance thresholds pass

## 14. Rollback

- Select runtime variant per request or deployment configuration.
- Do not modify legacy workflow outputs during the comparison period.
- If Pi or MCP fails operational thresholds, route new traffic to legacy workflow.
- Store evaluation records in a common format so results remain comparable.

## 15. Decisions Deferred To WP-03

- Exact JSON Schema fields and versioning
- Exact SQL parser/AST library
- Supported first-release dialects
- Concrete timeout, row and scan limits
- MCP tool aliases versus new wrapper tools
- Trace storage format
