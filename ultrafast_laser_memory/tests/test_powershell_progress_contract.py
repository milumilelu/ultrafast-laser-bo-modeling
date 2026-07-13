from __future__ import annotations

import subprocess


def test_powershell_progress_functions_exist(project_root):
    module = project_root / "scripts" / "powershell" / "AgentTui.psm1"
    script = (
        f"Import-Module -Force '{module}'; "
        "Get-Command Show-AgentProgressBar,Show-AgentThinkingStatus,Show-AgentTraceEvent,Show-AgentWorkflowState,Show-AgentExecutionTrace,Show-AgentToolCall,Show-AgentEvidenceSummary,Show-AgentTrialDecision,Show-AgentApprovalCard,Show-AgentLatencyWaterfall | "
        "Select-Object -ExpandProperty Name"
    )

    result = subprocess.run(["pwsh", "-NoProfile", "-Command", script], capture_output=True, text=True, check=True)

    assert "Show-AgentProgressBar" in result.stdout
    assert "Show-AgentThinkingStatus" in result.stdout
    assert "Show-AgentTraceEvent" in result.stdout
    assert "Show-AgentWorkflowState" in result.stdout
    assert "Show-AgentExecutionTrace" in result.stdout
    assert "Show-AgentToolCall" in result.stdout
    assert "Show-AgentEvidenceSummary" in result.stdout
    assert "Show-AgentTrialDecision" in result.stdout
    assert "Show-AgentApprovalCard" in result.stdout
    assert "Show-AgentLatencyWaterfall" in result.stdout


def test_powershell_equipment_range_and_waiting_prompt_exist(project_root):
    module_text = (project_root / "scripts" / "powershell" / "AgentTui.psm1").read_text(encoding="utf-8")

    assert "Read-AgentNullableRange" in module_text
    assert "脉宽范围fs（示例：500,8000）" in module_text
    assert "重复频率范围kHz（示例：50,1000）" in module_text
    assert "扫描速度范围mm/s（示例：10,3000）" in module_text
    assert "加工助手执行中" in module_text


def test_powershell_agent_trace_mode_contract(project_root):
    module_text = (project_root / "scripts" / "powershell" / "AgentTui.psm1").read_text(encoding="utf-8")

    assert "/mode normal|research|debug" in module_text
    assert "agent_trace" in module_text
    assert '$script:AgentDisplayMode = "debug"' in module_text
    assert "duration_ms" in module_text
    assert "cache_hit" in module_text
    assert "Show-AgentTrialChoice" in module_text
    assert "Show-AgentKnowledgeUsageCard" in module_text
    assert "加工助手执行中" in module_text
    assert "加工助手思考中" not in module_text
    assert "Set-AgentStreamMode -Enabled $true" in module_text
    assert "Debug + full public trace" in module_text


def test_powershell_llm_reconfigure_command_restarts_and_validates_backend(project_root):
    module_text = (project_root / "scripts" / "powershell" / "AgentTui.psm1").read_text(encoding="utf-8")

    assert '"/llm config", "/llm reconfigure"' in module_text
    assert "Initialize-AgentDeepSeekConfig -Reconfigure" in module_text
    assert "Start-AgentApiServerBackground -PreferredPort $port -MaxPort $port -RestartExisting" in module_text
    assert "Test-AgentLlmConnection -BaseUrl $newBaseUrl" in module_text
