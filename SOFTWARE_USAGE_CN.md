# 超快激光多工艺参数推荐软件说明

## 1. 软件概述

本软件用于超快激光加工实验数据的整理、建模、关键参数辨识和工艺参数推荐。软件当前支持两类工艺场景：

- `milling`：铣削、面加工、槽加工等去除加工场景；
- `cutting`：切割工艺场景。

软件的核心流程为：

```text
process_type → material → objective_mode → process_parameters
→ recommend → feedback → recommend-next
```

也就是说，用户先选择工艺场景、材料和加工目标，系统根据历史数据或冷启动规则推荐一组工艺参数；完成实验后，用户反馈加工结果，系统再根据反馈方向推荐下一轮参数。

当前软件已经具备完整的铣削数据建模与推荐流程。切割场景目前实现了数据接口、UI、冷启动规则推荐和反馈闭环，但当前仓库尚无切割实验数据，因此切割推荐属于 `rule_based_cold_start`，不是已训练贝叶斯优化模型的预测结果。

## 2. 软件主要功能

### 2.1 多工艺场景支持

软件通过 `process_type` 区分不同工艺场景：

| 工艺场景 | process_type | 当前状态 |
|---|---|---|
| 铣削 / 面加工 / 槽加工 | `milling` | 支持数据驱动建模、混合规则推荐和交互反馈 |
| 切割 | `cutting` | 支持接口、UI、冷启动推荐和反馈闭环；当前无切割数据 |

旧版本请求中如果没有 `process_type` 字段，系统默认按 `milling` 处理，以保证向后兼容。

### 2.2 实验数据清洗与统一

软件可以读取多材料实验数据表，并统一整理为标准数据结构。支持的输入文件包括 CSV 和 Excel。

统一后的实验数据包含工艺参数、质量指标、工艺场景、材料信息、数据来源和有效性标记。缺失字段保留为 `NaN`，系统不会编造缺失的激光功率、光斑、粗糙度或切割质量数据。

### 2.3 特征工程

软件会根据原始工艺参数构造建模特征。主要包括：

- 对脉宽、频率、填充间距、加工次数、扫描速度等变量取对数；
- 构造脉冲密度代理量；
- 构造单脉冲能量代理量；
- 构造面积能量代理量；
- 构造切割线能量代理量；
- 构造脉冲间距；
- 构造层间距相关特征。

常用特征包括：

```text
D_proxy
pulse_density_proxy
pulse_energy_uJ
areal_energy_proxy
line_energy_proxy
pulse_spacing_um
layer_count_proxy
```

其中：

```text
pulse_energy_uJ = 1000 * laser_power_W / frequency_kHz
areal_energy_proxy = laser_power_W * passes / (scan_speed_mm_s * hatch_spacing_um)
line_energy_proxy = laser_power_W / scan_speed_mm_s
pulse_spacing_um = scan_speed_mm_s / frequency_kHz
```

需要注意：如果旧数据没有 `laser_power_W`，功率相关特征会保留为 `NaN`，系统不会自动补值。

### 2.4 分材料建模

铣削场景中，软件可以按材料分别建立工艺参数到质量指标的代理模型。主要目标变量包括：

```text
depth_um
Sa_um
Sq_um
Sz_um
removal_rate_um3_s
```

当前建模流程支持：

- RSM 二阶响应面模型；
- GPR 高斯过程回归；
- Random Forest；
- XGBoost 或 HistGradientBoosting fallback；
- MLPRegressor 作为深度学习对照模型。

模型评价指标包括：

```text
MAE
RMSE
R2
CV_MAE
CV_RMSE
CV_R2
```

软件会输出模型性能汇总、预测结果、残差图、预测-实测散点图和关键参数重要性结果。

### 2.5 关键参数辨识

软件会根据模型结果输出关键工艺参数的重要性排序。支持的证据包括：

- 响应面模型系数；
- permutation importance；
- 树模型重要性；
- 单变量响应曲线。

输出结果用于判断不同材料中哪些参数更显著影响加工深度、表面粗糙度或加工效率。

### 2.6 贝叶斯优化推荐

铣削场景中，当某个 `process_type + material` 的有效样本数量足够时，系统可以使用代理模型和 acquisition function 推荐下一轮实验参数。

推荐模式包括：

| 推荐模式 | 含义 |
|---|---|
| `exploitation` | 偏向当前模型预测最优的区域 |
| `exploration` | 偏向模型不确定性较高的区域 |
| `balanced` | 兼顾预测性能和模型不确定性 |

系统推荐结果会记录预测均值、预测不确定性、acquisition score、反馈规则修正和最终选择理由。

### 2.7 切割冷启动推荐

当前仓库没有切割实验数据，因此切割场景不会训练切割代理模型，也不会输出虚假的切割质量预测。

当用户选择 `process_type = cutting` 时，系统会进入冷启动推荐模式：

```text
model_status = rule_based_cold_start
```

此时系统根据用户给定的参数边界、切割需求和反馈规则生成保守参数推荐。无法预测的字段会显式输出为 `null`，例如：

```text
cut_through_probability
kerf_top_width_um
kerf_bottom_width_um
kerf_taper_deg
cut_edge_Sa_um
HAZ_width_um
chipping_um
```

当后续积累足够切割实验数据后，可以复用相同接口切换到 `hybrid_rule_bo` 或 `data_driven_bo`。

### 2.8 五级反馈闭环

软件支持五级定性反馈：

```text
很小 = -2
较小 = -1
适中 = 0
较大 = +1
很大 = +2
```

旧版反馈值仍兼容：

```text
acceptable
too_large
too_small
too_shallow
too_deep
too_low
too_high
unknown
```

不同指标的方向含义不同。例如：

- 铣削粗糙度较大：系统倾向降低能量累积；
- 铣削深度较小：系统倾向提高去除强度；
- 切割未切透：系统倾向提高激光功率、降低扫描速度、增加加工次数、减小层间距；
- 切割过烧蚀：系统倾向降低激光功率、提高扫描速度、减少加工次数、增大层间距。

## 3. 安装方法

在仓库根目录下执行：

```bash
python -m pip install -r requirements.txt
```

如果未安装 `xgboost`，软件会自动 fallback 到 `HistGradientBoostingRegressor`，不影响主流程运行。

建议使用 Python 3.10 或更高版本。

## 4. 离线建模流程

离线建模用于批量处理已有实验数据、训练模型、输出参数重要性和贝叶斯优化推荐表。

运行命令：

```bash
python main.py --config config.yaml
```

主要输出包括：

```text
data/processed/unified_experiments.csv
data/processed/unified_experiments_with_features.csv
data/processed/data_quality_report.csv

outputs/model_performance_summary.csv
outputs/prediction_results.csv
outputs/feature_importance_summary.csv
outputs/bo_recommendations.csv
outputs/modeling_report.md

figures/*.png
```

其中：

- `unified_experiments.csv`：统一后的实验数据；
- `unified_experiments_with_features.csv`：加入特征工程后的数据；
- `data_quality_report.csv`：数据质量报告；
- `model_performance_summary.csv`：模型性能汇总；
- `feature_importance_summary.csv`：关键参数重要性；
- `bo_recommendations.csv`：离线贝叶斯优化推荐参数；
- `modeling_report.md`：自动生成的建模报告；
- `figures/`：模型评价图、残差图、特征重要性图和响应曲线图。

## 5. 交互式推荐流程

交互式推荐用于模拟真实实验中的“推荐—实验—反馈—再推荐”闭环。

### 5.1 铣削推荐

```bash
python main.py recommend --process-type milling --material SiC --objective quality_first
```

如果不写 `--process-type`，系统默认使用 `milling`：

```bash
python main.py recommend --material SiC --objective quality_first
```

### 5.2 切割冷启动推荐

```bash
python main.py recommend --process-type cutting --material SiC --objective quality_first
```

由于当前没有切割实验数据，该命令会返回冷启动推荐：

```text
model_status = rule_based_cold_start
```

切割预测字段会保持为 `null`。

### 5.3 提交反馈

铣削场景可以使用 CLI 直接反馈：

```bash
python main.py feedback \
  --task-id SiC_YYYYMMDD_001 \
  --iteration 1 \
  --roughness 很大 \
  --depth-status 适中 \
  --efficiency 很小
```

切割场景建议使用 JSON 反馈接口，因为切割反馈字段更多。

### 5.4 推荐下一组参数

```bash
python main.py recommend-next --task-id SiC_YYYYMMDD_001 --type balanced
```

系统会读取任务历史、上一轮推荐和用户反馈，生成下一轮参数推荐，并记录推荐理由。

## 6. JSON 接口使用

JSON 接口适合第三方测试和自动化调用。

### 6.1 运行任务请求

```bash
python main.py run-json --task-request inputs/task_request.json
```

### 6.2 提交反馈

```bash
python main.py feedback-json --feedback inputs/feedback.json
```

或：

```bash
python main.py feedback --feedback inputs/feedback.json
```

## 7. task_request.json 示例

### 7.1 铣削任务示例

```json
{
  "process_type": "milling",
  "material": "SiC",
  "objective_mode": "quality_first",
  "requirements": {
    "depth_min_um": 30,
    "Sa_max_um": 2.0
  },
  "parameter_bounds": {
    "pulse_width_ps": [0.3, 10],
    "frequency_kHz": [50, 500],
    "laser_power_W": [1, 20],
    "scan_speed_mm_s": [50, 2000],
    "passes": [1, 20],
    "hatch_spacing_um": [1, 20],
    "layer_step_um": [1, 20],
    "fill_pattern": ["zigzag", "contour", "concentric"]
  }
}
```

### 7.2 切割任务示例

```json
{
  "process_type": "cutting",
  "material": "SiC",
  "objective_mode": "quality_first",
  "requirements": {
    "material_thickness_um": 500,
    "cut_through_required": true,
    "target_kerf_width_um": 30,
    "max_taper_deg": 3,
    "max_edge_Sa_um": 2.0
  },
  "parameter_bounds": {
    "pulse_width_ps": [0.3, 10],
    "frequency_kHz": [50, 500],
    "laser_power_W": [1, 20],
    "scan_speed_mm_s": [10, 1000],
    "passes": [1, 30],
    "focus_offset_um": [-100, 100],
    "layer_step_um": [1, 20],
    "hatch_spacing_um": [1, 20],
    "fill_pattern": ["none", "contour", "polyline"]
  }
}
```

## 8. feedback.json 示例

### 8.1 铣削反馈示例

```json
{
  "task_id": "milling_SiC_001",
  "iteration": 1,
  "measured_result": {
    "depth_um": 28.7,
    "Sa_um": 2.4
  },
  "qualitative_feedback": {
    "surface_roughness_level": "较大",
    "depth_level": "适中",
    "efficiency_level": "较小"
  },
  "note": "粗糙度偏大，效率偏低。"
}
```

### 8.2 切割反馈示例

```json
{
  "task_id": "cutting_SiC_001",
  "iteration": 1,
  "measured_result": {
    "cut_through": false,
    "kerf_top_width_um": null,
    "kerf_bottom_width_um": null,
    "cut_edge_Sa_um": null,
    "chipping_um": null
  },
  "qualitative_feedback": {
    "cut_through_level": "未切透",
    "edge_roughness_level": "适中",
    "efficiency_level": "较小"
  },
  "note": "样品未切透，需要提高切割强度。"
}
```

切割 `cut_through_level` 支持：

```text
未切透
勉强切透
适中
过烧蚀
严重过烧蚀
```

其他反馈字段使用五级大小语义：

```text
很小 / 较小 / 适中 / 较大 / 很大
```

## 9. recommendation.json 说明

推荐结果至少包含：

```text
task_id
iteration
process_type
material
model_status
objective_mode
recommended_parameters
prediction
acquisition
reason
bo_component
feedback_interpretation
feedback_rule_component
final_selection_reason
```

其中：

- `recommended_parameters`：推荐工艺参数；
- `prediction`：模型预测结果；切割冷启动时无法预测的字段为 `null`；
- `acquisition`：贝叶斯优化采集函数信息；
- `bo_component`：代理模型和 BO 相关信息；
- `feedback_interpretation`：对上一轮反馈的解释；
- `feedback_rule_component`：反馈规则对推荐方向的影响；
- `final_selection_reason`：最终推荐理由。

切割冷启动推荐中，典型输出为：

```json
{
  "model_status": "rule_based_cold_start",
  "prediction": {
    "cut_through_probability": null,
    "kerf_top_width_um": null,
    "kerf_bottom_width_um": null,
    "kerf_taper_deg": null,
    "cut_edge_Sa_um": null,
    "HAZ_width_um": null,
    "chipping_um": null
  },
  "bo_component": {
    "surrogate_model": null,
    "acquisition": null
  }
}
```

## 10. model_status 说明

每次推荐都会返回 `model_status`：

| model_status | 含义 |
|---|---|
| `rule_based_cold_start` | 有效样本少于 10，使用规则冷启动推荐 |
| `hybrid_rule_bo` | 有效样本为 10–29，使用规则与 BO 混合推荐 |
| `data_driven_bo` | 有效样本不少于 30，可使用数据驱动 BO 推荐 |

有效样本数量按 `process_type + material` 统计。对具体目标变量建模时，还需要进一步检查该目标变量的有效样本数量。

当前切割场景没有有效切割数据，因此默认返回：

```text
model_status = rule_based_cold_start
```

## 11. UI 使用方法

启动 Streamlit UI：

```bash
python -m streamlit run src/ui_app.py
```

UI 支持：

- 工艺场景选择：铣削 / 切割；
- 材料选择；
- 加工目标选择：质量优先 / 效率优先 / 平衡；
- 激光功率范围输入；
- 脉宽、频率、扫描速度、加工次数输入；
- 填充方式选择；
- 填充间距输入；
- 层间距输入；
- 切割厚度、目标切缝宽度、最大锥度、最大断面粗糙度输入；
- 五级反馈输入；
- 生成下一轮推荐参数。

UI 显示中文填充方式，但保存时使用稳定内部枚举：

| UI 显示 | 内部枚举 |
|---|---|
| 弓字形 | `zigzag` |
| 回字形/轮廓 | `contour` |
| 同心圆 | `concentric` |
| 折线 | `polyline` |
| 螺旋 | `spiral` |
| 无填充/单线切割 | `none` |
| 自定义 | `custom` |

## 12. 统一数据字段说明

统一实验表主要字段如下：

```text
record_id
process_type
material

pulse_width_ps
frequency_kHz
laser_power_W
scan_speed_mm_s
passes
focus_offset_um

fill_pattern
hatch_spacing_um
layer_step_um
path_overlap_um

material_thickness_um
cut_length_mm

depth_um
Sa_um
Sq_um
Sz_um
removal_rate_um3_s

cut_through
kerf_top_width_um
kerf_bottom_width_um
kerf_taper_deg
cut_edge_Sa_um
HAZ_width_um
chipping_um

objective_mode
source_file
valid_flag
note
```

字段说明：

| 字段 | 含义 |
|---|---|
| `process_type` | 工艺场景，`milling` 或 `cutting` |
| `material` | 材料名称 |
| `pulse_width_ps` | 脉宽，单位 ps |
| `frequency_kHz` | 重复频率，单位 kHz |
| `laser_power_W` | 激光功率，单位 W |
| `scan_speed_mm_s` | 扫描速度或切割速度，单位 mm/s |
| `passes` | 加工次数或重复扫描次数 |
| `focus_offset_um` | 初始离焦量，单位 µm |
| `fill_pattern` | 填充方式 |
| `hatch_spacing_um` | 填充间距，单位 µm |
| `layer_step_um` | 层间距，即每层焦点下移距离，单位 µm |
| `depth_um` | 加工深度，单位 µm |
| `Sa_um` | 面粗糙度 Sa，单位 µm |
| `Sq_um` | 均方根粗糙度 Sq，单位 µm |
| `Sz_um` | 最大高度差 Sz，单位 µm |
| `cut_through` | 是否切透 |
| `kerf_top_width_um` | 上表面切缝宽度，单位 µm |
| `kerf_bottom_width_um` | 下表面切缝宽度，单位 µm |
| `kerf_taper_deg` | 切缝锥度，单位 ° |
| `cut_edge_Sa_um` | 切割断面粗糙度，单位 µm |
| `HAZ_width_um` | 热影响区宽度，单位 µm |
| `chipping_um` | 崩边尺寸，单位 µm |
| `valid_flag` | 数据是否有效 |
| `note` | 备注 |

## 13. 第三方测试建议

第三方测试可以按以下流程进行。

### 13.1 测试离线建模

```bash
python main.py --config config.yaml
```

检查是否生成：

```text
data/processed/unified_experiments.csv
outputs/model_performance_summary.csv
outputs/feature_importance_summary.csv
outputs/bo_recommendations.csv
outputs/modeling_report.md
```

### 13.2 测试铣削推荐

```bash
python main.py recommend --process-type milling --material SiC --objective quality_first
```

检查：

- 是否生成推荐参数；
- 是否包含 `model_status`；
- 是否包含预测结果；
- 是否能接受五级反馈；
- 下一轮推荐是否随反馈方向变化。

### 13.3 测试切割冷启动

```bash
python main.py run-json --task-request inputs/task_request.json
```

当 `task_request.json` 中 `process_type = cutting` 时，应检查：

- `process_type` 是否为 `cutting`；
- `model_status` 是否为 `rule_based_cold_start`；
- 切割预测字段是否为 `null`；
- `bo_component.surrogate_model` 是否为 `null`；
- 系统是否在没有切割数据的情况下正常运行；
- 反馈 `cut_through_level = 未切透` 后，下一轮推荐是否倾向提高切割强度；
- 反馈 `cut_through_level = 严重过烧蚀` 后，下一轮推荐是否倾向降低热输入。

## 14. 运行测试

执行：

```bash
pytest -q
```

测试内容应覆盖：

- 铣削旧接口兼容；
- 五级反馈映射；
- 填充方式中文和内部枚举映射；
- 功率相关特征单位换算；
- 切割冷启动推荐；
- 切割反馈方向；
- `model_status` 阈值；
- 无切割数据时不崩溃。

## 15. 当前限制

当前版本需要注意以下限制：

1. 切割场景当前没有实验数据，因此不能训练切割代理模型。
2. 切割推荐当前是规则冷启动推荐，不是已训练 BO 预测。
3. 如果实验数据缺少 `laser_power_W`，功率相关特征会保留为 `NaN`。
4. 如果缺少光斑直径、离焦量、脉冲能量、材料批次等信息，模型更多是统计代理模型，不能完整解释物理因果。
5. BO 推荐点需要通过实验验证，不能直接声明为全局最优。
6. 定性反馈只能提供方向性修正；数值反馈，如实测深度、Sa、切缝宽度、锥度等，更适合更新代理模型。

## 16. 推荐使用流程

实际使用时建议按以下顺序：

1. 准备原始实验数据；
2. 检查字段和单位；
3. 运行离线建模流程；
4. 查看数据质量报告和模型性能；
5. 根据材料选择推荐目标；
6. 获取第一组推荐参数；
7. 完成实验并记录实测结果；
8. 提交数值反馈或五级反馈；
9. 生成下一轮推荐；
10. 重复反馈和推荐，逐步优化工艺窗口。

## 17. 结题报告推荐表述

可在项目结题中表述为：

```text
本软件建立了面向超快激光加工的多工艺参数推荐系统，支持铣削和切割两类工艺场景。系统以实验数据库为基础，完成数据清洗、特征工程、分材料代理模型训练、关键参数辨识和贝叶斯优化推荐；同时支持五级定性反馈和人机闭环迭代推荐。对于已有铣削数据，系统可执行数据驱动或混合贝叶斯优化推荐；对于当前尚无实验数据的切割场景，系统实现了稳定接口、冷启动规则推荐和反馈闭环，为后续切割数据接入和数据驱动优化提供了可扩展框架。
```

## 18. 常见问题

### Q1：没有 `process_type` 的旧数据还能用吗？

可以。旧请求默认按 `milling` 处理。

### Q2：没有激光功率数据怎么办？

可以继续运行，但 `pulse_energy_uJ`、`areal_energy_proxy`、`line_energy_proxy` 等功率相关特征会是 `NaN`。系统不会自动编造功率。

### Q3：切割推荐是不是贝叶斯优化结果？

当前不是。当前没有切割实验数据，切割推荐是规则冷启动结果。后续有切割数据后，才能训练切割代理模型并切换到 `hybrid_rule_bo` 或 `data_driven_bo`。

### Q4：为什么反馈要用五级？

五级反馈比二值反馈能表达强度差异。例如“粗糙度很大”应比“粗糙度较大”触发更强的参数修正。

### Q5：推荐参数能直接作为最终最优参数吗？

不能。推荐参数是下一轮实验候选点，需要经过实验验证。

### Q6：质量优先和效率优先有什么区别？

质量优先通常优先降低粗糙度、锥度、崩边等质量指标；效率优先通常优先提高去除深度、去除率或扫描速度，但仍需满足质量约束。
