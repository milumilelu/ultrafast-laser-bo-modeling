from ultrafast_memory.agent_runtime.planner import MainAgentPlanner
from ultrafast_memory.agent_runtime.task_intake import prepare_task_context


def test_single_missing_question_allowed():
    preparation = prepare_task_context(
        "在铝基碳化硅板材上加工5×5mm矩形槽",
        {"task": {}},
    )
    action = MainAgentPlanner.deterministic_fallback(
        {"task": preparation.context_updates["task"], "task_intake": {
            "blocking_fields": preparation.blocking_fields,
        }},
        [],
        [],
        reason="test",
    )

    assert preparation.blocking_fields == ["geometry.depth_mm"]
    assert action.action == "ask_user"
    assert action.message == "目标槽深是多少，还是要求贯穿？"
    assert action.message.count("？") == 1

