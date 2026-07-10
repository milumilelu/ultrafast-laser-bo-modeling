# Ultrafast Laser Memory MVP

## 项目目标

本项目搭建一个可审计的超快激光加工专业知识记忆库与自学习数据闭环 MVP。它把配方、日志、检测 CSV 和操作员备注归档、解析、标准化、校验并写入 SQLite，之后生成经验候选并导出 BO 训练候选数据。

边界很明确：本 MVP 不训练大模型，不让 LLM 自动改参数，不自动生成正式工艺规则；LLM 只能作为后续 `experience_candidate` 抽取模块。

## 安装

```powershell
cd ultrafast_laser_memory
pip install -e .[dev]
```

## 初始化数据库

```powershell
python -m ultrafast_memory.app.cli init-db
```

默认数据库为 `data/ultrafast_memory.db`。

## 导入示例数据

```powershell
python -m ultrafast_memory.app.cli scan examples
python -m ultrafast_memory.app.cli list-artifacts
python -m ultrafast_memory.app.cli list-runs
```

导入时会计算 SHA256，并把原始文件复制到 `data/raw_artifacts/YYYY-MM-DD/`。重复 SHA256 文件会跳过，原始文件不会被移动或修改。

## 查看经验候选

```powershell
python -m ultrafast_memory.app.cli list-candidates
python -m ultrafast_memory.app.cli review-candidate <candidate_id> --action accept
```

接受候选不会自动写入 `validated_rule`。规则晋升必须由后续显式人工流程触发。

## 导出 BO 数据

```powershell
python -m ultrafast_memory.app.cli export-bo
```

输出文件：`data/exports/bo_training_samples.csv`。字段缺失时保持为空，不编造数据。异常中断、报警、关键参数缺失或无有效检测结果的 run 不会被标记为可训练样本。

## FastAPI

```powershell
python -m uvicorn ultrafast_memory.app.api:app --reload --host 127.0.0.1 --port 8000
```

主要接口：`/health`、`/ingest/scan`、`/artifacts`、`/runs`、`/experience/candidates`、`/bo/export`、`/llm/config`、`/llm/test`、`/chat/sessions`、`/chat`、`/chat/stream_ndjson`。

## 聊天功能

`/chat` 是超快激光智能体的 Agent Orchestrator 入口，不是普通 LLM proxy。MVP 流程为：PowerShell TUI -> `/chat` -> rule-based skill router -> LLM adapter or MockLLM -> session persistence -> audit trace。

启动后端：

```powershell
python -m uvicorn ultrafast_memory.app.api:app --reload --host 127.0.0.1 --port 8000
```

进入 PowerShell 聊天：

```powershell
pwsh -ExecutionPolicy Bypass -File scripts/start_agent_tui.ps1
```

默认启动流程已简化为 DeepSeek 专用向导：只选择 `Flash` 或 `Pro` 模型并输入 DeepSeek API Key。数据库初始化、示例扫描、BO CSV 导出、FastAPI 后端启动都会自动完成，随后直接进入聊天界面。

无 API Key 或 LLM 配置不完整时会使用 `MockLLMClient`，因此离线也可跑通会话保存、skill 路由和审计记录。当前 TUI 默认固定供应商为 DeepSeek，只保留 `deepseek-v4-flash` 和 `deepseek-v4-pro` 两个模型选项。其他 OpenAI-Compatible provider 仍保留在后端 adapter 中，但默认启动器不再要求用户配置。

重要：如果在 TUI 中配置了 API Key，必须从同一个 TUI 会话中启动 FastAPI，否则后端进程可能无法继承环境变量。API Key 不会出现在 `/chat`、`/chat/sessions` 或消息历史响应中。

当前 MVP 不真正调用 RAG/BO/tool calling，不支持 Web Chat 前端。

API 示例：

```bash
curl -X POST http://127.0.0.1:8000/chat/sessions \
  -H "Content-Type: application/json" \
  -d '{"title":"test","mode":"agent"}'
```

```bash
curl -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"我想加工金刚石CRL","use_skills":true}'
```

## Streaming Chat 与混合 Router

`/chat` 返回兼容字段 `selected_skill`，同时返回结构化 `route_plan`。混合 Router 按以下顺序判断：session continuation、手动 `/skill` 覆盖、规则路由、LLM 路由、低置信 fallback。路由主记录写入 `chat_route_trace`，会话状态写入 `chat_session_state`。

流式接口：

```bash
curl -N -X POST http://127.0.0.1:8000/chat/stream_ndjson \
  -H "Content-Type: application/json" \
  -d '{"message":"我想加工金刚石CRL","use_skills":true,"stream":true}'
```

返回 `application/x-ndjson`，事件类型包括 `meta`、`route`、`trace`、`delta`、`warning`、`error`、`done`。`delta` 为模型输出增量；`route` 包含 `primary_skill`、`secondary_skills`、`confidence` 和 `route_source`。

PowerShell TUI 聊天命令：

- `/stream on`：启用 NDJSON 流式输出；
- `/stream off`：关闭流式输出；
- `/skill <skill_name>`：本轮手动指定 skill；
- `/no_skill`：本轮禁用 skill 路由；
- `/debug router on`、`/debug router off`：开关 router debug 状态；
- `/state`：查看 session state；
- `/reset`：清空 session state；
- `/routes`：查看可用 skill。

## 知识冷启动与专家审核

`knowledge_bootstrap` 用于解决内部 RAG 初期知识不足的问题。它不会把 LLM 知识或外部检索结果直接写入正式知识库，而是先生成可追溯的 `knowledge_candidate`，再创建 `knowledge_review_task` 等待专家审核。

核心边界：

- 外部检索结果只能先进入候选知识；
- 候选知识未经审核不能作为确定性工艺建议；
- `accept_to_rag` 只表示可作为 RAG 背景解释，不代表可用于 BO；
- `accept_as_literature_evidence` 表示可作为文献证据，并同时进入 RAG；
- `process_prior` 才能作为 BO 搜索边界候选；
- `validated_rule` 才能参与推荐过滤；
- `bo_training_sample` 必须来自完整、可追溯、通过质量校验的实验记录；
- 当前 MVP 只实现 MockWebSearchClient，不执行真实联网检索。

检测 evidence gap：

```bash
curl -X POST http://127.0.0.1:8000/knowledge/evidence-gap \
  -H "Content-Type: application/json" \
  -d '{"task_spec":{"material":"diamond","component_type":"CRL","process_type":"femtosecond_laser_micromachining"},"question":"金刚石CRL如何进行超快激光加工？","internal_hits":[]}'
```

执行 mock web bootstrap：

```bash
curl -X POST http://127.0.0.1:8000/knowledge/bootstrap-web \
  -H "Content-Type: application/json" \
  -d '{"task_spec":{"material":"diamond","component_type":"CRL","process_type":"femtosecond_laser_micromachining"},"query_intent":"find_literature_prior","question":"金刚石CRL如何进行超快激光加工？","max_sources":3,"review_required":true}'
```

查看候选知识和审核队列：

```http
GET http://127.0.0.1:8000/knowledge/candidates?status=pending_review
GET http://127.0.0.1:8000/knowledge/review/tasks?status=pending_review
GET http://127.0.0.1:8000/knowledge/review/tasks/{review_id}
```

专家审核接收入 RAG：

```bash
curl -X POST http://127.0.0.1:8000/knowledge/review/tasks/<review_id>/action \
  -H "Content-Type: application/json" \
  -d '{"action":"accept_to_rag","reviewer_id":"expert_001","comment":"作为背景知识接收入RAG，禁止用于BO参数推荐。","target_level":"LEVEL_1_RAG_BACKGROUND"}'
```

聊天集成：

- 新材料、新结构、查文献、基于文献制定方案、BO 参数推荐证据不足时，`/chat` 会先执行 evidence gap check；
- 内部证据不足且配置要求授权时，聊天会请求用户确认；
- 用户输入“可以 / 同意 / 允许 / 执行冷启动 / yes / ok”后才会执行 mock bootstrap；
- `/bootstrap status` 查看当前会话候选知识和审核状态；
- `/review tasks` 和 `/review open <review_id>` 可在 PowerShell TUI 聊天模式查看审核任务；
- 审核通过后，当前 chat session 的 `active_knowledge_bootstrap` 会感知已接收的 RAG 文档。

后续接入真实 web search 时，应替换 `OpenAIWebSearchClient` stub，并继续保持 `web / LLM -> candidate -> expert review -> governed memory -> RAG / rules / BO` 的治理链路。

## 任务进度与公开思考状态

聊天任务解析阶段会返回规则型 workflow 进度，避免连续追问时用户不知道流程是否结束。进度百分比不是实际计算耗时，而是当前阶段的可解释状态，例如 `clarification_round_1 = 40%`、`evidence_gap_checking = 85%`、`blocked_need_expert_review = 90%`。

系统最多进行 3 轮澄清。第 3 轮后仍缺少关键字段时，应给出当前已知信息、仍缺失信息和可继续的保守方案，不能无限追问，也不能进入确定性 BO 参数推荐。

系统不展示模型原始隐藏推理链。返回和 TUI 展示的是可公开的 Agent 执行轨迹、任务状态、工具调用状态、证据检查结果和简要推理摘要，字段使用 `progress`、`thinking_status`、`workflow_state`、`execution_trace`、`audit_trace`。

非流式 `/chat` 会返回：

```json
{
  "progress": {
    "workflow_type": "crl_task_planning",
    "current_stage": "evidence_gap_checking",
    "progress_percent": 85,
    "status": "waiting_user"
  },
  "thinking_status": [
    {
      "event_type": "task_parsed",
      "title": "任务解析",
      "summary": "已识别材料 diamond、对象 CRL。"
    }
  ],
  "workflow_state": {
    "missing_slots": ["diamond_type", "laser_system", "post_processing_allowed"],
    "clarification_round": 1,
    "max_clarification_rounds": 3
  },
  "execution_trace": [
    {
      "event_type": "state_update",
      "title": "任务解析",
      "summary": "已识别材料 diamond、对象 CRL。"
    }
  ]
}
```

流式 `/chat/stream_ndjson` 会在 `delta` 前输出：

```json
{"type":"progress","workflow_type":"task_intake","stage":"clarification_round_1","progress_percent":40}
{"type":"thinking_status","event_type":"slot_check","summary":"仍缺少激光器参数范围。"}
{"type":"agent_trace","event_type":"state_update","title":"缺失字段检查","summary":"仍缺少激光器参数范围。"}
{"type":"delta","content":"..."}
{"type":"done"}
```

查看当前会话进度：

```http
GET http://127.0.0.1:8000/chat/sessions/{session_id}/progress
```

查看公开状态轨迹：

```http
GET http://127.0.0.1:8000/chat/sessions/{session_id}/thinking-status
```

查看完整公开 Agent 执行轨迹：

```http
GET http://127.0.0.1:8000/chat/sessions/{session_id}/agent-trace
```

PowerShell TUI 会在普通聊天回复前显示：

```text
[任务进度] [########------------] 40% clarification_round_1
[状态] 任务解析: 已识别材料 diamond、对象 CRL。
```

流式模式下，TUI 会实时识别 `progress`、`thinking_status`、`agent_trace` 和 `workflow_state` NDJSON 事件并打印同样的状态信息。

TUI 支持三种显示模式：

```text
/mode normal
/mode research
/mode debug
```

`normal` 尽量只看最终回复，`research` 显示任务状态和工具调用摘要，`debug` 额外显示 skill、tool、stage、输入输出摘要。三种模式都不得展示 hidden chain-of-thought。

## 数据库表

核心表包括：`raw_artifact`、`process_task`、`process_recipe`、`process_run`、`measurement_record`、`experience_candidate`、`validated_rule`、`bo_training_sample`、`external_source_artifact`、`knowledge_candidate`、`knowledge_review_task`、`knowledge_review_action`、`rag_document`、`rag_index_job`、`workflow_progress`、`reasoning_status_trace`、`agent_trace_event`、`equipment_profile`、`laser_source_config`、`optical_setup_config`、`motion_system_config`、`process_capability_config`、`equipment_config_revision`。

每条结构化记录保留 `artifact_id`，可追溯到归档原始文件和 SHA256。

## 设备参数配置与设备记忆

激光器功率、频率、扫描速度、脉宽和光斑是固定设备边界，不应在每个加工任务里反复追问。当前机床参数只要求：波长 nm、脉宽范围 fs、额定最大功率 W、实际最大功率 W、重复频率范围 kHz、扫描速度范围 mm/s、光斑直径 um。范围参数统一用 `最小值,最大值` 输入，例如 `脉宽范围fs（示例：500,8000）`、`重复频率范围kHz（示例：50,1000）`、`扫描速度范围mm/s（示例：10,3000）`。系统将这些信息保存到结构化设备记忆表：`equipment_profile` 保存主档，`laser_source_config`、`optical_setup_config`、`motion_system_config` 保存边界，`equipment_config_revision` 保存每次创建、更新和 active 切换的版本快照。

设备配置不是 RAG。任务解析和 BO 推荐必须读取结构化 `equipment_profile` / `machine_bounds`；RAG 只能用于解释背景，不能作为设备边界的权威来源。

创建 active 设备配置：

```http
POST http://127.0.0.1:8000/equipment/profiles
```

查看当前 active 设备和 BO 可用边界：

```http
GET http://127.0.0.1:8000/equipment/active
GET http://127.0.0.1:8000/equipment/active/machine-bounds
```

PowerShell TUI 菜单：

```text
[12] 配置设备参数
[13] 查看当前设备配置
[14] 切换当前设备配置
[15] 修改当前设备参数
```

创建 active profile 后，`/chat` 的 `workflow_state` 会返回 `equipment_profile_used`、`machine_bounds` 和 `missing_equipment_fields`。已配置的功率、频率和扫描速度不会再次作为普通追问；如果缺少光斑直径等字段，只追问具体缺失字段。

聊天 TUI 中可直接输入：

```text
/equipment show
/equipment edit
```

BO 默认要求 active equipment profile。没有 active profile 时，系统阻塞 BO 参数推荐并提示先配置设备参数，或显式提供任务级 `machine_bounds_override`。任务级 override 必须给出原因，且不得超过设备物理边界。所有 BO 推荐都应记录 `equipment_profile_id`、`revision_id` 和实际使用的 `machine_bounds`。

## 自学习机制边界

操作员备注只生成 `experience_candidate`。候选经验是待审核陈述，不是物理事实，也不是正式工艺规则。未经质量校验的数据不会进入 BO 训练样本。

## 当前 MVP 不做什么

不做实时 GUI、完整 RAG、真实 LLM API 调用、真实 BO 仓库集成、自动规则晋升、复杂 PDF 表格解析、多用户权限系统。

## 后续扩展

已预留 `knowledge/experience_extractor.py`、`rag/index_stub.py`、`bo/bo_engine_adapter.py`。后续可接入 LLM JSON schema extraction、向量索引和 `ultrafast-laser-bo-modeling`。

## PowerShell TUI 启动器

一键完成本地配置并启动聊天：

```powershell
ultrafast
```

该脚本会：

- 固定供应商为 DeepSeek；
- 首次运行让用户选择 `Flash` 或 `Pro`；
- 首次运行使用 `Read-Host -AsSecureString` 输入 API Key；
- 保存不含明文 key 的 LLM 配置，并用 Windows DPAPI 加密保存 API Key；
- 后续启动自动复用已有配置，不再重复选择模型或输入 API Key；
- 自动检查数据库 schema；
- 示例数据和 BO CSV 已存在时自动跳过扫描和导出；
- 自动后台启动 FastAPI；
- 首次未配置 active 设备参数时提示是否进入设备向导；
- 自动进入聊天界面。

如果尚未安装命令，先执行：

```powershell
python -m pip install -e .
```

强制重新选择模型或更新 API Key：

```powershell
ultrafast --reconfigure
```

强制重新扫描示例数据和导出 BO CSV：

```powershell
ultrafast --force-initialize
```

兼容旧启动方式仍可用：

```powershell
pwsh -ExecutionPolicy Bypass -File scripts/start_agent_tui.ps1
```

跳过 DeepSeek API Key 配置并使用 MockLLM：

```powershell
pwsh -ExecutionPolicy Bypass -File scripts/start_agent_tui.ps1 -SkipLlmConfig
```

本次会话不保存 LLM 配置：

```powershell
pwsh -ExecutionPolicy Bypass -File scripts/start_agent_tui.ps1 -NoSave
```

打开兼容旧功能的手动菜单：

```powershell
pwsh -ExecutionPolicy Bypass -File scripts/start_agent_tui.ps1 -ShowMenu
```

默认模型列表只是启动器默认值，实际可用模型以用户 API 服务商账户权限为准。DeepSeek API Base URL 自动使用 `https://api.deepseek.com`。

API Key 使用 `Read-Host -AsSecureString` 输入，不明文回显。`configs/llm.local.json` 只保存 provider/model/API base/key env 名，不保存明文 key。API Key 会保存到 `configs/secrets/*.dpapi`，由 Windows DPAPI 加密，仅当前 Windows 用户可解密；该目录已加入 `.gitignore`。

查看配置可在 TUI 菜单选择“查看配置”，或启动 FastAPI 后访问：

```http
GET http://127.0.0.1:8000/llm/config
POST http://127.0.0.1:8000/llm/test
```

接口不会返回真实 API Key，`/llm/test` 只检查配置完整性，不执行外部调用。

## 测试

```powershell
pytest
```

## RAG 文献知识库

系统支持两类文献资产进入同一 canonical 文献层：未整理 PDF，以及包含
`literature_cards.jsonl`、`paper_table.csv`、`paper_cards/*.json`、
`knowledge_candidates.jsonl` 等文件的结构化交付物。结构化元数据优先，PDF
作为原始证据补齐正文、页码和引用；字段冲突会标记 `needs_review`，不会静默覆盖。

### 盘点、导入与增量索引

```powershell
ultrafast literature inventory --root "超快智能体文献检索"
ultrafast literature ingest --root "超快智能体文献检索"
ultrafast literature list
ultrafast literature show <paper_id>

ultrafast rag create-index --name literature_default
ultrafast rag index --name literature_default
ultrafast rag status --name literature_default
ultrafast rag query "diamond CRL femtosecond laser machining"
```

导入按 SHA256、标准化 DOI、标题与年份去重。相同 PDF 不重复归档，相同 DOI
关联到同一个 `literature_paper`，相同 `paper_id + content_hash` 不重复建立 chunk。
重复执行 `ingest` 和 `rag index` 时，未变化记录会跳过。使用 `--force` 可以重新
解析或重建当前索引；更换 embedding provider、model 或 dimension 时应创建新索引，
不得覆盖旧索引，从而保留可审计性。

### 原始证据、chunk 与 Evidence Pack

PDF 使用 PyMuPDF 分页解析，页码统一为 1-based；章节按 Abstract、Methods、Results、
Discussion、Conclusion 等识别，References 默认不进入主索引。平均每页有效字符数
低于 50 的 PDF 标记为 `needs_ocr`，保留来源记录但不进入正文索引。本 MVP 不自动 OCR。

查询同时使用 SQLite FTS5（不可用时退化为关键词检索）和本地向量索引，通过 RRF
融合后执行 metadata filter 和规则 rerank。可过滤：

```text
scenario_id, material, material_grade, process_type, component_type,
laser_type, year_min, year_max, evidence_level, review_status, section_type
```

`POST /rag/query` 和 `/chat` 返回 Evidence Pack，其中包含 `paper_id`、`chunk_id`、
`page_start/page_end`、DOI、审核状态、适用范围及证据充足度。内部引用格式为：

```text
[paper_id, p.12, chunk_id]
```

主要 API：

```text
POST /literature/inventory
POST /literature/ingest
GET  /literature/ingestion-jobs/{job_id}
GET  /literature/papers
GET  /literature/papers/{paper_id}
GET  /literature/papers/{paper_id}/chunks
POST /rag/indexes
POST /rag/indexes/{index_id}/index
POST /rag/query
```

质量报告写入：

```text
data/reports/literature_quality_report.json
data/reports/literature_quality_report.md
```

### 审核和 BO 硬边界

RAG 是检索层，不是正式规则库。`literature_chunk` 保存可追溯原文；从文献抽取的
结论继续写入现有 `knowledge_candidate`，保持 `pending_review` 并创建审核任务。

必须遵守：

1. RAG 只能引用已入库 chunk，不得伪造论文、作者、DOI、页码或来源；
2. `pending_review` 必须标记为候选证据，`rejected` 内容不得返回；
3. `not_usable_for` 在检索和回答阶段都生效；
4. `evidence_status=insufficient` 时不得给出确定性工艺结论；
5. 文献参数不得自动写入 `process_prior`、`validated_rule` 或 `bo_training_sample`；
6. RAG 不得覆盖结构化设备边界，BO 仍以 active equipment profile 为硬约束；
7. 原始 PDF 和既有 CSV/JSON 不删除、不覆盖，只在独立归档和数据库中生成派生数据。
