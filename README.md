# Ultrafast Laser Multi-Process BO Recommendation

This repository builds a reproducible code framework for ultrafast-laser process parameter modeling and recommendation.

Current supported workflow:

```text
process_type -> material -> objective_mode -> process_parameters -> recommend -> feedback -> recommend-next
```

Supported process types:

- `milling`: existing data-driven or hybrid Bayesian optimization workflow for face/milling process data.
- `cutting`: schema, interface, UI, cold-start rule recommendation, and feedback loop.

Important limitation: the current repository has no cutting experiment data. Cutting recommendations are therefore `rule_based_cold_start`, not trained BO model predictions. Cutting prediction fields remain `null` until valid cutting data are collected.

## Install

```bash
python -m pip install -r requirements.txt
```

`xgboost` is optional. If unavailable, the offline modeling pipeline falls back to `HistGradientBoostingRegressor`.

## Offline Modeling Pipeline

```bash
python main.py --config config.yaml
```

Offline modeling and offline BO are grouped by `process_type + material`. Milling and cutting rows are never fitted into the same target model. Current milling targets are `depth_um` and `Sa_um`; cutting targets are prepared as `cut_through`, `kerf_top_width_um`, `kerf_taper_deg`, `cut_edge_Sa_um`, and `chipping_um`, but no cutting surrogate is trained until real cutting rows exist.

Main outputs:

- `data/processed/unified_experiments.csv`
- `data/processed/unified_experiments_with_features.csv`
- `data/processed/data_quality_report.csv`
- `outputs/model_performance_summary.csv`
- `outputs/feature_importance_summary.csv`
- `outputs/bo_recommendations.csv`
- `outputs/modeling_report.md`
- `figures/*.png`

## Unified Schema

The unified experiment table includes both milling and cutting fields:

```text
record_id, process_type, material,
pulse_width_ps, frequency_kHz, laser_power_W, scan_speed_mm_s, passes,
focus_offset_um, fill_pattern, hatch_spacing_um, layer_step_um, path_overlap_um,
material_thickness_um, cut_length_mm,
depth_um, Sa_um, Sq_um, Sz_um, removal_rate_um3_s,
cut_through, kerf_top_width_um, kerf_bottom_width_um, kerf_taper_deg,
cut_edge_Sa_um, HAZ_width_um, chipping_um,
objective_mode, source_file, valid_flag, note
```

Missing fields are retained as `NaN`. Old data without `laser_power_W` keep power-derived features as `NaN`; the system does not fabricate laser power.

## Feature Engineering

Legacy pulse-density features are retained:

- `D_proxy`
- `pulse_density_proxy`
- log-transformed pulse width, frequency, hatch spacing, passes, and scan speed

New power and cutting features:

- `pulse_energy_uJ = 1000 * laser_power_W / frequency_kHz`
- `areal_energy_proxy = laser_power_W * passes / (scan_speed_mm_s * hatch_spacing_um)`
- `line_energy_proxy = laser_power_W / scan_speed_mm_s`
- `pulse_spacing_um = scan_speed_mm_s / frequency_kHz`
- `layer_count_proxy = target_depth_um / layer_step_um` when target depth exists

After adding `laser_power_W`, `pulse_energy_uJ` and `areal_energy_proxy` are more physically meaningful than using only `D_proxy`.

## Interactive CLI

Milling recommendation:

```bash
python main.py recommend --process-type milling --material SiC --objective quality_first
```

Cutting cold-start recommendation:

```bash
python main.py recommend --process-type cutting --material SiC --objective quality_first
```

Existing task:

```bash
python main.py recommend --task-id SiC_YYYYMMDD_001 --type balanced
python main.py feedback --task-id SiC_YYYYMMDD_001 --iteration 1 --roughness 很大 --depth-status 适中 --efficiency 很小
python main.py recommend-next --task-id SiC_YYYYMMDD_001 --type balanced
```

JSON interface:

```bash
python main.py run-json --task-request inputs/task_request.json
python main.py feedback --feedback inputs/feedback.json
python main.py feedback-json --feedback inputs/feedback.json
```

Old commands without `--process-type` default to `milling`.

For cutting feedback, use the JSON interface (`feedback-json` or `feedback --feedback`) because the plain feedback CLI flags only cover the legacy milling fields `roughness/depth/efficiency`.

## UI

```bash
python -m streamlit run src/ui_app.py
```

The UI supports:

- process selection: 铣削 / 切割
- laser power bounds
- fill pattern selection with stable internal enums
- hatch spacing and layer-step inputs
- cutting requirements: material thickness, cut-through requirement, target kerf width, max taper, max edge roughness
- process-specific feedback forms

Chinese fill-pattern labels map to internal enums:

- 弓字形 -> `zigzag`
- 回字形/轮廓 -> `contour`
- 同心圆 -> `concentric`
- 折线 -> `polyline`
- 螺旋 -> `spiral`
- 无填充/单线切割 -> `none`
- 自定义 -> `custom`

## Model Status

`model_status` is returned in every recommendation:

- `rule_based_cold_start`: fewer than 10 valid samples
- `hybrid_rule_bo`: 10 to 29 valid samples
- `data_driven_bo`: at least 30 valid samples

The interactive task status count is scoped by `process_type + material`. Target-specific surrogate availability is checked separately during model fitting. Cutting currently returns `rule_based_cold_start` because no cutting data are present.

## Feedback

Five-level feedback is normalized internally:

```text
很小 = -2
较小 = -1
适中 = 0
较大 = +1
很大 = +2
```

Metric direction is not shared blindly across fields:

- Milling roughness too large reduces energy accumulation.
- Milling depth too small increases removal intensity.
- Cutting not-through increases cutting intensity.
- Cutting overburn reduces heat input.

Legacy values remain accepted: `acceptable`, `too_large`, `too_small`, `too_shallow`, `too_deep`, `too_low`, `too_high`, `unknown`.

## Interface Contract

See [INTERFACE.md](INTERFACE.md) for:

1. `task_request.json` schema
2. `feedback.json` schema
3. `recommendation.json` schema
4. `task_state.json` schema
5. five-level feedback mapping
6. legacy compatibility rules
7. BO acquisition plus feedback-direction adjustment
8. cutting cold-start limitations
9. third-party test flow

## Tests

```bash
pytest -q
```

The tests cover milling backward compatibility, fill-pattern mapping, power feature units, cutting cold-start behavior, cutting feedback direction, and `model_status` thresholds.
