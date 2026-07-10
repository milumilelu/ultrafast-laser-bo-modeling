---
name: crl-task-planning
description: Plan diamond CRL, compound refractive lens, X-ray lens, curvature-radius, focal-length, aperture, lens-count, photon-energy, parabola-spacing, and micromachining workflows. Use when a user asks about diamond refractive lenses, CRL, X-ray refractive lenses, optical consistency, manufacturing risks, or CRL-specific experiment planning.
---

# CRL Task Planning

## Input

Accept CRL geometry, optical targets, material, manufacturing target metrics, and available task context.

## Output

Return `crl_task_spec`, optical consistency check, manufacturing risks, required clarifications, recommended workflow, `workflow_progress`, and `public_reasoning_summary`.

## Execution Steps

1. Extract material, radius, aperture, thickness, lens count, photon energy, focal length, and surface targets.
2. Check whether `R`, `N`, `E`, and `f` are mutually plausible when enough data exists.
3. Identify whether the request is manufacturing planning, parameter recommendation, or experiment design.
4. List CRL-specific risks: form error, focal-length error, roughness, graphitization, edge chipping, subsurface damage, alignment error.
5. If parameter recommendation is needed, hand off to `bo-recommendation`.
6. Stop clarification after 3 rounds. If geometry, optical target, material grade, device boundary, or post-processing permission remains missing, provide a conservative planning path and explicit BO/RAG blockers.

## Tool Calls

Use calculators or structured task files when available. Use RAG only when evidence or prior ranges are requested.

## Prohibitions

- Do not treat `Ra < 460 nm` as proof of optical qualification.
- Do not ignore form error, focal-length error, or assembly error.
- Do not reuse flat milling parameters as CRL parameters.
- Do not call BO for fixed parameters without machine bounds and data status.
- Do not expose hidden chain-of-thought. Only expose public task status and concise reasoning summaries.

## Quality Checks

- State which optical fields are checked and which are missing.
- Keep manufacturing risk separate from optical qualification.
- Include next required skill when planning cannot continue.
- Ensure `clarification_round <= 3` and each clarification question states its purpose.

## Failure Handling

If CRL geometry or optical data is incomplete, return the missing fields and at most 3 questions. After the third clarification round, stop asking and return the conservative workflow boundary.
