# 超快激光智能体 Codex 优化任务包

## 1. 任务包用途

本任务包用于指导 Codex 在当前仓库中完成下一阶段系统性优化。

本任务包已经综合当前讨论中确定的全部关键结论：

```text
1. 平台架构需要收敛；
2. Chat Orchestrator 需要拆分；
3. Evolution Foundation 本轮正式落地；
4. BO 唯一内核与动态搜索空间拆成两个不同任务；
5. BO 必须严格进行数据切片、准入、版本和回滚；
6. BO 必须支持设备限制、任务限制和只调整部分参数；
7. 系统只提供 CAM 工艺参数数据接口，不接设备、不替代 CAD/CAM；
8. CAM 接口使用通用 JSON 契约，并实现首个厂商 Adapter；
9. OCR 只接 PaddleOCR；
10. 图像语义解析只实现多模态大模型 API 骨架，默认关闭且不验收效果；
11. 当前不做认证与 RBAC；
12. 参数推荐必须遵循 BO、审核先验、RAG、LLM 候选的治理顺序。
```

本任务包覆盖三个主任务。每个主任务内部可以拆分成多个 PR，但不得再次合并成一个超大提交。

---

## 2. 文件说明

```text
00_GLOBAL_CONTEXT_AND_CODEX_RULES.md
  全局上下文、系统边界、治理原则、Codex 执行规则。

01_TASK_PLATFORM_RUNTIME_EVOLUTION.md
  任务一：平台架构收敛、Agent Runtime、后台任务与 Evolution Foundation。

02_TASK_BO_CORE_UNIFICATION.md
  任务二：BO 唯一内核、数据治理、Readiness、模型生命周期。

03_TASK_CONSTRAINED_BO_CAM_DOCUMENTS.md
  任务三：动态约束搜索空间、CAM 参数接口、首个厂商 Adapter、PaddleOCR、视觉骨架。

04_DEPENDENCIES_ACCEPTANCE_MATRIX.md
  三个任务之间的依赖、PR 划分、统一验收矩阵和退出条件。

05_CAM_VENDOR_INPUT_TEMPLATE.md
  首个厂商 CAM Adapter 所需资料模板。Codex 不得自行虚构厂商字段。
```

---

## 3. 推荐执行顺序

```text
任务一
  PR 1A：架构边界与 Chat Runtime
  PR 1B：后台任务与执行审计
  PR 1C：Evolution Foundation

任务二
  PR 2A：BO 唯一内核与数据治理
  PR 2B：BO 模型生命周期与 Evolution 接入

任务三
  PR 3A：动态搜索空间与约束 BO
  PR 3B：ProcessRecommendation、CAM JSON 与首个厂商 Adapter
  PR 3C：PaddleOCR 与默认关闭的视觉语义骨架
```

依赖关系：

```text
PR 1A → PR 1B → PR 1C
           ↓
         PR 3C 可在 PR 1B 后并行

PR 1C + PR 2A → PR 2B
PR 2A → PR 3A → PR 3B
```

---

## 4. 总体完成标志

全部任务完成后，系统应满足：

```text
1. Chat 只负责交互和编排，不直接实现 BO、RAG、OCR 或 CAM 业务；
2. 新旧 BO 不再并行运行，所有入口调用唯一 BO 内核；
3. 不同材料、工艺、设备和目标不会默认混合训练；
4. BO 可以只优化用户允许调整的参数；
5. 固定参数仍作为模型条件和完整 Recipe 的组成部分；
6. 设备硬边界、任务约束和审核先验共同编译搜索空间；
7. 推荐结果可以通过通用 JSON 契约交付给 CAM；
8. 首个厂商 CAM Adapter 有真实字段映射依据，且不包含设备控制；
9. PaddleOCR 通过后台任务处理扫描文档；
10. OCR 数值不能未经确认进入 BO、规则或 CAM；
11. 图像语义代码存在但默认关闭，无法从用户入口调用；
12. BO 模型、Router、Skill/Prompt 等可版本化、评价、晋升和回滚；
13. 所有关键推荐均可追溯到数据、模型、搜索空间和代码版本。
```

---

## 5. 优先级

```text
P0：任务一 PR 1A、任务二 PR 2A、任务三 PR 3A、PR 3B 的通用 JSON 契约
P1：任务一 PR 1B/1C、任务二 PR 2B、首个厂商 Adapter、PaddleOCR
P2：图像语义实验骨架，以及后续多目标 Pareto 优化
```

本任务包中的“明确不做”优先于历史任务说明。历史文档中若存在与本任务包冲突的内容，以本任务包为准。
