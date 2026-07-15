# Main Agent 控制平面

日期：2026-07-15

唯一前台链路为 `User ↔ MainAgentLoop ↔ WorkingContext / Skills / Tools`。Planner 的 `context_updates` 直接更新开放式内存上下文；持久化、Trace、报告与治理失败只产生 warning。

全部八个前台安全 Tool 始终可发现；六项 Skill 只提供专业指导和排序提示。Router 只输出 intent/Skill hint。试切与正式加工分别收敛为 `manage_trial`、`manage_process`，并由 Main Agent 根据 Observation 动态迭代。

正常结束仅由 `ask_user` 或 `final_answer` 等语义动作决定。相同 Tool、参数和 Observation 会复用已有观察；连续无进展触发 probable-agent-loop。30 次内部 emergency breaker 只防程序失控，不作为业务步数限制。

人工确认只对当前 `manage_trial.start` 或 `manage_process.start` 生效。参数结果保留 `source_type`、`source_refs`、`data_support`、`evidence_level`、`uncertainty`、`limitations` 和 `recommended_use`。
