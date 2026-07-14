# Skill inventory before refactor

The former registry exposed 65 entries. It mixed user capabilities, workflow steps, domain scenarios, diagnostics, and deprecated aliases in one namespace.

## Former entries (65)

`task_intake`, `task_normalization`, `equipment_context_loading`, `material_identification`, `geometry_interpretation`, `hole_drilling_planning`, `constraint_extraction`, `rag_evidence_retrieval`, `historical_case_retrieval`, `similar_case_retrieval`, `process_route_planning`, `parameter_space_construction`, `toolpath_strategy_selection`, `quality_plan_generation`, `measurement_plan_generation`, `trial_need_assessment`, `trial_strategy_selection`, `simple_trial_design`, `full_trial_design`, `knowledge_use_gate`, `process_risk_assessment`, `equipment_capability_match`, `bo_mode_selection`, `bo_recommendation`, `candidate_validation`, `formal_process_gate`, `execution_plan_generation`, `in_process_monitoring_plan`, `trial_result_ingestion`, `trial_acceptance_evaluation`, `trial_to_process_transition`, `quality_evaluation`, `result_ingestion`, `knowledge_candidate_generation`, `process_prior_promotion`, `report_generation`, `latency_diagnostics`, `execution_trace_summary`, `parameter_recommendation_planning`, `data_support_assessment`, `parameter_source_selection`, `parameter_recommendation_explanation`, `optimization_campaign_initialization`, `iteration_planning`, `candidate_generation`, `candidate_safety_filter`, `trial_batch_planning`, `observation_ingestion`, `observation_validation`, `surrogate_model_update`, `acquisition_optimization`, `iteration_decision`, `search_space_refinement`, `fidelity_transition`, `formal_checkpoint_evaluation`, `formal_local_adjustment`, `campaign_termination`, `process_file_ingestion`, `knowledge_bootstrap`, `expert_review`, `bo_dataset_governance`, `rag_literature_retrieval`, `experience_memory_update`, `crl_task_planning`, `skill_router`.

## Problems

- Workflow stages were presented as independent Skills.
- Domain-specific scenarios such as hole drilling and CRL planning became control branches.
- `allowed_tools` made Skill loading an authorization gate instead of guidance.
- Deprecated aliases remained visible to the planner.
- Diagnostics and routing internals competed with business capabilities.
