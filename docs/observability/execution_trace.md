# Public execution trace

## Event contract

Runtime events are persisted in `runtime_public_event` with a unique `(run_id, sequence)` key. Each event can expose:

- Sequence, event type, stage, title, summary, status, and progress.
- Selected Skill and real Tool name.
- Duration, retry attempt, and cache-hit state.
- Redacted structured public data.
- Session/task/run links and timestamp.

Canonical Runtime events include `workflow_started`, `tool_started`, `tool_completed`, `tool_failed`, `state_updated`, `workflow_completed`, and `workflow_failed`; decisions, warnings, retry/fallback and cancellation retain explicit status fields. Legacy chat trace names remain readable for one compatibility cycle.

## Display modes

| Mode | Visible detail |
|---|---|
| Normal | Concise progress, decisions, warnings/errors, answer; detailed tool traces remain folded |
| Research | Skill/tool/evidence/route/model-status summaries |
| Debug | Public sequence, stage, input/output summaries, duration, cache and retry metadata |

All modes exclude chain-of-thought, raw thoughts, hidden reasoning, system prompts, API keys, authorization/password fields, DPAPI values, and secret payloads.

## Streaming

- Chat: `POST /chat/stream_ndjson`
- Formal workflow: `POST /workflows/{workflow_name}/stream_ndjson`
- Persisted trace: `GET /execution-traces/{run_id}`

The first NDJSON event is emitted before long-running tool work. Sequence is monotonic in both live streams and persisted trace.

## Performance waterfall

RAG returns index lookup, lexical, vector, fusion, rerank/limit, evidence-pack, trace-write, total, revision-cache and fallback metadata. Runtime events add per-tool latency and declared parallel groups. Final performance reports publish P50/P95/P99 without external LLM calls unless explicitly configured.
