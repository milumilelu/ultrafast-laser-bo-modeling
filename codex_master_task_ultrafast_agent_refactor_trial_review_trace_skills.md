# Codex 主任务文档：超快激光智能体架构重构、双模式试切、Skill 重构、按需审核与实时执行轨迹

更新时间：2026-07-10

## 0. 文档定位

本任务文档整合当前系统的五项核心需求，并补充展示前必须完成的工程化工作。

五项核心需求：

```text
1. 优化当前由早期贝叶斯优化系统二次扩展而来的仓库结构；
2. 在架构优化后实现单人、低操作成本、使用时触发的知识审核系统；
3. 扩大公开执行过程的实时可见范围，并同步优化响应时间；
4. 将试切拆分为简化试切和完整试切两种可选模式；
5. 重新盘点、梳理和优化现有 Skill，处理 crl_task_planning 等历史 Skill。
```

展示与工程补充要求：

```text
1. 建立唯一技术路线和唯一正式入口；
2. 打通一个可重复、可解释、可离线降级的端到端演示闭环；
3. 明确哪些能力真实实现、哪些为部分实现、哪些为计划；
4. 生成任务报告、执行审计和性能 waterfall；
5. 保持旧 BO 功能和旧命令兼容；
6. 所有高风险参数必须经过设备边界和知识使用决策门。
```

本任务不是简单整理目录，也不是增加几个 API。

最终目标是把当前系统收束为：

```text
任务理解
→ 设备与材料硬约束
→ 内部知识检索
→ 工艺路线规划
→ 试切策略选择
→ 简化或完整试切
→ 质量评价
→ 知识使用审核
→ 贝叶斯优化
→ 正式加工规划
→ 结果回收
→ 实验与知识闭环
```

---

# 1. 总体原则

## 1.1 架构原则

```text
先盘点，后重构；
先稳定领域边界，后新增审核和试切；
先统一 Runtime，后扩展执行轨迹；
先保持旧接口兼容，后逐步迁移；
先完成真实端到端链路，后扩展更多场景。
```

## 1.2 决策原则

```text
LLM 负责理解、分类、解释和流程建议；
规则负责准入和硬约束；
设备配置负责物理边界；
RAG 负责提供证据；
审核负责允许高风险知识进入决策；
BO 负责参数优化；
用户保留高风险决策的最终控制权。
```

## 1.3 知识治理原则

```text
RAG 是检索层，不是知识准入本体；
未审核文献原文可用于背景解释和证据展示；
未审核参数不得直接用于确定性参数推荐；
未审核参数不得影响 BO 搜索边界；
process_prior 必须由审核动作产生；
bo_training_sample 只能来自完整、有效、质量校验后的实验记录；
不得由 LLM 或文献自动生成 validated_rule。
```

## 1.4 执行过程公开边界

允许公开：

```text
任务解析状态
工作流阶段
选择的 Skill
工具调用状态
输入摘要
输出摘要
证据数量
路由摘要
设备配置摘要
审核门结论
BO 状态
错误、重试和 fallback
耗时和缓存命中
```

禁止公开：

```text
模型隐藏 chain-of-thought
raw_thoughts
hidden_reasoning
模型内部草稿
完整 system prompt
API Key
敏感工具载荷
DPAPI 密文
未经脱敏的用户隐私数据
```

---

# 2. 任务范围

## 2.1 本任务必须完成

```text
仓库事实盘点
依赖关系分析
目标架构设计
模块化重构
旧 BO 兼容层
统一 Agent Runtime
Skill inventory 和 Skill 迁移
双模式试切
知识使用决策门
单人按需审核
审批复用
真实工具执行轨迹
NDJSON 流式输出
性能 waterfall
Demo Mode
Doctor 健康检查
端到端演示场景
任务结果报告
测试和 README
```

## 2.2 本任务暂不完成

```text
真实机床闭环控制
完整 CAD/CAM 商业软件替代
自动 OCR
复杂图像和公式视觉理解
多用户 RBAC 审核系统
微服务拆分
自动下载付费论文
自动生成 validated_rule
自动把文献参数写入 BO 训练集
完整 Web 管理后台
```

---

# 3. 阶段 0：仓库事实盘点与基线冻结

Codex 不得直接移动文件或重写业务逻辑。

第一阶段只允许盘点、分析和生成报告。

## 3.1 Git 盘点

输出：

```text
remote URL
current branch
HEAD commit
所有本地分支
所有 remote 分支
未提交文件
未跟踪文件
被 .gitignore 排除的关键目录
是否存在多个项目根
```

生成：

```text
reports/repository_inventory.json
docs/architecture/current_git_state.md
```

## 3.2 代码盘点

扫描：

```text
所有 Python 文件
所有入口
所有 API
所有 CLI 命令
所有 PowerShell TUI 脚本
所有 Skill
所有 Tool
所有 Service
所有数据库模型
所有 migration
所有配置文件
所有测试
```

每项标记：

```text
implemented
partial
stub
planned_only
not_found
```

生成：

```text
docs/architecture/current_state.md
docs/architecture/dependency_graph.md
docs/architecture/implementation_status_matrix.md
```

## 3.3 功能盘点

至少检查：

```text
BO
Chat
Router
Agent Runtime
Skill
Equipment Memory
RAG
Literature Ingestion
Knowledge Candidate
Knowledge Review
Trial Cut
Execution Trace
PowerShell TUI
FastAPI
Demo Mode
Doctor
Task Report
```

## 3.4 数据盘点

检查：

```text
SQLite 数据库
数据库表
RAG 索引
PDF 文献
literature_cards
knowledge_candidates
review tasks
equipment profiles
BO datasets
任务状态文件
日志
报告
```

生成：

```text
reports/data_inventory.json
```

## 3.5 性能基线

测量：

```text
应用启动时间
/chat 首事件时间
/chat 首 token 时间
/chat 总响应时间
RAG 查询时间
Router 时间
设备配置读取时间
数据库查询时间
BO 推荐时间
试切计划生成时间
```

输出：

```text
reports/baseline_performance.json
reports/baseline_performance.md
```

## 3.6 基线冻结

必须完成：

```text
创建 git tag：pre-agent-refactor
备份数据库
备份配置
运行全部 pytest
保存关键 CLI 输出
保存关键 API golden response
保存典型会话 replay fixture
```

典型任务：

```text
TGV 高深径比打孔
T300 CFRP 表面织构或微孔
金刚石 CRL
设备配置读取
BO 冷启动
BO 混合模式
RAG 查询
知识候选审核前状态
```

阶段 0 完成前，禁止进入后续重构。

---

# 4. 阶段 1：目标架构与仓库重构

## 4.1 目标形态

采用模块化单体，不立即拆微服务。

建议结构：

```text
repository/
  pyproject.toml
  README.md
  configs/
  migrations/
  scripts/
  docs/
  reports/
  tests/

  apps/
    api/
    cli/
    tui/

  src/
    ultrafast_agent/
      runtime/
      workflows/
      observability/

    ultrafast_domain/
      task/
      equipment/
      process/
      trial/
      evidence/
      knowledge/
      review/

    ultrafast_bo/
      application/
      domain/
      infrastructure/
      compatibility/

    ultrafast_rag/
      ingestion/
      indexing/
      retrieval/
      evidence_pack/

    ultrafast_integrations/
      llm/
      storage/
      files/
      web_search/

    ultrafast_shared/
      config/
      db/
      ids/
      time/
      errors/
      schemas/
```

## 4.2 依赖方向

只允许：

```text
apps
→ application/runtime
→ domain
→ infrastructure adapters
```

禁止：

```text
domain 依赖 FastAPI
domain 依赖 PowerShell
BO 依赖 Chat
RAG 直接依赖 BO
API 直接拼接 SQL
Skill 直接操作数据库
LLM adapter 直接写知识库
```

## 4.3 领域职责

### `ultrafast_agent`

负责：

```text
session
route plan
workflow execution
tool registry
event bus
timeout
retry
cancellation
trace
result aggregation
```

### `ultrafast_domain.task`

负责：

```text
任务结构
任务状态
缺失字段
用户约束
任务 revision
```

### `ultrafast_domain.equipment`

负责：

```text
设备权威配置
设备 revision
物理边界
设备能力匹配
```

### `ultrafast_domain.trial`

负责：

```text
试切必要性
试切模式
试切计划
试切执行
试切结果
正式加工解锁
```

### `ultrafast_domain.knowledge`

负责：

```text
knowledge_candidate
literature_evidence
process_prior
validated_rule
bo_training_sample
知识用途边界
```

### `ultrafast_domain.review`

负责：

```text
知识使用决策
当前任务批准
长期先验批准
审批复用
撤销
审计
```

### `ultrafast_bo`

只负责：

```text
实验数据校验
特征工程
代理模型
采集函数
候选生成
候选排序
反馈更新
```

### `ultrafast_rag`

只负责：

```text
文献导入
chunk
索引
混合检索
rerank
Evidence Pack
引用
```

## 4.4 旧 BO 兼容

不得一次性删除旧 `main.py` 和旧命令。

采用兼容 Facade：

```text
旧入口
→ compatibility adapter
→ 新 BO application service
```

必须继续支持旧命令，至少一个稳定版本周期。

新增正式服务：

```python
OfflineModelingService
RecommendationService
FeedbackService
DatasetValidationService
BOStatusService
```

## 4.5 统一配置

配置分组：

```yaml
app:
agent:
llm:
database:
equipment:
rag:
knowledge_review:
trial:
bo:
observability:
performance:
demo:
```

加载顺序：

```text
default.yaml
→ local.yaml
→ environment variables
→ CLI override
```

## 4.6 统一数据库访问

新增：

```text
ultrafast_shared/db/
  session.py
  unit_of_work.py
  migrations.py
```

要求：

```text
审核动作和审计动作原子提交
试切执行和结果原子提交
BO 推荐和 trace 可关联
API 不直接持有连接
migration 幂等
```

## 4.7 阶段 1 验收

```text
旧 BO 命令兼容
全部旧测试通过
全部现有智能体测试通过
无新增循环依赖
Apps 不包含核心业务规则
RAG 与 BO 解耦
数据库 migration 可重复运行
golden response 通过
性能不比基线恶化超过 10%
```

---

# 5. 阶段 2：Skill 体系重新梳理与优化

## 5.1 先做 Skill Inventory

生成：

```text
docs/skills/skill_inventory.md
docs/skills/skill_dependency_graph.md
docs/skills/skill_decision_matrix.md
```

每个 Skill 记录：

```text
name
file path
callers
called tools
input schema
output schema
side effects
timeout
cache policy
tests
usage count
duplicated logic
domain-specific logic
```

分类：

```text
keep
refactor
merge
split
deprecate
remove
convert_to_tool
convert_to_domain_rule
```

## 5.2 Skill 设计原则

从“场景型 Skill”转向：

```text
通用能力 Skill
+ 领域规则包
+ 工艺策略插件
+ 检测模板
```

## 5.3 通用基础 Skill

```text
task_intake
task_normalization
equipment_context_loading
material_identification
geometry_interpretation
constraint_extraction
rag_evidence_retrieval
historical_case_retrieval
similar_case_retrieval
```

## 5.4 工艺规划 Skill

```text
process_route_planning
parameter_space_construction
toolpath_strategy_selection
quality_plan_generation
measurement_plan_generation
trial_need_assessment
trial_strategy_selection
```

## 5.5 决策与优化 Skill

```text
knowledge_use_gate
process_risk_assessment
equipment_capability_match
bo_mode_selection
bo_recommendation
candidate_validation
formal_process_gate
```

## 5.6 执行与闭环 Skill

```text
execution_plan_generation
in_process_monitoring_plan
trial_result_ingestion
quality_evaluation
result_ingestion
knowledge_candidate_generation
process_prior_promotion
report_generation
latency_diagnostics
execution_trace_summary
```

## 5.7 Tool 与 Skill 边界

以下应是 Tool 或 Service，不应是 Skill：

```text
读取 SQLite
调用 FTS
向量查询
计算 SHA256
加载设备配置
单位转换
阈值检查
PDF 文本抽取
文件复制
写 CSV
```

Skill 必须包含业务判断或流程编排。

## 5.8 Domain Pack

新增：

```text
domain_packs/
  crl/
  tgv/
  film_cooling_hole/
  cover_glass/
  surface_texturing/
```

每个 pack 可包含：

```text
geometry_rules.py
quality_metrics.py
process_constraints.py
trial_templates.py
measurement_templates.py
prompts.py
```

## 5.9 `crl_task_planning` 处理

不得直接删除。

先生成：

```text
docs/skills/crl_task_planning_assessment.md
```

必须回答：

```text
当前路径
调用者
输入输出
副作用
调用工具
重复逻辑
CRL 专有逻辑
可迁移通用 Skill 的逻辑
可迁移 Domain Pack 的逻辑
建议 keep/refactor/merge/deprecate
兼容迁移方案
```

推荐目标：

```text
保留旧名作为兼容入口
内部调用 optical_component_task_workflow
加载 crl domain pack
发出 deprecated_skill_used 事件
```

仅当 CRL 确实存在以下专有能力时，保留轻量编排 Skill：

```text
双抛物面几何
专用路径生成
双光路协同
面形误差
波前和焦斑评价
```

## 5.10 Skill 契约

每个 Skill 必须声明：

```yaml
name:
version:
purpose:
inputs:
outputs:
preconditions:
side_effects:
allowed_tools:
forbidden_tools:
failure_modes:
timeout_ms:
cache_policy:
emitted_events:
```

阶段 2 验收：

```text
所有 Skill 有 inventory
重复 Skill 被合并或标记迁移
业务 Skill 不直接访问数据库
场景差异优先进入 Domain Pack
crl_task_planning 有清晰迁移结论
用户界面不要求理解 Skill 名称
Research/Debug 模式可查看 Skill 调用链
```

---

# 6. 阶段 3：双模式试切

## 6.1 统一试切模式

```text
skip_trial
simple_trial_cut
full_trial_cut
```

## 6.2 新增 Skill

```text
trial_need_assessment
trial_strategy_selection
simple_trial_design
full_trial_design
trial_measurement_planning
trial_acceptance_evaluation
trial_result_ingestion
trial_to_process_transition
```

## 6.3 简化试切

目标：

```text
用最小材料、时间和参数点验证：
去除量
去除稳定性
加工质量
热影响
裂纹和崩边
设备状态
参数量级
```

代表性几何：

```text
铣削：单道线、矩形、阶梯块、小方槽
切割：直线、小圆、小方形、短圆弧
钻孔：单孔、3×3 孔阵列、小型 DOE
表面织构：小面积沟槽、点阵、条纹块
CRL：浅抛物面片段、缩比透镜、局部测试坑
气膜孔：单孔、不同入射角小孔组
```

简化试切不验证：

```text
完整复杂轮廓
全路径累积误差
完整零件总加工时间
所有服役性能
```

## 6.4 完整试切

验证：

```text
完整几何
完整路径
完整层策略
完整换区逻辑
完整加工时间
完整检测
```

必须支持停止条件：

```text
能量漂移
深度偏离
温升异常
裂纹增长
崩边超限
在线监测异常
设备报警
加工时间异常
```

## 6.5 推荐规则

推荐简化试切：

```text
首次材料
首次设备 revision
首次波长或脉宽
无已批准 process_prior
证据不足
几何复杂
材料昂贵
完整试切耗时长
高风险
有效样本少于 10
```

推荐完整试切：

```text
材料、设备、工艺高度匹配
有验证参数
有相似历史任务
有可复用审批
设备 revision 未变化
需要验证完整路径累积效应
```

允许跳过：

```text
完全重复任务
设备、材料、几何、参数都在已验证范围
有完整合格记录
用户明确允许
```

## 6.6 数据模型

### `trial_plan`

```sql
CREATE TABLE trial_plan (
    trial_plan_id TEXT PRIMARY KEY,
    task_id TEXT,
    trial_mode TEXT,
    representative_geometry_json TEXT,
    parameter_matrix_json TEXT,
    measurement_plan_json TEXT,
    acceptance_criteria_json TEXT,
    stop_conditions_json TEXT,
    status TEXT,
    created_at TEXT,
    updated_at TEXT
);
```

### `trial_execution`

```sql
CREATE TABLE trial_execution (
    execution_id TEXT PRIMARY KEY,
    trial_plan_id TEXT,
    equipment_revision TEXT,
    actual_parameters_json TEXT,
    actual_path_json TEXT,
    monitoring_summary_json TEXT,
    started_at TEXT,
    finished_at TEXT,
    status TEXT
);
```

### `trial_result`

```sql
CREATE TABLE trial_result (
    result_id TEXT PRIMARY KEY,
    execution_id TEXT,
    measurements_json TEXT,
    defects_json TEXT,
    quality_status TEXT,
    decision TEXT,
    reviewer_comment TEXT,
    created_at TEXT
);
```

决策：

```text
pass
conditional_pass
fail
```

## 6.7 API

```http
POST /tasks/{task_id}/trial/assess
POST /tasks/{task_id}/trial/select
POST /tasks/{task_id}/trial/plans
GET  /trial/plans/{trial_plan_id}
POST /trial/plans/{trial_plan_id}/executions
POST /trial/executions/{execution_id}/results
POST /trial/results/{result_id}/evaluate
```

## 6.8 用户交互

只显示：

```text
系统建议先进行简化试切。

[简化试切]
[完整试切]
[跳过试切]
```

高级内容折叠：

```text
推荐依据
测试几何
参数矩阵
验收标准
预计时间
预计材料消耗
```

## 6.9 阶段 3 验收

```text
用户可选简化或完整试切
系统给出推荐和原因
简化试切生成代表性几何
完整试切支持停止条件
两类试切都能回收结果
试切结果可解锁或阻塞正式加工
试切记录不自动进入 BO
质量校验后才可进入实验数据层
```

---

# 7. 阶段 4：单人按需审核系统

## 7.1 审核触发原则

不触发：

```text
文献检索
背景解释
缺陷总结
表征方法
展示原始文献数值
```

触发：

```text
参数推荐
BO 搜索边界
候选参数过滤
process_prior 晋升
安全阈值使用
冲突知识使用
```

## 7.2 最小状态

候选知识：

```text
background
review_required
approved
rejected
```

批准范围：

```text
current_task
process_prior
```

## 7.3 LLM 分类

固定输出：

```json
{
  "claim_type": "background|mechanism|measurement|trend|numeric_range|recommendation|safety",
  "risk_level": "low|medium|high|critical",
  "allowed_uses": ["background_explanation"],
  "requires_review_before": ["parameter_recommendation"],
  "reason_summary": "包含具体扫描速度范围。"
}
```

LLM 只能分类，不能批准。

## 7.4 确定性规则兜底

```text
含数值和单位 → 至少 medium
含上下限 → high
含“最优、推荐、应采用” → high
安全和损伤阈值 → critical
仅定义、背景、测量方法 → low
分类失败 → background_only
```

## 7.5 KnowledgeUseGate

```python
decision = KnowledgeUseGate.evaluate(
    task_spec=task_spec,
    intended_use=intended_use,
    evidence=evidence_pack,
    equipment=equipment_snapshot,
)
```

输出：

```text
allowed
approval_required
blocked
```

## 7.6 一次聚合审核

同一任务最多主动弹出一次。

每次最多包含 5 个参数或结论。

审核的是 `Decision Evidence Bundle`，不是单条 claim。

普通界面只显示：

```text
[本次允许使用]
[批准为长期工艺先验]
[不使用]
```

高级详情折叠：

```text
原文上下文
页码
来源论文
适用条件
冲突文献
设备裁剪
参数上下限
审核备注
```

## 7.7 审批复用

审批 key 必须包括：

```text
source revision
claim revision
material
material_grade
process_type
equipment revision
intended use
condition hash
```

以下变化使审批失效：

```text
来源变化
结论变化
设备 revision 变化
材料变化
适用范围扩大
出现冲突证据
超出批准范围
```

## 7.8 数据表

### `knowledge_usage_decision`

```sql
CREATE TABLE knowledge_usage_decision (
    decision_id TEXT PRIMARY KEY,
    session_id TEXT,
    task_id TEXT,
    intended_use TEXT,
    evidence_ids_json TEXT,
    proposed_usage_json TEXT,
    risk_level TEXT,
    status TEXT,
    created_at TEXT,
    resolved_at TEXT
);
```

### `knowledge_usage_approval`

```sql
CREATE TABLE knowledge_usage_approval (
    approval_id TEXT PRIMARY KEY,
    decision_id TEXT,
    approval_scope TEXT,
    reviewer_id TEXT,
    approved_payload_json TEXT,
    applicable_conditions_json TEXT,
    source_revision_hash TEXT,
    comment TEXT,
    created_at TEXT,
    revoked_at TEXT
);
```

复用已有 append-only `knowledge_review_action`。

## 7.9 API

```http
GET  /knowledge/usage-decisions/{decision_id}
POST /knowledge/usage-decisions/{decision_id}/approve-task
POST /knowledge/usage-decisions/{decision_id}/approve-prior
POST /knowledge/usage-decisions/{decision_id}/reject
POST /knowledge/usage-approvals/{approval_id}/revoke
```

## 7.10 阶段 4 验收

```text
普通 RAG 不触发审核
参数进入决策时只触发一次
当前任务批准不写入长期先验
长期批准生成受条件约束的 process_prior
未操作时继续，但不输出确定性参数
相同条件自动复用审批
设备 revision 变化使审批失效
BO 不能绕过 Gate
审核服务失败时 fail closed
```

---

# 8. 阶段 5：统一 Agent Runtime 与实时执行轨迹

## 8.1 Runtime 模块

新增：

```text
workflow_runner.py
tool_registry.py
event_bus.py
execution_context.py
cancellation.py
timeout_policy.py
retry_policy.py
trace_collector.py
```

统一入口：

```python
runtime.execute(workflow, context)
```

所有 Skill、Tool、RAG、设备读取、审核门、试切和 BO 必须通过 Runtime。

## 8.2 AgentEvent

```python
class AgentEvent:
    event_id: str
    trace_id: str
    session_id: str
    task_id: str | None
    sequence: int
    timestamp: str
    event_type: str
    stage: str
    status: str
    title: str
    summary: str
    progress: int | None
    duration_ms: int | None
    tool_name: str | None
    input_summary: dict
    output_summary: dict
    evidence_refs: list
    parent_event_id: str | None
    visibility: str
```

事件类型：

```text
workflow_started
stage_started
stage_progress
stage_completed
route_selected
skill_selected
skill_deprecated
domain_pack_loaded
state_updated
tool_started
tool_progress
tool_completed
tool_failed
cache_hit
cache_miss
evidence_found
evidence_filtered
trial_need_assessed
trial_mode_recommended
trial_mode_selected
trial_plan_generated
decision_gate
approval_required
warning
fallback
finalizing
workflow_completed
workflow_failed
```

## 8.3 真实事件原则

错误：

```text
LLM 说“正在读取设备配置”
```

正确：

```text
EquipmentTool 开始
→ tool_started
EquipmentTool 返回
→ tool_completed
```

## 8.4 NDJSON Streaming

```http
POST /chat/stream
Content-Type: application/x-ndjson
```

示例：

```json
{"type":"workflow_started","stage":"intake","summary":"开始解析任务"}
{"type":"route_selected","stage":"routing","summary":"进入复杂加工任务规划","progress":10}
{"type":"tool_started","stage":"equipment","tool_name":"equipment_memory","summary":"读取设备配置","progress":20}
{"type":"tool_completed","stage":"equipment","summary":"设备配置已加载","duration_ms":32,"progress":30}
{"type":"tool_started","stage":"rag","tool_name":"hybrid_retriever","summary":"检索 TGV 文献","progress":40}
{"type":"evidence_found","stage":"rag","summary":"命中 8 个 chunk，来自 4 篇论文","progress":55}
{"type":"trial_mode_recommended","stage":"trial","summary":"建议简化试切","progress":65}
{"type":"decision_gate","stage":"knowledge_use","summary":"当前仅用于背景解释，无需审核","progress":72}
{"type":"assistant_delta","text":"已识别任务为……"}
{"type":"workflow_completed","progress":100,"duration_ms":6840}
```

## 8.5 显示模式

### Normal

```text
总进度
当前阶段
关键警告
最终结果
```

### Research

```text
全部工具步骤
设备摘要
证据数量
试切判断
审核门
BO 状态
耗时
```

### Debug

```text
route_plan
Skill 链
缓存
输入输出摘要
错误
retry
fallback
各阶段 latency
```

命令：

```text
/mode normal
/mode research
/mode debug
```

## 8.6 PowerShell TUI

新增或完善：

```text
Show-AgentProgressBar
Show-AgentWorkflowState
Show-AgentExecutionTrace
Show-AgentToolCall
Show-AgentEvidenceSummary
Show-AgentTrialDecision
Show-AgentApprovalCard
Show-AgentLatencyWaterfall
```

折叠段：

```text
任务理解
设备与边界
执行轨迹
文献证据
试切策略
知识审核
BO 状态
风险与下一步
```

## 8.7 阶段 5 验收

```text
请求 500 ms 内出现首事件
所有工具事件来自真实执行器
事件 sequence 单调
失败时有 tool_failed/workflow_failed
最终必有 completed 或 failed
Research/Debug 可展开
无隐藏 chain-of-thought
无敏感数据泄露
```

---

# 9. 阶段 6：响应时间治理

## 9.1 延迟预算

```yaml
performance:
  budgets_ms:
    route: 800
    equipment: 300
    rag: 2500
    review_gate: 500
    trial_strategy: 1000
    bo: 3000
    llm_first_token: 2500
    total_soft: 12000
    total_hard: 30000
```

## 9.2 并行

任务字段足够时并行：

```text
设备读取
会话历史读取
RAG 查询准备
审批缓存检查
历史案例检索
```

## 9.3 缓存

缓存：

```text
active equipment profile
route result
RAG query + filters
paper/chunk metadata
candidate classification
approved knowledge usage
similar cases
BO surrogate
trial template
```

所有缓存 key 必须包含 revision。

## 9.4 避免重复 LLM

一次任务默认最多：

```text
Router LLM：规则不确定时
Classifier LLM：新候选且缓存失效时
Answer LLM：一次
```

## 9.5 预计算

```text
文献 embedding
candidate 风险分类
metadata filter fields
BO surrogate
设备快照
演示查询缓存
```

## 9.6 连接复用

```text
数据库连接池
HTTP Client 复用
LLM keep-alive
索引句柄复用
```

## 9.7 fallback

```text
RAG 超时 → FTS 或结构化知识 fallback
Router 超时 → 规则 Router
LLM 失败 → 模板化演示答案
BO 超时 → 返回搜索空间和阻塞原因
审核服务失败 → 禁止使用高风险知识
数据库只读 → Demo read-only
```

## 9.8 Waterfall

每个请求记录：

```text
request_received
session_load
route
equipment
rag_lexical
rag_vector
rag_rerank
trial_strategy
knowledge_gate
bo
prompt_build
llm_first_token
llm_complete
response_complete
```

输出 P50/P95/P99。

阶段 6 验收：

```text
首事件 < 500 ms
缓存命中明显快于未命中
重复 RAG 不重复 embedding
同一任务不重复 Router LLM
常规任务 P95 在预算内
每次请求有 waterfall
```

---

# 10. 阶段 7：展示模式与端到端闭环

## 10.1 唯一正式入口

```powershell
ultrafast
```

旧 BO 可作为兼容命令：

```powershell
ultrafast legacy-bo ...
```

## 10.2 Demo Mode

```powershell
ultrafast --demo
```

固定：

```text
设备配置
文献索引
示例任务
LLM 模型
随机种子
模拟试切结果
缓存
超时
fallback
```

## 10.3 Doctor

```powershell
ultrafast doctor
```

检查：

```text
Python
依赖
数据库
migration
设备 profile
RAG index
文献数量
LLM 连通性
BO 数据
端口
写权限
测试数据
Demo fixtures
```

输出：

```text
READY FOR DEMO
```

或阻塞项。

## 10.4 主演示场景：TGV

完整链路：

```text
输入 TGV 任务
→ 读取设备
→ 识别玻璃、厚度、孔径、深径比
→ RAG 检索
→ Evidence Pack
→ 推荐简化试切：3×3 孔阵列
→ 生成 5–9 个参数点
→ 导入模拟或真实检测结果
→ 判定 pass/conditional_pass/fail
→ 需要时触发一次知识审核
→ BO 下一轮推荐
→ 生成正式加工规划
→ 输出任务报告
```

## 10.5 辅助演示场景：金刚石 CRL

展示：

```text
复杂几何
CRL Domain Pack
浅抛物面简化试切
面形误差和波前评价
Skill 组合而非单体 crl_task_planning
```

## 10.6 任务报告

每个任务生成：

```text
task_report.md
task_report.json
```

内容：

```text
任务目标
材料和构件
设备及 revision
文献和引用
Evidence Status
工艺路线
试切模式
测试几何
参数窗口和来源
设备裁剪
审核记录
BO 模式
有效样本数
推荐参数
质量计划
停止条件
风险
下一步
执行耗时
```

## 10.7 README 功能状态矩阵

必须明确：

```text
功能
状态
是否可演示
是否使用真实数据
限制
```

禁止同时出现：

```text
“RAG 未实现”
和
“RAG 已完整实现”
```

---

# 11. API 拆分

禁止继续把全部接口放在单一 `api.py`。

建议：

```text
apps/api/
  main.py
  routers/
    chat.py
    equipment.py
    literature.py
    rag.py
    knowledge.py
    review.py
    trial.py
    bo.py
    reports.py
    health.py
```

CLI 同样按 command group 拆分。

---

# 12. 统一正式工作流

## 12.1 `complex_process_task`

```text
task_intake
equipment_context_loading
geometry_interpretation
rag_evidence_retrieval
similar_case_retrieval
process_route_planning
trial_need_assessment
trial_strategy_selection
simple_trial_design 或 full_trial_design
knowledge_use_gate
bo_mode_selection
bo_recommendation
quality_plan_generation
execution_plan_generation
report_generation
```

## 12.2 `optical_component_task_workflow`

```text
task_intake
equipment_context_loading
geometry_interpretation
load_domain_pack(crl)
dual_paraboloid_constraint_check
process_route_planning
trial_need_assessment
trial_strategy_selection
toolpath_strategy_selection
measurement_plan_generation
report_generation
```

## 12.3 `microhole_array_task_workflow`

```text
task_intake
equipment_context_loading
load_domain_pack(tgv)
aspect_ratio_assessment
density_and_pitch_check
rag_evidence_retrieval
trial_strategy_selection
monitoring_plan_generation
bo_recommendation
quality_plan_generation
```

---

# 13. 测试要求

## 13.1 架构测试

```text
依赖方向
禁止反向依赖
禁止 apps 直接访问数据库
migration 幂等
旧 CLI golden tests
```

## 13.2 Skill 测试

```text
Skill inventory 完整
Skill 契约校验
Tool/Skill 边界
deprecated Skill 兼容
CRL Workflow
TGV Workflow
```

## 13.3 试切测试

```text
简化试切推荐
完整试切推荐
跳过试切
代表性几何
参数矩阵
停止条件
pass/conditional_pass/fail
正式加工解锁
```

## 13.4 审核测试

```text
背景解释不审核
参数推荐触发一次
任务批准只对当前任务有效
长期批准可复用
设备变化失效
BO 无法绕过 Gate
审核失败 fail closed
```

## 13.5 执行轨迹测试

```text
sequence 单调
真实工具事件
失败事件
最终事件
敏感字段过滤
Normal/Research/Debug
折叠显示
```

## 13.6 性能测试

```text
首事件
首 token
RAG P95
并发 5 会话
8512 chunks 检索
缓存命中
数据库增长
```

## 13.7 故障注入

```text
LLM 超时
RAG 索引损坏
数据库锁
设备配置缺失
BO 数据不足
审核服务异常
试切结果缺失
```

## 13.8 Demo Replay

新增：

```text
scripts/demo_replay.ps1
```

每次提交后自动运行。

---

# 14. 实施顺序

严格按以下顺序：

```text
Phase 0：仓库盘点与基线冻结
Phase 1：包结构和领域边界重构
Phase 2：旧 BO 兼容层
Phase 3：Agent Runtime
Phase 4：Skill Inventory
Phase 5：Skill 重构与 Domain Pack
Phase 6：双模式试切
Phase 7：KnowledgeUseGate
Phase 8：单人按需审核
Phase 9：真实执行轨迹与 NDJSON
Phase 10：PowerShell TUI 折叠显示
Phase 11：性能优化
Phase 12：Demo Mode、Doctor、任务报告
Phase 13：端到端验收
Phase 14：README 和迁移文档
```

任何 Phase 未通过验收，不得跳到后续高风险修改。

---

# 15. Codex 输出物

必须生成：

```text
docs/architecture/current_state.md
docs/architecture/target_state.md
docs/architecture/dependency_graph.md
docs/architecture/migration_map.md
docs/architecture/implementation_status_matrix.md

docs/skills/skill_inventory.md
docs/skills/skill_dependency_graph.md
docs/skills/skill_decision_matrix.md
docs/skills/crl_task_planning_assessment.md

docs/trial/trial_workflow_design.md
docs/review/knowledge_use_gate.md
docs/observability/execution_trace.md
docs/demo/demo_runbook.md

reports/repository_inventory.json
reports/data_inventory.json
reports/baseline_tests.txt
reports/baseline_performance.json
reports/final_performance.json

scripts/demo_replay.ps1
scripts/backup_before_refactor.ps1
scripts/rollback_refactor.ps1
```

---

# 16. P0 / P1 / P2 优先级

## P0：近期展示前必须完成

```text
仓库事实盘点
唯一系统入口
README 状态矩阵
真实 TGV 端到端闭环
确认 BO 是否真实调用
简化试切 MVP
单次聚合审核卡
真实工具执行轨迹
Demo Mode
Doctor
任务报告
离线 fallback
```

## P1：建议展示前完成

```text
Agent Runtime 完整化
Skill inventory
crl_task_planning 评估
Domain Pack
API Router 拆分
性能 waterfall
CRL 辅助演示
```

## P2：展示后完成

```text
完整物理目录迁移
全部旧 Skill 迁移
完整复杂试切数据闭环
更多场景 Domain Pack
多用户审核
真实机床和原位监测
完整 Web GUI
```

---

# 17. 最终完成定义

本任务只有满足以下全部条件才算完成：

```text
1. 仓库有清晰、统一的主架构；
2. BO、RAG、知识、审核、试切、Agent Runtime 边界清晰；
3. 旧 BO 命令仍可使用；
4. Skill 已盘点并给出 keep/refactor/merge/deprecate 结论；
5. crl_task_planning 不再重复通用能力；
6. 复杂任务支持简化和完整试切；
7. 试切结果能控制正式加工是否解锁；
8. 未审核文献参数不能影响 BO；
9. 单任务最多一次聚合审核；
10. 当前任务批准与长期先验批准分离；
11. 用户 500 ms 内能看到真实执行状态；
12. 工具、证据、设备、Skill、审核、BO 和耗时可折叠查看；
13. 不暴露隐藏 chain-of-thought；
14. 有 Demo Mode 和 Doctor；
15. 有端到端 TGV 演示；
16. 有完整任务报告；
17. 有性能 P50/P95；
18. 全部测试通过；
19. 支持回滚；
20. README 与真实实现一致。
```

---
