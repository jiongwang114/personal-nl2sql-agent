param(
    [int]$FirstPort = 8512,
    [int]$SecondPort = 8513,
    [string]$Datasource = "benchmark_demo"
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$apiExe = Join-Path $projectRoot ".venv\Scripts\dataengineer.exe"

if (-not (Test-Path -LiteralPath $apiExe)) {
    throw "DataEngineer executable not found: $apiExe"
}
if ([string]::IsNullOrWhiteSpace($env:WLB_API_KEY)) {
    throw "WLB_API_KEY is empty. Set the first key before starting services."
}
if ([string]::IsNullOrWhiteSpace($env:WLB_API_KEY_2)) {
    throw "WLB_API_KEY_2 is empty. Fill the second key before starting services."
}
if ($FirstPort -eq $SecondPort) {
    throw "FirstPort and SecondPort must be different."
}

function Start-WlbService([string]$Key, [int]$Port, [string]$Label) {
    $pidFile = Join-Path $projectRoot "reports\wlb-$Label.pid"
    $psi = [System.Diagnostics.ProcessStartInfo]::new()
    $psi.FileName = $apiExe
    $psi.WorkingDirectory = $projectRoot
    $psi.Arguments = "--web --datasource $Datasource --host 127.0.0.1 --port $Port"
    $psi.UseShellExecute = $false
    $psi.Environment["WLB_API_KEY"] = $Key
    $process = [System.Diagnostics.Process]::new()
    $process.StartInfo = $psi
    [void]$process.Start()
    Set-Content -LiteralPath $pidFile -Value $process.Id -Encoding ascii
    Write-Output "$Label started: PID=$($process.Id) PORT=$Port"
}

New-Item -ItemType Directory -Force (Join-Path $projectRoot "reports") | Out-Null
Start-WlbService $env:WLB_API_KEY $FirstPort "key1"
Start-WlbService $env:WLB_API_KEY_2 $SecondPort "key2"
