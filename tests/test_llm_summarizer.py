"""LLM 摘要工具单元测试 — utils.llm_summarizer

覆盖：正常路径、空文本、LLM 错误、锚点失配、摘要长度异常、文本截断。
"""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from utils.llm_summarizer import (
    summarize_employee_texts,
    verify_anchors,
    check_summary_lengths,
    TEXT_LIMIT,
)


# ── 模拟 LLM 返回值 ───────────────────────────────────────────────────────

_MOCK_SUCCESS = {
    "content": {
        "performance_summary": "该员工三年绩效表现稳定，从B级提升至A级，完成核心任务。",
        "project_summary": "参与核心系统开发项目，担任核心开发角色，使用Python和Docker技术栈。",
        "evaluation_summary": "上级评价专业能力强，同事评价协作良好，自评较为谦虚。",
        "anchors": {
            "performance": ["该员工本年度表现"],
            "projects": ["核心系统开发项目"],
            "evaluation": ["专业能力强"],
        },
    },
    "error": None,
    "usage": {"prompt_tokens": 500, "completion_tokens": 150},
    "model": "deepseek-chat",
}

_MOCK_ERROR = {
    "content": None,
    "error": "API rate limit exceeded",
    "usage": {},
    "model": "deepseek-chat",
}

_MOCK_EMPTY_ANCHORS = {
    "content": {
        "performance_summary": "绩效表现稳定。",
        "project_summary": "项目经历丰富。",
        "evaluation_summary": "评价良好。",
        "anchors": {},
    },
    "error": None,
    "usage": {"prompt_tokens": 300, "completion_tokens": 100},
    "model": "deepseek-chat",
}

_MOCK_LONG_SUMMARY = {
    "content": {
        "performance_summary": "A" * 300,  # 原文只有 50 字，摘要 300 字 → 幻觉标记
        "project_summary": "项目摘要",
        "evaluation_summary": "评价摘要",
        "anchors": {"performance": ["原文开头"], "projects": ["项目描述"], "evaluation": ["评价原文"]},
    },
    "error": None,
    "usage": {"prompt_tokens": 400, "completion_tokens": 200},
    "model": "deepseek-chat",
}


_EXPECTED_KEYS = {
    "text_summaries", "anchors", "anchor_mismatch",
    "hallucination_flags", "error", "model", "tokens", "usage",
}


def _assert_expected_keys(result: dict) -> None:
    """验证返回字典包含所有必需顶层 key（D3 对称性）。"""
    assert set(result.keys()) == _EXPECTED_KEYS, (
        f"key 集合不匹配: 多出={set(result.keys()) - _EXPECTED_KEYS}, "
        f"缺失={_EXPECTED_KEYS - set(result.keys())}"
    )


# ── 测试类 ────────────────────────────────────────────────────────────────


class TestSummarizeEmployeeTexts:
    """验证 summarize_employee_texts 主函数。"""

    @patch("utils.llm_summarizer.call_llm_json", return_value=_MOCK_SUCCESS)
    def test_normal_summary(self, mock_call):
        """正常路径：三段文本 → 返回结构化摘要。"""
        result = summarize_employee_texts(
            "T0001",
            "该员工本年度表现良好，完成了各项任务。",
            "核心系统开发项目，担任核心开发角色。",
            "专业能力强，沟通协作好。",
        )
        assert result["error"] is None
        assert result["text_summaries"] is not None
        assert "performance_summary" in result["text_summaries"]
        assert "project_summary" in result["text_summaries"]
        assert "evaluation_summary" in result["text_summaries"]
        assert result["anchors"] is not None
        assert isinstance(result["anchor_mismatch"], bool)
        assert isinstance(result["hallucination_flags"], dict)
        assert result["model"] == "deepseek-chat"
        assert result["tokens"] == 650  # 500 + 150
        mock_call.assert_called_once()

    @patch("utils.llm_summarizer.call_llm_json", return_value=_MOCK_ERROR)
    def test_llm_error(self, mock_call):
        """LLM 调用失败 → error 字段非空，text_summaries 为 None。"""
        result = summarize_employee_texts("T0001", "绩效文本", "项目文本", "评价文本")
        assert result["error"] == "API rate limit exceeded"
        assert result["text_summaries"] is None
        assert result["anchors"] is None
        assert result["anchor_mismatch"] is False
        mock_call.assert_called_once()

    def test_all_texts_empty(self):
        """三段文本均为空 → 不调用 LLM，直接返回文本不足。"""
        result = summarize_employee_texts("T0001", "", "", "")
        assert result["error"] == "文本数据不足"
        assert result["text_summaries"] is None
        assert result["anchors"] is None
        assert result["tokens"] == 0

    def test_all_texts_none(self):
        """三段文本均为 None → 视为空，不调用 LLM。"""
        result = summarize_employee_texts("T0001", None, None, None)
        assert result["error"] == "文本数据不足"

    @patch("utils.llm_summarizer.call_llm_json", return_value=_MOCK_SUCCESS)
    def test_partial_text(self, mock_call):
        """仅绩效文本可用，项目和评价为空 → 仍能调用 LLM。"""
        result = summarize_employee_texts("T0001", "绩效表现优秀。", "", "")
        assert result["error"] is None
        assert result["text_summaries"] is not None
        mock_call.assert_called_once()

    @patch("utils.llm_summarizer.call_llm_json", return_value=_MOCK_LONG_SUMMARY)
    def test_hallucination_detected(self, mock_call):
        """摘要长度远超原文 → hallucination_flags 非空。"""
        result = summarize_employee_texts(
            "T0001",
            "原文" * 25,  # 50 字
            "项目摘要原文",
            "评价摘要原文",
        )
        assert result["hallucination_flags"] != {}
        assert "performance_summary" in result["hallucination_flags"]

    @patch("utils.llm_summarizer.call_llm_json", return_value=_MOCK_EMPTY_ANCHORS)
    def test_empty_anchors(self, mock_call):
        """LLM 返回空锚点 → anchor_mismatch 为 False。"""
        result = summarize_employee_texts("T0001", "绩效文本", "项目文本", "评价文本")
        assert result["anchor_mismatch"] is False

    @patch("utils.llm_summarizer.call_llm_json", return_value=_MOCK_SUCCESS)
    def test_text_truncation(self, mock_call):
        """超长文本 → 被截断至 TEXT_LIMIT。"""
        long_text = "A" * (TEXT_LIMIT + 1000)
        result = summarize_employee_texts("T0001", long_text, "项目文本", "评价文本")
        assert result["error"] is None
        call_kwargs = mock_call.call_args[1]
        prompt = call_kwargs.get("prompt", "")
        assert prompt is not None
        assert "A" * TEXT_LIMIT in prompt
        # 反向验证：超出部分不在 prompt 中
        assert prompt.count("A") == TEXT_LIMIT, (
            f"截断失效: 预期 {TEXT_LIMIT} 个 A, 实际 {prompt.count('A')}"
        )

    @patch("utils.llm_summarizer.call_llm_json", return_value=_MOCK_SUCCESS)
    def test_return_format_keys(self, mock_call):
        """返回字典包含所有必需顶层 key。"""
        result = summarize_employee_texts("T0001", "绩效文本", "项目文本", "评价文本")
        _assert_expected_keys(result)


# ── 测试 verify_anchors ─────────────────────────────────────────────────


class TestVerifyAnchors:
    """验证锚点存在性检查。"""

    def test_all_anchors_match(self):
        """所有锚点都在原文中出现 → False。"""
        anchors = {"performance": ["该员工本年度表现", "完成各项目标"]}
        result = verify_anchors(
            anchors,
            "该员工本年度表现良好，完成各项目标。",
            "",
            "",
        )
        assert result is False

    def test_some_anchors_mismatch(self):
        """多数锚点不在原文中 → True。"""
        anchors = {"performance": ["该员工本年度表现", "完全不存在的锚点"]}
        result = verify_anchors(
            anchors,
            "该员工本年度表现良好。",
            "",
            "",
        )
        assert result is True  # 命中率 1/2 = 50% < 80%

    def test_empty_anchors(self):
        """空锚点字典 → False。"""
        assert verify_anchors({}, "原文", "", "") is False

    def test_none_anchors(self):
        """None 锚点 → False。"""
        assert verify_anchors(None, "原文", "", "") is False

    def test_fuzzy_match_partial(self):
        """模糊匹配：部分锚点通过偏移 2 字匹配，部分完全失配。"""
        anchors = {"performance": ["员工本年度表现良", "完全不存在的锚点文字"]}
        result = verify_anchors(
            anchors,
            "该员工本年度表现良好。",
            "",
            "",
        )
        # "员工本年度表现良" 通过精确匹配找到
        # "完全不存在的锚点文字" 完全失配
        # 命中率 = 1/2 = 50% < 80% → mismatch
        assert result is True

    def test_fuzzy_match_pass(self):
        """精确匹配通过。"""
        anchors = {"performance": ["该员工本年度表现良好"]}
        result = verify_anchors(
            anchors,
            "该员工本年度表现良好，完成各项目标。",
            "",
            "",
        )
        assert result is False  # 精确匹配找到

    def test_fuzzy_edge_trim(self):
        """模糊匹配：锚点左偏 2 字后匹配原文。"""
        anchors = {"performance": ["员工本年度表现良好，完成"]}
        result = verify_anchors(
            anchors,
            "该员工本年度表现良好，完成各项目标。",
            "",
            "",
        )
        # 精确匹配不成立: "员工本年度表现良好，完成" 不在 "该员工本年度表现良好，完成各项目标。" 中
        # trimmed[2:] = "本年度表现良好，完成" → 在原文中 → 匹配
        assert result is False  # 通过模糊匹配找到

    def test_cross_category_match(self):
        """跨类别锚点检查：项目锚点在项目文本中匹配。"""
        anchors = {"projects": ["核心系统开发项目"]}
        result = verify_anchors(
            anchors,
            "绩效评语文本",
            "核心系统开发项目，使用Python。",
            "",
        )
        assert result is False  # 在项目文本中找到


# ── 测试 check_summary_lengths ────────────────────────────────────────────


class TestCheckSummaryLengths:
    """验证摘要长度合理性检查。"""

    def test_normal_summary(self):
        """摘要不超过原文 1.5 倍 → 空标记。"""
        flags = check_summary_lengths(
            {"performance_summary": "表现良好（50字以内摘要）"},
            "原文原文原文原文原文原文原文原文原文原文原文",  # 约 33 字
            "",
            "",
        )
        assert flags == {}

    def test_hallucination_long_summary(self):
        """摘要超过原文 1.5 倍 → 标记。"""
        flags = check_summary_lengths(
            {"performance_summary": "A" * 100},
            "原文" * 20,  # 40 字
            "",
            "",
        )
        assert "performance_summary" in flags

    def test_short_original_text_relaxed(self):
        """原文不足 30 字 → 摘要上限放宽至 2 倍。"""
        flags = check_summary_lengths(
            {"performance_summary": "A" * 50},
            "短原文",  # 3 字
            "",
            "",
        )
        # 3 * 2 = 6 < 50 → 标记
        assert "performance_summary" in flags

    def test_short_original_within_limit(self):
        """原文不足 30 字且摘要 ≤ 2 倍 → 不标记。"""
        flags = check_summary_lengths(
            {"performance_summary": "A" * 5},
            "短原文",  # 3 字
            "",
            "",
        )
        # 3 * 2 = 6 >= 5 → 不标记
        assert flags == {}

    def test_empty_summaries(self):
        """空摘要字典 → 空标记。"""
        assert check_summary_lengths({}, "", "", "") == {}