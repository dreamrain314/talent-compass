"""要求—证据对齐引擎（Round 3，预注册 docs/preregister_round3_evidence_alignment_20261022.md §二，2026-10-22 封存）。

更换比较单元：不再「员工↔岗位整段语义相似度」，而是「岗位原子要求 ↔ 原始证据片段」
逐要求对齐，覆盖评分 S = 80·Σ(w_r·v)/Σw_r + 10·B + 10·P。

预注册硬约束（只执行不发挥）：
- §2.1 斜杠枚举默认「上位概念+实例」：命中其一即满足，不机械计成三项
- §2.1 权重 w_r 来自 JD 必要性定义（必要/加分），不得根据"哪个员工应获胜"设置
- §2.2 原始记录始终可检索（chunk 即原始记录切片），不以标签抽取成功为前提
- §2.3 五类关系事前冻结；等价表达=经核验同义改写（未经核验不成立，如实报未证实）
- §2.3 不设字面加成：字面命中与等价命中同档计分，字面只是便于验证
- §2.4 CE 高分只是相关性信号，不得直接解释为"该要求已成立"（成立判定走规则+核验表）
- §2.4 每要求贡献有上限（v=max），同一事实不制造多个独立能力项
- 运行时零 LLM（CE 本地 + 确定性规则），确定性基线不动摇

T2/T3 暂冻结（§二排期）：B/P 基座直接复用 match_engine 的冻结通道。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np

import config
from utils.match_engine import _norm_literal, score_t2_behavior, score_t3_potential

__all__ = [
    "extract_requirements",
    "classify_relation",
    "recall_candidates",
    "score_coverage",
    "build_evidence_matrix",
    "encode_query_texts",
    "COVERAGE_RELATION_VALUES",
]

# ── 五类关系的计分值（预注册 §2.3 事前冻结）─────────────────────────
# 等价表达/有向支持（完成态、正向）→ 同档计分；证据状态不同 → 不同分；
# 仅相关 → 不计成立；明确否定/冲突 → 单独标记且不被高相似度覆盖。
COVERAGE_RELATION_VALUES = {
    "equivalent": 1.0,      # 等价表达（仅限已核验等价表内条目）
    "direct_support": 1.0,  # 有向支持：e 是 r 的下位实例（禁止反向推导）
    "state_different": 0.5, # 计划/学习中 vs 已完成
    "relevant_only": 0.0,   # 仅相关：只作候选召回，不计成立
    "contradiction": 0.0,   # 明确否定/冲突：单独标记
}

# 证据状态标记（training/绩效原文中的状态词；「已完成」默认态不在此列）
_STATE_MARKERS = ("学习中", "计划中", "拟参加", "即将参加", "准备参加", "报名")
# 明确否定（预注册 §2.3：记录明确说明未参与相关开发——窄口径，不用泛负向词）
_NEGATION_MARKERS = ("未参与", "没有相关", "不具备相关", "无相关经验", "未接触")

_GATE_ITEM_RE = re.compile(r"学历|年及以上|年以上.{0,4}经验|司龄|年限")
_PAREN_RE = re.compile(r"[（(]([^（）()]*)[)）]")
_REQ_PREFIX_RE = re.compile(
    r"^(熟悉|掌握|精通|具备|具有|了解|能够|能|会|熟练使用|熟练掌握)+"
)


# ── §2.1 要求抽取 ────────────────────────────────────────────────
def extract_requirements(job: dict) -> list[dict]:
    """JD → 原子要求集 R（确定性，零 LLM；解析结果在验收前须人工核验并冻结）。

    规则（预注册 §2.1）：
    - 来源：requirements + responsibilities 文本条目；学历/年限条目归硬门槛，不入 R
    - 必要性：含「优先」→ 加分项 w=0.5，否则必要项 w=1.0（w 来自 JD，不来自候选）
    - 斜杠枚举：括号内 /、，分隔的实例清单 → 归并为单个上位要求（命中其一即满足）
    - JD 明确「或」→ either_ok=True（任选）；「同时具备」按并列拆分（mock 未见，保守不拆）

    Returns:
        [{rid, text, head, instances, kind, weight, either_ok}]
        head=去括号+去请求性前缀的核心文本；instances=括号内实例列表。
    """
    reqs: list[dict] = []
    seen_heads: set[str] = set()
    raw_items: list[str] = []
    for field in ("requirements", "responsibilities"):
        items = job.get(field) or []
        if isinstance(items, list):
            raw_items.extend(str(x) for x in items if x)

    for idx, item in enumerate(raw_items):
        if _GATE_ITEM_RE.search(item):
            continue  # 硬门槛条目不入要求集（Round 3 骨架无闸门项，权重表达必要性）
        parens = _PAREN_RE.findall(item)
        instances: list[str] = []
        for grp in parens:
            instances.extend(
                p.strip() for p in re.split(r"[/、，,]", grp) if p.strip()
            )
        head = _PAREN_RE.sub("", item)
        head = re.sub(r"\s+", "", head)
        head = _REQ_PREFIX_RE.sub("", head) or head
        head = head.rstrip("；;。.，, ")
        if not head:
            continue
        # 无括号但 head 本身是斜杠枚举（如「教学设计/课程设计/教学管理」）→ 段即实例
        if not instances and head.count("/") >= 1:
            segs = [s.strip() for s in head.split("/") if len(s.strip()) >= 2]
            if len(segs) >= 2:
                instances = segs
        kind = "preferred" if "优先" in item else "necessary"
        key = _norm_literal(head)
        if key in seen_heads:
            continue  # 同名要求去重（同 §2.4 一事实不重复计分）
        seen_heads.add(key)
        reqs.append({
            "rid": f"R{idx + 1:02d}",
            "text": item,
            "head": head,
            "instances": instances,
            "kind": kind,
            "weight": config.COVERAGE_W_PREFERRED if kind == "preferred" else config.COVERAGE_W_NECESSARY,
            # 斜杠枚举 = 上位+实例，命中其一即满足（§2.1）；v=max 聚合天然实现，
            # 本标志仅作展示。显式「同时具备」的并列拆分 mock 未见，保守不拆。
            "either_ok": bool(instances),
        })
    return reqs


# ── 等价表（人工核验后才生效；Day 6-7 离线裁决填充）─────────────────
def load_verified_equivalences(path: str | Path | None = None) -> dict[str, list[str]]:
    """已核验等价表：{要求侧归一词: [证据侧归一词, ...]}。

    文件不存在 → 空表（等价类无条目，相关改写如实报「未证实」，见 build_evidence_matrix）。
    种子：data/jobs/alias_patches.json 的 4 对回归补丁（逐对过盲测的既有资产）。
    """
    table: dict[str, list[str]] = {}
    try:
        alias_path = getattr(config, "T0_ALIAS_PATCHES_PATH", None)
        if alias_path and Path(alias_path).exists():
            data = json.loads(Path(alias_path).read_text(encoding="utf-8"))
            for left, rights in (data.get("aliases") or {}).items():
                table.setdefault(_norm_literal(left), [])
                for r in rights or []:
                    nl = _norm_literal(r)
                    if nl and nl not in table[_norm_literal(left)]:
                        table[_norm_literal(left)].append(nl)
    except Exception:
        pass
    p = Path(path) if path is not None else getattr(config, "COVERAGE_EQUIVALENCE_PATH", None)
    if p and Path(p).exists():
        try:
            data = json.loads(Path(p).read_text(encoding="utf-8"))
            for left, rights in (data.get("equivalences") or {}).items():
                bucket = table.setdefault(_norm_literal(left), [])
                for r in rights or []:
                    nl = _norm_literal(r)
                    if nl and nl not in bucket:
                        bucket.append(nl)
        except Exception:
            pass
    return table


# ── §2.2 双通道召回 + CE 重排 ────────────────────────────────────
def _char_bigrams(s: str) -> set[str]:
    s = _norm_literal(s)
    return {s[i:i + 2] for i in range(len(s) - 1)} if len(s) > 1 else {s}


def _lexical_score(req: dict, chunk_text: str) -> float:
    """词法通道：要求文本（head+实例）与 chunk 的字符 bigram Dice 系数（0-1）。"""
    req_text = _norm_literal(req["head"] + "".join(req["instances"]))
    a = _char_bigrams(req_text)
    b = _char_bigrams(chunk_text)
    if not a or not b:
        return 0.0
    inter = len(a & b)
    return 2.0 * inter / (len(a) + len(b))


def recall_candidates(
    req: dict,
    emp_chunks: list[dict],
    emp_chunk_vecs: np.ndarray,
    query_vec: np.ndarray,
    top_k: int | None = None,
) -> list[dict]:
    """单要求 × 单员工的候选证据召回：embedding + 词法双通道并集 → 上限 k。

    预注册 §2.2 次序：双通道召回并 k 截断在先，CE 对候选逐对评分在后
    （score_coverage 内执行）。CE 只重排/记录，不改变成立判定（§2.4）。

    Args:
        req: extract_requirements 产物。
        emp_chunks: 该员工的 chunk 列表（chunk_employee 产物，原始记录切片）。
        emp_chunk_vecs: 与 emp_chunks 对齐的向量矩阵（EvidenceIndex 真实编码或 fake）。
        query_vec: 要求文本的 query 向量（shape (dim,)）。
        top_k: 候选上限，默认 config.COVERAGE_RECALL_K（预注册 §七-3 冻结 k≤3）。

    Returns:
        [{chunk..., "sim_embed", "sim_lexical"}] 双通道最优序，≤k 条。
    """
    k = top_k if top_k is not None else config.COVERAGE_RECALL_K
    if not emp_chunks or emp_chunk_vecs.size == 0 or query_vec.size == 0:
        return []
    qn = np.linalg.norm(query_vec) or 1.0
    cn = np.linalg.norm(emp_chunk_vecs, axis=1)
    denom = np.where(cn * qn == 0, 1.0, cn * qn)
    sims = np.nan_to_num((emp_chunk_vecs @ query_vec) / denom, nan=0.0, posinf=0.0, neginf=0.0)
    lex = [_lexical_score(req, c["text"]) for c in emp_chunks]

    n = len(emp_chunks)
    order_embed = sorted(range(n), key=lambda i: -sims[i])[: min(2, n)]
    order_lex = sorted(range(n), key=lambda i: -lex[i])[: min(2, n)]
    union = list(dict.fromkeys(order_embed + order_lex))  # 去重保序
    union.sort(key=lambda i: -max(float(sims[i]), lex[i]))

    return [
        {
            **emp_chunks[i],
            "sim_embed": round(float(sims[i]), 4),
            "sim_lexical": round(lex[i], 4),
        }
        for i in union[:k]
    ]


# ── §2.3 关系分类 g(r,e)（规则确定性判定；CE 只是相关性信号）────────
def classify_relation(req: dict, chunk: dict, equivalences: dict[str, list[str]]) -> dict:
    """单 (要求, 证据) 对的五类关系判定（预注册 §2.3 冻结定义，零 LLM）。

    判定次序：明确否定 > 状态不同 > 等价（核验表）> 有向支持（实例命中）> 仅相关。
    字面实例命中与核验等价同档计分（§2.3 不设字面加成）。

    Returns:
        {"relation", "value", "hit_terms", "note"}
    """
    text_n = _norm_literal(chunk["text"])
    terms = [req["head"]] + list(req["instances"])
    term_norms = [_norm_literal(t) for t in terms if _norm_literal(t)]
    # head 归一后可能整句过长，取其 2-8 字滑窗核心词 + 实例做命中检测
    head_cores = _head_core_terms(req["head"])
    hit_terms = [t for t in term_norms if t and t in text_n]
    core_hits = [t for t in head_cores if t in text_n]
    is_state = any(m in chunk["text"] for m in _STATE_MARKERS)
    is_neg = any(m in chunk["text"] for m in _NEGATION_MARKERS)

    term_hit = bool(hit_terms or core_hits)

    if term_hit and is_neg:
        return {"relation": "contradiction", "value": COVERAGE_RELATION_VALUES["contradiction"],
                "hit_terms": hit_terms or core_hits, "note": "记录含明确否定标记，单独标记不被相似度覆盖"}
    if term_hit and is_state:
        return {"relation": "state_different", "value": COVERAGE_RELATION_VALUES["state_different"],
                "hit_terms": hit_terms or core_hits, "note": "证据状态为计划/学习中，非已完成"}
    # 等价表达：仅限已核验表；表内命中 → 与字面同档
    eq_hits = []
    for t in head_cores + hit_terms:
        for equiv in equivalences.get(t, []):
            if equiv and equiv in text_n:
                eq_hits.append(equiv)
    if eq_hits:
        return {"relation": "equivalent", "value": COVERAGE_RELATION_VALUES["equivalent"],
                "hit_terms": eq_hits, "note": "经核验等价表命中（与字面同档，无字面加成）"}
    if term_hit:
        return {"relation": "direct_support", "value": COVERAGE_RELATION_VALUES["direct_support"],
                "hit_terms": hit_terms or core_hits, "note": "实例/核心词命中（有向支持，下位实例可支持）"}
    return {"relation": "relevant_only", "value": COVERAGE_RELATION_VALUES["relevant_only"],
            "hit_terms": [], "note": "仅主题相关，未检出支持性命中；如系同义改写待人工核验入表"}


def _head_core_terms(head: str) -> list[str]:
    """head 的字面可检核心词——保守口径：仅短 head（归一后 ≤6 字）整体参与。

    长 head 不做字面命中（n-gram 滑窗会把「交付」「质量」等通用词误判成支持，
    违反 §2.3「仅相关不计成立」）；长 head 的成立通道 = 括号/斜杠实例命中
    （mock JD 的具体技能都在实例里）或已核验等价表。这是刻意的保守：
    宁可如实报「未证实」，不制造字面碰词分。
    """
    h = _norm_literal(head)
    if not h:
        return []
    return [h] if len(h) <= 6 else []


# ── §2.4 覆盖评分 + §2.5 证据矩阵 ────────────────────────────────
def score_coverage(
    requirements: list[dict],
    employees: list[dict],
    index,  # EvidenceIndex
    cross_encoder_fn=None,
    equivalences: dict[str, list[str]] | None = None,
    encode_fn=None,
) -> dict[str, dict]:
    """全员工 × 全要求覆盖评分（预注册 §2.4 骨架，暂定权重已封存）。

    S(j,c) = 80·[Σ w_r·v(r,c)/Σ w_r] + 10·B(c) + 10·P(c)；v(r,c)=max_e g(r,e)。

    Args:
        requirements: extract_requirements 产物（验收使用前须人工核验冻结）。
        employees: Agent① 员工列表。
        index: EvidenceIndex（原始记录切片索引，passage 侧编码）。
        cross_encoder_fn: CE predict 函数 list[pairs]->scores（本地 reranker）；
            None→跳过 CE（候选次序回退双通道）。
        equivalences: 已核验等价表；None→自动加载。
        encode_fn: 要求侧 query 编码注入（测试用）；None→真实 query_embed 路径。

    Returns:
        {emp_id: {"total", "coverage", "b", "p", "requirements": {rid: {
            "v", "relation", "evidence": [...top候选...]}}}}
    """
    reqs = requirements
    if not reqs:
        return {}
    equiv = equivalences if equivalences is not None else load_verified_equivalences()
    chunk_emp = np.array([c["emp_id"] for c in index.chunks]) if len(index.chunks) else np.array([])
    query_vecs = encode_query_texts([r["text"] for r in reqs], encode_fn)
    if query_vecs is None or query_vecs.size == 0:
        return {}

    out: dict[str, dict] = {}
    for emp in employees:
        eid = str(emp.get("employee_id", ""))
        if not eid:
            continue
        idxs = np.where(chunk_emp == eid)[0] if chunk_emp.size else []
        emp_chunks = [index.chunks[i] for i in idxs]
        emp_vecs = index.matrix[idxs] if len(idxs) else np.array([])
        b = score_t2_behavior(emp)
        p = score_t3_potential(emp)
        # 第一遍：全要求召回（CE 在后——§2.2 次序：召回截断在先，CE 对候选逐对评分）
        all_cands: dict[str, list[dict]] = {}
        for ri, req in enumerate(reqs):
            all_cands[req["rid"]] = recall_candidates(
                req, emp_chunks, emp_vecs, np.asarray(query_vecs[ri]).reshape(-1),
            )
        # CE 批处理：按员工合并全部 (要求, 候选) 对为一次 predict（延迟实测入验收报告）
        if cross_encoder_fn is not None:
            pair_index: list[tuple[str, int]] = []
            pairs: list[tuple[str, str]] = []
            for req in reqs:
                for ci, c in enumerate(all_cands[req["rid"]]):
                    pairs.append((req["text"], c["text"]))
                    pair_index.append((req["rid"], ci))
            if pairs:
                try:
                    ce_vals = cross_encoder_fn(pairs)
                    ce_vals = [float(v) for v in (ce_vals if isinstance(ce_vals, (list, np.ndarray)) else [ce_vals])]
                except Exception:
                    ce_vals = [0.0] * len(pairs)
                for (rid, ci), cv in zip(pair_index, ce_vals):
                    all_cands[rid][ci]["ce"] = round(max(0.0, min(1.0, cv)), 4)
                for req in reqs:
                    all_cands[req["rid"]].sort(
                        key=lambda c: -(c["ce"] if c["ce"] is not None else 0.0))
        req_results: dict[str, dict] = {}
        w_sum = 0.0
        w_cov = 0.0
        for req in reqs:
            cands = all_cands[req["rid"]]
            best: dict | None = None
            best_cls: dict | None = None
            best_key: tuple = (-1.0, 0)
            for c in cands:
                cls = classify_relation(req, c, equiv)
                # v=max；同分时矛盾标记优先于仅相关（§2.3 不被高相似度覆盖）
                key = (cls["value"], 1 if cls["relation"] == "contradiction" else 0)
                if key > best_key:
                    best, best_cls, best_key = c, cls, key
                if cls["value"] >= 1.0:
                    break  # v=max：已达上限，后续候选不再改变该要求贡献
            v = best_cls["value"] if best_cls else 0.0
            w_sum += float(req["weight"])
            w_cov += float(req["weight"]) * v
            req_results[req["rid"]] = {
                "v": v,
                "relation": best_cls["relation"] if best_cls else "no_candidate",
                "note": best_cls["note"] if best_cls else "无候选证据",
                "hit_terms": best_cls["hit_terms"] if best_cls else [],
                "evidence": [_ev_row(c, best_cls) for c in cands],
            }
        coverage = w_cov / w_sum if w_sum else 0.0
        total = (
            config.COVERAGE_W_COVERAGE * coverage
            + config.COVERAGE_W_BEHAVIOR * b
            + config.COVERAGE_W_POTENTIAL * p
        )
        out[eid] = {
            "total": round(total, 2),
            "coverage": round(coverage, 4),
            "b": round(b, 4),
            "p": round(p, 4),
            "requirements": req_results,
        }
    return out


def _ev_row(cand: dict, cls: dict | None) -> dict:
    return {
        "source": cand["source"],
        "anchor": cand["anchor"],
        "text": cand["text"],
        "relation": cls["relation"] if cls else None,
        "value": cls["value"] if cls else None,
        "sim_embed": cand.get("sim_embed"),
        "sim_lexical": cand.get("sim_lexical"),
        "ce": cand.get("ce"),
    }


def build_evidence_matrix(requirements: list[dict], emp_result: dict) -> list[dict]:
    """工作台证据矩阵（预注册 §2.5 必交付）：每要求一行——支持状态/证据/限制。"""
    status_map = {
        "equivalent": "已支持（核验等价）",
        "direct_support": "已支持",
        "state_different": "部分（状态存疑）",
        "relevant_only": "未证实",
        "contradiction": "冲突标记",
        "no_candidate": "未证实（无候选）",
    }
    limit_map = {
        "direct_support": "仅证明经历/命中，不证明熟练度",
        "equivalent": "等价关系以人工核验表为准",
        "state_different": "计划/学习中，未完成",
        "relevant_only": "主题相邻但未检出支持性证据；如系同义改写待人工核验",
        "contradiction": "记录含明确否定，需人工复核",
        "no_candidate": "该员工记录中未召回到相关证据",
    }
    rows: list[dict] = []
    req_by_rid = {r["rid"]: r for r in requirements}
    for rid, res in (emp_result.get("requirements") or {}).items():
        req = req_by_rid.get(rid, {})
        ev = res.get("evidence") or []
        rows.append({
            "rid": rid,
            "requirement": req.get("text", rid),
            "kind": req.get("kind", ""),
            "support_status": status_map.get(res.get("relation"), res.get("relation")),
            "v": res.get("v"),
            "evidence": ev[:1],
            "limitation": limit_map.get(res.get("relation"), ""),
        })
    return rows


# ── query 侧编码（Day1-2 诊断实锤修复：bge 检索指令前缀）────────────
_QUERY_INSTRUCTION = "为这个句子生成表示以用于检索相关文章："


def encode_query_texts(texts: list[str], encode_fn=None) -> np.ndarray | None:
    """要求文本的 query 侧编码。

    Day1-2 诊断（utils/label_embedding._embed）：旧路径 query 与 passage 同走
    model.embed()，未用 fastembed 的 query_embed/passage_embed 分工。本引擎的
    query 侧优先走 model.query_embed；不可用则回退「官方 bge 指令前缀 + embed」。
    passage 侧（chunk 矩阵）维持 EvidenceIndex 现状不加前缀。

    encode_fn 注入（测试）时原样直通，不加前缀（fake 编码器无指令语义）。
    """
    texts = [t for t in texts if (t or "").strip()]
    if not texts:
        return None
    if encode_fn is not None:
        vecs = encode_fn(texts)
        return np.asarray(vecs, dtype=float)
    from utils.label_embedding import get_embedding_model

    model = get_embedding_model()
    try:
        vecs = np.array(list(model.query_embed(texts)))
        return vecs if vecs.ndim == 2 else vecs.reshape(len(texts), -1)
    except Exception:
        return np.array(list(model.embed([_QUERY_INSTRUCTION + t for t in texts])))
