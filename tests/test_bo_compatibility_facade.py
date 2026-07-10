from __future__ import annotations

from src import bo_compatibility


def test_legacy_cli_uses_compatibility_facade():
    assert bo_compatibility._SERVICE.__class__.__name__ == "LegacyCommandCompatibilityService"
    assert callable(bo_compatibility.init_task)
    assert callable(bo_compatibility.recommend_parameters)
