# Legacy、Single、Multi 真实对照评测记录

评测日期：2026-09-18。每种模式运行同一组 8 个问题，共 24 次真实 Web API 请求。本页记录这一次实验，不代表多次重复实验或统计显著的总体性能。

> 历史记录：本实验执行时 Legacy 仍可选。当前阶段只比较 Single/Multi；原始 JSONL 与人工标签保留作历史证据，当前汇总已排除 Legacy。本页的三模式运行命令不再被现行 benchmark 执行器接受。

## 方法

1. 使用 `benchmark/semantic_layer/testing_set.csv` 中的 8 个问题，统一指定 `benchmark_demo` 数据源和每次请求 180 秒超时。
2. 向同一 Web API 分别发送 `legacy`、`single` 和 `multi` 请求。`scripts/run_pi_benchmark.py` 逐条写入 JSONL，失败和超时也保留。
3. 在 `sample_data/mf-demo.duckdb` 上直接执行参考 SQL；结合问题要求审阅响应，将逐题正确性保存于 `benchmark/semantic_layer/result_labels.json`。
4. `scripts/compare_pi_variants.py` 合并人工标签，计算完成率、正确率、中位延迟和 P95 延迟。正确率的分母包含失败与超时请求。延迟统计也包含以 180 秒记录的超时请求；P95 使用最近秩法。

复现命令（需自行配置模型凭据，先启动 API）：

```powershell
python scripts/run_pi_benchmark.py `
  --cases benchmark/semantic_layer/testing_set.csv `
  --output reports/benchmark-raw.jsonl `
  --base-url http://127.0.0.1:8512 `
  --variants legacy,single,multi `
  --datasource benchmark_demo --timeout 180

python scripts/compare_pi_variants.py reports/benchmark-raw.jsonl `
  --labels benchmark/semantic_layer/result_labels.json `
  --output reports/benchmark-summary.json
```

`reports/` 是本地运行证据目录，不纳入公开 Git。仓库保留测试集、人工标签、评测脚本和样例数据库；重新运行模型时，生成结果可能不同。人工标签只适用于这一次响应，复评时必须重新审阅，不能沿用旧标签来声称新运行的正确率。

## 结果

| 模式（每组 n=8） | 正确 | 完成 | 中位延迟 | P95 延迟 |
| --- | ---: | ---: | ---: | ---: |
| Legacy | 5/8（62.5%） | 5/8（62.5%） | 12.891 秒 | 180 秒 |
| Single | 3/8（37.5%） | 5/8（62.5%） | 142.258 秒 | 180 秒 |
| Multi | 1/8（12.5%） | 6/8（75.0%） | 109.586 秒 | 180 秒 |

人工判定为正确的案例：Legacy 为 1、2、4、5、7；Single 为 1、5、7；Multi 为 2。案例 3 的三种模式均超时；案例 6 的 Legacy 和 Single 超时；案例 8 的三种模式均失败或超时。

## 限制

- 样本量只有每组 8 题，不能将上述百分比外推为产品整体正确率。
- HTTP 客户端超时后，服务端任务仍可能继续运行。在本次实验中，这种残留工作影响了后续请求，需要重启服务。因而后续请求的延迟不能视为隔离负载下的结果。
- P95 均达到 180 秒的超时上限，它是截断观测值，不表示真实服务端完成时间恰为 180 秒。
- 三种运行链路的模型配置并不完全相同。本次结果比较的是具体系统配置，不是仅改变 Agent 数量的受控消融实验。
- 本历史实验的结论仅为：在这 8 题和这次配置下，Legacy 正确数最高；Multi 完成数最高，但正确数最低。不能据此宣称 Multi 提高了准确率或降低了延迟。
