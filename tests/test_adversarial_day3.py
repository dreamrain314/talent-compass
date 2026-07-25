"""对抗性检验：Day 3 交付物的边界与异常路径测试

假设这里全是 bug，逐行推演发现的攻击面：

1. `_safe_val()` 不处理 pd.NA → 返回 pd.NA 而非 default
2. `_preprocess_360()` 当所有角色不被 ROLE_WEIGHTS_BASELINE 覆盖 → ZeroDivisionError
3. `validate_input()` 中空 projects.json 的 `[]` → IndexError
4. `_check_missing()` 缺失率恰好等于 0.1 → 边界歧义
5. `_find_text_insufficient()` 中列不存在时的 KeyError
6. `_preprocess_360()` 中 global_std = 0（所有评分相同）→ 2σ = 0
7. `check_data_quality()` 对重复 employee_id 的处理
8. `_check_summary_lengths()` 原文恰好 30 字时的分支行为
9. `_merge_records()` 中 tools_used 是字符串时 json.loads 的结果可能非 list
10. `execute()` 中 "degraded" 路径的 metadata 是否与 "success" 对称
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from agents.data_understanding import DataUnderstanding, ROLE_WEIGHTS_BASELINE


from utils.data_quality import (
    check_data_quality,
    _check_missing,
    _find_text_insufficient,
    _find_severe_missing,
    VALID_AGE_RANGE,
    VALID_SCORE_RANGE,
    VALID_YOS_RANGE,
)


def _make_mock_summary(
    perf_summary="绩效表现良好",
    proj_summary="参与核心开发",
    eval_summary="团队协作好",
    anchors=None,
    error=None,
    usage=None,
    model="mock",
):
    """构建 summarize_employee_texts 的 mock 返回值。"""
    if anchors is None:
        anchors = {"performance": ["2024年度"], "projects": [], "evaluation": []}
    if usage is None:
        usage = {"prompt_tokens": 100, "completion_tokens": 50}
    tokens = int(usage.get("prompt_tokens", 0) or 0) + int(usage.get("completion_tokens", 0) or 0)
    return {
        "text_summaries": None if error else {
            "performance_summary": perf_summary,
            "project_summary": proj_summary,
            "evaluation_summary": eval_summary,
        },
        "anchors": None if error else anchors,
        "anchor_mismatch": False,
        "hallucination_flags": {},
        "error": error,
        "model": model,
        "usage": usage,
        "tokens": tokens,
    }


# ── 辅助函数（与 test_data_quality.py 中的 _make_complete_dfs 保持一致）──

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


# =============================================================================
# Part A: utils/data_quality.py 对抗测试
# =============================================================================


class TestDataQuality_BoundaryValues:
    """边界值精确测试 — 现有测试未覆盖的边界点。"""

    def test_age_lower_bound_valid(self):
        """年龄 = 18（边界有效值）→ 不应报范围错误。"""
        dfs = _make_complete_dfs(3)
        dfs["employees"].loc[0, "age"] = 18
        result = check_data_quality(dfs)
        age_ranges = [i for i in result["range_issues"] if i["column"] == "age"]
        assert len(age_ranges) == 0, "age=18 应是合法值"

    def test_age_upper_bound_valid(self):
        """年龄 = 70（边界有效值）→ 不应报范围错误。"""
        dfs = _make_complete_dfs(3)
        dfs["employees"].loc[0, "age"] = 70
        result = check_data_quality(dfs)
        age_ranges = [i for i in result["range_issues"] if i["column"] == "age"]
        assert len(age_ranges) == 0, "age=70 应是合法值"

    def test_age_lower_bound_invalid(self):
        """年龄 = 17（刚好低于下界）→ 应报范围错误。"""
        dfs = _make_complete_dfs(3)
        dfs["employees"].loc[0, "age"] = 17
        result = check_data_quality(dfs)
        age_ranges = [i for i in result["range_issues"] if i["column"] == "age"]
        assert len(age_ranges) == 1, "age=17 应报错"

    def test_yos_lower_bound_valid(self):
        """工龄 = 0（边界有效值）→ 不应报范围错误。"""
        dfs = _make_complete_dfs(3)
        dfs["employees"].loc[0, "years_of_service"] = 0
        result = check_data_quality(dfs)
        yos_ranges = [i for i in result["range_issues"] if i["column"] == "years_of_service"]
        assert len(yos_ranges) == 0, "yos=0 应是合法值"

    def test_yos_upper_bound_valid(self):
        """工龄 = 50（边界有效值）→ 不应报范围错误。"""
        dfs = _make_complete_dfs(3)
        dfs["employees"].loc[0, "years_of_service"] = 50
        result = check_data_quality(dfs)
        yos_ranges = [i for i in result["range_issues"] if i["column"] == "years_of_service"]
        assert len(yos_ranges) == 0, "yos=50 应是合法值"

    def test_yos_upper_bound_invalid(self):
        """工龄 = 51（刚好超出上界）→ 应报范围错误。"""
        dfs = _make_complete_dfs(3)
        dfs["employees"].loc[0, "years_of_service"] = 51
        result = check_data_quality(dfs)
        yos_ranges = [i for i in result["range_issues"] if i["column"] == "years_of_service"]
        assert len(yos_ranges) == 1, "yos=51 应报错"

    def test_score_lower_bound_valid(self):
        """360评分 = 1（边界有效值）→ 不应报范围错误。"""
        dfs = _make_complete_dfs(3)
        dfs["evaluation_360"].loc[0, "score"] = 1
        result = check_data_quality(dfs)
        score_ranges = [i for i in result["range_issues"] if i["column"] == "score"]
        assert len(score_ranges) == 0, "score=1 应是合法值"

    def test_score_upper_bound_valid(self):
        """360评分 = 5（边界有效值）→ 不应报范围错误。"""
        dfs = _make_complete_dfs(3)
        dfs["evaluation_360"].loc[0, "score"] = 5
        result = check_data_quality(dfs)
        score_ranges = [i for i in result["range_issues"] if i["column"] == "score"]
        assert len(score_ranges) == 0, "score=5 应是合法值"

    def test_missing_rate_exactly_10pct(self):
        """缺失率恰好 10%（1/10）→ level 应为 high。"""
        dfs = _make_complete_dfs(10)
        dfs["employees"].loc[0, "age"] = np.nan  # 1/10 = 10%
        result = check_data_quality(dfs)
        emp_missing = result["missing_details"].get("employees", [])
        age_entry = next((m for m in emp_missing if m["column"] == "age"), None)
        assert age_entry is not None
        assert age_entry["level"] == "high", "rate=0.1 应进 high 分支"


class TestDataQuality_NaN_pdNA:
    """pd.NA 与 np.nan 混合场景。"""

    def test_severe_missing_with_pd_NA(self):
        """employees 中有 pd.NA 值 → 不应抛异常。"""
        dfs = _make_complete_dfs(3)
        dfs["employees"].loc[0, "name"] = pd.NA
        dfs["employees"].loc[0, "age"] = pd.NA
        dfs["employees"].loc[0, "gender"] = pd.NA
        dfs["employees"].loc[0, "education"] = pd.NA
        dfs["employees"].loc[0, "major"] = pd.NA
        result = check_data_quality(dfs)
        assert len(result["severe_missing_employees"]) >= 1

    def test_find_text_insufficient_with_nan_comments(self):
        """所有文本列全为 np.nan → 判定为文本不足。"""
        dfs = _make_complete_dfs(3)
        dfs["performance"]["performance_comment"] = np.nan
        dfs["projects"]["description"] = np.nan
        dfs["evaluation_360"]["comment"] = np.nan
        result = check_data_quality(dfs)
        assert result["text_insufficient_count"] == 3


class TestDataQuality_ColumnErrors:
    """列不存在时的防御测试。"""

    def test_missing_performance_comment_column(self):
        """performance 没有 performance_comment 列 → _find_text_insufficient 的 KeyError。"""
        dfs = _make_complete_dfs(3)
        perf_df = dfs["performance"].drop(columns=["performance_comment"])
        try:
            _find_text_insufficient(dfs["employees"], perf_df, dfs["projects"], dfs["evaluation_360"])
        except KeyError:
            pytest.fail("_find_text_insufficient: 缺少列时应优雅处理，不应抛 KeyError")

    def test_missing_employee_id_column(self):
        """employees 没有 employee_id 列 → 应有返回值而非崩溃。"""
        dfs = _make_complete_dfs(3)
        emp_no_id = dfs["employees"].drop(columns=["employee_id"])
        result = _find_severe_missing(emp_no_id)
        assert isinstance(result, list)

    def test_type_check_unknown_file_spec(self):
        """不在 _KEY_COLUMNS 中的文件 → 空 issues。"""
        from utils.data_quality import _check_types
        df = pd.DataFrame({"a": [1, 2], "b": ["x", "y"]})
        issues = _check_types(df, "unknown_table")
        assert issues == []


class TestDataQuality_DuplicateEmployees:
    """重复 employee_id 场景。"""

    def test_duplicate_employee_ids(self):
        """employees 有重复 ID → 不影响统计。"""
        dfs = _make_complete_dfs(3)
        dup = dfs["employees"].iloc[0].to_dict()
        dup["name"] = "重复员工"
        dfs["employees"] = pd.concat([dfs["employees"], pd.DataFrame([dup])], ignore_index=True)
        result = check_data_quality(dfs)
        assert isinstance(result["text_insufficient_count"], int)

    def test_duplicate_text_partial(self):
        """一个员工有两条文本 = 仍算有文本。"""
        dfs = _make_complete_dfs(3)
        extra = dfs["performance"].iloc[0].to_dict()
        dfs["performance"] = pd.concat([dfs["performance"], pd.DataFrame([extra])], ignore_index=True)
        result = check_data_quality(dfs)
        assert result["text_insufficient_count"] <= 1


class TestDataQuality_TypeAnomalyEdge:
    """类型检查的边界攻击。"""

    def test_numeric_string_in_score(self):
        """score 列有"3.5"这种可转数字字符串 → 不应触发类型错误。"""
        dfs = _make_complete_dfs(3)
        dfs["evaluation_360"]["score"] = dfs["evaluation_360"]["score"].astype(object)
        dfs["evaluation_360"].loc[0, "score"] = "3.5"
        result = check_data_quality(dfs)
        score_issues = [i for i in result["type_issues"] if i["column"] == "score"]
        assert len(score_issues) == 0, "可转数字的字符串不应算类型错误"

    def test_mixed_type_column(self):
        """同一列混有 int 和 str → 应能识别到类型问题。"""
        dfs = _make_complete_dfs(5)
        dfs["employees"]["age"] = dfs["employees"]["age"].astype(object)
        dfs["employees"].loc[0, "age"] = "三十五"
        dfs["employees"].loc[1, "age"] = 28
        result = check_data_quality(dfs)
        age_issues = [i for i in result["type_issues"] if i["column"] == "age"]
        assert len(age_issues) >= 1, "混合类型应至少报告一个问题"


class TestDataQuality_EmptyStringID:
    """空字符串 employee_id 场景。"""

    def test_empty_employee_id_text_insufficient(self):
        """employee_id 为空字符串 → 被跳过，不抛异常。"""
        dfs = _make_complete_dfs(3)
        dfs["employees"].loc[0, "employee_id"] = ""
        result = check_data_quality(dfs)
        assert "text_insufficient_count" in result

    def test_empty_employee_id_severe_missing(self):
        """employee_id 为空字符串 → 返回 "?"。"""
        dfs = _make_complete_dfs(3)
        dfs["employees"].loc[0, "employee_id"] = ""
        dfs["employees"].loc[0, "name"] = np.nan
        dfs["employees"].loc[0, "age"] = np.nan
        result = check_data_quality(dfs)
        assert "severe_missing_employees" in result


# =============================================================================
# Part B: agents/data_understanding.py 对抗测试
# =============================================================================


def _write_csv(path, rows):
    pd.DataFrame(rows).to_csv(path, index=False, encoding="utf-8-sig")


def _write_json(path, rows):
    with open(path, "w", encoding="utf-8-sig") as f:
        json.dump(rows, f, ensure_ascii=False)


def _make_minimal_data(tmp_dir, n=3):
    """在 tmp_dir 下生成最小对抗测试数据集。"""
    emp_rows = [
        {"employee_id": f"T{i:04d}", "name": f"员工{i}", "age": 30 + i,
         "gender": "男", "education": "本科", "major": "计算机",
         "job_sequence": "技术研发类", "current_position": "工程师",
         "current_level": f"P{i+3}", "hire_date": "2020-01-01", "years_of_service": 6}
        for i in range(1, n + 1)
    ]
    _write_csv(os.path.join(tmp_dir, "employees.csv"), emp_rows)
    perf_rows = []
    for emp in emp_rows:
        for y in [2024, 2025, 2026]:
            perf_rows.append({
                "employee_id": emp["employee_id"], "year": y,
                "performance_grade": "B",
                "performance_comment": f"{y}年绩效表现良好，完成各项任务。",
            })
    _write_csv(os.path.join(tmp_dir, "performance.csv"), perf_rows)
    proj_rows = []
    for emp in emp_rows:
        proj_rows.append({
            "employee_id": emp["employee_id"], "project_name": "测试项目",
            "role": "核心开发", "start_date": "2025-01", "end_date": "2025-06",
            "description": f"{emp['employee_id']}参与的核心系统开发项目",
            "team_size": 5, "tools_used": ["Python", "Docker"],
        })
    _write_json(os.path.join(tmp_dir, "projects.json"), proj_rows)
    train_rows = []
    for emp in emp_rows:
        train_rows.append({
            "employee_id": emp["employee_id"], "course_name": "Python高级",
            "completion_date": "2025-03", "status": "已完成", "score": 85,
        })
    _write_csv(os.path.join(tmp_dir, "training.csv"), train_rows)
    eval_rows = []
    roles = ["上级", "同事", "下属", "HR"]
    dims = ["专业能力", "沟通协作", "领导力", "责任心", "学习能力"]
    for emp in emp_rows:
        eid = emp["employee_id"]
        for dim in dims:
            for role in roles:
                eval_rows.append({
                    "employee_id": eid,
                    "evaluator_id": f"E{role}_{eid}",
                    "evaluator_role": role,
                    "dimension": dim,
                    "score": 3 + hash(f"{eid}{dim}{role}") % 3,
                    "comment": f"{role}评价：{dim}表现良好。",
                })
            eval_rows.append({
                "employee_id": emp["employee_id"],
                "evaluator_id": f"E{emp['employee_id']}",
                "evaluator_role": "自评",
                "dimension": dim,
                "score": 4,
                "comment": "自我评价尚可。",
            })
    _write_csv(os.path.join(tmp_dir, "evaluation_360.csv"), eval_rows)
    return {
        "employees": os.path.join(tmp_dir, "employees.csv"),
        "performance": os.path.join(tmp_dir, "performance.csv"),
        "projects": os.path.join(tmp_dir, "projects.json"),
        "training": os.path.join(tmp_dir, "training.csv"),
        "evaluation_360": os.path.join(tmp_dir, "evaluation_360.csv"),
    }


@pytest.fixture
def agent():
    return DataUnderstanding()


@pytest.fixture
def tmp_data(tmp_path):
    return _make_minimal_data(str(tmp_path), n=3)


@pytest.fixture
def mock_context():
    return {"trace_id": "test-adv", "timeout_seconds": 60}


# ═════════════════════════════════════════════════════════════════════
# B1: _safe_val 的 pd.NA 漏洞
# ═════════════════════════════════════════════════════════════════════


class TestSafeVal_PdNA:
    """_safe_val 对 pd.NA 的隐性错误 — pd.NA 不是 float / None。"""

    def test_safe_val_pdna_returns_default(self):
        """pd.NA 字段 → 应返回 default，而非原样的 pd.NA。"""
        row = pd.Series({"name": pd.NA, "age": pd.NA, "gender": "男"})
        name = DataUnderstanding._safe_val(row, "name")
        assert name is None, f"pd.NA name 应返回 None，实际: {name!r}"
        age = DataUnderstanding._safe_val(row, "age", 0)
        assert age == 0, f"pd.NA age 应返回 0，实际: {age!r}"

    def test_merge_records_with_pdna(self, agent, tmp_data):
        """employees 含 pd.NA → _merge_records 产出 {structured} 中字段不应是 pd.NA。"""
        dfs = agent._read_data_files(tmp_data)
        dfs["employees"].loc[0, "name"] = pd.NA
        dfs["employees"].loc[0, "current_position"] = pd.NA
        data_quality = agent._detect_missing(dfs)
        summaries = [
            {"employee_id": "T0001", "text_summaries": None, "anchors": None,
             "summary_error": "文本数据不足", "anchor_mismatch": False, "hallucination_flags": {}},
            {"employee_id": "T0002", "text_summaries": None, "anchors": None,
             "summary_error": "文本数据不足", "anchor_mismatch": False, "hallucination_flags": {}},
            {"employee_id": "T0003", "text_summaries": None, "anchors": None,
             "summary_error": "文本数据不足", "anchor_mismatch": False, "hallucination_flags": {}},
        ]
        scores_360 = agent._preprocess_360(dfs["evaluation_360"], dfs["employees"])
        records = agent._merge_records(
            dfs["employees"], dfs["performance"], dfs["projects"],
            dfs["training"], summaries, scores_360, data_quality,
        )
        t1 = next(r for r in records if r["employee_id"] == "T0001")
        s = t1["structured"]
        assert s["name"] is None, f"name 应为 None, 实际: {s['name']!r}"
        assert s["current_position"] is None, f"current_position 应为 None, 实际: {s['current_position']!r}"


# ═════════════════════════════════════════════════════════════════════
# B2: _preprocess_360 中 weight_total = 0 时的 ZeroDivisionError
# ═════════════════════════════════════════════════════════════════════


class Test360WeightTotalZero:
    """_preprocess_360 weight_total=0 → ZeroDivisionError 攻击面。"""

    def test_all_self_eval_only(self, agent):
        """只有自评 → 所有非自评都跳过 → weight_total=0 → 不应崩溃。"""
        rows = [
            {"employee_id": "T0001", "evaluator_id": "Self",
             "evaluator_role": "自评", "dimension": "专业能力",
             "score": 4, "comment": "自评。"},
        ]
        df = pd.DataFrame(rows)
        emp_df = pd.DataFrame([{"employee_id": "T0001", "job_sequence": "技术研发类"}])
        result = agent._preprocess_360(df, emp_df)
        summary = result.get("_summary", {})
        assert summary.get("error") is None, "只有自评不应报 error"
        scores = result.get("T0001", {})
        for dim in ["专业能力", "沟通协作", "领导力", "责任心", "学习能力"]:
            assert scores.get(dim) is None, f"{dim} 应为 None"

    def test_unknown_role_only(self, agent):
        """只有未知角色（不在 ROLE_WEIGHTS_BASELINE 中）→ weight_total=0。"""
        rows = [
            {"employee_id": "T0001", "evaluator_id": "E1",
             "evaluator_role": "实习生", "dimension": "专业能力",
             "score": 3, "comment": "评价。"},
            {"employee_id": "T0001", "evaluator_id": "E2",
             "evaluator_role": "外部顾问", "dimension": "专业能力",
             "score": 4, "comment": "评价。"},
        ]
        df = pd.DataFrame(rows)
        emp_df = pd.DataFrame([{"employee_id": "T0001", "job_sequence": "技术研发类"}])
        result = agent._preprocess_360(df, emp_df)
        assert result.get("_summary", {}).get("error") is None
        scores = result.get("T0001", {})
        for dim in ["专业能力", "沟通协作", "领导力", "责任心", "学习能力"]:
            assert scores.get(dim) is None


# ═════════════════════════════════════════════════════════════════════
# B3: validate_input 中空 projects.json 的 IndexError
# ═════════════════════════════════════════════════════════════════════


class TestValidateInputEmptyJSON:
    """空 JSON 文件 = [] → validate_input 应优雅处理。"""

    def test_empty_projects_json(self, agent, tmp_path):
        """projects.json 为 [] → 不应抛 IndexError。"""
        data = _make_minimal_data(str(tmp_path), n=3)
        _write_json(data["projects"], [])
        try:
            agent.validate_input(data)
        except IndexError:
            pytest.fail("validate_input: 空 projects.json 抛 IndexError")
        except Exception:
            pass


# ═════════════════════════════════════════════════════════════════════
# B4: _preprocess_360 中 global_std = 0
# ═════════════════════════════════════════════════════════════════════


class Test360AllSameScores:
    """所有评分相同 → global_std = 0 → 2σ = 0 检查。"""

    def test_all_same_scores_std_zero(self, agent):
        """全部评分 = 3 → std = 0 → 异常检测不应报异常。"""
        rows = []
        for i in range(50):
            rows.append({
                "employee_id": f"T{i // 10:04d}", "evaluator_id": f"E{i}",
                "evaluator_role": "上级", "dimension": "专业能力",
                "score": 3, "comment": "评分相同。",
            })
        df = pd.DataFrame(rows)
        emp_df = pd.DataFrame([{"employee_id": "T0001", "job_sequence": "技术研发类"}])
        result = agent._preprocess_360(df, emp_df)
        summary = result["_summary"]
        assert summary["global_std"] == 0.0
        assert summary["anomalous_evaluators"] == 0


# ═════════════════════════════════════════════════════════════════════
# B5: employee_id 类型不匹配
# ═════════════════════════════════════════════════════════════════════


class TestEmployeeIDTypeMismatch:
    """employee_id 在表之间类型不匹配 → 数据无法关联。"""

    def test_employee_id_int_in_perf(self, agent, tmp_path, mock_context):
        """performance.csv 的 employee_id 为数字 ID → 与其他表字符串 ID 类型不匹配。"""
        # 使用纯数字 employee_id
        n = 3
        emp_rows = [
            {"employee_id": 1001 + i, "name": f"员工{i+1}", "age": 30 + i,
             "gender": "男", "education": "本科", "major": "计算机",
             "job_sequence": "技术研发类", "current_position": "工程师",
             "current_level": f"P{i+3}", "hire_date": "2020-01-01", "years_of_service": 6}
            for i in range(n)
        ]
        _write_csv(os.path.join(str(tmp_path), "employees.csv"), emp_rows)
        # performance 也使用整数 (但不指定 dtype → 读为 int64)
        perf_rows = []
        for emp in emp_rows:
            for y in [2024, 2025, 2026]:
                perf_rows.append({
                    "employee_id": emp["employee_id"], "year": y,
                    "performance_grade": "B",
                    "performance_comment": f"{y}年绩效良好。",
                })
        _write_csv(os.path.join(str(tmp_path), "performance.csv"), perf_rows)
        # projects.json 也用数字
        proj_rows = [{
            "employee_id": emp["employee_id"], "project_name": "测试项目",
            "role": "核心开发", "description": f"{emp['employee_id']}参与的项目",
            "tools_used": ["Python"],
        } for emp in emp_rows]
        _write_json(os.path.join(str(tmp_path), "projects.json"), proj_rows)
        data = {
            "employees": os.path.join(str(tmp_path), "employees.csv"),
            "performance": os.path.join(str(tmp_path), "performance.csv"),
            "projects": os.path.join(str(tmp_path), "projects.json"),
            "training": os.path.join(str(tmp_path), "training.csv"),
            "evaluation_360": os.path.join(str(tmp_path), "evaluation_360.csv"),
        }
        # 补 training 和 evaluation_360
        train_rows = [{
            "employee_id": emp["employee_id"], "course_name": "Python高级",
            "completion_date": "2025-03", "status": "已完成", "score": 85,
        } for emp in emp_rows]
        _write_csv(data["training"], train_rows)
        roles = ["上级", "同事", "下属", "HR"]
        dims = ["专业能力", "沟通协作"]
        eval_rows = []
        for emp in emp_rows:
            eid = emp["employee_id"]
            for dim in dims:
                for role in roles:
                    eval_rows.append({
                        "employee_id": eid, "evaluator_id": f"E{role}_{eid}",
                        "evaluator_role": role, "dimension": dim,
                        "score": 3, "comment": f"{role}评价。",
                    })
        _write_csv(data["evaluation_360"], eval_rows)

        assert agent.validate_input(data) is True
        dfs = agent._read_data_files(data)
        # employees 不指定 dtype → employee_id 可能是 int64
        emp_id_type = dfs["employees"]["employee_id"].dtype
        perf_id_type = dfs["performance"]["employee_id"].dtype
        # 如果两者类型不同 → 关联时会 0 匹配（安全）
        if emp_id_type != perf_id_type:
            emp_id_val = dfs["employees"].iloc[0]["employee_id"]
            matches = dfs["performance"]["employee_id"] == emp_id_val
            assert matches.sum() >= 0  # 不抛异常即通过


# ═════════════════════════════════════════════════════════════════════
# B6: _check_summary_lengths 的边界分支
# ═════════════════════════════════════════════════════════════════════


class TestCheckSummaryLengthsEdge:
    """摘要长度检查的边界分支测试。"""

    def test_original_exactly_30_chars(self):
        """原文恰好 30 字符 → 不进入特殊分支，用通用 1.5 倍规则。"""
        texts = {"performance_summary": "A" * 44}  # 30*1.5=45, 44<45
        flags = DataUnderstanding._check_summary_lengths(texts, "A" * 30, "", "")
        assert len(flags) == 0

    def test_original_29_chars(self):
        """原文 29 字符 → 进"原文不足 30 字"分支，上限 = 原文 × 2。"""
        texts = {"performance_summary": "A" * 57}  # 29*2=58, 57<58
        flags = DataUnderstanding._check_summary_lengths(texts, "A" * 29, "", "")
        assert len(flags) == 0

    def test_hit_short_original_upper_bound(self):
        """29 字原文 + 59 (=29×2+1) 字摘要 → 应标记。"""
        texts = {"performance_summary": "A" * 59}  # 59 > 58 → True
        flags = DataUnderstanding._check_summary_lengths(texts, "A" * 29, "", "")
        assert "performance_summary" in flags


# ═════════════════════════════════════════════════════════════════════
# B7: _merge_records 中 tools_used 字符串处理
# ═════════════════════════════════════════════════════════════════════


class TestToolsUsedEdgeCases:
    """tools_used 的序列化反序列化边界。"""

    def test_tools_used_string_json_list(self, agent, tmp_path):
        """tools_used 是 JSON 字符串 '["Python"]' → 应被正常反序列化为 list。"""
        data = _make_minimal_data(str(tmp_path), n=1)
        with open(data["projects"], "r", encoding="utf-8-sig") as f:
            proj = json.load(f)
        proj[0]["tools_used"] = '["Python", "Docker"]'
        _write_json(data["projects"], proj)
        dfs = agent._read_data_files(data)
        assert isinstance(dfs["projects"]["tools_used"].iloc[0], list)

    def test_tools_used_invalid_json_string(self, agent, tmp_path):
        """tools_used 是非法 JSON 字符串 → 应 fallback 为 [tools]。"""
        data = _make_minimal_data(str(tmp_path), n=1)
        with open(data["projects"], "r", encoding="utf-8-sig") as f:
            proj = json.load(f)
        proj[0]["tools_used"] = "not a json"
        _write_json(data["projects"], proj)
        dfs = agent._read_data_files(data)
        tools = dfs["projects"]["tools_used"].iloc[0]
        assert isinstance(tools, list)

    def test_tools_used_none(self, agent, tmp_path):
        """tools_used 为 None → 应 fallback 为 []。"""
        data = _make_minimal_data(str(tmp_path), n=1)
        with open(data["projects"], "r", encoding="utf-8-sig") as f:
            proj = json.load(f)
        proj[0]["tools_used"] = None
        _write_json(data["projects"], proj)
        dfs = agent._read_data_files(data)
        tools = dfs["projects"]["tools_used"].iloc[0]
        assert isinstance(tools, list)
        assert tools == []


# ═════════════════════════════════════════════════════════════════════
# B8: execute() 中 "degraded" vs "success" 的 metadata 对称性
# ═════════════════════════════════════════════════════════════════════


class TestDegradedPathMetadata:
    """degraded 路径的 metadata 必须与 success 对称（D3 原则）。"""

    SUCCESS_KEYS = {"agent_name", "agent_version", "duration_ms", "trace_id", "error", "data_lineage"}

    def test_degraded_via_run_has_expected_keys(self, agent, tmp_data):
        """run() 的 degraded 路径 metadata 应含 'error' key。"""
        context = {"trace_id": "test-symmetry", "timeout_seconds": 60}
        with patch("utils.llm_summarizer.summarize_employee_texts") as mock_llm, \
                patch("agents.data_understanding.time.sleep") as mock_sleep:
            mock_llm.return_value = _make_mock_summary(error="API 失败")
            result = agent.run(tmp_data, context)
        meta = result.get("metadata", {})
        for key in self.SUCCESS_KEYS:
            assert key in meta, f"degraded path metadata 缺失 key: {key}"

    def test_execute_metadata_has_error(self, agent, tmp_data, mock_context):
        """execute() 的 metadata 应有 error key（即使为 None）。"""
        with patch("utils.llm_summarizer.summarize_employee_texts") as mock_llm, \
                patch("agents.data_understanding.time.sleep") as mock_sleep:
            mock_llm.return_value = _make_mock_summary("良好", "核心开发", "好", anchors={})
            result = agent.execute(tmp_data, mock_context)
        meta = result.get("metadata", {})
        assert "error" in meta, "execute metadata 缺少 error key（D3 对称性违规）"


# ═════════════════════════════════════════════════════════════════════
# B9: 指数退避的边界值
# ═════════════════════════════════════════════════════════════════════


class TestBackoffBoundary:
    """指数退避边界确认。"""

    def test_backoff_capped_properly(self):
        """确保 8→15s 上限。"""
        with patch("agents.data_understanding.time.sleep") as mock_sleep:
            DataUnderstanding._apply_backoff(7)
            assert mock_sleep.call_args[0][0] == 14.0
            DataUnderstanding._apply_backoff(8)
            assert mock_sleep.call_args[0][0] == 15.0
            DataUnderstanding._apply_backoff(100)
            assert mock_sleep.call_args[0][0] == 15.0

    def test_apply_backoff_zero_passes(self):
        """0 次失败 → 不应 sleep。"""
        with patch("agents.data_understanding.time.sleep") as mock_sleep:
            DataUnderstanding._apply_backoff(0)
            mock_sleep.assert_not_called()


# ═════════════════════════════════════════════════════════════════════
# B10: 空数据源文件的读取
# ═════════════════════════════════════════════════════════════════════


class TestEmptyDataFiles:
    """空数据源文件的边界。"""

    def test_empty_csv_nonzero_rows(self, agent, tmp_path, mock_context):
        """所有 CSV 唯余表头 → 不应崩溃。"""
        data = _make_minimal_data(str(tmp_path), n=0)
        with patch("utils.llm_summarizer.summarize_employee_texts") as mock_llm, \
                patch("agents.data_understanding.time.sleep"):
            mock_llm.return_value = _make_mock_summary(error="无效")
            result = agent.execute(data, mock_context)
        assert result["status"] in ("success", "degraded", "error")
        if result["data"] is not None:
            assert len(result["data"]["employees"]) == 0

    def test_single_employee_single_evaluator(self, agent, tmp_path, mock_context):
        """1 员工 1 评价者 → 最小化边界。"""
        data = _make_minimal_data(str(tmp_path), n=1)
        with patch("utils.llm_summarizer.summarize_employee_texts") as mock_llm, \
                patch("agents.data_understanding.time.sleep"):
            mock_llm.return_value = _make_mock_summary("绩效", "项目", "评价", anchors={})
            result = agent.execute(data, mock_context)
        assert result["status"] in ("success", "degraded")
        if result["data"]:
            assert len(result["data"]["employees"]) == 1
            assert result["data"]["scores_360"].get("T0001") is not None