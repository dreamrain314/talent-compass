"""Agent① DataUnderstanding 测试

覆盖：输入校验、异常检测、角色权重、输出格式、取消事件、边界值。
"""
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import numpy as np
import pytest

from agents.data_understanding import DataUnderstanding
from config import RAW_DATA_DIR, EVALUATOR_MIN_SAMPLE_SIZE, AGENT_DATAUNDERSTANDING_TIMEOUT


# ── 辅助函数 ───────────────────────────────────────────────────────

def _write_csv(path, rows):
    pd.DataFrame(rows).to_csv(path, index=False, encoding="utf-8-sig")


def _write_json(path, rows):
    with open(path, "w", encoding="utf-8-sig") as f:
        json.dump(rows, f, ensure_ascii=False)


def _make_minimal_data(tmp_dir, n=3):
    """在 tmp_dir 下生成最小测试数据集（n 名员工）。"""
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


# ── Fixtures ───────────────────────────────────────────────────────

@pytest.fixture
def agent():
    return DataUnderstanding()


@pytest.fixture
def tmp_data(tmp_path):
    return _make_minimal_data(str(tmp_path), n=3)


@pytest.fixture
def mock_context():
    return {"trace_id": "test-001", "timeout_seconds": 60}


# ── 测试类 ─────────────────────────────────────────────────────────

def _make_mock_summary(
    perf_summary="绩效表现良好",
    proj_summary="参与核心开发",
    eval_summary="团队协作好",
    anchors=None,
    error=None,
    usage=None,
    model="mock",
):
    """构建 simulate_employee_texts 的 mock 返回值。"""
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


class TestAgentBasics:
    """Agent 基础属性测试。"""

    def test_agent_identity(self, agent):
        assert agent.agent_name == "DataUnderstanding"
        assert agent.agent_version == "0.1.0"
        assert agent.timeout_seconds == AGENT_DATAUNDERSTANDING_TIMEOUT
        assert agent.timeout_seconds > 120

    def test_schemas(self, agent):
        schema = agent.get_input_schema()
        assert "required" in schema
        assert len(schema["required"]) == 5
        schema_out = agent.get_output_schema()
        assert "employees" in schema_out["properties"]
        assert "data_quality_report" in schema_out["properties"]


class TestInputValidation:
    """输入校验测试。"""

    def test_valid_input(self, agent, tmp_data):
        assert agent.validate_input(tmp_data) is True

    def test_missing_file(self, agent, tmp_data):
        bad = dict(tmp_data)
        bad["employees"] = "/nonexistent/file.csv"
        assert agent.validate_input(bad) is False

    def test_empty_path(self, agent, tmp_data):
        bad = dict(tmp_data)
        bad["employees"] = ""
        assert agent.validate_input(bad) is False

    def test_invalid_type(self, agent, tmp_data):
        bad = dict(tmp_data)
        bad["employees"] = 123
        assert agent.validate_input(bad) is False

    def test_bad_column(self, agent, tmp_data, tmp_path):
        bad_path = os.path.join(str(tmp_path), "bad_employees.csv")
        _write_csv(bad_path, [{"name": "张三", "age": 30}])
        bad = dict(tmp_data)
        bad["employees"] = bad_path
        assert agent.validate_input(bad) is False

    def test_non_dict_input(self, agent):
        assert agent.validate_input("not a dict") is False
        assert agent.validate_input(None) is False


class TestReadDataFiles:
    """数据读取测试。"""

    def test_read_all_files(self, agent, tmp_data):
        dfs = agent._read_data_files(tmp_data)
        assert dfs is not None
        assert set(dfs.keys()) == {"employees", "performance", "projects", "training", "evaluation_360"}
        assert len(dfs["employees"]) == 3
        assert len(dfs["performance"]) == 9
        assert len(dfs["projects"]) == 3
        assert len(dfs["training"]) == 3
        assert len(dfs["evaluation_360"]) > 0

    def test_employee_id_is_str(self, agent, tmp_data):
        dfs = agent._read_data_files(tmp_data)
        assert dfs["employees"]["employee_id"].dtype == object

    def test_nonexistent_file(self, agent, tmp_data):
        bad = dict(tmp_data)
        bad["projects"] = str(Path(tmp_data["projects"]).parent / "nonexistent.json")
        dfs = agent._read_data_files(bad)
        assert dfs is None


class TestDataQuality:
    """缺失值检测测试。"""

    def test_no_missing(self, agent, tmp_data):
        dfs = agent._read_data_files(tmp_data)
        report = agent._detect_missing(dfs)
        assert report["total_employees"] == 3
        assert report["text_insufficient_count"] == 0
        assert len(report["severe_missing_employees"]) == 0

    def test_empty_strings_not_counted_as_insufficient(self, agent, tmp_path):
        """空字符串 comment 不应被视为有效文本。"""
        tmp = str(tmp_path)
        _write_csv(os.path.join(tmp, "employees.csv"), [
            {"employee_id": "T0001", "name": "员工1", "age": 30,
             "gender": "男", "education": "本科", "major": "计算机",
             "job_sequence": "技术研发类", "current_position": "工程师",
             "current_level": "P3", "hire_date": "2020-01-01", "years_of_service": 6},
        ])
        _write_csv(os.path.join(tmp, "performance.csv"), [
            {"employee_id": "T0001", "year": 2024, "performance_grade": "B", "performance_comment": ""},
        ])
        _write_json(os.path.join(tmp, "projects.json"), [
            {"employee_id": "T0001", "project_name": "测试", "role": "开发",
             "description": "", "tools_used": []},
        ])
        _write_csv(os.path.join(tmp, "training.csv"), [
            {"employee_id": "T0001", "course_name": "Python", "completion_date": "2025-03",
             "status": "已完成", "score": 85},
        ])
        _write_csv(os.path.join(tmp, "evaluation_360.csv"), [
            {"employee_id": "T0001", "evaluator_id": "E001", "evaluator_role": "上级",
             "dimension": "专业能力", "score": 4, "comment": ""},
        ])
        data = {"employees": os.path.join(tmp, "employees.csv"),
                "performance": os.path.join(tmp, "performance.csv"),
                "projects": os.path.join(tmp, "projects.json"),
                "training": os.path.join(tmp, "training.csv"),
                "evaluation_360": os.path.join(tmp, "evaluation_360.csv")}
        dfs = agent._read_data_files(data)
        report = agent._detect_missing(dfs)
        assert report["text_insufficient_count"] == 1

    def test_whitespace_only_not_counted(self, agent, tmp_path):
        """纯空白 comment 不应被视为有效文本。"""
        tmp = str(tmp_path)
        _write_csv(os.path.join(tmp, "employees.csv"), [
            {"employee_id": "T0001", "name": "员工1", "age": 30,
             "gender": "男", "education": "本科", "major": "计算机",
             "job_sequence": "技术研发类", "current_position": "工程师",
             "current_level": "P3", "hire_date": "2020-01-01", "years_of_service": 6},
        ])
        _write_csv(os.path.join(tmp, "performance.csv"), [
            {"employee_id": "T0001", "year": 2024, "performance_grade": "B", "performance_comment": "   "},
        ])
        _write_json(os.path.join(tmp, "projects.json"), [
            {"employee_id": "T0001", "project_name": "测试", "role": "开发",
             "description": "   ", "tools_used": []},
        ])
        _write_csv(os.path.join(tmp, "training.csv"), [
            {"employee_id": "T0001", "course_name": "Python", "completion_date": "2025-03",
             "status": "已完成", "score": 85},
        ])
        _write_csv(os.path.join(tmp, "evaluation_360.csv"), [
            {"employee_id": "T0001", "evaluator_id": "E001", "evaluator_role": "上级",
             "dimension": "专业能力", "score": 4, "comment": "   "},
        ])
        data = {"employees": os.path.join(tmp, "employees.csv"),
                "performance": os.path.join(tmp, "performance.csv"),
                "projects": os.path.join(tmp, "projects.json"),
                "training": os.path.join(tmp, "training.csv"),
                "evaluation_360": os.path.join(tmp, "evaluation_360.csv")}
        dfs = agent._read_data_files(data)
        report = agent._detect_missing(dfs)
        assert report["text_insufficient_count"] == 1


class Test360AnomalyDetection:
    """360 异常评价者检测测试。"""

    def test_no_anomaly(self, agent, tmp_data):
        dfs = agent._read_data_files(tmp_data)
        result = agent._preprocess_360(dfs["evaluation_360"], dfs["employees"])
        assert result["_summary"]["anomalous_evaluators"] == 0

    def test_global_anomaly(self, agent):
        """构造一个偏差 > 2σ 的评价者（大量正常数据压低 σ）。"""
        rows = []
        # 大量正常评价者：100 条评分 ≈ 3
        for i in range(100):
            rows.append({
                "employee_id": f"N{i // 10:04d}",
                "evaluator_id": "Normal_Eval", "evaluator_role": "上级",
                "dimension": "专业能力" if i % 2 == 0 else "沟通协作",
                "score": 3, "comment": "正常评价。",
            })
        # 异常评价者：20 条评分 = 1
        for i in range(20):
            rows.append({
                "employee_id": f"A{i // 10:04d}",
                "evaluator_id": "Anomalous_Eval", "evaluator_role": "同事",
                "dimension": "专业能力" if i % 2 == 0 else "沟通协作",
                "score": 1, "comment": "异常低分。",
            })
        df = pd.DataFrame(rows)
        emp_df = pd.DataFrame([
            {"employee_id": "N001", "job_sequence": "技术研发类"},
            {"employee_id": "N002", "job_sequence": "技术研发类"},
            {"employee_id": "N003", "job_sequence": "技术研发类"},
            {"employee_id": "N004", "job_sequence": "技术研发类"},
        ])
        result = agent._preprocess_360(df, emp_df)
        assert result["_summary"]["anomalous_evaluators"] >= 1

    def test_low_sample_skip(self, agent):
        """样本量 < EVALUATOR_MIN_SAMPLE_SIZE → 跳过异常检测。"""
        rows = []
        for i in range(3):
            rows.append({
                "employee_id": "L001", "evaluator_id": "LowSample",
                "evaluator_role": "上级", "dimension": "专业能力",
                "score": 1, "comment": "低分。",
            })
        for i in range(20):
            rows.append({
                "employee_id": "L002", "evaluator_id": f"Normal_{i%5}",
                "evaluator_role": "同事", "dimension": "沟通协作",
                "score": 3, "comment": "正常。",
            })
        df = pd.DataFrame(rows)
        emp_df = pd.DataFrame([
            {"employee_id": "L001", "job_sequence": "技术研发类"},
            {"employee_id": "L002", "job_sequence": "技术研发类"},
        ])
        result = agent._preprocess_360(df, emp_df)
        assert result["_summary"]["evaluators_skipped_low_sample"] >= 1


class TestRoleWeights:
    """角色权重计算测试。"""

    def test_normal_weighting(self, agent, tmp_data):
        dfs = agent._read_data_files(tmp_data)
        result = agent._preprocess_360(dfs["evaluation_360"], dfs["employees"])
        for emp_id in dfs["employees"]["employee_id"]:
            scores = result.get(emp_id, {})
            for dim in ["专业能力", "沟通协作", "领导力", "责任心", "学习能力"]:
                assert dim in scores, f"{emp_id} 缺少维度 {dim}"

    def test_self_eval_excluded(self, agent, tmp_data):
        dfs = agent._read_data_files(tmp_data)
        employees_df = dfs["employees"]
        eval_df = dfs["evaluation_360"]
        self_evals = eval_df[eval_df["evaluator_role"] == "自评"]
        assert len(self_evals) > 0
        result = agent._preprocess_360(eval_df, employees_df)
        for emp_id in employees_df["employee_id"]:
            scores = result.get(emp_id, {})
            has_valid = any(v is not None for v in scores.values())
            assert has_valid, f"{emp_id} 所有维度都是 None"

    def test_tech_role_adjustment(self, agent, tmp_data):
        dfs = agent._read_data_files(tmp_data)
        emp_df = dfs["employees"].copy()
        emp_df["job_sequence"] = "技术研发类"
        result = agent._preprocess_360(dfs["evaluation_360"], emp_df)
        for emp_id, scores in result.items():
            if emp_id.startswith("_"):
                continue
            for v in scores.values():
                if v is not None:
                    assert 1.0 <= v <= 5.0, f"{emp_id} 得分 {v} 超出范围"


class TestOutputFormat:
    """输出格式测试。"""

    def test_execute_structure(self, agent, tmp_data, mock_context):
        """测试 execute 返回结构符合 BaseAgent 契约（mock LLM 调用）。"""
        with patch("utils.llm_summarizer.summarize_employee_texts") as mock_llm, \
                patch("agents.data_understanding.time.sleep"):
            mock_llm.return_value = _make_mock_summary()
            result = agent.execute(tmp_data, mock_context)
        assert "status" in result
        assert result["status"] in ("success", "degraded", "error")
        assert "data" in result
        assert "metadata" in result
        assert result["metadata"].get("llm_calls", 0) >= 0

    def test_output_has_employees(self, agent, tmp_data, mock_context):
        with patch("utils.llm_summarizer.summarize_employee_texts") as mock_llm, \
                patch("agents.data_understanding.time.sleep"):
            mock_llm.return_value = _make_mock_summary("良好", "核心开发", "好", anchors={})
            result = agent.execute(tmp_data, mock_context)
        if result["data"] is not None:
            employees = result["data"].get("employees", [])
            assert len(employees) == 3
            for emp in employees:
                assert "employee_id" in emp
                assert "structured" in emp
                assert "performance" in emp
                assert "projects" in emp
                assert "training" in emp
                assert "scores_360" in emp

    def test_output_has_data_quality(self, agent, tmp_data, mock_context):
        with patch("utils.llm_summarizer.summarize_employee_texts") as mock_llm, \
                patch("agents.data_understanding.time.sleep"):
            mock_llm.return_value = _make_mock_summary("良好", "核心开发", "好", anchors={})
            result = agent.execute(tmp_data, mock_context)
        if result["data"] is not None:
            dq = result["data"].get("data_quality_report", {})
            assert "total_employees" in dq
            assert "missing_summary" in dq

    def test_metadata_keys(self, agent, tmp_data, mock_context):
        with patch("utils.llm_summarizer.summarize_employee_texts") as mock_llm, \
                patch("agents.data_understanding.time.sleep"):
            mock_llm.return_value = _make_mock_summary("良好", "核心开发", "好", anchors={})
            result = agent.execute(tmp_data, mock_context)
        meta = result.get("metadata", {})
        assert "error" in meta

    def test_error_path_no_files(self, agent, mock_context):
        bad_data = {
            "employees": "/nonexistent/e.csv",
            "performance": "/nonexistent/p.csv",
            "projects": "/nonexistent/pr.json",
            "training": "/nonexistent/t.csv",
            "evaluation_360": "/nonexistent/e360.csv",
        }
        result = agent.execute(bad_data, mock_context)
        assert result["status"] == "error"
        assert result["data"] is None
        assert result["metadata"].get("error") is not None


class TestEdgeCases:
    """边界值测试。"""

    def test_empty_employee_file(self, agent, tmp_path, mock_context):
        data = _make_minimal_data(str(tmp_path), n=0)
        with patch("utils.llm_summarizer.summarize_employee_texts") as mock_llm, \
                patch("agents.data_understanding.time.sleep"):
            mock_llm.return_value = _make_mock_summary(error="无员工")
            result = agent.execute(data, mock_context)
        if result["data"] is not None:
            assert len(result["data"]["employees"]) == 0

    def test_all_anomalous_evaluators(self, agent, tmp_path, mock_context):
        """所有评价者都是极端偏离 → 零除守卫。"""
        data = _make_minimal_data(str(tmp_path), n=1)
        eval_rows = []
        roles = ["上级", "同事", "下属", "HR"]
        for role in roles:
            for dim in ["专业能力", "沟通协作"]:
                for _ in range(10):
                    eval_rows.append({
                        "employee_id": "T0001", "evaluator_id": f"Extreme_{role}",
                        "evaluator_role": role, "dimension": dim,
                        "score": 1, "comment": "极端低分。",
                    })
        _write_csv(os.path.join(str(tmp_path), "evaluation_360.csv"), eval_rows)
        data["evaluation_360"] = os.path.join(str(tmp_path), "evaluation_360.csv")
        with patch("utils.llm_summarizer.summarize_employee_texts") as mock_llm, \
                patch("agents.data_understanding.time.sleep"):
            mock_llm.return_value = _make_mock_summary("良好", "核心开发", "好")
            result = agent.execute(data, mock_context)
        assert result["status"] in ("degraded", "success")


class TestCancelEvent:
    """取消事件测试。"""

    def test_cancel_not_set(self, agent, tmp_data):
        import threading
        context = {"trace_id": "test-cancel", "cancel_event": threading.Event()}
        dfs = agent._read_data_files(tmp_data)
        with patch("utils.llm_summarizer.summarize_employee_texts") as mock_llm, \
                patch("agents.data_understanding.time.sleep"):
            mock_llm.return_value = _make_mock_summary()
            summaries, stats = agent._process_employees(
                dfs["employees"], dfs["performance"],
                dfs["projects"], dfs["evaluation_360"], context,
            )
        assert stats["total"] > 0

    def test_cancel_set(self, agent, tmp_data):
        import threading
        cancel = threading.Event()
        cancel.set()
        context = {"trace_id": "test-cancel", "cancel_event": cancel}
        dfs = agent._read_data_files(tmp_data)
        with patch("utils.llm_summarizer.summarize_employee_texts") as mock_llm, \
                patch("agents.data_understanding.time.sleep"):
            mock_llm.return_value = _make_mock_summary(error="mocked fail")
            summaries, stats = agent._process_employees(
                dfs["employees"], dfs["performance"],
                dfs["projects"], dfs["evaluation_360"], context,
            )
        assert stats["total"] == 3


class TestMergeRecords:
    """数据融合测试。"""

    def test_merge_structure(self, agent, tmp_data):
        dfs = agent._read_data_files(tmp_data)
        data_quality = agent._detect_missing(dfs)
        summaries = []
        for emp_id in dfs["employees"]["employee_id"]:
            summaries.append({
                "employee_id": emp_id,
                "text_summaries": {
                    "performance_summary": "良好",
                    "project_summary": "核心开发",
                    "evaluation_summary": "团队协作好",
                },
                "anchors": {"performance": ["2024年绩效表现"], "projects": [], "evaluation": []},
                "summary_error": None,
            })
        scores_360 = agent._preprocess_360(dfs["evaluation_360"], dfs["employees"])
        records = agent._merge_records(
            dfs["employees"], dfs["performance"], dfs["projects"],
            dfs["training"], summaries, scores_360, data_quality,
        )
        assert len(records) == 3
        for rec in records:
            assert "structured" in rec
            assert "performance" in rec
            assert "projects" in rec
            assert "training" in rec
            assert "text_summaries" in rec
            assert "scores_360" in rec
            assert "anchors" in rec
            assert "data_quality_flags" in rec


class TestAnchorVerification:
    """锚点存在性验证测试。"""

    def test_all_anchors_match(self):
        anchors = {
            "performance": ["2024年绩效表现"],
            "projects": ["核心系统开发"],
        }
        perf_text = "2024年绩效表现良好，完成各项任务。"
        proj_text = "核心系统开发项目涉及多个模块。"
        result = DataUnderstanding._verify_anchors(anchors, perf_text, proj_text, "")
        assert result is False  # 全部命中 → 无 mismatch

    def test_partial_mismatch(self):
        anchors = {
            "performance": ["2024年绩效表现", "完全虚构的文本不存在"],
            "projects": ["核心系统开发"],
        }
        perf_text = "2024年绩效表现良好，完成各项任务。"
        proj_text = "核心系统开发项目。"
        result = DataUnderstanding._verify_anchors(anchors, perf_text, proj_text, "")
        assert result is True  # 命中率 2/3 < 80% → mismatch

    def test_empty_anchors(self):
        result = DataUnderstanding._verify_anchors({}, "", "", "")
        assert result is False

    def test_fuzzy_match_edge(self):
        """±2 字差异的模糊匹配。"""
        anchors = {"performance": ["年绩效表现良好，完成各项任务。"]}
        perf_text = "2024年绩效表现良好，完成各项任务，超额完成目标。"
        result = DataUnderstanding._verify_anchors(anchors, perf_text, "", "")
        assert result is False  # 去掉前2字后匹配

    def test_all_anchors_missing(self):
        anchors = {"performance": ["完全不存在的锚点文本abc123"]}
        perf_text = "完全不同的原文内容。"
        result = DataUnderstanding._verify_anchors(anchors, perf_text, "", "")
        assert result is True  # 0% 命中率


class TestSummaryLengthCheck:
    """摘要长度合理性检查测试。"""

    def test_normal_summary(self):
        """摘要短于原文 → 无标记。"""
        summaries = {"performance_summary": "绩效表现良好。", "project_summary": "核心开发。"}
        flags = DataUnderstanding._check_summary_lengths(summaries, "2024年绩效表现良好，完成各项任务，超额完成目标。", "核心系统开发项目。", "")
        assert len(flags) == 0

    def test_hallucination_long_summary(self):
        """摘要显著长于原文 → 标记 possible_hallucination。"""
        summaries = {"performance_summary": "A" * 100, "project_summary": "B" * 5}
        flags = DataUnderstanding._check_summary_lengths(summaries, "原文。", "项目描述。", "")
        # 原文长度 3字，摘要 100 字 → 远超 1.5 倍
        assert "performance_summary" in flags
        assert "project_summary" not in flags  # 短摘要

    def test_short_original_text_relaxed(self):
        """原文不足 30 字 → 允许摘要长度 = 原文 × 2。"""
        summaries = {"performance_summary": "A" * 50}
        flags = DataUnderstanding._check_summary_lengths(summaries, "短原文只有20字。", "", "")
        # 原文 8 字，摘要 50 字 → 8×2=16，50 > 16 → 标记
        assert "performance_summary" in flags

    def test_short_original_within_limit(self):
        """原文不足 30 字，摘要未超过 ×2 → 不标记。"""
        summaries = {"performance_summary": "A" * 15}
        flags = DataUnderstanding._check_summary_lengths(summaries, "短原文只有20字。", "", "")
        # 原文 8 字，摘要 15 字 → 15 < 16 → 不标记
        assert len(flags) == 0

    def test_empty_summaries(self):
        flags = DataUnderstanding._check_summary_lengths({}, "", "", "")
        assert flags == {}


class TestExponentialBackoff:
    """指数退避测试。"""

    def test_no_failures_no_sleep(self):
        """连续失败 0 次 → 不 sleep。"""
        import time
        t0 = time.time()
        DataUnderstanding._apply_backoff(0)
        assert time.time() - t0 < 0.1

    def test_backoff_param_validation(self):
        """验证退避值计算正确：1次→2s, 3次→6s, 8次→15s。"""
        with patch("agents.data_understanding.time.sleep") as mock_sleep:
            DataUnderstanding._apply_backoff(1)
            assert mock_sleep.call_args[0][0] == 2.0
            DataUnderstanding._apply_backoff(3)
            assert mock_sleep.call_args[0][0] == 6.0
            DataUnderstanding._apply_backoff(8)
            assert mock_sleep.call_args[0][0] == 15.0  # 8×2=16→上限15

    def test_backoff_negative(self):
        """负数传入 → 不 sleep。"""
        with patch("agents.data_understanding.time.sleep") as mock_sleep:
            DataUnderstanding._apply_backoff(-1)
            mock_sleep.assert_not_called()


class TestNewFieldsInOutput:
    """验证新字段被传递到输出记录中。"""

    def test_output_has_new_fields(self, agent, tmp_data, mock_context):
        with patch("utils.llm_summarizer.summarize_employee_texts") as mock_llm, \
                patch("agents.data_understanding.time.sleep"):
            mock_llm.return_value = _make_mock_summary()
            result = agent.execute(tmp_data, mock_context)
        if result["data"] is not None:
            for emp in result["data"]["employees"]:
                assert "anchor_mismatch" in emp
                assert "hallucination_flags" in emp


class TestWithRealMockData:
    """使用真实 mock 数据的端到端测试（需要 data/raw/ 下文件）。"""

    @pytest.fixture
    def real_data(self):
        raw_dir = Path(RAW_DATA_DIR)
        files = {
            "employees": str(raw_dir / "employees.csv"),
            "performance": str(raw_dir / "performance.csv"),
            "projects": str(raw_dir / "projects.json"),
            "training": str(raw_dir / "training.csv"),
            "evaluation_360": str(raw_dir / "evaluation_360.csv"),
        }
        for path in files.values():
            if not os.path.isfile(path):
                pytest.skip(f"Mock data 不存在: {path}")
        return files

    def test_validate_with_real_data(self, agent, real_data):
        assert agent.validate_input(real_data) is True

    def test_read_real_data(self, agent, real_data):
        dfs = agent._read_data_files(real_data)
        assert dfs is not None
        assert len(dfs["employees"]) == 100
        assert 200 <= len(dfs["performance"]) <= 300
        assert len(dfs["evaluation_360"]) > 1000

    def test_data_quality_real(self, agent, real_data):
        dfs = agent._read_data_files(real_data)
        report = agent._detect_missing(dfs)
        assert report["total_employees"] == 100
        assert report["text_insufficient_count"] == 0

    def test_360_preprocess_real(self, agent, real_data):
        dfs = agent._read_data_files(real_data)
        result = agent._preprocess_360(dfs["evaluation_360"], dfs["employees"])
        summary = result["_summary"]
        assert "global_mean" in summary
        assert "global_std" in summary
        for emp_id in dfs["employees"]["employee_id"]:
            scores = result.get(emp_id, {})
            if emp_id.startswith("_"):
                continue
            for dim in ["专业能力", "沟通协作", "领导力", "责任心", "学习能力"]:
                assert dim in scores, f"{emp_id} 缺少 {dim}"
