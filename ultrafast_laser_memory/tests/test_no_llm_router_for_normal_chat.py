import json

from ultrafast_memory.chat.schemas import ChatRequest
from ultrafast_memory.chat.service import handle_chat
from ultrafast_memory.db.init_db import init_database


def test_no_llm_router_for_normal_chat(isolated_root, monkeypatch):
    class MainAgentOnlyLLM:
        provider = "fixture"
        model = "main-agent-only"

        def __init__(self):
            self.calls = 0

        def chat(self, messages, **kwargs):
            self.calls += 1
            return {"content": json.dumps({
                "action": "respond",
                "decision_summary": "当前轮回复",
                "message": "已收到。NextAction：补充加工目标。",
            }, ensure_ascii=False)}

    init_database()
    llm = MainAgentOnlyLLM()
    monkeypatch.setattr("ultrafast_memory.chat.service.create_llm_client", lambda config: llm)
    response = handle_chat(ChatRequest(message="普通自然语言请求"))

    assert llm.calls == 1
    assert response.route_plan["route_source"] in {"rule_router", "fallback"}
    assert response.audit_trace[0]["step"] == "rule_skill_hints"

