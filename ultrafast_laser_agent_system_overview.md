# 超快激光智能体系统总览：整体架构、技术路线与当前功能状态

更新时间：2026-07-08  
适用仓库：`ultrafast-laser-bo-modeling`  
整理依据：当前对话中形成的系统方案、Codex 任务说明、以及用户提供的当前仓库新增功能状态。

---

## 1. 当前系统定位

当前系统不是一个单纯的“LLM 聊天工具”，也不是一个单纯的“贝叶斯优化参数推荐脚本”。

更准确的定位是：

```text
面向超快激光加工任务的智能规划与闭环优化系统
```

系统目标是把以下能力连接成闭环：

```text
用户加工需求
→ 任务解析
→ 设备边界读取
→ 专业知识检索
→ 外部知识冷启动
→ 专家审核
→ 工艺方案生成
→ BO 参数推荐
→ 加工文件与实验结果回流
→ 经验沉淀
→ 下一轮优化
```

其中，大模型负责理解、编排、追问和解释；RAG 负责检索可追溯证据；BO 负责参数优化；专业知识记忆库负责沉淀结构化工艺知识；专家审核机制负责防止知识污染。

---

## 2. 总体技术路线

当前总体技术路线可以概括为：

```text
PowerShell / CLI 启动入口
↓
FastAPI 后端
↓
Chat Orchestrator 智能体入口
↓
Skill Router / Route Plan
↓
Task Intake / CRL Planning / RAG / BO / Knowledge Bootstrap / Review / Equipment Memory
↓
专业知识记忆库 + 结构化数据库 + RAG 索引
↓
BO 推荐与实验反馈闭环
```

一句话版：

```text
用 LLM 做任务理解和工具编排；
用 Skill 固化流程；
用设备记忆提供机器边界；
用 RAG 提供可追溯证据；
用知识冷启动补足初始知识；
用专家审核控制知识准入；
用 BO 做参数优化；
用文件解析和实验反馈形成自学习闭环。
```

---

## 3. 整体架构分层

推荐按 9 层理解当前系统。

```text
L1 启动与配置层
  ultrafast CLI
  PowerShell TUI
  LLM 配置
  DPAPI 加密 API Key
  增量初始化

L2 交互入口层
  /chat
  /chat/stream_ndjson
  PowerShell 聊天循环
  后续 Web UI

L3 会话与工作流层
  chat_session
  chat_message
  chat_session_state
  workflow_progress
  thinking_status
  route_plan

L4 Skill / Agent 编排层
  task_intake
  crl_task_planning
  rag_literature_retrieval
  bo_recommendation
  process_file_ingestion
  experience_memory_update
  bo_dataset_governance
  report_generation
  knowledge_bootstrap
  expert_review

L5 结构化记忆层
  equipment_profile
  process_prior
  literature_evidence
  validated_rule
  experiment_case
  bo_training_sample

L6 RAG 与文献证据层
  rag_document
  rag_index_job
  文献证据
  外部来源
  审核后知识

L7 知识冷启动与专家审核层
  evidence_gap_detector
  web_bootstrap
  knowledge_candidate
  knowledge_review_task
  knowledge_review_action
  review gate

L8 BO 参数优化层
  rule_based_cold_start
  hybrid_rule_bo
  data_driven_bo
  machine_bounds
  objective_mode
  uncertainty

L9 文件自学习与实验反馈层
  raw_artifact
  recipe/log/measurement parser
  experience_candidate
  BO 数据导出
  实验反馈闭环
```

---

## 4. 核心数据流

### 4.1 普通任务规划流程

```text
用户输入模糊加工需求
↓
/chat 接收消息
↓
route_plan 判断任务类型
↓
task_intake 抽取材料、对象、几何、目标
↓
读取 active equipment profile
↓
补齐 machine_bounds
↓
若缺少关键字段，最多 3 轮澄清
↓
生成 task_spec
↓
进入 RAG / BO / report_generation
```

### 4.2 知识不足时的冷启动流程

```text
用户提出新材料 / 新结构 / 新工艺问题
↓
内部 RAG / 知识库检索不足
↓
evidence_gap_detector 标记证据缺口
↓
系统请求用户授权外部知识冷启动
↓
生成检索 query
↓
调用外部检索或 MockWebSearchClient
↓
保存 external_source_artifact
↓
抽取 claim
↓
生成 knowledge_candidate
↓
创建 knowledge_review_task
↓
专家审核
↓
审核通过后进入 RAG / literature_evidence / process_prior
↓
当前聊天 workflow 可继续使用审核后的知识
```

### 4.3 BO 推荐流程

```text
task_spec
+ equipment_profile / machine_bounds
+ process_prior
+ validated_rule
+ historical experiment samples
+ objective_mode
↓
判断样本量：
  <10    rule_based_cold_start
  10-29  hybrid_rule_bo
  >=30   data_driven_bo
↓
生成候选参数
↓
检查设备边界
↓
输出 recommendation + uncertainty + evidence_trace
↓
实验反馈回流
```

---

## 5. 当前已确认实现的功能

以下功能是根据用户当前提供的仓库状态整理，属于当前已实现或已通过测试验证的部分。

### 5.1 一条命令启动

已新增命令：

```powershell
ultrafast
```

作用：

```text
默认启动系统；
复用已有配置；
避免每次重复选择模型或输入 API Key。
```

### 5.2 重新配置模型/API Key

已新增：

```powershell
ultrafast --reconfigure
```

用途：

```text
重新选择模型服务商；
重新选择模型；
重新输入或更新 API Key；
更新本地 LLM 配置。
```

### 5.3 强制初始化

已新增：

```powershell
ultrafast --force-initialize
```

用途：

```text
强制重新扫描示例数据；
强制重新导出 BO CSV；
适合测试、重置和调试。
```

### 5.4 命令帮助

已验证：

```powershell
ultrafast --help
```

可用。

### 5.5 LLM 配置复用

当前方案支持默认复用：

```text
configs/llm.local.json
```

也就是说，后续启动时默认读取本地保存的模型配置，而不是每次重新配置。

### 5.6 API Key 加密保存

当前方案支持使用 Windows DPAPI 加密保存 API Key。

效果：

```text
首次补充 API Key 后；
后续启动可复用加密保存的 key；
不再每次手动输入。
```

注意：

```text
因为旧版本没有保存 DPAPI 加密 key，升级后第一次启动可能仍需要补一次 API Key。
补完后，后续启动不需要重复输入。
```

### 5.7 增量初始化

当前初始化流程已改为增量检查。

行为：

```text
数据库 schema 会检查；
示例数据如果已存在则跳过；
BO CSV 如果已存在则跳过；
避免每次启动重复初始化。
```

### 5.8 测试通过状态

用户提供的当前验证结果：

```text
pytest -q
54 passed
```

这说明当前仓库基础功能、CLI、配置、初始化逻辑以及已有测试覆盖在当前状态下是通过的。

---

## 6. 已设计且已写入任务说明的功能

以下功能已经在 Codex 任务说明中完成了架构设计和实现要求，但是否已经完全进入仓库代码，需要以后续仓库状态或测试结果为准。

### 6.1 聊天闭环

目标设计：

```text
PowerShell TUI
→ POST /chat
→ Chat Orchestrator
→ Session Manager
→ Skill Router
→ LLM Provider Adapter
→ 保存会话与审计记录
→ 返回智能体回复
```

关键设计：

```text
/chat 不应只是普通 LLM proxy；
/chat 应作为智能体统一入口；
支持 session；
支持 route_plan；
支持 audit_trace；
支持 selected_skill / route_plan 返回；
支持后续工具调用。
```

当前状态判断：

```text
已形成完整任务说明；
是否已完整实现需以仓库代码和测试为准；
若只实现了基础 chat，则仍属于 MVP。
```

### 6.2 NDJSON Streaming

设计目标：

```text
POST /chat/stream_ndjson
```

用于 PowerShell/终端流式输出。

事件类型包括：

```text
meta
progress
thinking_status
delta
trace
warning
error
done
```

当前状态判断：

```text
已完成设计；
是否实现真实 LLM streaming 需后续验证；
MVP 可先使用 Mock streaming。
```

### 6.3 Route Planner

设计目标是从简单关键词规则升级为：

```text
规则路由 + LLM 路由 + session state + 手动调试覆盖
```

目标输出不再是简单的：

```json
{
  "selected_skill": "task_intake"
}
```

而是：

```json
{
  "route_type": "agent_workflow",
  "primary_skill": "crl_task_planning",
  "secondary_skills": [
    "rag_literature_retrieval",
    "bo_recommendation"
  ],
  "requires_evidence_gap_check": true,
  "requires_web_bootstrap": false,
  "requires_expert_review": false,
  "blocked_tools": []
}
```

当前状态判断：

```text
已完成设计；
如果仓库仍是规则关键词 router，则属于简要实现，需要后续增强。
```

### 6.4 任务解析进度条

设计目标：

```text
任务解析阶段显示 workflow_progress；
避免用户不知道当前追问什么时候结束。
```

设计字段：

```text
workflow_type
current_stage
progress_percent
status
message
missing_slots
completed_steps
pending_steps
```

典型阶段：

```text
intake_started
basic_info_extracted
missing_slots_identified
clarification_round_1
clarification_round_2
clarification_round_3
task_spec_confirmed
ready_for_planning
ready_for_bo
workflow_completed
```

当前状态判断：

```text
已写入任务说明；
是否已实现需检查 /chat 返回和 TUI 展示。
```

### 6.5 可公开思考状态

设计目标：

```text
显示公开的任务状态、工具调用轨迹和推理摘要；
不展示模型隐藏 chain-of-thought。
```

允许展示：

```text
当前阶段；
已完成动作；
缺失字段；
下一步动作；
工具调用状态；
公开 reasoning summary；
audit trace。
```

禁止展示：

```text
hidden chain-of-thought；
raw_thoughts；
system prompt；
API Key；
未审核候选知识的确定性结论。
```

当前状态判断：

```text
已完成任务说明；
实现时应使用 thinking_status / public_reasoning_summary / audit_trace 等字段。
```

---

## 7. 知识库与 RAG 相关设计状态

### 7.1 专业知识记忆库

系统设计中，知识库不是简单 RAG，而是多层结构：

```text
文献证据库
结构化工艺先验库
内部实验案例库
已验证规则库
设备参数库
BO 状态库
RAG 文档库
```

关键原则：

```text
RAG 是读取知识库的一种方式；
RAG 不是知识库本体；
结构化设备参数、实验样本、BO 数据不应主要依赖 RAG 读取。
```

当前状态判断：

```text
已形成完整设计；
实际实现程度需要检查数据库表、API 和测试。
```

### 7.2 知识冷启动与外部证据吸收

设计模块：

```text
knowledge_bootstrap/
  evidence_gap_detector.py
  query_generator.py
  web_search_client.py
  source_fetcher.py
  claim_extractor.py
  candidate_builder.py
  precheck.py
  rag_ingestion.py
  service.py
```

核心流程：

```text
内部证据不足
↓
生成 query
↓
外部检索
↓
保存 source
↓
抽取 claim
↓
生成 candidate
↓
专家审核
↓
审核通过后入库
```

当前状态判断：

```text
已设计；
MVP 可先用 MockWebSearchClient；
真实联网检索、真实论文解析、真实向量库接入需要后续完善。
```

### 7.3 专家审核工作流

设计目标：

```text
所有新知识必须先进入 knowledge_candidate；
专家审核决定知识进入哪个层级。
```

审核动作：

```text
reject
needs_more_evidence
accept_to_rag
accept_as_literature_evidence
accept_as_process_prior
promote_to_validated_rule
approve_for_bo_training
withdraw
```

关键边界：

```text
进入 RAG 不等于可用于 BO；
进入 process_prior 才能作为 BO 搜索边界候选；
进入 validated_rule 才能参与推荐过滤；
进入 bo_training_sample 必须来自完整实验记录。
```

当前状态判断：

```text
已完成任务说明；
MVP 可先实现 accept_to_rag / reject / needs_more_evidence；
process_prior、validated_rule、BO training approval 需要更严格后续实现。
```

---

## 8. 设备记忆层设计状态

### 8.1 设计目标

初始化时配置设备参数，后续任务自动读取，避免每次加工任务重复询问固定设备边界。

目标流程：

```text
初始化配置设备参数
↓
写入 equipment_profile
↓
设置 active equipment profile
↓
task_intake 自动读取
↓
bo_recommendation 自动使用 machine_bounds
```

### 8.2 设计数据库

包括：

```text
equipment_profile
laser_source_config
optical_setup_config
motion_system_config
process_capability_config
equipment_config_revision
```

### 8.3 设计 API

```text
POST /equipment/profiles
GET /equipment/active
GET /equipment/profiles
POST /equipment/profiles/{id}/activate
PATCH /equipment/profiles/{id}
GET /equipment/active/machine-bounds
```

### 8.4 当前状态判断

```text
已写入任务说明；
是否已经实现需要检查仓库；
如果尚未实现，则优先级较高，因为它直接影响 task_intake 和 BO 推荐体验。
```

---

## 9. BO 推荐系统设计状态

### 9.1 已有 BO 仓库基础

当前项目基础来自超快激光 BO 推荐仓库。系统设计中，BO 支持按样本数量分级：

```text
<10    rule_based_cold_start
10-29  hybrid_rule_bo
>=30   data_driven_bo
```

### 9.2 BO 输入应包括

```text
task_spec
material
process_type
objective_mode
machine_bounds
literature_priors
validated_rules
historical_samples
constraints
```

### 9.3 BO 输出应包括

```text
model_status
candidate parameters
predicted metrics
uncertainty
evidence_trace
risks
next_experiment_plan
```

### 9.4 当前状态判断

```text
BO 基础推荐能力来自原仓库；
与 chat、equipment_profile、knowledge_review、RAG 的深度集成属于后续增强；
越界检查、equipment revision 记录、BO training sample 准入仍需重点完善。
```

---

## 10. 文件自学习与实验反馈设计状态

### 10.1 设计流程

```text
监听加工软件文件
↓
原始文件归档
↓
解析 recipe / log / measurement / notes
↓
单位标准化
↓
写入结构化数据库
↓
生成 experience_candidate
↓
专家审核
↓
进入规则库或 BO 数据集
```

### 10.2 设计数据表

```text
raw_artifact
process_task
process_recipe
process_run
machine_timeseries
measurement_record
experience_candidate
validated_rule
bo_training_sample
```

### 10.3 当前状态判断

```text
已完成数据结构和任务说明设计；
当前仓库中可能已有示例数据扫描、BO CSV 导出等基础能力；
自动文件监听、复杂 parser、经验候选审核、BO training sample 自动治理仍需要后续完善。
```

---

## 11. 当前功能成熟度分级

### 11.1 已确认实现

```text
ultrafast CLI；
ultrafast --help；
ultrafast --reconfigure；
ultrafast --force-initialize；
configs/llm.local.json 复用；
DPAPI 加密 API Key；
增量初始化；
schema 检查；
示例数据和 BO CSV 已存在则跳过；
pytest -q：54 passed。
```

### 11.2 已设计，可能已有 MVP

```text
/chat 聊天接口；
LLM provider adapter；
MockLLMClient；
PowerShell TUI 聊天循环；
规则版 skill_router；
chat_session / chat_message；
audit_trace；
基础 FastAPI 后端。
```

这些功能需要用当前仓库代码和 API 实测确认成熟度。

### 11.3 已设计，但大概率仍需完善

```text
NDJSON streaming；
route_plan；
LLM router；
session_state 驱动 workflow；
任务进度条；
thinking_status；
知识冷启动接入聊天；
专家审核回流当前 workflow；
设备记忆层；
真实 RAG index；
真实 web search；
真实 BO 与 chat 深度联动；
文件自学习闭环；
BO training sample 治理。
```

### 11.4 明确不应自动执行的能力

```text
LLM 直接生成确定加工参数；
LLM 自动生成 validated_rule；
未审核知识直接进入正式 RAG；
未审核知识影响 BO；
网页摘要直接变成工艺先验；
无 active equipment profile 时输出 BO 确定参数；
显示模型隐藏 chain-of-thought。
```

---

## 12. 当前主要技术债

### 12.1 任务说明较完整，但实现边界需要持续校验

当前已经形成多个较完整的 Codex 任务说明，但任务说明不等于代码实现。后续每次新增功能后，建议维护一张功能状态表：

```text
设计完成
MVP 实现
测试覆盖
接入 /chat
接入 TUI
接入数据库
接入 README
生产可用
```

### 12.2 RAG 与结构化知识边界必须继续保持清晰

不要把所有知识都塞进向量库。  
设备边界、BO 样本、测量结果、规则状态、审核状态都应以结构化数据库为主。

### 12.3 Chat Orchestrator 是后续集成核心

如果 `/chat` 只是普通 LLM proxy，后续所有能力都会变成旁路功能。  
后续重点应保证：

```text
/chat → route_plan → session_state → skill/tool → audit_trace
```

### 12.4 专家审核必须防止形式化

专家审核不能只是“通过/拒绝”。  
特别是进入 process_prior、validated_rule、bo_training_sample 时，必须强制填写适用条件、来源、限制和置信度。

### 12.5 设备记忆层应尽快落地

设备参数是每次工艺推荐的基础边界。  
如果没有 active equipment profile，系统会反复追问设备参数，也无法可靠执行 BO 推荐。

---

## 13. 建议下一步开发优先级

### Priority 1：确认当前已实现功能状态

建议执行：

```powershell
ultrafast --help
ultrafast
ultrafast --reconfigure
ultrafast --force-initialize
pytest -q
```

并补充检查：

```text
是否存在 /chat；
是否存在 chat_session 表；
是否存在 skill_router；
是否存在 llm adapter；
是否存在 TUI 聊天入口；
是否存在 equipment API；
是否存在 knowledge review API。
```

### Priority 2：落地设备记忆层

优先原因：

```text
直接减少任务解析重复提问；
直接约束 BO；
实现难度低于知识冷启动；
收益高。
```

优先实现：

```text
/equipment/profiles
/equipment/active
/equipment/active/machine-bounds
PowerShell 设备配置向导
task_intake 自动读取 active profile
```

### Priority 3：重构 route_plan + session_state

优先原因：

```text
后续知识冷启动、专家审核、进度条、BO 都依赖 workflow state。
```

### Priority 4：接入任务进度条和 thinking_status

优先原因：

```text
改善调试体验；
减少用户等待焦虑；
便于观察 agent 当前卡在哪一步。
```

### Priority 5：知识冷启动 + 专家审核 MVP

优先实现：

```text
MockWebSearchClient
knowledge_candidate
review_task
accept_to_rag
reject
needs_more_evidence
rag_document index stub
```

### Priority 6：BO 与设备边界深度集成

重点：

```text
BO 输入记录 equipment_profile_id；
候选参数越界检查；
无 active profile 时阻塞；
task-level override；
BO sample 质量治理。
```

---

## 14. 推荐 README 顶层说明

可以在仓库 README 中加入以下概括：

```text
Ultrafast Laser Agent is a task-oriented assistant for ultrafast laser process planning and Bayesian optimization. It combines LLM-based task intake, structured equipment memory, evidence-governed RAG, expert-reviewed knowledge bootstrap, and BO-driven parameter recommendation.

The system is designed to avoid unsupported process recommendations. LLM outputs are treated as orchestration and explanation; process parameters must be grounded in equipment bounds, reviewed evidence, validated rules, or BO outputs.
```

中文说明：

```text
超快激光智能体是一个面向超快激光加工任务规划与贝叶斯优化的智能系统。系统结合大模型任务解析、结构化设备记忆、可审核 RAG、外部知识冷启动、专家审核和 BO 参数推荐。

系统不允许大模型直接编造加工参数。所有参数建议必须来自设备边界、审核通过的证据、验证规则、历史实验数据或 BO 输出。
```

---

## 15. 当前状态一句话总结

当前系统已经从“BO 推荐仓库”演进为“超快激光加工智能体平台”的雏形。

已确认落地的是：

```text
更稳定的启动、配置复用、DPAPI API Key 加密、增量初始化和 ultrafast CLI。
```

已经完成系统级设计但需要继续实现和集成的是：

```text
/chat 智能体工作流、route_plan、session_state、设备记忆、任务进度、公开思考状态、知识冷启动、专家审核、RAG 入库、BO 深度联动和文件自学习闭环。
```

后续关键方向不是继续堆功能，而是把这些模块统一接入：

```text
/chat → workflow state → skill/tool → memory/RAG/BO → audit trace
```

这样系统才会从“多个工具集合”变成真正的“超快激光加工智能体”。
