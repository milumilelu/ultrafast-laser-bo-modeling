from __future__ import annotations

from typing import Any

from ultrafast_agent.observability.renderers import NDJSONRenderer


def normalize_stream_event(event: dict[str, Any], sequence: int, mode: str = "normal") -> dict[str, Any] | None:
    return NDJSONRenderer().render(event, render_sequence=sequence, mode=mode)
