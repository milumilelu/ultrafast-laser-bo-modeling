# Legacy retirement audit

Audit scope: new-write callers, direct readers, compatibility readers, and formal workflow state
branches after `0011_legacy_trace_migration_ledger`.

| Legacy object | New write callers | Direct read callers | Compatibility action |
|---|---:|---:|---|
| `agent_trace_event` | 0 | 0 | Backfill; old API fallback only when canonical history is empty |
| `reasoning_status_trace` | 0 | 0 | Backfill; old API fallback only when canonical history is empty |
| `public_reasoning_trace` | 0 | 0 | Backfill only; canonical renderer is the active reader |
| `workflow_progress` | 1 legacy adapter | 1 legacy adapter | Quarantined to non-process chat compatibility |
| fine `ProcessState` | 0 formal writers | 1 adapter | Historical read/progress compatibility |
| `substatus` | compatibility writes | UI/audit readers | Formal branches use `BusinessState` plus `execution_step` |

Retirement sequence is `Freeze → Audit → Backfill → Switch Reader → Quarantine → Remove`.
The migration command supports `--dry-run`, `--limit`, `--resume`, and `--verify`. It records each
converted source row in `legacy_trace_migration`, uses canonical event idempotency, never deletes the
source row, and reports conversion, skip, conflict, and verification counts.
