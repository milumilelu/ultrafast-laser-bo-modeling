# Codex 任务说明：为超快激光智能体新增聊天闭环

## 0. 任务背景

当前项目已经具备：

```text
1. PowerShell TUI 启动器；
2. LLM 服务商与模型选择；
3. API Key 输入与环境变量配置；
4. FastAPI 后端启动；
5. 数据库初始化；
6. 文件扫描；
7. BO 数据导出；
8. LLM 配置状态接口。
```

但当前 TUI 仍只是“启动器/配置器”，不能进行真正的聊天。

本任务目标是新增一个最小可用的聊天闭环，并将其设计为后续接入 skill、RAG、BO、自学习记忆库的统一入口。

重要判断：

```text
不要把 /chat 做成普通 LLM proxy。
/chat 必须从第一版开始设计成 Agent Orchestrator 入口。
```

---

## 1. 总体目标

实现以下闭环：

```text
PowerShell TUI
→ POST /chat
→ FastAPI Chat Orchestrator
→ Session Manager
→ Skill Router
→ LLM Provider Adapter
→ 保存会话与审计记录
→ 返回智能体回复
```

MVP 阶段暂不要求真正调用 RAG、BO 或文件自学习工具，但必须预留工具调用和审计结构。

---

## 2. 必须实现的能力

本次任务必须完成：

```text
1. 新增聊天数据库表；
2. 新增 LLM provider adapter；
3. 新增 OpenAI-Compatible 调用能力；
4. 新增 MockLLMClient，用于无 API Key 测试；
5. 新增 POST /chat/sessions；
6. 新增 POST /chat；
7. 新增 GET /chat/sessions/{session_id}/messages；
8. 新增规则版 skill_router；
9. PowerShell TUI 主菜单新增 [9] 进入聊天；
10. PowerShell 实现聊天循环；
11. 聊天记录持久化；
12. skill 路由结果持久化；
13. API Key 不得返回、打印或写入日志；
14. pytest 覆盖核心流程。
```

---

## 3. 明确不做

MVP 阶段不做：

```text
1. 不做 streaming；
2. 不做 Web Chat 前端；
3. 不做真实 RAG 调用；
4. 不做真实 BO 调用；
5. 不做复杂 tool calling；
6. 不做文件上传聊天；
7. 不做多用户权限系统；
8. 不做自动总结长期会话；
9. 不做真实 Anthropic API 调用，先预留 adapter。
```

---

## 4. 新增目录结构

在现有项目中新增或补充以下结构：

```text
src/
  ultrafast_memory/
    chat/
      __init__.py
      schemas.py
      service.py
      session_store.py
      prompt_builder.py
      skill_router.py

    llm/
      __init__.py
      base.py
      openai_compatible.py
      anthropic.py
      mock.py
      factory.py

tests/
  test_chat_api.py
  test_chat_service.py
  test_llm_factory.py
  test_skill_router.py

scripts/
  start_agent_tui.ps1
  powershell/
    AgentTui.psm1
```

如果现有项目已有类似目录，请在原有结构上合并，不要重复创建冲突模块。

---

## 5. 数据库新增表

如果项目使用 SQLAlchemy ORM，请同步新增 ORM model 和初始化逻辑。

### 5.1 `chat_session`

```sql
CREATE TABLE chat_session (
    session_id TEXT PRIMARY KEY,
    title TEXT,
    mode TEXT,
    created_at TEXT,
    updated_at TEXT,
    status TEXT
);
```

字段说明：

```text
session_id：会话 ID
title：会话标题
mode：chat / agent
status：active / archived
```

### 5.2 `chat_message`

```sql
CREATE TABLE chat_message (
    message_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT,
    metadata_json TEXT
);
```

`role` 允许：

```text
system
user
assistant
tool
```

### 5.3 `chat_skill_trace`

```sql
CREATE TABLE chat_skill_trace (
    trace_id TEXT PRIMARY KEY,
    session_id TEXT,
    message_id TEXT,
    selected_skill TEXT,
    confidence REAL,
    reason TEXT,
    created_at TEXT
);
```

### 5.4 `chat_tool_trace`

```sql
CREATE TABLE chat_tool_trace (
    trace_id TEXT PRIMARY KEY,
    session_id TEXT,
    message_id TEXT,
    tool_name TEXT,
    input_json TEXT,
    output_json TEXT,
    status TEXT,
    created_at TEXT,
    error_message TEXT
);
```

MVP 阶段 tool_trace 可以为空，但表必须存在。

---

## 6. Chat Schemas

实现：

```text
src/ultrafast_memory/chat/schemas.py
```

建议使用 Pydantic。

### 6.1 `CreateChatSessionRequest`

```python
from pydantic import BaseModel
from typing import Optional

class CreateChatSessionRequest(BaseModel):
    title: Optional[str] = None
    mode: str = "agent"
```

### 6.2 `CreateChatSessionResponse`

```python
class CreateChatSessionResponse(BaseModel):
    session_id: str
    title: str
    mode: str
    created_at: str
```

### 6.3 `ChatRequest`

```python
class ChatRequest(BaseModel):
    session_id: Optional[str] = None
    message: str
    mode: str = "agent"
    use_skills: bool = True
    stream: bool = False
```

### 6.4 `ChatResponse`

```python
class ChatResponse(BaseModel):
    session_id: str
    assistant_message: str
    selected_skill: Optional[str] = None
    tool_calls: list = []
    audit_trace: list = []
```

### 6.5 `ChatMessageView`

```python
class ChatMessageView(BaseModel):
    message_id: str
    session_id: str
    role: str
    content: str
    created_at: str
    metadata: dict = {}
```

---

## 7. LLM Adapter 设计

新增：

```text
src/ultrafast_memory/llm/
```

### 7.1 `base.py`

```python
from abc import ABC, abstractmethod
from typing import Any

class BaseLLMClient(ABC):
    @abstractmethod
    def chat(self, messages: list[dict[str, str]], **kwargs: Any) -> dict:
        raise NotImplementedError
```

统一返回格式：

```python
{
    "content": "assistant reply",
    "raw": {},
    "provider": "openai",
    "model": "gpt-4.1-mini"
}
```

### 7.2 `mock.py`

用于无 API Key、离线测试、CI 测试。

```python
class MockLLMClient(BaseLLMClient):
    def chat(self, messages: list[dict[str, str]], **kwargs) -> dict:
        last_user_message = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                last_user_message = m.get("content", "")
                break

        return {
            "content": f"[MockLLM] 已收到：{last_user_message}",
            "raw": {},
            "provider": "mock",
            "model": "mock"
        }
```

### 7.3 `openai_compatible.py`

实现 OpenAI-Compatible Chat Completions 调用。

适用 provider：

```text
openai
deepseek
moonshot
qwen
glm
local
```

从配置中读取：

```text
provider
model
api_base
api_key_env
```

使用环境变量读取真实 API Key：

```python
api_key = os.getenv(api_key_env)
```

不得打印 API Key。

请求：

```http
POST {api_base}/chat/completions
```

请求体：

```json
{
  "model": "...",
  "messages": [...],
  "temperature": 0.2
}
```

注意：

```text
如果 api_base 已经包含 /v1，不要重复拼接 /v1。
如果 api_base 不包含 /v1，由配置决定，不要硬编码强行添加。
```

建议用标准库 `urllib.request` 或 `httpx`。  
如果新增 `httpx`，请更新依赖文件。

### 7.4 `anthropic.py`

MVP 只做 stub。

```python
class AnthropicClient(BaseLLMClient):
    def chat(self, messages: list[dict[str, str]], **kwargs) -> dict:
        raise NotImplementedError("Anthropic adapter is not implemented in MVP.")
```

### 7.5 `factory.py`

```python
def create_llm_client(config: dict) -> BaseLLMClient:
    ...
```

逻辑：

```text
1. 如果 config 缺失，返回 MockLLMClient；
2. 如果 api_key_available == false，返回 MockLLMClient；
3. 如果 provider in openai/deepseek/moonshot/qwen/glm/local，返回 OpenAICompatibleClient；
4. 如果 provider == anthropic，返回 AnthropicClient；
5. 否则返回 MockLLMClient。
```

---

## 8. LLM 配置读取

如果已有：

```text
src/ultrafast_memory/core/llm_config.py
```

请复用。

必须提供：

```python
def get_llm_config() -> dict:
    ...
```

返回：

```python
{
    "provider": "openai",
    "model": "gpt-4.1-mini",
    "api_base": "https://api.openai.com/v1",
    "api_key_env": "OPENAI_API_KEY",
    "api_key_available": true
}
```

安全要求：

```text
1. 不返回真实 API Key；
2. 不打印真实 API Key；
3. 不写入日志；
4. FastAPI 响应中不得出现真实 API Key。
```

---

## 9. Skill Router MVP

实现：

```text
src/ultrafast_memory/chat/skill_router.py
```

MVP 先用规则路由，不调用 LLM。

函数：

```python
def route_skill(message: str) -> dict:
    ...
```

返回：

```python
{
    "selected_skill": "task_intake",
    "confidence": 0.5,
    "reason": "default route"
}
```

路由规则：

```text
如果包含：
CRL、金刚石透镜、曲率半径、焦距、X-ray、抛物面
→ crl_task_planning

如果包含：
日志、recipe、工艺文件、检测结果、csv、log、job
→ process_file_ingestion

如果包含：
推荐参数、贝叶斯、BO、优化、下一轮实验
→ bo_recommendation

如果包含：
文献、论文、参考文献、机制、损伤
→ rag_literature_retrieval

如果包含：
经验、记忆库、自学习、规则、沉淀
→ experience_memory_update

否则：
task_intake
```

注意：

```text
如果同时命中多个规则，优先级：
process_file_ingestion
> bo_recommendation
> crl_task_planning
> rag_literature_retrieval
> experience_memory_update
> task_intake
```

---

## 10. Prompt Builder

实现：

```text
src/ultrafast_memory/chat/prompt_builder.py
```

函数：

```python
def build_system_prompt(selected_skill: str | None = None) -> str:
    ...
```

MVP system prompt：

```text
你是超快激光加工智能体。
你必须遵守：
1. 不得编造激光加工参数；
2. 参数必须来自用户输入、设备边界、文献证据、规则库或 BO 输出；
3. 如果信息不足，先追问；
4. 每轮最多提出 3 个关键问题；
5. 对工艺推荐必须区分文献依据、内部经验、BO 预测和待验证建议；
6. 如果当前系统尚未接入某个工具，必须明确说明，而不是假装已调用。
```

根据 `selected_skill` 追加简短指令：

```text
task_intake：
先解析任务，列出已知信息、缺失信息和最多 3 个追问。

crl_task_planning：
关注 CRL 几何、光学一致性、面形误差、粗糙度、石墨化、崩边风险。

bo_recommendation：
不得直接给参数；先检查设备边界、目标函数和样本数量。

process_file_ingestion：
引导用户使用文件扫描/导入流程，不要凭空声称已经读取文件。

rag_literature_retrieval：
如果未实际检索文献，不得伪造引用。

experience_memory_update：
只生成经验候选，不得自动生成正式规则。
```

---

## 11. Session Store

实现：

```text
src/ultrafast_memory/chat/session_store.py
```

提供函数或类：

```python
create_session(title: str | None, mode: str) -> dict
save_message(session_id: str, role: str, content: str, metadata: dict | None = None) -> dict
get_recent_messages(session_id: str, limit: int = 20) -> list[dict]
list_messages(session_id: str) -> list[dict]
save_skill_trace(session_id: str, message_id: str, route: dict) -> None
save_tool_trace(...) -> None
```

要求：

```text
1. 默认只取最近 20 条消息给 LLM；
2. 保存 user message；
3. 保存 assistant message；
4. 保存 skill route trace；
5. session_id 不存在时返回明确错误或自动创建，二者择一并在 README 说明。
```

建议策略：  
如果 `POST /chat` 没有传 `session_id`，自动创建新 session。

---

## 12. Chat Service

实现：

```text
src/ultrafast_memory/chat/service.py
```

核心函数：

```python
def handle_chat(request: ChatRequest) -> ChatResponse:
    ...
```

执行步骤：

```text
1. 若无 session_id，创建 session；
2. 保存 user message；
3. 如果 use_skills=true，调用 route_skill；
4. 保存 skill trace；
5. 读取最近 20 条历史消息；
6. 构造 system prompt；
7. 读取 LLM config；
8. create_llm_client；
9. 调用 client.chat；
10. 保存 assistant message；
11. 返回 ChatResponse。
```

MVP 阶段不执行真实 tool 调用。  
但 `audit_trace` 中应写明：

```json
[
  {
    "step": "skill_router",
    "status": "success",
    "selected_skill": "task_intake"
  },
  {
    "step": "llm_chat",
    "status": "success",
    "provider": "mock"
  }
]
```

---

## 13. FastAPI 接口

在现有：

```text
src/ultrafast_memory/app/api.py
```

中新增接口。

### 13.1 创建会话

```http
POST /chat/sessions
```

请求：

```json
{
  "title": "diamond CRL planning",
  "mode": "agent"
}
```

返回：

```json
{
  "session_id": "sess_xxx",
  "title": "diamond CRL planning",
  "mode": "agent",
  "created_at": "..."
}
```

### 13.2 发送消息

```http
POST /chat
```

请求：

```json
{
  "session_id": "sess_xxx",
  "message": "我想加工一个金刚石 CRL，参数表如下……",
  "mode": "agent",
  "use_skills": true,
  "stream": false
}
```

返回：

```json
{
  "session_id": "sess_xxx",
  "assistant_message": "...",
  "selected_skill": "crl_task_planning",
  "tool_calls": [],
  "audit_trace": []
}
```

### 13.3 获取会话消息

```http
GET /chat/sessions/{session_id}/messages
```

返回：

```json
{
  "session_id": "sess_xxx",
  "messages": [
    {
      "message_id": "msg_xxx",
      "role": "user",
      "content": "...",
      "created_at": "...",
      "metadata": {}
    }
  ]
}
```

---

## 14. PowerShell TUI 修改

修改：

```text
scripts/powershell/AgentTui.psm1
scripts/start_agent_tui.ps1
```

### 14.1 主菜单新增

```text
[9] 进入聊天
```

### 14.2 新增函数

在 `AgentTui.psm1` 中新增：

```powershell
Start-AgentChat
New-AgentChatSession
Send-AgentChatMessage
Test-AgentApiServer
```

### 14.3 聊天逻辑

`Start-AgentChat`：

```powershell
function Start-AgentChat {
    Test-AgentApiServer

    $session = New-AgentChatSession
    $sessionId = $session.session_id

    Write-Host ""
    Write-Host "进入超快激光智能体聊天模式。输入 exit 退出。" -ForegroundColor Cyan
    Write-Host ""

    while ($true) {
        $inputText = Read-Host "你"

        if ($inputText -eq "exit") {
            break
        }

        if ([string]::IsNullOrWhiteSpace($inputText)) {
            continue
        }

        $resp = Send-AgentChatMessage -SessionId $sessionId -Message $inputText

        Write-Host ""
        Write-Host "智能体：" -ForegroundColor Cyan
        Write-Host $resp.assistant_message
        Write-Host ""

        if ($resp.selected_skill) {
            Write-Host "[skill: $($resp.selected_skill)]" -ForegroundColor DarkGray
            Write-Host ""
        }
    }
}
```

### 14.4 后端未启动处理

如果 FastAPI 未启动，应提示：

```text
FastAPI 后端未启动。
请先在主菜单选择“启动 FastAPI 服务”，或允许当前 TUI 自动启动。
```

MVP 阶段可只提示，不自动启动。

### 14.5 重要环境变量问题

README 和 TUI 提示中必须说明：

```text
如果在 TUI 中配置了 API Key，必须从同一个 TUI 会话中启动 FastAPI，
否则后端进程可能无法继承环境变量。
```

---

## 15. 安全要求

必须满足：

```text
1. API Key 不得出现在 /chat 返回值中；
2. API Key 不得出现在 /chat/sessions 返回值中；
3. API Key 不得出现在 /chat/sessions/{id}/messages 返回值中；
4. API Key 不得写入 chat_message；
5. API Key 不得写入 chat_tool_trace；
6. API Key 不得打印到 PowerShell；
7. API Key 不得写入 pytest fixture；
8. MockLLMClient 必须在无 key 时可用。
```

---

## 16. 测试要求

新增 pytest。

### 16.1 `test_skill_router.py`

测试：

```text
金刚石 CRL → crl_task_planning
推荐参数 / BO → bo_recommendation
日志 / recipe → process_file_ingestion
文献 / 论文 → rag_literature_retrieval
普通模糊需求 → task_intake
```

### 16.2 `test_llm_factory.py`

测试：

```text
无配置 → MockLLMClient
api_key_available=false → MockLLMClient
provider=openai 且 key 可用 → OpenAICompatibleClient
provider=anthropic → AnthropicClient 或 NotImplemented stub
未知 provider → MockLLMClient
```

不要使用真实 API Key。

### 16.3 `test_chat_service.py`

测试：

```text
无 session_id 时自动创建 session；
user message 被保存；
assistant message 被保存；
selected_skill 被保存；
MockLLM 能返回内容；
audit_trace 包含 skill_router 和 llm_chat。
```

### 16.4 `test_chat_api.py`

使用 FastAPI TestClient 测试：

```text
POST /chat/sessions 成功；
POST /chat 成功；
GET /chat/sessions/{id}/messages 返回历史；
响应中不包含 API Key；
stream=true 时明确返回 400 或忽略，并在响应中说明 MVP 不支持 streaming。
```

---

## 17. README 更新

新增章节：

```text
聊天功能
```

必须说明：

```text
1. 如何启动 FastAPI；
2. 如何进入 PowerShell 聊天；
3. 如何使用 MockLLM；
4. 如何配置 OpenAI-Compatible 服务；
5. 当前 MVP 不支持 streaming；
6. 当前 MVP 不真正调用 RAG/BO；
7. /chat 是 Agent Orchestrator 入口，不是普通 LLM proxy；
8. API Key 安全注意事项。
```

示例命令：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/start_agent_tui.ps1
```

进入菜单后选择：

```text
[9] 进入聊天
```

也应提供 API 示例：

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

---

## 18. 验收标准

完成后应满足：

### 18.1 命令行验收

```bash
pytest -q
```

全部通过。

### 18.2 API 验收

启动后端：

```bash
python -m uvicorn ultrafast_memory.app.api:app --reload --host 127.0.0.1 --port 8000
```

创建会话：

```bash
curl -X POST http://127.0.0.1:8000/chat/sessions \
  -H "Content-Type: application/json" \
  -d '{"title":"diamond CRL planning","mode":"agent"}'
```

发送消息：

```bash
curl -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"我想加工金刚石CRL，Ra小于460nm","use_skills":true}'
```

预期：

```text
1. 返回 assistant_message；
2. selected_skill = crl_task_planning；
3. audit_trace 非空；
4. 数据库中有 user 和 assistant 消息；
5. 响应中没有 API Key。
```

### 18.3 TUI 验收

```powershell
powershell -ExecutionPolicy Bypass -File scripts/start_agent_tui.ps1 -SkipLlmConfig
```

进入主菜单，选择：

```text
[9] 进入聊天
```

输入：

```text
我想加工金刚石CRL，Ra小于460nm
```

预期：

```text
1. TUI 打印智能体回复；
2. 显示 skill: crl_task_planning；
3. 输入 exit 可退出聊天模式；
4. 无 API Key 时使用 MockLLM，不崩溃。
```

---

## 19. 实现顺序

请 Codex 按以下顺序实现：

```text
Phase 1：数据库表和 ORM models
Phase 2：chat schemas 和 session_store
Phase 3：LLM base/mock/factory
Phase 4：OpenAICompatibleClient
Phase 5：skill_router
Phase 6：prompt_builder
Phase 7：chat service
Phase 8：FastAPI endpoints
Phase 9：PowerShell TUI 聊天菜单
Phase 10：测试和 README
```

不要先做 streaming，不要先接 RAG/BO。先保证最小聊天闭环稳定。

---

## 20. 关键质量要求

```text
1. /chat 必须能在无 API Key 时通过 MockLLM 工作；
2. /chat 必须保存会话历史；
3. /chat 必须返回 selected_skill；
4. /chat 必须保存 skill trace；
5. PowerShell TUI 必须能进入聊天循环；
6. API Key 不得泄露；
7. 后端和 TUI 错误提示必须清晰；
8. 单元测试不得依赖外部网络；
9. OpenAICompatibleClient 代码必须可替换 provider；
10. Anthropic adapter 允许 stub，但不得假装已实现。
```

---

## 21. 后续扩展预留

本任务完成后，后续可继续做：

```text
1. 接入 agent_skills/ 中的 SKILL.md；
2. 根据 selected_skill 加载对应 SKILL.md；
3. 接入 RAG 文献检索；
4. 接入 BO 推荐引擎；
5. 接入文件自学习工具；
6. 支持 tool trace 真实记录；
7. 支持 streaming；
8. 支持 Web Chat UI；
9. 支持会话摘要压缩；
10. 支持多轮任务状态机。
```

---

## 22. 一句话总结

本任务要实现的不是“普通聊天”，而是超快激光智能体的统一交互入口。

第一版只需要跑通：

```text
PowerShell TUI
→ /chat
→ skill_router
→ LLM adapter 或 MockLLM
→ 会话保存
→ 审计返回
```

但接口和数据库必须为后续 RAG、BO、skill、专业知识记忆库、自学习闭环留出结构。
