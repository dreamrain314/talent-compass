"""utils/data_quality.py 单元测试

覆盖：正常数据、缺失值、类型错误、范围异常、文本不足、边界情况。
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from utils.data_quality import (
    check_data_quality,
    VALID_AGE_RANGE,
    VALID_SCORE_RANGE,
    VALID_YOS_RANGE,
)


def _make_complete_dfs(n=10) -> dict[str, pd.DataFrame]:
    """生成完整无缺失的测试数据集。"""
    employees = pd.DataFrame({
        "employee_id": [f"T{i:04d}" for i in range(1, n + 1)],
        "name": [f"员工{i}" for i in range(1, n + 1)],
        "age": [30 + i for i in range(n)],
        "gender": ["男", "女"] * (n // 2) + ["男"] * (n % 2),
        "education": ["本科"] * n,
        "major": (["计算机", "软件", "通信", "电子", "机械"] * (n // 5 + 1))[:n],
        "job_sequence": ["技术研发类"] * n,
        "current_position": ["工程师"] * n,
        "current_level": [f"P{i + 3}" for i in range(n)],
        "hire_date": ["2020-01-01"] * n,
        "years_of_service": [5] * n,
    })
    performance = pd.DataFrame({
        "employee_id": [f"T{i:04d}" for i in range(1, n + 1) for _ in range(3)],
        "year": [2024, 2025, 2026] * n,
        "performance_grade": ["A", "B", "C"] * n,
        "performance_comment": ["表现良好"] * (n * 3),
    })
    projects = pd.DataFrame({
        "employee_id": [f"T{i:04d}" for i in range(1, n + 1)],
        "project_name": ["项目A"] * n,
        "role": ["核心开发"] * n,
        "description": ["项目描述文本"] * n,
        "tools_used": [[] for _ in range(n)],
    })
    training = pd.DataFrame({
        "employee_id": [f"T{i:04d}" for i in range(1, n + 1)],
        "course_name": ["Python高级"] * n,
        "completion_date": ["2025-03"] * n,
        "status": ["已完成"] * n,
        "score": [85] * n,
    })
    evaluation_360 = pd.DataFrame({
        "employee_id": [f"T{i:04d}" for i in range(1, n + 1) for _ in range(5)],
        "evaluator_id": [f"E_{i}" for i in range(n * 5)],
        "evaluator_role": ["上级", "同事", "下属", "HR", "自评"] * n,
        "dimension": ["专业能力", "沟通协作", "领导力", "责任心", "学习能力"] * n,
        "score": [4, 3, 5, 4, 3] * n,
        "comment": ["评价文本"] * (n * 5),
    })
    return {
        "employees": employees,
        "performance": performance,
        "projects": projects,
        "training": training,
        "evaluation_360": evaluation_360,
    }


class TestNormalData:
    """完整无缺失数据测试。"""

    def test_all_files_present(self):
        dfs = _make_complete_dfs(10)
        result = check_data_quality(dfs)
        assert len(result["file_summaries"]) == 5
        all_ok = all(s["status"] == "ok" for s in result["file_summaries"])
        assert all_ok, f"不是所有文件状态为 ok: {[s['status'] for s in result['file_summaries']]}"

    def test_no_missing(self):
        dfs = _make_complete_dfs(10)
        result = check_data_quality(dfs)
        for name, details in result["missing_details"].items():
            all_none = all(m["level"] == "none" for m in details)
            assert all_none, f"{name} 含有非 none 缺失标记"

    def test_no_type_issues(self):
        dfs = _make_complete_dfs(10)
        result = check_data_quality(dfs)
        assert len(result["type_issues"]) == 0

    def test_no_range_issues(self):
        dfs = _make_complete_dfs(10)
        result = check_data_quality(dfs)
        assert len(result["range_issues"]) == 0

    def test_no_text_insufficient(self):
        dfs = _make_complete_dfs(10)
        result = check_data_quality(dfs)
        assert result["text_insufficient_count"] == 0

    def test_no_severe_missing(self):
        dfs = _make_complete_dfs(10)
        result = check_data_quality(dfs)
        assert len(result["severe_missing_employees"]) == 0


class TestMissingValues:
    """缺失值检测测试。"""

    def test_single_column_missing(self):
        dfs = _make_complete_dfs(5)
        dfs["employees"].loc[0, "age"] = np.nan
        result = check_data_quality(dfs)
        emp_missing = result["missing_details"].get("employees", [])
        age_entry = next((m for m in emp_missing if m["column"] == "age"), None)
        assert age_entry is not None
        assert age_entry["missing"] == 1
        assert age_entry["level"] == "high"  # 1/5 = 20% >= 10%

    def test_all_missing_one_file(self):
        dfs = _make_complete_dfs(3)
        dfs["training"]["score"] = np.nan
        result = check_data_quality(dfs)
        train_missing = result["missing_details"].get("training", [])
        score_entry = next((m for m in train_missing if m["column"] == "score"), None)
        assert score_entry is not None
        assert score_entry["missing"] == 3
        assert score_entry["level"] == "high"


class TestTypeErrors:
    """类型异常检测测试。"""

    def test_performance_grade_invalid(self):
        dfs = _make_complete_dfs(5)
        dfs["performance"].loc[0, "performance_grade"] = "X"
        dfs["performance"].loc[1, "performance_grade"] = "E"
        result = check_data_quality(dfs)
        grade_issues = [i for i in result["type_issues"] if i["column"] == "performance_grade"]
        assert len(grade_issues) == 1
        assert grade_issues[0]["file"] == "performance"

    def test_age_string(self):
        dfs = _make_complete_dfs(3)
        dfs["employees"]["age"] = dfs["employees"]["age"].astype(object)
        dfs["employees"].loc[0, "age"] = "二十五"
        result = check_data_quality(dfs)
        age_issues = [i for i in result["type_issues"] if i["column"] == "age"]
        assert len(age_issues) == 1
        assert age_issues[0]["file"] == "employees"

    def test_score_non_numeric(self):
        dfs = _make_complete_dfs(3)
        dfs["evaluation_360"]["score"] = dfs["evaluation_360"]["score"].astype(object)
        dfs["evaluation_360"].loc[0, "score"] = "高"
        result = check_data_quality(dfs)
        score_issues = [i for i in result["type_issues"] if i["column"] == "score"]
        assert len(score_issues) >= 1


class TestRangeErrors:
    """范围异常检测测试。"""

    def test_age_out_of_range_high(self):
        dfs = _make_complete_dfs(5)
        dfs["employees"].loc[0, "age"] = 999
        result = check_data_quality(dfs)
        age_ranges = [i for i in result["range_issues"] if i["column"] == "age"]
        assert len(age_ranges) == 1
        assert f"[{VALID_AGE_RANGE[0]}" in age_ranges[0]["issue"]

    def test_age_out_of_range_low(self):
        dfs = _make_complete_dfs(5)
        dfs["employees"].loc[0, "age"] = 10
        result = check_data_quality(dfs)
        age_ranges = [i for i in result["range_issues"] if i["column"] == "age"]
        assert len(age_ranges) == 1

    def test_years_of_service_negative(self):
        dfs = _make_complete_dfs(5)
        dfs["employees"].loc[0, "years_of_service"] = -1
        result = check_data_quality(dfs)
        yos_ranges = [i for i in result["range_issues"] if i["column"] == "years_of_service"]
        assert len(yos_ranges) == 1

    def test_years_of_service_excessive(self):
        dfs = _make_complete_dfs(5)
        dfs["employees"].loc[0, "years_of_service"] = 99
        result = check_data_quality(dfs)
        yos_ranges = [i for i in result["range_issues"] if i["column"] == "years_of_service"]
        assert len(yos_ranges) == 1

    def test_score_out_of_range_zero(self):
        dfs = _make_complete_dfs(3)
        dfs["evaluation_360"].loc[0, "score"] = 0
        result = check_data_quality(dfs)
        score_ranges = [i for i in result["range_issues"] if i["column"] == "score"]
        assert len(score_ranges) == 1

    def test_score_out_of_range_six(self):
        dfs = _make_complete_dfs(3)
        dfs["evaluation_360"].loc[0, "score"] = 6
        result = check_data_quality(dfs)
        score_ranges = [i for i in result["range_issues"] if i["column"] == "score"]
        assert len(score_ranges) == 1


class TestTextInsufficient:
    """文本不足检测测试。"""

    def test_all_text_missing(self):
        dfs = _make_complete_dfs(5)
        dfs["performance"]["performance_comment"] = np.nan
        dfs["projects"]["description"] = np.nan
        dfs["evaluation_360"]["comment"] = np.nan
        result = check_data_quality(dfs)
        assert result["text_insufficient_count"] == 5

    def test_partial_text_sufficient(self):
        dfs = _make_complete_dfs(5)
        dfs["projects"]["description"] = np.nan
        dfs["evaluation_360"]["comment"] = None
        result = check_data_quality(dfs)
        assert result["text_insufficient_count"] == 0

    def test_single_employee_missing_text(self):
        dfs = _make_complete_dfs(5)
        emp_id = dfs["employees"].loc[0, "employee_id"]
        perf_mask = dfs["performance"]["employee_id"] == emp_id
        dfs["performance"].loc[perf_mask, "performance_comment"] = np.nan
        proj_mask = dfs["projects"]["employee_id"] == emp_id
        dfs["projects"].loc[proj_mask, "description"] = np.nan
        eval_mask = dfs["evaluation_360"]["employee_id"] == emp_id
        dfs["evaluation_360"].loc[eval_mask, "comment"] = np.nan
        result = check_data_quality(dfs)
        assert result["text_insufficient_count"] == 1
        assert emp_id in result["text_insufficient_ids"]


class TestEdgeCases:
    """边界情况测试。"""

    def test_empty_dataframe(self):
        dfs = {"employees": pd.DataFrame(), "performance": pd.DataFrame()}
        result = check_data_quality(dfs)
        assert len(result["file_summaries"]) == 2
        assert result["file_summaries"][0]["status"] == "empty"

    def test_all_nan(self):
        dfs = _make_complete_dfs(3)
        dfs["employees"] = dfs["employees"].map(lambda _: np.nan)
        result = check_data_quality(dfs)
        severe = result.get("severe_missing_employees", [])
        assert len(severe) == 3

    def test_non_dict_input(self):
        result = check_data_quality("not a dict")  # type: ignore
        assert result["file_summaries"] == []

    def test_non_dataframe_value(self):
        dfs = {"employees": "not a dataframe"}
        result = check_data_quality(dfs)  # type: ignore
        assert len(result["file_summaries"]) == 0

    def test_empty_dict(self):
        result = check_data_quality({})
        assert result["file_summaries"] == []
        assert result["missing_details"] == {}
        assert result["text_insufficient_count"] == 0

    def test_large_values(self):
        dfs = _make_complete_dfs(3)
        dfs["employees"].loc[0, "age"] = 9999
        dfs["employees"].loc[0, "years_of_service"] = 999
        dfs["evaluation_360"].loc[0, "score"] = 999
        result = check_data_quality(dfs)
        assert len(result["range_issues"]) >= 3

    def test_employees_without_text_cols(self):
        dfs = _make_complete_dfs(3)
        del dfs["projects"]
        result = check_data_quality(dfs)
        assert "projects" not in result["missing_details"]
        assert "employees" in result["missing_details"]

    def test_partial_data_only(self):
        dfs = {"employees": _make_complete_dfs(3)["employees"]}
        result = check_data_quality(dfs)
        assert len(result["file_summaries"]) == 1
        assert result["text_insufficient_count"] == 3
