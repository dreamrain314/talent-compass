# 实施计划：T1 硬技能 recall@GT 优化落地（S1 → S8a → S8b → B3 → S2 → S3）

> 状态：[APPROVED]（2026-09-10 用户拍板：①C 修复已回写本文档 ②S8a 双向边设计确认；Phase 1 于新窗口开工）
> 日期：2026-09-09（2026-09-10 修订：回写角色C 检视修复 HIGH-1 / MED-1..4，检视报告见 `docs/review_t1_workflow_c.md`）
> 撰写：角色A 计划员（工作流 fan-out；恢复续跑后交付）
> 任务来源：`docs/plan_t1_optimization.md`（S1-S7 定义，编号沿用）+ `docs/competitive_research_skill_extraction.md`（S8 拆分为 S8a/S8b、B3 分轨）+ `tmp/t1_attribution_report.md`（miss 归因）
> 目标：T1 recall@GT 从 25-37.5% 提升至 ≥60%（3-run 均值）；ISO9001→质量工程 间接映射必须翻正（S8 验收锚点）

---

## 一、Overview

miss 归因显示 87% 损耗在抽取层（B1 单遍漏抽）、13% 在匹配层（B2 间接映射丢失 + B3 软技能误杀），且 B4（LLM 兜底未接线）使匹配层低分项被直接弃单。本计划按已定迁移排序落地六个改动：S1 把 `rerank_label_llm` 接线为 cross-encoder 低分项的终裁层（纯接线，积木已存在）；S8a/S8b 引入 LinkedIn 式技能扩展（别名富化 + 抽取后近邻扩展）解 B2；B3 对 soft 类分轨新标签阈值；S2 稳定抽取 prompt（数量下限 + 覆盖自查 + few-shot kNN）；S3 多遍并集（预算门控 + F8 前置验证）。每步带独立 A/B 开关，经 `scripts/experiment_embedding_vs_llm.py` 单步增量归因，不同时叠加。

## 二、需求与约束

- R1 编号沿用 `plan_t1_optimization.md` 的 S1/S2/S3；S8a/S8b 为竞品调研 S8 的拆分；B3 用瓶颈编号命名。不发明新编号。
- R2 每步改动落到 文件:函数 级锚点（本文所有函数名/行为均来自实际读到的代码）。
- R3 每步正例 + ≥1 条负向断言；S8b 附副作用矩阵（写入点 × 快速退出路径），确认零额外落盘。
- R4 F8：S3 依赖 GLM temperature 与 thinking 模式兼容性，前置验证步骤是 S3 的硬性 gate。
- R5 每步独立 A/B，载体 `scripts/experiment_embedding_vs_llm.py`，≥3 run 取均值（口径警告：8 个 T1 GT，±1 命中 = ±12.5pp）。
- R6 硬纪律：写入核心逻辑后同 turn 在 `progress.md` 追加 `[AWAITING_VERIFY]`；清闸门 = pytest 全绿 + 对抗审查。编辑共享文件前创建 `.agent-lock.json`（共存协议）。

## 三、架构改动总览

| 文件 | 改动 |
|------|------|
| `utils/label_matching.py` | S1：`rerank_cross_encoder` 加 LLM 终裁块 + 2 个新 source 枚举；B3：分轨阈值；`SOURCE_EXPANDED` 枚举（D2 单一来源，供 S8b） |
| `agents/profile_generation.py` | S8b：新方法 `_expand_indirect_labels`；S2：`_build_system_prompt` 加约束 + 签名加 `employee` 形参 + 新方法 `_select_few_shot_examples`；S3：`_llm_extract` 加 `temperature` 形参 + 新方法 `_multi_pass_extract` / `_union_extract_contents`；`execute`/`_process_employee`/`_inject_mapping_fields` 的 stats 三处对称扩展；超时预算联动公式 |
| `config.py` | 新常量 8 个（见第四节） |
| `data/t0_registries.json` | S8a：质量管理类条目 aliases 富化（纯数据，零代码） |
| `scripts/experiment_embedding_vs_llm.py` | Path C 统计扩展（新 source 计数）+ S8b 扩展调用 + S3 换用 `_multi_pass_extract` |
| `tests/test_label_matching.py` / `tests/test_profile_generation.py` | 每步新增测试类（见第八节） |
| `docs/plan-profile-agent-schema.md` | S8b 落地后同步 expanded 项字段（tracking 纪律，commit 前完成） |

## 四、新增 config 常量（D1/D2 单一来源）

统一加在 `config.py` 的 `RERANKER_*` / `LABEL_*` 常量区之后（L241 之后新块），每个常量带消费者注释：

```python
# ── T1 recall 优化（plan: S1/S8b/B3/S2/S3，2026-09）──
def _env_flag(name, default="0"):  # [MED-3 修复 2026-09-10] 默认关（opt-in）：默认开会破坏 A/B baseline 纪律与测试隔离
    return os.getenv(name, default).strip().lower() in _TRUTHY  # _TRUTHY=("1","true","yes","on") 提炼模块级共享常量，与 is_offline_mode 复用（LOW-2，实施时顺手消重）

# S1：cross-encoder 低分项（SOURCE_CROSS_NEW_LABEL / SOURCE_CROSS_PENDING）送 LLM 终裁
# 消费者：utils/label_matching.rerank_cross_encoder（A/B 开关：TC_LLM_ADJUDICATION）
RERANKER_LLM_ADJUDICATION = _env_flag("TC_LLM_ADJUDICATION")
# B3：soft 类（behavior/potential）新标签阈值分轨；hard 轨沿用 RERANKER_NEW_LABEL_THRESHOLD=0.15
# 消费者：utils/label_matching.rerank_cross_encoder（A/B 开关：TC_SOFT_TRACK）
RERANKER_SOFT_CATEGORIES = frozenset({"behavior", "potential"})
RERANKER_NEW_LABEL_THRESHOLD_SOFT = 0.05
RERANKER_SOFT_TRACK = _env_flag("TC_SOFT_TRACK")
# S8b：抽取后间接映射扩展（近邻阈值 / 每源近邻数 / 每员工上限）
# 消费者：agents/profile_generation._expand_indirect_labels（A/B 开关：TC_EXPAND）
EXPAND_NEIGHBOR_SIM = 0.75
EXPAND_TOP_N = 2
EXPAND_MAX_PER_EMP = 2
EXPAND_ENABLED = _env_flag("TC_EXPAND")
# S2：T1 抽取数量下限（prompt 文案 + 低于下限记 stats，不触发二次 LLM）与 few-shot kNN 选取数
# 消费者：agents/profile_generation._build_system_prompt / _process_employee / _select_few_shot_examples
T1_EXTRACT_MIN_COUNT = 5
FEWSHOT_KNN_K = 2
# S3：多遍抽取并集（预算门控：>1 需用户确认；A/B 开关：TC_EXTRACT_PASSES）
# 消费者：agents/profile_generation._multi_pass_extract / execute 超时预算联动
EXTRACT_PASSES = int(os.getenv("TC_EXTRACT_PASSES", "1"))
EXTRACT_UNION_TEMPERATURE = 0.7  # ADU 温度实验：适中温度换多样性，高温单次质量崩
```

注：S1 行为常量复用 `LABEL_RERANK_MAX_TOKENS` / `LABEL_RERANK_TIMEOUT`（plan_t1_optimization.md S1 原定义「config 无新行为常量」），仅新增开关量。

## 五、数据契约变更（C1）

**不变的契约**：`_RERANK_ITEM_KEYS`（`utils/label_matching.py` L85-88，7 key）不动——S1/B3 只扩展 `mapping_source` 的取值域，不增删 key。`_llm_extract` 返回 key 集 `{content, error, model, usage, offline_skipped}` 不变，仅加带默认值的 `temperature` 形参（向后兼容，所有既有调用点零改动）。

**新/改函数的返回 key 集合**：

| 函数 | 返回契约（所有路径同 key 集） |
|------|------|
| `rerank_cross_encoder`（改） | 每项仍为 `_RERANK_ITEM_KEYS` 7 key。路径注释（L465-469 docstring）需补 adjudication 路径：空 items→[]；encoder 不可用→LLM 降级；打分失败→LLM 降级；正常+终裁→7 key 全 |
| `_multi_pass_extract`（新，S3） | 与 `_llm_extract` 同 key 集 `{content, error, model, usage, offline_skipped}`。三条路径（offline 直通 / 全遍 error / 并集成功）key 集相同，函数末尾注释列明 |
| `_union_extract_contents`（新，S3） | 返回 content dict，key 集 = `_empty_extract()` 的 5 key `{t1_professional, t2_behavioral, big_five, t3_raw, t3_labels}` |
| `_expand_indirect_labels`（新，S8b） | 返回 `int`（新增扩展项数）；`content` / `emp_stats` 原地变更 |
| `_select_few_shot_examples`（新，S2） | 返回 `list[dict]`（示例库子集，元素 key `{channel, source_text, concept, standard_label, note}`（channel 为实现期新增第 5 键：t1t2/t3，供 prompt 分通道渲染——计划笔误补正 2026-09-10，独立检查 LOW-3 回写）） |
| `emp_stats` / `execute` stats | 新增 3 key：`llm_adjudications` / `expanded_labels` / `t1_below_min`。三处对称：`_process_employee` 初始化（L695-698）、`execute` 两个降级 stats dict（L642-647、L652-657）、聚合块（L659-672 `_sum`）——三处必须同 turn 同步改，防 key 漂移 |

**新增 mapping_source 枚举**（`utils/label_matching.py` L91-105 枚举区追加，D2 单一来源）：

```python
SOURCE_CROSS_NEW_LLM_CONFIRMED = "cross_new_llm_confirmed"  # S1：LLM 终裁否决新标签判定，从候选救回
SOURCE_CROSS_NEW_LLM_REJECTED = "cross_new_llm_rejected"    # S1：LLM 终裁维持"无合适候选"（计入新标签 cap）
SOURCE_EXPANDED = "expanded_neighbor"                        # S8b：间接映射扩展项（profile_generation 导入消费）
```

语义定死（防跨 agent 术语漂移）：`confirmed` = LLM 复核确认候选中有匹配（救回）；`rejected` = LLM 复核维持新标签判定。

## 六、实施步骤

### Phase 0（人工前置，零代码，建议但不阻塞 Phase 1）

0. **GT 复核与实验池扩展**（文件：`data/experiment/ground_truth_5.json`、`scripts/experiment_embedding_vs_llm.py:TARGET_EMPLOYEES` L65）
   - Action：用户复核 GT（7 个新增 T1 标签 + 「项目管理 vs 项目管理知识体系」口径二选一）；可选把 TARGET_EMPLOYEES 扩到 5 人（T1 GT 8→16，±1=6.25pp）。
   - Why：plan_t1_optimization.md Step 0 原文；口径类 miss 直接消除 3/31。
   - Dependencies：None；Risk：低（GT 改口径后历史数字需在 tracking 注明分界）。

### Phase 1：S1 LLM 兜底接线（匹配层 B4，改动最小，先做）

1. **`rerank_cross_encoder` 加终裁块**（File: `d:\workplace\talent-compass\utils\label_matching.py`，函数 `rerank_cross_encoder` L438-630）
   - Action：在每项打分循环（L557-602）结束之后、新标签防滥块（L604-620）之前插入：
     a. 收集 `rerank_results_by_idx` 中 `mapping_source ∈ {SOURCE_CROSS_NEW_LABEL, SOURCE_CROSS_PENDING}` 的项对应的 `to_rerank_items[ri]` 原始条目（含 idx/concept/standard_label/category/candidates/extract_confidence，契约与 `rerank_label_llm` 入参一致）；
     b. `config.RERANKER_LLM_ADJUDICATION` 为真且收集非空时，单次调用 `rerank_label_llm(adj_items, employee_context, corpus, call_llm_json_fn=call_llm_json_fn, trust_exact_match=False)`（`trust_exact_match=False` 与本函数既有两处降级调用 L496-499/L538-541 的 Step 1.10 语义一致：不让 exact 快路径锁死错误标签）；
     c. 合并规则：LLM 选了候选（`SOURCE_LLM_RERANK` 或 `SOURCE_PENDING`）→ 覆盖原项为 `{...matched_label=LLM 选择, is_new_label=False, mapping_source=SOURCE_CROSS_NEW_LLM_CONFIRMED, rationale="LLM复核救回: "+原 rationale}`，`match_confidence` 保留 LLM 值（<0.7 的 pending 性质经 confidence 可见）；LLM 判 NEW（`SOURCE_NEW_LABEL`）→ 覆盖为 `SOURCE_CROSS_NEW_LLM_REJECTED`，`is_new_label=True`，`matched_label=concept`；LLM 内部 cap 改写（`SOURCE_NEW_CAPPED`——`rerank_label_llm` 自身 cap L335-351 会把单员工第 3+ 个 NEW 项改写为此值）→ 同样覆盖为 `SOURCE_CROSS_NEW_LLM_REJECTED` + `matched_label=concept` + `is_new_label=True`，计入外层 cap 不二次惩罚（**[HIGH-1 修复 2026-09-10]**：原三分支漏此路径，会落入「保留原判定」兜底且内外 cap 双重计数）；LLM 降级（`SOURCE_RERANK_FAILED`）或返回长度 != len(adj_items)（C3 isinstance/长度守卫）→ **保留原 cross-encoder 决策**（D6：复核失败不改变原判定、不重试）；
     d. 新标签 cap 条件（L605-607 与 L607 对应处）从 `== SOURCE_CROSS_NEW_LABEL` 扩为 `in (SOURCE_CROSS_NEW_LABEL, SOURCE_CROSS_NEW_LLM_REJECTED)`，超额改写沿用既有 `SOURCE_NEW_CAPPED`（L619）。
     e. 超时联动（**[MED-4 修复 2026-09-10]**）：S1 启用时 `agents/profile_generation.py:execute`（L632-634）员工级超时改为 `timeout = config.AGENT_PROFILE_TIMEOUT + (config.LABEL_RERANK_TIMEOUT if config.RERANKER_LLM_ADJUDICATION else 0)`（120→300s）——GLM 慢 API（60-150s/次）下 90s 抽取 + 180s 终裁必然撞破 120s，不加联动则终裁永远被员工级超时降级抢杀。
   - Why：B4 断点在 L570-580——top_score < 0.15 即判新标签弃单，`rerank_label_llm` 存在但生产路径只在加载/打分失败时触发；Ma et al. 2023 验证 LLM 是困难样本的好 reranker。
   - Dependencies：None；Risk：中（终裁救错 → 见风险表 R1）。
   - 验证：正例 = mock `cross_encoder_fn` 全低分（<0.15）+ mock `call_llm_json_fn` 返回候选选择 → `mapping_source == "cross_new_llm_confirmed"` 且 key 集 == `_RERANK_ITEM_KEYS`。负向断言：① 开关关 → fake LLM 调用计数 == 0、`SOURCE_CROSS_NEW_LABEL` 保持现状；② fake LLM 返回 error → 原决策保留（不 trust standard_label）；③ 3 项 LLM 全判 NEW → 第 3 项为 `SOURCE_NEW_CAPPED`（cap 跨 source 生效）；④ V8 持续失败：fake 连续 error 跨 batch → LLM 调用次数有上界（每员工 ≤1 轮终裁，无重试放大）。
   - 配套：`agents/profile_generation.py:_inject_mapping_fields`（L825-831）stats 分支扩展——`cross_new_llm_confirmed` → `emp_stats["llm_adjudications"] += 1`；new_labels 分支元组（L828）加入 `cross_new_llm_rejected`。

### Phase 2：S8a 别名富化（数据侧，解 B2 的词面基础）

2. **t0_registries 质量管理类条目别名聚类**（File: `d:\workplace\talent-compass\data\t0_registries.json`，`KNOWLEDGE_REGISTRY` 中 category=="质量管理" 的 4 项）
   - Action（纯数据，零代码——`_load_registry_corpus`（`utils/label_embedding.py` L375-431）已把 aliases 拼进 corpus text（L419-420）且 `keywords=aliases`（L428））：
     - `ISO9001.aliases += ["质量工程", "质量体系"]`
     - `IATF16949.aliases += ["ISO9001", "质量工程"]`；`GJB9001C.aliases += ["ISO9001", "质量工程"]`；`六西格玛.aliases += ["质量工程"]`
   - 解释决策（需用户知悉）：指令字面为「给质量工程类条目 += ISO9001/质量管理体系」，但 t0_registries 中无名为「质量工程」的条目（质量工程是 `standard_label_library_v1.json` 的 T1 项，keywords 为 QE/PQA/SPC 系，不含 ISO9001 词面）。为打通 ISO9001→质量工程，落地为**质量管理类条目以 ISO9001/质量管理体系/质量工程家族词互为别名（双向边）**：词面进 keywords → `_build_system_prompt` 的 `_fmt_items`（L315-323）展示给抽取 LLM（见 ISO9001 证据可直接提议 standard_label=质量工程）；词面进 text → 召回相似度与 S8b 近邻扩展同时打通。若只做单向边，concept 侧选标签与标签侧找邻居两个方向都通不了。T1 标签库项的 aliases 消费机制属 S7 范围（需改 `load_label_corpus` L474 的 text 构造），本计划不动。
   - Why：竞品调研 B2 行——LinkedIn skill expansion 的前提是分类法内有别名/兄弟边；`docs/source_extracts_skill_extraction.md` 中 SkillNer（MIT）的 surface_forms 双槽位机制印证「一词多名进匹配层」是业界标配底层。
   - Dependencies：None（与 Phase 1 独立）；Risk：低（数据可 git 回退）。
   - 验证：正例 = `load_label_corpus()`（生产默认路径）后 ISO9001 项 `text` 与 `keywords` 含「质量工程」。负向断言：① corpus 的 name 集合前后不变（aliases 只进 text/keywords，GT 命中池不动）；② 测试 fixture 路径（`load_label_corpus(path=...)`）不合并 registry 的既有行为不变（现有 `tests/test_label_embedding.py` 保护）。

### Phase 3：S8b 抽取后扩展步（解 B2 的管线步）

**前置校准探针（[MED-2 修复 2026-09-10]，硬性 gate，先于任何 S8b 代码）**：S8a 数据 apply 后，用生产 corpus 打印 ISO9001 / IATF16949 / GJB9001C / 六西格玛 / 质量工程 各自的 top-5 近邻及 sim 值，人工确认：①「质量工程」能进 ISO9001 的 top-2 扩展槽；②无近亲证书项以更高 sim 占位（若有 → S8a 改单向边或扩展目标限 skill 类目）。若 ISO9001↔质量工程 sim 远低于 0.75，按 C 反事实预案转向 low_surface_forms 低置信候选注入（`docs/source_extracts_skill_extraction.md` 摘录 1），**禁止降阈值硬凑**。

3. **新方法 `_expand_indirect_labels`**（File: `d:\workplace\talent-compass\agents\profile_generation.py`，新增实例方法；调用点：`_process_employee` L734 `_inject_mapping_fields` 之后、L742 `compute_t3_scores` 之前，gate 为 `config.EXPAND_ENABLED and corpus`）
   - Action：
     a. 扩展源：仅 `content["t1_professional"]` 中「已匹配」项（`matched_label` 非空且存在于 corpus name 索引），排除 `item.get("expanded")` 项（防链式）；
     b. 对每个源：**直接取 `corpus_text_vecs` 中该源项对应行向量**，与全 corpus 向量矩阵算 cosine 取 top `EXPAND_TOP_N + 1`（**[MED-1 修复 2026-09-10]**：原方案调 `recall_top_k(query_text=...)` 的「LRU 命中零编码」断言不成立——缓存以整批 texts tuple 为 key，单条 query 的 1-tuple 不命中，每源产生 1 次冗余编码；行直查才是真零新增编码）；
     c. 近邻过滤：`name != 源名`、corpus 项 `tier == "T1_专业能力"`（防跨层扩展出 T2/T3 标签）、`sim > EXPAND_NEIGHBOR_SIM`、name 不在员工已匹配标签全集（t1/t2/t3 的 matched_label + 已扩展项）中；
     d. 命中即向 `content["t1_professional"]` append 扩展项：`{concept: 邻居name, standard_label: 邻居name, category: 邻居category, confidence: float(sim), matched_label: 邻居name, is_new_label: False, mapping_source: SOURCE_EXPANDED, match_confidence: float(sim), rerank_candidates: [源名, 邻居name], rerank_rationale: f"间接映射扩展: {源名} 近邻 sim={sim:.3f}", expanded: True, expanded_from: 源名, evidence: []}`（evidence 留空不伪造锚点，靠 `expanded` 标记区分——C8 不发明数据）；
     e. 上限：每员工新增 ≤ `EXPAND_MAX_PER_EMP`，到达即 break；返回新增数并写 `emp_stats["expanded_labels"]`。
   - Why：竞品调研 S8——LinkedIn 的解法不是让抽取器更聪明，而是抽取后沿技能图关系补全隐式技能；embedding top-2 近邻即兄弟技能边（S8a 别名已把 ISO9001 与质量工程的 text 拉近）。
   - Dependencies：Phase 2（S8a 数据边）；Risk：中（expanded 项缺 sfia_level/ability_score/evidence → 下游 schema 兼容，见风险 R3；F2 grep 已确认代码内 `t1_professional` 消费仅本文件/实验脚本/测试）。
   - 类型守卫（C3/G）：corpus 项非 dict 跳过；`matched_label`/邻居 name 非 str 或为空跳过；`recall_top_k` 返回的 sim 非 float 直接 `float()` 夹紧失败即跳过该邻居；失败信息含 `type(x).__name__`。
   - 验证：正例 = 构造 t1 项 `matched_label="ISO9001"`，fake 编码使「质量工程」为 ISO9001 text 的 top-1 近邻 sim=0.82 → 扩展后 t1_professional 多 1 项 `matched_label=="质量工程"` 且 `expanded is True`、`mapping_source=="expanded_neighbor"`。负向断言：① cap：可扩展源 ≥3 时仅新增 ≤2；② sim=0.74 ≤ 0.75 不新增；③ 近邻 name 已在员工匹配集不重复新增；④ `expanded:True` 项不作为扩展源（无链式）；⑤ `EXPAND_ENABLED=False` → content deepcopy 对比不变且 `emp_stats["expanded_labels"]==0`；⑥ 近邻为 T2/T3 tier 项不扩展；⑦ 零落盘：运行 `_process_employee` 前后 `data/intermediate/` 目录文件清单（glob 快照）不变。

   **S8b 副作用矩阵**（写入点 × 快速退出路径）：

   | 写入点 | EXPAND_ENABLED=False | corpus=None/空 | 无已匹配 T1 项 | 近邻全 sim≤0.75 | cap 已满 | offline 短路 |
   |---|---|---|---|---|---|---|
   | `content["t1_professional"].append`（进程内） | gate 直接 return 0 | return 0 | return 0 | 不 append | 不 append | 不进入（offline 走 `_assemble_profile`，L714-718，不调本方法） |
   | `emp_stats["expanded_labels"]` | 0 | 0 | 0 | 0 | 0 | 0 |
   | 磁盘/缓存/目录 | 无 | 无 | 无 | 无 | 无 | 无 |

   结论：唯一副作用是进程内 list append 与计数；所有快速退出路径零 append；**零额外落盘**（矩阵逐项对照通过）。

### Phase 4：B3 软技能分轨阈值

4. **`rerank_cross_encoder` 分轨 new_threshold**（File: `d:\workplace\talent-compass\utils\label_matching.py`，打分循环 L557 起；阈值读取点 L549）
   - Action：循环内每项计算有效阈值：`cat = it.get("category", "")`，`is_soft = config.RERANKER_SOFT_TRACK and isinstance(cat, str) and cat in config.RERANKER_SOFT_CATEGORIES`，`eff_new_threshold = config.RERANKER_NEW_LABEL_THRESHOLD_SOFT if is_soft else config.RERANKER_NEW_LABEL_THRESHOLD`；L570 判定改用 `eff_new_threshold`，L577 rationale 的 f-string 同步带有效阈值值（审计可解释）。`conf_threshold`（0.5）两轨共用不改。
   - Why：B3——T2/T3 抽象词的 cross-encoder 打分天然低（0.03-0.10 < 0.15 → `SOURCE_CROSS_NEW_LABEL` 误杀）；LinkedIn 分关系类型打分的轻量版。备选变体「soft 跳过 cross-encoder 直送 LLM」不加死 config（D1：消费者必须存在），留作 0.05 轨无效时的替代方向（两次失败换方向纪律）。
   - Dependencies：None（与 Phase 1 同函数不同分支）；Risk：低-中（0.05 偏低假阳性 → env 可调 + S1 终裁兜底）。
   - 验证：正例 = behavior 项 score=0.08 → `is_new_label is False` 且 `matched_label == top 候选`（0.08 ≥ 0.05，落在 pending/确认带而非新标签带）。负向断言：① skill 项 score=0.08 < 0.15 → 仍 `SOURCE_CROSS_NEW_LABEL`（hard 轨不变）；② soft 项 score=0.03 < 0.05 → 仍判新标签（软轨非免死金牌）；③ `category` 缺失/非 str → 走 hard 轨（isinstance 守卫）。

### Phase 5：S2 prompt 稳定化 + few-shot kNN 选取

5. **`_build_system_prompt` 加约束与签名扩展**（File: `d:\workplace\talent-compass\agents\profile_generation.py`，`_build_system_prompt` L289-419；调用点 `_llm_extract` L201）
   - Action：
     a. 签改 `def _build_system_prompt(self, employee: dict | None = None) -> str`；`employee is None` → 用静态默认 few-shot（向后兼容，测试隔离）；`_llm_extract` L201 改为 `self._build_system_prompt(employee)`（F2：grep 该方法全部调用点，本仓仅 `_llm_extract` 与测试）。
     b. T1 通道块（L342 附近）加约束文案：T1 至少输出 `T1_EXTRACT_MIN_COUNT` 个标签；输出前逐字段自查（岗位序列/项目摘要/绩效摘要/证书/培训课程各扫一遍，字段中的技术词汇映射到标签库者不得遗漏；证书须评估其对质量/体系类标签的证据价值）。
     c. few-shot 由静态 `few_shot_t1t2`/`few_shot_t3`（L375-398）改为：模块级示例库 `_FEWSHOT_BANK`（~10 条，种子取自现 6 条 + 扩充覆盖硬技能/软技能/潜质/证书类）+ 新方法 `_select_few_shot_examples(employee, encode_fn=None)`：员工 `summary_perf+summary_proj` 拼接文本 encode 后与 bank 各条 `source_text` cosine，取 top `FEWSHOT_KNN_K` 条渲染进 prompt（每员工 1 次 encode，LRU 缓存）。
   - Why：B1 的引导性部分（整段字段没看类漏抽）；竞品调研迁移建议 4——Nguyen 结论 few-shot 按输入语义相似度选取优于随机；`docs/source_extracts_skill_extraction.md` 中 Skill-LLM（无 LICENSE，仅模式参考）的 concept+context 双锚点输出契约与本步自查清单同向（text_snippet 已是 context 锚点弱化版，本步不加新字段、不动输出 schema）。
   - Dependencies：None；Risk：中（prompt 改动影响同调用三通道 → 全量回归；数量下限诱导凑数 → confidence 下限由匹配层 cap 兜底）。
   - 类型守卫：summary 各字段非 str → 按 "" 处理（isinstance，日志含 `type(x).__name__`），encode 失败 → 回退静态 2 条（不重试，D6）。
   - 验证：正例 = prompt 含「至少」+ `str(T1_EXTRACT_MIN_COUNT)`；fake `encode_fn` 使员工与 bank 条目 1 最近 → 渲染含该条示例。负向断言：① `employee=None` → 不触发 encode（fake 计数 0）且输出含静态默认示例；② t1 数 3 < 5 → `emp_stats["t1_below_min"]==1` 且 `emp_stats["llm_calls"]==1`（D6：不触发第二次 LLM）；③ bank 不全量进 prompt（kNN 只选 K=2 条，断言渲染后 prompt 相对静态版增量 < 2000 字符）。

### Phase 6：S3 多遍并集（预算门控 + F8 前置验证）

6. **F8 前置验证探针（硬性 gate，先于任何 S3 代码）**
   - Action：用 `_llm_extract` 加 `temperature` 形参后（见步骤 7a），同一员工 prompt × 5 次 `temperature=EXTRACT_UNION_TEMPERATURE`（0.7）探针（一次性脚本，不入库）：断言 ≥3 次输出的 concept 集两两有差异；同时确认 thinking 模式兼容（`PROFILE_EXTRACT_MAX_TOKENS=8192` 下 finish_reason 非 length、content 可解析、无 API 报错）。
   - Why：F8——DeepSeek-V4-Pro 为推理模型，thinking tokens 计入 max_tokens（config.py L212-217 注释），且部分思考型端点忽略/钳制 temperature；若输出全同，S3 的 k 遍并集零增益而成本 ×3。
   - 失败处置：探针不通过 → S3 停止实施，向用户上报（候选替代：换模型槽做多样性遍 / 接受 S2+S8+S1+B3 组合结果），禁止带病上线。
7. **`_llm_extract` 加形参 + `_multi_pass_extract` + `_union_extract_contents`**（File: `d:\workplace\talent-compass\agents\profile_generation.py`）
   - a. `_llm_extract`（L156-264）签名加 `temperature: float = 0.0`，L210 `call_llm_json(..., temperature=temperature, ...)`。默认值保证既有调用零变化。
   - b. 新方法 `_multi_pass_extract(employee, context)`：C1 与 `_llm_extract` 同 5 key 返回集。路径（末尾注释列明）：offline/cancel → 直通单遍；k=`config.EXTRACT_PASSES`（运行时读 env）；k==1 → 单遍 `temperature=0.0`（与现状逐位一致）；k>1 → 各遍 `temperature=EXTRACT_UNION_TEMPERATURE`；某遍 infra error → 记 warning 用其余成功遍（不重试）；全部遍 error → 返回最后一遍 error 结果；解析失败遍已由 `_llm_extract` 内部降级为空 content（error=None），并集无害。
   - c. 新方法 `_union_extract_contents(contents: list[dict]) -> dict`：t1/t2/t3_labels 按 `concept` 精确名去重（首见保留结构，同 concept 后续遍的 evidence 按 text_snippet 去重后并入）；big_five 各维取均值 clamp 0-100；t3_raw 各子列表去重并集。返回 key 集 = `_empty_extract()` 5 key。
   - d. 接线：`_process_employee` L705 `extract = self._llm_extract(...)` → `self._multi_pass_extract(...)`；L706-707 `emp_stats["llm_calls"]` 由固定 1 改为尝试遍数（offline 为 0）——C8 真实调用计数口径。
   - e. 超时联动：`execute` L632-634 `fut.result(timeout=config.AGENT_PROFILE_TIMEOUT)` → `timeout=max(config.AGENT_PROFILE_TIMEOUT, config.PROFILE_EXTRACT_LLM_TIMEOUT * config.EXTRACT_PASSES + 30)`。k=1 → max(120,120)=120 不变；k=3 → 300s（防 3×90s 串行必然超时降级）。
   - Why：归因决定性事实——6-run concept 并集可命中 7/8 GT，单次抽取非确定性才是瓶颈；ADU 温度实验支撑 temp 0.7 适中。
   - Dependencies：步骤 6 探针通过 + 用户预算确认（实验 5 员工 × 3 run × 3 pass ≈ 30 万 tokens；50 员工 demo ≈ 1M tokens 增量）。
   - 验证：正例 = monkeypatch `_llm_extract` 两遍返回不同 concept → 并集含两者、同 concept evidence 合并去重、usage 求和。负向断言：① `EXTRACT_PASSES=1` → `_llm_extract` 仅 1 次且 `temperature==0.0`（零行为变化）；② offline → `offline_skipped=True` 直通 0 次 LLM；③ 全遍 error → 返回 error 且 key 集对称；④ k=1 时超时预算仍为 120（公式断言）。

## 七、A/B 实验设计（单步增量归因，不同时叠加）

载体：`scripts/experiment_embedding_vs_llm.py`（`TARGET_EMPLOYEES` L65，主指标 `path_c_recall_at_gt_pct`，每配置 ≥3 run 取均值）。归因规则：每次只翻一个开关，其余固定在「已接受」状态；每步 commit 独立，实验数据归档 + `progress.md`/`change-log`/tracking 同步（commit 前三件套纪律）。

| 序 | 配置 | 开关状态 | 脚本改动 | 观测 |
|---|---|---|---|---|
| 0 | Baseline | 全关（TC_LLM_ADJUDICATION=0, TC_EXPAND=0, TC_SOFT_TRACK=0, TC_EXTRACT_PASSES=1）+ S8a 数据 git 回退 + S2 基线 commit | 无 | 基线 recall@GT（对齐 25-37.5%） |
| 1 | S1 | TC_LLM_ADJUDICATION=1 | Path C 统计块（L381-412）加 source 计数：cross_new_llm_confirmed/rejected；summary["path_c"] 新增 key（向后兼容） | new_labels 降、confirmed>0、「数据分析」类 miss 救回 |
| 2 | S8a | 数据 apply（其余同序 1 已接受态） | 无 | ISO9001 概念的 candidates 含质量工程 |
| 3 | S8b | TC_EXPAND=1 | 脚本不走 `_process_employee`，需在 L379 rerank 后显式调 `agent._expand_indirect_labels(content, corpus, corpus_text_vecs, stats_proxy)` + per-employee expanded 明细 | **验收锚点：ISO9001→质量工程 翻正（≥2/3 run）**；expanded ≤2/员工 |
| 4 | B3 | TC_SOFT_TRACK=1 | 无 | 软技能 GT（团队管理等）命中变化；硬技能不回归 |
| 5 | S2 | prompt 新版（基线 = 上一 commit，git A/B） | 无（流经 `_llm_extract`） | t1_count 均值上升；漏抽类 GT 救回 |
| 6 | S3 | TC_EXTRACT_PASSES=3（探针 + 预算已确认） | L239 `agent._llm_extract(...)` → `agent._multi_pass_extract(...)`；L241-242 attempts 计数改 += `config.EXTRACT_PASSES`；summary 加 `extract_passes` | recall@GT 3-run 均值 ≥60% 判定门 |

两次失败纪律：同一步 A/B 3-run 无提升或回归 → 停，列 ≥2 个替代方向（各附预期收益/风险/验证方法），禁止微调后第三次。

## 八、测试策略

- 单元测试（改/新增文件级）：
  - `tests/test_label_matching.py`：`TestRerankCrossEncoder`（L377 起）新增 S1 四用例 + B3 三用例（见 Phase 1/4 验证块）；`TestLoadCrossEncoderRetry`（L625 起）不动。
  - `tests/test_profile_generation.py`：S8b 七用例 + 副作用矩阵零落盘用例；S2 三用例；S3 四用例。
- 集成测试：`pytest tests/ -v` 全量回归（S2 改 prompt 触及三通道，必须全量）；fixture 走真实 I/O 路径（防假绿：不得构造 dict 绕过 `_process_employee` 的 iterrows/注入真实分支）。
- E2E/实验：第七节 A/B 序列；每步 ≥3 run；口径警告遵守（±1 GT = 12.5pp，扩 5 员工则 6.25pp）。

## 九、风险与缓解

- **R1 S1 终裁救错（precision 回退）**：观测 confirmed 项 in_ground_truth 比例；必要时收窄为仅 `SOURCE_CROSS_NEW_LABEL` 复核（去掉 PENDING）再 A/B。
- **R2 S8a 双向边精度风险**：质量工程 concept 可能反向召回 ISO9001/体系工程 knowledge 项错配。缓解：cross-encoder 全候选重排（Step 1.10 已禁 exact 锁定）+ S1 终裁；监控 path_c 误配率。
- **R3 S8b expanded 项缺 sfia_level/ability_score/evidence**：F2 grep 确认代码内消费仅 profile_generation/实验脚本/测试；`docs/plan-profile-agent-schema.md` 需在 S8b commit 前同步 expanded 字段定义；下游若取 `item["sfia_level"]`（非 .get）会崩——schema 同步 + 消费侧 .get 约定写入 schema 文档。
- **R4 B3 soft=0.05 假阳性**：env/常量可调；S1 终裁兜底；软技能 precision 监控。
- **R5 S3 F8 兼容性 + 成本 + 超时**：探针 gate（Phase 6 步骤 6）+ 预算用户确认 + 超时联动公式（步骤 7e）；并集假阳性靠 S1 终裁 + `LABEL_NEW_LABEL_MAX_PER_EMP` cap + confidence 过滤兜底。
- **R6 `_build_system_prompt` 签名变更破坏测试**：F2 grep 调用点（仅 `_llm_extract` + tests）；`employee=None` 默认路径保兼容。
- **R7 stats key 三处漂移**：`emp_stats` 新 key 必须同 turn 同步三处（L695-698 初始化、L642-647/L652-657 降级 dict、L659-672 聚合），`_sum` 用 .get 容错但对称纪律以三处齐改为准。
- **R8 S1 终裁超时撞破员工级预算（[MED-4 修复]）**：联动公式见 Phase 1 步骤 e（S1 开→120→300s）；监控 path_c 中 rerank 降级率不升。

## 十、成功标准

- [ ] ISO9001→质量工程 翻正（S8 验收锚点）：含 ISO9001 证据员工 3-run 中 ≥2 run 输出含「质量工程」（直接 matched 或 expanded）
- [ ] T1 recall@GT（`path_c_recall_at_gt_pct`）3-run 均值 ≥60%
- [ ] S1 负向断言：开关关 = 零 LLM 终裁调用，行为与基线一致；LLM 失败不改原判定
- [ ] S8b：expanded 每员工 ≤2、零链式、`data/intermediate` 零新增文件（副作用矩阵验收）
- [ ] B3：soft 轨不误杀（0.08 不判新）、hard 轨不变（0.08 仍判新）
- [ ] S3：k=1 零行为变化（temperature=0.0、单次调用、超时 120 不变）；F8 探针通过后才允许 k>1
- [ ] `python -m pytest tests/ -v` 全绿；每步 commit 前 `progress.md` [AWAITING_VERIFY]→[VERIFIED] + tracking 三件套同步
- [ ] 新标签不泛滥：每员工 new（含 rejected/capped）≤ `LABEL_NEW_LABEL_MAX_PER_EMP`

---

计划完毕。关键落地锚点文件：`d:\workplace\talent-compass\utils\label_matching.py`（S1/B3/枚举）、`d:\workplace\talent-compass\agents\profile_generation.py`（S8b/S2/S3/超时联动）、`d:\workplace\talent-compass\config.py`（新常量块）、`d:\workplace\talent-compass\data\t0_registries.json`（S8a 数据）、`d:\workplace\talent-compass\scripts\experiment_embedding_vs_llm.py`（A/B 载体）、`d:\workplace\talent-compass\docs\source_extracts_skill_extraction.md`（机制参考，S8a/S8b/S2 各引一处）。

一处解释性决策需用户确认：S8a 的别名富化方向（第六节 Phase 2 「解释决策」段）——t0_registries 无「质量工程」条目，落地为质量管理类条目家族词双向聚类而非字面单向追加，以满足 ISO9001→质量工程翻正锚点。
