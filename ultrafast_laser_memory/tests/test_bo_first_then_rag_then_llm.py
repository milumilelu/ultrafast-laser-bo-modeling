from ultrafast_memory.agent_runtime import tool_registry


def test_bo_first_then_rag_then_llm(monkeypatch):
    order = []

    def bo(payload, context):
        order.append("bo")
        return {"status": "insufficient_data", "process_parameters": {},
                "allowed_for_trial": False, "data_support": {
                    "support_status": "insufficient", "model_mode": "blocked",
                }}

    def rag(payload, context):
        order.append("rag")
        return {"status": "insufficient_data", "process_parameters": {}}

    def exploratory(payload, context):
        order.append("llm")
        return {"status": "exploratory", "process_parameters": {"laser_power_W": 1.0},
                "allowed_for_trial": True, "allowed_for_formal_process": False}

    monkeypatch.setattr(tool_registry, "_recommend_bo", bo)
    monkeypatch.setattr(tool_registry, "_recommend_rag", rag)
    monkeypatch.setattr(tool_registry, "_exploratory", exploratory)
    result = tool_registry._recommend_process_parameters(
        {"allow_llm_fallback": True, "candidate": {"laser_power_W": 1.0}},
        {},
    )

    assert order == ["bo", "rag", "llm"]
    assert result["selected_source"] == "llm_exploration"

