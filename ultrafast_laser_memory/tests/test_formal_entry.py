from __future__ import annotations

from ultrafast_memory.app.main import main


def test_pyproject_declares_unique_formal_entry(project_root):
    text = (project_root / "pyproject.toml").read_text(encoding="utf-8")
    assert 'ultrafast = "ultrafast_memory.app.main:main"' in text


def test_formal_entry_doctor_and_legacy_launcher_help(isolated_root, capsys):
    assert main(["doctor"]) == 0
    output = capsys.readouterr().out
    assert '"status": "healthy"' in output

    assert main(["--help"]) == 0


def test_formal_demo_flag_is_supported(isolated_root, monkeypatch, capsys):
    monkeypatch.setattr(
        "ultrafast_memory.app.main.DemoService.run_tgv",
        lambda self, approve_review=False: {"status": "waiting_review"},
    )

    assert main(["--demo"]) == 0
    assert '"status": "waiting_review"' in capsys.readouterr().out
