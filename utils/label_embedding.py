"""标签 Embedding 验证器 + 纠正器。

角色（第二周开发指南）：
- LLM 提议标签 → Embedding 验证 → 验证失败则 Embedding 自动纠正（不额外调 LLM）
- 五层方案 §0：T0（工具/领域/知识）已融合进 T1 专业能力层，corpus 不再有独立 tier="T0"。
  registry 项 tier="T1_专业能力"，用 category（tool/domain/knowledge）区分来源。

四个公共函数：
- get_embedding_model()：单例懒加载（双检锁，动态读 config）
- encode_labels(label_texts, encode_fn=None)：线程安全 LRU 缓存编码
- verify_mapping(concept, proposed_label, label_corpus, ...)：验证器+纠正器三路径
- load_label_corpus(path=None)：加载标签库 JSON + 显性条件注册表，构造 corpus

消费者：agents/profile_generation.py Phase 0 加载 corpus，Phase 1 每标签 verify_mapping。
"""

from __future__ import annotations

import json
import threading

import cachetools
import numpy as np

import config

__all__ = [
    "get_embedding_model",
    "encode_labels",
    "verify_mapping",
    "load_label_corpus",
]


# ── 单例模型（双检锁，F4: 每次访问检查 config 变化）──
_model_lock = threading.Lock()
_model_instance = None
_model_name_cached = ""


def get_embedding_model():
    """单例 TextEmbedding，双检锁，动态读 config.EMBEDDING_MODEL_NAME。

    首次加载 ~95MB，fastembed 缓存到 ~/.cache/fastembed。
    运行时改 config.EMBEDDING_MODEL_NAME → 下次调用重建单例。
    """
    global _model_instance, _model_name_cached
    current_name = config.EMBEDDING_MODEL_NAME  # 动态读，不冻结 import 值
    if _model_instance is None or _model_name_cached != current_name:
        with _model_lock:
            if _model_instance is None or _model_name_cached != current_name:
                from fastembed import TextEmbedding

                _model_instance = TextEmbedding(model_name=current_name)
                _model_name_cached = current_name
    return _model_instance


def _embed(texts: list[str]) -> np.ndarray:
    """内部编码：用单例模型。"""
    model = get_embedding_model()
    return np.array(list(model.embed(texts)))


# ── 线程安全 LRU 缓存（cachetools + Lock，决策 1）──
_cache = cachetools.LRUCache(maxsize=config.EMBEDDING_CACHE_SIZE)
_cache_lock = threading.Lock()


@cachetools.cached(_cache, lock=_cache_lock)
def _cached_encode(texts_tuple: tuple) -> np.ndarray:
    """真实路径缓存编码。入参 tuple（可哈希）。"""
    if not texts_tuple:
        return np.array([])
    return _embed(list(texts_tuple))


def encode_labels(label_texts, encode_fn=None) -> np.ndarray:
    """编码标签列表为 2D ndarray。

    Args:
        label_texts: tuple[str, ...] 或 list[str]，标签文本。
        encode_fn: 可选编码函数 list[str]->np.ndarray，测试注入确定性 fake。
            None → 用单例模型 + LRU 缓存（真实路径）。

    Returns:
        np.ndarray shape (N, dim)；空输入返回 shape (0,)。

    线程安全：真实路径走 _cached_encode（cachetools+Lock）；测试路径不走共享缓存。
    """
    # C3 守卫：单字符串误传时包成单元素 tuple（tuple("AAA") 会逐字符拆分）
    if isinstance(label_texts, str):
        label_texts = (label_texts,)
    texts_tuple = (
        tuple(label_texts) if not isinstance(label_texts, tuple) else label_texts
    )
    if not texts_tuple:
        return np.array([])
    if encode_fn is not None:
        # 测试路径：不污染共享缓存
        return np.array(encode_fn(list(texts_tuple)))
    return _cached_encode(texts_tuple)


def _cosine_batch(query_vec: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    """query_vec (dim,) vs matrix (N, dim) → sims (N,)。零向量→0.0。"""
    if matrix.size == 0:
        return np.array([])
    q = np.asarray(query_vec, dtype=float)
    m = np.asarray(matrix, dtype=float)
    if q.ndim == 1:
        q = q.reshape(1, -1)
    if m.ndim == 1:
        m = m.reshape(1, -1)
    q_norm = np.linalg.norm(q, axis=1)
    m_norm = np.linalg.norm(m, axis=1)
    # 避免除零
    denom = np.outer(q_norm, m_norm)
    with np.errstate(divide="ignore", invalid="ignore"):
        sims = (q @ m.T) / denom
    sims = np.nan_to_num(sims, nan=0.0, posinf=0.0, neginf=0.0)
    return sims[0]  # 返回 (N,)


def verify_mapping(
    concept: str,
    proposed_label: str,
    label_corpus: list[dict],
    threshold: float = None,
    margin: float = None,
    encode_fn=None,
) -> dict:
    """验证 LLM 提议的标签映射，失败则 Embedding 纠正。

    流程（第二周指南 Task 1.3 §1-7）：
      Phase A 名称解析：
        - name 精确匹配 → resolved=label，name_source="exact"
        - 未找到 → Embedding 模糊匹配标签名
          → best_name_sim ≥ threshold → resolved=最相似标签，name_source="embedding_corrected_renamed"
          → < threshold → label_not_found（pending）
      Phase B 概念验证（concept vs resolved.text，并与全 corpus 比对取 top1/top2）：
        - resolved 是 top1 且 sim≥threshold 且 margin≥margin → verified
          （name_source="renamed"→"embedding_corrected_renamed"，否则"llm_proposed:verified"）
        - top1 是其他标签且 best_sim≥threshold → embedding_corrected（corrected_label=top1.name）
        - resolved 是 top1 但 margin<margin（相似第二名逼近）→ low_margin pending
        - best_sim<threshold → both_low pending

    Args:
        concept: 员工能力概念（LLM 自由文本）。
        proposed_label: LLM 提议的标准标签名。
        label_corpus: load_label_corpus() 返回的 corpus 列表。
        threshold: 相似度绝对下限，None→config.EMBEDDING_MIN_SIM。
        margin: top1-top2 最小差值，None→config.EMBEDDING_MARGIN。
        encode_fn: 测试注入 fake 编码函数。

    Returns:
        C1 对称：所有路径返回相同顶层 key 集合
        {verified, similarity, mapping_source, pending_review, corrected_label}
        非纠正路径 corrected_label=None、pending_review=False。
    """
    # 默认值动态读 config（F4: 不冻结 import 值）
    if threshold is None:
        threshold = config.EMBEDDING_MIN_SIM
    if margin is None:
        margin = config.EMBEDDING_MARGIN

    # C1 对称契约的默认返回结构
    # 路径 key 集合：{verified, similarity, mapping_source, pending_review, corrected_label}

    # C3 守卫：空输入
    if not label_corpus or not proposed_label or not concept:
        return {
            "verified": False,
            "similarity": 0.0,
            "mapping_source": "label_not_found",
            "pending_review": True,
            "corrected_label": None,
        }

    # ── Phase A: 名称解析 ──
    resolved = None
    name_source = "exact"
    for item in label_corpus:
        if item.get("name") == proposed_label:
            resolved = item
            break

    if resolved is None:
        # Embedding 模糊匹配标签名
        names = [item.get("name", "") for item in label_corpus]
        name_vecs = encode_labels(tuple(names), encode_fn=encode_fn)
        proposed_name_vec = encode_labels((proposed_label,), encode_fn=encode_fn)
        if proposed_name_vec.size == 0 or name_vecs.size == 0:
            return {
                "verified": False,
                "similarity": 0.0,
                "mapping_source": "label_not_found",
                "pending_review": True,
                "corrected_label": None,
            }
        name_sims = _cosine_batch(proposed_name_vec[0], name_vecs)
        best_name_idx = int(np.argmax(name_sims))
        best_name_sim = float(name_sims[best_name_idx])
        if best_name_sim >= threshold:
            resolved = label_corpus[best_name_idx]
            name_source = "embedding_corrected_renamed"
        else:
            return {
                "verified": False,
                "similarity": best_name_sim,
                "mapping_source": "label_not_found",
                "pending_review": True,
                "corrected_label": None,
            }

    # ── Phase B: 概念验证 ──
    concept_vec = encode_labels((concept,), encode_fn=encode_fn)
    texts = [item.get("text", "") for item in label_corpus]
    text_vecs = encode_labels(tuple(texts), encode_fn=encode_fn)
    if concept_vec.size == 0 or text_vecs.size == 0:
        return {
            "verified": False,
            "similarity": 0.0,
            "mapping_source": "both_low",
            "pending_review": True,
            "corrected_label": None,
        }

    sims = _cosine_batch(concept_vec[0], text_vecs)
    best_idx = int(np.argmax(sims))
    best_sim = float(sims[best_idx])
    # top1-top2 margin
    sorted_desc = np.sort(sims)[::-1]
    top2_sim = float(sorted_desc[1]) if len(sorted_desc) > 1 else 0.0
    actual_margin = best_sim - top2_sim

    resolved_idx = next(
        (i for i, item in enumerate(label_corpus) if item.get("name") == resolved.get("name")),
        0,
    )
    resolved_sim = float(sims[resolved_idx])

    # ── 分支决策 ──
    if best_sim < threshold:
        # 全 corpus 无足够相似标签
        return {
            "verified": False,
            "similarity": best_sim,
            "mapping_source": "both_low",
            "pending_review": True,
            "corrected_label": None,
        }
    if resolved_idx == best_idx and actual_margin >= margin:
        # 提议标签是清晰 top1
        return {
            "verified": True,
            "similarity": best_sim,
            "mapping_source": (
                "embedding_corrected_renamed"
                if name_source == "embedding_corrected_renamed"
                else "llm_proposed:verified"
            ),
            "pending_review": False,
            "corrected_label": None,
        }
    if resolved_idx == best_idx and actual_margin < margin:
        # 提议是 top1 但第二名逼近（歧义）→ 待人工
        return {
            "verified": False,
            "similarity": best_sim,
            "mapping_source": "low_margin",
            "pending_review": True,
            "corrected_label": None,
        }
    # top1 是其他标签 → 纠正
    return {
        "verified": True,
        "similarity": best_sim,
        "mapping_source": "embedding_corrected",
        "pending_review": False,
        "corrected_label": label_corpus[best_idx].get("name"),
    }


# ── 标签库加载 ──
_TIER_DEFAULT_CATEGORY = {
    "T1_专业能力": "skill",
    "T2_行为能力": "behavior",
    "T3_发展潜力": "potential",
}


# ── 能力等级双框架映射（双层三通道方案 §2.3，Step 1.2）──
# IT 类 T1：SFIA 0-7 → ability_score = sfia_level × (100/7)，取整
# 非 IT 类 T1：通用能力等级 1-5 → ability_score = (level-1) × 25
# T2 沿用 SFIA：调用方须传 is_it_label=True 强制走 SFIA 框架（§2.3 "T2 沿用 SFIA 复用"）
# D2：IT 标签集合来源 config.IT_T1_TAG_NAMES，本函数只做映射不持有标签分类
def _clamp_int(v, lo, hi, default=None):
    """夹紧整数到 [lo, hi]；非法值返回 default（default=None 时返回 lo）。"""
    try:
        x = int(v)
    except (TypeError, ValueError):
        return lo if default is None else default
    return max(lo, min(hi, x))


def clamp_int(v, lo, hi):
    """公共整数夹紧（D2 单一来源）：跨模块复用，profile_generation._clamp_extract_ranges 消费。

    等价 _clamp_int(v, lo, hi, default=None)——非法值兜底下限 lo。
    """
    return _clamp_int(v, lo, hi)


def ability_score_from_level(label_name, sfia_level=None, general_level=None,
                             is_it_label=None):
    """据标签所属能力框架把等级映射为 ability_score（0-100 整数）。

    框架选择（§2.3）：
    - is_it_label 显式传入优先；否则查 config.IT_T1_TAG_NAMES 判定
    - is_it_label=True / IT 集合内：走 SFIA 框架，sfia_level × (100/SFIA_MAX_LEVEL)
      （T2 沿用 SFIA：调用方传 is_it_label=True）
    - is_it_label=False / 非 IT 集合：走通用能力框架，(general_level-1) × 25
    - 选定框架的 level 缺失 → 回退另一框架；都缺失 → 返回 0（C4 守卫，不崩）

    G（跨边界类型守卫）：label_name 非 str / level 非 int → 不崩，返回 0。
    """
    # G：label_name 守卫
    if not isinstance(label_name, str):
        return 0

    # 框架判定：显式参数 > 集合查表
    if is_it_label is None:
        is_it = label_name in config.IT_T1_TAG_NAMES
    else:
        is_it = bool(is_it_label)

    if is_it:
        # IT 类：SFIA 0-7 → 0-100
        level = sfia_level
        if level is None:
            level = general_level  # 回退非 IT 等级（语义不严格，仅防全空）
        if level is None:
            return 0
        clamped = _clamp_int(level, 0, config.SFIA_MAX_LEVEL)
        # ×(100/7)：用浮点算再取整，sfia=7 → 100，sfia=0 → 0
        score = round(clamped * (config.ABILITY_SCORE_MAX / config.SFIA_MAX_LEVEL))
        return max(config.ABILITY_SCORE_MIN, min(config.ABILITY_SCORE_MAX, score))
    else:
        # 非 IT 类：通用能力 1-5 → (level-1) × 25
        level = general_level
        if level is None:
            level = sfia_level  # 回退 SFIA 等级
        if level is None:
            return 0
        clamped = _clamp_int(level, 1, config.GENERAL_ABILITY_MAX_LEVEL)
        score = (clamped - 1) * 25
        return max(config.ABILITY_SCORE_MIN, min(config.ABILITY_SCORE_MAX, score))


def _derive_category(tier: str, name: str, keywords: list) -> str:
    """推导 category（仅用于标签库 T1/T2/T3 项）。

    v2.0：T1 扩展到 40 个细标签后，keywords 含"测试框架""EAP""内控"等词会误触发
    旧的 tool/knowledge 分流。双层架构下 T1 标签库项统一为 skill（专业能力技能），
    category 区分由 tier 决定不由 keywords 推导，符合"T1/T2/T3 独立抽取互不干涉"设计。

    注：显性条件注册表（工具/领域/知识）的 category 由来源直接决定
    （tool/domain/knowledge），不走本函数；五层方案 §0 这些项已融合进 T1 层，
    tier="T1_专业能力"，仅用 category 区分来源，不再独立为 T0 tier。
    """
    return _TIER_DEFAULT_CATEGORY.get(tier, "skill")


def _load_registry_corpus(path) -> list[dict]:
    """加载显性条件注册表（工具/行业领域/知识体系），构造 T1 层 corpus 项。

    五层方案 §0：T0 已融合进 T1 专业能力层。registry 项 tier="T1_专业能力"，
    用 category（tool/domain/knowledge）区分来源，与标签库 T1 项（category="skill"）
    同 tier 不同 category。corpus 项结构与 T1/T2/T3 同
    （{tier,name,text,category,definition,keywords}），保证 verify_mapping /
    encode_labels 消费者无感知。

    - text = f"{name}: {aliases joined}"（aliases 作为同义语料，提升 Embedding 命中）
    - definition = typical_use or ""（DOMAIN_REGISTRY 无 typical_use → definition=""）
    - keywords = aliases（供 _llm_extract prompt 展示同义词）
    - category 由 registry 来源直接决定（tool/domain/knowledge），不走 _derive_category
    """
    with open(path, encoding="utf-8-sig") as f:  # C9
        data = json.load(f)

    # G: 跨边界类型守卫
    if not isinstance(data, dict):
        raise ValueError(
            f"invalid explicit registries: expected dict, got {type(data).__name__}"
        )

    registry_to_category = {
        "TOOL_REGISTRY": "tool",
        "DOMAIN_REGISTRY": "domain",
        "KNOWLEDGE_REGISTRY": "knowledge",
    }
    corpus: list[dict] = []
    for reg_key, category in registry_to_category.items():
        items = data.get(reg_key)
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            name = item.get("name", "")
            if not name:
                continue
            aliases = item.get("aliases", []) or []
            # 守卫 aliases 元素类型（C4）：非 str 元素 str() 化，防 join 崩
            alias_strs = [a if isinstance(a, str) else str(a) for a in aliases]
            typical_use = item.get("typical_use") or ""
            # text 含 name + aliases，提升 Embedding 模糊匹配召回
            text_parts = [name] + [a for a in alias_strs if a and a != name]
            text = f"{name}: {' / '.join(text_parts[1:])}" if len(text_parts) > 1 else name
            corpus.append(
                {
                    "tier": "T1_专业能力",
                    "name": name,
                    "text": text,
                    "category": category,
                    "definition": typical_use,
                    "keywords": alias_strs,
                }
            )
    return corpus


def load_label_corpus(path=None) -> list[dict]:
    """加载标准标签库 JSON，构造 corpus。

    Args:
        path: 标签库 JSON 路径，None→config.LABEL_LIBRARY_PATH。
            当 path 显式给定（测试 fixture）时，**不合并显性条件注册表**，保证测试隔离；
            当 path is None（生产默认）时，合并 config.T0_REGISTRIES_PATH 的注册表项
            （工具/领域/知识），融合进 T1 层（tier="T1_专业能力"，category 区分来源）。

    Returns:
        [{tier, name, text, category, definition, keywords}, ...]
        T1/T2/T3 标签库项在前（text=f"{name}: {definition}"，category 由 _derive_category 推导），
        显性条件注册表项在后（tier="T1_专业能力"，text=f"{name}: {aliases}"，
        category 为 tool/domain/knowledge）。
    """
    lib_path = path if path is not None else config.LABEL_LIBRARY_PATH
    with open(lib_path, encoding="utf-8-sig") as f:  # C9: 显式 encoding
        data = json.load(f)

    # G: 跨边界类型守卫
    if not isinstance(data, dict):
        raise ValueError(
            f"invalid label library: expected dict, got {type(data).__name__}"
        )
    labels = data.get("labels")
    if not isinstance(labels, dict):
        raise ValueError(
            f"invalid labels field: expected dict, got {type(labels).__name__}"
        )

    corpus: list[dict] = []
    for tier, items in labels.items():
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            name = item.get("name", "")
            definition = item.get("definition", "")
            keywords = item.get("keywords", []) or []
            text = f"{name}: {definition}"
            corpus.append(
                {
                    "tier": tier,
                    "name": name,
                    "text": text,
                    "category": _derive_category(tier, name, keywords),
                    "definition": definition,
                    "keywords": keywords,
                }
            )

    # 五层方案 §0：生产默认路径合并显性条件注册表（工具/领域/知识），
    # 融合进 T1 层（tier="T1_专业能力"，category=tool/domain/knowledge）。
    # 测试 fixture 路径不合并，保证隔离。
    if path is None:
        reg_path = config.T0_REGISTRIES_PATH
        if reg_path and reg_path.exists():
            corpus.extend(_load_registry_corpus(reg_path))

    return corpus
