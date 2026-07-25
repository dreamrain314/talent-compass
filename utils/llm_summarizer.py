"""LLM 文本摘要工具 — 非结构化文本语义理解

提供与 DataUnderstanding._summarize_employee 相同的 LLM 调用逻辑，
但作为独立模块可直接被 Streamlit UI Step 4 调用，避免 D2 重复定义。

用法:
    from utils.llm_summarizer import summarize_employee_texts
    result = summarize_employee_texts("T0001", perf_text, proj_text, eval_text)
    if result.get("error") is None:
        summaries = result["text_summaries"]
        anchors = result["anchors"]
"""
from __future__ import annotations

import logging
import re
from typing import Any

from utils.llm_client import call_llm_json
from config import (
    is_offline_mode,
    PLACEHOLDER_SUMMARY_LEN,
    PLACEHOLDER_ANCHOR_LEN,
)

logger = logging.getLogger(__name__)

# ── 常量 ───────────────────────────────────────────────────────────────────
# 单段文本最大字符数（防止超长文本超出 token 限制）
TEXT_LIMIT = 6000
# LLM 最大输出 token
MAX_TOKENS = 4096

# ── 公共函数 ───────────────────────────────────────────────────────────────


def summarize_employee_texts(
    emp_id: str,
    perf_text: str,
    proj_text: str,
    eval_text: str,
) -> dict[str, Any]:
    """对单员工调用 LLM 生成结构化摘要。

    与原 DataUnderstanding._summarize_employee 功能一致，
    但返回格式更便于 UI 直接消费：
        {
            "text_summaries": { ... },
            "anchors": { ... },
            "anchor_mismatch": bool,
            "hallucination_flags": dict,
            "error": str | None,
            "model": str,
            "tokens": int,
        }

    Args:
        emp_id: 员工 ID（仅用于 LLM 提示中的标识）。
        perf_text: 绩效评语文本（将被截断至 TEXT_LIMIT 字符）。
        proj_text: 项目描述文本（将被截断至 TEXT_LIMIT 字符）。
        eval_text: 360 评价文本（将被截断至 TEXT_LIMIT 字符）。

    Returns:
        结构化摘要字典，error 不为 None 表示调用失败。
    """
    # 截断长文本
    perf_text = perf_text[:TEXT_LIMIT] if perf_text else ""
    proj_text = proj_text[:TEXT_LIMIT] if proj_text else ""
    eval_text = eval_text[:TEXT_LIMIT] if eval_text else ""

    # 三段文本都为空 → 直接返回，不调用 LLM
    if not perf_text and not proj_text and not eval_text:
        return {
            "text_summaries": None,
            "anchors": None,
            "anchor_mismatch": False,
            "hallucination_flags": {},
            "error": "文本数据不足",
            "model": "",
            "usage": {},
            "tokens": 0,
        }

    # ── 离线模式：跳过真实 API，从原文确定性派生摘要与锚点 ──
    # 用于无 API Key 或真实 API 截断/限流时绕过雪崩，验证编排逻辑。
    if is_offline_mode():
        return _derive_placeholder_summary(
            emp_id, perf_text, proj_text, eval_text, source="offline-placeholder"
        )

    system_prompt = (
        "你是一个HR数据分析助手。你的任务是将人事文本数据转化为标准化的结构化摘要。"
        "严格基于原文，不添加原文中没有的信息。不做推断、不评价。"
    )

    user_prompt = f"""员工ID: {emp_id}

绩效评语:
{perf_text}

项目描述:
{proj_text}

360评价:
{eval_text}

请生成以下JSON（严格按此格式，不要添加额外字段）：
{{
    "performance_summary": "综合三年绩效的客观摘要（≤200字）",
    "project_summary": "项目经历的核心产出和角色概括（≤200字）",
    "evaluation_summary": "360评价的综合概述（≤200字）",
    "anchors": {{
        "performance": ["绩效评语开头10字", ...],
        "projects": ["项目描述开头10字", ...],
        "evaluation": ["评价开头10字", ...]
    }}
}}"""

    result = call_llm_json(
        prompt=user_prompt,
        system_prompt=system_prompt,
        temperature=0.0,
        max_tokens=MAX_TOKENS,
    )

    # ── 降级回路：call_llm_json 因空内容/JSON 解析失败 → 从原文派生占位符 ──
    # 🔴 不再调第 2 次 LLM（原 _fallback_text_summary）：真实 API 截断时
    # 第 2 次调用同样会截断，且每失败 1 人触发指数退避（2s→4s→6s…），
    # 10 人即超 120s。改为确定性占位符 → error=None → 无退避雪崩。
    # API 认证/限流/网络错误（非解析类）仍返回 error，由调用方退避。
    if result.get("error"):
        err = result["error"]
        parse_failure = ("empty content" in err or "JSON parse" in err
                          or "Expecting value" in err)
        if parse_failure:
            logger.warning(
                "call_llm_json 解析失败 (%s)，从原文派生占位符（不再调第 2 次 LLM）", err
            )
            return _derive_placeholder_summary(
                emp_id, perf_text, proj_text, eval_text, source="degraded-placeholder"
            )
        return {
            "text_summaries": None,
            "anchors": None,
            "anchor_mismatch": False,
            "hallucination_flags": {},
            "error": result["error"],
            "model": result.get("model", ""),
            "usage": result.get("usage", {}) or {},
            "tokens": _sum_tokens(result),
        }

    content = result.get("content")
    if not isinstance(content, dict):
        if content is None:
            content = {}
        else:
            return {
                "text_summaries": None,
                "anchors": None,
                "anchor_mismatch": False,
                "hallucination_flags": {},
                "error": f"LLM 返回了非 dict 结构: {type(content).__name__}",
                "model": result.get("model", ""),
                "usage": result.get("usage", {}) or {},
                "tokens": _sum_tokens(result),
            }
    summaries = {
        "performance_summary": content.get("performance_summary", ""),
        "project_summary": content.get("project_summary", ""),
        "evaluation_summary": content.get("evaluation_summary", ""),
    }
    anchors = content.get("anchors", {})

    # 锚点验证 + 长度检查
    anchor_mismatch = verify_anchors(anchors, perf_text, proj_text, eval_text)
    hallucination_flags = check_summary_lengths(summaries, perf_text, proj_text, eval_text)

    return {
        "text_summaries": summaries,
        "anchors": anchors,
        "anchor_mismatch": anchor_mismatch,
        "hallucination_flags": hallucination_flags,
        "error": None,
        "model": result.get("model", ""),
        "usage": result.get("usage", {}) or {},
        "tokens": _sum_tokens(result),
    }


def _derive_placeholder_summary(
    emp_id: str,
    perf_text: str,
    proj_text: str,
    eval_text: str,
    source: str = "placeholder",
) -> dict[str, Any]:
    """从原文确定性派生摘要与锚点（不调用 LLM）。

    用于：① offline 模式（TC_OFFLINE=1）；② live 路径 call_llm_json
    解析失败时降级（替代原 _fallback_text_summary 的第 2 次 LLM 调用）。

    策略：摘要 = 原文前 PLACEHOLDER_SUMMARY_LEN 字，锚点 = 原文前
    PLACEHOLDER_ANCHOR_LEN 字。两者均为原文精确子串 → 锚点命中率 100%、
    摘要长度 ≤ 原文长度（不会触发幻觉标记）。空字段 → 空字符串、无锚点。
    """
    summaries = {
        "performance_summary": (perf_text or "")[:PLACEHOLDER_SUMMARY_LEN],
        "project_summary": (proj_text or "")[:PLACEHOLDER_SUMMARY_LEN],
        "evaluation_summary": (eval_text or "")[:PLACEHOLDER_SUMMARY_LEN],
    }
    anchors: dict[str, list[str]] = {}
    if perf_text:
        anchors["performance"] = [perf_text[:PLACEHOLDER_ANCHOR_LEN]]
    if proj_text:
        anchors["projects"] = [proj_text[:PLACEHOLDER_ANCHOR_LEN]]
    if eval_text:
        anchors["evaluation"] = [eval_text[:PLACEHOLDER_ANCHOR_LEN]]

    anchor_mismatch = verify_anchors(anchors, perf_text, proj_text, eval_text)
    hallucination_flags = check_summary_lengths(summaries, perf_text, proj_text, eval_text)

    return {
        "text_summaries": summaries,
        "anchors": anchors,
        "anchor_mismatch": anchor_mismatch,
        "hallucination_flags": hallucination_flags,
        "error": None,
        "model": source,
        "usage": {},
        "tokens": 0,
    }


# ── 锚点存在性验证 ────────────────────────────────────────────────────────


def verify_anchors(
    anchors: dict,
    perf_text: str,
    proj_text: str,
    eval_text: str,
) -> bool:
    """验证锚点是否在原文中出现。命中率 < 80% → 返回 True (有 mismatch)。

    从 DataUnderstanding._verify_anchors 提取的独立函数。
    """
    if not anchors:
        return False

    text_map = {"performance": perf_text, "projects": proj_text, "evaluation": eval_text}
    total = 0
    hits = 0

    for key, anchor_list in anchors.items():
        if not isinstance(anchor_list, list):
            continue
        source_text = text_map.get(key, "")
        for anchor in anchor_list:
            if not isinstance(anchor, str) or not anchor.strip():
                continue
            total += 1
            trimmed = anchor.strip()
            if not trimmed:
                continue
            if trimmed in source_text:
                hits += 1
            elif len(trimmed) > 4 and trimmed[2:] in source_text:
                hits += 1
            elif len(trimmed) > 4 and trimmed[:-2] in source_text:
                hits += 1
            elif len(trimmed) > 4 and trimmed[1:-1] in source_text:
                hits += 1

    if total == 0:
        return False
    hit_rate = hits / total
    return hit_rate < 0.8  # True = 存在 mismatch


# ── 摘要长度合理性检查 ────────────────────────────────────────────────────


def check_summary_lengths(
    summaries: dict,
    perf_text: str,
    proj_text: str,
    eval_text: str,
) -> dict:
    """检查摘要是否显著长于原文。返回异常标记字典。

    从 DataUnderstanding._check_summary_lengths 提取的独立函数。
    """
    if not summaries:
        return {}

    original_lengths = {
        "performance": len(perf_text) if perf_text else 0,
        "projects": len(proj_text) if proj_text else 0,
        "evaluation": len(eval_text) if eval_text else 0,
    }

    summary_to_key = {
        "performance_summary": "performance",
        "project_summary": "projects",
        "evaluation_summary": "evaluation",
    }

    flags = {}
    for summary_key, orig_key in summary_to_key.items():
        summary_text = summaries.get(summary_key, "")
        orig_len = original_lengths.get(orig_key, 0)
        summary_len = len(summary_text) if summary_text else 0

        if orig_len == 0 or summary_len == 0:
            if orig_len == 0 and summary_len > 0:
                flags[summary_key] = "possible_hallucination"
            continue

        if orig_len < 30:
            if summary_len > orig_len * 2:
                flags[summary_key] = "possible_hallucination"
        elif summary_len > orig_len * 1.5:
            flags[summary_key] = "possible_hallucination"

    return flags


# ── 内部辅助 ──────────────────────────────────────────────────────────────


def _sum_tokens(result: dict) -> int:
    """从 call_llm_json 返回结果中提取 token 总数。"""
    usage = result.get("usage", {}) or {}
    return int(usage.get("prompt_tokens", 0) or 0) + int(usage.get("completion_tokens", 0) or 0)