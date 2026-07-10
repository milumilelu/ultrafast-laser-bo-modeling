---
name: bo-dataset-governance
description: Govern whether ultrafast laser experiment records can enter Bayesian optimization training data. Use when exporting BO datasets, updating training samples, judging if a run is valid_for_training, handling abnormal logs, checking measurement quality, standardizing units, or constructing BO-compatible CSV data.
---

# BO Dataset Governance

## Input

Accept run, recipe, task, measurement records, unit status, and abnormal/alarm status.

## Output

Return `valid_for_training`, invalid reasons, x parameters, y metrics, and warnings.

## Execution Steps

1. Check `run_status == completed`.
2. Check `abnormal_flag == 0` and no alarms.
3. Check recipe key parameters.
4. Check material and process type.
5. Check at least one valid quality metric.
6. Check standardized units.
7. Check sample/run/recipe/measurement linkage.
8. Export only eligible samples as training data.

## Tool Calls

Use repository validation and dataset-builder modules when available.

## Prohibitions

- Do not fill missing measurements.
- Do not ignore alarms or interruptions.
- Do not use subjective notes as numeric metrics.
- Do not include data with unknown units.

## Quality Checks

- Invalid samples must include reasons.
- X parameters and Y metrics must be separated.
- Output must preserve traceability.

## Failure Handling

If any required relation is missing, mark invalid and return the missing relation.
