$projectRoot = Split-Path -Parent $PSScriptRoot
foreach ($label in @("key1", "key2")) {
    $pidFile = Join-Path $projectRoot "reports\wlb-$label.pid"
    if (Test-Path -LiteralPath $pidFile) {
        $servicePid = [int](Get-Content -LiteralPath $pidFile -Raw)
        Stop-Process -Id $servicePid -Force -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
        Write-Output "$label stopped: PID=$servicePid"
    }
}
