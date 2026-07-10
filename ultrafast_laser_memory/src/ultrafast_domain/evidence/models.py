from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class EvidenceReference:
    evidence_id: str
    source_revision: str
    claim_revision: str
    allowed_uses: tuple[str, ...] = field(default_factory=tuple)
    risk_level: str = "low"

    def allows(self, intended_use: str) -> bool:
        return intended_use in self.allowed_uses
