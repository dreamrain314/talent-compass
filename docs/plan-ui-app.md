# Task 2.2 Streamlit 过滤层界面 实现计划

> **日期:** 2026-07-22
> **对应:** 第一周开发指南 Task 2.2 — Streamlit 过滤层界面
> **前置依赖:** Task 2.1 (BasicFilter) — 已完成，69/69 测试全绿

---

## 一、修改范围

| 文件 | 操作 | 说明 |
|------|------|------|
| `ui/app.py` | 重构 | 从测试页面升级为步骤化界面，~280 行 |

### 不变的部分

- `main.py` — **不动**（`from ui.app import render; render()` 入口不变）
- `filter/basic_filter.py` — **不动**（UI 作为调用方，直接 import 使用）
- `config.py` — **不动**（UI 引用 config 中的路径常量）

---

## 二、页面布局

```
┌──────────────────────────────────────────────────────────────┐
│  🧭 Talent Compass —— AI驱动的动态胜任力画像与智能人岗匹配系统   │
├─────────────┬────────────────────────────────────────────────┤
│  Sidebar    │  Main Area                                     │
│             │                                                │
│  📋 操作流程 │  Step 1 (step=1):                              │
│  ├ ① 数据上传│    6 个 file_uploader (3×2 网格)              │
│  ├ ② 基础过滤│    数据预览表格 (st.dataframe, 前5行)          │
│  ├ ③ 数据理解│    "确认上传" 按钮                              │
│  ├ ④ 画像生成 │                                                │
│  ├ ⑤ 岗位匹配 │  Step 2 (step=2):                              │
│  └ ⑥ 推荐结果 │    过滤前总人数卡片                             │
│             │    过滤日志 (逐条展示)                           │
│  ─────────  │    过滤后员工表格 (st.dataframe)                 │
│  ⚙️ API 配置 │    岗位序列分布柱状图 (st.bar_chart)            │
│  (API Key)  │    "返回上传" 按钮                               │
│  ─────────  │                                                │
│  🔧 API 调试 │                                                │
│  (折叠区域)  │                                                │
│             │                                                │
│  ─────────  │                                                │
│  🔍 过滤条件 │                                                │
│  (step≥2才   │                                                │
│   显示)      │                                                │
│             │                                                │
└─────────────┴────────────────────────────────────────────────┘
```

---

## 三、步骤流程

### Step 1：数据上传

| 元素 | 组件 | 说明 |
|------|------|------|
| file_uploader × 6 | `st.file_uploader` | 每个文件一个，按 3×2 网格排列 |
| 列名校验 | 内部函数 `_validate_columns()` | 检查上传文件的列名是否完整 |
| 数据预览 | `st.dataframe` | 每个文件展示前 5 行 |
| 确认上传按钮 | `st.button("确认上传")` | 校验通过 → 存入 session_state，step=2 |

**6 个文件上传控件（3 列 × 2 行）：**

```python
col1, col2, col3 = st.columns(3)
with col1:
    emp_file = st.file_uploader("员工基础信息 (employees.csv)", type="csv")
with col2:
    perf_file = st.file_uploader("绩效记录 (performance.csv)", type="csv")
with col3:
    proj_file = st.file_uploader("项目经历 (projects.json)", type="json")
with col1:
    train_file = st.file_uploader("培训记录 (training.csv)", type="csv")
with col2:
    eval_file = st.file_uploader("360评价 (evaluation_360.csv)", type="csv")
```

**列名校验规则：**

```python
_REQUIRED_COLUMNS = {
    "employees.csv": {"employee_id", "name", "age", "gender", "political_status",
                      "education", "major", "department", "job_sequence",
                      "current_position", "current_level", "hire_date", "years_of_service"},
    "performance.csv": {"employee_id", "year", "performance_grade", "performance_comment"},
    "training.csv": {"employee_id", "course_name", "completion_date", "status", "score"},
    "evaluation_360.csv": {"employee_id", "evaluator_id", "evaluator_role", "dimension",
                           "score", "comment", "year"},
}

# projects.json 校验：读取 JSON 后检查第一个元素是否包含所有 key
_PROJECT_REQUIRED_KEYS = {"employee_id", "project_name", "role", "start_date",
                          "end_date", "description", "team_size", "tools_used"}
```

**确认上传逻辑：**

```python
if st.button("确认上传"):
    errors = []
    # 逐个文件校验：存在 + 列名完整
    if not errors:
        # 读取所有文件为 DataFrame/JSON
        st.session_state["employees_df"] = pd.read_csv(emp_file)
        st.session_state["performance_df"] = pd.read_csv(perf_file)
        # ...
        st.session_state["step"] = 2
        st.rerun()
    else:
        for err in errors:
            st.error(err)
```

### Step 2：基础过滤

**侧边栏过滤条件区（step ≥ 2 时显示）：**

| 条件 | 组件 | 映射到 BasicFilter 的 key |
|------|------|--------------------------|
| 年龄区间 | `st.slider("年龄区间", 22, 60, (30, 45))` | `age_range: [min, max]` |
| 政治面貌 | `st.multiselect("政治面貌", options=[...])` | `political_status: [...]` |
| 专业关键词 | `st.text_input("专业关键词")`，逗号分隔 → 列表 | `major_keywords: [...]` |
| 最低工作年限 | `st.number_input("最低工作年限", 0, 50, 0)` | `min_years_of_service: int` |
| 职级范围 | `st.select_slider("职级范围", options=P1-P9, value=(P1,P9))` | `level_range: ["Px","Py"]` |
| 绩效底线 | `st.selectbox("绩效底线", options=["A","B","C","D"], index=1)` | `min_performance: "B"` |

**执行过滤按钮：**

```python
if st.sidebar.button("执行过滤", type="primary"):
    conditions = build_conditions()  # 从 UI 组件取值构建 conditions dict
    filter = BasicFilter(st.session_state["employees_df"],
                         st.session_state["performance_df"])
    result = filter.apply(conditions)
    st.session_state["filter_result"] = result
    # 结果展示在主区域
```

**主区域展示过滤结果：**

```
┌──────────────────────────────────────┐
│  📊 过滤结果                          │
│  过滤前: 100 人  →  过滤后: 42 人     │  ← 卡片
├──────────────────────────────────────┤
│  📋 过滤日志                          │
│  age_range: 100 → 74 (移除 26 人)     │
│  political_status: 74 → 21 (移除 53)  │
│  min_performance: 21 → 7 (移除 14)    │
│  ⚠ insufficient_data: 1 人            │  ← 新员工标记
├──────────────────────────────────────┤
│  🏢 岗位序列分布                       │
│  [bar chart: 技术研发类 10, 管理...]  │
├──────────────────────────────────────┤
│  👥 筛选后员工列表                     │
│  [dataframe: employee_id, name, ...]  │
└──────────────────────────────────────┘
```

**"返回上传"按钮：**

```python
if st.button("← 返回重新上传"):
    st.session_state["step"] = 1
    st.session_state["filter_result"] = None
    st.rerun()
```

---

## 四、session_state 变量定义

```python
# 在 render() 顶部初始化所有 session_state 变量
_SESSION_DEFAULTS = {
    "step": 1,
    "employees_df": None,
    "performance_df": None,
    "projects_data": None,
    "training_df": None,
    "evaluation_360_df": None,
    "filter_result": None,
    "last_model": None,
}

for key, default in _SESSION_DEFAULTS.items():
    if key not in st.session_state:
        st.session_state[key] = default
```

---

## 五、代码结构（render() 函数内部）

```python
def render() -> None:
    # 1. set_page_config + 标题
    st.set_page_config(page_title="Talent Compass", page_icon="🧭", layout="wide")
    st.title("🧭 Talent Compass —— AI驱动的动态胜任力画像与智能人岗匹配系统")

    # 2. 初始化 session_state
    _init_session_state()

    # 3. 侧边栏
    _render_sidebar()

    # 4. 主区域（按步骤）
    if st.session_state["step"] == 1:
        _render_step_upload()
    elif st.session_state["step"] == 2:
        _render_step_filter()
```

为保持 render() 函数结构清晰（不违反 main.py 的入口约定），内部子函数也定义为模块级私有函数（`_render_sidebar()`, `_render_step_upload()` 等），因为：
- 嵌套函数在 Streamlit 重运行时每次都重新定义，影响性能
- 模块级函数只定义一次，Streamlit 重运行时直接调用

---

## 六、与 BasicFilter 的对接

UI 直接调用 BasicFilter，无需中间层：

```python
# 在 _render_step_filter() 中
from filter.basic_filter import BasicFilter

# 构建 conditions dict
conditions = {}
if age_range := st.session_state.get("age_range"):
    conditions["age_range"] = list(age_range)
if political_status := st.session_state.get("political_status"):
    conditions["political_status"] = political_status
# ...

# 调用 BasicFilter
filter = BasicFilter(st.session_state["employees_df"], st.session_state["performance_df"])
result = filter.apply(conditions)

# 展示结果
st.metric("过滤前", result["total_before"])
st.metric("过滤后", result["total_after"])
for log in result["filter_log"]:
    st.write(f"**{log['condition']}**: {log['before_count']} → {log['after_count']} (移除 {log['removed_count']} 人)")
    if "insufficient_data" in log:
        st.caption(f"⚠ 新员工无完整年度数据: {log['insufficient_data']} 人")
if result["skipped_conditions"]:
    st.warning(f"不支持的条件已跳过: {result['skipped_conditions']}")
```

---

## 七、测试方案

Streamlit UI 无法用 pytest 直接测试（`st.*` 函数只在 Streamlit 运行时中可用）。验证方式：

### 自动化测试（`tests/test_ui_app.py`）

```python
"""验证 ui/app.py 的模块级函数可被正确导入"""
import pytest

def test_import_render():
    """render() 函数可导入（不调用 st.*，仅验证导入路径）"""
    from ui.app import render
    assert callable(render)
```

### 手动验收清单

```bash
streamlit run main.py
```

| 验收项 | 操作 | 预期结果 |
|--------|------|---------|
| 页面加载 | 打开浏览器 | 标题显示"Talent Compass"，非"Streamlit" |
| Step 1 上传 | 逐个上传 6 个文件 | 每个文件显示数据预览表格 |
| 列名校验 | 上传列名错误的文件 | 显示错误提示，阻止进入下一步 |
| 确认上传 | 点击"确认上传" | 进入 Step 2，过滤条件区出现 |
| 过滤条件 | 设置年龄 [30,45] + 中共党员 | 侧边栏显示已选值 |
| 执行过滤 | 点击"执行过滤" | 显示过滤结果表格 + 日志 + 分布图 |
| 全部过滤 | 年龄 [0,0] 过滤 | 显示"建议放宽条件"提示 |
| 返回上传 | 点击"返回重新上传" | 回到 Step 1，数据保留 |
| API 调试 | 侧边栏展开"API 调试" | 可发送测试消息 |
| 侧边栏 Key | 输入 API Key | 可正常使用 |

---

## 八、实现步骤

按以下顺序实现：

1. 备份当前 `ui/app.py`（`cp ui/app.py ui/app_test_page_backup.py`）
2. 在 `ui/app.py` 中保留 `render()` 函数结构，**完全替换主区域代码**
3. 实现 `_init_session_state()` — 初始化所有 session_state 变量
4. 实现 `_render_sidebar()` — 步骤指示器 + API 配置 + API 调试折叠区
5. 实现 `_render_step_upload()` — 6 个 file_uploader + 列名校验 + 确认按钮
6. 实现 `_render_step_filter()` — 侧边栏过滤条件 + 结果展示
7. 运行 `python -m pytest tests/test_ui_app.py -v`（仅验证导入不崩溃）
8. 手动验收：`streamlit run main.py`，走通完整流程

---

## 九、注意事项

### 🔴 关键约束（来自指南）

1. **必须保留 `def render() -> None:` 函数结构** — `main.py` 依赖此入口
2. **测试页面内容必须完全替换，不能保留** — 主区域的 text_area + send 按钮必须删干净，不能放在旁边或作为"调试控制台"
3. **API 测试功能移到侧边栏折叠区** — `st.expander("🔧 API 调试", expanded=False)`
4. **保留侧边栏 API Key 配置** — 已有的 text_input + "应用 Key 变更"按钮不动

### 🟡 常见陷阱

1. **Streamlit 重运行**：点击按钮后整个脚本重运行，所有 `st.*` 重新执行 → 必须用 `st.session_state` 持久化数据
2. **文件上传编码**：`pd.read_csv(uploaded_file)` 直接接受文件对象，无需写临时文件
3. **JSON 上传**：`st.file_uploader(type="json")` 上传后读取：`json.load(uploaded_file)`
4. **rerun 循环**：点击"确认上传"后 `st.rerun()` 确保立即切换到 Step 2
5. **第一次打开**：session_state 中无数据 → 侧边栏过滤条件区不显示（step=1）