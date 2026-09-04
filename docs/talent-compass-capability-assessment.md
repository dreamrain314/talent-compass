# Talent Compass 能力盘点与目标

> 生成日期：2026-07-27
> 任务：2.2.2b 双层三通道标签抽取重构（Step 1.10）
> 当前实验口径：3 员工 / 20 GT 标签，recall@GT 实测 35–55% 抖动

---

## 一、拥有的能力（代码验证可执行）

### A. 标签库（固定，121 项）

- 数据源：`data/standard_label_library_v1.json`
- 结构：`{version, created_at, updated_at, framework, update_note, labels}`
- labels 三层：
  - T1 专业能力：99 项（含注册表融合的工具/领域/知识，由 `load_label_corpus` 合并 `config.T0_REGISTRIES_PATH`）
  - T2 行为能力：13 项
  - T3 发展潜力：9 项
- 每项 schema：`{name, definition, keywords}`
- corpus text 构造：`"{name}: {definition}"`
- **不可变**——评判"命中"的地面真相池

### B. Embedding 召回（bge-small-zh-v1.5 / fastembed）

- 入口：`utils/label_matching.py:recall_top_k(concept, corpus, top_k=20)`
- 配置：`EMBEDDING_MODEL_NAME="BAAI/bge-small-zh-v1.5"`，`LABEL_RECALL_TOP_K=20`
- 性能：首调 ~1.5s（含模型加载），后续毫秒级
- 返回：`[(name, score), ...]`
- **实测弱点**：对抽象软技能召回尚可——
  - `逆境反弹能力` 的 top-10 里**包含** GT `成长型思维`、`学习敏捷性`、`领导力潜质`、`抗压韧性`
  - `非职权影响力` 的 top-10 里**包含** GT `影响力构建`、`领导力潜质`
  - **召回层没漏 GT 标签**

### C. Cross-encoder 重排（bge-reranker-v2-m3，本地）

- 入口：`utils/label_matching.py:rerank_cross_encoder(items, ctx, corpus)`
- 模型路径：`config.RERANKER_LOCAL_PATH="D:/workplace/bge-reranker-v2-m3"`
- 性能：单批 ~10s（首调含加载）
- 判定阈值（当前）：
  - `RERANKER_NEW_LABEL_THRESHOLD=0.15` — score<此 → is_new_label=True
  - `RERANKER_CONFIDENCE_THRESHOLD=0.5` — [0.15,0.5) → pending_review；≥0.5 → 命中
- 行为：对 `(concept, candidates)` 逐对打分，选 top1；按阈值分流命中/待复核/新标签
- **实测弱点（决定性）**：
  - `逆境反弹` 对 candidates（含 GT `成长型思维`）打分 **0.10** → 判新标签，**没选 GT**
  - `非职权影响力` 对 candidates（含 GT `领导力潜质`）打分 **0.03** → 判新标签，**没选 GT**
  - 即 GT 已在 candidates 里，但 cross-encoder 给的分低于新标签阈值被丢
  - 这是 BGE 对中文抽象软技能的固有低分，非召回问题

### D. LLM（DeepSeek-V4-Pro，Paratera 代理）

- 配置：`DEEPSEEK_BASE_URL=https://llmapi.paratera.com`，`DEEPSEEK_MODEL=DeepSeek-V4-Pro`
- 超时配置：
  - Agent① 抽取 `PROFILE_EXTRACT_LLM_TIMEOUT=90s`，`PROFILE_EXTRACT_MAX_TOKENS=8192`
  - Agent② verify/correct `LABEL_RERANK_TIMEOUT=180s`，`LABEL_RERANK_MAX_TOKENS=2048`
  - 通用 `LLM_API_TIMEOUT=30s`
- 两条 LLM 通道：
  - **Agent① 抽取**（`agents/profile_generation.py`）：输入 phase1 原始数据，输出 T1/T2/T3 concept + standard_label 提议
  - **Agent② verify/correct**（`utils/label_matching.py:rerank_label_llm`）：对 cross-encoder 判不定/新标签的项做最终裁决
- **实测弱点**：
  - 抽取非确定性——同一员工两次跑抽出的 concept 集合不同（JZ0004 一次抽"嵌入式开发/项目管理/学习敏捷性"，下次完全不抽）
  - Agent② 偶发 JSON 解析失败 → 确定性降级，不重试（按 `root-cause-llm-fallback-cascade` 设计）
  - 抽取会漏掉 GT concept（JZ0004 整个没抽"嵌入式开发"）
- 兜底配置：`RERANKER_FALLBACK_TO_LLM=True`，`LABEL_NEW_LABEL_MAX_PER_EMP=2`

### E. 实验轨道（`scripts/experiment_embedding_vs_llm.py`）

- Path A：LLM 提议 → embedding 自动纠正
- Path B：纯 embedding 召回 top-1/top-3
- Path C（当前主线）：embedding 召回 top-20 → cross-encoder 重排 →（失败项）LLM 兜底
- 指标 recall@GT = 命中 GT 的 unique 标签数 / GT 标签总数
- GT 文件：`data/experiment/ground_truth_5.json`（5 员工 × ~7 标签，当前实验用前 3 人 = 20 GT 标签）

### F. 已落地的修复（测试 461 绿）

1. concept 抽象化 prompt（`_build_system_prompt` 加 few-shot，要求 concept 是抽象能力名而非原文片段）
2. 禁用 exact 快路径锁定（所有项进全候选重排，cross-encoder 有机会纠正 LLM 选错的相近标签）
3. 降 BGE 新标签阈值（`RERANKER_NEW_LABEL_THRESHOLD` 0.3→0.15，0.15–0.3 区间收为 pending_review）

---

## 二、瓶颈定位（实测，非猜测）

| 层 | 是否漏 GT | 根因 |
|---|---|---|
| 召回（B） | **不漏** | GT 标签在 top-10 candidates 里 |
| 重排（C） | **漏** | BGE 对抽象软技能打分 0.03–0.10 < 0.15，判新标签丢弃 |
| 抽取（D Agent①） | **漏** | LLM 非确定性，有时整个不抽某 GT concept |
| 兜底（D Agent②） | 偶发失败 | JSON 解析失败降级；**且 Path C 未接通此路径** |

### 关键事实

1. **召回层是好的**——GT 总在 top-10 里，别动它
2. **重排层（BGE）对硬技能好、对软技能差**——`逆境反弹→成长型思维` 这种语义跳跃它做不了
3. **LLM 兜底路径代码存在但 Path C 没接**——判 new_label 的项当前直接返回 `concept` 当 matched_label，没送 Agent② 复核。实验输出"真实 LLM 触发项: 0"印证此路径未启用。这是一条**已实现但未启用**的能力
4. **抽取非确定性**——单次抽取漏 concept 是常态，需多次或锚点约束
5. corpus 121 项不大，全量 LLM 重排（对每项 concept 让 LLM 从 121 项里选）成本可控

---

## 三、目标

**recall@GT ≥ 70%**

当前实测 35–55% 抖动（3 员工 / 20 GT 标签口径），距目标差 15–35pp。

### 约束

- 不能改标签库（121 项固定）
- LLM 非确定性无法消除，只能靠架构吸收
- BGE 对中文抽象软技能低分是固有的，调阈值会误判其它项
- 成本敏感（CLAUDE.md B 节限流，已投入约 $16）

---

## 四、新框架可用的积木（每块代码已验证可调）

1. **召回保 top-k**（B 层不动）
2. **重排按 concept 类型分流**：硬技能走 BGE / 软技能走 LLM
3. **抽取加锚点 + 数量下限**（改 `_build_system_prompt`，传入 current_position/项目作为锚点，要求 ≥N 个 concept）
4. **new_label 项强制过 Agent②**（接通 Path C 的 LLM 兜底路径，代码已存在）
5. **多次抽取取并集**（cheap 但放大 LLM 成本）
6. **全量 LLM 重排**（121 项不大，对每项 concept 让 LLM 从全库选）

---

## 五、关键文件索引

| 文件 | 作用 |
|------|------|
| `config.py` L238-241 | Reranker 路径/阈值配置 |
| `utils/label_matching.py` L29 `recall_top_k` | Embedding 召回 |
| `utils/label_matching.py` L438 `rerank_cross_encoder` | BGE 重排（已禁 exact 锁） |
| `utils/label_matching.py` L203 `rerank_label_llm` | LLM 兜底重排（Agent②，Path C 未接通） |
| `utils/label_embedding.py` L434 `load_label_corpus` | 标签库加载（121 项） |
| `agents/profile_generation.py` L372 `_build_system_prompt` | Agent① 抽取 prompt（已加 concept 抽象化 few-shot） |
| `scripts/experiment_embedding_vs_llm.py` | Path A/B/C 对比实验 |
| `data/experiment/ground_truth_5.json` | GT 标签（5 员工，实验用前 3） |
| `data/standard_label_library_v1.json` | 标签库（T1:99/T2:13/T3:9） |
