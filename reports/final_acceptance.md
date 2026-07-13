# Task-package final acceptance audit

Audit date: 2026-07-13 (Asia/Shanghai). Evidence is the current worktree and commands executed against this workspace.

Source note: six task documents match `MANIFEST.sha256`; the unpacked task-package `README.md` does not match the archive manifest because its repository-URL stanza was replaced by “当前仓库”. The user explicitly referenced the unpacked README, so that current file was followed and left unchanged.

## Result

**Conditionally blocked, not fully complete.** All implementable repository work and automated acceptance checks pass. The real first-vendor CAM Adapter and its golden fixture cannot be truthfully implemented because `05_CAM_VENDOR_INPUT_TEMPLATE.md` contains no vendor identity, field mapping, units, enums, format sample, or acceptance owner/version.

| Area | Result | Evidence |
|---|---|---|
| Architecture, shared Chat workflow, Tool Executor | pass | AST boundary tests; sync/NDJSON compatibility tests |
| Persistent Jobs | pass | SQLite claim, idempotency, event sequence, retry/recovery/cancel APIs |
| Evolution Foundation | pass | evaluation + approval gates, activation/rollback, immutable content, SQLite restart recovery |
| Single formal BO service | pass | root offline/interactive and application entrypoints delegate to `BORecommendationService`; legacy adapters contain no GPR/acquisition implementation |
| BO governance and readiness | pass | material/process/equipment/target slicing, feedback eligibility, coverage/dimension/noise checks |
| BO lifecycle/replay | pass | dataset/model/evaluation registry, activation gate, rollback, versioned run trace/replay |
| Dynamic constrained search space | pass | fixed/partial/integer/categorical/conditional/forbidden/unknown policies, hard-bound intersection, conflict reporting, energy/outcome constraints |
| ProcessRecommendation + Generic/ConfigDriven CAM | pass | complete Recipe, parameter provenance, readiness gate, no-value-mutation tests, feedback candidate chain |
| Real vendor CAM Adapter | **blocked** | Gate D input is absent; inventing vendor fields is explicitly prohibited |
| PaddleOCR structure and Jobs | pass | lazy adapter, native-PDF skip, scanned-document idempotency design, page/bbox/confidence schema, review-only numeric candidates |
| OCR accuracy/per-page benchmark | not evaluated | accuracy is outside scope; no authorized scanned-PDF benchmark corpus or installed model was supplied |
| Vision semantic skeleton | pass | default disabled, `experimental_unvalidated`, no Chat/TUI/API registration |
| Migrations and rollback plan | pass | migrations `0007`–`0009`; forward/default/backfill/restore strategy documented |
| Doctor and deterministic Demo | pass | Doctor healthy with 0 failures/warnings; `scripts/demo_replay.ps1` exit 0 |
| Performance gate | pass | 12/12 checks in `reports/final_performance.json` |

## Test evidence

- `ultrafast_laser_memory`: **191 passed**, 8 sklearn convergence warnings, 73.81 s.
- Root repository tests: **31 passed**, 16 sklearn convergence warnings, 8.11 s.
- Total: **222 passed**, 0 failed.
- Doctor: `healthy`, `READY FOR DEMO`, migrations `0001`–`0009`, database integrity `ok`.
- Demo replay: exit code 0, MockLLM/offline, explicit `simple_trial_cut` and review approval.

The sklearn warnings report optimizer convergence or learned hyperparameters near configured bounds. They do not invalidate tests, but production model promotion must continue to use held-out/grouped evaluation and uncertainty calibration rather than suppressing them as proof of quality.

## Performance evidence

Key P95 values: application startup 607.429 ms; Chat first event 290.048 ms; Router 0.006 ms; workflow event 0.015 ms; BO slice 0.214 ms; governed hybrid GPR recommendation 28.885 ms; RAG 391.390 ms; Job enqueue+claim 76.663 ms; concurrent five-session latency 1,600.794 ms.

The first-event baseline is not like-for-like: the old stream emitted metadata before running its separate workflow, while the final stream renders the completed shared sync workflow. It still passes the absolute 500 ms gate. OCR per-page latency is explicitly `not_measured`, not fabricated.

## Required external input to close the only blocker

Complete `05_CAM_VENDOR_INPUT_TEMPLATE.md` with the vendor/product/version, internal-to-vendor field mapping, units/conversions, enum mapping, required/default rules, serialization sample, validation rules, golden input/output, and acceptance owner/version. Only then can a named vendor Adapter and golden test be added.
