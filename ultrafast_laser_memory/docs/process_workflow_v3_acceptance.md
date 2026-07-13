# 加工工作流 V3 验收记录

日期：2026-07-13

## 结论

V3 软件整改已实现并通过回归测试。系统现在对加工任务执行 fail-closed 工作流；未完成需求确认、试切选择、试切结果验证、知识准入、正式放行和最终检测时，不得进入后续阶段。

## 已实现

- 加工任务强制路由至 `complex_process_task`，需求字段检查先于 RAG/BO。
- 确定性加工状态机和 Campaign 状态机，拒绝非法跨阶段迁移。
- 动态进度、Workflow overview、NextAction、Skill/Tool/Public reasoning trace。
- BO → RAG → 受控 LLM fallback 参数策略；聊天模型不得自由生成参数。
- 统一参数 Schema、来源权限、设备边界校验和 provenance 输出。
- RAG 来源追溯、上下文匹配、审核状态和可信度汇总。
- 用户未明确选择简化/完整/跳过试切时停在 `TRIAL_MODE_PENDING`。
- Observation validation、fidelity 隔离、BO 样本准入和模型快照门。
- 正式加工 release、preflight、start、checkpoint、pause/resume/abort/finish、inspection、quality decision、rework、report 和 archive API。
- `/chat` 已贯通“试切通过 → preflight → 正式加工检查点 → 最终检测 → BO 准入 → 报告 → 归档”，活动任务的 JSON 输入不会再掉回普通聊天路由。
- 正式计划、执行、检查点、终检、质量判定、实验记录、Campaign、Observation、Model snapshot 和参数 provenance 已写入 SQLite；服务重启不再丢失核心闭环记录。
- 正式加工只允许批准窗口、设备边界和局部信赖域的交集。
- Debug 命令 `/trace`、`/tools`、`/skills`、`/reasoning`、`/waterfall`、`/campaign`、`/model`。
- Trace 敏感字段脱敏，禁止保存或输出隐藏 chain-of-thought。
- HTTP 429/503 和 “Selected model is at capacity” 的明确、安全错误处理。
- SQLite V3 表：正式加工、检测、质量决策、实验记录、Campaign、Iteration、Candidate、Observation、Model snapshot、Parameter provenance、Public reasoning trace。

## 验证

- 全量回归：`167 passed`。
- 新增端到端用例覆盖 T300 多轮需求补齐、强制试切选择，以及试切通过后直到正式加工归档的完整对话闭环。
- `ruff`（V3、聊天及相关测试模块）：通过。
- `compileall`：通过。
- `git diff --check`：通过；仅有 Git 的 LF→CRLF 提示，无空白错误。

测试中的 scikit-learn `ConvergenceWarning` 为既有小样本高斯过程拟合警告，不是测试失败；V3 会将相应数据支持度判为 cold-start/partial，不把警告模型冒充已验证正式工艺。

## 边界

Demo 的“正式加工”是离线确定性模拟，不控制真实激光设备。真实设备执行仍需操作者确认、设备接口和现场安全联锁。
