from __future__ import annotations


DIAMOND_CRL_QUERIES = [
    "diamond compound refractive lens femtosecond laser micromachining",
    "single crystal diamond X-ray refractive lens laser fabrication",
    "femtosecond laser diamond graphitization surface roughness",
    "diamond CRL polishing surface roughness X-ray optics",
    "diamond laser micromachining surface roughness Ra",
]


def generate_search_queries(task_spec: dict, question: str | None, query_intent: str) -> list[str]:
    material = str(task_spec.get("material") or "").strip() or "material"
    process_type = str(task_spec.get("process_type") or "").strip() or "micromachining"
    component_type = str(task_spec.get("component_type") or "").strip()
    haystack = f"{material} {process_type} {component_type} {question or ''}".lower()
    if ("diamond" in haystack or "金刚石" in haystack) and ("crl" in haystack or "透镜" in haystack or "x-ray" in haystack):
        return DIAMOND_CRL_QUERIES.copy()
    return [
        f"{material} ultrafast laser {process_type} surface roughness",
        f"{material} femtosecond laser micromachining parameters",
        f"{material} laser ablation damage mechanism",
        f"{material} ultrafast laser process optimization",
    ]
