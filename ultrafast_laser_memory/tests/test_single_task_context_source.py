from fastapi.testclient import TestClient

from ultrafast_memory.agent_runtime.main_agent_loop import run_main_agent_turn
from ultrafast_memory.agent_runtime.working_context import load_working_context
from ultrafast_memory.apps.api.main import app
from ultrafast_memory.chat.session_state import get_session_state


def test_single_task_context_source(isolated_root):
    session_id = TestClient(app).post("/chat/sessions", json={}).json()["session_id"]
    result = run_main_agent_turn(
        session_id=session_id,
        message="加工 3 mm 厚 T300 碳纤维板的 4 mm 通孔",
        message_id="single-context",
        client=None,
    )
    state = get_session_state(session_id)
    loaded = load_working_context(state)

    assert result["task_spec"] == result["working_context"]["task"]
    assert loaded.task == result["task_spec"]
    assert state["collected_slots"]["task_spec"] == result["task_spec"]

