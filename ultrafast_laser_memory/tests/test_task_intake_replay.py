from __future__ import annotations

from ultrafast_agent.task_intake.replay import evaluate_replay, load_replay_cases


def test_deterministic_replay_corpus(project_root):
    cases = load_replay_cases(project_root / "tests/replay/process_task_cases.jsonl")
    report = evaluate_replay(cases)

    assert len(cases) == 50
    assert report["passed"] == 50
    assert report["failed"] == 0
    assert report["field_precision"] == 1
    assert report["field_recall"] == 1
    assert report["critical_field_accuracy"] == 1
    assert report["schema_valid_rate"] == 1
    assert report["hallucinated_field_rate"] == 0
    assert report["existing_field_overwrite_rate"] == 0
    assert report["workflow_progression_accuracy"] == 1


def test_replay_corpus_covers_required_categories(project_root):
    cases = load_replay_cases(project_root / "tests/replay/process_task_cases.jsonl")
    tags = {tag for case in cases for tag in case.tags}
    assert {
        "real_bug",
        "expression_variant",
        "correction",
        "ambiguity",
        "attack",
        "multi_turn_state",
    } <= tags
