from __future__ import annotations

from ultrafast_agent.runtime import ToolExecutor
from ultrafast_memory.agent_runtime.tool_registry import build_main_agent_tool_registry
from ultrafast_memory.db.init_db import init_database
from ultrafast_memory.equipment.schemas import EquipmentProfileCreate
from ultrafast_memory.equipment.service import create_equipment_profile


def _equipment_profile() -> None:
    create_equipment_profile(
        EquipmentProfileCreate(
            profile_name="Semantic fs laser",
            laser_source={
                "wavelength_nm": 1030,
                "pulse_width_fixed_fs": 300,
                "average_power_min_W": 0.1,
                "average_power_max_W": 5.0,
                "frequency_min_kHz": 2,
                "frequency_max_kHz": 200,
            },
            optical_setup={"spot_diameter_um": 5},
            motion_system={"scan_speed_min_mm_s": 1, "scan_speed_max_mm_s": 200},
            process_capability={"layer_step_min_um": 1, "layer_step_max_um": 20},
            set_active=True,
        )
    )


def _equipment_output() -> dict:
    execution = ToolExecutor(build_main_agent_tool_registry()).execute(
        "get_equipment_context", {}, {"session_id": "semantic"},
    )
    assert execution.status == "succeeded"
    return execution.output


def test_equipment_parameter_separation(isolated_root) -> None:
    init_database()
    _equipment_profile()

    equipment = _equipment_output()

    assert "machine_bounds" not in equipment
    assert equipment["fixed_conditions"] == {
        "wavelength_nm": 1030,
        "pulse_width_fs": 300,
        "spot_diameter_um": 5,
    }
    assert equipment["tunable_capabilities"]["laser_power_W"] == {
        "min": 0.1, "max": 5.0, "unit": "W", "role": "equipment_tunable",
    }


def test_exploratory_not_machine_midpoint_and_only_uses_plan_variables(isolated_root) -> None:
    init_database()
    _equipment_profile()
    equipment = _equipment_output()
    payload = {
        "task_context": {"material": {"name": "氧化锆陶瓷"}},
        "process_plan": {
            "objective": "建立稳定去除窗口",
            "controllable_variables": [
                {"name": "laser_power_W"}, {"name": "scan_speed_mm_s"},
            ],
        },
        "variables": ["laser_power_W", "scan_speed_mm_s"],
        "equipment_context": equipment,
        "evidence_summary": {"bo": "insufficient", "rag": "insufficient"},
        "intended_use": "trial",
        "candidate": {"laser_power_W": 1.2, "scan_speed_mm_s": 40},
    }

    execution = ToolExecutor(build_main_agent_tool_registry()).execute(
        "propose_exploratory_parameters", payload, {"session_id": "semantic"},
    )
    result = execution.output

    assert result["status"] == "exploratory"
    assert set(result["process_parameters"]) == {"laser_power_W", "scan_speed_mm_s"}
    assert "frequency_kHz" not in result["process_parameters"]
    assert result["process_parameters"]["laser_power_W"]["value"] != 2.55
    assert result["process_parameters"]["scan_speed_mm_s"]["value"] != 100.5


def test_parameter_provenance_and_trial_only_authority(isolated_root) -> None:
    init_database()
    _equipment_profile()
    equipment = _equipment_output()
    payload = {
        "task_context": {"material": {"name": "氧化锆陶瓷"}},
        "process_plan": {"controllable_variables": [{"name": "laser_power_W"}]},
        "variables": ["laser_power_W"],
        "equipment_context": equipment,
        "evidence_summary": {},
        "intended_use": "trial",
        "candidate": {"laser_power_W": 1.1},
    }

    result = ToolExecutor(build_main_agent_tool_registry()).execute(
        "propose_exploratory_parameters", payload, {"session_id": "semantic"},
    ).output
    parameter = result["process_parameters"]["laser_power_W"]

    assert parameter["role"] == "process_setpoint"
    assert parameter["source_type"] == "llm_exploration"
    assert parameter["authority_level"] == "exploratory"
    assert parameter["validated"] is False
    assert parameter["allowed_for_trial"] is True
    assert parameter["allowed_for_formal_process"] is False
    assert parameter["allowed_for_bo_training"] is False
    assert result["fixed_equipment_conditions"]["wavelength_nm"] == 1030
    assert "wavelength_nm" not in result["process_parameters"]


def test_exploratory_rejects_non_object_candidate_without_crashing(isolated_root) -> None:
    init_database()
    _equipment_profile()
    equipment = _equipment_output()
    payload = {
        "task_context": {"material": {"name": "generic"}},
        "process_plan": {"controllable_variables": [{"name": "laser_power_W"}]},
        "variables": ["laser_power_W"],
        "equipment_context": equipment,
        "evidence_summary": {},
        "intended_use": "trial",
        "candidate": [{"name": "laser_power_W", "value": 1.1}],
    }

    result = ToolExecutor(build_main_agent_tool_registry()).execute(
        "propose_exploratory_parameters", payload, {"session_id": "semantic"},
    ).output

    assert result["status"] == "validation_error"
    assert result["received_type"] == "list"


def test_exploratory_accepts_explicit_variables_in_open_nested_plan(isolated_root) -> None:
    init_database()
    _equipment_profile()
    equipment = _equipment_output()
    payload = {
        "task_context": {"material": {"name": "generic"}},
        "process_plan": {
            "operations": [{
                "name": "task-selected operation",
                "controllable_variables": [{"name": "laser_power_W"}],
            }],
            "selected_exploratory_variables": ["laser_power_W"],
        },
        "variables": ["laser_power_W"],
        "equipment_context": equipment,
        "evidence_summary": {},
        "intended_use": "trial",
        "candidate": {"laser_power_W": 1.1},
    }

    result = ToolExecutor(build_main_agent_tool_registry()).execute(
        "propose_exploratory_parameters", payload, {"session_id": "semantic"},
    ).output

    assert result["status"] == "exploratory"
    assert result["process_parameters"]["laser_power_W"]["value"] == 1.1


def test_exploratory_accepts_explicit_value_metadata_and_flat_fixed_equipment(isolated_root) -> None:
    init_database()
    _equipment_profile()
    payload = {
        "task_context": {"material": {"name": "generic"}},
        "process_plan": {"controllable_variables": [{"name": "laser_power_W"}]},
        "variables": ["laser_power_W"],
        "equipment_context": {
            "wavelength_nm": 1030,
            "spot_diameter_um": 5,
            "tunable_capabilities": {
                "laser_power_W": {"min": 0.1, "max": 5.0},
            },
        },
        "evidence_summary": {},
        "intended_use": "trial",
        "candidate": {
            "laser_power_W": {
                "name": "laser_power_W", "value": 1.1,
                "source_type": "main_agent_proposal",
            },
        },
    }

    result = ToolExecutor(build_main_agent_tool_registry()).execute(
        "propose_exploratory_parameters", payload, {"session_id": "semantic"},
    ).output

    assert result["status"] == "exploratory"
    assert result["fixed_equipment_conditions"] == {
        "wavelength_nm": 1030, "spot_diameter_um": 5,
    }
    assert result["process_parameters"]["laser_power_W"]["source_type"] == "llm_exploration"


def test_exploratory_accepts_wrapped_parameters_without_deriving_values(isolated_root) -> None:
    init_database()
    _equipment_profile()
    equipment = _equipment_output()
    payload = {
        "task_context": {"material": {"name": "generic"}},
        "process_plan": {"controllable_variables": [{"name": "laser_power_W"}]},
        "variables": ["laser_power_W"],
        "equipment_context": equipment,
        "evidence_summary": {},
        "intended_use": "trial",
        "candidate": {"parameters": {"laser_power_W": {"value": 1.1, "unit": "W"}}},
    }

    result = ToolExecutor(build_main_agent_tool_registry()).execute(
        "propose_exploratory_parameters", payload, {"session_id": "semantic"},
    ).output

    assert result["status"] == "exploratory"
    assert result["process_parameters"]["laser_power_W"]["value"] == 1.1


def test_exploratory_separates_explicit_strategy_parameters(isolated_root) -> None:
    init_database()
    _equipment_profile()
    equipment = _equipment_output()
    payload = {
        "task_context": {"material": {"name": "generic"}},
        "process_plan": {"controllable_variables": [
            {"name": "laser_power_W", "role": "process_setpoint"},
            {"name": "scan_pattern", "role": "strategy_parameter"},
        ]},
        "variables": ["laser_power_W", "scan_pattern"],
        "equipment_context": equipment,
        "evidence_summary": {},
        "intended_use": "trial",
        "candidate": {"parameters": {
            "laser_power_W": {"value": 1.1, "unit": "W"},
            "scan_pattern": {"value": "cross_hatch"},
        }},
    }

    result = ToolExecutor(build_main_agent_tool_registry()).execute(
        "propose_exploratory_parameters", payload, {"session_id": "semantic"},
    ).output

    assert result["status"] == "exploratory"
    assert set(result["process_parameters"]) == {"laser_power_W"}
    assert result["strategy_parameters"]["scan_pattern"]["value"] == "cross_hatch"
    assert result["strategy_parameters"]["scan_pattern"]["role"] == "strategy_parameter"


def test_exploratory_does_not_infer_strategy_role_from_missing_equipment_bound(isolated_root) -> None:
    init_database()
    _equipment_profile()
    equipment = _equipment_output()
    payload = {
        "task_context": {"material": {"name": "generic"}},
        "process_plan": {"controllable_variables": [{"name": "scan_pattern"}]},
        "variables": ["scan_pattern"],
        "equipment_context": equipment,
        "evidence_summary": {},
        "intended_use": "trial",
        "candidate": {"parameters": {"scan_pattern": {"value": "cross_hatch"}}},
    }

    result = ToolExecutor(build_main_agent_tool_registry()).execute(
        "propose_exploratory_parameters", payload, {"session_id": "semantic"},
    ).output

    assert result["status"] == "validation_error"
    assert "role=strategy_parameter" in result["summary"]


def test_exploratory_normalizes_unambiguous_trial_and_role_aliases(isolated_root) -> None:
    init_database()
    _equipment_profile()
    equipment = _equipment_output()
    payload = {
        "task_context": {"material": {"name": "generic"}},
        "process_plan": {"controllable_variables": [
            {"name": "laser_power_W", "role": "工艺设定值"},
            {"name": "scan_pattern", "role": "策略参数"},
        ]},
        "variables": ["laser_power_W", "scan_pattern"],
        "equipment_context": equipment,
        "evidence_summary": {},
        "intended_use": "first_trial",
        "candidate": {"parameters": {
            "laser_power_W": {"value": 1.1},
            "scan_pattern": {"value": "cross_hatch"},
        }},
    }

    result = ToolExecutor(build_main_agent_tool_registry()).execute(
        "propose_exploratory_parameters", payload, {"session_id": "semantic"},
    ).output

    assert result["status"] == "exploratory"
    assert result["process_parameters"]["laser_power_W"]["role"] == "process_setpoint"
    assert result["strategy_parameters"]["scan_pattern"]["role"] == "strategy_parameter"


def test_exploratory_rejects_unvalidated_tunable_fixed_condition(isolated_root) -> None:
    init_database()
    _equipment_profile()
    equipment = _equipment_output()
    payload = {
        "task_context": {"material": {"name": "generic"}},
        "process_plan": {
            "fixed_conditions": {"frequency_kHz": 2},
            "controllable_variables": [{"name": "laser_power_W"}],
        },
        "variables": ["laser_power_W"],
        "equipment_context": equipment,
        "evidence_summary": {},
        "intended_use": "trial",
        "candidate": {"laser_power_W": 1.1},
    }

    result = ToolExecutor(build_main_agent_tool_registry()).execute(
        "propose_exploratory_parameters", payload, {"session_id": "semantic"},
    ).output

    assert result["status"] == "validation_error"
    assert result["invalid_variables"] == ["frequency_kHz"]
    assert "process_setpoint" in result["summary"]
