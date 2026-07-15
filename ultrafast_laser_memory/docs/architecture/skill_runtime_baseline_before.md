# Skill Runtime Baseline Before Professional-Method Restoration

Date: 2026-07-15

## Runtime identity

- Git HEAD: `5e3081bf7a2c0939bf4c1920a77d6188f0c40ce8`
- Branch: `main`
- Worktree: clean
- Runtime mode: `capability_discovery`
- Backend PID: `14456`
- Runtime commit: `5e3081bf7a2c0939bf4c1920a77d6188f0c40ce8`
- Main loop: `src/ultrafast_memory/agent_runtime/main_agent_loop.py`
- Planner: `src/ultrafast_memory/agent_runtime/planner.py`
- Skill registry: `src/ultrafast_memory/agent_runtime/skill_registry.py`
- Tool registry: `src/ultrafast_memory/agent_runtime/tool_registry.py`

## Six formal Skills

The registry contains exactly `task_understanding`, `evidence_research`,
`process_planning`, `parameter_recommendation`, `experiment_optimization`, and
`result_learning`. Each current contract has a description, use hints, three short
guidance statements, and recommended Tools. It does not yet model method,
required considerations, output expectations, prohibitions, or failure handling as
separate stable contract fields.

## AgentAction and Working Context

`AgentAction` already supports the five intended actions and `context_updates`.
`WorkingContext` is open-world (`extra="allow"`) and stores a partial `task`,
observations, active Skills, equipment context, and document metadata. The main loop
applies `context_updates` in memory before executing an action. Persistence is a
sidecar warning path rather than a foreground failure.

`update_task_context` is not present in the foreground Tool Registry. Context merge
and persistence remain internal in `WorkingContext.apply` and
`ContextPersistenceService`.

## Planner prompt and task understanding

The Planner already receives the complete user message, Working Context, recent
observations, Skill catalog, loaded Skills, and all safe Tool schemas. Structured
output retry runs twice and the second attempt receives a sanitized repair note.

Current defects:

- `ask_user` is validated by counting question marks and requires 3–5 questions.
- System prompt, repair prompt, attachment prompt, and deterministic fallback all
  repeat the 3–5 rule.
- The deterministic rectangular-groove parser asks five questions although only
  depth is blocking.
- The deterministic parser supports AlSiC groove, CFRP cutting, and diamond hole,
  but not the zirconia through-hole acceptance case.
- Several deterministic paths return a status acknowledgement instead of continuing
  toward a complete process/trial plan.
- Blocking questions, assumptions, reminders, warnings, and optional preferences are
  not explicitly separated.

## MainAgentLoop

The foreground has one `MainAgentLoop`. All foreground-safe Tools remain
discoverable; loaded Skills only affect ranking. There is no normal eight-step limit.
An absolute emergency breaker remains at 30 decisions. Equivalent observations are
reused by Tool name, normalized arguments, cache policy, and equipment revision.
Events are published live through an event sink, and streaming emits named model,
Tool, and stage heartbeats.

Known gaps:

- No explicit internal `ProcessPlan`, `ParameterValue`, or complete `TrialPlan`
  projection exists in Working Context.
- Final-answer completeness depends almost entirely on the LLM prompt and thin Skill
  text.

## Foreground Tool Registry

The default safe set is:

- `get_equipment_context`
- `search_knowledge`
- `recommend_parameters_bo`
- `recommend_parameters_rag`
- `propose_exploratory_parameters`
- `manage_trial`
- `manage_process`
- `record_process_result`

On-demand background Tools remain separate. `update_task_context` is absent.

## Equipment and parameter semantics

`get_equipment_context` currently forwards `build_machine_bounds()`. Fixed values
such as wavelength and spot diameter are encoded as `[value, value]` beside tunable
ranges. Therefore callers cannot distinguish fixed equipment facts from tunable
capabilities without inferring from equal endpoints.

BO, RAG, and exploratory recommendation remain separate. Their shared result uses a
flat `parameters` object and result-level provenance, not one provenance-bearing
`ParameterValue` per process parameter.

## Exploratory parameter implementation

The current `_exploratory` implementation uses `payload.variables` or, when absent,
all machine bounds. For every numeric range it returns `(lower + upper) / 2`. This is
exactly the machine-midpoint behavior to remove. It does not require a ProcessPlan,
does not require Main Agent-selected variables, and does not distinguish fixed
equipment conditions from process setpoints.

## Current ProcessPlan and TrialPlan

`ultrafast_domain.process.ProcessPlan` currently stores only task ID, route,
parameter window, quality plan, stop conditions, and status.

`TrialPlanDraft` currently stores trial mode, representative geometry, parameter
matrix, measurement plan, acceptance criteria, stop conditions, status, and warnings.
It lacks the required objective, machining/process strategy, toolpath, fixed equipment
conditions, provenance-bearing process parameters, derived metrics, adjustment logic,
and explicit risk rationale. `manage_trial` is a persistence/lifecycle Tool and does
not currently construct the richer plan itself.

## Baseline judgment

Keep the single Main Agent, open Working Context, dynamic capability discovery,
separate BO/RAG/exploratory Tools, retry, observation cache, streaming, and sidecar
persistence. Restore professional method contracts, semantic parameter structures,
complete plan objects, and blocking-only interaction without adding Agents, FSMs,
scene Skills, or a second foreground path.
