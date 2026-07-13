# Codex 任务方案：超快激光智能体自学习数据闭环 MVP

## 0. 项目目标

搭建一个面向“超快激光加工智能体”的自学习数据闭环 MVP。

本阶段不训练大模型，不让大模型自动修改自身参数，也不直接让 LLM 自动生成正式工艺规则。目标是实现：

```text
加工软件文件 / 日志 / 工艺配方 / 检测结果 / 操作员备注
→ 自动监听与归档
→ 结构化解析
→ 单位标准化
→ 数据质量校验
→ 写入专业知识记忆库
→ 生成经验候选
→ 人工审核
→ 晋升为验证规则或 BO 训练样本
```

本任务优先实现工程骨架和数据闭环。后续可接入 RAG、LLM API 和贝叶斯优化仓库。

参考优化引擎仓库：

```text
https://github.com/milumilelu/ultrafast-laser-bo-modeling
```

该仓库后续作为 BO 推荐模块接入，本任务先预留接口，不强制集成。

---

## 1. 设计原则

### 1.1 必须满足

1. 原始文件必须归档，不能被修改。
2. 每条结构化数据必须能追溯到原始文件。
3. 每个原始文件必须计算 SHA256。
4. LLM 只能生成 `experience_candidate`，不能直接写入 `validated_rule`。
5. 未经校验的数据不能进入 BO 训练样本表。
6. 所有单位必须标准化，同时保存原始单位和值。
7. 每个 parser 必须有版本号。
8. 每次导入必须幂等：同一文件重复导入不得重复生成数据。
9. 所有异常都要记录，不允许静默失败。
10. 代码必须包含基础测试。

### 1.2 明确禁止

1. 不要自动删除或覆盖原始文件。
2. 不要用 LLM 猜测缺失的功率、速度、频率、粗糙度等数值。
3. 不要把操作员主观描述直接当作物理事实。
4. 不要把报警或中断的加工记录直接加入 BO 训练集。
5. 不要把单次失败归纳成正式规则。
6. 不要把 RAG 当作数据库使用；结构化数据必须入库。

---

## 2. MVP 范围

本 MVP 只实现以下能力：

```text
1. 监听或扫描指定目录；
2. 发现新增文件；
3. 归档原始文件；
4. 计算 SHA256；
5. 识别文件类型；
6. 解析 recipe/log/csv/txt 四类文件；
7. 写入 SQLite 数据库；
8. 标准化单位；
9. 关联 task / recipe / run / measurement；
10. 从操作员备注中生成经验候选；
11. 提供人工审核接口；
12. 导出 BO 可用候选数据；
13. 提供 CLI 和最小 FastAPI 接口。
```

本 MVP 暂不要求：

```text
1. 实时 GUI；
2. 完整 RAG；
3. 真正调用 LLM API；
4. 真正调用 BO 仓库；
5. 自动规则晋升；
6. 复杂 PDF 表格解析；
7. 多用户权限系统。
```

但代码结构要为这些能力预留扩展点。

---

## 3. 推荐技术栈

```text
Python >= 3.10
SQLite：MVP 数据库
SQLAlchemy：ORM
Pydantic：数据结构校验
watchdog：目录监听
pandas：csv/xlsx 读取
FastAPI：服务接口
Typer：CLI
pytest：测试
ruff：代码风格
```

建议创建 `requirements.txt` 或 `pyproject.toml`。

---

## 4. 项目目录结构

请按以下结构创建项目：

```text
ultrafast_laser_memory/
  README.md
  pyproject.toml 或 requirements.txt
  .gitignore

  configs/
    default.yaml

  data/
    watch_dirs/
      recipes/
      logs/
      measurements/
      notes/
    raw_artifacts/
    exports/

  src/
    ultrafast_memory/
      __init__.py

      app/
        api.py
        cli.py

      core/
        config.py
        hashing.py
        file_type.py
        time_utils.py
        ids.py

      db/
        base.py
        session.py
        models.py
        init_db.py

      schemas/
        artifact.py
        task.py
        recipe.py
        run.py
        measurement.py
        experience.py
        bo.py

      ingestion/
        scanner.py
        watcher.py
        archive.py
        pipeline.py

      parsers/
        base.py
        recipe_json_parser.py
        simple_log_parser.py
        measurement_csv_parser.py
        operator_note_parser.py

      normalization/
        units.py
        fields.py

      validation/
        quality_checks.py
        bo_eligibility.py

      knowledge/
        experience_extractor.py
        rule_promotion.py
        review_queue.py

      bo/
        dataset_builder.py
        bo_engine_adapter.py

      rag/
        index_stub.py

  tests/
    test_hashing.py
    test_file_type.py
    test_units.py
    test_parsers.py
    test_pipeline.py

  examples/
    sample_recipe.json
    sample_run.log
    sample_measurement.csv
    sample_note.txt
```

---

## 5. 数据库设计

使用 SQLite。数据库文件默认放在：

```text
data/ultrafast_memory.db
```

### 5.1 `raw_artifact`

保存原始文件信息。

```sql
CREATE TABLE raw_artifact (
    artifact_id TEXT PRIMARY KEY,
    file_path TEXT NOT NULL,
    archived_path TEXT NOT NULL,
    file_type TEXT NOT NULL,
    sha256 TEXT NOT NULL UNIQUE,
    file_size_bytes INTEGER,
    created_at TEXT,
    modified_at TEXT,
    imported_at TEXT NOT NULL,
    parser_name TEXT,
    parser_version TEXT,
    parse_status TEXT NOT NULL,
    error_message TEXT
);
```

### 5.2 `process_task`

保存加工任务。

```sql
CREATE TABLE process_task (
    task_id TEXT PRIMARY KEY,
    component_type TEXT,
    material TEXT,
    material_grade TEXT,
    geometry_json TEXT,
    target_json TEXT,
    priority_mode TEXT,
    created_by TEXT,
    created_at TEXT,
    status TEXT
);
```

### 5.3 `process_recipe`

保存计划工艺参数。

```sql
CREATE TABLE process_recipe (
    recipe_id TEXT PRIMARY KEY,
    task_id TEXT,
    artifact_id TEXT,
    process_type TEXT,
    laser_wavelength_nm REAL,
    pulse_width_fs REAL,
    laser_power_W REAL,
    frequency_kHz REAL,
    scan_speed_mm_s REAL,
    passes INTEGER,
    hatch_spacing_um REAL,
    layer_step_um REAL,
    focus_offset_um REAL,
    fill_pattern TEXT,
    path_strategy TEXT,
    parameters_json TEXT,
    created_at TEXT
);
```

### 5.4 `process_run`

保存一次实际运行。

```sql
CREATE TABLE process_run (
    run_id TEXT PRIMARY KEY,
    task_id TEXT,
    recipe_id TEXT,
    artifact_id TEXT,
    machine_id TEXT,
    operator_id TEXT,
    start_time TEXT,
    end_time TEXT,
    duration_s REAL,
    run_status TEXT,
    alarm_count INTEGER,
    abnormal_flag INTEGER,
    abnormal_summary TEXT
);
```

### 5.5 `measurement_record`

保存检测结果。

```sql
CREATE TABLE measurement_record (
    measurement_id TEXT PRIMARY KEY,
    run_id TEXT,
    artifact_id TEXT,
    metric_name TEXT NOT NULL,
    metric_value REAL NOT NULL,
    metric_unit TEXT NOT NULL,
    raw_value TEXT,
    raw_unit TEXT,
    measurement_method TEXT,
    instrument_id TEXT,
    region_of_interest TEXT,
    measured_at TEXT,
    valid_flag INTEGER
);
```

### 5.6 `experience_candidate`

保存 LLM 或规则抽取出的候选经验。

```sql
CREATE TABLE experience_candidate (
    candidate_id TEXT PRIMARY KEY,
    task_id TEXT,
    run_id TEXT,
    source_artifact_ids TEXT,
    extracted_claim TEXT NOT NULL,
    evidence_json TEXT,
    confidence REAL,
    status TEXT NOT NULL,
    extracted_by TEXT,
    extracted_at TEXT,
    review_comment TEXT
);
```

`status` 可选：

```text
candidate
accepted
rejected
needs_more_evidence
```

### 5.7 `validated_rule`

保存人工确认或多案例支持的规则。

```sql
CREATE TABLE validated_rule (
    rule_id TEXT PRIMARY KEY,
    material TEXT,
    process_type TEXT,
    condition_json TEXT,
    rule_text TEXT NOT NULL,
    recommended_action_json TEXT,
    supporting_case_ids TEXT,
    counter_case_ids TEXT,
    confidence REAL,
    status TEXT,
    version INTEGER,
    created_at TEXT,
    updated_at TEXT
);
```

### 5.8 `bo_training_sample`

保存可进入 BO 的训练样本。

```sql
CREATE TABLE bo_training_sample (
    sample_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    material TEXT,
    process_type TEXT,
    x_parameters_json TEXT NOT NULL,
    y_metrics_json TEXT NOT NULL,
    constraints_json TEXT,
    valid_for_training INTEGER NOT NULL,
    invalid_reason TEXT,
    added_at TEXT
);
```

---

## 6. 文件类型识别

实现模块：

```text
src/ultrafast_memory/core/file_type.py
```

输入：文件路径。  
输出：文件类型字符串。

支持：

```text
json_recipe
machine_log
measurement_csv
operator_note
unknown
```

识别规则：

```text
.json → json_recipe
.csv → measurement_csv
.log → machine_log
.txt → 若路径含 notes 或文件名含 note，则 operator_note，否则 machine_log
其他 → unknown
```

后续可扩展为：

```text
xlsx_measurement
pdf_report
gcode_toolpath
nc_toolpath
xml_recipe
```

---

## 7. 原始文件归档

实现模块：

```text
src/ultrafast_memory/ingestion/archive.py
```

功能：

1. 计算 SHA256；
2. 检查数据库中是否已有相同 SHA256；
3. 若已有，跳过重复导入；
4. 若没有，将原始文件复制到：

```text
data/raw_artifacts/YYYY-MM-DD/<sha256>_<original_filename>
```

5. 写入 `raw_artifact`。

注意：不得移动原文件，只复制归档。

---

## 8. Parser 设计

### 8.1 Parser 基类

实现：

```text
src/ultrafast_memory/parsers/base.py
```

定义统一接口：

```python
class BaseParser:
    name: str
    version: str

    def parse(self, file_path: str) -> dict:
        raise NotImplementedError
```

返回统一结构：

```python
{
    "tasks": [],
    "recipes": [],
    "runs": [],
    "measurements": [],
    "notes": [],
    "errors": []
}
```

### 8.2 JSON 工艺配方 parser

实现：

```text
src/ultrafast_memory/parsers/recipe_json_parser.py
```

支持样例：

```json
{
  "task_id": "task_diamond_crl_001",
  "component_type": "diamond_CRL",
  "material": "diamond",
  "process_type": "surface_micromachining",
  "geometry": {
    "curvature_radius_mm": 1.0,
    "thickness_mm": 1.0,
    "aperture_mm": 0.9849,
    "parabola_spacing_um": 30
  },
  "target": {
    "Ra_nm_max": 460,
    "focal_length_m": 9.8,
    "photon_energy_keV": 10,
    "lens_count": 7
  },
  "laser": {
    "wavelength_nm": 1030,
    "pulse_width_fs": 300,
    "power_W": 5.0,
    "frequency_kHz": 200
  },
  "scan": {
    "scan_speed_mm_s": 500,
    "passes": 3,
    "hatch_spacing_um": 5,
    "layer_step_um": 2,
    "focus_offset_um": 0,
    "fill_pattern": "bidirectional",
    "path_strategy": "layered_surface"
  }
}
```

必须提取：

```text
process_task
process_recipe
```

若缺少 `task_id`，自动生成，但要记录来源。

### 8.3 简单日志 parser

实现：

```text
src/ultrafast_memory/parsers/simple_log_parser.py
```

支持样例：

```text
run_id: run_023
task_id: task_diamond_crl_001
recipe_id: recipe_023
machine_id: laser_A
operator_id: user_01
start_time: 2026-07-07 10:00:00
end_time: 2026-07-07 10:12:30
status: completed
actual_power_W: 5.1
actual_frequency_kHz: 200
alarm_count: 0
abnormal_summary: none
```

必须提取：

```text
process_run
```

如果 `status != completed` 或 `alarm_count > 0`，则：

```text
abnormal_flag = 1
```

### 8.4 检测结果 CSV parser

实现：

```text
src/ultrafast_memory/parsers/measurement_csv_parser.py
```

支持 CSV 字段：

```text
run_id,metric_name,metric_value,metric_unit,measurement_method,instrument_id,region_of_interest,measured_at
```

样例：

```csv
run_id,metric_name,metric_value,metric_unit,measurement_method,instrument_id,region_of_interest,measured_at
run_023,Ra,520,nm,white_light_interferometry,wli_01,CRL_center,2026-07-07 11:00:00
run_023,form_error,8.2,um,profile_measurement,profiler_01,CRL_full,2026-07-07 11:10:00
```

必须提取：

```text
measurement_record
```

并调用单位标准化。

### 8.5 操作员备注 parser

实现：

```text
src/ultrafast_memory/parsers/operator_note_parser.py
```

MVP 阶段不调用真实 LLM，先用规则关键词抽取。

支持样例：

```text
run_id: run_023
note: 加工后表面发黑，边缘轻微崩裂，深度比预期浅，Ra 未达标。
```

关键词映射：

```text
表面发黑 / 发黑 / blackening → surface_blackening
崩裂 / 崩边 / chipping → edge_chipping
深度不足 / 太浅 → depth_insufficient
粗糙度大 / Ra 未达标 → roughness_above_target
```

生成 `experience_candidate`：

```text
extracted_claim:
"该加工记录出现 surface_blackening, edge_chipping, depth_insufficient, roughness_above_target，需进一步验证原因。"

confidence:
0.4
status:
candidate
extracted_by:
rule_based_note_parser
```

后续再替换成 LLM schema extraction。

---

## 9. 单位标准化

实现模块：

```text
src/ultrafast_memory/normalization/units.py
```

内部标准单位：

```text
laser_power: W
frequency: kHz
pulse_width: fs
scan_speed: mm/s
hatch_spacing: um
layer_step: um
focus_offset: um
roughness: nm
depth: um
form_error: um
duration: s
```

必须支持：

```text
um → nm，针对 Ra/Sa/Sq 等粗糙度指标
μm → nm
mm/min → mm/s
Hz → kHz
MHz → kHz
ps → fs
```

示例：

```python
normalize_value(value=0.46, from_unit="um", quantity="roughness")
# returns (460.0, "nm")
```

如果无法识别单位，保留原始值，并标记 `valid_flag=0`。

---

## 10. 数据质量校验

实现模块：

```text
src/ultrafast_memory/validation/quality_checks.py
```

### 10.1 基础检查

对每个 run 检查：

```text
1. 是否有关联 recipe；
2. 是否有 material；
3. 是否有 process_type；
4. 是否有关键输入参数：
   laser_power_W
   frequency_kHz
   scan_speed_mm_s
5. 是否有至少一个质量输出：
   Ra / Sa / depth / form_error / removal_rate / graphitization_score
6. 是否异常中断；
7. 是否报警；
8. 单位是否已标准化。
```

### 10.2 BO eligibility

实现模块：

```text
src/ultrafast_memory/validation/bo_eligibility.py
```

规则：

```text
valid_for_training = true 需要满足：

1. run_status == completed
2. abnormal_flag == 0
3. recipe 关键参数完整
4. 至少有一个有效 measurement
5. measurement.valid_flag == 1
6. material 不为空
7. process_type 不为空
```

否则写入：

```text
valid_for_training = false
invalid_reason = "... "
```

---

## 11. BO 数据导出

实现模块：

```text
src/ultrafast_memory/bo/dataset_builder.py
```

功能：

1. 查询所有满足 BO eligibility 的 run；
2. 组合 recipe 参数为 `x_parameters_json`；
3. 组合 measurement 为 `y_metrics_json`；
4. 写入 `bo_training_sample`；
5. 导出 CSV：

```text
data/exports/bo_training_samples.csv
```

CSV 字段尽量兼容 BO 仓库：

```text
sample_id
run_id
material
process_type
pulse_width_fs
frequency_kHz
laser_power_W
scan_speed_mm_s
passes
focus_offset_um
hatch_spacing_um
layer_step_um
Ra_nm
Sa_nm
depth_um
form_error_um
removal_rate_um3_s
graphitization_score
valid_for_training
invalid_reason
```

注意：若字段缺失，保留为空，不要编造。

---

## 12. 经验候选与人工审核

实现模块：

```text
src/ultrafast_memory/knowledge/review_queue.py
```

提供函数：

```python
list_candidates(status: str = "candidate") -> list
accept_candidate(candidate_id: str, comment: str = "") -> None
reject_candidate(candidate_id: str, comment: str = "") -> None
mark_needs_more_evidence(candidate_id: str, comment: str = "") -> None
```

MVP 阶段，接受候选不自动写入 `validated_rule`。后续可以增加：

```python
promote_candidate_to_rule(candidate_id: str)
```

但必须显式调用，不可自动触发。

---

## 13. FastAPI 接口

实现：

```text
src/ultrafast_memory/app/api.py
```

需要以下接口：

### 13.1 健康检查

```http
GET /health
```

返回：

```json
{"status": "ok"}
```

### 13.2 扫描目录

```http
POST /ingest/scan
```

请求：

```json
{
  "directory": "data/watch_dirs"
}
```

返回：

```json
{
  "imported": 4,
  "skipped": 1,
  "errors": []
}
```

### 13.3 查看原始文件

```http
GET /artifacts
```

返回最近导入文件列表。

### 13.4 查看加工记录

```http
GET /runs
```

返回最近 process_run 列表。

### 13.5 查看经验候选

```http
GET /experience/candidates
```

### 13.6 审核经验候选

```http
POST /experience/candidates/{candidate_id}/review
```

请求：

```json
{
  "action": "accept",
  "comment": "人工确认该描述与显微图一致，但仍缺少 Raman 验证。"
}
```

action 可选：

```text
accept
reject
needs_more_evidence
```

### 13.7 导出 BO 数据

```http
POST /bo/export
```

返回：

```json
{
  "export_path": "data/exports/bo_training_samples.csv",
  "sample_count": 12
}
```

---

## 14. CLI 命令

实现：

```text
src/ultrafast_memory/app/cli.py
```

使用 Typer。

需要支持：

```bash
python -m ultrafast_memory.app.cli init-db
python -m ultrafast_memory.app.cli scan data/watch_dirs
python -m ultrafast_memory.app.cli list-artifacts
python -m ultrafast_memory.app.cli list-runs
python -m ultrafast_memory.app.cli list-candidates
python -m ultrafast_memory.app.cli review-candidate <candidate_id> --action accept
python -m ultrafast_memory.app.cli export-bo
```

---

## 15. 配置文件

创建：

```text
configs/default.yaml
```

内容：

```yaml
database:
  url: "sqlite:///data/ultrafast_memory.db"

paths:
  watch_dirs:
    - "data/watch_dirs/recipes"
    - "data/watch_dirs/logs"
    - "data/watch_dirs/measurements"
    - "data/watch_dirs/notes"
  raw_artifacts: "data/raw_artifacts"
  exports: "data/exports"

ingestion:
  archive_originals: true
  skip_duplicate_sha256: true

parsers:
  recipe_json:
    enabled: true
  simple_log:
    enabled: true
  measurement_csv:
    enabled: true
  operator_note:
    enabled: true

bo:
  export_filename: "bo_training_samples.csv"
```

---

## 16. 示例数据

创建四个示例文件。

### 16.1 `examples/sample_recipe.json`

```json
{
  "task_id": "task_diamond_crl_001",
  "component_type": "diamond_CRL",
  "material": "diamond",
  "process_type": "surface_micromachining",
  "geometry": {
    "curvature_radius_mm": 1.0,
    "thickness_mm": 1.0,
    "aperture_mm": 0.9849,
    "parabola_spacing_um": 30
  },
  "target": {
    "Ra_nm_max": 460,
    "focal_length_m": 9.8,
    "photon_energy_keV": 10,
    "lens_count": 7
  },
  "laser": {
    "wavelength_nm": 1030,
    "pulse_width_fs": 300,
    "power_W": 5.0,
    "frequency_kHz": 200
  },
  "scan": {
    "scan_speed_mm_s": 500,
    "passes": 3,
    "hatch_spacing_um": 5,
    "layer_step_um": 2,
    "focus_offset_um": 0,
    "fill_pattern": "bidirectional",
    "path_strategy": "layered_surface"
  }
}
```

### 16.2 `examples/sample_run.log`

```text
run_id: run_023
task_id: task_diamond_crl_001
recipe_id: recipe_task_diamond_crl_001
machine_id: laser_A
operator_id: user_01
start_time: 2026-07-07 10:00:00
end_time: 2026-07-07 10:12:30
status: completed
actual_power_W: 5.1
actual_frequency_kHz: 200
alarm_count: 0
abnormal_summary: none
```

### 16.3 `examples/sample_measurement.csv`

```csv
run_id,metric_name,metric_value,metric_unit,measurement_method,instrument_id,region_of_interest,measured_at
run_023,Ra,520,nm,white_light_interferometry,wli_01,CRL_center,2026-07-07 11:00:00
run_023,form_error,8.2,um,profile_measurement,profiler_01,CRL_full,2026-07-07 11:10:00
```

### 16.4 `examples/sample_note.txt`

```text
run_id: run_023
note: 加工后表面发黑，边缘轻微崩裂，深度比预期浅，Ra 未达标。
```

---

## 17. 测试要求

必须实现 pytest 测试。

### 17.1 `test_hashing.py`

检查：

```text
同一文件 SHA256 一致；
不同文件 SHA256 不同。
```

### 17.2 `test_file_type.py`

检查：

```text
sample_recipe.json → json_recipe
sample_run.log → machine_log
sample_measurement.csv → measurement_csv
sample_note.txt → operator_note
```

### 17.3 `test_units.py`

检查：

```text
0.46 um roughness → 460 nm
1 MHz frequency → 1000 kHz
300 ps pulse_width → 300000 fs
60 mm/min scan_speed → 1 mm/s
```

### 17.4 `test_parsers.py`

检查：

```text
recipe parser 能提取 material=diamond；
log parser 能提取 run_id=run_023；
measurement parser 能提取 Ra=520 nm；
note parser 能提取 surface_blackening 和 edge_chipping。
```

### 17.5 `test_pipeline.py`

检查完整流程：

```text
1. 初始化数据库；
2. 扫描 examples；
3. 写入 raw_artifact；
4. 写入 process_task；
5. 写入 process_recipe；
6. 写入 process_run；
7. 写入 measurement_record；
8. 写入 experience_candidate；
9. 导出 bo_training_samples.csv。
```

---

## 18. 验收标准

Codex 完成后，应满足：

```bash
pytest
```

全部通过。

并且以下命令可运行：

```bash
python -m ultrafast_memory.app.cli init-db
python -m ultrafast_memory.app.cli scan examples
python -m ultrafast_memory.app.cli list-artifacts
python -m ultrafast_memory.app.cli list-runs
python -m ultrafast_memory.app.cli list-candidates
python -m ultrafast_memory.app.cli export-bo
```

成功后应生成：

```text
data/ultrafast_memory.db
data/raw_artifacts/
data/exports/bo_training_samples.csv
```

`bo_training_samples.csv` 中至少包含：

```text
run_id = run_023
material = diamond
process_type = surface_micromachining
laser_power_W = 5.0
frequency_kHz = 200
scan_speed_mm_s = 500
Ra_nm = 520
form_error_um = 8.2
```

---

## 19. 后续扩展接口

请预留以下接口，但 MVP 可先实现 stub。

### 19.1 LLM 抽取接口

```text
src/ultrafast_memory/knowledge/experience_extractor.py
```

预留函数：

```python
def extract_experience_with_llm(note_text: str, context: dict) -> dict:
    """
    MVP 返回 NotImplementedError 或调用 rule_based_extractor。
    后续接入大模型 JSON schema extraction。
    """
```

### 19.2 RAG 索引接口

```text
src/ultrafast_memory/rag/index_stub.py
```

预留函数：

```python
def index_experience_candidate(candidate_id: str) -> None:
    pass

def search_memory(query: str, filters: dict | None = None) -> list:
    return []
```

### 19.3 BO 引擎接口

```text
src/ultrafast_memory/bo/bo_engine_adapter.py
```

预留函数：

```python
def call_bo_recommendation(task_spec: dict, training_csv_path: str) -> dict:
    """
    后续接入 ultrafast-laser-bo-modeling。
    MVP 只返回 model_status='not_connected'。
    """
```

---

## 20. 推荐实现顺序

请 Codex 按以下顺序实现：

```text
Phase 1：项目结构、依赖、配置、数据库模型
Phase 2：hash、文件类型识别、归档
Phase 3：四类 parser
Phase 4：ingestion pipeline
Phase 5：单位标准化与质量校验
Phase 6：经验候选与审核
Phase 7：BO 数据导出
Phase 8：CLI
Phase 9：FastAPI
Phase 10：测试与 README
```

不要先做 LLM、RAG、BO 深度集成。先保证数据闭环可靠。

---

## 21. README 必须说明

README 至少包含：

```text
1. 项目目标；
2. 安装方法；
3. 初始化数据库；
4. 导入示例数据；
5. 查看经验候选；
6. 导出 BO 数据；
7. 数据库表说明；
8. 自学习机制边界；
9. 当前 MVP 不做什么；
10. 后续扩展计划。
```

---

## 22. 关键质量要求

代码必须满足：

```text
1. 类型标注尽量完整；
2. 函数职责单一；
3. 解析失败不终止整个 pipeline；
4. 每个 parser 独立可测试；
5. 数据库写入幂等；
6. 日志清晰；
7. 不使用硬编码绝对路径；
8. 不依赖外部网络；
9. 不要求真实加工软件；
10. 示例数据即可跑通。
```

---

## 23. 最终交付物

Codex 最终应交付：

```text
1. 完整项目代码；
2. README.md；
3. SQLite schema / ORM models；
4. 示例数据；
5. CLI；
6. FastAPI；
7. pytest 测试；
8. BO 数据导出 CSV；
9. 后续 LLM/RAG/BO 集成 stub。
```

---


---

## 25. 新增需求：基于 PowerShell 的智能体 TUI 启动界面

需要新增一个基于 PowerShell 的本地 TUI 启动界面，用于在 Windows 环境下启动超快激光智能体系统。

该界面不是 Web 前端，也不是完整 GUI，而是一个命令行交互式启动器。  
主要目标是让用户在启动系统前完成：

```text
1. 选择大模型服务商；
2. 选择具体模型；
3. 输入 API Key；
4. 配置 API Base URL；
5. 保存或临时使用配置；
6. 启动 FastAPI 后端；
7. 查看系统状态；
8. 进入常用操作菜单。
```

### 25.1 文件位置

请新增目录：

```text
scripts/
  start_agent_tui.ps1
  powershell/
    AgentTui.psm1
```

其中：

```text
scripts/start_agent_tui.ps1
```

作为主入口脚本。

```text
scripts/powershell/AgentTui.psm1
```

作为 PowerShell 模块，封装菜单、配置读写、密钥处理、服务启动等函数。

### 25.2 TUI 启动页功能

启动页需要显示：

```text
超快激光智能体启动器
Ultrafast Laser Agent Launcher

[1] OpenAI
[2] DeepSeek
[3] Anthropic
[4] Moonshot / Kimi
[5] 通义千问 Qwen
[6] 智谱 GLM
[7] 本地 OpenAI-Compatible 服务
[8] 跳过 LLM 配置，仅启动数据闭环服务
```

用户选择服务商后，进入模型选择页。

### 25.3 模型选择

每个服务商提供默认模型列表。

建议默认配置如下，后续允许用户自定义：

```text
OpenAI:
  gpt-4.1
  gpt-4.1-mini
  gpt-4o
  gpt-4o-mini

DeepSeek:
  deepseek-chat
  deepseek-reasoner

Anthropic:
  claude-3-5-sonnet-latest
  claude-3-5-haiku-latest

Moonshot / Kimi:
  moonshot-v1-8k
  moonshot-v1-32k
  moonshot-v1-128k

Qwen:
  qwen-plus
  qwen-max
  qwen-turbo

GLM:
  glm-4
  glm-4-air
  glm-4-flash

Local OpenAI-Compatible:
  自定义 model name
```

注意：模型列表只是启动器默认值，不要求保证所有模型当前可用。  
README 中必须声明：实际可用模型以用户 API 服务商账户权限为准。

### 25.4 API Key 输入

启动器必须支持输入 API Key。

要求：

```text
1. API Key 输入时不应明文回显；
2. 支持仅本次会话使用；
3. 支持保存到本地配置文件；
4. 支持从环境变量读取；
5. 支持清除已保存 API Key；
6. 不得把 API Key 写入日志；
7. 不得把 API Key 提交到 git。
```

PowerShell 中应使用：

```powershell
Read-Host -AsSecureString
```

读取密钥。

若需要转为普通字符串写入进程环境变量，只能在当前进程中使用，不得打印。

### 25.5 配置文件

新增配置文件：

```text
configs/llm.local.json
```

该文件默认不提交 git。  
需要在 `.gitignore` 中加入：

```text
configs/llm.local.json
.env
*.key
```

配置结构：

```json
{
  "provider": "openai",
  "model": "gpt-4.1-mini",
  "api_base": "https://api.openai.com/v1",
  "api_key_source": "env",
  "api_key_env": "OPENAI_API_KEY",
  "created_at": "2026-07-07T00:00:00",
  "updated_at": "2026-07-07T00:00:00"
}
```

如果用户选择保存 API Key，不建议明文保存。  
MVP 阶段优先采用环境变量方式：

```powershell
$env:OPENAI_API_KEY = "<current-session-key>"
```

如必须持久保存，请优先使用 Windows Credential Manager。  
可以预留函数：

```powershell
Save-AgentSecret
Get-AgentSecret
Remove-AgentSecret
```

MVP 中可先实现 stub，并在 README 中说明暂未启用持久安全密钥存储。

### 25.6 API Base URL

启动器应根据服务商填入默认 API Base URL。

建议：

```text
OpenAI:
  https://api.openai.com/v1

DeepSeek:
  https://api.deepseek.com

Anthropic:
  https://api.anthropic.com

Moonshot:
  https://api.moonshot.cn/v1

Qwen:
  https://dashscope.aliyuncs.com/compatible-mode/v1

GLM:
  https://open.bigmodel.cn/api/paas/v4

Local OpenAI-Compatible:
  用户输入
```

注意：这些默认地址可能随服务商调整。  
README 中必须说明可通过 TUI 修改 API Base URL。

### 25.7 环境变量映射

根据 provider 自动设置环境变量：

```text
OpenAI:
  OPENAI_API_KEY

DeepSeek:
  DEEPSEEK_API_KEY

Anthropic:
  ANTHROPIC_API_KEY

Moonshot:
  MOONSHOT_API_KEY

Qwen:
  DASHSCOPE_API_KEY

GLM:
  ZHIPUAI_API_KEY

Local:
  OPENAI_API_KEY 或用户自定义
```

同时设置通用变量，供 Python 后端读取：

```text
ULTRAFAST_LLM_PROVIDER
ULTRAFAST_LLM_MODEL
ULTRAFAST_LLM_API_BASE
ULTRAFAST_LLM_API_KEY_ENV
```

不要把实际 API Key 写入 `ULTRAFAST_LLM_API_KEY`，除非用户明确选择“仅本次会话注入”。

### 25.8 启动 FastAPI 后端

TUI 配置完成后，提供菜单：

```text
[1] 初始化数据库
[2] 扫描示例数据
[3] 启动 FastAPI 服务
[4] 导出 BO 数据集
[5] 查看配置
[6] 清除本地 LLM 配置
[7] 退出
```

启动服务命令建议：

```powershell
python -m uvicorn ultrafast_memory.app.api:app --reload --host 127.0.0.1 --port 8000
```

如果 Python 环境未安装依赖，应提示：

```powershell
pip install -e .
```

或：

```powershell
pip install -r requirements.txt
```

### 25.9 PowerShell 函数要求

`AgentTui.psm1` 至少实现以下函数：

```powershell
Show-AgentBanner
Show-ProviderMenu
Show-ModelMenu
Read-AgentApiKey
Set-AgentEnvironment
Save-AgentLlmConfig
Load-AgentLlmConfig
Clear-AgentLlmConfig
Show-AgentMainMenu
Initialize-AgentDatabase
Invoke-AgentScan
Start-AgentApiServer
Export-AgentBoDataset
Test-AgentPythonEnvironment
```

### 25.10 PowerShell 脚本骨架

`start_agent_tui.ps1` 应包含：

```powershell
param(
    [switch]$NoSave,
    [switch]$SkipLlmConfig
)

$ErrorActionPreference = "Stop"

$ModulePath = Join-Path $PSScriptRoot "powershell/AgentTui.psm1"
Import-Module $ModulePath -Force

Show-AgentBanner

if (-not $SkipLlmConfig) {
    $provider = Show-ProviderMenu
    $model = Show-ModelMenu -Provider $provider
    $apiKeyInfo = Read-AgentApiKey -Provider $provider
    Set-AgentEnvironment -Provider $provider -Model $model -ApiKeyInfo $apiKeyInfo

    if (-not $NoSave) {
        Save-AgentLlmConfig -Provider $provider -Model $model -ApiKeyInfo $apiKeyInfo
    }
}

Show-AgentMainMenu
```

### 25.11 后端读取配置

Python 后端需要新增配置读取逻辑：

```text
src/ultrafast_memory/core/llm_config.py
```

读取优先级：

```text
1. 当前进程环境变量；
2. configs/llm.local.json；
3. configs/default.yaml；
4. 未配置状态。
```

需要提供函数：

```python
def get_llm_config() -> dict:
    ...
```

返回结构：

```python
{
    "provider": "openai",
    "model": "gpt-4.1-mini",
    "api_base": "https://api.openai.com/v1",
    "api_key_env": "OPENAI_API_KEY",
    "api_key_available": true
}
```

注意：API 返回结果中不得包含真实 API Key。

### 25.12 FastAPI 新增接口

新增接口：

```http
GET /llm/config
```

返回当前 LLM 配置状态，但不返回 API Key。

示例：

```json
{
  "provider": "openai",
  "model": "gpt-4.1-mini",
  "api_base": "https://api.openai.com/v1",
  "api_key_env": "OPENAI_API_KEY",
  "api_key_available": true
}
```

新增接口：

```http
POST /llm/test
```

MVP 阶段可以只检查配置是否完整，不实际调用外部 API。

返回：

```json
{
  "configured": true,
  "provider": "openai",
  "model": "gpt-4.1-mini",
  "api_key_available": true,
  "external_call_performed": false
}
```

### 25.13 安全要求

必须满足：

```text
1. API Key 不得打印到控制台；
2. API Key 不得写入普通日志；
3. API Key 不得出现在 FastAPI 响应中；
4. configs/llm.local.json 默认不保存明文 key；
5. 若用户选择保存 key，需要明确提示风险；
6. .gitignore 必须排除本地密钥文件；
7. 单元测试中不得使用真实 key；
8. 示例配置只能使用占位符。
```

### 25.14 README 新增说明

README 中新增章节：

```text
PowerShell TUI 启动器
```

内容包括：

```text
1. 启动命令；
2. 如何选择模型服务商；
3. 如何输入 API Key；
4. 如何仅启动数据闭环服务；
5. 如何查看当前 LLM 配置；
6. 如何清除配置；
7. 安全注意事项。
```

启动命令示例：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/start_agent_tui.ps1
```

跳过 LLM 配置：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/start_agent_tui.ps1 -SkipLlmConfig
```

不保存配置：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/start_agent_tui.ps1 -NoSave
```

### 25.15 测试要求

新增测试：

```text
tests/test_llm_config.py
```

检查：

```text
1. 没有环境变量时返回未配置状态；
2. 有环境变量时 api_key_available = true；
3. configs/llm.local.json 可被读取；
4. FastAPI /llm/config 不返回真实 API Key；
5. FastAPI /llm/test 不执行真实外部调用。
```

PowerShell 脚本至少要求：

```text
1. 能在 Windows PowerShell 5.1 或 PowerShell 7+ 中启动；
2. 无 API Key 时可选择跳过；
3. 输入非法 provider 时能重新提示；
4. 缺少 Python 时给出清晰错误；
5. 缺少依赖时给出安装提示。
```

### 25.16 验收标准补充

完成后，以下命令应可执行：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/start_agent_tui.ps1 -SkipLlmConfig
```

进入菜单后至少可执行：

```text
初始化数据库
扫描示例数据
导出 BO 数据集
查看配置
退出
```

配置 LLM 后，以下接口应可用：

```http
GET http://127.0.0.1:8000/llm/config
POST http://127.0.0.1:8000/llm/test
```

并且接口返回中不得出现真实 API Key。

---

## 24. 一句话总结

本任务不是做一个会聊天的 Agent，而是先搭建一个可审计的“超快激光加工专业知识记忆库与自学习数据闭环”。

LLM、RAG、BO 都是后续模块；本 MVP 的核心是让加工软件产生的文件稳定转化为可追溯、可审核、可优化的数据资产。
