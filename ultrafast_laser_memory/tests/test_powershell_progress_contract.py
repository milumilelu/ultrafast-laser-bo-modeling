from __future__ import annotations

import subprocess


def test_powershell_progress_functions_exist(project_root):
    module = project_root / "scripts" / "powershell" / "AgentTui.psm1"
    script = (
        f"Import-Module -Force '{module}'; "
        "Get-Command Show-AgentProgressBar,Show-AgentThinkingStatus,Show-AgentTraceEvent,Show-AgentWorkflowState | "
        "Select-Object -ExpandProperty Name"
    )

    result = subprocess.run(["pwsh", "-NoProfile", "-Command", script], capture_output=True, text=True, check=True)

    assert "Show-AgentProgressBar" in result.stdout
    assert "Show-AgentThinkingStatus" in result.stdout
    assert "Show-AgentTraceEvent" in result.stdout
    assert "Show-AgentWorkflowState" in result.stdout


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
    assert "加工助手执行中" in module_text
    assert "加工助手思考中" not in module_text
    assert "Set-AgentStreamMode -Enabled $true" in module_text
    assert "已启用实时流式执行轨迹" in module_text
