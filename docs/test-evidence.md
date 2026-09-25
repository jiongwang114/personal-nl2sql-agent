# 测试与覆盖率证据

更新时间：2026-09-19。执行环境为 Windows、Python 3.12.14、Pytest 8.0.2；使用锁定依赖的 `uv` 环境。以下是两个不同测试范围的结果，覆盖率不能混用。

## 非 nightly 单元测试

运行前将 `DATAENGINEER_TEST_ROOT=R:\` 指向 D 盘仓库的 ASCII 路径映射，并将 `TEMP`、`TMP` 指向 D 盘临时目录。`R:` 映射到 `D:\完整data-engineer`；`--basetemp` 同样位于 D 盘。运行命令：

```powershell
uv run pytest tests/unit_tests -m 'not nightly' -q -o addopts='' -o log_cli=false --timeout=120 --basetemp=R:\.pytest-tmp-unit-controlled --junitxml=reports/junit-unit-final.xml --cov=dataengineer --cov-report=xml:reports/coverage-unit-final.xml --cov-report=json:reports/coverage-unit-final.json --cov-report=term
```

结果：10,694 项（10,678 通过、15 跳过、1 预期失败），0 失败、0 错误；耗时 545.68 秒。JUnit 把预期失败也计入 `skipped=16`。`dataengineer` 行覆盖率为 **81.85%**（45,213/55,239 行），按 `pyproject.toml` 的覆盖率排除规则计算。运行期间 D 盘最低观察余量约 29.6 GB；本轮 Pytest 和 `TEMP/TMP` 临时目录已删除，恢复到约 42.7 GB 可用。

15 条普通跳过分别是：6 条因未安装可选 `datus-scheduler-airflow`、7 条因 Windows 没有 `pty`、1 条因当前 Windows 账户无创建符号链接权限、1 条因 `SemanticModelStorage.batch_store` 缺失。另外 1 条 `ReasoningInput` 不接受 `sql_query` 标记为预期失败。后两者对应尚未解决的产品/API 问题，不能计作功能通过。

原始本地证据：`reports/junit-unit-final.xml`、`reports/coverage-unit-final.xml`、`reports/coverage-unit-final.json`。`reports/` 已被 Git 忽略，公开仓库只保留本页命令和汇总数字；复现时需要自行生成报告。

## 验收测试

同样设置 `DATAENGINEER_TEST_ROOT`、`TEMP` 和 `TMP`，执行：

```powershell
uv run pytest -m acceptance -q -o addopts='' -o log_cli=false --timeout=120 --basetemp=R:\.pytest-tmp-acceptance-final --junitxml=reports/junit-acceptance-final.xml --cov=dataengineer --cov-report=xml:reports/coverage-acceptance-final.xml --cov-report=json:reports/coverage-acceptance-final.json --cov-report=term
```

结果：162 项（153 通过、9 个模块在收集时按声明条件跳过），0 失败、0 错误；JUnit 耗时 220.959 秒。`dataengineer` 在**验收范围内**的行覆盖率为 **29.25%**（16,155/55,239 行），不是整个仓库的最终覆盖率。跳过的模块为 ClickHouse、Greenplum、Hive、MySQL、PostgreSQL、Spark、StarRocks、Trino 适配器集成测试及 Web E2E 回归测试；它们需要当前本地验收环境没有提供的服务或条件。

原始本地证据：`reports/junit-acceptance-final.xml`、`reports/coverage-acceptance-final.xml`、`reports/coverage-acceptance-final.json`。本轮临时目录也已删除。GitHub Actions 尚未实际运行，不能据此声称云端 CI 通过。

## 范围边界

单元测试命令只运行 `tests/unit_tests` 中非 `nightly` 项；验收命令运行被显式标记为 `acceptance` 的项。真实 LLM、外部数据库与 nightly 集成能力不在这两次通过结果内。两轮测试都报告了 3 条运行时警告，需与失败、跳过分开看待。
