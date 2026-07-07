param(
    [switch]$NoSave,
    [switch]$SkipLlmConfig
)

$ErrorActionPreference = "Stop"

$ModulePath = Join-Path $PSScriptRoot "powershell/AgentTui.psm1"
Import-Module $ModulePath -Force -DisableNameChecking

Show-AgentBanner

if (-not $SkipLlmConfig) {
    $provider = Show-ProviderMenu
    if ($provider -ne "skip") {
        $model = Show-ModelMenu -Provider $provider
        $apiKeyInfo = Read-AgentApiKey -Provider $provider
        Set-AgentEnvironment -Provider $provider -Model $model -ApiKeyInfo $apiKeyInfo

        if (-not $NoSave) {
            Save-AgentLlmConfig -Provider $provider -Model $model -ApiKeyInfo $apiKeyInfo
        }
    }
}

Show-AgentMainMenu
