# Codex 任务说明：新增 NDJSON Streaming 与混合 Skill Router

## 0. 任务背景

当前项目已经完成最小聊天闭环：

```text
PowerShell TUI
→ POST /chat
→ FastAPI Chat Orchestrator
→ Session Manager
→ Skill Router
→ LLM Adapter / MockLLM
→ 保存会话与审计记录
→ 返回智能体回复
```

但当前实现仍有两个限制：

```text
1. 聊天输出是非流式响应，终端体验较差；
2. Skill Router 主要依赖关键词规则，容易误判复杂多意图输入。
```

本任务目标是：

```text
1. 为 PowerShell TUI 增加 NDJSON streaming 聊天能力；
2. 将 skill router 从 selected_skill 单点输出升级为 route_plan；
3. 新增 session_state，让智能体能理解多轮澄清上下文；
4. 新增 LLM router，用于处理规则难以判断的复杂意图；
5. 新增调试与手动覆盖指令，方便开发期间测试。
```

重要原则：

```text
不要直接把 router 改成纯 LLM 路由。
正确路线是：manual override + session state + rule router + LLM router + fallback。
```

---

## 1. 总体目标

实现新的聊天路由与流式输出架构：

```text
PowerShell TUI
→ /chat 或 /chat/stream_ndjson
→ Session State
→ Manual Override
→ Rule Router
→ LLM Router
→ Route Plan
→ Skill Execution Stub
→ LLM / MockLLM Streaming
→ Audit Trace
```

MVP 阶段不要求真正执行 RAG、BO、文件自学习工具，但必须预留 tool trace 和 route_plan 结构。

---

## 2. 必须实现的能力

本任务必须完成：

```text
1. 新增 POST /chat/stream_ndjson；
2. 支持 application/x-ndjson 流式返回；
3. PowerShell TUI 支持流式聊天；
4. 支持 /stream on 和 /stream off；
5. MockLLMClient 支持 stream_chat；
6. OpenAICompatibleClient 支持 stream_chat；
7. 新增 chat_session_state 表；
8. 新增 chat_route_trace 表；
9. 将 selected_skill 升级为 route_plan；
10. 保留兼容字段 selected_skill；
11. 新增 manual override 指令；
12. 新增 rule router；
13. 新增 LLM router；
14. 新增 hybrid router；
15. 新增 /debug router on/off；
16. 新增 /state、/reset、/routes 等调试命令；
17. pytest 覆盖 streaming 和 router。
```

---

## 3. 明确不做

MVP 阶段不做：

```text
1. 不做 Web SSE 前端；
2. 不要求浏览器 SSE；
3. 不做复杂 tool calling；
4. 不真正调用 RAG；
5. 不真正调用 BO；
6. 不做会话摘要压缩；
7. 不做多用户权限；
8. 不做 GUI；
9. 不做长期任务自动运行；
10. 不把 PowerShell 做成复杂前端。
```

---

## 4. 推荐实现顺序

请 Codex 按以下顺序实现：

```text
Phase 1：数据库新增 session_state 和 route_trace；
Phase 2：route_plan schema；
Phase 3：manual override 和调试命令；
Phase 4：session_state 管理；
Phase 5：rule router 重构；
Phase 6：LLM router stub / real implementation；
Phase 7：hybrid router；
Phase 8：chat service 支持 route_plan；
Phase 9：MockLLM stream_chat；
Phase 10：OpenAICompatibleClient stream_chat；
Phase 11：/chat/stream_ndjson；
Phase 12：PowerShell TUI streaming；
Phase 13：测试和 README。
```

优先重构 router，再做 streaming。  
原因：如果路由错误，streaming 只是更快地输出错误结果。

---

## 5. 新增/修改目录结构

在现有项目中新增或修改：

```text
src/
  ultrafast_memory/
    chat/
      schemas.py
      service.py
      session_store.py
      session_state.py
      prompt_builder.py

      router/
        __init__.py
        schemas.py
        manual_override.py
        rule_router.py
        llm_router.py
        hybrid_router.py
        debug_commands.py

    llm/
      base.py
      mock.py
      openai_compatible.py
      anthropic.py
      factory.py

tests/
  test_stream_ndjson.py
  test_streaming_mock_llm.py
  test_router_manual_override.py
  test_router_session_state.py
  test_router_hybrid.py
  test_chat_route_plan.py

scripts/
  powershell/
    AgentTui.psm1
  start_agent_tui.ps1
```

如果已有文件，请在原有文件中增量修改，不要重复创建冲突模块。

---

## 6. 数据库新增表

### 6.1 `chat_session_state`

用于保存多轮任务状态。

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
    debug_router INTEGER DEFAULT 0,
    streaming_enabled INTEGER DEFAULT 0,
    updated_at TEXT
);
```

字段说明：

```text
active_workflow：
当前活跃工作流，例如 diamond_crl_planning、file_ingestion、bo_optimization。

active_skill：
当前正在执行或等待补充信息的 skill。

workflow_stage：
当前阶段，例如 intake、clarification、planning、waiting_for_file、ready_for_bo。

collected_slots_json：
已经收集到的结构化槽位。

pending_questions_json：
上一轮系统提出、等待用户回答的问题。

allowed_next_skills_json：
当前 workflow 允许的后续 skill。

debug_router：
是否开启 router 调试输出。

streaming_enabled：
当前 session 是否默认使用 streaming。
```

### 6.2 `chat_route_trace`

替代或补充原 `chat_skill_trace`。

```sql
CREATE TABLE chat_route_trace (
    trace_id TEXT PRIMARY KEY,
    session_id TEXT,
    message_id TEXT,
    route_source TEXT,
    route_plan_json TEXT,
    confidence REAL,
    created_at TEXT
);
```

`route_source` 允许：

```text
manual_override
session_state
rule_router
llm_router
hybrid_router
fallback
```

### 6.3 兼容性要求

如果已有 `chat_skill_trace`，不要删除。  
可以继续写入 `selected_skill`，但新的主记录应写入 `chat_route_trace`。

---

## 7. Route Plan Schema

新增：

```text
src/ultrafast_memory/chat/router/schemas.py
```

建议使用 Pydantic。

### 7.1 `RoutePlan`

```python
from pydantic import BaseModel, Field
from typing import Any, Optional

class BlockedTool(BaseModel):
    tool: str
    reason: str

class StateUpdate(BaseModel):
    active_workflow: Optional[str] = None
    active_skill: Optional[str] = None
    workflow_stage: Optional[str] = None
    collected_slots: dict[str, Any] = Field(default_factory=dict)
    pending_questions: list[str] = Field(default_factory=list)
    allowed_next_skills: list[str] = Field(default_factory=list)

class RoutePlan(BaseModel):
    route_type: str = "agent_workflow"
    primary_skill: str
    secondary_skills: list[str] = Field(default_factory=list)
    intent: str = "unknown"
    workflow_stage: str = "unknown"
    confidence: float = 0.0
    reason: str = ""
    requires_clarification: bool = False
    clarification_questions: list[str] = Field(default_factory=list)
    allowed_tools: list[str] = Field(default_factory=list)
    blocked_tools: list[BlockedTool] = Field(default_factory=list)
    state_update: StateUpdate = Field(default_factory=StateUpdate)
    route_source: str = "unknown"
```

### 7.2 最小 JSON 示例

```json
{
  "route_type": "agent_workflow",
  "primary_skill": "crl_task_planning",
  "secondary_skills": [
    "rag_literature_retrieval",
    "bo_recommendation"
  ],
  "intent": "diamond_crl_manufacturing_planning",
  "workflow_stage": "clarification",
  "confidence": 0.87,
  "reason": "用户输入包含金刚石 CRL 几何与粗糙度目标，但缺少设备边界和材料类型。",
  "requires_clarification": true,
  "clarification_questions": [
    "金刚石是单晶、CVD 多晶还是 HPHT？",
    "现有激光器的波长、脉宽、最大功率和频率范围是多少？",
    "是否允许后处理？"
  ],
  "allowed_tools": [
    "memory_query",
    "rag_search"
  ],
  "blocked_tools": [
    {
      "tool": "bo_recommendation",
      "reason": "缺少设备边界和优化变量范围。"
    }
  ],
  "state_update": {
    "active_workflow": "diamond_crl_planning",
    "active_skill": "crl_task_planning",
    "workflow_stage": "clarification",
    "collected_slots": {
      "material": "diamond",
      "component": "CRL"
    },
    "pending_questions": [
      "diamond_type",
      "laser_system",
      "post_processing_allowed"
    ],
    "allowed_next_skills": [
      "rag_literature_retrieval",
      "bo_recommendation",
      "report_generation"
    ]
  },
  "route_source": "hybrid_router"
}
```

---

## 8. Manual Override 与调试命令

新增：

```text
src/ultrafast_memory/chat/router/manual_override.py
src/ultrafast_memory/chat/router/debug_commands.py
```

### 8.1 支持命令

必须支持：

```text
/skill <skill_name>
/debug router on
/debug router off
/state
/reset
/routes
/stream on
/stream off
/no_skill
```

### 8.2 `/skill <skill_name>`

示例：

```text
/skill bo_recommendation
```

输出 route_plan：

```json
{
  "primary_skill": "bo_recommendation",
  "route_source": "manual_override",
  "confidence": 1.0,
  "reason": "User manually selected skill."
}
```

### 8.3 `/debug router on/off`

修改 `chat_session_state.debug_router`。

开启后，`/chat` 和 `/chat/stream_ndjson` 返回中应包含 router 调试信息。

### 8.4 `/state`

返回当前 session state，不调用 LLM。

### 8.5 `/reset`

清空当前 session_state：

```text
active_workflow = null
active_skill = null
workflow_stage = null
collected_slots = {}
pending_questions = []
allowed_next_skills = []
```

不删除聊天历史。

### 8.6 `/routes`

返回可用 skill 列表和说明。

### 8.7 `/stream on/off`

修改当前 session 的 `streaming_enabled`。

PowerShell TUI 可以据此选择调用 `/chat` 或 `/chat/stream_ndjson`。

---

## 9. Session State 管理

新增：

```text
src/ultrafast_memory/chat/session_state.py
```

提供函数：

```python
get_session_state(session_id: str) -> dict
create_or_get_session_state(session_id: str) -> dict
update_session_state(session_id: str, state_update: dict) -> dict
reset_session_state(session_id: str) -> None
set_debug_router(session_id: str, enabled: bool) -> None
set_streaming_enabled(session_id: str, enabled: bool) -> None
```

### 9.1 Session State 优先级

router 必须先检查 session state。

如果：

```text
active_skill 不为空；
workflow_stage == clarification；
pending_questions 非空；
用户输入看起来是在回答上一轮问题；
```

则优先继续当前 active_skill。

例如：

```text
上一轮 pending_questions:
["diamond_type", "laser_system", "post_processing_allowed"]

用户输入：
“单晶金刚石，1030nm，300fs，最大功率20W，可以后处理。”

应继续：
crl_task_planning
```

不得因为出现 `20W` 就跳到 `bo_recommendation`。

---

## 10. Rule Router 重构

新增：

```text
src/ultrafast_memory/chat/router/rule_router.py
```

函数：

```python
def rule_route(message: str, session_state: dict | None = None) -> RoutePlan | None:
    ...
```

规则优先级：

```text
process_file_ingestion
> bo_recommendation
> crl_task_planning
> rag_literature_retrieval
> experience_memory_update
> report_generation
> task_intake
```

### 10.1 高置信规则

高置信规则 confidence >= 0.9：

```text
用户显式输入：
/skill xxx
导入日志
扫描 recipe
读取 csv
导出 BO 数据
```

### 10.2 中等置信规则

confidence 0.5–0.9：

```text
包含多个领域关键词；
可能涉及多个 skill；
需要 LLM router 复核。
```

示例：

```text
“我这个 CRL 加工后表面发黑，粗糙度没到目标，下一步该怎么调？”
```

规则 router 应给候选：

```json
{
  "primary_skill": "experience_memory_update",
  "secondary_skills": [
    "crl_task_planning",
    "bo_recommendation"
  ],
  "confidence": 0.65,
  "reason": "包含失败现象、CRL 对象和下一轮调参意图。"
}
```

### 10.3 低置信规则

confidence < 0.5：

交给 LLM router 或 fallback 到 `task_intake`。

---

## 11. LLM Router

新增：

```text
src/ultrafast_memory/chat/router/llm_router.py
```

函数：

```python
def llm_route(message: str, session_state: dict, candidate_route: RoutePlan | None = None) -> RoutePlan:
    ...
```

### 11.1 LLM Router Prompt

必须短，不加载完整 skill 文档。

Prompt 核心：

```text
你是超快激光智能体的路由器。
你的任务是根据用户消息、session_state 和候选规则路由，输出 route_plan JSON。
不要回答用户问题。
不要生成加工参数。
只能选择已有 skill。
如果信息不足，设置 requires_clarification=true。
```

Skill 列表：

```json
{
  "task_intake": "模糊任务解析和追问",
  "crl_task_planning": "金刚石 CRL / X-ray 透镜制造规划",
  "rag_literature_retrieval": "文献检索和证据提取",
  "bo_recommendation": "贝叶斯优化参数推荐",
  "process_file_ingestion": "日志、工艺文件、检测结果导入",
  "experience_memory_update": "经验候选和规则沉淀",
  "bo_dataset_governance": "判断实验记录能否进入 BO 训练集",
  "report_generation": "生成任务方案、执行清单或报告"
}
```

### 11.2 无 API Key 情况

如果 LLM 不可用，`llm_route` 不得崩溃。  
应返回 candidate_route 或 fallback：

```text
candidate_route 存在 → 使用 candidate_route
candidate_route 不存在 → task_intake
```

### 11.3 JSON 修复

LLM router 输出必须经过 JSON parse 和 Pydantic 校验。  
失败时回退到 candidate_route 或 task_intake。

---

## 12. Hybrid Router

新增：

```text
src/ultrafast_memory/chat/router/hybrid_router.py
```

主函数：

```python
def route_message(message: str, session_id: str, use_llm_router: bool = True) -> RoutePlan:
    ...
```

执行顺序：

```text
1. 检查 manual override / debug command；
2. 读取 session_state；
3. 如果命中 session_state continuation，则返回 session_state route；
4. 调用 rule_router，得到 candidate_route；
5. 如果 candidate_route.confidence >= 0.9，直接采用；
6. 如果 0.5 <= confidence < 0.9 且 use_llm_router=true，调用 LLM router 复核；
7. 如果 confidence < 0.5 且 use_llm_router=true，调用 LLM router；
8. 如果 LLM router 失败，fallback；
9. 写入 chat_route_trace；
10. 应用 state_update。
```

### 12.1 Fallback

```json
{
  "primary_skill": "task_intake",
  "confidence": 0.3,
  "reason": "Router confidence is low; fallback to task intake.",
  "requires_clarification": true,
  "route_source": "fallback"
}
```

---

## 13. Chat Service 修改

修改：

```text
src/ultrafast_memory/chat/service.py
```

原逻辑如果只返回 `selected_skill`，需要改为 route_plan。

### 13.1 `/chat` 响应兼容

返回中保留：

```json
{
  "selected_skill": "crl_task_planning"
}
```

但新增：

```json
{
  "route_plan": {
    "primary_skill": "crl_task_planning",
    "secondary_skills": [],
    "confidence": 0.87,
    "route_source": "hybrid_router"
  }
}
```

### 13.2 ChatResponse schema 修改

```python
class ChatResponse(BaseModel):
    session_id: str
    assistant_message: str
    selected_skill: str | None = None
    route_plan: dict | None = None
    tool_calls: list = []
    audit_trace: list = []
```

### 13.3 Prompt Builder 修改

`prompt_builder` 应根据 `route_plan.primary_skill` 构造系统提示。

MVP 阶段不需要加载完整 SKILL.md。  
后续再接 `agent_skills/`。

---

## 14. NDJSON Streaming 设计

### 14.1 新增接口

```http
POST /chat/stream_ndjson
```

请求体同 `/chat`：

```json
{
  "session_id": "sess_xxx",
  "message": "我想加工金刚石CRL，Ra小于460nm",
  "mode": "agent",
  "use_skills": true,
  "stream": true
}
```

响应头：

```text
Content-Type: application/x-ndjson
```

### 14.2 事件格式

每一行一个 JSON 对象。

事件类型：

```text
meta
route
trace
delta
warning
error
done
```

### 14.3 示例输出

```json
{"type":"meta","session_id":"sess_001","model":"mock","provider":"mock"}
{"type":"route","primary_skill":"crl_task_planning","confidence":0.87,"route_source":"hybrid_router"}
{"type":"trace","step":"skill_router","status":"success"}
{"type":"delta","content":"我已识别为金刚石 CRL 制造任务。"}
{"type":"delta","content":"当前信息不足以直接推荐激光参数。"}
{"type":"done"}
```

---

## 15. LLM Streaming Interface

修改：

```text
src/ultrafast_memory/llm/base.py
```

新增：

```python
from collections.abc import Iterator

class BaseLLMClient(ABC):
    @abstractmethod
    def chat(self, messages: list[dict[str, str]], **kwargs) -> dict:
        raise NotImplementedError

    def stream_chat(self, messages: list[dict[str, str]], **kwargs) -> Iterator[dict]:
        result = self.chat(messages, **kwargs)
        yield {
            "type": "delta",
            "content": result.get("content", "")
        }
        yield {"type": "done"}
```

### 15.1 MockLLMClient

`MockLLMClient.stream_chat` 应分块输出：

```python
for chunk in ["[MockLLM] ", "已收到：", last_user_message]:
    yield {"type": "delta", "content": chunk}
yield {"type": "done"}
```

### 15.2 OpenAICompatibleClient

实现 OpenAI-Compatible streaming：

请求体增加：

```json
{
  "stream": true
}
```

解析返回流中的：

```text
data: {...}
data: [DONE]
```

并转换为内部事件：

```json
{"type":"delta","content":"..."}
```

注意：

```text
OpenAI-compatible 服务商的 streaming 格式可能略有差异。
解析失败时必须返回 error event，不得崩溃。
```

---

## 16. FastAPI Streaming 实现

在：

```text
src/ultrafast_memory/app/api.py
```

新增：

```python
@app.post("/chat/stream_ndjson")
def chat_stream_ndjson(request: ChatRequest):
    ...
```

建议在 `chat/service.py` 中实现：

```python
def handle_chat_stream_ndjson(request: ChatRequest):
    yield {"type": "meta", ...}
    yield {"type": "route", ...}
    yield {"type": "trace", ...}
    for event in client.stream_chat(...):
        yield event
    yield {"type": "done"}
```

FastAPI 层只负责：

```python
def to_ndjson(events):
    for event in events:
        yield json.dumps(event, ensure_ascii=False) + "\n"
```

返回：

```python
return StreamingResponse(
    to_ndjson(handle_chat_stream_ndjson(request)),
    media_type="application/x-ndjson"
)
```

### 16.1 错误处理

如果中途错误：

```json
{"type":"error","message":"..."}
{"type":"done"}
```

不得直接断开而无解释。

---

## 17. PowerShell TUI Streaming

修改：

```text
scripts/powershell/AgentTui.psm1
```

### 17.1 新增函数

```powershell
Send-AgentChatStream
Set-AgentStreamMode
Get-AgentStreamMode
```

### 17.2 聊天模式逻辑

如果当前 session `streaming_enabled == true`，调用：

```text
POST /chat/stream_ndjson
```

否则调用：

```text
POST /chat
```

### 17.3 PowerShell NDJSON 消费

使用 `.NET HttpClient`，不要用 `Invoke-RestMethod` 处理 streaming。

示例：

```powershell
function Send-AgentChatStream {
    param(
        [string]$SessionId,
        [string]$Message
    )

    $body = @{
        session_id = $SessionId
        message = $Message
        mode = "agent"
        use_skills = $true
        stream = $true
    } | ConvertTo-Json -Depth 10

    $client = [System.Net.Http.HttpClient]::new()
    $content = [System.Net.Http.StringContent]::new($body, [System.Text.Encoding]::UTF8, "application/json")

    $request = [System.Net.Http.HttpRequestMessage]::new(
        [System.Net.Http.HttpMethod]::Post,
        "http://127.0.0.1:8000/chat/stream_ndjson"
    )
    $request.Content = $content

    $response = $client.SendAsync(
        $request,
        [System.Net.Http.HttpCompletionOption]::ResponseHeadersRead
    ).Result

    $stream = $response.Content.ReadAsStreamAsync().Result
    $reader = [System.IO.StreamReader]::new($stream)

    while (-not $reader.EndOfStream) {
        $line = $reader.ReadLine()

        if ([string]::IsNullOrWhiteSpace($line)) {
            continue
        }

        $event = $line | ConvertFrom-Json

        switch ($event.type) {
            "meta" {
                if ($event.provider) {
                    Write-Host "[provider: $($event.provider), model: $($event.model)]" -ForegroundColor DarkGray
                }
            }
            "route" {
                Write-Host "[skill: $($event.primary_skill), confidence: $($event.confidence)]" -ForegroundColor DarkGray
            }
            "trace" {
                # 默认不打印，可在 debug router on 时打印
            }
            "delta" {
                Write-Host -NoNewline $event.content
            }
            "warning" {
                Write-Host ""
                Write-Host "[warning] $($event.message)" -ForegroundColor Yellow
            }
            "error" {
                Write-Host ""
                Write-Host "[error] $($event.message)" -ForegroundColor Red
            }
            "done" {
                Write-Host ""
                break
            }
        }
    }
}
```

---

## 18. Chat 命令支持

在聊天循环中识别以下命令，并直接发送给 `/chat`：

```text
/skill bo_recommendation
/debug router on
/debug router off
/state
/reset
/routes
/stream on
/stream off
/no_skill
exit
```

`exit` 本地处理，退出聊天。  
其他 slash 命令交给后端处理，让后端统一更新 session_state。

---

## 19. API 响应变化

### 19.1 `/chat`

返回示例：

```json
{
  "session_id": "sess_001",
  "assistant_message": "我已识别为金刚石 CRL 制造任务……",
  "selected_skill": "crl_task_planning",
  "route_plan": {
    "primary_skill": "crl_task_planning",
    "secondary_skills": [
      "rag_literature_retrieval"
    ],
    "confidence": 0.87,
    "route_source": "hybrid_router",
    "requires_clarification": true
  },
  "tool_calls": [],
  "audit_trace": [
    {
      "step": "hybrid_router",
      "status": "success"
    }
  ]
}
```

### 19.2 `/chat/stream_ndjson`

必须返回 route event：

```json
{"type":"route","primary_skill":"crl_task_planning","confidence":0.87,"route_source":"hybrid_router"}
```

---

## 20. 测试要求

### 20.1 `test_router_manual_override.py`

测试：

```text
/skill bo_recommendation → primary_skill=bo_recommendation, route_source=manual_override
/debug router on → session_state.debug_router=true
/stream on → session_state.streaming_enabled=true
/reset → 清空 active_workflow 等字段
/routes → 返回可用 skill 列表
```

### 20.2 `test_router_session_state.py`

测试：

```text
已有 active_skill=crl_task_planning 且 pending_questions 非空；
用户输入“单晶，1030nm，300fs，最大功率20W”；
router 应继续 crl_task_planning；
不得跳到 bo_recommendation。
```

### 20.3 `test_router_hybrid.py`

测试：

```text
高置信规则 → 不调用 LLM router；
中等置信规则 → 调用 LLM router；
LLM 不可用 → fallback 到 candidate_route；
低置信输入 → fallback task_intake。
```

### 20.4 `test_streaming_mock_llm.py`

测试：

```text
MockLLMClient.stream_chat 产生多个 delta；
最后产生 done；
不需要 API Key。
```

### 20.5 `test_stream_ndjson.py`

测试 FastAPI：

```text
POST /chat/stream_ndjson 返回 application/x-ndjson；
至少包含 meta、route、delta、done；
每一行都是合法 JSON；
响应中不包含 API Key。
```

### 20.6 `test_chat_route_plan.py`

测试：

```text
POST /chat 返回 route_plan；
兼容字段 selected_skill 存在；
chat_route_trace 被写入；
chat_session_state 被更新。
```

---

## 21. README 更新

README 新增章节：

```text
Streaming Chat 与混合 Router
```

必须说明：

```text
1. 为什么 PowerShell 使用 NDJSON 而不是 SSE；
2. 如何开启 streaming；
3. 如何关闭 streaming；
4. slash commands 列表；
5. router 的执行顺序；
6. manual override 的用途；
7. session_state 的作用；
8. 当前不支持 Web SSE；
9. 当前不真正执行 RAG/BO；
10. 如何查看 router 调试输出。
```

示例：

```text
/stream on
/stream off
/debug router on
/state
/skill bo_recommendation
/reset
```

---

## 22. 验收标准

### 22.1 单元测试

```bash
pytest -q
```

必须通过。

### 22.2 非流式 API

```bash
curl -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"我想加工金刚石CRL，Ra小于460nm","use_skills":true}'
```

预期：

```text
1. 返回 assistant_message；
2. 返回 selected_skill；
3. 返回 route_plan；
4. route_plan.primary_skill = crl_task_planning；
5. 数据库写入 chat_route_trace。
```

### 22.3 流式 API

```bash
curl -N -X POST http://127.0.0.1:8000/chat/stream_ndjson \
  -H "Content-Type: application/json" \
  -d '{"message":"我想加工金刚石CRL，Ra小于460nm","use_skills":true,"stream":true}'
```

预期输出包含：

```json
{"type":"meta",...}
{"type":"route",...}
{"type":"delta",...}
{"type":"done"}
```

### 22.4 PowerShell TUI

```powershell
powershell -ExecutionPolicy Bypass -File scripts/start_agent_tui.ps1 -SkipLlmConfig
```

进入聊天后：

```text
/stream on
我想加工金刚石CRL，Ra小于460nm
```

预期：

```text
1. TUI 流式打印回复；
2. 显示 skill 和 confidence；
3. 输入 /stream off 后恢复非流式；
4. 输入 /state 可查看状态；
5. 输入 /reset 可重置状态；
6. 输入 exit 可退出聊天。
```

---

## 23. 安全要求

```text
1. API Key 不得出现在 route_plan；
2. API Key 不得出现在 NDJSON events；
3. API Key 不得出现在 chat_route_trace；
4. API Key 不得出现在 chat_session_state；
5. API Key 不得被 PowerShell 打印；
6. 测试不得使用真实 API Key；
7. LLM router prompt 不得包含 API Key；
8. 错误 event 不得泄露请求 headers。
```

---

## 24. 关键设计判断

### 24.1 为什么不用纯 SSE？

```text
SSE 更适合浏览器。
PowerShell 解析 SSE 较繁琐。
NDJSON 更适合 CLI/TUI。
```

后续如果做 Web UI，可以新增：

```text
POST /chat/stream_sse
```

但本任务先不做。

### 24.2 为什么不用纯 LLM Router？

```text
纯 LLM Router 不稳定、难调试、成本高。
规则 router 对显式命令和高置信场景更可靠。
session_state 对多轮澄清至关重要。
manual override 对开发调试至关重要。
```

因此采用：

```text
manual override
→ session state
→ rule router
→ LLM router
→ fallback
```

### 24.3 为什么 route_plan 优于 selected_skill？

复杂用户输入往往包含多个意图。  
例如：

```text
“我上传了金刚石 CRL 的加工记录，表面发黑，Ra 没达标，下一轮怎么调？”
```

该输入同时涉及：

```text
process_file_ingestion
experience_memory_update
crl_task_planning
bo_recommendation
report_generation
```

单一 `selected_skill` 无法表达这种执行计划。  
`route_plan` 可以表达主 skill、辅助 skill、工具阻塞原因、追问问题和状态更新。

---

## 25. 后续扩展预留

本任务完成后可继续：

```text
1. 根据 route_plan 加载 agent_skills/<skill>/SKILL.md；
2. 将 route_plan 交给真实 skill executor；
3. 接入 RAG；
4. 接入 BO；
5. 接入 process_file_ingestion tool；
6. 支持 Web SSE；
7. 支持 Python Textual TUI；
8. 支持会话摘要压缩；
9. 支持 route_plan 可视化；
10. 支持多步 tool execution。
```

---

## 26. 一句话总结

本任务要把当前聊天系统从：

```text
TUI → /chat → selected_skill → LLM response
```

升级为：

```text
TUI → /chat 或 /chat/stream_ndjson
→ session_state
→ manual override / rule router / LLM router
→ route_plan
→ LLM streaming
→ audit trace
```

目标不是追求复杂，而是让聊天入口具备长期扩展到 RAG、BO、自学习和多轮任务规划的结构基础。
