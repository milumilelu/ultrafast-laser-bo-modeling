from fastapi.testclient import TestClient

from ultrafast_agent.task_intake import update_task_context
from ultrafast_agent.task_intake.schemas import ClarificationContext
from ultrafast_memory.apps.api.main import app


def test_progressive_context_projects_nested_geometry(isolated_root):
    session_id = TestClient(app).post("/chat/sessions", json={}).json()["session_id"]
    context = ClarificationContext(workflow_type="task_understanding", stage="intake")
    result = update_task_context(
        {"updates": [
            {"field_name": "material", "value": "金刚石", "evidence": "金刚石"},
            {"field_name": "process_type", "value": "通孔", "evidence": "通孔"},
            {"field_name": "hole_diameter_mm", "value": 2, "unit": "mm", "evidence": "直径2mm"},
            {"field_name": "through_hole", "value": True, "evidence": "通孔"},
        ]},
        {"session_id": session_id, "message_id": "m", "user_message": "金刚石直径2mm通孔",
         "clarification_context": context.model_dump(mode="json")},
    )
    assert result["task_spec"]["geometry"] == {"hole_diameter_mm": 2.0, "through_hole": True}
