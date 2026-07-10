# Phase 0 risk register

| Priority | Risk | Evidence | Consequence | Recommended control |
|---|---|---|---|---|
| P0 | Agent BO appears available by name but is not connected | Adapter returns `model_status: not_connected` | Demo may imply a recommendation that never used BO | Wire only through a tested compatibility facade; expose model status |
| P0 | Two project roots can drift independently | Separate entrypoints, configs, tests, data paths | Fixes can land in one system but not the other | Establish one formal entry while preserving old CLI compatibility |
| P0 | No versioned migrations | Schema is created/extended in `init_db.py` | New trial/review tables risk irreversible live-DB changes | Add migration IDs, online backup, idempotency, and rollback test before schema work |
| P0 | Unreviewed knowledge could be mistaken for approved prior | 345 candidates/tasks, 0 actions, 0 process priors | Unsafe parameter or BO-bound use | Implement and test fail-closed KnowledgeUseGate before BO integration |
| P0 | Trial gating is absent | No trial module/schema/API | Formal processing cannot be safely unlocked by evidence | Implement simple/full/skip state machine before claiming end-to-end closure |
| P0 | Local data volume is easy to upload accidentally | ~120 MB live DB; 456 source/archive PDF files totaling gigabytes | Data leakage and oversized Git history | Preserve ignore rules; pre-push secret/data audit; never force-add ignored data |
| P1 | Skills are outside version control and have no runtime contract | Nine untracked `SKILL.md` files | Runtime naming and documentation can diverge | Inventory/adopt files, validate schemas, preserve aliases |
| P1 | FastAPI and Chat are monolithic composition points | 43 endpoints in one file; chat coordinates many domains | High regression and circular-dependency risk during refactor | Extract services behind stable transport contracts; add architecture tests |
| P1 | Trace is useful but not a full runtime event model | Trace table and NDJSON exist; no sequence/event bus/waterfall | Ordering, latency, retry, and failure analysis remain ambiguous | Add monotonic sequence and public event schema; redact centrally |
| P1 | RAG latency is material | P95 about 1,055.6 ms on 8,512 chunks | Slow evidence steps and delayed full answers | Profile FTS/vector/rerank stages; cache immutable query components |
| P1 | Performance baseline excludes HTTP/network transport | First event P95 about 102.0 ms in-process | Real TUI latency may be higher | Add localhost HTTP and 5-session concurrency benchmarks later |
| P1 | Baseline tag is local only | `pre-agent-refactor` not pushed | Other clones cannot use the rollback anchor | Push tag only after user approves the Phase 0 artifact set |
| P2 | Legacy BO tests emit convergence warnings | 32 warnings in 30-test run | Model-bound or data-quality issue may be overlooked | Track warning thresholds and inspect kernel bounds separately |
| P2 | File watcher is a callable stub | Explicit `NotImplementedError` | Background ingestion claims would be false | Keep disabled or implement with failure/restart tests |

## Security finding

Current ignore rules correctly cover the live data tree, literature workspace, local LLM configuration, and DPAPI secret directory. Phase 0 did not expose secret contents. The local baseline backup copies `default.yaml` and `llm.local.json` inside the already ignored data tree; it deliberately does not copy the DPAPI/API-key store.
