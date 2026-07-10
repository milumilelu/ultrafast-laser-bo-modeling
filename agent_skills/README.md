# Ultrafast Laser Agent Skills

This directory contains reusable execution-protocol skills for the ultrafast laser agent. These skills define stable workflows, input/output contracts, safety boundaries, and quality checks.

They intentionally do not store literature, private logs, API keys, experimental records, or validated process facts. Dynamic knowledge belongs in memory, RAG, SQLite, validated rules, or BO datasets.

## Skills

- `skill-router`: route user requests to the correct workflow skill.
- `task-intake`: convert vague manufacturing requests into a structured `task_spec`.
- `crl-task-planning`: plan diamond CRL / X-ray refractive lens manufacturing tasks.
- `rag-literature-retrieval`: build evidence packs from literature or knowledge retrieval.
- `bo-recommendation`: call or prepare BO recommendations without inventing parameters.
- `process-file-ingestion`: ingest recipes, logs, measurements, and notes with traceability.
- `experience-memory-update`: turn observations into reviewable experience candidates.
- `bo-dataset-governance`: decide whether records can enter BO training data.
- `report-generation`: produce evidence-linked plans, reports, and execution checklists.

## Usage

Start with `skill-router/routing_rules.json` when the task type is unclear. Each skill folder includes:

- `SKILL.md`: trigger conditions, workflow, prohibitions, quality checks, and failure handling.
- `input_schema.json`: expected input contract.
- `output_schema.json`: expected output contract.
- `examples.md`: normal, missing-information, and refusal examples.

## Boundary

Skills control process. They must not fabricate laser power, frequency, scan speed, hatch spacing, layer step, focus offset, pass count, surface roughness, form error, Raman results, or other physical data.
