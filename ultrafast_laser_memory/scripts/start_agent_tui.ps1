param(
    [switch]$NoSave,
    [switch]$SkipLlmConfig,
    [switch]$ShowMenu,
    [switch]$Reconfigure,
    [switch]$ForceInitialize
)

$ErrorActionPreference = "Stop"

$ModulePath = Join-Path $PSScriptRoot "powershell/AgentTui.psm1"
Import-Module $ModulePath -Force -DisableNameChecking

Show-AgentBanner

if ($ShowMenu) {
    Show-AgentMainMenu
    return
}

Start-AgentDeepSeekAutoLaunch -NoSave:$NoSave -SkipLlmConfig:$SkipLlmConfig -Reconfigure:$Reconfigure -ForceInitialize:$ForceInitialize
