from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from src.bayes_opt import BO_COLUMNS, recommend_bo
from src.features import add_engineered_features
from src.models import fit_models_for_target
from src.preprocessing import clean_material_table, normalize_column_name


def test_column_normalization():
    assert normalize_column_name(" 深度/μm ") == "深度_um"
    assert normalize_column_name("Scan Speed mm/s") == "scanspeedmm_s"


def test_d_proxy_calculation():
    df = pd.DataFrame(
        {
            "frequency_kHz": [10.0, 10.0],
            "passes": [2.0, 2.0],
            "scan_speed_mm_s": [5.0, 0.0],
            "hatch_spacing_um": [4.0, 4.0],
            "pulse_width_ps": [1.0, 1.0],
            "power_W": [np.nan, np.nan],
        }
    )
    out = add_engineered_features(df)
    assert out.loc[0, "D_proxy"] == 1.0
    assert pd.isna(out.loc[1, "D_proxy"])


def test_missing_values_do_not_crash_cleaning():
    raw = pd.DataFrame({"脉宽fs": [500, None], "频率kHz": [10, 20], "间距mm": [0.002, None], "重复加工次数": [1, 2]})
    cleaned, _ = clean_material_table(raw, "Test", {"source_file": "synthetic.csv"})
    assert len(cleaned) == 2
    assert "depth_um" in cleaned.columns
    assert cleaned["depth_um"].isna().all()


def test_small_sample_models_are_skipped():
    logger = logging.getLogger("test")
    df = pd.DataFrame(
        {
            "material": ["T"] * 3,
            "pulse_width_ps": [1, 2, 3],
            "frequency_kHz": [10, 20, 30],
            "hatch_spacing_um": [2, 3, 4],
            "passes": [1, 1, 1],
            "scan_speed_mm_s": [5, 6, 7],
            "depth_um": [1, 2, 3],
            "Sa_um": [0.1, 0.2, 0.3],
            "valid_flag": [True, True, True],
        }
    )
    featured = add_engineered_features(df)
    results = fit_models_for_target(featured, "T", "depth_um", ["pulse_width_ps", "frequency_kHz"], 42, 5, logger)
    assert results == []


def test_bo_recommendations_schema_with_fitted_gpr():
    logger = logging.getLogger("test")
    rows = []
    for i in range(12):
        rows.append(
            {
                "material": "T",
                "pulse_width_ps": [0.5, 1.0, 2.0][i % 3],
                "frequency_kHz": [2, 10, 20][i % 3],
                "hatch_spacing_um": [2, 4][i % 2],
                "passes": [1, 2, 3][i % 3],
                "scan_speed_mm_s": [5, 10, 15, 20][i % 4],
                "power_W": np.nan,
                "depth_um": float(i + 1),
                "Sa_um": float(0.1 * (i + 1)),
                "valid_flag": True,
            }
        )
    df = add_engineered_features(pd.DataFrame(rows))
    features = ["pulse_width_ps", "frequency_kHz", "hatch_spacing_um", "passes", "scan_speed_mm_s", "D_proxy"]
    results = fit_models_for_target(df, "T", "depth_um", features, 42, 3, logger)
    recs, _ = recommend_bo(df, results, {"bo_n_recommendations": 5, "bo_candidate_grid_size": 64, "random_seed": 42}, logger)
    assert list(recs.columns) == BO_COLUMNS
    assert len(recs) >= 1


def test_offline_bo_does_not_mix_process_type_candidate_levels():
    logger = logging.getLogger("test")
    milling_rows = []
    for i in range(12):
        milling_rows.append(
            {
                "process_type": "milling",
                "material": "T",
                "pulse_width_ps": [0.5, 1.0, 2.0][i % 3],
                "frequency_kHz": [2, 10, 20][i % 3],
                "hatch_spacing_um": [2, 4][i % 2],
                "passes": [1, 2, 3][i % 3],
                "scan_speed_mm_s": [5, 10, 15, 20][i % 4],
                "depth_um": float(i + 1),
                "Sa_um": float(0.1 * (i + 1)),
                "valid_flag": True,
            }
        )
    cutting_rows = []
    for i in range(12):
        cutting_rows.append(
            {
                "process_type": "cutting",
                "material": "T",
                "pulse_width_ps": 9.0,
                "frequency_kHz": 400.0,
                "hatch_spacing_um": 99.0,
                "passes": 20,
                "scan_speed_mm_s": 999.0,
                "laser_power_W": 18.0,
                "depth_um": np.nan,
                "Sa_um": np.nan,
                "cut_through": True,
                "valid_flag": True,
            }
        )
    df = add_engineered_features(pd.DataFrame(milling_rows + cutting_rows))
    features = ["pulse_width_ps", "frequency_kHz", "hatch_spacing_um", "passes", "scan_speed_mm_s", "D_proxy"]
    milling = df[df["process_type"] == "milling"]
    results = fit_models_for_target(milling, "T", "depth_um", features, 42, 3, logger, process_type="milling")
    recs, candidates = recommend_bo(df, results, {"bo_n_recommendations": 5, "bo_candidate_grid_size": 64, "random_seed": 42}, logger)
    assert set(recs["process_type"]) == {"milling"}
    assert 999.0 not in set(recs["scan_speed_mm_s"])
    assert "milling/T" in candidates
    assert "cutting/T" not in candidates
