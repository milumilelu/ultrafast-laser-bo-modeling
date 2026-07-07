from __future__ import annotations

from ultrafast_memory.core.file_type import detect_file_type


def test_detect_file_types(project_root):
    examples = project_root / "examples"
    assert detect_file_type(examples / "sample_recipe.json") == "json_recipe"
    assert detect_file_type(examples / "sample_run.log") == "machine_log"
    assert detect_file_type(examples / "sample_measurement.csv") == "measurement_csv"
    assert detect_file_type(examples / "sample_note.txt") == "operator_note"
