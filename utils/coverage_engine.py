"""要求—证据对齐引擎（Round 3，预注册 §二 2026-10-22 封存 + 两类划分修订 §十八 2026-10-24）。

更换比较单元：不再「员工↔岗位整段语义相似度」，而是「岗位原子要求 ↔ 原始证据片段」
逐要求对齐。两类划分（用户 2026-10-24 五决议，结构=开题报告四类职业矩阵）：
total = [W1·S_prof + W2·S_behav + W3·P] + 优先项加分(k)；
S_prof/S_behav = 各类必须项加权覆盖分；W 矩阵按 job_type 选档；
专业类必须项未成立 → total×0.6；证据侧不隔离不打折（证据天然多面）。

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
from utils.match_engine import _norm_literal, score_t3_potential

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

_GATE_ITEM_RE = re.compile(r"学历|年及以上|年以上.{0,4}经验|司龄|年限|等相关专业")
_PAREN_RE = re.compile(r"[（(]([^（）()]*)[)）]")
_REQ_PREFIX_RE = re.compile(
    r"^(熟悉|掌握|精通|具备|具有|了解|能够|能|会|熟练使用|熟练掌握"
    r"|承担|参与|负责|主导|组织|配合|协助|跟进|跟踪|推动|编写|收集|维护)+"
)
# 尾部清理：加分标记（「者优先」/「优先」）不进 head
_TAIL_PREF_RE = re.compile(r"(者)?优先$")
# 顿号枚举（与斜杠枚举同类：上位概念+实例，§2.1）。两种保守模式：
# P1「A、B等」显式等标记枚举；P2 ≥3 段、每段 2-8 字且无动词头的纯列举子句。
# 如「工业物联网、智慧园区等数字化项目」→ [工业物联网, 智慧园区]。
_ENUM_DENG_RE = re.compile(
    r"([^，。；、（）()；;\s等]{2,8})、([^，。；、（）()；;\s等]{2,8})等"
)
_VERB_HEADS = ("熟悉", "掌握", "具备", "具有", "负责", "主导", "参与",
               "承担", "了解", "输出", "使用", "持有", "能够", "开展", "完成")


def _duhao_instances(item: str) -> list[str]:
    """顿号枚举实例化（保守口径）：段长 2-8 字、段内不含请求性动词头。"""
    def _strip_lead(s: str) -> str:
        s2 = re.sub(r"^[有具熟掌精了具]|^具备|^具有|^熟悉|^掌握|^了解", "", s)
        return s2 if len(s2) >= 2 else s

    out: list[str] = []
    for m in _ENUM_DENG_RE.finditer(item):  # P1: A、B等
        segs = [_strip_lead(m.group(1).strip()), _strip_lead(m.group(2).strip())]
        if all(2 <= len(s) <= 8 and not any(v in s for v in _VERB_HEADS) for s in segs):
            out.extend(s for s in segs if s not in out)
    if out:
        return out
    for clause in re.split(r"[，。；；]", item):  # P2: ≥3 段纯列举
        if clause.count("、") >= 2:
            segs = [_strip_lead(s.strip()) for s in clause.split("、") if s.strip()]
            clean = [s for s in segs
                     if 2 <= len(s) <= 8 and not any(v in s for v in _VERB_HEADS)]
            if len(clean) == len(segs) and len(clean) >= 3:
                out.extend(s for s in clean if s not in out)
    return out


# ── §2.1 要求抽取 ────────────────────────────────────────────────
def _split_clauses(item: str) -> list[str]:
    """复合句拆原子（用户 2026-10-25 指令）：按中文逗号/分号切子句。

    一句话携带多个要求时（「承担嵌入式软件方案设计与模块开发，参与需求
    分析和技术路线论证」）拆为独立原子要求；顿号不拆（枚举归并语义）；
    子句 <4 字丢弃；全拆失败回退整句。
    """
    parts = [p.strip() for p in re.split(r"[，；;]", item) if p.strip()]
    kept = [p for p in parts if len(_norm_literal(p)) >= 4]
    return kept if kept else [item]


def extract_requirements(job: dict, clause_split: bool = True) -> list[dict]:
    """JD → 原子要求集 R（确定性，零 LLM；解析结果在验收前须人工核验并冻结）。

    规则（预注册 §2.1 + 用户 2026-10-25 拆句指令）：
    - 来源：requirements + responsibilities 文本条目；学历/年限条目归硬门槛，不入 R
    - **子句拆分**（clause_split，默认开）：条目按逗号/分号切子句，每子句独立成
      要求（gate 剔除/括号实例/顿号枚举/优先识别逐子句进行）——「一句话多个
      要求」不再挤成一个长 head
    - 必要性：子句含「优先」→ 加分项，否则必要项
    - 斜杠/顿号枚举：实例清单归并为单个上位要求（命中其一即满足）

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
        sub_items = _split_clauses(item) if clause_split else [item]
        for si, sub in enumerate(sub_items):
            if _GATE_ITEM_RE.search(sub):
                continue  # 硬门槛子句不入要求集
            parens = _PAREN_RE.findall(sub)
            instances: list[str] = []
            for grp in parens:
                instances.extend(
                    p.strip() for p in re.split(r"[/、，,]", grp) if p.strip()
                )
            head = _PAREN_RE.sub("", sub)
            head = re.sub(r"\s+", "", head)
            head = _REQ_PREFIX_RE.sub("", head) or head
            head = head.rstrip("；;。.，, ")
            head = _TAIL_PREF_RE.sub("", head.rstrip("；;。.，, ")) or head
            if not head:
                continue
            # 无括号但 head 本身是斜杠枚举（如「教学设计/课程设计/教学管理」）→ 段即实例
            if not instances and head.count("/") >= 1:
                segs = [s.strip() for s in head.split("/") if len(s.strip()) >= 2]
                if len(segs) >= 2:
                    instances = segs
            if not instances:
                instances = _duhao_instances(sub)  # 顿号枚举（§2.1 同类归并）
            kind = "preferred" if "优先" in sub else "necessary"
            key = _norm_literal(head)
            if key in seen_heads:
                continue  # 同名要求去重（同 §2.4 一事实不重复计分）
            seen_heads.add(key)
            # rid=父条目索引（被剔的学历/年限条目照旧占号——保持既有 rid 空间
            # 稳定，用户裁决表/等价表键不漂移）；拆出的子句加字母后缀
            base = f"R{idx + 1:02d}"
            rid = base if len(sub_items) == 1 else f"{base}-{chr(97 + si)}"
            reqs.append({
                "rid": rid,
                "text": sub,
                "head": head,
                "instances": instances,
                "kind": kind,
                "weight": config.COVERAGE_W_MUST,  # 必须项类内等权；优先项不进加权（加分制）
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
def classify_relation(req: dict, chunk: dict, equivalences: dict[str, list[str]],
                 bridge_keys: list[tuple[str, float]] | None = None) -> dict:
    """单 (要求, 证据) 对的五类关系判定（预注册 §2.3 冻结定义，零 LLM）。

    判定次序：明确否定 > 状态不同 > 等价（核验表）> 有向支持（实例命中）> 仅相关。
    字面实例命中与核验等价同档计分（§2.3 不设字面加成）。

    Returns:
        {"relation", "value", "hit_terms", "note"}
    """
    text_n = _norm_literal(chunk["text"])
    terms = [req["head"]] + list(req["instances"])
    term_norms = [_norm_literal(t) for t in terms if _norm_literal(t)]
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
    # 等价表达：仅限已核验表。两条激活路径：
    # ① 查找键全集精确命中（head_lookup_keys：head+实例+长head分段）
    # ② 子串激活：表键 ⊂ 要求文本（如「沟通表达」⊂「良好的沟通表达与执行推进能力」，
    #    或「激励学员」⊂ B09 职责句）——改写 miss 场景键集为空，必须由表键反向激活
    lookup_keys = head_lookup_keys(req)
    eq_hits: list[tuple[str, str]] = []  # (表键, 证据侧词)
    req_full = _norm_literal(req["text"] + req["head"] + "".join(req.get("instances", [])))
    for t in lookup_keys:
        for equiv in equivalences.get(t, []):
            if equiv and equiv in text_n:
                eq_hits.append((t, equiv))
    if not eq_hits:
        for k in equivalences:
            if len(k) >= 2 and k in req_full:
                for equiv in equivalences[k]:
                    if equiv and equiv in text_n:
                        eq_hits.append((k, equiv))
    # ③ 语义桥兜底（用户 2026-10-25 决议）：要求词与表键 bge 词级 cos≥阈值 →
    # 表键视作统一标签，其人工核验值链复用（证据侧不引入新碰词面）
    bridge_hit = False
    if not eq_hits and bridge_keys:
        for k, _cos in bridge_keys:
            for equiv in equivalences.get(k, []):
                if equiv and equiv in text_n:
                    eq_hits.append((k, equiv))
                    bridge_hit = True
    if eq_hits:
        # deduct 条目（用户 D组决议）：受众错位映射按 0.8 计
        deduct_set = _load_deduct_set()
        if any((k, ev) in deduct_set for (k, ev) in eq_hits):
            return {"relation": "equivalent", "value": config.COVERAGE_DEDUCTION_VALUE,
                    "hit_terms": [ev for (_, ev) in eq_hits],
                    "note": "经核验等价表命中（D组受众错位，按 0.8 酌情减分）"}
        if bridge_hit:
            src = "；".join(f"{k}({c:.2f})" for k, c in (bridge_keys or []) if any(
                ev in text_n for ev in equivalences.get(k, [])))
            return {"relation": "equivalent", "value": COVERAGE_RELATION_VALUES["equivalent"],
                    "hit_terms": [ev for (_, ev) in eq_hits],
                    "note": f"语义桥激活表键 {src}→值链复用（与字面同档）"}
        return {"relation": "equivalent", "value": COVERAGE_RELATION_VALUES["equivalent"],
                "hit_terms": [ev for (_, ev) in eq_hits],
                "note": "经核验等价表命中（与字面同档，无字面加成）"}
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


def head_lookup_keys(req: dict) -> list[str]:
    """等价表查找键全集（引擎与 Day6-7 裁决脚本共用，防口径漂移）：
    短 head 整体 + 全部实例归一词 + 长 head 的分段子词（逗号切分、剥动词头、≥2 字）。"""
    keys = _head_core_terms(req["head"])
    keys += [_norm_literal(t) for t in req.get("instances", []) if _norm_literal(t)]
    h = _norm_literal(req["head"])
    if len(h) > 6:
        seg_raw = re.split(r"[，。；、]", req["head"])
        for seg in seg_raw:
            seg2 = _REQ_PREFIX_RE.sub("", seg.strip()).strip()
            n = _norm_literal(seg2)
            if len(n) >= 2 and n not in keys:
                keys.append(n)
    return list(dict.fromkeys(keys))


# ── §2.4 覆盖评分 + §2.5 证据矩阵 ────────────────────────────────
def _load_deduct_set() -> set:
    """等价表 deduct 条目集合（懒读文件；无文件/异常→空集，测试 monkeypatch 路径友好）。"""
    p = getattr(config, "COVERAGE_EQUIVALENCE_PATH", None)
    if not p or not Path(p).exists():
        return set()
    try:
        data = json.loads(Path(p).read_text(encoding="utf-8"))
        return {tuple(x) for x in (data.get("deduct") or []) if isinstance(x, (list, tuple)) and len(x) == 2}
    except Exception:
        return set()


class SemanticBridgeIndex:
    """语义桥索引：表键词向量矩阵（懒构建一次；测试注入 encode_fn 时同样构建）。

    桥的职责=「要求词 → 已核验表键」的对接（用户 2026-10-25 决议）：
    cos ≥ COVERAGE_SEMANTIC_BRIDGE_THRESHOLD 的表键被视作统一标签激活，
    其人工核验值链全部复用；证据侧不引入新碰词面。仅 professional 类要求。
    """

    def __init__(self, equivalences: dict[str, list[str]], encode_fn=None):
        from utils.label_embedding import encode_labels as _enc

        self.keys = [k for k in equivalences if k]
        # 编码器绑定实例（同 EvidenceIndex 契约）：构建用哪个编码器，激活也用它
        self.encode_fn = encode_fn if encode_fn is not None else (lambda xs: _enc(list(xs)))
        mat = np.asarray(self.encode_fn(self.keys), dtype=float)
        nrm = np.linalg.norm(mat, axis=1, keepdims=True)
        self.matrix = mat / np.where(nrm == 0, 1.0, nrm)

    def activate(self, terms: list[str], threshold: float | None = None,
                 top_k: int = 3) -> list[tuple[str, float]]:
        """terms（要求侧词）→ [(表键, cos)]，按 cos 降序，仅 ≥threshold，≤top_k。"""
        if not self.keys or not terms:
            return []
        th = threshold if threshold is not None else getattr(
            config, "COVERAGE_SEMANTIC_BRIDGE_THRESHOLD", 0.72)
        q = np.asarray(self.encode_fn(terms), dtype=float)
        nrm = np.linalg.norm(q, axis=1, keepdims=True)
        q = q / np.where(nrm == 0, 1.0, nrm)
        best = (q @ self.matrix.T).max(axis=0)  # 每表键取 terms 内最高 cos
        order = np.argsort(-best)[:top_k]
        return [(self.keys[i], float(best[i])) for i in order if best[i] >= th]


def load_atomic_splits() -> dict[str, list[str]]:
    """等价表 atomic_splits：复合要求词 → 原子能力列表（用户 A组拆解决议）。"""
    p = getattr(config, "COVERAGE_EQUIVALENCE_PATH", None)
    if not p or not Path(p).exists():
        return {}
    try:
        data = json.loads(Path(p).read_text(encoding="utf-8"))
        return {k: v for k, v in (data.get("atomic_splits") or {}).items()
                if isinstance(v, list) and v}
    except Exception:
        return {}


# ── 两类划分（用户 2026-10-24 五决议 + 划界准则表；用户 83 条裁决为回归闸门）──
# 判定次序（用户准则）：①专业名词命中 → professional（最优先）；
# ②行为词典命中 head → behavioral；③兜底 professional（拿不准宁归专业——
# 专业池为空是更严重症状）。「有XX经验者优先」等经验类归 professional。
_BEHAVIOR_EXTRA = (
    "沟通", "协作", "团队", "激励", "倾听", "表达", "协调", "跨部门", "学习",
    "担当", "影响力", "带动", "骨干", "意识", "态度", "靠谱", "自驱", "成长",
    "适应", "亲和", "反馈", "迁移", "敏捷", "推动", "按时", "闭环意识",
)
# 专业词根补充（T1 标签库 + T0 注册表之外的裁决覆盖，来源=用户改判 22 条归纳）
_PROFESSIONAL_EXTRA = (
    "内审", "数据治理", "调度", "数据集成", "方案设计", "进度管理", "员工关系",
    "取数", "建模", "端到端", "部署", "架构", "系统集成", "风险矩阵", "内控",
    "审计", "测评", "职称", "师者优先", "经验者优先",
)
# 毒词剔除（用户 83 条裁决校准）：这些词或是领域语境词（智能制造/数据分析/项目管理
# ——只该在实例枚举里算专业），或是 T2 行为关键词混入（交付/合规/可靠性/敏捷/培训
# ——留在行为词典），或是工艺过程词（试制/质量管控）。命中不算专业信号。
_PROFESSIONAL_EXCLUDE = frozenset((
    "交付", "试制", "合规", "可靠性", "敏捷", "培训", "质量管控",
    "智能制造", "数据分析", "项目管理", "人力资源",
))
_behavior_lexicon: set[str] | None = None
_professional_strong: set[str] | None = None
_professional_weak: set[str] | None = None


def _get_behavior_lexicon() -> set[str]:
    """T2 标签库名称+关键词 ∪ 行为词根补充（确定性，懒加载一次）。"""
    global _behavior_lexicon
    if _behavior_lexicon is not None:
        return _behavior_lexicon
    lex = set(_BEHAVIOR_EXTRA) | {"管控", "决策"}
    try:
        lib = json.loads((config.DATA_DIR / "standard_label_library_v1.json").read_text(encoding="utf-8"))
        for item in (lib.get("labels") or {}).get("T2_行为能力") or []:
            lex.add(_norm_literal(item.get("name", "")))
            for kw in item.get("keywords") or []:
                lex.add(_norm_literal(kw))
    except Exception:
        pass
    _behavior_lexicon = {w for w in lex if len(w) >= 2}
    return _behavior_lexicon


def _build_professional_lexicons() -> tuple[set[str], set[str]]:
    """专业词典两档（强/弱）。

    strong：具体专业名词/工具/方法/证书——T0 工具+知识体系（名称+别名）、
    T1 keywords、curated 词根。head 或 instances 命中即 professional。
    weak：领域语境词——T1 标签名、T0 行业领域名。仅在 instances（枚举清单）
    命中才算 professional；出现在 head 只作语境不算（「智能制造平台类项目的
    质量管控」的能力是管控行为，不是智能制造）。
    毒词（_PROFESSIONAL_EXCLUDE）两档全部剔除。
    """
    strong: set[str] = set(_PROFESSIONAL_EXTRA)
    weak: set[str] = set()
    try:
        lib = json.loads((config.DATA_DIR / "standard_label_library_v1.json").read_text(encoding="utf-8"))
        for item in (lib.get("labels") or {}).get("T1_专业能力") or []:
            weak.add(_norm_literal(item.get("name", "")))
            for kw in item.get("keywords") or []:
                strong.add(_norm_literal(kw))
        t0 = json.loads((config.DATA_DIR / "t0_registries.json").read_text(encoding="utf-8"))
        for item in t0.get("TOOL_REGISTRY") or []:
            strong.add(_norm_literal(item.get("name", "")))
            for a in item.get("aliases") or []:
                strong.add(_norm_literal(a))
        for item in t0.get("KNOWLEDGE_REGISTRY") or []:
            strong.add(_norm_literal(item.get("name", "")))
            for a in item.get("aliases") or []:
                strong.add(_norm_literal(a))
        for item in t0.get("DOMAIN_REGISTRY") or []:
            weak.add(_norm_literal(item.get("name", "")))
            for a in item.get("aliases") or []:
                weak.add(_norm_literal(a))
    except Exception:
        pass
    strong = {w for w in strong if len(w) >= 2 and w not in _PROFESSIONAL_EXCLUDE}
    weak = {w for w in weak if len(w) >= 2 and w not in _PROFESSIONAL_EXCLUDE} - strong
    return strong, weak


def _get_professional_lexicons() -> tuple[set[str], set[str]]:
    global _professional_strong, _professional_weak
    if _professional_strong is None:
        _professional_strong, _professional_weak = _build_professional_lexicons()
    return _professional_strong, _professional_weak


def requirement_type(req: dict) -> str:
    """要求二分类（用户划界准则 2026-10-24，83 条裁决=回归闸门 verify_typing_adjudication.py）。

    ①强专业名词命中（head 或实例；T0 工具/知识体系 + T1 keywords + 词根）
      或 弱领域词命中实例（枚举清单）→ professional——「质量管理体系（ISO9001）」
      「Spark/Flink 等大数据调度组件」归此类；
    ②行为词典命中 head → behavioral——含 T2 全部名称/关键词（交付/合规/可靠性/
      敏捷等双栖词以行为侧为准）；
    ③兜底 professional（拿不准宁归专业）。
    证据侧不隔离不打折（证据天然多面）。
    """
    h = _norm_literal(req.get("head") or "")
    inst = _norm_literal("".join(str(x) for x in (req.get("instances") or [])))
    strong, weak = _get_professional_lexicons()
    if any(w in h for w in strong) or any(w in inst for w in strong | weak):
        return "professional"
    lex = _get_behavior_lexicon()
    if any(w in h for w in lex):
        return "behavioral"
    return "professional"


def job_weight_triple(job_type: str | None) -> tuple[float, float, float]:
    """四类职业权重矩阵选档（W1 专业, W2 行为, W3 潜力，百分数）。

    来源=开题报告《五层匹配评分体系细化方案_2026-07-24.md》§2.8.1；
    职能类（管理职能）映射Ⅲ管理领导档；未识别用 _default。
    """
    matrix = getattr(config, "COVERAGE_JOB_WEIGHT_MATRIX", {})
    key = str(job_type or "").strip()
    if key in matrix:
        return tuple(float(x) for x in matrix[key])
    return tuple(float(x) for x in matrix.get("_default", (45.0, 35.0, 20.0)))


def _expand_requirements(reqs: list[dict], splits: dict[str, list[str]]) -> list[dict]:
    """A组原子拆解（用户核验决议）：含复合词的要求 → 等权原子子要求。

    匹配半边经等价表命中计分；舍弃半边无表项、走常规通道（通常保持未证实）——
    防止「半匹配」按整要求计满分污染排名。Σw 不变（原子权重 = 原权重/原子数）。
    """
    if not splits:
        return reqs
    out: list[dict] = []
    for r in reqs:
        h = _norm_literal(r["head"])
        compound = next((c for c in splits if c and c in h), None)
        if compound is None:
            out.append(r)
            continue
        atomics = splits[compound]
        for i, a in enumerate(atomics):
            out.append({**r, "rid": f"{r['rid']}-{chr(97 + i)}", "text": a, "head": a,
                        "instances": [], "either_ok": True,
                        "weight": round(float(r["weight"]) / len(atomics), 4),
                        "atomic_of": compound})
    return out


def score_coverage(
    requirements: list[dict],
    employees: list[dict],
    index,  # EvidenceIndex
    cross_encoder_fn=None,
    equivalences: dict[str, list[str]] | None = None,
    encode_fn=None,
    atomic_splits: dict[str, list[str]] | None = None,
    job_type: str | None = None,
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
    # A组原子拆解（用户核验决议）：含复合词的要求 → 等权原子子要求（Σw 不变）
    if atomic_splits is None:
        atomic_splits = load_atomic_splits()
    reqs = _expand_requirements(reqs, atomic_splits)
    # 两类划分（behavioral/professional）；必须/优先为正交维度 kind
    for r in reqs:
        r["rtype"] = requirement_type(r)
    equiv = equivalences if equivalences is not None else load_verified_equivalences()
    chunk_emp = np.array([c["emp_id"] for c in index.chunks]) if len(index.chunks) else np.array([])
    query_vecs = encode_query_texts([r["text"] for r in reqs], encode_fn)
    if query_vecs is None or query_vecs.size == 0:
        return {}
    w1, w2, w3 = job_weight_triple(job_type)
    # 语义桥：表键向量索引（懒构建一次）+ 每条 professional 要求的桥激活（req 级一次）
    bridge_keys_by_rid: dict[str, list[tuple[str, float]]] = {}
    if getattr(config, "COVERAGE_SEMANTIC_BRIDGE_ENABLED", True):
        try:
            bridge = SemanticBridgeIndex(equiv, encode_fn=encode_fn)
            for r in reqs:
                if r.get("rtype") == "professional":
                    keys = bridge.activate(head_lookup_keys(r))
                    if keys:
                        bridge_keys_by_rid[r["rid"]] = keys
        except Exception:
            bridge_keys_by_rid = {}  # 桥失败不阻断主链路（fail-open 到无桥口径）
    # 分池索引：专业必须 / 行为必须 / 优先项（加分池，不进加权求和）
    prof_must = [r for r in reqs if r["rtype"] == "professional" and r["kind"] == "necessary"]
    behav_must = [r for r in reqs if r["rtype"] == "behavioral" and r["kind"] == "necessary"]
    preferred_reqs = [r for r in reqs if r["kind"] == "preferred"]
    n_must = len(prof_must) + len(behav_must)

    out: dict[str, dict] = {}
    for emp in employees:
        eid = str(emp.get("employee_id", ""))
        if not eid:
            continue
        idxs = np.where(chunk_emp == eid)[0] if chunk_emp.size else []
        emp_chunks = [index.chunks[i] for i in idxs]
        emp_vecs = index.matrix[idxs] if len(idxs) else np.array([])
        p = score_t3_potential(emp)  # P 潜力基座（W3 列；B 基座已并入行为类实测，取消）
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
        for req in reqs:
            cands = all_cands[req["rid"]]
            best: dict | None = None
            best_cls: dict | None = None
            best_key: tuple = (-1.0, 0)
            for c in cands:
                cls = classify_relation(req, c, equiv,
                                        bridge_keys=bridge_keys_by_rid.get(req["rid"]))
                # v=max；同分时矛盾标记优先于仅相关（§2.3 不被高相似度覆盖）
                key = (cls["value"], 1 if cls["relation"] == "contradiction" else 0)
                if key > best_key:
                    best, best_cls, best_key = c, cls, key
                if cls["value"] >= 1.0:
                    break  # v=max：已达上限，后续候选不再改变该要求贡献
            v = best_cls["value"] if best_cls else 0.0
            req_results[req["rid"]] = {
                "v": v,
                "relation": best_cls["relation"] if best_cls else "no_candidate",
                "note": best_cls["note"] if best_cls else "无候选证据",
                "hit_terms": best_cls["hit_terms"] if best_cls else [],
                "evidence": [_ev_row(c, best_cls) for c in cands],
            }
        # 分池聚合（两类 × 必须项加权覆盖；优先项走加分池不进加权）
        def _pool_score(pool: list[dict]) -> float | None:
            if not pool:
                return None
            ws = sum(float(r["weight"]) for r in pool)
            wv = sum(float(r["weight"]) * req_results[r["rid"]]["v"] for r in pool)
            return wv / ws if ws else 0.0

        s_prof_raw = _pool_score(prof_must)
        s_behav_raw = _pool_score(behav_must)
        s_prof = 0.5 if s_prof_raw is None else s_prof_raw          # 空类中性（缺失层惯例）
        s_behav = 0.5 if s_behav_raw is None else s_behav_raw
        s_prof_flagged = s_prof_raw is None
        s_behav_flagged = s_behav_raw is None
        # 全部必须项综合覆盖（展示连续性字段）
        must_all = prof_must + behav_must
        coverage = (lambda ws: (sum(float(r["weight"]) * req_results[r["rid"]]["v"] for r in must_all) / ws) if ws else 0.0)(
            sum(float(r["weight"]) for r in must_all))
        # 优先项加分（原案 §2.6 加分制）：bonus = k × Σ(优先项 v) / max(1, N_must)
        bonus = (getattr(config, "COVERAGE_PREFERRED_K", 2.0)
                 * sum(req_results[r["rid"]]["v"] for r in preferred_reqs)
                 / max(1, n_must)) if preferred_reqs else 0.0
        # total = [W1·S_prof + W2·S_behav + W3·P] + bonus（W 百分数 × S∈[0,1] → 满分 100）
        total = w1 * s_prof + w2 * s_behav + w3 * p + bonus
        # 闸门（用户 2026-10-25 指令）：专业必须项缺 k 项 → total ×(1-0.05k)，封 0；
        # 行为类必须项不触发
        gate_rids = [r["rid"] for r in prof_must
                     if req_results[r["rid"]]["v"] <= 0.0 + 1e-9]
        step = getattr(config, "COVERAGE_GATE_STEP", 0.05)
        gate_coef = max(0.0, 1.0 - step * len(gate_rids))
        gate_info = ({"k": len(gate_rids), "coef": round(gate_coef, 4),
                      "rids": gate_rids} if gate_rids else None)
        if gate_rids:
            total *= gate_coef
        out[eid] = {
            "total": round(total, 2),
            "coverage": round(coverage, 4),
            "s_prof": round(s_prof, 4),
            "s_behav": round(s_behav, 4),
            "p": round(p, 4),
            "bonus": round(bonus, 4),
            "w_matrix": [w1, w2, w3],
            "class_neutral": [c for c, f in (("professional", s_prof_flagged), ("behavioral", s_behav_flagged)) if f] or None,
            "required_skill_gate": gate_info,
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
