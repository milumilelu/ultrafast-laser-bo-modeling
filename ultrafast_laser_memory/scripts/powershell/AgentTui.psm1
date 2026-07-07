$script:RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")

$script:Providers = @{
    "1" = @{ Id = "openai"; Name = "OpenAI"; Env = "OPENAI_API_KEY"; Base = "https://api.openai.com/v1"; Models = @("gpt-4.1", "gpt-4.1-mini", "gpt-4o", "gpt-4o-mini") }
    "2" = @{ Id = "deepseek"; Name = "DeepSeek"; Env = "DEEPSEEK_API_KEY"; Base = "https://api.deepseek.com"; Models = @("deepseek-chat", "deepseek-reasoner") }
    "3" = @{ Id = "anthropic"; Name = "Anthropic"; Env = "ANTHROPIC_API_KEY"; Base = "https://api.anthropic.com"; Models = @("claude-3-5-sonnet-latest", "claude-3-5-haiku-latest") }
    "4" = @{ Id = "moonshot"; Name = "Moonshot / Kimi"; Env = "MOONSHOT_API_KEY"; Base = "https://api.moonshot.cn/v1"; Models = @("moonshot-v1-8k", "moonshot-v1-32k", "moonshot-v1-128k") }
    "5" = @{ Id = "qwen"; Name = "通义千问 Qwen"; Env = "DASHSCOPE_API_KEY"; Base = "https://dashscope.aliyuncs.com/compatible-mode/v1"; Models = @("qwen-plus", "qwen-max", "qwen-turbo") }
    "6" = @{ Id = "glm"; Name = "智谱 GLM"; Env = "ZHIPUAI_API_KEY"; Base = "https://open.bigmodel.cn/api/paas/v4"; Models = @("glm-4", "glm-4-air", "glm-4-flash") }
    "7" = @{ Id = "local"; Name = "本地 OpenAI-Compatible 服务"; Env = "OPENAI_API_KEY"; Base = ""; Models = @("__custom__") }
}

function Show-AgentBanner {
    try {
        Clear-Host
    } catch {
        Write-Host ""
    }
    Write-Host "超快激光智能体启动器"
    Write-Host "Ultrafast Laser Agent Launcher"
    Write-Host ""
}

function Show-ProviderMenu {
    while ($true) {
        Write-Host "[1] OpenAI"
        Write-Host "[2] DeepSeek"
        Write-Host "[3] Anthropic"
        Write-Host "[4] Moonshot / Kimi"
        Write-Host "[5] 通义千问 Qwen"
        Write-Host "[6] 智谱 GLM"
        Write-Host "[7] 本地 OpenAI-Compatible 服务"
        Write-Host "[8] 跳过 LLM 配置，仅启动数据闭环服务"
        $choice = Read-Host "请选择服务商"
        if ($choice -eq "8") { return "skip" }
        if ($script:Providers.ContainsKey($choice)) { return $script:Providers[$choice].Id }
        Write-Host "无效选择，请重新输入。"
    }
}

function Get-AgentProviderInfo {
    param([string]$Provider)
    foreach ($item in $script:Providers.Values) {
        if ($item.Id -eq $Provider) { return $item }
    }
    throw "Unknown provider: $Provider"
}

function Show-ModelMenu {
    param([string]$Provider)
    $info = Get-AgentProviderInfo -Provider $Provider
    if ($Provider -eq "local") {
        $model = Read-Host "请输入自定义 model name"
        if ([string]::IsNullOrWhiteSpace($model)) { return "local-model" }
        return $model
    }
    for ($i = 0; $i -lt $info.Models.Count; $i++) {
        Write-Host ("[{0}] {1}" -f ($i + 1), $info.Models[$i])
    }
    while ($true) {
        $choice = Read-Host "请选择模型"
        $index = 0
        $parsed = [int]::TryParse($choice, [ref]$index)
        if ($parsed -and $index -ge 1 -and $index -le $info.Models.Count) {
            return $info.Models[$index - 1]
        }
        Write-Host "无效选择，请重新输入。"
    }
}

function ConvertFrom-AgentSecureString {
    param([securestring]$SecureString)
    if ($null -eq $SecureString -or $SecureString.Length -eq 0) { return "" }
    $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($SecureString)
    try {
        return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
    } finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
    }
}

function Read-AgentApiKey {
    param([string]$Provider)
    $info = Get-AgentProviderInfo -Provider $Provider
    $existing = [Environment]::GetEnvironmentVariable($info.Env, "Process")
    if ($existing) {
        $useExisting = Read-Host ("检测到环境变量 {0}，直接使用？(Y/n)" -f $info.Env)
        if ($useExisting -ne "n") {
            return @{ EnvName = $info.Env; Source = "env"; HasKey = $true; Key = "" }
        }
    }
    $secure = Read-Host ("请输入 API Key，留空则跳过 ({0})" -f $info.Env) -AsSecureString
    $plain = ConvertFrom-AgentSecureString -SecureString $secure
    return @{ EnvName = $info.Env; Source = "session"; HasKey = -not [string]::IsNullOrWhiteSpace($plain); Key = $plain }
}

function Set-AgentEnvironment {
    param([string]$Provider, [string]$Model, [hashtable]$ApiKeyInfo)
    $info = Get-AgentProviderInfo -Provider $Provider
    $apiBase = $info.Base
    if ($Provider -eq "local") {
        $customBase = Read-Host "请输入 API Base URL"
        if (-not [string]::IsNullOrWhiteSpace($customBase)) { $apiBase = $customBase }
    } else {
        $customBase = Read-Host ("API Base URL [{0}]" -f $apiBase)
        if (-not [string]::IsNullOrWhiteSpace($customBase)) { $apiBase = $customBase }
    }
    $env:ULTRAFAST_LLM_PROVIDER = $Provider
    $env:ULTRAFAST_LLM_MODEL = $Model
    $env:ULTRAFAST_LLM_API_BASE = $apiBase
    $env:ULTRAFAST_LLM_API_KEY_ENV = $ApiKeyInfo.EnvName
    if ($ApiKeyInfo.HasKey -and $ApiKeyInfo.Key) {
        Set-Item -Path ("Env:{0}" -f $ApiKeyInfo.EnvName) -Value $ApiKeyInfo.Key
    }
}

function Save-AgentSecret {
    param([string]$Name, [securestring]$Secret)
    throw "Windows Credential Manager persistence is reserved for a later version."
}

function Get-AgentSecret {
    param([string]$Name)
    return $null
}

function Remove-AgentSecret {
    param([string]$Name)
    return $null
}

function Save-AgentLlmConfig {
    param([string]$Provider, [string]$Model, [hashtable]$ApiKeyInfo)
    $info = Get-AgentProviderInfo -Provider $Provider
    $configDir = Join-Path $script:RepoRoot "configs"
    New-Item -ItemType Directory -Force -Path $configDir | Out-Null
    $path = Join-Path $configDir "llm.local.json"
    $now = (Get-Date).ToUniversalTime().ToString("s")
    $data = [ordered]@{
        provider = $Provider
        model = $Model
        api_base = $env:ULTRAFAST_LLM_API_BASE
        api_key_source = "env"
        api_key_env = $ApiKeyInfo.EnvName
        created_at = $now
        updated_at = $now
    }
    $data | ConvertTo-Json | Set-Content -Path $path -Encoding UTF8
    Write-Host "已保存 LLM 配置；API Key 未写入配置文件。"
}

function Load-AgentLlmConfig {
    $path = Join-Path $script:RepoRoot "configs\llm.local.json"
    if (-not (Test-Path $path)) { return $null }
    return Get-Content -Path $path -Raw | ConvertFrom-Json
}

function Clear-AgentLlmConfig {
    $path = Join-Path $script:RepoRoot "configs\llm.local.json"
    if (Test-Path $path) { Remove-Item -Path $path -Force }
    Write-Host "本地 LLM 配置已清除。"
}

function Test-AgentPythonEnvironment {
    $python = Get-Command python -ErrorAction SilentlyContinue
    if (-not $python) {
        Write-Host "未找到 Python。请先安装 Python >= 3.10。"
        return $false
    }
    Push-Location $script:RepoRoot
    try {
        python -c "import ultrafast_memory, fastapi, typer, sqlalchemy" 2>$null
        if ($LASTEXITCODE -ne 0) {
            Write-Host "依赖未安装。请执行：pip install -e ."
            return $false
        }
        return $true
    } finally {
        Pop-Location
    }
}

function Initialize-AgentDatabase {
    if (-not (Test-AgentPythonEnvironment)) { return }
    Push-Location $script:RepoRoot
    try { python -m ultrafast_memory.app.cli init-db } finally { Pop-Location }
}

function Invoke-AgentScan {
    if (-not (Test-AgentPythonEnvironment)) { return }
    Push-Location $script:RepoRoot
    try { python -m ultrafast_memory.app.cli scan examples } finally { Pop-Location }
}

function Start-AgentApiServer {
    if (-not (Test-AgentPythonEnvironment)) { return }
    Push-Location $script:RepoRoot
    try { python -m uvicorn ultrafast_memory.app.api:app --reload --host 127.0.0.1 --port 8000 } finally { Pop-Location }
}

function Export-AgentBoDataset {
    if (-not (Test-AgentPythonEnvironment)) { return }
    Push-Location $script:RepoRoot
    try { python -m ultrafast_memory.app.cli export-bo } finally { Pop-Location }
}

function Show-AgentConfig {
    Write-Host ("Provider: {0}" -f $env:ULTRAFAST_LLM_PROVIDER)
    Write-Host ("Model: {0}" -f $env:ULTRAFAST_LLM_MODEL)
    Write-Host ("API Base: {0}" -f $env:ULTRAFAST_LLM_API_BASE)
    Write-Host ("API Key Env: {0}" -f $env:ULTRAFAST_LLM_API_KEY_ENV)
    $local = Load-AgentLlmConfig
    if ($local) { Write-Host "Local config: configs/llm.local.json" } else { Write-Host "Local config: none" }
}

function Show-AgentMainMenu {
    while ($true) {
        Write-Host ""
        Write-Host "[1] 初始化数据库"
        Write-Host "[2] 扫描示例数据"
        Write-Host "[3] 启动 FastAPI 服务"
        Write-Host "[4] 导出 BO 数据集"
        Write-Host "[5] 查看配置"
        Write-Host "[6] 清除本地 LLM 配置"
        Write-Host "[7] 退出"
        $choice = Read-Host "请选择操作"
        if ($choice -eq "1") {
            Initialize-AgentDatabase
        } elseif ($choice -eq "2") {
            Invoke-AgentScan
        } elseif ($choice -eq "3") {
            Start-AgentApiServer
        } elseif ($choice -eq "4") {
            Export-AgentBoDataset
        } elseif ($choice -eq "5") {
            Show-AgentConfig
        } elseif ($choice -eq "6") {
            Clear-AgentLlmConfig
        } elseif ($choice -eq "7") {
            return
        } else {
            Write-Host "无效选择，请重新输入。"
        }
    }
}

Export-ModuleMember -Function Show-AgentBanner, Show-ProviderMenu, Show-ModelMenu, Read-AgentApiKey, Set-AgentEnvironment, Save-AgentLlmConfig, Load-AgentLlmConfig, Clear-AgentLlmConfig, Show-AgentMainMenu, Initialize-AgentDatabase, Invoke-AgentScan, Start-AgentApiServer, Export-AgentBoDataset, Test-AgentPythonEnvironment, Save-AgentSecret, Get-AgentSecret, Remove-AgentSecret
