# Ultrafast Laser Process Modeling and BO Recommendation

This project builds a reproducible workflow for:

1. input data cleaning and schema unification
2. feature engineering
3. per-material machine learning models
4. key parameter identification
5. offline Bayesian optimization recommendations
6. exportable tables, figures and Markdown reports

## Install

```bash
python -m pip install -r requirements.txt
```

`xgboost` is optional. If it is not installed, the workflow automatically uses `HistGradientBoostingRegressor`.

## Run

```bash
python main.py --config config.yaml
```

## Input Data

The default `config.yaml` reads:

- `AlSiC.csv`
- `CFRP.csv`
- `SiC.csv`
- `ZrO2.csv`
- `金刚石实验结果.xlsx`

CSV files are read with robust encoding fallback. Excel files are read with `openpyxl`.

The unified schema is:

- `material`
- `pulse_width_ps`
- `frequency_kHz`
- `hatch_spacing_um`
- `passes`
- `scan_speed_mm_s`
- `power_W`
- `depth_um`
- `Sa_um`
- `Sq_um`
- `Sz_um`
- `source_file`
- `valid_flag`
- `note`

Missing fields are retained as `NaN`. Critical process parameters are not filled by arbitrary means.

## Outputs

- `data/processed/unified_experiments.csv`
- `data/processed/data_quality_report.csv`
- `data/processed/unified_experiments_with_features.csv`
- `outputs/data_schema_summary.md`
- `outputs/model_performance_summary.csv`
- `outputs/prediction_results.csv`
- `outputs/feature_importance_summary.csv`
- `outputs/response_curves.csv`
- `outputs/bo_recommendations.csv`
- `outputs/modeling_report.md`
- `figures/*.png`

## Configure Targets and Constraints

Edit `config.yaml`:

```yaml
target_depth_by_material:
  AlSiC: 20
  CFRP: 30
Sa_max_by_material:
  AlSiC: 2.0
  CFRP: 3.0
bo_mode: target_depth_min_sa
```

If `target_depth_by_material` is empty, the BO module uses the observed median depth for that material and records this in the recommendation notes. For constrained optimization, set:

```yaml
bo_mode: constrained_depth
```

## Method Limits

`D_proxy = frequency_kHz * passes / (scan_speed_mm_s * hatch_spacing_um)` is a cumulative pulse action density proxy, not a strict energy density. If `power_W`, spot diameter, pulse energy and defocus are missing, the models are statistical surrogate models rather than complete physical causal models. BO recommendations are next-experiment candidates and require experimental validation; they are not global optima.
