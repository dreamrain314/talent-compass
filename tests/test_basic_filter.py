"""BasicFilter 单元测试 — 12 + 边界测试

覆盖计划文档中列出的 12 个核心场景及额外边界值。
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from filter.basic_filter import BasicFilter
from utils import numpy_to_native

# ── 测试数据路径 ───────────────────────────────────────────────────────────
DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"
EMPLOYEES_CSV = DATA_DIR / "employees.csv"
PERFORMANCE_CSV = DATA_DIR / "performance.csv"


# ── Fixtures ───────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def employees_df() -> pd.DataFrame:
    """加载真实模拟员工数据（100 人）。"""
    return pd.read_csv(EMPLOYEES_CSV, encoding="utf-8-sig")


@pytest.fixture(scope="module")
def performance_df() -> pd.DataFrame:
    """加载真实模拟绩效数据（297 条）。"""
    return pd.read_csv(PERFORMANCE_CSV, encoding="utf-8-sig")


@pytest.fixture
def filter_(employees_df: pd.DataFrame, performance_df: pd.DataFrame) -> BasicFilter:
    """构造 BasicFilter 实例。"""
    return BasicFilter(employees_df, performance_df)


# ── 辅助函数 ───────────────────────────────────────────────────────────────

def _ids(result: dict) -> set[str]:
    """从过滤结果中提取 employee_id 集合。"""
    return {e["employee_id"] for e in result["filtered_employees"]}


# ═══════════════════════════════════════════════════════════════════════════
# 测试用例
# ═══════════════════════════════════════════════════════════════════════════

class TestAgeRange:
    """1. age_range 正常区间过滤"""

    def test_normal_range(self, filter_: BasicFilter, employees_df: pd.DataFrame):
        result = filter_.apply({"age_range": [30, 45]})
        assert 0 < result["total_after"] < result["total_before"]
        for e in result["filtered_employees"]:
            assert 30 <= e["age"] <= 45

    def test_no_lower_bound(self, filter_: BasicFilter):
        """min=0 → 不过滤下限"""
        result = filter_.apply({"age_range": [0, 30]})
        for e in result["filtered_employees"]:
            assert e["age"] <= 30

    def test_no_upper_bound(self, filter_: BasicFilter):
        """max=999 → 不过滤上限"""
        result = filter_.apply({"age_range": [45, 999]})
        for e in result["filtered_employees"]:
            assert e["age"] >= 45

    def test_all_filtered_out(self, filter_: BasicFilter):
        """age_range=[0,0] → 全部排除"""
        result = filter_.apply({"age_range": [0, 0]})
        assert result["total_after"] == 0
        assert result["filter_log"][-1].get("note") == "建议放宽条件"


class TestPoliticalStatus:
    """2. political_status 多选过滤"""

    def test_single_value(self, filter_: BasicFilter):
        result = filter_.apply({"political_status": ["中共党员"]})
        for e in result["filtered_employees"]:
            assert e["political_status"] == "中共党员"

    def test_multiple_values(self, filter_: BasicFilter):
        result = filter_.apply({"political_status": ["中共党员", "共青团员"]})
        for e in result["filtered_employees"]:
            assert e["political_status"] in ("中共党员", "共青团员")

    def test_empty_list(self, filter_: BasicFilter):
        """空列表 → 不过滤"""
        result = filter_.apply({"political_status": []})
        assert result["total_after"] == result["total_before"]


class TestMajorKeywords:
    """3. major_keywords 关键词 OR 匹配"""

    def test_single_keyword(self, filter_: BasicFilter, employees_df: pd.DataFrame):
        result = filter_.apply({"major_keywords": ["计算机"]})
        for e in result["filtered_employees"]:
            assert "计算机" in e["major"]

    def test_multiple_keywords_or(self, filter_: BasicFilter, employees_df: pd.DataFrame):
        """多个关键词 OR 关系"""
        result = filter_.apply({"major_keywords": ["计算机", "软件"]})
        for e in result["filtered_employees"]:
            assert "计算机" in e["major"] or "软件" in e["major"]

    def test_special_characters(self, filter_: BasicFilter):
        """特殊字符不应引发异常"""
        result = filter_.apply({"major_keywords": ["(test)", "[.*+]"]})
        # 没有专业匹配这些关键词，但不应抛异常
        assert result["total_after"] == 0

    def test_empty_list(self, filter_: BasicFilter):
        """空列表 → 不过滤"""
        result = filter_.apply({"major_keywords": []})
        assert result["total_after"] == result["total_before"]


class TestMinYearsOfService:
    """4. min_years_of_service 工龄下限"""

    def test_zero_passes_all(self, filter_: BasicFilter):
        """0 → 全通过"""
        result = filter_.apply({"min_years_of_service": 0})
        assert result["total_after"] == result["total_before"]

    def test_normal_threshold(self, filter_: BasicFilter):
        """5 年 → 工龄 >=5"""
        result = filter_.apply({"min_years_of_service": 5})
        for e in result["filtered_employees"]:
            assert e["years_of_service"] >= 5

    def test_high_threshold(self, filter_: BasicFilter):
        """50 → 全部排除"""
        result = filter_.apply({"min_years_of_service": 50})
        assert result["total_after"] == 0


class TestLevelRange:
    """5. level_range 数值比较（防字符串序）"""

    def test_normal_range(self, filter_: BasicFilter, employees_df: pd.DataFrame):
        """P5-P8 → 应包含 P5-P8，不应包含 P1-P4 或 P9"""
        result = filter_.apply({"level_range": ["P5", "P8"]})
        for e in result["filtered_employees"]:
            level_num = int(e["current_level"][1:])
            assert 5 <= level_num <= 8

    def test_numeric_not_string(self, filter_: BasicFilter):
        """P10 > P5，但字符串序 "P10" < "P5" 为 True → 确保用数值比较"""
        # 创建一个有 P10 的临时 DataFrame
        df = pd.DataFrame({
            "employee_id": ["T001", "T002", "T003"],
            "current_level": ["P10", "P5", "P8"],
            "age": [30, 30, 30],
            "years_of_service": [5, 5, 5],
            "hire_date": ["2015-01-01", "2015-01-01", "2015-01-01"],
            "political_status": ["群众", "群众", "群众"],
            "major": ["计算机", "计算机", "计算机"],
        })
        pf = pd.DataFrame(columns=["employee_id", "year", "performance_grade"])
        f = BasicFilter(df, pf)
        result = f.apply({"level_range": ["P5", "P8"]})
        ids = {e["employee_id"] for e in result["filtered_employees"]}
        # P10 应被排除（数值 10 > 8），P5 和 P8 应保留
        assert "T001" not in ids, "P10 数值 10 > 8，不应被包含"
        assert "T002" in ids
        assert "T003" in ids

    def test_malformed_value(self, filter_: BasicFilter):
        """畸形值（如空字符串）→ 标记 skipped"""
        # 创建一个有空职级的 DataFrame
        df = pd.DataFrame({
            "employee_id": ["T001", "T002"],
            "current_level": ["P5", ""],
            "age": [30, 30],
            "years_of_service": [5, 5],
            "hire_date": ["2015-01-01", "2015-01-01"],
            "political_status": ["群众", "群众"],
            "major": ["计算机", "计算机"],
        })
        pf = pd.DataFrame(columns=["employee_id", "year", "performance_grade"])
        f = BasicFilter(df, pf)
        result = f.apply({"level_range": ["P5", "P8"]})
        assert "level_range" in result["skipped_conditions"]


class TestMinPerformance:
    """6. min_performance 绩效底线过滤"""

    def test_grade_b(self, filter_: BasicFilter, employees_df: pd.DataFrame):
        """底线 B → 排除有 C/D 绩效的员工"""
        result = filter_.apply({"min_performance": "B"})
        assert result["total_after"] > 0
        # 检查 filter_log 中 min_performance 条目
        logs = [log for log in result["filter_log"] if log["condition"] == "min_performance"]
        assert len(logs) == 1
        assert logs[0]["removed_count"] > 0  # 一定有被排除的

    def test_grade_d(self, filter_: BasicFilter):
        """底线 D → 几乎全通过（D 是最低）"""
        result = filter_.apply({"min_performance": "D"})
        # D 是最低等级，几乎所有人通过
        assert result["total_after"] == result["total_before"]

    def test_case_insensitive(self, filter_: BasicFilter):
        """大小写不敏感"""
        result_lower = filter_.apply({"min_performance": "b"})
        result_upper = filter_.apply({"min_performance": "B"})
        assert result_lower["total_after"] == result_upper["total_after"]


class TestNewEmployee:
    """7. 新员工不排除"""

    def test_new_employee_not_excluded(self, filter_: BasicFilter):
        """2026 年入职员工 → 无完整年度绩效 → insufficient_data 标记，不排除"""
        result = filter_.apply({"min_performance": "B"})
        logs = [log for log in result["filter_log"] if log["condition"] == "min_performance"]
        if logs and "insufficient_data" in logs[0]:
            ids = _ids(result)
            # JZ0010 是 2026 年入职，应有 insufficient_data 但仍在结果中
            assert "JZ0010" in ids

    def test_insufficient_data_logged(self, filter_: BasicFilter):
        """insufficient_data 计数出现在 filter_log 中"""
        result = filter_.apply({"min_performance": "A"})
        logs = [log for log in result["filter_log"] if log["condition"] == "min_performance"]
        if logs:
            log_entry = logs[0]
            # 至少应有 1 个 insufficient_data（JZ0010 2026 入职）
            assert log_entry.get("insufficient_data", 0) >= 1


class TestCombinedConditions:
    """8. 多条件叠加"""

    def test_age_and_political(self, filter_: BasicFilter):
        """年龄 + 政治面貌 → 叠加"""
        result = filter_.apply({
            "age_range": [30, 40],
            "political_status": ["中共党员"],
        })
        for e in result["filtered_employees"]:
            assert 30 <= e["age"] <= 40
            assert e["political_status"] == "中共党员"
        assert len(result["filter_log"]) == 2

    def test_three_conditions(self, filter_: BasicFilter):
        """年龄 + 政治面貌 + 工龄 → 三层叠加"""
        result = filter_.apply({
            "age_range": [25, 50],
            "political_status": ["中共党员", "共青团员"],
            "min_years_of_service": 3,
        })
        for e in result["filtered_employees"]:
            assert 25 <= e["age"] <= 50
            assert e["political_status"] in ("中共党员", "共青团员")
            assert e["years_of_service"] >= 3


class TestAllFilteredOut:
    """9. 全部被过滤 → total_after=0 + 提示"""

    def test_all_filtered_note(self, filter_: BasicFilter):
        result = filter_.apply({"age_range": [0, 0]})
        assert result["total_after"] == 0
        assert result["filter_log"][-1].get("note") == "建议放宽条件"


class TestEmptyConditions:
    """10. 空条件返回全部"""

    def test_empty_dict(self, filter_: BasicFilter):
        result = filter_.apply({})
        assert result["total_after"] == 100
        assert result["filter_log"] == []
        assert result["skipped_conditions"] == []


class TestUnknownCondition:
    """11. 不支持的条件 → skipped_conditions"""

    def test_unknown_key(self, filter_: BasicFilter):
        result = filter_.apply({"foo": "bar"})
        assert result["skipped_conditions"] == ["foo"]
        assert result["total_after"] == 100  # 不中断其他条件

    def test_unknown_with_known(self, filter_: BasicFilter):
        """未知 + 已知条件混合"""
        result = filter_.apply({
            "age_range": [30, 40],
            "foo": "bar",
            "political_status": ["中共党员"],
        })
        assert "foo" in result["skipped_conditions"]
        assert result["total_after"] < 100
        assert len(result["filter_log"]) == 2  # 只记录已知条件


class TestSerialization:
    """12. JSON 序列化安全"""

    def test_json_dumps_safe(self, filter_: BasicFilter):
        """numpy 类型已转换为原生类型 → json.dumps 不抛 TypeError"""
        result = filter_.apply({"age_range": [30, 45]})
        json_str = json.dumps(result, ensure_ascii=False)
        assert isinstance(json_str, str)
        parsed = json.loads(json_str)
        assert parsed["total_before"] == 100


# ═══════════════════════════════════════════════════════════════════════════
# 额外边界测试
# ═══════════════════════════════════════════════════════════════════════════

class TestEdgeCases:
    """计划文档中列出的额外边界场景"""

    def test_conditions_is_not_dict(self, filter_: BasicFilter):
        """conditions 非 dict → 返回 error"""
        result = filter_.apply("not_a_dict")
        assert result["error"] is not None
        assert "str" in result["error"]

    def test_condition_value_none(self, filter_: BasicFilter):
        """条件值为 None → 跳过"""
        result = filter_.apply({"age_range": None, "political_status": ["中共党员"]})
        assert "age_range" in result["skipped_conditions"]
        # political_status 应正常执行
        for e in result["filtered_employees"]:
            assert e["political_status"] == "中共党员"

    def test_level_range_non_list(self, filter_: BasicFilter):
        """level_range 非列表 → 返回原样"""
        result = filter_.apply({"level_range": "invalid"})
        # 非列表 → _apply_level_range 返回原 df，log 记录 before=after
        log = [l for l in result["filter_log"] if l["condition"] == "level_range"]
        assert len(log) == 1
        assert log[0]["removed_count"] == 0

    def test_min_performance_invalid_grade(self, filter_: BasicFilter):
        """绩效底线为非法值 → 跳过"""
        result = filter_.apply({"min_performance": "Z"})
        # Z 不在 PERFORMANCE_ORDINAL 中 → 跳过
        log = [l for l in result["filter_log"] if l["condition"] == "min_performance"]
        assert len(log) == 0 or log[0]["removed_count"] == 0

    def test_major_keywords_non_list(self, filter_: BasicFilter):
        """major_keywords 非列表 → 返回原样"""
        result = filter_.apply({"major_keywords": "计算机"})
        assert result["total_after"] == result["total_before"]

    def test_hire_date_parse_failure(self):
        """hire_date 无法解析 → 视为新员工（hire_year=9999）"""
        df = pd.DataFrame({
            "employee_id": ["T001", "T002"],
            "age": [30, 35],
            "years_of_service": [5, 10],
            "hire_date": ["invalid-date", "2020-01-01"],
            "political_status": ["群众", "群众"],
            "major": ["计算机", "计算机"],
            "current_level": ["P5", "P6"],
        })
        pf = pd.DataFrame(columns=["employee_id", "year", "performance_grade"])
        f = BasicFilter(df, pf)
        # T001 hire_date 无法解析 → hire_year=9999
        assert f._hire_years.get("T001") == 9999


class TestNumpyToNative:
    """numpy_to_native 工具函数（D2 单一来源：由 utils/__init__.py 提供）"""

    def test_numpy_int(self):
        assert numpy_to_native(np.int32(42)) == 42
        assert numpy_to_native(np.int64(100)) == 100

    def test_numpy_float(self):
        assert numpy_to_native(np.float32(3.14)) == pytest.approx(3.14, rel=1e-6)
        assert numpy_to_native(np.float64(3.14)) == pytest.approx(3.14, rel=1e-12)

    def test_numpy_bool(self):
        assert numpy_to_native(np.bool_(True)) is True

    def test_nested_dict(self):
        data = {"a": np.int32(1), "b": {"c": np.float64(2.5)}}
        result = numpy_to_native(data)
        assert result == {"a": 1, "b": {"c": 2.5}}

    def test_list_of_dicts(self):
        data = [{"x": np.int32(10)}, {"x": np.int32(20)}]
        result = numpy_to_native(data)
        assert result == [{"x": 10}, {"x": 20}]

    def test_json_serializable(self):
        data = {"value": np.int64(999)}
        native = numpy_to_native(data)
        json.dumps(native)  # 不应抛出异常