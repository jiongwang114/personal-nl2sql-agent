$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$rows = Import-Csv benchmark/semantic_layer/testing_set_v2.csv
for ($i=0; $i -lt 2; $i++) {
  $shard = $rows | Where-Object { ([array]::IndexOf($rows, $_) % 2) -eq $i }
  $shard | Export-Csv "reports/wlb-shard-$i.csv" -NoTypeInformation -Encoding UTF8
}
foreach ($spec in @(@{i=0;port=8512}, @{i=1;port=8513})) {
  $script = "Set-Location '$root'; uv run python scripts/run_pi_benchmark.py --cases 'reports/wlb-shard-$($spec.i).csv' --output 'reports/wlb-key$($spec.i+1)-multi.jsonl' --base-url 'http://127.0.0.1:$($spec.port)' --variants multi --datasource benchmark_demo --repeats 3 --concurrency 2 --timeout 300; uv run python scripts/run_pi_benchmark.py --cases 'reports/wlb-shard-$($spec.i).csv' --output 'reports/wlb-key$($spec.i+1)-single.jsonl' --base-url 'http://127.0.0.1:$($spec.port)' --variants single --datasource benchmark_demo --repeats 1 --concurrency 2 --timeout 300"
  Start-Process powershell.exe -ArgumentList '-NoProfile','-Command',$script -WorkingDirectory $root -RedirectStandardOutput (Join-Path $root "reports/wlb-key$($spec.i+1).out.log") -RedirectStandardError (Join-Path $root "reports/wlb-key$($spec.i+1).err.log") -WindowStyle Hidden | Out-Null
}
