from __future__ import annotations

from typing import Any


STAGE_LABELS = {
    "INTAKE": "任务接收",
    "REQUIREMENTS_PENDING": "等待补充加工要求",
    "PARSER_STALL": "字段解析停滞",
    "REQUIREMENTS_CONFIRMED": "加工要求已确认",
    "EQUIPMENT_LOADING": "读取设备配置",
    "EVIDENCE_RETRIEVAL": "检索文献与历史案例",
    "EVIDENCE_ASSESSMENT": "评估证据可信度",
    "TRIAL_ASSESSMENT": "评估试切必要性",
    "TRIAL_MODE_PENDING": "等待选择试切方式",
    "TRIAL_PLAN_READY": "试切方案已生成",
    "TRIAL_RESULT_PENDING": "等待提交试切结果",
    "TRIAL_RESULT_EVALUATION": "评价试切结果",
    "KNOWLEDGE_APPROVAL_PENDING": "等待知识使用审核",
    "PARAMETER_SOURCE_APPROVAL_PENDING": "等待参数来源授权",
    "BO_READY": "贝叶斯优化准备就绪",
    "BO_RUNNING": "执行贝叶斯优化",
    "FORMAL_PROCESS_READY": "正式加工方案就绪",
    "FORMAL_RELEASE_PENDING": "等待正式加工放行",
    "FORMAL_PREFLIGHT": "正式加工前检查",
    "FORMAL_PROCESS_RUNNING": "正式加工执行中",
    "FINAL_INSPECTION_PENDING": "等待最终检测",
    "QUALITY_DECISION": "质量判定",
    "REWORK_PENDING": "等待返修决策",
    "REPORT_PENDING": "生成任务报告",
    "ARCHIVE_PENDING": "等待任务归档",
    "COMPLETED": "任务已完成",
    "BLOCKED": "任务已阻塞",
    "FAILED": "任务失败",
}

FIELD_LABELS = {
    "material": "材料及牌号",
    "process_type": "加工类型",
    "thickness_mm": "材料厚度（mm）",
    "quality_requirement": "质量要求",
    "cut_length_mm": "切割长度（mm）",
    "efficiency_requirement": "效率要求",
    "auxiliary": "辅助介质或辅助气体",
    "layer_cut_allowed": "是否允许分层多次切割",
    "hole_diameter_mm": "孔径（mm）",
    "hole_depth_mm": "孔深（mm）",
    "through_hole": "是否通孔",
    "taper_requirement": "锥度要求",
    "entrance_quality": "入口质量",
    "exit_quality": "出口质量",
    "equipment_revision": "设备版本",
    "material_batch": "材料批次",
    "actual_parameters": "实际加工参数",
    "parameter_units": "参数单位",
    "actual_path": "实际加工路径",
    "measurements": "测量结果",
    "defects": "缺陷记录",
    "files": "照片或检测附件",
    "progress_percent": "加工进度（%）",
    "deviation_level": "偏差等级",
    "observation": "检查点观测",
    "required_metrics": "必检指标",
    "constraint_results": "约束判定结果",
    "operator_confirmation": "操作者确认",
}

FIELD_QUESTIONS = {
    "material": "请确认材料名称和牌号。",
    "process_type": "请确认加工类型，例如切割、打孔或刻蚀。",
    "thickness_mm": "请提供材料厚度，单位为 mm。",
    "quality_requirement": "请说明质量要求，例如切缝区域无分层、无明显热损伤。",
    "cut_length_mm": "请提供本次切割总长度和轮廓形式，例如 100 mm 直线。",
    "efficiency_requirement": "请说明是否有加工时间或效率要求；没有可回答“无效率要求”。",
    "auxiliary": "请说明辅助介质，例如压缩空气、氮气；不使用可回答“无辅助气体”。",
    "layer_cut_allowed": "请确认是否允许多次分层切割，请回答“允许”或“不允许”。",
    "hole_diameter_mm": "请提供孔径，单位为 mm。",
    "hole_depth_mm": "请提供孔深，单位为 mm。",
    "through_hole": "请确认是否为通孔。",
    "taper_requirement": "请说明孔锥度要求。",
    "entrance_quality": "请说明入口崩边或表面质量要求。",
    "exit_quality": "请说明出口崩边或表面质量要求。",
}

ACTION_LABELS = {
    "submit_structured_fields": "按字段模板补充加工要求",
    "select_trial_mode": "选择试切方式",
    "approve_llm_fallback": "授权探索性参数候选",
    "resolve_parameter_evidence": "补充参数证据",
    "submit_trial_result": "提交试切结果",
    "review_trial_failure": "审查试切失败原因",
    "submit_formal_preflight": "提交正式加工前检查",
    "submit_formal_checkpoint": "提交正式加工检查点",
    "correct_formal_checkpoint": "修正检查点记录",
    "confirm_checkpoint_resume": "确认是否恢复加工",
    "submit_final_inspection": "提交最终检测",
    "complete_final_inspection": "补齐最终检测数据",
    "assess_rework": "评估返修",
    "return_to_trial": "返回试切阶段",
    "review_workflow_state": "审查工作流状态",
    "none": "无需操作",
}

STATUS_LABELS = {"completed": "已完成", "current": "当前", "pending": "未开始", "blocked": "阻塞"}


def stage_label(code: str | None) -> str:
    return STAGE_LABELS.get(code or "", code or "未知阶段")


def localize_action(action: dict[str, Any]) -> dict[str, Any]:
    result = dict(action)
    action_type = str(result.get("action_type") or "")
    fields = list(result.get("required_fields") or [])
    result["action_label"] = ACTION_LABELS.get(action_type, action_type)
    result["required_field_labels"] = [FIELD_LABELS.get(str(field), str(field)) for field in fields]
    return result
