# 竞品调研：专业技能能力提取（T1 recall 优化）

> **日期:** 2026-09-09 · **触发:** 用户指令「查询 GitHub/论坛上竞品（尤其专业技能提取）的解决思路」
> **目标:** 为 T1 硬技能 recall 25-37.5% 的 4 个瓶颈寻找业界可借鉴方案（不强求思路一致，达目的即可）
> **方法:** 4 轴搜索（简历技能抽取生态 / 分类法本体链接 / 人岗匹配工业界 / LLM 抽取 recall 技术）→ 分层阅读（L1 简介筛相关性 → L2 深读 5 个最相关源）→ 按瓶颈映射 → 迁移排序

---

## 0. 研究方法与局限（诚实披露）

- **fan-out 模拟**: 本 session 无 Workflow/subagent 工具，用「并行搜索 + 串行深读」模拟分工；搜索后端并行 6 连发触发 429 限流（4/6 降级），动态调整为串行+间隔后恢复
- **深读通道**: WebFetch 域名验证全挂（arxiv/github/eightfold 均 Unable to verify），改用 web_reader MCP 全文抓取，5/5 成功
- **阅读策略结论**: L1 看简介/repo README 足够筛掉不相关项；L2 深读只对「直接对准我们瓶颈」的源做（论文方法节 + 工程博客架构节），源码级阅读本轮未做（迁移决策不需要，已以论文自报指标 + 架构描述为依据）

---

## 1. 竞品对比总表

| 竞品 | 类型 | 核心思路 | 关键指标 | 语言/规模 | 对我们的可迁移性 |
|------|------|---------|---------|----------|----------------|
| **Skill-LLM** (arxiv 2410.12052) | 论文 | 微调 LLaMA3-8B (LoRA) 做 span 抽取，skill_span+context 输出格式 | Total Span F1 **64.8%**（SOTA） | 英文/SkillSpan | 低（无中文标注数据）但格式设计可抄 |
| **GPT-3.5/4 纯 prompting** (Nguyen et al. 2024) | 论文基准 | 5-shot prompting，Extract-style 输出 | GPT-4 仅 **27.8%**，GPT-3.5 Extract-style 25.0%，NER-style 17.8% | 英文 | 高（我们正在这条路线上，解释了 recall 天花板） |
| **ADU 博客** (autonomy.work) | 工程实测 | 微调 GPT-3.5 ($7/2h) vs BERT/RoBERTa；**温度×recall 实验** | 微调 GPT-3.5 F1 0.572-0.605 > JobBERT 0.518；temp=0 近确定性且 recall 最高，temp→2 recall 崩、precision 升 | 英文/SkillSpan | 高（温度-多样性结论直接支撑 S3 并集策略） |
| **LinkedIn Skills Graph** | 工业系统 | trie 精确打标 + 双塔 mBERT 语义打标 + **技能图扩展(parent/child/sibling)** + 多任务打分(required/core/mention) | 41k 技能分类法；200 edits/s@100ms；蒸馏减 80% 体积 | 多语 | 高（**skill expansion 直接对准我们的间接映射瓶颈**） |
| **Eightfold** | 工业系统 | 深度语义 embedding + 结构化特征（技能重叠全量/近期双口径、RNN 下一职位预测、理想候选人锚点）+ 校准打分 | 数千万历史配对训练；0-5 星输出 | 英文 | 中（matching 层为主，双口径技能重叠可借鉴） |
| **SkillNer** (GitHub) | 开源库 | 规则式: spaCy PhraseMatcher + EMSI 技能库 trie 匹配，full_matches + ngram_scored | 无学术指标；确定性 100% | 仅英文 | 中（确定性词表快路径思想 = 我们 exact_name_match 的印证） |
| **NNOSE** (Zhang et al. 2024) | 论文 | kNN 检索增强：从多训练集检索近邻文本辅助抽取 | F1 64.2%（第二高） | 英文 | 中（检索增强思想可轻量版落地） |
| **ESCOXLM-R** (Zhang et al. 2023) | 论文 | ESCO 多语分类法预训练 (XLM-R) + 关系预测目标 | F1 62.6% | 多语(含中文分类法) | 中低（预训练成本高，但「分类法注入」思想可用 prompt 实现） |
| **Ma et al. 2023** | 论文 | **「LLM 不是好的 few-shot 抽取器，但是困难样本的好 reranker」** | — | 英文 | 高（**直接验证我们三阶段架构：embedding 召回 + LLM 精排**） |
| chalkline / skills-ML / TechWolf / MELO | 开源/基准 | Wave 1 搜到线索（架构同构：抽取→词表注册→embedding），本轮未深读 | — | — | 备查（本轮 5 深读已覆盖同类思路） |

---

## 2. 深读要点（5 源）

### 2.1 Skill-LLM 论文 — 「为什么我们 prompting 卡在 25-37%」

最有信息量的表格（SkillSpan 测试集 Total Span F1）：

| 方法 | 参数量 | F1 | 训练方式 |
|------|-------|-----|---------|
| BERT | 110M | 57.7% | 微调 |
| JobSpanBERT（域内预训练+微调） | 110M | 58.9% | 预训练+微调 |
| ESCOXLM-R（ESCO 分类法预训练） | 550M | 62.6% | 预训练+微调 |
| NNOSE（kNN 检索增强） | 123M | 64.2% | 预训练+微调+kNN |
| GLiNER 微调 | 166M | 58.4% | 微调 |
| **Skill-LLM（LLaMA3-8B LoRA 微调）** | 8B | **64.8%** | 微调 2 epoch |
| GPT-3.5 NER-style | 175B | **17.8%** | 5-shot |
| GPT-3.5 Extract-style | 175B | **25.0%** | 5-shot |
| GPT-4 | 1.7T | **27.8%** | ≤350 样本子集 |

**对我们的含义**:
1. **纯 prompting 的天花板就在 25-30% 区间**——我们实测单遍 25-37.5% 与文献完全吻合，这不是我们 prompt 写得差，是范式极限
2. 微调是唯一稳定破 60% 的路径，但需要标注数据（中文无现成 SkillSpan）
3. 论文的输出格式设计值得抄：每个 span 附 **context（左右各 1 token）**，用于回文校验防幻觉——比我们的 evidence 字段更强校验
4. Nguyen et al. 结论：**Extract-style（直接列技能清单）> NER-style（标 B/I/O）**，我们已是 Extract-style ✅

### 2.2 ADU 博客 — 温度与召回的关系（S3 的理论依据）

- 微调 GPT-3.5 在 SkillSpan 上 F1 0.572（test），超 JobBERT/RoBERTa，成本仅 **$7 + 2 小时**（OpenAI ft API，3 epochs）——「小成本微调」是 demo 后可选路径
- **温度实验（对我们最关键）**: temp=0 时 5 次推理结果几乎相同且 recall/F1 最佳；温度升高 → 每次抽取的技能集不同（多样性↑）→ 单次 recall 下降、precision 反而升；极高温度输出退化为乱码
- **推论**: 我们观察到的「同员工两次抽的 concept 集不同」正是温度>0 的多样性；**多遍并集（S3）在文献语义下 = 用单次 precision 换 union recall**，是合法策略而非 hack

### 2.3 LinkedIn Skills Graph — skill expansion（间接映射瓶颈的正解）

管线: 分段 → **trie 精确打标 + 双塔 mBERT 语义打标（并行互补）** → **技能图扩展**（查 Skills Graph 的同组/父子/兄弟技能）→ 多任务打分（required/core/mention 三种关系而非二元判定）→ 蒸馏部署。

**对我们的含义**:
1. **「ISO9001→质量工程」这类间接映射，LinkedIn 的解法不是让抽取器更聪明，而是抽取后用技能图扩展**——从抽到的显式技能出发，沿分类法关系（别名/父子/兄弟）补全隐式技能
2. trie（词表精确）+ 语义（embedding）**双通道并行**，互为补充而非串联过滤——印证我们 exact 快路径 + embedding 召回的组合
3. 软技能误杀的解法方向：不打单一分数阈值，而是**分关系类型打分**（required/core/mention），soft skill 走 mention 通道不参与硬阈值
4. 反馈回路（招聘者编辑建议技能 = 人工 GT 标注）——我们的 S7 GT 复核就是 mini 版

### 2.4 Eightfold — matching 层借鉴

- 技能重叠双口径：**全量技能 vs 近期技能**分别算 cosine——对应我们 ability_score 该区分「8 年前用过」和「正在用」
- RNN 预测下一职位/下一公司作为 trajectory 特征——T3 成长潜力的另一种建法（我们用代理指标，demo 期够用）
- 理想候选人锚点（招聘者上传标杆画像做相似度参照）——与我们备选池四象限的参照系思路一致

### 2.5 SkillNer — 确定性词表路线

- spaCy PhraseMatcher + EMSI 技能库，输出 full_matches（整词命中）+ ngram_scored（部分命中带分）
- 100% 确定性、零 LLM 成本——但仅英文、且依赖词表覆盖
- 印证：**确定性词表快路径（我们 exact_name_match）是业界标配底层**，不是落后设计

---

## 3. 四瓶颈 × 竞品方案映射

| 我们的瓶颈 | miss 占比 | 竞品解法 | 来源 | 迁移成本 |
|-----------|----------|---------|------|---------|
| **B1 单遍抽取漏标** | 87% | ① 温度>0 多遍并集 ② few-shot 样例 kNN 选取 ③ 微调（长期） | ADU / Nguyen / Skill-LLM | S3 已规划；②改 prompt 即可；③无数据 |
| **B2 间接映射丢失**（ISO9001→质量工程） | 主要 | **抽取后技能图扩展**（沿别名/父子/兄弟补全） | LinkedIn | 低：t0_registries 已有 aliases，embedding 近邻可当兄弟技能 |
| **B3 软技能 cross-encoder 低分误杀**（0.03-0.10 < 0.15） | 次要 | 分关系类型打分；硬/软技能分轨 | LinkedIn / SkillSpan | 低：分类别阈值或软技能直通 LLM rerank |
| **B4 LLM 兜底未接线** | — | LLM-as-reranker 对困难样本有效 | **Ma et al. 2023** | 零新依赖（S1 纯接线） |

**交叉验证**: Ma et al.「LLM 是好 reranker 不是好 extractor」+ Nguyen「prompting 天花板 27.8%」+ 我们实测「S4 直选 38.9% 且确定性无 union 增益」→ 三方一致：**LLM 应放在管线精排位，抽取位靠多样性并集补 recall**。我们现有架构方向正确，缺的是 B2 的扩展步和 B4 的接线。

---

## 4. 迁移建议（排序）

1. **S1 LLM 兜底接线**（原计划，文献加持）——Ma et al. 验证；零新依赖
2. **S8 技能扩展步（新增，源自 LinkedIn）**——抽取后对每个已匹配标签查 t0_registries aliases + embedding top-2 近邻（sim>阈值），补全间接映射；标记 `expanded: true` 供审计；每员工上限防泛滥。**直接对准 B2（S4 实验证明直选模式丢硬映射，扩展步在管线模式补回）**
3. **B3 修复：分类别阈值**——cross-encoder 阈值按 T1-hard / T2-soft 分轨（如 soft 0.05），或软技能项跳过 cross-encoder 直送 LLM rerank（Ma et al. 路线）
4. **S2 prompt 稳定化**（原计划）——吸收 Nguyen：few-shot 样例按输入语义相似度选取（kNN 选取优于随机）
5. **S3 多遍并集**（原计划，预算门控）——ADU 温度证据支撑；建议 temp 适中（0.7）而非高温（高温单次质量崩）
6. **不推荐现在做**: 微调（Skill-LLM/GLiNER 路线）——无中文标注数据；若未来做，可先用 LLM 生成合成标注（GREEN 数据集路线）再低成本微调（ADU $7 实测）

## 5. 验证计划

- 载体: `scripts/experiment_embedding_vs_llm.py`，3-5 员工，recall@GT 为主指标
- S8 验证: ISO9001→质量工程 案例必须翻正；负向断言：expanded 项不超上限、无新标签泛滥
- B3 验证: 软技能 GT 标签（如 团队管理/尽责性）命中率变化，硬技能不回归
- 每项独立 A/B，不同时叠加（归因清晰）

---

## Sources

- [Skill-LLM: Repurposing General-Purpose LLMs for Skill Extraction](https://arxiv.org/html/2410.12052v1)
- [Skills Extraction with Large Language Models (ADU blog)](https://adu.autonomy.work/posts/2023_11_14_skills-extraction-w-llms/)
- [LinkedIn: AI-Powered Skills Extraction and Mapping for the LinkedIn Skills Graph (ZenML LLMOps)](https://www.zenml.io/llmops-database/ai-powered-skills-extraction-and-mapping-for-the-linkedin-skills-graph)
- [Eightfold: AI-powered talent matching](https://eightfold.ai/engineering-blog/ai-powered-talent-matching-the-tech-behind-smarter-and-fairer-hiring/)
- [SkillNer (GitHub)](https://github.com/AnasAito/SkillNer)
- [Nguyen et al. 2024: Rethinking Skill Extraction in the Job Market Domain using LLMs](https://aclanthology.org/2024.nlp4hr-1.3.pdf)（经 Skill-LLM 转述）
