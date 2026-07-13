# 全局上下文与 Codex 执行规则

## 0. 仓库与当前状态

目标仓库：

```text
https://github.com/milumilelu/ultrafast-laser-bo-modeling
```

当前仓库已经包含：

```text
1. 根目录离线 BO 与交互式推荐代码；
2. ultrafast_laser_memory 子项目；
3. FastAPI、Chat、NDJSON、混合 Router、PowerShell TUI；
4. 知识冷启动、RAG、审核、KnowledgeUseGate；
5. Agent 侧 BO Adapter；
6. 试切与正式加工工作流基础；
7. Doctor、Demo、测试和性能报告；
8. 新包与 ultrafast_memory 兼容层并存。
```

当前核心问题不是“从零开始”，而是：

```text
新旧实现并存；
职责边界不清；
Chat Service 膨胀；
BO 正确性和治理不够严格；
搜索空间表达能力不足；
外部 CAM 缺少稳定参数契约；
缺少统一演化控制面。
```

Codex 必须在现有代码基础上增量重构，不得另起一个平行项目。

---

## 1. 系统定位

系统是：

```text
面向超快激光加工的任务分析、知识检索、工艺参数推荐、
试切/正式加工迭代、工艺数据治理和 CAM 参数交付智能体。
```

Agent 负责：

```text
任务理解；
任务分解；
工作流规划；
缺失信息追问；
工具选择与调用；
结果聚合；
状态管理；
公开执行轨迹；
异常和阻塞解释。
```

Agent 不得自行承担具体参数推荐算法。参数必须通过显式工具产生：

```text
bo_parameter_recommendation
rag_parameter_recommendation
llm_parameter_candidate
```

参数来源治理顺序：

```text
1. 数据充分且适用的 BO 推荐；
2. 已审核 process_prior / validated_rule；
3. RAG 规则与文献证据形成的参数候选；
4. 内部数据和 RAG 均不足时的 LLM 试切候选。
```

约束：

```text
RAG 原始文献参数不能直接进入 BO 边界；
未审核候选不能进入正式推荐；
LLM 参数只能是待验证候选，默认只能用于试切；
CAM 自动设置只能消费状态允许、边界已校验的参数。
```

---

## 2. 本轮明确不做

Codex 不得实现或暗示已经实现：

```text
1. 基础认证、RBAC、多租户；
2. 真实设备状态读取；
3. Shadow Mode；
4. PLC、激光器、振镜、运动平台控制；
5. 启动、暂停、停止设备；
6. 商业 CAD/CAM 替代；
7. 通用几何建模和刀路生成；
8. 多 OCR 引擎；
9. OCR 模型训练；
10. 图像语义准确率验证；
11. 对外开放图像语义能力；
12. 自动发布 validated_rule；
13. Agent 自主修改生产代码或数据库结构；
14. Agent 自动放宽设备硬边界；
15. 无评价、无批准的模型自动替换。
```

---

## 3. 核心架构原则

### 3.1 分层

目标分层：

```text
Interface Layer
  Chat API / NDJSON / TUI / CAM Parameter API / Job API

Agent Runtime & Application Layer
  Router / Session / Workflow / Tool Executor

Domain Layer
  Task / Recipe / Trial / Recommendation / Knowledge / Evolution

BO Optimization Layer
  Dataset / Readiness / Search Space / Model / Acquisition

Knowledge & Document Layer
  RAG / Evidence / Review / PaddleOCR / Vision Stub

Evolution Control Plane
  Candidate / Evaluation / Promotion / Rollback

Integration Layer
  LLM / PaddleOCR / CAM Adapter / Web Provider

Infrastructure Layer
  DB / File Store / Vector Index / Job Worker / Audit

Compatibility Layer
  Legacy ultrafast_memory adapters
```

### 3.2 依赖方向

允许：

```text
interface → application → domain
application → tool interface
integration → tool interface + external SDK
compatibility → application
```

禁止：

```text
domain → FastAPI
domain → SQLAlchemy ORM
domain → OpenAI/PaddleOCR SDK
BO → Chat
RAG → Chat
CAM Adapter → BO 业务逻辑
compatibility → 新业务实现
```

### 3.3 唯一业务实现

每项核心业务只能存在一个正式 application service。兼容入口只能做字段映射和转发，不得保留第二套业务判断。

### 3.4 可追溯

关键对象必须拥有稳定 ID、版本、来源和父子链：

```text
workflow_id
recommendation_id
iteration_number
parent_recommendation_id
bo_run_id
model_version
dataset_version
search_space_version
objective_version
constraint_version
code_version
```

---

## 4. Agent 公开过程信息

系统应展示：

```text
当前工作流阶段；
已完成步骤；
缺失字段；
正在调用的 Skill/Tool；
工具调用输入摘要；
工具调用结果摘要；
参数来源；
阻塞原因；
下一步动作。
```

系统不得展示：

```text
隐藏 chain-of-thought；
系统提示词；
模型内部 token 推理；
未经处理的内部草稿；
API Key 或秘密配置。
```

使用公开 `execution_trace`、`audit_trace` 和结构化 Workflow Event，而不是伪造内部思维链。

---

## 5. Codex 开始工作前必须执行

Codex 必须先：

```text
1. 阅读根目录 README、pyproject、requirements 和 CI；
2. 阅读 ultrafast_laser_memory README 和 pyproject；
3. 列出 src、tests、scripts、API router 和数据库模块；
4. 定位所有正式 CLI 和 FastAPI 入口；
5. 定位 Chat Service、Router、Workflow、BO Adapter、Knowledge Gate；
6. 定位根目录旧 BO 与 ultrafast_bo 新 BO 的所有调用者；
7. 运行现有完整测试；
8. 运行 doctor 和离线 demo/replay；
9. 记录基线测试数量、警告、耗时和失败；
10. 创建本任务对应的基线报告。
```

若现有测试无法运行，Codex 必须记录真实错误，不得删测试或降低断言来制造通过。

---

## 6. 工作纪律

### 6.1 不做超大提交

每个主任务必须按指定 PR 划分。每个 PR 应：

```text
只解决一个清晰主题；
可独立测试；
提供迁移/兼容策略；
能够回滚；
避免同时大规模重命名和修改业务行为。
```

### 6.2 先建立测试，再迁移

对每项重构：

```text
先固定当前行为或明确新契约；
增加回归测试；
迁移实现；
删除重复代码；
再次运行全部测试。
```

不得长期保留两套“临时”实现。

### 6.3 不虚构外部协议

对于首个厂商 CAM Adapter：

```text
必须基于厂商文档、样例文件或用户提供的字段表；
不得自行猜测厂商字段、单位、枚举或通信方式；
若资料缺失，完成通用 ConfigDrivenCamAdapter 和输入模板，
将真实厂商 Adapter 标记为明确阻塞，不得声称已经兼容。
```

### 6.4 兼容性

尽量保持：

```text
现有 CLI；
现有 /chat；
现有 /chat/stream_ndjson；
现有 TUI；
现有 Demo；
现有 Knowledge API；
根目录旧脚本的基础使用方式。
```

若必须变更，需提供：

```text
兼容 Adapter；
迁移说明；
弃用警告；
回滚方式；
契约测试。
```

---

## 7. 数据治理规则

### 7.1 原始数据不可覆盖

原始工艺、运行、检测、OCR、文献和用户反馈必须保留原始记录或原始 Artifact 哈希。

### 7.2 训练准入

任何反馈都必须先成为候选：

```text
BOTrainingSampleCandidate
→ Eligibility
→ ApprovedBOTrainingSample
```

不得收到反馈后直接 `valid_flag=true`。

### 7.3 知识等级

继续遵守：

```text
Level 0：未验证候选
Level 1：RAG 背景
Level 2：文献证据
Level 3：Process Prior
Level 4：Validated Rule
Level 5：BO Training Sample
```

只有 Level 3 及以上、且通过 KnowledgeUseGate 的结构化参数，才能影响 BO 搜索边界。

### 7.4 OCR 和视觉

```text
OCR 结果是解析候选，不是正式参数；
视觉语义结果是 experimental_unvalidated；
两者都不能直接进入 BO、规则或 CAM。
```

---

## 8. 统一错误与阻塞语义

至少支持以下状态或等价结构：

```text
ready
blocked
insufficient_data
insufficient_evidence
no_optimizable_parameters
infeasible_search_space
pending_review
experimental_disabled
provider_unavailable
validation_failed
```

阻塞时必须返回：

```text
机器可读 code；
用户可读 message；
blocking_reasons；
conflicting_sources；
suggested_next_actions。
```

不得静默忽略冲突约束或用默认值掩盖缺失数据。

---

## 9. 最低测试要求

每个 PR 都必须运行：

```text
1. 新增模块单元测试；
2. 相关 API/CLI 集成测试；
3. 根目录完整 pytest；
4. ultrafast_laser_memory 子项目完整 pytest；
5. Doctor；
6. 离线 Demo/Replay；
7. 架构依赖测试；
8. 基础性能回归。
```

若仓库实际命令不同，以仓库当前正式命令为准，并在报告中记录。

---

## 10. 每个 PR 的交付物

```text
代码；
数据库 migration；
Schema；
测试；
README/架构说明；
兼容说明；
迁移说明；
回滚说明；
测试报告；
已知限制。
```

Codex 最终回复必须列出：

```text
修改文件；
新增文件；
删除/弃用文件；
运行的命令；
测试结果；
未完成或阻塞事项；
下一 PR 的依赖。
```
