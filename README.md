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

## Interactive Bayesian Optimization Demo

See [INTERFACE.md](INTERFACE.md) for the stable JSON schema, feedback-level mapping, compatibility rules, and third-party test contract.

The interactive module adds a closed-loop recommendation workflow:

select material -> choose objective -> recommend one process setting -> submit feedback -> update task state -> recommend the next setting.

It does not control laser hardware and does not claim that one recommendation is a global optimum.

### CLI

Initialize a task:

```bash
python main.py init-task --config config.yaml --material SiC --objective quality_first --target-depth 30 --sa-max 2.0
```

Recommend parameters:

```bash
python main.py recommend --task-id SiC_20260101_001 --type balanced
```

Submit feedback with the new five-level qualitative scale:

```bash
python main.py feedback --task-id SiC_20260101_001 --iteration 1 --depth 28.7 --sa 2.4 --roughness 较大 --depth-status 适中
```

Legacy qualitative values are still accepted for compatibility: `acceptable`, `too_large`, `too_small`, `too_shallow`, `too_deep`, `too_low`, `too_high`, and `unknown`. Internally they are mapped to the five-level scale.

Recommend after feedback:

```bash
python main.py recommend-next --task-id SiC_20260101_001 --type balanced
```

Export task logs:

```bash
python main.py export-task --task-id SiC_20260101_001
```

JSON interface:

```bash
python main.py run-json --task-request inputs/task_request.json
python main.py feedback-json --feedback inputs/feedback.json
```

### UI

Run:

```bash
python -m streamlit run src/ui_app.py
```

The UI contains task settings, parameter recommendation, machining feedback, and task history panels.

### JSON Examples

`inputs/task_request.json`:

```json
{
  "material": "SiC",
  "objective_mode": "quality_first",
  "target_depth_um": 30,
  "depth_min_um": 25,
  "Sa_max_um": 2.0,
  "recommendation_type": "balanced",
  "parameter_bounds": {
    "pulse_width_ps": [0.3, 10],
    "frequency_kHz": [2, 50],
    "hatch_spacing_um": [2, 20],
    "passes": [1, 10],
    "scan_speed_mm_s": [20, 200]
  }
}
```

`inputs/feedback.json`:

```json
{
  "task_id": "SiC_20260101_001",
  "iteration": 1,
  "measured_result": {
    "depth_um": 28.7,
    "Sa_um": 2.4,
    "processing_time_s": 36.0
  },
  "qualitative_feedback": {
    "roughness": "较大",
    "depth": "适中",
    "efficiency": "适中"
  },
  "note": "Surface roughness exceeds requirement."
}
```

### Interactive Outputs

- `outputs/recommendation.json`
- `outputs/task_state.json`
- `outputs/recommendation_log.csv`
- `outputs/feedback_log.csv`
- `outputs/tasks/*_task_state.json`
- `data/processed/updated_experiments.csv`

### Interactive Method Limits

If only qualitative feedback is provided, the system does not fabricate numeric labels. Qualitative feedback uses five levels: `很小`, `较小`, `适中`, `较大`, `很大`. Larger roughness favors lower `D_proxy`; smaller depth favors higher `D_proxy`; smaller efficiency favors faster scan speed and fewer passes. The old categorical values remain supported as aliases.

Only measured `depth_um` and/or `Sa_um` are appended to the training table. Missing measured values remain missing.

The current `efficiency_first` objective uses depth as the efficiency proxy. If reliable `processing_time_s` is collected, a future version can use `depth_um / processing_time_s`.

`D_proxy` remains a pulse-action-density proxy, not strict energy density, because power, spot diameter, defocus, and pulse energy may be unavailable. Every recommendation requires experimental validation.
