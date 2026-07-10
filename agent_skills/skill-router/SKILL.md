---
name: skill-router
description: Route ultrafast laser agent requests to the correct workflow skill. Use when the user request may involve task intake, diamond CRL planning, literature/RAG evidence retrieval, Bayesian optimization parameter recommendation, process file ingestion, experience memory update, BO dataset governance, report generation, or any ambiguous ultrafast-laser workflow that needs deterministic skill selection.
---

# Skill Router

## Input

Accept raw user text, attached-file summaries, and optional current workflow state.

## Output

Return `selected_skill`, `confidence`, `reason`, and `required_next_action`. Use names from `routing_rules.json`.

## Execution Steps

1. Read `routing_rules.json`.
2. Identify explicit task intent and attached-file type.
3. Prefer the most specific skill over a broad skill.
4. If multiple skills apply, output the first skill and list follow-up skills in `required_next_action`.
5. If confidence is below 0.55, select `task-intake` and ask at most 3 clarifying questions.

## Tool Calls

Use no external tools unless the user asks to inspect files. This skill routes; it does not execute downstream workflows.

## Prohibitions

- Do not answer domain questions directly.
- Do not recommend process parameters.
- Do not treat routing as evidence retrieval or BO output.
- Do not invent missing task fields.

## Quality Checks

- Ensure `selected_skill` is one of the configured skills.
- Ensure the reason cites the request feature that caused routing.
- Ensure ambiguous requests default to `task-intake`.

## Failure Handling

If routing cannot be resolved, return `task-intake` with low confidence and concrete missing information.
