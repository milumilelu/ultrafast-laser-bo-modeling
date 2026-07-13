from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class BlockedResult:
    """Serializable failure contract shared by application services and APIs."""

    code: str
    message: str
    blocking_reasons: list[str] = field(default_factory=list)
    conflicting_sources: list[dict[str, Any]] = field(default_factory=list)
    suggested_next_actions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class GovernanceError(ValueError):
    def __init__(self, result: BlockedResult):
        super().__init__(result.message)
        self.result = result

