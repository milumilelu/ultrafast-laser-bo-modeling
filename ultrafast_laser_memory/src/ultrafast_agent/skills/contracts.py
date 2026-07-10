from __future__ import annotations

import re
from functools import lru_cache
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


REQUIRED_FIELDS = {
    "name",
    "version",
    "purpose",
    "inputs",
    "outputs",
    "preconditions",
    "side_effects",
    "allowed_tools",
    "forbidden_tools",
    "failure_modes",
    "timeout_ms",
    "cache_policy",
    "emitted_events",
}
DIRECT_STORAGE_TOOLS = {"sqlite", "database_connection", "raw_sql"}


@dataclass(frozen=True, slots=True)
class SkillContract:
    name: str
    version: str
    purpose: str
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    preconditions: tuple[str, ...]
    side_effects: tuple[str, ...]
    allowed_tools: tuple[str, ...]
    forbidden_tools: tuple[str, ...]
    failure_modes: tuple[str, ...]
    timeout_ms: int
    cache_policy: str
    emitted_events: tuple[str, ...]

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "SkillContract":
        missing = REQUIRED_FIELDS - set(value)
        if missing:
            raise ValueError(f"skill contract missing fields: {sorted(missing)}")
        name = str(value["name"])
        version = str(value["version"])
        if not re.fullmatch(r"[a-z][a-z0-9_]*", name):
            raise ValueError(f"invalid skill name: {name}")
        if not re.fullmatch(r"\d+\.\d+\.\d+(?:-[a-z0-9.]+)?", version):
            raise ValueError(f"invalid skill version: {name}={version}")
        timeout_ms = int(value["timeout_ms"])
        if timeout_ms <= 0:
            raise ValueError(f"timeout_ms must be positive: {name}")
        allowed = tuple(map(str, value["allowed_tools"]))
        forbidden = tuple(map(str, value["forbidden_tools"]))
        if set(allowed) & set(forbidden):
            raise ValueError(f"tool cannot be both allowed and forbidden: {name}")
        if set(allowed) & DIRECT_STORAGE_TOOLS:
            raise ValueError(f"business skill cannot directly access storage: {name}")
        return cls(
            name=name,
            version=version,
            purpose=str(value["purpose"]),
            inputs=tuple(map(str, value["inputs"])),
            outputs=tuple(map(str, value["outputs"])),
            preconditions=tuple(map(str, value["preconditions"])),
            side_effects=tuple(map(str, value["side_effects"])),
            allowed_tools=allowed,
            forbidden_tools=forbidden,
            failure_modes=tuple(map(str, value["failure_modes"])),
            timeout_ms=timeout_ms,
            cache_policy=str(value["cache_policy"]),
            emitted_events=tuple(map(str, value["emitted_events"])),
        )


class SkillRegistry:
    def __init__(self, contracts: list[SkillContract]):
        names = [contract.name for contract in contracts]
        duplicates = sorted({name for name in names if names.count(name) > 1})
        if duplicates:
            raise ValueError(f"duplicate skill contracts: {duplicates}")
        self._contracts = {contract.name: contract for contract in contracts}

    def get(self, name: str) -> SkillContract:
        try:
            return self._contracts[name]
        except KeyError as exc:
            raise KeyError(f"skill not registered: {name}") from exc

    def list(self) -> list[SkillContract]:
        return [self._contracts[name] for name in sorted(self._contracts)]


def load_skill_contracts(path: str | Path) -> SkillRegistry:
    source = Path(path)
    with source.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or {}
    values = payload.get("skills")
    if not isinstance(values, list):
        raise ValueError("skill contracts file must contain a skills list")
    return SkillRegistry([SkillContract.from_dict(value) for value in values])


def default_contract_path() -> Path:
    return Path(__file__).resolve().parents[3] / "skills/contracts.yaml"


@lru_cache(maxsize=1)
def get_default_skill_registry() -> SkillRegistry:
    return load_skill_contracts(default_contract_path())
