# Current Agent control flow

The main LLM owns planning. Skills provide loadable guidance, tools perform validated effects, and Business State is a projection for display/audit only.

```mermaid
flowchart LR
    U["User message"] --> R["Router: non-binding Skill hints"]
    R --> A["Main Agent"]
    C["Six-Skill catalog"] --> A
    A -->|"load_skill / unload_skill"| S["Loaded guidance + recommended tools"]
    S --> A
    A -->|"call_tool"| T["Unified Tool Registry"]
    T --> G["Validation, physical bounds, data admission, human approval guards"]
    G --> O["ToolResult observation"]
    O --> A
    A -->|"ask_user"| U
    A -->|"final_answer"| V["Chat / stream / TUI projection"]
    O --> P["Session observations and Business State projection"]
    P --> V
```

## Persistence

Session persistence exposes `active_skills_json`, `agent_observations_json`, `agent_decision_count`, and `last_agent_action_json`. These are stored inside the existing session JSON column to avoid a parallel state database. The renderer also exposes `discoverable_tools` and recent public observations.

## Termination and streaming

The Agent loop has no fixed per-turn step limit. It terminates on `ask_user`, `final_answer`, a system error, or a repeated action with unchanged task/Skill state. Exact equipment observations are reused while the equipment revision is unchanged; knowledge-search observations are reusable only within the current turn.

Chat streaming publishes route, planning, Skill, Tool, and completion events as execution happens. A heartbeat is emitted every three seconds while a model or Tool call is still pending.

## Remaining true guards

- physical equipment bounds;
- required action context and input schemas;
- BO data eligibility;
- human approval for external knowledge bootstrap and knowledge review;
- human approval for trial execution/evaluation;
- prohibited-tool and permission-level enforcement.

There is no mandatory scene workflow and no Business-State-derived action allowlist.
