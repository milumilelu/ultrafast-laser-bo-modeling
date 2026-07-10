# Final implementation status matrix

Status is based on executable code, tests, Demo replay and final measurements. It does not infer implementation from filenames.

| Capability | Status | Evidence | Current limitation |
|---|---|---|---|
| BO | implemented | Real GPR/Matern RecommendationService; cold/hybrid/data-driven tests; legacy facade | `<10` validated samples uses conservative rule mode |
| Chat/Router | implemented | Persistent sync/NDJSON chat, rule/manual/session routing, Mock/external adapters | Legacy chat service remains for compatibility alongside formal Runtime |
| Agent Runtime | implemented | AgentRuntime, ToolRegistry, EventBus, timeout/retry/cancel, parallel groups, terminal events | Modular monolith, not distributed execution |
| Skill | implemented | 45 validated contracts and complete inventory/decision matrix | Deprecated aliases retained one stable cycle |
| Domain Packs | implemented | CRL/TGV/film-cooling/cover-glass/surface-texturing tests | Additional processes are future packs |
| Equipment Memory | implemented | Profiles, immutable revisions, active bounds, override validation | User must provide/calibrate real equipment values |
| RAG/Literature | implemented | 8,512 corpus chunks, hybrid retrieval, vector-matrix/revision cache, FTS fallback, citations | OCR/visual formula understanding excluded |
| Knowledge Candidate/Review | implemented | Candidate review plus KnowledgeUseGate, scoped approval/reuse/revoke and append-only actions | Single-user workflow, no RBAC |
| Trial Cut | implemented | skip/simple/full API, 5/9-point matrices, result evaluation and formal unlock | No real machine execution |
| Execution Trace | implemented | Monotonic AgentEvent persistence/NDJSON, redaction, duration/cache/retry/fallback | Only public summaries, never hidden reasoning |
| PowerShell TUI | implemented | Normal/Research/Debug folds, evidence/trial/approval/latency cards | No Web GUI |
| FastAPI | implemented | 11 split routers plus compatibility import; architecture/API tests | Runs in-process as modular monolith |
| Demo Mode | implemented | Deterministic offline TGV replay exits 0 | Fixture measurements are simulated and labelled |
| Doctor | implemented | Python/dependency/config/DB/migration/write/port/equipment/RAG/LLM/BO/fixture checks | LLM check is offline configuration, not an external call |
| Task Report | implemented | Auditable Markdown/JSON with evidence, trial, review, BO, clipping and timings | Generated reports remain local/ignored |
| Versioned migrations | implemented | Ordered 0001–0005, atomic/idempotent tests | Rollback restores a backup rather than destructive down-migrations |

The Phase 0 matrix is preserved by Git tag `pre-agent-refactor` and the baseline reports.
