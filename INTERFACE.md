# Interactive BO Interface Contract

This document defines the stable interface for the interactive Bayesian optimization demo.

## 1. `task_request.json`

Required:

- `material`: one of the materials available in the processed experiment table.
- `objective_mode`: `quality_first`, `efficiency_first`, or `balanced`.

Optional:

- `target_depth_um`
- `depth_min_um`
- `Sa_max_um`
- `recommendation_type`: `exploitation`, `exploration`, or `balanced`.
- `parameter_bounds`: per-parameter `[min, max]` bounds. The system intersects user bounds with historical observed ranges and rejects empty intersections.

Example:

```json
{
  "material": "SiC",
  "objective_mode": "quality_first",
  "target_depth_um": 30,
  "depth_min_um": 25,
  "Sa_max_um": 2.0,
  "recommendation_type": "balanced"
}
```

## 2. `recommendation.json`

Core fields:

- `task_id`
- `iteration`
- `material`
- `objective_mode`
- `recommended_parameters`
- `prediction`
- `acquisition`
- `D_proxy`
- `reason`

Audit fields:

- `bo_component`: GPR surrogate, acquisition type, predicted mean, predicted std, objective value, raw BO acquisition score.
- `feedback_interpretation`: five-level feedback values, numeric mapping, directional interpretation, conflict flag, conflict resolution.
- `feedback_rule_component`: whether feedback rules were applied, rule strength, score penalty or bias.
- `final_selection_reason`: final selection statement after combining BO and feedback adjustment.

The final candidate is selected by BO acquisition score after optional feedback-direction adjustment. Five-level feedback changes candidate scores or feasible ranking; it does not replace the surrogate model.

## 3. `feedback.json`

Required:

- `task_id`
- `iteration`

Optional numeric feedback:

- `measured_result.depth_um`
- `measured_result.Sa_um`
- `measured_result.processing_time_s`

Optional qualitative feedback:

- `qualitative_feedback.roughness`
- `qualitative_feedback.depth`
- `qualitative_feedback.efficiency`
- `note`

Numeric feedback can be appended to `data/processed/updated_experiments.csv`. Qualitative feedback is never fabricated into numeric measurements.

## 4. `task_state.json`

The task state stores:

- initialization configuration
- parameter bounds
- model availability flags
- complete recommendation history
- complete feedback history
- whether numeric feedback updated the training table
- whether qualitative feedback rules adjusted recommendation ranking

## 5. Five-Level Mapping

Internal mapping:

| level | score |
|---|---:|
| 很小 | -2 |
| 较小 | -1 |
| 适中 | 0 |
| 较大 | +1 |
| 很大 | +2 |

Metric-specific interpretation:

- Roughness: positive scores mean roughness is too large; the search favors lower `D_proxy`, fewer passes, higher scan speed, or wider hatch spacing.
- Depth: negative scores mean removal is insufficient; the search favors higher `D_proxy`.
- Efficiency: negative scores mean efficiency is insufficient; the search favors higher removal intensity under the selected objective and constraints.

`D_proxy = frequency_kHz * passes / (scan_speed_mm_s * hatch_spacing_um)` is a cumulative pulse action density proxy, not strict energy density.

## 6. Legacy Feedback Compatibility

Legacy values remain accepted:

- `acceptable` -> `适中`
- `too_large` -> `较大`
- `too_small` -> `较小`
- `too_shallow` -> `较小`
- `too_deep` -> `较大`
- `too_low` -> `较小`
- `too_high` -> `较大`
- `unknown` -> `unknown`

The state and logs store the normalized five-level values.

## 7. Recommendation Logic

The backend separates two components:

1. BO component: GPR surrogate predicts `depth_um` and `Sa_um`; acquisition scores candidates by `exploitation`, `exploration`, or `balanced`.
2. Feedback rule component: qualitative feedback applies directional penalties or biases to the acquisition score.

If feedback directions conflict, the system records `conflict=true` and resolves by objective:

- `quality_first`: prioritize roughness reduction and quality constraints.
- `efficiency_first`: prioritize removal/efficiency while respecting roughness constraints in the objective.
- `balanced`: use a weighted tradeoff.

## 8. Minimal Third-Party Test Flow

```bash
python main.py init-task --config config.yaml --material SiC --objective quality_first --target-depth 30 --sa-max 2.0
python main.py recommend --task-id SiC_YYYYMMDD_001 --type balanced
python main.py feedback --task-id SiC_YYYYMMDD_001 --iteration 1 --roughness 很大 --depth-status 适中 --efficiency 很小
python main.py recommend-next --task-id SiC_YYYYMMDD_001 --type balanced
python main.py export-task --task-id SiC_YYYYMMDD_001
```

Expected checks:

- Stronger roughness feedback should produce stronger downward pressure on `D_proxy`.
- Stronger insufficient-efficiency feedback should produce stronger upward pressure on removal intensity.
- Conflicting feedback should set `feedback_interpretation.suggested_direction.conflict=true`.
- `bo_component` and `feedback_rule_component` must both be present in `recommendation.json`.
