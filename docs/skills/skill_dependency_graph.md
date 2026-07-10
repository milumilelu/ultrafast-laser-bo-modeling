# Skill dependency graph

Skills orchestrate business decisions; low-level persistence, hashing, FTS/vector access, file copying, unit conversion, and threshold calculations remain services/tools.

```mermaid
flowchart TD
  Intake["task_intake"] --> Normalize["task_normalization"]
  Normalize --> Equipment["equipment_context_loading"]
  Normalize --> Material["material_identification"]
  Normalize --> Geometry["geometry_interpretation"]
  Equipment --> Constraints["constraint_extraction"]
  Geometry --> Constraints

  Constraints --> Evidence["rag_evidence_retrieval"]
  Constraints --> History["historical_case_retrieval"]
  History --> Similar["similar_case_retrieval"]
  Evidence --> Route["process_route_planning"]
  Similar --> Route
  Route --> Risk["process_risk_assessment"]
  Route --> TrialNeed["trial_need_assessment"]
  TrialNeed --> TrialSelect["trial_strategy_selection"]
  TrialSelect --> Simple["simple_trial_design"]
  TrialSelect --> Full["full_trial_design"]

  Equipment --> ParamSpace["parameter_space_construction"]
  Evidence --> KnowledgeGate["knowledge_use_gate"]
  KnowledgeGate --> ParamSpace
  ParamSpace --> BOMode["bo_mode_selection"]
  BOMode --> BO["bo_recommendation"]
  BO --> Candidate["candidate_validation"]
  Simple --> FormalGate["formal_process_gate"]
  Full --> FormalGate
  Candidate --> FormalGate
  KnowledgeGate --> FormalGate

  Route --> Quality["quality_plan_generation"]
  Quality --> Measurement["measurement_plan_generation"]
  FormalGate --> Execution["execution_plan_generation"]
  Route --> Monitoring["in_process_monitoring_plan"]
  Execution --> Report["report_generation"]
  Monitoring --> Report
  Trace["execution_trace_summary"] --> Report

  CRLAlias["crl_task_planning (deprecated)"] -.-> OpticalWorkflow["optical_component_task_workflow"]
  OpticalWorkflow --> CRLPack["CRL domain pack"]
  RAGAlias["rag_literature_retrieval (deprecated)"] -.-> Evidence
  MemoryAlias["experience_memory_update (deprecated)"] -.-> CandidateKnowledge["knowledge_candidate_generation"]
```

## Service/tool boundary

The following are not Skills: SQLite reads/writes, FTS/vector query mechanics, SHA256, equipment configuration loading, unit conversion, threshold comparison, PDF extraction, file copying, and CSV writing. Contracts can call application services that encapsulate those operations, but cannot list `sqlite`, `database_connection`, or `raw_sql` as allowed tools.
