# Skill merge matrix

Every former entry has one disposition below. “Merge” means its useful guidance moved into a broad capability descriptor; implementation remains in tools/services where applicable.

| New capability / disposition | Former entries |
|---|---|
| `task_understanding` | `task_intake`, `task_normalization`, `material_identification`, `geometry_interpretation`, `constraint_extraction` |
| `evidence_research` | `rag_evidence_retrieval`, `historical_case_retrieval`, `similar_case_retrieval`, `knowledge_use_gate`, `knowledge_bootstrap`, `rag_literature_retrieval` |
| `process_planning` | `equipment_context_loading`, `hole_drilling_planning`, `process_route_planning`, `parameter_space_construction`, `toolpath_strategy_selection`, `quality_plan_generation`, `measurement_plan_generation`, `trial_need_assessment`, `trial_strategy_selection`, `simple_trial_design`, `full_trial_design`, `process_risk_assessment`, `equipment_capability_match`, `formal_process_gate`, `execution_plan_generation`, `in_process_monitoring_plan`, `trial_to_process_transition` |
| `parameter_recommendation` | `bo_mode_selection`, `bo_recommendation`, `candidate_validation`, `parameter_recommendation_planning`, `data_support_assessment`, `parameter_source_selection`, `parameter_recommendation_explanation` |
| `experiment_optimization` | `optimization_campaign_initialization`, `iteration_planning`, `candidate_generation`, `candidate_safety_filter`, `trial_batch_planning`, `observation_ingestion`, `observation_validation`, `surrogate_model_update`, `acquisition_optimization`, `iteration_decision`, `search_space_refinement`, `fidelity_transition`, `formal_checkpoint_evaluation`, `formal_local_adjustment`, `campaign_termination` |
| `result_learning` | `trial_result_ingestion`, `trial_acceptance_evaluation`, `quality_evaluation`, `result_ingestion`, `knowledge_candidate_generation`, `process_prior_promotion`, `report_generation`, `experience_memory_update` |
| Moved to tool layer | `process_file_ingestion`, `expert_review`, `bo_dataset_governance` |
| Moved to observability, not a Skill | `latency_diagnostics`, `execution_trace_summary` |
| Deleted as a planner-visible alias/control component | `crl_task_planning`, `skill_router` |

Legacy name resolution exists only at read boundaries for a small set of persisted/scripted inputs. Aliases are not registry entries and cannot be loaded.
