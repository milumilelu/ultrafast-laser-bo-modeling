# `crl_task_planning` assessment

## Current state

| Field | Finding |
|---|---|
| Current path | `agent_skills/crl-task-planning/SKILL.md`; router selection in `ultrafast_memory/chat/router/rule_router.py` |
| Callers | Legacy rule router and chat service; 5 persisted selections in the Phase 0 local trace |
| Input | CRL geometry, optical targets, material, manufacturing metrics, and task context |
| Output | CRL task draft, optical consistency result, risks, clarifications, workflow recommendation, public status |
| Side effects | None declared |
| Called tools | Calculator/structured files; conditional RAG and BO handoff |
| Existing tests | Router and task-intake/equipment tests cover selection and clarification, not a full CRL workflow |

## Duplicate generic logic

The legacy Skill duplicates task intake, missing-field clarification, equipment loading, RAG retrieval, process planning, BO handoff, risk assessment, quality planning, and report generation. Those responsibilities are now separate contracts and must not remain embedded in one CRL prompt.

## CRL-specific logic retained

- Dual-paraboloid/two-surface geometry checks.
- Radius/aperture/lens-count/optical-target consistency inputs.
- Form error, surface roughness, graphitization, edge chipping, wavefront, focal spot, and transmission metrics.
- Surface-alignment and complete-path concerns.
- Shallow paraboloid segment or scaled-lens simple trial geometry.

This logic is implemented in `ultrafast_domain.domain_packs.crl`, not in the generic workflow.

## Decision

`deprecate` the monolithic implementation while retaining the old name as a compatibility entry for at least one stable version. The compatibility contract delegates to `optical_component_task_workflow`, loads the CRL domain pack, and emits a public `deprecated_skill_used` event.

The old name must not directly call the database, RAG index mechanics, or BO engine. It may only invoke the formal workflow and domain-pack loader. Removal is allowed only after usage reaches zero and the compatibility period is explicitly closed.
