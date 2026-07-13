# Codex 任务一：平台架构收敛、Agent Runtime、后台任务与 Evolution Foundation

## 0. 任务定位

本任务解决：

```text
新旧包职责不清；
Chat Service 过度集中；
流式与非流式业务路径重复；
长任务缺少持久化执行；
缺少统一版本、评价、晋升与回滚控制面。
```

本任务不修改 BO 数学算法，不实现动态搜索空间和 CAM 参数接口。

建议拆成：

```text
PR 1A：包边界、Chat Runtime 与统一 Workflow
PR 1B：持久化后台任务与执行审计
PR 1C：Evolution Foundation
```

---

## 1. 任务目标

完成后系统应具备：

```text
1. 清晰、可测试的包依赖方向；
2. Chat 只负责消息入口、路由和响应渲染；
3. Router、Session、Workflow、Tool Executor 独立；
4. /chat 与 /chat/stream_ndjson 共用同一 Workflow 事件源；
5. OCR、索引、报告等长任务可以持久化运行；
6. BO 模型、Router、Skill/Prompt 等可注册不可变版本；
7. 改进候选可离线评价、人工批准、激活和回滚。
```

---

# PR 1A：包边界、Chat Runtime 与统一 Workflow

## 2. 包职责

目标职责：

```text
ultrafast_agent
  chat、routing、session、workflow、tool orchestration

ultrafast_domain
  纯领域模型和策略接口

ultrafast_bo
  BO 正式内核，任务二实现

ultrafast_integrations
  LLM、PaddleOCR、CAM、Web 等适配器

ultrafast_shared
  ID、时间、错误、事件、日志、序列化

ultrafast_memory
  兼容入口，不再新增业务逻辑
```

### 2.1 增加架构边界测试

至少增加：

```text
test_architecture_dependencies.py
test_no_reverse_imports.py
test_legacy_package_has_no_new_services.py
```

测试应扫描 Import AST 或使用仓库已有架构测试方式，阻止：

```text
ultrafast_domain import FastAPI/SQLAlchemy/OpenAI/PaddleOCR
ultrafast_bo import chat
ultrafast_integrations import application service
新 application service 放入 ultrafast_memory
```

不要仅通过文档约束，必须自动测试。

---

## 3. 拆分 Chat Orchestrator

建议目标目录，可根据现有包路径做最小迁移：

```text
ultrafast_agent/
  chat/
    message_service.py
    command_handler.py
    response_renderer.py
    stream_renderer.py

  routing/
    route_plan.py
    manual_override.py
    rule_router.py
    llm_router.py
    hybrid_router.py

  session/
    state_service.py
    state_repository.py

  workflow/
    engine.py
    registry.py
    context.py
    events.py
    transitions.py
    workflows/
      task_intake.py
      process_planning.py
      trial_iteration.py
      production_iteration.py
      knowledge_bootstrap.py
      document_ingestion.py

  tools/
    registry.py
    executor.py
    schemas.py
```

若现有路径已经承担这些职责，优先移动/抽取，不要重复创建平行模块。

### 3.1 Chat 层只保留

```text
接收用户消息；
读取/创建会话；
执行手动命令；
调用 Hybrid Router；
调用 Workflow Engine；
将 Workflow Event 渲染为普通或 NDJSON 响应；
保存消息和公开 trace。
```

### 3.2 Chat 层移除

```text
BO 业务规则；
RAG 召回算法；
Knowledge Review 写库逻辑；
OCR Provider 调用；
CAM 字段映射；
试切算法；
正式加工算法；
外部 Provider 具体 SDK 调用。
```

---

## 4. 统一 WorkflowContext

定义正式 Schema，字段可以根据现有数据库调整，但语义必须完整：

```python
class WorkflowContext:
    session_id: str
    workflow_id: str
    workflow_type: str
    stage: str

    task_spec: dict
    collected_slots: dict
    missing_slots: list[str]

    evidence_state: dict
    recommendation_state: dict
    trial_state: dict
    production_state: dict

    pending_actions: list[dict]
    public_trace: list[dict]

    created_at: str
    updated_at: str
```

要求：

```text
1. 所有工作流通过该对象或等价不可变快照传递状态；
2. 不在 Chat Service 内散落多个私有 dict；
3. 状态更新必须经过明确 transition；
4. 每次 transition 产生 Workflow Event；
5. session continuation 优先于普通规则路由。
```

---

## 5. 统一 Workflow Event

至少定义：

```text
workflow_started
stage_changed
slot_extracted
clarification_required
tool_started
tool_succeeded
tool_failed
recommendation_created
recommendation_blocked
review_required
job_created
job_progressed
workflow_completed
workflow_blocked
```

每个事件至少包含：

```text
event_id
sequence
session_id
workflow_id
event_type
public_summary
payload
created_at
```

### 5.1 普通与流式共用

```text
/chat
  收集事件并生成最终 ChatResponse

/chat/stream_ndjson
  按 sequence 流式输出同一批事件
```

不得保留两套业务流程。

### 5.2 兼容字段

保留现有 `selected_skill`，但以 `route_plan.primary_skill` 为源。所有新逻辑使用 `route_plan`。

---

## 6. Tool Registry 与 Tool Executor

Tool Schema 至少包含：

```text
tool_name
tool_version
input_schema
output_schema
side_effect_level
timeout_policy
retry_policy
async_capable
enabled
```

Tool Executor 负责：

```text
输入校验；
超时；
取消；
调用；
错误映射；
公开 trace；
审计记录；
同步工具与后台任务的桥接。
```

禁止工具直接写 Chat 消息。

---

## 7. PR 1A 测试

至少增加：

```text
test_chat_and_stream_share_workflow.py
test_workflow_context_transition.py
test_workflow_event_sequence.py
test_tool_executor_validation.py
test_router_session_continuation.py
test_architecture_dependencies.py
```

兼容测试：

```text
/chat 旧客户端仍可使用；
selected_skill 仍存在；
NDJSON sequence 单调递增；
现有 TUI 命令仍可使用；
MockLLM 离线流程不依赖网络。
```

---

# PR 1B：持久化后台任务与执行审计

## 8. 适用任务

首期支持：

```text
PaddleOCR 文档解析；
页面渲染；
批量文献导入；
RAG 索引；
BO 数据集重建；
模型离线评价；
报告生成。
```

不支持设备控制。

---

## 9. 数据库设计

建议新增或等价实现：

```sql
CREATE TABLE background_job (
    job_id TEXT PRIMARY KEY,
    job_type TEXT NOT NULL,
    status TEXT NOT NULL,
    input_json TEXT,
    output_json TEXT,
    progress REAL DEFAULT 0,
    current_step TEXT,
    attempt INTEGER DEFAULT 0,
    max_attempts INTEGER DEFAULT 3,
    idempotency_key TEXT UNIQUE,
    created_at TEXT,
    started_at TEXT,
    finished_at TEXT,
    heartbeat_at TEXT,
    error_code TEXT,
    error_message TEXT
);
```

```sql
CREATE TABLE background_job_event (
    event_id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL,
    sequence INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    message TEXT,
    progress REAL,
    payload_json TEXT,
    created_at TEXT
);
```

状态至少支持：

```text
queued
running
waiting_review
retrying
succeeded
failed
cancel_requested
cancelled
timed_out
```

---

## 10. Worker

首期允许：

```text
SQLite + 单进程 Worker + DB 轮询 + 文件系统 Artifact Store
```

必须实现：

```text
幂等键；
Worker claim；
heartbeat；
服务重启后的任务恢复；
可恢复错误重试；
不可恢复错误直接失败；
协作式取消；
任务超时；
事件和进度记录。
```

不得因重试造成：

```text
重复导入文档；
重复创建知识候选；
重复写 BO 样本；
重复生成报告。
```

---

## 11. Job API

```http
POST /jobs
GET /jobs/{job_id}
GET /jobs/{job_id}/events
POST /jobs/{job_id}/cancel
POST /jobs/{job_id}/retry
```

若现有 API 已拆分 Router，按当前应用结构接入。

错误必须可序列化，不能把 Python traceback 直接返回给用户。

---

## 12. PR 1B 测试

```text
test_job_idempotency.py
test_job_recovery_after_restart.py
test_job_retry_policy.py
test_job_cancellation.py
test_job_event_sequence.py
test_workflow_job_bridge.py
```

验收：

```text
创建任务后立即返回 job_id；
断开客户端不影响任务；
重启 Worker 后任务可恢复；
重复 idempotency_key 不创建第二个任务；
进度和错误可查询。
```

---

# PR 1C：Evolution Foundation

## 13. 目标

正式实现受控演化底座，不实现自动修改生产代码。

定义“自进化”为：

```text
发现改进机会
→ 创建候选
→ 固定数据集离线评价
→ 与当前版本比较
→ 人工批准
→ 激活新版本
→ 在线监测
→ 必要时回滚
```

---

## 14. 可演化对象

首期支持类型：

```text
bo_model
bo_acquisition_strategy
router_policy
skill_definition
prompt_template
rag_query_strategy
workflow_policy
process_prior_candidate
validated_rule_candidate
```

禁止自动激活：

```text
设备硬边界；
数据库 Schema；
生产代码；
安全规则；
任意新 Tool；
正式 validated_rule。
```

---

## 15. 数据模型

### 15.1 EvolvableArtifactVersion

```text
artifact_version_id
artifact_id
artifact_type
version
status
content_hash
content_json
parent_version_id
created_from_candidate_id
source_data_version
evaluation_run_id
created_at
activated_at
retired_at
```

### 15.2 EvolutionCandidate

```text
candidate_id
candidate_type
target_artifact_id
target_version_id
proposed_content_json
reason
trigger_type
trigger_refs_json
expected_benefit_json
risk_level
status
created_by
created_at
```

`trigger_type` 至少支持：

```text
performance_regression
repeated_failure
user_feedback
new_experiment_data
knowledge_conflict
manual_proposal
llm_proposal
```

### 15.3 EvaluationRun

```text
evaluation_id
candidate_id
baseline_version_id
dataset_version
evaluator_version
metrics_json
failures_json
passed
created_at
```

### 15.4 Activation/rollback

记录：

```text
new_version
previous_version
activation_reason
evaluation_id
activated_at
rollback_condition
rollback_at
rollback_reason
```

---

## 16. 状态机

```text
observed
→ candidate
→ prepared
→ evaluating
→ evaluation_failed / evaluation_passed
→ pending_approval
→ approved
→ active
→ superseded / rolled_back / withdrawn
```

强制约束：

```text
candidate 不能直接 active；
没有 evaluation_passed 不能 pending_approval；
没有明确批准不能 active；
active 时必须记录 previous_version；
回滚不得覆盖历史版本。
```

---

## 17. 服务接口

至少实现：

```python
register_artifact_version(...)
get_active_version(...)
list_versions(...)
create_evolution_candidate(...)
prepare_candidate(...)
run_evaluation(...)
request_promotion(...)
approve_promotion(...)
reject_promotion(...)
activate_version(...)
rollback_version(...)
```

可以提供内部 CLI 或内部管理 API，但不要求 Web UI。

---

## 18. 评价与 Replay

评价运行必须固定：

```text
输入数据集版本；
LLM Provider/模型/temperature；
RAG 索引版本；
BO 数据集版本；
设备配置版本；
代码版本；
随机种子。
```

至少支持对以下对象做可运行的基础评价：

```text
Router Policy：固定会话 replay 路由准确率；
Prompt/Skill：任务完成和结构化输出契约测试；
BO Model：任务二接入后使用离线模型指标。
```

PR 1C 可以先提供 Router/Prompt 的真实评价和 BO 的 evaluator interface；任务二补充 BO evaluator 实现。

---

## 19. PR 1C 测试

```text
test_evolution_state_machine.py
test_candidate_cannot_activate_directly.py
test_evaluation_required_for_promotion.py
test_activation_preserves_previous_version.py
test_rollback_restores_previous_version.py
test_artifact_content_is_immutable.py
```

---

## 20. 任务一最终验收

```text
1. 现有 Chat、NDJSON、TUI 基本兼容；
2. 流式与非流式共享 Workflow；
3. Chat 不直接调用 BO、OCR 或 CAM Provider；
4. 包依赖测试通过；
5. ultrafast_memory 不再承载新业务；
6. 后台任务可恢复、取消、重试和幂等；
7. Router 或 Prompt 可完成版本注册、评价、批准、激活和回滚；
8. 全部旧测试、新测试、Doctor 和离线 Demo 通过。
```

---

## 21. 任务一明确不做

```text
不修改 BO 数学算法；
不实现动态 ParameterPolicy；
不实现 CAM 参数 API；
不自动生成并发布 Skill；
不做 RBAC；
不做设备控制。
```
