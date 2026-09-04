# 双层 argmax 标签抽取框架落地策划案

> **状态：[PAUSED — 待 T1 方案就绪后一起落地]**
> **日期：2026-07-29**
> **关联文档：`docs/plan_argmax_e_verify.md`（E 方案模拟验证，已完成）**

---

## 一、背景与目标

### 1.1 问题
当前三阶段匹配（recall_top_k + rerank_cross_encoder + rerank_label_llm）在真实 5 员工实验中整体 recall@GT 仅 **50.0%**（3 员工实测，Path A/C），分层表现极度不均：

| Tier | 旧路径 Path A | 旧路径 Path C | argmax 模拟 |
|------|--------------|--------------|------------|
| T1 硬技能 | 25.0% | 37.5% | 9.1%（不可行）|
| T2 行为能力 | 85.7% | 85.7% | 83.3% |
| T3 发展潜力 | 40.0% | 20.0% | **93.5%** |

**核心矛盾**：T3 旧路径极差（20-40%），但 argmax 模拟高达 93.5%；T2 两者持平（85.7% vs 83.3%）；T1 argmax 不可行（9.1%），旧路径也仅 25-37.5%。

### 1.2 目标
- **T2/T3 改为 argmax 路由**（无 LLM 兜底），预期 T2≈83%、T3≈93.5%
- **T1 维持旧路径现状**（25-37.5% 召回），T1 优化作为独立后续任务
- 整体 recall@GT 预期：T2/T3 大幅改善后，T1 成为唯一短板，待 T1 方案就绪后一并落地

### 1.3 架构原则（用户确认）
1. **跨层重叠可接受**：T2↔T3 独立抽取，同样的话中可同时提取 T2 和 T3 标签，跨层重叠不需处理
   > **两阶段区分（重要）**：
   > - **LLM 抽取阶段：非独立**——单次 LLM 调用，prompt 内 T1/T2/T3 三通道分块引导，三通道在同一次调用内产出
   > - **rerank/argmax 阶段：逐项独立**——每个 concept 独立走 recall+rerank 或 argmax 路由，tier 间互不影响
   > - argmax 改造后，T2/T3 的 argmax 路由仍是逐项独立（与旧 rerank 阶段一致），"独立抽取"指路由阶段而非 LLM 调用阶段
2. **层内正交**：每层内部标签间需尽量正交，冲突词独占给一方
3. **T2/T3 纯 argmax 无兜底**：成本最低，失败案例可接受（部分是 GT 不准确导致）

---

## 二、标签库改造方案（已定稿）

### 2.1 T1_专业能力
**维持现状不变**（99 标签），走旧 recall+rerank+LLM 路径。

### 2.2 T2_行为能力
**维持现状 13 标签**（D 方案 OVERRIDES 版，已在 `scripts/verify_argmax_routing.py` 验证 = 83.3%）。

> **决策记录**：曾尝试把"尽责性"移入 T2（E 方案初版 T2=14），但模拟显示尽责性成为强吸铁石，吞噬质量导向（66.7%→16.7%）和执行推进，T2 反退步至 77.4%。最终采纳 A2 方案——砍掉尽责性，态度词（靠谱/严谨细致）漂到执行推进或质量导向内部消化，接受 D 方案那样的内部抢票。跨层独立抽取，员工画像里态度词会被某个 T2 标签兜住。

T2 关键标签的 OVERRIDES（D 方案版，落地时写入标签库）：
- **执行推进**：`["执行","推进","落地","交付","按时","闭环","克服障碍","推进任务","进度","进度跟进"]`（纯动作，删态度词）
- **质量导向**：`["质量","标准","合规","规范","精度","零缺陷","质量控制","质量意识","分内工作尽责","质量把控","持续改进"]`
- **变革推动**：`["变革","改革","新流程","过渡方案","引导适应","推动变革","打破现状","转型","组织变革","有主见能推动决策","主导变革"]`
- 其余 10 个标签的 OVERRIDES 见 `scripts/verify_argmax_routing.py` 的 `OVERRIDES` dict

#### ✅ 已定稿：选项 B（D 方案 + 三个 keyword 偏好）

E 方案讨论阶段用户确认了三个 T2 keyword 调整，A2 决策"T2 回 D 方案 13 标签"后重跑模拟验证：

| 标签 | 用户偏好 | D 方案原值 | 选项 B 最终 keywords | 命中变化 |
|------|---------|-----------|---------------------|---------|
| **执行推进** | 用"行动导向/结果驱动"锚定 | `["执行","推进","落地","交付","按时","闭环","克服障碍","推进任务","进度","进度跟进"]` | `["行动","结果驱动","落地","按时交付","克服障碍","达成目标","坚持推进"]` | 70%→80% ↑ |
| **质量导向** | 删"精度/标准"（与"高标准"同质） | `["质量","标准","合规","规范","精度","零缺陷","质量控制","质量意识","分内工作尽责","质量把控","持续改进"]` | `["质量","零缺陷","合规","规范","过程控制","交付质量","质量保障"]` | 66.7%→66.7% = |
| **跨部门协调** | 保留"沟通"（用户明确"不接受删掉"） | `["跨部门","横向协调","信息壁垒","共识","多团队协作","部门协作","信息同步"]` | `["跨部门","横向协调","信息壁垒","部门墙","协作","共识","沟通"]` | 85.7%→85.7% = |

**模拟结果（2026-07-29）**：
- T2 = **85.2%**（vs 纯 D 方案 83.3%，+1.9pp）
- T3 = 93.5%（不变）
- 三个偏好全部无负面冲击，执行推进还涨了 1 个 query
- **选项 B 全面优于选项 A，定稿**

### 2.3 T3_发展潜力
**重排为 7 标签**（E 方案版，最终模拟 = 93.5%，2026-07-29 定稿）：

| # | 标签 | keywords |
|---|------|---------|
| 1 | 领导力潜质 | 愿景构建/激励他人/凝聚人心/承担leader/**承担leader角色**/带队潜质/决策担当/团队决策 |
| 2 | 影响力构建 | 专业输出/观点传播/人际网络/个人品牌/话语权/行业发声 |
| 3 | 自驱力 | 内生动力/目标设定/自我监督/进取心/**自觉**/无需督促 |
| 4 | 开放性 | 开放/好奇心/探索/多元视角/想象力/审美 |
| 5 | 战略眼光 | 战略眼光/趋势判断/前瞻/技术视野/长远洞察 |
| 6 | 跨界整合潜力 | 跨界/多领域/关联发现/知识迁移/跨域整合 |
| 7 | **韧性与成长心态** | 韧性/逆境反弹/持续学习/拥抱挑战/抗压/情绪稳定/恢复力/从挫折中恢复 |

**关键改动**：
- 合并"成长型思维"+"抗压韧性"→"韧性与成长心态"（argmax 永远分不开，合并后独占 94.4%）
- 领导力潜质加"决策担当/团队决策"（解决"决策力"漂移，60%→70%）
- 删除共享泛词："影响力""愿景"从领导力潜质/影响力构建双方删；"主动性"从自驱力/领导力潜质双方删
- **自驱力删"主动承担"加"自觉"**（2026-07-29 用户确认）：
  - 根因：自驱力定义是"内生动力驱动、无需外部督促"，核心是**内生、自觉**；"主动承担"是行为表现非内生动力
  - 层内正交：删"主动承担"消除与领导力潜质"承担leader"的"承担"词根抢票
  - 加"自觉"符合定义"无需外部督促"的内生特质
- **领导力潜质加"承担leader角色"**（保留原"承担leader"）：增强带人语境，拉回"自然承担leader角色"漏路由
- **接受的合理漏路由**（用户确认）：
  - "非职权影响力"→影响力构建（合理，影响力构建本含非职权维度）
  - "关键时刻能兜底"→韧性与成长心态（合理，兜底=抗压维度）
  - "主动承担责任"→领导力潜质（合理，符合定义调整后"主动承担"属领导担当而非自驱力）
  - 领导力潜质聚焦团队领导方向，不抢影响力/兜底

#### 最终模拟结果（2026-07-29 定稿）

| 标签 | 命中率 | 漏路由（均为合理归类）|
|------|--------|---------------------|
| 韧性与成长心态 | 34/36=94.4% | 视挑战为机会→战略眼光 |
| 领导力潜质 | 8/10=80% | 非职权影响力→影响力构建；关键时刻能兜底→韧性与成长心态 |
| 自驱力 | 7/8=87.5% | 主动承担责任→领导力潜质 |
| 开放性 | 6/6=100% | — |
| 战略眼光 | 6/6=100% | — |
| 跨界整合潜力 | 5/5=100% | — |
| 影响力构建 | 6/6=100% | — |
| **T3 总体** | **72/77=93.5%** | |

### 2.4 标签库数量变化
| Tier | 现状 | 改造后 | argmax 命中率 |
|------|------|--------|--------------|
| T1 | 99 | 99（不变，走旧路径）| 9.1%（argmax 不可行）|
| T2 | 13 | 13（选项 B：D 方案 + 三偏好）| **85.2%** |
| T3 | 9 | **7**（合并 2 个，E 重排 + 自驱力/领导力调整）| **93.5%** |
| **总体** | — | — | **78.4%**（T1 拖累，T1 优化后预期提升）|

---

## 三、代码改造方案

### 3.1 新增 `argmax_route()` 到 `utils/label_matching.py`

**职责**：concept → 全 tier 标签集 embedding argmax → top1 标签名

**接口设计**（待实现）：
```python
def argmax_route(
    concept: str,
    corpus: list[dict],          # 该 tier 的标签 corpus
    corpus_vecs: np.ndarray,     # 预编码的标签向量矩阵
    encode_fn: callable = None,
) -> dict:
    """concept 经 embedding argmax 路由到 tier 内 top1 标签。

    Returns:
        {
            "concept": str,
            "matched_label": str,
            "match_confidence": float,    # argmax cosine sim
            "mapping_source": "SOURCE_ARGMAX",
            "is_new_label": False,
            "rationale": "argmax route",
            "candidates_seen": len(corpus),
        }
    """
```

**契约要求**：
- 返回顶层 key 集合与 `_RERANK_ITEM_KEYS` 对齐（C1 对称，D3 返回格式对称）
- 不调 LLM，不调 cross-encoder（纯 embedding argmax）
- `mapping_source` 新增枚举 `SOURCE_ARGMAX`
- concept 为空/None → 走降级返回（参考 `_degrade_item`），保持 key 对称

### 3.2 改 `agents/profile_generation.py` 分流

**当前**：所有 tier 都走 recall+rerank（`_collect_rerank_items` → `rerank_cross_encoder`）

**改造后**：
- T1：维持旧路径（recall_top_k + rerank_cross_encoder + rerank_label_llm）
- T2/T3：改走 `argmax_route`（每 concept 独立 argmax 路由）

**实现要点**：
- Phase 0 预编码矩阵时，T2/T3 的矩阵用于 argmax（已有，复用 `encode_labels` 结果）
- `_collect_rerank_items` 内按 tier 分流：T1 收集进 rerank_items 走旧路径，T2/T3 直接调 `argmax_route` 生成结果项
- `_inject_mapping_fields` 对 argmax 项同样注入 data_lineage 等后处理字段（E 节错误路径等价性：argmax 路径不得绕过成功路径后处理管线）

### 3.3 `config.py` 加常量

```python
# argmax 路由配置
ARGMAX_TIERS = ["T2", "T3"]          # 走 argmax 的 tier（T1 维持旧路径）
ARGMAX_CONFIDENCE_THRESHOLD = 0.0    # 纯 argmax 无兜底，阈值仅用于记录不用于分流
```

**D2 配置单一来源**：`ARGMAX_TIERS` 在 config.py 定义一次，profile_generation.py 和 verify 脚本都 import 此常量，禁止重复硬编码。

### 3.4 改造 `scripts/verify_argmax_routing.py`

**当前**：用脚本内 `OVERRIDES`/`MERGE_MAP_T3`/`NEW_LABELS_T3` 双源（脚本常量 vs 标签库 json）

**改造后**：
- 删除 `OVERRIDES`/`MERGE_MAP_T3`/`MERGE_DEF_T3`/`NEW_LABELS_T2`/`NEW_LABELS_T3` 常量
- 改为读 `data/standard_label_library_v1.json`（落地后的 D+E 方案标签库）
- `run_e()` 重命名为 `run_final()`，读 json 跑 argmax 验证
- 保留 `TEST_CASES` + `EXTRA_TEST_CASES` 作为测试集

### 3.5 同步 GT 文件

`data/experiment/ground_truth_5.json`：
- T3 GT 标签：`成长型思维`/`抗压韧性` → `韧性与成长心态`
- T2 GT 标签：维持不变（A2 砍了尽责性，T2 GT 无需改）
- T1 GT 标签：维持不变（T1 优化是独立任务，本次不动 T1 GT）
- `_meta.status` 保留 `[AWAITING_USER_REVIEW]`（T1 GT 命名问题如"项目管理"vs"项目管理知识体系"待 T1 优化时一并审）

---

## 四、验证方案（C2 闸门）

### 4.1 单元测试
新增 `tests/test_argmax_route.py`：
- `TestArgmaxRoute`：
  - test_argmax_returns_symmetric_keys（C1 顶层 key 对称）
  - test_argmax_empty_concept_degrades_gracefully（空 concept 降级）
  - test_argmax_none_concept_type_guard（G 节类型守卫）
  - test_argmax_t3_merged_label_routes_correctly（韧性与成长心态合并后路由）
  - test_argmax_confidence_is_cosine_sim（置信度=argmax sim）

### 4.2 端到端测试
```
python scripts/experiment_embedding_vs_llm.py \
  --from-phase1 data/intermediate/phase1_output.json \
  --ground-truth data/experiment/ground_truth_5.json
```
**验收标准**：
- T3 recall@GT ≥ 85%（argmax 93.5% 模拟，端到端留 8pp 余量）
- T2 recall@GT ≥ 75%（argmax 83.3% 模拟，端到端留 8pp 余量）
- T1 recall@GT 维持现状 25-37.5%（不动）
- 整体 recall@GT ≥ 70%（T2/T3 改善后，T1 短板待后续优化）

### 4.3 对抗审查
对 `argmax_route` + `profile_generation` 分流逻辑做边界推演：
- concept 为空/None/非 str（类型守卫）
- corpus 为空 list
- corpus_vecs 维度与 concept 向量不匹配
- T2/T3 concept 数量极端（0 个 / 50 个）
- argmax sim 极低（<0.3）时是否需要标记（当前无兜底，仅记录）

### 4.4 闸门流程
1. 改核心逻辑后 → progress.md 追加 `[AWAITING_VERIFY]`（标注文件+变更摘要）
2. 跑 `python -m pytest tests/ -v` 全绿
3. 对抗审查逐行边界推演
4. 通过 → `[AWAITING_VERIFY]` 改 `[VERIFIED]`
5. 失败 → `git checkout` 回退，禁止修补式勉强通过

---

## 五、Tracking 三件套同步（commit 前）

落地完成后、commit 前必须同步：
1. **progress.md**：记录本次变更摘要 + C2 闸门验证结果
2. **docs/task-plan.md**：更新任务状态（argmax 落地完成、T1 优化待启动）
3. **docs/change-log.md**：记录文件变更明细 + 根因 + 决策依据

---

## 六、不做的事（本次落地范围外）

1. **T1 优化**：T1 旧路径 25-37.5% 召回，根因有三类（见 §七），需独立诊断，本次不动
2. **GT 命名规范化**：T1 GT 中"项目管理"vs标签库"项目管理知识体系"等命名不一致问题，待 T1 优化时一并审
3. **LLM 兜底**：T2/T3 纯 argmax 无兜底，若端到端 recall 不足再议是否加 LLM 兜底（当前决策是不加）
4. **keywords 调参**：已触顶，再调是过拟合（路径 A 失败教训）

---

## 七、T1 漏失根因记录（待 T1 优化时处理）

3 员工实测 T1 漏失链路分析：

| 根因 | 案例 | 阶段 | 占比 |
|------|------|------|------|
| **① LLM 抽取漏失** | JZ0001 质量工程、JZ0004 嵌入式开发/数据分析 | Phase1 抽取 | ~4/8（最严重）|
| **② embedding 纠正改错** | 智能制造→物联网(sim0.64)、Java开发→Android开发(sim0.73) | Path A 纠正 | ~2/8 |
| **③ GT 命名不一致** | GT"项目管理" vs 标签库"项目管理知识体系" | GT 口径 | ~1/8 |

**T1 优化方向（待用户想好方法后启动）**：
- 根因①：phase1 prompt 调整（为什么质量工程/嵌入式开发没抽出来？prompt 引导不足还是 LLM 能力问题）
- 根因②：低置信度纠正的硬改问题（sim<0.7 是否应保留 LLM proposed 而非纠正，对应 Plan B 决策）
- 根因③：GT 命名规范化（与标签库对齐）

---

## 八、决策时间线

| 日期 | 决策 |
|------|------|
| 2026-07-27 | 启动 argmax 框架规划，确认 D 方案为当前最优（T2=83%/T3=81%）|
| 2026-07-29 | E 方案层内正交重排模拟：T3=92.2%（+决策担当后 93.5%），T2 因加尽责性退步至 77.4% |
| 2026-07-29 | A2 方案：砍掉尽责性，T2 回 D 方案 13 标签=83.3%，T3=E 重排 7 标签=93.5% |
| 2026-07-29 | 实测 3 员工旧路径分层 recall：T1=25-37.5%（短板）、T2=85.7%、T3=20-40% |
| 2026-07-29 | 用户确认：T2/T3 都走 argmax，失败案例可接受（部分是 GT 不准）；T1 维持旧路径，优化作为独立任务；本次只写策划案不落地 |

---

## 九、待办（[PAUSED]）

- [ ] 用户想好 T1 优化方法后，解除暂停，按本策划案 §三 落地
- [ ] 落地顺序：json+GT → argmax_route → profile_generation 分流 → config 常量 → verify 脚本读 json → 测试 → 闸门 → tracking 三件套
