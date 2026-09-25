param(
    [string]$BaseUrl = "http://127.0.0.1:8512",
    [int]$TimeoutSeconds = 300
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot

uv run python scripts/run_pi_benchmark.py `
    --cases benchmark/semantic_layer/testing_set_v2.csv `
    --output reports/benchmark-deepseek-multi-raw.jsonl `
    --base-url $BaseUrl `
    --variants multi `
    --datasource benchmark_demo `
    --repeats 3 `
    --timeout $TimeoutSeconds `
    --resume

uv run python scripts/run_pi_benchmark.py `
    --cases benchmark/semantic_layer/testing_set_v2.csv `
    --output reports/benchmark-deepseek-single-raw.jsonl `
    --base-url $BaseUrl `
    --variants single `
    --datasource benchmark_demo `
    --repeats 1 `
    --timeout $TimeoutSeconds `
    --resume
