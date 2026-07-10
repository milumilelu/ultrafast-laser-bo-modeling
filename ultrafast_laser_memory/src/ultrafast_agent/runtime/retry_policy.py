from __future__ import annotations


def attempt_count(retries: int) -> int:
    if retries < 0:
        raise ValueError("retries cannot be negative")
    return retries + 1
