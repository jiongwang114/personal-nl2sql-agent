# Pi Web Runtime And Benchmark Design

## Status

- Approved in conversation on 2026-09-16.
- Implementation begins after written-spec review.
- Production cutover remains blocked until credentials are rotated and benchmark gates pass.

## Problem

The repository has a legacy Python agent workflow and a Pi SQL runtime, but the existing Web chat always uses the legacy workflow. Users need to select and compare the legacy, single-Agent, and multi-Agent variants from the same page. The comparison must use the same runtime paths as Web traffic so benchmark results represent production behavior.

## Scope

This change will:

1. Add a visible `legacy / single / multi` selector to the existing Web page.
2. Add `runtime_variant` to the chat request contract.
3. Route legacy requests through the existing `ChatService` unchanged.
4. Route single and multi requests through Pi using `custom/gpt-5.5`.
5. Convert Pi output and failures into the existing SSE response contract.
6. Add a benchmark runner that invokes all three runtime variants through the same application service.
7. Keep `legacy` as the production default until cutover gates pass.

This change will not replace the external chatbot package, add recursive subagents, or switch production traffic automatically.

## Considered Approaches

### Selected: Isolated Pi Process Per Request

The Python API starts one Pi process for each single or multi request. The process runs without a persistent Pi session and is terminated when the request is cancelled.

Advantages:

- Matches the current Pi extensions and agent definitions.
- Isolates request state and failures.
- Makes cancellation and rollback explicit.
- Avoids introducing another deployed service.

Trade-off: process startup adds latency. A persistent Pi service can replace this implementation later without changing the Web contract.

### Deferred: Persistent Pi Sidecar

A long-running TypeScript service would reduce startup latency and support richer token streaming, but introduces service discovery, health checking, deployment, and session ownership concerns that are unnecessary for the first production comparison.

### Rejected: Reimplement Pi Orchestration In Python

This would reduce process boundaries but duplicate the Agent loop and state machine. It conflicts with the established responsibility split in which Pi owns Agent orchestration and Python owns database, RAG, validation, and execution primitives.

## Request Contract

`StreamChatInput` gains:

```json
{
  "runtime_variant": "legacy | single | multi"
}
```

The field defaults to `legacy`. Existing clients therefore retain current behavior. Invalid values fail request validation.

The Web selector stores the selected variant locally. Before initializing the external chatbot bundle, the page wraps `window.fetch`. The wrapper clones JSON request bodies only for `/api/v1/chat/stream`, adds `runtime_variant`, and delegates every other request unchanged. The API contract remains independent of this page adapter.

## Runtime Components

### Runtime Router

The API route delegates to a runtime router:

- `legacy`: call the existing `ChatService.stream_chat` path.
- `single`: invoke Pi with the baseline tool allowlist.
- `multi`: invoke Pi with the orchestrator and `sql_subagent` tool.

The router owns variant selection only. It does not implement SQL generation, validation, or database access.

### Pi Process Runner

The runner:

- uses the project-local Pi installation;
- selects `custom/gpt-5.5`;
- invokes the appropriate single or multi tool allowlist;
- passes the user question and configured datasource;
- reads Pi JSON events;
- captures the final assistant message and usage metadata;
- terminates the process on cancellation;
- sets a bounded execution timeout;
- never logs prompts, SQL result rows, credentials, or environment values.

Pi continues to call Python capabilities through the existing MCP bridge. SQL execution remains available only through `execute_readonly_sql`.

### SSE Adapter

Pi output is mapped to the existing SSE model so the chatbot does not need a separate rendering system. The first implementation guarantees complete final messages and terminal errors. Token-by-token Pi streaming is optional and must not delay the first release.

Every response identifies the requested and effective runtime variant. Pi failures are returned as explicit SSE errors. The API does not silently execute the same request with legacy because that would invalidate benchmark comparisons and could duplicate database work.

## Web Experience

The existing header receives a compact three-option segmented control:

- Legacy
- Single Agent
- Multi Agent

The initial value is `legacy`. The selection is retained in browser local storage. Changing the selector affects new messages only and does not reinterpret existing session history. The active variant remains visible while a request is running.

The control is keyboard accessible, responsive, and uses the page's existing monochrome design tokens.

## Benchmark

The benchmark runner reads a versioned case file containing at least:

```json
{"task_id":"case-1","question":"...","datasource":"demo"}
```

It executes the same cases through `legacy`, `single`, and `multi`, using `custom/gpt-5.5` for Pi variants and fixed run parameters. Results are appended to separate JSONL files and summarized by the existing comparison script.

Required metrics:

- final result correctness;
- first SQL executability;
- repair success;
- dangerous SQL rejection;
- latency;
- tool calls;
- human intervention.

Token cost is recorded when the provider reports enough usage and pricing data; otherwise it is explicitly unavailable rather than estimated.

The first run uses a small representative subset before the full suite to cap accidental spend and verify the harness.

Correctness is evaluated against the selected benchmark case's expected result or gold SQL execution result. Cases without a machine-checkable expectation are marked for human review and excluded from the automated correctness rate.

## Safety And Cutover

Production remains on `legacy` until all of these conditions hold:

- exposed model and database credentials have been revoked and replaced;
- dangerous SQL rejection is 100%;
- multi-Agent final correctness is not below legacy;
- latency and cost are accepted;
- cancellation works from Web request to Pi child process;
- Pi health failures are visible and legacy remains manually selectable.

Credential rotation is an operational prerequisite and is not performed by application code.

## Error Handling

- Invalid variant: HTTP validation failure.
- Missing Pi executable or model: explicit SSE configuration error.
- Pi timeout: terminate the process and return a timeout event.
- Client cancellation: terminate the Pi process and stop emission.
- Invalid Pi protocol output: return a protocol error without exposing raw stderr secrets.
- SQL Guard rejection: preserve the safe failure; never bypass the Guard.

## Testing

Tests will cover:

- request model default and variant validation;
- router selection for all three variants;
- Pi command construction without starting a paid model;
- Pi JSON event parsing and final-message conversion;
- cancellation and timeout cleanup;
- SSE success and error mapping;
- benchmark case loading, resume behavior, and aggregation;
- Web selector layout and request augmentation at desktop and mobile widths.

The real-model smoke benchmark runs only after deterministic tests pass. Production cutover is a separate operation after benchmark review and credential rotation.
