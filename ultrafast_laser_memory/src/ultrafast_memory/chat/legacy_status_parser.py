from __future__ import annotations

import re
from typing import Any


def legacy_non_process_status_snapshot(message: str) -> dict[str, Any]:
    """Compatibility-only status hints for legacy non-process workflows.

    This output is never merged into process_task_spec.
    """
    text = message.lower()
    task: dict[str, Any] = {}
    if "diamond" in text or "金刚石" in text:
        task["material"] = "diamond"
    if "cfrp" in text or "碳纤维" in text or "t300" in text:
        task["material"] = "CFRP_T300" if "t300" in text else "CFRP"
    if "切割" in text or "cutting" in text:
        task["process_type"] = "cutting"
        task["component_type"] = "workpiece"
    if "crl" in text or "透镜" in text or "x-ray" in text:
        task["component_type"] = "CRL"
    if "飞秒" in text or "femtosecond" in text or "超快" in text:
        task["process_type"] = "femtosecond_laser_micromachining"
    roughness = re.search(r"ra\s*[<小于]*\s*(\d+(?:\.\d+)?)\s*(nm|um|µm)?", message, re.I)
    if roughness:
        task["roughness_target"] = f"Ra < {roughness.group(1)} {roughness.group(2) or 'nm'}"
    if "单晶" in message or "single crystal" in text:
        task["diamond_type"] = "single_crystal"
    if any(marker in text for marker in ("1030", "515", "800", "fs", "khz", "w")):
        task["laser_system"] = "mentioned"
    if "后处理" in message:
        task["post_processing_allowed"] = "mentioned"
    return task
