from __future__ import annotations

from ultrafast_memory.chat.router.schemas import RoutePlan


def rule_route(message: str, session_state: dict | None = None) -> RoutePlan:
    """Return non-binding skill hints; never activate a Skill or gate a tool."""
    text = message.lower()
    if text.strip().startswith("/bootstrap"):
        return RoutePlan(
            primary_skill="evidence_research", intent="skill_hint",
            workflow_stage="agent_planning", confidence=0.9,
            reason="Knowledge bootstrap command suggests evidence research.",
            route_source="rule_router",
        )
    scores = {
        "task_understanding": _count(text, ["任务", "材料", "尺寸", "孔", "切割", "加工", "约束", "目标"]),
        "evidence_research": _count(text, ["文献", "论文", "证据", "知识库", "检索", "机制", "依据"]),
        "process_planning": _count(text, ["方案", "路线", "工艺", "质量计划", "测量", "风险", "试切"]),
        "parameter_recommendation": _count(text, ["参数", "推荐", "窗口", "功率", "频率", "速度"]),
        "experiment_optimization": _count(text, ["bo", "贝叶斯", "优化", "下一轮", "迭代", "实验设计"]),
        "result_learning": _count(text, ["结果", "测量", "失败", "沉淀", "报告", "知识候选", "经验"]),
    }
    ranked = sorted(scores, key=lambda name: (-scores[name], name))
    primary = ranked[0] if scores[ranked[0]] else "task_understanding"
    secondary = [name for name in ranked[1:] if scores[name] > 0][:2]
    confidence = min(0.9, 0.45 + scores[primary] * 0.12)
    return RoutePlan(
        primary_skill=primary, secondary_skills=secondary, intent="skill_hint",
        workflow_stage="agent_planning", confidence=confidence,
        reason="Keyword evidence produced non-binding capability hints.",
        route_source="rule_router",
    )


def _count(text: str, markers: list[str]) -> int:
    return sum(marker in text for marker in markers)
