# Agent Tool inventory

## Foreground safe (6)

`get_equipment_context`, `search_knowledge`, `recommend_process_parameters`, `manage_trial`, `manage_process`, `record_process_result`.

`recommend_parameters_bo` 与 `recommend_parameters_rag` 仅是参数 Tool 内部实现，Planner 不直接选择。

## On demand post-process (3)

`bootstrap_external_knowledge`, `ingest_files`, `generate_report`。这些能力不进入普通前台默认发现集合。

Skill 不控制 Tool 是否存在或权限。公开 `ToolResult.status` 为 `success / partial / insufficient_data / blocked / validation_error / failed`。
