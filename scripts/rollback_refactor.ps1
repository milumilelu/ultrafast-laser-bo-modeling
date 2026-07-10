param(
    [Parameter(Mandatory = $true)]
    [string]$BackupRoot,
    [switch]$ConfirmRollback,
    [switch]$RestoreDatabase,
    [switch]$RestoreConfig,
    [switch]$RestoreCode
)

$ErrorActionPreference = "Stop"
if (-not $ConfirmRollback) {
    throw "Rollback requires -ConfirmRollback. No state was changed."
}

$RepositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$ProjectRoot = (Resolve-Path (Join-Path $RepositoryRoot "ultrafast_laser_memory")).Path
$AllowedBackupRoot = [System.IO.Path]::GetFullPath((Join-Path $ProjectRoot "data\backups"))
$ResolvedBackup = [System.IO.Path]::GetFullPath((Resolve-Path -LiteralPath $BackupRoot).Path)
if (-not $ResolvedBackup.StartsWith($AllowedBackupRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "BackupRoot must remain under $AllowedBackupRoot"
}

$ManifestPath = Join-Path $ResolvedBackup "manifest.json"
if (-not (Test-Path -LiteralPath $ManifestPath)) {
    throw "Backup manifest not found: $ManifestPath"
}
$Manifest = Get-Content -LiteralPath $ManifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
if (-not $Manifest.database.logical_snapshot_matches) {
    throw "Backup manifest does not prove a valid logical database snapshot."
}

if ($RestoreDatabase) {
    $SourceDatabase = [System.IO.Path]::GetFullPath((Join-Path $ResolvedBackup "database\ultrafast_memory.db"))
    $TargetDatabase = [System.IO.Path]::GetFullPath((Join-Path $ProjectRoot "data\ultrafast_memory.db"))
    if (-not $TargetDatabase.StartsWith($ProjectRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Resolved database target escaped the project root."
    }
    Copy-Item -LiteralPath $SourceDatabase -Destination $TargetDatabase -Force
}

if ($RestoreConfig) {
    $ConfigBackup = Join-Path $ResolvedBackup "configs"
    $ConfigTarget = [System.IO.Path]::GetFullPath((Join-Path $ProjectRoot "configs"))
    if (-not $ConfigTarget.StartsWith($ProjectRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Resolved config target escaped the project root."
    }
    foreach ($Name in @("default.yaml", "local.yaml", "llm.local.json")) {
        $Source = Join-Path $ConfigBackup $Name
        if (Test-Path -LiteralPath $Source) {
            Copy-Item -LiteralPath $Source -Destination (Join-Path $ConfigTarget $Name) -Force
        }
    }
}

if ($RestoreCode) {
    $Dirty = git -C $RepositoryRoot status --porcelain=v1
    if ($Dirty) {
        throw "Refusing code rollback while the Git worktree is dirty. Commit or stash changes first."
    }
    git -C $RepositoryRoot switch --detach pre-agent-refactor
    if ($LASTEXITCODE -ne 0) {
        throw "Git rollback failed."
    }
}

Write-Host "Rollback completed for the explicitly selected scopes." -ForegroundColor Green
