# Offline demo runbook

## Preconditions

```powershell
cd ultrafast_laser_memory
pip install -e .[dev]
ultrafast doctor
```

Doctor may warn when no active equipment or RAG index exists, but database integrity, migrations, BO service, and Python checks must pass. Demo Mode creates only clearly labelled deterministic fixture records and never calls an external model or network search.

## TGV primary demo

Interactive review stop:

```powershell
ultrafast demo tgv
```

The documented flag alias is equivalent:

```powershell
ultrafast --demo
```

Expected result: `waiting_review` with one approval card containing at most five evidence items.

Complete replay after explicit task-scoped approval:

```powershell
ultrafast demo tgv --approve-review
```

Expected chain:

1. TGV task and aspect ratio parsed.
2. Active equipment revision loaded.
3. Internal RAG evidence retrieved.
4. One aggregated knowledge-use decision created.
5. Explicit Demo approval recorded as `current_task`.
6. Real BO application returns `rule_based_cold_start` when validated samples are below ten.
7. Simple 3×3-hole representative trial with five bounded parameter points planned.
8. Deterministic fixture execution/result passes declared criteria.
9. Formal-process gate unlocks.
10. Markdown and JSON task reports are written under ignored `data/reports/tasks/`.

The fixture result is not a real machine measurement and is labelled accordingly.

If SQLite rejects writes as read-only, Demo Mode returns `read_only_demo`: a non-persistent five-point trial/BO preview. Knowledge approval remains blocked, formal processing is not unlocked, and no report/result is written.

## Automated replay

From the repository root:

```powershell
pwsh -ExecutionPolicy Bypass -File scripts/demo_replay.ps1
```

The script forces MockLLM/offline mode, runs Doctor, then executes the TGV replay. It does not upload data or secrets.

## CRL auxiliary demo

Run `optical_component_task_workflow` with a JSON request containing the CRL domain pack and dual-paraboloid geometry. The workflow checks radius/aperture/lens count/two surfaces, proposes a shallow-paraboloid simple trial, and reports form error, roughness, graphitization, wavefront, focal spot, and transmission metrics. The deprecated `crl_task_planning` name remains a compatibility alias and emits `deprecated_skill_used`.
