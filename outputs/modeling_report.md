# 工艺参数-质量指标建模与贝叶斯优化推荐报告

## 数据概况

- 统一后总样本数：548
- 材料数：5
- 原始数据按 process_type + material 分组建模，避免铣削和切割数据混入同一目标函数。

| material   |   n_samples |   valid_rows |   valid_depth_samples |   valid_roughness_samples |   missing_field_ratio |   outlier_row_count |   missing_power_W_ratio |   missing_Sq_um_ratio |   missing_Sz_um_ratio |
|:-----------|------------:|-------------:|----------------------:|--------------------------:|----------------------:|--------------------:|------------------------:|----------------------:|----------------------:|
| AlSiC      |         120 |          120 |                   120 |                       120 |              0.608696 |                  14 |                       1 |                     0 |                     0 |
| CFRP       |         128 |          128 |                   128 |                       128 |              0.608696 |                  27 |                       1 |                     0 |                     0 |
| Diamond    |          60 |           52 |                    52 |                        52 |              0.707246 |                   8 |                       1 |                     1 |                     1 |
| SiC        |         120 |          120 |                   120 |                       120 |              0.608696 |                  21 |                       1 |                     0 |                     0 |
| ZrO2       |         120 |          120 |                   120 |                       120 |              0.608696 |                  16 |                       1 |                     0 |                     0 |

## 缺失值与单位说明

- 缺失字段保留为 NaN；未对关键工艺参数做均值填补。
- 标记为 fs 或数值尺度明显为飞秒的脉宽字段已转换为 ps。
- 标记为 mm 或数值尺度明显为毫米的填充间距字段已转换为 um。
- 若缺少 laser_power_W、power_W、Sq_um、Sz_um，记录保留，派生功率/能量代理特征保持 NaN。

## 特征工程

- 构造 log_pulse_width、log_frequency、log_hatch_spacing、log_passes、log_scan_speed。
- 构造 D_proxy = frequency_kHz * passes / (scan_speed_mm_s * hatch_spacing_um)。
- 构造 pulse_energy_uJ、areal_energy_proxy、line_energy_proxy、pulse_spacing_um 等功率和切割相关代理特征。
- D_proxy 是单位面积累计脉冲作用密度的统计代理量，不是严格能量密度。
- power_W 可用时才构造 pulse_energy_proxy 与 energy_density_proxy；当前缺失时不强行估计。

## 模型性能对比

| process_type   | material   | target   | model        |          MAE |         RMSE |        R2 |    CV_MAE |   CV_RMSE |        CV_R2 |   n_samples |   n_features |   cv_folds |
|:---------------|:-----------|:---------|:-------------|-------------:|-------------:|----------:|----------:|----------:|-------------:|------------:|-------------:|-----------:|
| milling        | AlSiC      | Sa_um    | GPR          |  0.014668    |  0.0354295   |  0.999787 |  0.883579 |  2.18694  |  0.18925     |         120 |           13 |          5 |
| milling        | AlSiC      | Sa_um    | RandomForest |  0.564166    |  1.50215     |  0.617494 |  0.962422 |  2.1956   |  0.182817    |         120 |           13 |          5 |
| milling        | AlSiC      | Sa_um    | XGBoost      |  0.274951    |  0.490083    |  0.959285 |  1.01835  |  2.43001  | -0.000991386 |         120 |           13 |          5 |
| milling        | AlSiC      | Sa_um    | MLP          |  0.905865    |  2.12685     |  0.23319  |  1.17522  |  2.48533  | -0.0470859   |         120 |           13 |          5 |
| milling        | AlSiC      | Sa_um    | RSM          |  0.71633     |  1.35368     |  0.689371 |  1.5561   |  2.94555  | -0.470775    |         120 |           13 |          5 |
| milling        | AlSiC      | depth_um | GPR          |  0.0877902   |  0.153152    |  0.999913 |  5.0997   | 10.2951   |  0.605702    |         120 |           13 |          5 |
| milling        | AlSiC      | depth_um | RSM          |  2.55504     |  4.31634     |  0.930691 |  5.95018  | 10.8979   |  0.558182    |         120 |           13 |          5 |
| milling        | AlSiC      | depth_um | RandomForest |  2.79462     |  5.3463      |  0.893667 |  6.30074  | 11.88     |  0.474961    |         120 |           13 |          5 |
| milling        | AlSiC      | depth_um | XGBoost      |  0.984198    |  1.30546     |  0.99366  |  5.98937  | 12.4974   |  0.418965    |         120 |           13 |          5 |
| milling        | AlSiC      | depth_um | MLP          |  6.92163     | 12.28        |  0.439008 |  9.81537  | 17.4156   | -0.12833     |         120 |           13 |          5 |
| milling        | CFRP       | Sa_um    | GPR          |  0.160703    |  0.208905    |  0.889642 |  0.400846 |  0.513504 |  0.333204    |         128 |           13 |          5 |
| milling        | CFRP       | Sa_um    | RandomForest |  0.206271    |  0.276821    |  0.806223 |  0.437164 |  0.578988 |  0.152296    |         128 |           13 |          5 |
| milling        | CFRP       | Sa_um    | XGBoost      |  0.12299     |  0.167332    |  0.929195 |  0.459839 |  0.593807 |  0.108348    |         128 |           13 |          5 |
| milling        | CFRP       | Sa_um    | MLP          |  0.573817    |  0.712884    | -0.28512  |  0.529441 |  0.667997 | -0.128377    |         128 |           13 |          5 |
| milling        | CFRP       | Sa_um    | RSM          |  0.26371     |  0.343655    |  0.701358 |  0.530112 |  0.69394  | -0.217724    |         128 |           13 |          5 |
| milling        | CFRP       | depth_um | GPR          |  1.64597     |  2.44547     |  0.983822 |  3.02373  |  4.61857  |  0.942294    |         128 |           13 |          5 |
| milling        | CFRP       | depth_um | XGBoost      |  0.875277    |  1.23648     |  0.995864 |  3.13786  |  4.9537   |  0.933616    |         128 |           13 |          5 |
| milling        | CFRP       | depth_um | MLP          |  2.94363     |  4.02715     |  0.956127 |  3.65433  |  5.21237  |  0.926502    |         128 |           13 |          5 |
| milling        | CFRP       | depth_um | RSM          |  1.59087     |  2.28289     |  0.985901 |  3.2941   |  5.42369  |  0.920422    |         128 |           13 |          5 |
| milling        | CFRP       | depth_um | RandomForest |  1.85734     |  3.00675     |  0.975543 |  3.84161  |  5.92722  |  0.90496     |         128 |           13 |          5 |
| milling        | Diamond    | Sa_um    | MLP          |  0.132541    |  0.18098     |  0.78448  |  0.209569 |  0.28814  |  0.453699    |          52 |           13 |          5 |
| milling        | Diamond    | Sa_um    | XGBoost      |  0.0216952   |  0.0291737   |  0.9944   |  0.195378 |  0.292826 |  0.435787    |          52 |           13 |          5 |
| milling        | Diamond    | Sa_um    | RandomForest |  0.0955523   |  0.16376     |  0.823542 |  0.202508 |  0.322705 |  0.314771    |          52 |           13 |          5 |
| milling        | Diamond    | Sa_um    | GPR          |  0.0774463   |  0.113301    |  0.915531 |  0.197242 |  0.358088 |  0.156266    |          52 |           13 |          5 |
| milling        | Diamond    | Sa_um    | RSM          |  0.0421715   |  0.0580363   |  0.977837 |  0.281046 |  0.500652 | -0.649288    |          52 |           13 |          5 |
| milling        | Diamond    | depth_um | XGBoost      |  0.461048    |  0.644076    |  0.999418 |  5.30572  |  7.49473  |  0.921136    |          52 |           13 |          5 |
| milling        | Diamond    | depth_um | RandomForest |  3.25379     |  4.18537     |  0.975406 |  7.2492   |  9.46079  |  0.874333    |          52 |           13 |          5 |
| milling        | Diamond    | depth_um | GPR          |  0.000780117 |  0.00111903  |  1        |  7.58501  | 11.7793   |  0.805193    |          52 |           13 |          5 |
| milling        | Diamond    | depth_um | MLP          |  4.47068     |  6.1743      |  0.946477 | 10.8859   | 14.6253   |  0.699684    |          52 |           13 |          5 |
| milling        | Diamond    | depth_um | RSM          |  1.40971     |  2.02828     |  0.994224 | 11.2543   | 27.8787   | -0.0912251   |          52 |           13 |          5 |
| milling        | SiC        | Sa_um    | GPR          |  0.000636589 |  0.000827659 |  1        |  1.76263  |  2.30023  | -0.0162801   |         120 |           13 |          5 |
| milling        | SiC        | Sa_um    | RandomForest |  1.01647     |  1.37433     |  0.637211 |  1.89621  |  2.47659  | -0.178094    |         120 |           13 |          5 |
| milling        | SiC        | Sa_um    | MLP          |  1.49927     |  2.11877     |  0.137737 |  1.61663  |  2.53536  | -0.234667    |         120 |           13 |          5 |
| milling        | SiC        | Sa_um    | XGBoost      |  0.70485     |  1.01703     |  0.801328 |  2.0485   |  2.75795  | -0.460979    |         120 |           13 |          5 |
| milling        | SiC        | Sa_um    | RSM          |  1.2315      |  1.63251     |  0.488103 |  2.30351  |  3.06863  | -0.808672    |         120 |           13 |          5 |
| milling        | SiC        | depth_um | GPR          |  0.00588404  |  0.00747202  |  1        | 16.3578   | 20.8271   | -0.0222449   |         120 |           13 |          5 |
| milling        | SiC        | depth_um | MLP          | 14.4254      | 19.3103      |  0.121225 | 14.3504   | 22.3973   | -0.182197    |         120 |           13 |          5 |
| milling        | SiC        | depth_um | RandomForest |  9.36054     | 12.2342      |  0.647268 | 17.8702   | 22.7842   | -0.223392    |         120 |           13 |          5 |
| milling        | SiC        | depth_um | XGBoost      |  6.24857     |  8.73907     |  0.820018 | 18.3442   | 24.6314   | -0.429805    |         120 |           13 |          5 |
| milling        | SiC        | depth_um | RSM          | 11.4223      | 15.3657      |  0.443579 | 22.5281   | 28.7529   | -0.948316    |         120 |           13 |          5 |
| milling        | ZrO2       | Sa_um    | MLP          |  0.726486    |  1.31296     |  0.179259 |  0.749435 |  1.39204  |  0.0774131   |         120 |           13 |          5 |
| milling        | ZrO2       | Sa_um    | RandomForest |  0.422483    |  0.791581    |  0.701673 |  0.813847 |  1.40495  |  0.0602243   |         120 |           13 |          5 |
| milling        | ZrO2       | Sa_um    | RSM          |  0.513815    |  0.695756    |  0.76953  |  1.00152  |  1.4658   | -0.0229364   |         120 |           13 |          5 |
| milling        | ZrO2       | Sa_um    | GPR          |  8.23083e-05 |  0.000517223 |  1        |  0.823263 |  1.47212  | -0.0317768   |         120 |           13 |          5 |
| milling        | ZrO2       | Sa_um    | XGBoost      |  0.196044    |  0.285747    |  0.961126 |  0.830282 |  1.4957   | -0.0650989   |         120 |           13 |          5 |
| milling        | ZrO2       | depth_um | GPR          |  1.11069     |  1.57426     |  0.994008 |  3.69101  |  5.78245  |  0.919157    |         120 |           13 |          5 |
| milling        | ZrO2       | depth_um | XGBoost      |  0.89827     |  1.26866     |  0.996109 |  4.00708  |  6.46714  |  0.898879    |         120 |           13 |          5 |
| milling        | ZrO2       | depth_um | RSM          |  2.00964     |  2.74727     |  0.981752 |  4.2926   |  6.58066  |  0.895298    |         120 |           13 |          5 |
| milling        | ZrO2       | depth_um | MLP          |  3.35223     |  4.63807     |  0.94799  |  5.24338  |  7.21239  |  0.87423     |         120 |           13 |          5 |
| milling        | ZrO2       | depth_um | RandomForest |  2.08299     |  3.38889     |  0.972233 |  4.54516  |  7.22787  |  0.87369     |         120 |           13 |          5 |

## 每种材料的最佳模型

| process_type | material | target | best_model | CV_RMSE | CV_R2 | n_samples |
|---|---|---|---:|---:|---:|---:|
| milling | AlSiC | depth_um | GPR | 10.3 | 0.6057 | 120 |
| milling | AlSiC | Sa_um | GPR | 2.187 | 0.1893 | 120 |
| milling | CFRP | depth_um | GPR | 4.619 | 0.9423 | 128 |
| milling | CFRP | Sa_um | GPR | 0.5135 | 0.3332 | 128 |
| milling | Diamond | depth_um | XGBoost | 7.495 | 0.9211 | 52 |
| milling | Diamond | Sa_um | XGBoost | 0.2928 | 0.4358 | 52 |
| milling | SiC | depth_um | GPR | 20.83 | -0.02224 | 120 |
| milling | SiC | Sa_um | GPR | 2.3 | -0.01628 | 120 |
| milling | ZrO2 | depth_um | GPR | 5.782 | 0.9192 | 120 |
| milling | ZrO2 | Sa_um | RandomForest | 1.405 | 0.06022 | 120 |

## 关键参数辨识结果

排序来自模型结果，不预设任何参数的重要性。RSM 证据为二阶响应面系数绝对值聚合；非线性证据为最佳模型的 permutation importance。

| process_type   | material   | target   | model   | feature             |   importance_value | method               |   importance_rank |
|:---------------|:-----------|:---------|:--------|:--------------------|-------------------:|:---------------------|------------------:|
| milling        | AlSiC      | Sa_um    | RSM     | pulse_width_ps      |          7.59654   | RSM_abs_coefficient  |                 1 |
| milling        | AlSiC      | Sa_um    | RSM     | log_passes          |          6.68036   | RSM_abs_coefficient  |                 2 |
| milling        | AlSiC      | Sa_um    | RSM     | log_scan_speed      |          5.27548   | RSM_abs_coefficient  |                 3 |
| milling        | AlSiC      | Sa_um    | RSM     | log_hatch_spacing   |          4.88333   | RSM_abs_coefficient  |                 4 |
| milling        | AlSiC      | Sa_um    | RSM     | log_pulse_width     |          4.7177    | RSM_abs_coefficient  |                 5 |
| milling        | AlSiC      | Sa_um    | RSM     | hatch_spacing_um    |          4.58119   | RSM_abs_coefficient  |                 6 |
| milling        | AlSiC      | Sa_um    | RSM     | scan_speed_mm_s     |          4.508     | RSM_abs_coefficient  |                 7 |
| milling        | AlSiC      | Sa_um    | RSM     | passes              |          4.25162   | RSM_abs_coefficient  |                 8 |
| milling        | AlSiC      | Sa_um    | RSM     | log_frequency       |          3.55596   | RSM_abs_coefficient  |                 9 |
| milling        | AlSiC      | Sa_um    | RSM     | pulse_density_proxy |          3.3752    | RSM_abs_coefficient  |                10 |
| milling        | AlSiC      | Sa_um    | RSM     | D_proxy             |          3.3752    | RSM_abs_coefficient  |                11 |
| milling        | AlSiC      | Sa_um    | RSM     | frequency_kHz       |          3.14484   | RSM_abs_coefficient  |                12 |
| milling        | AlSiC      | Sa_um    | RSM     | pulse_spacing_um    |          2.84594   | RSM_abs_coefficient  |                13 |
| milling        | AlSiC      | Sa_um    | GPR     | frequency_kHz       |          1.56755   | permutation_neg_RMSE |                 1 |
| milling        | AlSiC      | Sa_um    | GPR     | pulse_width_ps      |          1.50407   | permutation_neg_RMSE |                 2 |
| milling        | AlSiC      | Sa_um    | GPR     | D_proxy             |          1.22864   | permutation_neg_RMSE |                 3 |
| milling        | AlSiC      | Sa_um    | GPR     | pulse_density_proxy |          1.22864   | permutation_neg_RMSE |                 4 |
| milling        | AlSiC      | Sa_um    | GPR     | log_frequency       |          1.19052   | permutation_neg_RMSE |                 5 |
| milling        | AlSiC      | Sa_um    | GPR     | log_hatch_spacing   |          1.16659   | permutation_neg_RMSE |                 6 |
| milling        | AlSiC      | Sa_um    | GPR     | log_scan_speed      |          1.1555    | permutation_neg_RMSE |                 7 |
| milling        | AlSiC      | Sa_um    | GPR     | log_passes          |          1.12996   | permutation_neg_RMSE |                 8 |
| milling        | AlSiC      | Sa_um    | GPR     | scan_speed_mm_s     |          1.10225   | permutation_neg_RMSE |                 9 |
| milling        | AlSiC      | Sa_um    | GPR     | passes              |          1.09195   | permutation_neg_RMSE |                10 |
| milling        | AlSiC      | Sa_um    | GPR     | hatch_spacing_um    |          1.08244   | permutation_neg_RMSE |                11 |
| milling        | AlSiC      | Sa_um    | GPR     | log_pulse_width     |          0.982057  | permutation_neg_RMSE |                12 |
| milling        | AlSiC      | Sa_um    | GPR     | pulse_spacing_um    |          0.745342  | permutation_neg_RMSE |                13 |
| milling        | AlSiC      | depth_um | RSM     | frequency_kHz       |         45.0656    | RSM_abs_coefficient  |                 1 |
| milling        | AlSiC      | depth_um | RSM     | D_proxy             |         28.3139    | RSM_abs_coefficient  |                 2 |
| milling        | AlSiC      | depth_um | RSM     | pulse_density_proxy |         28.3139    | RSM_abs_coefficient  |                 3 |
| milling        | AlSiC      | depth_um | RSM     | pulse_width_ps      |         23.1722    | RSM_abs_coefficient  |                 4 |
| milling        | AlSiC      | depth_um | RSM     | hatch_spacing_um    |         23.0146    | RSM_abs_coefficient  |                 5 |
| milling        | AlSiC      | depth_um | RSM     | log_pulse_width     |         20.1761    | RSM_abs_coefficient  |                 6 |
| milling        | AlSiC      | depth_um | RSM     | log_frequency       |         19.5409    | RSM_abs_coefficient  |                 7 |
| milling        | AlSiC      | depth_um | RSM     | log_passes          |         18.6929    | RSM_abs_coefficient  |                 8 |
| milling        | AlSiC      | depth_um | RSM     | pulse_spacing_um    |         16.911     | RSM_abs_coefficient  |                 9 |
| milling        | AlSiC      | depth_um | RSM     | log_hatch_spacing   |         16.0616    | RSM_abs_coefficient  |                10 |
| milling        | AlSiC      | depth_um | RSM     | log_scan_speed      |         15.7757    | RSM_abs_coefficient  |                11 |
| milling        | AlSiC      | depth_um | RSM     | passes              |         15.0407    | RSM_abs_coefficient  |                12 |
| milling        | AlSiC      | depth_um | RSM     | scan_speed_mm_s     |         10.6565    | RSM_abs_coefficient  |                13 |
| milling        | AlSiC      | depth_um | GPR     | pulse_density_proxy |          8.0306    | permutation_neg_RMSE |                 1 |
| milling        | AlSiC      | depth_um | GPR     | D_proxy             |          8.0306    | permutation_neg_RMSE |                 2 |
| milling        | AlSiC      | depth_um | GPR     | frequency_kHz       |          6.38221   | permutation_neg_RMSE |                 3 |
| milling        | AlSiC      | depth_um | GPR     | pulse_width_ps      |          5.97915   | permutation_neg_RMSE |                 4 |
| milling        | AlSiC      | depth_um | GPR     | log_frequency       |          5.19732   | permutation_neg_RMSE |                 5 |
| milling        | AlSiC      | depth_um | GPR     | log_passes          |          4.75142   | permutation_neg_RMSE |                 6 |
| milling        | AlSiC      | depth_um | GPR     | passes              |          4.32448   | permutation_neg_RMSE |                 7 |
| milling        | AlSiC      | depth_um | GPR     | log_pulse_width     |          4.21439   | permutation_neg_RMSE |                 8 |
| milling        | AlSiC      | depth_um | GPR     | hatch_spacing_um    |          4.0797    | permutation_neg_RMSE |                 9 |
| milling        | AlSiC      | depth_um | GPR     | log_hatch_spacing   |          3.87504   | permutation_neg_RMSE |                10 |
| milling        | AlSiC      | depth_um | GPR     | log_scan_speed      |          3.24473   | permutation_neg_RMSE |                11 |
| milling        | AlSiC      | depth_um | GPR     | pulse_spacing_um    |          3.14045   | permutation_neg_RMSE |                12 |
| milling        | AlSiC      | depth_um | GPR     | scan_speed_mm_s     |          2.99959   | permutation_neg_RMSE |                13 |
| milling        | CFRP       | Sa_um    | RSM     | scan_speed_mm_s     |          1.73286   | RSM_abs_coefficient  |                 1 |
| milling        | CFRP       | Sa_um    | RSM     | log_frequency       |          1.59639   | RSM_abs_coefficient  |                 2 |
| milling        | CFRP       | Sa_um    | RSM     | log_pulse_width     |          1.54354   | RSM_abs_coefficient  |                 3 |
| milling        | CFRP       | Sa_um    | RSM     | passes              |          1.50935   | RSM_abs_coefficient  |                 4 |
| milling        | CFRP       | Sa_um    | RSM     | pulse_width_ps      |          1.48786   | RSM_abs_coefficient  |                 5 |
| milling        | CFRP       | Sa_um    | RSM     | log_hatch_spacing   |          1.47875   | RSM_abs_coefficient  |                 6 |
| milling        | CFRP       | Sa_um    | RSM     | log_passes          |          1.45077   | RSM_abs_coefficient  |                 7 |
| milling        | CFRP       | Sa_um    | RSM     | frequency_kHz       |          1.38891   | RSM_abs_coefficient  |                 8 |
| milling        | CFRP       | Sa_um    | RSM     | hatch_spacing_um    |          1.22883   | RSM_abs_coefficient  |                 9 |
| milling        | CFRP       | Sa_um    | RSM     | log_scan_speed      |          1.11741   | RSM_abs_coefficient  |                10 |
| milling        | CFRP       | Sa_um    | RSM     | pulse_density_proxy |          0.991202  | RSM_abs_coefficient  |                11 |
| milling        | CFRP       | Sa_um    | RSM     | D_proxy             |          0.991202  | RSM_abs_coefficient  |                12 |
| milling        | CFRP       | Sa_um    | RSM     | pulse_spacing_um    |          0.934038  | RSM_abs_coefficient  |                13 |
| milling        | CFRP       | Sa_um    | GPR     | frequency_kHz       |          0.232561  | permutation_neg_RMSE |                 1 |
| milling        | CFRP       | Sa_um    | GPR     | log_frequency       |          0.168353  | permutation_neg_RMSE |                 2 |
| milling        | CFRP       | Sa_um    | GPR     | hatch_spacing_um    |          0.145392  | permutation_neg_RMSE |                 3 |
| milling        | CFRP       | Sa_um    | GPR     | pulse_width_ps      |          0.143408  | permutation_neg_RMSE |                 4 |
| milling        | CFRP       | Sa_um    | GPR     | log_pulse_width     |          0.142951  | permutation_neg_RMSE |                 5 |
| milling        | CFRP       | Sa_um    | GPR     | log_hatch_spacing   |          0.141221  | permutation_neg_RMSE |                 6 |
| milling        | CFRP       | Sa_um    | GPR     | log_scan_speed      |          0.133858  | permutation_neg_RMSE |                 7 |
| milling        | CFRP       | Sa_um    | GPR     | scan_speed_mm_s     |          0.133677  | permutation_neg_RMSE |                 8 |
| milling        | CFRP       | Sa_um    | GPR     | pulse_spacing_um    |          0.1248    | permutation_neg_RMSE |                 9 |
| milling        | CFRP       | Sa_um    | GPR     | passes              |          0.123616  | permutation_neg_RMSE |                10 |
| milling        | CFRP       | Sa_um    | GPR     | log_passes          |          0.109501  | permutation_neg_RMSE |                11 |
| milling        | CFRP       | Sa_um    | GPR     | D_proxy             |          0.0786868 | permutation_neg_RMSE |                12 |
| milling        | CFRP       | Sa_um    | GPR     | pulse_density_proxy |          0.0786868 | permutation_neg_RMSE |                13 |
| milling        | CFRP       | depth_um | RSM     | log_frequency       |         22.0881    | RSM_abs_coefficient  |                 1 |
| milling        | CFRP       | depth_um | RSM     | log_scan_speed      |         15.6877    | RSM_abs_coefficient  |                 2 |

## 贝叶斯优化推荐参数

BO 推荐用于规划下一轮实验点，不证明已经找到全局最优。候选点限制在已有实验参数水平或观测范围内。

| process_type   | material   |   rank | recommendation_type   |   pulse_width_ps |   frequency_kHz |   laser_power_W |   hatch_spacing_um |   passes |   scan_speed_mm_s |   focus_offset_um |   layer_step_um | fill_pattern   |   predicted_depth_um |   predicted_depth_std_um |   predicted_Sa_um |   predicted_Sa_std_um |   predicted_cut_through |   predicted_cut_through_std |   predicted_kerf_top_width_um |   predicted_kerf_taper_deg |   predicted_cut_edge_Sa_um |   predicted_chipping_um |   objective_value |   acquisition_score | roughness_model_available   | note                                                     |
|:---------------|:-----------|-------:|:----------------------|-----------------:|----------------:|----------------:|-------------------:|---------:|------------------:|------------------:|----------------:|:---------------|---------------------:|-------------------------:|------------------:|----------------------:|------------------------:|----------------------------:|------------------------------:|---------------------------:|---------------------------:|------------------------:|------------------:|--------------------:|:----------------------------|:---------------------------------------------------------|
| milling        | AlSiC      |      1 | exploitation          |            0.223 |               5 |             nan |                  4 |        4 |            175    |               nan |             nan | none           |             10.3303  |                 4.4203   |       1.33711     |             1.82451   |                     nan |                         nan |                           nan |                        nan |                        nan |                     nan |        0.171308   |         -0.171308   | True                        | target_depth not configured; using observed median depth |
| milling        | AlSiC      |      2 | exploitation          |            0.5   |               5 |             nan |                  4 |        4 |            175    |               nan |             nan | none           |              9.85837 |                 3.1253   |       1.23549     |             1.48242   |                     nan |                         nan |                           nan |                        nan |                        nan |                     nan |        0.18706    |         -0.18706    | True                        | target_depth not configured; using observed median depth |
| milling        | AlSiC      |      3 | exploitation          |            0.5   |               2 |             nan |                  2 |        5 |            175    |               nan |             nan | none           |             10.1582  |                 5.40837  |       1.50704     |             1.94984   |                     nan |                         nan |                           nan |                        nan |                        nan |                     nan |        0.203352   |         -0.203352   | True                        | target_depth not configured; using observed median depth |
| milling        | AlSiC      |      4 | exploitation          |            0.223 |               2 |             nan |                  2 |        4 |            175    |               nan |             nan | none           |             10.2674  |                 3.78807  |       1.63263     |             1.54322   |                     nan |                         nan |                           nan |                        nan |                        nan |                     nan |        0.212677   |         -0.212677   | True                        | target_depth not configured; using observed median depth |
| milling        | AlSiC      |      5 | exploitation          |            0.5   |               5 |             nan |                  4 |        5 |            200    |               nan |             nan | none           |             11.0765  |                 4.49165  |       1.37304     |             1.80827   |                     nan |                         nan |                           nan |                        nan |                        nan |                     nan |        0.218378   |         -0.218378   | True                        | target_depth not configured; using observed median depth |
| milling        | CFRP       |      1 | exploitation          |            4     |               2 |             nan |                  2 |        3 |              1    |               nan |             nan | none           |             16.159   |                 3.90355  |       1.30461     |             0.531371  |                     nan |                         nan |                           nan |                        nan |                        nan |                     nan |        0.194587   |         -0.194587   | True                        | target_depth not configured; using observed median depth |
| milling        | CFRP       |      2 | exploitation          |            4     |               2 |             nan |                  3 |        3 |              1    |               nan |             nan | none           |             16.5861  |                 3.52183  |       1.20307     |             0.465475  |                     nan |                         nan |                           nan |                        nan |                        nan |                     nan |        0.201771   |         -0.201771   | True                        | target_depth not configured; using observed median depth |
| milling        | CFRP       |      3 | exploitation          |            4     |               2 |             nan |                  5 |        3 |              1    |               nan |             nan | none           |             15.9683  |                 3.89889  |       1.33506     |             0.520116  |                     nan |                         nan |                           nan |                        nan |                        nan |                     nan |        0.203818   |         -0.203818   | True                        | target_depth not configured; using observed median depth |
| milling        | CFRP       |      4 | exploitation          |            4     |               2 |             nan |                  5 |        4 |              1    |               nan |             nan | none           |             16.2452  |                 3.8244   |       1.34348     |             0.48456   |                     nan |                         nan |                           nan |                        nan |                        nan |                     nan |        0.204777   |         -0.204777   | True                        | target_depth not configured; using observed median depth |
| milling        | CFRP       |      5 | exploitation          |            0.5   |              20 |             nan |                  2 |        1 |              5    |               nan |             nan | none           |             16.2147  |                 5.5934   |       1.53571     |             0.615215  |                     nan |                         nan |                           nan |                        nan |                        nan |                     nan |        0.231488   |         -0.231488   | True                        | target_depth not configured; using observed median depth |
| milling        | Diamond    |      1 | exploitation          |            0.5   |               2 |             nan |                  5 |        7 |              0.05 |               nan |             nan | none           |             62.0067  |                 3.59104  |      -0.000742209 |             0.194581  |                     nan |                         nan |                           nan |                        nan |                        nan |                     nan |        0.00324028 |         -0.00324028 | True                        | target_depth not configured; using observed median depth |
| milling        | Diamond    |      2 | exploitation          |            0.223 |               2 |             nan |                  5 |       10 |              0.2  |               nan |             nan | none           |             60.7335  |                 8.25057  |      -0.041779    |             0.229468  |                     nan |                         nan |                           nan |                        nan |                        nan |                     nan |        0.00673265 |         -0.00673265 | True                        | target_depth not configured; using observed median depth |
| milling        | Diamond    |      3 | exploitation          |            2     |               2 |             nan |                  4 |        7 |              0.05 |               nan |             nan | none           |             62.3307  |                 3.75879  |       0.0415251   |             0.194564  |                     nan |                         nan |                           nan |                        nan |                        nan |                     nan |        0.0190501  |         -0.0190501  | True                        | target_depth not configured; using observed median depth |
| milling        | Diamond    |      4 | exploitation          |            0.223 |               2 |             nan |                  4 |       10 |              0.2  |               nan |             nan | none           |             63.5339  |                 6.5834   |      -0.0145082   |             0.210871  |                     nan |                         nan |                           nan |                        nan |                        nan |                     nan |        0.0245133  |         -0.0245133  | True                        | target_depth not configured; using observed median depth |
| milling        | Diamond    |      5 | exploitation          |            4     |              20 |             nan |                  1 |        4 |              0.5  |               nan |             nan | none           |             62.1644  |                 5.47767  |       0.0818848   |             0.207407  |                     nan |                         nan |                           nan |                        nan |                        nan |                     nan |        0.0264495  |         -0.0264495  | True                        | target_depth not configured; using observed median depth |
| milling        | SiC        |      1 | exploitation          |            0.5   |               2 |             nan |                  8 |        5 |             20    |               nan |             nan | none           |              6.01483 |                 0.554779 |       0.501515    |             0.0614517 |                     nan |                         nan |                           nan |                        nan |                        nan |                     nan |        0.173391   |         -0.173391   | True                        | target_depth not configured; using observed median depth |
| milling        | SiC        |      2 | exploitation          |            0.223 |               5 |             nan |                 10 |        4 |             20    |               nan |             nan | none           |              6.58962 |                 0.554779 |       0.659457    |             0.0614517 |                     nan |                         nan |                           nan |                        nan |                        nan |                     nan |        0.18509    |         -0.18509    | True                        | target_depth not configured; using observed median depth |
| milling        | SiC        |      3 | exploitation          |            4     |              40 |             nan |                  2 |        5 |             50    |               nan |             nan | none           |              6.18877 |                 0.554779 |       0.637465    |             0.0614517 |                     nan |                         nan |                           nan |                        nan |                        nan |                     nan |        0.19897    |         -0.19897    | True                        | target_depth not configured; using observed median depth |
| milling        | SiC        |      4 | exploitation          |            0.5   |              40 |             nan |                  2 |        1 |             50    |               nan |             nan | none           |              7.78519 |                 0.554779 |       0.689447    |             0.0614517 |                     nan |                         nan |                           nan |                        nan |                        nan |                     nan |        0.209933   |         -0.209933   | True                        | target_depth not configured; using observed median depth |
| milling        | SiC        |      5 | exploitation          |            0.223 |               5 |             nan |                 10 |        5 |             20    |               nan |             nan | none           |              7.37434 |                 0.554779 |       0.831395    |             0.0614517 |                     nan |                         nan |                           nan |                        nan |                        nan |                     nan |        0.225559   |         -0.225559   | True                        | target_depth not configured; using observed median depth |
| milling        | ZrO2       |      1 | exploitation          |            4     |             200 |             nan |                  8 |        2 |             11    |               nan |             nan | none           |             35.4476  |                 4.58163  |       0.237307    |             1.35989   |                     nan |                         nan |                           nan |                        nan |                        nan |                     nan |        0.0627552  |         -0.0627552  | True                        | target_depth not configured; using observed median depth |
| milling        | ZrO2       |      2 | exploitation          |            4     |             200 |             nan |                 10 |        4 |             11    |               nan |             nan | none           |             40.894   |                 4.81555  |      -0.275175    |             1.36244   |                     nan |                         nan |                           nan |                        nan |                        nan |                     nan |        0.0808981  |         -0.0808981  | True                        | target_depth not configured; using observed median depth |
| milling        | ZrO2       |      3 | exploitation          |            4     |             200 |             nan |                  8 |        2 |              9    |               nan |             nan | none           |             35.9521  |                 3.93232  |       0.354367    |             1.30095   |                     nan |                         nan |                           nan |                        nan |                        nan |                     nan |        0.0993478  |         -0.0993478  | True                        | target_depth not configured; using observed median depth |
| milling        | ZrO2       |      4 | exploitation          |            4     |             200 |             nan |                 10 |        5 |             11    |               nan |             nan | none           |             41.8873  |                 5.22878  |      -0.269879    |             1.40433   |                     nan |                         nan |                           nan |                        nan |                        nan |                     nan |        0.110149   |         -0.110149   | True                        | target_depth not configured; using observed median depth |
| milling        | ZrO2       |      5 | exploitation          |            4     |             100 |             nan |                 10 |        4 |             11    |               nan |             nan | none           |             36.6049  |                 4.1411   |       0.332452    |             1.19568   |                     nan |                         nan |                           nan |                        nan |                        nan |                     nan |        0.112222   |         -0.112222   | True                        | target_depth not configured; using observed median depth |

## 当前数据限制

- 当前数据未提供逐样本平均功率、单脉冲能量、光斑直径和离焦量；模型主要是统计代理模型，不具备完整物理因果解释。
- 金刚石数据存在深度和粗糙度缺失；缺失样本不会参与对应目标建模。
- 交叉验证评估受样本量和参数设计空间覆盖影响，外推到未观测工艺窗口的可信度有限。
- MLP 仅作为深度学习对照，不作为主结论来源。

## 后续实验建议

- 对 BO 推荐点做小批量验证，并记录同一参数下的重复实验，用于估计实验噪声。
- 补充 power_W、光斑直径、离焦量、加工气氛等变量后，再构造更接近物理意义的能量密度特征。
- 对最佳模型预测误差较大的材料，优先在误差集中的参数区间加密实验。
- 将高度图识别结果与工艺表通过样本编号或实验批次建立显式关联，避免人工拼接误差。
