# Pi SQL Runtime

## Install

```powershell
Set-Location F:\data_engineer\dataengineer-agent-personal\.pi
npm install --ignore-scripts
```

Python 环境必须已经安装项目依赖，并能运行 `dataengineer.mcp_server`。

## Run Single-Agent Baseline

```powershell
.\scripts\run_pi_sql.ps1 -Mode single -Model "provider/model"
```

## Run Multi-Agent Runtime

```powershell
.\scripts\run_pi_sql.ps1 -Mode multi -Model "provider/model"
```

## Non-interactive Prompt

```powershell
.\scripts\run_pi_sql.ps1 -Mode multi -Model "provider/model" -Prompt "查询加州学校的平均数学成绩"
```

## Verify

```powershell
Set-Location .pi
npm run check

Set-Location ..
.\.venv\Scripts\python.exe -m pytest `
  tests/unit_tests/tools/test_sql_guard.py `
  tests/unit_tests/scripts/test_compare_pi_variants.py `
  -q --basetemp .pytest-tmp-pi-runtime
```

## Compare Evaluation Records

```powershell
.\.venv\Scripts\python.exe scripts\compare_pi_variants.py `
  reports\single.jsonl reports\multi.jsonl `
  --output reports\pi-runtime-comparison.json
```

## Security

- Do not expose `read_query` directly to the Orchestrator.
- Use `execute_readonly_sql`; it invokes `validate_sql` first.
- Use read-only database credentials.
- Rotate any credential previously committed to configuration files.
- Runtime traces omit tool arguments and result rows.
