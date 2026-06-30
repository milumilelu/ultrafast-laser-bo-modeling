# Multi-Process Recommendation Interface

This document is the stable contract for the interactive ultrafast-laser process recommendation interface.

## 1. Process Types

`process_type` is required in new requests and persisted in every task, feedback, recommendation, and log.

Allowed values:

- `milling`: data-driven or hybrid BO for existing face/milling data.
- `cutting`: schema, UI, cold-start rules, and feedback loop. Current repository has no cutting experiment data, so cutting does not train a surrogate model yet.

Legacy requests without `process_type` are treated as `milling`.

## 2. Unified Data Schema

The unified experiment table supports these columns. Missing fields remain `NaN`; the system does not fabricate values.

```text
record_id
process_type
material
pulse_width_ps
frequency_kHz
laser_power_W
scan_speed_mm_s
passes
focus_offset_um
fill_pattern
hatch_spacing_um
layer_step_um
path_overlap_um
material_thickness_um
cut_length_mm
power_W
depth_um
Sa_um
Sq_um
Sz_um
removal_rate_um3_s
cut_through
kerf_top_width_um
kerf_bottom_width_um
kerf_taper_deg
cut_edge_Sa_um
HAZ_width_um
chipping_um
objective_mode
source_file
valid_flag
note
```

Milling targets are mainly `depth_um`, `Sa_um`, `Sq_um`, `Sz_um`, and `removal_rate_um3_s`.
Cutting targets are mainly `cut_through`, kerf geometry, edge roughness, HAZ, and chipping fields.

## 3. Fill Pattern Mapping

The UI displays Chinese labels and saves stable internal enums.

| UI label | enum |
|---|---|
| 弓字形 | `zigzag` |
| 回字形/轮廓 | `contour` |
| 同心圆 | `concentric` |
| 折线 | `polyline` |
| 螺旋 | `spiral` |
| 无填充/单线切割 | `none` |
| 自定义 | `custom` |

## 4. Feature Engineering

Existing features are retained:

- `log_pulse_width`
- `log_frequency`
- `log_hatch_spacing`
- `log_passes`
- `log_scan_speed`
- `D_proxy`
- `pulse_density_proxy`

New power and cutting features:

- `pulse_energy_uJ = 1000 * laser_power_W / frequency_kHz`
- `areal_energy_proxy = laser_power_W * passes / (scan_speed_mm_s * hatch_spacing_um)`
- `pulse_density_proxy = frequency_kHz * passes / (scan_speed_mm_s * hatch_spacing_um)`
- `line_energy_proxy = laser_power_W / scan_speed_mm_s`
- `pulse_spacing_um = scan_speed_mm_s / frequency_kHz`
- `layer_count_proxy = target_depth_um / layer_step_um` when `target_depth_um` exists

`laser_power_W` is more physically meaningful than the old pulse-density-only `D_proxy`. Old data missing `laser_power_W` keep power-derived features as `NaN`; the code must not invent power.

## 5. `task_request.json`

Required:

- `process_type`: `milling` or `cutting`; omitted legacy value defaults to `milling`.
- `material`
- `objective_mode`: `quality_first`, `efficiency_first`, or `balanced`

Optional:

- `requirements`
- `parameter_bounds`
- `target_depth_um`, `depth_min_um`, `Sa_max_um` for milling
- `recommendation_type`: `exploitation`, `exploration`, or `balanced`

Cutting example:

```json
{
  "process_type": "cutting",
  "material": "SiC",
  "objective_mode": "quality_first",
  "requirements": {
    "material_thickness_um": 500,
    "cut_through_required": true,
    "target_kerf_width_um": 30,
    "max_taper_deg": 3,
    "max_edge_Sa_um": 2.0
  },
  "parameter_bounds": {
    "pulse_width_ps": [0.3, 10],
    "frequency_kHz": [50, 500],
    "laser_power_W": [1, 20],
    "scan_speed_mm_s": [10, 1000],
    "passes": [1, 30],
    "focus_offset_um": [-100, 100],
    "layer_step_um": [1, 20],
    "hatch_spacing_um": [1, 20],
    "fill_pattern": ["none", "contour", "polyline"]
  }
}
```

## 6. `feedback.json`

Milling qualitative fields:

- `surface_roughness_level` or legacy `roughness`
- `depth_level` or legacy `depth`
- `efficiency_level` or legacy `efficiency`

Cutting qualitative fields:

- `cut_through_level`
- `kerf_width_level`
- `edge_roughness_level`
- `taper_level`
- `chipping_level`
- `efficiency_level`

Cutting `cut_through_level` values:

- `未切透`
- `勉强切透`
- `适中`
- `过烧蚀`
- `严重过烧蚀`

Other qualitative fields use:

```text
很小 = -2
较小 = -1
适中 = 0
较大 = +1
很大 = +2
```

The score is only a common internal scale. Metric direction is process-specific:

- Roughness `较大/很大`: reduce heat input or energy accumulation.
- Depth `较小/很小`: increase removal intensity.
- Milling efficiency `较小/很小`: favor higher removal intensity subject to objective constraints.
- Cutting `未切透`: raise `laser_power_W`, lower `scan_speed_mm_s`, increase `passes`, reduce `layer_step_um`.
- Cutting `过烧蚀/严重过烧蚀`: lower `laser_power_W`, raise `scan_speed_mm_s`, reduce `passes`, increase `layer_step_um`.

Legacy values remain accepted: `acceptable`, `too_large`, `too_small`, `too_shallow`, `too_deep`, `too_low`, `too_high`, `unknown`.

## 7. `recommendation.json`

Required core fields:

- `task_id`
- `iteration`
- `process_type`
- `material`
- `model_status`
- `objective_mode`
- `recommended_parameters`
- `prediction`
- `acquisition`
- `reason`

Audit fields:

- `bo_component`
- `feedback_interpretation`
- `feedback_rule_component`
- `final_selection_reason`

For cutting cold start, unavailable predictions are explicit `null`, for example:

```json
{
  "model_status": "rule_based_cold_start",
  "prediction": {
    "cut_through_probability": null,
    "kerf_top_width_um": null,
    "kerf_bottom_width_um": null,
    "kerf_taper_deg": null,
    "cut_edge_Sa_um": null,
    "HAZ_width_um": null,
    "chipping_um": null
  },
  "bo_component": {
    "surrogate_model": null,
    "acquisition": null
  }
}
```

## 8. `task_state.json`

The state stores:

- `process_type`
- material and objective
- requirements and parameter bounds
- sample count by `process_type + material`
- `model_status`
- model availability flags
- full recommendation and feedback history
- warning messages

## 9. Model Status

Interactive `model_status` is computed by valid sample count scoped to `process_type + material`.
Target-specific surrogate availability is checked separately when fitting each model target.

| valid samples | status |
|---:|---|
| `< 10` | `rule_based_cold_start` |
| `10-29` | `hybrid_rule_bo` |
| `>= 30` | `data_driven_bo` |

Current limitation: this repository has no valid cutting data. Cutting recommendations therefore return `model_status = "rule_based_cold_start"`. They are not trained BO predictions. After cutting data are accumulated, the same interface can switch to `hybrid_rule_bo` or `data_driven_bo`.

## 10. Recommendation Logic

Offline modeling and offline BO:

1. Group data by `process_type + material`.
2. For `milling`, fit only milling targets such as `depth_um` and `Sa_um`.
3. For `cutting`, use cutting targets such as `cut_through`, kerf geometry, edge roughness, and chipping when real cutting rows exist.
4. Generate offline BO candidate grids inside the same `process_type + material` group. Cutting candidates keep cutting parameters such as `laser_power_W`, `layer_step_um`, `focus_offset_um`, and `fill_pattern` separate from milling candidates.

Milling:

1. Fit GPR surrogates when data are sufficient.
2. Score candidates with an acquisition function.
3. Apply qualitative feedback as an acquisition penalty or bias.
4. Record both BO and feedback-rule components.

Cutting today:

1. Validate schema and requirements.
2. Select conservative parameters within user bounds.
3. Apply feedback-direction rules after each iteration.
4. Keep prediction fields `null` because no cutting surrogate is trained.

Conflict handling is explicit. Example: `roughness=很大` and `efficiency=很小` sets `conflict=true`; resolution depends on `objective_mode`.

## 11. CLI Flow

```bash
python main.py recommend --process-type milling --material SiC --objective quality_first
python main.py recommend --process-type cutting --material SiC --objective quality_first
python main.py feedback --task-id SiC_YYYYMMDD_001 --iteration 1 --roughness 很大 --depth-status 适中
python main.py feedback --feedback inputs/feedback.json
python main.py recommend-next --task-id SiC_YYYYMMDD_001
```

Cutting feedback should use `feedback-json` or `feedback --feedback inputs/feedback.json`; the plain `feedback` flags are kept for milling compatibility.

## 12. Third-Party Test Flow

```bash
python main.py run-json --task-request inputs/task_request.json
```

Expected checks for cutting without data:

- `process_type = "cutting"`
- `model_status = "rule_based_cold_start"`
- cutting prediction fields are `null`
- `bo_component.surrogate_model = null`
- recommendation does not crash without cutting rows

Feedback-direction checks:

- `cut_through_level = 未切透` should push toward higher `laser_power_W`, lower `scan_speed_mm_s`, more `passes`, and smaller `layer_step_um`.
- `cut_through_level = 严重过烧蚀` should push toward lower `laser_power_W`, higher `scan_speed_mm_s`, fewer `passes`, and larger `layer_step_um`.
- conflicting directions must set `conflict=true` and record `resolution`.
