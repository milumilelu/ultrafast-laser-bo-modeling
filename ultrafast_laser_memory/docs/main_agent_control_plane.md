# Main Agent 控制平面

日期：2026-07-14

## 当前边界

- Main Agent 统一处理对话、澄清、Skill 组合和多轮 Tool 调用。
- Skill 是可选软指导，可同时加载多个，不拥有流程控制权。
- Tool Registry 是可执行能力事实源；输入缺口、权限、设备边界和人工审批在 Tool 执行边界校验。
- TaskSpec 渐进式补充，不存在所有加工任务共用的必填字段表。
- BusinessState 是事件投影，仅服务进度、审计、恢复和 TUI。
- 正式加工、知识晋升、BO 样本准入和设备物理边界仍 fail-closed。

## 对话执行

```text
User -> Main Agent -> Tool -> Observation -> Main Agent -> ... -> Answer
              |          |
              |          +-- deterministic policy/validation
              +-- optional multi-skill guidance
```

`update_task_context` 负责字段白名单、单位、适用性、原文证据、冲突和显式修正语义。初始仅发现它和 `get_equipment_context`；加载六项 Skill 后逐步发现 12 个核心工具与 2 个按需工具。所有执行统一返回 `ToolResult`；缺失上下文时返回 `insufficient_data`，由 Main Agent 决定追问、换工具或停止。

## 通孔回归基线

输入：`在4mm厚的金刚石上加工一个直径2mm的通孔`

最低事实：`material=diamond`、`thickness_mm=4`、`process_type=hole_drilling`、`geometry.hole_diameter_mm=2`、`geometry.through_hole=true`。不得要求 `cut_length_mm`，首次结构化输出校验失败必须进入无严格 Schema 的第二次修复请求，不能退化为全局表单。
