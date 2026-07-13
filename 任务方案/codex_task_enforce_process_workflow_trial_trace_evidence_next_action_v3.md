# Codex 整改任务 V3：强制加工工作流、参数推荐工具链、迭代优化、完整 Skill/Tool 轨迹、公开推理摘要与正式加工闭环

更新时间：2026-07-10

## 0. 整改背景

当前演示没有按照已经设定的加工智能体工作流运行。

示例任务：

```text
切割 5 mm 厚 T300 碳纤维板
质量要求：切缝区域无分层
辅助条件：压缩空气
允许层切
无效率要求
```

当前系统实际表现：

```text
任务解析
→ 设备配置读取
→ LLM 直接生成参数建议
→ 提示用户自行试切
```

缺失了以下关键环节：

```text
试切必要性评估
试切模式选择
RAG 真实检索
资料来源和可信度分析
Skill 调用链展示
Tool 调用链展示
知识使用决策门
参数来源分类
下一步输入契约
任务总流程和当前进度
```

更严重的问题是，当前回复直接给出了：

```text
4.0 W
150 kHz
500 fs
20 mm/s
500–1000 次扫描
0.2–0.5 MPa 压缩空气
典型去除阈值 5–10 J/cm²
飞秒热影响区 <1 μm
```

但回复同时声明：

```text
未接入实时文献库
参数来自内部经验估算
未经过验证
```

这违反系统的核心安全边界：

```text
LLM 不得凭空生成工艺参数；
没有可靠证据时不得输出确定性参数；
未经审核的文献参数不得进入工艺建议；
试切策略必须先于参数推荐；
设备边界不等于工艺可用区间。
```

本任务的目标是将这些要求从“提示词建议”升级为“代码级强制工作流”。

V3 新增三项核心原则：

```text
1. 参数推荐优先级：
   工艺数据库与 BO
   → RAG 规则/工艺先验/文献
   → 受控 LLM 兜底参数工具。

2. 试切和正式加工不是单轮操作，而是带预算、停止条件、
   模型快照和数据准入门的迭代 Campaign。

3. 调试阶段尽可能公开执行过程：
   公开任务分析摘要、候选方案、证据比较、决策依据、
   全部实际 Skill 调用和 Tool Call；
   但不得输出模型隐藏 chain-of-thought、内部草稿或敏感信息。
```

---

# 1. 整改目标

完成后，每个加工任务必须遵循：

```text
任务流程展示
→ 当前进度展示
→ 任务字段解析
→ 缺失字段检查
→ 设备配置读取
→ Skill 路由
→ Tool 执行
→ RAG / 历史案例 / 工艺规则检索
→ 证据可信度评估
→ 试切必要性评估
→ 简化试切 / 完整试切 / 跳过试切选择
→ 用户选择试切模式
→ 生成对应试切方案
→ 用户提交试切结果
→ 试切结果评价
→ 知识使用审核
→ BO 或保守参数优化
→ 正式加工规划
→ 结果与下一步需求
```

任何情况下，不允许从“设备边界已读取”直接跳到“具体参数推荐”。

---

# 2. 当前演示问题诊断

## 2.1 没有试切模式选择

当前回复只说：

```text
请务必进行工艺试验
```

但没有调用：

```text
trial_need_assessment
trial_strategy_selection
simple_trial_design
full_trial_design
```

也没有向用户展示：

```text
[简化试切]
[完整试切]
[跳过试切]
```

## 2.2 Skill 和 Tool 轨迹不完整

当前只展示：

```text
读取设备配置
路由决策
```

未展示：

```text
调用了哪个 Skill
为什么选择该 Skill
Skill 输入摘要
Skill 输出摘要
调用了哪些 Tool
RAG 是否实际运行
历史案例是否检索
试切策略是否执行
审核门是否执行
BO 是否执行
```

当前“路由决策：No high-confidence domain rule matched”也没有告诉用户：

```text
回退到了什么 Workflow
哪些规则未命中
采用了什么 fallback
```

## 2.3 没有资料来源和可信度分析

当前回复承认：

```text
未接入实时文献库
```

但系统此前已经实现内部 RAG。

这说明：

```text
/chat 没有真正调用 RAG；
或者路由没有强制 requires_internal_rag；
或者 RAG 调用失败后没有显式报告；
或者 LLM 绕过了 Evidence Pack。
```

## 2.4 没有下一步输入契约

当前只笼统要求：

```text
记录扫描次数
检查是否分层、崩边、石墨化
```

没有明确要求用户提交哪些字段、单位、文件和判定结果。

## 2.5 没有整体流程和当前进度

当前只显示：

```text
[进度 80%]
```

但用户并不知道：

```text
为什么已经 80%
总流程有多少阶段
当前在哪个阶段
哪些阶段尚未完成
为什么最终回答仍然只是初步建议
```

因此当前进度百分比没有业务意义。

---

# 3. 强制状态机

新增统一加工任务状态机：

```text
CREATED
INTAKE
REQUIREMENTS_PENDING
REQUIREMENTS_CONFIRMED
EQUIPMENT_LOADING
EVIDENCE_RETRIEVAL
EVIDENCE_ASSESSMENT
TRIAL_ASSESSMENT
TRIAL_MODE_PENDING
TRIAL_PLAN_READY
TRIAL_EXECUTION_PENDING
TRIAL_RESULT_PENDING
TRIAL_RESULT_EVALUATION
KNOWLEDGE_APPROVAL_PENDING
BO_READY
BO_RUNNING
FORMAL_PROCESS_READY
COMPLETED
BLOCKED
FAILED
```

## 3.1 合法状态迁移

```text
CREATED
→ INTAKE

INTAKE
→ REQUIREMENTS_PENDING
或 REQUIREMENTS_CONFIRMED

REQUIREMENTS_CONFIRMED
→ EQUIPMENT_LOADING
→ EVIDENCE_RETRIEVAL
→ EVIDENCE_ASSESSMENT
→ TRIAL_ASSESSMENT

TRIAL_ASSESSMENT
→ TRIAL_MODE_PENDING
或 BLOCKED

TRIAL_MODE_PENDING
→ TRIAL_PLAN_READY

TRIAL_PLAN_READY
→ TRIAL_EXECUTION_PENDING
→ TRIAL_RESULT_PENDING

TRIAL_RESULT_PENDING
→ TRIAL_RESULT_EVALUATION

TRIAL_RESULT_EVALUATION
→ KNOWLEDGE_APPROVAL_PENDING
或 BO_READY
或 BLOCKED

BO_READY
→ BO_RUNNING
→ FORMAL_PROCESS_READY

FORMAL_PROCESS_READY
→ COMPLETED
```

禁止：

```text
EQUIPMENT_LOADING
→ FORMAL_PROCESS_READY

EQUIPMENT_LOADING
→ 参数推荐

EVIDENCE_RETRIEVAL 失败
→ LLM 自行补参数

TRIAL_MODE_PENDING
→ 默认替用户选择完整试切

未收到试切结果
→ 声称试切通过

未审核参数
→ 写入 process_prior

未审核参数
→ 进入 BO 搜索边界
```

---

# 4. 每次回答必须包含任务流程和当前进度

每次 `/chat` 响应必须包含：

```json
{
  "workflow_overview": [],
  "current_stage": "",
  "completed_stages": [],
  "pending_stages": [],
  "blocked_stages": [],
  "next_required_action": {},
  "progress": {
    "completed_steps": 0,
    "total_steps": 0,
    "percent": 0
  }
}
```

## 4.1 进度必须基于真实步骤

禁止硬编码：

```text
task_spec_confirmed = 80%
```

建议按当前 Workflow 动态计算：

```python
percent = completed_required_steps / total_required_steps * 100
```

如果任务需要 10 个阶段，完成 4 个阶段：

```text
进度 = 40%
```

## 4.2 用户可读格式

每次回复顶部显示：

```text
任务流程
1. 任务需求确认               已完成
2. 设备边界读取               已完成
3. 文献/历史案例检索          已完成
4. 证据可信度评估             已完成
5. 试切方式选择               等待用户
6. 试切方案生成               未开始
7. 试切结果评价               未开始
8. BO 参数优化                未开始
9. 正式加工方案               未开始

当前阶段：试切方式选择
总体进度：4/9（44%）
```

不要只给一个没有解释的百分比。

---

# 5. 强制 Skill 调用流程

对于加工任务，Router 必须选择：

```text
complex_process_task
```

该 Workflow 至少调用：

```text
task_intake
equipment_context_loading
material_identification
geometry_interpretation
constraint_extraction
rag_evidence_retrieval
historical_case_retrieval
process_risk_assessment
trial_need_assessment
trial_strategy_selection
```

用户选择试切模式后，再调用：

```text
simple_trial_design
或
full_trial_design
```

试切结果提交后，再调用：

```text
trial_result_ingestion
trial_acceptance_evaluation
knowledge_use_gate
bo_mode_selection
bo_recommendation
formal_process_gate
report_generation
```

## 5.1 Skill 不得被 LLM 隐式替代

错误：

```text
LLM 根据 prompt 自行决定“建议试切”
```

正确：

```text
TrialNeedAssessmentSkill.execute()
TrialStrategySelectionSkill.execute()
```

---

# 6. 强制 Tool 调用流程

加工任务至少可能使用：

```text
equipment_memory_tool
rag_query_tool
historical_case_tool
process_rule_tool
trial_template_tool
knowledge_approval_tool
bo_engine_tool
report_writer_tool
```

## 6.1 工具调用轨迹

每个工具必须发：

```text
tool_started
tool_completed
```

失败时：

```text
tool_failed
fallback
```

## 6.2 ToolTrace

```json
{
  "tool_name": "rag_query_tool",
  "status": "completed",
  "input_summary": {
    "material": "CFRP_T300",
    "process_type": "cutting",
    "thickness_mm": 5
  },
  "output_summary": {
    "paper_count": 4,
    "chunk_count": 8,
    "evidence_status": "partial"
  },
  "duration_ms": 312,
  "evidence_ids": [
    "chunk_001",
    "chunk_002"
  ]
}
```

## 6.3 TUI 模式

Normal：

```text
显示当前阶段和关键工具
```

Research：

```text
显示全部 Skill 和 Tool
```

Debug：

```text
显示 Skill 输入输出摘要、Tool 输入输出摘要、缓存、fallback 和耗时
```

用户当前明确要求“展示调用的所有 Skill 和 Tool”，因此演示默认模式应为：

```text
/mode research
```

---

# 7. 资料来源和可信度分析

每次使用 RAG 后，必须生成：

```text
Evidence Credibility Summary
```

## 7.1 返回结构

```json
{
  "evidence_status": "sufficient|partial|insufficient",
  "sources": [
    {
      "paper_id": "",
      "title": "",
      "authors": "",
      "year": "",
      "doi": "",
      "page_start": 0,
      "page_end": 0,
      "chunk_id": "",
      "review_status": "approved|pending_review|needs_review|rejected",
      "evidence_level": "raw_literature|literature_evidence|process_prior",
      "relevance_score": 0.0,
      "applicability": {
        "material_match": true,
        "thickness_match": false,
        "process_match": true,
        "equipment_match": false
      },
      "credibility": "high|medium|low",
      "limitations": []
    }
  ],
  "approved_source_count": 0,
  "pending_source_count": 0,
  "rejected_source_count": 0,
  "warnings": []
}
```

## 7.2 可信度计算

至少考虑：

```text
是否有 DOI
是否可追溯到原始 PDF
是否有页码
是否经过人工审核
材料是否匹配
厚度是否匹配
工艺是否匹配
设备条件是否匹配
是否为单一来源
是否存在冲突
是否包含完整实验条件
```

建议分级：

### High

```text
来源可追溯
经过审核
材料和工艺匹配
实验条件完整
至少两篇独立来源支持
```

### Medium

```text
来源可追溯
未完成知识晋升审核
材料或厚度部分匹配
可用于背景和试切设计
```

### Low

```text
只有单篇
材料不完全匹配
缺少实验条件
无法确认参数适用性
只能用于检索提示
```

## 7.3 演示输出

必须显示：

```text
资料库检索结果：
- 命中 8 个 chunk，来自 4 篇论文
- 已审核资料源：1
- 待审核资料源：3
- 当前证据充分度：partial
- 可用于：缺陷识别、试切测量项设计
- 不可用于：直接参数推荐、BO 搜索边界
```

## 7.4 RAG 失败与参数推荐链

RAG 不是所有参数推荐的第一入口。参数推荐必须先经过统一策略：

```text
BO 参数推荐
→ RAG 参数推荐
→ 受控 LLM 兜底参数工具
```

如果 BO 数据充分：

```text
RAG 失败不阻止 BO 推荐；
但必须明确缺少文献解释、冲突检查或外部证据。
```

如果 BO 数据不足且 RAG 失败：

```text
默认阻止普通参数推荐；
只有策略允许、用户允许探索性试切、设备硬边界完整时，
才可调用 llm_fallback_parameter_tool。
```

禁止聊天模型直接使用：

```text
内部经验估算
常识估算
模型先验
```

绕过专用参数工具。

---

# 8. 参数推荐工具链、来源优先级与权限控制

参数推荐必须是工具调用结果，不得由聊天 LLM 在自由文本中直接生成。

统一优先级：

```text
第一优先级：工艺数据库 + 贝叶斯优化器
第二优先级：RAG 规则库 / 工艺先验 / 文献库
第三优先级：受控 LLM 兜底参数工具
```

## 8.1 LLM 的职责边界

LLM 负责：

```text
任务分析
任务拆解
流程规划
选择 Skill
调用参数推荐工具
解释工具结果
生成试切和检测计划
汇总下一步需求
```

LLM 不直接负责：

```text
自由生成工艺参数
自行判断设备安全边界
直接修改 BO 搜索空间
批准文献先验
写入 process_prior
写入 BO 数据集
```

正确关系：

```text
LLM = Orchestrator
BO/RAG/LLM fallback = Parameter Tools
Policy/Gate = 准入控制
数据库 = 事实来源
```

## 8.2 参数推荐策略服务

新增确定性服务：

```text
ParameterRecommendationPolicy
```

它只决定调用顺序和权限，不直接产生参数。

```python
def recommend_parameters(context):
    bo_result = bo_parameter_recommendation_tool.run(context)

    if bo_result.support_status == "supported":
        return parameter_constraint_validation_tool.run(bo_result)

    if bo_result.support_status == "partially_supported":
        rag_prior = rag_parameter_recommendation_tool.run(
            context.with_intended_use("bo_prior")
        )
        prior_decision = knowledge_use_gate.evaluate(rag_prior)

        if prior_decision.allowed:
            hybrid_result = bo_parameter_recommendation_tool.run(
                context.with_priors(prior_decision.approved_payload)
            )
            return parameter_constraint_validation_tool.run(hybrid_result)

    rag_result = rag_parameter_recommendation_tool.run(
        context.with_intended_use("simple_trial")
    )

    if rag_result.support_status == "supported":
        return parameter_constraint_validation_tool.run(rag_result)

    if rag_result.support_status == "partially_supported":
        return request_aggregated_review(rag_result)

    if not context.allow_llm_fallback:
        return blocked("工艺数据库与知识库均不足")

    llm_result = llm_fallback_parameter_tool.run(
        task_spec=context.task_spec,
        equipment_snapshot=context.equipment_snapshot,
        bo_insufficiency_report=bo_result.insufficiency_report,
        rag_insufficiency_report=rag_result.insufficiency_report,
        intended_use="simple_trial",
    )
    return validate_for_simple_trial_only(llm_result)
```

## 8.3 BO 参数推荐工具

新增：

```text
bo_parameter_recommendation_tool
```

BO 是默认首选参数来源。

输入至少包括：

```text
task_spec
material_context
geometry_context
equipment_snapshot
quality_objectives
process_constraints
fidelity_level
campaign_id
```

工具首先执行数据支持度评估：

```text
同材料或兼容材料样本数
同工艺样本数
同设备或兼容设备样本数
相近厚度样本数
相似几何样本数
同 fidelity 样本数
质量指标完整度
异常数据比例
模型验证指标
预测不确定度
```

返回：

```text
supported
partially_supported
insufficient
```

不得只根据全局样本总数判断。

BO 模式：

```text
data_driven_bo
hybrid_rule_bo
rule_based_cold_start
```

含义：

```text
data_driven_bo：
工艺数据库充分，BO 独立推荐；
RAG 用于解释和冲突检查。

hybrid_rule_bo：
数据部分充分；
RAG 提供经审核的边界、先验或约束；
BO 在该先验下推荐。

rule_based_cold_start：
BO 数据不足；
RAG 提供冷启动先验；
BO 负责试验覆盖、候选排序和后续迭代。
```

## 8.4 RAG 参数推荐工具

新增：

```text
rag_parameter_recommendation_tool
```

它不同于普通 `rag_query_tool`，必须完成：

```text
结构化参数提取
实验条件匹配
单位归一化
审核状态识别
来源可信度评价
文献冲突分析
参数范围合并
设备边界裁剪
推荐权限判断
```

检索优先级：

```text
validated_rule
approved_process_prior
verified_experiment
reviewed_literature_evidence
pending_review_literature
raw_literature_chunk
```

RAG 参数推荐输出必须说明：

```text
可用于简化试切
可用于完整试切
可用于正式加工
可用于 BO 先验
是否需要审核
```

## 8.5 受控 LLM 兜底参数工具

新增：

```text
llm_fallback_parameter_tool
```

只有以下条件全部满足才允许调用：

```text
BO support_status == insufficient
RAG support_status == insufficient
任务允许试切
用户允许探索性候选
设备硬边界完整
ParameterRecommendationPolicy 明确授权
```

输出权限固定为：

```text
authority_level = exploratory_hypothesis
recommendation_scope = simple_trial_only
allowed_for_full_trial = false
allowed_for_formal_process = false
allowed_for_bo_prior = false
requires_user_approval = true
requires_trial_validation = true
```

允许：

```text
受控地生成少量简化试切候选
```

禁止：

```text
生成正式加工参数
生成 BO 硬边界
写入 process_prior
声称参数已验证
```

因此需要区分：

```text
free_form_llm_estimate：
聊天模型自由估算，始终禁止。

llm_fallback_hypothesis：
专用工具经 Policy 授权产生，仅允许简化试切。
```

## 8.6 统一参数推荐 Schema

三个参数工具必须返回同一结构：

```json
{
  "recommendation_id": "",
  "recommendation_mode": "bo|bo_with_rag_prior|rag|llm_fallback",
  "support_status": "supported|partially_supported|insufficient",
  "authority_level": "verified|reviewed|evidence_based|exploratory",
  "intended_use": "simple_trial|full_trial|formal_process|bo_prior",
  "parameters": [
    {
      "name": "",
      "value": null,
      "range": null,
      "unit": "",
      "source_type": "",
      "source_refs": [],
      "confidence": 0.0,
      "allowed_for_simple_trial": true,
      "allowed_for_full_trial": false,
      "allowed_for_formal_process": false,
      "allowed_for_bo_prior": false
    }
  ],
  "context_match": {},
  "data_support": {},
  "uncertainty": {},
  "constraints_applied": [],
  "warnings": [],
  "requires_review": false,
  "requires_trial_validation": true
}
```

## 8.7 参数来源类型

```text
user_input
equipment_bound
validated_rule
approved_process_prior
verified_experiment
bo_recommendation
bo_recommendation_with_rag_prior
rag_parameter_recommendation
pending_review_rag_candidate
llm_fallback_hypothesis
free_form_llm_estimate
```

## 8.8 各来源权限

| 参数来源 | 简化试切 | 完整试切 | 正式加工 | BO 先验 |
|---|---:|---:|---:|---:|
| `bo_recommendation` 且数据充分 | 是 | 是 | 试切或历史验证后 | 是 |
| `bo_recommendation_with_rag_prior` | 是 | 是 | 试切通过后 | 是 |
| `approved_process_prior` | 是 | 是 | 试切通过后 | 是 |
| `verified_experiment` | 是 | 是 | 是，需匹配条件 | 是 |
| `rag_parameter_recommendation` 已审核 | 是 | 审核后 | 否 | 审核后 |
| `pending_review_rag_candidate` | 审核后 | 否 | 否 | 否 |
| `llm_fallback_hypothesis` | 用户确认后 | 否 | 否 | 否 |
| `free_form_llm_estimate` | 否 | 否 | 否 | 否 |

正式加工参数必须来自：

```text
通过试切或历史验证的 BO 推荐
或
已验证实验
或
经审核先验与 BO 组合推荐
```

纯 RAG 或 LLM fallback 不能直接进入正式加工。

## 8.9 参数约束校验工具

新增：

```text
parameter_constraint_validation_tool
```

依次执行：

```text
单位校验
设备硬边界
材料/工艺规则
知识使用权限
历史失败区域
组合安全规则
试切/正式加工用途权限
重复候选检查
```

## 8.10 参数来源注册

新增：

```text
parameter_provenance_registry_tool
```

每个参数必须记录：

```json
{
  "parameter_name": "scan_speed_mm_s",
  "value": 20,
  "unit": "mm/s",
  "source_type": "rag_parameter_recommendation",
  "recommendation_id": "",
  "source_refs": [],
  "authority_level": "reviewed",
  "allowed_for_simple_trial": true,
  "allowed_for_formal_process": false
}
```

设备边界只能说明：

```text
设备允许范围
```

不能直接当作：

```text
工艺推荐范围
```
# 9. 双模式试切必须先让用户选择

## 9.1 试切策略响应

任务信息确认和证据评估后，系统必须返回：

```text
试切方式建议

推荐：简化试切
原因：
- 5 mm T300 厚板属于复杂、高风险切割任务
- 当前没有已批准的同条件工艺先验
- 当前证据不足以支持直接完整参数建议
- 简化试切可先验证单位去除量和分层风险

可选：
[1] 简化试切
[2] 完整试切
[3] 暂不试切，只查看方案框架
```

禁止系统直接代替用户选择。

## 9.2 简化试切方案

对于 5 mm T300 碳纤维切割，简化试切应优先设计：

```text
测试对象：
同材料废料或见证试样

测试几何：
短直线切缝
或小矩形开口
或浅槽分层去除测试

目标：
标定单次/固定扫描次数去除深度
检查切缝边缘和层间分层
检查排渣
检查热影响和树脂退化
```

参数矩阵必须由 `ParameterRecommendationPolicy` 产生，优先级为：

```text
BO 参数推荐
→ RAG 参数推荐
→ 经授权的 LLM 兜底参数工具
```

如果 BO 和 RAG 均不足，但用户未允许 LLM 探索性兜底：

```text
只生成变量设计和测量方案；
不生成数值候选。
```

如果用户允许 LLM 兜底：

```text
只能生成少量简化试切候选；
必须标记为 exploratory_hypothesis；
不得用于完整试切、正式加工或 BO 先验。
```

## 9.3 完整试切方案

必须包含：

```text
完整切割几何
完整层切路径
中间检查节点
停机条件
检测计划
失败回退
```

---

# 10. 下一步输入契约

每次回答结尾必须给出：

```text
下一步需要用户提供什么
提供格式
单位
是否必填
示例
```

## 10.1 选择试切模式时

```json
{
  "next_action": "select_trial_mode",
  "required": true,
  "options": [
    "simple_trial_cut",
    "full_trial_cut",
    "view_framework_only"
  ]
}
```

## 10.2 简化试切结果输入

系统必须明确要求：

```text
必填：
1. 试样材料及板号
2. 实际厚度 mm
3. 实际激光功率 W
4. 实际频率 kHz
5. 实际脉宽 fs
6. 实际扫描速度 mm/s
7. 扫描次数
8. 切缝长度 mm
9. 实际去除深度或是否穿透
10. 是否出现分层
11. 最大分层宽度 μm 或 mm
12. 是否出现崩边
13. 是否出现树脂烧蚀/石墨化
14. 切缝宽度 μm 或 mm
15. 辅助气体压力 MPa
16. 加工时间 s 或 min

推荐上传：
17. 切缝正面照片
18. 切缝背面照片
19. 截面显微照片
20. 测量 CSV
21. 原位监测日志
```

## 10.3 用户可复制模板

```text
试切模式：简化试切
材料：T300 CFRP
厚度：5 mm
功率：
频率：
脉宽：
扫描速度：
扫描次数：
试切几何：
切缝长度：
去除深度/是否穿透：
是否分层：
最大分层宽度：
是否崩边：
是否石墨化/树脂烧损：
切缝宽度：
气体压力：
加工时间：
照片/文件：
备注：
```

## 10.4 未收到结果时

系统必须保持：

```text
TRIAL_RESULT_PENDING
```

不得继续生成正式加工参数。

---

# 11. 每次回答的固定结构

加工任务的每次回答必须按以下结构输出。

## 11.1 固定章节

```text
1. 任务流程与当前进度
2. 已确认任务信息
3. 当前执行的 Skill 与 Tool
4. 设备配置与硬边界
5. 资料库来源与可信度
6. 当前阶段结论
7. 可选操作
8. 下一步需要提供的内容
9. 风险和限制
```

## 11.2 第一轮信息不足

输出：

```text
任务流程
当前进度
已知字段
缺失字段
当前只执行了哪些 Skill/Tool
下一步需要回答的问题
```

此时不得给参数。

## 11.3 信息确认后

输出：

```text
任务流程
当前进度
Skill/Tool
RAG 结果
可信度
试切推荐
三个选项
```

此时仍不得跳到正式参数。

## 11.4 用户选择试切后

输出：

```text
任务流程
试切方案
参数来源
测量计划
验收标准
停止条件
下一步试切结果模板
```

## 11.5 用户提交试切结果后

输出：

```text
试切结果解析
质量判定
是否通过
是否需要审核
是否进入 BO
下一步需要什么
```

---

# 12. 正确演示示例

用户完成需求确认后，系统应类似输出：

```text
任务流程
1. 任务需求确认               已完成
2. 设备边界读取               已完成
3. 资料库与历史案例检索       已完成
4. 证据可信度评估             已完成
5. 试切方式选择               等待用户
6. 试切方案生成               未开始
7. 试切结果评价               未开始
8. BO 参数优化                未开始
9. 正式加工方案               未开始

当前进度：4/9（44%）

已调用 Skill
✓ task_intake
✓ equipment_context_loading
✓ rag_evidence_retrieval
✓ process_risk_assessment
✓ trial_need_assessment
✓ trial_strategy_selection

已调用 Tool
✓ equipment_memory_tool：读取 eqrev_xxx
✓ rag_query_tool：8 chunks / 4 papers
✓ historical_case_tool：未找到同条件已验证案例
✓ process_rule_tool：未找到可直接使用的 validated_rule

资料来源可信度
- 已审核资料源：1
- 待审核资料源：3
- 当前 Evidence Status：partial
- 可用于：分层风险识别、测量项设计、试切策略
- 不可用于：直接推荐功率、频率、扫描速度和扫描次数

试切建议
推荐：简化试切

原因：
- 5 mm T300 属于厚板复杂切割
- 当前没有同条件批准工艺先验
- 完整试切成本高且失败原因难定位
- 应先标定去除量和分层风险

请选择：
[1] 简化试切
[2] 完整试切
[3] 暂不试切，只查看规划框架

下一步
请回复 1、2 或 3。
```

---

# 13. API 与响应 Schema

扩展 `ChatResponse`：

```python
class ChatResponse(BaseModel):
    message: str
    workflow_overview: list[WorkflowStep]
    current_stage: str
    workflow_progress: WorkflowProgress
    skill_trace: list[SkillTrace]
    tool_trace: list[ToolTrace]
    equipment_snapshot: dict | None
    evidence_credibility: EvidenceCredibilitySummary | None
    trial_decision: TrialDecision | None
    next_action: NextAction | None
    warnings: list[str]
```

## 13.1 `WorkflowStep`

```python
class WorkflowStep(BaseModel):
    step_id: str
    title: str
    status: str
    required: bool
    started_at: str | None
    completed_at: str | None
```

## 13.2 `SkillTrace`

```python
class SkillTrace(BaseModel):
    skill_name: str
    version: str
    status: str
    input_summary: dict
    output_summary: dict
    duration_ms: int | None
```

## 13.3 `NextAction`

```python
class NextAction(BaseModel):
    action_type: str
    title: str
    required: bool
    fields: list[dict]
    options: list[dict]
    example: dict | None
```

---

# 14. Router 强制规则

对于加工任务：

```python
if intent == "process_task":
    route.requires_parameter_recommendation_planning = True
    route.requires_data_support_assessment = True
    route.requires_trial_assessment = True
    route.requires_workflow_progress = True
    route.requires_reasoning_trace = True
    route.requires_skill_trace = True
    route.requires_tool_trace = True
```

参数推荐流程固定为：

```text
先调用 BO 参数推荐工具；
BO 数据不足或部分不足时再调用 RAG 参数推荐工具；
两者均不足时，根据配置和用户授权决定是否调用 LLM 兜底工具。
```

若无已验证工艺记录或与当前条件匹配的正式参数：

```python
route.require_trial_selection = True
```

若三个参数工具均不能给出合法候选：

```python
route.block_parameter_recommendation = True
```

---

# 15. System Prompt 强制约束

加入：

```text
聊天 LLM 不得在自由文本中直接创造工艺参数。
具体参数只能来自：
bo_parameter_recommendation_tool、
rag_parameter_recommendation_tool、
或经 ParameterRecommendationPolicy 授权的 llm_fallback_parameter_tool。
设备允许范围不是推荐范围。
没有 Evidence Pack 时不得声称有文献依据。
没有执行 TrialStrategySelectionSkill 时不得给出试切方式。
未取得用户试切模式选择时不得生成试切参数矩阵。
未经试切或历史验证的参数不得进入正式加工。
每次回答必须说明当前流程、当前阶段、已完成步骤和下一步输入。
所有 Skill、Tool、公开推理摘要和决策依据必须来自 Runtime trace，禁止自行声称调用。
不得输出隐藏 chain-of-thought、raw_thoughts、内部草稿或完整 system prompt。
```

---

# 16. P0 整改项

近期演示前必须完成：

```text
1. 强制加工 Workflow 状态机；
2. 每次回答展示流程和当前进度；
3. 信息确认后必须进入试切方式选择；
4. 默认 Research 模式展示全部 Skill 和 Tool；
5. 强制执行 BO→RAG→受控 LLM 兜底参数推荐链；
6. 显示工艺数据库覆盖、文献来源、审核状态和可信度；
7. 三个参数工具均不足时阻止具体参数；
8. 每次回答生成 NextAction；
9. 简化试切结果模板；
10. 修复“内部经验估算参数”绕过问题；
11. 修复虚假或未调用 RAG 的声明；
12. 添加端到端 T300 5 mm CFRP 演示测试。
```

---

# 17. 测试要求

## 17.1 加工流程测试

用户输入：

```text
我想切割 5 mm 厚的 T300 碳纤维板。
```

预期：

```text
进入 REQUIREMENTS_PENDING
不输出具体参数
显示任务流程
显示当前进度
显示缺失字段
```

用户补充：

```text
无分层，压缩空气，允许层切，无效率要求。
```

预期：

```text
调用 RAG
调用 trial_need_assessment
调用 trial_strategy_selection
进入 TRIAL_MODE_PENDING
显示三种选择
不输出正式参数
```

## 17.2 Skill/Tool Trace 测试

Research 模式必须返回：

```text
全部实际调用 Skill
全部实际调用 Tool
顺序正确
持续时间
输入输出摘要
```

不得出现未实际调用的 Skill/Tool。

## 17.3 Evidence 测试

必须返回：

```text
paper_id
title
page
chunk_id
review_status
evidence_level
credibility
applicability
```

RAG 失败时：

```text
禁止参数推荐
```

## 17.4 NextAction 测试

每个非终态响应必须有：

```text
next_action
```

`TRIAL_RESULT_PENDING` 时必须列出具体试切结果字段。

## 17.5 参数来源测试

任何输出参数必须有：

```text
source_type
recommendation_mode
authority_level
allowed_for_simple_trial
allowed_for_full_trial
allowed_for_formal_process
allowed_for_bo_prior
```

`free_form_llm_estimate` 必须被拦截。

`llm_fallback_hypothesis` 只有在 BO 和 RAG 均不足、Policy 授权且用户允许时，
才能进入简化试切。

## 17.6 进度测试

```text
进度基于真实 Workflow Step
不会在试切选择前显示 80%
进入 TRIAL_MODE_PENDING 时进度通常约 40%–60%
```

## 17.7 回归测试

增加：

```text
test_cfrp_cutting_workflow.py
test_trial_mode_required.py
test_skill_tool_trace_complete.py
test_evidence_credibility_output.py
test_next_action_contract.py
test_parameter_source_guard.py
test_no_free_form_llm_parameter_invention.py
test_parameter_recommendation_priority.py
test_bo_parameter_tool_first.py
test_rag_parameter_tool_fallback.py
test_llm_fallback_requires_authorization.py
```

---

# 18. 验收标准

本整改只有满足以下条件才算完成：

```text
1. 加工任务不能绕过试切策略；
2. 用户必须看到简化、完整和仅查看框架选项；
3. Research 模式展示全部实际 Skill 和 Tool；
4. 每条资料源有来源、页码、审核状态和可信度；
5. 参数推荐必须优先调用 BO，数据不足时才调用 RAG；
6. BO 与 RAG 均不足时，只有受控 LLM 工具可生成简化试切假设；
7. 设备边界不会被当成推荐区间；
7. 每次回答有流程图和真实进度；
8. 每个非终态回答有明确 NextAction；
9. 等待试切结果时列出完整字段模板；
10. 未收到试切结果不能进入 BO；
11. 未审批文献参数不能进入 BO；
12. 不再出现“内部经验估算”的确定性参数；
13. T300 5 mm CFRP 演示完整通过；
14. 所有新增测试通过；
15. README 和演示脚本同步更新。
```

---

# 19. Codex 实施顺序

```text
Phase 1：增加 Workflow 状态机和进度模型
Phase 2：强制加工任务 Workflow
Phase 3：接入 SkillTrace 和 ToolTrace
Phase 4：强制 RAG 和 Evidence Credibility
Phase 5：参数来源 Guard
Phase 6：试切模式选择
Phase 7：NextAction 输入契约
Phase 8：PowerShell TUI 展示
Phase 9：端到端测试
Phase 10：README 和 Demo Replay
```

禁止只修改 Prompt 而不修改 Runtime、状态机、Guard 和测试。

---

# 20. Demo Replay

更新：

```text
scripts/demo_replay.ps1
```

固定演示：

```text
用户：我想切割5mm厚的碳纤维板，板号T300
用户：无分层；压缩空气；允许层切；无效率要求
系统：展示 Workflow、Skill、Tool、Evidence
系统：要求选择简化或完整试切
用户：选择简化试切
系统：给出试切计划和试切结果模板
用户：提交模拟结果
系统：评价试切
系统：必要时请求一次审核
系统：进入 BO
系统：生成正式方案和任务报告
```

该脚本必须可以在 Demo Mode 下稳定复现。


---

# 21. 正式加工之后的强制闭环流程

正式加工完成不能直接将任务标记为 `COMPLETED`。

正确流程必须继续执行：

```text
正式加工方案确认
→ 加工前检查
→ 正式加工执行
→ 过程监控
→ 中间检查点
→ 加工完成确认
→ 最终质量检测
→ 质量判定
→ 合格 / 条件合格 / 返修 / 报废 / 结果不充分
→ 结果数据校验
→ 实验记录构建
→ BO 样本准入判断
→ 知识候选生成
→ 报告生成
→ 数据与文件归档
→ 任务关闭
```

核心原则：

```text
正式加工结束 ≠ 任务完成；
设备停止 ≠ 产品合格；
检测数据存在 ≠ 数据可进入 BO；
单次成功 ≠ validated_rule；
加工结果必须经过质量判定和数据质量校验。
```

---

# 22. 扩展状态机

在原状态机基础上新增：

```text
FORMAL_PROCESS_PLAN_READY
FORMAL_PROCESS_RELEASE_PENDING
FORMAL_PROCESS_PREFLIGHT
FORMAL_PROCESS_EXECUTION_READY
FORMAL_PROCESS_RUNNING
FORMAL_PROCESS_PAUSED
FORMAL_PROCESS_CHECKPOINT
FORMAL_PROCESS_ABORTED
FORMAL_PROCESS_FINISHED

FINAL_INSPECTION_PENDING
FINAL_INSPECTION_RUNNING
FINAL_INSPECTION_COMPLETE
QUALITY_DECISION_PENDING
QUALITY_ACCEPTED
QUALITY_CONDITIONAL
QUALITY_REWORK_REQUIRED
QUALITY_REJECTED
QUALITY_INCONCLUSIVE

REWORK_PLANNING
REWORK_APPROVAL_PENDING
REWORK_EXECUTION_READY
REWORK_RUNNING
REWORK_INSPECTION_PENDING

RESULT_VALIDATION
EXPERIMENT_RECORD_BUILDING
BO_SAMPLE_ELIGIBILITY
KNOWLEDGE_EXTRACTION
REPORT_GENERATION
ARCHIVING
CLOSED
```

## 22.1 正式加工合法迁移

```text
FORMAL_PROCESS_READY
→ FORMAL_PROCESS_PLAN_READY
→ FORMAL_PROCESS_RELEASE_PENDING
→ FORMAL_PROCESS_PREFLIGHT
→ FORMAL_PROCESS_EXECUTION_READY
→ FORMAL_PROCESS_RUNNING
```

加工过程中：

```text
FORMAL_PROCESS_RUNNING
→ FORMAL_PROCESS_CHECKPOINT
→ FORMAL_PROCESS_RUNNING
```

异常时：

```text
FORMAL_PROCESS_RUNNING
→ FORMAL_PROCESS_PAUSED
→ FORMAL_PROCESS_RUNNING
或 FORMAL_PROCESS_ABORTED
```

完成时：

```text
FORMAL_PROCESS_RUNNING
→ FORMAL_PROCESS_FINISHED
→ FINAL_INSPECTION_PENDING
→ FINAL_INSPECTION_RUNNING
→ FINAL_INSPECTION_COMPLETE
→ QUALITY_DECISION_PENDING
```

质量分支：

```text
QUALITY_DECISION_PENDING
├─ QUALITY_ACCEPTED
├─ QUALITY_CONDITIONAL
├─ QUALITY_REWORK_REQUIRED
├─ QUALITY_REJECTED
└─ QUALITY_INCONCLUSIVE
```

合格分支：

```text
QUALITY_ACCEPTED
→ RESULT_VALIDATION
→ EXPERIMENT_RECORD_BUILDING
→ BO_SAMPLE_ELIGIBILITY
→ KNOWLEDGE_EXTRACTION
→ REPORT_GENERATION
→ ARCHIVING
→ CLOSED
```

返修分支：

```text
QUALITY_REWORK_REQUIRED
→ REWORK_PLANNING
→ REWORK_APPROVAL_PENDING
→ REWORK_EXECUTION_READY
→ REWORK_RUNNING
→ REWORK_INSPECTION_PENDING
→ FINAL_INSPECTION_RUNNING
```

结果不充分：

```text
QUALITY_INCONCLUSIVE
→ FINAL_INSPECTION_PENDING
```

报废或拒收：

```text
QUALITY_REJECTED
→ REPORT_GENERATION
→ ARCHIVING
→ CLOSED
```

## 22.2 禁止迁移

```text
FORMAL_PROCESS_FINISHED
→ CLOSED

FORMAL_PROCESS_FINISHED
→ BO_SAMPLE_ELIGIBILITY

FINAL_INSPECTION_COMPLETE
→ KNOWLEDGE_EXTRACTION

QUALITY_REWORK_REQUIRED
→ QUALITY_ACCEPTED

QUALITY_ACCEPTED
→ validated_rule

QUALITY_REJECTED
→ bo_training_sample
```

---

# 23. 正式加工释放门

正式加工开始前必须经过：

```text
FormalProcessReleaseGate
```

调用：

```python
release = FormalProcessReleaseGate.evaluate(
    task_spec=task_spec,
    equipment_snapshot=equipment_snapshot,
    trial_result=trial_result,
    approved_parameters=approved_parameters,
    toolpath_plan=toolpath_plan,
    measurement_plan=measurement_plan,
    stop_conditions=stop_conditions,
)
```

返回：

```json
{
  "status": "released|approval_required|blocked",
  "blocking_reasons": [],
  "warnings": [],
  "release_conditions": [],
  "required_confirmations": []
}
```

## 23.1 放行条件

至少检查：

```text
试切结果已通过或条件通过；
正式参数有合法来源；
设备 revision 与试切一致；
参数在设备硬边界内；
正式路径已生成并校验；
工件材料和批次已确认；
辅助气体和夹具条件已确认；
检测计划已定义；
中间检查点已定义；
停止条件已定义；
用户已确认开始正式加工。
```

任何一项不满足：

```text
不得进入 FORMAL_PROCESS_RUNNING。
```

---

# 24. 正式加工前检查

新增 Skill：

```text
formal_process_preflight
```

必须检查：

```text
工件材料、牌号和批次
工件尺寸和厚度
设备 profile 和 revision
激光器状态
光路和聚焦状态
夹具和定位
焦点零位
辅助气体类型和压力
路径文件版本
参数文件版本
预计加工时间
预计扫描次数或层数
检测设备可用性
停止条件
文件保存路径
操作人确认
```

输出：

```json
{
  "preflight_id": "",
  "status": "pass|warning|fail",
  "checks": [],
  "warnings": [],
  "blocking_items": [],
  "equipment_revision": "",
  "toolpath_revision": "",
  "parameter_revision": ""
}
```

用户界面显示：

```text
正式加工前检查
✓ 设备配置一致
✓ 参数在硬边界内
✓ 试切结果已通过
✓ 路径文件已校验
✓ 压缩空气已确认
! 尚未确认截面检测设备是否可用

下一步：
请确认检测设备或选择替代检测方案。
```

---

# 25. 正式加工执行与过程监控

新增 Skill：

```text
formal_process_execution
in_process_monitoring
checkpoint_evaluation
anomaly_triage
```

## 25.1 过程监控信息

系统应尽可能记录：

```text
实际功率
实际频率
实际脉宽
实际扫描速度
实际层数
实际扫描次数
焦点位置
辅助气体压力
设备报警
温度或热信号
等离子体/光学监测信号
加工进度
暂停和恢复
路径偏差
加工时间
```

没有在线数据时，也必须记录：

```text
monitoring_availability = unavailable
```

不得假装存在原位监测数据。

## 25.2 中间检查点

对复杂任务必须支持检查点。

示例：

```text
完成 10% 深度
完成 25% 深度
完成 50% 深度
完成 75% 深度
接近穿透
完成全部路径
```

每个检查点输出：

```json
{
  "checkpoint_id": "",
  "planned_progress": 0.5,
  "actual_progress": 0.47,
  "measurements": {},
  "defects": [],
  "monitoring_summary": {},
  "decision": "continue|adjust|pause|abort",
  "reason": ""
}
```

## 25.3 正式加工停止条件

至少包括：

```text
分层超过阈值
裂纹超过阈值
树脂严重烧损
边缘崩损超限
去除深度明显偏离
路径偏移
辅助气体中断
设备报警
温度或监测信号异常
加工时间超出预期
连续多个检查点无有效去除
```

系统只提出停止建议时，应明确：

```text
这是系统停止建议，不代表已真实控制设备停机。
```

除非系统已接入真实设备控制接口。

---

# 26. 正式加工过程的 Skill 与 Tool 展示

Research 模式必须显示：

```text
Skill
✓ formal_process_preflight
✓ formal_process_execution
✓ in_process_monitoring
✓ checkpoint_evaluation
✓ anomaly_triage

Tool
✓ equipment_status_tool
✓ toolpath_reader_tool
✓ parameter_file_tool
✓ monitoring_log_tool
✓ checkpoint_record_tool
✓ execution_file_registry_tool
```

如果无真实设备连接：

```text
equipment_status_tool = simulation_or_manual_input
```

必须在轨迹中显式标注。

新增事件：

```text
formal_process_release_requested
formal_process_released
formal_process_blocked
preflight_started
preflight_completed
formal_process_started
formal_process_progress
formal_process_paused
formal_process_resumed
checkpoint_reached
checkpoint_evaluated
stop_condition_triggered
formal_process_aborted
formal_process_finished
```

---

# 27. 加工完成后的下一步输入契约

正式加工结束后，系统必须要求用户提交或导入以下数据。

## 27.1 必填执行数据

```text
1. 实际开始时间
2. 实际结束时间
3. 实际设备 revision
4. 实际参数文件
5. 实际路径文件
6. 实际功率 W
7. 实际频率 kHz
8. 实际脉宽 fs
9. 实际扫描速度 mm/s
10. 实际扫描次数或层数
11. 辅助气体类型
12. 实际气体压力 MPa
13. 是否发生暂停
14. 是否发生报警
15. 是否触发停止条件
16. 实际加工结果：完成/中止/失败
```

## 27.2 必填质量数据

根据当前 T300 CFRP 切割场景，至少要求：

```text
1. 是否完全切透
2. 切缝入口宽度
3. 切缝出口宽度
4. 切缝锥度
5. 是否分层
6. 最大分层宽度
7. 分层位置：入口/出口/侧壁/局部
8. 是否崩边
9. 最大崩边尺寸
10. 是否有树脂烧损
11. 是否有明显石墨化
12. 是否有纤维拔出
13. 切缝侧壁质量
14. 是否有未切断纤维
15. 检测结论
```

## 27.3 推荐附件

```text
正面照片
背面照片
切缝侧壁照片
截面显微照片
SEM
轮廓测量文件
原位监测日志
设备日志
参数文件
路径文件
测量 CSV
异常照片
```

## 27.4 可复制模板

```text
正式加工结果

任务 ID：
加工状态：完成 / 中止 / 失败
设备 revision：
开始时间：
结束时间：

实际功率：
实际频率：
实际脉宽：
实际扫描速度：
实际扫描次数/层数：
辅助气体：
气体压力：
暂停次数：
设备报警：
停止条件触发：

是否切透：
入口切缝宽度：
出口切缝宽度：
锥度：
是否分层：
最大分层宽度：
分层位置：
是否崩边：
最大崩边尺寸：
是否树脂烧损：
是否石墨化：
是否纤维拔出：
是否存在未切断纤维：
侧壁质量：
检测结论：

参数文件：
路径文件：
设备日志：
测量文件：
照片：
备注：
```

---

# 28. 最终质量检测

新增 Skill：

```text
final_inspection_planning
inspection_result_ingestion
final_quality_evaluation
```

新增 Tool：

```text
metrology_file_reader
image_attachment_registry
inspection_csv_parser
defect_record_tool
```

## 28.1 检测计划必须来源明确

检测项目来源：

```text
用户质量要求
行业或项目验收标准
已审核 validated_rule
已批准 measurement template
试切阶段确定的验收标准
```

LLM 不得自行生成强制验收阈值。

## 28.2 质量判定结果

```json
{
  "quality_decision": "accepted|conditional|rework_required|rejected|inconclusive",
  "passed_metrics": [],
  "failed_metrics": [],
  "missing_metrics": [],
  "defects": [],
  "evidence_files": [],
  "decision_basis": [],
  "warnings": []
}
```

### Accepted

```text
所有必需质量指标满足要求。
```

### Conditional

```text
主要功能满足，但存在可接受偏差；
必须明确条件和使用限制。
```

### Rework Required

```text
允许通过返修或二次加工修正。
```

### Rejected

```text
严重缺陷或无法修复。
```

### Inconclusive

```text
检测数据不足或检测方法不充分。
```

---

# 29. 返修与复加工流程

正式加工后如果不合格，不能直接回到最初任务重新生成参数。

必须进入：

```text
rework_decision
```

新增 Skill：

```text
rework_feasibility_assessment
rework_plan_generation
rework_risk_assessment
rework_result_evaluation
```

## 29.1 返修判断

至少检查：

```text
缺陷是否可修复
剩余材料余量
再次加工是否扩大分层
是否影响尺寸
是否超出设备能力
是否有已验证返修策略
返修后如何检测
返修是否需要再次审核
```

输出：

```text
rework_allowed
rework_not_recommended
scrap_recommended
additional_measurement_required
```

## 29.2 返修也需要试切判断

如果返修参数或路径与原正式加工明显不同：

```text
重新进入 trial_need_assessment。
```

不得默认直接执行返修。

---

# 30. 结果数据校验

加工和检测完成后，新增：

```text
result_validation
```

检查：

```text
任务 ID 一致
设备 revision 一致
参数文件可追溯
路径文件可追溯
时间信息完整
材料批次完整
质量字段完整
单位合法
附件存在
检测结果与判定一致
是否有人工修改
是否存在异常日志
```

输出：

```json
{
  "validation_status": "valid|partial|invalid",
  "missing_fields": [],
  "conflicts": [],
  "warnings": [],
  "eligible_for_experiment_record": true
}
```

无效数据：

```text
不得进入 BO 数据集；
不得晋升为验证规则；
可以保留为失败案例或审计记录。
```

---

# 31. 实验记录构建

新增 Skill：

```text
experiment_record_builder
```

构建统一记录：

```json
{
  "experiment_id": "",
  "task_id": "",
  "trial_or_formal": "formal",
  "material": {},
  "equipment": {},
  "process_parameters": {},
  "toolpath": {},
  "environment": {},
  "monitoring": {},
  "quality_metrics": {},
  "defects": [],
  "files": [],
  "result_status": "",
  "data_quality": "",
  "created_at": ""
}
```

正式加工记录必须和试切记录分开，但可以建立关联：

```text
derived_from_trial_plan_id
derived_from_trial_result_id
```

---

# 32. BO 样本准入

新增：

```text
bo_sample_eligibility
```

正式加工结果不能自动进入 BO。

## 32.1 准入条件

```text
参数完整
质量指标完整
单位统一
设备 revision 明确
材料和批次明确
无关键字段冲突
结果可追溯
数据质量通过
不存在未处理异常
```

## 32.2 输出

```json
{
  "eligible": true,
  "reason": "",
  "sample_type": "successful|failed|censored",
  "quality_score": 0.0,
  "excluded_fields": [],
  "warnings": []
}
```

失败结果也可以作为：

```text
failed sample
censored sample
```

但必须由 BO 数据策略明确支持，不能默认混入普通成功样本。

## 32.3 人工确认

正式加工数据首次进入 BO 数据集时，建议提供：

```text
[批准加入 BO 数据集]
[仅归档，不加入 BO]
```

如果已有明确自动准入规则，可由配置决定。

---

# 33. 知识沉淀

新增 Skill：

```text
knowledge_candidate_generation
knowledge_conflict_check
knowledge_promotion_suggestion
```

从正式加工结果可以生成：

```text
历史案例
失败案例
设备能力案例
候选工艺趋势
候选质量规则
候选返修经验
```

但默认状态：

```text
knowledge_candidate
pending_review
```

单次正式加工不得自动生成：

```text
validated_rule
approved_process_prior
```

如果相同条件多次验证：

```text
系统可以建议晋升；
仍需审核。
```

---

# 34. 任务报告与归档

最终报告必须包含两个阶段：

```text
A. 试切与参数形成过程
B. 正式加工与质量闭环
```

## 34.1 报告内容

```text
任务目标
材料与批次
设备及 revision
任务流程
Skill 和 Tool 轨迹摘要
文献来源和可信度
试切模式与结果
知识审核记录
BO 模式和推荐依据
正式加工参数
路径版本
正式加工过程
检查点
异常和处置
最终检测结果
质量判定
返修记录
BO 样本准入结果
知识候选
文件清单
总耗时
未完成事项
```

## 34.2 归档内容

```text
task_report.md
task_report.json
workflow_trace.jsonl
equipment_snapshot.json
evidence_pack.json
trial_plan.json
trial_result.json
approval_record.json
formal_process_plan.json
formal_process_execution.json
inspection_result.json
quality_decision.json
experiment_record.json
bo_eligibility.json
knowledge_candidates.jsonl
参数文件
路径文件
设备日志
监测日志
检测文件
照片
```

## 34.3 关闭条件

只有以下条件满足时才能：

```text
CLOSED
```

```text
正式加工状态明确
最终质量状态明确
关键文件已归档
结果数据校验完成
BO 准入结论已生成
知识候选已生成或明确跳过
任务报告已生成
没有未解决阻塞项
```

---

# 35. 每次正式加工阶段回答的固定结构

正式加工阶段每次回答仍必须包含：

```text
1. 完整任务流程与当前进度
2. 当前加工状态
3. 已执行 Skill 和 Tool
4. 设备、参数和路径 revision
5. 当前监控和检查点
6. 异常、警告和停止条件
7. 当前阶段结论
8. 下一步需要提供的内容
9. 尚未完成的后续阶段
```

## 35.1 正式加工开始前

下一步：

```text
确认正式加工释放
确认检测设备
确认参数文件和路径文件
```

## 35.2 正式加工进行中

下一步：

```text
提交当前检查点数据
确认继续/调整/暂停/中止
```

## 35.3 正式加工完成后

下一步：

```text
提交正式加工结果和检测数据
```

## 35.4 质量评价后

下一步：

```text
接受结果
执行返修
补充检测
仅归档
批准加入 BO
```

---

# 36. 完整任务流程显示

对复杂加工任务，建议显示 16 个主阶段：

```text
1. 需求确认
2. 设备边界
3. 资料检索
4. 证据评估
5. 试切策略
6. 试切方案
7. 试切执行
8. 试切评价
9. 知识审核
10. BO 优化
11. 正式方案
12. 正式加工
13. 最终检测
14. 质量判定
15. 数据与知识闭环
16. 报告归档
```

示例：

```text
任务流程
1. 需求确认                 已完成
2. 设备边界                 已完成
3. 资料检索                 已完成
4. 证据评估                 已完成
5. 试切策略                 已完成
6. 试切方案                 已完成
7. 试切执行                 已完成
8. 试切评价                 已完成
9. 知识审核                 已完成
10. BO 优化                 已完成
11. 正式方案                已完成
12. 正式加工                已完成
13. 最终检测                等待数据
14. 质量判定                未开始
15. 数据与知识闭环          未开始
16. 报告归档                未开始

当前阶段：最终检测
总体进度：12/16（75%）

下一步：
请提交入口/出口切缝宽度、分层情况、截面照片和检测结论。
```

---

# 37. 正式加工 API

新增：

```http
POST /tasks/{task_id}/formal-process/release
POST /tasks/{task_id}/formal-process/preflight
POST /tasks/{task_id}/formal-process/start
POST /formal-process/executions/{execution_id}/progress
POST /formal-process/executions/{execution_id}/checkpoints
POST /formal-process/executions/{execution_id}/pause
POST /formal-process/executions/{execution_id}/resume
POST /formal-process/executions/{execution_id}/abort
POST /formal-process/executions/{execution_id}/finish

POST /formal-process/executions/{execution_id}/inspection
POST /inspection-records/{inspection_id}/evaluate

POST /tasks/{task_id}/rework/assess
POST /tasks/{task_id}/rework/plans
POST /rework/plans/{rework_plan_id}/approve

POST /tasks/{task_id}/results/validate
POST /tasks/{task_id}/experiment-records
POST /experiment-records/{experiment_id}/bo-eligibility
POST /tasks/{task_id}/knowledge-candidates
POST /tasks/{task_id}/reports
POST /tasks/{task_id}/archive
```

---

# 38. 正式加工数据表

## 38.1 `formal_process_plan`

```sql
CREATE TABLE formal_process_plan (
    plan_id TEXT PRIMARY KEY,
    task_id TEXT,
    trial_result_id TEXT,
    parameter_revision TEXT,
    toolpath_revision TEXT,
    equipment_revision TEXT,
    parameters_json TEXT,
    toolpath_json TEXT,
    checkpoint_plan_json TEXT,
    monitoring_plan_json TEXT,
    stop_conditions_json TEXT,
    inspection_plan_json TEXT,
    status TEXT,
    created_at TEXT,
    updated_at TEXT
);
```

## 38.2 `formal_process_execution`

```sql
CREATE TABLE formal_process_execution (
    execution_id TEXT PRIMARY KEY,
    plan_id TEXT,
    actual_parameters_json TEXT,
    actual_toolpath_json TEXT,
    monitoring_summary_json TEXT,
    alarm_summary_json TEXT,
    started_at TEXT,
    finished_at TEXT,
    status TEXT
);
```

## 38.3 `process_checkpoint`

```sql
CREATE TABLE process_checkpoint (
    checkpoint_id TEXT PRIMARY KEY,
    execution_id TEXT,
    checkpoint_index INTEGER,
    planned_progress REAL,
    actual_progress REAL,
    measurements_json TEXT,
    defects_json TEXT,
    monitoring_json TEXT,
    decision TEXT,
    created_at TEXT
);
```

## 38.4 `inspection_record`

```sql
CREATE TABLE inspection_record (
    inspection_id TEXT PRIMARY KEY,
    execution_id TEXT,
    measurement_plan_json TEXT,
    measurements_json TEXT,
    defects_json TEXT,
    files_json TEXT,
    completeness_status TEXT,
    created_at TEXT
);
```

## 38.5 `quality_decision`

```sql
CREATE TABLE quality_decision (
    quality_decision_id TEXT PRIMARY KEY,
    inspection_id TEXT,
    decision TEXT,
    passed_metrics_json TEXT,
    failed_metrics_json TEXT,
    missing_metrics_json TEXT,
    basis_json TEXT,
    reviewer_comment TEXT,
    created_at TEXT
);
```

## 38.6 `experiment_record`

```sql
CREATE TABLE experiment_record (
    experiment_id TEXT PRIMARY KEY,
    task_id TEXT,
    execution_id TEXT,
    record_json TEXT,
    validation_status TEXT,
    bo_eligible INTEGER,
    created_at TEXT
);
```

---

# 39. 正式加工测试要求

新增：

```text
test_formal_process_release_gate.py
test_formal_process_preflight.py
test_formal_process_state_machine.py
test_process_checkpoint.py
test_stop_condition.py
test_final_inspection_contract.py
test_quality_decision.py
test_rework_workflow.py
test_result_validation.py
test_experiment_record_builder.py
test_bo_sample_eligibility.py
test_knowledge_candidate_from_result.py
test_task_archive.py
```

必须测试：

```text
1. 未通过试切不能正式放行；
2. 参数来源非法不能放行；
3. 设备 revision 变化不能自动放行；
4. 正式加工完成后不能直接关闭；
5. 检测数据不完整进入 QUALITY_INCONCLUSIVE；
6. 返修必须重新评估；
7. 无效结果不能进入 BO；
8. 单次成功不生成 validated_rule；
9. 归档前必须生成报告；
10. 每个非终态响应都有 NextAction。
```

---

# 40. Demo Replay 扩展

完整 Demo 必须继续到正式加工后闭环：

```text
用户：选择简化试切
系统：生成简化试切方案
用户：提交试切结果
系统：判定通过
系统：必要时审核参数
系统：运行 BO
系统：生成正式加工方案
用户：确认正式加工
系统：执行 preflight
系统：进入正式加工模拟
系统：显示检查点和监控轨迹
系统：正式加工完成
系统：要求提交最终检测数据
用户：提交检测结果和照片
系统：质量判定
系统：生成实验记录
系统：判断 BO 样本准入
系统：生成知识候选
系统：生成任务报告
系统：归档并关闭任务
```

演示不能在“生成正式加工方案”处结束。

---

# 41. 补充验收标准

在原验收标准基础上增加：

```text
16. 正式加工开始前必须经过 Release Gate；
17. 正式加工前必须完成 preflight；
18. 正式加工过程中可显示进度、检查点和停止条件；
19. 正式加工完成后必须进入最终检测；
20. 没有质量判定不能关闭任务；
21. 不合格结果可进入返修或拒收分支；
22. 正式加工数据必须经过结果校验；
23. BO 样本准入必须单独判断；
24. 单次正式加工不能自动生成 validated_rule；
25. 任务关闭前必须完成报告和归档；
26. 正式加工后的每次回复仍有流程、进度和 NextAction。
```

---

# 42. 试切与正式加工的迭代 Campaign

试切和正式加工不能设计成单次推荐、单次执行。

统一采用：

```text
Plan
→ Gate
→ Execute
→ Observe
→ Validate
→ Update
→ Decide
```

三级闭环：

```text
一级：简化试切探索迭代
二级：完整试切/正式加工受控修正迭代
三级：跨任务 BO 模型与知识更新迭代
```

## 42.1 Optimization Campaign

每个加工任务创建一个或多个 Campaign：

```text
simple_trial_campaign
full_trial_campaign
formal_process_campaign
rework_campaign
```

统一结构：

```json
{
  "campaign_id": "",
  "task_id": "",
  "campaign_type": "",
  "fidelity_level": "",
  "material_context": {},
  "equipment_revision": "",
  "active_variables": [],
  "fixed_parameters": {},
  "objectives": [],
  "hard_constraints": [],
  "soft_constraints": [],
  "search_space": {},
  "budget": {},
  "current_iteration": 0,
  "status": "running"
}
```

Campaign 必须绑定：

```text
材料和批次
设备 revision
光路配置
工艺类型
几何范围
试切模式
优化目标
参数空间
质量约束
试验预算
```

关键上下文变化时：

```text
暂停 Campaign；
重新判断历史数据和审批是否仍适用。
```

## 42.2 Fidelity Level

每条观测必须标记：

```text
simple_trial
full_trial
formal_process
rework
```

规则：

```text
simple_trial：
用于探索去除与缺陷趋势。

full_trial：
用于验证完整几何和路径累计效应。

formal_process：
高保真实际加工结果。

rework：
独立返修数据，不与初加工结果无条件混合。
```

MVP 阶段不同 fidelity 独立建模或显式加权，不得直接混为同一质量目标。

## 42.3 每轮迭代

每轮必须包含：

```text
1. 数据支持度评估
2. 参数来源选择
3. 候选生成
4. 安全与权限过滤
5. 用户确认或自动放行
6. 执行
7. 结果采集
8. 数据质量校验
9. BO 模型更新
10. 下一轮决策
```

## 42.4 候选数量

建议配置：

```yaml
optimization:
  simple_trial:
    default_batch_size: 3
    max_batch_size: 9
  full_trial:
    default_batch_size: 1
  formal_process:
    default_batch_size: 1
```

简化试切可批量探索；完整试切和正式加工一般一次执行一个方案。

## 42.5 目标与约束分离

不得只使用单一综合分数。

至少区分：

```text
优化目标：
去除深度、切缝宽度、锥度、加工时间、表面质量。

硬约束：
无分层、无严重烧损、设备不越界、必须切透等。

软约束：
尽量减小切缝、缩短时间、降低锥度。
```

BO 应优先满足可行性，再优化目标。

---

# 43. 迭代状态机

新增：

```text
CAMPAIGN_CREATED
ITERATION_PLANNING
DATA_SUPPORT_ASSESSMENT
PARAMETER_SOURCE_SELECTION
CANDIDATE_GENERATION
CANDIDATE_FILTERING
CANDIDATE_APPROVAL_PENDING
ITERATION_EXECUTION
OBSERVATION_PENDING
OBSERVATION_VALIDATION
MODEL_UPDATE
ITERATION_DECISION
CAMPAIGN_CONVERGED
CAMPAIGN_BUDGET_EXHAUSTED
CAMPAIGN_BLOCKED
CAMPAIGN_TERMINATED
```

合法迁移：

```text
CAMPAIGN_CREATED
→ ITERATION_PLANNING
→ DATA_SUPPORT_ASSESSMENT
→ PARAMETER_SOURCE_SELECTION
→ CANDIDATE_GENERATION
→ CANDIDATE_FILTERING
→ CANDIDATE_APPROVAL_PENDING 或 ITERATION_EXECUTION
→ OBSERVATION_PENDING
→ OBSERVATION_VALIDATION
→ MODEL_UPDATE
→ ITERATION_DECISION
```

决策：

```text
continue_exploration
repeat_candidate
narrow_search_space
expand_search_space
switch_to_full_trial
ready_for_formal_process
pause_for_review
return_to_simple_trial
rework
stop_success
stop_failure
```

禁止：

```text
未完成 observation validation 就更新模型；
未完成 model update 就生成下一轮 BO 推荐；
正式加工中进行大范围探索；
设备 revision 变化后继续使用旧 Campaign。
```

---

# 44. 数据支持度与 BO 模式切换

样本数量必须按当前上下文统计：

```text
同材料或兼容材料
同工艺
同设备或兼容设备
同 fidelity
相近厚度
相似几何
质量字段完整
```

返回：

```text
matched_sample_count
effective_sample_count
context_match_score
data_quality_score
model_validation_score
prediction_uncertainty
```

模式：

```text
effective sample < 10：
rule_based_cold_start

10–29：
hybrid_rule_bo

>= 30：
data_driven_bo
```

阈值可配置，但不得只看全库总数。

参数权威应随迭代逐步迁移：

```text
LLM 探索性假设
→ RAG 证据
→ RAG 辅助 BO
→ 数据驱动 BO
→ 已验证正式工艺
```

---

# 45. 观测数据准入与模型更新

每轮结果进入：

```text
received
validation_pending
valid
partial
invalid
excluded
approved_for_bo
```

校验：

```text
参数完整
单位合法
设备 revision 匹配
材料和批次明确
测量字段完整
附件可追溯
异常记录完整
重复性可接受
结果与执行记录一致
```

只有：

```text
approved_for_bo
```

才能更新正式模型。

失败结果不得删除，可标记：

```text
failed_sample
infeasible_sample
censored_sample
aborted_sample
```

用于学习失败区和安全边界。

每次模型更新必须生成：

```text
model_snapshot
```

记录：

```text
训练样本 ID
模型模式
超参数
验证指标
特征定义
目标定义
约束定义
模型文件
创建时间
```

---

# 46. 正式加工中的受控迭代

正式加工不是继续大范围 BO 探索。

允许调整范围：

```text
approved_window
∩ equipment_bounds
∩ local_trust_region
```

检查点：

```text
开始前
10% 或第一阶段
25%
50%
75%
接近穿透/最后层
完成
```

偏差分级：

```text
Level 0：
结果正常，继续。

Level 1：
轻微偏差，在批准信赖域内建议小幅修正。

Level 2：
接近质量边界，暂停并由用户确认。

Level 3：
严重分层、热损伤、连续无去除或预测失效；
中止正式加工，返回试切 Campaign。
```

禁止 LLM 在路径执行中随意修改参数。

---

# 47. 迭代停止条件

成功停止：

```text
质量目标满足
硬约束满足
重复性满足
模型不确定度低于阈值
连续多轮改进低于阈值
已获得可放行方案
```

失败停止：

```text
连续多轮无可行候选
全部安全候选失败
严重缺陷重复
设备能力不足
预算耗尽
材料不足
检测结果长期不可靠
```

人工停止：

```text
用户中止
设备维护
材料批次变化
任务目标变化
设备 revision 变化
```

停止输出必须包含：

```text
停止原因
最佳已知结果
剩余风险
未探索区域
是否建议更换设备、工艺或材料
```

---

# 48. 迭代数据模型

## 48.1 `optimization_campaign`

```sql
CREATE TABLE optimization_campaign (
    campaign_id TEXT PRIMARY KEY,
    task_id TEXT,
    campaign_type TEXT,
    fidelity_level TEXT,
    material_context_json TEXT,
    equipment_revision TEXT,
    objectives_json TEXT,
    constraints_json TEXT,
    search_space_json TEXT,
    budget_json TEXT,
    status TEXT,
    created_at TEXT,
    updated_at TEXT
);
```

## 48.2 `optimization_iteration`

```sql
CREATE TABLE optimization_iteration (
    iteration_id TEXT PRIMARY KEY,
    campaign_id TEXT,
    iteration_index INTEGER,
    model_mode TEXT,
    model_snapshot_id TEXT,
    data_support_json TEXT,
    proposed_candidates_json TEXT,
    selected_candidates_json TEXT,
    decision TEXT,
    decision_reason TEXT,
    started_at TEXT,
    completed_at TEXT,
    status TEXT
);
```

## 48.3 `optimization_candidate`

```sql
CREATE TABLE optimization_candidate (
    candidate_id TEXT PRIMARY KEY,
    iteration_id TEXT,
    parameters_json TEXT,
    parameter_sources_json TEXT,
    predicted_objectives_json TEXT,
    uncertainty_json TEXT,
    feasibility_probability REAL,
    risk_level TEXT,
    status TEXT
);
```

## 48.4 `optimization_observation`

```sql
CREATE TABLE optimization_observation (
    observation_id TEXT PRIMARY KEY,
    candidate_id TEXT,
    execution_id TEXT,
    measurements_json TEXT,
    quality_metrics_json TEXT,
    constraint_results_json TEXT,
    data_quality_status TEXT,
    bo_eligible INTEGER,
    created_at TEXT
);
```

## 48.5 `model_snapshot`

```sql
CREATE TABLE model_snapshot (
    model_snapshot_id TEXT PRIMARY KEY,
    campaign_id TEXT,
    iteration_index INTEGER,
    model_type TEXT,
    training_sample_ids_json TEXT,
    hyperparameters_json TEXT,
    metrics_json TEXT,
    artifact_path TEXT,
    created_at TEXT
);
```

---

# 49. 新增 Skill 与 Tool

## 49.1 Skill

```text
parameter_recommendation_planning
data_support_assessment
parameter_source_selection
parameter_recommendation_explanation

optimization_campaign_initialization
iteration_planning
candidate_generation
candidate_safety_filter
trial_batch_planning
observation_ingestion
observation_validation
surrogate_model_update
acquisition_optimization
iteration_decision
search_space_refinement
fidelity_transition
formal_checkpoint_evaluation
formal_local_adjustment
campaign_termination
```

## 49.2 Tool

```text
bo_parameter_recommendation_tool
rag_parameter_recommendation_tool
llm_fallback_parameter_tool
parameter_constraint_validation_tool
parameter_provenance_registry_tool

experiment_store_tool
measurement_parser_tool
quality_metric_tool
model_snapshot_tool
candidate_registry_tool
equipment_bounds_tool
process_prior_tool
```

参数来源选择应由确定性 Policy 完成，不应完全依赖 LLM Skill。

---

# 50. 调试阶段的最大化公开执行过程

当前调试目标是尽可能让开发人员看清：

```text
系统理解了什么
当前假设是什么
考虑了哪些方案
采用了哪些证据
拒绝了哪些候选
为什么选择某个 Skill
为什么调用某个 Tool
参数从哪里来
为何进入下一阶段
为何被阻塞
```

但公开内容必须是：

```text
公开推理摘要
决策依据
候选比较
证据引用
策略判断
```

不得输出模型隐藏 chain-of-thought。

## 50.1 新增 ReasoningTrace

```python
class ReasoningTrace(BaseModel):
    trace_id: str
    sequence: int
    stage: str
    event_type: str
    title: str
    summary: str
    assumptions: list[str]
    evidence_refs: list[str]
    alternatives_considered: list[dict]
    selected_alternative: str | None
    rejection_reasons: list[dict]
    uncertainty: dict
    next_step: str | None
    visibility: str
    created_at: str
```

`event_type`：

```text
task_interpretation
assumption_declared
evidence_considered
hypothesis_generated
alternative_considered
alternative_rejected
policy_evaluated
decision_rationale
uncertainty_assessed
next_step_planned
```

## 50.2 Debug 模式默认展示

```text
任务字段解析结果
缺失字段与默认假设
Workflow 选择原因
全部 Skill 调用
全部 Tool Call
Tool 输入摘要
Tool 输出摘要
数据库命中数量
RAG query 和 filters
候选参数及来源
被过滤候选及原因
BO 模式和样本支持
RAG 证据可信度
LLM fallback 是否获得授权
状态迁移原因
每个步骤耗时
缓存命中
重试和 fallback
```

## 50.3 Tool Call 展示要求

调试模式默认展示完整但脱敏的：

```text
tool_name
call_id
start_time
end_time
duration_ms
input
output
status
error
retry_count
cache_status
evidence_refs
```

大对象必须：

```text
提供摘要
提供记录 ID 或文件路径
允许通过命令展开
```

不得把整个 PDF、向量或大型二进制直接刷屏。

## 50.4 Skill 展示要求

```text
skill_name
skill_version
选择原因
前置条件
输入
允许工具
实际调用工具
输出
副作用
耗时
状态
```

## 50.5 公开推理摘要示例

```text
[公开推理摘要]
- 当前任务属于厚板 CFRP 切割，风险主要为分层和热累积。
- BO 数据覆盖评估仅找到 3 条相似样本，支持度不足。
- 因此转入 RAG 参数推荐。
- RAG 找到 4 篇相关论文，但厚度匹配不足，参数只允许用于简化试切。
- 当前不调用 LLM 兜底，因为 RAG 已能提供部分候选。
```

这是允许公开的过程摘要。

禁止输出：

```text
逐 token 内部推理
隐藏草稿
私有 chain-of-thought
完整内部提示词
```

## 50.6 TUI 命令

保留：

```text
/mode normal
/mode research
/mode debug
```

新增：

```text
/trace summary
/trace full
/trace off
/tools
/skills
/reasoning
/waterfall
/campaign
/model
```

调试阶段默认：

```text
/mode debug
/trace full
```

正式演示或生产可切回 Research/Normal。

## 50.7 脱敏策略

必须隐藏：

```text
API Key
Authorization Header
Cookie
数据库密码
DPAPI 密文
完整 system prompt
用户敏感信息
```

文件路径可配置：

```text
full
relative
basename_only
```

## 50.8 事件持久化

所有公开执行事件写入：

```text
agent_trace_event
```

新增字段：

```text
reasoning_trace_json
skill_trace_json
tool_trace_json
parameter_provenance_json
campaign_id
iteration_id
model_snapshot_id
```

---

# 51. 每次回答的迭代进度显示

除总任务进度外，必须显示当前 Campaign：

```text
任务总流程：8/16
当前阶段：简化试切

优化 Campaign：campaign_001
当前轮次：2
当前模式：rule_based_cold_start
本轮候选：3
已完成：2
待执行：1
有效累计样本：7
当前最佳：1 个无分层候选
下一决策：完成本轮后判断是否进入完整试切
```

参数推荐链：

```text
1. BO 数据支持评估
   Tool: bo_parameter_recommendation_tool
   结果: insufficient
   有效样本: 3

2. RAG 参数检索
   Tool: rag_parameter_recommendation_tool
   结果: partially_supported
   来源: 4 篇论文 / 8 chunks

3. 知识使用门
   结果: 仅允许简化试切

4. LLM 兜底
   状态: 未调用
   原因: RAG 已提供部分支持
```

---

# 52. 每轮 NextAction

每轮结束必须输出：

```text
本轮结果
数据准入状态
模型是否更新
当前最佳候选
仍未满足的约束
下一轮决策
用户需要提供的内容
```

示例：

```text
本轮完成 3 个简化试切点：
- 1 个满足无分层
- 1 个轻微分层
- 1 个检测数据不完整

模型更新：
- 2 条进入 BO
- 1 条等待补充最大分层宽度

下一步：
1. 补充候选 C 的分层宽度；
2. 确认是否执行第 3 轮；
3. 确认剩余试样数量；
4. 确认本轮最多允许 3 个试验点。
```

---

# 53. 新增测试

```text
test_parameter_recommendation_policy.py
test_bo_first_priority.py
test_bo_partial_triggers_rag_prior.py
test_rag_fallback_when_bo_insufficient.py
test_llm_fallback_only_after_bo_and_rag_fail.py
test_llm_fallback_simple_trial_only.py
test_parameter_provenance_registry.py

test_optimization_campaign.py
test_iteration_state_machine.py
test_fidelity_separation.py
test_observation_validation_before_model_update.py
test_model_snapshot_created.py
test_iteration_stop_conditions.py
test_formal_local_trust_region.py
test_formal_process_return_to_trial.py

test_reasoning_trace_public_summary.py
test_all_skill_calls_visible_in_debug.py
test_all_tool_calls_visible_in_debug.py
test_trace_redaction.py
test_no_hidden_chain_of_thought_field.py
test_campaign_progress_output.py
```

---

# 54. V3 补充验收标准

```text
27. 参数推荐必须优先调用 BO；
28. BO 部分支持时允许 RAG 提供先验后重新运行 BO；
29. BO 不足时才进入 RAG 参数推荐；
30. BO 和 RAG 均不足时才允许受控 LLM 兜底；
31. LLM 兜底只能用于简化试切；
32. 所有参数具有 provenance 和用途权限；
33. 试切和正式加工均以 Campaign 形式迭代；
34. 不同 fidelity 数据不无条件混合；
35. 数据校验完成前不得更新模型；
36. 每轮生成模型快照；
37. 正式加工只允许局部信赖域修正；
38. 每轮有预算、停止条件和 NextAction；
39. Debug 模式展示所有实际 Skill 与 Tool Call；
40. Debug 模式展示公开推理摘要、候选比较和决策依据；
41. 不输出隐藏 chain-of-thought；
42. 参数工具链、Campaign 和 Runtime trace 均有端到端测试。
```

---

# 55. V3 实施顺序

```text
Phase 1：修复参数自由生成和旧参数 Guard
Phase 2：实现统一参数推荐 Schema
Phase 3：实现 ParameterRecommendationPolicy
Phase 4：实现 BO 参数推荐工具
Phase 5：实现 RAG 参数推荐工具
Phase 6：实现受控 LLM 兜底参数工具
Phase 7：实现参数 provenance 与权限校验
Phase 8：实现 Optimization Campaign 和迭代状态机
Phase 9：实现 observation validation 和 model snapshot
Phase 10：实现正式加工局部信赖域迭代
Phase 11：实现 ReasoningTrace
Phase 12：Debug 模式展示全部 Skill/Tool/公开推理摘要
Phase 13：补充 TUI 命令和脱敏
Phase 14：端到端测试与 Demo Replay
```

禁止：

```text
只修改 Prompt；
只在最终回答中添加文字说明；
让聊天 LLM 绕过参数工具；
伪造 Skill 或 Tool 轨迹；
把隐藏 chain-of-thought 写入数据库或界面。
```
