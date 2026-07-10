from __future__ import annotations


def extract_claims_from_source(source: dict, task_spec: dict) -> list[dict]:
    text = f"{source.get('title') or ''} {source.get('raw_snippet') or source.get('snippet') or ''}".lower()
    if "diamond" in text and ("x-ray" in text or "lens" in text or "crl" in text):
        return [
            {
                "claim": "飞秒激光微加工已有用于单晶金刚石 X-ray refractive lens / CRL 制造的报道。",
                "material": "diamond",
                "process_type": "femtosecond_laser_micromachining",
                "component_type": "X-ray_CRL",
                "parameter": {},
                "condition": {},
                "usable_for": ["feasibility_assessment", "literature_background"],
                "not_usable_for": ["direct_parameter_recommendation", "BO_training"],
                "evidence_type": "web_evidence",
                "confidence": 0.65,
            }
        ]
    claim = source.get("raw_snippet") or source.get("snippet") or source.get("title") or ""
    return [
        {
            "claim": claim or "外部来源内容不足，无法抽取可靠结论。",
            "material": task_spec.get("material"),
            "process_type": task_spec.get("process_type"),
            "component_type": task_spec.get("component_type"),
            "parameter": {},
            "condition": {},
            "usable_for": ["literature_background"] if claim else [],
            "not_usable_for": ["direct_parameter_recommendation", "BO_training"],
            "evidence_type": "web_evidence",
            "confidence": 0.35 if claim else 0.1,
            "status": "needs_more_evidence" if not claim else "candidate",
        }
    ]
