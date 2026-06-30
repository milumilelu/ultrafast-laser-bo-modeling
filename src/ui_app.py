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
            "iteration": item.get("iteration"),
            "process_type": process_type,
            "model_status": rec.get("model_status"),
            "pulse_width_ps": params.get("pulse_width_ps"),
            "frequency_kHz": params.get("frequency_kHz"),
            "laser_power_W": params.get("laser_power_W"),
            "scan_speed_mm_s": params.get("scan_speed_mm_s"),
            "passes": params.get("passes"),
            "focus_offset_um": params.get("focus_offset_um"),
            "layer_step_um": params.get("layer_step_um"),
            "hatch_spacing_um": params.get("hatch_spacing_um"),
            "fill_pattern": params.get("fill_pattern"),
            "efficiency_feedback": qual.get("efficiency") or qual.get("efficiency_level"),
            "reason": rec.get("reason"),
        }
        if process_type == "cutting":
            row.update(
                {
                    "cut_through_probability": pred.get("cut_through_probability"),
                    "cut_through": measured.get("cut_through"),
                    "cut_through_level": qual.get("cut_through_level"),
                    "kerf_width_level": qual.get("kerf_width_level"),
                    "edge_roughness_level": qual.get("edge_roughness_level"),
                    "taper_level": qual.get("taper_level"),
                    "chipping_level": qual.get("chipping_level"),
                }
            )
        else:
            row.update(
                {
                    "predicted_depth_um": pred.get("depth_um"),
                    "predicted_Sa_um": pred.get("Sa_um"),
                    "measured_depth_um": measured.get("depth_um"),
                    "measured_Sa_um": measured.get("Sa_um"),
                    "roughness_feedback": qual.get("roughness"),
                    "depth_feedback": qual.get("depth"),
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
        recommendation_type = st.selectbox("推荐类型", ["exploitation", "exploration", "balanced"], index=2)
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
    st.write(
        {
            "process_type": process_type,
            "historical_samples": int(len(material_data)),
            "valid_samples": int(material_data.get("valid_flag", pd.Series(dtype=bool)).fillna(False).astype(bool).sum()) if not material_data.empty else 0,
        }
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
        st.success(f"task_id: {state['task_id']} | model_status: {state['model_status']}")

    if st.session_state.task_state:
        st.subheader("当前搜索范围")
        st.json(st.session_state.task_state["parameter_bounds"])
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
        st.dataframe(pd.DataFrame([rec["recommended_parameters"]]), use_container_width=True)
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
            st.dataframe(pd.DataFrame([old["recommended_parameters"], new["recommended_parameters"]], index=["previous", "next"]), use_container_width=True)
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
        lower = st.number_input(f"{label} min", value=default_min, step=step)
    with hi:
        upper = st.number_input(f"{label} max", value=default_max, step=step)
    return [float(lower), float(upper)]


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
