# V3.1 Planner ValidationError — Before Fix

## Reproduction scope

- Baseline commit: `18f8725086750bb8ba1bf7b7bceee2c56bbdade8`
- Rollback tag: `v31-runtime-fix-baseline-20260716`
- User message: `我想加工 3 mm 厚的 T300 碳纤维板，开一个 4 mm 通孔。`
- Reproduction mode: controlled invalid model output through the real `run_main_agent_turn()` path.
- Production model credentials were not invoked. The invalid output is a fixed fixture, not claimed as a captured production-model response.

## Raw model output

```json
{
  "action": "call_tool",
  "decision_summary": "先推荐参数",
  "tool_name": "recommend_parameters",
  "arguments": []
}
```

## Parsed JSON

The JSON parser succeeded and produced the same object. Pydantic action validation then failed because `arguments` was a list rather than an object.

## Exact `ValidationError.errors()`

```json
[
  {
    "type": "dict_type",
    "loc": ["arguments"],
    "msg": "Input should be a valid dictionary",
    "input": [],
    "url": "https://errors.pydantic.dev/2.11/v/dict_type"
  }
]
```

The pre-fix public trace omitted the received value (`[]`) and expected type (`object`). It only retained `loc`, `type`, and `msg`.

## Retry behavior

| Attempt | Prompt characters | Result |
|---:|---:|---|
| 1 | 9,665 | `ValidationError` at `arguments` |
| 2 | 9,914 | Same `ValidationError` |

The repair attempt resent the full planning prompt and appended an error note. It did not use a small action-only repair prompt.

## Pre-fix terminal behavior

After the second validation failure, the planner returned:

```json
{
  "action": "final_answer",
  "decision_summary": "主 Agent 行动规划失败：ValidationError。",
  "message": "主 Agent 连续两次未能产生有效的结构化行动……"
}
```

This ended the turn instead of selecting a deterministic safe next action.

## AgentAction schema before fix

```text
action = call_tool | ask_user | final_answer
decision_summary: string
skills_used: string[]
tool_name: string | null
arguments: object
message: string | null
context_updates: object
```

Schema version was not recorded before the fix.

## Foreground tool visibility before fix

The Main Agent-visible capability set was already reduced to:

```text
get_equipment_context
manage_process
manage_trial
recommend_process_parameters
record_process_result
search_knowledge
```

The registry also retained internal/compatibility contracts for BO, RAG, and exploratory recommendation. Registry version was not recorded before the fix.

## Active skills

```text
task_understanding
evidence_research
process_planning
parameter_recommendation
experiment_optimization
```

## WorkingContext before planner failure

```json
{
  "task": {
    "process_intent": "through_hole_drilling",
    "material": {
      "name": "CFRP",
      "description": "碳纤维板",
      "grade": "T300"
    },
    "workpiece": {"thickness_mm": 3.0}
  },
  "equipment_context": null,
  "observations": []
}
```

The diameter was not extracted from `开一个 4 mm 通孔`; this is a separate deterministic intake defect confirmed by the reproduction.

## Root causes

1. The wire schema rejected a common malformed model value, but the trace discarded the received value.
2. Repair reused the complete planner prompt rather than an action-only repair payload.
3. Repair failure returned a terminal-style answer instead of deterministic progression.
4. The task extractor required an explicit `直径` marker and missed `4 mm 通孔`.
