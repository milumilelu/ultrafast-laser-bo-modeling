from ultrafast_memory.chat.router.rule_router import rule_route
from ultrafast_memory.process_workflow.business_state import BusinessStateController


def test_router_is_hint_and_business_state_has_no_action_gate():
    route = rule_route("加工金刚石通孔并制定方案", {})
    workflow = {}
    BusinessStateController.ensure(workflow)
    assert route.intent == "skill_hint"
    assert "state_update" not in route.model_dump()
    assert "allowed_actions" not in workflow
