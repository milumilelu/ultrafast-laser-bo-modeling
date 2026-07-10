from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from ultrafast_agent.runtime.cancellation import CancellationToken


@dataclass(slots=True)
class RunContext:
    data: dict[str, Any]
    run_id: str = field(default_factory=lambda: f"run-{uuid.uuid4().hex}")
    session_id: str | None = None
    task_id: str | None = None
    display_mode: str = "normal"
    cancellation: CancellationToken = field(default_factory=CancellationToken)
