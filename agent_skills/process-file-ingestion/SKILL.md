---
name: process-file-ingestion
description: Ingest ultrafast laser process files, recipes, jobs, logs, CSV/XLSX measurements, G-code/NC files, inspection reports, and operator notes into traceable structured records. Use when the user uploads or points to machining software outputs, asks to auto-read files, archive originals, calculate SHA256, parse process files, standardize units, or create experience candidates from notes.
---

# Process File Ingestion

## Input

Accept file paths, watch directories, parser hints, and optional database location.

## Output

Return import summary, created record IDs, and quality warnings.

## Execution Steps

1. Identify file type.
2. Calculate SHA256.
3. Archive original by copying; never move or modify it.
4. Call the dedicated parser.
5. Standardize units while preserving raw value and unit.
6. Write `raw_artifact`.
7. Write task, recipe, run, and measurement records.
8. Convert notes only into `experience_candidate`.
9. Record parse errors and quality warnings.

## Tool Calls

Prefer repository modules under `ultrafast_memory.ingestion`, `parsers`, `normalization`, and `db` when available.

## Prohibitions

- Do not modify original files.
- Do not skip hash calculation.
- Do not guess missing numeric values.
- Do not convert operator notes into validated rules.
- Do not add abnormal or alarmed runs directly to BO.

## Quality Checks

- Every structured record must trace to `artifact_id`.
- Every artifact must have SHA256.
- Parser name and version must be recorded.
- Duplicate SHA256 imports must be idempotent.

## Failure Handling

If a parser fails, record the error and continue with other files.
