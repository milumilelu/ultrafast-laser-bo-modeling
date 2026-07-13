from __future__ import annotations

import json

from fastapi.testclient import TestClient

from ultrafast_memory.apps.api.main import app
from ultrafast_memory.db.init_db import init_database


def test_stream_includes_progress_and_thinking_before_delta(isolated_root):
    init_database()
    client = TestClient(app)

    response = client.post(
        "/chat/stream_ndjson",
        json={"message": "我想加工金刚石 CRL，Ra小于460nm", "use_skills": True, "stream": True},
    )

    assert response.status_code == 200
    events = [json.loads(line) for line in response.text.splitlines() if line.strip()]
    types = [event["type"] for event in events]
    assert "progress" in types
    assert "thinking_status" in types
    assert types.index("progress") < types.index("delta")
    assert types.index("thinking_status") < types.index("delta")
    assert events[-1]["type"] == "done"
