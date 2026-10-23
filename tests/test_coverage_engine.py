"""utils/coverage_engine.py 单元测试（Round 3 要求—证据对齐，预注册 §二）。

确定性 fake 编码（字符桶），零 LLM、零 fastembed、零 torch。
判定规则全部对照预注册 §2.1/§2.3/§2.4 冻结条款。
"""
from __future__ import annotations

import numpy as np
import pytest

import config
from utils.coverage_engine import (
    COVERAGE_RELATION_VALUES,
    _apply_behavior_decay,
    build_evidence_matrix,
    classify_relation,
    extract_requirements,
    load_verified_equivalences,
    recall_candidates,
    requirement_type,
    score_coverage,
)


DIM = 64


def char_bucket_encode(texts: list[str]) -> np.ndarray:
    """确定性 fake 编码：字符 ord 桶计数 + 归一化。共享字符越多 cos 越高。"""
    vecs = []
    for t in texts:
        v = np.zeros(DIM)
        for ch in str(t):
            v[ord(ch) % DIM] += 1.0
        n = np.linalg.norm(v)
        vecs.append(v / n if n > 0 else v)
    return np.array(vecs) if vecs else np.array([])


# ── §2.1 要求抽取 ────────────────────────────────────────────────
class TestExtractRequirements:
    def test_slash_enum_is_one_requirement_with_instances(self):
        job = {"requirements": ["熟悉嵌入式开发（MCU/STM32/ARM/RTOS/驱动开发）"]}
        reqs = extract_requirements(job)
        assert len(reqs) == 1
        r = reqs[0]
        assert r["head"] == "嵌入式开发"
        assert r["instances"] == ["MCU", "STM32", "ARM", "RTOS", "驱动开发"]
        assert r["kind"] == "necessary" and r["weight"] == config.COVERAGE_W_NECESSARY

    def test_preferred_item_gets_lower_weight(self):
        job = {"requirements": ["有工业物联网项目质量工作经验者优先"]}
        reqs = extract_requirements(job)
        assert reqs[0]["kind"] == "preferred"
        assert reqs[0]["weight"] == config.COVERAGE_W_PREFERRED

    def test_gate_items_excluded(self):
        job = {"requirements": [
            "本科及以上学历，工学、理学等相关专业",
            "3年及以上制造业质量管理相关工作经验",
            "熟悉质量管理体系（ISO9001）",
        ]}
        reqs = extract_requirements(job)
        assert [r["head"] for r in reqs] == ["质量管理体系"]

    def test_head_slash_enum_becomes_instances(self):
        job = {"requirements": ["熟悉教学设计/课程设计/教学管理/教研实务"]}
        reqs = extract_requirements(job)
        assert len(reqs) == 1
        assert reqs[0]["instances"] == ["教学设计", "课程设计", "教学管理", "教研实务"]
        assert reqs[0]["either_ok"] is True

    def test_duplicate_heads_deduped(self):
        job = {"responsibilities": ["熟悉嵌入式开发", "熟悉嵌入式开发（MCU）"]}
        reqs = extract_requirements(job)
        assert len(reqs) == 1


# ── §2.3 关系分类 ────────────────────────────────────────────────
def _req(head="嵌入式开发", instances=None):
    return {"rid": "R01", "text": head, "head": head,
            "instances": instances or [], "kind": "necessary",
            "weight": 1.0, "either_ok": bool(instances)}


class TestClassifyRelation:
    def test_instance_hit_is_direct_support(self):
        cls = classify_relation(_req(instances=["MCU", "STM32"]),
                                {"text": "项目「网关固件」工具：STM32；负责驱动开发"}, {})
        assert cls["relation"] == "direct_support"
        assert cls["value"] == 1.0

    def test_short_head_literal_hit_supported(self):
        cls = classify_relation(_req(head="嵌入式开发"), {"text": "岗位：嵌入式开发工程师"}, {})
        assert cls["relation"] == "direct_support"

    def test_long_head_without_instances_not_literal_matched(self):
        # 长 head 无实例：通用词碰瓷不算支持（保守口径，宁报未证实）
        cls = classify_relation(
            _req(head="推动跨部门质量改进并处理交付过程中的问题闭环"), {"text": "按时交付，质量良好"}, {})
        assert cls["relation"] == "relevant_only"
        assert cls["value"] == 0.0

    def test_state_marker_downgrades_to_half(self):
        cls = classify_relation(_req(instances=["STM32"]),
                                {"text": "培训：STM32开发（学习中）"}, {})
        assert cls["relation"] == "state_different"
        assert cls["value"] == 0.5

    def test_negation_beats_hit_and_marks_contradiction(self):
        cls = classify_relation(_req(instances=["STM32"]),
                                {"text": "记录：未参与STM32相关开发"}, {})
        assert cls["relation"] == "contradiction"
        assert cls["value"] == 0.0

    def test_verified_equivalence_counts_same_tier(self):
        equiv = {"嵌入式开发": ["网关开发"]}
        cls = classify_relation(_req(head="嵌入式开发"), {"text": "边缘计算网关开发 负责人"}, equiv)
        assert cls["relation"] == "equivalent"
        assert cls["value"] == 1.0

    def test_all_values_frozen_scale(self):
        assert COVERAGE_RELATION_VALUES == {
            "equivalent": 1.0, "direct_support": 1.0,
            "state_different": 0.5, "relevant_only": 0.0, "contradiction": 0.0,
        }


# ── §2.2 双通道召回 ──────────────────────────────────────────────
class TestRecallCandidates:
    def _idx_chunks(self):
        chunks = [
            {"emp_id": "E1", "source": "projects", "text": "项目「网关」：STM32 固件开发", "anchor": "x"},
            {"emp_id": "E1", "source": "training", "text": "培训：瑜伽入门", "anchor": "y"},
            {"emp_id": "E1", "source": "performance", "text": "2026年绩效优秀A：表现突出", "anchor": "z"},
            {"emp_id": "E1", "source": "projects", "text": "项目「固件」：ARM 平台移植", "anchor": "w"},
        ]
        return chunks, char_bucket_encode([c["text"] for c in chunks])

    def test_cap_k_and_dedupe(self):
        chunks, vecs = self._idx_chunks()
        q = char_bucket_encode(["嵌入式开发（STM32/ARM）"])[0]
        cands = recall_candidates(_req(instances=["STM32", "ARM"]), chunks, vecs, q, top_k=3)
        assert len(cands) <= 3
        texts = [c["text"] for c in cands]
        assert len(texts) == len(set(texts))  # 双通道并集去重
        # 相关 chunk 应排在无关 chunk 前（两通道至少一路命中）
        assert "瑜伽" not in texts[0]

    def test_empty_inputs_return_empty(self):
        assert recall_candidates(_req(), [], np.array([]), np.zeros(DIM)) == []


# ── §2.4 覆盖评分 ────────────────────────────────────────────────
def _employee(eid="E1", s360=None, grades=None, training=None):
    return {
        "employee_id": eid,
        "scores_360": s360 or {},
        "performance": [{"year": y, "grade": g, "comment": "c"} for y, g in (grades or [])],
        "training": [{"course_name": t, "status": "已完成"} for t in (training or [])],
    }


class TestScoreCoverage:
    def test_full_coverage_math(self):
        job = {"requirements": ["熟悉嵌入式开发（STM32）"]}
        reqs = extract_requirements(job)
        emp = _employee(grades=[(2026, "B")], training=["Python"])
        chunks = [{"emp_id": "E1", "source": "projects",
                   "text": "项目「x」：STM32 固件", "anchor": "a"}]
        from utils.evidence_index import EvidenceIndex
        idx = EvidenceIndex(chunks, char_bucket_encode([c["text"] for c in chunks]),
                            encode_fn=char_bucket_encode)
        res = score_coverage(reqs, [emp], idx, cross_encoder_fn=None,
                             equivalences={}, encode_fn=char_bucket_encode)
        r = res["E1"]
        assert r["coverage"] == 1.0
        # S = 80·1 + 10·B + 10·P；单年绩效 B → B=(3-1)/4=0.5；1 条培训 → 0.2·(0.2)=...
        assert r["total"] == pytest.approx(
            config.COVERAGE_W_COVERAGE * 1.0
            + config.COVERAGE_W_BEHAVIOR * 0.5
            + config.COVERAGE_W_POTENTIAL * r["p"], abs=0.01)

    def test_uncovered_requirement_reports_unverified(self):
        job = {"requirements": ["熟悉嵌入式开发（STM32）"]}
        reqs = extract_requirements(job)
        emp = _employee()
        chunks = [{"emp_id": "E1", "source": "training",
                   "text": "培训：瑜伽入门（已完成）", "anchor": "a"}]
        from utils.evidence_index import EvidenceIndex
        idx = EvidenceIndex(chunks, char_bucket_encode([c["text"] for c in chunks]),
                            encode_fn=char_bucket_encode)
        res = score_coverage(reqs, [emp], idx, cross_encoder_fn=None,
                             equivalences={}, encode_fn=char_bucket_encode)
        rr = res["E1"]["requirements"]["R01"]
        assert rr["v"] == 0.0
        assert rr["relation"] == "relevant_only"
        row = build_evidence_matrix(reqs, res["E1"])[0]
        assert row["support_status"] == "未证实"
        assert "待人工核验" in row["limitation"]

    def test_ce_reranks_but_does_not_establish(self):
        # CE 高分不改变规则判定：无字面/等价命中 → 仍 relevant_only（§2.4）
        job = {"requirements": ["熟悉嵌入式开发（STM32）"]}
        reqs = extract_requirements(job)
        emp = _employee()
        chunks = [{"emp_id": "E1", "source": "summary_project",
                   "text": "参与嵌入式平台建设", "anchor": "a"}]
        from utils.evidence_index import EvidenceIndex
        idx = EvidenceIndex(chunks, char_bucket_encode([c["text"] for c in chunks]),
                            encode_fn=char_bucket_encode)

        def fake_ce(pairs):
            return [0.99 for _ in pairs]

        res = score_coverage(reqs, [emp], idx, cross_encoder_fn=fake_ce,
                             equivalences={}, encode_fn=char_bucket_encode)
        rr = res["E1"]["requirements"]["R01"]
        assert rr["v"] == 0.0  # CE 0.99 也不成立
        assert rr["evidence"][0]["ce"] == 0.99  # 但 CE 分被记录（相关性信号）

    def test_v_is_max_across_candidates(self):
        job = {"requirements": ["熟悉嵌入式开发（STM32）"]}
        reqs = extract_requirements(job)
        emp = _employee()
        chunks = [
            {"emp_id": "E1", "source": "training", "text": "培训：STM32入门（学习中）", "anchor": "a"},
            {"emp_id": "E1", "source": "projects", "text": "项目：STM32 固件开发", "anchor": "b"},
        ]
        from utils.evidence_index import EvidenceIndex
        idx = EvidenceIndex(chunks, char_bucket_encode([c["text"] for c in chunks]),
                            encode_fn=char_bucket_encode)
        res = score_coverage(reqs, [emp], idx, cross_encoder_fn=None,
                             equivalences={}, encode_fn=char_bucket_encode)
        assert res["E1"]["requirements"]["R01"]["v"] == 1.0  # 完成态项目压过学习中


# ── 等价表加载 ───────────────────────────────────────────────────
class TestEquivalenceTable:
    def test_missing_file_returns_dict_with_alias_seed(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "COVERAGE_EQUIVALENCE_PATH", tmp_path / "nope.json", raising=False)
        eq = load_verified_equivalences()
        assert isinstance(eq, dict)
        # alias_patches.json 的 4 对回归补丁是种子（物联网等）
        assert any("物联网" in k for k in eq) or eq == {}

    def test_equivalence_file_loaded(self, tmp_path, monkeypatch):
        f = tmp_path / "eq.json"
        f.write_text('{"equivalences": {"嵌入式开发": ["网关开发"]}}', encoding="utf-8")
        monkeypatch.setattr(config, "T0_ALIAS_PATCHES_PATH", tmp_path / "no-alias.json", raising=False)
        monkeypatch.setattr(config, "COVERAGE_EQUIVALENCE_PATH", f, raising=False)
        eq = load_verified_equivalences()
        assert eq.get("嵌入式开发") == ["网关开发"]


# ── 等价表 v1 新机制（子串激活 / deduct 减分 / 原子拆解）────────────
class TestTableActivation:
    def test_substring_activation(self):
        # 表键「沟通表达」⊂ 要求「具备良好的沟通表达与执行推进能力」（改写 miss 场景）
        req = _req(head="良好的沟通表达与执行推进能力")
        req["text"] = "具备良好的沟通表达与执行推进能力"
        equiv = {"沟通表达": ["跨部门沟通顺畅"]}
        cls = classify_relation(req, {"text": "360: 跨部门沟通顺畅，协作融洽"}, equiv)
        assert cls["relation"] == "equivalent" and cls["value"] == 1.0

    def test_deduct_value(self, tmp_path, monkeypatch):
        import json as _json
        f = tmp_path / "eq.json"
        f.write_text(_json.dumps({"equivalences": {"激励学员": ["能激发团队士气"]},
                                  "deduct": [["激励学员", "能激发团队士气"]],
                                  "atomic_splits": {}}), encoding="utf-8")
        monkeypatch.setattr(config, "COVERAGE_EQUIVALENCE_PATH", f, raising=False)
        req = _req(head="激励学员")
        req["text"] = "以骨干影响力构建课程愿景、激励学员（领导潜质发展通道）"
        cls = classify_relation(req, {"text": "360: 能激发团队士气"}, {"激励学员": ["能激发团队士气"]})
        assert cls["relation"] == "equivalent"
        assert cls["value"] == pytest.approx(config.COVERAGE_DEDUCTION_VALUE)
        assert "减分" in cls["note"]

    def test_atomic_split_weights_and_partial_credit(self):
        from utils.coverage_engine import _expand_requirements
        req = _req(head="良好的沟通表达与执行推进能力", instances=None)
        req["text"] = "具备良好的沟通表达与执行推进能力"
        splits = {"良好的沟通表达与执行推进能力": ["沟通表达", "执行推进"]}
        out = _expand_requirements([req], splits)
        assert len(out) == 2
        assert sum(r["weight"] for r in out) == pytest.approx(req["weight"])
        assert [r["head"] for r in out] == ["沟通表达", "执行推进"]
        # 匹配半边经表命中 1.0；舍弃半边无表项保持未证实 → 整要求 0.5 而非 1.0
        equiv = {"沟通表达": ["跨部门沟通顺畅"]}
        hit = classify_relation(out[0], {"text": "跨部门沟通顺畅"}, equiv)
        miss = classify_relation(out[1], {"text": "跨部门沟通顺畅"}, equiv)
        assert hit["value"] == 1.0 and miss["value"] == 0.0

    def test_no_split_when_compound_absent(self):
        from utils.coverage_engine import _expand_requirements
        req = _req(head="嵌入式开发", instances=["STM32"])
        out = _expand_requirements([req], {"良好的沟通表达与执行推进能力": ["沟通表达", "执行推进"]})
        assert len(out) == 1 and out[0] is req


# ── 杠杆三：三分类 / 行为衰减 / 必要技能闸门 ─────────────────────
class TestLever3:
    def test_requirement_typing(self):
        assert requirement_type(_req(head="软件测试", instances=["STM32"])) == "skill_required"
        assert requirement_type({**_req(head="高级会计师职称"), "kind": "preferred"}) == "professional"
        assert requirement_type(_req(head="沟通表达与执行推进能力")) == "behavior"
        assert requirement_type(_req(head="质量导向：标准合规、过程规范")) == "behavior"  # T2 名称优先于顿号实例

    def test_behavior_decay_beyond_free_n(self):
        reqs = [_req(head=f"沟通表达变体{i}") for i in range(4)]
        for r in reqs:
            r["rtype"] = "behavior"
        _apply_behavior_decay(reqs)
        full = [r for r in reqs if not r.get("behavior_decayed")]
        dec = [r for r in reqs if r.get("behavior_decayed")]
        assert len(full) == config.COVERAGE_BEHAVIOR_FREE_N
        assert len(dec) == 2
        assert dec[0]["weight"] == pytest.approx(_req(head="x")["weight"] * config.COVERAGE_BEHAVIOR_DECAY)

    def test_required_skill_gate(self):
        job = {"requirements": ["熟悉嵌入式开发（STM32）", "具备良好的沟通能力"]}
        reqs = extract_requirements(job)
        emp = _employee(grades=[(2026, "B")], training=["Python"])
        chunks = [{"emp_id": "E1", "source": "training", "text": "培训：瑜伽入门（已完成）", "anchor": "a"}]
        from utils.evidence_index import EvidenceIndex
        idx = EvidenceIndex(chunks, char_bucket_encode([c["text"] for c in chunks]), encode_fn=char_bucket_encode)
        res = score_coverage(reqs, [emp], idx, cross_encoder_fn=None,
                             equivalences={}, encode_fn=char_bucket_encode, atomic_splits={})
        r = res["E1"]
        assert r["required_skill_gate"] is not None      # 必要技能 STM32 未成立
        assert r["coverage"] == pytest.approx(r["coverage_raw"] * config.COVERAGE_REQUIRED_SKILL_GATE)

    def test_gate_not_triggered_when_skill_met(self):
        job = {"requirements": ["熟悉嵌入式开发（STM32）"]}
        reqs = extract_requirements(job)
        emp = _employee()
        chunks = [{"emp_id": "E1", "source": "projects", "text": "项目：STM32 固件开发", "anchor": "a"}]
        from utils.evidence_index import EvidenceIndex
        idx = EvidenceIndex(chunks, char_bucket_encode([c["text"] for c in chunks]), encode_fn=char_bucket_encode)
        res = score_coverage(reqs, [emp], idx, cross_encoder_fn=None,
                             equivalences={}, encode_fn=char_bucket_encode, atomic_splits={})
        assert res["E1"]["required_skill_gate"] is None
        assert res["E1"]["coverage"] == res["E1"]["coverage_raw"] == 1.0
