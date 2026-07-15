from __future__ import annotations

import re
from collections import Counter
from statistics import median
from typing import Any

from ultrafast_memory.equipment.bounds import PARAMETER_UNITS
from ultrafast_memory.rag.metadata_filter import enforce_purpose


PARAMETER_SPECS: dict[str, dict[str, Any]] = {
    "laser_power_W": {
        "aliases": ["laser power", "average power", "激光功率", "平均功率", "功率"],
        "units": {"w": 1.0, "mw": 0.001},
        "unit": "W",
    },
    "frequency_kHz": {
        "aliases": ["repetition rate", "frequency", "重复频率", "脉冲频率", "频率"],
        "units": {"khz": 1.0, "mhz": 1000.0, "hz": 0.001},
        "unit": "kHz",
    },
    "pulse_width_fs": {
        "aliases": ["pulse width", "pulse duration", "脉宽", "脉冲宽度"],
        "units": {"fs": 1.0, "ps": 1000.0},
        "unit": "fs",
    },
    "scan_speed_mm_s": {
        "aliases": ["scan speed", "scanning speed", "扫描速度"],
        "units": {"mm/s": 1.0, "m/s": 1000.0},
        "unit": "mm/s",
    },
    "hatch_spacing_um": {
        "aliases": ["hatch spacing", "line spacing", "填充间距", "扫描间距"],
        "units": {"um": 1.0, "μm": 1.0, "µm": 1.0, "mm": 1000.0},
        "unit": "um",
    },
    "layer_step_um": {
        "aliases": ["layer step", "layer thickness", "层步距", "分层厚度"],
        "units": {"um": 1.0, "μm": 1.0, "µm": 1.0, "mm": 1000.0},
        "unit": "um",
    },
    "passes": {
        "aliases": ["passes", "pass count", "扫描次数", "加工遍数"],
        "units": {"": 1.0},
        "unit": None,
    },
}


def recommend_from_evidence(
    variables: list[str],
    variable_roles: dict[str, str],
    hits: list[dict[str, Any]],
    equipment_bounds: dict[str, tuple[float, float]],
) -> dict[str, Any]:
    observations: dict[str, list[dict[str, Any]]] = {name: [] for name in variables}
    for hit in hits:
        if not enforce_purpose(hit, "parameter_recommendation"):
            continue
        for name in variables:
            observations[name].extend(_extract_hit_observations(hit, name))

    process: dict[str, float | int | str] = {}
    strategy: dict[str, float | int | str] = {}
    details: dict[str, dict[str, Any]] = {}
    missing: list[str] = []
    for name in variables:
        values = observations[name]
        if not values:
            missing.append(name)
            continue
        numeric = [float(item["value"]) for item in values if isinstance(item.get("value"), (int, float))]
        strings = [str(item["value"]) for item in values if isinstance(item.get("value"), str)]
        if numeric:
            chosen: float | int | str = float(median(numeric))
            if name == "passes":
                chosen = int(round(chosen))
        elif strings:
            chosen = Counter(strings).most_common(1)[0][0]
        else:
            missing.append(name)
            continue

        role = variable_roles.get(name) or "process_setpoint"
        clipped = False
        if role == "process_setpoint":
            bound = equipment_bounds.get(name)
            if bound is None or not isinstance(chosen, (int, float)):
                missing.append(name)
                continue
            lower, upper = float(bound[0]), float(bound[1])
            if not lower <= float(chosen) <= upper:
                missing.append(name)
                details[name] = {
                    "unit": PARAMETER_UNITS.get(name),
                    "source_refs": list(dict.fromkeys(
                        str(item["source_ref"]) for item in values
                    )),
                    "authority_level": "literature_prior",
                    "uncertainty": {
                        "basis": "reviewed_rag_evidence",
                        "observation_count": len(values),
                        "observed_value": chosen,
                        "equipment_bounds": [lower, upper],
                        "rejection_reason": "outside_equipment_bounds",
                    },
                }
                continue
            clipped = False
            chosen = int(round(float(chosen))) if name == "passes" else float(chosen)
            process[name] = chosen
        elif role == "strategy_parameter":
            strategy[name] = chosen
        else:
            missing.append(name)
            continue

        refs = list(dict.fromkeys(str(item["source_ref"]) for item in values))
        observed_numeric = [
            float(item["value"]) for item in values if isinstance(item.get("value"), (int, float))
        ]
        details[name] = {
            "unit": next((item.get("unit") for item in values if item.get("unit")), None)
            or PARAMETER_UNITS.get(name),
            "source_refs": refs,
            "authority_level": "literature_prior",
            "uncertainty": {
                "basis": "reviewed_rag_evidence",
                "observation_count": len(values),
                "observed_min": min(observed_numeric) if observed_numeric else None,
                "observed_max": max(observed_numeric) if observed_numeric else None,
                "equipment_clipped": clipped,
            },
        }
    return {
        "process_parameters": process,
        "strategy_parameters": strategy,
        "parameter_details": details,
        "missing_variables": sorted(set(missing)),
        "observation_counts": {name: len(values) for name, values in observations.items()},
    }


def _extract_hit_observations(hit: dict[str, Any], name: str) -> list[dict[str, Any]]:
    source_ref = _source_ref(hit)
    metadata = hit.get("metadata") if isinstance(hit.get("metadata"), dict) else {}
    output = _structured_observations(metadata.get("parameter"), name, source_ref)
    output.extend(_text_observations(str(hit.get("content") or ""), name, source_ref))
    unique: list[dict[str, Any]] = []
    seen: set[tuple[str, str | None]] = set()
    for item in output:
        key = (str(item.get("value")), item.get("unit"))
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return unique


def _structured_observations(value: Any, name: str, source_ref: str) -> list[dict[str, Any]]:
    candidate: Any = None
    if isinstance(value, dict):
        if name in value:
            candidate = value[name]
        elif value.get("name") == name:
            candidate = value
    elif isinstance(value, list):
        candidate = next(
            (item for item in value if isinstance(item, dict) and item.get("name") == name),
            None,
        )
    if candidate is None:
        return []
    if isinstance(candidate, (int, float, str)):
        parsed = _coerce_value(candidate, None, name)
        return [{**parsed, "source_ref": source_ref}] if parsed else []
    if not isinstance(candidate, dict):
        return []
    unit = candidate.get("unit")
    direct = candidate.get("value", candidate.get("recommended", candidate.get("setpoint")))
    if direct is not None:
        parsed = _coerce_value(direct, unit, name)
        return [{**parsed, "source_ref": source_ref}] if parsed else []
    lower = candidate.get("lower", candidate.get("min", candidate.get("lower_bound")))
    upper = candidate.get("upper", candidate.get("max", candidate.get("upper_bound")))
    if isinstance(lower, (int, float)) and isinstance(upper, (int, float)):
        parsed = _coerce_value((float(lower) + float(upper)) / 2, unit, name)
        return [{**parsed, "source_ref": source_ref}] if parsed else []
    return []


def _text_observations(text: str, name: str, source_ref: str) -> list[dict[str, Any]]:
    spec = PARAMETER_SPECS.get(name)
    if not spec:
        return []
    alias = "|".join(re.escape(item) for item in spec["aliases"])
    unit = "|".join(re.escape(item) for item in spec["units"] if item)
    number = r"[-+]?\d+(?:\.\d+)?"
    suffix = rf"\s*(?P<unit>{unit})" if unit else ""
    pattern = re.compile(
        rf"(?:{alias})\s*(?:[:=：为]|is|of)?\s*(?P<value>{number}){suffix}",
        re.IGNORECASE,
    )
    output = []
    for match in pattern.finditer(text):
        parsed = _coerce_value(match.group("value"), match.groupdict().get("unit"), name)
        if parsed:
            output.append({**parsed, "source_ref": source_ref})
    return output


def _coerce_value(value: Any, unit: Any, name: str) -> dict[str, Any] | None:
    spec = PARAMETER_SPECS.get(name)
    if isinstance(value, str):
        stripped = value.strip()
        try:
            value = float(stripped)
        except ValueError:
            return {"value": stripped, "unit": str(unit) if unit else None} if stripped else None
    if not isinstance(value, (int, float)):
        return None
    if spec:
        normalized_unit = str(unit or spec.get("unit") or "").strip().lower()
        factors = {str(key).lower(): factor for key, factor in spec["units"].items()}
        if normalized_unit not in factors:
            return None
        return {
            "value": float(value) * float(factors[normalized_unit]),
            "unit": spec.get("unit"),
        }
    return {"value": float(value), "unit": str(unit) if unit else None}


def _source_ref(hit: dict[str, Any]) -> str:
    paper = str(hit.get("paper_id") or "unknown")
    chunk = str(hit.get("chunk_id") or "unknown")
    page = hit.get("page_start")
    return f"{paper}:{chunk}" + (f":p.{page}" if page else "")
