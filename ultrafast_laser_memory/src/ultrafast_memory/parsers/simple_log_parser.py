from __future__ import annotations

from datetime import datetime
from pathlib import Path

from ultrafast_memory.parsers.base import BaseParser, empty_result


def _parse_key_values(file_path: str) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for line in Path(file_path).read_text(encoding="utf-8").splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        parsed[key.strip()] = value.strip()
    return parsed


def _duration_seconds(start: str | None, end: str | None) -> float | None:
    if not start or not end:
        return None
    try:
        fmt = "%Y-%m-%d %H:%M:%S"
        return (datetime.strptime(end, fmt) - datetime.strptime(start, fmt)).total_seconds()
    except ValueError:
        return None


class SimpleLogParser(BaseParser):
    name = "simple_log_parser"
    version = "1.0.0"

    def parse(self, file_path: str) -> dict:
        result = empty_result()
        data = _parse_key_values(file_path)
        alarm_count = int(data.get("alarm_count") or 0)
        status = data.get("status")
        result["runs"].append(
            {
                "run_id": data.get("run_id"),
                "task_id": data.get("task_id"),
                "recipe_id": data.get("recipe_id"),
                "machine_id": data.get("machine_id"),
                "operator_id": data.get("operator_id"),
                "start_time": data.get("start_time"),
                "end_time": data.get("end_time"),
                "duration_s": _duration_seconds(data.get("start_time"), data.get("end_time")),
                "run_status": status,
                "alarm_count": alarm_count,
                "abnormal_flag": int(status != "completed" or alarm_count > 0),
                "abnormal_summary": data.get("abnormal_summary"),
            }
        )
        return result
