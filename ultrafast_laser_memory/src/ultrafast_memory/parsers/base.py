from __future__ import annotations

from typing import Any


EMPTY_RESULT = {
    "tasks": [],
    "recipes": [],
    "runs": [],
    "measurements": [],
    "notes": [],
    "errors": [],
}


class BaseParser:
    name: str = "base"
    version: str = "0.0.0"

    def parse(self, file_path: str) -> dict[str, list[dict[str, Any]]]:
        raise NotImplementedError


def empty_result() -> dict[str, list[dict[str, Any]]]:
    return {key: [] for key in EMPTY_RESULT}
