# Codex 任务二：BO 唯一内核、数据治理、Readiness 与模型生命周期

## 0. 任务定位

本任务解决：

```text
根目录旧 BO 与 Agent 新 BO 并存；
不同入口可能产生不一致推荐；
训练数据可能未严格按任务隔离；
反馈可能过早进入训练集；
模型可用性只按样本数判断；
模型、数据和推荐缺少完整版本；
不确定度与验证体系不足。
```

本任务不实现动态搜索空间。ParameterPolicy、fixed/forbidden/conditional 参数和 CAM 接口属于任务三。

建议拆成：

```text
PR 2A：BO 唯一内核、数据切片、Eligibility、Readiness
PR 2B：模型组件、评价、版本、Evolution 接入
```

---

# PR 2A：BO 唯一内核与数据治理

## 1. 确定唯一内核

正式内核：

```text
ultrafast_bo
```

所有入口必须调用同一 application service：

```python
BORecommendationService.recommend(...)
```

调用者至少包括：

```text
Agent BO Adapter；
根目录 CLI；
交互式 BO；
离线建模报告；
后续 CAM ProcessRecommendation。
```

根目录旧实现改为兼容层，仅允许：

```text
旧字段转换；
旧请求映射；
调用新 Service；
旧响应格式转换；
弃用提示。
```

不得保留第二套候选评分或模型训练逻辑。

---

## 2. 迁移前建立基线

固定至少 20～30 个测试任务，覆盖：

```text
不同材料；
不同 process_type；
冷启动；
数据充分；
缺少目标；
设备边界；
定性反馈；
切割无数据场景；
重复推荐；
异常反馈。
```

保存：

```text
输入；
旧推荐；
随机种子；
旧模型状态；
旧警告；
旧运行时间。
```

新实现允许改善行为，但必须对不兼容变化给出明确说明和新测试。

---

## 3. BODatasetSliceService

新增唯一数据切片服务：

```python
class BODatasetSliceService:
    def select(
        self,
        samples,
        *,
        material,
        process_type,
        equipment_profile_id=None,
        target_metric=None,
        measurement_method=None,
        process_stage=None,
        feature_schema_version=None,
    ):
        ...
```

默认严格过滤：

```text
material 完全匹配；
process_type 完全匹配；
目标指标存在；
valid_for_training=true 或等价批准状态；
设备相同或显式声明兼容；
测量方法相同或显式标准化；
单位 Schema 一致；
关键参数完整；
异常、报警、中断数据不直接进入训练。
```

禁止默认混合：

```text
不同材料；
cutting 与 milling/surface_micromachining；
不同测量定义；
不同设备能力；
试切失败记录与正常训练样本；
未经审核的 OCR/RAG/LLM 参数。
```

跨材料迁移学习只保留扩展接口，本轮不实现。

### 3.1 数据切片报告

返回：

```text
selected_sample_ids
excluded_counts_by_reason
material
process_type
equipment_scope
target_metric
measurement_scope
warnings
```

推荐审计必须保存该报告摘要。

---

## 4. 训练样本准入

新增或等价实现：

```text
BOTrainingSampleCandidate
BOEligibilityReport
ApprovedBOTrainingSample
```

反馈数据链：

```text
recommended_parameters
→ cam_applied_parameters
→ machine_actual_parameters
→ measurements
→ run_status / alarms
→ completeness validation
→ unit validation
→ anomaly validation
→ BO Eligibility
→ ApprovedBOTrainingSample
```

不得假定三组参数相同。

### 4.1 Eligibility 最低检查

```text
任务和推荐可追溯；
实际参数存在；
目标测量存在；
单位可标准化；
运行完成；
无阻塞型报警；
测量方法已知；
参数未越界；
非重复或重复有明确 replicate_id；
人工排除状态未设置。
```

Eligibility 返回：

```text
eligible
blocking_reasons
warnings
normalized_parameters
normalized_measurements
source_ids
```

---

## 5. BOReadinessAssessmentService

不再只使用：

```text
<10 / 10～29 / >=30
```

新增：

```python
class BOReadinessReport:
    model_status: str
    valid_sample_count: int
    complete_target_count: int
    complete_feature_count: int
    effective_dimension: int
    parameter_coverage: dict
    replicate_count: int
    noise_estimate: float | None
    validation_metrics: dict
    uncertainty_calibrated: bool
    blocking_reasons: list[str]
    warnings: list[str]
```

状态可沿用：

```text
rule_based_cold_start
hybrid_rule_bo
data_driven_bo
blocked
```

但判断必须综合：

```text
有效目标样本；
完整输入样本；
有效维度；
参数空间覆盖；
异常比例；
重复实验；
噪声；
交叉验证；
预测区间覆盖；
设备和批次一致性。
```

样本数量阈值只能作为其中一个条件。

---

## 6. 统一输出

PR 2A 阶段定义内部 BORecommendationResult：

```text
bo_run_id
status
model_status
task_scope
dataset_slice_report
readiness_report
recommended_parameters
predictions
uncertainty
warnings
blocking_reasons
model_version
dataset_version
feature_schema_version
objective_version
acquisition_version
random_seed
created_at
```

任务三会将其封装成完整 `ProcessRecommendation`。

---

## 7. PR 2A 测试

至少增加：

```text
test_dataset_slice_by_material.py
test_dataset_slice_by_process_type.py
test_dataset_slice_by_equipment.py
test_dataset_slice_by_target.py
test_invalid_feedback_not_training_sample.py
test_bo_readiness_not_sample_count_only.py
test_all_entrypoints_use_same_bo_service.py
test_legacy_adapter_does_not_reimplement_bo.py
```

关键回归：

```text
金刚石任务不得使用 SiC/CFRP 样本；
切割任务不得使用表面加工样本；
缺少实际参数的反馈不得进入训练；
同一输入、版本和随机种子可复现；
切割无数据仍明确返回冷启动，不伪造预测。
```

---

# PR 2B：模型组件、评价、版本与 Evolution 接入

## 8. BO 组件接口

至少定义：

```text
FeatureBuilder
ObjectiveBuilder
SurrogateModelFactory
AcquisitionStrategy
CandidateGenerator
ModelEvaluator
RecommendationRecorder
BOModelRegistry
```

接口应允许任务三扩展动态搜索空间，而不需要重写内核。

---

## 9. 首期模型基线

实现或统一：

```text
输入标准化；
输出标准化；
Matern 5/2；
ARD length scale；
显式 noise；
多次超参数重启；
固定随机种子；
失败时明确 fallback 或阻塞。
```

保留可替换接口，但本轮不引入深度 GP。

### 9.1 重复实验和噪声

若存在重复实验：

```text
按相同/近似参数分组；
估计观测噪声；
记录 replicate_count；
在评价中检查预测区间。
```

没有重复实验时，不得伪造精确噪声估计。

---

## 10. 候选和采集基线

PR 2B 只需要：

```text
Sobol/空间填充冷启动；
UCB 作为可复现基线；
候选去重；
固定随机种子；
历史推荐排除。
```

qLogNEI、概率约束和混合参数空间在任务三实现。

---

## 11. 评价体系

根据字段可用性实现：

```text
GroupKFold：按 task_id/workpiece_id/batch_id；
Time-based split：按迭代或时间；
Leave-one-batch-out：跨批次泛化。
```

指标至少包括：

```text
MAE
RMSE
negative log predictive density
prediction interval coverage
uncertainty calibration error
baseline comparison
```

必须与简单基线比较，例如：

```text
均值预测；
最近邻；
随机搜索 replay。
```

不能只报告训练拟合分数。

---

## 12. 版本对象

### 12.1 BODatasetVersion

```text
dataset_version_id
content_hash
sample_ids
slice_scope
feature_schema_version
created_at
```

### 12.2 BOModelArtifact

```text
model_version_id
artifact_path
model_type
hyperparameters
training_dataset_version
feature_schema_version
objective_version
code_version
random_seed
status
created_at
```

### 12.3 BOEvaluationRun

```text
evaluation_id
model_version_id
baseline_model_version_id
dataset_version
split_strategy
metrics
failures
passed
created_at
```

每次推荐必须关联精确模型和数据集版本。

---

## 13. 接入 Evolution Foundation

实现 BO 对象的真实 evaluator 和 promotion policy。

示例晋升门槛：

```text
验证误差不得显著劣于当前模型；
预测区间覆盖不低于设定阈值；
约束违规 replay 不增加；
所有 regression/safety tests 通过；
人工批准；
激活时保留当前模型作为 rollback target。
```

流程：

```text
新数据集版本
→ 训练候选模型
→ EvolutionCandidate
→ BOEvaluationRun
→ pending_approval
→ approved
→ active
→ 在线指标退化时 rollback
```

不允许新数据到达后直接替换在线模型。

---

## 14. 推荐复现

每次 BO run 至少记录：

```text
bo_run_id
training_sample_ids
dataset_version
model_version
feature_schema_version
objective_version
acquisition_version
random_seed
code_commit
equipment_profile_version
approved_prior_versions
```

提供内部 replay 命令或 service：

```text
replay_bo_run(bo_run_id)
```

在版本和依赖一致时应得到等价结果；存在浮点差异时使用明确容差。

---

## 15. PR 2B 测试

```text
test_gp_uses_ard.py
test_model_training_is_reproducible.py
test_group_split_avoids_leakage.py
test_prediction_interval_metrics.py
test_bo_model_version_registry.py
test_bo_candidate_requires_evaluation.py
test_bo_model_activation_and_rollback.py
test_bo_run_replay.py
```

---

## 16. 任务二最终验收

```text
1. 根目录 CLI、Agent、离线报告调用同一 BO 内核；
2. 不同材料和工艺不会默认混合；
3. 反馈不会自动成为训练样本；
4. Readiness 不只由总样本数决定；
5. GP 训练和候选生成可复现；
6. 不确定度有基础校准评价；
7. 每次推荐可追溯到精确数据和模型版本；
8. BO 模型可以通过 Evolution Foundation 评价、晋升和回滚；
9. 旧入口保持兼容或提供明确迁移方式；
10. 全部测试、Doctor 和 Demo 通过。
```

---

## 17. 任务二明确不做

```text
不实现 ParameterPolicy；
不实现 fixed/forbidden/conditional 参数；
不实现设备约束交集编译；
不实现 CAM API；
不实现多目标 Pareto；
不做跨材料迁移学习；
不做设备控制。
```
