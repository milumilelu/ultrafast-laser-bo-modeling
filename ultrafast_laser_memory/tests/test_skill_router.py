from __future__ import annotations

from ultrafast_memory.chat.skill_router import route_skill


def test_skill_router_routes_expected_messages():
    assert route_skill("我想加工金刚石 CRL，Ra小于460nm")["selected_skill"] == "task_understanding"
    assert route_skill("请调用 BO 做下一轮优化迭代")["selected_skill"] == "experiment_optimization"
    assert route_skill("读取 recipe 和 log 日志")["selected_skill"] == "task_understanding"
    assert route_skill("查文献和论文解释损伤机制")["selected_skill"] == "evidence_research"
    assert route_skill("帮我做一个加工工艺方案")["selected_skill"] == "process_planning"
