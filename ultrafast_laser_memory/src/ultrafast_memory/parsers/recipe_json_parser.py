from __future__ import annotations

import json
from pathlib import Path

from ultrafast_memory.core.ids import stable_id
from ultrafast_memory.core.time_utils import utc_now_iso
from ultrafast_memory.parsers.base import BaseParser, empty_result


class RecipeJsonParser(BaseParser):
    name = "recipe_json_parser"
    version = "1.0.0"

    def parse(self, file_path: str) -> dict:
        result = empty_result()
        with Path(file_path).open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        task_id = data.get("task_id") or stable_id("task", file_path, data)
        if "task_id" not in data:
            result["errors"].append({"message": "missing task_id; generated deterministic task_id"})
        laser = data.get("laser", {})
        scan = data.get("scan", {})
        result["tasks"].append(
            {
                "task_id": task_id,
                "component_type": data.get("component_type"),
                "material": data.get("material"),
                "material_grade": data.get("material_grade"),
                "geometry_json": json.dumps(data.get("geometry", {}), ensure_ascii=False),
                "target_json": json.dumps(data.get("target", {}), ensure_ascii=False),
                "priority_mode": data.get("priority_mode"),
                "created_by": data.get("created_by"),
                "created_at": data.get("created_at") or utc_now_iso(),
                "status": data.get("status") or "planned",
            }
        )
        recipe_id = data.get("recipe_id") or f"recipe_{task_id}"
        result["recipes"].append(
            {
                "recipe_id": recipe_id,
                "task_id": task_id,
                "process_type": data.get("process_type"),
                "laser_wavelength_nm": laser.get("wavelength_nm"),
                "pulse_width_fs": laser.get("pulse_width_fs"),
                "laser_power_W": laser.get("power_W"),
                "frequency_kHz": laser.get("frequency_kHz"),
                "scan_speed_mm_s": scan.get("scan_speed_mm_s"),
                "passes": scan.get("passes"),
                "hatch_spacing_um": scan.get("hatch_spacing_um"),
                "layer_step_um": scan.get("layer_step_um"),
                "focus_offset_um": scan.get("focus_offset_um"),
                "fill_pattern": scan.get("fill_pattern"),
                "path_strategy": scan.get("path_strategy"),
                "parameters_json": json.dumps(data, ensure_ascii=False),
                "created_at": data.get("created_at") or utc_now_iso(),
            }
        )
        return result
