---
name: rag-literature-retrieval
description: Retrieve and structure traceable literature or RAG evidence for ultrafast laser machining mechanisms, parameter ranges, similar process cases, damage, graphitization, roughness, form error, and removal efficiency. Use when the user asks to search literature, find references, explain mechanisms, establish priors, or support claims with sources.
---

# RAG Literature Retrieval

## Input

Accept `task_spec`, query intent, material, process type, target metrics, and optional filters.

## Output

Return `evidence_pack`, `parameter_priors`, `risk_mechanisms`, and `evidence_gaps`.

## Execution Steps

1. Build multiple queries from material, process, scale, pulse width, metric, and mechanism.
2. Retrieve from available literature/RAG sources or official databases.
3. Filter by material, process type, pulse regime, measurement metric, and geometry scale.
4. Extract claims with source IDs and page/section when available.
5. Mark each claim as usable and not usable for specific decisions.
6. State evidence gaps explicitly.

## Tool Calls

Use approved literature search, local RAG, PDF, or citation tools. Browse only when current external evidence is required.

## Prohibitions

- Do not migrate a literature optimum as the current optimum.
- Do not summarize without sources.
- Do not mix materials, pulse widths, or scales without warning.
- Do not hide insufficient evidence.

## Quality Checks

- Each claim must have a source.
- Parameter priors must be ranges or qualitative constraints, not fabricated precise values.
- Evidence confidence must be stated.

## Failure Handling

If retrieval fails, return `evidence_gaps` and do not recommend fixed parameters.
