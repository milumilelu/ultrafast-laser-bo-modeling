# Codex 任务三：动态约束搜索空间、CAM 参数交付、PaddleOCR 与视觉语义骨架

## 0. 任务定位

本任务在任务二唯一 BO 内核之上实现用户可感知的受约束推荐与外部交付能力：

```text
根据设备、任务和用户要求限制可调参数；
只优化允许调整的部分参数；
返回完整工艺 Recipe；
通过通用 JSON 契约交付 CAM；
实现首个厂商 Adapter；
接入 PaddleOCR；
实现默认关闭的图像语义 Provider 骨架。
```

建议拆成：

```text
PR 3A：ParameterPolicy、SearchSpaceBuilder、约束 BO
PR 3B：ProcessRecommendation、CAM JSON、首个厂商 Adapter、反馈闭环
PR 3C：PaddleOCR、后台任务接入、视觉语义实验骨架
```

---

# PR 3A：动态搜索空间与约束 BO

## 1. ParameterPolicy

每个参数必须支持以下模式或语义等价枚举：

```text
fixed
optimizable
bounded
integer
categorical
conditional
derived
forbidden
unavailable
unknown
```

示例：

```json
{
  "laser_power_W": {
    "mode": "optimizable",
    "lower": 2.0,
    "upper": 6.0
  },
  "frequency_kHz": {
    "mode": "fixed",
    "value": 200
  },
  "passes": {
    "mode": "integer",
    "lower": 1,
    "upper": 5
  },
  "fill_pattern": {
    "mode": "categorical",
    "allowed_values": ["contour"]
  },
  "focus_offset_um": {
    "mode": "forbidden",
    "reason": "fixture_constraint"
  }
}
```

### 1.1 固定参数语义

固定参数：

```text
参与历史数据筛选；
参与模型条件；
出现在完整 Recipe；
不进入 acquisition 的自由变量。
```

不得因为参数固定就从模型上下文中删除。

### 1.2 unknown

参数状态无法判断时必须返回 clarification/blocking，不得自动设为 optimizable。

---

## 2. SearchSpaceBuilder

定义：

```python
class SearchSpaceBuilder:
    def compile(
        self,
        task_spec,
        equipment_snapshot,
        parameter_policy,
        approved_priors,
        current_recipe,
        trial_mode,
    ) -> CompiledSearchSpace:
        ...
```

最终空间：

```text
设备硬边界
∩ 任务加工要求
∩ 用户允许调整范围
∩ 当前 Recipe 固定条件
∩ 已审核 Process Prior
∩ 当前试切/正式加工模式
= 本轮合法搜索空间
```

### 2.1 优先级

```text
设备硬边界：不可放宽；
任务显式固定/禁止：必须执行；
审核 Process Prior：可以收窄，不可放宽设备边界；
RAG/LLM 候选：不能直接修改正式边界；
BO：只在编译后的空间中优化。
```

### 2.2 区间交集

```text
final_lower = max(all lower bounds)
final_upper = min(all upper bounds)
```

若 `final_lower > final_upper`：

```text
status = infeasible_search_space
```

返回所有冲突来源，不得忽略其中一项。

### 2.3 CompiledSearchSpace

至少包含：

```text
variables
fixed_parameters
forbidden_parameters
derived_constraints
outcome_constraints
source_trace
search_space_version
feasibility_status
blocking_reasons
warnings
```

---

## 3. 参数类型

必须支持：

```text
continuous
integer
categorical
conditional
derived
fixed
```

设备步进必须显式建模：

```text
功率步进；
频率步进；
扫描速度步进；
passes 整数；
厂商枚举。
```

候选输出前投影到合法值，并再次验证。投影后若重复或失效，重新选择候选，不得静默返回非法点。

---

## 4. 耦合约束

不得执行用户提供的任意字符串代码。使用受控 Constraint Type。

首期至少支持：

```text
pulse_energy_max
pulse_energy_min
line_energy_max
areal_energy_max
parameter_sum_limit
parameter_product_limit
conditional_parameter_required
conditional_parameter_forbidden
```

示例：

```json
{
  "constraint_type": "pulse_energy_max",
  "threshold": 30,
  "unit": "uJ"
}
```

内部公式必须集中维护、带版本、带单位测试。

---

## 5. 结果约束

区分：

```text
输入约束：定义可搜索参数；
结果约束：限制加工质量或效率结果。
```

首期结果约束建议支持：

```text
Ra 最大值；
Sa 最大值；
深度最小值；
form_error 最大值；
graphitization_score 最大值；
加工时间最大值；
cut_through 必须满足。
```

推荐应返回：

```text
预测均值；
预测标准差；
每项约束满足概率；
总体可行概率；
不确定度警告。
```

第一阶段优先实现约束单目标：

```text
优化一个主目标
×
满足全部约束的概率
```

多目标 Pareto/qLogNEHVI 不在本任务强制范围。

---

## 6. Acquisition 增强

在任务二 UCB 基线基础上增加：

```text
qLogNEI 或等价有噪声 Expected Improvement；
概率可行性约束；
候选去重；
pending experiment；
局部与全局候选混合；
设备步进投影后再验证。
```

必须保留 UCB 作为 replay 基线并做历史对比。

若依赖 BoTorch，必须：

```text
固定版本；
记录依赖；
不删除现有离线 fallback；
提供 CPU 可运行测试；
失败时返回明确错误。
```

---

## 7. 特殊情况

### 7.1 一个参数可调

允许一维 BO。

### 7.2 没有参数可调

返回：

```text
no_optimizable_parameters
```

只评估当前 Recipe，不运行 BO。

### 7.3 空可行域

返回：

```text
infeasible_search_space
```

并列出冲突来源。

### 7.4 高维小样本

当可调维度相对样本过高时，Readiness 必须降级，建议固定部分参数或执行简化试切，不得假装数据驱动模型充分。

---

## 8. PR 3A 测试

```text
test_fixed_parameter_not_optimized.py
test_fixed_parameter_used_as_context.py
test_only_selected_parameters_are_optimized.py
test_device_bounds_cannot_be_relaxed.py
test_bound_intersection.py
test_infeasible_search_space.py
test_integer_and_step_projection.py
test_conditional_parameter.py
test_pulse_energy_constraint.py
test_outcome_feasibility_probability.py
test_no_optimizable_parameters.py
```

---

# PR 3B：ProcessRecommendation、CAM JSON、首个厂商 Adapter 与反馈闭环

## 9. ProcessRecommendation

定义正式领域对象：

```text
recommendation_id
task_id
workflow_id
iteration_number
parent_recommendation_id
process_type
material
component_type
stage
complete_recipe
optimized_parameters
fixed_parameters
forbidden_parameters
predictions
constraints
recommendation_source
confidence/support_status
model_version
dataset_version
search_space_version
objective_version
constraint_version
evidence_ids
prior_ids
status
created_at
expires_at
```

阶段至少支持：

```text
trial_cut
production_candidate
production_approved
reoptimization
manual_override
```

状态至少支持：

```text
ready_for_trial
ready_for_cam
pending_review
blocked
expired
superseded
```

### 9.1 完整 Recipe

即使只优化两个参数，返回值也必须包含完整参数集合，并标明来源：

```text
bo_recommendation
user_fixed
equipment_default
approved_process_prior
validated_rule
manual_override
```

不得只返回变化字段。

---

## 10. 通用 CAM JSON 契约

API：

```http
POST /api/v1/process-recommendations
GET /api/v1/process-recommendations/{recommendation_id}
GET /api/v1/process-recommendations/{recommendation_id}/cam-parameters
POST /api/v1/process-recommendations/{recommendation_id}/feedback
```

通用响应至少包含：

```json
{
  "schema_version": "1.0",
  "recommendation_id": "rec_001",
  "task_id": "task_001",
  "stage": "trial_cut",
  "status": "ready_for_cam",
  "process_type": "surface_micromachining",
  "material": "single_crystal_diamond",
  "parameters": {
    "laser_power_W": 5.0,
    "frequency_kHz": 200.0,
    "scan_speed_mm_s": 500.0,
    "passes": 3
  },
  "parameter_metadata": {
    "laser_power_W": {
      "source": "bo_recommendation",
      "mode": "optimizable",
      "unit": "W",
      "allowed_range": [2.0, 6.0]
    },
    "frequency_kHz": {
      "source": "user_fixed",
      "mode": "fixed",
      "unit": "kHz"
    }
  },
  "model_version": "...",
  "dataset_version": "...",
  "search_space_version": "...",
  "created_at": "...",
  "expires_at": null
}
```

规则：

```text
单位标准化；
字段名稳定；
Schema 有版本；
缺失字段使用 null/明确缺失，不伪造；
未通过校验不得 ready_for_cam；
不包含设备启动、停止或控制命令；
新增字段可兼容，修改语义必须升级 API/Schema 版本。
```

---

## 11. CAM Adapter 接口

```python
class CamAdapter:
    def validate_mapping(self, recommendation): ...
    def map_parameters(self, recommendation): ...
    def serialize(self, mapped_parameters): ...
```

实现：

```text
GenericJsonCamAdapter
ConfigDrivenCamAdapter
首个真实厂商 CamAdapter
```

Adapter 只允许：

```text
字段名映射；
单位转换；
枚举映射；
必填字段检查；
文件/JSON 序列化。
```

禁止：

```text
重新运行 BO；
修改推荐逻辑；
放宽边界；
用厂商默认值覆盖未授权缺失字段；
生成设备执行命令；
连接设备。
```

### 11.1 首个厂商 Adapter 资料要求

Codex 必须先读取：

```text
05_CAM_VENDOR_INPUT_TEMPLATE.md
```

以及仓库或用户提供的真实厂商资料。

若资料齐全：

```text
实现真实厂商 Adapter；
增加黄金样例；
实现字段/单位/枚举契约测试；
记录厂商格式版本。
```

若资料不齐全：

```text
实现 GenericJsonCamAdapter + ConfigDrivenCamAdapter；
生成明确阻塞报告；
不得虚构厂商字段；
不得将 demo profile 声称为真实厂商兼容。
```

---

## 12. 反馈接口

输入至少支持：

```text
run_id
recommendation_id
cam_applied_parameters
machine_actual_parameters
measurements
run_status
alarms
operator_comment
measurement_method
```

反馈处理：

```text
保存原始反馈；
关联推荐版本；
创建 BOTrainingSampleCandidate；
调用 Eligibility；
不得直接进入训练。
```

---

## 13. 试切与正式加工状态

试切：

```text
trial_planning
trial_parameters_ready
trial_exported_to_cam
trial_feedback_pending
trial_evaluating
trial_recommend_next
trial_completed
trial_blocked
```

正式加工：

```text
production_ready
production_parameters_ready
production_exported_to_cam
production_feedback_pending
production_quality_check
production_continue
production_reoptimization_required
production_completed
```

系统只记录外部状态，不读取设备、不控制设备。

每轮必须新建：

```text
recommendation_id
iteration_number
parent_recommendation_id
```

不得覆盖旧推荐。

---

## 14. PR 3B 测试

```text
test_cam_json_schema.py
test_cam_output_contains_complete_recipe.py
test_cam_output_marks_parameter_sources.py
test_not_ready_recommendation_not_exported.py
test_generic_cam_adapter.py
test_config_driven_cam_adapter.py
test_vendor_adapter_golden_file.py
test_cam_adapter_does_not_modify_values.py
test_feedback_links_recommendation.py
test_feedback_creates_candidate_not_training_sample.py
test_trial_iteration_version_chain.py
```

---

# PR 3C：PaddleOCR、后台任务接入与视觉语义实验骨架

## 15. OCR 范围

只使用：

```text
PaddleOCR
```

不接入其他 OCR 引擎，不训练模型。

原生文本 PDF：

```text
优先使用现有原生文本解析
```

扫描 PDF/图片：

```text
通过任务一 background_job 调用 PaddleOCR
```

---

## 16. OcrProvider

定义稳定接口：

```python
class OcrProvider:
    def parse(self, artifact) -> OcrDocument:
        ...
```

唯一实现：

```text
PaddleOcrProvider
```

业务层不得直接依赖 PaddleOCR SDK 输出结构。

---

## 17. DocumentElement

统一输出至少包含：

```text
document_id
page_number
element_id
element_type
content
bbox
confidence
parser_name
parser_version
source_image_hash
review_status
```

元素类型至少：

```text
title
paragraph
table
table_cell
caption
header
footer
formula_text
unknown
```

`formula_text` 不等于公式 AST。

---

## 18. OCR 质量门

流程：

```text
OCR Element
→ 参数抽取候选
→ 单位标准化
→ 设备/领域范围校验
→ 置信度评估
→ 人工确认状态
→ 结构化业务数据
```

关键字段使用更高阈值：

```text
波长；
脉宽；
平均功率；
脉冲能量；
频率；
扫描速度；
光斑；
焦点偏移；
粗糙度；
深度；
面形误差。
```

OCR 结果不得直接写入：

```text
process_recipe
measurement_record
process_prior
validated_rule
bo_training_sample
CAM Recipe
```

---

## 19. OCR 后台任务

任务必须支持：

```text
idempotency_key = document_hash + parser_version
页面级进度；
失败页面记录；
任务恢复；
原页面图像保留；
重复提交不重复导入。
```

---

## 20. 图像语义 Provider 骨架

定义：

```python
class VisionSemanticProvider:
    def analyze(
        self,
        image_artifact,
        analysis_type,
        context,
    ) -> VisionAnalysisCandidate:
        ...
```

实现多模态 LLM Adapter，但默认关闭。

输出：

```text
analysis_id
artifact_id
analysis_type
observations
regions
confidence
limitations
provider
model
prompt_version
status = experimental_unvalidated
created_at
```

### 20.1 默认配置

```yaml
experimental_features:
  vision_semantic_analysis:
    implemented: true
    enabled: false
    expose_api: false
    expose_chat_tool: false
    allow_rag_ingestion: false
    allow_knowledge_candidate: false
    allow_process_recommendation: false
    allow_bo_usage: false
    allow_cam_usage: false
```

### 20.2 不开放要求

```text
不注册 Chat Tool；
不在 /routes 显示；
不在 TUI 显示；
不提供公共 API；
不自动调用；
不写 RAG；
不进入 BO；
不进入 CAM。
```

只进行结构测试，不做准确率验收。

---

## 21. PR 3C 测试

```text
test_native_pdf_skips_ocr.py
test_scanned_pdf_creates_ocr_job.py
test_ocr_document_element_schema.py
test_ocr_job_idempotency.py
test_low_confidence_numeric_candidate_requires_review.py
test_ocr_data_not_written_to_bo.py
test_vision_feature_disabled.py
test_vision_not_registered_as_chat_tool.py
test_vision_result_is_experimental.py
test_api_key_not_logged.py
```

---

## 22. 任务三最终端到端验收

必须完成以下离线闭环：

```text
TaskSpec
→ ParameterPolicy
→ Equipment/Task/Prior Constraint Compilation
→ BO Readiness
→ Constrained BO Recommendation
→ Complete ProcessRecommendation
→ Generic CAM JSON Export
→ Vendor Adapter Export（资料齐全时）
→ External Feedback
→ BOTrainingSampleCandidate
→ Eligibility
→ Recommend Next
```

验收点：

```text
1. 用户可指定只调整功率和扫描速度；
2. 固定频率、脉宽和 passes 不被修改；
3. 设备硬边界不能被放宽；
4. 空可行域明确阻塞；
5. 耦合约束可过滤非法候选；
6. 推荐返回完整 Recipe；
7. CAM JSON 契约稳定、带版本；
8. Adapter 不修改推荐值；
9. 反馈关联原 recommendation_id；
10. OCR 不污染 BO；
11. 视觉语义默认关闭；
12. 全部测试、Doctor 和 Demo 通过。
```

---

## 23. 任务三明确不做

```text
不做设备连接或控制；
不做 CAD/CAM 几何和刀路；
不做认证/RBAC；
不做多 OCR；
不做视觉准确率验收；
不做无审核自动规则晋升；
不做多目标 Pareto 强制交付。
```
