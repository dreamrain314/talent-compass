# 修改方案 —— 基于 Day 0-1 代码审查的 7 项修复

> **生成日期:** 2026-07-22
> **审查范围:** Day 0（环境搭建）+ Day 1（编排器框架 + 模拟数据集）
> **审查方法:** 完整代码审查 + 实际数据分布验证 + 网上研究参考
> **问题总数:** 12 个潜在问题，合并为 7 项修改方案

---

## 目录

- [P0-1: 2σ 异常检测改用"评价者均值标准差"](#p0-1-2σ-异常检测改用评价者均值标准差)
- [P0-2: PipelineRunner 增加数据格式适配器机制](#p0-2-pipelinerunner-增加数据格式适配器机制)
- [P0-3: `_save_intermediate` numpy 转换改为递归兜底](#p0-3-save_intermediate-numpy-转换改为递归兜底)
- [P1-4: 增加 `numpy_to_native` 和 `reset_client` 单元测试](#p1-4-增加-numpy_to_native-和-reset_client-单元测试)
- [P1-5: `ui/app.py` 测试页面内容替换方案](#p1-5-uiapppy-测试页面内容替换方案)
- [P2-6: 增加 `PERFORMANCE_FULL_YEARS` 常量保护年度计算](#p2-6-增加-performance_full_years-常量保护年度计算)
- [P3-7: 中间文件目录清理 + 测试隔离](#p3-7-中间文件目录清理--测试隔离)

---

## P0-1: 2σ 异常检测改用"评价者均值标准差"

### 问题

**严重度:** 🔴 静默数据错误 — 不报错不崩溃，但异常评价者全部被忽略

**数据验证：**

| 指标 | 值 |
|------|-----|
| 全局分数均值 | 4.08 |
| 全局分数标准差（所有分数） | 0.73 |
| 2σ 范围（基于所有分数） | [2.61, 5.54] |
| 极端评价者（全5分）z-score | **1.26**（< 2σ，检测不出） |
| 被 2σ 检测为异常的评价者数 | **0/100** |

**根因：** 指南写"偏差 > 全局 2σ → 标记异常"，但未明确 σ 的计算对象。当前 `DS` 字典生成的基线分数分布在 3-5，全局分数标准差 0.73 被"正常评价者"的内部变异拉大，即使全 5 分的评价者也只偏离均值 1.26 个标准差。

**网上参考：** Journal of Experimental Social Psychology (2013) 指出 mean ± kσ 在非正态分布下不可靠，推荐使用 MAD（中位数绝对偏差）替代。但本项目 HR 评分场景有明确的"评价者均值为单位"的领域结构，使用 evaluator-mean 的 σ 更直观。参考 arXiv:1606.09264v1 中 360 评价的异常检测实践——使用评价者层面的汇总统计而非单次评分层面的统计。

### 修改方案

**需修改 2 处文件，联动修复：**

#### ① `generate_mock_data.py` — 扩展分数分布

在 `DS` 字典中为每个评价维度增加 1-2 分的基线值，覆盖 1-5 全量程：

```python
# 修改前（示例：专业能力-上级）：评分池只含 3-5
"上级": [4, 5, 5, 4, 4, 5, 3, 4, 5, 4, 5, 5],

# 修改后：增加 1-2 分项，覆盖全量程
"上级": [1, 2, 4, 5, 5, 4, 4, 5, 3, 4, 5, 4, 5, 5, 2],
```

**参考：** 美国教育研究协会（AERA）的 360 评价指南指出，评价者评分应覆盖全量程才有区分度。扩展后预期分数分布：{1: ~5%, 2: ~10%, 3: ~25%, 4: ~40%, 5: ~20%}。

#### ② `agents/data_understanding.py` — 修改异常检测逻辑（Day 3 实现时）

在 Agent① 步骤 1.4 中使用**评价者均值的标准差**（between-subject SD）作为 2σ 阈值：

```python
# 检测逻辑（伪代码）
# 步骤 1: 对每个评价者计算其所有评分的均值
evaluator_means = {}
for evaluator_id in all_evaluator_ids:
    scores = [row["score"] for row in all_rows if row["evaluator_id"] == evaluator_id]
    evaluator_means[evaluator_id] = statistics.mean(scores)

# 步骤 2: 计算评价者均值的全局均值和标准差
global_mean = statistics.mean(evaluator_means.values())
between_sd = statistics.stdev(evaluator_means.values())  # ← 评价者之间的 σ

# 步骤 3: 判断异常
for eid, mean in evaluator_means.items():
    z = (mean - global_mean) / between_sd
    if abs(z) > 2:
        mark_as_anomalous(eid)  # 权重 × 0.2
```

**验证方法：** 修改后打印每个评价者的 z-score 和异常标记结果，确认极端评价者（全5分）被标记为异常。

---

## P0-2: PipelineRunner 增加数据格式适配器机制

### 问题

**严重度:** 🔴 Pipeline 中断 — BasicFilter 返回 records 列表，Agent① 期望文件路径

**根因：** `BasicFilter.apply()` 返回 `{"filtered_employees": [...], "filter_log": [...], ...}`（records 列表），Agent① 的 `execute()` 期望 `{"employees": "file_path.csv", ...}`（文件路径字符串）。指南在 Task 4.1 中通过手动写临时 CSV 解决，但这不是 PipelineRunner 的自动行为，后续集成时极易遗漏。

**网上参考：** Refactoring.Guru 的 Adapter 模式 + Spark ML Pipeline 的 Transformer 概念——在阶段之间插入专用的数据格式转换器，使各阶段解耦。Martin Fowler 的 Pipeline 架构模式也推荐使用 Adapter 处理阶段间的数据契约不匹配。

### 修改方案

**修改 `orchestrator/pipeline.py`，增加 FormatAdapter 机制：**

```python
class PipelineRunner:
    def __init__(
        self,
        agents: list[BaseAgent],
        output_dir: str | None = None,
        default_timeout: int = AGENT_EXEC_TIMEOUT,
        format_adapters: list[tuple[int, Callable[[dict, dict], dict]]] | None = None,
    ):
        self.format_adapters = format_adapters or []
        ...

    def run(self, initial_data: dict, trace_id: str | None = None) -> dict:
        ...
        for i, agent in enumerate(self.agents):
            # 在将 data 传给 agent 之前，检查是否有 adapter
            for step_idx, adapter in self.format_adapters:
                if step_idx == i:
                    current_data = adapter(current_data, context)
                    break
            step_result = self._execute_with_timeout(agent, ...)
```

**使用示例：** `scripts/run_pipeline_phase1.py` 中：

```python
def filter_to_agent_adapter(data: dict, context: dict) -> dict:
    """将 BasicFilter 的 records 输出转为 Agent① 期望的文件路径格式"""
    import pandas as pd
    from datetime import datetime
    from config import INTERMEDIATE_DIR

    filtered = data.get("filtered_employees", [])
    if not filtered:
        return data

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    temp_path = INTERMEDIATE_DIR / f"filtered_employees_{timestamp}.csv"
    df = pd.DataFrame(filtered)
    # 🔴 employee_id 强制 str 类型，防止 INNER JOIN 类型不匹配
    if "employee_id" in df.columns:
        df["employee_id"] = df["employee_id"].astype(str)
    df.to_csv(temp_path, index=False, encoding="utf-8-sig")

    return {
        "employees": str(temp_path),
        "performance": "data/raw/performance.csv",
        "projects": "data/raw/projects.json",
        "training": "data/raw/training.csv",
        "evaluation_360": "data/raw/evaluation_360.csv",
    }

runner = PipelineRunner(
    [basic_filter_adapter, data_understanding_agent],
    format_adapters=[(0, filter_to_agent_adapter)],
)
```

---

## P0-3: `_save_intermediate` numpy 转换改为递归兜底

### 问题

**严重度:** 🔴 序列化崩溃 — `json.dumps` 遇到 `numpy.int64` 等类型抛出 `TypeError`

**根因：** `_save_intermediate` 只在 `data` 是 `list[dict]` 时调用 `numpy_to_native` 转换，但 BasicFilter 和 Agent① 的 `data` 字段都是嵌套 dict，转换不生效。

**网上参考：** Stack Overflow 社区 + NumPy 官方文档确认 `json.dumps(default=...)` 是处理 numpy 类型的最不侵入方案。FastAPI 社区（GitHub issue #15085）也推荐使用 `json.dumps(default=str)` 或自定义 default 函数兜底。

### 修改方案

**修改 `orchestrator/pipeline.py` 的 `_save_intermediate` 方法，1 行变更：**

```python
# 修改前：手动遍历 list[dict] 做 numpy 转换，然后 json.dumps
data = result.get("data")
if isinstance(data, list) and data and isinstance(data[0], dict):
    try:
        for item in data:
            for k, v in item.items():
                item[k] = numpy_to_native(v)
    except Exception:
        pass
serialized = json.dumps(result, ensure_ascii=False, indent=2, default=str)

# 修改后：移除手动遍历，在 json.dumps 的 default 参数中传入 numpy_to_native
serialized = json.dumps(
    result, ensure_ascii=False, indent=2,
    default=lambda x: numpy_to_native(x) if hasattr(x, 'dtype') else str(x)
)
```

**验证方法：** 构造一个含 `numpy.int64` 值的嵌套 dict，`json.dumps(result, default=numpy_to_native)` 应不抛异常。

---

## P1-4: 增加 `numpy_to_native` 和 `reset_client` 单元测试

### 问题

**严重度:** 🟠 测试覆盖缺口 — 2 个函数无测试

| 函数 | 复杂度 | 是否有测试 |
|------|--------|-----------|
| `numpy_to_native()` | 递归处理 6 种类型 + NaN 边界 | ❌ 无 |
| `reset_client()` | 线程安全 + 全局状态操作 | ❌ 无 |

### 修改方案

**新建 `tests/test_utils.py`：**

```python
"""utils 模块单元测试 — numpy_to_native + reset_client"""
import json
import pytest
import numpy as np
from utils import numpy_to_native


class TestNumpyToNative:
    """验证 numpy_to_native 的 6 种类型转换 + 边界条件"""

    def test_numpy_int64(self):
        result = numpy_to_native(np.int64(42))
        assert result == 42
        assert isinstance(result, int)

    def test_numpy_float64(self):
        result = numpy_to_native(np.float64(3.14))
        assert result == 3.14
        assert isinstance(result, float)

    def test_numpy_float64_nan(self):
        """NaN 应转为 None（JSON 兼容）"""
        result = numpy_to_native(np.float64("nan"))
        assert result is None

    def test_numpy_bool(self):
        result = numpy_to_native(np.bool_(True))
        assert result is True
        assert isinstance(result, bool)

    def test_numpy_array(self):
        """ndarray 应转为 list"""
        arr = np.array([1, 2, 3])
        result = numpy_to_native(arr)
        assert result == [1, 2, 3]

    def test_nested_dict(self):
        """嵌套 dict 中的 numpy 值应递归转换"""
        obj = {"a": np.int64(1), "b": {"c": np.float64(2.0)}}
        result = numpy_to_native(obj)
        assert result["a"] == 1
        assert result["b"]["c"] == 2.0

    def test_list_of_dicts(self):
        """list[dict] 中的 numpy 值应递归转换"""
        obj = [{"x": np.int64(10)}, {"x": np.int64(20)}]
        result = numpy_to_native(obj)
        assert result[0]["x"] == 10

    def test_round_trip_json(self):
        """转换后的结果应可被 json.dumps 序列化"""
        obj = {"a": np.int64(1), "b": np.float64(2.5), "c": np.bool_(True)}
        native = numpy_to_native(obj)
        json_str = json.dumps(native)
        parsed = json.loads(json_str)
        assert parsed["a"] == 1
        assert parsed["b"] == 2.5
        assert parsed["c"] is True


class TestResetClient:
    """验证 reset_client 的线程安全缓存重建"""

    def test_reset_does_not_crash(self):
        from utils.llm_client import reset_client, _get_client
        reset_client()
        c1 = _get_client()
        reset_client()
        c2 = _get_client()
        assert c1 is not None
        assert c2 is not None
```

---

## P1-5: `ui/app.py` 测试页面内容替换方案

### 问题

**严重度:** 🟡 UI 混乱 — 主区域是测试输入框 + 发送按钮，指南要求替换为文件上传 + 过滤 UI

**根因：** 当前 `ui/app.py` 的主区域是"💬 测试消息"文本输入框 + "🚀 发送"按钮。指南 Task 2.2 明确要求"测试页面内容必须完全替换，不能保留"——但开发者可能倾向"追加"而非"替换"，导致两套控件共存。

### 修改方案

**Day 2.2 实现时分三步做，避免"追加"行为：**

#### 第一步：备份当前文件

```bash
cp ui/app.py ui/app_test_page_backup.py
```

#### 第二步：删除主区域测试代码

移除 `# ── 主区域 ──` 到 `# ── 页脚 ──` 之间的所有代码，包括：
- `st.text_area("💬 测试消息", ...)`
- `st.button("🚀 发送", ...)`
- `if send_btn and user_input:` 逻辑块
- 页脚的 `st.caption(page时间...)`

#### 第三步：在主区域中新建步骤化 UI

```python
# 主区域（新）
st.header("📋 操作流程")
step = st.session_state.get("step", 1)

if step == 1:
    col1, col2 = st.columns(2)
    with col1:
        emp_file = st.file_uploader("员工基础信息 (employees.csv)", type="csv")
        perf_file = st.file_uploader("绩效记录 (performance.csv)", type="csv")
        proj_file = st.file_uploader("项目经历 (projects.json)", type="json")
    with col2:
        train_file = st.file_uploader("培训记录 (training.csv)", type="csv")
        eval_file = st.file_uploader("360评价 (evaluation_360.csv)", type="csv")

    if st.button("确认上传"):
        st.session_state["step"] = 2
        st.rerun()

elif step == 2:
    # 基础过滤结果展示
    ...
```

#### 第四步：将 API 测试功能折叠到侧边栏

```python
with st.sidebar:
    # ... 原有 API Key 配置 ...

    with st.expander("🔧 API 调试", expanded=False):
        user_input = st.text_area("测试消息", ...)
        if st.button("发送测试"):
            ...
```

---

## P2-6: 增加 `PERFORMANCE_FULL_YEARS` 常量保护年度计算

### 问题

**严重度:** 🟡 轻微误筛 — `performance.csv` 包含 2026 年（当前不完整年度）数据，但 `min_performance` 只应检查 2024+2025

**根因：** 指南 Task 2.1 正确指定了"当前年份-2 和 当前年份-1"，但模拟数据包含 2026 年绩效数据。如果 BasicFilter 实现者不小心把 `full_years` 写为 `[this_year-2, this_year-1, this_year]`，将错误地把 2026 年未完成的绩效纳入筛选。

### 修改方案

**修改 `config.py`，增加年度常量作为单一来源：**

```python
# config.py 新增（在超时常量之后，路径常量之前）
from datetime import datetime

# ── 绩效检查的完整年度范围 ──
# 🔴 仅包含"当前年份-2"和"当前年份-1"（不包含当前不完整年度）
# 消费者：filter/basic_filter.py 的 min_performance 逻辑
# 禁止在其他文件中重新定义此值（参见 CLAUDE.md D2 单一来源原则）
PERFORMANCE_FULL_YEARS = [datetime.now().year - 2, datetime.now().year - 1]
```

**在 `filter/basic_filter.py` 的 `apply()` 方法中引用：**

```python
from config import PERFORMANCE_FULL_YEARS

# min_performance 处理逻辑
if "min_performance" in conditions:
    min_grade = conditions["min_performance"]
    min_ordinal = PERFORMANCE_ORDINAL.get(min_grade, 0)

    full_year_perf = performance_df[performance_df["year"].isin(PERFORMANCE_FULL_YEARS)]

    for emp_id in employees_df["employee_id"]:
        emp_perf = full_year_perf[full_year_perf["employee_id"] == emp_id]
        if emp_perf.empty:
            filter_log.append({"condition": "min_performance",
                               "status": "insufficient_data", ...})
            continue
        # 检查是否所有完整年度绩效都 ≥ min_grade
        ...
```

---

## P3-7: 中间文件目录清理 + 测试隔离

### 问题

**严重度:** 🟢 维护困难 — `data/intermediate/` 已积累 80+ 测试 JSON 文件，与真实输出混合

### 修改方案

**修改 2 个文件 + 可选 1 个新文件：**

#### ① `tests/conftest.py` — 增加测试后清理

```python
def pytest_sessionfinish(session):
    """测试会话结束后清理测试产生的中间文件"""
    from config import INTERMEDIATE_DIR
    if INTERMEDIATE_DIR.exists():
        test_files = [
            f for f in INTERMEDIATE_DIR.iterdir()
            if f.is_file() and f.suffix == ".json"
            and ("pipe-test" in f.name or "timeout-test" in f.name
                 or "test-fallback" in f.name)
        ]
        for f in test_files:
            try:
                f.unlink()
            except OSError:
                pass
```

#### ② 确认测试全部使用 `tmp_path`

```bash
grep -n "data/intermediate" tests/*.py
# 输出应为空——无硬编码路径
```

#### ③ 可选：`scripts/clean_intermediate.py`

```python
"""清理 data/intermediate/ 中的测试残留文件"""
from config import INTERMEDIATE_DIR

if INTERMEDIATE_DIR.exists():
    count = 0
    for f in INTERMEDIATE_DIR.iterdir():
        if f.is_file() and f.suffix == ".json":
            if "pipe-test" in f.name or "timeout-test" in f.name:
                f.unlink()
                count += 1
    print(f"已清理 {count} 个测试残留文件")
```

---

## 附录：修改优先级与工作量

| 优先级 | 编号 | 名称 | 涉及文件 | 工作量 | 最佳时机 |
|--------|------|------|---------|--------|---------|
| 🔴 P0 | P0-1 | 2σ 异常检测改用评价者均值标准差 | `generate_mock_data.py`, `agents/data_understanding.py` | 2 处修改 | Day 3 实现前 |
| 🔴 P0 | P0-2 | PipelineRunner 增加 Adapter 机制 | `orchestrator/pipeline.py` | 新功能 ~50 行 | 任何 Agent 串联前 |
| 🔴 P0 | P0-3 | `_save_intermediate` numpy 递归转换 | `orchestrator/pipeline.py` | 1 行变更 | 立即 |
| 🟠 P1 | P1-4 | 增加 `numpy_to_native` + `reset_client` 测试 | `tests/test_utils.py`（新建） | 2 个测试类 | 立即 |
| 🟡 P1 | P1-5 | `ui/app.py` 测试页面替换 | `ui/app.py` | 整体重构 | Day 2.2 实现时 |
| 🟡 P2 | P2-6 | 增加 `PERFORMANCE_FULL_YEARS` 常量 | `config.py`, `filter/basic_filter.py` | 2 处修改 | Day 2.1 实现前 |
| 🟢 P3 | P3-7 | 中间文件清理 + 测试隔离 | `conftest.py`, `scripts/clean_intermediate.py` | 2 个新文件 | 立即 |

### 依赖关系

```
P0-3 (numpy 递归转换) → 无依赖，可立即修改
P1-4 (测试补充) → 依赖 P0-3 修改后的代码
P2-6 (PERFORMANCE_FULL_YEARS) → 必须在 Day 2.1 实现前完成
P0-2 (Adapter 机制) → 必须早于 Day 4.1（脚本串联）
P0-1 (2σ 异常检测) → 必须在 Day 3 实现 Agent① 步骤 1.4 前完成
P1-5 (UI 替换) → 必须在 Day 2.2 实现前完成
P3-7 (清理) → 无依赖，随时可做
```

---

## 附录：网上参考来源

| 问题 | 参考来源 | 核心借鉴 |
|------|---------|---------|
| 2σ 异常检测失效 | Journal of Experimental Social Psychology (2013) — "Detecting outliers: Do not use standard deviation around the mean" | 使用基于评价者层级的统计量替代原始分数层级 |
| 评分分布覆盖不足 | arXiv:1606.09264v1 — 360 评价异常检测 | 评价者层面的汇总统计 vs 单次评分统计 |
| 数据格式适配器 | Refactoring.Guru — Adapter Pattern | 在 Pipeline 阶段间插入格式转换器 |
| 管道架构设计 | Martin Fowler — Pipeline Architecture | 阶段间数据契约的解耦方案 |
| numpy 序列化 | FastAPI GitHub Issue #15085, Stack Overflow | `json.dumps(default=...)` 作为递归兜底 |
| 不完整年度处理 | 绩效管理实践指南 | 只使用完整年度（当前年份-2, 当前年份-1） |

---

*本方案基于 2026-07-22 的完整代码审查（Day 0-1）和实际数据分布验证生成。*