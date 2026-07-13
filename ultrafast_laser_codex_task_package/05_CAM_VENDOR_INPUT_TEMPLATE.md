# 首个厂商 CAM Adapter 输入资料模板

## 0. 使用说明

本文件必须在实现真实厂商 Adapter 前补全。

Codex 不得根据常识或搜索结果自行猜测字段。必须以用户提供、仓库已有或厂商正式文档为依据。

若本模板未补全，Codex 可以完成：

```text
GenericJsonCamAdapter
ConfigDrivenCamAdapter
Adapter 接口和测试基础设施
```

但必须将真实厂商 Adapter 标记为阻塞，不得声称兼容具体厂商。

---

## 1. 厂商与产品

```text
厂商名称：<待填写>
软件名称：<待填写>
软件版本：<待填写>
插件/模块名称：<如适用>
```

---

## 2. 集成方式

选择并填写：

```text
[ ] HTTP/REST API
[ ] 本地 JSON 文件导入
[ ] CSV 文件导入
[ ] XML 文件导入
[ ] 厂商专用 Recipe 文件
[ ] 命令行参数
[ ] SDK
[ ] 其他：<待填写>
```

接口/文件格式版本：

```text
<待填写>
```

---

## 3. 样例资料

必须至少提供一种：

```text
[ ] 正式接口文档
[ ] 字段表
[ ] 一份有效输入样例
[ ] 一份厂商导出的 Recipe 样例
[ ] SDK 示例代码
```

资料路径或链接：

```text
<待填写>
```

---

## 4. 参数映射

| 内部规范字段 | 厂商字段 | 内部单位 | 厂商单位 | 类型 | 必填 | 步进/精度 | 备注 |
|---|---|---|---|---|---|---|---|
| laser_power_W |  | W |  | number |  |  |  |
| frequency_kHz |  | kHz |  | number |  |  |  |
| pulse_width_fs |  | fs |  | number |  |  |  |
| scan_speed_mm_s |  | mm/s |  | number |  |  |  |
| passes |  | count |  | integer |  |  |  |
| hatch_spacing_um |  | µm |  | number |  |  |  |
| layer_step_um |  | µm |  | number |  |  |  |
| focus_offset_um |  | µm |  | number |  |  |  |
| fill_pattern |  | enum |  | enum |  |  |  |
| path_strategy |  | enum |  | enum |  |  |  |

增加其他字段：

```text
<待填写>
```

---

## 5. 枚举映射

### fill_pattern

| 内部值 | 厂商值 |
|---|---|
| contour |  |
| zigzag |  |

### path_strategy

| 内部值 | 厂商值 |
|---|---|
|  |  |

---

## 6. 缺失值规则

```text
厂商是否允许缺失字段：<待填写>
缺失字段是否使用厂商默认值：<待填写>
哪些字段绝对不能默认：<待填写>
```

要求：Codex 不得自行使用默认值补全关键参数。

---

## 7. 边界和验证

```text
厂商软件自身参数边界：<待填写>
导入失败返回方式：<待填写>
非法枚举返回方式：<待填写>
单位错误返回方式：<待填写>
```

---

## 8. 输出样例

请提供一份真实、可导入的最小样例：

```text
<待填写或附文件>
```

该样例将用于 golden test。

---

## 9. 非目标确认

确认本 Adapter：

```text
[ ] 只生成参数数据或 Recipe 文件
[ ] 不连接设备
[ ] 不启动加工
[ ] 不读取设备状态
[ ] 不实现 CAD/CAM 几何和刀路
```

---

## 10. 验收人和版本

```text
资料提供人：<待填写>
确认日期：<待填写>
映射版本：<待填写>
适用软件版本：<待填写>
```
