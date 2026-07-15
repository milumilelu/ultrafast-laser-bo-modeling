# Agent Tool inventory

## Foreground safe (8)

`get_equipment_context`, `search_knowledge`, `recommend_parameters_bo`, `recommend_parameters_rag`, `propose_exploratory_parameters`, `manage_trial`, `manage_process`, `record_process_result`.

## On demand post-process (3)

`bootstrap_external_knowledge`, `ingest_files`, `generate_report`。这些能力不进入普通前台默认发现集合。

Skill 不控制 Tool 是否存在，只影响推荐顺序。公开 `ToolResult.status` 为 `success / partial / insufficient_data / blocked / validation_error / failed`（探索性参数额外标记 `exploratory`）。
