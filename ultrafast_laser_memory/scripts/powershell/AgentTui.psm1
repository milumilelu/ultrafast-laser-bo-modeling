$script:RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")

$script:Providers = @{
    "1" = @{ Id = "openai"; Name = "OpenAI"; Env = "OPENAI_API_KEY"; Base = "https://api.openai.com/v1"; Models = @("gpt-5.5", "gpt-5.4", "gpt-5.4-mini", "gpt-5.4-nano") }
    "2" = @{ Id = "deepseek"; Name = "DeepSeek"; Env = "DEEPSEEK_API_KEY"; Base = "https://api.deepseek.com"; Models = @("deepseek-v4-pro", "deepseek-v4-flash") }
    "3" = @{ Id = "anthropic"; Name = "Anthropic"; Env = "ANTHROPIC_API_KEY"; Base = "https://api.anthropic.com"; Models = @("claude-fable-5", "claude-opus-4-8", "claude-sonnet-5", "claude-haiku-4-5") }
    "4" = @{ Id = "moonshot"; Name = "Moonshot / Kimi"; Env = "MOONSHOT_API_KEY"; Base = "https://api.moonshot.ai/v1"; Models = @("kimi-k2.7-code", "kimi-k2.7-code-highspeed", "kimi-k2.6", "moonshot-v1-128k") }
    "5" = @{ Id = "qwen"; Name = "通义千问 Qwen"; Env = "DASHSCOPE_API_KEY"; Base = "https://dashscope.aliyuncs.com/compatible-mode/v1"; Models = @("qwen3.7-max", "qwen3.7-plus", "qwen3.6-flash") }
    "6" = @{ Id = "glm"; Name = "智谱 GLM / Z.ai"; Env = "ZHIPUAI_API_KEY"; Base = "https://api.z.ai/api/paas/v4"; Models = @("glm-5.2", "glm-5.1", "glm-5", "glm-5-turbo") }
    "7" = @{ Id = "local"; Name = "本地 OpenAI-Compatible 服务"; Env = "OPENAI_API_KEY"; Base = ""; Models = @("__custom__") }
}

$script:DeepSeekProvider = "deepseek"
$script:DeepSeekModels = @(
    @{ Label = "Flash"; Model = "deepseek-v4-flash" },
    @{ Label = "Pro"; Model = "deepseek-v4-pro" }
)
$script:AgentStreamMode = $false
$script:AgentDisplayMode = "debug"

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
        Write-Host "[6] 智谱 GLM / Z.ai"
        Write-Host "[7] 本地 OpenAI-Compatible 服务"
        Write-Host "[8] 跳过 LLM 配置，仅启动数据闭环服务"
        $choice = Read-Host "请选择服务商"
        if ([string]::IsNullOrWhiteSpace($choice) -and [Console]::IsInputRedirected) { return "skip" }
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
        if ([string]::IsNullOrWhiteSpace($choice) -and [Console]::IsInputRedirected) { return $info.Models[0] }
        $index = 0
        $parsed = [int]::TryParse($choice, [ref]$index)
        if ($parsed -and $index -ge 1 -and $index -le $info.Models.Count) {
            return $info.Models[$index - 1]
        }
        Write-Host "无效选择，请重新输入。"
    }
}

function Show-DeepSeekModelMenu {
    Write-Host "DeepSeek 模型选择"
    for ($i = 0; $i -lt $script:DeepSeekModels.Count; $i++) {
        $item = $script:DeepSeekModels[$i]
        Write-Host ("[{0}] {1} ({2})" -f ($i + 1), $item.Label, $item.Model)
    }
    while ($true) {
        $choice = Read-Host "请选择模型"
        if ([string]::IsNullOrWhiteSpace($choice) -and [Console]::IsInputRedirected) {
            return $script:DeepSeekModels[0].Model
        }
        $index = 0
        $parsed = [int]::TryParse($choice, [ref]$index)
        if ($parsed -and $index -ge 1 -and $index -le $script:DeepSeekModels.Count) {
            return $script:DeepSeekModels[$index - 1].Model
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
    param(
        [string]$Provider,
        [switch]$ForcePrompt
    )
    $info = Get-AgentProviderInfo -Provider $Provider
    $savedSecret = Get-AgentSecret -Name $info.Env
    $existing = [Environment]::GetEnvironmentVariable($info.Env, "Process")

    if (-not $ForcePrompt -and $savedSecret) {
        $plainSaved = ConvertFrom-AgentSecureString -SecureString $savedSecret
        return @{ EnvName = $info.Env; Source = "secret"; HasKey = $true; Key = $plainSaved }
    }
    if (-not $ForcePrompt -and $existing) {
        return @{ EnvName = $info.Env; Source = "env"; HasKey = $true; Key = $existing }
    }

    $secure = Read-Host ("请输入 API Key，留空则跳过 ({0})" -f $info.Env) -AsSecureString
    $plain = ConvertFrom-AgentSecureString -SecureString $secure
    if ([string]::IsNullOrWhiteSpace($plain) -and $savedSecret) {
        $plainSaved = ConvertFrom-AgentSecureString -SecureString $savedSecret
        return @{ EnvName = $info.Env; Source = "secret"; HasKey = $true; Key = $plainSaved }
    }
    if ([string]::IsNullOrWhiteSpace($plain) -and $existing) {
        return @{ EnvName = $info.Env; Source = "env"; HasKey = $true; Key = $existing }
    }
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

function Set-AgentDeepSeekEnvironment {
    param([string]$Model, [hashtable]$ApiKeyInfo)
    $env:ULTRAFAST_LLM_PROVIDER = "deepseek"
    $env:ULTRAFAST_LLM_MODEL = $Model
    $env:ULTRAFAST_LLM_API_BASE = "https://api.deepseek.com"
    $env:ULTRAFAST_LLM_API_KEY_ENV = "DEEPSEEK_API_KEY"
    if ($ApiKeyInfo.HasKey -and $ApiKeyInfo.Key) {
        $env:DEEPSEEK_API_KEY = $ApiKeyInfo.Key
    }
}

function Use-AgentSavedDeepSeekConfig {
    $local = Load-AgentLlmConfig
    if (-not $local) { return $false }
    if ($local.provider -ne $script:DeepSeekProvider) { return $false }
    if ([string]::IsNullOrWhiteSpace($local.model)) { return $false }

    $env:ULTRAFAST_LLM_PROVIDER = "deepseek"
    $env:ULTRAFAST_LLM_MODEL = $local.model
    $env:ULTRAFAST_LLM_API_BASE = $(if ($local.api_base) { $local.api_base } else { "https://api.deepseek.com" })
    $env:ULTRAFAST_LLM_API_KEY_ENV = $(if ($local.api_key_env) { $local.api_key_env } else { "DEEPSEEK_API_KEY" })

    $secret = Get-AgentSecret -Name $env:ULTRAFAST_LLM_API_KEY_ENV
    if ($secret) {
        $env:DEEPSEEK_API_KEY = ConvertFrom-AgentSecureString -SecureString $secret
        Write-Host ("已加载已有 DeepSeek 配置：{0}" -f $env:ULTRAFAST_LLM_MODEL)
        return $true
    }
    if ([Environment]::GetEnvironmentVariable($env:ULTRAFAST_LLM_API_KEY_ENV, "Process")) {
        Write-Host ("已加载已有 DeepSeek 配置：{0}" -f $env:ULTRAFAST_LLM_MODEL)
        return $true
    }
    Write-Host ("已加载已有 DeepSeek 模型配置：{0}；未找到已保存 API Key。" -f $env:ULTRAFAST_LLM_MODEL)
    return $false
}

function Initialize-AgentDeepSeekConfig {
    param(
        [switch]$NoSave,
        [switch]$Reconfigure
    )
    if (-not $Reconfigure) {
        if (Use-AgentSavedDeepSeekConfig) { return }
        $local = Load-AgentLlmConfig
        if ($local -and $local.provider -eq $script:DeepSeekProvider -and $local.model) {
            Write-Host "只需补充 DeepSeek API Key；模型配置将复用已有设置。"
            $apiKeyInfo = Read-AgentApiKey -Provider $script:DeepSeekProvider
            Set-AgentDeepSeekEnvironment -Model $local.model -ApiKeyInfo $apiKeyInfo
            if (-not $NoSave) {
                Save-AgentLlmConfig -Provider $script:DeepSeekProvider -Model $local.model -ApiKeyInfo $apiKeyInfo
            }
            return
        }
    }

    Write-Host "供应商：DeepSeek"
    $model = Show-DeepSeekModelMenu
    $apiKeyInfo = Read-AgentApiKey -Provider $script:DeepSeekProvider -ForcePrompt:$Reconfigure
    Set-AgentDeepSeekEnvironment -Model $model -ApiKeyInfo $apiKeyInfo
    if (-not $NoSave) {
        Save-AgentLlmConfig -Provider $script:DeepSeekProvider -Model $model -ApiKeyInfo $apiKeyInfo
    }
}

function Save-AgentSecret {
    param([string]$Name, [securestring]$Secret)
    if ($null -eq $Secret -or $Secret.Length -eq 0) { return }
    $secretDir = Join-Path $script:RepoRoot "configs\secrets"
    New-Item -ItemType Directory -Force -Path $secretDir | Out-Null
    $path = Join-Path $secretDir ("{0}.dpapi" -f $Name)
    $Secret | ConvertFrom-SecureString | Set-Content -Path $path -Encoding UTF8 -NoNewline
}

function Get-AgentSecret {
    param([string]$Name)
    $path = Join-Path $script:RepoRoot ("configs\secrets\{0}.dpapi" -f $Name)
    if (-not (Test-Path $path)) { return $null }
    try {
        return (Get-Content -Path $path -Raw).Trim() | ConvertTo-SecureString
    } catch {
        return $null
    }
}

function Remove-AgentSecret {
    param([string]$Name)
    $path = Join-Path $script:RepoRoot ("configs\secrets\{0}.dpapi" -f $Name)
    if (Test-Path $path) { Remove-Item -Path $path -Force }
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
    if ($ApiKeyInfo.HasKey -and $ApiKeyInfo.Key) {
        $secure = ConvertTo-SecureString $ApiKeyInfo.Key -AsPlainText -Force
        Save-AgentSecret -Name $ApiKeyInfo.EnvName -Secret $secure
    }
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
    Remove-AgentSecret -Name "DEEPSEEK_API_KEY"
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

function Update-AgentDatabaseSchemaQuiet {
    if (-not (Test-AgentPythonEnvironment)) { return }
    Push-Location $script:RepoRoot
    try { python -m ultrafast_memory.app.cli init-db | Out-Null } finally { Pop-Location }
}

function Invoke-AgentScan {
    if (-not (Test-AgentPythonEnvironment)) { return }
    Push-Location $script:RepoRoot
    try { python -m ultrafast_memory.app.cli scan examples } finally { Pop-Location }
}

function Start-AgentApiServer {
    if (-not (Test-AgentPythonEnvironment)) { return }
    Push-Location $script:RepoRoot
    $previousPythonPath = $env:PYTHONPATH
    $env:PYTHONPATH = (Join-Path $script:RepoRoot "src") + [IO.Path]::PathSeparator + $previousPythonPath
    try { python -m uvicorn ultrafast_memory.apps.api.main:app --reload --host 127.0.0.1 --port 8000 } finally {
        $env:PYTHONPATH = $previousPythonPath
        Pop-Location
    }
}

function Export-AgentBoDataset {
    if (-not (Test-AgentPythonEnvironment)) { return }
    Push-Location $script:RepoRoot
    try { python -m ultrafast_memory.app.cli export-bo } finally { Pop-Location }
}

function Test-AgentExampleDataImported {
    $rawDir = Join-Path $script:RepoRoot "data\raw_artifacts"
    return (Test-Path $rawDir) -and ((Get-ChildItem -Path $rawDir -Recurse -File -ErrorAction SilentlyContinue | Select-Object -First 1) -ne $null)
}

function Test-AgentBoDatasetExported {
    $path = Join-Path $script:RepoRoot "data\exports\bo_training_samples.csv"
    return Test-Path $path
}

function Initialize-AgentLocalBootstrap {
    param([switch]$Force)
    if (-not (Test-AgentPythonEnvironment)) { return }
    Write-Host "检查本地数据库 schema..."
    Update-AgentDatabaseSchemaQuiet
    if ($Force -or -not (Test-AgentExampleDataImported)) {
        Invoke-AgentScan
    } else {
        Write-Host "示例数据已存在，跳过扫描。"
    }
    if ($Force -or -not (Test-AgentBoDatasetExported)) {
        Export-AgentBoDataset
    } else {
        Write-Host "BO 数据集已存在，跳过导出。"
    }
}

function Show-AgentConfig {
    Write-Host ("Provider: {0}" -f $env:ULTRAFAST_LLM_PROVIDER)
    Write-Host ("Model: {0}" -f $env:ULTRAFAST_LLM_MODEL)
    Write-Host ("API Base: {0}" -f $env:ULTRAFAST_LLM_API_BASE)
    Write-Host ("API Key Env: {0}" -f $env:ULTRAFAST_LLM_API_KEY_ENV)
    $local = Load-AgentLlmConfig
    if ($local) { Write-Host "Local config: configs/llm.local.json" } else { Write-Host "Local config: none" }
}

function Test-AgentApiServer {
    param(
        [string]$BaseUrl = "http://127.0.0.1:8000",
        [switch]$Quiet
    )
    try {
        $resp = Invoke-RestMethod -Method Get -Uri "$BaseUrl/health" -TimeoutSec 3
        return ($resp.status -eq "ok")
    } catch {
        if (-not $Quiet) {
            Write-Host "FastAPI 后端未启动。"
            Write-Host "请先在主菜单选择“启动 FastAPI 服务”，并保持该服务运行。"
            Write-Host "如果在 TUI 中配置了 API Key，必须从同一个 TUI 会话中启动 FastAPI，后端进程才会继承环境变量。"
        }
        return $false
    }
}

function Show-AgentRuntimeIdentity {
    param($Health)
    if ($null -eq $Health -or $null -eq $Health.runtime_identity) { return }
    $identity = $Health.runtime_identity
    Write-Host "[Runtime Identity]" -ForegroundColor Cyan
    Write-Host ("runtime_mode={0}" -f $identity.runtime_mode)
    Write-Host ("git_commit={0}" -f $identity.git_commit)
    Write-Host ("git_branch={0}" -f $identity.git_branch)
    Write-Host ("git_dirty={0}" -f $identity.git_dirty)
    Write-Host ("python={0}" -f $identity.python)
    Write-Host ("package_root={0}" -f $identity.package_root)
    Write-Host ("main_agent_loop={0}" -f $identity.main_agent_loop)
    Write-Host ("main_agent_planner={0}" -f $identity.main_agent_planner)
    Write-Host ("skill_registry={0}" -f $identity.skill_registry)
    Write-Host ("tool_registry={0}" -f $identity.tool_registry)
    Write-Host ("update_task_context_tool={0}" -f $identity.update_task_context_tool)
    Write-Host ("backend_pid={0}" -f $identity.backend_pid)
    Write-Host ("backend_started_at={0}" -f $identity.backend_started_at)
}

function Test-AgentRuntimeIdentity {
    param($Health)
    if ($null -eq $Health -or $Health.agent_capability_contract -ne "skill-discovery-v2") { return $false }
    if ($null -eq $Health.runtime_identity) { return $false }
    if ($Health.runtime_identity.runtime_mode -ne "capability_discovery") { return $false }
    $localCommit = (& git -C $script:RepoRoot rev-parse HEAD 2>$null).Trim()
    $expectedRoot = [IO.Path]::GetFullPath((Join-Path $script:RepoRoot "src")).TrimEnd('\').ToLowerInvariant()
    $actualRoot = [IO.Path]::GetFullPath([string]$Health.runtime_identity.package_root).TrimEnd('\').ToLowerInvariant()
    $runtimeFiles = @(
        $Health.runtime_identity.main_agent_loop,
        $Health.runtime_identity.main_agent_planner,
        $Health.runtime_identity.skill_registry,
        $Health.runtime_identity.tool_registry
    )
    $filesValid = -not ($runtimeFiles | Where-Object { -not $_ -or -not (Test-Path ([string]$_)) })
    return ($localCommit -and $Health.runtime_identity.git_commit -eq $localCommit -and $actualRoot -eq $expectedRoot -and $filesValid)
}

function Test-AgentEquipmentApiServer {
    param([string]$BaseUrl = "http://127.0.0.1:8000")
    try {
        Invoke-RestMethod -Method Get -Uri "$BaseUrl/equipment/active" -TimeoutSec 3 | Out-Null
        $schema = Invoke-RestMethod -Method Get -Uri "$BaseUrl/equipment/schema" -TimeoutSec 3
        return ($schema.schema_version -ge 2 -and ($schema.required_setup_fields -contains "actual_max_power_W") -and ($schema.required_setup_fields -contains "pulse_width_min_fs"))
    } catch {
        return $false
    }
}

function Test-AgentLlmConnection {
    param([string]$BaseUrl = "http://127.0.0.1:8000")
    try {
        $result = Invoke-RestMethod -Method Post -Uri "$BaseUrl/llm/test" -TimeoutSec 25
        if ($result.valid) {
            Write-Host ("DeepSeek 调用链验证通过：{0}/{1}" -f $result.provider, $result.model) -ForegroundColor Green
            return $true
        }
        $message = if ($result.message) { $result.message } else { "未知验证错误。" }
        Write-Host ("DeepSeek 调用链验证失败：{0}" -f $message) -ForegroundColor Red
        Write-Host "请关闭后使用 .\scripts\start_agent_tui.ps1 -Reconfigure 重新配置有效 API Key。" -ForegroundColor Yellow
        return $false
    } catch {
        Write-Host ("DeepSeek 调用链验证请求失败：{0}" -f $_.Exception.Message) -ForegroundColor Red
        return $false
    }
}

function Update-AgentLlmConfigFromChat {
    param([string]$BaseUrl = "http://127.0.0.1:8000")
    Write-Host "重新配置 DeepSeek API Key 与模型。凭证输入不会回显。" -ForegroundColor Cyan
    Initialize-AgentDeepSeekConfig -Reconfigure
    $port = ([Uri]$BaseUrl).Port
    $newBaseUrl = Start-AgentApiServerBackground -PreferredPort $port -MaxPort $port -RestartExisting
    if (-not $newBaseUrl) {
        Write-Host "LLM 配置已保存，但后端重启失败。" -ForegroundColor Red
        return $null
    }
    Test-AgentLlmConnection -BaseUrl $newBaseUrl | Out-Null
    return $newBaseUrl
}

function Format-AgentRestError {
    param($ErrorRecord)
    $message = $ErrorRecord.Exception.Message
    $detail = $null
    if ($ErrorRecord.ErrorDetails -and -not [string]::IsNullOrWhiteSpace($ErrorRecord.ErrorDetails.Message)) {
        $detail = $ErrorRecord.ErrorDetails.Message
    }
    if (-not $detail -and $ErrorRecord.Exception.Response) {
        try {
            $stream = $ErrorRecord.Exception.Response.GetResponseStream()
            if ($stream) {
                $reader = [System.IO.StreamReader]::new($stream)
                $detail = $reader.ReadToEnd()
                $reader.Dispose()
            }
        } catch {
            $detail = $null
        }
    }
    if ($detail) { return "$message Detail: $detail" }
    return $message
}

function Test-AgentTcpPortAvailable {
    param([int]$Port)
    $listener = $null
    try {
        $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Parse("127.0.0.1"), $Port)
        $listener.Start()
        return $true
    } catch {
        return $false
    } finally {
        if ($listener) { $listener.Stop() }
    }
}

function Start-AgentApiServerBackground {
    param(
        [int]$PreferredPort = 8000,
        [int]$MaxPort = 8010,
        [switch]$RestartExisting
    )
    if (-not (Test-AgentPythonEnvironment)) { return $false }
    for ($port = $PreferredPort; $port -le $MaxPort; $port++) {
        $baseUrl = "http://127.0.0.1:$port"
        if (Test-AgentApiServer -BaseUrl $baseUrl -Quiet) {
            if (Test-AgentEquipmentApiServer -BaseUrl $baseUrl) {
                $health = $null
                try { $health = Invoke-RestMethod -Method Get -Uri "$baseUrl/health" -TimeoutSec 3 } catch { $health = $null }
                $staleWorkflowBackend = ($null -eq $health -or $health.workflow_contract -ne "process-workflow-v3")
                $staleRuntimeIdentity = -not (Test-AgentRuntimeIdentity -Health $health)
                if ($staleWorkflowBackend -or $staleRuntimeIdentity) {
                    Write-Host ("检测到后端版本或运行源码身份不一致，必须重启：{0}" -f $baseUrl) -ForegroundColor Yellow
                    $RestartExisting = $true
                }
                if ($RestartExisting) {
                    $ownerPid = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
                        Select-Object -First 1 -ExpandProperty OwningProcess
                    if (-not $ownerPid) {
                        throw "无法确定端口 $port 上现有后端的进程 ID。"
                    }
                    Write-Host ("正在重启现有 FastAPI 后端以应用新 LLM 凭证。PID: {0}" -f $ownerPid)
                    Stop-Process -Id $ownerPid -Force
                    for ($i = 0; $i -lt 20; $i++) {
                        Start-Sleep -Milliseconds 200
                        if (Test-AgentTcpPortAvailable -Port $port) { break }
                    }
                    if (-not (Test-AgentTcpPortAvailable -Port $port)) {
                        throw "端口 $port 上的旧后端未能及时退出。"
                    }
                } else {
                    Write-Host ("FastAPI 后端已运行：{0}" -f $baseUrl)
                    Show-AgentRuntimeIdentity -Health $health
                    return $baseUrl
                }
            }
            if (Test-AgentApiServer -BaseUrl $baseUrl -Quiet) {
                Write-Host ("端口 {0} 已有后端运行，但缺少设备配置接口，尝试下一个端口。" -f $port) -ForegroundColor Yellow
                continue
            }
        }
        if (-not (Test-AgentTcpPortAvailable -Port $port)) {
            Write-Host ("端口 {0} 已被占用，尝试下一个端口。" -f $port)
            continue
        }
        Write-Host ("正在后台启动 FastAPI 后端：{0} ..." -f $baseUrl)
        $previousPythonPath = $env:PYTHONPATH
        $env:PYTHONPATH = (Join-Path $script:RepoRoot "src") + [IO.Path]::PathSeparator + $previousPythonPath
        try {
            $process = Start-Process -FilePath "python" `
                -ArgumentList @("-m", "uvicorn", "ultrafast_memory.apps.api.main:app", "--host", "127.0.0.1", "--port", "$port") `
                -WorkingDirectory $script:RepoRoot `
                -WindowStyle Hidden `
                -PassThru
        } finally {
            $env:PYTHONPATH = $previousPythonPath
        }
        for ($i = 0; $i -lt 30; $i++) {
            Start-Sleep -Milliseconds 500
            if (Test-AgentApiServer -BaseUrl $baseUrl -Quiet) {
                if (-not (Test-AgentEquipmentApiServer -BaseUrl $baseUrl)) {
                    Write-Host ("FastAPI 后端在端口 {0} 启动后缺少设备配置接口，尝试下一个端口。" -f $port) -ForegroundColor Yellow
                    if ($process -and -not $process.HasExited) {
                        Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
                    }
                    break
                }
                Write-Host ("FastAPI 后端已启动。PID: {0}; URL: {1}" -f $process.Id, $baseUrl)
                $health = Invoke-RestMethod -Method Get -Uri "$baseUrl/health" -TimeoutSec 3
                Show-AgentRuntimeIdentity -Health $health
                return $baseUrl
            }
            if ($process.HasExited) {
                Write-Host ("FastAPI 后端在端口 {0} 启动失败，尝试下一个端口。" -f $port)
                break
            }
        }
    }
    Write-Host ("FastAPI 后端启动失败。请检查 {0}-{1} 端口是否被占用，或手动运行 python -m uvicorn ultrafast_memory.apps.api.main:app --host 127.0.0.1 --port <port>" -f $PreferredPort, $MaxPort)
    return $false
}

function New-AgentChatSession {
    param(
        [string]$BaseUrl = "http://127.0.0.1:8000",
        [string]$Title = "PowerShell TUI chat"
    )
    $body = @{
        title = $Title
        mode = "agent"
    } | ConvertTo-Json
    return Invoke-RestMethod -Method Post -Uri "$BaseUrl/chat/sessions" -ContentType "application/json; charset=utf-8" -Body $body
}

function Send-AgentChatMessage {
    param(
        [string]$SessionId,
        [string]$Message,
        [string]$BaseUrl = "http://127.0.0.1:8000"
    )
    $body = @{
        session_id = $SessionId
        message = $Message
        mode = "agent"
        stream = $false
    } | ConvertTo-Json
    return Invoke-RestMethod -Method Post -Uri "$BaseUrl/chat" -ContentType "application/json; charset=utf-8" -Body $body
}

function Get-AgentStreamMode {
    return $script:AgentStreamMode
}

function Set-AgentStreamMode {
    param([bool]$Enabled)
    $script:AgentStreamMode = $Enabled
}

function Get-AgentDisplayMode {
    return $script:AgentDisplayMode
}

function Set-AgentDisplayMode {
    param([string]$Mode)
    if ($Mode -notin @("normal", "research", "debug")) {
        Write-Host "无效模式。可选：normal, research, debug" -ForegroundColor Yellow
        return
    }
    $script:AgentDisplayMode = $Mode
    Write-Host ("显示模式已切换为：{0}" -f $Mode) -ForegroundColor Green
}

function Show-AgentProgressBar {
    param(
        $Percent,
        [string]$Stage,
        [string]$Message
    )
    if ($null -eq $Percent) {
        Write-Host ("[任务状态] {0}" -f $Stage) -ForegroundColor DarkCyan
        if (-not [string]::IsNullOrWhiteSpace($Message)) {
            Write-Host $Message -ForegroundColor DarkGray
        }
        return
    }
    if ((Get-AgentDisplayMode) -eq "normal") {
        Write-Host ("[进度 {0}%] {1} {2}" -f [Math]::Round($Percent), $Stage, $Message) -ForegroundColor DarkCyan
        return
    }
    $width = 20
    $filled = [Math]::Floor($Percent / 100 * $width)
    $empty = $width - $filled
    $bar = ("#" * $filled) + ("-" * $empty)
    Write-Host ("[任务进度] [{0}] {1}%  {2}" -f $bar, [Math]::Round($Percent), $Stage) -ForegroundColor Green
    if (-not [string]::IsNullOrWhiteSpace($Message)) {
        Write-Host $Message -ForegroundColor DarkGray
    }
}

function Show-AgentThinkingStatus {
    param(
        [string]$Title,
        [string]$Summary
    )
    if ((Get-AgentDisplayMode) -eq "normal") {
        Write-Host ("[状态] {0}" -f $Title) -ForegroundColor DarkCyan
        return
    }
    Write-Host ("[状态] {0}: {1}" -f $Title, $Summary) -ForegroundColor DarkCyan
}

function Show-AgentTraceEvent {
    param($Event)
    if ($null -eq $Event) { return }
    $mode = Get-AgentDisplayMode
    if ($mode -eq "normal" -and $Event.event_type -notin @("decision", "decision_gate", "approval_required", "warning", "error", "tool_failed", "workflow_end", "workflow_completed", "workflow_failed", "knowledge_lookup", "device_lookup")) { return }
    $mark = switch ($Event.status) {
        "completed" { "✓" }
        "failed" { "!" }
        "error" { "!" }
        default { "·" }
    }
    $label = if ($Event.title) { $Event.title } else { $Event.event_type }
    $summary = if ($Event.summary) { $Event.summary } else { "" }
    Write-Host ("{0} {1}: {2}" -f $mark, $label, $summary) -ForegroundColor DarkCyan
    if ($mode -eq "debug") {
        if ($Event.sequence) { Write-Host ("  sequence: {0}" -f $Event.sequence) -ForegroundColor DarkGray }
        $toolName = if ($Event.tool_name) { $Event.tool_name } else { $Event.tool }
        if ($toolName) { Write-Host ("  tool: {0}" -f $toolName) -ForegroundColor DarkGray }
        if ($Event.skill) { Write-Host ("  skill: {0}" -f $Event.skill) -ForegroundColor DarkGray }
        if ($Event.stage) { Write-Host ("  stage: {0}" -f $Event.stage) -ForegroundColor DarkGray }
        if ($Event.input_summary) { Write-Host ("  input: {0}" -f $Event.input_summary) -ForegroundColor DarkGray }
        if ($Event.output_summary) { Write-Host ("  output: {0}" -f $Event.output_summary) -ForegroundColor DarkGray }
        if ($null -ne $Event.duration_ms) { Write-Host ("  duration_ms: {0}" -f $Event.duration_ms) -ForegroundColor DarkGray }
        if ($null -ne $Event.cache_hit) { Write-Host ("  cache_hit: {0}" -f $Event.cache_hit) -ForegroundColor DarkGray }
        if ($Event.attempt) { Write-Host ("  attempt: {0}" -f $Event.attempt) -ForegroundColor DarkGray }
    }
}

function Show-AgentWorkflowState {
    param($WorkflowState)
    if ((Get-AgentDisplayMode) -eq "normal") { return }
    if ($null -eq $WorkflowState) { return }
    if ($WorkflowState.current_stage) {
        $percent = if ($null -ne $WorkflowState.percent) { $WorkflowState.percent } else { "?" }
        Write-Host ("[工作流] 当前阶段={0}；总体进度={1}%" -f $WorkflowState.current_stage, $percent) -ForegroundColor Green
    }
    if ($WorkflowState.workflow_overview -and (Get-AgentDisplayMode) -eq "debug") {
        foreach ($step in @($WorkflowState.workflow_overview)) {
            Write-Host ("  [{0}] {1}" -f $step.status, $step.step) -ForegroundColor DarkGray
        }
    }
    if ($WorkflowState.next_required_action) {
        $actionLabel = if ($WorkflowState.next_required_action.action_label) {
            $WorkflowState.next_required_action.action_label
        } else {
            $WorkflowState.next_required_action.action_type
        }
        Write-Host ("[下一步] {0}" -f $actionLabel) -ForegroundColor Yellow
        $requiredLabels = if ($WorkflowState.next_required_action.required_field_labels) {
            @($WorkflowState.next_required_action.required_field_labels)
        } else {
            @($WorkflowState.next_required_action.required_fields)
        }
        if ($requiredLabels.Count -gt 0) {
            Write-Host ("  必填：{0}" -f ($requiredLabels -join "、")) -ForegroundColor DarkGray
        }
    }
    $campaign = if ($WorkflowState.formal_campaign) { $WorkflowState.formal_campaign } else { $WorkflowState.campaign }
    if ($campaign) {
        Write-Host ("[优化任务] {0}；保真级别={1}；轮次={2}；状态={3}" -f `
            $campaign.campaign_id, $campaign.fidelity_level, $campaign.current_iteration, $campaign.status) -ForegroundColor DarkCyan
    }
    if ($WorkflowState.equipment_profile_used) {
        Write-Host ("[设备] {0} ({1})" -f $WorkflowState.equipment_profile_used.profile_name, $WorkflowState.equipment_profile_used.revision_id) -ForegroundColor DarkGray
    }
    if ($WorkflowState.missing_slots -and $WorkflowState.missing_slots.Count -gt 0) {
        Write-Host ("[缺失字段] {0}" -f (($WorkflowState.missing_slots | ForEach-Object { "$_" }) -join ", ")) -ForegroundColor DarkGray
    }
}

function Show-AgentExecutionTrace {
    param($Events)
    if ($null -eq $Events -or (Get-AgentDisplayMode) -eq "normal") { return }
    Write-Host "▼ 执行轨迹" -ForegroundColor Cyan
    foreach ($traceEvent in @($Events)) {
        Show-AgentTraceEvent -Event $traceEvent
    }
}

function Show-AgentToolCall {
    param($Event)
    if ($null -eq $Event) { return }
    $mode = Get-AgentDisplayMode
    if ($mode -eq "normal" -and $Event.status -notin @("failed", "error", "retrying")) { return }
    $toolName = if ($Event.tool_name) { $Event.tool_name } else { $Event.tool }
    $duration = if ($null -ne $Event.duration_ms) { "；$($Event.duration_ms) ms" } else { "" }
    Write-Host ("[工具] {0}：{1}{2}" -f $toolName, $Event.status, $duration) -ForegroundColor DarkCyan
    if ($mode -eq "debug") {
        if ($Event.input_summary) { Write-Host ("  input: {0}" -f ($Event.input_summary | ConvertTo-Json -Compress -Depth 6)) -ForegroundColor DarkGray }
        if ($Event.output_summary) { Write-Host ("  output: {0}" -f ($Event.output_summary | ConvertTo-Json -Compress -Depth 6)) -ForegroundColor DarkGray }
        if ($Event.attempt) { Write-Host ("  attempt: {0}" -f $Event.attempt) -ForegroundColor DarkGray }
    }
}

function Show-AgentEvidenceSummary {
    param($EvidencePack)
    if ($null -eq $EvidencePack) { return }
    $hits = @($EvidencePack.hits).Count
    $citations = @($EvidencePack.citations).Count
    Write-Host ("[文献证据] status={0}；chunks={1}；citations={2}" -f $EvidencePack.evidence_status, $hits, $citations) -ForegroundColor DarkCyan
    if ((Get-AgentDisplayMode) -ne "normal" -and $EvidencePack.missing_evidence) {
        Write-Host ("  缺失：{0}" -f (@($EvidencePack.missing_evidence) -join "；")) -ForegroundColor DarkGray
    }
}

function Show-AgentTrialDecision {
    param($Decision)
    if ($null -eq $Decision) { return }
    $recommended = if ($Decision.recommended_mode) { $Decision.recommended_mode } else { $Decision.trial_mode }
    Write-Host ("[试切策略] 建议/选择：{0}" -f $recommended) -ForegroundColor DarkCyan
    if ((Get-AgentDisplayMode) -ne "normal" -and $Decision.reasons) {
        Write-Host ("  依据：{0}" -f (@($Decision.reasons) -join "；")) -ForegroundColor DarkGray
    }
}

function Show-AgentApprovalCard {
    param($Decision)
    Show-AgentKnowledgeUsageCard -Decision $Decision
}

function Show-AgentLatencyWaterfall {
    param($Waterfall)
    if ($null -eq $Waterfall -or (Get-AgentDisplayMode) -eq "normal") { return }
    Write-Host "▼ 延迟 waterfall" -ForegroundColor Cyan
    foreach ($property in $Waterfall.PSObject.Properties | Sort-Object Name) {
        Write-Host ("  {0}: {1} ms" -f $property.Name, $property.Value) -ForegroundColor DarkGray
    }
}

function Read-AgentNullableDouble {
    param([string]$Prompt)
    $value = Read-Host $Prompt
    if ([string]::IsNullOrWhiteSpace($value)) { return $null }
    return [double]$value
}

function Read-AgentNullableDoubleDefault {
    param(
        [string]$Prompt,
        $Default = $null
    )
    $label = $Prompt
    if ($null -ne $Default -and -not [string]::IsNullOrWhiteSpace([string]$Default)) {
        $label = "$Prompt [$Default]"
    }
    $value = Read-Host $label
    if ([string]::IsNullOrWhiteSpace($value)) { return $null }
    return [double]$value
}

function Read-AgentNullableRange {
    param([string]$Prompt)
    $value = Read-Host $Prompt
    if ([string]::IsNullOrWhiteSpace($value)) { return $null }
    $normalized = $value.Replace("，", ",")
    $parts = $normalized.Split(",") | ForEach-Object { $_.Trim() }
    if ($parts.Count -ne 2 -or [string]::IsNullOrWhiteSpace($parts[0]) -or [string]::IsNullOrWhiteSpace($parts[1])) {
        throw "请输入范围格式：最小值,最大值，例如 500,8000"
    }
    $min = [double]$parts[0]
    $max = [double]$parts[1]
    if ($min -gt $max) {
        throw "范围最小值不能大于最大值。"
    }
    return @($min, $max)
}

function Read-AgentNullableRangeDefault {
    param(
        [string]$Prompt,
        $DefaultMin = $null,
        $DefaultMax = $null
    )
    $label = $Prompt
    if ($null -ne $DefaultMin -and $null -ne $DefaultMax) {
        $label = "$Prompt [$DefaultMin,$DefaultMax]"
    }
    return Read-AgentNullableRange $label
}

function Get-AgentMachineBounds {
    param([string]$BaseUrl = "http://127.0.0.1:8000")
    return Invoke-RestMethod -Method Get -Uri "$BaseUrl/equipment/active/machine-bounds"
}

function Start-EquipmentSetupWizard {
    param([string]$BaseUrl = "http://127.0.0.1:8000")
    if (-not (Test-AgentApiServer -BaseUrl $BaseUrl)) { return }
    Write-Host ""
    Write-Host "=== 设备参数配置向导 ===" -ForegroundColor Cyan
    Write-Host "不确定字段可直接回车跳过；系统会记录为空，不会编造。" -ForegroundColor DarkGray
    $profileName = Read-Host "设备名称"
    if ([string]::IsNullOrWhiteSpace($profileName)) {
        Write-Host "设备名称不能为空。"
        return
    }
    $machineId = Read-Host "machine_id"
    $wavelength = Read-AgentNullableDouble "波长 nm"
    $pulseRange = Read-AgentNullableRange "脉宽范围fs（示例：500,8000）"
    $ratedMaxPower = Read-AgentNullableDouble "额定最大功率 W"
    $actualMaxPower = Read-AgentNullableDouble "实际最大功率 W"
    $frequencyRange = Read-AgentNullableRange "重复频率范围kHz（示例：50,1000）"
    $scanRange = Read-AgentNullableRange "扫描速度范围mm/s（示例：10,3000）"
    $spot = Read-AgentNullableDouble "光斑直径 um"
    $activeChoice = Read-Host "是否设为当前 active 设备？Y/N"
    $body = @{
        profile_name = $profileName
        machine_id = $(if ([string]::IsNullOrWhiteSpace($machineId)) { $null } else { $machineId })
        laser_source = @{
            wavelength_nm = $wavelength
            pulse_width_min_fs = $(if ($null -ne $pulseRange) { $pulseRange[0] } else { $null })
            pulse_width_max_fs = $(if ($null -ne $pulseRange) { $pulseRange[1] } else { $null })
            rated_max_power_W = $ratedMaxPower
            actual_max_power_W = $actualMaxPower
            frequency_min_kHz = $(if ($null -ne $frequencyRange) { $frequencyRange[0] } else { $null })
            frequency_max_kHz = $(if ($null -ne $frequencyRange) { $frequencyRange[1] } else { $null })
        }
        optical_setup = @{
            spot_diameter_um = $spot
        }
        motion_system = @{
            scan_speed_min_mm_s = $(if ($null -ne $scanRange) { $scanRange[0] } else { $null })
            scan_speed_max_mm_s = $(if ($null -ne $scanRange) { $scanRange[1] } else { $null })
        }
        process_capability = @{}
        set_active = ($activeChoice -match "^(y|Y)")
    } | ConvertTo-Json -Depth 8
    try {
        $result = Invoke-RestMethod -Method Post -Uri "$BaseUrl/equipment/profiles" -ContentType "application/json; charset=utf-8" -Body $body
        Write-Host ("已创建设备配置：{0}" -f $result.equipment_profile_id) -ForegroundColor Green
        Write-Host ("Revision: {0}, Active: {1}" -f $result.revision_id, $result.is_active)
    } catch {
        Write-Host ("设备配置失败：{0}" -f (Format-AgentRestError $_)) -ForegroundColor Red
    }
}

function Update-ActiveEquipmentProfileWizard {
    param([string]$BaseUrl = "http://127.0.0.1:8000")
    if (-not (Test-AgentApiServer -BaseUrl $BaseUrl)) { return }
    $active = Invoke-RestMethod -Method Get -Uri "$BaseUrl/equipment/active"
    if (-not $active.active) {
        Write-Host "当前尚未配置 active 设备，先进入新建设备配置向导。" -ForegroundColor Yellow
        Start-EquipmentSetupWizard -BaseUrl $BaseUrl
        return
    }
    Write-Host ""
    Write-Host "=== 修改当前 active 设备参数 ===" -ForegroundColor Cyan
    Write-Host "直接回车表示保留原值。" -ForegroundColor DarkGray
    $wavelength = Read-AgentNullableDoubleDefault "波长 nm" $active.laser_source.wavelength_nm
    $pulseRange = Read-AgentNullableRangeDefault "脉宽范围fs（示例：500,8000）" $active.laser_source.pulse_width_min_fs $active.laser_source.pulse_width_max_fs
    $ratedMaxPower = Read-AgentNullableDoubleDefault "额定最大功率 W" $active.laser_source.rated_max_power_W
    $actualMaxPower = Read-AgentNullableDoubleDefault "实际最大功率 W" $active.laser_source.actual_max_power_W
    $frequencyRange = Read-AgentNullableRangeDefault "重复频率范围kHz（示例：50,1000）" $active.laser_source.frequency_min_kHz $active.laser_source.frequency_max_kHz
    $scanRange = Read-AgentNullableRangeDefault "扫描速度范围mm/s（示例：10,3000）" $active.motion_system.scan_speed_min_mm_s $active.motion_system.scan_speed_max_mm_s
    $spot = Read-AgentNullableDoubleDefault "光斑直径 um" $active.optical_setup.spot_diameter_um
    $laserSource = @{}
    if ($null -ne $wavelength) { $laserSource.wavelength_nm = $wavelength }
    if ($null -ne $pulseRange) {
        $laserSource.pulse_width_min_fs = $pulseRange[0]
        $laserSource.pulse_width_max_fs = $pulseRange[1]
    }
    if ($null -ne $ratedMaxPower) { $laserSource.rated_max_power_W = $ratedMaxPower }
    if ($null -ne $actualMaxPower) { $laserSource.actual_max_power_W = $actualMaxPower }
    if ($null -ne $frequencyRange) {
        $laserSource.frequency_min_kHz = $frequencyRange[0]
        $laserSource.frequency_max_kHz = $frequencyRange[1]
    }
    $motionSystem = @{}
    if ($null -ne $scanRange) {
        $motionSystem.scan_speed_min_mm_s = $scanRange[0]
        $motionSystem.scan_speed_max_mm_s = $scanRange[1]
    }
    $opticalSetup = @{}
    if ($null -ne $spot) { $opticalSetup.spot_diameter_um = $spot }
    if ($laserSource.Count -eq 0 -and $motionSystem.Count -eq 0 -and $opticalSetup.Count -eq 0) {
        Write-Host "没有修改任何设备参数。"
        return
    }
    $bodyHash = @{}
    if ($laserSource.Count -gt 0) { $bodyHash.laser_source = $laserSource }
    if ($motionSystem.Count -gt 0) { $bodyHash.motion_system = $motionSystem }
    if ($opticalSetup.Count -gt 0) { $bodyHash.optical_setup = $opticalSetup }
    $body = $bodyHash | ConvertTo-Json -Depth 8
    try {
        $result = Invoke-RestMethod -Method Patch -Uri "$BaseUrl/equipment/profiles/$($active.equipment_profile_id)" -ContentType "application/json; charset=utf-8" -Body $body
        Write-Host ("设备参数已更新。Revision: {0}" -f $result.revision_id) -ForegroundColor Green
    } catch {
        Write-Host ("设备参数修改失败：{0}" -f (Format-AgentRestError $_)) -ForegroundColor Red
    }
}

function Show-ActiveEquipmentProfile {
    param([string]$BaseUrl = "http://127.0.0.1:8000")
    if (-not (Test-AgentApiServer -BaseUrl $BaseUrl)) { return }
    $active = Invoke-RestMethod -Method Get -Uri "$BaseUrl/equipment/active"
    if (-not $active.active) {
        Write-Host "当前尚未配置 active 设备。"
        return
    }
    $bounds = Get-AgentMachineBounds -BaseUrl $BaseUrl
    Write-Host ""
    Write-Host "当前 active 设备：" -ForegroundColor Cyan
    Write-Host ("Profile: {0}" -f $active.profile_name)
    Write-Host ("Equipment ID: {0}" -f $active.equipment_profile_id)
    Write-Host ("Wavelength: {0} nm" -f $active.laser_source.wavelength_nm)
    Write-Host ("Pulse width: {0}-{1} fs" -f $active.laser_source.pulse_width_min_fs, $active.laser_source.pulse_width_max_fs)
    Write-Host ("Rated max power: {0} W" -f $active.laser_source.rated_max_power_W)
    Write-Host ("Actual max power: {0} W" -f $active.laser_source.actual_max_power_W)
    Write-Host ("Frequency: {0}-{1} kHz" -f $active.laser_source.frequency_min_kHz, $active.laser_source.frequency_max_kHz)
    Write-Host ("Scan speed: {0}-{1} mm/s" -f $active.motion_system.scan_speed_min_mm_s, $active.motion_system.scan_speed_max_mm_s)
    Write-Host ("Spot diameter: {0} um" -f $active.optical_setup.spot_diameter_um)
    Write-Host ("Revision: {0}" -f $active.revision_id)
    Write-Host "Machine bounds:"
    Write-Host ($bounds.machine_bounds | ConvertTo-Json -Depth 8)
}

function Select-ActiveEquipmentProfile {
    param([string]$BaseUrl = "http://127.0.0.1:8000")
    if (-not (Test-AgentApiServer -BaseUrl $BaseUrl)) { return }
    $profiles = Invoke-RestMethod -Method Get -Uri "$BaseUrl/equipment/profiles"
    if (-not $profiles -or $profiles.Count -eq 0) {
        Write-Host "暂无设备配置。"
        return
    }
    Write-Host "equipment_profile_id | active | profile_name"
    foreach ($profile in $profiles) {
        Write-Host ("{0} | {1} | {2}" -f $profile.equipment_profile_id, $profile.is_active, $profile.profile_name)
    }
    $id = Read-Host "请输入要设为 active 的 equipment_profile_id"
    if ([string]::IsNullOrWhiteSpace($id)) { return }
    try {
        $result = Invoke-RestMethod -Method Post -Uri "$BaseUrl/equipment/profiles/$id/activate"
        Write-Host ("已切换 active 设备：{0}, revision: {1}" -f $result.equipment_profile_id, $result.revision_id) -ForegroundColor Green
    } catch {
        Write-Host "切换失败：$($_.Exception.Message)" -ForegroundColor Red
    }
}

function Send-AgentChatStream {
    param(
        [string]$SessionId,
        [string]$Message,
        [string]$BaseUrl = "http://127.0.0.1:8000"
    )
    $body = @{
        session_id = $SessionId
        message = $Message
        mode = (Get-AgentDisplayMode)
        stream = $true
    } | ConvertTo-Json -Depth 8

    $client = [System.Net.Http.HttpClient]::new()
    $request = [System.Net.Http.HttpRequestMessage]::new([System.Net.Http.HttpMethod]::Post, "$BaseUrl/chat/stream_ndjson")
    $request.Content = [System.Net.Http.StringContent]::new($body, [System.Text.Encoding]::UTF8, "application/json")
    $response = $null
    $reader = $null
    try {
        $response = $client.SendAsync($request, [System.Net.Http.HttpCompletionOption]::ResponseHeadersRead).GetAwaiter().GetResult()
        $response.EnsureSuccessStatusCode() | Out-Null
        $stream = $response.Content.ReadAsStreamAsync().GetAwaiter().GetResult()
        $reader = [System.IO.StreamReader]::new($stream, [System.Text.Encoding]::UTF8)

        Write-Host ""
        $traceHeaderShown = $false
        $answerHeaderShown = $false
        while (-not $reader.EndOfStream) {
            $line = $reader.ReadLine()
            if ([string]::IsNullOrWhiteSpace($line)) { continue }
            try {
                $event = $line | ConvertFrom-Json
            } catch {
                Write-Host ""
                Write-Host "[stream parse warning] $line" -ForegroundColor Yellow
                continue
            }
            if ($event.type -eq "meta") {
                Write-Host ("[stream: {0}/{1}]" -f $event.provider, $event.model) -ForegroundColor DarkGray
            } elseif ($event.type -eq "progress") {
                Show-AgentProgressBar -Percent $event.progress_percent -Stage $event.stage -Message $event.message
            } elseif ($event.type -eq "thinking_status") {
                Show-AgentThinkingStatus -Title $event.title -Summary $event.summary
            } elseif ($event.type -eq "heartbeat") {
                Write-Host ("[处理中] {0} {1}s" -f $event.summary, $event.elapsed_s) -ForegroundColor DarkGray
            } elseif ($event.type -eq "agent_trace") {
                if ((Get-AgentDisplayMode) -ne "normal" -and -not $traceHeaderShown) {
                    Write-Host "▼ 执行轨迹" -ForegroundColor Cyan
                    $traceHeaderShown = $true
                }
                if ($event.event_type -in @("tool_call", "tool_result", "tool_started", "tool_completed", "tool_failed")) {
                    Show-AgentToolCall -Event $event
                } else {
                    Show-AgentTraceEvent -Event $event
                }
            } elseif ($event.type -eq "workflow_state") {
                Show-AgentWorkflowState -WorkflowState $event
            } elseif ($event.type -eq "route") {
                if ((Get-AgentDisplayMode) -ne "normal" -and $event.primary_skill) {
                    Write-Host ("[skill: {0}, source: {1}, confidence: {2}]" -f $event.primary_skill, $event.route_source, $event.confidence) -ForegroundColor DarkGray
                }
            } elseif ($event.type -eq "delta") {
                if (-not $answerHeaderShown) {
                    Write-Host ""
                    Write-Host "智能体：" -ForegroundColor Cyan
                    $answerHeaderShown = $true
                }
                Write-Host -NoNewline $event.content
            } elseif ($event.type -eq "warning") {
                Write-Host ""
                $warningText = if ($event.summary) { $event.summary } else { $event.message }
                Write-Host ("[warning] {0}" -f $warningText) -ForegroundColor Yellow
            } elseif ($event.type -eq "error") {
                Write-Host ""
                $errorText = if ($event.summary) { $event.summary } else { $event.message }
                Write-Host ("[error] {0}" -f $errorText) -ForegroundColor Red
            } elseif ($event.type -eq "done") {
                Write-Host ""
            }
        }
        Write-Host ""
    } finally {
        if ($reader) { $reader.Dispose() }
        if ($response) { $response.Dispose() }
        $request.Dispose()
        $client.Dispose()
    }
}

function Show-AgentTrialChoice {
    param([string]$RecommendedMode = "simple_trial_cut")
    $label = switch ($RecommendedMode) {
        "full_trial_cut" { "完整试切" }
        "skip_trial" { "跳过试切" }
        default { "简化试切" }
    }
    Write-Host ("系统建议先进行{0}。" -f $label) -ForegroundColor Cyan
    Write-Host "[1] 简化试切"
    Write-Host "[2] 完整试切"
    Write-Host "[3] 跳过试切"
    $choice = Read-Host "请选择"
    $selectedMode = switch ($choice) {
        "2" { "full_trial_cut" }
        "3" { "skip_trial" }
        default { "simple_trial_cut" }
    }
    return $selectedMode
}

function Show-AgentKnowledgeUsageCard {
    param($Decision)
    if ($null -eq $Decision) { return }
    Write-Host "需要确认以下知识是否可用于当前决策：" -ForegroundColor Yellow
    Write-Host ("风险等级：{0}；证据数量：{1}" -f $Decision.risk_level, $Decision.evidence_ids.Count) -ForegroundColor DarkGray
    Write-Host "[1] 本次允许使用"
    Write-Host "[2] 批准为长期工艺先验"
    Write-Host "[3] 不使用"
}

function Show-AgentReviewTasks {
    param(
        [string]$BaseUrl = "http://127.0.0.1:8000",
        [string]$Status = "pending_review"
    )
    $tasks = Invoke-RestMethod -Method Get -Uri "$BaseUrl/knowledge/review/tasks?status=$Status"
    if (-not $tasks -or $tasks.Count -eq 0) {
        Write-Host "没有匹配的审核任务。"
        return
    }
    Write-Host "review_id | risk_level | suggested_action"
    foreach ($task in $tasks) {
        Write-Host ("{0} | {1} | {2}" -f $task.review_id, $task.risk_level, $task.auto_suggestion)
    }
}

function Show-AgentReviewTaskDetail {
    param(
        [string]$ReviewId,
        [string]$BaseUrl = "http://127.0.0.1:8000"
    )
    $detail = Invoke-RestMethod -Method Get -Uri "$BaseUrl/knowledge/review/tasks/$ReviewId"
    Write-Host ("Review: {0}" -f $detail.review_id)
    Write-Host ("Status: {0}" -f $detail.review_status)
    Write-Host ("Risk: {0}" -f $detail.risk_level)
    if ($detail.candidate) {
        Write-Host ("Claim: {0}" -f $detail.candidate.claim)
        Write-Host ("Material: {0}" -f $detail.candidate.material)
        Write-Host ("Process: {0}" -f $detail.candidate.process_type)
    }
    if ($detail.source) {
        Write-Host ("Source: {0}" -f $detail.source.title)
        Write-Host ("URL: {0}" -f $detail.source.url)
    }
}

function Invoke-AgentKnowledgeBootstrapMenu {
    $baseUrl = "http://127.0.0.1:8000"
    if (-not (Test-AgentApiServer -BaseUrl $baseUrl)) { return }
    $question = Read-Host "请输入问题"
    $material = Read-Host "material"
    $processType = Read-Host "process_type"
    $componentType = Read-Host "component_type"
    $taskSpec = @{
        material = $material
        process_type = $processType
        component_type = $componentType
    }
    $gapBody = @{
        task_spec = $taskSpec
        question = $question
        internal_hits = @()
    } | ConvertTo-Json -Depth 8
    $gap = Invoke-RestMethod -Method Post -Uri "$baseUrl/knowledge/evidence-gap" -ContentType "application/json; charset=utf-8" -Body $gapBody
    Write-Host ("evidence_score: {0}, recommended_action: {1}" -f $gap.evidence_score, $gap.recommended_action)
    if ($gap.recommended_action -eq "web_bootstrap") {
        $confirm = Read-Host "内部证据不足，是否执行 mock web bootstrap？(y/N)"
        if ($confirm -eq "y") {
            $body = @{
                task_spec = $taskSpec
                question = $question
                query_intent = "find_literature_prior"
                max_sources = 5
                review_required = $true
            } | ConvertTo-Json -Depth 8
            $result = Invoke-RestMethod -Method Post -Uri "$baseUrl/knowledge/bootstrap-web" -ContentType "application/json; charset=utf-8" -Body $body
            Write-Host ("生成 sources: {0}, candidates: {1}, review_tasks: {2}" -f $result.sources.Count, $result.knowledge_candidates.Count, $result.review_tasks.Count)
        }
    }
}

function Invoke-AgentReviewQueueMenu {
    $baseUrl = "http://127.0.0.1:8000"
    if (-not (Test-AgentApiServer -BaseUrl $baseUrl)) { return }
    while ($true) {
        Write-Host ""
        Write-Host "[1] 查看待审核任务"
        Write-Host "[2] 查看任务详情"
        Write-Host "[3] 接收入 RAG"
        Write-Host "[4] 接收为文献证据"
        Write-Host "[5] 拒绝"
        Write-Host "[6] 标记需要更多证据"
        Write-Host "[7] 返回"
        $choice = Read-Host "请选择操作"
        if ($choice -eq "1") {
            Show-AgentReviewTasks -BaseUrl $baseUrl
        } elseif ($choice -eq "2") {
            Show-AgentReviewTaskDetail -BaseUrl $baseUrl -ReviewId (Read-Host "review_id")
        } elseif ($choice -in @("3", "4", "5", "6")) {
            $reviewId = Read-Host "review_id"
            $reviewer = Read-Host "reviewer_id"
            $comment = Read-Host "comment"
            $action = @{
                "3" = "accept_to_rag"
                "4" = "accept_as_literature_evidence"
                "5" = "reject"
                "6" = "needs_more_evidence"
            }[$choice]
            $body = @{
                action = $action
                reviewer_id = $reviewer
                comment = $comment
                target_level = $(if ($action -eq "accept_to_rag") { "LEVEL_1_RAG_BACKGROUND" } else { $null })
                payload = @{}
            } | ConvertTo-Json -Depth 8
            $result = Invoke-RestMethod -Method Post -Uri "$baseUrl/knowledge/review/tasks/$reviewId/action" -ContentType "application/json; charset=utf-8" -Body $body
            Write-Host ($result | ConvertTo-Json -Depth 8)
        } elseif ($choice -eq "7") {
            return
        }
    }
}

function Start-AgentChat {
    param([string]$BaseUrl = "http://127.0.0.1:8000")
    $baseUrl = $BaseUrl
    if (-not (Test-AgentApiServer -BaseUrl $baseUrl)) { return }

    $session = New-AgentChatSession -BaseUrl $baseUrl
    $sessionId = $session.session_id
    Set-AgentStreamMode -Enabled $true

    Write-Host ""
    Write-Host "进入超快激光智能体聊天模式。输入 exit 退出。" -ForegroundColor Cyan
    Write-Host "可用命令：/stream on|off, /mode normal|research|debug, /trace summary|full|off, /skills, /tools, /reasoning, /waterfall, /campaign, /model, /llm config, /routes, /state, /reset, /skill <name>, /no_skill, /equipment show|edit"
    Write-Host ""
    Write-Host "已启用 Debug + full public trace。隐藏推理、系统提示词和凭据不会公开。" -ForegroundColor DarkGray

    while ($true) {
        $inputText = Read-Host "你"
        if ([string]::IsNullOrWhiteSpace($inputText) -and [Console]::IsInputRedirected) { break }
        if ($inputText -eq "exit") { break }
        if ([string]::IsNullOrWhiteSpace($inputText)) { continue }

        try {
            if ($inputText.Trim() -eq "/review tasks") {
                Show-AgentReviewTasks -BaseUrl $baseUrl
                continue
            }
            if ($inputText.Trim().StartsWith("/review open ")) {
                $reviewId = $inputText.Trim().Substring("/review open ".Length).Trim()
                Show-AgentReviewTaskDetail -BaseUrl $baseUrl -ReviewId $reviewId
                continue
            }
            if ($inputText.Trim() -eq "/equipment show") {
                Show-ActiveEquipmentProfile -BaseUrl $baseUrl
                continue
            }
            if ($inputText.Trim() -eq "/equipment edit") {
                Update-ActiveEquipmentProfileWizard -BaseUrl $baseUrl
                continue
            }
            if ($inputText.Trim() -in @("/llm config", "/llm reconfigure")) {
                $newBaseUrl = Update-AgentLlmConfigFromChat -BaseUrl $baseUrl
                if ($newBaseUrl) { $baseUrl = $newBaseUrl }
                continue
            }
            if ($inputText.Trim().StartsWith("/mode ")) {
                Set-AgentDisplayMode -Mode ($inputText.Trim().Substring("/mode ".Length).Trim().ToLowerInvariant())
                continue
            }
            Write-Host "加工助手执行中..." -ForegroundColor DarkCyan
            if (Get-AgentStreamMode) {
                Send-AgentChatStream -SessionId $sessionId -Message $inputText -BaseUrl $baseUrl
            } else {
                $resp = Send-AgentChatMessage -SessionId $sessionId -Message $inputText -BaseUrl $baseUrl
                Write-Host ""
                if ($resp.progress) {
                    Show-AgentProgressBar -Percent $resp.progress.progress_percent -Stage $resp.progress.current_stage -Message $resp.progress.message
                }
                if ($resp.thinking_status) {
                    foreach ($status in $resp.thinking_status) {
                        Show-AgentThinkingStatus -Title $status.title -Summary $status.summary
                    }
                }
                if ($resp.execution_trace) {
                    Write-Host "▼ 执行轨迹" -ForegroundColor Cyan
                    foreach ($traceEvent in $resp.execution_trace) {
                        Show-AgentTraceEvent -Event $traceEvent
                    }
                }
                if ($resp.workflow_state) {
                    Show-AgentWorkflowState -WorkflowState $resp.workflow_state
                }
                Write-Host "智能体：" -ForegroundColor Cyan
                Write-Host $resp.assistant_message
                Write-Host ""
                if ($resp.selected_skill) {
                    if ($resp.route_plan) {
                        Write-Host ("[skill: {0}, source: {1}, confidence: {2}]" -f $resp.selected_skill, $resp.route_plan.route_source, $resp.route_plan.confidence) -ForegroundColor DarkGray
                    } else {
                        Write-Host "[skill: $($resp.selected_skill)]" -ForegroundColor DarkGray
                    }
                    Write-Host ""
                }
            }
            if ($inputText.Trim() -eq "/stream on") { Set-AgentStreamMode -Enabled $true }
            if ($inputText.Trim() -eq "/stream off") { Set-AgentStreamMode -Enabled $false }
        } catch {
            Write-Host "聊天请求失败：$($_.Exception.Message)"
        }
    }
}

function Start-AgentDeepSeekAutoLaunch {
    param(
        [switch]$NoSave,
        [switch]$SkipLlmConfig,
        [switch]$Reconfigure,
        [switch]$ForceInitialize
    )
    if (-not $SkipLlmConfig) {
        Initialize-AgentDeepSeekConfig -NoSave:$NoSave -Reconfigure:$Reconfigure
    } else {
        Write-Host "已跳过 DeepSeek API Key 配置；聊天将使用 MockLLM。"
    }

    Initialize-AgentLocalBootstrap -Force:$ForceInitialize
    # The launcher owns this local backend: restart it so updated source and credentials cannot be shadowed by an old process.
    $baseUrl = Start-AgentApiServerBackground -RestartExisting
    if (-not $baseUrl) { return }
    if (-not $SkipLlmConfig) {
        Test-AgentLlmConnection -BaseUrl $baseUrl | Out-Null
    }
    try {
        $activeEquipment = Invoke-RestMethod -Method Get -Uri "$baseUrl/equipment/active"
        if (-not $activeEquipment.active) {
            Write-Host "当前尚未配置激光设备参数。" -ForegroundColor Yellow
            Write-Host "建议先配置设备边界，否则任务解析和 BO 推荐会反复询问设备信息。" -ForegroundColor Yellow
            $configureEquipment = Read-Host "是否现在配置？[Y/N]"
            if ($configureEquipment -match "^(y|Y)") {
                Start-EquipmentSetupWizard -BaseUrl $baseUrl
            }
        }
    } catch {
        Write-Host "设备配置检查失败：$($_.Exception.Message)" -ForegroundColor Yellow
        Write-Host "正在打开设备参数配置向导。" -ForegroundColor Yellow
        Start-EquipmentSetupWizard -BaseUrl $baseUrl
    }
    Start-AgentChat -BaseUrl $baseUrl
}

function Show-AgentMainMenu {
    while ($true) {
        Write-Host ""
        Write-Host "[1] 一键初始化本地数据闭环"
        Write-Host "[2] 初始化数据库"
        Write-Host "[3] 扫描示例数据"
        Write-Host "[4] 启动 FastAPI 服务"
        Write-Host "[5] 导出 BO 数据集"
        Write-Host "[6] 查看配置"
        Write-Host "[7] 清除本地 LLM 配置"
        Write-Host "[8] 退出"
        Write-Host "[9] 进入聊天"
        Write-Host "[10] 知识冷启动"
        Write-Host "[11] 专家审核队列"
        Write-Host "[12] 配置设备参数"
        Write-Host "[13] 查看当前设备配置"
        Write-Host "[14] 切换当前设备配置"
        Write-Host "[15] 修改当前设备参数"
        $choice = Read-Host "请选择操作"
        if ([string]::IsNullOrWhiteSpace($choice) -and [Console]::IsInputRedirected) { return }
        if ($choice -eq "1") {
            Initialize-AgentLocalBootstrap
        } elseif ($choice -eq "2") {
            Initialize-AgentDatabase
        } elseif ($choice -eq "3") {
            Invoke-AgentScan
        } elseif ($choice -eq "4") {
            Start-AgentApiServer
        } elseif ($choice -eq "5") {
            Export-AgentBoDataset
        } elseif ($choice -eq "6") {
            Show-AgentConfig
        } elseif ($choice -eq "7") {
            Clear-AgentLlmConfig
        } elseif ($choice -eq "8") {
            return
        } elseif ($choice -eq "9") {
            Start-AgentChat
        } elseif ($choice -eq "10") {
            Invoke-AgentKnowledgeBootstrapMenu
        } elseif ($choice -eq "11") {
            Invoke-AgentReviewQueueMenu
        } elseif ($choice -eq "12") {
            Start-EquipmentSetupWizard
        } elseif ($choice -eq "13") {
            Show-ActiveEquipmentProfile
        } elseif ($choice -eq "14") {
            Select-ActiveEquipmentProfile
        } elseif ($choice -eq "15") {
            Update-ActiveEquipmentProfileWizard
        } else {
            Write-Host "无效选择，请重新输入。"
        }
    }
}

Export-ModuleMember -Function Show-AgentBanner, Show-ProviderMenu, Show-ModelMenu, Show-DeepSeekModelMenu, Read-AgentApiKey, Set-AgentEnvironment, Set-AgentDeepSeekEnvironment, Initialize-AgentDeepSeekConfig, Use-AgentSavedDeepSeekConfig, Save-AgentLlmConfig, Load-AgentLlmConfig, Clear-AgentLlmConfig, Show-AgentMainMenu, Initialize-AgentDatabase, Update-AgentDatabaseSchemaQuiet, Invoke-AgentScan, Start-AgentApiServer, Start-AgentApiServerBackground, Export-AgentBoDataset, Initialize-AgentLocalBootstrap, Test-AgentPythonEnvironment, Test-AgentApiServer, Test-AgentRuntimeIdentity, Test-AgentLlmConnection, Update-AgentLlmConfigFromChat, New-AgentChatSession, Send-AgentChatMessage, Send-AgentChatStream, Get-AgentStreamMode, Set-AgentStreamMode, Get-AgentDisplayMode, Set-AgentDisplayMode, Show-AgentProgressBar, Show-AgentThinkingStatus, Show-AgentTraceEvent, Show-AgentRuntimeIdentity, Show-AgentWorkflowState, Show-AgentExecutionTrace, Show-AgentToolCall, Show-AgentEvidenceSummary, Show-AgentTrialDecision, Show-AgentApprovalCard, Show-AgentLatencyWaterfall, Show-AgentTrialChoice, Show-AgentKnowledgeUsageCard, Get-AgentMachineBounds, Start-EquipmentSetupWizard, Update-ActiveEquipmentProfileWizard, Show-ActiveEquipmentProfile, Select-ActiveEquipmentProfile, Show-AgentReviewTasks, Show-AgentReviewTaskDetail, Invoke-AgentKnowledgeBootstrapMenu, Invoke-AgentReviewQueueMenu, Start-AgentChat, Start-AgentDeepSeekAutoLaunch, Save-AgentSecret, Get-AgentSecret, Remove-AgentSecret
