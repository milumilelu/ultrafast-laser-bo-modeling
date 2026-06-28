"""Markdown reporting for the modeling workflow."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from .models import FitResult


def _md_table(df: pd.DataFrame, max_rows: int = 20) -> str:
    if df is None or df.empty:
        return "No records."
    return df.head(max_rows).to_markdown(index=False)


def generate_modeling_report(
    path: str | Path,
    unified: pd.DataFrame,
    quality: pd.DataFrame,
    performance: pd.DataFrame,
    best_models: dict[tuple[str, str], FitResult],
    importance: pd.DataFrame,
    recommendations: pd.DataFrame,
) -> None:
    """Write the final Markdown report for project closeout."""
    lines = [
        "# 工艺参数-质量指标建模与贝叶斯优化推荐报告",
        "",
        "## 数据概况",
        "",
        f"- 统一后总样本数：{len(unified)}",
        f"- 材料数：{unified['material'].nunique() if not unified.empty else 0}",
        "- 原始数据按材料分别建模，未将所有材料直接混合为一个主模型。",
        "",
        _md_table(quality),
        "",
        "## 缺失值与单位说明",
        "",
        "- 缺失字段保留为 NaN；未对关键工艺参数做均值填补。",
        "- 标记为 fs 或数值尺度明显为飞秒的脉宽字段已转换为 ps。",
        "- 标记为 mm 或数值尺度明显为毫米的填充间距字段已转换为 um。",
        "- 若缺少 power_W、Sq_um、Sz_um，记录保留，派生能量代理特征保持 NaN。",
        "",
        "## 特征工程",
        "",
        "- 构造 log_pulse_width、log_frequency、log_hatch_spacing、log_passes、log_scan_speed。",
        "- 构造 D_proxy = frequency_kHz * passes / (scan_speed_mm_s * hatch_spacing_um)。",
        "- D_proxy 是单位面积累计脉冲作用密度的统计代理量，不是严格能量密度。",
        "- power_W 可用时才构造 pulse_energy_proxy 与 energy_density_proxy；当前缺失时不强行估计。",
        "",
        "## 模型性能对比",
        "",
        _md_table(performance.sort_values(["material", "target", "CV_RMSE"]) if not performance.empty else performance, max_rows=80),
        "",
        "## 每种材料的最佳模型",
        "",
        "| material | target | best_model | CV_RMSE | CV_R2 | n_samples |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for (material, target), result in best_models.items():
        lines.append(
            f"| {material} | {target} | {result.model_name} | {result.metrics.get('CV_RMSE', float('nan')):.4g} | "
            f"{result.metrics.get('CV_R2', float('nan')):.4g} | {result.metrics.get('n_samples', 0)} |"
        )
    lines.extend(
        [
            "",
            "## 关键参数辨识结果",
            "",
            "排序来自模型结果，不预设任何参数的重要性。RSM 证据为二阶响应面系数绝对值聚合；非线性证据为最佳模型的 permutation importance。",
            "",
            _md_table(importance.sort_values(["material", "target", "method", "importance_rank"]) if not importance.empty else importance, max_rows=80),
            "",
            "## 贝叶斯优化推荐参数",
            "",
            "BO 推荐用于规划下一轮实验点，不证明已经找到全局最优。候选点限制在已有实验参数水平或观测范围内。",
            "",
            _md_table(recommendations, max_rows=80),
            "",
            "## 当前数据限制",
            "",
            "- 当前数据未提供逐样本平均功率、单脉冲能量、光斑直径和离焦量；模型主要是统计代理模型，不具备完整物理因果解释。",
            "- 金刚石数据存在深度和粗糙度缺失；缺失样本不会参与对应目标建模。",
            "- 交叉验证评估受样本量和参数设计空间覆盖影响，外推到未观测工艺窗口的可信度有限。",
            "- MLP 仅作为深度学习对照，不作为主结论来源。",
            "",
            "## 后续实验建议",
            "",
            "- 对 BO 推荐点做小批量验证，并记录同一参数下的重复实验，用于估计实验噪声。",
            "- 补充 power_W、光斑直径、离焦量、加工气氛等变量后，再构造更接近物理意义的能量密度特征。",
            "- 对最佳模型预测误差较大的材料，优先在误差集中的参数区间加密实验。",
            "- 将高度图识别结果与工艺表通过样本编号或实验批次建立显式关联，避免人工拼接误差。",
            "",
        ]
    )
    Path(path).write_text("\n".join(lines), encoding="utf-8")
