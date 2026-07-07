from __future__ import annotations

from ultrafast_memory.parsers.measurement_csv_parser import MeasurementCsvParser
from ultrafast_memory.parsers.operator_note_parser import OperatorNoteParser
from ultrafast_memory.parsers.recipe_json_parser import RecipeJsonParser
from ultrafast_memory.parsers.simple_log_parser import SimpleLogParser


def test_parsers(project_root):
    examples = project_root / "examples"
    recipe = RecipeJsonParser().parse(str(examples / "sample_recipe.json"))
    assert recipe["tasks"][0]["material"] == "diamond"

    run = SimpleLogParser().parse(str(examples / "sample_run.log"))
    assert run["runs"][0]["run_id"] == "run_023"

    measurement = MeasurementCsvParser().parse(str(examples / "sample_measurement.csv"))
    assert measurement["measurements"][0]["metric_name"] == "Ra"
    assert measurement["measurements"][0]["metric_value"] == 520
    assert measurement["measurements"][0]["metric_unit"] == "nm"

    note = OperatorNoteParser().parse(str(examples / "sample_note.txt"))
    claim = note["experience_candidates"][0]["extracted_claim"]
    assert "surface_blackening" in claim
    assert "edge_chipping" in claim
