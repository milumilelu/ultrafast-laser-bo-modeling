from ultrafast_agent.skills import get_default_skill_registry


def test_skill_registry_has_exactly_six_descriptors():
    registry = get_default_skill_registry()
    assert len(registry.list()) == 6
    assert all(item.guidance and item.recommended_tools for item in registry.list())
    assert all(item.method and item.required_considerations for item in registry.list())
    assert all(item.output_expectations and item.prohibitions for item in registry.list())
    assert all(item.failure_handling for item in registry.list())
    assert not any(hasattr(item, "allowed_tools") for item in registry.list())


def test_loaded_skill_exposes_the_complete_professional_protocol():
    loaded = get_default_skill_registry().load("parameter_recommendation")

    assert loaded["purpose"]
    assert loaded["when_useful"]
    assert loaded["method"]
    assert loaded["required_considerations"]
    assert loaded["output_expectations"]
    assert loaded["prohibitions"]
    assert loaded["failure_handling"]
    assert any("边界中点" in item for item in loaded["prohibitions"])
