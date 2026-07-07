from __future__ import annotations

from ultrafast_memory.core.hashing import sha256_file


def test_sha256_same_and_different(tmp_path):
    one = tmp_path / "one.txt"
    two = tmp_path / "two.txt"
    one.write_text("abc", encoding="utf-8")
    two.write_text("abcd", encoding="utf-8")
    assert sha256_file(one) == sha256_file(one)
    assert sha256_file(one) != sha256_file(two)
