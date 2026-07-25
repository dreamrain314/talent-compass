# BasicFilter 实现计划

> **日期:** 2026-07-22
> **对应:** 第一周开发指南 Task 2.1 — Pandas 过滤引擎
> **后续对接:** Task 2.2 (Streamlit UI) / Task 3 (Agent①) / Task 4.1 (Pipeline 脚本)

---

## 一、文件清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `filter/__init__.py` | 新建 | 空文件，包标记 |
| `filter/basic_filter.py` | 新建 | 核心实现，~150 行 |
| `tests/test_basic_filter.py` | 新建 | ~12 个测试 |

---

## 二、架构设计

```
filter/basic_filter.py
├── class BasicFilter
│   ├── __init__(self, employees_df: pd.DataFrame, performance_df: pd.DataFrame)
│   │   └── 保存引用 + 预计算员工入职年份映射 {employee_id: hire_year}
│   │
│   └── apply(self, conditions: dict) -> dict
│       ├── 遍历 conditions 逐条件叠加过滤
│       │   ├── age_range         → _apply_age_range()
│       │   ├── political_status  → _apply_political_status()
│       │   ├── major_keywords    → _apply_major_keywords()
│       │   ├── min_years_of_service → _apply_min_years()
│       │   ├── level_range       → _apply_level_range()
│       │   ├── min_performance   → _apply_min_performance()
│       │   └── 其他 key          → 追加到 skipped_conditions
│       │
│       ├── 每步记录 filter_log: [condition, before_count, after_count, removed_count]
│       ├── 最终 filtered_employees 用 numpy_to_native 递归转换
│       └── 返回 {
│               "filtered_employees": [...],
│               "filter_log": [...],
│               "skipped_conditions": [...],
│               "total_before": int,
│               "total_after": int
│           }
```

### 不继承 BaseAgent 的原因

BasicFilter 是纯 Pandas 确定性代码（零 AI 调用），不适用 BaseAgent 的抽象契约：
- `validate_input()` → conditions 是自由格式 dict，无固定 schema
- `get_input_schema()` / `get_output_schema()` → 无意义
- `data_lineage` / `cancel_event` → 不需要

PipelineRunner 中通过 Task 4.1 脚本直接调用，而非作为 Agent 子类。

---

## 三、6 个过滤条件的实现细节

### 1. age_range: [min, max]

```python
df['age'].between(min, max)
```

- `min=0` → 不过滤下限
- `max=999` → 不过滤上限

### 2. political_status: list[str]

```python
df['political_status'].isin(values)
```

- 空列表 `[]` → 不过滤（全通过）

### 3. major_keywords: list[str]

```python
mask = pd.Series(False, index=df.index)
for kw in keywords:
    mask |= df['major'].str.contains(kw, na=False, regex=False)
```

- 多个关键词 OR 关系
- `na=False` 防止 NaN 抛异常
- `regex=False` 防止特殊字符被解释为正则
- 空列表 → 不过滤

### 4. min_years_of_service: int

```python
df['years_of_service'] >= min_years
```

### 5. level_range: [min, max]

```python
# 🔴 必须数值比较，禁止字符串比较
df['_level_num'] = df['current_level'].str[1:].astype(int)
df['_level_num'].between(min_num, max_num)
```

- `"P10" < "P5"` 在字符串序中为 `True`，必须用 `int(level[1:])`
- 畸形值（如 `""`）→ `int("")` 抛 `ValueError` → 该条件标记为 `skipped`

### 6. min_performance: str (A/B/C/D)

```python
from config import PERFORMANCE_FULL_YEARS, PERFORMANCE_ORDINAL

min_ordinal = PERFORMANCE_ORDINAL.get(min_grade, 0)

# 只取完整年度
full_year_perf = performance_df[performance_df['year'].isin(PERFORMANCE_FULL_YEARS)]

for emp_id in employees_df['employee_id']:
    emp_perf = full_year_perf[full_year_perf['employee_id'] == emp_id]
    if emp_perf.empty:
        # 新员工：无任何完整年度绩效
        filter_log 标记 insufficient_data, 不排除
        continue
    
    hire_year = self._hire_years[emp_id]
    for _, row in emp_perf.iterrows():
        if row['year'] < hire_year:
            continue  # 入职前的年度跳过
        if PERFORMANCE_ORDINAL.get(row['performance_grade'], 0) < min_ordinal:
            exclude  # 某一年绩效低于底线 → 排除
```

#### 新员工处理规则

| 场景 | 行为 |
|------|------|
| 入职年份 > 2024，有 2025 绩效 | 只检查 2025 |
| 入职年份 > 2025，无 2024/2025 绩效 | `insufficient_data` 标记，**不排除** |
| 入职年份 ≤ 2024，有 2024+2025 绩效 | 两年都检查 |

---

## 四、返回格式

```python
{
    "filtered_employees": [
        {
            "employee_id": "JZ0001",
            "name": "王芳",
            "age": 39,
            "gender": "男",
            "political_status": "中共党员",
            "education": "本科",
            "major": "计算机科学与技术",
            "department": "信息技术部",
            "job_sequence": "技术研发类",
            "current_position": "软件工程师",
            "current_level": "P6",
            "hire_date": "2010-05-09",
            "years_of_service": 16
        },
        # ... 全部字段已通过 numpy_to_native 转换为 Python 原生类型
    ],
    "filter_log": [
        {
            "condition": "age_range",
            "before_count": 100,
            "after_count": 74,
            "removed_count": 26
        },
        {
            "condition": "min_performance",
            "before_count": 74,
            "after_count": 68,
            "removed_count": 6,
            "insufficient_data": 2  # 新员工无完整年度数据
        }
    ],
    "skipped_conditions": ["unsupported_key_xxx"],
    "total_before": 100,
    "total_after": 68
}
```

---

## 五、边界情况处理

| 场景 | 行为 |
|------|------|
| `conditions={}`（空字典） | 返回所有员工，`filter_log=[]` |
| 条件 key 不支持 | 追加到 `skipped_conditions`，**不静默跳过**，不中断其他条件 |
| 全部被过滤（total_after=0） | `filter_log` 最后一条追加 `"note": "建议放宽条件"` |
| 新员工无完整年度绩效 | `filter_log` 中标注 `"insufficient_data": N`，**不排除** |
| `level_range` 含畸形值 | `int(x[1:])` 抛 `ValueError` → 该条件标记为 `skipped` |
| `major_keywords` 含特殊字符 | `regex=False` 防止正则解释 |
| 某条件值为 `None` 或非法类型 | 该条件标记为 `skipped` |

---

## 六、对接面分析

### 对接面 1：BasicFilter → Streamlit UI（Task 2.2）

同进程内 Python 对象直接调用，无序列化要求：

```python
# Task 2.2 中调用
filter = BasicFilter(df_emp, df_perf)
result = filter.apply(conditions)

# 直接使用：
st.dataframe(result["filtered_employees"])   # 渲染表格
for log in result["filter_log"]:             # 展示过滤日志
    st.write(f"{log['condition']}: {log['before_count']}→{log['after_count']}")
```

**BasicFilter 保证的契约：**
- `filtered_employees` → Python 原生类型，Streamlit 可直接渲染
- `filter_log` → 每条含 `condition`/`before_count`/`after_count`/`removed_count`，UI 无需重算
- `employee_id` 始终为 `str`（`"JZ0001"`），表格显示正确

### 对接面 2：BasicFilter → Agent①（Task 3 → Task 4.1）

格式转换点在 Task 4.1 脚本中，不在 BasicFilter 内部：

```python
# Task 4.1 中做转换
result = filter.apply(conditions)

# 转换层：records → 临时 CSV（5 行代码，无需通用 Adapter）
temp_csv = output_dir / f"filtered_employees_{timestamp}.csv"
pdf = pd.DataFrame(result["filtered_employees"])
pdf["employee_id"] = pdf["employee_id"].astype(str)  # 🔴 确保 JOIN 类型一致
pdf.to_csv(temp_csv, index=False, encoding="utf-8-sig")

# 传给 Agent①
agent_input = {
    "employees": str(temp_csv),                    # 过滤后的子集
    "performance": "data/raw/performance.csv",     # 全量
    "projects": "data/raw/projects.json",
    "training": "data/raw/training.csv",
    "evaluation_360": "data/raw/evaluation_360.csv",
}
```

**BasicFilter 保证的契约：**
- `filtered_employees` 字段集与 `employees.csv` 一致（13 字段，不做增减）
- `employee_id` 为 `str`，写入 CSV 再读回时 INNER JOIN 不失效

### 对接面 3：BasicFilter → 端到端验证脚本（Task 5.2）

验证脚本将直接调用 BasicFilter 并校验结果完整性。

---

## 七、测试计划

新建 `tests/test_basic_filter.py`，至少 12 个测试：

| # | 测试方法 | 验证点 | 边界值 |
|---|---------|--------|--------|
| 1 | `test_age_range` | 正常区间过滤 | `[30,45]`，25 岁/54 岁应被排除 |
| 2 | `test_political_status` | 多选过滤 | `["中共党员"]`，空列表不过滤 |
| 3 | `test_major_keywords` | 关键词 OR 匹配 | `["计算机", "软件"]`，含特殊字符 |
| 4 | `test_min_years_of_service` | 工龄下限 | `0`(全通过), `5`, `50`(全排除) |
| 5 | `test_level_range` | 数值比较（防字符串序） | `["P5","P8"]`，确保 `P10` 不会误判 |
| 6 | `test_min_performance` | 绩效底线过滤 | `"B"`，检查 2024+2025 两年 |
| 7 | `test_new_employee` | 新员工不够除 | JZ0010（2026 入职）→ `insufficient_data` |
| 8 | `test_combined_conditions` | 多条件叠加 | 年龄+政治面貌+绩效，验证组合结果 |
| 9 | `test_all_filtered_out` | 全部被过滤 | `age_range=[0,0]` → `total_after=0` + 提示 |
| 10 | `test_empty_conditions` | 空条件返回全部 | `{}` → `total_after=100` |
| 11 | `test_unknown_condition` | 不支持的条件 | `{"foo": "bar"}` → `skipped_conditions=["foo"]` |
| 12 | `test_serialization` | numpy 序列化安全 | `json.dumps(result)` 不抛 `TypeError` |

---

## 八、实现步骤

按以下顺序实现：

1. 创建 `filter/__init__.py`（空文件）
2. 实现 `filter/basic_filter.py`：
   - `__init__` → 保存 DataFrame 引用 + 入职年份映射
   - 6 个 `_apply_*` 私有方法（每个独立可测试）
   - `apply()` → 遍历 conditions → 逐条件叠加 → 包装返回
3. 创建 `tests/test_basic_filter.py` → 12 个测试
4. 运行 `python -m pytest tests/test_basic_filter.py -v` 确认全绿
5. 运行 `python -m pytest tests/ -v` 确认原有 28 个测试不退化