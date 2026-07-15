from ultrafast_memory.agent_runtime.tool_registry import _exploratory


def test_llm_fallback_simple_trial_only():
    result = _exploratory(
        {
            "process_plan": {"controllable_variables": [
                {"name": "laser_power_W", "role": "process_setpoint"},
            ]},
            "variables": ["laser_power_W"],
            "candidate": {"laser_power_W": 1.0},
            "intended_use": "trial",
        },
        {"equipment_snapshot": {
            "fixed_conditions": {},
            "tunable_capabilities": {
                "laser_power_W": {"min": 0.1, "max": 5.0, "unit": "W"},
            },
        }},
    )

    assert result["allowed_for_trial"] is True
    assert result["allowed_for_formal_process"] is False
    assert result["allowed_for_bo_training"] is False
    assert result["recommended_use"] == ["trial"]

