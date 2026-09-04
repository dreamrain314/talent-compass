"""Talent Compass - Streamlit 过滤层界面

步骤化界面：
  Step 1: 数据上传（6 个文件）
  Step 2: 基础过滤（调用 BasicFilter）
  Step 3-6: 为后续 Task 预留

使用模块级私有函数模式（而非嵌套函数），
避免 Streamlit 重运行时重复定义。

入口由 main.py 调用 render()。
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from typing import Any

import pandas as pd
import streamlit as st

from utils.data_quality import check_data_quality

logger = logging.getLogger(__name__)

# ── 列名校验常量（单一来源，参见 CLAUDE.md D2）──────────────────────────────
_REQUIRED_COLUMNS: dict[str, set[str]] = {
    "employees.csv": {
        "employee_id", "name", "age", "gender", "political_status",
        "education", "major", "department", "job_sequence",
        "current_position", "current_level", "hire_date",
        "years_of_service", "certificates",
    },
    "performance.csv": {
        "employee_id", "year", "performance_grade", "performance_comment",
    },
    "training.csv": {
        "employee_id", "course_name", "completion_date", "status", "score",
    },
    "evaluation_360.csv": {
        "employee_id", "evaluator_id", "evaluator_role", "dimension",
        "score", "comment", "year",
    },
}

_PROJECT_REQUIRED_KEYS: set[str] = {
    "employee_id", "project_name", "role", "start_date",
    "end_date", "description", "team_size", "tools_used",
}

# ── 会话默认值 ────────────────────────────────────────────────────────────────
_SESSION_DEFAULTS: dict[str, Any] = {
    "step": 1,
    "employees_df": None,
    "performance_df": None,
    "projects_data": None,
    "training_df": None,
    "evaluation_360_df": None,
    "filter_result": None,
    "data_quality": None,
    "last_model": None,
    "text_summaries": {},        # {employee_id: {text_summaries, anchors, ...}}
    "text_summary_status": {},   # {employee_id: "pending"|"running"|"done"|"error"}
    "selected_employee": None,   # 当前选中的员工 ID
}

# ── 步骤配置 ─────────────────────────────────────────────────────────────────
_STEPS = [
    ("①", "数据上传"),
    ("②", "基础过滤"),
    ("③", "数据质量"),
    ("④", "文本摘要"),
    ("⑤", "360评价"),
    ("⑥", "画像生成"),
    ("⑦", "岗位匹配"),
    ("⑧", "推荐结果"),
]

# ── 政治面貌选项（单一来源，后续可统一到 config）────────────────────────────
_POLITICAL_OPTIONS = ["中共党员", "共青团员", "群众", "民主党派"]

# ── 职级选项 ─────────────────────────────────────────────────────────────────
_LEVEL_OPTIONS = [f"P{i}" for i in range(1, 10)]

# ── 绩效选项 ─────────────────────────────────────────────────────────────────
_PERFORMANCE_OPTIONS = ["A", "B", "C", "D"]


# ═══════════════════════════════════════════════════════════════════════════════
# 模块级私有函数
# ═══════════════════════════════════════════════════════════════════════════════


def _init_session_state() -> None:
    """初始化所有 session_state 变量（幂等，可重复调用）。"""
    for key, default in _SESSION_DEFAULTS.items():
        if key not in st.session_state:
            st.session_state[key] = default


def _render_sidebar() -> None:
    """渲染侧边栏：步骤指示器 + API 配置 + API 调试 + 过滤条件（step≥2）。"""
    with st.sidebar:
        # ── 步骤指示器 ──
        st.markdown("### 📋 操作流程")
        current_step = st.session_state.get("step", 1)
        for i, (icon, label) in enumerate(_STEPS):
            step_num = i + 1
            if step_num == current_step:
                st.markdown(f"**{icon} {label}** ← 当前")
            elif step_num < current_step:
                st.markdown(f"~~{icon} {label}~~ ✅")
            else:
                st.markdown(f"{icon} {label}")

        st.divider()

        # ── API 配置 ──
        st.markdown("### ⚙️ API 配置")
        api_key = st.text_input(
            "DeepSeek API Key",
            type="password",
            value=os.getenv("DEEPSEEK_API_KEY", ""),
            help="输入你的 DeepSeek API Key，修改后点下方按钮生效",
        )
        if api_key:
            os.environ["DEEPSEEK_API_KEY"] = api_key

        if st.button("🔄 应用 Key 变更", use_container_width=True,
                     help="修改 Key 后点击此按钮，强制重建 API 客户端"):
            try:
                from utils.llm_client import reset_client
                reset_client()
                st.success("已切换到新 Key")
            except Exception as exc:
                st.error(f"切换失败: {exc}")

        if api_key:
            masked = "..." + str(api_key)[-4:] if len(str(api_key)) > 4 else str(api_key)
            st.caption(f"当前 Key: {masked}")
        else:
            st.caption("未设置 API Key")

        st.divider()

        # ── API 调试（折叠区）──
        with st.expander("🔧 API 调试", expanded=False):
            _render_api_debug()

        # ── 过滤条件（step ≥ 2 时显示）──
        if st.session_state.get("step", 1) >= 2:
            st.divider()
            st.markdown("### 🔍 过滤条件")
            _render_filter_conditions()


def _render_api_debug() -> None:
    """侧边栏折叠区中的 API 调试功能。"""
    debug_input = st.text_area(
        "测试消息",
        placeholder="输入你想发给AI的消息...",
        height=100,
        key="debug_input",
    )
    if st.button("🚀 发送测试", type="primary", use_container_width=True, key="debug_send"):
        api_key = os.getenv("DEEPSEEK_API_KEY", "")
        if not api_key:
            st.error("请先设置 API Key")
        elif not debug_input:
            st.warning("请输入测试消息")
        else:
            with st.spinner("正在调用 API..."):
                try:
                    from utils.llm_client import call_llm
                    result = call_llm(
                        prompt=debug_input,
                        system_prompt="你是一个HR领域的AI助手。请用中文简洁回答用户的问题。",
                    )
                    if result.get("error"):
                        st.error(f"API 调用失败: {result['error']}")
                    elif result.get("error") is None:
                        st.session_state["last_model"] = result.get("model", "N/A")
                        st.success("API 调用成功")
                        if result.get("content"):
                            st.markdown("### AI 回复")
                            st.info(result["content"])
                        else:
                            st.caption("（AI 返回了空内容）")
                        st.caption(
                            f"模型：{result.get('model', 'N/A')}  |  "
                            f"Prompt Token：{result.get('usage', {}).get('prompt_tokens', 0)}  |  "
                            f"Completion Token：{result.get('usage', {}).get('completion_tokens', 0)}"
                        )
                    else:
                        st.warning(f"未知响应: {result}")
                except Exception as e:
                    import traceback
                    st.error(f"调用异常: {e}")
                    with st.expander("详细错误信息"):
                        st.code(traceback.format_exc())


def _render_filter_conditions() -> None:
    """侧边栏过滤条件区（step ≥ 2 时显示）。"""
    # 年龄区间
    st.session_state["age_range"] = st.slider(
        "年龄区间", 22, 60, (30, 45),
        key="filter_age_range",
    )

    # 政治面貌
    st.session_state["political_status"] = st.multiselect(
        "政治面貌",
        options=_POLITICAL_OPTIONS,
        default=[],
        key="filter_political",
    )

    # 专业关键词
    kw_text = st.text_input(
        "专业关键词（逗号分隔）",
        placeholder="如: 计算机, 软件, 自动化",
        key="filter_major_kw",
    )
    if kw_text and kw_text.strip():
        st.session_state["major_keywords"] = [kw.strip() for kw in kw_text.split(",") if kw.strip()]
    else:
        st.session_state["major_keywords"] = []

    # 最低工作年限
    st.session_state["min_years_of_service"] = st.number_input(
        "最低工作年限", 0, 50, 0,
        key="filter_min_years",
    )

    # 职级范围
    st.session_state["level_range"] = st.select_slider(
        "职级范围",
        options=_LEVEL_OPTIONS,
        value=("P1", "P9"),
        key="filter_level",
    )

    # 绩效底线
    st.session_state["min_performance"] = st.selectbox(
        "绩效底线",
        options=_PERFORMANCE_OPTIONS,
        index=1,
        key="filter_perf",
    )

    # 执行过滤按钮
    if st.button("▶ 执行过滤", type="primary", use_container_width=True, key="btn_exec_filter"):
        _execute_filter()


def _execute_filter() -> None:
    """从 session_state 构建 conditions 并调用 BasicFilter。"""
    conditions: dict[str, Any] = {}

    # 年龄区间
    age_range = st.session_state.get("age_range")
    if age_range:
        conditions["age_range"] = list(age_range)

    # 政治面貌
    political_status = st.session_state.get("political_status", [])
    if political_status:
        conditions["political_status"] = political_status

    # 专业关键词
    major_keywords = st.session_state.get("major_keywords", [])
    if major_keywords:
        conditions["major_keywords"] = major_keywords

    # 最低工作年限
    min_years = st.session_state.get("min_years_of_service", 0)
    if min_years > 0:
        conditions["min_years_of_service"] = int(min_years)

    # 职级范围
    level_range = st.session_state.get("level_range")
    if level_range:
        conditions["level_range"] = list(level_range)

    # 绩效底线
    min_perf = st.session_state.get("min_performance")
    if min_perf:
        conditions["min_performance"] = str(min_perf)

    # 获取数据
    employees_df = st.session_state.get("employees_df")
    performance_df = st.session_state.get("performance_df")
    if employees_df is None or performance_df is None:
        st.error("数据未加载，请先返回上传页面重新上传")
        return

    # 调用 BasicFilter
    from filter.basic_filter import BasicFilter
    filter_ = BasicFilter(employees_df, performance_df)
    result = filter_.apply(conditions)

    # 存入 session_state
    st.session_state["filter_result"] = result
    st.rerun()


def _render_step_upload() -> None:
    """主区域 Step 1：数据上传。"""
    st.markdown("## Step 1：数据上传")
    st.caption("请上传以下 6 个数据文件，系统将自动校验列名完整性。")

    errors: list[str] = []

    # 文件上传（3 列 × 2 行）
    col1, col2, col3 = st.columns(3)

    with col1:
        emp_file = st.file_uploader(
            "员工基础信息 (employees.csv)", type="csv",
            key="upload_emp",
        )
    with col2:
        perf_file = st.file_uploader(
            "绩效记录 (performance.csv)", type="csv",
            key="upload_perf",
        )
    with col3:
        proj_file = st.file_uploader(
            "项目经历 (projects.json)", type="json",
            key="upload_proj",
        )
    with col1:
        train_file = st.file_uploader(
            "培训记录 (training.csv)", type="csv",
            key="upload_train",
        )
    with col2:
        eval_file = st.file_uploader(
            "360评价 (evaluation_360.csv)", type="csv",
            key="upload_eval",
        )

    # ── 数据预览 ──
    _render_upload_previews(emp_file, perf_file, proj_file, train_file, eval_file)

    # ── 确认上传按钮 ──
    if st.button("✅ 确认上传", type="primary", use_container_width=True, key="btn_confirm_upload"):
        errors = _validate_uploads(emp_file, perf_file, proj_file, train_file, eval_file)
        if not errors:
            _load_uploaded_data(emp_file, perf_file, proj_file, train_file, eval_file)
            st.session_state["step"] = 2
            st.rerun()
        else:
            for err in errors:
                st.error(err)


def _render_upload_previews(
    emp_file: Any, perf_file: Any, proj_file: Any,
    train_file: Any, eval_file: Any,
) -> None:
    """展示已上传文件的数据预览（前 5 行）。"""
    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**📄 文件预览**")
        if emp_file:
            try:
                df = pd.read_csv(emp_file)
                st.dataframe(df.head(5), use_container_width=True)
                emp_file.seek(0)  # 重置文件指针
            except Exception as e:
                st.caption(f"employees.csv 预览失败: {e}")
        if perf_file:
            try:
                df = pd.read_csv(perf_file)
                st.dataframe(df.head(5), use_container_width=True)
                perf_file.seek(0)
            except Exception as e:
                st.caption(f"performance.csv 预览失败: {e}")
        if train_file:
            try:
                df = pd.read_csv(train_file)
                st.dataframe(df.head(5), use_container_width=True)
                train_file.seek(0)
            except Exception as e:
                st.caption(f"training.csv 预览失败: {e}")

    with col2:
        st.markdown("&nbsp;")
        if eval_file:
            try:
                df = pd.read_csv(eval_file)
                st.dataframe(df.head(5), use_container_width=True)
                eval_file.seek(0)
            except Exception as e:
                st.caption(f"evaluation_360.csv 预览失败: {e}")
        if proj_file:
            try:
                data = json.load(proj_file)
                if isinstance(data, list) and len(data) > 0:
                    preview_df = pd.DataFrame(data[:5])
                    st.dataframe(preview_df, use_container_width=True)
                proj_file.seek(0)
            except Exception as e:
                st.caption(f"projects.json 预览失败: {e}")


def _validate_uploads(
    emp_file: Any, perf_file: Any, proj_file: Any,
    train_file: Any, eval_file: Any,
) -> list[str]:
    """校验上传文件的列名完整性。

    Returns:
        错误信息列表，空列表表示全部通过。
    """
    errors: list[str] = []

    # 检查文件是否全部上传
    file_map = {
        "employees.csv": emp_file,
        "performance.csv": perf_file,
        "projects.json": proj_file,
        "training.csv": train_file,
        "evaluation_360.csv": eval_file,
    }
    for name, f in file_map.items():
        if f is None:
            errors.append(f"缺少文件: {name}")

    # 列名校验（CSV 文件）
    csv_checks = [
        ("employees.csv", emp_file, _REQUIRED_COLUMNS["employees.csv"]),
        ("performance.csv", perf_file, _REQUIRED_COLUMNS["performance.csv"]),
        ("training.csv", train_file, _REQUIRED_COLUMNS["training.csv"]),
        ("evaluation_360.csv", eval_file, _REQUIRED_COLUMNS["evaluation_360.csv"]),
    ]
    for name, f, required_cols in csv_checks:
        if f is None:
            continue
        try:
            f.seek(0)
            df = pd.read_csv(f)
            actual_cols = set(df.columns)
            missing = required_cols - actual_cols
            if missing:
                errors.append(f"{name} 缺少列: {', '.join(sorted(missing))}")
            f.seek(0)
        except Exception as e:
            errors.append(f"{name} 读取失败: {e}")

    # projects.json 校验
    if proj_file is not None:
        try:
            proj_file.seek(0)
            data = json.load(proj_file)
            if not isinstance(data, list):
                errors.append("projects.json 格式错误：应为 JSON 数组")
            elif len(data) == 0:
                errors.append("projects.json 为空数组")
            else:
                first = data[0]
                if not isinstance(first, dict):
                    errors.append("projects.json 元素应为对象")
                else:
                    missing = _PROJECT_REQUIRED_KEYS - set(first.keys())
                    if missing:
                        errors.append(f"projects.json 缺少字段: {', '.join(sorted(missing))}")
            proj_file.seek(0)
        except json.JSONDecodeError as e:
            errors.append(f"projects.json 解析失败: {e}")
        except Exception as e:
            errors.append(f"projects.json 读取失败: {e}")

    return errors


def _load_uploaded_data(
    emp_file: Any, perf_file: Any, proj_file: Any,
    train_file: Any, eval_file: Any,
) -> None:
    """将上传文件读入 DataFrame 并存入 session_state。"""
    try:
        emp_file.seek(0)
        st.session_state["employees_df"] = pd.read_csv(emp_file)
    except Exception as e:
        st.error(f"employees.csv 加载失败: {e}")
        return

    try:
        perf_file.seek(0)
        st.session_state["performance_df"] = pd.read_csv(perf_file)
    except Exception as e:
        st.error(f"performance.csv 加载失败: {e}")
        return

    try:
        proj_file.seek(0)
        st.session_state["projects_data"] = json.load(proj_file)
    except Exception as e:
        st.error(f"projects.json 加载失败: {e}")
        return

    try:
        train_file.seek(0)
        st.session_state["training_df"] = pd.read_csv(train_file)
    except Exception as e:
        st.error(f"training.csv 加载失败: {e}")
        return

    try:
        eval_file.seek(0)
        st.session_state["evaluation_360_df"] = pd.read_csv(eval_file)
    except Exception as e:
        st.error(f"evaluation_360.csv 加载失败: {e}")
        return

    st.success("所有文件加载成功！")


# ── Step 3: 数据质量报告 ──────────────────────────────────────────────────────


def _check_and_store_data_quality() -> None:
    """从 session_state 构建 dfs → check_data_quality → 存入 session_state。"""
    employees_df = st.session_state.get("employees_df")
    performance_df = st.session_state.get("performance_df")
    projects_data = st.session_state.get("projects_data")
    training_df = st.session_state.get("training_df")
    evaluation_360_df = st.session_state.get("evaluation_360_df")

    if employees_df is None:
        return

    # 构建 dfs 字典
    dfs = {"employees": employees_df}

    if performance_df is not None:
        dfs["performance"] = performance_df
    if projects_data is not None:
        dfs["projects"] = pd.DataFrame(projects_data) if isinstance(projects_data, list) else pd.DataFrame()
    if training_df is not None:
        dfs["training"] = training_df
    if evaluation_360_df is not None:
        dfs["evaluation_360"] = evaluation_360_df

    try:
        report = check_data_quality(dfs)
        st.session_state["data_quality"] = report
    except Exception as e:
        st.session_state["data_quality"] = {"_error": str(e)}


def _render_missing_table(missing_list: list[dict], title: str) -> None:
    """渲染单文件的缺失值统计表格。"""
    if not missing_list:
        return

    with st.expander(f"📄 {title}", expanded=False):
        rows = []
        for m in missing_list:
            missing = m["missing"]
            rate_pct = round(m["rate"] * 100, 1)
            if m["level"] == "none":
                icon = "🟢"
                tag = "无"
            elif m["level"] == "low":
                icon = "🟡"
                tag = "轻度"
            else:
                icon = "🔴"
                tag = "严重"
            rows.append({
                "列名": m["column"],
                "缺失数": missing,
                "缺失率": f"{rate_pct}%",
                "状态": f"{icon} {tag}",
            })

        df_show = pd.DataFrame(rows)
        st.dataframe(df_show, use_container_width=True, hide_index=True)


def _render_issues_section(issues: list[dict], title: str, icon: str) -> None:
    """渲染类型/范围异常列表。"""
    if not issues:
        st.success(f"✅ 未发现 {title}")
        return

    st.warning(f"{icon} 发现 {len(issues)} 项{title}")
    for issue in issues:
        detail = " | ".join(f"{k}={v}" for k, v in issue.items())
        st.caption(f"  • {detail}")


def _render_step_data_quality() -> None:
    """主区域 Step 3：数据质量报告。"""
    st.markdown("## Step 3：数据质量报告")

    # 检查数据是否已上传
    employees_df = st.session_state.get("employees_df")
    if employees_df is None:
        st.info("请先上传数据")
        if st.button("← 返回上传", use_container_width=True, key="btn_dq_back_upload"):
            st.session_state["step"] = 1
            st.rerun()
        return

    # 检查数据质量报告
    report = st.session_state.get("data_quality")
    if report is None:
        with st.spinner("正在分析数据质量..."):
            _check_and_store_data_quality()
        report = st.session_state.get("data_quality")
        st.rerun()
        return

    if isinstance(report, dict) and "_error" in report:
        st.error(f"数据质量分析失败: {report['_error']}")
        return

    # ── 数据源概览 ──
    st.markdown("### 📊 数据源概览")
    summaries = report.get("file_summaries", [])
    cols = st.columns(len(summaries) if summaries else 1)
    for i, summary in enumerate(summaries):
        with cols[i]:
            name = summary.get("name", "?")
            status = summary.get("status", "ok")
            icon_map = {"ok": "✅", "warning": "⚠️", "error": "❌", "empty": "⬜"}
            st.metric(
                label=f"{icon_map.get(status, '❓')} {name}",
                value=f"{summary.get('records', 0)} 条记录",
                help=f"完整率: {summary.get('complete_pct', 100)}%",
            )

    # ── 缺失值详情 ──
    st.markdown("### 🔍 缺失值详情")
    missing_details = report.get("missing_details", {})
    if missing_details:
        for file_name, missing_list in missing_details.items():
            _render_missing_table(missing_list, file_name)
    else:
        st.info("无缺失值数据（文件可能为空）")

    # ── 类型异常 ──
    st.markdown("### ⚠️ 类型异常")
    type_issues = report.get("type_issues", [])
    _render_issues_section(type_issues, "类型异常", "⚠️")

    # ── 范围异常 ──
    st.markdown("### 🚨 范围异常")
    range_issues = report.get("range_issues", [])
    _render_issues_section(range_issues, "范围异常", "🚨")

    # ── 严重缺失预警 ──
    st.markdown("### 👥 严重缺失预警")
    severe_ids = report.get("severe_missing_employees", [])
    if severe_ids:
        st.error(f"🔴 {len(severe_ids)} 名员工基础字段缺失率 > 50%")
        for sid in severe_ids:
            st.caption(f"  • {sid}")
    else:
        st.success("✅ 无严重缺失员工")

    # ── 文本不足预警 ──
    st.markdown("### 📝 文本数据预警")
    text_count = report.get("text_insufficient_count", 0)
    text_ids = report.get("text_insufficient_ids", [])
    if text_count > 0:
        st.warning(f"🟡 {text_count} 名员工缺少绩效/项目/360评论文本")
        if len(text_ids) <= 20:
            for tid in text_ids:
                st.caption(f"  • {tid}")
        else:
            st.caption(f"  前 20 名: {', '.join(text_ids[:20])}...")
    else:
        st.success("✅ 所有员工均有可用文本数据")

    # ── 导航按钮 ──
    st.divider()
    col1, col2 = st.columns([1, 1])
    with col1:
        if st.button("← 返回过滤", use_container_width=True, key="btn_dq_back_filter"):
            st.session_state["step"] = 2
            st.session_state["data_quality"] = None  # 下次进入重新分析
            st.rerun()
    with col2:
        if st.button("下一步 → 文本摘要", use_container_width=True, key="btn_dq_next_summary"):
            st.session_state["step"] = 4
            st.session_state["selected_employee"] = None
            st.rerun()


def _render_step_filter() -> None:
    """主区域 Step 2：基础过滤结果展示。"""
    st.markdown("## Step 2：基础过滤")

    result = st.session_state.get("filter_result")

    if result is None:
        st.info("请在左侧边栏设置过滤条件，然后点击「执行过滤」。")
        return

    if result.get("error"):
        st.error(f"过滤执行出错: {result['error']}")
        return

    total_before = result.get("total_before", 0)
    total_after = result.get("total_after", 0)

    # 人数卡片
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("过滤前总人数", total_before)
    with col2:
        st.metric("过滤后总人数", total_after)
    with col3:
        ratio = f"{total_after / total_before * 100:.1f}%" if total_before > 0 else "N/A"
        st.metric("保留比例", ratio)

    # 过滤日志
    filter_log = result.get("filter_log", [])
    if filter_log:
        st.markdown("### 📋 过滤日志")
        for log in filter_log:
            condition = log.get("condition", "unknown")
            before = log.get("before_count", 0)
            after = log.get("after_count", 0)
            removed = log.get("removed_count", 0)
            st.write(f"- **{condition}**: {before} → {after} (移除 {removed} 人)")
            if "insufficient_data" in log:
                st.caption(f"  ⚠ 新员工无完整年度数据: {log['insufficient_data']} 人")
            note = log.get("note")
            if note:
                st.warning(note)

    # 跳过条件提示
    skipped = result.get("skipped_conditions", [])
    if skipped:
        st.warning(f"不支持的条件已跳过: {', '.join(skipped)}")

    # 岗位序列分布柱状图
    filtered_employees = result.get("filtered_employees", [])
    if filtered_employees:
        st.markdown("### 🏢 岗位序列分布")
        df_result = pd.DataFrame(filtered_employees)
        if "job_sequence" in df_result.columns:
            seq_counts = df_result["job_sequence"].value_counts()
            st.bar_chart(seq_counts)
        else:
            st.caption("（数据中无 job_sequence 字段）")

        # 筛选后员工列表
        st.markdown("### 👥 筛选后员工列表")
        display_cols = ["employee_id", "name", "age", "department",
                        "job_sequence", "current_position", "current_level"]
        available_cols = [c for c in display_cols if c in df_result.columns]
        st.dataframe(df_result[available_cols], use_container_width=True)
    else:
        st.caption("（无符合条件的员工）")

    # 导航按钮
    st.divider()
    col_back, col_next = st.columns([1, 1])
    with col_back:
        if st.button("← 返回重新上传", use_container_width=True, key="btn_back_upload"):
            st.session_state["step"] = 1
            st.session_state["filter_result"] = None
            st.rerun()
    with col_next:
        if st.button("下一步 → 数据质量报告", use_container_width=True, key="btn_next_quality"):
            st.session_state["step"] = 3
            st.session_state["data_quality"] = None  # 进入时重新分析
            st.rerun()


def _render_step_text_summary() -> None:
    """主区域 Step 4：LLM 文本摘要与原文对照视图。

    展示已过滤员工的非结构化文本（绩效评语/项目描述/360评价），
    支持逐员工调用 LLM 生成摘要，并提供原文↔摘要对照。
    """
    st.markdown("## Step 4：文本语义理解")
    st.caption("对员工绩效评语、项目描述和 360 评价进行 LLM 摘要，查看原文与摘要对照。")

    # 检查数据
    employees_df = st.session_state.get("employees_df")
    performance_df = st.session_state.get("performance_df")
    projects_data = st.session_state.get("projects_data")
    evaluation_360_df = st.session_state.get("evaluation_360_df")
    if employees_df is None:
        st.info("请先上传数据")
        if st.button("← 返回上传", use_container_width=True, key="btn_ts_back_upload"):
            st.session_state["step"] = 1
            st.rerun()
        return

    # 获取员工列表（优先用过滤后的，否则用全部）
    filter_result = st.session_state.get("filter_result")
    if filter_result and filter_result.get("filtered_employees"):
        emp_ids = [e["employee_id"] for e in filter_result["filtered_employees"]]
        emp_names = {str(e["employee_id"]): e.get("name", "?") for e in filter_result["filtered_employees"]}
    else:
        emp_ids = employees_df["employee_id"].astype(str).tolist()
        emp_names = dict(zip(
            employees_df["employee_id"].astype(str),
            employees_df.get("name", employees_df["employee_id"]).astype(str),
        ))

    if not emp_ids:
        st.warning("无可用员工数据")
        if st.button("← 返回过滤", use_container_width=True, key="btn_ts_back_filter"):
            st.session_state["step"] = 2
            st.rerun()
        return

    # ── 员工选择器 ──
    col_sel, col_info = st.columns([2, 1])
    with col_sel:
        emp_options = {f"{eid} - {emp_names.get(eid, '?')}": eid for eid in emp_ids}
        selected_label = st.selectbox(
            "👤 选择员工",
            options=list(emp_options.keys()),
            key="ts_employee_selector",
        )
        selected_emp_id = emp_options[selected_label]
        st.session_state["selected_employee"] = selected_emp_id

    # 检查该员工是否已有摘要
    summaries = st.session_state.setdefault("text_summaries", {})
    summary_status = st.session_state.setdefault("text_summary_status", {})

    # ── 收集该员工的文本数据 ──
    emp_id = selected_emp_id
    perf_text = _collect_employee_text(performance_df, emp_id, "performance_comment", "; ")
    proj_text = _collect_project_text(projects_data, emp_id)
    eval_text = _collect_employee_text(evaluation_360_df, emp_id, "comment", "; ")

    has_text = bool(perf_text or proj_text or eval_text)

    with col_info:
        if summary_status.get(emp_id) == "done":
            st.success("✅ 摘要已生成")
        elif summary_status.get(emp_id) == "running":
            st.info("🔄 生成中...")
        elif not has_text:
            st.warning("⚠️ 无文本数据")
        else:
            st.caption("点击下方按钮生成摘要")

    # ── 原文展示 ──
    st.markdown("### 📄 原文数据")
    tab1, tab2, tab3 = st.tabs(["📝 绩效评语", "🏗 项目经历", "👥 360 评价"])

    with tab1:
        if perf_text:
            st.text_area("绩效评语原文", value=perf_text, height=120, disabled=True, key=f"perf_{emp_id}")
        else:
            st.caption("（无绩效评语文本）")

    with tab2:
        if proj_text:
            st.text_area("项目描述原文", value=proj_text, height=120, disabled=True, key=f"proj_{emp_id}")
        else:
            st.caption("（无项目描述文本）")

    with tab3:
        if eval_text:
            st.text_area("360评价原文", value=eval_text, height=120, disabled=True, key=f"eval_{emp_id}")
        else:
            st.caption("（无360评价文本）")

    # ── 生成/摘要展示 ──
    st.divider()
    st.markdown("### 🤖 LLM 摘要")

    emp_summary = summaries.get(emp_id)
    status = summary_status.get(emp_id, "pending")

    if status == "running":
        st.info("正在调用 LLM 生成摘要，请稍候...")
        _run_single_summary(emp_id, perf_text, proj_text, eval_text)
        st.rerun()

    elif emp_summary and emp_summary.get("error") is None:
        _render_summary_comparison(emp_summary)

    elif emp_summary and emp_summary.get("error"):
        st.error(f"摘要生成失败: {emp_summary['error']}")
        if st.button("🔄 重试", key=f"retry_{emp_id}"):
            summary_status[emp_id] = "pending"
            summaries.pop(emp_id, None)
            st.rerun()

    if status != "done" and has_text:
        if st.button("📄 生成摘要", type="primary", key=f"gen_{emp_id}"):
            summary_status[emp_id] = "running"
            st.rerun()

    # ── 质量标记汇总 ──
    if emp_summary and emp_summary.get("error") is None:
        st.divider()
        st.markdown("### 📊 质量标记")
        col_q1, col_q2, col_q3 = st.columns(3)
        with col_q1:
            if emp_summary.get("anchor_mismatch"):
                st.error("🔴 锚点失配")
            else:
                st.success("✅ 锚点匹配")
        with col_q2:
            hf = emp_summary.get("hallucination_flags", {})
            if hf:
                st.warning(f"⚠️ {len(hf)} 项摘要长度异常")
                for k, v in hf.items():
                    st.caption(f"  • {k}: {v}")
            else:
                st.success("✅ 摘要长度正常")
        with col_q3:
            model = emp_summary.get("model", "N/A")
            tokens = emp_summary.get("tokens", 0)
            st.metric("模型", model)
            st.metric("Token 消耗", tokens)

    # ── 导航按钮 ──
    st.divider()
    col_back, col_next = st.columns([1, 1])
    with col_back:
        if st.button("← 返回数据质量", use_container_width=True, key="btn_ts_back_dq"):
            st.session_state["step"] = 3
            st.rerun()
    with col_next:
        if st.button("下一步 → 360评价", use_container_width=True, key="btn_ts_next_360"):
            st.session_state["step"] = 5
            st.session_state["selected_employee"] = None
            st.rerun()


def _collect_employee_text(df, emp_id: str, column: str, separator: str = "; ") -> str:
    """从 DataFrame 中收集某员工的指定文本列，用分隔符连接。"""
    if df is None or df.empty:
        return ""
    emp_str = str(emp_id)
    subset = df[df["employee_id"].astype(str) == emp_str]
    if column not in subset.columns:
        return ""
    texts = subset[column].dropna().astype(str).tolist()
    return separator.join(texts) if texts else ""


def _collect_project_text(projects_data, emp_id: str) -> str:
    """从 projects_data（list[dict] 或 DataFrame）收集某员工的项目描述。"""
    if projects_data is None:
        return ""
    emp_str = str(emp_id)
    descs = []
    if isinstance(projects_data, list):
        for p in projects_data:
            if str(p.get("employee_id", "")) == emp_str:
                desc = p.get("description", "")
                if desc:
                    descs.append(str(desc))
    elif isinstance(projects_data, pd.DataFrame):
        subset = projects_data[projects_data["employee_id"].astype(str) == emp_str]
        if "description" in subset.columns:
            descs = subset["description"].dropna().astype(str).tolist()
    return "; ".join(descs) if descs else ""


def _run_single_summary(emp_id: str, perf_text: str, proj_text: str, eval_text: str) -> None:
    """对单个员工调用 LLM 生成摘要，并将结果存入 session_state。"""
    from utils.llm_summarizer import summarize_employee_texts

    summaries = st.session_state.setdefault("text_summaries", {})
    status = st.session_state.setdefault("text_summary_status", {})

    try:
        result = summarize_employee_texts(emp_id, perf_text, proj_text, eval_text)
        summaries[emp_id] = result
        status[emp_id] = "done" if result.get("error") is None else "error"
    except Exception as e:
        logger.error("_run_single_summary 异常: %s", e)
        summaries[emp_id] = {"error": str(e)}
        status[emp_id] = "error"


def _render_summary_comparison(emp_summary: dict) -> None:
    """渲染摘要结果与质量标记。"""
    summaries = emp_summary.get("text_summaries") or {}
    anchors = emp_summary.get("anchors") or {}

    col_s1, col_s2, col_s3 = st.columns(3)
    with col_s1:
        st.markdown("**绩效摘要**")
        st.info(summaries.get("performance_summary", "（空）") or "（空）")
    with col_s2:
        st.markdown("**项目摘要**")
        st.info(summaries.get("project_summary", "（空）") or "（空）")
    with col_s3:
        st.markdown("**评价摘要**")
        st.info(summaries.get("evaluation_summary", "（空）") or "（空）")

    # 锚点展示（折叠区）
    with st.expander("🔗 锚点详情", expanded=False):
        for key, anchor_list in anchors.items():
            if anchor_list and isinstance(anchor_list, list):
                st.markdown(f"**{key}** ({len(anchor_list)} 个锚点)")
                for a in anchor_list[:10]:  # 最多显示 10 个
                    # st.code 不支持 line_height/line_limit（Streamlit 1.51 签名仅 body/language/line_numbers/wrap_lines/height/width）；
                    # a[:80] 已截断长度，锚点单行短语无需额外行高控制
                    st.code(a[:80])
                if len(anchor_list) > 10:
                    st.caption(f"... 还有 {len(anchor_list) - 10} 个锚点")


# ── Step 5: 360 评价展示 ────────────────────────────────────────────────────────


def _compute_360_scores(eval_df: pd.DataFrame, employees_df: pd.DataFrame) -> dict:
    """轻量级 360 评分计算（用于 UI 预览，无 LLM 依赖）。

    使用基线角色权重 + 简单异常检测，返回 nested dict 结构。
    """
    from config import (
        ROLE_WEIGHTS_BASELINE,
        SELF_EVAL_ROLE,
        ANOMALY_SIGMA_THRESHOLD,
        ANOMALY_PENALTY_FACTOR,
    )

    # C3 守卫：score 可能含字符串（如"优良中"夹具），转 numeric 防下游 .mean()/.std()/groupby 崩
    # 复用 utils/data_quality.py:248 的 to_numeric(errors='coerce') 模式（D2：不在本处独立定义转换语义）
    eval_df = eval_df.copy()
    eval_df["score"] = pd.to_numeric(eval_df["score"], errors="coerce")
    all_scores = eval_df["score"].dropna()
    if len(all_scores) == 0:
        return {}

    global_mean = all_scores.mean()
    global_std = all_scores.std()

    # 异常检测
    evaluator_means = eval_df.groupby("evaluator_id")["score"].agg(["mean", "count"]).reset_index()
    anomalous = set()
    for _, row in evaluator_means.iterrows():
        if row["count"] < 15:
            continue
        if abs(row["mean"] - global_mean) > ANOMALY_SIGMA_THRESHOLD * global_std:
            anomalous.add(row["evaluator_id"])

    result = {}
    for emp_id in eval_df["employee_id"].unique():
        emp_data = eval_df[eval_df["employee_id"] == emp_id]
        dims = emp_data["dimension"].unique()
        emp_scores = {}
        for dim in dims:
            dim_data = emp_data[emp_data["dimension"] == dim]
            w_sum, w_total = 0.0, 0.0
            for _, row in dim_data.iterrows():
                if pd.isna(row["score"]) or row["evaluator_role"] == SELF_EVAL_ROLE:
                    continue
                base_w = ROLE_WEIGHTS_BASELINE.get(row["evaluator_role"])
                if base_w is None:
                    continue
                penalty = ANOMALY_PENALTY_FACTOR if row["evaluator_id"] in anomalous else 1.0
                fw = base_w * penalty
                w_sum += row["score"] * fw
                w_total += fw
            emp_scores[dim] = round(float(w_sum / w_total), 4) if w_total > 0 else None
        result[emp_id] = emp_scores
    return result


def _render_step_360() -> None:
    """主区域 Step 5：360 评价展示。"""
    from config import (
        ROLE_WEIGHTS_BASELINE as _rwb_display,
        ANOMALY_SIGMA_THRESHOLD as _ast,
        ANOMALY_PENALTY_FACTOR as _apf,
        TIME_DECAY_RATE as _tdr,
        DISCRIMINATION_PERFUNCTORY_WEIGHT as _dpw,
        DISCRIMINATION_POSITIVE_THRESHOLD as _dpt,
        CONFIDENCE_EVALUATOR_BASELINE as _ceb,
    )

    st.markdown("## Step 5：360 评价")
    st.caption("查看员工 360 评价各维度得分，权重因子详情，以及全局统计。")

    eval_df = st.session_state.get("evaluation_360_df")
    employees_df = st.session_state.get("employees_df")
    if eval_df is None or employees_df is None:
        st.info("请先上传数据")
        if st.button("← 返回上传", use_container_width=True, key="btn_360_back_upload"):
            st.session_state["step"] = 1
            st.rerun()
        return

    # 员工列表
    emp_ids = eval_df["employee_id"].astype(str).unique().tolist()
    emp_names = dict(zip(
        employees_df["employee_id"].astype(str),
        employees_df.get("name", employees_df["employee_id"]).astype(str),
    ))

    if not emp_ids:
        st.warning("360 评价数据中无员工记录")
        return

    # ── 员工选择器 ──
    emp_options = {f"{eid} - {emp_names.get(eid, '?')}": eid for eid in emp_ids}
    selected_label = st.selectbox(
        "👤 选择员工",
        options=list(emp_options.keys()),
        key="360_employee_selector",
    )
    selected_emp_id = emp_options[selected_label]
    st.session_state["selected_employee"] = selected_emp_id

    # ── 计算评分 ──
    all_scores = _compute_360_scores(eval_df, employees_df)
    emp_scores = all_scores.get(selected_emp_id, {})

    if not emp_scores:
        st.warning("该员工暂无 360 评分数据")
    else:
        # 5 维度得分
        st.markdown("### 📊 各维度得分")
        dim_order = ["专业能力", "沟通协作", "领导力", "责任心", "学习能力"]
        dims_with_scores = [(d, emp_scores.get(d)) for d in dim_order if d in emp_scores]
        n_cols = min(len(dims_with_scores), 5)
        cols = st.columns(n_cols)
        for i, (dim, score) in enumerate(dims_with_scores):
            with cols[i]:
                if score is not None:
                    st.metric(label=dim, value=f"{score:.2f}")
                    # 条形图（用 st.progress，score 假设 1-5 分）
                    pct = max(0.0, min(1.0, score / 5.0))
                    st.progress(pct, text=f"{score:.2f} / 5")
                else:
                    st.metric(label=dim, value="N/A")

        # 维度得分横向对比条形图
        st.markdown("#### 维度得分横向对比")
        chart_data = {
            d: s for d, s in dims_with_scores if s is not None
        }
        if chart_data:
            chart_df = pd.DataFrame({
                "维度": list(chart_data.keys()),
                "得分": list(chart_data.values()),
            })
            st.bar_chart(chart_df.set_index("维度"), use_container_width=True)

    # ── 置信度（色彩编码） ──
    st.markdown("### 🎯 置信度")
    confidence = None
    # 从 session_state 已处理的 scores_360 中读取（如果 DataUnderstanding 已运行）
    processed = st.session_state.get("scores_360", {})
    emp_proc = processed.get(selected_emp_id, {})
    if isinstance(emp_proc, dict) and "confidence" in emp_proc:
        confidence = emp_proc["confidence"]
    if confidence is not None:
        if confidence >= 0.8:
            st.success(f"🟢 高置信度 ({confidence:.2f})")
        elif confidence >= 0.5:
            st.warning(f"🟡 中等置信度 ({confidence:.2f})")
        else:
            st.error(f"🔴 低置信度 ({confidence:.2f})")
    else:
        st.caption("（运行完整 Pipeline 后显示置信度；当前为预览模式）")

    # ── 权重因子详情（折叠区） ──
    with st.expander("⚙️ 权重因子详情", expanded=False):
        st.markdown("**角色基线权重**")
        for role, w in _rwb_display.items():
            st.caption(f"  • {role}: {w:.2f}")
        st.markdown("**异常检测**")
        st.caption(f"  • σ 阈值: {_ast}σ（来自 config）")
        st.caption(f"  • 异常惩罚系数: {_apf}")
        st.caption(f"  • 时间衰减率: {_tdr}")
        st.markdown("**区分度检测**")
        st.caption(f"  • 敷衍判定权重: {_dpw}")
        st.caption(f"  • 正向阈值: {_dpt}")
        st.markdown("**置信度**")
        st.caption(f"  • 评价者基线: {_ceb}")

    # ── 全局摘要 ──
    with st.expander("📈 全局统计摘要", expanded=False):
        _render_360_global_summary(eval_df)

    # ── 导航按钮 ──
    st.divider()
    col_back, col_next = st.columns([1, 1])
    with col_back:
        if st.button("← 返回文本摘要", use_container_width=True, key="btn_360_back_summary"):
            st.session_state["step"] = 4
            st.rerun()
    with col_next:
        if st.button("下一步 → 画像生成", use_container_width=True, key="btn_360_next_profile"):
            st.session_state["step"] = 6
            st.rerun()


def _render_360_global_summary(eval_df: pd.DataFrame) -> None:
    """渲染 360 评价全局统计摘要。"""
    all_scores = eval_df["score"].dropna()
    if len(all_scores) == 0:
        st.caption("无可用评分数据")
        return

    st.metric("评价总条数", len(eval_df))
    st.metric("员工覆盖数", eval_df["employee_id"].nunique())
    st.metric("评价者总数", eval_df["evaluator_id"].nunique())

    # 各维度均分（C3 守卫：score 转 numeric 防字符串崩，与 _compute_360_scores 同模式）
    st.markdown("**各维度全局均分**")
    _score_num = pd.to_numeric(eval_df["score"], errors="coerce")
    dim_means = _score_num.groupby(eval_df["dimension"]).mean().round(2)
    dim_df = pd.DataFrame({"维度": dim_means.index, "均分": dim_means.values})
    st.dataframe(dim_df, use_container_width=True, hide_index=True)

    # 角色分布
    st.markdown("**评价者角色分布**")
    role_counts = eval_df["evaluator_role"].value_counts()
    role_df = pd.DataFrame({"角色": role_counts.index, "评价数": role_counts.values})
    st.dataframe(role_df, use_container_width=True, hide_index=True)


def render() -> None:
    """渲染 Talent Compass Streamlit 界面。

    main.py 依赖此函数签名，禁止修改。
    """
    # set_page_config 必须是第一个 st 调用
    st.set_page_config(
        page_title="Talent Compass",
        page_icon="🧭",
        layout="wide",
    )

    # 页面标题
    st.title("🧭 Talent Compass —— AI驱动的动态胜任力画像与智能人岗匹配系统")
    st.caption(f"当前时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # 初始化 session_state
    _init_session_state()

    # 侧边栏
    _render_sidebar()

    # 主区域（按步骤）
    step = st.session_state.get("step", 1)
    if step == 1:
        _render_step_upload()
    elif step == 2:
        _render_step_filter()
    elif step == 3:
        _render_step_data_quality()
    elif step == 4:
        _render_step_text_summary()
    elif step == 5:
        _render_step_360()
    else:
        st.info(f"Step {step} 尚未实现，敬请期待。")