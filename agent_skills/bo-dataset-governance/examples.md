# Examples

## Normal

Completed run, no alarms, complete recipe, valid Ra measurement.

Output: valid sample with x/y fields.

## Missing

Run has no linked recipe.

Output: invalid with reason `missing recipe`.

## Refusal

Input asks to use `效果不错` as objective value.

Output: reject subjective note as numeric BO target.
