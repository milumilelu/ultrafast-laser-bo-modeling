from __future__ import annotations

import csv
from pathlib import Path

from ultrafast_memory.core.ids import stable_id
from ultrafast_memory.normalization.units import normalize_measurement
from ultrafast_memory.parsers.base import BaseParser, empty_result


class MeasurementCsvParser(BaseParser):
    name = "measurement_csv_parser"
    version = "1.0.0"

    def parse(self, file_path: str) -> dict:
        result = empty_result()
        with Path(file_path).open("r", encoding="utf-8-sig", newline="") as fh:
            for row in csv.DictReader(fh):
                raw_value = row.get("metric_value")
                raw_unit = row.get("metric_unit")
                value, unit, valid = normalize_measurement(
                    float(raw_value), raw_unit or "", row.get("metric_name") or ""
                )
                result["measurements"].append(
                    {
                        "measurement_id": stable_id("measurement", row.get("run_id"), row.get("metric_name"), raw_value, row.get("measured_at")),
                        "run_id": row.get("run_id"),
                        "metric_name": row.get("metric_name"),
                        "metric_value": value,
                        "metric_unit": unit,
                        "raw_value": raw_value,
                        "raw_unit": raw_unit,
                        "measurement_method": row.get("measurement_method"),
                        "instrument_id": row.get("instrument_id"),
                        "region_of_interest": row.get("region_of_interest"),
                        "measured_at": row.get("measured_at"),
                        "valid_flag": int(valid),
                    }
                )
        return result
