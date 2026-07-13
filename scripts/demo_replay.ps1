param(
    [bool]$ApproveReview = $true
)

$ErrorActionPreference = "Stop"
$RepositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$ProjectRoot = (Resolve-Path (Join-Path $RepositoryRoot "ultrafast_laser_memory")).Path
$env:PYTHONPATH = (Join-Path $ProjectRoot "src")
$env:ULTRAFAST_MEMORY_ROOT = $ProjectRoot
$env:ULTRAFAST_LLM_PROVIDER = "mock"
$env:ULTRAFAST_LLM_MODEL = "deterministic-demo"

Push-Location $ProjectRoot
try {
    & python -m ultrafast_memory.app.main doctor
    if ($LASTEXITCODE -ne 0) { throw "Doctor failed." }
    $Arguments = @("-m", "ultrafast_memory.app.main", "demo", "tgv", "--trial-mode", "simple_trial_cut")
    if ($ApproveReview) { $Arguments += "--approve-review" }
    & python @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Demo replay failed." }
} finally {
    Pop-Location
}
