from __future__ import annotations

from ultrafast_memory.chat.router.schemas import BlockedTool, RoutePlan, StateUpdate
from ultrafast_memory.equipment.bounds import build_machine_bounds
from ultrafast_agent.skills import get_default_skill_registry


def rule_route(message: str, session_state: dict | None = None) -> RoutePlan | None:
    state = session_state or {}
    if _is_continuation(message, state):
        skill = state.get("active_skill") or "task_intake"
        return RoutePlan(
            primary_skill=skill,
            intent="session_continuation",
            workflow_stage=state.get("workflow_stage") or "clarification",
            confidence=0.95,
            reason="User appears to answer pending clarification questions.",
            route_source="session_state",
            state_update=StateUpdate(
                active_skill=skill,
                workflow_stage=state.get("workflow_stage") or "clarification",
            ),
        )

    text = message.lower()
    if text.strip() == "/bootstrap run":
        return RoutePlan(
            primary_skill="knowledge_bootstrap",
            secondary_skills=["expert_review"],
            intent="manual_knowledge_bootstrap",
            workflow_stage="knowledge_bootstrap",
            confidence=1.0,
            reason="User explicitly requested knowledge bootstrap.",
            requires_evidence_gap_check=True,
            requires_web_bootstrap=True,
            requires_user_permission=False,
            requires_expert_review=True,
            allowed_tools=["evidence_gap_detector", "knowledge_bootstrap"],
            route_source="manual_override",
            state_update=StateUpdate(active_workflow="knowledge_bootstrap", active_skill="knowledge_bootstrap", workflow_stage="knowledge_bootstrap"),
        )
    hits = {
        "process_file_ingestion": _hit(text, ["导入日志", "扫描 recipe", "读取 csv", "日志", "recipe", "工艺文件", "检测结果", "csv", "log", "job"]),
        "bo_dataset_governance": _hit(text, ["导出 bo 数据", "导出bo数据", "bo 数据集", "训练集", "bo dataset", "export bo"]),
        "bo_recommendation": _hit(text, ["推荐参数", "贝叶斯", "bo", "优化", "下一轮实验", "怎么调"]),
        "crl_task_planning": _hit(text, ["crl", "金刚石透镜", "曲率半径", "焦距", "x-ray", "抛物面"]),
        "rag_literature_retrieval": _hit(text, ["文献", "论文", "参考文献", "机制", "损伤"]),
        "experience_memory_update": _hit(text, ["经验", "记忆库", "自学习", "规则", "沉淀", "发黑", "粗糙度没到", "失败"]),
        "report_generation": _hit(text, ["生成报告", "执行清单", "任务方案", "实验设计", "失败分析"]),
    }
    matched = [skill for skill, ok in hits.items() if ok]
    if not matched:
        return RoutePlan(
            primary_skill="task_intake",
            intent="task_intake",
            workflow_stage="intake",
            confidence=0.49,
            reason="No high-confidence domain rule matched.",
            requires_clarification=True,
            route_source="rule_router",
            state_update=StateUpdate(active_skill="task_intake", workflow_stage="intake"),
        )

    priority = [
        "process_file_ingestion",
        "bo_dataset_governance",
        "bo_recommendation",
        "crl_task_planning",
        "rag_literature_retrieval",
        "experience_memory_update",
        "report_generation",
    ]
    primary = next(skill for skill in priority if skill in matched)
    secondary = [skill for skill in matched if skill != primary]
    confidence = 0.92 if len(matched) == 1 and primary == "process_file_ingestion" else 0.86
    if len(matched) > 1:
        confidence = 0.65
        if "experience_memory_update" in matched and "bo_recommendation" in matched:
            primary = "experience_memory_update"
            secondary = [skill for skill in matched if skill != primary]
        elif "rag_literature_retrieval" in matched and any(marker in text for marker in ["文献", "论文", "查文献", "literature"]):
            primary = "rag_literature_retrieval"
            secondary = [skill for skill in matched if skill != primary]
    equipment_context = build_machine_bounds()
    equipment_ready = bool(equipment_context.get("active")) and not equipment_context.get("missing_equipment_fields")
    blocked_tools = []
    if primary in {"bo_recommendation", "experience_memory_update"}:
        if not equipment_ready:
            blocked_tools.append(BlockedTool(tool="bo_recommendation", reason="当前没有 active 设备配置，无法进行 BO 参数推荐。"))
    needs_clarification = bool(blocked_tools) or primary == "crl_task_planning"
    needs_gap_check = primary in {"rag_literature_retrieval", "bo_recommendation", "crl_task_planning"} or any(
        marker in text for marker in ["新材料", "新工艺", "查文献", "基于文献", "x-ray optics", "特殊陶瓷", "复合材料"]
    )
    if needs_gap_check:
        if not any(item.tool == "bo_recommendation" for item in blocked_tools) and "bo_recommendation" in matched:
            blocked_tools.append(BlockedTool(tool="bo_recommendation", reason="尚未完成文献证据和工艺先验审核，不能进入参数推荐。"))
    _validate_registered_skill(primary)
    return RoutePlan(
        primary_skill=primary,
        secondary_skills=secondary + (["knowledge_bootstrap", "expert_review"] if needs_gap_check else []),
        intent=primary,
        workflow_stage="evidence_check" if needs_gap_check else ("clarification" if needs_clarification else "intake"),
        confidence=confidence,
        reason=f"Rule router matched: {', '.join(matched)}.",
        requires_clarification=needs_clarification,
        requires_internal_rag=needs_gap_check,
        requires_evidence_gap_check=needs_gap_check,
        requires_web_bootstrap=needs_gap_check,
        requires_user_permission=needs_gap_check,
        requires_expert_review=needs_gap_check,
        clarification_questions=_questions(primary, matched, equipment_ready),
        allowed_tools=["evidence_gap_detector", "knowledge_bootstrap"] if needs_gap_check else [],
        blocked_tools=blocked_tools,
        route_source="rule_router",
        **_compatibility_metadata(primary),
        state_update=StateUpdate(
            active_workflow=_workflow_for(primary),
            active_skill=primary,
            workflow_stage="clarification" if needs_clarification else "intake",
            pending_questions=_pending_question_keys(primary, matched, equipment_ready),
            allowed_next_skills=secondary,
        ),
    )


def _validate_registered_skill(name: str) -> None:
    get_default_skill_registry().get(name)


def _compatibility_metadata(name: str) -> dict:
    replacements = {
        "crl_task_planning": "optical_component_task_workflow",
        "rag_literature_retrieval": "rag_evidence_retrieval",
        "experience_memory_update": "knowledge_candidate_generation",
    }
    replacement = replacements.get(name)
    return {
        "deprecated_skill_used": replacement is not None,
        "replacement_skill": replacement,
        "emitted_events": ["deprecated_skill_used"] if replacement else [],
    }


def _hit(text: str, keywords: list[str]) -> bool:
    return any(keyword.lower() in text for keyword in keywords)


def _is_continuation(message: str, state: dict) -> bool:
    if not state.get("active_skill"):
        return False
    if state.get("workflow_stage") != "clarification":
        return False
    if not state.get("pending_questions"):
        return False
    text = message.lower()
    continuation_markers = ["单晶", "多晶", "1030", "nm", "fs", "w", "可以", "不可以", "后处理", "最大功率"]
    return any(marker in text for marker in continuation_markers)


def _questions(primary: str, matched: list[str], equipment_ready: bool = False) -> list[str]:
    if primary == "crl_task_planning":
        questions = ["金刚石类型是什么？", "是否允许后处理？"]
        if not equipment_ready:
            questions.insert(1, "现有激光器的波长、脉宽、功率和频率边界是多少？")
        return questions
    if primary in {"bo_recommendation", "experience_memory_update"}:
        questions = ["目标函数和约束是什么？", "已有多少有效训练样本？"]
        if not equipment_ready:
            questions.insert(0, "设备边界是什么？")
        return questions
    return []


def _pending_question_keys(primary: str, matched: list[str], equipment_ready: bool = False) -> list[str]:
    if primary == "crl_task_planning":
        keys = ["diamond_type", "post_processing_allowed"]
        if not equipment_ready:
            keys.insert(1, "laser_system")
        return keys
    if primary in {"bo_recommendation", "experience_memory_update"}:
        keys = ["objective", "training_sample_count"]
        if not equipment_ready:
            keys.insert(0, "machine_bounds")
        return keys
    return []


def _workflow_for(primary: str) -> str | None:
    return {
        "crl_task_planning": "diamond_crl_planning",
        "process_file_ingestion": "file_ingestion",
        "bo_dataset_governance": "bo_dataset_governance",
        "bo_recommendation": "bo_optimization",
        "experience_memory_update": "experience_update",
    }.get(primary)
