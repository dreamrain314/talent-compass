# 备选池（Candidate Pool）对接框架设计

> **更新日期：** 2026-07-26
> **依据：** `开题报告/五层匹配评分体系细化方案_2026-07-24.md` §5 备选池设计
> **当前代码状态：** BasicFilter 完成，H1Filter 未实现，Agent ①-④ 未实现

---

## 一、备选池在系统中的定位

### 五层匹配架构中的位置

```
H0Filter（BasicFilter — 现有，不动）
  │  required 不满足 → ❌ 直接排除，不进备选池
  │  preferred 不满足 → 标记继续
  ▼
H1Filter（新建）
  │  required 不满足 → ❌ 直接排除，不进备选池
  │  preferred 不满足 → 标记继续
  ▼
Agent① 数据理解 → Agent② 画像生成 / Agent③ 岗位分析（并行）
  ▼
Agent④ 匹配解释
  │  ① 必需能力检查（T1 required 技能：员工 SFIA < 要求 SFIA）
  │     → 全部达标 → 主推荐池（按最终排序分降序）
  │     → 有任一不达标 → 备选池（按综合推荐指数降序）
  │
  │  ② T1 评分（SFIA_diff × w_i）
  │  ③ T2 评分（SFIA_diff × w_i，双源融合）
  │  ④ T3 评分（代理指标聚合）
  │  ⑤ 优先项加分
  │  ⑥ 最终排序分 = T1×W1 + T2×W2 + T3×W3 + 加分
  │
  │  ⑦ 备选池：四象限标记 + 综合推荐指数 + 主池参考排名
```

### 与旧设计的核心区别（2026-07-26 更新）

| 设计项 | 旧（2026-07-26 前） | 新（2026-07-26） |
|--------|-------------------|----------------|
| 入池条件 | H1/T0 软条件失败 + 胜任力≥阈值 | **T1 required 技能不达标**（H0/H1 required 直接排除，不进池） |
| 池结构 | 高潜备选/普通备选 二分类 | **四象限 A/B/C/D**（⭐高价值/⚡偏科/接近达标/差距大） |
| 排序方式 | 阈值分档（≥100%/≥80%） | **综合推荐指数**（deficit 0.40 + T1 0.25 + T3 0.25 + T2 0.10） |
| 主池关系 | 无 | **主池参考排名** |
| Demo 期 | 未定义 | **仅标记"考虑录用"，不做自动排序变更** |

---

## 二、备选池判定逻辑

### 2.1 入池条件

```
进入备选池的唯一条件：
  ① 已通过 H0Filter + H1Filter（required 全部满足 or preferred 被标记）
  ② Agent④ 必需能力检查中，有 ≥1 项 T1 required 技能：
       员工 SFIA < 要求 SFIA

不进入备选池的情况：
  · H0/H1 required 不满足 → ❌ 直接排除
  · 所有 T1 required 技能全部达标 → ✅ 主推荐池
```

### 2.2 四象限矩阵

```
                    T1 得分（在 required 技能上的表现）
                 低 ←──────────────→ 高
              ┌─────────────────────────────────┐
      小      │  B：差距小·T1低               A：差距小·T1高  │
              │  "差一点就达标"              ⭐"高价值候选人"  │
    ↑         │  培训成本低                  建议优先考虑      │
    差         │  ─────────────              ═══════════      │
    距         │                                               │
    ↓         ├─────────────────────────────────┤
      大      │  D：差距大·T1低               C：差距大·T1高  │
              │  "全面不匹配"                 ⚡"偏科天才"    │
              │  培训成本高                  需针对性补差      │
              └─────────────────────────────────┘
```

**象限判定规则：**

| 象限 | 标记 | 条件 | 含义 |
|------|------|------|------|
| A | ⭐ 高价值候选人 | deficit ≤ 2 且 T1 ≥ 70 | 整体优秀，仅微小差距，建议优先考虑 |
| B | 接近达标 | deficit ≤ 2 且 T1 < 70 | 差一点就达标，培训成本低 |
| C | ⚡ 偏科天才 | deficit > 2 且 T1 ≥ 70 | 专业很强但部分技能缺口大，需针对性补差 |
| D | 差距较大 | deficit > 2 且 T1 < 70 | 全面不匹配，培训成本高 |

### 2.3 综合推荐指数

```
综合推荐指数 = 0.40 × (1 - deficit_normalized)
              + 0.25 × (T1/100)
              + 0.25 × (T3/100)
              + 0.10 × (T2/100)

其中：
  deficit = Σ max(0, 要求SFIA - 员工SFIA)   ← 只加不达标部分
  deficit_normalized = min(deficit / 5, 1)   ← 归一化（假设最大合理差距为5）
  T1/100 = 专业能力得分（归一化）
  T2/100 = 行为能力得分（归一化）
  T3/100 = 发展潜力得分（归一化）
```

**权重分配逻辑：**

| 维度 | 权重 | 理由 |
|------|:----:|------|
| deficit 差距 | 0.40 | 备选池的核心原因，差距越小越优先 |
| T1 专业能力 | 0.25 | 整体专业水平，体现"这个人整体很强" |
| T3 发展潜力 | 0.25 | 补上差距的可能性，体现"这个人值不值得培养" |
| T2 行为能力 | 0.10 | 辅助参考，不决定"是否值得拉回来" |

### 2.4 主池参考排名

```
备选池候选人的"主池参考排名"：
  = 用该候选人的实际 SFIA 等级照常计算 T1/T2/T3 得分
  = 用同样公式算出"假设排序分"（T1×W1 + T2×W2 + T3×W3 + 加分）
  = 插入主池排名中，看能排在第几

公式与主池完全一致，不修改公式本身。
```

---

## 三、数据结构设计

### 3.1 备选池条目

```python
@dataclass
class CandidatePoolItem:
    employee_id: str                # 员工ID
    employee_info: dict             # 13字段基础信息
    # 差距信息
    deficit: int                    # 总差距（Σ max(0, 要求-员工)）
    deficit_details: list[dict]     # 差距详情：[{"skill":"Docker","required":4,"actual":3,"gap":1}]
    # 评分
    t1_score: float                 # T1 专业能力得分（0-100）
    t2_score: float                 # T2 行为能力得分（0-100）
    t3_score: float                 # T3 发展潜力得分（0-100）
    bonus_score: float              # 优先项加分
    hypothetical_rank: int          # 主池参考排名（如果达标会在主池排第几）
    # 象限
    quadrant: str                   # "A" | "B" | "C" | "D"
    quadrant_label: str             # "高价值候选人" | "接近达标" | "偏科天才" | "差距较大"
    comprehensive_score: float      # 综合推荐指数（0-1）
    # 状态
    marked_consider: bool           # HR 是否标记"考虑录用"（Demo 期仅标记，不做排序变更）
    improvement_suggestions: list[str]  # 改善建议
    created_at: str                 # 入池时间
```

### 3.2 备选池容器

```python
@dataclass
class CandidatePool:
    pool_id: str                    # 池ID（关联岗位需求）
    job_requirements: dict          # 关联的岗位需求摘要
    primary_candidates: list[dict]  # 主推荐池（Top-N，按最终排序分降序）
    alternative_candidates: list[CandidatePoolItem]  # 备选池（按综合推荐指数降序）
    created_at: str
    updated_at: str
```

### 3.3 排序方式枚举

```python
class SortMode(Enum):
    COMPREHENSIVE = "comprehensive"   # 综合推荐指数（默认）
    DEFICIT = "deficit"               # 差距最小
    T1_HIGHEST = "t1_highest"         # T1 最高
    T3_HIGHEST = "t3_highest"         # T3 最高
    MANUAL = "manual"                 # 手动拖拽
```

---

## 四、与当前代码的对接点

### 对接点 1：Agent④ 备选池判定

**文件**：`agents/agent_04_match.py`（待实现）

**逻辑**：

```python
# 伪代码：Agent④ 备选池判定
def determine_pool(candidate, job_requirements):
    # 1. 必需能力检查
    deficits = []
    for skill in job_requirements.required_skills:
        if candidate.sfia_level(skill) < job_requirements.sfia_required(skill):
            deficits.append({
                "skill": skill,
                "required": job_requirements.sfia_required(skill),
                "actual": candidate.sfia_level(skill),
                "gap": job_requirements.sfia_required(skill) - candidate.sfia_level(skill)
            })
    
    if not deficits:
        # 全部达标 → 主推荐池
        return {"pool": "primary", "score": calculate_final_score(candidate)}
    
    # 2. 有短板 → 备选池
    deficit = sum(d["gap"] for d in deficits)
    deficit_norm = min(deficit / 5, 1)
    t1, t2, t3 = calculate_scores(candidate)
    
    comprehensive = (
        0.40 * (1 - deficit_norm) +
        0.25 * (t1 / 100) +
        0.25 * (t3 / 100) +
        0.10 * (t2 / 100)
    )
    
    # 3. 象限判定
    if deficit <= 2 and t1 >= 70:
        quadrant, label = "A", "⭐ 高价值候选人"
    elif deficit <= 2 and t1 < 70:
        quadrant, label = "B", "接近达标"
    elif deficit > 2 and t1 >= 70:
        quadrant, label = "C", "⚡ 偏科天才"
    else:
        quadrant, label = "D", "差距较大"
    
    # 4. 主池参考排名（需要主池结果）
    hypothetical_score = calculate_final_score(candidate)  # 用实际 SFIA 算
    
    return {
        "pool": "alternative",
        "deficit": deficit,
        "deficit_details": deficits,
        "t1_score": t1,
        "t2_score": t2,
        "t3_score": t3,
        "comprehensive_score": comprehensive,
        "quadrant": quadrant,
        "quadrant_label": label,
        "hypothetical_score": hypothetical_score
    }
```

### 对接点 2：PipelineRunner → 主池+备选池数据传递

**文件**：`orchestrator/pipeline.py`

**数据流**：

```
PipelineRunner.run(initial_data)
  → BasicFilter → H1Filter → 过滤后候选人集合
  → Agent① 数据理解 → 融合数据
  → Agent② 画像生成（并行）→ 员工画像
  → Agent③ 岗位分析（并行）→ 岗位画像
  → Agent④ 匹配解释
    → 输出：
      {
        "primary_pool": [...],       # 主推荐池（按最终排序分降序）
        "alternative_pool": [...],   # 备选池（按综合推荐指数降序）
        "pool_metadata": {
          "primary_threshold": ...,   # 主池最低分
          "total_evaluated": N,
          "primary_count": M,
          "alternative_count": K
        }
      }
```

### 对接点 3：Streamlit UI → 备选池展示

**文件**：`ui/app.py`

**UI 布局**：

```
Step 6 推荐结果（当前）：
  ┌─ 推荐结果 ──────────────────────────────────┐
  │  排名 | 姓名 | 总分 | 匹配详情               │
  │  1    | 张三  | 92   | ...                   │
  │  ...                                        │
  └──────────────────────────────────────────────┘

Step 6 推荐结果（扩展后）：
  ┌─ Tab: 主推荐池(20) ── Tab: 备选池(12) ───┐
  │                                            │
  │  [排序方式 ▼] 综合推荐 | 差距最小 | T1最高  │
  │  [筛选象限 ▼] ☑ A ☑ B ☑ C ☑ D            │
  │                                            │
  │  ════════════════════════════════════════  │
  │  ⭐ 排名1 │ 甲 │ 象限A                     │
  │    综合:0.82 │ 差距: Docker L3→L4(-1)      │
  │    主池参考: 第3/20                         │
  │    建议: 微小差距，建议优先联系              │
  │  ────────────────────────────────────────  │
  │  排名2 │ 乙 │ 象限B                         │
  │    综合:0.45 │ 差距: Python(-2), SQL(-1)    │
  │    主池参考: 第15/20                        │
  │  ════════════════════════════════════════  │
  │                                            │
  │  [转为人工评估] [发送补差培训邀请] [查看画像]  │
  └────────────────────────────────────────────┘
```

---

## 五、Demo 期简化规则

| 功能 | Demo 期行为 |
|------|-----------|
| 标记"考虑录用" | 仅打标记，**不做任何排序/池的变更** |
| 备选池→主池联动 | 不实现 |
| 被标记者的排序变化 | 不变化 |
| 后续版本 | 加入"筛除已标记+重新排序"功能 |

---

## 六、分阶段实现路径

### 阶段 1：Agent④ 备选池判定（第 3 周，08.06）

**目标**：在 Agent④ 中实现四象限 + 综合推荐指数逻辑

| 文件 | 变更 | 说明 |
|------|------|------|
| `agents/agent_04_match.py` | 实现 `determine_pool()` 方法 | 必需能力检查 + 四象限判定 + 综合推荐指数 |
| `agents/agent_04_match.py` | 实现 `calculate_hypothetical_rank()` | 主池参考排名计算 |

### 阶段 2：UI 展示（第 3 周，08.07-08.09）

**目标**：备选池在 Streamlit 中可交互展示

| 文件 | 变更 | 说明 |
|------|------|------|
| `ui/app.py` | Step 6 新增"备选池"标签页 | 展示备选池列表 + 排序/筛选控件 |
| `ui/app.py` | 每个备选池条目展示 | 差距详情 + 主池参考排名 + 象限标记 |

### 阶段 3：Demo 验证（第 3-4 周）

**目标**：用 7 个画像验证备选池逻辑正确性

| 验证点 | 方法 | 预期 |
|--------|------|------|
| 画像④（行为短板）进备选池 | ④ 的 T1 必需技能不达标 | 应进入备选池，象限标记正确 |
| 画像⑥（证书不符）不进备选池 | ⑥ 被 H1Filter 排除 | 应直接排除，不入池 |
| 画像⑦（年限不符）不进备选池 | ⑦ 被 H0Filter 排除 | 应直接排除，不入池 |
| 主池参考排名正确 | ④ 的主池参考排名 | 应显示"如果在主池排第 X" |
| 排序切换正确 | 切换综合/差距/T1/T3 | 排序应合理变化 |

---

## 七、与旧代码的兼容说明

### 已废弃的旧设计（2026-07-26 前，不删除但不再使用）

- ~~`CandidatePool.pool_level`~~ → 改用 `quadrant` 字段
- ~~`CandidatePool.high_potential / normal` 二分类~~ → 改用四象限
- ~~`CandidatePool.failed_layers`~~ → 改用 `deficit_details`（仅追踪 T1 required 技能差距）
- ~~阈值分档（≥100%/≥80%）~~ → 改用综合推荐指数排序

### 向后兼容

- BasicFilter 的 `filtered_out_employees` 输出（原阶段 1 工作）**保留**，供 UI Step 2 展示"被过滤员工"信息
- 但该数据 **不再用于备选池判定**（备选池只从通过 H0+H1 的候选人中产生）

---

*——备选池对接框架设计文档结束——*
*设计依据：五层匹配评分体系细化方案 §5（2026-07-26 更新）*