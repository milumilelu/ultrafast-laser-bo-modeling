from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from ultrafast_domain.process import ProcessPlan
from ultrafast_domain.trial import TrialPlan
from ultrafast_memory.agent_runtime.main_agent_loop import run_main_agent_turn
from ultrafast_memory.agent_runtime.planner import MainAgentPlanner
from ultrafast_memory.agent_runtime.task_intake import prepare_task_context
from ultrafast_memory.apps.api.main import app


def _session() -> str:
    return TestClient(app).post("/chat/sessions", json={}).json()["session_id"]


def _plans(diameter_mm: float = 1.0) -> tuple[dict, dict]:
    process_plan = {
        "objective": f"在 3 mm 氧化锆陶瓷上加工直径 {diameter_mm:g} mm 通孔并建立稳定去除窗口",
        "strategy": {
            "mode": "layered_deep_hole_ablation",
            "debris_management": "每层后停留并吹除碎屑",
        },
        "operations": [
            {"name": "定位"},
            {"name": "轮廓与螺旋扫描", "pattern": "contour_plus_spiral"},
            {"name": "按深度推进", "layer_step_um": 10, "focus_step_um": 50},
        ],
        "fixed_conditions": {
            "wavelength_nm": 1030,
            "pulse_width_fs": 300,
            "spot_diameter_um": 5,
        },
        "controllable_variables": [
            {"name": "laser_power_W", "role": "process_setpoint"},
            {"name": "frequency_kHz", "role": "process_setpoint", "selected_for_trial": False},
            {"name": "scan_speed_mm_s", "role": "process_setpoint", "selected_for_trial": False},
            {"name": "layer_step_um", "role": "strategy_parameter"},
        ],
        "evaluation_plan": [
            {"metric": "through_status", "method": "透光或背面显微检查"},
            {"metric": "entrance_exit_diameter", "method": "显微测量"},
            {"metric": "taper", "method": "截面或三维形貌"},
            {"metric": "edge_chipping", "method": "入口与出口显微检查"},
        ],
        "risks": [
            {"name": "氧化锆脆性崩边"}, {"name": "深孔排屑不足"},
            {"name": "锥度增大"}, {"name": "热累积裂纹"},
        ],
        "assumptions": ["第一轮目标是建立稳定去除窗口，不作为正式加工参数"],
        "adaptation_guidance": [
            {"observation": "去除不足", "adjustment": "小幅提高单脉冲能量或降低扫描速度"},
            {"observation": "崩边增加", "adjustment": "降低单脉冲能量并减小层步距"},
            {"observation": "锥度过大", "adjustment": "增加焦点推进频次并校正轮廓补偿"},
        ],
    }
    parameter = {
        "name": "laser_power_W",
        "value": 1.1,
        "unit": "W",
        "role": "process_setpoint",
        "source_type": "llm_exploration",
        "source_refs": [],
        "authority_level": "exploratory",
        "uncertainty": {},
        "validated": False,
        "allowed_for_trial": True,
        "allowed_for_formal_process": False,
        "allowed_for_bo_training": False,
    }
    layer_parameter = {
        "name": "layer_step_um",
        "value": 10,
        "unit": "um",
        "role": "strategy_parameter",
        "source_type": "llm_exploration",
        "source_refs": [],
        "authority_level": "exploratory",
        "uncertainty": {},
        "validated": False,
        "allowed_for_trial": True,
        "allowed_for_formal_process": False,
        "allowed_for_bo_training": False,
    }
    trial_plan = {
        "objective": "验证稳定去除、排屑和贯穿趋势",
        "hypothesis": "受控分层去除可降低脆性损伤并改善深孔排屑",
        "setup": {
            "material": "氧化锆陶瓷", "thickness_mm": 3,
            "diameter_mm": diameter_mm, "sample_count": 3,
            "fixed_conditions": process_plan["fixed_conditions"],
        },
        "strategy": process_plan["strategy"],
        "parameter_candidates": [{"candidate_id": "trial-1", "parameters": {
            "laser_power_W": parameter,
            "layer_step_um": layer_parameter,
        }}],
        "evaluation_plan": process_plan["evaluation_plan"],
        "success_criteria": [
            {"metric": "through_status", "operator": "==", "value": True},
            {"metric": "edge_chipping", "operator": "no_worse_than", "value": "agreed_limit"},
        ],
        "stop_conditions": [
            {"condition": "出现贯穿裂纹"}, {"condition": "设备报警"},
            {"condition": "崩边连续扩大"}, {"condition": "热累积异常"},
        ],
        "adaptation_guidance": process_plan["adaptation_guidance"],
        "provenance": [{"source_type": "llm_exploration", "authority_level": "exploratory"}],
        "warnings": ["本轮参数未经验证，只允许试切，不得直接用于正式加工或 BO 训练。"],
    }
    return process_plan, trial_plan


class CompletePlanLLM:
    provider = "test"
    model = "complete-plan"

    def __init__(self, diameter_mm: float = 1.0) -> None:
        self.diameter_mm = diameter_mm
        self.calls = 0

    def chat(self, messages, **kwargs):
        self.calls += 1
        process_plan, trial_plan = _plans(self.diameter_mm)
        if self.calls == 1:
            action = {
                "action": "call_tool",
                "decision_summary": "验证 Main Agent 选择的第一轮探索参数",
                "tool_name": "recommend_process_parameters",
                "arguments": {
                    "task_context": {"material": "氧化锆陶瓷"},
                    "process_plan": process_plan,
                    "variables": ["laser_power_W", "layer_step_um"],
                    "equipment_context": {
                        "fixed_conditions": process_plan["fixed_conditions"],
                        "tunable_capabilities": {
                            "laser_power_W": {"min": 0.1, "max": 5.0, "unit": "W"},
                        },
                    },
                    "evidence_summary": "测试探索假设",
                    "allow_llm_fallback": True,
                    "candidate": {"laser_power_W": 1.1, "layer_step_um": 10},
                },
            }
            return {
                "provider": self.provider, "model": self.model,
                "content": json.dumps(action, ensure_ascii=False),
            }
        content = {
            "action": "final_answer",
            "decision_summary": "已形成完整的第一轮试切方案",
            "message": (
                "任务理解：3 mm 厚氧化锆陶瓷，直径通孔。\n"
                "设备固定条件：1030 nm，300 fs，5 μm 光斑。\n"
                "加工策略：分层轮廓与螺旋扫描，焦点随深度推进并逐层排屑。\n"
                "第一轮试切：3 个样本，检测贯穿、入口/出口孔径、锥度、崩边和圆度。\n"
                "下一轮：去除不足则提高单脉冲能量或降速；崩边增加则降低能量并减小层步距。\n"
                "警告：参数未经验证，只允许第一轮试切，不得直接用于正式加工。"
            ),
            "context_updates": {"process_plan": process_plan, "trial_plan": trial_plan},
        }
        return {"provider": self.provider, "model": self.model, "content": json.dumps(content, ensure_ascii=False)}


def test_task_understanding_single_pass() -> None:
    preparation = prepare_task_context(
        "在3mm厚的氧化锆陶瓷上加工一个直径1mm的通孔",
        {"task": {}},
    )

    task = preparation.context_updates["task"]
    assert task["material"]["name"] == "氧化锆陶瓷"
    assert task["workpiece"]["thickness_mm"] == 3
    assert task["process_intent"] == "through_hole_drilling"
    assert task["geometry"]["feature_type"] == "through_hole"
    assert task["geometry"]["dimensions"]["diameter_mm"] == 1


def test_no_repeated_question() -> None:
    context = {
        "task": {
            "material": {"name": "氧化锆陶瓷"},
            "workpiece": {"thickness_mm": 3},
            "process_intent": "through_hole_drilling",
            "geometry": {"feature_type": "through_hole", "dimensions": {"diameter_mm": 2}},
        }
    }

    preparation = prepare_task_context("通孔直径改成1mm", context)

    assert preparation.context_updates["task"] == {"geometry": {
        "dimensions": {"diameter_mm": 1.0},
        "description": "直径 1 mm 通孔",
        "through": True,
    }}
    assert not preparation.blocking_fields


def test_blocking_question_only() -> None:
    preparation = prepare_task_context(
        "在铝基碳化硅板材上加工5×5mm矩形槽",
        {"task": {}},
    )

    assert preparation.blocking_fields == ["geometry.depth_mm"]


def test_reminder_is_not_question(isolated_root) -> None:
    result = run_main_agent_turn(
        session_id=_session(),
        message="在3mm厚的氧化锆陶瓷上加工一个直径1mm的通孔",
        message_id="complete-plan",
        client=CompletePlanLLM(),
    )

    assert result["final_action"]["action"] == "respond"
    assert "参数未经验证" in result["content"]
    assert "是否接受" not in result["content"]
    assert "？" not in result["content"]


def test_trial_plan_complete(isolated_root) -> None:
    result = run_main_agent_turn(
        session_id=_session(),
        message="在3mm厚的氧化锆陶瓷上加工一个直径1mm的通孔",
        message_id="trial-plan",
        client=CompletePlanLLM(),
    )
    process = ProcessPlan.model_validate(result["working_context"]["process_plan"])
    trial = TrialPlan.model_validate(result["working_context"]["trial_plan"])

    assert process.strategy and process.operations and process.evaluation_plan
    assert trial.objective
    assert trial.strategy
    assert trial.setup
    assert trial.parameter_candidates
    assert trial.evaluation_plan
    assert trial.success_criteria
    assert trial.adaptation_guidance
    assert trial.warnings


def test_open_plan_models_do_not_encode_deep_hole_defaults() -> None:
    cases = [
        ("CFRP 切割", {"type": "contour_cutting", "pass_mode": "multi_pass"}, ["kerf_width", "delamination"]),
        ("表面微结构", {"type": "surface_patterning", "pattern": "cross_hatch"}, ["period", "depth", "uniformity"]),
        ("薄膜选择性去除", {"type": "selective_film_removal"}, ["residual_rate", "substrate_damage"]),
        ("金刚石 CRL", {"type": "freeform_optical_surface"}, ["curvature_radius", "form_error", "roughness"]),
    ]
    generic_parameter = {
        "name": "task_specific_variable", "value": 1, "unit": None,
        "role": "process_setpoint", "source_type": "test_hypothesis",
        "source_refs": [], "authority_level": "exploratory", "uncertainty": {},
        "validated": False, "allowed_for_trial": True,
        "allowed_for_formal_process": False, "allowed_for_bo_training": False,
    }

    for objective, strategy, metrics in cases:
        process = ProcessPlan.model_validate({
            "objective": objective,
            "strategy": strategy,
            "operations": [{"name": "task_specific_operation"}],
            "fixed_conditions": {},
            "controllable_variables": [{"name": "task_specific_variable"}],
            "evaluation_plan": [{"metric": metric} for metric in metrics],
            "risks": [{"name": "task_specific_risk"}],
            "assumptions": [],
        })
        trial = TrialPlan.model_validate({
            "objective": f"验证：{objective}",
            "strategy": strategy,
            "parameter_candidates": [{"parameters": {"task_specific_variable": generic_parameter}}],
            "evaluation_plan": [{"metric": metric} for metric in metrics],
            "success_criteria": [{"metric": metrics[0], "operator": "within_target"}],
        })

        serialized = json.dumps({
            "process": process.model_dump(mode="json"),
            "trial": trial.model_dump(mode="json"),
        }, ensure_ascii=False)
        assert "layer_step" not in serialized
        assert "focus_step" not in serialized
        assert "through_status" not in serialized


def test_open_plan_models_normalize_equivalent_generic_shapes() -> None:
    parameter = {
        "name": "scan_speed_mm_s", "value": 40, "unit": "mm/s",
        "role": "process_setpoint", "source_type": "llm_exploration",
        "source_refs": [], "authority_level": "exploratory", "uncertainty": {},
        "validated": False, "allowed_for_trial": True,
        "allowed_for_formal_process": False, "allowed_for_bo_training": False,
    }
    process = ProcessPlan.model_validate({
        "objective": "generic task",
        "strategy": "task-selected strategy",
        "operations": ["task-selected operation"],
        "controllable_variables": ["scan_speed_mm_s"],
        "evaluation_plan": {"measurements": ["task-selected metric"]},
        "risks": ["task-selected risk"],
    })
    trial = TrialPlan.model_validate({
        "objective": "generic trial",
        "strategy": "task-selected strategy",
        "parameter_candidates": {"parameters": {"scan_speed_mm_s": parameter}},
        "evaluation_plan": {"metric": "task-selected metric"},
        "success_criteria": {"metric": "task-selected metric", "operator": "within_target"},
        "stop_conditions": "unsafe observation",
        "adaptation_guidance": "adapt from observed result",
        "warnings": "trial only",
    })

    assert process.strategy == {"description": "task-selected strategy"}
    assert process.evaluation_plan == [{"measurements": ["task-selected metric"]}]
    assert trial.strategy == {"description": "task-selected strategy"}
    assert len(trial.parameter_candidates) == 1
    assert trial.stop_conditions == [{"description": "unsafe observation"}]


def test_latest_parameter_truth_keeps_process_and_strategy_parameters() -> None:
    process_parameter = {
        "name": "laser_power_W", "value": 1.1, "role": "process_setpoint",
    }
    strategy_parameter = {
        "name": "scan_pattern", "value": "cross_hatch", "role": "strategy_parameter",
    }

    truth = MainAgentPlanner._latest_parameter_truth([{"data": {
        "process_parameters": {"laser_power_W": process_parameter},
        "strategy_parameters": {"scan_pattern": strategy_parameter},
    }}])

    assert truth == {
        "laser_power_W": process_parameter,
        "scan_pattern": strategy_parameter,
    }


def test_plan_semantics_rejects_tunable_as_strategy_and_unproven_assigned_control() -> None:
    process = ProcessPlan.model_validate({
        "objective": "generic",
        "strategy": {"type": "task_selected"},
        "operations": [{"name": "operation"}],
        "controllable_variables": [
            {"name": "pulse_width_fs", "role": "strategy_parameter", "fixed": 500},
            {"name": "scan_pattern", "role": "strategy_parameter", "fixed": "cross_hatch"},
        ],
        "evaluation_plan": [{"metric": "task_specific"}],
    })
    equipment = {
        "fixed_conditions": {"wavelength_nm": 1030},
        "tunable_capabilities": {"pulse_width_fs": {"min": 500, "max": 8000}},
    }

    with pytest.raises(ValueError, match="equipment_tunable_must_be_process_setpoint"):
        MainAgentPlanner._validate_process_parameter_semantics(
            process, {"scan_pattern": {"role": "strategy_parameter"}}, equipment,
        )

    process.controllable_variables[0]["role"] = "process_setpoint"
    with pytest.raises(ValueError, match="controllable_variable_requires_parameter_tool_truth"):
        MainAgentPlanner._validate_process_parameter_semantics(
            process, {"pulse_width_fs": {"role": "process_setpoint"}}, equipment,
        )


def test_plan_semantics_allows_tool_validated_setpoint_held_fixed_for_trial() -> None:
    process = ProcessPlan.model_validate({
        "objective": "generic",
        "strategy": {"type": "task_selected"},
        "operations": [{"name": "operation"}],
        "fixed_conditions": {"pulse_width_fs": 500},
        "controllable_variables": [{"name": "pulse_width_fs", "role": "process_setpoint"}],
        "evaluation_plan": [{"metric": "task_specific"}],
    })
    truth = {"pulse_width_fs": {
        "name": "pulse_width_fs", "value": 500, "role": "process_setpoint",
    }}
    equipment = {
        "fixed_conditions": {"wavelength_nm": 1030},
        "tunable_capabilities": {"pulse_width_fs": {"min": 500, "max": 8000}},
    }

    MainAgentPlanner._validate_process_parameter_semantics(process, truth, equipment)


def test_completed_answer_removes_nonblocking_confirmation_invitation() -> None:
    normalized = MainAgentPlanner._normalize_provider_action({
        "action": "final_answer",
        "message": "方案已完成。\n下一步：确认后可按 TrialPlan 执行首轮试切。",
    }, "task")

    assert "确认后" not in normalized["message"]
    assert "按 TrialPlan 执行首轮试切" in normalized["message"]


def test_planning_cannot_overwrite_established_task_facts_without_user_correction() -> None:
    raw = {
        "action": "call_tool",
        "context_updates": {"task": {
            "material": {"name": "rewritten-material"},
            "geometry": "rewritten-geometry",
            "assumptions": ["new explicit assumption"],
        }},
    }
    context = {"task": {
        "material": {"name": "established-material"},
        "geometry": {"feature_type": "open-feature"},
    }}

    protected = MainAgentPlanner._protect_established_task_facts(raw, context, "开始规划加工任务")
    corrected = MainAgentPlanner._protect_established_task_facts(raw, context, "材料改为新材料")

    assert protected["context_updates"]["task"] == {
        "assumptions": ["new explicit assumption"],
    }
    assert corrected["context_updates"]["task"]["material"]["name"] == "rewritten-material"


def test_final_plan_message_must_be_self_contained() -> None:
    incomplete = (
        "任务和策略已形成。第一轮试切参数仅供验证，未经审核。"
        "详细方案见上下文中的 process_plan 和 trial_plan。"
    )
    complete = (
        "任务采用任务相关的加工策略与路线。第一轮试切参数均未经验证，来源为探索假设。"
        "检测与评价包括目标指标和成功判据；出现异常时按停止条件处理。"
        "下一轮根据测量结果调整选定变量并继续迭代。风险与警告已列出，正式加工前必须验证。"
    )

    with pytest.raises(ValueError, match="self_contained"):
        MainAgentPlanner._validate_self_contained_plan_message(incomplete)
    MainAgentPlanner._validate_self_contained_plan_message(complete)
