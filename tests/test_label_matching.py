"""tests/test_label_matching.py — 三阶段标签匹配 Stage 2 recall_top_k 测试。

策略（仿 test_label_embedding）：
- 用 fake embedder（可控向量）测逻辑，不依赖真实模型
- _cache.clear() 防跨测试污染（[[test-isolation-module-level-state-leak]]）
- Stage 3 rerank_label_llm 测试在 Step 4 实现后补
"""
import numpy as np
import pytest

import config
from utils import label_embedding
from utils.label_matching import recall_top_k


# ── fake embedder（与 test_label_embedding 同款，可控向量）──
def _fake_embed(texts):
    """文本含 'AAA'→[1,0,0,0]，'BBB'→[0,1,0,0]，'CCC'→[0,0,1,0]，否则零向量。"""
    vec_map = {"AAA": [1.0, 0.0, 0.0, 0.0], "BBB": [0.0, 1.0, 0.0, 0.0],
               "CCC": [0.0, 0.0, 1.0, 0.0]}
    out = []
    for t in texts:
        v = [0.0, 0.0, 0.0, 0.0]
        for tag, vec in vec_map.items():
            if tag in t:
                v = vec
                break
        out.append(v)
    return np.array(out, dtype=float)


def _fake_corpus():
    """三标签 corpus（AAA/BBB/CCC）。"""
    return [
        {"tier": "T1", "name": "AAA", "text": "AAA: aaa desc",
         "category": "skill", "definition": "aaa desc", "keywords": []},
        {"tier": "T1", "name": "BBB", "text": "BBB: bbb desc",
         "category": "skill", "definition": "bbb desc", "keywords": []},
        {"tier": "T1", "name": "CCC", "text": "CCC: ccc desc",
         "category": "skill", "definition": "ccc desc", "keywords": []},
    ]


@pytest.fixture(autouse=True)
def _clear_cache():
    """每测清 LRU 缓存，防跨测试污染。"""
    label_embedding._cache.clear()
    yield
    label_embedding._cache.clear()


# ════════════ recall_top_k 基础逻辑 ════════════

class TestRecallTopK:
    def test_top1_is_most_similar(self):
        """concept 含 AAA → top1 应是 AAA（sim=1.0）。"""
        corpus = _fake_corpus()
        result = recall_top_k("AAA concept", corpus, encode_fn=_fake_embed, top_k=3)
        assert len(result) == 3
        assert result[0][0] == "AAA"
        assert result[0][1] == pytest.approx(1.0)

    def test_sim_descending_order(self):
        """返回项按 sim 降序。"""
        corpus = _fake_corpus()
        result = recall_top_k("AAA concept", corpus, encode_fn=_fake_embed, top_k=3)
        sims = [s for _, s in result]
        assert sims == sorted(sims, reverse=True)

    def test_top_k_limits_count(self):
        """top_k=2 → 返回 2 项。"""
        result = recall_top_k("AAA", _fake_corpus(), encode_fn=_fake_embed, top_k=2)
        assert len(result) == 2

    def test_top_k_exceeds_corpus_returns_all(self):
        """top_k > len(corpus) → 返回 len(corpus) 项，不越界。"""
        result = recall_top_k("AAA", _fake_corpus(), encode_fn=_fake_embed, top_k=10)
        assert len(result) == 3

    def test_top_k_none_uses_config_default(self, monkeypatch):
        """top_k=None → 读 config.LABEL_RECALL_TOP_K 作为默认 k。

        用 monkeypatch 把 config 默认设为 2（< corpus 3 项），解耦真实 config 值，
        真正验证"None 时回退到 config 默认"而非硬编码。
        """
        monkeypatch.setattr(config, "LABEL_RECALL_TOP_K", 2)
        result = recall_top_k("AAA", _fake_corpus(), encode_fn=_fake_embed, top_k=None)
        assert len(result) == 2  # config 默认 2 生效（corpus 3 项，k=2 截断）

    def test_default_top_k_is_tuned_20(self):
        """config.LABEL_RECALL_TOP_K 锁定 k=20（recall@k=20 实验定标，2026-07-27）。

        原 k=3 致 GT 常不在候选内（recall 实验），k=20 修复召回。此断言是
        config 漂移 guard——若有人调 k，需同步更新此处与实验记录。
        """
        assert config.LABEL_RECALL_TOP_K == 20


# ════════════ C3 边界守卫 ════════════

class TestRecallTopKGuards:
    def test_empty_concept_returns_empty(self):
        assert recall_top_k("", _fake_corpus(), encode_fn=_fake_embed) == []

    def test_none_concept_returns_empty(self):
        assert recall_top_k(None, _fake_corpus(), encode_fn=_fake_embed) == []

    def test_empty_corpus_returns_empty(self):
        assert recall_top_k("AAA", [], encode_fn=_fake_embed) == []

    def test_top_k_zero_returns_empty(self):
        assert recall_top_k("AAA", _fake_corpus(), encode_fn=_fake_embed, top_k=0) == []

    def test_negative_top_k_returns_empty(self):
        assert recall_top_k("AAA", _fake_corpus(), encode_fn=_fake_embed, top_k=-1) == []


# ════════════ corpus 预编码矩阵复用 ════════════

class TestRecallPrecomputedVecs:
    def test_precomputed_vecs_skips_rencode(self):
        """corpus_text_vecs 传入 → 不现场重编码 corpus（验证复用，省成本）。"""
        corpus = _fake_corpus()
        # 预编码一次
        pre_vecs = label_embedding.encode_labels(
            tuple(c["text"] for c in corpus), encode_fn=_fake_embed
        )
        # patch encode_labels 监控是否被调（传入 pre_vecs 时 concept 仍需编码，但 corpus 不应重编）
        call_count = {"n": 0}
        original = label_embedding.encode_labels

        def counting_encode(texts, encode_fn=None):
            call_count["n"] += 1
            return original(texts, encode_fn=encode_fn)

        import utils.label_matching as lm
        lm.encode_labels = counting_encode
        try:
            result = recall_top_k(
                "AAA", corpus, corpus_text_vecs=pre_vecs, encode_fn=_fake_embed, top_k=3
            )
        finally:
            lm.encode_labels = original
        # 只应编码 concept 1 次，corpus 不重编
        assert call_count["n"] == 1
        assert result[0][0] == "AAA"

    def test_precomputed_vecs_none_rencodes(self):
        """corpus_text_vecs=None → 现场编码 corpus（靠 LRU 缓存）。"""
        corpus = _fake_corpus()
        result = recall_top_k(
            "AAA", corpus, corpus_text_vecs=None, encode_fn=_fake_embed, top_k=3
        )
        assert result[0][0] == "AAA"

    def test_precomputed_vecs_empty_returns_empty(self):
        """预编码矩阵为空 → []。"""
        result = recall_top_k(
            "AAA", _fake_corpus(),
            corpus_text_vecs=np.array([]), encode_fn=_fake_embed, top_k=3,
        )
        assert result == []


# ════════════ Stage 3: rerank_label_llm ════════════

from utils.label_matching import rerank_label_llm  # noqa: E402


def _make_item(idx, concept, standard_label, candidates,
               category="skill", extract_confidence=0.5):
    """构造 rerank 输入项。"""
    return {
        "idx": idx, "concept": concept, "standard_label": standard_label,
        "category": category, "candidates": candidates,
        "extract_confidence": extract_confidence,
    }


def _fake_corpus_with_names(names):
    """构造指定 name 集的 corpus（供快路径精确匹配测试）。"""
    return [{"name": n, "text": f"{n}: desc", "category": "skill"} for n in names]


class _FakeLLM:
    """记录调用次数 + 返回可配置 response。"""
    def __init__(self, response, n_calls_to_fail=None):
        self.response = response
        self.call_count = 0
        self.n_calls_to_fail = n_calls_to_fail  # 前 N 次返回 error

    def __call__(self, **kwargs):
        self.call_count += 1
        if self.n_calls_to_fail and self.call_count <= self.n_calls_to_fail:
            return {"content": None, "error": "simulated parse failed",
                    "model": "mock", "usage": {}, "raw_content": None,
                    "schema_validated": False}
        return self.response


class TestRerankLabelLlm:
    def test_empty_items_returns_empty_no_llm(self):
        fake = _FakeLLM({"content": [], "error": None})
        assert rerank_label_llm([], {}, None, call_llm_json_fn=fake) == []
        assert fake.call_count == 0

    def test_c1_symmetry_success_and_failure_same_keys(self):
        """成功 + 解析失败两路径，每项顶层 key 集合相同。"""
        items = [_make_item(0, "Java开发", "Java开发", ["Java开发", "Python开发"])]
        # 成功路径
        ok_llm = _FakeLLM({"content": [{"idx": 0, "matched_label": "Java开发",
                                       "match_confidence": 0.9, "rationale": "ok"}],
                          "error": None})
        ok = rerank_label_llm(items, {}, None, call_llm_json_fn=ok_llm)
        # 失败路径
        fail_llm = _FakeLLM({"content": None, "error": "parse failed"})
        fail = rerank_label_llm(items, {}, None, call_llm_json_fn=fail_llm)
        assert len(ok) == 1 and len(fail) == 1
        assert set(ok[0].keys()) == set(fail[0].keys())

    def test_d6_no_retry_on_parse_failure_v8(self):
        """V8：持续失败输入 → LLM 仅调 1 次，全部降级 trust standard_label。"""
        items = [
            _make_item(0, "Java开发", "Java开发", ["Java开发", "Python开发"]),
            _make_item(1, "团队管理", "团队管理", ["团队管理", "领导力"]),
        ]
        # 连续失败
        fail_llm = _FakeLLM({"content": None, "error": "parse failed"})
        result = rerank_label_llm(items, {}, None, call_llm_json_fn=fail_llm)
        assert fail_llm.call_count == 1  # D6：不重试
        assert len(result) == 2
        assert all(r["mapping_source"] == "rerank_failed_trust_llm" for r in result)
        # 降级信任 standard_label
        assert result[0]["matched_label"] == "Java开发"
        assert result[1]["matched_label"] == "团队管理"

    def test_batch_single_call_for_multiple_items(self):
        """5 项 items 单次 LLM 调用。"""
        items = [_make_item(i, f"c{i}", f"s{i}", [f"s{i}", "x"]) for i in range(5)]
        content = [{"idx": i, "matched_label": f"s{i}", "match_confidence": 0.9,
                    "rationale": "ok"} for i in range(5)]
        fake = _FakeLLM({"content": content, "error": None})
        result = rerank_label_llm(items, {}, None, call_llm_json_fn=fake)
        assert fake.call_count == 1
        assert len(result) == 5
        assert [r["matched_label"] for r in result] == [f"s{i}" for i in range(5)]

    def test_exact_match_skips_rerank(self):
        """standard_label 精确匹配 corpus name → LLM 不被调。"""
        corpus = _fake_corpus_with_names(["Java开发", "Python开发"])
        items = [_make_item(0, "Java开发经验", "Java开发", ["Java开发", "Python开发"])]
        fake = _FakeLLM({"content": [], "error": None})
        result = rerank_label_llm(items, {}, corpus, call_llm_json_fn=fake)
        assert fake.call_count == 0
        assert result[0]["mapping_source"] == "exact_name_match"
        assert result[0]["matched_label"] == "Java开发"
        assert result[0]["match_confidence"] == 1.0

    def test_corpus_none_disables_exact_match(self):
        """corpus=None → 不启用快路径，全走 rerank。"""
        items = [_make_item(0, "Java开发经验", "Java开发", ["Java开发", "Python开发"])]
        content = [{"idx": 0, "matched_label": "Python开发",
                    "match_confidence": 0.8, "rationale": "x"}]
        fake = _FakeLLM({"content": content, "error": None})
        result = rerank_label_llm(items, {}, None, call_llm_json_fn=fake)
        assert fake.call_count == 1
        assert result[0]["mapping_source"] == "llm_rerank"

    def test_new_label_high_confidence(self):
        """LLM 返回 NEW + conf≥阈值 → is_new_label=True。"""
        items = [_make_item(0, "量子计算", "量子计算", ["数据分析", "机器学习"])]
        content = [{"idx": 0, "matched_label": "NEW",
                    "match_confidence": 0.9, "rationale": "无合适候选"}]
        fake = _FakeLLM({"content": content, "error": None})
        result = rerank_label_llm(items, {}, None, call_llm_json_fn=fake)
        assert result[0]["is_new_label"] is True
        assert result[0]["mapping_source"] == "new_label"
        assert result[0]["matched_label"] == "量子计算"  # 用 concept 作新标签

    def test_new_label_low_confidence_becomes_pending(self):
        """LLM 返回 NEW 但 conf<阈值 → 不算新标签，降 pending 选 top1。"""
        items = [_make_item(0, "量子计算", "量子计算", ["数据分析", "机器学习"])]
        content = [{"idx": 0, "matched_label": "NEW",
                    "match_confidence": 0.3, "rationale": "不确定"}]
        fake = _FakeLLM({"content": content, "error": None})
        result = rerank_label_llm(items, {}, None, call_llm_json_fn=fake)
        assert result[0]["is_new_label"] is False
        assert result[0]["mapping_source"] == "pending_review"
        assert result[0]["matched_label"] == "数据分析"  # candidates[0]

    def test_new_label_cap_overflow_degrades_third(self, monkeypatch):
        """3 项全 NEW 高 conf，cap=2 → 第 3 个降级选 top1。"""
        monkeypatch.setattr(config, "LABEL_NEW_LABEL_MAX_PER_EMP", 2)
        items = [_make_item(i, f"c{i}", f"s{i}", [f"s{i}", "x"]) for i in range(3)]
        content = [{"idx": i, "matched_label": "NEW",
                    "match_confidence": 0.9, "rationale": "新"} for i in range(3)]
        fake = _FakeLLM({"content": content, "error": None})
        result = rerank_label_llm(items, {}, None, call_llm_json_fn=fake)
        sources = [r["mapping_source"] for r in result]
        assert sources.count("new_label") == 2
        assert sources.count("new_label_capped_trust_top1") == 1
        # 第 3 个降级选 candidates[0]
        capped = [r for r in result if r["mapping_source"] == "new_label_capped_trust_top1"][0]
        assert capped["matched_label"] == "s2"

    def test_matched_label_not_in_candidates_degrades(self):
        """LLM 返回 candidates 之外的标签（非 NEW）→ 降级 trust standard_label。"""
        items = [_make_item(0, "Java开发", "Java开发", ["Java开发", "Python开发"])]
        content = [{"idx": 0, "matched_label": "C++开发",  # 不在 candidates
                    "match_confidence": 0.9, "rationale": "x"}]
        fake = _FakeLLM({"content": content, "error": None})
        result = rerank_label_llm(items, {}, None, call_llm_json_fn=fake)
        assert result[0]["mapping_source"] == "rerank_failed_trust_llm"
        assert result[0]["matched_label"] == "Java开发"  # 信任 standard_label

    def test_low_confidence_match_becomes_pending(self):
        """matched 在 candidates 但 conf<阈值 → pending_review。"""
        items = [_make_item(0, "Java开发", "Java开发", ["Java开发", "Python开发"])]
        content = [{"idx": 0, "matched_label": "Python开发",
                    "match_confidence": 0.4, "rationale": "不确定"}]
        fake = _FakeLLM({"content": content, "error": None})
        result = rerank_label_llm(items, {}, None, call_llm_json_fn=fake)
        assert result[0]["mapping_source"] == "pending_review"
        assert result[0]["matched_label"] == "Python开发"

    def test_empty_rationale_uses_default(self):
        """rationale 空 → 用默认串，不降级（matched 仍合法）。"""
        items = [_make_item(0, "Java开发", "Java开发", ["Java开发", "Python开发"])]
        content = [{"idx": 0, "matched_label": "Java开发",
                    "match_confidence": 0.9, "rationale": ""}]
        fake = _FakeLLM({"content": content, "error": None})
        result = rerank_label_llm(items, {}, None, call_llm_json_fn=fake)
        assert result[0]["mapping_source"] == "llm_rerank"
        assert result[0]["rationale"] == "LLM 重排选择"

    def test_non_dict_response_degrades(self):
        """LLM 返回非 dict response（如异常场景字符串）→ 降级。"""
        items = [_make_item(0, "Java开发", "Java开发", ["Java开发"])]
        # 直接传返回非 dict 的 callable（绕过 _FakeLLM 的 dict 契约）
        result = rerank_label_llm(items, {}, None, call_llm_json_fn=lambda **k: "not a dict")
        assert result[0]["mapping_source"] == "rerank_failed_trust_llm"
        assert result[0]["matched_label"] == "Java开发"

    def test_idx_alignment_preserved(self):
        """非连续 idx 的 items → 结果按原 items 顺序返回。"""
        items = [
            _make_item(10, "c10", "s10", ["s10", "x"]),
            _make_item(20, "c20", "s20", ["s20", "x"]),
        ]
        content = [{"idx": 0, "matched_label": "s10", "match_confidence": 0.9, "rationale": "a"},
                   {"idx": 1, "matched_label": "s20", "match_confidence": 0.9, "rationale": "b"}]
        fake = _FakeLLM({"content": content, "error": None})
        result = rerank_label_llm(items, {}, None, call_llm_json_fn=fake)
        # 结果按 items 原序，matched_label 对齐
        assert [r["matched_label"] for r in result] == ["s10", "s20"]


# ════════════ Stage 3: rerank_cross_encoder (Step 8c) ════════════

from utils.label_matching import (  # noqa: E402
    rerank_cross_encoder, _reset_cross_encoder_for_test,
    SOURCE_CROSS_RERANK, SOURCE_CROSS_NEW_LABEL, SOURCE_CROSS_PENDING,
    SOURCE_CROSS_FAILED_FALLBACK_LLM, SOURCE_EXACT_CONFIRMED,
)


def _fake_encoder_high(cands_target="s0"):
    """构造打分函数：让 cands_target 候选得分最高（>conf 阈值）。"""
    def _fn(pairs):
        scores = []
        for concept, cand in pairs:
            scores.append(0.9 if cand == cands_target else 0.1)
        return scores
    return _fn


class TestRerankCrossEncoder:
    """Step 8c：cross-encoder 精排替换 zero-shot LLM。"""

    def setup_method(self):
        """每测试重置单例，避免 _load_cross_encoder 缓存干扰。"""
        _reset_cross_encoder_for_test()

    def test_empty_items_returns_empty_no_encoder(self):
        """空 items → 返回 []，cross-encoder 不被调。"""
        called = {"n": 0}

        def _fn(pairs):
            called["n"] += 1
            return []
        result = rerank_cross_encoder([], {}, None, cross_encoder_fn=_fn)
        assert result == []
        assert called["n"] == 0

    def test_exact_match_always_goes_through_full_rerank(self):
        """Step 1.10：禁用 exact 快路径锁定——exact 项也进全候选重排。

        旧 Step 8e 逻辑：standard_label 精确匹配 corpus 名时，单 pair 确认高分即跳过。
        副作用：LLM 选错相近标签时被锁死。新逻辑：所有项进全候选重排，cross-encoder
        对 (concept, 全候选) 打分选最优。LLM 提议若最优会被选中，选错能纠正。
        """
        corpus = _fake_corpus_with_names(["Java开发", "Python开发"])
        items = [_make_item(0, "Java开发经验", "Java开发", ["Java开发", "Python开发"])]
        call_count = {"n": 0}

        def _fn(pairs):
            call_count["n"] += 1
            # 全候选打分：Java开发 高分（cross-encoder 选它）
            return [0.9 if cand == "Java开发" else 0.1 for _, cand in pairs]
        result = rerank_cross_encoder(items, {}, corpus, cross_encoder_fn=_fn)
        # exact 项进全候选重排 → cross-encoder 选 Java开发（最高分）
        assert result[0]["matched_label"] == "Java开发"
        assert result[0]["mapping_source"] == SOURCE_CROSS_RERANK
        assert result[0]["match_confidence"] == 0.9
        # 进了全候选打分（不再有单独的 exact 确认 pair 调用）
        assert call_count["n"] == 1

    def test_exact_match_unconfirmed_falls_through_to_rerank(self):
        """Step 1.10：所有项默认进全候选重排——cross-encoder 选最优候选纠正 LLM 错误提议。

        典型：concept='参与工业IoT管理平台' standard_label='物联网'（精确匹配 corpus）
        但 cross-encoder 对全候选打分 → 智能制造高分 → 纠正到智能制造。
        """
        corpus = _fake_corpus_with_names(["物联网", "智能制造"])
        items = [_make_item(0, "参与工业IoT管理平台", "物联网",
                             ["物联网", "智能制造"])]

        def _fn(pairs):
            # 全候选 pair (IoT平台, 物联网)(IoT平台, 智能制造) → 智能制造高分
            scores = []
            for concept, cand in pairs:
                if cand == "智能制造":
                    scores.append(0.85)
                else:
                    scores.append(0.1)
            return scores
        result = rerank_cross_encoder(items, {}, corpus, cross_encoder_fn=_fn)
        # 全候选重排 → 选智能制造（纠正 LLM 的物联网错误提议）
        assert result[0]["matched_label"] == "智能制造"
        assert result[0]["mapping_source"] == SOURCE_CROSS_RERANK

    def test_cross_encoder_selects_top1_candidate(self):
        """cross-encoder 打分最高候选被选，mapping_source=cross_encoder_rerank。"""
        items = [_make_item(0, "Java微服务", "Java开发", ["Python开发", "Java开发"])]
        encoder = _fake_encoder_high(cands_target="Java开发")
        result = rerank_cross_encoder(items, {}, None, cross_encoder_fn=encoder)
        assert result[0]["matched_label"] == "Java开发"
        assert result[0]["mapping_source"] == SOURCE_CROSS_RERANK
        assert result[0]["is_new_label"] is False
        assert result[0]["match_confidence"] == 0.9

    def test_low_score_below_new_threshold_is_new_label(self, monkeypatch):
        """top1 score < RERANKER_NEW_LABEL_THRESHOLD → is_new_label=True。"""
        monkeypatch.setattr(config, "RERANKER_NEW_LABEL_THRESHOLD", 0.5)
        items = [_make_item(0, "量子计算", "量子计算", ["数据分析", "机器学习"])]

        def _low_fn(pairs):
            return [0.1] * len(pairs)  # 全部低分
        result = rerank_cross_encoder(items, {}, None, cross_encoder_fn=_low_fn)
        assert result[0]["mapping_source"] == SOURCE_CROSS_NEW_LABEL
        assert result[0]["is_new_label"] is True
        assert result[0]["matched_label"] == "量子计算"  # 用 concept

    def test_mid_score_between_thresholds_is_pending(self, monkeypatch):
        """new_threshold ≤ score < conf_threshold → pending_review。"""
        monkeypatch.setattr(config, "RERANKER_NEW_LABEL_THRESHOLD", 0.3)
        monkeypatch.setattr(config, "RERANKER_CONFIDENCE_THRESHOLD", 0.6)
        items = [_make_item(0, "Java开发", "Java开发", ["Java开发", "Python开发"])]

        def _mid_fn(pairs):
            return [0.4] * len(pairs)  # 介于 0.3 和 0.6 之间
        result = rerank_cross_encoder(items, {}, None, cross_encoder_fn=_mid_fn)
        assert result[0]["mapping_source"] == SOURCE_CROSS_PENDING
        assert result[0]["is_new_label"] is False
        assert result[0]["match_confidence"] == 0.4

    def test_fallback_to_llm_when_encoder_none(self):
        """cross_encoder_fn=None 且加载失败 → 降级 rerank_label_llm。"""
        import utils.label_matching as lm
        original = lm._load_cross_encoder
        lm._load_cross_encoder = lambda: None
        try:
            items = [_make_item(0, "Java开发", "Java开发", ["Java开发", "Python开发"])]
            content = [{"idx": 0, "matched_label": "Java开发",
                        "match_confidence": 0.9, "rationale": "llm ok"}]
            fake = _FakeLLM({"content": content, "error": None})
            result = rerank_cross_encoder(items, {}, None,
                                          call_llm_json_fn=fake)
            assert result[0]["matched_label"] == "Java开发"
            # LLM 路径成功 → mapping_source=llm_rerank（未被改标 fallback）
            assert result[0]["mapping_source"] == "llm_rerank"
        finally:
            lm._load_cross_encoder = original

    def test_fallback_llm_failure_marked_cross_failed(self):
        """降级到 LLM 后 LLM 也失败 → mapping_source=cross_failed_fallback_llm。"""
        import utils.label_matching as lm
        original = lm._load_cross_encoder
        lm._load_cross_encoder = lambda: None
        try:
            items = [_make_item(0, "Java开发", "Java开发", ["Java开发"])]
            fail_llm = _FakeLLM({"content": None, "error": "parse failed"})
            result = rerank_cross_encoder(items, {}, None,
                                          call_llm_json_fn=fail_llm)
            assert result[0]["mapping_source"] == SOURCE_CROSS_FAILED_FALLBACK_LLM
            assert result[0]["matched_label"] == "Java开发"  # 信任 standard_label
        finally:
            lm._load_cross_encoder = original

    def test_encoder_none_with_exact_corpus_not_locked(self):
        """P0 回归：encoder=None + corpus 有 + exact 命中 → 不再 conf=1.0 锁死，改走 LLM 重排。

        复现实验 025304 真实路径：cross-encoder 加载失败，LLM 提议 '物联网' 精确命中
        corpus，旧逻辑 conf=1.0 直接跳过锁死错误提议。修复后应降级 LLM 重排，
        LLM 有机会纠正到 '智能制造'。
        """
        import utils.label_matching as lm
        original = lm._load_cross_encoder
        lm._load_cross_encoder = lambda: None
        try:
            corpus = _fake_corpus_with_names(["物联网", "智能制造"])
            items = [_make_item(0, "参与工业IoT管理平台", "物联网",
                                 ["物联网", "智能制造"])]
            # LLM 重排纠正到智能制造
            content = [{"idx": 0, "matched_label": "智能制造",
                        "match_confidence": 0.85, "rationale": "IoT平台服务于智能制造"}]
            fake = _FakeLLM({"content": content, "error": None})
            result = rerank_cross_encoder(items, {}, corpus,
                                          call_llm_json_fn=fake)
            # 不应锁死为 exact_name_match + conf=1.0
            assert result[0]["mapping_source"] != "exact_name_match"
            assert result[0]["match_confidence"] != 1.0
            # LLM 重排纠正成功
            assert result[0]["matched_label"] == "智能制造"
            assert result[0]["mapping_source"] == "llm_rerank"
            assert fake.call_count == 1  # LLM 被调用
        finally:
            lm._load_cross_encoder = original

    def test_encoder_exception_falls_back_to_llm(self):
        """cross-encoder 打分抛异常 → 整批降级 LLM。"""
        items = [_make_item(0, "Java开发", "Java开发", ["Java开发", "Python开发"])]

        def _bad_encoder(pairs):
            raise RuntimeError("model crashed")

        content = [{"idx": 0, "matched_label": "Java开发",
                    "match_confidence": 0.9, "rationale": "llm ok"}]
        fake = _FakeLLM({"content": content, "error": None})
        result = rerank_cross_encoder(items, {}, None,
                                      cross_encoder_fn=_bad_encoder,
                                      call_llm_json_fn=fake)
        assert result[0]["matched_label"] == "Java开发"
        assert result[0]["mapping_source"] == "llm_rerank"  # LLM 成功

    def test_c1_symmetry_all_paths_same_keys(self, monkeypatch):
        """成功/新标签/pending/降级 四路径顶层 key 集合相同。"""
        monkeypatch.setattr(config, "RERANKER_NEW_LABEL_THRESHOLD", 0.3)
        monkeypatch.setattr(config, "RERANKER_CONFIDENCE_THRESHOLD", 0.6)
        expected_keys = {"idx", "matched_label", "is_new_label", "match_confidence",
                         "rationale", "candidates_seen", "mapping_source"}
        items_base = [_make_item(0, "c", "s0", ["s0", "x"])]

        # 成功
        r1 = rerank_cross_encoder(items_base, {}, None,
                                   cross_encoder_fn=_fake_encoder_high("s0"))
        # 新标签（全低分）
        r2 = rerank_cross_encoder(items_base, {}, None,
                                   cross_encoder_fn=lambda p: [0.1] * len(p))
        # pending（中分）
        r3 = rerank_cross_encoder(items_base, {}, None,
                                   cross_encoder_fn=lambda p: [0.4] * len(p))
        # 降级 LLM 成功
        import utils.label_matching as lm
        original = lm._load_cross_encoder
        lm._load_cross_encoder = lambda: None
        try:
            content = [{"idx": 0, "matched_label": "s0",
                        "match_confidence": 0.9, "rationale": "ok"}]
            fake = _FakeLLM({"content": content, "error": None})
            r4 = rerank_cross_encoder(items_base, {}, None,
                                       call_llm_json_fn=fake)
        finally:
            lm._load_cross_encoder = original

        for r, label in [(r1[0], "success"), (r2[0], "new_label"),
                         (r3[0], "pending"), (r4[0], "fallback")]:
            assert set(r.keys()) == expected_keys, f"{label} keys mismatch: {set(r.keys())}"

    def test_idx_alignment_preserved(self):
        """非连续 idx → 结果按 items 原序。"""
        items = [
            _make_item(10, "c10", "s10", ["s10", "x"]),
            _make_item(20, "c20", "s20", ["s20", "x"]),
        ]
        # 让每项的第一个候选最高分
        def _fn(pairs):
            # pairs 按 (item0_c0, item0_c1, item1_c0, item1_c1) 顺序
            return [0.9, 0.1, 0.9, 0.1]
        result = rerank_cross_encoder(items, {}, None, cross_encoder_fn=_fn)
        assert [r["matched_label"] for r in result] == ["s10", "s20"]
        assert all(r["mapping_source"] == SOURCE_CROSS_RERANK for r in result)

    def test_new_label_cap_overflow_degrades(self, monkeypatch):
        """3 项全 low-score 新标签，cap=2 → 第 3 个降级选 top1 候选。"""
        monkeypatch.setattr(config, "LABEL_NEW_LABEL_MAX_PER_EMP", 2)
        monkeypatch.setattr(config, "RERANKER_NEW_LABEL_THRESHOLD", 0.5)
        items = [_make_item(i, f"c{i}", f"s{i}", [f"s{i}", "x"]) for i in range(3)]
        # 全部低分 → 全判新标签，超额第 3 降级
        result = rerank_cross_encoder(items, {}, None,
                                      cross_encoder_fn=lambda p: [0.1] * len(p))
        sources = [r["mapping_source"] for r in result]
        assert sources.count(SOURCE_CROSS_NEW_LABEL) == 2
        assert sources.count("new_label_capped_trust_top1") == 1

    def test_empty_candidates_degrades(self):
        """某项 candidates 为空 → 该项降级（无 pair 可打分）。"""
        items = [_make_item(0, "c", "s", [])]  # 空候选
        encoder = _fake_encoder_high("s")
        result = rerank_cross_encoder(items, {}, None, cross_encoder_fn=encoder)
        # 无 pairs → 该项无 top1 → 降级 _degrade_item
        assert result[0]["mapping_source"] == SOURCE_CROSS_FAILED_FALLBACK_LLM


class TestLoadCrossEncoderRetry:
    """P0-1 回归：加载异常不永久缓存 None，允许下次重试。"""

    def test_transient_failure_does_not_cache_none(self, monkeypatch):
        """首次加载抛异常 → 返回 None；下次调用应重新尝试（不返回缓存 None）。"""
        import utils.label_matching as lm
        _reset_cross_encoder_for_test()

        call_count = {"n": 0}

        def _flaky_load():
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise RuntimeError("cold start timeout")  # 首次临时失败
            return "fake_encoder"  # 第二次成功

        # 强制走加载分支：配置存在 + 未尝试
        monkeypatch.setattr(config, "RERANKER_MODEL_NAME", "BAAI/bge-reranker-v2-m3")
        monkeypatch.setattr(config, "RERANKER_LOCAL_PATH", None)
        # patch CrossEncoder 导入为可控行为
        import sys
        fake_module = type(sys)("sentence_transformers")
        fake_module.CrossEncoder = lambda name: _flaky_load()
        monkeypatch.setitem(sys.modules, "sentence_transformers", fake_module)

        try:
            r1 = lm._load_cross_encoder()
            r2 = lm._load_cross_encoder()
            assert r1 is None  # 首次失败返回 None
            assert r2 == "fake_encoder"  # 第二次重试成功（未缓存 None）
            assert call_count["n"] == 2  # 调用了两次
        finally:
            _reset_cross_encoder_for_test()

    def test_success_caches(self, monkeypatch):
        """加载成功 → 后续调用不重复加载（D6 成功路径缓存）。"""
        import utils.label_matching as lm
        _reset_cross_encoder_for_test()

        call_count = {"n": 0}

        def _load():
            call_count["n"] += 1
            return "fake_encoder"

        monkeypatch.setattr(config, "RERANKER_MODEL_NAME", "BAAI/bge-reranker-v2-m3")
        monkeypatch.setattr(config, "RERANKER_LOCAL_PATH", None)
        import sys
        fake_module = type(sys)("sentence_transformers")
        fake_module.CrossEncoder = lambda name: _load()
        monkeypatch.setitem(sys.modules, "sentence_transformers", fake_module)

        try:
            lm._load_cross_encoder()
            lm._load_cross_encoder()
            lm._load_cross_encoder()
            assert call_count["n"] == 1  # 仅加载一次，后续走缓存
        finally:
            _reset_cross_encoder_for_test()

