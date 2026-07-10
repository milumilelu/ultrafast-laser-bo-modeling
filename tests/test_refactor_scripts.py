from pathlib import Path


def test_required_refactor_scripts_exist_and_preserve_safety_contract():
    root = Path(__file__).resolve().parents[1]
    backup = (root / "scripts/backup_before_refactor.ps1").read_text(encoding="utf-8")
    rollback = (root / "scripts/rollback_refactor.ps1").read_text(encoding="utf-8")
    replay = (root / "scripts/demo_replay.ps1").read_text(encoding="utf-8")

    assert "backup_repository_state.py" in backup
    assert "ConfirmRollback" in rollback
    assert "logical_snapshot_matches" in rollback
    assert "git reset --hard" not in rollback
    assert "ULTRAFAST_LLM_PROVIDER" in replay and '"mock"' in replay
    assert "--approve-review" in replay
