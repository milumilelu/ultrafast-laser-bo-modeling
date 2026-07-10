# Examples

## Normal

Input: `我有 recipe 和检测 CSV，帮我自动读取进记忆库。`

Output: `process-file-ingestion`, because the request contains process files and ingestion intent.

## Missing

Input: `帮我做个超快激光方案。`

Output: `task-intake`, low confidence, ask for material, geometry, and target metric.

## Refusal

Input: `直接给我功率和扫描速度。`

Output: `task-intake` or `bo-recommendation` depending on context, but do not generate parameters.
