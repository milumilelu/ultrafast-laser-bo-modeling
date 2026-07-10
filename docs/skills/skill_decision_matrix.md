# Skill decision matrix

| Existing skill | Decision | Target | Compatibility behavior |
|---|---|---|---|
| `task_intake` | refactor | `task_intake` + `task_normalization` + focused material/geometry/constraint skills | Old name retained |
| `skill_router` | convert_to_tool | Agent Runtime route planner | Old contract delegates to `route_planner` |
| `process_file_ingestion` | refactor | Thin orchestration over `ingestion_service`; hashing/copy/parsing remain tools | Old name retained |
| `bo_dataset_governance` | convert_to_domain_rule | `DatasetValidationService` and BO eligibility rules | Compatibility contract retained |
| `bo_recommendation` | refactor | `bo_mode_selection` + real `RecommendationService` + candidate validation | Old name retained; no `not_connected` placeholder |
| `rag_literature_retrieval` | merge | `rag_evidence_retrieval` | Deprecated alias emits `deprecated_skill_used` |
| `experience_memory_update` | merge | `knowledge_candidate_generation` + explicit promotion review | Deprecated alias emits `deprecated_skill_used` |
| `report_generation` | refactor | Structured Markdown/JSON task report service | Old name retained |
| `crl_task_planning` | deprecate | `optical_component_task_workflow` + CRL domain pack | Old name delegates and emits `deprecated_skill_used` |

## New composition rules

- Scenario-specific differences live in `ultrafast_domain.domain_packs`, not duplicated scenario Skills.
- CRL owns dual-paraboloid geometry, form error, wavefront, focal spot, transmission, and shallow-paraboloid trial templates.
- TGV owns aspect-ratio, pitch/density, taper/crack/chipping, array-yield, and representative hole-array rules.
- UI text describes user decisions and workflow stages; users are not required to know Skill names.
- Research/Debug display modes may show the public Skill call chain, but never hidden chain-of-thought.
