# V3.1 首次运行时稳定性修复报告

## 结论

首次提交范围 A–F 已完成。`/chat` 不再因 `AgentAction ValidationError` 直接中断；T300 最小任务可从事实提取连续推进到设备读取、统一参数推荐和试切模式选择。

本次没有继续 V3.1 后续大规模重构。

## 修改内容

1. `AgentAction` 收敛为 `update_context | call_tool | ask_user | respond`，并明确 `respond != task_completed`。
2. 基础 Pydantic 校验仅保留类型和必要字段；移除复杂计划、权限和阶段业务校验。
3. Debug 错误增加 `location/type/received/expected/parsed_action/schema version/tool registry version`，并执行敏感字段脱敏。
4. 首次失败后只发送一次小型 Action Repair Prompt；Repair 再失败后，本轮强制走确定性 fallback。
5. Fallback 顺序覆盖：等待输入、阻塞字段、设备上下文、统一参数推荐、当前阶段回复。
6. 修复 `开一个 4 mm 通孔` 的直径提取，T300、CFRP、3 mm、4 mm 通孔均进入唯一 WorkingContext。
7. 单个阻塞字段可只问一个问题，不再要求凑足 3–5 问。
8. 单轮 Planner/模型调用硬上限为 6，并记录调用数、Prompt 大小、Repair 数和延迟。
9. 参数公开观察增加 BO 支持度、uncertainty、fidelity、来源、权限和内部 BO→RAG→LLM fallback 顺序。

## 删除或停用内容

- 从 Action 合同删除 `final_answer`，旧模型输出仅在兼容归一化层映射到 `respond`。
- 停止 Repair 重发完整规划 Prompt。
- 停止 Repair 失败后返回终止式错误答复。
- 停止基础 `AgentAction` 承担 ProcessPlan/TrialPlan、参数权限和阶段业务规则。
- 停止把当前轮 `respond` 投影为任务完成。

本次 A–F 范围没有删除受 Git 跟踪的文件。提交使用 `git add -A`，因此仓库内若存在本地删除，也会同步为 Git 删除，而不是只提交新增文件。

## ValidationError 前后对比

修复前：

```text
第 1 次 Prompt = 9,665 字符
第 2 次 Prompt = 9,914 字符
两次失败后 final_answer，任务停止
错误日志缺少 received/expected
```

修复后：

```text
第 1 次 Prompt = 10,497 字符
Repair Prompt = 965 字符
repair_count = 1
received = []
expected = object
失败后继续 get_equipment_context → recommend_process_parameters → respond
```

完整记录见：

- `reports/v31_validation_error_before.md`
- `reports/v31_validation_error_after.md`

## 最小 T300 对话结果

```text
输入：3 mm T300 CFRP，4 mm 通孔
提取：T300 / CFRP / 3.0 mm / through_hole / 4.0 mm
工具：get_equipment_context → recommend_process_parameters
策略：BO partially_supported → RAG insufficient_data → LLM fallback 未调用
来源：bo_cold_start
权限：仅允许试切；禁止正式加工和 BO 训练
最终：respond；NextAction 为选择简化试切或完整试切
```

完整回放见 `reports/v31_minimal_chat_replay.txt`。

## 测试结果

```text
指定新增测试：12 passed
全量测试：270 passed, 8 warnings
Ruff：All checks passed
```

8 条 warning 均来自既有 scikit-learn Gaussian Process 收敛/边界提示，不是本次新增失败。

## 回滚

```text
tag = v31-runtime-fix-baseline-20260716
commit = 18f8725086750bb8ba1bf7b7bceee2c56bbdade8
bundle = C:\Users\94494\Desktop\ultrafast-agent-backups\ultrafast-agent-v31-baseline-18f8725.bundle
```

Tag 已推送，bundle 已通过 `git bundle verify`。

## 仍存在的问题

1. ValidationError 复现使用固定无效模型输出；没有伪称它来自生产模型。
2. 当前真实 T300 回放得到的是 0 匹配样本的规则冷启动候选，证据仅为 `partially_supported`。
3. RAG 未找到可用参数证据，受控 LLM fallback 未授权、未调用。
4. 因此当前结果只证明主聊天链恢复连续运行，不证明参数已具备正式加工可信度。

## 后续建议

按任务要求在首次提交后停止。待人工确认本提交后，再依次处理统一 Task Intake、统一 WorkingContext、Router/Skill 收口及正式加工闭环；不得并行扩大重构范围。

