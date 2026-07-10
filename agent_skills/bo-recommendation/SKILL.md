---
name: bo-recommendation
description: Prepare or call Bayesian optimization recommendations for ultrafast laser machining parameters. Use when the user asks to recommend next-round parameters, optimize experiments, update parameters from feedback, or invoke BO. Enforces that LLM must not fabricate laser power, frequency, scan speed, hatch spacing, layer step, focus offset, passes, or predicted metrics.
---

# BO Recommendation

## Input

Require material, process type, objective mode, machine bounds, decision variables, target metrics, constraints, and training sample count.

## Output

Return `model_status`, recommendations, evidence trace, risks, and next experiment plan.

## Execution Steps

1. Check task completeness.
2. Check machine bounds and decision variables.
3. Check target function and constraints.
4. Query or receive training sample count.
5. Set model status:
   - `<10`: `rule_based_cold_start`
   - `10-29`: `hybrid_rule_bo`
   - `>=30`: `data_driven_bo`
6. Construct BO input.
7. Call BO engine only when available.
8. Filter dangerous or unsupported parameters with rules and evidence.
9. Output candidate parameters only if they come from BO, bounds, rules, user input, or cited evidence.

## Tool Calls

Use the repository BO interface or `ultrafast_memory.bo.bo_engine_adapter` if available. Do not invent fallback numeric parameters.

## Prohibitions

- Do not generate numeric process parameters from LLM reasoning alone.
- Do not call BO data-driven when sample count is insufficient.
- Do not state BO output as measured optimum.
- Do not omit `model_status`.
- Do not output fixed parameters if machine bounds are missing.

## Quality Checks

- Every numeric parameter must have a source.
- Include uncertainty or mark it unavailable.
- Include risks and next feedback format.

## Failure Handling

If BO is unavailable, return `model_status=not_connected` or the cold-start status and request missing inputs.
