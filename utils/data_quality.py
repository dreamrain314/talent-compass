"""数据质量检测工具

纯 pandas 实现，不依赖 LLM 调用，不从 Agent 类继承。
入口：check_data_quality(dfs) → dict

用于 Streamlit UI Step 3 数据质量报告展示。
也兼容 DataUnderstanding._detect_missing() 的输出结构（超集）。
"""
from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ── 有效值常量 ──────────────────────────────────────────────────────────
VALID_PERFORMANCE_GRADES = {"A", "B", "C", "D"}
VALID_SCORE_RANGE = (1, 5)
VALID_AGE_RANGE = (18, 70)
VALID_YOS_RANGE = (0, 50)

# ── 每个文件用于类型/范围检查的关键列 ────────────────────────────────────
_KEY_COLUMNS: dict[str, dict[str, Any]] = {
    "employees": {
        "numeric": {"age", "years_of_service"},
        "grade": set(),
    },
    "performance": {
        "numeric": {"year"},
        "grade": {"performance_grade"},
    },
    "evaluation_360": {
        "numeric": {"score", "year"},
        "grade": set(),
    },
    "training": {
        "numeric": {"score"},
        "grade": set(),
    },
}


def check_data_quality(dfs: dict[str, pd.DataFrame]) -> dict:
    """检查上传数据的质量，返回结构化质量报告。

    Args:
        dfs: {source_name: DataFrame} 格式，与 session_state 中存储的数据一致。
             预期键：employees, performance, projects, training, evaluation_360

    Returns:
        {
            "file_summaries": [{"name", "records", "complete_pct", "status"}, ...],
            "missing_details": {source_name: [{"column","missing","total","rate","level"}, ...]},
            "type_issues": [{"file","column","expected","example"}, ...],
            "range_issues": [{"file","column","value","issue"}, ...],
            "text_insufficient_count": int,
            "text_insufficient_ids": [str],
            "severe_missing_employees": [str],
        }
    """
    result: dict[str, Any] = {
        "file_summaries": [],
        "missing_details": {},
        "type_issues": [],
        "range_issues": [],
        "text_insufficient_count": 0,
        "text_insufficient_ids": [],
        "severe_missing_employees": [],
    }

    if not isinstance(dfs, dict):
        logger.warning(f"check_data_quality: 输入类型异常 {type(dfs).__name__}")
        return result

    # ── 遍历每个文件 ─────────────────────────────────────────────────
    for name, df in dfs.items():
        if not isinstance(df, pd.DataFrame):
            logger.warning(f"{name}: 非 DataFrame 类型 {type(df).__name__}，跳过")
            continue

        records = len(df)
        if records == 0:
            result["file_summaries"].append({
                "name": name, "records": 0, "complete_pct": 100.0, "status": "empty",
            })
            continue

        # 1) 缺失值统计
        missing = _check_missing(df, name)
        result["missing_details"][name] = missing
        total_cells = df.size
        missing_cells = int(df.isnull().sum().sum())
        complete_pct = round((1 - missing_cells / max(total_cells, 1)) * 100, 1)

        # 2) 类型检查
        type_issues = _check_types(df, name)
        result["type_issues"].extend(type_issues)

        # 3) 范围检查
        range_issues = _check_ranges(df, name)
        result["range_issues"].extend(range_issues)

        # 文件概要状态
        has_errors = (
            any(m["level"] == "high" for m in missing)
            or len(type_issues) > 0
            or len(range_issues) > 0
        )
        has_warnings = any(m["level"] == "medium" for m in missing)
        if has_errors:
            status = "error"
        elif has_warnings:
            status = "warning"
        else:
            status = "ok"

        result["file_summaries"].append({
            "name": name,
            "records": records,
            "complete_pct": complete_pct,
            "status": status,
        })

    # ── 员工级质量标记 ─────────────────────────────────────────────
    employees_df = dfs.get("employees")
    if isinstance(employees_df, pd.DataFrame) and len(employees_df) > 0:
        # 严重缺失员工
        severe_ids = _find_severe_missing(employees_df)
        result["severe_missing_employees"] = severe_ids

        # 文本不足检查
        text_ids = _find_text_insufficient(
            employees_df,
            dfs.get("performance"),
            dfs.get("projects"),
            dfs.get("evaluation_360"),
        )
        result["text_insufficient_ids"] = text_ids
        result["text_insufficient_count"] = len(text_ids)

    return result


def _check_missing(df: pd.DataFrame, name: str) -> list[dict]:
    """逐列统计缺失值。"""
    total = len(df)
    details = []
    for col in df.columns:
        missing = int(df[col].isnull().sum())
        rate = missing / max(total, 1)
        if missing == 0:
            level = "none"  # 🟢
        elif rate < 0.1:
            level = "low"  # 🟡
        else:
            level = "high"  # 🔴
        details.append({
            "column": str(col),
            "missing": missing,
            "total": total,
            "rate": round(rate, 3),
            "level": level,
        })
    return details


def _check_types(df: pd.DataFrame, name: str) -> list[dict]:
    """检查关键列的类型异常（非空时）。"""
    issues = []
    spec = _KEY_COLUMNS.get(name, {})

    for col in spec.get("numeric", set()):
        if col not in df.columns:
            continue
        non_null = df[col].dropna()
        if len(non_null) == 0:
            continue
        # 检查是否能转为数字
        for val in non_null:
            if isinstance(val, (int, float, np.integer, np.floating)):
                continue
            elif isinstance(val, str):
                try:
                    float(val)
                except (ValueError, TypeError):
                    issues.append({
                        "file": name, "column": col,
                        "expected": "numeric",
                        "example": str(val)[:50],
                    })
                    break  # 找到一个问题项就够报告了
            else:
                issues.append({
                    "file": name, "column": col,
                    "expected": "numeric",
                    "example": str(type(val).__name__),
                })
                break

    for col in spec.get("grade", set()):
        if col not in df.columns:
            continue
        non_null = df[col].dropna().astype(str).str.strip()
        bad = non_null[~non_null.isin(VALID_PERFORMANCE_GRADES)]
        if len(bad) > 0:
            issues.append({
                "file": name, "column": col,
                "expected": "A/B/C/D",
                "example": bad.iloc[0][:50],
            })

    return issues


def _check_ranges(df: pd.DataFrame, name: str) -> list[dict]:
    """检查关键列的数值范围异常。"""
    issues = []

    if name == "employees":
        if "age" in df.columns:
            _age = pd.to_numeric(df["age"], errors="coerce")
            bad = df[_age.notna() & (
                (_age < VALID_AGE_RANGE[0]) | (_age > VALID_AGE_RANGE[1])
            )]
            for _, row in bad.iterrows():
                issues.append({
                    "file": name, "column": "age",
                    "value": str(row["age"]),
                    "issue": f"超出 [{VALID_AGE_RANGE[0]}, {VALID_AGE_RANGE[1]}]",
                })
        if "years_of_service" in df.columns:
            _yos = pd.to_numeric(df["years_of_service"], errors="coerce")
            bad = df[_yos.notna() & (
                (_yos < VALID_YOS_RANGE[0]) | (_yos > VALID_YOS_RANGE[1])
            )]
            for _, row in bad.iterrows():
                issues.append({
                    "file": name, "column": "years_of_service",
                    "value": str(row["years_of_service"]),
                    "issue": f"超出 [{VALID_YOS_RANGE[0]}, {VALID_YOS_RANGE[1]}]",
                })

    elif name == "evaluation_360":
        if "score" in df.columns:
            _score = pd.to_numeric(df["score"], errors="coerce")
            bad = df[_score.notna() & (
                (_score < VALID_SCORE_RANGE[0]) | (_score > VALID_SCORE_RANGE[1])
            )]
            for _, row in bad.head(20).iterrows():  # 最多报告 20 条
                issues.append({
                    "file": name, "column": "score",
                    "value": str(row["score"]),
                    "issue": f"超出 [{VALID_SCORE_RANGE[0]}, {VALID_SCORE_RANGE[1]}]",
                })

    return issues


def _find_severe_missing(employees_df: pd.DataFrame) -> list[str]:
    """找出基础字段缺失率 > 50% 的员工。"""
    base_fields = [
        "name", "age", "gender", "education", "major",
        "job_sequence", "current_position", "current_level",
    ]
    available = [c for c in base_fields if c in employees_df.columns]
    if not available:
        return []

    severe = []
    for _, emp in employees_df.iterrows():
        missing = sum(1 for c in available if pd.isna(emp.get(c)))
        rate = missing / len(available)
        if rate > 0.5:
            severe.append(str(emp.get("employee_id", "?")))
    return severe


def _find_text_insufficient(
    employees_df: pd.DataFrame,
    perf_df: pd.DataFrame | None,
    proj_df: pd.DataFrame | None,
    eval_df: pd.DataFrame | None,
) -> list[str]:
    """找出同时缺少绩效/项目/360评论文本的员工。"""
    insufficient = []
    for _, emp in employees_df.iterrows():
        emp_id = str(emp.get("employee_id", ""))
        if not emp_id:
            continue

        has_perf_text = False
        if perf_df is not None and "performance_comment" in perf_df.columns:
            subset = perf_df[perf_df["employee_id"] == emp_id]
            has_perf_text = subset["performance_comment"].dropna().shape[0] > 0

        has_proj_text = False
        if proj_df is not None and "description" in proj_df.columns:
            subset = proj_df[proj_df["employee_id"] == emp_id]
            has_proj_text = subset["description"].dropna().shape[0] > 0

        has_eval_text = False
        if eval_df is not None and "comment" in eval_df.columns:
            subset = eval_df[eval_df["employee_id"] == emp_id]
            has_eval_text = subset["comment"].dropna().shape[0] > 0

        if not (has_perf_text or has_proj_text or has_eval_text):
            insufficient.append(emp_id)

    return insufficient
