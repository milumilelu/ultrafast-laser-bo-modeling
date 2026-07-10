from __future__ import annotations

from ultrafast_memory.chat.router.schemas import RoutePlan, StateUpdate


AVAILABLE_SKILLS = {
    "task_intake": "模糊任务解析和追问",
    "crl_task_planning": "金刚石 CRL / X-ray 透镜制造规划",
    "rag_literature_retrieval": "文献检索和证据提取",
    "bo_recommendation": "贝叶斯优化参数推荐",
    "process_file_ingestion": "日志、工艺文件、检测结果导入",
    "experience_memory_update": "经验候选和规则沉淀",
    "bo_dataset_governance": "判断实验记录能否进入 BO 训练集",
    "report_generation": "生成任务方案、执行清单或报告",
}


def parse_manual_override(message: str) -> RoutePlan | None:
    text = message.strip()
    if not text.startswith("/skill "):
        return None
    skill = text.split(maxsplit=1)[1].strip()
    if skill not in AVAILABLE_SKILLS:
        return RoutePlan(
            primary_skill="task_intake",
            intent="manual_override_invalid",
            workflow_stage="clarification",
            confidence=0.2,
            reason=f"Unknown skill override: {skill}",
            requires_clarification=True,
            clarification_questions=[f"可用 skill: {', '.join(AVAILABLE_SKILLS)}"],
            route_source="manual_override",
        )
    return RoutePlan(
        primary_skill=skill,
        intent="manual_override",
        workflow_stage="manual",
        confidence=1.0,
        reason="User manually selected skill.",
        route_source="manual_override",
        state_update=StateUpdate(active_skill=skill, workflow_stage="manual"),
    )
