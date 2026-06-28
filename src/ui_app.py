"""Streamlit UI for the interactive Bayesian optimization demo."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.interactive_bo import (
    export_task_logs,
    init_task,
    load_experiment_data,
    load_task_state,
    recommend_next,
    recommend_parameters,
    submit_feedback,
)
from src.io_utils import load_config


CONFIG_PATH = ROOT / "config.yaml"


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
    for item in task_state.get("history", []):
        rec = item.get("recommendation", {})
        params = rec.get("recommended_parameters", {})
        pred = rec.get("prediction", {})
        fb = item.get("feedback", {})
        measured = fb.get("measured_result", {})
        qual = fb.get("qualitative_feedback", {})
        rows.append(
            {
                "iteration": item.get("iteration"),
                "pulse_width_ps": params.get("pulse_width_ps"),
                "frequency_kHz": params.get("frequency_kHz"),
                "hatch_spacing_um": params.get("hatch_spacing_um"),
                "passes": params.get("passes"),
                "scan_speed_mm_s": params.get("scan_speed_mm_s"),
                "predicted_depth_um": pred.get("depth_um"),
                "predicted_Sa_um": pred.get("Sa_um"),
                "measured_depth_um": measured.get("depth_um"),
                "measured_Sa_um": measured.get("Sa_um"),
                "roughness_feedback": qual.get("roughness"),
                "depth_feedback": qual.get("depth"),
                "efficiency_feedback": qual.get("efficiency"),
                "reason": rec.get("reason"),
            }
        )
    return pd.DataFrame(rows)


def run_app() -> None:
    """Run the Streamlit application."""
    import streamlit as st

    st.set_page_config(page_title="Interactive BO Process Recommendation", layout="wide")
    st.title("Interactive Bayesian Optimization Process Recommendation")

    config = load_ui_config()
    data = load_experiment_data(config)
    materials = sorted(data["material"].dropna().astype(str).unique())
    if "task_state" not in st.session_state:
        st.session_state.task_state = None
    if "last_recommendation" not in st.session_state:
        st.session_state.last_recommendation = None

    st.header("1. Task Settings")
    c1, c2, c3 = st.columns(3)
    with c1:
        material = st.selectbox("material", materials)
        objective_mode = st.selectbox(
            "objective_mode",
            ["quality_first", "efficiency_first", "balanced"],
            format_func=lambda value: {
                "quality_first": "加工质量优先 quality_first",
                "efficiency_first": "加工效率优先 efficiency_first",
                "balanced": "质量效率折中 balanced",
            }[value],
        )
    with c2:
        target_depth_um = st.number_input("target_depth_um", min_value=0.0, value=30.0, step=1.0)
        depth_min_um = st.number_input("depth_min_um", min_value=0.0, value=0.0, step=1.0)
    with c3:
        Sa_max_um = st.number_input("Sa_max_um", min_value=0.0, value=2.0, step=0.1)
        recommendation_type = st.selectbox("recommendation_type", ["exploitation", "exploration", "balanced"], index=2)

    material_data = data[data["material"].astype(str) == material]
    st.write(
        {
            "historical_samples": int(len(material_data)),
            "depth_model_available": bool(material_data["depth_um"].notna().sum() >= 5),
            "roughness_model_available": bool(material_data["Sa_um"].notna().sum() >= 5),
        }
    )

    if st.button("初始化任务", type="primary"):
        state = init_task(
            config,
            material=material,
            objective_mode=objective_mode,
            target_depth_um=target_depth_um if target_depth_um > 0 else None,
            depth_min_um=depth_min_um if depth_min_um > 0 else None,
            Sa_max_um=Sa_max_um if Sa_max_um > 0 else None,
        )
        st.session_state.task_state = state
        st.session_state.last_recommendation = None
        st.success(f"task_id: {state['task_id']}")

    if st.session_state.task_state:
        st.subheader("Current Search Range")
        st.dataframe(pd.DataFrame(st.session_state.task_state["parameter_bounds"]).T.rename(columns={0: "min", 1: "max"}), use_container_width=True)
        if st.session_state.task_state.get("warnings"):
            st.warning(" | ".join(st.session_state.task_state["warnings"]))

    st.header("2. Parameter Recommendation")
    if st.button("推荐参数"):
        if not st.session_state.task_state:
            st.error("Initialize a task first.")
        else:
            rec = recommend_parameters(st.session_state.task_state, recommendation_type)
            st.session_state.task_state = load_task_state(rec["task_id"])
            st.session_state.last_recommendation = rec

    rec = st.session_state.last_recommendation
    if rec:
        params_df = pd.DataFrame([rec["recommended_parameters"]])
        pred_df = pd.DataFrame(
            [
                {
                    "predicted_depth_um": rec["prediction"].get("depth_um"),
                    "predicted_depth_std_um": rec["prediction"].get("depth_std_um"),
                    "predicted_Sa_um": rec["prediction"].get("Sa_um"),
                    "predicted_Sa_std_um": rec["prediction"].get("Sa_std_um"),
                    "acquisition_score": rec["acquisition"].get("score"),
                    "reason": rec.get("reason"),
                }
            ]
        )
        st.dataframe(params_df, use_container_width=True)
        st.dataframe(pred_df, use_container_width=True)
        st.json(rec)

    st.header("3. Feedback")
    f1, f2, f3 = st.columns(3)
    with f1:
        measured_depth_um = st.number_input("measured_depth_um", min_value=0.0, value=0.0, step=0.1)
        measured_Sa_um = st.number_input("measured_Sa_um", min_value=0.0, value=0.0, step=0.01)
        processing_time_s = st.number_input("processing_time_s", min_value=0.0, value=0.0, step=1.0)
    with f2:
        roughness_feedback = st.selectbox("roughness_feedback", ["acceptable", "too_large", "too_small", "unknown"], index=3)
        depth_feedback = st.selectbox("depth_feedback", ["acceptable", "too_shallow", "too_deep", "unknown"], index=3)
        efficiency_feedback = st.selectbox("efficiency_feedback", ["acceptable", "too_low", "too_high", "unknown"], index=3)
    with f3:
        note = st.text_area("note", value="")

    if st.button("提交反馈并推荐下一组参数"):
        if not st.session_state.task_state:
            st.error("Initialize and recommend before submitting feedback.")
        elif not st.session_state.last_recommendation:
            st.error("Recommend a parameter set before submitting feedback.")
        else:
            iteration = st.session_state.last_recommendation["iteration"]
            feedback = {
                "task_id": st.session_state.task_state["task_id"],
                "iteration": iteration,
                "measured_result": {
                    "depth_um": measured_depth_um if measured_depth_um > 0 else None,
                    "Sa_um": measured_Sa_um if measured_Sa_um > 0 else None,
                    "processing_time_s": processing_time_s if processing_time_s > 0 else None,
                },
                "qualitative_feedback": {
                    "roughness": roughness_feedback,
                    "depth": depth_feedback,
                    "efficiency": efficiency_feedback,
                },
                "note": note,
            }
            updated = submit_feedback(st.session_state.task_state, feedback)
            old = st.session_state.last_recommendation
            new = recommend_next(updated, recommendation_type)
            st.session_state.task_state = load_task_state(new["task_id"])
            st.session_state.last_recommendation = new
            st.subheader("New vs Previous Parameters")
            comparison = pd.DataFrame([old["recommended_parameters"], new["recommended_parameters"]], index=["previous", "next"])
            st.dataframe(comparison, use_container_width=True)
            st.info(new["reason"])

    st.header("4. Task History")
    if st.session_state.task_state:
        history_df = task_history_table(st.session_state.task_state)
        st.dataframe(history_df, use_container_width=True)
        e1, e2, e3 = st.columns(3)
        with e1:
            if st.button("导出 recommendation_log.csv"):
                paths = export_task_logs(st.session_state.task_state, ROOT / "outputs")
                st.code(paths["recommendation_log"])
        with e2:
            if st.button("导出 feedback_log.csv"):
                paths = export_task_logs(st.session_state.task_state, ROOT / "outputs")
                st.code(paths["feedback_log"])
        with e3:
            if st.button("导出 task_state.json"):
                paths = export_task_logs(st.session_state.task_state, ROOT / "outputs")
                st.code(paths["task_state"])
        st.download_button(
            "Download task_state.json",
            data=json.dumps(st.session_state.task_state, ensure_ascii=False, indent=2),
            file_name=f"{st.session_state.task_state['task_id']}_task_state.json",
            mime="application/json",
        )


if __name__ == "__main__":
    run_app()
