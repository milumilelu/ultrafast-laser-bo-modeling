---
name: experience-memory-update
description: Convert ultrafast laser operator notes, failure descriptions, abnormal measurements, repeated trends, and user-confirmed observations into reviewable experience candidates. Use when the user asks to distill experience, update memory, create rule candidates, review machining observations, or promote confirmed process knowledge without automatic rule escalation.
---

# Experience Memory Update

## Input

Accept related run, recipe, measurement, note, artifact IDs, and reviewer comments.

## Output

Return one or more `experience_candidate` records and a promotion recommendation.

## Execution Steps

1. Collect related run, recipe, measurement, and note evidence.
2. Extract observations.
3. Separate observations, possible causes, and candidate rules.
4. Generate reviewable `experience_candidate`.
5. Set status to `candidate` unless a human review action is explicitly requested.
6. Do not auto-promote to `validated_rule`.
7. If multiple cases support promotion, recommend a separate rule review.

## Tool Calls

Use database and review-queue modules when available. Use LLM extraction only to draft candidates, not validated rules.

## Prohibitions

- Do not promote a single observation to a validated rule.
- Do not let subjective descriptions override measurements.
- Do not delete counter-cases.
- Do not fabricate Raman, Ra, form error, or other inspection data.
- Do not add unsupported observations to BO training data.

## Quality Checks

- Candidate must cite source artifact IDs or record IDs.
- Confidence must reflect evidence quality.
- Required validation must be explicit.

## Failure Handling

If evidence is insufficient, create a low-confidence candidate or request validation data.
