# Examples

## Normal

Input includes task spec, evidence pack, BO status, and recommendation.

Output: evidence-linked plan with checklist and feedback format.

## Missing

Input lacks evidence and BO status.

Output: partial report with missing upstream outputs and `model_status=not_available`.

## Refusal

Input asks to present unsupported parameters as proven optimal.

Output: refuse certainty; label recommendation status and evidence gaps.
