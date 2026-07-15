# Current Agent control flow

The Main LLM is the only foreground business orchestrator. Router output and six Skills are non-binding hints; all eight foreground-safe Tools remain discoverable.

```mermaid
flowchart LR
    U["User message"] --> R["Router hints"]
    R --> A["MainAgentPlanner"]
    W["Open WorkingContext"] <--> A
    S["Six Skills: guidance/ranking"] --> A
    A -->|"context_updates"| W
    A -->|"call_tool"| T["Eight foreground-safe Tools"]
    T --> O["Provenance-preserving ToolResult"]
    O --> A
    A -->|"ask_user / final_answer"| U
    W -. "non-blocking" .-> P["Persistence / trace projection"]
    O -. "sidecar" .-> G["Knowledge / BO data / reports"]
```

Normal termination is semantic, not step-count based. Duplicate Tool calls reuse the existing Observation and replan; repeated no-progress triggers `probable_agent_loop`. An internal 30-decision emergency breaker exists only for program runaway protection.

True blocking guards are limited to equipment physical safety, explicit unsafe conditions, one-time confirmation for actual trial/formal start, and governance approval. BO dataset eligibility never blocks the current machining task.
