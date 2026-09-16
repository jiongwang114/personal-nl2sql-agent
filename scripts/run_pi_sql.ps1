param(
    [ValidateSet("single", "multi")]
    [string]$Mode = "multi",
    [string]$Model = "",
    [string]$Prompt = ""
)

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Pi = Join-Path $ProjectRoot ".pi\node_modules\.bin\pi.cmd"

if (-not (Test-Path -LiteralPath $Pi)) {
    throw "Pi is not installed. Run npm install --ignore-scripts in $ProjectRoot\.pi"
}

$Tools = if ($Mode -eq "single") {
    "search_table,list_tables,describe_table,get_table_ddl,search_metrics,search_reference_sql,validate_sql,execute_readonly_sql"
} else {
    "sql_subagent,validate_sql,execute_readonly_sql"
}

$Arguments = @("--approve", "--tools", $Tools)
if ($Model) { $Arguments += @("--model", $Model) }
if ($Prompt) { $Arguments += @($Prompt) }

& $Pi @Arguments
