"""向量直配匹配引擎（M3 核心，竞品 TalentAtlas 思路 × 我方五层公式融合）。

范式（docs/competitor_talentatlas_analysis.md 差距分析的落地）：
- 召回不依赖 LLM 抽取标签：岗位要求 query 直接与员工证据 chunk 向量配对
  （EvidenceIndex bi-encoder 召回；Top-N 候选再过 bge-reranker-v2-m3
  交叉重排校准——竞品"按成本与效果分工"的三层栈等价物：全员 bi 初排 ≈
  L1/L2 廉价层，CE 只打短名单 ≈ L3 精排层，每岗位 1 次 predict 调用）
- 固定公式百分制、零 LLM 评分：
    总分 = T0 直接技能×50 + T1 语义×30 + T2 行为×10 + T3 潜力×10
  （权重 config.MATCH_FORMULA_WEIGHTS；LLM 只写理由不碰分数）
- 置信三档：<0.60 驳回 / 0.60–0.85 待审（=备选池）/ ≥0.85 自动推荐；
  H0/H1 硬闸门未过者：语义仍强（≥MATCH_POOL_SEMANTIC_MIN）→ 备选池，否则驳回
- 确定性：全链路无温度采样；相同输入 → 相同排序（连跑两次逐位一致）

消费者：agents/matching.py（Agent 封装）、scripts/blind_test.py（M4 盲测）。
"""

from __future__ import annotations

import math

import numpy as np

import config
from utils.evidence_index import EvidenceIndex

__all__ = [
    "check_hard_gate",
    "rank_candidates",
    "score_t0_direct",
    "score_t1_bi",
    "calibrate_t1_with_ce",
]

_EDU_ORDINAL = {"大专": 1, "本科": 2, "硕士": 3, "研究生": 3, "博士": 4}

# T0 直接技能的字面命中源（证书/培训/工具/岗位语义 → 只扫这三类 chunk）
_T0_SOURCES = {"position", "training", "projects"}


# ── 硬闸门（H0/H1）───────────────────────────────────────────────
def check_hard_gate(hard_requirements: dict, employee: dict) -> dict:
    """H0/H1 硬条件闸门：学历下限 + 年限下限。

    证书不做闸门（JD 中"优先"项；作为 T0 直接技能加分项参与评分）。

    Returns:
        {"passed": bool, "fail_reasons": [str]}
    """
    hard = hard_requirements or {}
    structured = (employee.get("structured") or {}) if isinstance(employee, dict) else {}
    reasons: list[str] = []

    edu_min = str(hard.get("education_min") or "").strip()
    if edu_min:
        need = _EDU_ORDINAL.get(edu_min)
        have = _EDU_ORDINAL.get(str(structured.get("education", "")).strip())
        if need is not None and (have is None or have < need):
            reasons.append(f"学历{structured.get('education', '未知')}低于要求{edu_min}及以上")

    years_min = hard.get("years_min")
    if isinstance(years_min, int) and years_min > 0:
        years = (structured.get("years_of_service") or 0)
        if not isinstance(years, (int, float)) or years < years_min:
            reasons.append(f"司龄{years}年低于要求{years_min}年")

    return {"passed": not reasons, "fail_reasons": reasons}


def _employee_t0_pool(employee: dict) -> str:
    """员工 T0 命中池文本：position/training/projects chunk + 结构化证书行。"""
    from utils.evidence_index import chunk_employee

    parts: list[str] = []
    structured = employee.get("structured") or {}
    certs = structured.get("certificates") or ""
    if certs and certs != "无":
        parts.append(str(certs))
    for chunk in chunk_employee(employee):
        if chunk["source"] in _T0_SOURCES:
            parts.append(chunk["text"])
    return "\n".join(parts)


def _norm_literal(s: str) -> str:
    """字面层归一化：去空白 + 小写（「Power BI」→「powerbi」，竞品 L1 字面层惯例）。"""
    return "".join(str(s).lower().split())


# ── T0 直接技能（字面命中，50 分）───────────────────────────────
def score_t0_direct(job_profile: dict, employee: dict) -> tuple[float, list[str]]:
    """技能要求名 + 必备证书 在员工岗位/培训/项目证据中的字面命中率。

    命中判定：归一化（去空白/大小写：PowerBI ↔ Power BI）后的全子串。
    2026-10-21 标定记录：① 不拆 detail 关键词入分母（分母膨胀失真）；
    ② 不用标签库 keywords 桥接（泛化 kw 令全员 t0≈0.92+，失去区分度，
    排名被 T2/T3 接管）——字面层只管精确命中，同义改写（人力资源管理 ↔
    人力资源数字化平台、法务审计 ↔ 合规审计）交给 T1 语义层区分。

    Returns:
        (score01, hit_terms)：score01∈[0,1]，无要求项 → 0.5（中性分）。
    """
    terms: list[str] = []
    for s in job_profile.get("skill_requirements", []):
        name = str(s.get("name", "")).strip()
        if name:
            terms.append(name)
    for c in (job_profile.get("hard_requirements") or {}).get("certificates") or []:
        c = str(c).strip()
        if c:
            terms.append(c)
    terms = list(dict.fromkeys(terms))
    if not terms:
        return 0.5, []

    pool_norm = _norm_literal(_employee_t0_pool(employee))
    hits = [t for t in terms if _norm_literal(t) in pool_norm]
    return len(hits) / len(terms), hits


# ── T1 语义匹配（30 分）─────────────────────────────────────────
def score_t1_bi(
    job_profile: dict,
    index: EvidenceIndex,
    emp_id: str,
) -> tuple[float, list[dict]]:
    """bi-encoder 人级语义分（全员初排用，廉价层）。

    queries 人级聚合（employee_scores 内 max-pool→mean）→ 下限截断
    （低于 MATCH_SEMANTIC_FLOOR 视为噪声归零，防低分填充）。

    Returns:
        (score01, evidence)：evidence 为 [{query, source, text, anchor, sim}]，
        按 sim 降序最多 6 条（证据链素材，anchor 可点回原文）。
    """
    queries = job_profile.get("queries") or []
    if not queries or index.matrix.size == 0:
        return 0.0, []

    bi_raw = index.employee_scores(queries, emp_ids=[emp_id]).get(emp_id, 0.0)
    floor = config.MATCH_SEMANTIC_FLOOR
    bi_norm = min(1.0, max(0.0, (bi_raw - floor) / (1.0 - floor))) if bi_raw > floor else 0.0

    # 证据链素材：每条 query 取该员工 top1 chunk
    top1_by_query: list[dict] = []
    for q in queries:
        chunks = index.top_chunks_for_employee(q, emp_id, top_k=1)
        if chunks:
            top1_by_query.append({"query": q, **chunks[0]})
    top1_by_query.sort(key=lambda c: -c["sim"])
    evidence = [
        {k: c[k] for k in ("query", "source", "text", "anchor", "sim")}
        for c in top1_by_query[:6]
    ]
    return bi_norm, evidence


def _sigmoid(x: float) -> float:
    """数值稳定 sigmoid（cross-encoder 原始 logit → 0-1 校准分）。"""
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-min(x, 30.0)))
    z = math.exp(max(x, -30.0))
    return z / (1.0 + z)


def calibrate_t1_with_ce(
    job_profile: dict,
    index: EvidenceIndex,
    emp_ids: list[str],
    cross_encoder_fn=None,
) -> dict[str, float]:
    """cross-encoder 批量校准短名单（精排层，每岗位 1 次 predict 调用）。

    对每个 emp 的每条 query 取其 top1 chunk，(query, chunk) 全量 pairs
    一次 predict → sigmoid 均值 → {emp_id: ce01}。任何失败 → {}（纯 bi 分）。
    """
    if not emp_ids:
        return {}
    encoder = cross_encoder_fn
    if encoder is None:
        from utils.label_matching import _load_cross_encoder

        encoder = _load_cross_encoder()
    if encoder is None:
        return {}

    queries = job_profile.get("queries") or []
    pairs: list[tuple[str, str]] = []
    owner: list[str] = []
    for emp_id in emp_ids:
        for q in queries:
            chunks = index.top_chunks_for_employee(q, emp_id, top_k=1)
            if chunks:
                pairs.append((q, chunks[0]["text"]))
                owner.append(emp_id)
    if not pairs:
        return {}
    try:
        # 双契约：真实 CrossEncoder 对象走 .predict；测试注入为裸函数 fn(pairs)
        predict_fn = encoder.predict if hasattr(encoder, "predict") else encoder
        scores = predict_fn(pairs)
        arr = np.asarray(scores, dtype=float).ravel()
        if arr.size != len(pairs):
            return {}
    except Exception:
        return {}

    sums: dict[str, list[float]] = {}
    for eid, s in zip(owner, arr.tolist()):
        sums.setdefault(eid, []).append(_sigmoid(s))
    return {eid: float(np.mean(v)) for eid, v in sums.items()}


# ── T2 行为（10 分）─────────────────────────────────────────────
def score_t2_behavior(employee: dict) -> float:
    """360 五维均分 → 0-1（缺 360 → 0.5 中性）。"""
    s360 = employee.get("scores_360") or {}
    if not isinstance(s360, dict) or not s360:
        return 0.5
    vals = [v for v in s360.values() if isinstance(v, (int, float))]
    if not vals:
        return 0.5
    mean = float(np.mean(vals))  # 五维量表 1-5
    return min(1.0, max(0.0, (mean - 1.0) / 4.0))


# ── T3 潜力（10 分，确定性代理）─────────────────────────────────
def score_t3_potential(employee: dict) -> float:
    """绩效轨迹 + 培训量 确定性代理（隐形高潜信号：上升轨迹加权）。

    t3_01 = 0.5×平均绩效 + 0.3×轨迹方向 + 0.2×培训量
    - 平均绩效：等级序数 (avg-1)/3，D=1→0，A=4→1
    - 轨迹方向：(last-first+3)/6，上升翻盘→>0.5，高开低走→<0.5
    - 培训量：min(count,5)/5；无绩效记录 → 0.5 中性
    """
    perf = employee.get("performance") or []
    grade_map = {"A": 4, "B": 3, "C": 2, "D": 1}
    grades: list[int] = []
    if isinstance(perf, list):
        for p in perf:
            if isinstance(p, dict):
                g = grade_map.get(str(p.get("grade", "")).strip())
                if g is not None:
                    grades.append(g)
    training = employee.get("training") or []
    training_count = len([t for t in training if isinstance(t, dict)]) if isinstance(training, list) else 0

    # 零信号（无绩效也无培训）→ 精确中性 0.5
    if not grades and training_count == 0:
        return 0.5

    if not grades:
        avg01, trend01 = 0.5, 0.5
    else:
        avg01 = (float(np.mean(grades)) - 1.0) / 3.0
        trend01 = (grades[-1] - grades[0] + 3) / 6.0
    training01 = min(training_count, 5) / 5.0
    return min(1.0, max(0.0, 0.5 * avg01 + 0.3 * trend01 + 0.2 * training01))


# ── 汇总排序（两段式：全员 bi 初排 → Top-N CE 校准 → 终排）──────
def _template_reason(hit_terms: list[str], evidence: list[dict], scores: dict) -> str:
    """离线模板推荐理由（零 LLM；LLM 富化留 hook，默认不启用）。"""
    parts: list[str] = []
    if hit_terms:
        parts.append(f"字面命中技能证据 {len(hit_terms)} 项（如「{hit_terms[0]}」）")
    if evidence:
        ev = evidence[0]
        parts.append(f"语义最相关证据：{ev['anchor']}…（sim {ev['sim']:.2f}）")
    parts.append(
        f"T1语义 {scores['t1'] * 100:.0f}／T2行为 {scores['t2'] * 100:.0f}"
        f"／T3潜力 {scores['t3'] * 100:.0f}"
    )
    return "；".join(parts)


def rank_candidates(
    job_profile: dict,
    employees: list[dict],
    index: EvidenceIndex,
    cross_encoder_fn=None,
) -> dict:
    """对岗位画像 × 全员证据索引跑完整匹配（固定公式，确定性排序）。

    两段式（成本分层）：全员 bi-encoder 初排 → 总分 Top
    MATCH_RERANK_TOPN 进 cross-encoder 批量校准（1 次 predict）→ 终排。

    Returns:
        {"job_id", "title", "candidates": [
            {"emp_id", "name", "gate": {"passed", "fail_reasons"},
             "scores": {t0, t1, t2, t3, total, confidence}, "ce_calibrated": bool,
             "decision": "recommend"|"review"|"backup_pool"|"rejected",
             "evidence": [...], "reason": str}
        ] 按 total 降序（并列按 emp_id 升序，保证逐位一致）,
         "formula": 权重快照, "thresholds": 三档快照}
    """
    weights = config.MATCH_FORMULA_WEIGHTS

    # ── 第一段：全员廉价评分（t0/t2/t3 + bi 语义）──
    prelim: list[dict] = []
    for emp in employees or []:
        emp_id = str(emp.get("employee_id", ""))
        if not emp_id:
            continue
        t0, hits = score_t0_direct(job_profile, emp)
        t1, evidence = score_t1_bi(job_profile, index, emp_id)
        t2 = score_t2_behavior(emp)
        t3 = score_t3_potential(emp)
        total = (
            weights["t0_direct"] * t0
            + weights["t1_semantic"] * t1
            + weights["t2_behavior"] * t2
            + weights["t3_potential"] * t3
        )
        prelim.append({
            "emp_id": emp_id,
            "emp": emp,
            "t0": t0, "t1": t1, "t2": t2, "t3": t3,
            "total": total, "hits": hits, "evidence": evidence,
        })

    prelim.sort(key=lambda c: (-c["total"], c["emp_id"]))

    # ── 第二段：短名单 CE 校准（精排层）──
    topn = max(1, int(config.MATCH_RERANK_TOPN))
    shortlist = [c["emp_id"] for c in prelim[:topn]]
    ce_scores = calibrate_t1_with_ce(
        job_profile, index, shortlist, cross_encoder_fn=cross_encoder_fn
    )
    blend = config.MATCH_RERANK_BLEND if ce_scores else 0.0

    candidates: list[dict] = []
    for c in prelim:
        ce = ce_scores.get(c["emp_id"])
        ce_calibrated = ce is not None
        if ce_calibrated:
            t1_final = min(1.0, max(0.0, (1.0 - blend) * c["t1"] + blend * ce))
        else:
            t1_final = c["t1"]
        total_final = (
            weights["t0_direct"] * c["t0"]
            + weights["t1_semantic"] * t1_final
            + weights["t2_behavior"] * c["t2"]
            + weights["t3_potential"] * c["t3"]
        )
        confidence = total_final / 100.0

        gate = check_hard_gate(job_profile.get("hard_requirements"), c["emp"])
        if not gate["passed"]:
            decision = (
                "backup_pool"
                if t1_final >= config.MATCH_POOL_SEMANTIC_MIN
                else "rejected"
            )
        elif confidence >= config.MATCH_REVIEW_THRESHOLD:
            decision = "recommend"
        elif confidence >= config.MATCH_REJECT_THRESHOLD:
            decision = "review"
        else:
            decision = "rejected"

        name = str((c["emp"].get("structured") or {}).get("name", ""))
        candidates.append({
            "emp_id": c["emp_id"],
            "name": name,
            "gate": gate,
            "scores": {
                "t0": round(c["t0"], 4),
                "t1": round(t1_final, 4),
                "t2": round(c["t2"], 4),
                "t3": round(c["t3"], 4),
                "total": round(total_final, 2),
                "confidence": round(confidence, 4),
            },
            "ce_calibrated": ce_calibrated,
            "decision": decision,
            "evidence": c["evidence"],
            "reason": _template_reason(c["hits"], c["evidence"],
                                       {"t1": t1_final, "t2": c["t2"], "t3": c["t3"]}),
        })

    candidates.sort(key=lambda c: (-c["scores"]["total"], c["emp_id"]))
    return {
        "job_id": str(job_profile.get("job_id", "")),
        "title": str(job_profile.get("title", "")),
        "candidates": candidates,
        "formula": dict(weights),
        "thresholds": {
            "reject": config.MATCH_REJECT_THRESHOLD,
            "review": config.MATCH_REVIEW_THRESHOLD,
            "pool_semantic_min": config.MATCH_POOL_SEMANTIC_MIN,
            "rerank_topn": topn,
            "rerank_blend": config.MATCH_RERANK_BLEND,
        },
    }
