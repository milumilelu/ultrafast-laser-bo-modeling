param(
    [switch]$NoSave,
    [switch]$SkipLlmConfig,
    [switch]$NoExampleData,
    [switch]$NoBoExport,
    [switch]$Reconfigure,
    [switch]$ForceInitialize
)

$ErrorActionPreference = "Stop"

if (-not (Get-Command pwsh -ErrorAction SilentlyContinue)) {
    throw "PowerShell 7 (pwsh) is required for this launcher."
}

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Push-Location $RepoRoot
try {
    $python = Get-Command python -ErrorAction SilentlyContinue
    if (-not $python) {
        throw "未找到 Python。请先安装 Python >= 3.10。"
    }

    Write-Host "[1/5] 安装 Python 包"
    python -m pip install -e .

    Write-Host "[2/5] 初始化数据库"
    python -m ultrafast_memory.app.cli init-db

    if (-not $NoExampleData) {
        Write-Host "[3/5] 扫描示例数据"
        python -m ultrafast_memory.app.cli scan examples
    } else {
        Write-Host "[3/5] 跳过示例数据扫描"
    }

    if (-not $NoBoExport) {
        Write-Host "[4/5] 导出 BO 数据集"
        python -m ultrafast_memory.app.cli export-bo
    } else {
        Write-Host "[4/5] 跳过 BO 导出"
    }

    Write-Host "[5/5] 启动 DeepSeek 聊天 TUI"
    $tuiScript = Join-Path $PSScriptRoot "start_agent_tui.ps1"
    $args = @()
    if ($NoSave) { $args += "-NoSave" }
    if ($SkipLlmConfig) { $args += "-SkipLlmConfig" }
    if ($Reconfigure) { $args += "-Reconfigure" }
    if ($ForceInitialize) { $args += "-ForceInitialize" }
    & $tuiScript @args
} finally {
    Pop-Location
}
