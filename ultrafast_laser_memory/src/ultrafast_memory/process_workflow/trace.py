from __future__ import annotations

import re
from typing import Any


FORBIDDEN_KEYS = {"chain_of_thought", "hidden_reasoning", "raw_thoughts", "system_prompt", "model_reasoning_tokens"}
SENSITIVE = re.compile(r"(api[_-]?key|authorization|cookie|password|dpapi)", re.I)


def redact_public_trace(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: "[REDACTED]" if SENSITIVE.search(key) else redact_public_trace(item)
                for key, item in value.items() if key not in FORBIDDEN_KEYS}
    if isinstance(value, list):
        return [redact_public_trace(item) for item in value]
    return value


def assert_public_trace(value: dict[str, Any]) -> None:
    rendered = repr(value).lower()
    if any(key in rendered for key in FORBIDDEN_KEYS):
        raise ValueError("hidden chain-of-thought fields are forbidden in public trace")
