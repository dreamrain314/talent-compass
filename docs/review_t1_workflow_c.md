# T1 优化工作流 · 角色C 总监督检视报告

> **检视角色**：角色C 总监督（ecc:code-reviewer，工作流 fan-out 第三角色） ｜ **日期**：2026-09-10
> **检视对象**：A 产出 `docs/plan_t1_s1_s8_b3_implementation.md`（六 Phase 实施计划）+ B 产出 `docs/source_extracts_skill_extraction.md`（SkillNer/Skill-LLM 源码摘录）
> **检视框架**：假设有 bug 的对抗审查——对计划引用的全部代码锚点逐一回到源码核实（幽灵引用检查）、边界值推演、契约对称性核对、许可证合规
> **主循环注**：LOW-1 所指笔误（TestLoadCrossCrossEncoderRetry）系竞态——C 读取文档与主循环 Edit 修复同块发生，盘上现为正确拼写，无需再修；其余内容保持 C 结论原样。

---

## 一、总判定

| 对象 | 判定 | 发现 |
|------|------|------|
| A 计划 | **APPROVE_WITH_FIXES** | 1 HIGH + 4 MED + 4 LOW；修复 HIGH-1 并补 MED-2 校准探针后方可进入 Phase 1 实施 |
| B 摘录 | **APPROVE** | 6 摘录源码引用与许可证标注核实无误，可直接归档使用 |

**锚点核对**：39 处代码锚点逐一回源码验证，38 处精确命中、1 处为上述笔误竞态（已修复）→ **幽灵引用 0**。计划对 `label_matching.py` / `profile_generation.py` / `config.py` 的行号、枚举、内部逻辑引用全部真实。

---

## 二、发现明细

### HIGH-1：S1 合并规则遗漏 `SOURCE_NEW_CAPPED` 路径

`rerank_label_llm` 内部有独立的新标签 cap（`utils/label_matching.py` L335-351）：单员工第 3+ 个 NEW 判定会被其内部改写为 `SOURCE_NEW_CAPPED`（拾取 top 候选）。A 计划的合并规则只定义了三个分支（LLM 选候选→CONFIRMED / LLM 判 NEW→REJECTED / LLM 降级→保留原判定），**`SOURCE_NEW_CAPPED` 不属于任何分支**——落在"保留原判定"兜底里，语义错误且外层 cap（L604-620 扩展后的判定）会与内层 cap 双重计数。
**修复**：增加显式第四分支——内层返回 `SOURCE_NEW_CAPPED` → 覆盖为 `SOURCE_CROSS_NEW_LLM_REJECTED` + `matched_label=concept` + `is_new_label=True`，计入外层 cap 但不二次惩罚。

### MED-1：S8b「零新增模型编码调用」断言不成立

`encode_labels` 的 LRU 缓存以整批 texts tuple 为 key；`_expand_indirect_labels` 用单条 query 文本调用 `recall_top_k`，1-tuple 与预编码时的全量 tuple key 不同 → **每个扩展源实际产生 1 次编码调用**。量级小（bge-small 单条 CPU 编码毫秒级）但断言为假。
**修复**：既然 query 就是 corpus 项，直接用 `corpus_text_vecs` 对应行查向量计算相似度（零编码），或修正文档断言。

### MED-2：S8a 双向别名制造近亲竞争，威胁验收锚点

S8a 把「ISO9001/质量工程」家族词同时加进 IATF16949、GJB9001C、六西格玛的 aliases → 富化后 ISO9001 文本的 top 近邻大概率是这批近亲证书项，而非 T1「质量工程」。S8b 的 `EXPAND_TOP_N=2` + `EXPAND_MAX_PER_EMP=2` 槽位会被近亲占满，**ISO9001→质量工程 验收锚点可能因排序竞争而非 sim<0.75 失败**——届时误诊为阈值问题去调 0.75 是错误方向。
**修复**（三选一，推荐 a）：a. S8b 启用前跑校准探针，打印 ISO9001/质量工程等的 top-5 邻居及 sim 值人工确认；b. S8a 改单向边（家族词只进 ISO9001 一侧）；c. 扩展目标限定 skill 类目。

### MED-3：`_env_flag` 默认 "1" 违反 baseline 纪律

`_env_flag(name, default="1")` 使四个开关（TC_LLM_ADJUDICATION/TC_SOFT_TRACK/TC_EXPAND）在 env 未设时**全部默认开启**——与 A/B 实验第 0 行「全关 baseline」及测试隔离纪律冲突：CI/pytest 环境未显式设 env 时会静默带 S1 跑测试。
**修复**：`default="0"`（opt-in），或测试 conftest 显式清 env。

### MED-4：S1 终裁超时未纳入预算

S1 在 `rerank_cross_encoder` 内调用 `rerank_label_llm`（预算 `LABEL_RERANK_TIMEOUT=180s`），而该调用链处于 `_process_employee` → `execute` 的 `fut.result(timeout=AGENT_PROFILE_TIMEOUT=120)` 之下。90s 抽取 + 180s 终裁 > 120s → **员工级超时降级会在 LLM 本可成功时触发**。计划只给 S3 写了超时联动公式（Phase 6 步骤 7e），S1 漏了。
**修复**：S1 启用时间样加联动（如 `timeout = AGENT_PROFILE_TIMEOUT + (LABEL_RERANK_TIMEOUT if RERANKER_LLM_ADJUDICATION else 0)`），并补进风险表 R8。

### LOW 级

- **LOW-1**：计划中出现 `TestLoadCrossCrossEncoderRetry` 笔误——系主循环修复与 C 读取的竞态，盘上已正确，无需处理。
- **LOW-2（D1）**：`_env_flag` 的真值元组 `("1","true","yes","on")` 与 `config.py:is_offline_mode`（L113-115）独立重复定义——应提炼共享常量。
- **LOW-3（F8 措辞）**：「部分思考型端点忽略/钳制 temperature」表述成立，探针设计已覆盖，无需改。
- **LOW-4（命名）**：`SOURCE_CROSS_PENDING`（cross-encoder 低置信带）与 `rerank_label_llm` 返回的 `SOURCE_PENDING`（<0.7 pending）语义相近易混淆，建议在枚举注释中写明二者区别。

---

## 三、确认通过项（对抗审查未击穿）

1. **B3 非假绿**：`_build_user_prompt` 的 category 取值已代码核实（t1 通道 skill/tool/domain/knowledge、t2 通道 behavioral、t3 通道 potential），`RERANKER_SOFT_CATEGORIES={behavior,potential}` 与真实值域吻合，无字符串比较盲区。
2. **S8a 测试安全**：aliases 只进 `_load_registry_corpus` 的 text/keywords（L419-420/L428），corpus name 集合不变 → GT 命中池不动；fixture 路径 `load_label_corpus(path=...)` 不合并 registry 的既有行为有测试保护。
3. **S8b 闭环自洽**：副作用矩阵覆盖全部快速退出路径，零落盘断言成立；cap/防链式/跨层过滤的负向断言齐全。
4. **契约对称（C1）**：新函数返回 key 集合均按路径列明；`_RERANK_ITEM_KEYS` 7 key 不动的约束贯穿始终；stats 三处对称扩展已识别（R7）。
5. **许可证合规**：SkillNer=MIT（可复用需保留声明）；Skill-LLM 无许可证——B 文档全程仅模式参考、伪代码已重写中文化，未逐字复制，合规。
6. **B 摘录质量**：抓取记录、行号、schema 还原、`len_` 变量遮蔽 bug 与 `eval()` 禁用点标注均核实；「抄/改/扔」三分结构可直接指导实施。

---

## 四、深度思考（超出逐条检视的三个观察）

**4.1 三个结构性空隙**
1. `EXPAND_NEIGHBOR_SIM=0.75` 是未标定常数——没有任何证据表明 bge-small-zh-v1.5 会把 ISO9001 与质量工程的相似度放到 0.75 以上（这正是 MED-2 校准探针必须前置的原因）。
2. S1 超时预算缺口（MED-4）在慢 API（GLM 60-150s/次）下不是理论风险而是必然触发。
3. S2 的 `t1_below_min` 只记 stats 不触发动作（无牙齿）——这是可接受的设计（D6 不加第二次 LLM），但应在计划中明说它是「监控指标」而非「纠正机制」，防止后续误读。

**4.2 收益估计的系统性偏差**：S3 的预期收益被高估（6-run 并集 87.5% 来自跨独立 run 的多样性，同一 prompt 下 temp=0.7 三遍的多样性弱于跨 run），S1 的收益被低估（纯接线、直接回收 13% 匹配层损耗、成本近零）。**建议维持 A 的排序（S1 最先）但把心理预期反过来**：S1 是确定性收益，S3 是彩票。

**4.3 若指标不动的诊断顺序**（给未来 debug 的自己）：`expanded_labels` 计数（S8b 是否触发）→ 近亲竞争检查（MED-2：邻居是谁）→ `t1_below_min`（S2 是否生效）→ F8 探针重跑（temperature 是否真生效）。

**4.4 反事实推演——如果这套方案整体失败，最可能的单点假设是什么？**
「embedding 词面相似度能承载证书→能力的语义跳跃」。若校准探针显示 ISO9001↔质量工程 sim 远低于 0.75，**正确动作不是降阈值**（会引入大规模噪声扩展），而是转向 B 摘录 1 的 `low_surface_forms` 设计：证书词作为低置信候选**直接注入 cross-encoder/LLM 终裁的候选列表**，跳过 embedding 召回这一跳。该转向与 S1（已实施时）天然兼容。

---

## 五、结论

1. **A 计划**：质量高于预期（锚点全真、契约意识完整、负向断言密度高）。**前置条件**：修复 HIGH-1（第四分支）+ 落实 MED-2 校准探针；MED-1/3/4 可在实施对应 Phase 时随手修。满足后按 Phase 1（S1）开工。
2. **B 摘录**：归档可用。实施 S2/S8 时回查对应摘录的「抄/改/扔」清单即可。
3. **给用户的决策点**：S8a 双向边设计（A 的解释性决策）需确认；开关默认值改 opt-in 需确认；S2 验收口径（监控而非纠正）与 S3 预算（约 30 万 tokens 实验 / 1M demo）需批准。

—— 角色C 检视完毕。39 锚点 · 幽灵 0 · 1 HIGH · 4 MED · 4 LOW · B3 假绿排除 · 反事实转向路径已备。
