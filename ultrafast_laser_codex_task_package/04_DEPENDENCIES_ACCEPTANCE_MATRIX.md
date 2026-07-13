# 任务依赖、PR 划分与统一验收矩阵

## 1. 三个主任务

| 主任务 | 解决的问题 | 主要交付 |
|---|---|---|
| 任务一 | 平台耦合、Chat 膨胀、长任务、缺少演化控制 | Agent Runtime、Workflow、Jobs、Evolution |
| 任务二 | 两套 BO、数据混用、准入不严、模型不可复现 | 唯一 BO 内核、Readiness、版本、模型晋升 |
| 任务三 | 无法限制可调参数、缺少 CAM 契约、扫描文档缺口 | 动态搜索空间、CAM、PaddleOCR、视觉 Stub |

---

## 2. PR 划分

| PR | 内容 | 依赖 | 可并行 |
|---|---|---|---|
| 1A | 包边界、Chat Runtime、Workflow Event | 无 | 否 |
| 1B | Background Job、Worker、Job API | 1A | 否 |
| 1C | Evolution Foundation | 1A，建议 1B | 部分 |
| 2A | 唯一 BO、Dataset Slice、Eligibility、Readiness | 1A | 可与 1B/1C 部分并行 |
| 2B | 模型组件、评价、版本、Evolution 接入 | 1C + 2A | 否 |
| 3A | ParameterPolicy、SearchSpace、约束 BO | 2A，建议 2B | 否 |
| 3B | ProcessRecommendation、CAM JSON、厂商 Adapter | 3A | 否 |
| 3C | PaddleOCR、OCR Job、视觉 Stub | 1B | 可与 2A/2B 并行 |

---

## 3. 强制依赖门

### Gate A：任务一进入任务二

必须满足：

```text
Chat 与 Stream 共用 Workflow；
架构边界测试通过；
Tool Executor 可调用正式 BO interface；
兼容层无新业务。
```

### Gate B：任务二进入任务三

必须满足：

```text
只有一个正式 BO RecommendationService；
数据切片和 Eligibility 已启用；
Readiness 可返回阻塞原因；
推荐可追溯到模型和数据版本。
```

### Gate C：3A 进入 3B

必须满足：

```text
ParameterPolicy 可编译；
固定参数不会被优化；
设备边界不可放宽；
空空间可阻塞；
完整 Recipe 可产生。
```

### Gate D：真实厂商 Adapter

必须满足：

```text
厂商名称明确；
导入/接口方式明确；
字段、单位、枚举和必填项有真实依据；
至少一个真实样例可用于黄金测试。
```

资料不满足时不得声称完成真实厂商兼容。

---

## 4. 统一测试矩阵

| 能力 | 单元测试 | 集成测试 | 端到端 |
|---|---:|---:|---:|
| 包依赖 | 必须 | 不适用 | 不适用 |
| Chat/Workflow | 必须 | 必须 | TUI/MockLLM |
| Job Worker | 必须 | 必须 | OCR/评价任务 |
| Evolution | 必须 | 必须 | Router/BO 版本回滚 |
| Dataset Slice | 必须 | 必须 | Agent BO 推荐 |
| Eligibility | 必须 | 必须 | Feedback→Candidate |
| Readiness | 必须 | 必须 | 冷启动/混合/数据驱动 |
| Model Evaluation | 必须 | 必须 | BO Evolution |
| Search Space | 必须 | 必须 | 只优化部分参数 |
| CAM JSON | 必须 | 必须 | Export→Feedback |
| Vendor Adapter | 必须 | 必须 | 黄金样例 |
| PaddleOCR | 必须 | 必须 | 扫描 PDF Job |
| Vision Stub | 必须 | 必须 | 验证默认不可调用 |

---

## 5. 性能守门

不得只追求功能通过。至少记录：

```text
Router p50/p95；
Chat 首事件延迟；
Workflow 事件处理耗时；
BO 数据切片耗时；
BO 单次推荐耗时；
RAG 查询耗时；
Job 入队和领取耗时；
OCR 每页耗时；
并发 5 会话 p95。
```

若显著退化，必须说明原因和是否接受，不得删除性能测试。

---

## 6. 数据迁移与回滚

每个数据库变更必须提供：

```text
向前 migration；
默认值策略；
旧数据补全策略；
回滚或兼容读取方式；
迁移前后数据计数检查。
```

重要对象使用 append-only 或版本化，不覆盖历史：

```text
推荐；
模型版本；
数据集版本；
知识审核；
Evolution 激活；
CAM 导出；
加工反馈。
```

---

## 7. 统一 Definition of Done

每个 PR 完成必须同时满足：

```text
1. 代码实现完整；
2. Schema 和 migration 完整；
3. 单元、集成、回归测试通过；
4. Doctor 和离线 Demo 通过；
5. README/架构文档更新；
6. 兼容、迁移和回滚说明完整；
7. 未完成项显式记录；
8. 不存在未经说明的临时双实现；
9. 日志不泄露 API Key、秘密或隐藏推理；
10. PR 规模符合单一主题。
```

---

## 8. 全部任务最终验收场景

### 场景 A：只调整两个参数

输入：

```text
材料：单晶金刚石
工艺：表面微加工
设备：指定 profile
固定：频率、脉宽、passes、焦点
可调：功率、扫描速度
质量要求：Ra ≤ 阈值
```

预期：

```text
只优化功率和速度；
完整 Recipe 包含所有固定参数；
设备边界和耦合约束通过；
返回可行概率、不确定度和版本；
CAM JSON 可导出。
```

### 场景 B：约束冲突

输入：

```text
设备功率 0–10 W
审核先验 8–12 W
用户限制 ≤6 W
```

预期：

```text
infeasible_search_space；
列出三个来源；
不运行 BO；
不自动忽略先验或用户限制。
```

### 场景 C：无有效训练数据

预期：

```text
Readiness 降级；
不得返回伪造 GP 预测；
按治理顺序使用审核先验/RAG/LLM 候选；
LLM 候选只允许试切。
```

### 场景 D：反馈准入

预期：

```text
保存推荐、CAM 设置、实际参数和检测结果；
创建训练候选；
异常运行不进入训练；
批准样本形成新 dataset version；
候选 BO 模型经评价和批准后激活。
```

### 场景 E：OCR

预期：

```text
原生 PDF 不 OCR；
扫描 PDF 进入 Job；
保存页码、bbox、置信度和版本；
低置信度工艺数值待确认；
不直接进入 BO/CAM。
```

### 场景 F：视觉功能

预期：

```text
代码和 Schema 存在；
默认 disabled；
Chat、TUI、公开 API 无入口；
结果不能进入 RAG、BO、CAM。
```

---

## 9. 退出条件

以下任一情况存在时，不能宣布整体任务完成：

```text
仍有两套正式 BO 推荐逻辑；
不同材料可能默认混训；
反馈仍可直接 valid_flag=true；
固定参数仍可能被 BO 修改；
CAM Adapter 会修改推荐值；
真实厂商字段由 Codex 猜测；
OCR 结果可直接进入 BO；
视觉功能可从用户入口调用；
Evolution 候选可绕过评价直接 active；
关键推荐无法追溯到数据与模型版本。
```
