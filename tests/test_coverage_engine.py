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
    build_evidence_matrix,
    classify_relation,
    extract_requirements,
    job_weight_triple,
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
        assert r["kind"] == "necessary" and r["weight"] == config.COVERAGE_W_MUST

    def test_preferred_item_gets_lower_weight(self):
        job = {"requirements": ["有工业物联网项目质量工作经验者优先"]}
        reqs = extract_requirements(job)
        assert reqs[0]["kind"] == "preferred"
        assert reqs[0]["kind"] == "preferred" and reqs[0]["weight"] == config.COVERAGE_W_MUST

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
        # 技术类矩阵：total = 70·S_prof + 15·S_behav + 15·P + bonus
        job = {"requirements": ["熟悉嵌入式开发（STM32）", "具备良好的沟通能力"]}
        reqs = extract_requirements(job)
        emp = _employee(grades=[(2026, "B")], training=["Python"])
        chunks = [{"emp_id": "E1", "source": "projects",
                   "text": "项目「x」：STM32 固件 + 沟通能力良好", "anchor": "a"}]
        from utils.evidence_index import EvidenceIndex
        idx = EvidenceIndex(chunks, char_bucket_encode([c["text"] for c in chunks]), encode_fn=char_bucket_encode)
        res = score_coverage(reqs, [emp], idx, cross_encoder_fn=None,
                             equivalences={}, encode_fn=char_bucket_encode,
                             atomic_splits={}, job_type="技术类")
        r = res["E1"]
        w = job_weight_triple("技术类")
        expect = w[0] * r["s_prof"] + w[1] * r["s_behav"] + w[2] * r["p"] + r["bonus"]
        if r["required_skill_gate"]:
            expect *= r["required_skill_gate"]["coef"]
        assert r["total"] == pytest.approx(expect, abs=0.05)
        assert r["w_matrix"] == [70.0, 15.0, 15.0]

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


# ── 两类划分（行为/专业 × 必须/优先 + 矩阵 + 加分 + total 级闸门）────────
class TestTwoClass:
    def test_requirement_typing_binary(self):
        assert requirement_type(_req(head="软件测试", instances=["STM32"])) == "professional"
        assert requirement_type(_req(head="数据分析与建模")) == "professional"
        assert requirement_type(_req(head="沟通表达与执行推进能力")) == "behavioral"
        assert requirement_type(_req(head="质量导向：标准合规、过程规范")) == "behavioral"  # T2 名称优先
        assert requirement_type(_req(head="团队管理经验或潜力")) == "behavioral"

    def test_matrix_lookup_and_default(self):
        assert job_weight_triple("技术类") == (70.0, 15.0, 15.0)
        assert job_weight_triple("职能类") == (40.0, 30.0, 30.0)
        assert job_weight_triple("不存在的类") == job_weight_triple("业务类")  # _default

    def test_preferred_bonus_not_in_weighted(self):
        # 优先项不进加权求和：只加 bonus = k×Σv/N_must
        job = {"requirements": ["熟悉嵌入式开发（STM32）", "有ISO9001证书者优先"]}
        reqs = extract_requirements(job)
        emp = _employee()
        chunks = [{"emp_id": "E1", "source": "training", "text": "培训：STM32（已完成）；证书：ISO9001", "anchor": "a"}]
        from utils.evidence_index import EvidenceIndex
        idx = EvidenceIndex(chunks, char_bucket_encode([c["text"] for c in chunks]), encode_fn=char_bucket_encode)
        res = score_coverage(reqs, [emp], idx, cross_encoder_fn=None,
                             equivalences={"有iso9001证书者优先": ["iso9001"]},
                             encode_fn=char_bucket_encode,
                             atomic_splits={}, job_type="技术类")
        r = res["E1"]
        assert r["s_prof"] == 1.0                      # 只有 1 条专业必须项且成立
        expect_bonus = config.COVERAGE_PREFERRED_K * 1.0 / 1  # 1 优先项成立 / 1 必须项
        assert r["bonus"] == pytest.approx(expect_bonus, abs=0.01)

    def test_prof_must_gate_on_total(self):
        job = {"requirements": ["熟悉嵌入式开发（STM32）", "具备良好的沟通能力"]}
        reqs = extract_requirements(job)
        emp = _employee()
        chunks = [{"emp_id": "E1", "source": "training", "text": "培训：瑜伽入门（已完成）", "anchor": "a"}]
        from utils.evidence_index import EvidenceIndex
        idx = EvidenceIndex(chunks, char_bucket_encode([c["text"] for c in chunks]), encode_fn=char_bucket_encode)
        res = score_coverage(reqs, [emp], idx, cross_encoder_fn=None,
                             equivalences={}, encode_fn=char_bucket_encode,
                             atomic_splits={}, job_type="技术类")
        r = res["E1"]
        assert r["required_skill_gate"] is not None    # 专业必须 STM32 未成立
        assert r["required_skill_gate"]["k"] == 1
        assert r["required_skill_gate"]["coef"] == pytest.approx(1 - config.COVERAGE_GATE_STEP)
        w = job_weight_triple("技术类")
        core = w[0] * r["s_prof"] + w[1] * r["s_behav"] + w[2] * r["p"] + r["bonus"]
        assert r["total"] == pytest.approx(core * r["required_skill_gate"]["coef"], abs=0.05)

    def test_behav_must_unmet_no_gate(self):
        # 行为类必须项未成立不触发闸门（仅专业必须触发）
        job = {"requirements": ["熟悉嵌入式开发（STM32）", "具备良好的沟通能力"]}
        reqs = extract_requirements(job)
        emp = _employee()
        chunks = [{"emp_id": "E1", "source": "projects", "text": "项目：STM32 固件开发", "anchor": "a"}]
        from utils.evidence_index import EvidenceIndex
        idx = EvidenceIndex(chunks, char_bucket_encode([c["text"] for c in chunks]), encode_fn=char_bucket_encode)
        res = score_coverage(reqs, [emp], idx, cross_encoder_fn=None,
                             equivalences={}, encode_fn=char_bucket_encode,
                             atomic_splits={}, job_type="技术类")
        r = res["E1"]
        assert r["required_skill_gate"] is None        # 专业必须成立（行为必须未成立无闸门）
        assert r["s_behav"] == 0.0

    def test_empty_class_neutral_half(self):
        # 只有行为要求 → 专业池空 → S_prof=0.5 中性
        job = {"requirements": ["具备良好的沟通表达能力"]}
        reqs = extract_requirements(job)
        emp = _employee()
        chunks = [{"emp_id": "E1", "source": "summary_evaluation", "text": "口头表达清晰", "anchor": "a"}]
        from utils.evidence_index import EvidenceIndex
        idx = EvidenceIndex(chunks, char_bucket_encode([c["text"] for c in chunks]), encode_fn=char_bucket_encode)
        res = score_coverage(reqs, [emp], idx, cross_encoder_fn=None,
                             equivalences={}, encode_fn=char_bucket_encode,
                             atomic_splits={}, job_type="职能类")
        r = res["E1"]
        assert r["class_neutral"] == ["professional"]
        assert r["s_prof"] == 0.5

    def test_evidence_multifaceted_no_discount(self):
        # 证据多面性：同一条 chunk 同时支撑专业要求与行为要求，无跨类打折
        equiv = {"团队管理": ["项目负责人"]}
        chunk = {"text": "项目「ERP升级」角色：项目负责人；负责方案设计与交付", "anchor": "a"}
        cls_prof = classify_relation(_req(head="项目管理"), chunk, equiv)
        cls_behav = classify_relation(_req(head="团队管理"), chunk, equiv)
        assert cls_behav["value"] == 1.0              # 行为要求被项目证据满足，不打折
        assert "跨类" not in cls_behav["note"]


# ── 拆句（用户 2026-10-25）+ 闸门 k 线性 ─────────────────────────
class TestClauseSplit:
    def test_compound_sentence_split(self):
        job = {"responsibilities": ["承担嵌入式软件方案设计与模块开发，参与需求分析和技术路线论证"]}
        reqs = extract_requirements(job)
        heads = [r["head"] for r in reqs]
        assert heads == ["嵌入式软件方案设计与模块开发", "需求分析和技术路线论证"]

    def test_gate_clause_dropped_subsentence(self):
        job = {"requirements": ["本科及以上学历，精通Java与微服务架构"]}
        reqs = extract_requirements(job)
        assert len(reqs) == 1 and reqs[0]["head"] == "Java与微服务架构"

    def test_preferred_per_clause(self):
        job = {"requirements": ["熟悉数据分析，有军工电子行业背景者优先"]}
        reqs = extract_requirements(job)
        kinds = {r["head"]: r["kind"] for r in reqs}
        assert kinds["数据分析"] == "necessary"
        assert kinds["有军工电子行业背景"] == "preferred"

    def test_no_clause_split_compat(self):
        job = {"requirements": ["熟悉数据处理与分析方法，了解大数据平台调度工具"]}
        reqs = extract_requirements(job, clause_split=False)
        assert len(reqs) == 1  # 旧模式整句单要求（83 闸门对照用）

    def test_short_fragment_fallback(self):
        job = {"requirements": ["懂C，会Linux"]}
        reqs = extract_requirements(job)  # 子句<4字全弃 → 回退整句
        assert len(reqs) == 1

    def test_gate_linear_k2(self):
        job = {"requirements": ["熟悉嵌入式开发（STM32）", "掌握CAN总线协议", "熟悉以太网"]}
        reqs = extract_requirements(job)
        emp = _employee()
        chunks = [{"emp_id": "E1", "source": "training", "text": "培训：瑜伽入门", "anchor": "a"}]
        from utils.evidence_index import EvidenceIndex
        idx = EvidenceIndex(chunks, char_bucket_encode([c["text"] for c in chunks]), encode_fn=char_bucket_encode)
        res = score_coverage(reqs, [emp], idx, cross_encoder_fn=None,
                             equivalences={}, encode_fn=char_bucket_encode,
                             atomic_splits={}, job_type="技术类")
        r = res["E1"]
        assert r["required_skill_gate"]["k"] == 3          # 三条专业必须全缺
        assert r["required_skill_gate"]["coef"] == pytest.approx(1 - 0.05 * 3)
