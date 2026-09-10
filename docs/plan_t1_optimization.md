# T1 硬技能 recall 优化 — 多方案研究与推荐

> 状态：[AWAITING_USER_REVIEW]（用户拍板后进入实施）
> 日期：2026-09-04
> 任务来源：task-plan 2.2.8；前置数据：`docs/talent-compass-capability-assessment.md`、`tmp/t1_attribution_report.md`（本次归因回放）
> 目标：T1 recall@GT 从实测 25-37.5% 提升至 ≥60%（3-run 均值），为 argmax T2/T3 落地（模拟总体 78.4%）扫清最后短板

---

## 〇、先决证据：miss 归因回放（2026-09-04，零 API 成本）

回放 07-27 18:00 后 6 个有效 live run（3 员工 = JZ0001/0003/0004，8 个 T1 GT 标签 × 6 run = 48 次机会）：

| 层 | miss 次数 | 占比 | 证据 |
|----|----------|------|------|
| **抽取层漏（LLM 单次没抽出相关 concept）** | **27/31** | **87%** | 智能制造(JZ0001) 5 run 未抽、质量工程 5 run 未抽、嵌入式开发 5 run 未抽、数据分析(JZ0003) 3 run、Java开发 1 run、项目管理 1 run |
| 匹配层错（抽出了但没配对） | 4/31 | 13% | ① 数据分析(JZ0004)：concept 是长句「工业大数据分析平台中Airflow等技术应用」→ cross-encoder 0.014 < 0.15 判新标签丢弃（LLM 兜底未接线）；② 项目管理(JZ0004)×3：实为「项目管理知识体系」vs GT「项目管理」命名口径 |
| **合计命中** | 17/48 | 35.4% | 与 argmax 文档记录的 25-37.5% 吻合 |

**决定性事实：跨 6 run 的 concept 并集可命中 7/8 GT（87.5%）**——流水线能力不是瓶颈，**单次抽取的非确定性才是**。同一员工 6 run 的 concept 并集 36-50 个 vs 单 run ~15 个。

> ⚠️ 口径警告：8 个 T1 GT 标签，±1 命中 = ±12.5pp。任何 A/B 对比必须跑 ≥3 run 取均值，且建议扩到 5 员工（T1 GT 8→16 个，±1 = ±6.25pp）再下结论。
> ⚠️ 归因方法局限：「未抽出」按词面 3 字前缀判相关，个别换词抽取的 run 可能被误计为未抽出——方向性结论（抽取层为主）不受影响，精确占比 ±10pp 内浮动。

---

## 一、候选方案

### S1 · 接通 cross-encoder 判新标签项的 LLM 兜底复核【匹配层 · 积木④】

- **核心思路**：`rerank_cross_encoder` 判 `SOURCE_CROSS_NEW_LABEL` / `SOURCE_CROSS_PENDING` 的项不再直接丢弃/放行，批量送 `rerank_label_llm` 终裁（代码已存在，能力盘点证实"Path C 真实 LLM 触发项=0"）。
- **业界对应**：BLINK/entity-linking 两阶段架构的兜底裁决层；我们自己的 D6 降级设计已有先例（encoder 不可用时已调 rerank_label_llm）。
- **落地改动**：`utils/label_matching.py:570-591`（new_label/pending 两个分支）→ 收集该类项、循环外一次 `rerank_label_llm(adjudicate_items, ...)`、新 mapping_source `cross_new_llm_confirmed/rejected`；config 无新常量（LABEL_RERANK_* 复用）；测试 mock cross_encoder_fn 返回低分 + mock call_llm_json 验证接线（V8 需含持续失败用例）。
- **优点**：改动最小（~40 行+测试）；直接修「数据分析」类 miss；零额外成本（只对被判新标签的少数项触发）。
- **缺点/风险**：只覆盖 13% 的 miss 中的新标签子集；LLM 终裁质量依赖 candidates 质量（本例 candidates 含 GT「数据分析」，能救回）。

### S2 · 抽取 prompt 稳定化：锚点 + 数量下限 + 覆盖自查【抽取层】

- **核心思路**：`_build_system_prompt` 加约束：① T1 至少 N 个（数量下限，如 ≥5）；② 必须逐项检查员工 raw 的岗位/项目/证书字段再决定（证据锚定）；③ 输出前自查清单（岗位关键词覆盖）。温度已 0.0，抖动来自长上下文采样与 prompt 引导不足。
- **业界对应**：ESCO/技能抽取管线的 schema-constrained extraction；LLM 结构化抽取的 checklist prompting。
- **落地改动**：`agents/profile_generation.py` `_build_system_prompt`（三通道 T1 块加约束）+ `_process_employee` 对 t1 数量 < 下限时的处理（记 metadata，不二次调用——避免 D6 雪崩）；config 加 `T1_EXTRACT_MIN_COUNT`。
- **优点**：单次调用成本不变；对「整段字段没看」（JZ0004 嵌入式 5 run 未抽）类漏抽直接起效。
- **缺点/风险**：prompt 改动会同时影响 T2/T3 通道输出（同一次调用的三通道分块），需全量回归；数量下限可能诱导凑数低质 concept（需配 confidence 下限过滤）。

### S3 · 多次抽取取并集【抽取层 · self-consistency 的 union 变体】

- **核心思路**：对同一员工跑 k 次 `_llm_extract`（temperature>0 或同温重采），concept 级并集去重后统一走匹配层。多数投票法（majority vote）用于提升精确率，**并集法（union）用于提升召回**——归因显示 87% miss 来自单次漏抽，union 是对症下药。
- **业界对应**：[Self-consistency 采样](https://arxiv.org/html/2603.08999v2)（多数投票）；抽取任务中的 sample-union 聚合是其在 recall 导向下的变体。
- **落地改动**：`agents/profile_generation.py` `_process_employee` 外层循环 k 次（复用现有 ThreadPoolExecutor 结构，k 次 LLM 调用本就并发受限 ≤3）；concept 去重（精确名+embedding 近似去重二选一，首版精确名即可）；config 加 `EXTRACT_PASSES=3`（offline=1 强制单次）。
- **优点**：**证据最强的方案**——6-run 并集 87.5% 是实测上限锚点；k=3 期望值估算（按各标签单次命中率 p，漏抽概率 (1-p)³）：智能制造JZ0001 ~42%、嵌入式 ~42%、项目管理 ~70%、总体期望 ~60%（单次 35.4% → k=3 约 +25pp）；与 S2 正交叠加。
- **缺点/风险**：LLM 成本 ×3（每员工 ~7k tokens ×3；50 员工 demo 一次全量约 1M tokens，需用户确认预算）；并集会放大假阳性 concept（需靠匹配层新标签闸门 + confidence 过滤兜住）；F3 线程纪律（不可杀线程重试）要遵守。

### S4 · LLM 全库直选 T1（绕过 embedding 两阶段）【匹配层替代 · ESCO LLM 零样本路线】

- **核心思路**：T1 的 40 个 skill 标签全量进 prompt（name+definition+keywords 约 3.4k tokens，已在预算内），第二遍专问「对照该员工证据，T1 标签库里哪些成立？」直接输出标签集，embedding/cross-encoder 只做旁路校验。
- **业界对应**：[ESCO 生态的 LLM 零样本匹配](https://www.researchgate.net/publication/408203944_Using_language_models_to_extract_and_map_emerging_skills_to_the_ESCO_taxonomy)、[LLM4Jobs 无监督职业编码](https://www.sciencedirect.com/science/article/pii/S0950705125003491)；Path A 历史实验（信 LLM 提议 31.4% > 旧纠正链）已给出部分正面信号。
- **落地改动**：新增第二遍调用（`_t1_direct_select`），与三阶段结果融合（并集或冲突取置信高者）；约 +80 行。
- **优点**：绕开 bge/cross-encoder 的中文语义鸿沟；天然是「覆盖检查」变体（S2 的强化版）。
- **缺点/风险**：每员工 +1 次调用；丢掉 rerank rationale 证据链（Agent④ 证据链依赖 mapping 可解释性，需保留三阶段路径作解释源）；40 标签全列直选的准确率未验证（历史 Path A 是自由提议不是受控直选，不能直接类推）。

### S5 · SetFit 少样本微调嵌入模型【训练侧 · 后备】

- **核心思路**：用 GT 35 对 + 历史映射构造 (concept, label) 句对，[SetFit 对比学习微调](https://github.com/huggingface/setfit) bge-small-zh（或换可训练底座），提升 argmax/召回质量——T1 argmax 模拟仅 9.1%，微调后可能质变。
- **业界对应**：[Ghent 大学的 ESCO bi-encoder LLM 合成数据训练](https://backoffice.biblio.ugent.be/download/01HDNKFAFWHB08J12A55DCN7GD/01HDNKK5FTNARV91HANPRB07XG)、[对比 bi-encoder 多标签技能抽取](https://arxiv.org/html/2601.09119v1)。
- **落地改动**：大——fastembed(ONNX) 不支持训练，需引入 sentence-transformers+torch 训练环境；训练数据只有 ~35-88 对且历史映射质量存疑；产出新模型文件 + EMBEDDING_MODEL_NAME 切换。
- **优点**：一次性投入，推理零增量成本；同时强化召回与未来 argmax。
- **缺点/风险**：**归因显示匹配层不是主瓶颈（召回层不漏 GT、错配仅 13%）→ 本方案打击面错位**；训练数据量在 SetFit 可行域边缘（每类 ~1-3 例）；环境与维护成本高。**不推荐首选。**

### S6 · BM25+dense 混合召回【召回层 · 不做】

- **核心思路**：字面 BM25 与向量召回融合（RRF），硬技能词（Java/FPGA）字面通道更稳。
- **判定**：能力盘点实测「召回层不漏 GT（GT 总在 top-10）」+ 本回放无反例 → 召回层不是瓶颈，改造收益趋近 0。仅在 S7 aliases 扩展后如需 argmax 复用时可顺路评估。

### S7 · 标签库 aliases 扩展 + GT 口径定稿【数据侧 · 必做前置】

- **核心思路**：① GT 复核（本就 [AWAITING_USER_REVIEW]）：「项目管理 vs 项目管理知识体系」等近义命名二选一定稿，直接消除 3/31 miss；② T1 标签库补 aliases 进 corpus text（ESCO preferred/alternative labels 惯例；T0 registry 已有 aliases 先例，`_load_registry_corpus` 同模式），不改 name 集合（GT 命中池不动），提升召回与未来 argmax。
- **落地改动**：GT 文件 `_meta.status` 改 [VERIFIED]（用户复核 7 新增 T1 + 命名口径）；`data/standard_label_library_v1.json` T1 项加 `aliases` 字段 + `utils/label_embedding.py` text 构造拼接（~15 行）。
- **优点**：零/低代码；修复口径类 miss；为 argmax 落地铺路（T2/T3 重排同样受益于 aliases 模式）。
- **缺点/风险**：aliases 编写是人工活（40 标签 × 3-5 别名）；GT 改口径后历史实验数字不可直接对比（需在 tracking 注明分界）。

---

## 二、综合对比

| 方案 | 打击层 | 归因覆盖 | 成本 | 改动量 | 确定性 | 独立性 |
|------|--------|---------|------|--------|--------|--------|
| S1 LLM 兜底接线 | 匹配 | 13% 中的新标签子集 | 低（按项触发） | 小 | 高（积木已存在） | ✅ 独立 |
| S2 prompt 稳定化 | 抽取 | 87% 的引导性部分 | 零增量 | 小 | 中 | 与 S3 叠加 |
| **S3 k=3 抽取并集** | **抽取** | **87% 主体** | **LLM ×3** | **中** | **高（实测并集 87.5% 锚点）** | ✅ 独立 |
| S4 LLM 全库直选 | 抽取+匹配 | 87%+13% | 每员工 +1 调用 | 中 | 中（未验证） | 与 S2/S3 重叠 |
| S5 SetFit 微调 | 匹配/召回 | 打击面错位 | 高（环境+训练） | 大 | 低 | 依赖新环境 |
| S6 混合召回 | 召回 | ≈0（召回不漏） | 中 | 中 | — | 不做 |
| S7 GT 定稿+aliases | 口径/数据 | 13% 中的口径部分 | 人工 | 零/低 | 高 | ✅ 前置必做 |

## 三、推荐：三段推进（S7 → S1+S2 → S3，后备 S4/S5）

**为什么不是"只上 S3"**：S3 是主攻但单用有两个问题——成本 ×3 换来的并集仍受 prompt 引导上限约束（质量工程 5/6 漏抽若源于 prompt 未引导看培训字段，k 次都漏）；且并集放大的假阳性若无 S1 终裁，匹配层丢弃率上升。

**为什么不是 S4/S5 先行**：S4 与 S2+S3 功能重叠但丢证据链；S5 打击面错位（匹配层仅 13% miss 且召回不漏）且环境成本最高。二者留作 S2+S3 后仍 <60% 时的后备。

**Step 0（人工，零代码）**：用户复核 GT——7 个新增 T1 标签 + 「项目管理 vs 项目管理知识体系」口径二选一 + TARGET_EMPLOYEES 扩 5 人（JZ0033/JZ0050 入池，T1 GT 8→16 个提升分辨力）。
**Step 1（小改动，1 session）**：S1 兜底接线 + S2 prompt 稳定化（同 session：改 `_build_system_prompt` 与 `rerank_cross_encoder`，测试全量回归 + V8 持续失败用例）。验证：3-run 真实实验，期望 T1 40-50%。
**Step 2（主攻，1 session）**：S3 `EXTRACT_PASSES=3` 并集抽取 + concept 去重。验证：3-run × 5 员工，判定门槛 T1 ≥60%（3-run 均值）。预算：实验阶段（5 员工 × 3 run × 3 pass）约 30 万 tokens，50 员工 demo 全量一次约 1M tokens 增量，需用户确认。
**后备**：Step 2 后仍 <60% → S4 直选变体（把第三 pass 换成全库直选 prompt 做 A/B）；仍不行 → S5 SetFit（需先攒 ≥5 对/标签的训练数据）。

**预期账**：S7（口径 3 例）+ S1（新标签 1 例）+ S2+S3（抽取 27 例中救回大部分）：单 run T1 35.4% → 60-70%；叠加 argmax T2/T3 落地（模拟 85.2%/93.5%）后总体 recall@GT 预期从 50% → **75-80%**，越过 70% 目标线。

---

## 附：本轮证据文件

- 归因脚本与报告：`tmp/t1_miss_attribution.py` / `tmp/t1_attribution_report.md`（6 run 回放，含逐标签命中表）
- 外部参考：SkiLLMo（ACM 3672608.3707960）、ESCO 官方 ML 映射、Self-consistency（arXiv 2603.08999）、SetFit（arXiv 2209.11055）、Ghent ESCO bi-encoder
