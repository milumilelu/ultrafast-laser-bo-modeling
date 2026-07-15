# V3.1 Planner ValidationError — After Fix

## 复测范围

- 基线提交：`18f8725086750bb8ba1bf7b7bceee2c56bbdade8`
- 输入：`我想加工 3 mm 厚的 T300 碳纤维板，开一个 4 mm 通孔。`
- 复测方式：固定无效模型输出，经真实 `run_main_agent_turn()` 主链执行。
- 说明：未调用生产模型凭据；以下无效输出是可重复测试夹具，不冒充生产模型原始响应。

## 原始输出与解析结果

```json
{
  "action": "call_tool",
  "decision_summary": "先推荐参数",
  "tool_name": "recommend_parameters",
  "arguments": []
}
```

JSON 解析成功；`AgentAction` 基础类型校验在 `arguments` 处失败。

## 修复后的完整脱敏错误

```json
{
  "loc": "arguments",
  "type": "dict_type",
  "msg": "Input should be a valid dictionary",
  "received": [],
  "expected": "object"
}
```

每个 `model_call_failed` 事件还记录：

```text
parsed_action
raw_model_output（脱敏、截断）
action_schema_version = v31-minimal-action-1
tool_registry_version = v31-foreground-tools-1
failure_stage
will_retry
```

敏感键 `api_key`、`authorization`、`password`、`secret`、`token` 会替换为 `[REDACTED]`。

## Repair 行为

| 调用 | Prompt 字符数 | 行为 |
|---:|---:|---|
| 1 | 10,497 | 完整规划；校验失败 |
| 2 | 965 | 仅修复 Action；再次失败 |

Repair Prompt 为首次 Prompt 的约 `9.2%`，只含原始 Action、解析后 Action、具体错误、最小 Action 约束、允许 Tool 名称和版本号。Repair 只执行一次。

第二次仍失败后，本轮切换为确定性模式，不再调用模型。主链实际继续执行：

```text
get_equipment_context
→ recommend_process_parameters
→ respond
```

复测指标：

```json
{
  "planner_call_count": 3,
  "model_call_count": 2,
  "tool_call_count": 2,
  "repair_count": 1,
  "max_prompt_chars": 10497,
  "total_latency_ms": 296.0
}
```

## 当前最小 AgentAction

```text
update_context
call_tool
ask_user
respond
```

基础 Schema 只检查动作类型、字段类型和必要字段。Tool 名称是否注册仍在 Planner 能力边界检查中；阶段、正式加工权限、参数权限和审核规则不再由基础 `AgentAction` 承担。

`respond` 只结束当前对话轮次。公开投影为：

```text
status = responded
next_required_action.action_type = continue_task
```

它不会再被投影为 `task_completed`。

