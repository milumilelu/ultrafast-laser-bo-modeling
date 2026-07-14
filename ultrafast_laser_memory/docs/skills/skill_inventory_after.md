# Skill inventory after refactor

The Agent-visible registry contains exactly six composable descriptors:

1. `task_understanding`
2. `evidence_research`
3. `process_planning`
4. `parameter_recommendation`
5. `experiment_optimization`
6. `result_learning`

Each descriptor contains `description`, `when_to_use`, `guidance`, and `recommended_tools`. It has no `allowed_tools`; loading a Skill reveals guidance and recommended capabilities but grants no authorization.
