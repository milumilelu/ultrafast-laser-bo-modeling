# Current implemented state

This document describes the post-refactor worktree. The frozen Phase 0 facts remain in `reports/repository_inventory.json`, `reports/data_inventory.json`, baseline reports, and the `pre-agent-refactor` tag.

## System shape

The repository is one modular monolith with one formal command, `ultrafast`. The historical root BO commands remain supported through a compatibility facade for one stable cycle. FastAPI is split into transport-only routers; application orchestration runs through `AgentRuntime`; domain rules do not depend on transports or storage.

| Area | Status | Executable evidence | Deliberate boundary |
|---|---|---|---|
| Formal entry | implemented | `ultrafast tui/api/doctor/demo/workflow/legacy-bo`; `ultrafast --demo` alias | Legacy no-subcommand/TUI and root BO commands remain compatible |
| BO | implemented | Real GPR/Matern modeling plus rule cold start, hybrid, data-driven modes; equipment and KnowledgeUseGate checks | No claim of machine-optimal parameters below the validated-data threshold |
| Agent Runtime | implemented | Tool registry, `AgentRuntime.execute`, event bus, cancellation, timeout, retry, declared parallel groups, aggregation | Only public summaries are emitted |
| Formal workflows | implemented | Complex process, optical/CRL, and microhole/TGV workflows | Plans only; no machine control |
| Skill system | implemented | 45 versioned contracts, validation, migration decisions, compatibility aliases | Historical aliases retained one stable cycle |
| Domain Packs | implemented | CRL, TGV, film-cooling-hole, cover-glass, surface-texturing | More scenarios are post-demo extensions |
| Trial workflow | implemented | skip/simple/full, 5/9-point bounded matrices, measurements, acceptance, stop conditions, formal gate | Trial records never become BO samples automatically |
| Knowledge governance | implemented | Deterministic classification, one aggregated task decision, scoped approval/reuse/revoke, append-only audit | LLM may classify but cannot approve |
| RAG | implemented | Ingestion, FTS/vector hybrid retrieval, rerank, citations, Evidence Pack, revision caches, lexical fallback | No automatic OCR or paid-paper acquisition |
| Observability | implemented | Monotonic persisted AgentEvent, NDJSON, real tool durations, cache/retry/fallback, Normal/Research/Debug | Hidden reasoning, prompts, keys, DPAPI and secrets are redacted |
| Demo/Doctor/report | implemented | Offline TGV replay, `READY FOR DEMO`, per-task Markdown/JSON report | Demo measurements are clearly labelled fixtures |
| FastAPI/TUI | implemented | Split routers and folded PowerShell cards | No Web administration console |

## Data and safety state

- The original local literature corpus contains 8,512 indexed chunks; Demo Mode adds one ignored deterministic fixture chunk when needed.
- SQLite databases, PDFs, generated task reports, backups, local config, logs, task state, DPAPI material, and API-key files remain ignored and are not release artifacts.
- Literature parameters cannot influence BO unless a repository-validated, matching, active approval makes `KnowledgeUseGate` return `allowed`.
- A missing/locked review store fails high-risk use closed. A corrupt vector path falls back to SQLite lexical retrieval; a total RAG failure returns an insufficient evidence pack.
- LLM failure uses a parameter-free safe template; BO timeout exposes only the equipment search space and blocker; a read-only database produces a non-persistent Demo preview with formal execution blocked.

## Known non-goals

Real machine control, commercial CAD/CAM replacement, automatic OCR/formula vision, multi-user RBAC, paid-paper downloading, automatic `validated_rule` creation, and a full Web backend are explicitly outside this task. The legacy watcher and Anthropic adapter are not presented as implemented capabilities.
