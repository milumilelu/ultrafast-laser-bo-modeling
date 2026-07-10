param(
    [string]$OutputPath = ""
)

$ErrorActionPreference = "Stop"
$RepositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$ProjectRoot = (Resolve-Path (Join-Path $RepositoryRoot "ultrafast_laser_memory")).Path
$env:PYTHONPATH = (Join-Path $ProjectRoot "src")
$Arguments = @((Join-Path $PSScriptRoot "backup_repository_state.py"))
if (-not [string]::IsNullOrWhiteSpace($OutputPath)) {
    $Arguments += @("--output", $OutputPath)
}
& python @Arguments
if ($LASTEXITCODE -ne 0) {
    throw "Baseline backup failed with exit code $LASTEXITCODE"
}
