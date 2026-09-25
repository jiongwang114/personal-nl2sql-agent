# 测试、评测与公开发布任务清单

更新时间：2026-09-19

本文档是测试、对照评测和公开仓库整理工作的统一任务账本。只有执行命令成功，且证据已保存到指定路径，任务才算完成。

## 1. 全量测试与覆盖率

- [x] 使用 `uv` 创建可复现的 Python 3.12 环境。
- [x] 使 `uv lock --check` 通过。
- [x] 恢复运行所需的认证模块和网关适配器模块。
- [x] 完成确定性验收测试：153 项通过，9 项按声明条件跳过。
- [x] 测量最终验收范围内的 `dataengineer` 覆盖率：29.25%。
- [x] 将验收测试证据保存到 `reports/junit-acceptance.xml`、`reports/coverage-acceptance.xml` 和 `reports/coverage-acceptance.json`。
- [x] 完成评测执行器、结果比较脚本、认证、网关适配器和 CLI 的针对性回归测试：109 项通过。
- [x] 完整运行所有非 nightly 单元测试：10,678 通过、15 跳过、1 预期失败。
- [x] 修复已确认的单元测试失败；剩余条件跳过与已知问题见 `docs/test-evidence.md`。
- [x] 最终代码修改完成后，重新完整运行一次验收测试：153 通过、9 个模块按条件跳过。
- [x] 在 `docs/test-evidence.md` 记录最终命令、数量、耗时、跳过项与覆盖率。

完成条件：非 nightly 单元测试和最终验收测试都完整执行成功，并明确说明条件跳过项和排除范围。

2026-09-19 Windows 全量尝试：`uv run pytest tests/unit_tests -m 'not nightly' -q -o addopts='' -o log_cli=false --timeout=120 --basetemp=R:\.pytest-tmp-unit-controlled --junitxml=reports/junit-unit-full.xml`。JUnit 记录 10,694 项，223 失败、24 错误、15 跳过，耗时 291.323 秒；因此目前**不能**声明全量通过。API 守护进程单文件修复后为 48/48 通过。失败中 140 项（含 setup 错误）与 Windows `prompt_toolkit` 无控制台句柄有关；其余包括可选 `datus` 依赖、旧调度器接口断言、Windows 路径/符号链接/文件锁语义等，仍须逐类核查。完整失败详情见本地 `reports/junit-unit-full.xml`。全量轮次的约 13 GB Pytest 临时目录已删除，D 盘恢复约 42.7 GB 可用；下一轮还须把 `TEMP`、`TMP` 指向 D 盘。

CLI 无控制台输出夹具修复后，单独运行 `tests/unit_tests/cli`：2,184 通过、22 失败、1 预期失败，耗时 33.427 秒，详见 `reports/junit-cli.xml`。剩余失败需要区分过时的 `Datus` 品牌断言、POSIX 路径假设及 Windows 权限/文件语义；完整单测仍须在全部修改完成后重跑。后续轮次已将 `TEMP` 和 `TMP` 指向 D 盘。

2026-09-19 带覆盖率全量复测：10,613 通过、65 失败、15 跳过、1 预期失败（JUnit 的 skipped 总计 16），耗时 548.51 秒。覆盖率为 `dataengineer` 45,133/55,193 行，即 **81.77%**；这是失败轮次的数据，不代表全量测试通过。证据为 `reports/junit-unit-full-with-coverage.xml`、`reports/coverage-unit-full.xml`、`reports/coverage-unit-full.json`。剩余失败：工具 29、存储 17、模型 5、CLI 4、配置 4、utils 4、SaaS 2。D 盘 Pytest 和 `TEMP/TMP` 临时目录已在轮次结束后删除，可用空间约 42.72 GB。

最终结果以 `docs/test-evidence.md` 为准：非 nightly 单元测试 10,678 通过、15 跳过、1 预期失败，整体行覆盖率 81.85%；验收测试 153 通过、9 个模块条件跳过，验收范围覆盖率 29.25%。之前的失败轮次保留为排障过程记录，不再代表当前状态。

## 2. Single/Multi 评测与三模式历史基线

### v2 重测（当前工作）

- [x] 设计 24 题分层题集：基础、关联、时间、复杂各 6 题。
- [x] 为每题配置稳定 `case_id`、能力标签和参考 SQL。
- [x] 在只读 `sample_data/mf-demo.duckdb` 上验证 24 条参考 SQL 均可执行。
- [x] 记录同模型配置、每格 3 次重复、随机顺序、超时隔离和结果集等价规则。
- [ ] 生成并冻结 24 题参考结果快照。
- [ ] 扩展比较脚本，支持自动结果等价、分层统计和重复稳定性。
- [ ] 验证请求取消或服务重启隔离流程。
- [ ] 冻结模型、提示词、配置和代码版本。
- [ ] 正式运行 24 题 × 2 模式（Single/Multi）× 3 次重复，共 144 次请求。
- [ ] 复核自动判分并生成新的公开证据。

设计文件：`docs/benchmark-v2-design.md`；题集：`benchmark/semantic_layer/testing_set_v2.csv`。当前尚未发送任何 v2 模型请求。

### v1 三模式历史结果（8 题）

> 历史记录：本轮在旧执行器仍支持 Legacy 时完成。原始 JSONL 与人工标签保留；当前 `reports/benchmark-summary.json` 已重算为仅含 Single/Multi，不能再用它复现下表的三模式汇总。

- [x] 每种运行模式执行 8 个已审阅问题，共发起 24 次真实 HTTP 请求。
- [x] 在 `sample_data/mf-demo.duckdb` 上直接执行参考 SQL。
- [x] 将原始响应保存到 `reports/benchmark-raw.jsonl`。
- [x] 将人工审阅的正确性标签保存到 `benchmark/semantic_layer/result_labels.json`。
- [x] 将计算后的汇总结果保存到 `reports/benchmark-summary.json`。
- [x] 统计正确率、完成率、中位延迟和 P95 延迟。
- [x] 保留失败和超时请求，不从统计中删除。
- [ ] 发布仓库内的评测证据文档，说明方法、精确结果、样本量、超时行为和限制。
- [ ] 在 README 中增加保守、可核验的评测表述。

当前人工审阅结果（每种模式 `n=8`）：

| 模式 | 正确结果 | 完成结果 | 中位延迟 | P95 延迟 |
| --- | ---: | ---: | ---: | ---: |
| Legacy | 5/8（62.5%） | 5/8（62.5%） | 12.891 秒 | 180 秒 |
| Single | 3/8（37.5%） | 5/8（62.5%） | 142.258 秒 | 180 秒 |
| Multi | 1/8（12.5%） | 6/8（75.0%） | 109.586 秒 | 180 秒 |

完成条件：公开文档必须使其他开发者在无法访问密钥和已忽略原始报告的情况下，仍能理解并复现本次评测。

## 3. 公开仓库、Git 与 CI

- [x] 恢复 Git 元数据并配置 `origin`。
- [x] 增加 `.gitattributes` 和公开仓库忽略规则。
- [x] 排除本地备份、个人笔记、测试临时目录、覆盖率文件和本地启动脚本。
- [x] 保留三个用于复现的样例数据库。
- [x] 增加 `.github/workflows/ci.yml`，执行锁定依赖安装、Ruff、验收测试、覆盖率统计和报告上传。
- [x] 增加可手动触发的真实评测工作流 `.github/workflows/benchmark.yml`。
- [x] 使 CI 检查范围内的 Ruff 检查通过。
- [x] 使 `git diff --check` 通过。
- [ ] 使用 YAML 解析器校验两份 GitHub Actions 工作流，并核对其中的命令与本地验证命令一致。
- [ ] 执行最终的锁定依赖检查和 Ruff 检查。
- [ ] 扫描已跟踪文件和计划公开文件中的凭据与本地绝对路径。
- [ ] 审核每个计划公开的文件，确认候选变更中不包含已忽略的本地文件。
- [ ] 使用可核验证据更新 README。
- [ ] 生成最终 Git 状态和候选文件报告。

完成条件：本地 CI 等效命令全部通过；公开证据完整；不包含凭据和个人文件；候选变更集合有明确记录。创建提交或推送仍需用户单独授权。

## 4. 表述边界

- 完整的非 nightly 单元测试成功结束前，不得写“全量测试通过”。
- 29.25% 必须写为“验收范围覆盖率”，不得写为仓库整体覆盖率；81.85% 是非 nightly 单元测试轮次的 `dataengineer` 覆盖率。
- 每次引用评测正确率或延迟时，都必须同时注明“每种模式 `n=8`”。
- 必须说明：HTTP 请求超时后，服务端任务仍继续执行；在服务重启前，它可能影响后续请求。
- GitHub Actions 尚未真实运行前，不得写“GitHub CI 已通过”；本地证据只能写“CI 配置已在本地验证”。
