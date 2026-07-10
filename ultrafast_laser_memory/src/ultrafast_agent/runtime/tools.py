from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


ToolHandler = Callable[[dict[str, Any], dict[str, Any]], Any]


@dataclass(frozen=True, slots=True)
class ToolContract:
    name: str
    purpose: str
    handler: ToolHandler
    timeout_ms: int = 30_000
    side_effects: tuple[str, ...] = ()
    cache_policy: str = "none"
    sensitive_input_fields: tuple[str, ...] = field(default_factory=tuple)


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, ToolContract] = {}

    def register(self, contract: ToolContract, *, replace: bool = False) -> None:
        if contract.name in self._tools and not replace:
            raise ValueError(f"tool already registered: {contract.name}")
        self._tools[contract.name] = contract

    def get(self, name: str) -> ToolContract:
        try:
            return self._tools[name]
        except KeyError as exc:
            raise KeyError(f"tool not registered: {name}") from exc

    def list_contracts(self) -> list[ToolContract]:
        return [self._tools[name] for name in sorted(self._tools)]

    def call(self, name: str, payload: dict[str, Any], context: dict[str, Any]) -> Any:
        return self.get(name).handler(payload, context)
