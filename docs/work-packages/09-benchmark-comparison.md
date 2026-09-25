# WP-09: Benchmark Comparison

> Historical work package. Its three-way rollout notes are superseded by `docs/frontend-next-work-plan.md`; current benchmark runs only Single and Multi.

## Status

- state: smoke_run_blocked; full_model_runs_pending
- depends_on: [WP-04, WP-08]

## Objective

使用统一记录比较旧 workflow、单 Agent 和多 Agent。

## Deliverables

- `.pi/extensions/sql-observability/index.ts`
- `scripts/compare_pi_variants.py`
- `scripts/run_pi_benchmark.py`
- `tests/unit_tests/scripts/test_compare_pi_variants.py`

## Input Record

每行 JSON 至少包含：

```json
{"variant":"single","task_id":"case-1","result_correct":true}
```

可选指标：

- `first_sql_executable`
- `repair_success`
- `dangerous_sql_rejected`
- `latency_ms`
- `token_cost`
- `tool_calls`
- `human_intervention`

## Verification

- 汇总脚本单元测试通过。
- Web runner 已对同一案例发起 single/multi 真实请求，Pi 扩展均成功注册并分别产生 2 次工具调用。
- Windows 下 Web 与 MCP 子进程不能共享已打开的 DuckDB；Pi Runtime 现为每次请求创建只读数据库快照并在结束后清理。
- `custom/gpt-5.5` 在工具结果后的续请求约 65 秒返回 `LiteLLM/OpenAI connection error`，因此本轮没有可判定的 SQL 或正确率，不能计为成功 Benchmark。
- RAG 工具仍由 Extension 注册，但当前 Web baseline 默认只启用本地结构、校验和只读执行工具；恢复 RAG 模型端点后再纳入正式对照。
- 生产默认保持 `legacy`，直到凭据轮换、三档完整 Benchmark 和人工结果评审全部通过。
