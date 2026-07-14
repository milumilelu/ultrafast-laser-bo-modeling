# Agent tool inventory before refactor

## Direct main-Agent registry (7)

`update_task_spec`, `get_task_state`, `get_equipment_profile`, `search_rag`, `retrieve_historical_cases`, `assess_bo_readiness`, `run_bo_recommendation`.

## Separately advertised V3 names (15)

`equipment_memory_tool`, `rag_query_tool`, `historical_case_tool`, `process_rule_tool`, `trial_template_tool`, `knowledge_approval_tool`, `bo_parameter_recommendation_tool`, `rag_parameter_recommendation_tool`, `llm_fallback_parameter_tool`, `parameter_constraint_validation_tool`, `parameter_provenance_registry_tool`, `experiment_store_tool`, `measurement_parser_tool`, `quality_metric_tool`, `model_snapshot_tool`.

These catalogs disagreed: diagnostics advertised tools that the main Agent could not directly call, while the main registry exposed all seven at once.
