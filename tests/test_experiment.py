"""tests/test_experiment.py — Day 2 实验脚本路径分类逻辑回归测试。

锁定 run_experiment 的 Path A（verified/corrected/pending）+ Path B（top-1/top-3）
分类逻辑，防 Day 3 重构时回归。用 mock _llm_extract 注入已知 content，断言分类。
"""
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import scripts.experiment_embedding_vs_llm as exp
from utils.label_embedding import load_label_corpus


_MOCK_CONTENT = {
    "t1_professional": [
        # LLM 正确提议 → 验证通过
        {"concept": "跨部门沟通顺畅", "standard_label": "跨部门协调", "category": "behavior"},
        # LLM 错提议 → embedding 纠正到 Java开发（不在 GT → corrected_wrong）
        {"concept": "Java微服务后端", "standard_label": "Python开发", "category": "skill"},
    ],
    "t2_behavioral": [],
    "big_five": {"openness": 72, "conscientiousness": 80, "extraversion": 55,
                 "agreeableness": 68, "neuroticism": 40},
    "t3_raw": {"learning_activities": [], "career_roles": [],
               "growth_evidence": [], "feedback_signals": []},
}

_MOCK_EXTRACT = {
    "content": _MOCK_CONTENT, "error": None,
    "model": "mock", "usage": {}, "offline_skipped": False,
}


def _make_emp(eid="JZ0001"):
    return {"employee_id": eid, "structured": {}, "text_summaries": {},
            "scores_360": {}, "performance": [], "training": []}


class TestRunExperiment:
    @pytest.fixture(autouse=True)
    def _mock_rerank(self):
        """mock rerank_cross_encoder 避免实验测试触发真实 BGE 模型加载（hermetic，省 16s）。

        Path C 用本地 BGE-reranker-v2-m3 cross-encoder 精排（rerank_cross_encoder）。
        降级时 rerank_cross_encoder 内部调 rerank_label_llm（默认 DeepSeek，非 Ollama）。
        mock 返回每项 matched_label=standard_label（信任 LLM 原始提议）+ cross_encoder_rerank 源。
        真实 cross-encoder 行为由 test_label_matching.py 的 TestRerankCrossEncoder 覆盖。
        """
        def fake_rerank(items, emp, corpus, **kw):
            return [{
                "idx": it.get("idx", i),
                "matched_label": it.get("standard_label", ""),
                "is_new_label": False,
                "match_confidence": 0.9,
                "rationale": "mock rerank",
                "candidates_seen": it.get("candidates", []),
                "mapping_source": "cross_encoder_rerank",
            } for i, it in enumerate(items)]
        with patch("scripts.experiment_embedding_vs_llm.rerank_cross_encoder",
                   side_effect=fake_rerank) as _m:
            yield _m

    def test_path_a_classifies_verified_and_corrected(self):
        # JZ0001 GT: 跨部门协调 in, Java开发 not in
        gt = {"JZ0001": {"跨部门协调", "团队管理", "智能制造"}}
        emps = [_make_emp("JZ0001")]
        corpus = load_label_corpus()
        with patch.object(exp.ProfileGeneration, "_llm_extract",
                          return_value=_MOCK_EXTRACT):
            summary = exp.run_experiment(emps, gt, corpus)
        pa = summary["path_a"]
        assert pa["total_mappings"] == 2
        # 跨部门沟通顺畅→跨部门协调 verified + in_gt
        assert pa["verified"] == 1
        assert pa["final_correct"] == 1
        # Java微服务后端→corrected to Java开发, not in GT → corrected_wrong
        assert pa["corrected_wrong"] == 1

    def test_path_b_top1_top3_hit(self):
        gt = {"JZ0001": {"跨部门协调", "Java开发"}}
        emps = [_make_emp("JZ0001")]
        corpus = load_label_corpus()
        with patch.object(exp.ProfileGeneration, "_llm_extract",
                          return_value=_MOCK_EXTRACT):
            summary = exp.run_experiment(emps, gt, corpus)
        pb = summary["path_b"]
        assert pb["total_mappings"] == 2
        # 跨部门沟通顺畅 top1=跨部门协调 (hit), Java微服务后端 top1=Java开发 (hit)
        assert pb["top1_hit"] == 2
        assert pb["top3_hit"] == 2

    def test_decision_thresholds(self):
        # ≥90% → 定稿；80-90% → 调阈值；<80% → Plan B
        # 用 verified-only mock 构造 100% 正确率
        good_content = {
            "t1_professional": [
                {"concept": "跨部门沟通顺畅", "standard_label": "跨部门协调", "category": "behavior"},
            ],
            "t2_behavioral": [], "big_five": {}, "t3_raw": {},
        }
        good_extract = {"content": good_content, "error": None,
                        "model": "mock", "usage": {}, "offline_skipped": False}
        gt = {"JZ0001": {"跨部门协调"}}
        emps = [_make_emp("JZ0001")]
        corpus = load_label_corpus()
        with patch.object(exp.ProfileGeneration, "_llm_extract",
                          return_value=good_extract):
            summary = exp.run_experiment(emps, gt, corpus)
        # 1/1 = 100% → 定稿
        assert summary["plan_b_triggered"] is False
        assert "定稿" in summary["decision"]

    def test_returns_key_symmetry(self):
        # C1: summary 顶层 key 稳定
        gt = {"JZ0001": {"跨部门协调"}}
        emps = [_make_emp("JZ0001")]
        corpus = load_label_corpus()
        with patch.object(exp.ProfileGeneration, "_llm_extract",
                          return_value=_MOCK_EXTRACT):
            summary = exp.run_experiment(emps, gt, corpus)
        for key in ("total_employees", "llm_call_attempts", "llm_call_failures",
                    "llm_calls", "valid_run", "path_a", "path_b", "path_c",
                    "decision", "plan_b_triggered", "per_employee"):
            assert key in summary
        for key in ("total_mappings", "verified", "corrected_correct",
                    "corrected_wrong", "pending", "final_correct",
                    "final_correct_rate_pct",
                    "recall_at_gt", "total_gt_labels", "recall_at_gt_pct"):
            assert key in summary["path_a"]
        for key in ("total_mappings", "top1_hit", "top3_hit",
                    "top1_rate_pct", "top3_rate_pct",
                    "top1_recall_at_gt", "total_gt_labels", "top1_recall_at_gt_pct"):
            assert key in summary["path_b"]
        for key in ("total_mappings", "final_correct", "final_correct_rate_pct",
                    "new_labels", "rerank_failures", "rerank_calls",
                    "recall_at_gt", "total_gt_labels", "recall_at_gt_pct",
                    "llm_rerank_actual_calls", "cross_encoder_actual_calls"):
            assert key in summary["path_c"]
        # per_employee 含 path_c 数组 + t3_count 字段（Step 1.8 C1 对称）
        assert "path_c" in summary["per_employee"][0]
        assert "t3_count" in summary["per_employee"][0]

    def test_t3_labels_flow_through_pairs_and_rerank(self):
        """Step 1.9a：t3_labels 项被 pairs/rerank_items 循环真实处理（非仅字段存在）。

        构造 content 含 t1(1)+t2(1)+t3(2)，其中 1 个 t3 项的 standard_label 在 GT 中。
        断言：
        a. path_c.total_mappings = t1+t2+t3 = 4（t3 项真进了 rerank 循环，非仅字段存在）
        b. emp_result.t3_count = 2（content_audit 真读 t3_labels 数组）
        c. path_c.recall_at_gt 含 T3 命中（t3 standard_label 在 GT → 计入 unique 命中集）
        d. total_gt_labels 含 T3 标签（防回归锁定）
        """
        content_with_t3 = {
            "t1_professional": [
                {"concept": "跨部门沟通顺畅", "standard_label": "跨部门协调",
                 "category": "behavior", "confidence": 0.9},
            ],
            "t2_behavioral": [
                {"concept": "主动承担新任务", "standard_label": "主动性",
                 "category": "behavior", "confidence": 0.8},
            ],
            "t3_labels": [
                # 第 1 项 standard_label 在 GT 中 → 应计入 path_c recall_at_gt
                {"concept": "对智能制造技术有好奇心", "standard_label": "智能制造潜质",
                 "category": "potential", "confidence": 0.7,
                 "evidence": [{"source": "360评价_2024", "text_snippet": "对新技术有兴趣"}]},
                # 第 2 项 standard_label 不在 GT
                {"concept": "乐于指导新人", "standard_label": "导师潜质",
                 "category": "potential", "confidence": 0.6,
                 "evidence": [{"source": "360评价_2024", "text_snippet": "愿意带新人"}]},
            ],
            "big_five": {}, "t3_raw": {},
        }
        extract_with_t3 = {"content": content_with_t3, "error": None,
                           "model": "mock", "usage": {}, "offline_skipped": False}
        # GT 含 t1 标签 + t3 第 1 项标签 → 命中 2 个 unique
        gt = {"JZ0001": {"跨部门协调", "智能制造潜质"}}
        emps = [_make_emp("JZ0001")]
        corpus = load_label_corpus()
        with patch.object(exp.ProfileGeneration, "_llm_extract",
                          return_value=extract_with_t3):
            summary = exp.run_experiment(emps, gt, corpus)

        pc = summary["path_c"]
        emp = summary["per_employee"][0]

        # a. path_c total = t1(1)+t2(1)+t3(2) = 4 → t3 项真进了 rerank 循环
        # （若 t3 未被 pairs/rerank_items 处理，total 会停在 2）
        assert pc["total_mappings"] == 4, (
            f"t3 项未进入 rerank 循环: expected 4, got {pc['total_mappings']}")
        # mock rerank 返回 standard_label，4 项都被 cross-encoder 处理
        assert pc["cross_encoder_actual_calls"] == 4
        # b. emp_result.t3_count = 2（content_audit 真读 t3_labels 数组）
        assert emp["t3_count"] == 2, (
            f"t3_count 未正确读取: expected 2, got {emp['t3_count']}")
        # c. T3 命中：跨部门协调(t1) + 智能制造潜质(t3) → path_c recall_at_gt = 2
        assert pc["recall_at_gt"] == 2, (
            f"T3 命中未计入 path_c recall_at_gt: expected 2, "
            f"got {pc['recall_at_gt']}")
        # d. total_gt_labels 含 T3 标签（GT 总标签数 = 2）
        assert pc["total_gt_labels"] == 2, (
            f"total_gt_labels 不含 T3 标签: expected 2, "
            f"got {pc['total_gt_labels']}")
        # final_correct = 2（t1 + t3 第 1 项在 GT；t2 + t3 第 2 项不在）
        assert pc["final_correct"] == 2
        # 防假绿：per_employee.path_c 真含 4 项（rerank 真跑过 t3 concept）
        assert len(emp["path_c"]) == 4
        # path_c 内含 T3 concept（验证 concept 真被回查）
        t3_concepts_in_path_c = {item["concept"] for item in emp["path_c"]}
        assert "对智能制造技术有好奇心" in t3_concepts_in_path_c
        assert "乐于指导新人" in t3_concepts_in_path_c

    def test_t3_labels_recall_at_gt_delta(self):
        """Step 1.9a：对比有/无 t3 的 path_c recall_at_gt——加 T3 命中标签后 recall 提升。

        场景：GT={t1_label, t3_label}（2 标签）
        - 无 t3：path_c 命中 1（仅 t1_label）→ recall_at_gt=1/2=50%
        - 有 t3：path_c 命中 2（t1_label + t3_label）→ recall_at_gt=2/2=100%
        防假绿：构造两个 content，断言 recall_at_gt 真因 T3 增加而提升。
        """
        # 无 t3 版本
        content_no_t3 = {
            "t1_professional": [
                {"concept": "跨部门沟通顺畅", "standard_label": "跨部门协调",
                 "category": "behavior", "confidence": 0.9},
            ],
            "t2_behavioral": [], "big_five": {}, "t3_raw": {},
        }
        # 有 t3 版本（t3 项命中 GT 第 2 个标签）
        content_with_t3 = dict(content_no_t3)
        content_with_t3["t3_labels"] = [
            {"concept": "对智能制造技术有好奇心", "standard_label": "智能制造潜质",
             "category": "potential", "confidence": 0.7,
             "evidence": [{"source": "360评价_2024", "text_snippet": "对新技术有兴趣"}]},
        ]
        gt = {"JZ0001": {"跨部门协调", "智能制造潜质"}}
        emps = [_make_emp("JZ0001")]
        corpus = load_label_corpus()

        results = {}
        for label, content in (("no_t3", content_no_t3), ("with_t3", content_with_t3)):
            extract = {"content": content, "error": None,
                       "model": "mock", "usage": {}, "offline_skipped": False}
            with patch.object(exp.ProfileGeneration, "_llm_extract",
                              return_value=extract):
                summary = exp.run_experiment(emps, gt, corpus)
            results[label] = summary["path_c"]

        # 无 t3：1 项命中（t1）→ recall_at_gt=1
        assert results["no_t3"]["recall_at_gt"] == 1, (
            f"baseline recall_at_gt 错误: expected 1, "
            f"got {results['no_t3']['recall_at_gt']}")
        # 有 t3：2 项命中（t1 + t3）→ recall_at_gt=2
        assert results["with_t3"]["recall_at_gt"] == 2, (
            f"T3 命中未提升 recall_at_gt: expected 2, "
            f"got {results['with_t3']['recall_at_gt']}")
        # 分母不变（GT 标签数相同）
        assert results["no_t3"]["total_gt_labels"] == 2
        assert results["with_t3"]["total_gt_labels"] == 2

    def test_path_c_counts_rerank_results(self):
        """Path C：mock rerank 返回命中 GT 的 matched_label → final_correct 计数。"""
        gt = {"JZ0001": {"跨部门协调"}}
        emps = [_make_emp("JZ0001")]
        corpus = load_label_corpus()
        with patch.object(exp.ProfileGeneration, "_llm_extract",
                          return_value=_MOCK_EXTRACT):
            summary = exp.run_experiment(emps, gt, corpus)
        pc = summary["path_c"]
        # _MOCK_CONTENT 有 2 个 t1 项 → path_c_total=2
        assert pc["total_mappings"] == 2
        assert pc["rerank_calls"] == 1
        # mock rerank 返回 standard_label，跨部门协调 in GT → 1 命中
        # Java开发 不在 GT → 0 命中
        assert pc["final_correct"] == 1
        assert pc["new_labels"] == 0
        assert pc["rerank_failures"] == 0
        # Path C 用 cross-encoder（BGE-reranker-v2-m3），mock 返回 cross_encoder_rerank source
        # → cross_encoder_actual_calls = 2（两项都被 cross-encoder 处理）
        # llm_rerank_actual_calls = 0（Path C 不走 LLM 重排，除非 BGE 降级）
        # rerank_calls=1 是入口计数，cross_encoder_actual_calls=2 是项级真实打分数
        assert pc["cross_encoder_actual_calls"] == 2
        assert pc["llm_rerank_actual_calls"] == 0

    def test_path_c_llm_adjudication_routing(self):
        """B3 统计扩展：S1 终裁 source 计数 + A9 分流修复。

        mock rerank 返回 2 项 cross_new_llm_confirmed + 1 项 cross_new_llm_rejected：
        a. summary.path_c 三新 key 正确计数（confirmed=2 / rejected=1 / calls=3）
        b. 负向（A9）：llm_rerank_actual_calls==0（纯 LLM 通道不被终裁产物污染）、
           cross_encoder_actual_calls==0（三口径互斥）
        c. per-employee 双级对称：emp 与 summary["path_c"] 同名 key 数值一致
        d. 既有 key 语义零变化：new_labels==0（rejected 不并入 new_labels）
        """
        content_adj = {
            "t1_professional": [
                {"concept": "数据分析", "standard_label": "数据分析",
                 "category": "skill", "confidence": 0.9},
                {"concept": "质量体系管理", "standard_label": "质量工程",
                 "category": "skill", "confidence": 0.8},
                {"concept": "跨部门沟通顺畅", "standard_label": "跨部门协调",
                 "category": "behavior", "confidence": 0.7},
            ],
            "t2_behavioral": [], "big_five": {}, "t3_raw": {},
        }
        extract_adj = {"content": content_adj, "error": None,
                       "model": "mock", "usage": {}, "offline_skipped": False}
        gt = {"JZ0001": {"数据分析"}}
        emps = [_make_emp("JZ0001")]
        corpus = load_label_corpus()

        def fake_adj_rerank(items, emp, corpus_, **kw):
            sources = ["cross_new_llm_confirmed", "cross_new_llm_confirmed",
                       "cross_new_llm_rejected"]
            return [{
                "idx": it.get("idx", i),
                "matched_label": it.get("standard_label", ""),
                "is_new_label": src == "cross_new_llm_rejected",
                "match_confidence": 0.6,
                "rationale": "LLM复核",
                "candidates_seen": it.get("candidates", []),
                "mapping_source": src,
            } for i, (it, src) in enumerate(zip(items, sources))]

        with patch.object(exp.ProfileGeneration, "_llm_extract",
                          return_value=extract_adj), \
             patch("scripts.experiment_embedding_vs_llm.rerank_cross_encoder",
                   side_effect=fake_adj_rerank):
            summary = exp.run_experiment(emps, gt, corpus)

        pc = summary["path_c"]
        emp = summary["per_employee"][0]
        # a. 新计数 key
        assert pc["total_mappings"] == 3
        assert pc["cross_new_llm_confirmed"] == 2
        assert pc["cross_new_llm_rejected"] == 1
        assert pc["llm_adjudication_calls"] == 3  # = confirmed + rejected
        # b. 负向：三口径互斥，终裁产物不污染纯 LLM 通道 / cross-encoder 计数
        assert pc["llm_rerank_actual_calls"] == 0
        assert pc["cross_encoder_actual_calls"] == 0
        # c. per-employee 双级对称（同名 key）
        assert emp["cross_new_llm_confirmed"] == 2
        assert emp["cross_new_llm_rejected"] == 1
        # d. 既有 key 语义零变化：new_labels 不含终裁产物
        assert pc["new_labels"] == 0

    def test_recall_at_gt_fair_metric(self):
        """recall@GT 公平口径：分母=GT 总标签数（非总映射数）。
        场景：1 员工 GT={跨部门协调,团队管理,智能制造}（3标签），LLM 提议 2 项
        命中 1 个 unique GT 标签（跨部门协调）→ recall@GT=1/3≈33.3%。"""
        gt = {"JZ0001": {"跨部门协调", "团队管理", "智能制造"}}
        emps = [_make_emp("JZ0001")]
        corpus = load_label_corpus()
        with patch.object(exp.ProfileGeneration, "_llm_extract",
                          return_value=_MOCK_EXTRACT):
            summary = exp.run_experiment(emps, gt, corpus)
        pa = summary["path_a"]
        pc = summary["path_c"]
        # GT 总标签数（跨员工求和）= 3
        assert pa["total_gt_labels"] == 3
        assert pc["total_gt_labels"] == 3
        # Path A: 跨部门协调命中（verified in GT）→ recall_at_gt=1
        # Java开发 corrected_wrong 不在 GT → 不命中
        assert pa["recall_at_gt"] == 1
        assert pa["recall_at_gt_pct"] == 33.3
        # Path C: mock rerank 返回 standard_label，跨部门协调命中 → recall_at_gt=1
        assert pc["recall_at_gt"] == 1
        assert pc["recall_at_gt_pct"] == 33.3

    def test_path_b_top_k_handles_empty_concept(self):
        corpus = load_label_corpus()
        # 空 concept → 空列表，不崩
        assert exp.path_b_top_k("", corpus) == []
        assert exp.path_b_top_k("Java微服务后端", []) == []

    def test_offline_skipped_does_not_count_llm_call(self):
        # offline _llm_extract 返回 offline_skipped=True → 不计 attempts/failures
        offline_extract = {
            "content": exp.ProfileGeneration._empty_extract(),
            "error": None, "model": "offline-placeholder",
            "usage": {}, "offline_skipped": True,
        }
        gt = {"JZ0001": set()}
        emps = [_make_emp("JZ0001")]
        corpus = load_label_corpus()
        with patch.object(exp.ProfileGeneration, "_llm_extract",
                          return_value=offline_extract):
            summary = exp.run_experiment(emps, gt, corpus)
        assert summary["llm_call_attempts"] == 0
        assert summary["llm_call_failures"] == 0
        assert summary["path_a"]["total_mappings"] == 0  # 空提取 → 无标签可映射

    def test_all_llm_failures_mark_invalid_not_plan_b(self):
        # V5: 全 LLM 失败（超时/网络）→ 实验无效，不触发 Plan B（infra 失败 ≠ 质量信号）
        timeout_extract = {
            "content": None, "error": "Request timed out.",
            "model": "", "usage": {}, "offline_skipped": False,
        }
        gt = {"JZ0001": {"跨部门协调"}, "JZ0003": {"智能制造"}}
        emps = [_make_emp("JZ0001"), _make_emp("JZ0003")]
        corpus = load_label_corpus()
        with patch.object(exp.ProfileGeneration, "_llm_extract",
                          return_value=timeout_extract):
            summary = exp.run_experiment(emps, gt, corpus)
        # 审计完整：2 次尝试，2 次失败，0 成功
        assert summary["llm_call_attempts"] == 2
        assert summary["llm_call_failures"] == 2
        assert summary["llm_calls"] == 0  # 成功数（向后兼容字段）
        assert summary["valid_run"] is False
        assert summary["plan_b_triggered"] is False  # 关键：不误触 Plan B
        assert "INVALID" in summary["decision"]
        assert "勿据此" in summary["decision"] or "重跑" in summary["decision"]

    def test_partial_llm_failures_still_evaluate(self):
        # 部分失败（1 成功 1 超时）→ 仍按成功部分评估，valid_run=True
        success_extract = {
            "content": {
                "t1_professional": [
                    {"concept": "跨部门沟通顺畅", "standard_label": "跨部门协调", "category": "behavior"},
                ],
                "t2_behavioral": [], "big_five": {}, "t3_raw": {},
            },
            "error": None, "model": "mock", "usage": {}, "offline_skipped": False,
        }
        timeout_extract = {
            "content": None, "error": "Request timed out.",
            "model": "", "usage": {}, "offline_skipped": False,
        }
        gt = {"JZ0001": {"跨部门协调"}, "JZ0003": set()}
        emps = [_make_emp("JZ0001"), _make_emp("JZ0003")]
        corpus = load_label_corpus()
        extract_iter = iter([success_extract, timeout_extract])
        with patch.object(exp.ProfileGeneration, "_llm_extract",
                          side_effect=lambda *a, **k: next(extract_iter)):
            summary = exp.run_experiment(emps, gt, corpus)
        assert summary["llm_call_attempts"] == 2
        assert summary["llm_call_failures"] == 1
        assert summary["llm_calls"] == 1  # 1 成功
        assert summary["valid_run"] is True
        # 成功的那员工有 path_a 数据
        assert summary["path_a"]["total_mappings"] == 1

    def test_error_path_per_employee_key_symmetry(self):
        """C1/E: error 路径 per_employee 项 key 集合必须与成功路径一致。

        对抗审查发现：error 路径曾只有 {employee_id, error, model}，缺成功路径 9 个 key
        （usage/content_keys/t1/t2/t3_count/ground_truth_count/path_a/b/c）。下游迭代
        per_employee 读任一 key 时遇 error 员工直接 KeyError。test_all_llm_failures /
        test_partial 只查 summary 顶层不查 per_employee 结构 → C1 违规潜伏。
        """
        timeout_extract = {
            "content": None, "error": "Request timed out.",
            "model": "", "usage": {}, "offline_skipped": False,
        }
        gt = {"JZ0001": {"跨部门协调", "智能制造"}}  # GT 2 标签 → ground_truth_count 应=2
        emps = [_make_emp("JZ0001")]
        corpus = load_label_corpus()
        with patch.object(exp.ProfileGeneration, "_llm_extract",
                          return_value=timeout_extract):
            summary = exp.run_experiment(emps, gt, corpus)
        emp = summary["per_employee"][0]
        # error 路径必须含成功路径的全部 key（C1 对称）
        expected_keys = {
            "employee_id", "error", "model", "usage", "content_keys",
            "t1_count", "t2_count", "t3_count", "ground_truth_count",
            "path_a", "path_b", "path_c",
            # B3 统计扩展：S1 终裁 per-employee 计数（error 路径对称为 0）
            "cross_new_llm_confirmed", "cross_new_llm_rejected",
        }
        assert set(emp.keys()) == expected_keys, (
            f"error 路径 per_employee key 不对称: missing={expected_keys - set(emp.keys())}, "
            f"extra={set(emp.keys()) - expected_keys}")
        # 失败员工无映射数据：各 count=0、各 path=[]、ground_truth_count=GT 数
        assert emp["error"] == "Request timed out."
        assert emp["t1_count"] == 0
        assert emp["t2_count"] == 0
        assert emp["t3_count"] == 0
        assert emp["ground_truth_count"] == 2  # GT 2 标签
        assert emp["path_a"] == []
        assert emp["path_b"] == []
        assert emp["path_c"] == []
        assert emp["content_keys"] == {}
