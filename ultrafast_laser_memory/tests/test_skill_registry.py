from ultrafast_agent.skills import get_default_skill_registry


def test_skill_registry_has_exactly_six_descriptors():
    registry = get_default_skill_registry()
    assert len(registry.list()) == 6
    assert all(item.guidance and item.recommended_tools for item in registry.list())
    assert not any(hasattr(item, "allowed_tools") for item in registry.list())
