"""T3 代理指标确定性打分器。

T3 四项代理指标全部由本模块确定性计算（不调 LLM），分数公式可单元测试、可手动验证。
LLM 只产 t3_raw 原始信号（learning_activities/career_roles/growth_evidence/feedback_signals），
本模块把原始信号映射到 0-100 分。

消费者：agents/profile_generation.py Step C（Phase 1 每员工线程内）。
输入契约见 docs/plan-profile-agent-schema.md 与第二周开发指南 Task 1.4。
"""

from __future__ import annotations

from config import (
    T3_CAREER_DIVERSITY_SCALE,
    T3_CONFIDENCE_BASELINE,
    T3_CONFIDENCE_DEGRADED,
    T3_FEEDBACK_SCALE,
    T3_GROWTH_EVIDENCE_SCALE,
    T3_LEARNING_SPEED_SCALE,
    T3_TRAINING_SCALE,
)

__all__ = ["compute_t3_scores"]


def _filter_nonempty(items) -> list:
    """过滤 None / 空串元素（C3/C4 守卫，防 set() 把 None 当一个角色计入去重）。"""
    if not isinstance(items, list):
        return []
    return [x for x in items if x is not None and x != ""]


def _safe_len(items) -> int:
    """安全长度：非 list 返回 0，过滤 None/空串后计数。"""
    return len(_filter_nonempty(items))


def compute_t3_scores(t3_raw: dict | None, employee: dict) -> dict:
    """计算 T3 四项代理指标分数。

    Args:
        t3_raw: LLM 提取的 T3 原始信号，可能为 None（LLM 截断/解析失败）。
            结构: {"learning_activities": [...], "career_roles": [...],
                   "growth_evidence": [...], "feedback_signals": [...]}
        employee: 员工记录（Agent② 适配后格式），需含 raw.years_of_service 与 training。

    Returns:
        {learning_speed, career_diversity, growth_orientation, growth_signals_360, confidence}
        所有数值为 Python float（非 numpy.float64），json.dumps 安全。
        全空输入 → confidence=T3_CONFIDENCE_DEGRADED + 四项全 0。
        部分空 → 空字段 0 分，非空正常，confidence=T3_CONFIDENCE_BASELINE。

    返回格式对称（C1）：唯一 return 路径，顶层 key 集合固定
    {learning_speed, career_diversity, growth_orientation, growth_signals_360, confidence}。
    """
    # ── 防御（C3/C4）：跨边界值守卫 ──
    t3_raw = t3_raw or {}
    if not isinstance(t3_raw, dict):
        t3_raw = {}
    raw = (employee.get("raw") if isinstance(employee, dict) else None) or {}

    # years: `or 0` 处理 None（键存在但值为 None 时 .get 返回 None，max(None,1) 会崩）
    years = max(raw.get("years_of_service") or 0, 1)

    # ── 原始信号（过滤 None/空串）──
    learning_activities = _safe_len(t3_raw.get("learning_activities"))
    career_roles = _filter_nonempty(t3_raw.get("career_roles"))
    growth_evidence = _safe_len(t3_raw.get("growth_evidence"))
    feedback_signals = _safe_len(t3_raw.get("feedback_signals"))
    # training: 过滤 None 元素（畸形记录），空 list/None → 0
    training_list = employee.get("training") if isinstance(employee, dict) else None
    training_count = _safe_len(training_list)

    # ── 四项指标（D2: scale 全部从 config import，禁内联数值）──
    learning_speed = min(100, learning_activities / years * T3_LEARNING_SPEED_SCALE)
    # str(r) 守卫：LLM 可能返回不可哈希元素（dict），set() 会崩；role 名本应 str，str() 恒等
    career_diversity = min(
        100, len({str(r) for r in career_roles}) * T3_CAREER_DIVERSITY_SCALE
    )
    growth_orientation = min(
        100,
        growth_evidence * T3_GROWTH_EVIDENCE_SCALE
        + training_count * T3_TRAINING_SCALE,
    )
    growth_signals_360 = min(100, feedback_signals * T3_FEEDBACK_SCALE)

    # ── confidence：全部空（无任何信号）→ 降级 ──
    all_empty = (
        learning_activities == 0
        and len(career_roles) == 0
        and growth_evidence == 0
        and feedback_signals == 0
        and training_count == 0
    )
    confidence = T3_CONFIDENCE_DEGRADED if all_empty else T3_CONFIDENCE_BASELINE

    # ── 类型清洗（C1/D2）：numpy float64 → Python float，防 json.dumps 失败 ──
    return {
        "learning_speed": float(learning_speed),
        "career_diversity": float(career_diversity),
        "growth_orientation": float(growth_orientation),
        "growth_signals_360": float(growth_signals_360),
        "confidence": float(confidence),
    }
