from __future__ import annotations

import json

from ultrafast_shared.config.loader import load_config


def test_config_precedence_default_local_environment_cli(isolated_root, monkeypatch):
    (isolated_root / "configs/default.yaml").write_text(
        "app:\n  name: default\ndemo:\n  enabled: false\ndatabase:\n  url: sqlite:///data/default.db\n",
        encoding="utf-8",
    )
    (isolated_root / "configs/local.yaml").write_text(
        "app:\n  name: local\ndemo:\n  enabled: true\n",
        encoding="utf-8",
    )
    monkeypatch.setenv(
        "ULTRAFAST_CONFIG_OVERRIDES",
        json.dumps({"app": {"name": "environment"}, "agent": {"max_retries": 2}}),
    )
    monkeypatch.setenv("ULTRAFAST_DATABASE_URL", "sqlite:///data/environment.db")

    config = load_config(cli_overrides={"app": {"name": "cli"}})

    assert config["app"]["name"] == "cli"
    assert config["demo"]["enabled"] is True
    assert config["agent"]["max_retries"] == 2
    assert config["database"]["url"] == "sqlite:///data/environment.db"


def test_config_environment_override_must_be_mapping(isolated_root, monkeypatch):
    monkeypatch.setenv("ULTRAFAST_CONFIG_OVERRIDES", "[]")

    try:
        load_config()
    except ValueError as exc:
        assert "JSON object" in str(exc)
    else:
        raise AssertionError("invalid override should fail")


def test_config_cache_invalidates_on_file_revision_and_returns_isolated_copy(
    isolated_root,
):
    path = isolated_root / "configs/default.yaml"
    path.write_text("app:\n  name: first\n", encoding="utf-8")
    first = load_config()
    first["app"]["name"] = "mutated-by-caller"
    assert load_config()["app"]["name"] == "first"

    path.write_text("app:\n  name: second-longer\n", encoding="utf-8")
    assert load_config()["app"]["name"] == "second-longer"
