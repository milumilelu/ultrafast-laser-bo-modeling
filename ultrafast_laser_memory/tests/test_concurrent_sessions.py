from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from ultrafast_memory.chat.schemas import ChatRequest
from ultrafast_memory.chat.service import handle_chat_stream_ndjson
from ultrafast_memory.db.init_db import init_database


def test_five_concurrent_mock_sessions_complete_without_cross_talk(
    isolated_root, monkeypatch
):
    monkeypatch.setenv("ULTRAFAST_LLM_PROVIDER", "mock")
    monkeypatch.setenv("ULTRAFAST_LLM_MODEL", "concurrency-test")
    init_database()

    def run(index: int) -> tuple[str, list[dict]]:
        events = list(
            handle_chat_stream_ndjson(
                ChatRequest(
                    message=f"concurrency sentinel {index}",
                    use_skills=False,
                    stream=True,
                )
            )
        )
        session_id = next(event["session_id"] for event in events if event["type"] == "meta")
        return session_id, events

    with ThreadPoolExecutor(max_workers=5) as executor:
        results = list(executor.map(run, range(5)))

    assert len({session_id for session_id, _ in results}) == 5
    for _, events in results:
        assert events[-1]["type"] == "done"
        assert not any(event["type"] == "error" for event in events)
        assert any(event["type"] == "delta" for event in events)
