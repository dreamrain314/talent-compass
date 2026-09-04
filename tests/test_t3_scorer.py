"""tests/test_t3_scorer.py — compute_t3_scores 单元测试。

覆盖（C4 边界穷举 + C6 公式验证 + V7 残缺输入）：
- 正常路径 / 全空降级 / 部分空
- 极端工龄（1 年触顶 / 20 年趋低 / 0 / None）
- 大规模培训触顶 / 重复角色去重
- 返回类型 Python float（非 numpy.float64）
- employee={} / {"raw":{}} 不崩
- t3_raw=None / 非 dict
- career_roles / training 含 None 元素
- json.dumps 不抛 TypeError
"""

import json

import numpy as np

from config import (
    T3_CAREER_DIVERSITY_SCALE,
    T3_CONFIDENCE_BASELINE,
    T3_CONFIDENCE_DEGRADED,
    T3_FEEDBACK_SCALE,
    T3_GROWTH_EVIDENCE_SCALE,
    T3_LEARNING_SPEED_SCALE,
    T3_TRAINING_SCALE,
)
from utils.t3_scorer import compute_t3_scores


def _emp(years=None, training=None, years_key="years_of_service"):
    """构造 employee（适配后格式）。years=None 表示键缺失。"""
    raw = {} if years is None else {years_key: years}
    return {"raw": raw, "training": training if training is not None else []}


class TestT3NormalPath:
    """正常路径。"""

    def test_normal(self):
        t3_raw = {
            "learning_activities": ["a", "b"],
            "career_roles": ["dev", "mgr"],
            "growth_evidence": ["g1"],
            "feedback_signals": ["f1"],
        }
        emp = _emp(years=5, training=[{"course_name": "c1"}])
        result = compute_t3_scores(t3_raw, emp)
        # 2/5*50 = 20
        assert result["learning_speed"] == 20.0
        # 2 roles * 15 = 30
        assert result["career_diversity"] == 30.0
        # 1*8 + 1*5 = 13
        assert result["growth_orientation"] == 13.0
        # 1*12 = 12
        assert result["growth_signals_360"] == 12.0
        assert result["confidence"] == T3_CONFIDENCE_BASELINE

    def test_keys_set_complete(self):
        """C1: 顶层 key 集合固定。"""
        result = compute_t3_scores({}, _emp())
        assert set(result.keys()) == {
            "learning_speed",
            "career_diversity",
            "growth_orientation",
            "growth_signals_360",
            "confidence",
        }


class TestT3AllEmpty:
    """全空降级。"""

    def test_empty_t3_raw_no_training(self):
        result = compute_t3_scores({}, _emp(years=5, training=[]))
        assert result["learning_speed"] == 0.0
        assert result["career_diversity"] == 0.0
        assert result["growth_orientation"] == 0.0
        assert result["growth_signals_360"] == 0.0
        assert result["confidence"] == T3_CONFIDENCE_DEGRADED

    def test_none_t3_raw(self):
        result = compute_t3_scores(None, _emp(years=5))
        assert result["confidence"] == T3_CONFIDENCE_DEGRADED
        assert all(result[k] == 0.0 for k in
                   ["learning_speed", "career_diversity", "growth_orientation", "growth_signals_360"])

    def test_non_dict_t3_raw(self):
        # C3 守卫：非 dict 不崩
        result = compute_t3_scores("not a dict", _emp(years=5))  # type: ignore[arg-type]
        assert result["confidence"] == T3_CONFIDENCE_DEGRADED


class TestT3PartialEmpty:
    """部分空：空字段 0 分，非空正常，confidence=baseline。"""

    def test_only_learning(self):
        t3_raw = {"learning_activities": ["a", "b", "c", "d"]}
        emp = _emp(years=2, training=[])
        result = compute_t3_scores(t3_raw, emp)
        # 4/2*50 = 100
        assert result["learning_speed"] == 100.0
        assert result["career_diversity"] == 0.0
        assert result["growth_orientation"] == 0.0
        assert result["growth_signals_360"] == 0.0
        assert result["confidence"] == T3_CONFIDENCE_BASELINE

    def test_only_training(self):
        # growth_orientation 仅靠 training
        emp = _emp(years=5, training=[{}, {}, {}, {}])  # 4 条培训
        result = compute_t3_scores({}, emp)
        assert result["growth_orientation"] == 20.0  # 4*5
        assert result["confidence"] == T3_CONFIDENCE_BASELINE


class TestT3ExtremeYears:
    """极端工龄。"""

    def test_one_year_caps_learning(self):
        # 1 年工龄，2 项活动 → 2/1*50 = 100 触顶
        t3_raw = {"learning_activities": ["a", "b"]}
        emp = _emp(years=1, training=[])
        result = compute_t3_scores(t3_raw, emp)
        assert result["learning_speed"] == 100.0

    def test_twenty_years_low_learning(self):
        t3_raw = {"learning_activities": ["a", "b"]}
        emp = _emp(years=20, training=[])
        result = compute_t3_scores(t3_raw, emp)
        # 2/20*50 = 5
        assert result["learning_speed"] == 5.0

    def test_zero_years_guard(self):
        # max(...,1) 守卫：years=0 → 1，不除零
        t3_raw = {"learning_activities": ["a"]}
        emp = _emp(years=0, training=[])
        result = compute_t3_scores(t3_raw, emp)
        # 1/1*50 = 50
        assert result["learning_speed"] == 50.0

    def test_none_years_value(self):
        # 🔴 键存在但值为 None：`or 0` 守卫，max(None,1) 不崩
        t3_raw = {"learning_activities": ["a"]}
        emp = {"raw": {"years_of_service": None}, "training": []}
        result = compute_t3_scores(t3_raw, emp)
        # years = max(None or 0, 1) = max(0,1) = 1 → 1/1*50 = 50
        assert result["learning_speed"] == 50.0


class TestT3CapsAndDedup:
    """上限与去重。"""

    def test_large_training_caps_growth(self):
        # 20 条培训 → 20*5 = 100 触顶
        emp = _emp(years=5, training=[{}] * 20)
        result = compute_t3_scores({}, emp)
        assert result["growth_orientation"] == 100.0

    def test_large_feedback_caps(self):
        # 9 项 feedback → 9*12 = 108 → 触顶 100
        t3_raw = {"feedback_signals": ["f"] * 9}
        result = compute_t3_scores(t3_raw, _emp(years=5))
        assert result["growth_signals_360"] == 100.0

    def test_duplicate_roles_dedup(self):
        # set() 去重：3 条但 2 唯一 → 2*15 = 30
        t3_raw = {"career_roles": ["dev", "dev", "mgr"]}
        result = compute_t3_scores(t3_raw, _emp(years=5))
        assert result["career_diversity"] == 30.0

    def test_many_unique_roles_cap(self):
        # 7 角色 → 7*15 = 105 → 触顶 100
        t3_raw = {"career_roles": ["r1", "r2", "r3", "r4", "r5", "r6", "r7"]}
        result = compute_t3_scores(t3_raw, _emp(years=5))
        assert result["career_diversity"] == 100.0


class TestT3NoneElements:
    """🔴 对抗审查发现的边界：None 元素守卫。"""

    def test_career_roles_with_none(self):
        # set([None,"A",None]) 会把 None 当一个角色 → 2；应过滤后 1
        t3_raw = {"career_roles": [None, "A", None]}
        result = compute_t3_scores(t3_raw, _emp(years=5))
        assert result["career_diversity"] == 15.0  # 1 unique * 15

    def test_career_roles_with_empty_string(self):
        t3_raw = {"career_roles": ["", "A", ""]}
        result = compute_t3_scores(t3_raw, _emp(years=5))
        assert result["career_diversity"] == 15.0

    def test_training_with_none_elements(self):
        # training 列表含 None 元素：应过滤，不计入
        emp = _emp(years=5, training=[None, {"c": 1}, None])
        result = compute_t3_scores({}, emp)
        # 1 valid training * 5 = 5
        assert result["growth_orientation"] == 5.0

    def test_learning_activities_with_none(self):
        t3_raw = {"learning_activities": [None, "a", None]}
        emp = _emp(years=1, training=[])
        result = compute_t3_scores(t3_raw, emp)
        # 1 valid / 1 year * 50 = 50
        assert result["learning_speed"] == 50.0

    def test_career_roles_with_unhashable_dict(self):
        # 🔴 LLM 可能返回 dict 元素：set() 会崩，str() 守卫安全去重
        t3_raw = {"career_roles": [{"role": "dev"}, {"role": "mgr"}, {"role": "dev"}]}
        result = compute_t3_scores(t3_raw, _emp(years=5))
        # str() 后 {"role":"dev"} 出现 2 次（同 str 去重为 1），{"role":"mgr"} 1 次 → 2 唯一
        assert result["career_diversity"] == 30.0


class TestT3Robustness:
    """残缺输入（V7）。"""

    def test_empty_employee(self):
        result = compute_t3_scores({"learning_activities": ["a"]}, {})
        # raw = None or {} = {}, years = max(None or 0, 1) = 1 → 1/1*50=50
        assert result["learning_speed"] == 50.0
        assert result["confidence"] == T3_CONFIDENCE_BASELINE

    def test_employee_raw_empty(self):
        result = compute_t3_scores({"learning_activities": ["a"]}, {"raw": {}})
        assert result["learning_speed"] == 50.0

    def test_employee_non_dict(self):
        # C3 守卫：employee 非 dict 不崩
        result = compute_t3_scores({"learning_activities": ["a"]}, None)  # type: ignore[arg-type]
        assert result["learning_speed"] == 50.0

    def test_t3_raw_with_none_values(self):
        # 信号字段值为 None：.get 返回 None → _safe_len 处理
        t3_raw = {
            "learning_activities": None,
            "career_roles": None,
            "growth_evidence": None,
            "feedback_signals": None,
        }
        result = compute_t3_scores(t3_raw, _emp(years=5))
        assert result["confidence"] == T3_CONFIDENCE_DEGRADED


class TestT3ReturnType:
    """返回类型为 Python float（非 numpy.float64）。"""

    def test_all_float(self):
        result = compute_t3_scores(
            {"learning_activities": ["a"]}, _emp(years=2, training=[{}])
        )
        for v in result.values():
            assert isinstance(v, float), f"{v} is {type(v).__name__}, expected float"
            assert not isinstance(v, np.floating)

    def test_json_serializable(self):
        # D2/C1: json.dumps 不抛 TypeError
        result = compute_t3_scores(
            {"learning_activities": ["a", "b"], "career_roles": ["x"]},
            _emp(years=3, training=[{}]),
        )
        s = json.dumps(result)
        assert "learning_speed" in s
        # 不产生 NaN/Infinity 字符串
        assert "NaN" not in s
        assert "Infinity" not in s


class TestT3FormulaWalkthrough:
    """C6: 极端 case I/O 表，人工走通计算链。"""

    def test_all_zero(self):
        result = compute_t3_scores({}, _emp(years=5))
        assert result == {
            "learning_speed": 0.0,
            "career_diversity": 0.0,
            "growth_orientation": 0.0,
            "growth_signals_360": 0.0,
            "confidence": float(T3_CONFIDENCE_DEGRADED),
        }

    def test_all_max(self):
        # 构造每项都触顶 100
        t3_raw = {
            "learning_activities": ["a"] * 10,  # 10/5*50 = 100
            "career_roles": ["r1", "r2", "r3", "r4", "r5", "r6", "r7"],  # 7*15=105→100
            "growth_evidence": ["g"] * 13,  # 13*8=104 → +0 training = 104→100
            "feedback_signals": ["f"] * 9,  # 9*12=108→100
        }
        emp = _emp(years=5, training=[])
        result = compute_t3_scores(t3_raw, emp)
        assert result["learning_speed"] == 100.0
        assert result["career_diversity"] == 100.0
        assert result["growth_orientation"] == 100.0
        assert result["growth_signals_360"] == 100.0
        assert result["confidence"] == T3_CONFIDENCE_BASELINE

    def test_distribution_100_random(self):
        """随机×100 看分布，确认非恒等变换、无异常。"""
        import random

        rng = random.Random(42)
        scores = {"learning_speed": [], "career_diversity": [],
                  "growth_orientation": [], "growth_signals_360": []}
        for _ in range(100):
            t3_raw = {
                "learning_activities": ["a"] * rng.randint(0, 20),
                "career_roles": [f"r{i}" for i in range(rng.randint(0, 8))],
                "growth_evidence": ["g"] * rng.randint(0, 15),
                "feedback_signals": ["f"] * rng.randint(0, 10),
            }
            emp = _emp(years=rng.randint(1, 30), training=[{}] * rng.randint(0, 25))
            result = compute_t3_scores(t3_raw, emp)
            for k in scores:
                scores[k].append(result[k])
        # 每个指标都有非零值且分布有方差（非恒等 0）
        for k, vals in scores.items():
            assert max(vals) > 0, f"{k} 全为 0，可能恒等变换"
            assert len(set(vals)) > 1, f"{k} 无方差，可能恒等变换"
            assert all(0.0 <= v <= 100.0 for v in vals), f"{k} 越界"
