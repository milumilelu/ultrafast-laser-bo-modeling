# Data Schema Summary

## Unified Columns

| column | dtype | missing_ratio |
|---|---:|---:|
| record_id | str | 0.0000 |
| process_type | str | 0.0000 |
| material | str | 0.0000 |
| pulse_width_ps | float64 | 0.0000 |
| frequency_kHz | int64 | 0.0000 |
| laser_power_W | float64 | 1.0000 |
| scan_speed_mm_s | float64 | 0.0000 |
| passes | int64 | 0.0000 |
| focus_offset_um | float64 | 1.0000 |
| fill_pattern | str | 0.0000 |
| hatch_spacing_um | float64 | 0.0000 |
| layer_step_um | float64 | 1.0000 |
| path_overlap_um | float64 | 1.0000 |
| material_thickness_um | float64 | 1.0000 |
| cut_length_mm | float64 | 1.0000 |
| power_W | float64 | 1.0000 |
| depth_um | float64 | 0.0146 |
| Sa_um | float64 | 0.0146 |
| Sq_um | float64 | 0.1095 |
| Sz_um | float64 | 0.1095 |
| removal_rate_um3_s | float64 | 1.0000 |
| cut_through | float64 | 1.0000 |
| kerf_top_width_um | float64 | 1.0000 |
| kerf_bottom_width_um | float64 | 1.0000 |
| kerf_taper_deg | float64 | 1.0000 |
| cut_edge_Sa_um | float64 | 1.0000 |
| HAZ_width_um | float64 | 1.0000 |
| chipping_um | float64 | 1.0000 |
| objective_mode | object | 1.0000 |
| source_file | str | 0.0000 |
| valid_flag | bool | 0.0000 |
| note | str | 0.0000 |

## Source Column Mapping

### AlSiC / AlSiC.csv
- encoding: gbk
- raw shape: 120 rows x 12 columns
- column map:
  - `脉宽fs` -> `pulse_width_ps`
  - `频率kHz` -> `frequency_kHz`
  - `间距mm` -> `hatch_spacing_um`
  - `重复加工次数` -> `passes`
  - `速度mm/s` -> `scan_speed_mm_s`
  - `mean_depth_um` -> `depth_um`
  - `Sa_um` -> `Sa_um`
  - `Sq_um` -> `Sq_um`
  - `Sz_um` -> `Sz_um`
  - `min_depth_um` -> `depth_um`
  - `max_depth_um` -> `depth_um`
- ignored columns: `序号`

### CFRP / CFRP.csv
- encoding: gbk
- raw shape: 128 rows x 12 columns
- column map:
  - `脉宽fs` -> `pulse_width_ps`
  - `频率kHz` -> `frequency_kHz`
  - `间距mm` -> `hatch_spacing_um`
  - `重复加工次数` -> `passes`
  - `速度mm/s` -> `scan_speed_mm_s`
  - `mean_depth_um` -> `depth_um`
  - `Sa_um` -> `Sa_um`
  - `Sq_um` -> `Sq_um`
  - `Sz_um` -> `Sz_um`
  - `min_depth_um` -> `depth_um`
  - `max_depth_um` -> `depth_um`
- ignored columns: `序号`

### SiC / SiC.csv
- encoding: gbk
- raw shape: 120 rows x 12 columns
- column map:
  - `脉宽fs` -> `pulse_width_ps`
  - `频率kHz` -> `frequency_kHz`
  - `间距mm` -> `hatch_spacing_um`
  - `重复加工次数` -> `passes`
  - `速度mm/s` -> `scan_speed_mm_s`
  - `mean_depth_um` -> `depth_um`
  - `Sa_um` -> `Sa_um`
  - `Sq_um` -> `Sq_um`
  - `Sz_um` -> `Sz_um`
  - `min_depth_um` -> `depth_um`
  - `max_depth_um` -> `depth_um`
- ignored columns: `序号`

### ZrO2 / ZrO2.csv
- encoding: gbk
- raw shape: 120 rows x 12 columns
- column map:
  - `脉宽fs` -> `pulse_width_ps`
  - `频率kHz` -> `frequency_kHz`
  - `间距mm` -> `hatch_spacing_um`
  - `重复加工次数` -> `passes`
  - `速度mm/s` -> `scan_speed_mm_s`
  - `mean_depth_um` -> `depth_um`
  - `Sa_um` -> `Sa_um`
  - `Sq_um` -> `Sq_um`
  - `Sz_um` -> `Sz_um`
  - `min_depth_um` -> `depth_um`
  - `max_depth_um` -> `depth_um`
- ignored columns: `序号`

### Diamond / 金刚石实验结果.xlsx
- sheet: Sheet1
- raw shape: 60 rows x 11 columns
- column map:
  - `脉冲宽度` -> `pulse_width_ps`
  - `重复频率` -> `frequency_kHz`
  - `填充间距` -> `hatch_spacing_um`
  - `加工次数` -> `passes`
  - `扫描速度` -> `scan_speed_mm_s`
  - `深度/μm` -> `depth_um`
  - `粗糙度/μm` -> `Sa_um`
  - `备注` -> `note`
- ignored columns: `序号`, `Unnamed: 8`, `Unnamed: 9`

## Quality Report

| material   |   n_samples |   valid_rows |   valid_depth_samples |   valid_roughness_samples |   missing_field_ratio |   outlier_row_count |   missing_power_W_ratio |   missing_Sq_um_ratio |   missing_Sz_um_ratio |
|:-----------|------------:|-------------:|----------------------:|--------------------------:|----------------------:|--------------------:|------------------------:|----------------------:|----------------------:|
| AlSiC      |         120 |          120 |                   120 |                       120 |              0.608696 |                  14 |                       1 |                     0 |                     0 |
| CFRP       |         128 |          128 |                   128 |                       128 |              0.608696 |                  27 |                       1 |                     0 |                     0 |
| Diamond    |          60 |           52 |                    52 |                        52 |              0.707246 |                   8 |                       1 |                     1 |                     1 |
| SiC        |         120 |          120 |                   120 |                       120 |              0.608696 |                  21 |                       1 |                     0 |                     0 |
| ZrO2       |         120 |          120 |                   120 |                       120 |              0.608696 |                  16 |                       1 |                     0 |                     0 |

Pulse width columns labelled as fs or with femtosecond-scale values are converted to ps. Spacing columns labelled as mm or with sub-0.1 values are converted to um.