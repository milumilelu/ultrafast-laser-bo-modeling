---
name: report-generation
description: Generate evidence-linked ultrafast laser task plans, execution checklists, process recommendations, experiment designs, failure analyses, optimization plans, and final reports. Use when the user asks for a plan, report, execution checklist, experiment design, failure analysis, or next-round optimization summary that must include evidence trace and model_status.
---

# Report Generation

## Input

Accept task spec, evidence pack, memory hits, BO status, recommendations, quality warnings, and audit trace.

## Output

Return a concise report with task understanding, knowns, missing fields, evidence, internal memory basis, BO model status, plan, risks, execution checklist, and feedback format.

## Execution Steps

1. Summarize task understanding.
2. Separate known conditions and missing conditions.
3. Include literature/RAG evidence if available.
4. Include internal memory or rule basis if available.
5. State BO `model_status`.
6. Present recommendations with source and uncertainty.
7. List risks and blocked decisions.
8. Provide execution checklist and next feedback format.

## Tool Calls

Use this skill after other workflow skills have produced structured outputs. Do not retrieve or optimize unless explicitly needed.

## Prohibitions

- Do not hide model status.
- Do not omit evidence sources.
- Do not present recommendations as verified optima.
- Do not output deterministic conclusions when evidence is insufficient.

## Quality Checks

- Every recommendation must cite an evidence path or declare missing evidence.
- Include `model_status` even when BO was not called.
- Include next-step data collection requirements.

## Failure Handling

If inputs are incomplete, produce a partial report and list missing upstream outputs.
