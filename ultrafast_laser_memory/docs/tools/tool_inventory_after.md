# Agent tool inventory after refactor

## Core tools (12)

`update_task_context`, `get_equipment_context`, `search_knowledge`, `bootstrap_external_knowledge`, `recommend_parameters_bo`, `recommend_parameters_rag`, `propose_exploratory_parameters`, `manage_trial`, `run_bo_iteration`, `record_process_result`, `create_knowledge_candidate`, `generate_report`.

## On-demand tools (2)

`ingest_files`, `review_knowledge_candidate`.

Initial discovery exposes only `update_task_context` and `get_equipment_context`. Loaded Skill descriptors reveal recommended tools. Every execution returns the same `ToolResult` envelope: `tool_name`, `status`, `data`, `error`, and `meta`.
