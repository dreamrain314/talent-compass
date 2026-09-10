"""utils.llm_client 单元测试 — _try_parse_json / _repair_truncated_json

覆盖：完整 JSON、markdown 代码块、finish_reason=length 截断（字符串值
从中间切断，闭引号缺失）、纯截断字符串值、数字/布尔/null/数组值。
"""
from __future__ import annotations

import pytest

from utils.llm_client import _try_parse_json, _repair_truncated_json
from utils import llm_client as lc


# ── _try_parse_json ───────────────────────────────────────────────────────


class TestTryParseJson:
    def test_direct_json(self):
        assert _try_parse_json('{"a": 1, "b": "x"}') == {"a": 1, "b": "x"}

    def test_markdown_code_block_json(self):
        raw = '```json\n{"a": 1}\n```'
        assert _try_parse_json(raw) == {"a": 1}

    def test_markdown_code_block_plain(self):
        raw = '```\n{"a": 2}\n```'
        assert _try_parse_json(raw) == {"a": 2}

    def test_json_embedded_in_text(self):
        raw = '前缀文字 {"a": 3} 后缀文字'
        assert _try_parse_json(raw) == {"a": 3}

    def test_truncated_string_value_recovered(self):
        """finish_reason=length：字符串值被从中间切断（无闭引号）。"""
        raw = '{"performance_summary": "2024年绩效表现稳定，从B级提升至A'
        # 应能恢复 performance_summary 字段（半截字符串）
        result = _try_parse_json(raw)
        assert result is not None
        assert "performance_summary" in result
        assert "B级提升至A" in result["performance_summary"]

    def test_truncated_after_complete_fields(self):
        """前几个字段完整，最后一个字段截断。"""
        raw = '{"performance_summary": "完整摘要", "project_summary": "项目截'
        result = _try_parse_json(raw)
        assert result is not None
        assert result["performance_summary"] == "完整摘要"
        assert "项目截" in result["project_summary"]

    def test_garbage_returns_none(self):
        assert _try_parse_json("不是 JSON 也没有花括号") is None


# ── _repair_truncated_json ────────────────────────────────────────────────


class TestRepairTruncatedJson:
    def test_truncated_string_value(self):
        raw = '{"performance_summary": "该员工表现稳定'
        result = _repair_truncated_json(raw)
        assert result is not None
        assert result["performance_summary"] == "该员工表现稳定"

    def test_mixed_complete_and_truncated(self):
        raw = '{"performance_summary": "完整", "project_summary": "截断的项'
        result = _repair_truncated_json(raw)
        assert result is not None
        assert result["performance_summary"] == "完整"
        assert result["project_summary"] == "截断的项"

    def test_complete_string_not_double_captured(self):
        """完整字符串值不应被截断轮重复捕获为半截。"""
        raw = '{"a": "完整值", "b": "另一个"}'
        result = _repair_truncated_json(raw)
        assert result is not None
        assert result["a"] == "完整值"
        assert result["b"] == "另一个"

    def test_non_string_values(self):
        """数字 / 布尔 / null / 数组值。"""
        raw = '{"count": 42, "flag": true, "miss": null, "tags": ["a", "b"]}'
        result = _repair_truncated_json(raw)
        assert result is not None
        assert result["count"] == 42
        assert result["flag"] is True
        assert result["miss"] is None
        assert result["tags"] == ["a", "b"]

    def test_escaped_quote_in_value(self):
        raw = '{"note": "他说\\"你好\\"后离开"}'
        result = _repair_truncated_json(raw)
        assert result is not None
        assert result["note"] == '他说"你好"后离开'

    def test_empty_content_returns_none(self):
        assert _repair_truncated_json("无 JSON 结构") is None

    def test_truncated_with_escaped_quote(self):
        """截断发生在含转义引号的值中段。"""
        raw = '{"note": "他说\\"你好'
        result = _repair_truncated_json(raw)
        assert result is not None
        # 转义引号后内容被部分恢复
        assert "你好" in result["note"]


# ── TC_LLM_REASONING_EFFORT 门控（GLM-5.3 思考强度 extra_body 注入）──────


class TestReasoningEffortKwargs:
    """call_llm 按模块常量门控：设置 → extra_body 含 thinking enabled +
    reasoning_effort 档位；空串 → extra_body 完全不出现在请求中（其他网关兼容）。"""

    def _capture_create_kwargs(self, monkeypatch, effort):
        """跑一次 call_llm，返回 create() 实收的完整 kwargs。"""
        monkeypatch.setattr(lc, "LLM_REASONING_EFFORT", effort)
        captured = {}

        class _Resp:
            choices = [type("Choice", (), {
                "message": type("Msg", (), {"content": "ok"}),
                "finish_reason": "stop",
            })()]
            model = "fake-model"
            usage = None

        class _Completions:
            def create(self, **kw):
                captured.update(kw)
                return _Resp()

        class _Client:
            chat = type("Chat", (), {"completions": _Completions()})()

        monkeypatch.setattr(lc, "_get_client", lambda: _Client())
        result = lc.call_llm(prompt="p")
        assert result["error"] is None
        return captured

    @pytest.mark.parametrize("effort", ["low", "high"])
    def test_effort_sent_as_extra_body(self, monkeypatch, effort):
        kw = self._capture_create_kwargs(monkeypatch, effort)
        assert kw["extra_body"] == {
            "thinking": {"type": "enabled"},
            "reasoning_effort": effort,
        }

    def test_empty_effort_not_sent(self, monkeypatch):
        # 负向断言：档位为空串时请求中不得出现 extra_body（DeepSeek 官方兼容）
        kw = self._capture_create_kwargs(monkeypatch, "")
        assert "extra_body" not in kw
