# Foreground runtime after convergence

```text
User / NDJSON stream
        ↕
MainAgentLoop
├─ MainAgentPlanner → AgentAction(context_updates + one action)
├─ WorkingContext (open-world, partial)
├─ six composable Skills (ranking/guidance only)
├─ eight always-discoverable foreground-safe Tools
├─ Tool Observations + duplicate cache
└─ non-blocking persistence / trace / post-process warnings
        │
        ├─ manage_trial → TrialApplicationService
        └─ manage_process → plan/start/checkpoint/result/complete/abort
```

Removed from normal runtime: task-update Tool and strict TaskSpec intake package, Skill visibility whitelist, fixed workflow services, BusinessState/Process FSM, TrialClosedLoop/Campaign path, mandatory BO continuation, fixed normal Agent step termination, and governance Tools from the foreground catalog.
