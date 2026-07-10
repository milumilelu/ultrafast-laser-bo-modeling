from __future__ import annotations

from ultrafast_memory.llm.mock import MockLLMClient


def test_mock_llm_streams_delta_events():
    client = MockLLMClient()
    events = list(client.stream_chat([{"role": "user", "content": "hello"}]))

    assert events[-1] == {"type": "done"}
    assert "".join(event["content"] for event in events if event["type"] == "delta") == "[MockLLM] 已收到：hello"
