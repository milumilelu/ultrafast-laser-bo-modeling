# Tool merge matrix

| Former Agent-facing name(s) | New public tool / disposition |
|---|---|
| `update_task_spec`, `get_task_state` | `update_task_context`; reads return the updated canonical context |
| `get_equipment_profile`, `equipment_memory_tool` | `get_equipment_context` |
| `search_rag`, `rag_query_tool`, `historical_case_tool` | `search_knowledge` |
| external evidence gap/bootstrap calls | `bootstrap_external_knowledge` |
| `assess_bo_readiness`, `run_bo_recommendation`, `bo_parameter_recommendation_tool` | `recommend_parameters_bo` |
| `rag_parameter_recommendation_tool` | `recommend_parameters_rag` |
| `llm_fallback_parameter_tool` | `propose_exploratory_parameters` (renamed to prevent false authority) |
| `trial_template_tool` | `manage_trial` |
| `experiment_store_tool`, `model_snapshot_tool`, acquisition internals | `run_bo_iteration` |
| `measurement_parser_tool`, `quality_metric_tool` | `record_process_result` |
| knowledge candidate write internals | `create_knowledge_candidate` |
| report writer internals | `generate_report` |
| ingestion service | on-demand `ingest_files` |
| `knowledge_approval_tool` | on-demand, human-approval-guarded `review_knowledge_candidate` |
| `process_rule_tool` | deleted from Agent catalog; rules are service validations or Skill guidance |
| `parameter_constraint_validation_tool` | internal validation inside parameter tools |
| `parameter_provenance_registry_tool` | internal provenance emitted by parameter tools |
