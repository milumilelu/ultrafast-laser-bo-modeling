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

主要接口：`/health`、`/ingest/scan`、`/artifacts`、`/runs`、`/experience/candidates`、`/bo/export`、`/llm/config`、`/llm/test`。

## 数据库表

核心表包括：`raw_artifact`、`process_task`、`process_recipe`、`process_run`、`measurement_record`、`experience_candidate`、`validated_rule`、`bo_training_sample`。

每条结构化记录保留 `artifact_id`，可追溯到归档原始文件和 SHA256。

## 自学习机制边界

操作员备注只生成 `experience_candidate`。候选经验是待审核陈述，不是物理事实，也不是正式工艺规则。未经质量校验的数据不会进入 BO 训练样本。

## 当前 MVP 不做什么

不做实时 GUI、完整 RAG、真实 LLM API 调用、真实 BO 仓库集成、自动规则晋升、复杂 PDF 表格解析、多用户权限系统。

## 后续扩展

已预留 `knowledge/experience_extractor.py`、`rag/index_stub.py`、`bo/bo_engine_adapter.py`。后续可接入 LLM JSON schema extraction、向量索引和 `ultrafast-laser-bo-modeling`。

## PowerShell TUI 启动器

一键完成本地配置并启动 TUI：

```powershell
pwsh -ExecutionPolicy Bypass -File scripts/setup_and_start_tui.ps1
```

该脚本会执行 `pip install -e .`、初始化数据库、扫描 `examples`、导出 BO CSV，然后进入 TUI。它不会自动生成或保存 API Key；LLM 密钥仍需通过 TUI 交互输入或由环境变量提供。

启动命令：

```powershell
pwsh -ExecutionPolicy Bypass -File scripts/start_agent_tui.ps1
```

跳过 LLM 配置，仅启动数据闭环服务菜单：

```powershell
pwsh -ExecutionPolicy Bypass -File scripts/start_agent_tui.ps1 -SkipLlmConfig
```

本次会话不保存配置：

```powershell
pwsh -ExecutionPolicy Bypass -File scripts/start_agent_tui.ps1 -NoSave
```

启动器支持选择 OpenAI、DeepSeek、Anthropic、Moonshot/Kimi、Qwen、GLM 和本地 OpenAI-Compatible 服务。默认模型列表已按 2026-07-07 官方文档更新：

- OpenAI：`gpt-5.5`、`gpt-5.4`、`gpt-5.4-mini`、`gpt-5.4-nano`
- DeepSeek：`deepseek-v4-pro`、`deepseek-v4-flash`
- Anthropic：`claude-fable-5`、`claude-opus-4-8`、`claude-sonnet-5`、`claude-haiku-4-5`
- Moonshot/Kimi：`kimi-k2.7-code`、`kimi-k2.7-code-highspeed`、`kimi-k2.6`、`moonshot-v1-128k`
- Qwen：`qwen3.7-max`、`qwen3.7-plus`、`qwen3.6-flash`
- GLM/Z.ai：`glm-5.2`、`glm-5.1`、`glm-5`、`glm-5-turbo`

默认模型列表只是启动器默认值，实际可用模型以用户 API 服务商账户权限为准。API Base URL 可在 TUI 中修改，默认地址也可能随服务商调整。

API Key 使用 `Read-Host -AsSecureString` 输入，不明文回显。默认只写入当前 PowerShell 进程环境变量，并保存不含明文 key 的 `configs/llm.local.json`。该文件已加入 `.gitignore`。Windows Credential Manager 持久密钥存储仅预留 stub，MVP 暂未启用。

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
