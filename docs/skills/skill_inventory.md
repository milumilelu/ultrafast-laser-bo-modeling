# Skill inventory

Contract source: `ultrafast_laser_memory/skills/contracts.yaml` (45 validated contracts).

Usage counts are observed rows in the current local `chat_skill_trace`; zero means no persisted call was observed, not proof that the capability is unused.

| Name | Version | Legacy path | Callers | Called tools | Inputs → outputs | Side effects | Timeout/cache | Tests | Usage | Decision |
|---|---|---|---|---|---|---|---|---|---:|---|
| bo_dataset_governance | 1.0.0-compat | agent_skills/bo-dataset-governance/SKILL.md | formal workflow composition | dataset_validation_service | run_records → bo_dataset_status | — | 30000 ms / none | — | 0 | convert_to_domain_rule |
| bo_mode_selection | 1.0.0 | — | formal workflow composition | bo_status_service | bo_dataset_status → model_status | — | 30000 ms / none | — | 0 | keep |
| bo_recommendation | 1.0.0 | agent_skills/bo-recommendation/SKILL.md | legacy rule router; complex_process_task | bo_recommendation_service | task_spec, parameter_space, approved_knowledge, validated_samples → bo_recommendation, model_status, uncertainty | — | 60000 ms / none | test_bo_application_services.py, test_bo_machine_bounds.py, test_route_plan_knowledge_bootstrap.py, test_router_hybrid.py, test_skill_contracts_and_domain_packs.py, test_skill_router.py | 1 | refactor |
| candidate_validation | 1.0.0 | — | formal workflow composition | candidate_validation_service | candidate, equipment_snapshot, task_constraints, approvals → candidate_validation | — | 30000 ms / none | — | 0 | keep |
| constraint_extraction | 1.0.0 | — | formal workflow composition | — | task_spec, equipment_snapshot → constraint_set | — | 30000 ms / none | — | 0 | keep |
| crl_task_planning | 1.0.0-compat | agent_skills/crl-task-planning/SKILL.md | legacy rule router; optical_component_task_workflow compatibility | optical_component_task_workflow, domain_pack_loader | task_context → optical_component_plan | — | 30000 ms / none | test_chat_api.py, test_chat_service.py, test_router_manual_override.py, test_router_session_state.py, test_skill_contracts_and_domain_packs.py, test_skill_router.py, test_stream_ndjson.py | 5 | deprecate |
| equipment_capability_match | 1.0.0 | — | formal workflow composition | equipment_context_service | equipment_snapshot, process_route, parameter_space → capability_match, violations | — | 30000 ms / none | — | 0 | keep |
| equipment_context_loading | 1.0.0 | — | formal workflow composition | equipment_context_service | task_context → equipment_snapshot | — | 30000 ms / by_equipment_revision | — | 0 | keep |
| execution_plan_generation | 1.0.0 | — | formal workflow composition | — | process_plan, trial_result, approved_parameters → execution_plan | — | 30000 ms / none | — | 0 | keep |
| execution_trace_summary | 1.0.0 | — | formal workflow composition | trace_query_service | execution_trace, display_mode → public_trace_summary | — | 30000 ms / none | — | 0 | keep |
| experience_memory_update | 1.0.0-compat | agent_skills/experience-memory-update/SKILL.md | formal workflow composition | knowledge_candidate_generation | task_context → knowledge_candidates | — | 30000 ms / none | test_router_hybrid.py | 0 | merge |
| expert_review | 1.0.0-compat | — | legacy knowledge review flow | knowledge_review_service | review_task, human_action → review_result | append_review_action | 30000 ms / none | — | 0 | keep |
| formal_process_gate | 1.0.0 | — | formal workflow composition | formal_process_gate_service | trial_result, knowledge_decisions, candidate_validation → formal_process_decision | — | 30000 ms / none | — | 0 | keep |
| full_trial_design | 1.0.0 | — | formal workflow composition | trial_service, domain_pack_loader | task_spec, parameter_space, domain_pack → trial_plan | — | 30000 ms / none | — | 0 | keep |
| geometry_interpretation | 1.0.0 | — | formal workflow composition | geometry_service, domain_pack_loader | task_spec, domain_pack → geometry_model, geometric_risks | — | 30000 ms / none | — | 0 | keep |
| historical_case_retrieval | 1.0.0 | — | formal workflow composition | historical_case_service | task_context → historical_cases | — | 30000 ms / by_dataset_revision | — | 0 | keep |
| in_process_monitoring_plan | 1.0.0 | — | formal workflow composition | domain_pack_loader | process_plan, domain_pack → monitoring_plan | — | 30000 ms / none | — | 0 | keep |
| knowledge_bootstrap | 1.0.0-compat | — | legacy chat permission flow | knowledge_bootstrap_service | task_spec, query, user_permission → knowledge_candidates, review_tasks | create_knowledge_candidate, create_review_task | 30000 ms / none | test_auto_precheck.py, test_candidate_builder.py, test_chat_knowledge_bootstrap_integration.py, test_evidence_gap_detector.py, test_knowledge_bootstrap.py, test_knowledge_review.py, test_query_generator.py, test_rag_ingestion.py, test_review_session_link.py, test_route_plan_knowledge_bootstrap.py | 0 | keep |
| knowledge_candidate_generation | 1.0.0 | — | formal workflow composition | knowledge_candidate_service | result_record, evidence → knowledge_candidates | create_knowledge_candidate | 30000 ms / none | — | 0 | keep |
| knowledge_use_gate | 1.0.0 | — | formal workflow composition | knowledge_use_gate_service | task_spec, intended_use, evidence_pack, equipment_snapshot → knowledge_use_decision | — | 30000 ms / none | — | 0 | keep |
| latency_diagnostics | 1.0.0 | — | formal workflow composition | trace_query_service | execution_trace → latency_waterfall | — | 30000 ms / none | — | 0 | keep |
| material_identification | 1.0.0 | — | formal workflow composition | material_registry_service, attachment_reader | task_spec, attachments → material_identity, confidence, missing_fields | — | 30000 ms / none | — | 0 | keep |
| measurement_plan_generation | 1.0.0 | — | formal workflow composition | domain_pack_loader | quality_plan, domain_pack → measurement_plan | — | 30000 ms / none | — | 0 | keep |
| parameter_space_construction | 1.0.0 | — | formal workflow composition | parameter_space_service, knowledge_use_gate_service | equipment_snapshot, approved_knowledge, task_constraints → parameter_space, source_trace | — | 30000 ms / none | — | 0 | keep |
| process_file_ingestion | 1.0.0-compat | agent_skills/process-file-ingestion/SKILL.md | formal workflow composition | ingestion_service | file_paths, parser_hints → ingestion_summary | archive_original_copy, create_ingestion_records | 30000 ms / none | test_chat_route_plan.py, test_skill_router.py | 0 | refactor |
| process_prior_promotion | 1.0.0 | — | formal workflow composition | knowledge_review_service | knowledge_candidate, approval → process_prior | create_process_prior | 30000 ms / none | — | 0 | keep |
| process_risk_assessment | 1.0.0 | — | formal workflow composition | — | task_context → risk_register, risk_level | — | 30000 ms / none | — | 0 | keep |
| process_route_planning | 1.0.0 | — | formal workflow composition | domain_pack_loader | task_spec, equipment_snapshot, evidence_pack, domain_pack → process_route, alternatives, blockers | — | 30000 ms / none | — | 0 | keep |
| quality_evaluation | 1.0.0 | — | formal workflow composition | quality_evaluation_service | quality_plan, measurements → quality_status, defects | — | 30000 ms / none | — | 0 | keep |
| quality_plan_generation | 1.0.0 | — | formal workflow composition | domain_pack_loader | task_spec, process_route, domain_pack → quality_plan | — | 30000 ms / none | — | 0 | keep |
| rag_evidence_retrieval | 1.0.0 | — | formal workflow composition | rag_query_service | task_spec, query_intent, filters → evidence_pack, citations, evidence_gaps | — | 30000 ms / by_index_revision_and_query | — | 0 | keep |
| rag_literature_retrieval | 1.0.0-compat | agent_skills/rag-literature-retrieval/SKILL.md | legacy rule router/chat; alias to rag_evidence_retrieval | rag_evidence_retrieval | task_context → evidence_pack | — | 30000 ms / none | test_chat_rag_integration.py, test_route_plan_knowledge_bootstrap.py, test_skill_router.py | 1 | merge |
| report_generation | 1.0.0 | agent_skills/report-generation/SKILL.md | legacy rule router; all formal workflows | task_report_service | task_context, workflow_outputs, execution_trace → task_report_markdown, task_report_json | write_task_report | 30000 ms / none | — | 0 | refactor |
| result_ingestion | 1.0.0 | — | formal workflow composition | result_ingestion_service | execution_result, measurements → result_record, validation_requirements | create_process_result | 30000 ms / none | — | 0 | keep |
| similar_case_retrieval | 1.0.0 | — | formal workflow composition | similarity_service | task_spec, historical_cases → similar_cases, similarity_explanation | — | 30000 ms / none | — | 0 | keep |
| simple_trial_design | 1.0.0 | — | formal workflow composition | trial_service, domain_pack_loader | task_spec, parameter_space, domain_pack → trial_plan | — | 30000 ms / none | — | 0 | keep |
| skill_router | 1.0.0-compat | agent_skills/skill-router/SKILL.md | formal workflow composition | route_planner | raw_request, session_state → route_plan | — | 30000 ms / none | test_skill_router.py | 0 | convert_to_tool |
| task_intake | 1.0.0 | agent_skills/task-intake/SKILL.md | legacy rule router; all formal workflows | attachment_reader | raw_request, attachments, session_state → task_spec, missing_fields, clarification_questions | — | 30000 ms / none | test_prompt_equipment_context.py, test_router_manual_override.py, test_skill_router.py, test_workflow_progress.py | 22 | refactor |
| task_normalization | 1.0.0 | — | formal workflow composition | unit_normalization_service | task_spec → normalized_task_spec | — | 30000 ms / by_task_revision | — | 0 | keep |
| toolpath_strategy_selection | 1.0.0 | — | formal workflow composition | domain_pack_loader | geometry_model, process_route, domain_pack → toolpath_strategy, path_risks | — | 30000 ms / none | — | 0 | keep |
| trial_acceptance_evaluation | 1.0.0 | — | formal workflow composition | trial_service | trial_plan, trial_result → trial_decision, formal_process_unlock | — | 30000 ms / none | — | 0 | keep |
| trial_need_assessment | 1.0.0 | — | formal workflow composition | trial_service | task_spec, equipment_snapshot, evidence_status, approved_priors, similar_cases → trial_required, recommended_mode, reasons | — | 30000 ms / none | — | 0 | keep |
| trial_result_ingestion | 1.0.0 | — | formal workflow composition | trial_service | trial_execution_payload, measurement_payload → trial_result | create_trial_result | 30000 ms / none | — | 0 | keep |
| trial_strategy_selection | 1.0.0 | — | formal workflow composition | trial_service | trial_assessment, user_selection → trial_mode, selection_trace | — | 30000 ms / none | — | 0 | keep |
| trial_to_process_transition | 1.0.0 | — | formal workflow composition | formal_process_gate_service | trial_decision, knowledge_decisions → formal_process_decision | — | 30000 ms / none | — | 0 | keep |

## Duplicate and domain-specific logic

| Skill | Duplicate logic | Domain-specific logic |
|---|---|---|
| bo_dataset_governance | Eligibility rules duplicate validation/BO application services. | None; scenario differences belong in domain packs. |
| bo_recommendation | No material duplication found. | None; scenario differences belong in domain packs. |
| crl_task_planning | Task intake, evidence, route, trial, quality, and report logic duplicate generic skills. | Dual-paraboloid geometry, wavefront/focal-spot quality, and shallow paraboloid trial template are now in the CRL domain pack. |
| experience_memory_update | Alias overlaps knowledge_candidate_generation. | None; scenario differences belong in domain packs. |
| process_file_ingestion | No material duplication found. | None; scenario differences belong in domain packs. |
| rag_literature_retrieval | Alias duplicates rag_evidence_retrieval. | None; scenario differences belong in domain packs. |
| report_generation | No material duplication found. | None; scenario differences belong in domain packs. |
| skill_router | Routing belongs to Agent Runtime route planning. | None; scenario differences belong in domain packs. |
| task_intake | No material duplication found. | None; scenario differences belong in domain packs. |

## Contract enforcement

Every contract declares name, version, purpose, inputs, outputs, preconditions, side effects, allowed/forbidden tools, failure modes, timeout, cache policy, and emitted events. Runtime validation rejects duplicate names, invalid versions, non-positive timeouts, allow/deny conflicts, and direct business-skill access to SQLite/raw SQL.
