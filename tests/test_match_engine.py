"""utils/match_engine.py 单元测试（M3 向量直配 + 固定公式）。

确定性 fake：字符桶向量编码 + 注入式 cross-encoder，不加载 torch。
"""
from __future__ import annotations

import json

import numpy as np
import pytest

import config
from utils.evidence_index import EvidenceIndex
from utils.match_engine import (
    calibrate_t1_with_ce,
    check_hard_gate,
    rank_candidates,
    score_t0_direct,
    score_t2_behavior,
    score_t3_potential,
)


DIM = 64


def char_bucket_encode(texts: list[str]) -> np.ndarray:
    vecs = []
    for t in texts:
        v = np.zeros(DIM)
        for ch in str(t):
            v[ord(ch) % DIM] += 1.0
        n = np.linalg.norm(v)
        vecs.append(v / n if n > 0 else v)
    return np.array(vecs) if vecs else np.array([])


def fake_ce_high(pairs) -> np.ndarray:
    """注入式 CE：全给高分 logit（sigmoid(2)≈0.88）。"""
    return np.array([2.0] * len(pairs))


def fake_ce_fail(pairs) -> np.ndarray:
    raise RuntimeError("CE boom")


@pytest.fixture
def emp_quality() -> dict:
    """质量工程师员工（证据密集体）。"""
    return {
        "employee_id": "E001",
        "structured": {"name": "周工", "education": "本科",
                       "years_of_service": 16, "current_position": "质量工程师",
                       "certificates": "无"},
        "projects": [{"project_name": "工业IoT管理平台", "role": "核心开发",
                      "tools": ["InfluxDB"], "description": "质量管控模块"}],
        "performance": [{"year": 2024, "grade": "B", "comment": "稳"},
                        {"year": 2025, "grade": "C", "comment": "波动"},
                        {"year": 2026, "grade": "A", "comment": "翻盘"}],
        "training": [{"course_name": "质量管理体系ISO9001", "status": "已完成",
                      "score": 91}],
        "scores_360": {"专业能力": 4.2, "沟通协作": 3.6, "领导力": 3.9,
                       "责任心": 3.9, "学习能力": 3.5},
        "text_summaries": {"evaluation_summary": "质量意识强，跨部门沟通顺畅"},
    }


@pytest.fixture
def emp_finance() -> dict:
    return {
        "employee_id": "E002",
        "structured": {"name": "程芳", "education": "本科",
                       "years_of_service": 11, "current_position": "薪酬福利专员",
                       "certificates": "高级会计师"},
        "projects": [{"project_name": "企业内控体系建设", "role": "协调人",
                      "tools": ["COSO"], "description": "内控流程梳理"}],
        "performance": [{"year": 2024, "grade": "A", "comment": "优"},
                        {"year": 2025, "grade": "B", "comment": "稳"},
                        {"year": 2026, "grade": "B", "comment": "稳"}],
        "training": [],
        "scores_360": {"专业能力": 4.5, "沟通协作": 4.0, "领导力": 3.0,
                       "责任心": 4.5, "学习能力": 3.8},
        "text_summaries": {"evaluation_summary": "风险意识强"},
    }


@pytest.fixture
def job_quality() -> dict:
    return {
        "job_id": "JOB_T1",
        "title": "质量体系工程师",
        "hard_requirements": {"education_min": "本科", "years_min": 3,
                              "certificates": []},
        "skill_requirements": [
            {"name": "质量工程", "detail": "质量管理体系、ISO9001"},
            {"name": "智能制造", "detail": "工业IoT、质量管控"},
        ],
        "soft_requirements": [{"name": "质量导向", "detail": "质量意识强"}],
        "queries": ["质量工程：质量管理体系ISO9001",
                    "智能制造：工业IoT质量管控"],
    }


class TestHardGate:
    def test_pass(self, emp_quality, job_quality):
        gate = check_hard_gate(job_quality["hard_requirements"], emp_quality)
        assert gate == {"passed": True, "fail_reasons": []}

    def test_education_fail(self, emp_quality):
        emp_quality["structured"]["education"] = "大专"
        gate = check_hard_gate({"education_min": "本科"}, emp_quality)
        assert not gate["passed"] and "学历" in gate["fail_reasons"][0]

    def test_years_fail(self, emp_quality):
        emp_quality["structured"]["years_of_service"] = 1
        gate = check_hard_gate({"years_min": 3}, emp_quality)
        assert not gate["passed"] and "司龄" in gate["fail_reasons"][0]

    def test_empty_requirements_pass(self, emp_quality):
        assert check_hard_gate({}, emp_quality)["passed"]


class TestT0:
    def test_hits(self, emp_quality, job_quality):
        score, hits = score_t0_direct(job_quality, emp_quality)
        assert score > 0 and hits, "「质量工程」应命中岗位「质量工程师」"
        assert "质量工程" in hits

    def test_neutral_when_no_reqs(self, emp_quality):
        score, hits = score_t0_direct(
            {"skill_requirements": [], "hard_requirements": {}}, emp_quality)
        assert score == 0.5 and hits == []

    def test_certificate_hit(self, emp_finance, job_quality):
        job_quality["hard_requirements"]["certificates"] = ["高级会计师"]
        score, hits = score_t0_direct(job_quality, emp_finance)
        assert "高级会计师" in hits

    def test_normalization_space(self, emp_quality):
        """「Power BI」JD 写法 vs 员工证据「PowerBI」：归一化后命中。"""
        emp_quality["projects"].append(
            {"project_name": "人力平台", "role": "开发", "tools": ["PowerBI"],
             "description": "报表开发"})
        job = {"skill_requirements": [{"name": "Power BI", "detail": ""}],
               "hard_requirements": {"certificates": []}}
        score, hits = score_t0_direct(job, emp_quality)
        assert hits == ["Power BI"] and score == 1.0

    def test_synonym_not_literal_miss(self, emp_quality):
        """同义改写（人力资源管理 ↔ 人力资源数字化平台）不算字面命中——
        分层各司其职：字面层管精确，同义交给 T1 语义层（2026-10-21 标定）。"""
        emp_quality["projects"].append(
            {"project_name": "人力资源数字化平台", "role": "执行人",
             "tools": [], "description": "流程优化"})
        job = {"skill_requirements": [{"name": "人力资源管理", "detail": ""}],
               "hard_requirements": {"certificates": []}}
        score, hits = score_t0_direct(job, emp_quality)
        assert hits == [] and score == 0.0

    def test_duplicate_names_deduped(self, emp_quality):
        """同名 skill 项重复不撑大分母（上游去重失效时的引擎侧兜底）。"""
        job = {"skill_requirements": [
            {"name": "质量工程", "detail": ""},
            {"name": "质量工程", "detail": ""},
            {"name": "智能制造", "detail": ""},
        ], "hard_requirements": {"certificates": []}}
        score, hits = score_t0_direct(job, emp_quality)
        assert len(hits) <= 2 and score in (0.0, 0.5, 1.0)  # 分母=2 去重后

    def test_keyword_miss_no_bridge(self, emp_quality):
        """name 不在证据 → 不命中（不放宽为部分子串）。"""
        job = {"skill_requirements": [{"name": "量子计算", "detail": ""}],
               "hard_requirements": {"certificates": []}}
        score, hits = score_t0_direct(job, emp_quality)
        assert hits == [] and score == 0.0


class TestT2T3:
    def test_t2_known(self, emp_quality):
        s = score_t2_behavior(emp_quality)
        assert 0.0 <= s <= 1.0 and s > 0.5

    def test_t2_missing_neutral(self):
        assert score_t2_behavior({}) == 0.5

    def test_t3_rising_beats_falling(self, emp_quality, emp_finance):
        rising = score_t3_potential(emp_quality)   # B→C→A
        falling = score_t3_potential(emp_finance)  # A→B→B
        assert rising > falling

    def test_t3_empty_neutral(self):
        assert score_t3_potential({}) == 0.5


class TestCalibrateCE:
    def test_batch_one_call(self, job_quality, emp_quality, emp_finance):
        idx = EvidenceIndex.build([emp_quality, emp_finance],
                                  encode_fn=char_bucket_encode)
        calls = []

        def counting_ce(pairs):
            calls.append(len(pairs))
            return np.array([2.0] * len(pairs))

        out = calibrate_t1_with_ce(job_quality, idx, ["E001", "E002"],
                                   cross_encoder_fn=counting_ce)
        assert set(out.keys()) == {"E001", "E002"}
        assert all(0.0 <= v <= 1.0 for v in out.values())
        assert len(calls) == 1  # 每岗位 1 次 predict（成本分层）

    def test_encoder_none_returns_empty(self, job_quality, emp_quality):
        idx = EvidenceIndex.build([emp_quality], encode_fn=char_bucket_encode)
        assert calibrate_t1_with_ce(job_quality, idx, ["E001"],
                                    cross_encoder_fn=None) in ({}, {"E001": pytest.approx(0, abs=1)})
        # None 触发真实加载路径（本地无 torch 环境时返回 {}，不崩）

    def test_encoder_raises_returns_empty(self, job_quality, emp_quality):
        idx = EvidenceIndex.build([emp_quality], encode_fn=char_bucket_encode)
        assert calibrate_t1_with_ce(job_quality, idx, ["E001"],
                                    cross_encoder_fn=fake_ce_fail) == {}


class TestRankCandidates:
    def test_end_to_end_gold_first(self, job_quality, emp_quality, emp_finance):
        idx = EvidenceIndex.build([emp_quality, emp_finance],
                                  encode_fn=char_bucket_encode)
        ranking = rank_candidates(job_quality, [emp_quality, emp_finance], idx,
                                  cross_encoder_fn=fake_ce_high)
        assert ranking["candidates"][0]["emp_id"] == "E001"
        assert ranking["candidates"][0]["ce_calibrated"]
        # E002 未进 CE 短名单标记为 False（TopN=10 时两人都进——用公式判断）
        for c in ranking["candidates"]:
            assert set(c["scores"].keys()) == {"t0", "t1", "t2", "t3",
                                               "total", "confidence"}
            assert c["decision"] in {"recommend", "review", "backup_pool", "rejected"}

    def test_determinism_bitwise(self, job_quality, emp_quality, emp_finance):
        idx = EvidenceIndex.build([emp_quality, emp_finance],
                                  encode_fn=char_bucket_encode)
        r1 = rank_candidates(job_quality, [emp_quality, emp_finance], idx,
                             cross_encoder_fn=fake_ce_high)
        r2 = rank_candidates(job_quality, [emp_quality, emp_finance], idx,
                             cross_encoder_fn=fake_ce_high)
        assert json.dumps(r1["candidates"], ensure_ascii=False, sort_keys=True) == \
               json.dumps(r2["candidates"], ensure_ascii=False, sort_keys=True)

    def test_gate_fail_high_semantic_backup_pool(self, emp_quality):
        """硬闸门未过 + 语义强 → 备选池（原设计四象限对接）。"""
        emp = emp_quality
        emp["structured"]["years_of_service"] = 0  # 闸门必挂
        job = {
            "job_id": "J", "title": "质量体系工程师",
            "hard_requirements": {"years_min": 5},
            "skill_requirements": [{"name": "质量工程", "detail": "ISO9001"}],
            "queries": ["质量工程：质量管理体系ISO9001培训 质量工程师岗位"],
        }
        idx = EvidenceIndex.build([emp], encode_fn=char_bucket_encode)
        ranking = rank_candidates(job, [emp], idx, cross_encoder_fn=fake_ce_high)
        c = ranking["candidates"][0]
        assert c["gate"]["passed"] is False
        assert c["decision"] == "backup_pool"
        assert c["scores"]["t1"] >= config.MATCH_POOL_SEMANTIC_MIN

    def test_gate_fail_low_semantic_rejected(self, emp_finance):
        job = {
            "job_id": "J", "title": "雷达信号处理工程师",
            "hard_requirements": {"years_min": 30},
            "skill_requirements": [{"name": "雷达微多普勒分析", "detail": "杂波抑制"}],
            "queries": ["雷达微多普勒信号分析与杂波抑制滤波器设计"],
        }
        idx = EvidenceIndex.build([emp_finance], encode_fn=char_bucket_encode)
        ranking = rank_candidates(job, [emp_finance], idx, cross_encoder_fn=None)
        c = ranking["candidates"][0]
        assert c["decision"] == "rejected"
        assert c["gate"]["passed"] is False

    def test_evidence_chain_anchors(self, job_quality, emp_quality, emp_finance):
        idx = EvidenceIndex.build([emp_quality, emp_finance],
                                  encode_fn=char_bucket_encode)
        ranking = rank_candidates(job_quality, [emp_quality, emp_finance], idx)
        ev = ranking["candidates"][0]["evidence"]
        assert ev and set(ev[0].keys()) == {"query", "source", "text", "anchor", "sim"}

    def test_sort_tie_break_by_emp_id(self, job_quality, emp_quality):
        """同分并列按 emp_id 升序（逐位一致的地基）。"""
        clone = json.loads(json.dumps(emp_quality, ensure_ascii=False))
        clone["employee_id"] = "E000"
        clone["structured"] = dict(emp_quality["structured"])
        idx = EvidenceIndex.build([emp_quality, clone],
                                  encode_fn=char_bucket_encode)
        ranking = rank_candidates(job_quality, [emp_quality, clone], idx)
        ids = [c["emp_id"] for c in ranking["candidates"]]
        # 两人证据文本一致 → 总分同 → E000 在前
        assert ids == sorted(ids, key=lambda x: x) or ids[0] == "E000"
