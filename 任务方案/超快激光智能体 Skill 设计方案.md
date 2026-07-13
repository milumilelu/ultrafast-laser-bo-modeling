# 超快激光智能体 Skill 设计方案

## 1. 设计目标

本方案用于将超快激光智能体中的稳定执行流程固化为可复用 skill，降低大模型上下文压力，避免长期对话中的流程遗忘、约束漂移和参数幻觉。

系统不应依赖一次性长 prompt 来维持行为，而应将关键流程拆分为多个小型 skill。每个 skill 负责一个稳定任务，例如任务解析、CRL 加工规划、RAG 检索、BO 推荐、加工文件自学习、经验库更新和报告生成。

最终目标是形成：

```text
用户输入 / 工艺文件 / 日志 / 检测结果
→ Skill 路由
→ 结构化任务建模
→ RAG / 知识库 / 实验库 / BO 调用
→ 证据化输出
→ 经验沉淀
```

## 2. 核心原则

### 2.1 Skill 是流程，不是知识库

Skill 只保存稳定操作规程、输入输出约束、禁止事项和质量检查。
动态知识、实验数据、文献内容、加工经验不应写入 skill，而应进入专业知识记忆库、RAG、结构化数据库或 BO 数据集。

分工如下：

```text
Skill：规定怎么做
Memory：保存专业知识状态
RAG：检索文献和非结构化经验
数据库：保存结构化实验事实
规则库：保存已验证工艺规则
BO：负责下一轮参数推荐
LLM：负责调度、解释和生成报告
```

### 2.2 不做单一巨型 skill

禁止设计一个包含所有流程的“超快激光总 skill”。
应拆分为多个小 skill，每个 skill 只解决一个明确任务。

### 2.3 Skill 不得让 LLM 直接编造参数

所有激光功率、频率、扫描速度、线间距、层步距、焦点偏移、扫描次数等数值，必须来自以下来源之一：

```text
1. 用户输入；
2. 设备参数边界；
3. 文献证据；
4. 结构化工艺知识库；
5. BO 输出；
6. 已验证规则库。
```

若来源不足，skill 应要求模型追问或输出“不足以推荐确定参数”。

## 3. 目录结构

建议在仓库中新增：

```text
agent_skills/
  README.md

  skill_router/
    SKILL.md
    routing_rules.json
    examples.md

  task_intake/
    SKILL.md
    input_schema.json
    output_schema.json
    examples.md

  crl_task_planning/
    SKILL.md
    input_schema.json
    output_schema.json
    examples.md

  rag_literature_retrieval/
    SKILL.md
    input_schema.json
    output_schema.json
    examples.md

  bo_recommendation/
    SKILL.md
    input_schema.json
    output_schema.json
    examples.md

  process_file_ingestion/
    SKILL.md
    input_schema.json
    output_schema.json
    examples.md

  experience_memory_update/
    SKILL.md
    input_schema.json
    output_schema.json
    examples.md

  bo_dataset_governance/
    SKILL.md
    input_schema.json
    output_schema.json
    examples.md

  report_generation/
    SKILL.md
    input_schema.json
    output_schema.json
    examples.md
```

## 4. Skill 总体调用流程

```text
用户输入
↓
skill_router 判断任务类型
↓
调用对应 skill
↓
skill 输出结构化结果
↓
必要时调用工具：RAG / 数据库 / BO / 文件解析 / 规则库
↓
report_generation 生成最终结果
```

路由逻辑：

```text
模糊加工需求 / 任务文件
→ task_intake

金刚石 CRL / X-ray lens / 曲率半径 / 焦距 / 口径
→ crl_task_planning

需要查文献、找参数范围、找损伤机制
→ rag_literature_retrieval

需要推荐下一轮加工参数
→ bo_recommendation

有日志、recipe、工艺文件、检测文件、操作备注
→ process_file_ingestion

需要沉淀经验、生成规则候选
→ experience_memory_update

需要判断样本能否进入 BO
→ bo_dataset_governance

需要输出任务方案、执行清单、实验报告
→ report_generation
```

## 5. Skill 标准模板

每个 `SKILL.md` 采用统一结构：

```markdown
# Skill Name

## 触发条件

说明什么时候必须使用该 skill。

## 输入

说明该 skill 需要哪些字段。

## 输出

说明必须输出什么结构。

## 执行步骤

列出固定流程。

## 工具调用

说明可调用哪些工具或模块。

## 禁止事项

列出绝对不能做的行为。

## 质量检查

输出前必须检查什么。

## 失败处理

信息不足、检索失败、BO 不可用时如何处理。
```

## 6. Skill 1：skill_router

### 6.1 目标

根据用户输入判断应调用哪个 skill，避免所有任务都走同一个长流程。

### 6.2 触发条件

所有用户输入都先经过该 skill，除非当前会话已处于某个明确 workflow 中。

### 6.3 输出格式

```json
{
  "selected_skill": "task_intake",
  "confidence": 0.86,
  "reason": "用户输入为模糊加工需求，尚未形成结构化任务。",
  "required_next_action": "parse_task"
}
```

### 6.4 路由规则

```text
包含“加工需求、任务文件、参数表、帮我做方案”
→ task_intake

包含“CRL、金刚石透镜、曲率半径、焦距、X-ray”
→ crl_task_planning

包含“查文献、参考文献、已有研究、机制、损伤”
→ rag_literature_retrieval

包含“推荐参数、下一轮实验、优化、BO、贝叶斯”
→ bo_recommendation

包含“日志、recipe、工艺文件、检测结果、自动读取”
→ process_file_ingestion

包含“经验、规则、记忆库、自学习、沉淀”
→ experience_memory_update

包含“是否能加入 BO、样本质量、训练集”
→ bo_dataset_governance

包含“生成报告、执行清单、任务方案”
→ report_generation
```

## 7. Skill 2：task_intake

### 7.1 目标

将用户模糊加工需求或任务文件转化为结构化任务模型。

### 7.2 触发条件

用户输入以下内容时使用：

```text
1. 模糊加工需求；
2. 材料和工艺目标；
3. 表格、任务文件、工程要求；
4. 不完整加工任务描述。
```

### 7.3 执行步骤

```text
1. 识别任务对象；
2. 抽取材料、几何、工艺目标、质量指标；
3. 识别已有信息和缺失信息；
4. 判断是否可直接进入方案设计；
5. 若信息不足，最多提出 3 个高价值问题；
6. 输出 task_spec 草案。
```

### 7.4 禁止事项

```text
1. 不得直接推荐激光参数；
2. 不得补全用户未提供的设备参数；
3. 不得把模糊需求直接转成 BO 输入；
4. 不得一次性追问超过 3 个核心问题。
```

### 7.5 输出结构

```json
{
  "task_type": "manufacturing_planning",
  "component": "diamond_CRL",
  "material": "diamond",
  "process_candidate": "ultrafast_laser_micromachining",
  "known_requirements": {},
  "missing_slots": [],
  "clarification_questions": [],
  "can_continue_to_planning": false
}
```

## 8. Skill 3：crl_task_planning

### 8.1 目标

处理金刚石 CRL、X-ray refractive lens、复合折射透镜等专门任务。

### 8.2 触发条件

用户输入包含：

```text
CRL
compound refractive lens
金刚石透镜
X-ray lens
曲率半径
焦距
10 keV
透镜片数
抛物面
```

### 8.3 执行步骤

```text
1. 抽取 CRL 几何参数；
2. 抽取光学性能要求；
3. 检查 R、N、E、f 是否自洽；
4. 判断该任务是制造规划、工艺推荐还是实验设计；
5. 识别制造风险：面形误差、粗糙度、石墨化、崩边、亚表面损伤；
6. 生成 CRL 制造任务方案；
7. 若需要参数推荐，交给 bo_recommendation。
```

### 8.4 输入字段

```json
{
  "material": "diamond",
  "curvature_radius_mm": 1.0,
  "thickness_mm": 1.0,
  "aperture_mm": 0.9849,
  "parabola_spacing_um": 30,
  "Ra_nm_max": 460,
  "photon_energy_keV": 10,
  "lens_count": 7,
  "focal_length_m": 9.8
}
```

### 8.5 输出字段

```json
{
  "crl_task_spec": {},
  "optical_consistency_check": {
    "status": "pass",
    "notes": []
  },
  "manufacturing_risks": [],
  "required_clarifications": [],
  "recommended_workflow": []
}
```

### 8.6 禁止事项

```text
1. 不得把 Ra < 460 nm 等同于 CRL 光学性能合格；
2. 不得忽略面形误差、焦距误差和装配误差；
3. 不得直接套用普通平面铣削参数；
4. 不得在没有设备边界时调用 BO 推荐确定参数。
```

## 9. Skill 4：rag_literature_retrieval

### 9.1 目标

基于任务模型生成专业检索 query，从文献库或网络检索中提取可追溯证据。

### 9.2 触发条件

用户需要：

```text
1. 查文献；
2. 获取材料加工机制；
3. 获取参数范围；
4. 查找类似工艺案例；
5. 解释损伤、石墨化、粗糙度、去除效率等现象。
```

### 9.3 执行步骤

```text
1. 读取 task_spec；
2. 生成多路 query；
3. 检索文献库；
4. 按材料、工艺、指标、设备条件过滤；
5. 提取 claim；
6. 标注 claim 可用于什么，不能用于什么；
7. 输出 evidence_pack。
```

### 9.4 输出结构

```json
{
  "evidence_pack": [
    {
      "claim": "",
      "source_id": "",
      "page": null,
      "usable_for": [],
      "not_usable_for": [],
      "confidence": "medium"
    }
  ],
  "parameter_priors": [],
  "risk_mechanisms": [],
  "evidence_gaps": []
}
```

### 9.5 禁止事项

```text
1. 不得把文献中的单组最佳参数直接迁移为当前任务最优参数；
2. 不得无来源总结；
3. 不得把不同材料、不同脉宽、不同加工尺度的结果混为一谈；
4. 检索不足时必须说明证据不足。
```

## 10. Skill 5：bo_recommendation

### 10.1 目标

在任务模型、设备边界、文献先验和实验数据基础上调用 BO 推荐下一轮实验参数。

### 10.2 触发条件

用户要求：

```text
1. 推荐加工参数；
2. 设计下一轮实验；
3. 根据反馈优化参数；
4. 调用贝叶斯优化。
```

### 10.3 输入要求

必须包含：

```json
{
  "material": "",
  "process_type": "",
  "objective_mode": "",
  "machine_bounds": {},
  "decision_variables": {},
  "target_metrics": {},
  "constraints": {},
  "training_sample_count": 0
}
```

### 10.4 样本数判断

```text
training_sample_count < 10
→ rule_based_cold_start

10 <= training_sample_count < 30
→ hybrid_rule_bo

training_sample_count >= 30
→ data_driven_bo
```

### 10.5 执行步骤

```text
1. 检查 task_spec 是否完整；
2. 检查设备边界是否存在；
3. 检查目标函数是否明确；
4. 查询可用训练样本数量；
5. 判断 model_status；
6. 构造 BO 输入；
7. 调用 BO 引擎；
8. 用规则库过滤危险参数；
9. 输出候选参数、证据链、模型状态和风险。
```

### 10.6 禁止事项

```text
1. LLM 不得自行生成功率、频率、速度等数值；
2. 不得把 BO 结果说成实测最优；
3. 不得省略 model_status；
4. 样本不足时不得声称 data_driven_bo；
5. 设备边界缺失时不得输出确定参数。
```

### 10.7 输出结构

```json
{
  "model_status": "hybrid_rule_bo",
  "recommendations": [
    {
      "candidate_id": "",
      "parameters": {},
      "predicted_metrics": {},
      "uncertainty": {},
      "reason": ""
    }
  ],
  "evidence_trace": [],
  "risks": [],
  "next_experiment_plan": []
}
```

## 11. Skill 6：process_file_ingestion

### 11.1 目标

处理加工软件系统产生的日志、工艺文件、检测结果和操作备注，转化为可追溯结构化数据。

### 11.2 触发条件

用户上传或系统检测到：

```text
recipe
job
log
csv
xlsx
gcode
nc
检测报告
操作员备注
```

### 11.3 执行步骤

```text
1. 识别文件类型；
2. 计算 SHA256；
3. 归档原始文件；
4. 调用专用 parser；
5. 标准化单位；
6. 写入 raw_artifact；
7. 写入 process_task / process_recipe / process_run / measurement_record；
8. 对备注生成 experience_candidate；
9. 标记解析错误和质量问题。
```

### 11.4 禁止事项

```text
1. 不得修改原始文件；
2. 不得跳过 hash；
3. 不得用 LLM 猜测缺失数值；
4. 不得把操作员描述直接写成正式规则；
5. 不得把异常中断数据直接加入 BO。
```

### 11.5 输出结构

```json
{
  "import_summary": {
    "imported_files": 0,
    "skipped_duplicates": 0,
    "errors": []
  },
  "created_records": {
    "tasks": [],
    "recipes": [],
    "runs": [],
    "measurements": [],
    "experience_candidates": []
  },
  "quality_warnings": []
}
```

## 12. Skill 7：experience_memory_update

### 12.1 目标

将加工过程中的有价值经验转化为候选知识，并通过审核机制进入专业知识记忆库。

### 12.2 触发条件

出现以下输入时使用：

```text
1. 操作员备注；
2. 加工失败描述；
3. 检测结果异常；
4. 多次实验趋势；
5. 用户要求沉淀经验；
6. 用户确认某条规则。
```

### 12.3 知识生命周期

```text
Level 0：原始文件
Level 1：结构化记录
Level 2：经验候选
Level 3：人工确认经验
Level 4：验证规则
Level 5：BO 训练样本
```

### 12.4 执行步骤

```text
1. 收集相关 run、recipe、measurement、note；
2. 抽取 observation；
3. 提出 possible_causes；
4. 生成 candidate_rule；
5. 判断是否需要人工确认；
6. 默认写入 experience_candidate；
7. 不自动晋升 validated_rule；
8. 若满足多案例条件，提示可进行规则晋升审核。
```

### 12.5 禁止事项

```text
1. 单次观察不得晋升为验证规则；
2. 无测量支撑不得进入 BO 训练集；
3. 主观描述不得覆盖实测数据；
4. 冲突案例不得删除；
5. 不得伪造 Raman、Ra、面形误差等检测结果。
```

### 12.6 输出结构

```json
{
  "experience_candidate": {
    "claim": "",
    "evidence": {},
    "confidence": 0.0,
    "status": "candidate",
    "required_validation": []
  },
  "promotion_recommendation": {
    "should_promote": false,
    "reason": ""
  }
}
```

## 13. Skill 8：bo_dataset_governance

### 13.1 目标

判断实验记录是否可进入 BO 训练集，防止脏数据污染优化模型。

### 13.2 触发条件

当系统需要：

```text
1. 导出 BO 数据集；
2. 更新 BO 样本；
3. 判断某次实验是否有效；
4. 处理异常日志；
5. 构造训练 CSV。
```

### 13.3 BO 准入条件

样本进入 BO 必须满足：

```text
1. run_status == completed；
2. abnormal_flag == 0；
3. recipe 参数完整；
4. material 不为空；
5. process_type 不为空；
6. 至少一个有效质量指标；
7. measurement.valid_flag == true；
8. 单位已标准化；
9. 样品、run、recipe、measurement 可关联。
```

### 13.4 输出结构

```json
{
  "run_id": "",
  "valid_for_training": false,
  "invalid_reasons": [],
  "x_parameters": {},
  "y_metrics": {},
  "warnings": []
}
```

### 13.5 禁止事项

```text
1. 不得自动补齐缺失测量值；
2. 不得忽略报警和中断；
3. 不得把备注中的“效果不错”当作数值指标；
4. 不得把单位不明的数据加入训练集。
```

## 14. Skill 9：report_generation

### 14.1 目标

将任务解析、文献证据、BO 推荐、经验库结果和风险检查整合成用户可执行的方案或报告。

### 14.2 触发条件

用户需要：

```text
1. 任务方案；
2. 执行清单；
3. 工艺建议；
4. 实验设计；
5. 失败分析；
6. 下一轮优化计划。
```

### 14.3 输出内容

报告必须包含：

```text
1. 任务理解；
2. 已知条件；
3. 缺失条件；
4. 文献依据；
5. 内部经验依据；
6. BO 模型状态；
7. 推荐方案；
8. 风险；
9. 执行清单；
10. 下一轮反馈格式。
```

### 14.4 禁止事项

```text
1. 不得隐藏模型状态；
2. 不得省略证据来源；
3. 不得把建议写成已验证最优；
4. 不得在证据不足时输出确定性结论。
```

## 15. Skill 之间的数据接口

所有 skill 之间传递统一对象：

```json
{
  "task_spec": {},
  "evidence_pack": [],
  "memory_hits": [],
  "bo_status": {},
  "recommendation": {},
  "quality_warnings": [],
  "audit_trace": []
}
```

其中 `audit_trace` 必须记录：

```json
[
  {
    "step": "task_intake",
    "input_summary": "",
    "output_summary": "",
    "timestamp": "",
    "status": "success"
  }
]
```

## 16. Skill 测试设计

每个 skill 至少需要 3 类测试：

### 16.1 正常案例

输入完整，skill 正确输出结构化结果。

### 16.2 缺失案例

输入不完整，skill 应追问或拒绝继续。

### 16.3 禁止案例

用户要求模型直接编造参数时，skill 必须拒绝。

示例测试：

```text
用户输入：
“我要加工金刚石 CRL，Ra < 460 nm，直接给我激光功率和速度。”

期望：
不直接给参数；
先调用 task_intake / crl_task_planning；
指出缺少设备边界、材料类型、工艺阶段、历史数据；
最多提出 3 个关键问题。
```

## 17. Codex 实现任务

给 Codex 的实现要求：

```text
1. 在仓库中新建 agent_skills/；
2. 为每个 skill 创建 SKILL.md；
3. 为核心 skill 创建 input_schema.json 和 output_schema.json；
4. 创建 skill_router/routing_rules.json；
5. 创建 examples.md，包含正例、缺失例、拒绝例；
6. 在 README 中说明 skill 的作用和使用方式；
7. 不要把文献和实验数据写进 SKILL.md；
8. 不要把 API Key、私有日志、用户实验记录放进 skill。
```

## 18. 验收标准

完成后应满足：

```text
1. 每个 skill 有明确触发条件；
2. 每个 skill 有明确输入输出；
3. 每个 skill 有禁止事项；
4. BO 推荐 skill 明确禁止 LLM 生成参数；
5. 文件自学习 skill 明确保留原始文件和 hash；
6. 经验更新 skill 明确候选经验不能自动晋升规则；
7. CRL skill 明确 Ra 不等于光学性能合格；
8. report_generation skill 明确必须输出证据链和 model_status；
9. skill_router 能将典型输入路由到正确 skill。
```

## 19. 总结

本项目中的 skill 不应被设计成“领域知识备忘录”，而应被设计成“稳定执行协议”。

正确架构是：

```text
Skill 控制流程
Memory 保存知识
RAG 检索证据
Database 保存事实
Rules 保存验证经验
BO 推荐参数
LLM 编排与解释
```

优先固化的流程是：

```text
模糊任务解析
CRL 制造规划
加工文件自学习
BO 推荐准入
经验库更新
证据化报告生成
```

这样可以显著降低上下文占用，减少大模型在长任务中的行为漂移，并使系统逐步具备可审计、可复现、可扩展的工程能力。