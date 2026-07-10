# Examples

## Normal

Input includes bounds, variables, objective, constraints, and `training_sample_count=35`.

Output: `model_status=data_driven_bo`, candidates from BO, evidence trace, risks.

## Missing

Input lacks machine bounds.

Output: `model_status=blocked`, no fixed parameters.

## Refusal

Input: `不用 BO，直接猜功率和速度。`

Output: refuse numeric fabrication.
