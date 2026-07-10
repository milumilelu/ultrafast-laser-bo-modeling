from __future__ import annotations


def detect_evidence_gap(
    question: str,
    task_spec: dict,
    internal_hits: list[dict] | None = None,
) -> dict:
    hits = internal_hits or []
    material = (task_spec.get("material") or "").lower()
    process_type = (task_spec.get("process_type") or "").lower()
    component_type = (task_spec.get("component_type") or "").lower()

    if not hits:
        score = 0.0
    else:
        score = min(1.0, 0.25 + 0.25 * min(len(hits), 3))
        if len(hits) < 2:
            score = min(score, 0.4)
        for hit in hits:
            hit_material = str(hit.get("material") or "").lower()
            hit_process = str(hit.get("process_type") or "").lower()
            if material and hit_material and material not in hit_material and hit_material not in material:
                score -= 0.2
            if process_type and hit_process and process_type not in hit_process and hit_process not in process_type:
                score -= 0.2
            if not hit.get("source_id"):
                score -= 0.1
        score = max(0.0, min(1.0, score))

    missing = _missing_evidence(question, material, process_type, component_type, hits)
    if score < 0.6:
        action = "web_bootstrap"
        reason = "内部知识库无足够匹配证据。"
    elif score < 0.8:
        action = "ask_user_clarification"
        reason = "内部证据部分可用，但仍缺少关键条件或来源。"
    else:
        action = "answer_from_internal"
        reason = "内部证据数量、来源和任务匹配度满足回答要求。"

    return {
        "has_sufficient_internal_evidence": score >= 0.8,
        "evidence_score": round(score, 3),
        "missing_evidence": missing,
        "recommended_action": action,
        "reason": reason,
    }


def _missing_evidence(question: str, material: str, process_type: str, component_type: str, hits: list[dict]) -> list[str]:
    missing: list[str] = []
    text = f"{question} {material} {process_type} {component_type}".lower()
    if "diamond" in text or "金刚石" in text:
        if "crl" in text or "x-ray" in text or "透镜" in text:
            missing.append("diamond_CRL_literature")
    if "parameter" in text or "参数" in text or "bo" in text:
        missing.extend(["machine_specific_parameters", "process_parameter_ranges"])
    if "damage" in text or "损伤" in text or "graphitization" in text or "石墨" in text:
        missing.append("damage_mechanism_evidence")
    if len(hits) < 2:
        missing.append("internal_experiment_cases")
    if not missing:
        missing.append("source_traceability")
    return list(dict.fromkeys(missing))
