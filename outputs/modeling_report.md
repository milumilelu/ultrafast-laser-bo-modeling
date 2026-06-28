# 工艺参数-质量指标建模与贝叶斯优化推荐报告

## 数据概况

- 统一后总样本数：548
- 材料数：5
- 原始数据按材料分别建模，未将所有材料直接混合为一个主模型。

| material   |   n_samples |   valid_rows |   valid_depth_samples |   valid_roughness_samples |   missing_field_ratio |   outlier_row_count |   missing_power_W_ratio |   missing_Sq_um_ratio |   missing_Sz_um_ratio |
|:-----------|------------:|-------------:|----------------------:|--------------------------:|----------------------:|--------------------:|------------------------:|----------------------:|----------------------:|
| AlSiC      |         120 |          120 |                   120 |                       120 |              0.1      |                  14 |                       1 |                     0 |                     0 |
| CFRP       |         128 |          128 |                   128 |                       128 |              0.1      |                  27 |                       1 |                     0 |                     0 |
| Diamond    |          60 |           52 |                    52 |                        52 |              0.326667 |                   8 |                       1 |                     1 |                     1 |
| SiC        |         120 |          120 |                   120 |                       120 |              0.1      |                  21 |                       1 |                     0 |                     0 |
| ZrO2       |         120 |          120 |                   120 |                       120 |              0.1      |                  16 |                       1 |                     0 |                     0 |

## 缺失值与单位说明

- 缺失字段保留为 NaN；未对关键工艺参数做均值填补。
- 标记为 fs 或数值尺度明显为飞秒的脉宽字段已转换为 ps。
- 标记为 mm 或数值尺度明显为毫米的填充间距字段已转换为 um。
- 若缺少 power_W、Sq_um、Sz_um，记录保留，派生能量代理特征保持 NaN。

## 特征工程

- 构造 log_pulse_width、log_frequency、log_hatch_spacing、log_passes、log_scan_speed。
- 构造 D_proxy = frequency_kHz * passes / (scan_speed_mm_s * hatch_spacing_um)。
- D_proxy 是单位面积累计脉冲作用密度的统计代理量，不是严格能量密度。
- power_W 可用时才构造 pulse_energy_proxy 与 energy_density_proxy；当前缺失时不强行估计。

## 模型性能对比

| material   | target   | model                |          MAE |         RMSE |         R2 |    CV_MAE |   CV_RMSE |       CV_R2 |   n_samples |   n_features |   cv_folds |
|:-----------|:---------|:---------------------|-------------:|-------------:|-----------:|----------:|----------:|------------:|------------:|-------------:|-----------:|
| AlSiC      | Sa_um    | GPR                  |  0.0150073   |  0.0355733   |  0.999785  |  0.891551 |  2.18636  |  0.189677   |         120 |           11 |          5 |
| AlSiC      | Sa_um    | RandomForest         |  0.57346     |  1.52174     |  0.607452  |  0.957043 |  2.19832  |  0.180792   |         120 |           11 |          5 |
| AlSiC      | Sa_um    | HistGradientBoosting |  0.77441     |  1.70739     |  0.50583   |  1.04813  |  2.22751  |  0.158893   |         120 |           11 |          5 |
| AlSiC      | Sa_um    | MLP                  |  1.12183     |  2.45969     | -0.0255912 |  1.00002  |  2.35119  |  0.0628909  |         120 |           11 |          5 |
| AlSiC      | Sa_um    | RSM                  |  0.738279    |  1.37513     |  0.679447  |  1.51682  |  2.87603  | -0.402165   |         120 |           11 |          5 |
| AlSiC      | depth_um | RSM                  |  2.69639     |  4.48955     |  0.925016  |  5.68709  |  9.65227  |  0.653407   |         120 |           11 |          5 |
| AlSiC      | depth_um | GPR                  |  0.105544    |  0.178544    |  0.999881  |  5.17516  |  9.78482  |  0.643823   |         120 |           11 |          5 |
| AlSiC      | depth_um | HistGradientBoosting |  4.0287      |  7.26619     |  0.803585  |  6.63105  | 11.0483   |  0.545899   |         120 |           11 |          5 |
| AlSiC      | depth_um | RandomForest         |  2.79529     |  5.32305     |  0.89459   |  6.322    | 11.9179   |  0.471606   |         120 |           11 |          5 |
| AlSiC      | depth_um | MLP                  |  9.02137     | 14.0021      |  0.270627  |  8.12817  | 14.614    |  0.205491   |         120 |           11 |          5 |
| CFRP       | Sa_um    | GPR                  |  0.180643    |  0.233942    |  0.861605  |  0.409111 |  0.521479 |  0.312332   |         128 |           11 |          5 |
| CFRP       | Sa_um    | RandomForest         |  0.209766    |  0.281131    |  0.800141  |  0.436663 |  0.579002 |  0.152255   |         128 |           11 |          5 |
| CFRP       | Sa_um    | HistGradientBoosting |  0.281722    |  0.367864    |  0.657801  |  0.455383 |  0.584518 |  0.136024   |         128 |           11 |          5 |
| CFRP       | Sa_um    | MLP                  |  0.226577    |  0.319442    |  0.741958  |  0.482413 |  0.610308 |  0.058102   |         128 |           11 |          5 |
| CFRP       | Sa_um    | RSM                  |  0.281654    |  0.365359    |  0.662445  |  0.524734 |  0.683552 | -0.181541   |         128 |           11 |          5 |
| CFRP       | depth_um | GPR                  |  1.61154     |  2.47974     |  0.983365  |  2.60005  |  4.09278  |  0.954685   |         128 |           11 |          5 |
| CFRP       | depth_um | RSM                  |  1.76531     |  2.53091     |  0.982672  |  3.24153  |  4.98756  |  0.932705   |         128 |           11 |          5 |
| CFRP       | depth_um | MLP                  |  3.10081     |  4.314       |  0.949654  |  3.98414  |  5.5608   |  0.916348   |         128 |           11 |          5 |
| CFRP       | depth_um | RandomForest         |  1.76277     |  3.12257     |  0.973623  |  3.73139  |  5.82329  |  0.908264   |         128 |           11 |          5 |
| CFRP       | depth_um | HistGradientBoosting |  2.1357      |  3.27201     |  0.971038  |  4.39138  |  6.4205   |  0.888483   |         128 |           11 |          5 |
| Diamond    | Sa_um    | MLP                  |  0.112828    |  0.143851    |  0.86384   |  0.231288 |  0.308868 |  0.372272   |          52 |           11 |          5 |
| Diamond    | Sa_um    | RandomForest         |  0.094075    |  0.164029    |  0.822962  |  0.199988 |  0.325088 |  0.304613   |          52 |           11 |          5 |
| Diamond    | Sa_um    | GPR                  |  0.068526    |  0.0981949   |  0.936554  |  0.201622 |  0.353666 |  0.176975   |          52 |           11 |          5 |
| Diamond    | Sa_um    | HistGradientBoosting |  0.214307    |  0.332058    |  0.274474  |  0.232456 |  0.382259 |  0.0385165  |          52 |           11 |          5 |
| Diamond    | Sa_um    | RSM                  |  0.0521915   |  0.0719282   |  0.965957  |  0.271502 |  0.492942 | -0.598883   |          52 |           11 |          5 |
| Diamond    | depth_um | RandomForest         |  3.2503      |  4.20327     |  0.975195  |  7.20264  |  9.41506  |  0.875545   |          52 |           11 |          5 |
| Diamond    | depth_um | GPR                  |  0.000749619 |  0.00101701  |  1         |  7.75938  | 11.7781   |  0.805232   |          52 |           11 |          5 |
| Diamond    | depth_um | MLP                  |  4.06067     |  5.34396     |  0.959905  | 13.9653   | 18.0196   |  0.544113   |          52 |           11 |          5 |
| Diamond    | depth_um | HistGradientBoosting |  9.13818     | 11.7107      |  0.807454  | 15.7721   | 19.2604   |  0.479165   |          52 |           11 |          5 |
| Diamond    | depth_um | RSM                  |  1.79355     |  2.58633     |  0.990609  | 10.6967   | 21.3714   |  0.358742   |          52 |           11 |          5 |
| SiC        | Sa_um    | GPR                  |  0.000636589 |  0.000827659 |  1         |  1.76255  |  2.29472  | -0.0114113  |         120 |           11 |          5 |
| SiC        | Sa_um    | MLP                  |  1.58254     |  2.18614     |  0.0820381 |  1.55473  |  2.43173  | -0.135802   |         120 |           11 |          5 |
| SiC        | Sa_um    | RandomForest         |  1.01649     |  1.36947     |  0.639774  |  1.93468  |  2.51054  | -0.210612   |         120 |           11 |          5 |
| SiC        | Sa_um    | HistGradientBoosting |  1.37017     |  1.7959      |  0.38051   |  1.90681  |  2.51545  | -0.215352   |         120 |           11 |          5 |
| SiC        | Sa_um    | RSM                  |  1.29167     |  1.70099     |  0.444259  |  2.25392  |  2.93717  | -0.657018   |         120 |           11 |          5 |
| SiC        | depth_um | GPR                  |  0.00588404  |  0.00747202  |  1         | 16.3578   | 20.8271   | -0.0222449  |         120 |           11 |          5 |
| SiC        | depth_um | MLP                  | 14.5235      | 19.8247      |  0.0737916 | 14.6294   | 22.3406   | -0.176216   |         120 |           11 |          5 |
| SiC        | depth_um | RandomForest         |  9.61149     | 12.5426      |  0.629255  | 18.2192   | 23.256    | -0.274586   |         120 |           11 |          5 |
| SiC        | depth_um | HistGradientBoosting | 12.1165      | 15.8812      |  0.405624  | 18.6758   | 24.2808   | -0.389393   |         120 |           11 |          5 |
| SiC        | depth_um | RSM                  | 11.9077      | 15.8414      |  0.408596  | 21.439    | 27.0039   | -0.718504   |         120 |           11 |          5 |
| ZrO2       | Sa_um    | RandomForest         |  0.413098    |  0.780033    |  0.710314  |  0.75384  |  1.35945  |  0.12011    |         120 |           11 |          5 |
| ZrO2       | Sa_um    | RSM                  |  0.52792     |  0.730601    |  0.745866  |  0.980657 |  1.41885  |  0.0415329  |         120 |           11 |          5 |
| ZrO2       | Sa_um    | HistGradientBoosting |  0.525161    |  0.908252    |  0.607252  |  0.835927 |  1.42409  |  0.0344399  |         120 |           11 |          5 |
| ZrO2       | Sa_um    | GPR                  |  8.2519e-05  |  0.000517228 |  1         |  0.808434 |  1.44076  |  0.0117136  |         120 |           11 |          5 |
| ZrO2       | Sa_um    | MLP                  |  0.695183    |  1.1865      |  0.329744  |  0.833749 |  1.45093  | -0.00229603 |         120 |           11 |          5 |
| ZrO2       | depth_um | GPR                  |  1.14558     |  1.553       |  0.994169  |  3.75422  |  5.8174   |  0.918177   |         120 |           11 |          5 |
| ZrO2       | depth_um | RSM                  |  2.21117     |  2.92713     |  0.979284  |  4.34477  |  6.55946  |  0.895971   |         120 |           11 |          5 |
| ZrO2       | depth_um | RandomForest         |  2.07121     |  3.39653     |  0.972107  |  4.4734   |  7.20836  |  0.874371   |         120 |           11 |          5 |
| ZrO2       | depth_um | HistGradientBoosting |  2.29621     |  3.22693     |  0.974824  |  5.1976   |  8.11202  |  0.840898   |         120 |           11 |          5 |
| ZrO2       | depth_um | MLP                  |  2.79481     |  3.6248      |  0.968232  |  7.16341  |  9.84783  |  0.765524   |         120 |           11 |          5 |

## 每种材料的最佳模型

| material | target | best_model | CV_RMSE | CV_R2 | n_samples |
|---|---|---:|---:|---:|---:|
| AlSiC | depth_um | RSM | 9.652 | 0.6534 | 120 |
| AlSiC | Sa_um | GPR | 2.186 | 0.1897 | 120 |
| CFRP | depth_um | GPR | 4.093 | 0.9547 | 128 |
| CFRP | Sa_um | GPR | 0.5215 | 0.3123 | 128 |
| Diamond | depth_um | RandomForest | 9.415 | 0.8755 | 52 |
| Diamond | Sa_um | RandomForest | 0.3251 | 0.3046 | 52 |
| SiC | depth_um | GPR | 20.83 | -0.02224 | 120 |
| SiC | Sa_um | GPR | 2.295 | -0.01141 | 120 |
| ZrO2 | depth_um | GPR | 5.817 | 0.9182 | 120 |
| ZrO2 | Sa_um | RandomForest | 1.359 | 0.1201 | 120 |

## 关键参数辨识结果

排序来自模型结果，不预设任何参数的重要性。RSM 证据为二阶响应面系数绝对值聚合；非线性证据为最佳模型的 permutation importance。

| material   | target   | model   | feature           |   importance_value | method               |   importance_rank |
|:-----------|:---------|:--------|:------------------|-------------------:|:---------------------|------------------:|
| AlSiC      | Sa_um    | RSM     | pulse_width_ps    |          6.57177   | RSM_abs_coefficient  |                 1 |
| AlSiC      | Sa_um    | RSM     | log_passes        |          5.84198   | RSM_abs_coefficient  |                 2 |
| AlSiC      | Sa_um    | RSM     | log_pulse_width   |          5.03512   | RSM_abs_coefficient  |                 3 |
| AlSiC      | Sa_um    | RSM     | log_scan_speed    |          4.82245   | RSM_abs_coefficient  |                 4 |
| AlSiC      | Sa_um    | RSM     | log_hatch_spacing |          4.58188   | RSM_abs_coefficient  |                 5 |
| AlSiC      | Sa_um    | RSM     | D_proxy           |          4.35656   | RSM_abs_coefficient  |                 6 |
| AlSiC      | Sa_um    | RSM     | scan_speed_mm_s   |          4.09971   | RSM_abs_coefficient  |                 7 |
| AlSiC      | Sa_um    | RSM     | hatch_spacing_um  |          3.85707   | RSM_abs_coefficient  |                 8 |
| AlSiC      | Sa_um    | RSM     | frequency_kHz     |          3.45679   | RSM_abs_coefficient  |                 9 |
| AlSiC      | Sa_um    | RSM     | passes            |          3.42414   | RSM_abs_coefficient  |                10 |
| AlSiC      | Sa_um    | RSM     | log_frequency     |          3.3691    | RSM_abs_coefficient  |                11 |
| AlSiC      | Sa_um    | GPR     | frequency_kHz     |          1.62982   | permutation_neg_RMSE |                 1 |
| AlSiC      | Sa_um    | GPR     | pulse_width_ps    |          1.52631   | permutation_neg_RMSE |                 2 |
| AlSiC      | Sa_um    | GPR     | D_proxy           |          1.31376   | permutation_neg_RMSE |                 3 |
| AlSiC      | Sa_um    | GPR     | log_frequency     |          1.2224    | permutation_neg_RMSE |                 4 |
| AlSiC      | Sa_um    | GPR     | log_hatch_spacing |          1.17622   | permutation_neg_RMSE |                 5 |
| AlSiC      | Sa_um    | GPR     | log_scan_speed    |          1.15817   | permutation_neg_RMSE |                 6 |
| AlSiC      | Sa_um    | GPR     | log_passes        |          1.15619   | permutation_neg_RMSE |                 7 |
| AlSiC      | Sa_um    | GPR     | passes            |          1.10904   | permutation_neg_RMSE |                 8 |
| AlSiC      | Sa_um    | GPR     | scan_speed_mm_s   |          1.1047    | permutation_neg_RMSE |                 9 |
| AlSiC      | Sa_um    | GPR     | hatch_spacing_um  |          1.09254   | permutation_neg_RMSE |                10 |
| AlSiC      | Sa_um    | GPR     | log_pulse_width   |          1.00488   | permutation_neg_RMSE |                11 |
| AlSiC      | depth_um | RSM     | frequency_kHz     |         44.3869    | RSM_abs_coefficient  |                 1 |
| AlSiC      | depth_um | RSM     | D_proxy           |         39.7514    | RSM_abs_coefficient  |                 2 |
| AlSiC      | depth_um | RSM     | pulse_width_ps    |         22.7039    | RSM_abs_coefficient  |                 3 |
| AlSiC      | depth_um | RSM     | hatch_spacing_um  |         19.2774    | RSM_abs_coefficient  |                 4 |
| AlSiC      | depth_um | RSM     | log_pulse_width   |         19.1712    | RSM_abs_coefficient  |                 5 |
| AlSiC      | depth_um | RSM     | log_passes        |         18.8796    | RSM_abs_coefficient  |                 6 |
| AlSiC      | depth_um | RSM     | log_frequency     |         18.8104    | RSM_abs_coefficient  |                 7 |
| AlSiC      | depth_um | RSM     | log_hatch_spacing |         17.9233    | RSM_abs_coefficient  |                 8 |
| AlSiC      | depth_um | RSM     | passes            |         16.5544    | RSM_abs_coefficient  |                 9 |
| AlSiC      | depth_um | RSM     | log_scan_speed    |         14.5947    | RSM_abs_coefficient  |                10 |
| AlSiC      | depth_um | RSM     | scan_speed_mm_s   |          8.49377   | RSM_abs_coefficient  |                11 |
| AlSiC      | depth_um | RSM     | D_proxy           |         12.6858    | permutation_neg_RMSE |                 1 |
| AlSiC      | depth_um | RSM     | frequency_kHz     |         12.3492    | permutation_neg_RMSE |                 2 |
| AlSiC      | depth_um | RSM     | pulse_width_ps    |         10.3222    | permutation_neg_RMSE |                 3 |
| AlSiC      | depth_um | RSM     | log_passes        |          8.795     | permutation_neg_RMSE |                 4 |
| AlSiC      | depth_um | RSM     | log_pulse_width   |          8.70665   | permutation_neg_RMSE |                 5 |
| AlSiC      | depth_um | RSM     | log_frequency     |          6.71041   | permutation_neg_RMSE |                 6 |
| AlSiC      | depth_um | RSM     | hatch_spacing_um  |          6.52148   | permutation_neg_RMSE |                 7 |
| AlSiC      | depth_um | RSM     | log_scan_speed    |          5.84059   | permutation_neg_RMSE |                 8 |
| AlSiC      | depth_um | RSM     | passes            |          5.64746   | permutation_neg_RMSE |                 9 |
| AlSiC      | depth_um | RSM     | log_hatch_spacing |          3.88319   | permutation_neg_RMSE |                10 |
| AlSiC      | depth_um | RSM     | scan_speed_mm_s   |          2.45264   | permutation_neg_RMSE |                11 |
| CFRP       | Sa_um    | RSM     | log_hatch_spacing |          1.45426   | RSM_abs_coefficient  |                 1 |
| CFRP       | Sa_um    | RSM     | scan_speed_mm_s   |          1.45059   | RSM_abs_coefficient  |                 2 |
| CFRP       | Sa_um    | RSM     | hatch_spacing_um  |          1.29348   | RSM_abs_coefficient  |                 3 |
| CFRP       | Sa_um    | RSM     | D_proxy           |          1.25719   | RSM_abs_coefficient  |                 4 |
| CFRP       | Sa_um    | RSM     | log_pulse_width   |          1.25241   | RSM_abs_coefficient  |                 5 |
| CFRP       | Sa_um    | RSM     | frequency_kHz     |          1.21352   | RSM_abs_coefficient  |                 6 |
| CFRP       | Sa_um    | RSM     | passes            |          1.19643   | RSM_abs_coefficient  |                 7 |
| CFRP       | Sa_um    | RSM     | log_passes        |          1.13972   | RSM_abs_coefficient  |                 8 |
| CFRP       | Sa_um    | RSM     | log_scan_speed    |          1.05819   | RSM_abs_coefficient  |                 9 |
| CFRP       | Sa_um    | RSM     | log_frequency     |          1.03752   | RSM_abs_coefficient  |                10 |
| CFRP       | Sa_um    | RSM     | pulse_width_ps    |          0.969441  | RSM_abs_coefficient  |                11 |
| CFRP       | Sa_um    | GPR     | frequency_kHz     |          0.216343  | permutation_neg_RMSE |                 1 |
| CFRP       | Sa_um    | GPR     | log_frequency     |          0.183194  | permutation_neg_RMSE |                 2 |
| CFRP       | Sa_um    | GPR     | hatch_spacing_um  |          0.141696  | permutation_neg_RMSE |                 3 |
| CFRP       | Sa_um    | GPR     | log_pulse_width   |          0.135156  | permutation_neg_RMSE |                 4 |
| CFRP       | Sa_um    | GPR     | log_hatch_spacing |          0.134932  | permutation_neg_RMSE |                 5 |
| CFRP       | Sa_um    | GPR     | log_scan_speed    |          0.134017  | permutation_neg_RMSE |                 6 |
| CFRP       | Sa_um    | GPR     | scan_speed_mm_s   |          0.132499  | permutation_neg_RMSE |                 7 |
| CFRP       | Sa_um    | GPR     | pulse_width_ps    |          0.13226   | permutation_neg_RMSE |                 8 |
| CFRP       | Sa_um    | GPR     | passes            |          0.11871   | permutation_neg_RMSE |                 9 |
| CFRP       | Sa_um    | GPR     | log_passes        |          0.105517  | permutation_neg_RMSE |                10 |
| CFRP       | Sa_um    | GPR     | D_proxy           |          0.0824579 | permutation_neg_RMSE |                11 |
| CFRP       | depth_um | RSM     | log_frequency     |         18.1701    | RSM_abs_coefficient  |                 1 |
| CFRP       | depth_um | RSM     | log_scan_speed    |         15.9627    | RSM_abs_coefficient  |                 2 |
| CFRP       | depth_um | RSM     | D_proxy           |         13.9419    | RSM_abs_coefficient  |                 3 |
| CFRP       | depth_um | RSM     | frequency_kHz     |         13.4708    | RSM_abs_coefficient  |                 4 |
| CFRP       | depth_um | RSM     | passes            |         13.3075    | RSM_abs_coefficient  |                 5 |
| CFRP       | depth_um | RSM     | pulse_width_ps    |         11.9993    | RSM_abs_coefficient  |                 6 |
| CFRP       | depth_um | RSM     | log_hatch_spacing |         11.2117    | RSM_abs_coefficient  |                 7 |
| CFRP       | depth_um | RSM     | log_passes        |         10.6113    | RSM_abs_coefficient  |                 8 |
| CFRP       | depth_um | RSM     | scan_speed_mm_s   |         10.4615    | RSM_abs_coefficient  |                 9 |
| CFRP       | depth_um | RSM     | log_pulse_width   |          9.43344   | RSM_abs_coefficient  |                10 |
| CFRP       | depth_um | RSM     | hatch_spacing_um  |          8.1802    | RSM_abs_coefficient  |                11 |
| CFRP       | depth_um | GPR     | log_scan_speed    |          9.76007   | permutation_neg_RMSE |                 1 |
| CFRP       | depth_um | GPR     | frequency_kHz     |          7.72966   | permutation_neg_RMSE |                 2 |
| CFRP       | depth_um | GPR     | log_frequency     |          5.31654   | permutation_neg_RMSE |                 3 |

## 贝叶斯优化推荐参数

BO 推荐用于规划下一轮实验点，不证明已经找到全局最优。候选点限制在已有实验参数水平或观测范围内。

| material   |   rank | recommendation_type   |   pulse_width_ps |   frequency_kHz |   hatch_spacing_um |   passes |   scan_speed_mm_s |   predicted_depth_um |   predicted_depth_std_um |   predicted_Sa_um |   predicted_Sa_std_um |   objective_value |   acquisition_score | roughness_model_available   | note                                                     |
|:-----------|-------:|:----------------------|-----------------:|----------------:|-------------------:|---------:|------------------:|---------------------:|-------------------------:|------------------:|----------------------:|------------------:|--------------------:|:----------------------------|:---------------------------------------------------------|
| AlSiC      |      1 | exploitation          |            0.5   |               5 |                  4 |        4 |            175    |             10.6993  |                 3.27798  |        1.14259    |             1.33514   |        0.166184   |         -0.166184   | True                        | target_depth not configured; using observed median depth |
| AlSiC      |      2 | exploitation          |            0.223 |              40 |                  4 |        5 |            200    |              9.59851 |                10.9839   |        1.15129    |             2.47346   |        0.192145   |         -0.192145   | True                        | target_depth not configured; using observed median depth |
| AlSiC      |      3 | exploitation          |            0.223 |               5 |                  4 |        4 |            175    |             11.1746  |                 4.38334  |        1.2196     |             1.60039   |        0.204838   |         -0.204838   | True                        | target_depth not configured; using observed median depth |
| AlSiC      |      4 | exploitation          |            0.223 |              20 |                  8 |        2 |            125    |             10.3206  |                 6.3042   |        1.73316    |             2.04569   |        0.222222   |         -0.222222   | True                        | target_depth not configured; using observed median depth |
| AlSiC      |      5 | exploitation          |            0.5   |               5 |                  4 |        4 |            125    |             11.2247  |                 3.79566  |        1.37688    |             1.52682   |        0.22787    |         -0.22787    | True                        | target_depth not configured; using observed median depth |
| CFRP       |      1 | exploitation          |            4     |               2 |                  2 |        3 |              1    |             16.4084  |                 4.05031  |        1.34759    |             0.550568  |        0.213834   |         -0.213834   | True                        | target_depth not configured; using observed median depth |
| CFRP       |      2 | exploitation          |            4     |               2 |                  6 |        4 |              1    |             16.2224  |                 4.55287  |        1.48269    |             0.574496  |        0.224084   |         -0.224084   | True                        | target_depth not configured; using observed median depth |
| CFRP       |      3 | exploitation          |            4     |               2 |                  6 |        3 |              1    |             16.2774  |                 4.65554  |        1.4781     |             0.586649  |        0.226256   |         -0.226256   | True                        | target_depth not configured; using observed median depth |
| CFRP       |      4 | exploitation          |            0.5   |              20 |                  2 |        1 |              5    |             16.1741  |                 5.90232  |        1.54378    |             0.624745  |        0.230575   |         -0.230575   | True                        | target_depth not configured; using observed median depth |
| CFRP       |      5 | exploitation          |            4     |              20 |                  6 |        4 |             20    |             16.0629  |                 3.5392   |        1.59618    |             0.479546  |        0.237355   |         -0.237355   | True                        | target_depth not configured; using observed median depth |
| Diamond    |      1 | exploitation          |            0.223 |               2 |                  4 |       10 |              0.2  |             61.7458  |                 7.11572  |       -0.013003   |             0.209015  |       -0.00245396 |          0.00245396 | True                        | target_depth not configured; using observed median depth |
| Diamond    |      2 | exploitation          |            0.5   |               2 |                  5 |        7 |              0.05 |             61.3259  |                 4.22773  |        0.00223055 |             0.188062  |        0.00814927 |         -0.00814927 | True                        | target_depth not configured; using observed median depth |
| Diamond    |      3 | exploitation          |            2     |              20 |                  1 |        4 |              1    |             61.9105  |                 6.96688  |        0.0428178  |             0.197642  |        0.0125738  |         -0.0125738  | True                        | target_depth not configured; using observed median depth |
| Diamond    |      4 | exploitation          |            2     |               2 |                  4 |        7 |              0.05 |             61.973   |                 4.43908  |        0.0593102  |             0.187997  |        0.0177082  |         -0.0177082  | True                        | target_depth not configured; using observed median depth |
| Diamond    |      5 | exploitation          |            2     |               2 |                  1 |        4 |              0.2  |             61.7269  |                 9.57813  |        0.0922948  |             0.215475  |        0.0241763  |         -0.0241763  | True                        | target_depth not configured; using observed median depth |
| SiC        |      1 | exploitation          |            0.5   |               2 |                  8 |        5 |             20    |              6.01483 |                 0.554779 |        0.501515   |             0.0614517 |        0.173391   |         -0.173391   | True                        | target_depth not configured; using observed median depth |
| SiC        |      2 | exploitation          |            0.223 |               5 |                 10 |        4 |             20    |              6.58962 |                 0.554779 |        0.659457   |             0.0614517 |        0.18509    |         -0.18509    | True                        | target_depth not configured; using observed median depth |
| SiC        |      3 | exploitation          |            4     |              40 |                  2 |        5 |             50    |              6.18877 |                 0.554779 |        0.637465   |             0.0614517 |        0.19897    |         -0.19897    | True                        | target_depth not configured; using observed median depth |
| SiC        |      4 | exploitation          |            0.5   |              40 |                  2 |        1 |             50    |              7.78519 |                 0.554779 |        0.689447   |             0.0614517 |        0.209933   |         -0.209933   | True                        | target_depth not configured; using observed median depth |
| SiC        |      5 | exploitation          |            0.223 |               5 |                 10 |        5 |             20    |              7.37434 |                 0.554779 |        0.831395   |             0.0614517 |        0.225559   |         -0.225559   | True                        | target_depth not configured; using observed median depth |
| ZrO2       |      1 | exploitation          |            4     |             200 |                  8 |        2 |             11    |             35.3801  |                 4.81215  |        0.218949   |             1.37395   |        0.0600626  |         -0.0600626  | True                        | target_depth not configured; using observed median depth |
| ZrO2       |      2 | exploitation          |            4     |             200 |                 10 |        4 |             11    |             40.3555  |                 5.08652  |       -0.281742   |             1.37503   |        0.0641172  |         -0.0641172  | True                        | target_depth not configured; using observed median depth |
| ZrO2       |      3 | exploitation          |            4     |             200 |                 10 |        5 |             11    |             41.1181  |                 5.5511   |       -0.267996   |             1.41865   |        0.0889937  |         -0.0889937  | True                        | target_depth not configured; using observed median depth |
| ZrO2       |      4 | exploitation          |            4     |             200 |                  8 |        2 |              9    |             35.8742  |                 4.05093  |        0.358858   |             1.30677   |        0.0982817  |         -0.0982817  | True                        | target_depth not configured; using observed median depth |
| ZrO2       |      5 | exploitation          |            0.5   |               2 |                  2 |        4 |              3    |             35.4525  |                 5.14232  |        0.382439   |             1.19121   |        0.0989004  |         -0.0989004  | True                        | target_depth not configured; using observed median depth |

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
