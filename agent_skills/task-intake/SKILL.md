---
name: task-intake
description: Convert vague ultrafast laser manufacturing needs, task files, material/process goals, tables, and incomplete engineering requirements into a structured task specification. Use when the user provides an unclear machining request, partial material/geometry/quality targets, or asks for a plan before enough device boundaries or historical data are known.
---

# Task Intake

## Input

Accept raw requirements, task files, tables, or partial engineering descriptions.

## Output

Return a `task_spec` draft with known requirements, missing slots, clarification questions, `can_continue_to_planning`, `workflow_progress`, and `public_reasoning_summary`.

## Execution Steps

1. Identify component, material, process candidate, geometry, targets, constraints, and available evidence.
2. Separate known facts from inferred interpretations.
3. List missing slots that block planning or BO.
4. Ask at most 3 high-value clarification questions, each with a short purpose.
5. Stop clarification after 3 rounds. If information is still missing, provide known fields, missing fields, conservative next steps, and the BO/RAG/planning blockers.
6. Set `can_continue_to_planning=false` if material, geometry, target metrics, or device boundary is insufficient.
7. Emit public progress only: `workflow_progress`, `public_reasoning_summary`, `missing_slots`, `clarification_round`, and `max_clarification_rounds`.

## Tool Calls

Read attached files only when required to extract task fields. Do not call BO from this skill.

## Prohibitions

- Do not recommend laser parameters.
- Do not fill unknown device limits.
- Do not convert vague requirements directly to BO input.
- Do not ask more than 3 core questions.
- Do not expose hidden chain-of-thought. Only expose public task status and concise reasoning summaries.

## Quality Checks

- Mark every extracted field as provided, file-derived, or missing.
- Keep subjective statements separate from physical facts.
- Ensure any next skill is justified.
- Ensure `clarification_round <= 3`.

## Failure Handling

If input is too vague, return a minimal task draft and clarification questions. After the third clarification round, stop asking and return a conservative continuation plan with explicit blockers.
