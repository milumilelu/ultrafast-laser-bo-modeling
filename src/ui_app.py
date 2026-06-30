"""Streamlit UI for the interactive multi-process recommendation demo."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.interactive_bo import (  # noqa: E402
    export_task_logs,
    init_task,
    load_experiment_data,
    load_task_state,
    recommend_next,
    recommend_parameters,
    submit_feedback,
)
from src.io_utils import load_config  # noqa: E402
from src.schema import FILL_PATTERN_DISPLAY  # noqa: E402


CONFIG_PATH = ROOT / "config.yaml"
PROCESS_LABELS = {"铣削": "milling", "切割": "cutting"}
PROCESS_TYPE_DISPLAY = {"milling": "铣削", "cutting": "切割"}
MODEL_STATUS_DISPLAY = {
    "rule_based_cold_start": "规则冷启动",
    "hybrid_rule_bo": "规则 + BO 混合",
    "data_driven_bo": "数据驱动 BO",
}
RECOMMENDATION_TYPE_DISPLAY = {"exploitation": "利用", "exploration": "探索", "balanced": "平衡"}
PARAMETER_LABELS = {
    "pulse_width_ps": "脉冲宽度 ps",
    "frequency_kHz": "重复频率 kHz",
    "laser_power_W": "激光功率 W",
    "scan_speed_mm_s": "扫描速度 mm/s",
    "passes": "加工次数",
    "focus_offset_um": "离焦量 um",
    "layer_step_um": "层间距 um",
    "hatch_spacing_um": "填充间距 um",
    "fill_pattern": "填充方式",
    "power_W": "功率 W",
}
PREDICTION_LABELS = {
    "depth_um": "预测深度 um",
    "depth_std_um": "深度不确定度 um",
    "Sa_um": "预测 Sa um",
    "Sa_std_um": "Sa 不确定度 um",
    "cut_through_probability": "切透概率",
    "kerf_top_width_um": "切缝上宽 um",
    "kerf_bottom_width_um": "切缝下宽 um",
    "kerf_taper_deg": "切缝锥度 deg",
    "cut_edge_Sa_um": "断面粗糙度 Sa um",
    "HAZ_width_um": "热影响区宽度 um",
    "chipping_um": "崩边 um",
}
LEVEL_OPTIONS = ["很小", "较小", "适中", "较大", "很大", "unknown"]
CUT_THROUGH_OPTIONS = ["未切透", "勉强切透", "适中", "过烧蚀", "严重过烧蚀", "unknown"]


def load_ui_config() -> dict[str, Any]:
    """Load config.yaml with an explicit project root."""
    config = load_config(CONFIG_PATH)
    config["_root"] = str(ROOT)
    return config


def task_history_table(task_state: dict[str, Any] | None) -> pd.DataFrame:
    """Convert task history into a UI table."""
    if not task_state:
        return pd.DataFrame()
    rows = []
    process_type = task_state.get("process_type", "milling")
    for item in task_state.get("history", []):
        rec = item.get("recommendation", {})
        params = rec.get("recommended_parameters", {})
        pred = rec.get("prediction", {})
        fb = item.get("feedback", {})
        measured = fb.get("measured_result", {})
        qual = fb.get("qualitative_feedback", {})
        row = {
            "轮次": item.get("iteration"),
            "工艺场景": PROCESS_TYPE_DISPLAY.get(process_type, process_type),
            "模型状态": MODEL_STATUS_DISPLAY.get(rec.get("model_status"), rec.get("model_status")),
            "脉冲宽度 ps": params.get("pulse_width_ps"),
            "重复频率 kHz": params.get("frequency_kHz"),
            "激光功率 W": params.get("laser_power_W"),
            "扫描速度 mm/s": params.get("scan_speed_mm_s"),
            "加工次数": params.get("passes"),
            "离焦量 um": params.get("focus_offset_um"),
            "层间距 um": params.get("layer_step_um"),
            "填充间距 um": params.get("hatch_spacing_um"),
            "填充方式": _display_fill_pattern(params.get("fill_pattern")),
            "效率反馈": qual.get("efficiency") or qual.get("efficiency_level"),
            "推荐说明": rec.get("reason"),
        }
        if process_type == "cutting":
            row.update(
                {
                    "切透概率": pred.get("cut_through_probability"),
                    "实测切透": measured.get("cut_through"),
                    "切透状态反馈": qual.get("cut_through_level"),
                    "切缝宽度反馈": qual.get("kerf_width_level"),
                    "断面粗糙度反馈": qual.get("edge_roughness_level"),
                    "锥度反馈": qual.get("taper_level"),
                    "崩边反馈": qual.get("chipping_level"),
                }
            )
        else:
            row.update(
                {
                    "预测深度 um": pred.get("depth_um"),
                    "预测 Sa um": pred.get("Sa_um"),
                    "实测深度 um": measured.get("depth_um"),
                    "实测 Sa um": measured.get("Sa_um"),
                    "粗糙度反馈": qual.get("roughness"),
                    "深度反馈": qual.get("depth"),
                }
            )
        rows.append(row)
    return pd.DataFrame(rows)


def run_app() -> None:
    """Run the Streamlit application."""
    import streamlit as st

    st.set_page_config(page_title="Interactive BO Process Recommendation", layout="wide")
    st.title("超快激光工艺参数推荐")

    config = load_ui_config()
    data = load_experiment_data(config)
    materials = sorted(data["material"].dropna().astype(str).unique())
    st.session_state.setdefault("task_state", None)
    st.session_state.setdefault("last_recommendation", None)

    st.header("1. 任务设置")
    c1, c2, c3 = st.columns(3)
    with c1:
        process_label = st.selectbox("工艺场景", list(PROCESS_LABELS), index=0)
        process_type = PROCESS_LABELS[process_label]
        material = st.selectbox("材料", materials)
    with c2:
        objective_mode = st.selectbox(
            "目标偏好",
            ["quality_first", "efficiency_first", "balanced"],
            format_func=lambda value: {
                "quality_first": "质量优先",
                "efficiency_first": "效率优先",
                "balanced": "质量效率折中",
            }[value],
        )
        recommendation_type = st.selectbox(
            "推荐类型",
            ["exploitation", "exploration", "balanced"],
            index=2,
            format_func=lambda value: RECOMMENDATION_TYPE_DISPLAY[value],
        )
    with c3:
        laser_power_bounds = _range_inputs(st, "激光功率 W", 1.0, 20.0, 0.5)
        fill_pattern = st.selectbox(
            "填充方式",
            ["zigzag", "contour", "concentric", "polyline", "spiral", "none", "custom"],
            index=5 if process_type == "cutting" else 0,
            format_func=lambda value: FILL_PATTERN_DISPLAY[value],
        )

    bounds: dict[str, Any] = {
        "laser_power_W": laser_power_bounds,
        "fill_pattern": [fill_pattern],
    }
    requirements: dict[str, Any] = {}
    target_depth_um = depth_min_um = Sa_max_um = None

    if process_type == "cutting":
        st.subheader("切割需求")
        q1, q2, q3, q4 = st.columns(4)
        with q1:
            requirements["material_thickness_um"] = st.number_input("材料厚度 um", min_value=0.0, value=500.0, step=10.0)
            requirements["cut_through_required"] = st.checkbox("要求切透", value=True)
        with q2:
            requirements["target_kerf_width_um"] = st.number_input("目标切缝宽度 um", min_value=0.0, value=30.0, step=1.0)
            requirements["max_taper_deg"] = st.number_input("最大锥度 deg", min_value=0.0, value=3.0, step=0.1)
        with q3:
            requirements["max_edge_Sa_um"] = st.number_input("最大断面粗糙度 um", min_value=0.0, value=2.0, step=0.1)
            bounds["layer_step_um"] = _range_inputs(st, "层间距 um", 1.0, 20.0, 1.0)
        with q4:
            bounds["hatch_spacing_um"] = _range_inputs(st, "填充间距 um", 1.0, 20.0, 1.0)
    else:
        st.subheader("铣削需求")
        m1, m2, m3 = st.columns(3)
        with m1:
            target_depth_um = st.number_input("目标深度 um", min_value=0.0, value=30.0, step=1.0)
        with m2:
            depth_min_um = st.number_input("最小深度 um", min_value=0.0, value=0.0, step=1.0)
        with m3:
            Sa_max_um = st.number_input("最大 Sa um", min_value=0.0, value=2.0, step=0.1)

    material_data = data[(data["material"].astype(str) == material) & (data["process_type"].fillna("milling") == process_type)]
    valid_count = int(material_data.get("valid_flag", pd.Series(dtype=bool)).fillna(False).astype(bool).sum()) if not material_data.empty else 0
    st.dataframe(
        pd.DataFrame(
            [
                {"项目": "工艺场景", "数值": PROCESS_TYPE_DISPLAY[process_type]},
                {"项目": "历史样本数", "数值": str(int(len(material_data)))},
                {"项目": "有效样本数", "数值": str(valid_count)},
            ]
        ),
        hide_index=True,
        use_container_width=True,
    )

    if st.button("初始化任务", type="primary"):
        state = init_task(
            config,
            material=material,
            objective_mode=objective_mode,
            process_type=process_type,
            target_depth_um=target_depth_um if target_depth_um and target_depth_um > 0 else None,
            depth_min_um=depth_min_um if depth_min_um and depth_min_um > 0 else None,
            Sa_max_um=Sa_max_um if Sa_max_um and Sa_max_um > 0 else None,
            parameter_bounds=bounds,
            requirements=requirements,
        )
        st.session_state.task_state = state
        st.session_state.last_recommendation = None
        st.success(f"任务 ID：{state['task_id']} | 模型状态：{MODEL_STATUS_DISPLAY.get(state['model_status'], state['model_status'])}")

    if st.session_state.task_state:
        st.subheader("当前搜索范围")
        st.dataframe(_bounds_table(st.session_state.task_state["parameter_bounds"]), hide_index=True, use_container_width=True)
        if st.session_state.task_state.get("warnings"):
            st.warning(" | ".join(st.session_state.task_state["warnings"]))

    st.header("2. 参数推荐")
    if st.button("推荐参数"):
        if not st.session_state.task_state:
            st.error("请先初始化任务。")
        else:
            rec = recommend_parameters(st.session_state.task_state, recommendation_type)
            st.session_state.task_state = load_task_state(rec["task_id"])
            st.session_state.last_recommendation = rec

    rec = st.session_state.last_recommendation
    if rec:
        st.subheader("推荐工艺参数")
        st.dataframe(_parameter_table(rec["recommended_parameters"]), hide_index=True, use_container_width=True)
        st.subheader("预测与推荐依据")
        st.dataframe(_prediction_table(rec.get("prediction", {}), rec.get("acquisition", {}), rec.get("model_status")), hide_index=True, use_container_width=True)
        st.info(rec.get("reason", ""))
        with st.expander("查看原始推荐 JSON"):
            st.json(rec)

    st.header("3. 实验反馈")
    if st.session_state.task_state and st.session_state.task_state.get("process_type") == "cutting":
        feedback = _cutting_feedback_form(st)
    else:
        feedback = _milling_feedback_form(st)

    if st.button("提交反馈并推荐下一组参数"):
        if not st.session_state.task_state or not st.session_state.last_recommendation:
            st.error("请先初始化任务并生成推荐。")
        else:
            feedback["task_id"] = st.session_state.task_state["task_id"]
            feedback["iteration"] = st.session_state.last_recommendation["iteration"]
            updated = submit_feedback(st.session_state.task_state, feedback)
            old = st.session_state.last_recommendation
            new = recommend_next(updated, recommendation_type)
            st.session_state.task_state = load_task_state(new["task_id"])
            st.session_state.last_recommendation = new
            st.subheader("上一组与下一组参数")
            st.dataframe(_comparison_table(old["recommended_parameters"], new["recommended_parameters"]), hide_index=True, use_container_width=True)
            st.info(new["reason"])

    st.header("4. 任务历史")
    if st.session_state.task_state:
        st.dataframe(task_history_table(st.session_state.task_state), use_container_width=True)
        e1, e2, e3 = st.columns(3)
        with e1:
            if st.button("导出 recommendation_log.csv"):
                st.code(export_task_logs(st.session_state.task_state, ROOT / "outputs")["recommendation_log"])
        with e2:
            if st.button("导出 feedback_log.csv"):
                st.code(export_task_logs(st.session_state.task_state, ROOT / "outputs")["feedback_log"])
        with e3:
            if st.button("导出 task_state.json"):
                st.code(export_task_logs(st.session_state.task_state, ROOT / "outputs")["task_state"])
        st.download_button(
            "Download task_state.json",
            data=json.dumps(st.session_state.task_state, ensure_ascii=False, indent=2),
            file_name=f"{st.session_state.task_state['task_id']}_task_state.json",
            mime="application/json",
        )


def _range_inputs(st: Any, label: str, default_min: float, default_max: float, step: float) -> list[float]:
    lo, hi = st.columns(2)
    with lo:
        lower = st.number_input(f"{label} 下限", value=default_min, step=step)
    with hi:
        upper = st.number_input(f"{label} 上限", value=default_max, step=step)
    return [float(lower), float(upper)]


def _parameter_table(params: dict[str, Any]) -> pd.DataFrame:
    rows = []
    for field, value in params.items():
        display_value = _display_fill_pattern(value) if field == "fill_pattern" else value
        rows.append({"参数": PARAMETER_LABELS.get(field, field), "内部字段": field, "推荐值": _format_value(display_value)})
    return pd.DataFrame(rows)


def _prediction_table(prediction: dict[str, Any], acquisition: dict[str, Any], model_status: str | None) -> pd.DataFrame:
    rows = [{"项目": "模型状态", "字段": "model_status", "数值": _format_value(MODEL_STATUS_DISPLAY.get(model_status, model_status))}]
    for field, value in prediction.items():
        rows.append({"项目": PREDICTION_LABELS.get(field, field), "字段": field, "数值": "暂无预测" if value is None else _format_value(value)})
    rows.append({"项目": "采集函数类型", "字段": "acquisition.type", "数值": _format_value(RECOMMENDATION_TYPE_DISPLAY.get(acquisition.get("type"), acquisition.get("type")))})
    rows.append({"项目": "采集函数得分", "字段": "acquisition.score", "数值": "暂无" if acquisition.get("score") is None else _format_value(acquisition.get("score"))})
    return pd.DataFrame(rows)


def _bounds_table(bounds: dict[str, Any]) -> pd.DataFrame:
    rows = []
    for field, value in bounds.items():
        if field == "fill_pattern":
            display_value = "、".join(_display_fill_pattern(item) for item in value)
            rows.append({"参数": PARAMETER_LABELS.get(field, field), "内部字段": field, "下限": "", "上限": "", "可选值": display_value})
        elif isinstance(value, list) and len(value) == 2:
            rows.append({"参数": PARAMETER_LABELS.get(field, field), "内部字段": field, "下限": _format_value(value[0]), "上限": _format_value(value[1]), "可选值": ""})
        else:
            rows.append({"参数": PARAMETER_LABELS.get(field, field), "内部字段": field, "下限": "", "上限": "", "可选值": _format_value(value)})
    return pd.DataFrame(rows)


def _comparison_table(previous: dict[str, Any], current: dict[str, Any]) -> pd.DataFrame:
    fields = list(dict.fromkeys(list(previous) + list(current)))
    rows = []
    for field in fields:
        prev_value = _display_fill_pattern(previous.get(field)) if field == "fill_pattern" else previous.get(field)
        cur_value = _display_fill_pattern(current.get(field)) if field == "fill_pattern" else current.get(field)
        rows.append({"参数": PARAMETER_LABELS.get(field, field), "内部字段": field, "上一组": _format_value(prev_value), "下一组": _format_value(cur_value)})
    return pd.DataFrame(rows)


def _display_fill_pattern(value: Any) -> Any:
    if value in FILL_PATTERN_DISPLAY:
        return FILL_PATTERN_DISPLAY[value]
    return value


def _format_value(value: Any) -> str:
    if value is None:
        return "暂无"
    if isinstance(value, float):
        return f"{value:.6g}"
    return str(value)


def _milling_feedback_form(st: Any) -> dict[str, Any]:
    f1, f2, f3 = st.columns(3)
    with f1:
        measured_depth_um = st.number_input("实测深度 um", min_value=0.0, value=0.0, step=0.1)
        measured_Sa_um = st.number_input("实测 Sa um", min_value=0.0, value=0.0, step=0.01)
    with f2:
        roughness_feedback = st.selectbox("粗糙度反馈", LEVEL_OPTIONS, index=2)
        depth_feedback = st.selectbox("深度反馈", LEVEL_OPTIONS, index=2)
        efficiency_feedback = st.selectbox("效率反馈", LEVEL_OPTIONS, index=2)
    with f3:
        note = st.text_area("备注", value="")
    return {
        "measured_result": {"depth_um": measured_depth_um if measured_depth_um > 0 else None, "Sa_um": measured_Sa_um if measured_Sa_um > 0 else None},
        "qualitative_feedback": {"roughness": roughness_feedback, "depth": depth_feedback, "efficiency": efficiency_feedback},
        "note": note,
    }


def _cutting_feedback_form(st: Any) -> dict[str, Any]:
    f1, f2, f3 = st.columns(3)
    with f1:
        cut_through = st.selectbox("是否切透", ["unknown", "true", "false"], index=0)
        kerf_top_width_um = st.number_input("切缝上宽 um", min_value=0.0, value=0.0, step=0.1)
        kerf_bottom_width_um = st.number_input("切缝下宽 um", min_value=0.0, value=0.0, step=0.1)
    with f2:
        cut_through_level = st.selectbox("切透状态", CUT_THROUGH_OPTIONS, index=2)
        kerf_width_level = st.selectbox("切缝宽度等级", LEVEL_OPTIONS, index=2)
        edge_roughness_level = st.selectbox("断面粗糙度等级", LEVEL_OPTIONS, index=2)
    with f3:
        taper_level = st.selectbox("锥度等级", LEVEL_OPTIONS, index=2)
        chipping_level = st.selectbox("崩边等级", LEVEL_OPTIONS, index=2)
        efficiency_level = st.selectbox("效率等级", LEVEL_OPTIONS, index=2)
        note = st.text_area("备注", value="")
    cut_map = {"true": True, "false": False, "unknown": None}
    return {
        "measured_result": {
            "cut_through": cut_map[cut_through],
            "kerf_top_width_um": kerf_top_width_um if kerf_top_width_um > 0 else None,
            "kerf_bottom_width_um": kerf_bottom_width_um if kerf_bottom_width_um > 0 else None,
        },
        "qualitative_feedback": {
            "cut_through_level": cut_through_level,
            "kerf_width_level": kerf_width_level,
            "edge_roughness_level": edge_roughness_level,
            "taper_level": taper_level,
            "chipping_level": chipping_level,
            "efficiency_level": efficiency_level,
        },
        "note": note,
    }


if __name__ == "__main__":
    run_app()
