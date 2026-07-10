from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "ultrafast_laser_memory"
CONTRACTS = PROJECT / "skills/contracts.yaml"
OUTPUT = ROOT / "docs/skills/skill_inventory.md"


DECISIONS = {
    "task_intake": "refactor",
    "skill_router": "convert_to_tool",
    "process_file_ingestion": "refactor",
    "bo_dataset_governance": "convert_to_domain_rule",
    "bo_recommendation": "refactor",
    "rag_literature_retrieval": "merge",
    "experience_memory_update": "merge",
    "report_generation": "refactor",
    "crl_task_planning": "deprecate",
}

DUPLICATES = {
    "skill_router": "Routing belongs to Agent Runtime route planning.",
    "bo_dataset_governance": "Eligibility rules duplicate validation/BO application services.",
    "rag_literature_retrieval": "Alias duplicates rag_evidence_retrieval.",
    "experience_memory_update": "Alias overlaps knowledge_candidate_generation.",
    "crl_task_planning": "Task intake, evidence, route, trial, quality, and report logic duplicate generic skills.",
}

CALLERS = {
    "crl_task_planning": "legacy rule router; optical_component_task_workflow compatibility",
    "rag_literature_retrieval": "legacy rule router/chat; alias to rag_evidence_retrieval",
    "bo_recommendation": "legacy rule router; complex_process_task",
    "task_intake": "legacy rule router; all formal workflows",
    "report_generation": "legacy rule router; all formal workflows",
    "knowledge_bootstrap": "legacy chat permission flow",
    "expert_review": "legacy knowledge review flow",
}


def usage_counts() -> dict[str, int]:
    path = PROJECT / "data/ultrafast_memory.db"
    if not path.exists():
        return {}
    try:
        with sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True) as connection:
            return {
                str(name): int(count)
                for name, count in connection.execute(
                    "SELECT selected_skill, COUNT(*) FROM chat_skill_trace GROUP BY selected_skill"
                ).fetchall()
                if name
            }
    except sqlite3.Error:
        return {}


def tests_for(name: str) -> list[str]:
    needles = {name, name.replace("_", "-")}
    found = []
    for path in sorted((PROJECT / "tests").glob("test_*.py")):
        text = path.read_text(encoding="utf-8", errors="replace")
        if any(needle in text for needle in needles):
            found.append(path.name)
    return found


def legacy_path(name: str) -> str:
    path = ROOT / "agent_skills" / name.replace("_", "-") / "SKILL.md"
    return path.relative_to(ROOT).as_posix() if path.exists() else "—"


def compact(values) -> str:
    return ", ".join(map(str, values)) if values else "—"


def main() -> int:
    payload = yaml.safe_load(CONTRACTS.read_text(encoding="utf-8"))
    skills = sorted(payload["skills"], key=lambda item: item["name"])
    usage = usage_counts()
    lines = [
        "# Skill inventory",
        "",
        f"Contract source: `ultrafast_laser_memory/skills/contracts.yaml` ({len(skills)} validated contracts).",
        "",
        "Usage counts are observed rows in the current local `chat_skill_trace`; zero means no persisted call was observed, not proof that the capability is unused.",
        "",
        "| Name | Version | Legacy path | Callers | Called tools | Inputs → outputs | Side effects | Timeout/cache | Tests | Usage | Decision |",
        "|---|---|---|---|---|---|---|---|---|---:|---|",
    ]
    for skill in skills:
        name = skill["name"]
        tests = tests_for(name)
        decision = DECISIONS.get(name, "keep")
        lines.append(
            "| {name} | {version} | {legacy} | {callers} | {tools} | {inputs} → {outputs} | {effects} | {timeout} ms / {cache} | {tests} | {usage} | {decision} |".format(
                name=name,
                version=skill["version"],
                legacy=legacy_path(name),
                callers=CALLERS.get(name, "formal workflow composition"),
                tools=compact(skill["allowed_tools"]),
                inputs=compact(skill["inputs"]),
                outputs=compact(skill["outputs"]),
                effects=compact(skill["side_effects"]),
                timeout=skill["timeout_ms"],
                cache=skill["cache_policy"],
                tests=compact(tests),
                usage=usage.get(name, 0),
                decision=decision,
            )
        )
    lines.extend(
        [
            "",
            "## Duplicate and domain-specific logic",
            "",
            "| Skill | Duplicate logic | Domain-specific logic |",
            "|---|---|---|",
        ]
    )
    for name in sorted(DECISIONS):
        domain = (
            "Dual-paraboloid geometry, wavefront/focal-spot quality, and shallow paraboloid trial template are now in the CRL domain pack."
            if name == "crl_task_planning"
            else "None; scenario differences belong in domain packs."
        )
        lines.append(f"| {name} | {DUPLICATES.get(name, 'No material duplication found.')} | {domain} |")
    lines.extend(
        [
            "",
            "## Contract enforcement",
            "",
            "Every contract declares name, version, purpose, inputs, outputs, preconditions, side effects, allowed/forbidden tools, failure modes, timeout, cache policy, and emitted events. Runtime validation rejects duplicate names, invalid versions, non-positive timeouts, allow/deny conflicts, and direct business-skill access to SQLite/raw SQL.",
            "",
        ]
    )
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"output": str(OUTPUT), "skills": len(skills), "usage": usage}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
