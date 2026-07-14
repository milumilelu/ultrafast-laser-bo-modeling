from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml


REQUIRED_FIELDS = {
    "name",
    "version",
    "description",
    "when_to_use",
    "guidance",
    "recommended_tools",
}


@dataclass(frozen=True, slots=True)
class SkillDescriptor:
    """Planner guidance loaded on demand; a Skill is not an execution gate."""

    name: str
    version: str
    description: str
    when_to_use: tuple[str, ...]
    guidance: tuple[str, ...]
    recommended_tools: tuple[str, ...]

    @property
    def purpose(self) -> str:
        """Read-compatible alias for older diagnostics clients."""
        return self.description

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "SkillDescriptor":
        missing = REQUIRED_FIELDS - set(value)
        if missing:
            raise ValueError(f"skill descriptor missing fields: {sorted(missing)}")
        name = str(value["name"])
        version = str(value["version"])
        if not re.fullmatch(r"[a-z][a-z0-9_]*", name):
            raise ValueError(f"invalid skill name: {name}")
        if not re.fullmatch(r"\d+\.\d+\.\d+(?:-[a-z0-9.]+)?", version):
            raise ValueError(f"invalid skill version: {name}={version}")
        recommended = tuple(dict.fromkeys(map(str, value["recommended_tools"])))
        return cls(
            name=name,
            version=version,
            description=str(value["description"]),
            when_to_use=tuple(map(str, value["when_to_use"])),
            guidance=tuple(map(str, value["guidance"])),
            recommended_tools=recommended,
        )


# Temporary read aliases are resolved at the boundary and never appear as Skills.
LEGACY_SKILL_ALIASES = {
    "task_intake": "task_understanding",
    "task_normalization": "task_understanding",
    "geometry_interpretation": "task_understanding",
    "rag_evidence_retrieval": "evidence_research",
    "rag_literature_retrieval": "evidence_research",
    "historical_case_retrieval": "evidence_research",
    "process_route_planning": "process_planning",
    "hole_drilling_planning": "process_planning",
    "bo_recommendation": "parameter_recommendation",
    "knowledge_candidate_generation": "result_learning",
    "report_generation": "result_learning",
}


class SkillRegistry:
    def __init__(self, descriptors: list[SkillDescriptor]):
        names = [descriptor.name for descriptor in descriptors]
        duplicates = sorted({name for name in names if names.count(name) > 1})
        if duplicates:
            raise ValueError(f"duplicate skill descriptors: {duplicates}")
        self._descriptors = {descriptor.name: descriptor for descriptor in descriptors}

    def resolve_name(self, name: str) -> str:
        return LEGACY_SKILL_ALIASES.get(name, name)

    def get(self, name: str) -> SkillDescriptor:
        resolved = self.resolve_name(name)
        try:
            return self._descriptors[resolved]
        except KeyError as exc:
            raise KeyError(f"skill not registered: {name}") from exc

    def list(self) -> list[SkillDescriptor]:
        return [self._descriptors[name] for name in sorted(self._descriptors)]

    def catalog_for_agent(self) -> list[dict[str, Any]]:
        """Small discovery catalog; full guidance is returned only by load_skill."""
        return [
            {
                "name": item.name,
                "description": item.description,
                "when_to_use": list(item.when_to_use),
            }
            for item in self.list()
        ]

    def load(self, name: str) -> dict[str, Any]:
        item = self.get(name)
        return {
            "name": item.name,
            "version": item.version,
            "description": item.description,
            "guidance": list(item.guidance),
            "recommended_tools": list(item.recommended_tools),
        }


# Read compatibility for imports; the model is intentionally a descriptor now.
SkillContract = SkillDescriptor


def load_skill_contracts(path: str | Path) -> SkillRegistry:
    source = Path(path)
    with source.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or {}
    values = payload.get("skills")
    if not isinstance(values, list):
        raise ValueError("skill descriptor file must contain a skills list")
    return SkillRegistry([SkillDescriptor.from_dict(value) for value in values])


def default_contract_path() -> Path:
    return Path(__file__).resolve().parents[3] / "skills/contracts.yaml"


@lru_cache(maxsize=1)
def get_default_skill_registry() -> SkillRegistry:
    return load_skill_contracts(default_contract_path())
