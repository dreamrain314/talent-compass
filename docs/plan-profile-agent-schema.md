# Agent② 画像生成 — 输出 JSON Schema 设计

> **状态:** [定稿] — §6 决策点已用户确认 (2026-07-26)
> **日期:** 2026-07-26
> **对应任务:** task-plan 2.1.11（第 2 周准备）
> **依据:** `开题报告/多Agent协作完整行为逻辑与实现方法.md` 步骤 2.1-2.9 + `五层匹配评分体系细化方案_2026-07-24.md` §2 评分公式 + `data/standard_label_library_v1.json` 标签库

---

## 1. 在管线中的位置

```
Agent① 融合JSON ─→ Agent② 画像生成 ─→ Agent③ 岗位分析 ─→ Agent④ 匹配解释
(员工基础+360+摘要)   (员工侧画像)      (岗位侧要求+权重)   (SFIA_diff+排序分)
```

- **输入**: Agent① 融合 JSON（员工基础数据 + 360 加权得分 + 文本摘要 + certificates）
- **输出**: 员工画像 JSON（**H0 + H1 + T1/T2/T3** 标签 + 成长曲线 + 大五；**T0 已融合进 T1**，五层方案 §0）
- **下游契约**: Agent③ 产出**要求侧** SFIA/权重；Agent④ 用 Agent② 的**员工侧** sfia_level + Agent③ 的**要求侧** sfia_required 算 `SFIA_diff`

**关键边界（防混淆）**: Agent② 只产出**员工 SFIA 等级**（0-7），**不算最终 T1 得分**——T1 得分公式 `Σ w_i × SFIA_diff` 是 Agent④ 的职责（需要 Agent③ 的要求侧 SFIA）。

---

## 2. 输出 Schema（包装在 BaseAgent 契约里，C1 对称）

```json
{
  "status": "success|degraded|error",
  "data": {
    "employee_id": "JZ0001",
    "h0_profile": {
      "age": 39,
      "political_status": "共青团员",
      "major": "人工智能",
      "years_of_service": 16,
      "current_level": "P6"
    },
    "h1_credentials": ["PMP", "系统架构设计师"],
    "t1_professional": [
      {
        "category": "skill",
        "standard_label": "Java开发",
        "free_labels": ["Java微服务", "Spring体系后端开发"],
        "sfia_level": 5,
        "ability_score": 71,
        "confidence": 0.85,
        "evidence": [
          {"source": "2025项目:智慧园区平台", "text": "负责Java微服务核心模块开发..."},
          {"source": "2025绩效评语", "text": "主导...攻克Java微服务技术难题"}
        ],
        "mapping_similarity": 0.92
      },
      {
        "category": "tool",
        "standard_label": "Spring Cloud",
        "free_labels": ["Spring Cloud"],
        "sfia_level": 4,
        "ability_score": 65,
        "confidence": 0.80,
        "evidence": [{"source": "2025项目:智慧园区平台", "text": "...Spring Cloud..."}],
        "mapping_similarity": 0.88
      },
      {
        "category": "domain",
        "standard_label": "智能制造",
        "free_labels": ["工业互联网"],
        "sfia_level": 3,
        "ability_score": 55,
        "confidence": 0.70,
        "evidence": [{"source": "项目经历", "text": "...智能制造..."}],
        "mapping_similarity": 0.75
      }
    ],
    "t2_behavioral": [
      {
        "standard_label": "跨部门协调",
        "free_labels": ["跨部门沟通顺畅"],
        "ability_score": 80,
        "confidence": 0.78,
        "evidence": [{"source": "2025绩效评语", "text": "..."}]
      }
    ],
    "t3_potential": [
      {
        "standard_label": "领导力潜质",
        "free_labels": ["有带团队潜力"],
        "ability_score": 65,
        "confidence": 0.62,
        "evidence": [{"source": "360下属评价", "text": "给予充分信任..."}],
        "growth_data": {"slope": 0.15, "trend": "上升", "years": [2024,2025,2026], "scores": [60,65,72]}
      }
    ],
    "big_five": {
      "openness": 72,
      "conscientiousness": 80,
      "extraversion": 55,
      "agreeableness": 68,
      "neuroticism": 40
    },
    "growth_curve": {
      "years": [2024, 2025, 2026],
      "performance_grades": ["B", "A", "A"],
      "composite_scores": [68, 78, 85],
      "slope": 8.5,
      "trend": "快速上升"
    },
    "labels_pending_review": ["抗压韧性"],
    "summary": "资深Java后端工程师，微服务架构能力突出，跨部门协调评价高，近3年绩效快速上升，展现领导力潜质。"
  },
  "metadata": {
    "agent_name": "ProfileGeneration",
    "agent_version": "1.0",
    "duration_ms": 4500,
    "trace_id": "TC-20260728-...",
    "error": null,
    "data_lineage": {
      "model": "DeepSeek-V4-Pro",
      "timestamp": "2026-07-28T10:30:00",
      "audit_status": "auto",
      "label_library_version": "1.0",
      "input_source": "Agent①融合JSON"
    }
  }
}
```

**降级路径（degraded）**: 当 LLM 调用失败/截断时，`status="degraded"`，`data` 用确定性降级值（从原文派生的关键词标签 + 置信度 0.3 + 空 evidence），`metadata.error` 记录原因。**禁止"再调一次 LLM 换 prompt"**（D6/[[root-cause-llm-fallback-cascade]]）。

---

## 3. 字段说明

| 字段 | 类型 | 说明 | 来源步骤 |
|---|---|---|---|
| `status` | str | success/degraded/error（C1 对称） | — |
| `data.employee_id` | str | 员工 ID | 输入透传 |
| `data.h0_profile` | obj | **H0 结构化硬条件**——age/political_status/major/years_of_service/current_level（透传 employees.csv，供 Agent④ 算 H0 preferred 加分） | 输入透传 |
| `data.h1_credentials` | list[str] | H1 资质档案——certificates 字段 `;` 分隔解析 | 2.1a |
| `data.t1_professional` | list[obj] | **T1 专业能力层（原 T0+T1 融合，五层方案 §0）**——含 skill/tool/domain/knowledge 四类 | 2.1a/2.1b/2.5/2.7 |
| └ `category` | str | 能力项类型：`skill`(技能)/`tool`(工具)/`domain`(领域)/`knowledge`(知识)，区分原 T0/T1 来源 | — |
| └ `standard_label` | str | 标准标签名（skill←`standard_label_library_v1.json`；tool/domain/knowledge←`t0_registries.json`） | 2.7 映射 |
| └ `free_labels` | list[str] | LLM 抽取的自由文本标签（映射前） | 2.1b 抽取 |
| └ `sfia_level` | int 0-7 | **员工侧 SFIA 等级**（Agent④ 算差值用） | 2.5 评定 |
| └ `ability_score` | int 0-100 | 标签能力评分（给 HR 直观展示） | 2.5 评定 |
| └ `confidence` | float 0-1 | 置信度，<0.6 → 进 `labels_pending_review` | 2.5 评定 |
| └ `evidence` | list[{source,text}] | 证据锚点（可追溯到原文） | 2.5 锚点 |
| └ `mapping_similarity` | float 0-1 | embedding 相似度（标准映射置信） | 2.7 映射 |
| `data.t2_behavioral` | list[obj] | T2 行为能力标签（无 SFIA，用 ability_score） | 2.1b/2.5 |
| `data.t3_potential` | list[obj] | T3 发展潜力标签（含 growth_data） | 2.4/2.5 |
| └ `growth_data` | obj | 单标签成长数据 {slope, trend, years, scores} | 2.6 建模 |
| `data.big_five` | obj | 大五人格 5 维度 0-100（T3 推断依据） | 2.4 推断 |
| `data.growth_curve` | obj | 绩效成长曲线（步骤 2.6，员工级） | 2.6 建模 |
| `data.labels_pending_review` | list[str] | 置信度<0.6 的标签（待 HR 审核） | 2.5 汇总 |
| `data.summary` | str | 员工资深画像摘要 | 2.9 汇总 |
| `metadata` | obj | BaseAgent 契约（C2 基类注入 data_lineage） | — |

---

## 4. 设计决策记录

### D1: T1 用 SFIA 0-7（含原 T0 工具/领域/知识），T2/T3 用 0-100 分（不混用 SFIA）
- **依据（T0+T1 融合）**: 五层方案 §0"T0+T1 融合层整体命名为 T1"——原 T0（工具/领域/知识）+ 原 T1（技术技能）**统一用 SFIA 0-7**，用 `category` 字段区分来源（不再单独输出 t0_explicit）。
- **依据（T2/T3 不用 SFIA）**: SFIA = Skills Framework for Information Age，针对 IT/数字技能。T2 行为能力（跨部门协调/团队管理）和 T3 潜力（领导力潜质/成长型思维）不在 SFIA 范畴，强套会失真。
- **T1 双指标**: `sfia_level`（给 Agent④ 算差值）+ `ability_score`（给 HR 直观）。

### D2: ability_score 与 sfia_level 双字段
- `ability_score` (0-100): LLM 评定的标签能力强度，连续值，给 HR 直观展示 + 排序参考。
- `sfia_level` (0-7): 离散标准化等级，给 Agent④ 算 `SFIA_diff = max(min(员工-要求,+2),-7)/7`。
- 两者**相关但独立**——SFIA 离散、ability_score 连续；映射关系不硬编码（避免 D2 违规），由 LLM 同时评定。

### D3: 大五人格独立输出（big_five 字段）
- T3 标签里含大五相关标签（开放性/尽责性），但 5 维度分数独立输出，作为 T3 推断的**可审计依据**（BEI 追问会引用）。
- 范围 0-100（与 ability_score 对齐，便于 HR 滑动条调权时统一尺度）。

### D4: Demo 期跳过聚类（步骤 2.8）
- 五层方案"Demo 期降级等权兜底"，聚类可视化在第四阶段（12 强赛，task-plan 4.1）。
- Schema **不含** `cluster_id`/`cluster_label`；第四阶段扩展时再加（向前兼容：新增字段不破坏旧消费者）。

### D5: labels_pending_review 收集低置信度标签
- 行为逻辑文档明确："置信度<0.6 的标签标记'待人工审核'，不直接用于匹配"。
- 单独收集到顶层 `labels_pending_review`（list[str] of standard_label），HR 界面集中展示。

### D6: evidence 证据锚点格式
- 行为逻辑文档定义: `{"标签":"...","证据":[{"来源":"...","原文":"..."}]}`。
- 本 Schema 扁平化为 `evidence: [{source, text}]`（标签名在外层 standard_label，不重复），下游 Agent④ 生成证据链时重组。

### D7: growth_curve 与 t3.growth_data 双层
- `growth_curve`（员工级）: 绩效时间序列 + 综合分斜率，用于 T3 整体趋势判断。
- `t3_potential[].growth_data`（标签级）: 单个 T3 标签的成长数据（如"领导力潜质"的成长斜率）。
- 两者数据源不同：员工级用绩效分，标签级用该维度 360/证据时间序列。

---

## 5. 与上下游契约

### 上游（Agent① 输入消费）
- 员工基础数据（employees.csv 字段）+ 360 加权得分（Agent① 输出）+ 文本摘要（llm_summarizer）
- H0 字段（age/political_status/major/years_of_service/current_level）→ `h0_profile`（透传，供 Agent④ 算 H0 preferred 加分）
- `certificates` 字段 → `h1_credentials`（`;` 分隔 → list）
- T0 词典（`t0_registries.json` 工具/领域/知识）+ T1 标签库（`standard_label_library_v1.json` T1_专业能力）→ `t1_professional`（`category` 区分来源，统一 SFIA）

### 下游（Agent③④ 消费）
| 消费者 | 用 Agent② 哪些字段 | 用途 |
|---|---|---|
| Agent③ | t1_professional[].standard_label | 对照岗位需求提取要求侧 SFIA |
| Agent③ | h0_profile, h1_credentials | 提取岗位 H0 要求（age 范围/政治面貌/专业/年限/职级）+ H1 要求证书 |
| Agent④ | t1_professional[].sfia_level | 算 `SFIA_diff = max(min(员工-要求,+2),-7)/7` → T1 得分 |
| Agent④ | h0_profile, h1_credentials | 算 H0/H1 preferred 加分（满足优先项数 × k_h0/k_h1，二元条件，五层方案 §2.4） |
| Agent④ | t2_behavioral[].ability_score, t3_potential[].ability_score | T2/T3 层得分 |
| Agent④ | growth_curve, big_five | T3 综合判断 + BEI 追问依据 |
| Agent④ | evidence[] | 生成证据链 + 反事实解释 |
| Agent④ | labels_pending_review | 跳过这些标签的匹配（置信度不足） |

---

## 6. 决策点定稿（用户 2026-07-26 确认）

| 决策 | 结论 | 备注 |
|---|---|---|
| **D2** T1 评分字段 | **双字段** `ability_score`(0-100 整数) + `sfia_level`(0-7) | LLM 同时评定；ability_score 给 HR 直观+排序，sfia_level 给 Agent④ 算 SFIA_diff |
| **大五范围** | **0-100** | 与 ability_score 对齐，HR 滑动条统一尺度 |
| **summary 字段** | **保留** | LLM 仅基于已抽标签生成（约束：不引入标签外信息，防幻觉） |
| **D4** 聚类 | **Demo 期跳过** | 第四阶段（12 强赛，task-plan 4.1）扩展，Schema 不含 cluster 字段（向前兼容） |
| **ability_score 粒度** | **整数 0-100** | 与 performance_grade/360 score 等整数尺度一致 |

---

## 7. 实现时的 config 常量（待加 config.py，D2 单一来源）

| 常量 | 值 | 消费者 |
|---|---|---|
| `SFIA_MAX_LEVEL` | 7 | Agent② sfia_level 上限 + Agent④ SFIA_diff 分母 |
| `SFIA_CAP_EXCESS` | 2 | Agent④ SFIA_diff 上限（cap+2，文献 Ge & Sekiguchi 2026） |
| `LABEL_CONFIDENCE_THRESHOLD` | 0.6 | Agent② labels_pending_review 收集阈值 |
| `ABILITY_SCORE_MIN/MAX` | 0/100 | Agent② ability_score 范围 |
| `BIG_FIVE_DIMENSIONS` | ["openness","conscientiousness","extraversion","agreeableness","neuroticism"] | Agent② big_five 字段 |
| `LABEL_LIBRARY_VERSION` | "1.0" | Agent② metadata.data_lineage.label_library_version |

> 实现代码时从 config import，禁止在 agents/profile_generation.py 内联硬编码（D2/F1）。

---

## 8. Embedding 框架选型 + 阈值标定（Demo 验证，2026-07-26）

### 8.1 框架决策
- **选型**: `fastembed` + `BAAI/bge-small-zh-v1.5`
- **理由**:
  - 离线可用（首次下载 ~95MB 后无网络也能跑，竞赛现场稳）
  - ONNX 后端，无 torch 依赖（~几十 MB vs sentence-transformers ~2GB）
  - bge-small-zh 是中文专用 embedding 模型，标签库为中文
  - DeepSeek/Paratera 不提供 embedding API，OpenAI key 未配置 → 本地是唯一可行方案
- **验证脚本**: `scripts/embedding_demo.py`（流程跑通，6 查询 top-1 排序 **6/6 命中预期**）

### 8.2 ⚠ 阈值标定发现（07.31 实现前必须解决）
- **问题**: 原四档阈值 `0.6/0.75/0.85/0.95` 是为 OpenAI embedding 标定；bge-small-zh 相似度绝对值普遍偏低（top-1 多在 0.59-0.69），几乎全部落入 `<0.60` pending。
- **现象**: 词汇高度重叠（"Java微服务后端"→"Java开发" sim=0.8962）sim 高；语义相近但用词不同（"带团队打硬仗"→"团队管理" sim=0.5973）sim 低。
- **07.31 实现时的两个选项**:
  - 选项 A: 为 bge 重新标定阈值（如 `0.50/0.60/0.70/0.85`）—— 需用真实员工标签数据标定
  - 选项 B: 改用 `top-1 + 相对 margin`（top1-top2 > Δ）判定 —— 不依赖绝对值，更鲁棒
- **建议**: 选项 B（margin 判定）+ 选项 A（绝对下限兜底）混合，07.31 用真实员工数据验证后定稿。

### 8.3 实现路径（07.31 Agent② 步骤 2.7）
- 复用 `scripts/embedding_demo.py` 的 `load_label_corpus` + `cosine_sim` 逻辑
- 抽到 `utils/label_embedding.py`（D2 单一来源，供 Agent② + UI 复用）
- `config.py` 加 `EMBEDDING_MODEL_NAME = "BAAI/bge-small-zh-v1.5"` + 阈值常量（标定后）
- 模型单例缓存（首次加载 ~2s，避免每次 Agent② 调用重新加载 — F4 单例每次访问检查配置变化）
