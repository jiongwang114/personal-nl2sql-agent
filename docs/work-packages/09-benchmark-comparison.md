# WP-09: Benchmark Comparison

## Status

- state: implementation_complete; model_runs_pending
- depends_on: [WP-04, WP-08]

## Objective

使用统一记录比较旧 workflow、单 Agent 和多 Agent。

## Deliverables

- `.pi/extensions/sql-observability/index.ts`
- `scripts/compare_pi_variants.py`
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
- 运行真实对照实验需要相同模型凭据、问题集和参数；尚未生成虚假结果。
