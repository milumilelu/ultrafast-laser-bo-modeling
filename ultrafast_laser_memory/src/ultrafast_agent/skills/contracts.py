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
    "purpose",
    "when_useful",
    "prompt",
    "process_guidance",
}


@dataclass(frozen=True, slots=True)
class SkillDescriptor:
    """Prompt and workflow guidance; never a permission or execution gate."""

    name: str
    version: str
    purpose: str
    when_useful: tuple[str, ...]
    prompt: str
    process_guidance: tuple[str, ...]
    tool_hints: tuple[str, ...]

    @property
    def description(self) -> str:
        return self.purpose

    @property
    def when_to_use(self) -> tuple[str, ...]:
        return self.when_useful

    @property
    def guidance(self) -> tuple[str, ...]:
        return (self.prompt, *self.process_guidance)

    @property
    def recommended_tools(self) -> tuple[str, ...]:
        """Compatibility alias; these are prompt hints and grant no access."""
        return self.tool_hints

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
        tool_hints = tuple(dict.fromkeys(map(str, value.get("tool_hints") or [])))
        return cls(
            name=name,
            version=version,
            purpose=str(value["purpose"]),
            when_useful=tuple(map(str, value["when_useful"])),
            prompt=str(value["prompt"]),
            process_guidance=tuple(map(str, value["process_guidance"])),
            tool_hints=tool_hints,
        )


class SkillRegistry:
    def __init__(self, descriptors: list[SkillDescriptor]):
        names = [descriptor.name for descriptor in descriptors]
        duplicates = sorted({name for name in names if names.count(name) > 1})
        if duplicates:
            raise ValueError(f"duplicate skill descriptors: {duplicates}")
        self._descriptors = {descriptor.name: descriptor for descriptor in descriptors}

    def get(self, name: str) -> SkillDescriptor:
        try:
            return self._descriptors[name]
        except KeyError as exc:
            raise KeyError(f"skill not registered: {name}") from exc

    def list(self) -> list[SkillDescriptor]:
        return [self._descriptors[name] for name in sorted(self._descriptors)]

    def catalog_for_agent(self) -> list[dict[str, Any]]:
        """Small discovery catalog; runtime activation injects full guidance directly."""
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
            "purpose": item.purpose,
            "when_useful": list(item.when_useful),
            "authority": "guidance_only",
            "prompt": item.prompt,
            "process_guidance": list(item.process_guidance),
            "guidance": list(item.guidance),
            "tool_hints": list(item.tool_hints),
        }
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
