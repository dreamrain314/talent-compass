# 备选池（Candidate Pool）对接框架设计

> 基于设计文档 `多Agent协作完整行为逻辑与实现方法.md` 第76-85行、第632-634行
> 当前代码状态：BasicFilter 完成，Agent ①-④ 未实现，PipelineRunner 完成

---

## 一、备选池在系统中的定位

### 五层匹配架构中的位置

```
H0(硬排除) → 基础过滤层（BasicFilter — 已实现）
  ↓ 通过 ← 进入主流程
  ↓ 不通过 → 直接丢弃（当前行为）
  ↓ 接近通过 → 可进入备选池（待实现）

H1(资质不足→备选池) → Agent ② 画像生成 / Agent ③ 岗位分析（未实现）
  ↓ required不满足 → 备选池评估
  ↓ preferred不满足 → 正常继续

T0(显性工具) → Agent ② T0抽取 / Agent ③ T0提取（未实现）
  ↓ 不匹配 → 备选池评估

T1/T2/T3(胜任力推断) → 加权余弦相似度（未实现）
  ↓ 匹配度计算 → 主推荐池 / 备选池判定
```

### 备选池判定时机（设计文档 4.3a）

```
Agent ④ 匹配解释 → 步骤4.1 五层匹配 → 步骤4.3a 备选池判定
                                        ↓
                       被H1/T0软条件筛掉 且 胜任力得分 ≥ 阈值
                                        ↓
                   高潜备选(≥100%阈值) / 普通备选(≥80%阈值)
```

---

## 二、数据结构设计

### 核心数据类

```python
# 备选池条目（单个员工在池中的记录）
@dataclass
class CandidatePoolItem:
    employee_id: str                # 员工ID
    employee_info: dict             # 13字段基础信息
    failed_layers: list[str]        # 失败层: ["H1", "T0"] 等
    failed_details: list[dict]      # 失败详情: [{"layer":"H1","condition":"PMP证书","required":True,"actual":None,"gap":"缺少证书"}]
    competency_score: float         # 胜任力综合得分(0-100)
    threshold_score: float          # 当时的主推荐池阈值
    pool_level: str                 # "high_potential" | "normal" | "discarded"
    improvement_suggestions: list[str]   # 改善建议
    created_at: str                 # 入池时间
    last_re_evaluated: str          # 最后重新评估时间
    version: int                    # 版本号（每次重评估+1）


# 备选池容器
@dataclass
class CandidatePool:
    pool_id: str                    # 池ID（关联岗位需求）
    job_requirements: dict          # 关联的岗位需求摘要
    primary_candidates: list[dict]  # 主推荐池（Top-N）
    high_potential: list[CandidatePoolItem]  # 高潜备选
    normal: list[CandidatePoolItem]         # 普通备选
    discarded: list[CandidatePoolItem]      # 丢弃（仅记录审计）
    created_at: str
    updated_at: str
```

### BasicFilter 输出扩展

当前输出：
```python
{"filtered_employees": [...], "filter_log": [...], "skipped_conditions": [...], "total_before": N, "total_after": M, "error": None}
```

扩展后输出（增加 `filtered_out_employees`）：
```python
{
    "filtered_employees": [...],       # 通过者（不变）
    "filtered_out_employees": [        # 新增——被过滤掉但接近通过的员工
        {
            "employee": {...},         # 员工13字段
            "failed_by": ["age_range", "political_status"],
            "failed_details": [
                {"condition": "age_range", "condition_value": [30,45], "actual_value": 28, "gap": "年龄28低于下限30"},
                {"condition": "political_status", "condition_value": ["中共党员"], "actual_value": "群众", "gap": "政治面貌不符"}
            ],
            "is_close_match": True     # 是否接近通过（仅差1个条件或差距很小）
        }
    ],
    "filter_log": [...],               # 不变
    "skipped_conditions": [...],       # 不变
    "total_before": N,
    "total_after": M,
    "filtered_out_count": K,           # 新增
    "error": None
}
```

### H0 硬条件 vs H1 软条件的区分

当前 BasicFilter 所有条件都是 H0（硬过滤）。未来引入 H1 后，需要在 conditions 中标记：

```python
# 在 conditions 中增加软硬标记（由 UI 或 HR 输入决定）
conditions = {
    "age_range": {"value": [30, 45], "type": "hard"},          # H0: 硬条件
    "political_status": {"value": ["中共党员"], "type": "hard"}, # H0: 硬条件
    "min_performance": {"value": "B", "type": "soft"},          # H1: 软条件→保留为备选
    "major_keywords": {"value": ["计算机"], "type": "soft"},     # H1: 软条件→保留为备选
}
```

当前 BasicFilter 的所有条件都是 H0（硬过滤），未来增加 H1 软条件后，备选池才有实际意义。但在此之前，**BasicFilter 的 `filtered_out_employees` 已经可以为备选池提供数据基础**。

---

## 三、与当前代码的 3 个对接点

### 对接点 1：BasicFilter → 备选池数据源

**文件**：`filter/basic_filter.py`

**变更**：
1. `apply()` 方法增加 `filtered_out_employees` 输出
2. 新增 `_get_filtered_out()` 内部方法，追踪每个被过滤员工触发了哪些条件
3. `is_close_match` 标记：仅被 1 个条件过滤掉，且差距在阈值内的员工

**接口变化**：
```python
# 当前
result = filter.apply(conditions)
# result 只有 filtered_employees 和 filter_log

# 扩展后
result = filter.apply(conditions)
# result 新增 filtered_out_employees 列表
```

### 对接点 2：PipelineRunner → 备选池数据传递

**文件**：`orchestrator/pipeline.py`

**变更**：
1. PipelineRunner 的 `run()` 方法接收 `filter_result` 作为初始数据
2. 在 Agent 间传递时，`filtered_out_employees` 随 `current_data` 一起传递
3. Agent ④ 匹配解释执行完毕后，从结果中提取备选池

**数据流**：
```
PipelineRunner.run(initial_data)
  initial_data = {
      "filtered_employees": [...],        # 当前已存在
      "filtered_out_employees": [...],    # 新增
      "job_requirements": {...},          # 新增（HR输入的岗位需求）
      "trace_id": "..."
  }
  → Agent① 数据理解 → 输出融合数据
  → Agent② 画像生成 → 输出员工画像（含H1/T0/T1/T2/T3）
  → Agent③ 岗位分析 → 输出岗位画像（含H1/T0/T1/T2/T3权重）
  → Agent④ 匹配解释 → 输出 {primary: [...], alternative: [...], discarded: [...]}
```

### 对接点 3：Streamlit UI → 备选池展示

**文件**：`ui/app.py`

**变更**：
1. Step 2（基础过滤）增加"被过滤员工"标签页
2. Step 6（推荐结果）展示备选池清单
3. 侧边栏操作流程增加备选池入口

**UI 布局**：
```
Step 2 过滤结果（当前）：
  ┌─ 过滤结果 ──────────────────────────────────────┐
  │  过滤前: 100人 → 过滤后: 42人                    │
  │  📋 过滤日志                                     │
  │  👥 筛选后员工列表                                │
  └──────────────────────────────────────────────────┘

Step 2 过滤结果（扩展后）：
  ┌─ 过滤结果 ──────────────────────────────────────┐
  │  过滤前: 100人 → 过滤后: 42人                     │
  │  📋 过滤日志                                     │
  │  ┌─ Tab: 已通过(42) ── Tab: 备选观察(15) ───┐    │
  │  │  被过滤但接近通过的员工列表               │     │
  │  │  name | 原因 | 差距 | 建议               │     │
  │  │  张三 | 年龄28<30 | 差2岁 | 放宽年龄至28  │     │
  │  └──────────────────────────────────────────┘     │
  │  👥 筛选后员工列表                                │
  └──────────────────────────────────────────────────┘
```

Step 6 推荐结果（将来）：
```
┌─ 主推荐池 ──────────┐  ┌─ 高潜备选池 ──────────┐
│  Top-5 推荐          │  │  被软条件筛掉但胜任力高   │
│  1. 李四 92% ✅      │  │  1. 王五 85% (缺PMP证书) │
│  2. 张三 88% ✅      │  │  2. 赵六 82% (无管理经验) │
│  3. ...              │  │  → 建议：完善证书后重新评估 │
└──────────────────────┘  └──────────────────────────┘
```

---

## 四、分阶段实现路径

### 阶段 1：数据捕获（当前 → 下一任务）

**目标**：让 BasicFilter 能够记录被过滤掉的员工信息，为备选池提供数据基础

| 文件 | 变更 | 说明 |
|------|------|------|
| `filter/basic_filter.py` | `apply()` 增加 `filtered_out_employees` 输出 | 追踪每个被过滤员工触发了哪些条件 |
| `filter/basic_filter.py` | 新增 `_get_filtered_out()` 方法 | 内部计算被过滤员工的条件差距 |
| `ui/app.py` | Step 2 增加"被过滤员工"折叠区 | 展示被过滤员工列表（含原因和差距） |
| `tests/test_basic_filter.py` | 新增 `TestFilteredOut` 测试类 | 验证 filtered_out_employees 输出正确性 |

**完成标志**：
- BasicFilter 输出含 `filtered_out_employees`（非空数组）
- UI 展示被过滤员工列表
- 测试覆盖：单条件过滤、多条件过滤、全部通过、全部过滤

### 阶段 2：Agent 数据传递（后续任务）

**目标**：在 PipelineRunner 和 Agent 之间传递备选池数据，为 Agent ④ 的备选池判定做准备

**前提**：Agent ①-④ 已实现

| 文件 | 变更 | 说明 |
|------|------|------|
| `orchestrator/pipeline.py` | `run()` 初始数据增加 `filtered_out_employees` | 从 BasicFilter 结果传递到 Agent ① |
| `agents/base_agent.py` | `context` 增加 `filtered_out_employees` 字段 | 所有 Agent 可访问备选池数据 |
| `agents/agent_04_match.py` | 实现步骤4.3a 备选池判定逻辑 | 根据 H1/T0 失败 + 胜任力得分判定 |

### 阶段 3：备选池管理（最终）

**目标**：完整的备选池生命周期管理，含重评估、改善建议、UI 展示

| 文件 | 变更 | 说明 |
|------|------|------|
| `filter/candidate_pool.py` | 新建 | `CandidatePool` / `CandidatePoolItem` 数据类 + 管理方法 |
| `filter/candidate_pool.py` | 实现 `re_evaluate()` 方法 | 当岗位条件变化时重新评估备选池 |
| `ui/app.py` | Step 6 实现备选池展示 | 主推荐池 + 高潜备选 + 普通备选 三栏 |
| `ui/app.py` | 侧边栏增加"备选池"步骤指示 | 步骤指示器从 Step 6 扩展为 Step 7 |

---

## 五、BasicFilter 的具体代码变更

### 5.1 `apply()` 方法扩展

```python
def apply(self, conditions: dict) -> dict:
    """执行过滤，返回过滤结果（含被过滤员工信息）。"""
    # ... 原有逻辑不变 ...
    
    filtered_out = self._get_filtered_out(original_df, filtered_df, conditions)
    
    return {
        "filtered_employees": numpy_to_native(filtered_df.to_dict("records")),
        "filtered_out_employees": filtered_out,  # 新增
        "filter_log": logs,
        "skipped_conditions": skipped,
        "total_before": len(original_df),
        "total_after": len(filtered_df),
        "filtered_out_count": len(filtered_out),  # 新增
        "error": None,
    }
```

### 5.2 `_get_filtered_out()` 方法

```python
def _get_filtered_out(self, original_df, filtered_df, conditions) -> list[dict]:
    """找出被过滤掉的员工，以及每个员工被哪些条件过滤掉。"""
    passed_ids = set(filtered_df["employee_id"])
    all_ids = set(original_df["employee_id"])
    filtered_out_ids = all_ids - passed_ids
    
    result = []
    for eid in filtered_out_ids:
        emp = original_df[original_df["employee_id"] == eid].iloc[0]
        details = self._check_employee_conditions(emp, conditions)
        is_close = len([d for d in details if d["failed"]]) <= 1
        
        result.append({
            "employee": numpy_to_native(emp.to_dict()),
            "failed_by": [d["condition"] for d in details if d["failed"]],
            "failed_details": details,
            "is_close_match": is_close,
        })
    
    # 按接近程度排序（接近通过的排前面）
    result.sort(key=lambda x: (not x["is_close_match"], len(x["failed_by"])))
    return result
```

### 5.3 测试用例

```python
class TestFilteredOut:
    """验证被过滤员工信息的完整性。"""
    
    def test_single_condition_filtered_out(self, sample_employees, sample_performance):
        """单条件过滤，确认被过滤员工信息正确。"""
        f = BasicFilter(sample_employees, sample_performance)
        result = f.apply({"age_range": [30, 45]})
        assert "filtered_out_employees" in result
        assert len(result["filtered_out_employees"]) > 0
        # 每个被过滤员工应有 failed_details
        for emp in result["filtered_out_employees"]:
            assert "failed_by" in emp
            assert "failed_details" in emp
            assert "age_range" in emp["failed_by"]
    
    def test_all_passed_no_filtered_out(self, sample_employees, sample_performance):
        """无过滤条件，不应有被过滤员工。"""
        f = BasicFilter(sample_employees, sample_performance)
        result = f.apply({})
        assert len(result["filtered_out_employees"]) == 0
    
    def test_all_filtered_out_all_have_details(self, sample_employees, sample_performance):
        """全部被过滤时，每个员工都有 fail_details。"""
        f = BasicFilter(sample_employees, sample_performance)
        result = f.apply({"age_range": [0, 0]})
        assert len(result["filtered_out_employees"]) == result["total_before"]
        for emp in result["filtered_out_employees"]:
            assert len(emp["failed_by"]) > 0
    
    def test_close_match_marked(self, sample_employees, sample_performance):
        """仅差一个条件的员工应标记 is_close_match=True。"""
        f = BasicFilter(sample_employees, sample_performance)
        result = f.apply({"age_range": [30, 45], "political_status": ["中共党员"]})
        close_matches = [e for e in result["filtered_out_employees"] if e["is_close_match"]]
        assert len(close_matches) >= 0  # 可能没有，但不应报错
        for emp in close_matches:
            assert len(emp["failed_by"]) == 1
    
    def test_filtered_out_does_not_include_passed(self, sample_employees, sample_performance):
        """被过滤员工不应包含已通过员工。"""
        f = BasicFilter(sample_employees, sample_performance)
        result = f.apply({"age_range": [30, 45]})
        passed_ids = {e["employee_id"] for e in result["filtered_employees"]}
        filtered_out_ids = {e["employee"]["employee_id"] for e in result["filtered_out_employees"]}
        assert passed_ids & filtered_out_ids == set()
```

---

## 六、UI 对接改动

### Step 2 增加"被过滤员工"标签页（阶段1）

```python
def _render_step_filter() -> None:
    # ... 现有过滤结果 ...
    
    # 新增：被过滤员工信息
    filtered_out = result.get("filtered_out_employees", [])
    if filtered_out:
        tab1, tab2 = st.tabs(["✅ 已通过", "⏳ 备选观察"])
        with tab1:
            # 现有展示
            _render_filtered_employees(result)
        with tab2:
            st.markdown(f"**被过滤但接近条件的员工：{len(filtered_out)} 人**")
            st.caption("以下员工因硬条件被过滤，但差距较小，可考虑放宽条件后重新评估。")
            
            for emp in filtered_out[:10]:  # 最多展示10条
                with st.expander(f"{emp['employee']['name']} — 失败: {', '.join(emp['failed_by'])}"):
                    for detail in emp["failed_details"]:
                        if detail["failed"]:
                            st.write(f"- **{detail['condition']}**: {detail['gap']}")
                    if emp["is_close_match"]:
                        st.info("💡 仅差一个条件，建议优先考虑")
    else:
        # 全部通过，无被过滤员工
        pass
```

### Step 6 展示备选池（阶段3，将来）

```python
def _render_step_recommendation() -> None:
    """Step 6：推荐结果展示（含备选池）。"""
    result = st.session_state.get("match_result", {})
    
    # 主推荐池
    st.markdown("## 🏆 主推荐池")
    for i, candidate in enumerate(result.get("primary", [])):
        with st.container():
            col1, col2 = st.columns([3, 1])
            col1.markdown(f"**{i+1}. {candidate['name']}**")
            col2.metric("匹配度", f"{candidate['score']}%")
    
    # 备选池
    st.markdown("---")
    st.markdown("## 📋 备选池")
    tab1, tab2 = st.tabs(["🌟 高潜备选", "📌 普通备选"])
    
    with tab1:
        for c in result.get("alternative", {}).get("high_potential", []):
            with st.expander(f"{c['employee_id']} — 胜任力 {c['competency_score']}分"):
                for reason in c["fail_reasons"]:
                    st.warning(f"❌ {reason}")
                for suggestion in c["improvement_suggestions"]:
                    st.info(f"💡 {suggestion}")
    
    with tab2:
        for c in result.get("alternative", {}).get("normal", []):
            pass
```

---

## 七、执行优先级与节奏

| 优先级 | 阶段 | 做什么 | 谁依赖 | 预估工时 |
|--------|------|--------|--------|----------|
| **P0** | 1 | BasicFilter 扩展 `filtered_out_employees` | 备选池数据基础 | 1次 |
| **P0** | 1 | UI Step 2 增加"备选观察"标签页 | 用户体验 | 1次 |
| **P0** | 1 | 测试覆盖 filtered_out_employees | 质量闸门 | 0.5次 |
| **P1** | 2 | Agent ①-④ 实现（含H1/T0/T1/T2/T3） | 备选池判定逻辑 | 4-6次 |
| **P1** | 2 | Agent ④ 步骤4.3a 备选池判定 | 备选池核心逻辑 | 1次 |
| **P2** | 3 | `candidate_pool.py` 数据类 + 管理 | 备选池持久化 | 1次 |
| **P2** | 3 | UI Step 6 备选池展示 | 用户可见 | 1次 |
| **P3** | 3 | 备选池重评估机制 | 动态条件放宽 | 1次 |

### 当前阶段的建议（P0）

由于 Agent ①-④ 尚未实现，备选池的完整判定逻辑（H1+T0+胜任力得分）无法在当前运行。但 **BasicFilter 的扩展可以在不依赖任何 Agent 的情况下独立完成**，且为后续备选池提供数据基础。

**建议立即执行 P0**，让 BasicFilter 输出 `filtered_out_employees`，UI 展示"备选观察"标签页。这样即使 Agent 未实现，用户也能看到"被过滤但接近条件的员工"信息。

---

## 八、架构演进图

### 当前状态
```
BasicFilter → filtered_employees → [下一步: Agent ①-④]
```

### 阶段1（P0）
```
BasicFilter → filtered_employees → [Agent ①-④]
            → filtered_out_employees → UI "备选观察"展示
```

### 阶段2（P1，Agent ①-④ 实现后）
```
BasicFilter → filtered_employees → Agent ①→②→③→④
                                          → primary_candidates
                                          → alternative_candidates (备选池)
            → filtered_out_employees → Agent ④ 综合评估
```

### 阶段3（P2-P3，完整状态）
```
BasicFilter → filtered_employees → Agent ①→②→③→④
                                          → primary_candidates → UI Step 6
                                          → alternative_candidates → UI Step 6
            → filtered_out_employees → Agent ④ 综合评估 → re_evaluate → 条件放宽时提拔
                                                                  → improvement_suggestions
```
