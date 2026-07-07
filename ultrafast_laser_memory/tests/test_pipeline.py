from __future__ import annotations

import csv

from ultrafast_memory.bo.dataset_builder import export_bo_dataset
from ultrafast_memory.db.init_db import init_database
from ultrafast_memory.db.session import get_connection
from ultrafast_memory.ingestion.pipeline import scan_directory


def test_pipeline_end_to_end(isolated_root, isolated_examples):
    init_database()
    result = scan_directory(isolated_examples)
    assert result["imported"] == 4
    assert result["errors"] == []

    with get_connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM raw_artifact").fetchone()[0] == 4
        assert conn.execute("SELECT COUNT(*) FROM process_task").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM process_recipe").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM process_run").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM measurement_record").fetchone()[0] == 2
        assert conn.execute("SELECT COUNT(*) FROM experience_candidate").fetchone()[0] == 1

    exported = export_bo_dataset()
    assert exported["sample_count"] == 1
    export_path = isolated_root / "data" / "exports" / "bo_training_samples.csv"
    with export_path.open("r", encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert rows[0]["run_id"] == "run_023"
    assert rows[0]["material"] == "diamond"
    assert rows[0]["process_type"] == "surface_micromachining"
    assert rows[0]["laser_power_W"] == "5.0"
    assert rows[0]["frequency_kHz"] == "200.0"
    assert rows[0]["scan_speed_mm_s"] == "500.0"
    assert rows[0]["Ra_nm"] == "520.0"
    assert rows[0]["form_error_um"] == "8.2"
