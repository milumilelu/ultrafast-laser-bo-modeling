# Implemented migration map

| Phase 0 source | Implemented destination | Compatibility/result |
|---|---|---|
| Root `interactive_bo.py` / `bayes_opt.py` | `ultrafast_bo` application/domain services | Root commands call `src/bo_compatibility.py`; golden compatibility tests pass |
| Agent BO placeholder | Real `RecommendationService` adapter | No `not_connected` response; equipment/Gate checks remain mandatory |
| Ad-hoc chat orchestration | `ultrafast_agent.runtime` and named formal workflows | Legacy chat/NDJSON response remains compatible |
| Router Skill literals | `skills/contracts.yaml` plus contract loader | Old names are aliases with deprecation events |
| `crl_task_planning` | Optical-component workflow plus CRL Domain Pack | Old name delegates for one stable cycle |
| No trial domain | `ultrafast_domain.trial`, repository/service/API | Simple/full/skip and formal-process gate implemented |
| Candidate-only review | KnowledgeUseGate and scoped usage decisions/approvals | One aggregated decision, reuse/invalidation/revoke and append-only audit |
| Fragmented traces | AgentEvent/EventBus/runtime-event repository | Monotonic streaming/persistence and redaction implemented |
| Monolithic `app/api.py` | `apps/api/main.py` plus 11 routers | Old import path remains a five-line wrapper |
| Repeated schema creation | Shared sessions/UoW and ordered migrations | Fast path initializes each DB once per process; migrations remain idempotent |

## Applied SQLite migrations

| ID | Purpose |
|---|---|
| `0001_baseline` | Register the frozen legacy schema |
| `0002_trial_workflow` | Trial plan/execution/result and formal-process decision |
| `0003_knowledge_use_gate` | Usage decision, scoped approval, reuse and revocation metadata |
| `0004_runtime_observability` | Monotonic public runtime events and latency metadata |
| `0005_task_reports` | Auditable task-report records and content hashes |

## Rollback and data policy

- `scripts/backup_before_refactor.ps1` creates an online SQLite backup and config snapshot before migration.
- `scripts/rollback_refactor.ps1` validates explicit repository/backup targets and restores without `git reset --hard`.
- Local DB/config backups and generated data are ignored. The code baseline is tagged `pre-agent-refactor`.
- Deprecated Skill names and old BO commands remain supported for at least one stable release cycle.
