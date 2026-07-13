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
