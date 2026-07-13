# Codex 任务说明：实现知识冷启动与外部证据吸收层 + 专家审核工作流

## 0. 背景

当前超快激光智能体已经具备以下基础能力：

```text
1. PowerShell TUI 启动器；
2. LLM 配置；
3. FastAPI 后端；
4. 聊天入口 /chat；
5. skill router；
6. 加工文件解析与知识记忆库雏形；
7. BO 数据导出；
8. RAG / BO / skill 后续集成接口。
```

现在需要新增两个核心模块：

```text
A. 知识冷启动与外部证据吸收层 knowledge_bootstrap
B. 专家审核工作流 knowledge_review
```

目标是解决：

```text
1. 内部 RAG 初期知识不足；
2. 需要调用大模型自身知识生成检索假设；
3. 需要调用联网检索或外部文献检索补全证据；
4. 外部知识不能直接污染 RAG；
5. 所有新知识必须经过专家审核后才能进入正式知识库；
6. 进入 RAG 不等于可用于 BO；
7. 进入 BO 必须是结构化、完整、可追溯、已审核的数据。
```

本任务的核心原则：

```text
LLM 只能生成候选知识。
Web search 只能提供外部证据。
专家审核决定知识能进入哪一层。
RAG 只索引经过治理的知识。
BO 只使用通过质量校验和专家审核的数据。
```

---

## 1. 总体目标

实现如下闭环：

```text
用户问题 / task_spec
↓
查询内部知识库与 RAG
↓
检测 evidence gap
↓
若内部证据不足，触发 knowledge_bootstrap
↓
LLM 生成专业检索 query
↓
调用 web search 或 mock search
↓
保存 external_source_artifact
↓
抽取 knowledge_candidate
↓
自动预审 auto_precheck
↓
创建 knowledge_review_task
↓
专家审核
↓
按审核结果写入：
  ├─ rag_document
  ├─ literature_evidence
  ├─ process_prior
  ├─ validated_rule
  └─ bo_training_sample
↓
更新 RAG 索引
↓
聊天或报告中可追溯引用
```

---

## 2. 明确不做

MVP 阶段不做：

```text
1. 不做真实论文 PDF 全文解析；
2. 不做复杂 DOI metadata 补全；
3. 不做双专家审核；
4. 不做完整权限系统；
5. 不做 Web 审核 UI；
6. 不做自动规则晋升；
7. 不做外部网页全文爬虫；
8. 不做真实 BO 自动重训练；
9. 不做自动把 LLM prior 写入 RAG；
10. 不做无审核自动进入 process_prior 或 validated_rule。
```

MVP 允许：

```text
1. 使用 MockWebSearchClient；
2. 使用 OpenAI / provider web search adapter stub；
3. 使用简单 CLI / TUI 审核；
4. 使用本地 Chroma 或 stub vector index；
5. 先实现 accept_to_rag / reject / needs_more_evidence 三个审核动作；
6. 预留 process_prior / validated_rule / bo_training_sample 审核动作。
```

---

## 3. 新增目录结构

在现有项目中新增或补充：

```text
src/
  ultrafast_memory/
    knowledge_bootstrap/
      __init__.py
      schemas.py
      evidence_gap_detector.py
      query_generator.py
      web_search_client.py
      source_registry.py
      claim_extractor.py
      candidate_builder.py
      auto_precheck.py
      rag_ingestion.py
      service.py

    knowledge_review/
      __init__.py
      schemas.py
      review_queue.py
      review_actions.py
      review_policy.py
      conflict_detector.py
      service.py

    rag/
      index_stub.py
      document_builder.py

tests/
  test_evidence_gap_detector.py
  test_query_generator.py
  test_knowledge_bootstrap.py
  test_candidate_builder.py
  test_auto_precheck.py
  test_knowledge_review.py
  test_rag_ingestion.py
  test_knowledge_api.py
```

如果已有同名模块，应合并，不要重复创建冲突目录。

---

## 4. 知识等级定义

实现以下知识等级常量：

```text
LEVEL_0_UNVERIFIED_CANDIDATE
LEVEL_1_RAG_BACKGROUND
LEVEL_2_LITERATURE_EVIDENCE
LEVEL_3_PROCESS_PRIOR
LEVEL_4_VALIDATED_RULE
LEVEL_5_BO_TRAINING_SAMPLE
```

含义：

```text
Level 0:
未验证候选知识。默认状态。不能用于正式回答依据、BO 或规则。

Level 1:
RAG 背景知识。可用于解释和背景说明，不可用于参数推荐。

Level 2:
文献证据。可用于方案依据、风险说明、文献追溯。

Level 3:
工艺先验。可作为 BO 搜索边界或冷启动约束，但必须专家审核。

Level 4:
内部验证规则。可参与推荐过滤、风险判断、反馈优化。

Level 5:
BO 训练样本。可进入 BO 数据集，要求最高。
```

代码位置建议：

```text
src/ultrafast_memory/knowledge_review/review_policy.py
```

---

## 5. 数据库新增表

如果项目使用 SQLAlchemy，请同步增加 ORM models 和初始化逻辑。  
如果当前使用原生 SQL，也请提供 schema 初始化脚本。

### 5.1 `external_source_artifact`

保存联网检索或外部来源。

```sql
CREATE TABLE external_source_artifact (
    source_id TEXT PRIMARY KEY,
    source_type TEXT,
    title TEXT,
    url TEXT,
    doi TEXT,
    authors TEXT,
    published_at TEXT,
    accessed_at TEXT,
    provider TEXT,
    raw_snippet TEXT,
    local_snapshot_path TEXT,
    content_hash TEXT,
    credibility_score REAL,
    status TEXT
);
```

字段说明：

```text
source_type:
web_page / paper / patent / standard / manual / llm_prior / internal_file

provider:
openai_web_search / mock_web_search / manual / imported_file

status:
fetched / parsed / rejected / accepted / needs_review
```

---

### 5.2 `knowledge_candidate`

保存候选知识。

```sql
CREATE TABLE knowledge_candidate (
    candidate_id TEXT PRIMARY KEY,
    source_id TEXT,
    claim TEXT NOT NULL,
    material TEXT,
    process_type TEXT,
    component_type TEXT,
    parameter_json TEXT,
    condition_json TEXT,
    usable_for_json TEXT,
    not_usable_for_json TEXT,
    evidence_type TEXT,
    confidence REAL,
    status TEXT,
    review_status TEXT,
    risk_level TEXT,
    suggested_action TEXT,
    conflict_flag INTEGER,
    duplicate_of TEXT,
    source_quality_score REAL,
    created_at TEXT,
    reviewed_by TEXT,
    review_comment TEXT
);
```

`evidence_type` 可选：

```text
llm_prior
web_evidence
paper_evidence
internal_case
validated_rule
```

`status` 可选：

```text
candidate
pending_review
accepted
rejected
needs_more_evidence
withdrawn
```

---

### 5.3 `literature_evidence`

保存审核通过的文献证据。

```sql
CREATE TABLE literature_evidence (
    evidence_id TEXT PRIMARY KEY,
    source_id TEXT,
    candidate_id TEXT,
    claim TEXT NOT NULL,
    material TEXT,
    process_type TEXT,
    component_type TEXT,
    metric_name TEXT,
    parameter_range_json TEXT,
    condition_json TEXT,
    page_or_section TEXT,
    confidence REAL,
    created_at TEXT
);
```

---

### 5.4 `process_prior`

保存可计算工艺先验。

```sql
CREATE TABLE process_prior (
    prior_id TEXT PRIMARY KEY,
    candidate_id TEXT,
    material TEXT,
    process_type TEXT,
    component_type TEXT,
    parameter_name TEXT,
    lower_bound REAL,
    upper_bound REAL,
    unit TEXT,
    condition_json TEXT,
    source_ids_json TEXT,
    confidence REAL,
    status TEXT,
    created_at TEXT
);
```

注意：

```text
process_prior 不能由系统自动写入。
必须由专家审核动作 accept_as_process_prior 触发。
MVP 可先实现 schema 和 stub，不强制实现完整写入。
```

---

### 5.5 `rag_document`

保存进入 RAG 的文档单元。

```sql
CREATE TABLE rag_document (
    rag_doc_id TEXT PRIMARY KEY,
    source_id TEXT,
    candidate_id TEXT,
    title TEXT,
    content TEXT NOT NULL,
    metadata_json TEXT,
    indexed INTEGER,
    index_name TEXT,
    created_at TEXT
);
```

---

### 5.6 `rag_index_job`

保存索引任务。

```sql
CREATE TABLE rag_index_job (
    job_id TEXT PRIMARY KEY,
    rag_doc_id TEXT,
    index_name TEXT,
    status TEXT,
    started_at TEXT,
    finished_at TEXT,
    error_message TEXT
);
```

---

### 5.7 `knowledge_review_task`

保存审核任务。

```sql
CREATE TABLE knowledge_review_task (
    review_id TEXT PRIMARY KEY,
    candidate_id TEXT NOT NULL,
    review_status TEXT NOT NULL,
    priority TEXT,
    risk_level TEXT,
    assigned_to TEXT,
    created_at TEXT,
    updated_at TEXT,
    due_at TEXT,
    auto_suggestion TEXT,
    review_comment TEXT
);
```

`review_status` 可选：

```text
pending_review
reviewing
rejected
needs_more_evidence
accepted_to_rag
accepted_as_literature_evidence
accepted_as_process_prior
promoted_to_validated_rule
approved_for_bo_training
withdrawn
```

---

### 5.8 `knowledge_review_action`

审核动作审计表，必须 append-only。

```sql
CREATE TABLE knowledge_review_action (
    action_id TEXT PRIMARY KEY,
    review_id TEXT NOT NULL,
    candidate_id TEXT NOT NULL,
    reviewer_id TEXT NOT NULL,
    action TEXT NOT NULL,
    target_level TEXT,
    comment TEXT,
    created_at TEXT,
    payload_json TEXT
);
```

---

### 5.9 `knowledge_conflict`

记录冲突知识。

```sql
CREATE TABLE knowledge_conflict (
    conflict_id TEXT PRIMARY KEY,
    candidate_id TEXT NOT NULL,
    existing_knowledge_id TEXT,
    conflict_type TEXT,
    conflict_summary TEXT,
    status TEXT,
    created_at TEXT,
    resolved_at TEXT,
    resolution_comment TEXT
);
```

`conflict_type` 可选：

```text
parameter_range_conflict
material_scope_conflict
process_type_conflict
metric_definition_conflict
source_contradiction
duplicate
```

---

## 6. Knowledge Bootstrap Schemas

实现：

```text
src/ultrafast_memory/knowledge_bootstrap/schemas.py
```

### 6.1 `EvidenceGapRequest`

```python
from pydantic import BaseModel
from typing import Any

class EvidenceGapRequest(BaseModel):
    task_spec: dict[str, Any] = {}
    question: str
    internal_hits: list[dict[str, Any]] = []
```

### 6.2 `EvidenceGapResponse`

```python
class EvidenceGapResponse(BaseModel):
    has_sufficient_internal_evidence: bool
    evidence_score: float
    missing_evidence: list[str]
    recommended_action: str
    reason: str
```

`recommended_action` 可选：

```text
answer_from_internal
ask_user_clarification
web_bootstrap
manual_review_required
```

---

### 6.3 `BootstrapWebRequest`

```python
class BootstrapWebRequest(BaseModel):
    task_spec: dict[str, Any] = {}
    query_intent: str = "find_literature_prior"
    question: str | None = None
    max_sources: int = 5
    review_required: bool = True
```

### 6.4 `BootstrapWebResponse`

```python
class BootstrapWebResponse(BaseModel):
    sources: list[dict[str, Any]]
    knowledge_candidates: list[dict[str, Any]]
    review_tasks: list[dict[str, Any]]
    auto_indexed: list[dict[str, Any]] = []
    requires_review: list[dict[str, Any]]
```

MVP 默认：

```text
auto_indexed = []
所有 candidate 进入 review queue
```

---

## 7. Evidence Gap Detector

实现：

```text
src/ultrafast_memory/knowledge_bootstrap/evidence_gap_detector.py
```

函数：

```python
def detect_evidence_gap(
    question: str,
    task_spec: dict,
    internal_hits: list[dict] | None = None,
) -> dict:
    ...
```

MVP 规则：

```text
1. internal_hits 为空 → evidence_score = 0.0；
2. internal_hits 少于 2 条 → evidence_score <= 0.4；
3. 命中结果 material 不匹配 → 降分；
4. 命中结果 process_type 不匹配 → 降分；
5. 命中结果无 source_id → 降分；
6. evidence_score < 0.6 → recommended_action = web_bootstrap；
7. 0.6 <= evidence_score < 0.8 → recommended_action = ask_user_clarification；
8. >= 0.8 → recommended_action = answer_from_internal。
```

必须返回 missing_evidence，例如：

```text
diamond_CRL_literature
machine_specific_parameters
internal_experiment_cases
process_parameter_ranges
damage_mechanism_evidence
```

---

## 8. Query Generator

实现：

```text
src/ultrafast_memory/knowledge_bootstrap/query_generator.py
```

函数：

```python
def generate_search_queries(task_spec: dict, question: str | None, query_intent: str) -> list[str]:
    ...
```

MVP 不调用 LLM，先用模板生成 query。

对于金刚石 CRL，生成：

```text
diamond compound refractive lens femtosecond laser micromachining
single crystal diamond X-ray refractive lens laser fabrication
femtosecond laser diamond graphitization surface roughness
diamond CRL polishing surface roughness X-ray optics
diamond laser micromachining surface roughness Ra
```

对于一般超快激光加工：

```text
{material} ultrafast laser {process_type} surface roughness
{material} femtosecond laser micromachining parameters
{material} laser ablation damage mechanism
{material} ultrafast laser process optimization
```

后续可替换为 LLM query generator，但 MVP 先用规则模板。

---

## 9. Web Search Client

实现：

```text
src/ultrafast_memory/knowledge_bootstrap/web_search_client.py
```

### 9.1 Base Client

```python
class BaseWebSearchClient:
    def search(self, queries: list[str], max_sources: int = 5) -> list[dict]:
        raise NotImplementedError
```

返回统一格式：

```python
{
    "title": "...",
    "url": "...",
    "snippet": "...",
    "source_type": "web_page",
    "provider": "mock_web_search",
    "published_at": None
}
```

### 9.2 MockWebSearchClient

MVP 必须实现，用于测试和离线运行。

对包含 `diamond` 和 `CRL` 的 query，返回 mock sources：

```python
[
    {
        "title": "Mock: Femtosecond laser micromachining of diamond X-ray lenses",
        "url": "https://example.org/mock-diamond-crl",
        "snippet": "Femtosecond laser micromachining has been reported for single-crystal diamond X-ray refractive lens fabrication. This supports feasibility but not direct parameter transfer.",
        "source_type": "paper",
        "provider": "mock_web_search"
    }
]
```

### 9.3 Provider Adapter Stub

预留：

```python
class OpenAIWebSearchClient(BaseWebSearchClient):
    def search(self, queries: list[str], max_sources: int = 5) -> list[dict]:
        raise NotImplementedError("Real OpenAI web search is not implemented in MVP.")
```

不得假装真实联网已经实现。

---

## 10. Source Registry

实现：

```text
src/ultrafast_memory/knowledge_bootstrap/source_registry.py
```

函数：

```python
def register_external_source(source: dict) -> dict:
    ...
```

要求：

```text
1. 生成 source_id；
2. 计算 content_hash，至少对 title + url + snippet 哈希；
3. 去重：相同 url 或 content_hash 不重复写入；
4. 写入 external_source_artifact；
5. 返回 source record。
```

---

## 11. Claim Extractor

实现：

```text
src/ultrafast_memory/knowledge_bootstrap/claim_extractor.py
```

MVP 使用规则抽取，不调用真实 LLM。

函数：

```python
def extract_claims_from_source(source: dict, task_spec: dict) -> list[dict]:
    ...
```

对于 mock source 生成：

```python
{
    "claim": "飞秒激光微加工已有用于单晶金刚石 X-ray refractive lens / CRL 制造的报道。",
    "material": "diamond",
    "process_type": "femtosecond_laser_micromachining",
    "component_type": "X-ray_CRL",
    "usable_for": ["feasibility_assessment", "literature_background"],
    "not_usable_for": ["direct_parameter_recommendation", "BO_training"],
    "evidence_type": "web_evidence",
    "confidence": 0.65
}
```

如果 source 中没有足够内容，生成低置信度 candidate，并标记：

```text
needs_more_evidence
```

---

## 12. Candidate Builder

实现：

```text
src/ultrafast_memory/knowledge_bootstrap/candidate_builder.py
```

函数：

```python
def build_knowledge_candidate(source_record: dict, extracted_claim: dict) -> dict:
    ...
```

写入 `knowledge_candidate`。

默认：

```text
status = candidate
review_status = pending_review
risk_level = auto_precheck 结果
suggested_action = auto_precheck 结果
```

---

## 13. Auto Precheck

实现：

```text
src/ultrafast_memory/knowledge_bootstrap/auto_precheck.py
```

函数：

```python
def run_auto_precheck(candidate: dict) -> dict:
    ...
```

检查：

```text
1. source_id 是否存在；
2. claim 是否为空；
3. material 是否存在；
4. process_type 是否存在；
5. 是否含具体参数；
6. usable_for / not_usable_for 是否存在；
7. 是否重复；
8. 是否与已有知识冲突；
9. 风险等级；
10. 建议审核动作。
```

风险等级规则：

```text
Low:
背景知识，不含具体参数，不影响 BO。

Medium:
材料特定机制、损伤趋势、工艺建议。

High:
具体参数范围、参数推荐、会影响 BO 搜索边界。

Critical:
设备安全、自动控制、危险操作。
```

建议动作：

```text
accept_to_rag
needs_more_evidence
reject
accept_as_literature_evidence
accept_as_process_prior
```

MVP 中，含具体参数的 candidate 一律：

```text
risk_level = high
suggested_action = needs_more_evidence
```

---

## 14. Knowledge Bootstrap Service

实现：

```text
src/ultrafast_memory/knowledge_bootstrap/service.py
```

### 14.1 `check_evidence_gap`

```python
def check_evidence_gap(request: EvidenceGapRequest) -> EvidenceGapResponse:
    ...
```

### 14.2 `bootstrap_from_web`

```python
def bootstrap_from_web(request: BootstrapWebRequest) -> BootstrapWebResponse:
    ...
```

流程：

```text
1. generate_search_queries；
2. web_search_client.search；
3. register_external_source；
4. extract_claims_from_source；
5. build_knowledge_candidate；
6. run_auto_precheck；
7. create review task；
8. 返回 sources / candidates / review_tasks。
```

MVP 所有 candidate 都必须创建 review task。  
不得自动写入正式 RAG。

---

## 15. RAG Document Builder

实现：

```text
src/ultrafast_memory/rag/document_builder.py
```

函数：

```python
def build_rag_document_from_candidate(candidate: dict, source: dict) -> dict:
    ...
```

生成内容格式：

```text
来源：{title}
URL：{url}
证据类型：{evidence_type}
材料：{material}
工艺：{process_type}
对象：{component_type}
结论：{claim}
适用范围：{usable_for}
不可用于：{not_usable_for}
置信度：{confidence}
审核状态：accepted_to_rag
```

写入 `rag_document`。

---

## 16. RAG Index Stub

实现或扩展：

```text
src/ultrafast_memory/rag/index_stub.py
```

函数：

```python
def index_rag_document(rag_doc_id: str, index_name: str = "default") -> dict:
    ...
```

MVP 可以只更新数据库：

```text
rag_document.indexed = 1
rag_document.index_name = index_name
创建 rag_index_job，status = success
```

后续再接 Chroma / FAISS / OpenAI vector store。

---

## 17. Knowledge Review Schemas

实现：

```text
src/ultrafast_memory/knowledge_review/schemas.py
```

### 17.1 `ReviewActionRequest`

```python
from pydantic import BaseModel
from typing import Any

class ReviewActionRequest(BaseModel):
    action: str
    reviewer_id: str
    comment: str = ""
    target_level: str | None = None
    payload: dict[str, Any] = {}
```

允许 action：

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

MVP 必须实现：

```text
reject
needs_more_evidence
accept_to_rag
accept_as_literature_evidence
```

其余可以 stub，但必须返回清晰错误：

```text
not_implemented_in_mvp
```

---

## 18. Review Queue

实现：

```text
src/ultrafast_memory/knowledge_review/review_queue.py
```

函数：

```python
def create_review_task(candidate_id: str, risk_level: str, suggested_action: str) -> dict:
    ...

def list_review_tasks(status: str = "pending_review") -> list[dict]:
    ...

def get_review_task(review_id: str) -> dict:
    ...
```

`get_review_task` 返回：

```text
review task
candidate
source
auto_precheck summary
conflicts
history
```

---

## 19. Review Actions

实现：

```text
src/ultrafast_memory/knowledge_review/review_actions.py
```

函数：

```python
def apply_review_action(review_id: str, request: ReviewActionRequest) -> dict:
    ...
```

### 19.1 reject

效果：

```text
knowledge_candidate.status = rejected
knowledge_candidate.review_status = rejected
knowledge_review_task.review_status = rejected
写入 knowledge_review_action
```

### 19.2 needs_more_evidence

效果：

```text
knowledge_candidate.status = needs_more_evidence
knowledge_candidate.review_status = needs_more_evidence
knowledge_review_task.review_status = needs_more_evidence
写入 knowledge_review_action
```

### 19.3 accept_to_rag

效果：

```text
knowledge_candidate.status = accepted
knowledge_candidate.review_status = accepted_to_rag
knowledge_review_task.review_status = accepted_to_rag
写入 knowledge_review_action
生成 rag_document
index_rag_document
```

重要：

```text
accept_to_rag 不得写入 process_prior；
accept_to_rag 不得写入 validated_rule；
accept_to_rag 不得写入 bo_training_sample。
```

### 19.4 accept_as_literature_evidence

效果：

```text
写入 literature_evidence
生成 rag_document
index_rag_document
更新 candidate / review task 状态
写入 knowledge_review_action
```

### 19.5 accept_as_process_prior

MVP 可返回：

```json
{
  "status": "not_implemented_in_mvp",
  "message": "accept_as_process_prior requires structured parameter validation and expert confirmation."
}
```

但必须保留接口。

### 19.6 promote_to_validated_rule

MVP 可返回 `not_implemented_in_mvp`。

### 19.7 approve_for_bo_training

MVP 可返回 `not_implemented_in_mvp`。

---

## 20. Conflict Detector

实现：

```text
src/ultrafast_memory/knowledge_review/conflict_detector.py
```

MVP 简单规则：

```text
1. 相同 claim hash → duplicate；
2. 相同 material + process_type + parameter_name，但范围差异超过 50% → parameter_range_conflict；
3. candidate not_usable_for 中包含 BO_training，但目标动作是 approve_for_bo_training → conflict。
```

函数：

```python
def detect_conflicts(candidate: dict) -> list[dict]:
    ...
```

如果有冲突，写入 `knowledge_conflict`，并设置：

```text
candidate.conflict_flag = 1
```

---

## 21. FastAPI 接口

在现有 FastAPI 中新增以下接口。

### 21.1 检测证据缺口

```http
POST /knowledge/evidence-gap
```

请求：

```json
{
  "task_spec": {
    "material": "diamond",
    "component_type": "CRL",
    "process_type": "femtosecond_laser_micromachining"
  },
  "question": "金刚石 CRL 如何进行超快激光加工？",
  "internal_hits": []
}
```

返回：

```json
{
  "has_sufficient_internal_evidence": false,
  "evidence_score": 0.0,
  "missing_evidence": [
    "diamond_CRL_literature",
    "internal_experiment_cases"
  ],
  "recommended_action": "web_bootstrap",
  "reason": "内部知识库无足够匹配证据。"
}
```

---

### 21.2 联网冷启动

```http
POST /knowledge/bootstrap-web
```

请求：

```json
{
  "task_spec": {
    "material": "diamond",
    "component_type": "CRL",
    "process_type": "femtosecond_laser_micromachining"
  },
  "query_intent": "find_literature_prior",
  "question": "金刚石 CRL 如何进行超快激光加工？",
  "max_sources": 5,
  "review_required": true
}
```

返回：

```json
{
  "sources": [],
  "knowledge_candidates": [],
  "review_tasks": [],
  "auto_indexed": [],
  "requires_review": []
}
```

MVP 使用 MockWebSearchClient，不要求真实联网。

---

### 21.3 查看候选知识

```http
GET /knowledge/candidates?status=pending_review
```

---

### 21.4 查看审核任务列表

```http
GET /knowledge/review/tasks?status=pending_review
```

---

### 21.5 查看审核任务详情

```http
GET /knowledge/review/tasks/{review_id}
```

返回：

```json
{
  "review_id": "rev_xxx",
  "candidate": {},
  "source": {},
  "conflicts": [],
  "history": []
}
```

---

### 21.6 执行审核动作

```http
POST /knowledge/review/tasks/{review_id}/action
```

请求：

```json
{
  "action": "accept_to_rag",
  "reviewer_id": "expert_001",
  "comment": "可作为 RAG 背景知识，但不能用于 BO 参数推荐。",
  "target_level": "LEVEL_1_RAG_BACKGROUND"
}
```

---

### 21.7 查看 RAG 文档

```http
GET /rag/documents
```

---

### 21.8 手动触发 RAG 索引

```http
POST /rag/index
```

请求：

```json
{
  "candidate_ids": ["kc_001"],
  "index_name": "ultrafast_laser_literature"
}
```

---

## 22. PowerShell TUI / CLI 审核入口

如果已有 PowerShell TUI，请新增菜单：

```text
[10] 知识冷启动
[11] 专家审核队列
```

### 22.1 知识冷启动菜单

功能：

```text
1. 输入问题；
2. 输入 material / process_type / component_type；
3. 调用 /knowledge/evidence-gap；
4. 若证据不足，询问是否执行 bootstrap-web；
5. 显示生成的候选知识和 review task。
```

### 22.2 专家审核菜单

功能：

```text
1. 查看待审核任务；
2. 查看任务详情；
3. 接收入 RAG；
4. 接收为文献证据；
5. 拒绝；
6. 标记需要更多证据；
7. 查看审核历史；
8. 返回主菜单。
```

MVP 不要求漂亮界面，必须可操作。

---

## 23. 聊天集成

在 `/chat` 的 agent workflow 中预留：

```text
如果 route_plan.requires_web_bootstrap = true：
  1. 调用 evidence-gap；
  2. 如果系统配置允许自动 bootstrap，则调用 bootstrap-web；
  3. 否则询问用户是否允许联网/外部证据检索；
  4. 回答时说明：新知识已进入候选队列，等待专家审核。
```

MVP 可先只在回答中提示，不自动调用。

必须禁止：

```text
聊天中不得声称“已加入正式知识库”。
只能说“已生成候选知识，等待专家审核”。
```

---

## 24. 安全与治理要求

必须满足：

```text
1. LLM prior 不得直接进入 RAG；
2. Web search 结果不得直接进入正式知识库；
3. accept_to_rag 不得进入 BO；
4. process_prior 必须专家审核；
5. validated_rule 必须有 supporting cases；
6. BO training sample 必须通过 bo eligibility；
7. 所有审核动作必须 append-only；
8. 不允许物理删除已审核记录；
9. withdraw 只能标记撤回；
10. 所有知识必须保留 source_id / candidate_id / review_id。
```

---

## 25. README 更新

新增章节：

```text
知识冷启动与专家审核
```

必须说明：

```text
1. 为什么需要 knowledge_bootstrap；
2. 为什么不能直接把 LLM 知识写入 RAG；
3. 如何检测 evidence gap；
4. 如何执行 mock web bootstrap；
5. 如何查看候选知识；
6. 如何专家审核；
7. accept_to_rag 与 accept_as_literature_evidence 的区别；
8. 进入 RAG 不等于可用于 BO；
9. 当前 MVP 不支持真实联网；
10. 后续如何接入真实 web search。
```

---

## 26. 测试要求

必须新增 pytest。

### 26.1 `test_evidence_gap_detector.py`

测试：

```text
internal_hits 为空 → web_bootstrap；
internal_hits 数量不足 → evidence_score 低；
material 不匹配 → evidence_score 降低；
高质量 internal_hits → answer_from_internal。
```

### 26.2 `test_query_generator.py`

测试：

```text
diamond + CRL → 生成 diamond compound refractive lens query；
普通 material/process_type → 生成通用 ultrafast laser query。
```

### 26.3 `test_knowledge_bootstrap.py`

测试：

```text
bootstrap_from_web 使用 MockWebSearchClient；
能生成 external_source_artifact；
能生成 knowledge_candidate；
能生成 review_task；
不会自动生成 rag_document。
```

### 26.4 `test_auto_precheck.py`

测试：

```text
无 source_id → risk 提高；
无 material → needs_more_evidence；
含具体参数 → high risk；
背景 claim → suggested_action accept_to_rag。
```

### 26.5 `test_knowledge_review.py`

测试：

```text
reject 更新 candidate 和 review_task；
needs_more_evidence 更新状态；
accept_to_rag 生成 rag_document；
accept_to_rag 不生成 process_prior；
accept_as_literature_evidence 生成 literature_evidence 和 rag_document；
review_action append-only。
```

### 26.6 `test_rag_ingestion.py`

测试：

```text
build_rag_document_from_candidate 内容包含 source、claim、usable_for、not_usable_for；
index_rag_document 更新 indexed=1；
rag_index_job status=success。
```

### 26.7 `test_knowledge_api.py`

使用 FastAPI TestClient 测试：

```text
POST /knowledge/evidence-gap；
POST /knowledge/bootstrap-web；
GET /knowledge/review/tasks；
GET /knowledge/review/tasks/{review_id}；
POST /knowledge/review/tasks/{review_id}/action；
GET /rag/documents。
```

所有测试不得依赖真实网络。

---

## 27. 验收标准

完成后必须满足：

```bash
pytest -q
```

全部通过。

### 27.1 API 验收流程

启动后端：

```bash
python -m uvicorn ultrafast_memory.app.api:app --reload --host 127.0.0.1 --port 8000
```

检测证据缺口：

```bash
curl -X POST http://127.0.0.1:8000/knowledge/evidence-gap \
  -H "Content-Type: application/json" \
  -d '{"task_spec":{"material":"diamond","component_type":"CRL","process_type":"femtosecond_laser_micromachining"},"question":"金刚石CRL如何进行超快激光加工？","internal_hits":[]}'
```

预期：

```text
recommended_action = web_bootstrap
```

执行 cold bootstrap：

```bash
curl -X POST http://127.0.0.1:8000/knowledge/bootstrap-web \
  -H "Content-Type: application/json" \
  -d '{"task_spec":{"material":"diamond","component_type":"CRL","process_type":"femtosecond_laser_micromachining"},"query_intent":"find_literature_prior","question":"金刚石CRL如何进行超快激光加工？","max_sources":3,"review_required":true}'
```

预期：

```text
生成 sources；
生成 knowledge_candidates；
生成 review_tasks；
不自动生成正式 rag_document。
```

查看审核队列：

```bash
curl http://127.0.0.1:8000/knowledge/review/tasks?status=pending_review
```

接收入 RAG：

```bash
curl -X POST http://127.0.0.1:8000/knowledge/review/tasks/<review_id>/action \
  -H "Content-Type: application/json" \
  -d '{"action":"accept_to_rag","reviewer_id":"expert_001","comment":"作为背景知识接收入RAG，禁止用于BO参数推荐。","target_level":"LEVEL_1_RAG_BACKGROUND"}'
```

预期：

```text
candidate 状态更新；
review task 状态更新；
review_action 写入；
rag_document 生成；
rag_document.indexed = 1；
不生成 process_prior；
不生成 bo_training_sample。
```

---

## 28. 实现顺序

请 Codex 按以下顺序实现：

```text
Phase 1：数据库表 / ORM models / schema 初始化
Phase 2：knowledge_bootstrap schemas
Phase 3：evidence_gap_detector
Phase 4：query_generator
Phase 5：MockWebSearchClient
Phase 6：source_registry
Phase 7：claim_extractor
Phase 8：candidate_builder + auto_precheck
Phase 9：review_queue
Phase 10：review_actions
Phase 11：rag document builder + index_stub
Phase 12：knowledge_bootstrap service
Phase 13：FastAPI endpoints
Phase 14：PowerShell TUI / CLI 菜单
Phase 15：pytest
Phase 16：README
```

---

## 29. 关键质量要求

```text
1. 所有外部知识必须先进入 knowledge_candidate；
2. 所有 candidate 必须生成 review_task；
3. accept_to_rag 只能进入 RAG，不得影响 BO；
4. LLM prior 不得自动入库；
5. MockWebSearchClient 必须可离线测试；
6. 所有审核动作必须写入 knowledge_review_action；
7. source_id / candidate_id / review_id 必须全链路可追溯；
8. 不得依赖真实网络；
9. 不得在测试中调用真实 API；
10. 不得假装真实 web search 已实现。
```

---

## 30. 后续扩展预留

本任务完成后，后续可继续做：

```text
1. 接入真实 OpenAI web_search；
2. 接入学术搜索 API；
3. 接入 DOI metadata；
4. 接入 PDF 全文解析；
5. 接入 Chroma / FAISS / OpenAI vector store；
6. 实现 process_prior 专家审核；
7. 实现 validated_rule 晋升；
8. 实现 BO training sample 专家审批；
9. 实现冲突可视化；
10. 实现 Web 审核 UI；
11. 实现双专家审核；
12. 实现知识撤回与版本管理。
```

---

## 31. 一句话总结

本任务要实现的是：

```text
内部 RAG 不足时，系统可以通过外部证据冷启动；
但任何新知识都必须先成为候选知识；
候选知识必须经过专家审核；
审核通过后才能进入 RAG、文献证据库、工艺先验库、规则库或 BO 数据集。
```

不要把它做成“联网搜索后自动更新 RAG”。  
正确目标是：

```text
web / LLM → candidate → expert review → governed memory → RAG / rules / BO
```


---

## 18. 新增要求：接入聊天窗与当前 Agent Workflow

当前知识冷启动与专家审核模块不能只作为独立 API 或 TUI 功能存在，必须接入 `/chat` 智能体工作流。

本节目标：

```text
用户在聊天中提出新材料 / 新结构 / 新工艺问题
↓
/chat 通过 route_plan 判断需要证据检索
↓
检测内部 RAG / 知识库是否足够
↓
若不足，向用户请求联网冷启动授权
↓
用户确认后调用 knowledge bootstrap
↓
生成 knowledge_candidate 和 review_task
↓
写入 chat session_state
↓
专家审核通过后更新 RAG
↓
当前聊天 workflow 能继续使用新入库知识
```

关键要求：

```text
知识冷启动必须成为聊天智能体 workflow 的内生步骤，而不是独立旁路功能。
```

---

## 19. Route Plan 扩展

当前 `/chat` 不应只返回 `selected_skill`。  
需要升级为 `route_plan`。

### 19.1 route_plan schema

新增或扩展：

```json
{
  "route_type": "agent_workflow",
  "primary_skill": "rag_literature_retrieval",
  "secondary_skills": [
    "knowledge_bootstrap",
    "expert_review"
  ],
  "intent": "find_external_evidence_for_new_process",
  "workflow_stage": "evidence_check",
  "confidence": 0.82,
  "reason": "内部知识库可能缺少 diamond CRL femtosecond laser micromachining 相关证据。",
  "requires_internal_rag": true,
  "requires_evidence_gap_check": true,
  "requires_web_bootstrap": true,
  "requires_user_permission": true,
  "requires_expert_review": true,
  "allowed_tools": [
    "evidence_gap_detector",
    "knowledge_bootstrap"
  ],
  "blocked_tools": [
    {
      "tool": "bo_recommendation",
      "reason": "尚未完成文献证据和工艺先验审核，不能进入参数推荐。"
    }
  ]
}
```

### 19.2 触发条件

当用户消息包含以下特征时，route_plan 应设置：

```text
requires_evidence_gap_check = true
```

触发场景：

```text
1. 用户询问新材料、新工艺、新结构；
2. 用户要求查文献；
3. 用户要求基于文献给工艺方案；
4. 用户要求对 RAG 中可能没有的对象进行解释；
5. 用户询问金刚石 CRL、X-ray optics、特殊陶瓷、复合材料等领域任务；
6. 用户要求推荐参数但内部样本和工艺先验可能不足；
7. selected_skill 为 rag_literature_retrieval 或 bo_recommendation，且证据不足。
```

---

## 20. /chat 中的 Evidence Gap 检查

`/chat` 或 `/chat/stream_ndjson` 内部需要新增以下逻辑。

### 20.1 执行流程

```text
1. 接收用户 message；
2. 读取 session_state；
3. 生成 route_plan；
4. 若 route_plan.requires_evidence_gap_check=true：
   4.1 从 message 和 session_state 构造 task_spec；
   4.2 调用 detect_evidence_gap(task_spec, question)；
   4.3 将 evidence_gap 写入 session_state；
   4.4 若证据足够，继续正常 RAG / 回答；
   4.5 若证据不足，进入 knowledge_bootstrap_decision。
```

### 20.2 证据不足时的默认回复

如果内部知识库不足，且用户尚未授权联网冷启动，聊天回复必须类似：

```text
当前内部知识库缺少足够证据，无法可靠支持该问题的结论。

我可以启动外部知识冷启动检索：
1. 生成专业检索 query；
2. 调用外部检索；
3. 抽取候选知识；
4. 写入专家审核队列；
5. 审核通过后再进入正式 RAG。

是否允许我现在执行外部知识冷启动？
```

禁止回复：

```text
我已经查到并加入知识库。
```

除非确实已完成 candidate 生成和 review_task 创建。

---

## 21. 用户授权机制

知识冷启动默认需要用户授权。

### 21.1 配置项

在 `configs/default.yaml` 中新增：

```yaml
knowledge_bootstrap:
  auto_web_bootstrap: false
  require_user_permission: true
  max_sources_per_chat: 5
  create_review_tasks: true
  allow_llm_prior_candidates: true
  allow_mock_web_search: true
```

默认：

```text
auto_web_bootstrap = false
require_user_permission = true
```

### 21.2 授权识别

当 session_state 中存在 `pending_bootstrap_permission=true` 时，若用户输入包含：

```text
可以
同意
允许
开始检索
执行冷启动
联网检索
yes
ok
```

则 `/chat` 可以调用 `bootstrap_external_knowledge`。

若用户输入包含：

```text
不需要
不要
取消
no
```

则取消本轮冷启动，并更新 session_state。

### 21.3 手动命令

为调试加入显式命令：

```text
/bootstrap on
/bootstrap off
/bootstrap run
/bootstrap status
```

命令含义：

```text
/bootstrap run：
基于当前 session_state 中的 task_spec 立即执行知识冷启动。

/bootstrap status：
查看当前 evidence_gap、candidate、review_task 状态。
```

---

## 22. Chat Session State 扩展

需要新增或扩展 `chat_session_state` 表。

### 22.1 新增表或字段

如果已有 `chat_session_state`，增加字段。  
如果没有，则创建：

```sql
CREATE TABLE chat_session_state (
    state_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    active_workflow TEXT,
    active_skill TEXT,
    workflow_stage TEXT,
    collected_slots_json TEXT,
    pending_questions_json TEXT,
    allowed_next_skills_json TEXT,
    evidence_gap_json TEXT,
    active_knowledge_bootstrap_json TEXT,
    pending_review_task_ids_json TEXT,
    pending_bootstrap_permission INTEGER,
    updated_at TEXT
);
```

### 22.2 active_knowledge_bootstrap_json 示例

```json
{
  "bootstrap_id": "kb_001",
  "task_spec": {
    "material": "diamond",
    "process_type": "femtosecond_laser_micromachining",
    "component_type": "CRL"
  },
  "queries": [
    "diamond compound refractive lens femtosecond laser micromachining"
  ],
  "candidate_ids": [
    "kc_001",
    "kc_002"
  ],
  "review_task_ids": [
    "rev_001",
    "rev_002"
  ],
  "status": "pending_expert_review"
}
```

### 22.3 pending_review_task_ids_json

用于支持用户在聊天中追问：

```text
刚才检索出来的知识审核了吗？
```

系统必须能根据当前 session 找到对应 review tasks。

---

## 23. /chat 调用 knowledge bootstrap

### 23.1 用户确认后执行

当用户授权后，`/chat` 应调用：

```python
bootstrap_external_knowledge(
    task_spec=session_state.task_spec,
    query_intent="find_literature_prior",
    max_sources=config.knowledge_bootstrap.max_sources_per_chat
)
```

### 23.2 /chat 返回结构扩展

`ChatResponse` 增加字段：

```python
knowledge_bootstrap: dict | None = None
route_plan: dict | None = None
evidence_gap: dict | None = None
```

返回示例：

```json
{
  "session_id": "sess_001",
  "assistant_message": "已完成外部知识冷启动检索，生成 3 条候选知识和 3 个专家审核任务。审核通过后才会进入正式 RAG。",
  "selected_skill": "rag_literature_retrieval",
  "route_plan": {
    "primary_skill": "rag_literature_retrieval",
    "requires_expert_review": true
  },
  "evidence_gap": {
    "has_sufficient_internal_evidence": false,
    "missing_evidence": [
      "diamond_CRL_literature"
    ]
  },
  "knowledge_bootstrap": {
    "executed": true,
    "created_candidates": 3,
    "created_review_tasks": 3,
    "candidate_ids": [
      "kc_001",
      "kc_002",
      "kc_003"
    ],
    "review_task_ids": [
      "rev_001",
      "rev_002",
      "rev_003"
    ],
    "next_action": "expert_review_required"
  },
  "audit_trace": []
}
```

### 23.3 audit_trace 要求

`audit_trace` 必须记录：

```json
[
  {
    "step": "route_plan",
    "status": "success",
    "primary_skill": "rag_literature_retrieval"
  },
  {
    "step": "evidence_gap_check",
    "status": "insufficient",
    "missing_evidence": ["diamond_CRL_literature"]
  },
  {
    "step": "knowledge_bootstrap",
    "status": "success",
    "created_candidates": 3
  },
  {
    "step": "expert_review_gate",
    "status": "pending_review"
  }
]
```

---

## 24. 审核完成后回流当前聊天 workflow

专家审核通过后，当前聊天会话必须能感知更新。

### 24.1 审核动作回写 session_state

当执行：

```text
accept_to_rag
accept_as_literature_evidence
accept_as_process_prior
```

时，系统应检查该 `candidate_id` 是否属于某个 `chat_session_state.active_knowledge_bootstrap_json`。

如果属于，则更新：

```json
{
  "status": "partially_reviewed",
  "accepted_candidate_ids": ["kc_001"],
  "accepted_rag_doc_ids": ["rag_001"]
}
```

若所有 review_task 已完成，则：

```text
status = reviewed
```

### 24.2 聊天中查询审核状态

新增或复用 `/chat` 命令：

```text
/bootstrap status
```

返回：

```text
当前会话共有 3 条候选知识：
- 1 条已接收入 RAG；
- 1 条需要更多证据；
- 1 条仍待专家审核。

你可以在审核完成后输入“继续生成方案”，系统将重新查询 RAG。
```

### 24.3 审核通过后继续 workflow

如果用户输入：

```text
继续生成方案
```

且当前 session_state 中存在：

```text
active_knowledge_bootstrap.status = reviewed
```

则 `/chat` 应：

```text
1. 重新查询内部 RAG；
2. 使用新入库 rag_document；
3. 生成方案；
4. 明确说明使用了刚审核通过的知识。
```

如果还有未审核项，则回复：

```text
仍有候选知识待审核。当前只能基于已审核知识生成初步方案，不能使用未审核候选。
```

---

## 25. Chat + Knowledge Bootstrap API 补充

### 25.1 获取当前会话知识冷启动状态

新增接口：

```http
GET /chat/sessions/{session_id}/knowledge-bootstrap
```

返回：

```json
{
  "session_id": "sess_001",
  "evidence_gap": {},
  "active_knowledge_bootstrap": {},
  "pending_review_tasks": [],
  "accepted_rag_documents": []
}
```

### 25.2 手动触发当前会话知识冷启动

新增接口：

```http
POST /chat/sessions/{session_id}/knowledge-bootstrap/run
```

请求：

```json
{
  "query_intent": "find_literature_prior",
  "max_sources": 5
}
```

返回：

```json
{
  "executed": true,
  "candidate_ids": [],
  "review_task_ids": [],
  "next_action": "expert_review_required"
}
```

此接口必须复用 `bootstrap_external_knowledge`，不要重复实现逻辑。

---

## 26. PowerShell TUI 集成补充

在聊天模式下支持以下命令：

```text
/bootstrap status
/bootstrap run
/review tasks
/review open <review_id>
```

### 26.1 /bootstrap run

PowerShell 发送普通 `/chat` 消息即可。  
后端识别命令并执行冷启动。

### 26.2 /review tasks

调用：

```http
GET /knowledge/review/tasks?status=pending_review
```

并在 TUI 中显示：

```text
review_id | risk_level | suggested_action | claim 摘要
```

### 26.3 /review open <review_id>

调用：

```http
GET /knowledge/review/tasks/{review_id}
```

显示候选详情。

MVP 暂不要求在聊天 TUI 中完成审核动作；审核动作仍可走专家审核菜单或 API。  
但可选实现：

```text
/review accept_to_rag <review_id>
/review reject <review_id>
/review more_evidence <review_id>
```

---

## 27. 修改原有测试要求

在已有测试基础上增加以下测试。

### 27.1 test_chat_knowledge_bootstrap_integration.py

必须测试：

```text
1. /chat 遇到新 diamond CRL 问题时触发 evidence_gap_check；
2. 证据不足时，/chat 返回授权提示，不直接执行 bootstrap；
3. 用户回复“可以”后，/chat 调用 bootstrap_external_knowledge；
4. /chat 返回 created_candidates 和 review_task_ids；
5. session_state 写入 active_knowledge_bootstrap_json；
6. /bootstrap status 能返回待审核任务；
7. accept_to_rag 后 session_state 能看到部分审核完成；
8. 未审核 candidate 不会被用于最终回答。
```

### 27.2 test_route_plan_knowledge_bootstrap.py

测试：

```text
1. rag_literature_retrieval 路由包含 requires_evidence_gap_check；
2. bo_recommendation 在证据不足时 blocked_tools 包含 bo_recommendation；
3. 手动命令 /bootstrap run 触发 knowledge_bootstrap route。
```

### 27.3 test_review_session_link.py

测试：

```text
1. candidate_id 能关联到 session_state；
2. review action 后 session_state 更新；
3. reviewed 状态可被 /chat 读取。
```

---

## 28. 验收标准补充

完成后必须满足以下流程。

### 28.1 聊天触发证据缺口

请求：

```bash
curl -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message":"我想做金刚石CRL的飞秒激光加工，帮我查文献并制定方案",
    "use_skills":true
  }'
```

预期：

```text
1. 返回 route_plan；
2. route_plan.requires_evidence_gap_check=true；
3. evidence_gap.has_sufficient_internal_evidence=false；
4. assistant_message 请求用户授权知识冷启动；
5. 不创建 validated_rule；
6. 不创建 process_prior；
7. 不创建 bo_training_sample。
```

### 28.2 用户授权后执行冷启动

继续：

```bash
curl -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "session_id":"<上一步 session_id>",
    "message":"可以，执行外部知识冷启动",
    "use_skills":true
  }'
```

预期：

```text
1. 调用 bootstrap_external_knowledge；
2. 创建 external_source_artifact；
3. 创建 knowledge_candidate；
4. 创建 knowledge_review_task；
5. 返回 knowledge_bootstrap.created_candidates > 0；
6. session_state.active_knowledge_bootstrap_json 非空；
7. assistant_message 明确说明等待专家审核。
```

### 28.3 审核后回流

执行：

```bash
curl -X POST http://127.0.0.1:8000/knowledge/review/tasks/<review_id>/action \
  -H "Content-Type: application/json" \
  -d '{
    "action":"accept_to_rag",
    "reviewer_id":"expert_001",
    "comment":"可作为背景知识，不能用于直接参数推荐。",
    "target_level":"rag_background",
    "payload":{}
  }'
```

然后：

```bash
curl http://127.0.0.1:8000/chat/sessions/<session_id>/knowledge-bootstrap
```

预期：

```text
1. 能看到 accepted_rag_documents；
2. pending_review_tasks 数量减少或状态更新；
3. /chat 后续能识别已有审核通过知识。
```

---

## 29. 关键边界补充

必须写入 README 和 system prompt：

```text
1. 聊天中触发外部检索，不代表知识已进入正式库；
2. 知识冷启动生成的是 candidate；
3. candidate 必须经专家审核；
4. accept_to_rag 只能用于解释和背景，不代表可用于 BO；
5. process_prior 才能作为 BO 搜索边界候选；
6. validated_rule 才能参与推荐过滤；
7. bo_training_sample 必须来自完整实验记录；
8. /chat 不得使用未审核 candidate 生成确定性工艺建议。
```

---

## 30. 更新后的总体任务完成定义

本任务完成后，系统应具备：

```text
用户在聊天中提出内部知识不足的新工艺问题
↓
系统自动检测 evidence gap
↓
系统请求用户授权
↓
用户授权后执行外部知识冷启动
↓
候选知识进入专家审核队列
↓
专家审核后写入 RAG
↓
当前聊天会话能感知审核结果
↓
用户可继续当前 workflow
```

如果只实现 `/knowledge/bootstrap-web` 和 `/knowledge/review/tasks`，但没有接入 `/chat`、`route_plan`、`session_state`，则本任务视为未完成。


---

## 31. 新增要求：任务解析进度条与可公开思考状态显示

当前任务解析阶段存在两个用户体验问题：

```text
1. 智能体连续追问时，用户不知道任务解析什么时候结束；
2. 用户回答问题后，如果后端处理时间较长，界面缺少状态反馈，用户不知道系统是否卡住。
```

因此需要新增：

```text
任务解析进度条
+
可公开思考状态显示
```

注意：这里的“思考状态”不是暴露模型原始 chain-of-thought。  
系统不得展示模型隐藏推理链。  
应展示的是可审计、可公开、可压缩的执行状态：

```text
当前阶段
已完成步骤
缺失槽位
下一步动作
工具调用状态
公开推理摘要
审计轨迹
```

禁止展示：

```text
模型隐藏 chain-of-thought
逐 token 内部推理
未过滤的系统 prompt
API Key
未审核候选知识的确定性结论
```

---

## 32. 任务解析进度模型

任务解析阶段应被设计为一个显式 workflow，而不是无限追问。

### 32.1 Task Intake Workflow Stage

新增标准阶段：

```text
intake_started
basic_info_extracted
missing_slots_identified
clarification_round_1
clarification_round_2
clarification_round_3
task_spec_confirmed
evidence_gap_checking
knowledge_bootstrap_pending
ready_for_planning
ready_for_rag
ready_for_bo
blocked_need_user_input
blocked_need_expert_review
```

### 32.2 进度百分比规则

MVP 使用规则型进度，不要求精确反映真实耗时。

建议映射：

```text
intake_started → 5%
basic_info_extracted → 15%
missing_slots_identified → 25%
clarification_round_1 → 40%
clarification_round_2 → 55%
clarification_round_3 → 70%
task_spec_confirmed → 80%
evidence_gap_checking → 85%
knowledge_bootstrap_pending → 88%
ready_for_planning → 90%
ready_for_rag → 92%
ready_for_bo → 95%
blocked_need_expert_review → 90%
workflow_completed → 100%
```

### 32.3 追问轮次限制

为了避免用户不知道什么时候结束，任务解析 skill 必须遵守：

```text
1. 默认最多 3 轮澄清；
2. 每轮最多 3 个问题；
3. 每轮问题必须标注目的；
4. 第 3 轮后必须给出：
   - 当前已知信息；
   - 仍缺失信息；
   - 可继续的保守方案；
   - 是否阻塞 BO / RAG / 方案生成。
```

若信息仍不足，不能无限追问。  
应输出：

```text
当前任务解析已完成 3 轮澄清，仍缺少以下关键字段。
系统可以继续生成保守任务方案，但不能进入确定性 BO 参数推荐。
```

---

## 33. 新增数据库表：workflow_progress

新增表：

```sql
CREATE TABLE workflow_progress (
    progress_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    workflow_id TEXT,
    workflow_type TEXT,
    current_stage TEXT,
    progress_percent REAL,
    status TEXT,
    message TEXT,
    completed_steps_json TEXT,
    pending_steps_json TEXT,
    missing_slots_json TEXT,
    updated_at TEXT
);
```

字段说明：

```text
workflow_type:
  task_intake
  crl_task_planning
  rag_literature_retrieval
  knowledge_bootstrap
  expert_review
  bo_recommendation

status:
  running
  waiting_user
  waiting_review
  completed
  failed
```

示例：

```json
{
  "workflow_type": "task_intake",
  "current_stage": "clarification_round_2",
  "progress_percent": 55,
  "status": "waiting_user",
  "message": "已完成基本任务识别，正在补充设备边界和验收指标。",
  "completed_steps": [
    "识别材料：diamond",
    "识别对象：CRL",
    "识别粗糙度目标：Ra < 460 nm"
  ],
  "pending_steps": [
    "确认金刚石类型",
    "确认激光器参数范围",
    "确认是否允许后处理"
  ],
  "missing_slots": [
    "diamond_type",
    "laser_system",
    "post_processing_allowed"
  ]
}
```

---

## 34. 新增数据库表：reasoning_status_trace

新增表，用于保存可公开推理摘要和执行轨迹。

```sql
CREATE TABLE reasoning_status_trace (
    trace_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    message_id TEXT,
    workflow_id TEXT,
    event_type TEXT,
    title TEXT,
    summary TEXT,
    detail_json TEXT,
    visibility TEXT,
    created_at TEXT
);
```

字段说明：

```text
event_type:
  thinking_started
  task_parsed
  slot_check
  clarification_planned
  evidence_gap_check
  tool_call_started
  tool_call_finished
  knowledge_candidate_created
  expert_review_required
  bo_blocked
  response_composing
  completed
  error

visibility:
  public
  internal
```

要求：

```text
1. 返回给前端/TUI 的只能是 visibility=public；
2. internal trace 只能用于调试日志，不应直接展示；
3. 不得保存原始 hidden chain-of-thought；
4. public summary 必须是简短、可审计、面向用户的状态说明。
```

示例：

```json
{
  "event_type": "slot_check",
  "title": "检查任务字段",
  "summary": "已识别材料、器件类型和粗糙度目标；仍缺少激光器参数范围。",
  "visibility": "public"
}
```

---

## 35. /chat 响应结构扩展

`ChatResponse` 新增字段：

```python
progress: dict | None = None
thinking_status: list[dict] = []
workflow_state: dict | None = None
```

返回示例：

```json
{
  "assistant_message": "我已识别为金刚石 CRL 制造任务。进入参数推荐前需要确认 3 项信息。",
  "progress": {
    "workflow_type": "task_intake",
    "current_stage": "clarification_round_1",
    "progress_percent": 40,
    "status": "waiting_user",
    "message": "已完成基本任务识别，正在补齐关键约束。"
  },
  "thinking_status": [
    {
      "event_type": "task_parsed",
      "title": "任务解析",
      "summary": "识别到材料为 diamond，对象为 CRL，目标包含 Ra < 460 nm。"
    },
    {
      "event_type": "slot_check",
      "title": "缺失字段检查",
      "summary": "缺少金刚石类型、激光器参数范围和是否允许后处理。"
    }
  ],
  "workflow_state": {
    "missing_slots": [
      "diamond_type",
      "laser_system",
      "post_processing_allowed"
    ],
    "clarification_round": 1,
    "max_clarification_rounds": 3
  }
}
```

---

## 36. Streaming 输出中的进度和思考状态

如果已实现 `/chat/stream_ndjson`，必须新增事件类型。

### 36.1 新增事件类型

```text
progress
thinking_status
workflow_state
```

示例：

```json
{"type":"progress","workflow_type":"task_intake","stage":"basic_info_extracted","progress_percent":15,"message":"已完成基本信息抽取。"}
{"type":"thinking_status","event_type":"slot_check","summary":"正在检查任务是否具备进入 BO 推荐的必要字段。"}
{"type":"progress","workflow_type":"task_intake","stage":"clarification_round_1","progress_percent":40,"message":"需要向用户确认 3 个关键问题。"}
{"type":"delta","content":"我已识别为金刚石 CRL 制造任务。"}
{"type":"done"}
```

### 36.2 PowerShell TUI 显示方式

PowerShell TUI 接收到 `progress` 事件时，显示简易进度条：

```text
[任务解析] [##########----------] 40%  clarification_round_1
已完成基本任务识别，正在补齐关键约束。
```

建议实现函数：

```powershell
Show-AgentProgressBar
Show-AgentThinkingStatus
```

---

## 37. PowerShell TUI 进度条实现要求

### 37.1 新增函数

在 `AgentTui.psm1` 中新增：

```powershell
Show-AgentProgressBar
Show-AgentThinkingStatus
Show-AgentWorkflowState
```

### 37.2 进度条示例实现

```powershell
function Show-AgentProgressBar {
    param(
        [double]$Percent,
        [string]$Stage,
        [string]$Message
    )

    $width = 20
    $filled = [Math]::Floor($Percent / 100 * $width)
    $empty = $width - $filled

    $bar = ("#" * $filled) + ("-" * $empty)

    Write-Host ("[任务进度] [{0}] {1}%  {2}" -f $bar, [Math]::Round($Percent), $Stage) -ForegroundColor Green

    if (-not [string]::IsNullOrWhiteSpace($Message)) {
        Write-Host $Message -ForegroundColor DarkGray
    }
}
```

### 37.3 思考状态显示示例

```powershell
function Show-AgentThinkingStatus {
    param(
        [string]$Title,
        [string]$Summary
    )

    Write-Host ("[状态] {0}: {1}" -f $Title, $Summary) -ForegroundColor DarkCyan
}
```

---

## 38. 非流式聊天中的进度显示

如果用户使用普通 `/chat` 非 streaming 模式，则后端应在响应中返回最终 progress 和 thinking_status。

PowerShell TUI 在打印 assistant_message 前，先打印：

```text
[任务进度] 40% clarification_round_1
[状态] 任务解析：识别到材料 diamond，对象 CRL。
[状态] 缺失字段检查：缺少激光器参数范围。
```

然后再打印智能体回复。

---

## 39. 任务解析 Skill 更新要求

需要更新 `task_intake` 和 `crl_task_planning` 的 skill 行为。

### 39.1 task_intake 必须输出

```json
{
  "workflow_progress": {
    "current_stage": "clarification_round_1",
    "progress_percent": 40,
    "status": "waiting_user"
  },
  "public_reasoning_summary": [
    {
      "title": "任务解析",
      "summary": "已识别材料、对象和质量目标。"
    }
  ],
  "clarification_round": 1,
  "max_clarification_rounds": 3,
  "missing_slots": [],
  "clarification_questions": []
}
```

### 39.2 crl_task_planning 必须输出

```json
{
  "workflow_progress": {
    "current_stage": "task_spec_confirmed",
    "progress_percent": 80,
    "status": "running"
  },
  "public_reasoning_summary": [
    {
      "title": "CRL 任务识别",
      "summary": "该任务涉及金刚石 X-ray CRL 制造规划，需要同时考虑粗糙度、面形误差和光学性能。"
    }
  ]
}
```

---

## 40. 不能展示隐藏推理链的硬约束

必须在 README、system prompt、skill 文档中写明：

```text
系统不展示模型原始隐藏推理链。
系统展示的是可公开的任务状态、工具调用轨迹、证据检查结果和简要推理摘要。
```

禁止使用字段名：

```text
chain_of_thought
raw_thoughts
hidden_reasoning
model_reasoning_tokens
```

推荐使用字段名：

```text
thinking_status
public_reasoning_summary
workflow_progress
audit_trace
tool_trace
```

---

## 41. 新增 API

### 41.1 获取当前会话进度

```http
GET /chat/sessions/{session_id}/progress
```

返回：

```json
{
  "session_id": "sess_001",
  "progress": {
    "workflow_type": "task_intake",
    "current_stage": "clarification_round_1",
    "progress_percent": 40,
    "status": "waiting_user",
    "message": "等待用户补充关键任务信息。"
  },
  "thinking_status": []
}
```

### 41.2 获取公开状态轨迹

```http
GET /chat/sessions/{session_id}/thinking-status
```

返回：

```json
{
  "session_id": "sess_001",
  "events": [
    {
      "event_type": "task_parsed",
      "title": "任务解析",
      "summary": "已识别材料 diamond 和对象 CRL。",
      "created_at": "..."
    }
  ]
}
```

注意：该接口只能返回 `visibility=public` 的记录。

---

## 42. 新增测试要求

### 42.1 test_workflow_progress.py

必须测试：

```text
1. 新 session 初始 progress 为 intake_started 或空；
2. task_intake 后 progress_percent > 0；
3. clarification_round_1 对应 progress_percent=40；
4. clarification_round 不超过 3；
5. workflow_completed 对应 100%。
```

### 42.2 test_public_thinking_status.py

必须测试：

```text
1. /chat 返回 thinking_status；
2. thinking_status 不包含 chain_of_thought/raw_thoughts/hidden_reasoning 字段；
3. GET /thinking-status 只返回 visibility=public；
4. tool_call_started / evidence_gap_check 等事件可保存和查询。
```

### 42.3 test_chat_stream_progress.py

如果实现 `/chat/stream_ndjson`，必须测试：

```text
1. stream 中包含 progress event；
2. stream 中包含 thinking_status event；
3. progress event 出现在 delta 之前；
4. done event 正常结束。
```

### 42.4 test_powershell_progress_contract.py

如果已有 PowerShell TUI 测试或脚本检查，必须确保：

```text
1. Show-AgentProgressBar 函数存在；
2. Show-AgentThinkingStatus 函数存在；
3. progress NDJSON event 可被识别；
4. thinking_status NDJSON event 可被识别。
```

---

## 43. 验收标准补充

### 43.1 非流式验收

调用：

```bash
curl -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message":"我想加工金刚石CRL，Ra小于460nm",
    "use_skills":true
  }'
```

预期：

```text
1. 返回 assistant_message；
2. 返回 progress；
3. progress.progress_percent > 0；
4. 返回 thinking_status；
5. thinking_status 为公开摘要，不包含隐藏推理链字段；
6. workflow_state 中包含 missing_slots；
7. 若需要追问，clarification_round <= 3。
```

### 43.2 流式验收

调用 `/chat/stream_ndjson` 时，应看到：

```json
{"type":"progress", ...}
{"type":"thinking_status", ...}
{"type":"delta", ...}
{"type":"done"}
```

PowerShell TUI 应显示：

```text
[任务进度] [########------------] 40% clarification_round_1
[状态] 任务解析：已识别材料 diamond，对象 CRL。
智能体：...
```

### 43.3 追问终止验收

构造一个持续缺少设备参数的任务，连续三轮追问后，系统必须输出：

```text
已完成最大澄清轮次。
当前可以生成保守任务方案，但不能进入确定性 BO 参数推荐。
```

不得继续无限追问。

---

## 44. README 补充

README 新增章节：

```text
任务进度与公开思考状态
```

必须说明：

```text
1. 任务解析阶段为什么有进度条；
2. 进度百分比是规则型 workflow 进度，不代表真实计算耗时；
3. 系统最多进行 3 轮澄清；
4. 系统展示的是公开推理摘要，不是模型隐藏 chain-of-thought；
5. 如何通过 /chat/sessions/{id}/progress 查看进度；
6. 如何通过 /chat/sessions/{id}/thinking-status 查看公开状态轨迹；
7. PowerShell TUI 如何显示 progress 和 thinking_status。
```

---

## 45. 实现顺序补充

请 Codex 在当前任务基础上按以下顺序实现：

```text
Phase A：workflow_progress 数据模型
Phase B：reasoning_status_trace 数据模型
Phase C：ChatResponse 增加 progress / thinking_status / workflow_state
Phase D：task_intake / crl_task_planning 输出 progress
Phase E：/chat 非流式返回 progress 和 thinking_status
Phase F：/chat/stream_ndjson 增加 progress / thinking_status event
Phase G：PowerShell TUI 显示进度条和状态
Phase H：新增 progress/thinking-status API
Phase I：测试与 README
```

---

## 46. 更新后的交互目标

最终用户体验应是：

```text
用户：我想加工金刚石 CRL，Ra 小于 460 nm

系统显示：
[任务进度] [###-----------------] 15% basic_info_extracted
[状态] 任务解析：已识别材料 diamond、对象 CRL、粗糙度目标 Ra < 460 nm。
[状态] 缺失字段检查：仍缺少金刚石类型、设备参数和是否允许后处理。

智能体：
进入参数推荐前需要确认 3 项信息：
1. 金刚石是单晶、CVD 多晶还是 HPHT？
2. 激光器波长、脉宽、最大功率和频率范围是多少？
3. 是否允许后处理？
```

当用户回答后，如果系统处理时间较长，TUI 或 stream 应持续显示：

```text
[任务进度] 55% clarification_round_2
[状态] 正在更新 task_spec。
[状态] 正在判断是否具备进入 RAG 检索条件。
[状态] 正在检查内部知识库证据是否足够。
```

用户不应再面对无反馈的长时间等待。



---

## 47. 新增要求：初始化设备参数配置与设备记忆层

当前任务解析中经常需要反复询问用户：

```text
激光器波长是多少？
脉宽范围是多少？
最大功率是多少？
重复频率范围是多少？
扫描速度范围是多少？
光斑尺寸是多少？
是否有振镜、位移台、物镜 NA 等信息？
```

这类信息通常属于固定设备边界，不应在每个加工任务中重复追问。  
因此需要在系统初始化配置阶段新增“设备参数配置向导”，并将设备信息写入专业知识记忆库中的结构化设备记忆层。

核心目标：

```text
初始化时配置设备参数
↓
写入 equipment_profile / machine_bounds
↓
设置 active_equipment_profile
↓
任务解析时自动读取设备边界
↓
BO 推荐时自动使用设备边界约束
↓
只有设备信息缺失、过期或任务需要特殊装夹/光路时才追问用户
```

设备记忆不应通过 RAG 实现。  
设备边界是结构化事实，应保存到数据库中，并由 task_intake / bo_recommendation 直接读取。

---

## 48. 设备配置范围

初始化配置至少支持以下信息。

### 48.1 激光源参数

```text
laser_name
manufacturer
model
wavelength_nm
pulse_width_min_fs
pulse_width_max_fs
pulse_width_fixed_fs
average_power_min_W
average_power_max_W
frequency_min_kHz
frequency_max_kHz
pulse_energy_max_uJ
beam_quality_M2
polarization
```

### 48.2 光路与聚焦参数

```text
objective_name
objective_NA
focal_length_mm
spot_diameter_um
working_distance_mm
beam_expander
focus_control_mode
focus_offset_min_um
focus_offset_max_um
```

### 48.3 扫描/运动系统参数

```text
scan_system_type
galvo_max_speed_mm_s
stage_max_speed_mm_s
scan_speed_min_mm_s
scan_speed_max_mm_s
positioning_accuracy_um
repeatability_um
work_area_x_mm
work_area_y_mm
work_area_z_mm
```

### 48.4 工艺参数边界

```text
passes_min
passes_max
hatch_spacing_min_um
hatch_spacing_max_um
layer_step_min_um
layer_step_max_um
fill_patterns_supported
path_strategies_supported
```

### 48.5 环境与辅助系统

```text
environment
assist_gas_supported
assist_gas_types
vacuum_supported
water_cooling
temperature_control
```

### 48.6 配置元数据

```text
equipment_profile_id
profile_name
created_at
updated_at
created_by
status
is_active
calibration_date
valid_until
notes
```

---

## 49. 新增数据库表

### 49.1 `equipment_profile`

保存设备主档。

```sql
CREATE TABLE equipment_profile (
    equipment_profile_id TEXT PRIMARY KEY,
    profile_name TEXT NOT NULL,
    machine_id TEXT,
    manufacturer TEXT,
    model TEXT,
    location TEXT,
    status TEXT,
    is_active INTEGER,
    created_by TEXT,
    created_at TEXT,
    updated_at TEXT,
    calibration_date TEXT,
    valid_until TEXT,
    notes TEXT
);
```

`status` 可选：

```text
draft
active
inactive
archived
needs_calibration
```

---

### 49.2 `laser_source_config`

保存激光源边界。

```sql
CREATE TABLE laser_source_config (
    config_id TEXT PRIMARY KEY,
    equipment_profile_id TEXT NOT NULL,
    laser_name TEXT,
    wavelength_nm REAL,
    pulse_width_min_fs REAL,
    pulse_width_max_fs REAL,
    pulse_width_fixed_fs REAL,
    average_power_min_W REAL,
    average_power_max_W REAL,
    frequency_min_kHz REAL,
    frequency_max_kHz REAL,
    pulse_energy_max_uJ REAL,
    beam_quality_M2 REAL,
    polarization TEXT,
    parameters_json TEXT
);
```

---

### 49.3 `optical_setup_config`

保存光路和聚焦配置。

```sql
CREATE TABLE optical_setup_config (
    config_id TEXT PRIMARY KEY,
    equipment_profile_id TEXT NOT NULL,
    objective_name TEXT,
    objective_NA REAL,
    focal_length_mm REAL,
    spot_diameter_um REAL,
    working_distance_mm REAL,
    beam_expander TEXT,
    focus_control_mode TEXT,
    focus_offset_min_um REAL,
    focus_offset_max_um REAL,
    parameters_json TEXT
);
```

---

### 49.4 `motion_system_config`

保存振镜、位移台和加工区域边界。

```sql
CREATE TABLE motion_system_config (
    config_id TEXT PRIMARY KEY,
    equipment_profile_id TEXT NOT NULL,
    scan_system_type TEXT,
    galvo_max_speed_mm_s REAL,
    stage_max_speed_mm_s REAL,
    scan_speed_min_mm_s REAL,
    scan_speed_max_mm_s REAL,
    positioning_accuracy_um REAL,
    repeatability_um REAL,
    work_area_x_mm REAL,
    work_area_y_mm REAL,
    work_area_z_mm REAL,
    parameters_json TEXT
);
```

---

### 49.5 `process_capability_config`

保存工艺参数边界。

```sql
CREATE TABLE process_capability_config (
    config_id TEXT PRIMARY KEY,
    equipment_profile_id TEXT NOT NULL,
    passes_min INTEGER,
    passes_max INTEGER,
    hatch_spacing_min_um REAL,
    hatch_spacing_max_um REAL,
    layer_step_min_um REAL,
    layer_step_max_um REAL,
    fill_patterns_supported_json TEXT,
    path_strategies_supported_json TEXT,
    materials_supported_json TEXT,
    process_types_supported_json TEXT,
    parameters_json TEXT
);
```

---

### 49.6 `equipment_config_revision`

保存设备配置版本历史。

```sql
CREATE TABLE equipment_config_revision (
    revision_id TEXT PRIMARY KEY,
    equipment_profile_id TEXT NOT NULL,
    revision_number INTEGER,
    changed_by TEXT,
    changed_at TEXT,
    change_summary TEXT,
    snapshot_json TEXT
);
```

要求：

```text
1. 设备配置修改必须记录 revision；
2. 不允许静默覆盖历史配置；
3. active profile 变更必须写入 revision；
4. BO 推荐必须记录当时使用的 equipment_profile_id 和 revision_id。
```

---

## 50. 初始化设备配置向导

PowerShell TUI 启动器需要新增设备配置流程。

### 50.1 启动页新增菜单

在主菜单中新增：

```text
[12] 配置设备参数
[13] 查看当前设备配置
[14] 切换当前设备配置
```

### 50.2 首次启动检查

系统启动时应检查是否存在 active equipment profile。

如果不存在，显示：

```text
当前尚未配置激光设备参数。
建议先配置设备边界，否则任务解析和 BO 推荐会反复询问设备信息。
是否现在配置？[Y/N]
```

如果用户选择 N，系统仍可运行，但 task_intake 需要继续追问设备信息。

### 50.3 配置向导问题

MVP 阶段采用交互式问题。

最少字段：

```text
1. 设备名称 / profile_name
2. 激光波长 wavelength_nm
3. 脉宽 pulse_width_fixed_fs 或 pulse_width_min/max_fs
4. 平均功率范围 average_power_min/max_W
5. 重复频率范围 frequency_min/max_kHz
6. 扫描速度范围 scan_speed_min/max_mm_s
7. 光斑直径 spot_diameter_um
8. 焦点偏移范围 focus_offset_min/max_um
9. 线间距范围 hatch_spacing_min/max_um
10. 层步距范围 layer_step_min/max_um
11. 最大扫描次数 passes_max
```

允许用户跳过不确定字段，但必须记录为空，不得编造。

---

## 51. 设备配置 API

新增 FastAPI 接口。

### 51.1 创建设备配置

```http
POST /equipment/profiles
```

请求：

```json
{
  "profile_name": "Lab fs laser 1030nm",
  "machine_id": "laser_A",
  "laser_source": {
    "wavelength_nm": 1030,
    "pulse_width_fixed_fs": 300,
    "average_power_min_W": 0.1,
    "average_power_max_W": 20,
    "frequency_min_kHz": 50,
    "frequency_max_kHz": 1000
  },
  "optical_setup": {
    "spot_diameter_um": 20,
    "focus_offset_min_um": -100,
    "focus_offset_max_um": 100
  },
  "motion_system": {
    "scan_speed_min_mm_s": 10,
    "scan_speed_max_mm_s": 3000,
    "work_area_x_mm": 100,
    "work_area_y_mm": 100
  },
  "process_capability": {
    "passes_min": 1,
    "passes_max": 20,
    "hatch_spacing_min_um": 1,
    "hatch_spacing_max_um": 50,
    "layer_step_min_um": 0.5,
    "layer_step_max_um": 20
  },
  "set_active": true
}
```

返回：

```json
{
  "equipment_profile_id": "eq_001",
  "revision_id": "eqrev_001",
  "is_active": true
}
```

---

### 51.2 获取当前 active 设备配置

```http
GET /equipment/active
```

返回：

```json
{
  "equipment_profile_id": "eq_001",
  "profile_name": "Lab fs laser 1030nm",
  "laser_source": {},
  "optical_setup": {},
  "motion_system": {},
  "process_capability": {},
  "revision_id": "eqrev_001"
}
```

---

### 51.3 查看所有设备配置

```http
GET /equipment/profiles
```

---

### 51.4 设置 active 设备

```http
POST /equipment/profiles/{equipment_profile_id}/activate
```

---

### 51.5 更新设备配置

```http
PATCH /equipment/profiles/{equipment_profile_id}
```

要求：

```text
1. 修改后必须创建新的 equipment_config_revision；
2. 不允许直接覆盖 revision 历史；
3. 如果是 active profile，任务解析后续自动使用新 revision。
```

---

### 51.6 获取 BO 可用 machine_bounds

```http
GET /equipment/active/machine-bounds
```

返回：

```json
{
  "equipment_profile_id": "eq_001",
  "revision_id": "eqrev_001",
  "machine_bounds": {
    "wavelength_nm": [1030, 1030],
    "pulse_width_fs": [300, 300],
    "laser_power_W": [0.1, 20],
    "frequency_kHz": [50, 1000],
    "scan_speed_mm_s": [10, 3000],
    "focus_offset_um": [-100, 100],
    "hatch_spacing_um": [1, 50],
    "layer_step_um": [0.5, 20],
    "passes": [1, 20]
  }
}
```

---

## 52. 任务解析阶段读取设备记忆

task_intake 和 crl_task_planning 必须优先读取 active equipment profile。

### 52.1 任务解析流程更新

原流程：

```text
用户输入
↓
识别材料/工艺/目标
↓
追问设备参数
```

更新为：

```text
用户输入
↓
识别材料/工艺/目标
↓
查询 active equipment profile
↓
若存在：
   自动填充 machine_bounds
   不再追问已知设备边界
若不存在或字段缺失：
   只追问缺失字段
```

### 52.2 ChatResponse 增加字段

`workflow_state` 中增加：

```json
{
  "equipment_profile_used": {
    "equipment_profile_id": "eq_001",
    "profile_name": "Lab fs laser 1030nm",
    "revision_id": "eqrev_001"
  },
  "machine_bounds": {
    "laser_power_W": [0.1, 20],
    "frequency_kHz": [50, 1000]
  },
  "missing_equipment_fields": []
}
```

### 52.3 thinking_status 说明

当系统读取设备记忆时，必须返回公开状态：

```json
{
  "event_type": "equipment_profile_loaded",
  "title": "读取设备配置",
  "summary": "已读取当前激光设备配置 Lab fs laser 1030nm，并自动填充功率、频率和扫描速度边界。"
}
```

---

## 53. BO 推荐必须使用设备边界

bo_recommendation skill 必须读取 active equipment profile，并将 machine_bounds 传入 BO 输入。

### 53.1 BO 输入记录

每次 BO 推荐记录中必须保存：

```json
{
  "equipment_profile_id": "eq_001",
  "equipment_revision_id": "eqrev_001",
  "machine_bounds": {}
}
```

### 53.2 参数越界检查

BO 输出候选参数后，必须检查：

```text
laser_power_W 是否在 active machine_bounds 内；
frequency_kHz 是否在 active machine_bounds 内；
scan_speed_mm_s 是否在 active machine_bounds 内；
focus_offset_um 是否在 active machine_bounds 内；
hatch_spacing_um 是否在 active machine_bounds 内；
layer_step_um 是否在 active machine_bounds 内；
passes 是否在 active machine_bounds 内。
```

若越界：

```text
1. 标记 candidate invalid；
2. 不得输出为推荐参数；
3. audit_trace 记录 blocked_by_machine_bounds。
```

---

## 54. 设备配置与 RAG 的关系

设备配置是结构化记忆，不应写入普通 RAG 作为主要读取方式。

可以生成一条 RAG 摘要用于解释，但任务解析和 BO 必须通过结构化数据库读取设备配置。

规则：

```text
equipment_profile → 结构化数据库主数据；
equipment_profile_summary → 可选进入 RAG，用于自然语言解释；
task_intake / bo_recommendation → 必须查结构化 equipment API；
RAG → 不得作为设备边界的唯一来源。
```

---

## 55. 新增服务模块

新增目录：

```text
src/ultrafast_memory/equipment/
  __init__.py
  schemas.py
  models.py
  service.py
  bounds.py
  validation.py
```

### 55.1 schemas.py

定义：

```python
class EquipmentProfileCreate(BaseModel):
    profile_name: str
    machine_id: str | None = None
    laser_source: dict = {}
    optical_setup: dict = {}
    motion_system: dict = {}
    process_capability: dict = {}
    set_active: bool = False
```

```python
class MachineBounds(BaseModel):
    equipment_profile_id: str
    revision_id: str
    machine_bounds: dict
```

### 55.2 bounds.py

实现：

```python
def build_machine_bounds(equipment_profile_id: str | None = None) -> dict:
    ...
```

若 `equipment_profile_id` 为空，使用 active profile。

### 55.3 validation.py

实现设备配置合法性检查：

```text
min <= max；
功率、频率、速度不能为负；
单位必须标准化；
pulse_width_fixed_fs 与 pulse_width_min/max_fs 不冲突；
active profile 至少应包含 laser_power_W、frequency_kHz、scan_speed_mm_s。
```

---

## 56. PowerShell TUI 实现要求

在 `AgentTui.psm1` 中新增函数：

```powershell
Start-EquipmentSetupWizard
Show-ActiveEquipmentProfile
Select-ActiveEquipmentProfile
Get-AgentMachineBounds
```

### 56.1 配置向导显示

示例：

```text
=== 设备参数配置向导 ===

设备名称：Lab fs laser 1030nm
波长 nm：1030
固定脉宽 fs：300
最小平均功率 W：0.1
最大平均功率 W：20
最小重复频率 kHz：50
最大重复频率 kHz：1000
最小扫描速度 mm/s：10
最大扫描速度 mm/s：3000
光斑直径 um：20
线间距范围 um：1-50
层步距范围 um：0.5-20
最大扫描次数：20

是否设为当前 active 设备？Y/N
```

### 56.2 查看当前设备

显示：

```text
当前 active 设备：
Profile: Lab fs laser 1030nm
Wavelength: 1030 nm
Pulse width: 300 fs
Power: 0.1–20 W
Frequency: 50–1000 kHz
Scan speed: 10–3000 mm/s
Spot diameter: 20 um
Revision: eqrev_001
```

---

## 57. 配置文件支持

允许在 `configs/default.yaml` 中设置默认 active equipment 行为：

```yaml
equipment:
  require_active_profile_for_bo: true
  warn_if_no_active_profile: true
  allow_task_level_override: true
  default_profile_id: null
```

含义：

```text
require_active_profile_for_bo:
  如果 true，没有 active equipment profile 时，BO 推荐必须阻塞。

allow_task_level_override:
  允许用户在某次任务中覆盖设备边界，但必须记录 override。
```

---

## 58. 任务级设备覆盖

有时用户某次任务使用不同光路或临时限制功率。需要支持 task-level override。

### 58.1 task_spec 中增加

```json
{
  "equipment_profile_id": "eq_001",
  "equipment_revision_id": "eqrev_001",
  "machine_bounds_override": {
    "laser_power_W": [0.1, 10]
  },
  "override_reason": "本次使用低功率物镜，限制最大功率为 10 W。"
}
```

### 58.2 规则

```text
1. override 不能超过设备物理边界；
2. override 必须记录 reason；
3. BO 推荐使用 override 后的 machine_bounds；
4. audit_trace 必须记录 task_level_machine_bounds_override。
```

---

## 59. 新增测试要求

### 59.1 test_equipment_profile.py

测试：

```text
1. 能创建 equipment_profile；
2. set_active=true 后 GET /equipment/active 返回该设备；
3. 更新设备配置会创建 revision；
4. 没有 active profile 时 GET /equipment/active 返回明确错误或 empty 状态。
```

### 59.2 test_machine_bounds.py

测试：

```text
1. build_machine_bounds 能生成 BO 所需边界；
2. 固定脉宽 pulse_width_fixed_fs 变成 [fixed, fixed]；
3. min/max 字段正确映射；
4. 缺失字段不会被编造；
5. 负数和 min > max 会被校验拒绝。
```

### 59.3 test_task_intake_equipment_memory.py

测试：

```text
1. 有 active equipment profile 时，task_intake 不再追问设备功率/频率/速度；
2. workflow_state 包含 equipment_profile_used；
3. thinking_status 包含 equipment_profile_loaded；
4. 若 active profile 缺少 spot_diameter_um，只追问该字段。
```

### 59.4 test_bo_machine_bounds.py

测试：

```text
1. BO 推荐前读取 active machine_bounds；
2. 无 active profile 且 require_active_profile_for_bo=true 时阻塞；
3. BO 候选越界时被标记 invalid；
4. task-level override 不能超过设备物理边界。
```

### 59.5 test_equipment_api.py

测试：

```text
POST /equipment/profiles；
GET /equipment/active；
GET /equipment/active/machine-bounds；
POST /equipment/profiles/{id}/activate；
PATCH /equipment/profiles/{id}。
```

---

## 60. README 补充

新增章节：

```text
设备参数配置与设备记忆
```

必须说明：

```text
1. 为什么初始化时要配置设备参数；
2. 设备配置保存在哪里；
3. 设备配置不是 RAG，而是结构化记忆；
4. 任务解析如何自动读取 active equipment profile；
5. BO 如何使用 machine_bounds；
6. 如何通过 PowerShell TUI 配置设备；
7. 如何查看和切换 active equipment profile；
8. 如何处理任务级 override；
9. 没有 active profile 时系统会怎样；
10. 设备配置修改会生成 revision。
```

---

## 61. 验收标准补充

### 61.1 初始化设备配置验收

通过 TUI 或 API 创建设备：

```bash
curl -X POST http://127.0.0.1:8000/equipment/profiles \
  -H "Content-Type: application/json" \
  -d '{
    "profile_name":"Lab fs laser 1030nm",
    "machine_id":"laser_A",
    "laser_source":{
      "wavelength_nm":1030,
      "pulse_width_fixed_fs":300,
      "average_power_min_W":0.1,
      "average_power_max_W":20,
      "frequency_min_kHz":50,
      "frequency_max_kHz":1000
    },
    "optical_setup":{
      "spot_diameter_um":20,
      "focus_offset_min_um":-100,
      "focus_offset_max_um":100
    },
    "motion_system":{
      "scan_speed_min_mm_s":10,
      "scan_speed_max_mm_s":3000
    },
    "process_capability":{
      "passes_min":1,
      "passes_max":20,
      "hatch_spacing_min_um":1,
      "hatch_spacing_max_um":50,
      "layer_step_min_um":0.5,
      "layer_step_max_um":20
    },
    "set_active":true
  }'
```

预期：

```text
1. 返回 equipment_profile_id；
2. 返回 revision_id；
3. is_active=true；
4. GET /equipment/active 可查到；
5. GET /equipment/active/machine-bounds 返回 BO 可用边界。
```

### 61.2 聊天任务解析验收

创建 active profile 后，调用：

```bash
curl -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message":"我想加工金刚石CRL，Ra小于460nm",
    "use_skills":true
  }'
```

预期：

```text
1. workflow_state.equipment_profile_used 非空；
2. thinking_status 包含 equipment_profile_loaded；
3. 系统不再询问已配置的功率、频率、扫描速度边界；
4. 若仍追问，只追问材料类型、后处理、面形误差等非设备固定信息。
```

### 61.3 BO 阻塞验收

如果没有 active equipment profile 且：

```yaml
equipment.require_active_profile_for_bo: true
```

用户要求推荐参数时，系统必须回复：

```text
当前没有 active 设备配置，无法进行 BO 参数推荐。
请先配置设备参数，或为本任务提供临时 machine_bounds。
```

不得输出确定参数。

---

## 62. 更新后的关键边界

必须写入 system prompt / skill / README：

```text
设备边界来自 equipment_profile；
任务解析优先读取 active equipment profile；
RAG 不作为设备边界的权威来源；
没有 active equipment profile 时，BO 推荐默认阻塞；
任务级 override 不得超过设备物理边界；
所有 BO 推荐必须记录 equipment_profile_id 和 revision_id；
设备配置变更必须保留 revision。
```

