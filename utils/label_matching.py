"""三阶段标签匹配的 Stage 2 召回 + Stage 3 LLM 重排。

角色（三阶段重构 2026-07-26）：
- recall_top_k：embedding 从 corpus 取 top-K 候选名（Stage 2，召回角色）
- rerank_label_llm：LLM 看 concept + top-3 候选 + 员工上下文 → 精排拍板（Stage 3）
- _apply_exact_match：快路径，LLM 提议标签精确匹配 corpus 名时跳过 LLM 重排

架构反转（vs 旧 verify_mapping）：
- 旧：embedding 自动纠正 LLM 的标签选择（5 害 1 助，净负 4）
- 新：embedding 只召回 top-K 候选，LLM 从候选里拍板或判新标签
- 业界共识（BLINK/TGRE/GoldenMatch/ESCO 管线/BGE 官方两阶段）：embedding 召回 + LLM 精排

消费者：agents/profile_generation.py execute Phase 1（每员工 _llm_extract → recall_top_k → rerank_label_llm）。
"""
from __future__ import annotations

import logging

import numpy as np

import config
from utils.label_embedding import _cosine_batch, encode_labels

logger = logging.getLogger(__name__)

__all__ = ["recall_top_k", "rerank_label_llm", "rerank_cross_encoder"]


def recall_top_k(
    concept: str,
    corpus: list[dict],
    corpus_text_vecs: np.ndarray | None = None,
    top_k: int | None = None,
    encode_fn=None,
) -> list[tuple[str, float]]:
    """Stage 2 召回：用 embedding 从 corpus 取 top-K 候选（name, sim）降序。

    Args:
        concept: 员工能力概念（LLM 抽取的自由文本）。
        corpus: load_label_corpus() 返回的 corpus 列表，每项含 name/text。
        corpus_text_vecs: 调用方预编码的 corpus 文本矩阵 (N, dim)，None→现场编码。
            生产路径由 execute Phase 0 编码一次传给所有员工复用，避免逐 concept 重算。
        top_k: 召回数，None→config.LABEL_RECALL_TOP_K。
        encode_fn: 测试注入 fake 编码函数（仿 label_embedding.encode_labels 用法）。

    Returns:
        [(name, sim), ...] 按 sim 降序，长度 min(top_k, len(corpus))。
        空 concept/空 corpus/空 vecs → []（C3 守卫）。
    """
    if top_k is None:
        top_k = config.LABEL_RECALL_TOP_K

    # C3 守卫
    if not concept or not corpus or top_k <= 0:
        return []

    concept_vec = encode_labels((concept,), encode_fn=encode_fn)
    if concept_vec.size == 0:
        return []

    # 预编码矩阵缺失 → 现场编码（复用 encode_labels LRU 缓存）
    if corpus_text_vecs is None:
        texts = [c.get("text", "") for c in corpus]
        corpus_text_vecs = encode_labels(tuple(texts), encode_fn=encode_fn)
    if corpus_text_vecs is None or corpus_text_vecs.size == 0:
        return []

    sims = _cosine_batch(concept_vec[0], corpus_text_vecs)
    if sims.size == 0:
        return []

    k = min(top_k, len(corpus))
    # np.argsort 升序 → 取末尾 k 后反转得降序 top-k
    order = np.argsort(sims)[::-1][:k]
    return [
        (corpus[int(i)].get("name", ""), float(sims[int(i)])) for i in order
    ]


# ════════════════════════════════════════════════════════════════════
# Stage 3: LLM 精排（替换旧 verify_mapping 的自动纠正）
# ════════════════════════════════════════════════════════════════════

# rerank 单项结果顶层 key 集合（C1 对称：所有路径相同）
_RERANK_ITEM_KEYS = frozenset({
    "idx", "matched_label", "is_new_label", "match_confidence",
    "rationale", "candidates_seen", "mapping_source",
})

# mapping_source 枚举
SOURCE_EXACT = "exact_name_match"
SOURCE_EXACT_DUP = "exact_name_match_dup"
SOURCE_EXACT_CONFIRMED = "exact_name_match_confirmed"  # cross-encoder 确认通过的 exact（P1：区分自动跳过，供实验统计真实触发）
SOURCE_LLM_RERANK = "llm_rerank"
SOURCE_NEW_LABEL = "new_label"
SOURCE_PENDING = "pending_review"
SOURCE_RERANK_FAILED = "rerank_failed_trust_llm"
SOURCE_NEW_CAPPED = "new_label_capped_trust_top1"
SOURCE_OFFLINE = "offline_skipped"
SOURCE_CORPUS_FAILED = "corpus_load_failed_trust_llm"
# cross-encoder 精排（Step 8c）
SOURCE_CROSS_RERANK = "cross_encoder_rerank"
SOURCE_CROSS_NEW_LABEL = "cross_encoder_new_label"
SOURCE_CROSS_PENDING = "cross_encoder_pending_review"
SOURCE_CROSS_FAILED_FALLBACK_LLM = "rerank_failed_fallback_llm"
# S1 LLM 终裁 + S8b 扩展（plan_t1_s1_s8_b3_implementation.md 第五节，D2 单一来源）
# 语义定死（防跨 agent 术语漂移）：confirmed = LLM 复核确认候选中有匹配（救回）；
# rejected = LLM 复核维持新标签判定（计入新标签 cap）。
SOURCE_CROSS_NEW_LLM_CONFIRMED = "cross_new_llm_confirmed"  # S1：LLM 终裁否决新标签判定，从候选救回
SOURCE_CROSS_NEW_LLM_REJECTED = "cross_new_llm_rejected"    # S1：LLM 终裁维持"无合适候选"（计入新标签 cap）
SOURCE_EXPANDED = "expanded_neighbor"                        # S8b：间接映射扩展项（profile_generation 导入消费）

_RERANK_BATCH_SIZE = 5  # items>10 时分批，防 prompt 过长


def _apply_exact_match(items: list[dict], corpus: list[dict]) -> dict:
    """快路径：standard_label 精确匹配 corpus name → 跳过 LLM 重排。

    Returns:
        {idx: "exact_name_match" | "exact_name_match_dup"} 命中索引映射。
        重名（corpus 内多个同名）标记 _dup 待人工审。
    """
    if not items or not corpus:
        return {}
    # corpus name → 出现次数（检测重名）
    name_counts: dict[str, int] = {}
    for c in corpus:
        n = c.get("name", "")
        if n:
            name_counts[n] = name_counts.get(n, 0) + 1
    matched = {}
    for i, item in enumerate(items):
        label = item.get("standard_label", "")
        if label and name_counts.get(label, 0) > 0:
            matched[i] = SOURCE_EXACT_DUP if name_counts[label] > 1 else SOURCE_EXACT
    return matched


def _build_rerank_prompt(items: list[dict], employee_context: dict) -> tuple[str, str]:
    """构造 Stage 3 重排 prompt（system, user）。

    仅含 concept + candidate names（不含 definition，省 token；def 已在 embedding 用）。
    约束 matched_label ∈ candidates ∪ {"NEW"}，不得创造第三值。
    """
    # 员工上下文摘要（紧凑，仅给 LLM 判断方向用）
    summary = (employee_context or {}).get("summary") or ""
    perf = (employee_context or {}).get("performance_history") or []
    perf_str = ""
    if isinstance(perf, list) and perf:
        # 取最近 2 条绩效的 grade
        grades = [str(p.get("performance_grade", "")) for p in perf if isinstance(p, dict)]
        if grades:
            perf_str = "；".join(grades[-2:])

    system = (
        "你是胜任力标签匹配专家。对每个概念，从给定的候选标准标签中选一个最匹配的，"
        "或判断候选中没有合适的需要新建标签。\n"
        "输出规则：\n"
        "1. matched_label 必须是该项 candidates 列表中的一个，或字面值 \"NEW\"（表示无合适候选）。"
        "不得输出 candidates 之外的任何标签名。\n"
        "2. match_confidence 为 0.0-1.0 浮点，表示你对这个匹配的置信度。\n"
        "3. rationale 简述理由（≤30字），说明为什么选这个或为何要新建。\n"
        "4. 输出 JSON 数组，每项含 {idx, matched_label, match_confidence, rationale}，"
        "idx 必须与输入对齐，顺序一致。"
    )

    lines = [f"员工摘要：{summary or '无'}", f"近期绩效：{perf_str or '无'}", "", "待匹配项："]
    for it in items:
        cands = it.get("candidates", [])
        lines.append(
            f"- idx={it['idx']} concept=\"{it.get('concept','')}\" "
            f"LLM提议=\"{it.get('standard_label','')}\" category={it.get('category','')} "
            f"candidates={cands}"
        )
    user = "\n".join(lines) + "\n\n请输出 JSON 数组。"
    return system, user


def _degrade_item(item: dict, mapping_source: str) -> dict:
    """确定性降级：信任 LLM 原始 standard_label，不重试（D6 防雪崩）。"""
    return {
        "idx": item.get("idx"),
        "matched_label": item.get("standard_label", ""),
        "is_new_label": False,
        "match_confidence": float(item.get("extract_confidence") or 0.0),
        "rationale": f"rerank 降级({mapping_source})，信任 LLM 原始提议",
        "candidates_seen": item.get("candidates", []),
        "mapping_source": mapping_source,
    }


def _parse_rerank_content(content, n_items: int) -> list[dict] | None:
    """解析 LLM 返回的 content 为 list[{idx, matched_label, ...}]。

    接受 list 或 dict 包裹的 list。返回 None 表示不可用（触发降级）。
    """
    if content is None:
        return None
    if isinstance(content, list):
        return content if len(content) == n_items else content  # 长度不符也返回，由调用方按 idx 对齐
    if isinstance(content, dict):
        # 找第一个 list 值
        for v in content.values():
            if isinstance(v, list):
                return v
    return None


def rerank_label_llm(
    items: list[dict],
    employee_context: dict,
    corpus: list[dict] | None = None,
    call_llm_json_fn=None,
    trust_exact_match: bool = True,
) -> list[dict]:
    """Stage 3 精排：LLM 看 concept + top-3 候选 + 员工上下文 → 拍板或判新标签。

    架构反转：embedding 只召回（Stage 2 已做），LLM 在候选里精排，不自动纠正。
    批量：一员工所有 to-rerank 项单次 LLM 调用（省成本）。

    Args:
        items: [{idx, concept, standard_label, category, candidates (list[str]),
                 extract_confidence}] 待匹配项。
        employee_context: 员工 dict（含 summary/performance_history 等供 LLM 判断方向）。
        corpus: 标签库 corpus，用于快路径精确名匹配。None→不启用快路径。
        call_llm_json_fn: 默认 utils.llm_client.call_llm_json，测试注入 fake。
        trust_exact_match: True（默认）→ standard_label 精确匹配 corpus name 时跳过 LLM
            （成本优化，信任 Stage 1 提议）。False → 强制全走 LLM 重排，用于 cross-encoder
            不可用时的降级路径——不无条件信任 Stage 1 提议，让 LLM 有机会纠正。

    Returns:
        list[dict] 与 items 同序，每项含
        {idx, matched_label, is_new_label, match_confidence, rationale,
         candidates_seen, mapping_source}（C1 对称：所有路径同 key 集合）。

    降级策略（D6 防雪崩，失败=确定性故障不重试）：
        - 空 items → 返回 []（不调 LLM）
        - LLM 调用返回 error / content 不可解析 → 每项 _degrade_item(trust standard_label)
        - 新标签超 LABEL_NEW_LABEL_MAX_PER_EMP → 超额项降级选 candidates[0]
    """
    # C3 守卫：空 items
    if not items:
        return []

    # 快路径：精确名匹配跳过 LLM（trust_exact_match=False 时禁用，强制全走 LLM 重排）
    exact_matched = _apply_exact_match(items, corpus) if (corpus and trust_exact_match) else {}
    results: list[dict | None] = [None] * len(items)
    to_rerank_indices = []
    for i, item in enumerate(items):
        if i in exact_matched:
            results[i] = {
                "idx": item.get("idx"),
                "matched_label": item.get("standard_label", ""),
                "is_new_label": False,
                "match_confidence": 1.0,
                "rationale": "LLM 提议标签精确匹配 corpus 名",
                "candidates_seen": item.get("candidates", []),
                "mapping_source": exact_matched[i],
            }
        else:
            to_rerank_indices.append(i)

    if not to_rerank_indices:
        # 全部快路径命中
        return [r for r in results if r is not None]  # type: ignore[return-value]

    # 分批（items>10 时每组 _RERANK_BATCH_SIZE）
    to_rerank_items = [items[i] for i in to_rerank_indices]
    batches = (
        [to_rerank_items]
        if len(to_rerank_items) <= 10
        else [to_rerank_items[i:i + _RERANK_BATCH_SIZE]
              for i in range(0, len(to_rerank_items), _RERANK_BATCH_SIZE)]
    )

    # 延迟导入避免循环（llm_client 不依赖本模块，但保持惰性符合 C10）
    if call_llm_json_fn is None:
        from utils.llm_client import call_llm_json as call_llm_json_fn  # noqa: E501

    rerank_results_by_idx: dict = {}
    for batch in batches:
        # 用 batch 内局部 idx 传入 prompt，映射回原 item idx
        prompt_items = [
            {**it, "idx": local_i} for local_i, it in enumerate(batch)
        ]
        system, user = _build_rerank_prompt(prompt_items, employee_context)
        try:
            resp = call_llm_json_fn(
                prompt=user, system_prompt=system,
                temperature=0.0,
                max_tokens=config.LABEL_RERANK_MAX_TOKENS,
                timeout=config.LABEL_RERANK_TIMEOUT,
            )
        except Exception as e:
            logger.warning("rerank LLM 调用异常: %s", e)
            resp = {"content": None, "error": f"exception: {e}"}

        content = resp.get("content") if isinstance(resp, dict) else None
        error = resp.get("error") if isinstance(resp, dict) else "non-dict response"
        parsed = _parse_rerank_content(content, len(batch)) if error is None else None

        if parsed is None:
            # D6 确定性降级：不重试，整批 trust standard_label
            logger.warning("rerank 解析失败（error=%s），整批降级 trust LLM", error)
            for local_i, it in enumerate(batch):
                rerank_results_by_idx[it.get("idx")] = _degrade_item(it, SOURCE_RERANK_FAILED)
            continue

        # 按 local idx 对齐解析结果
        by_local = {}
        for entry in parsed:
            if isinstance(entry, dict) and "idx" in entry:
                by_local[entry["idx"]] = entry
        for local_i, it in enumerate(batch):
            entry = by_local.get(local_i)
            if not isinstance(entry, dict):
                rerank_results_by_idx[it.get("idx")] = _degrade_item(it, SOURCE_RERANK_FAILED)
                continue
            matched = entry.get("matched_label")
            cands = it.get("candidates", [])
            # 守卫：matched 必须在 candidates 或 == "NEW"
            if matched == "NEW":
                rerank_results_by_idx[it.get("idx")] = _build_new_or_pending(it, entry, cands)
            elif isinstance(matched, str) and matched in cands:
                rerank_results_by_idx[it.get("idx")] = {
                    "idx": it.get("idx"),
                    "matched_label": matched,
                    "is_new_label": False,
                    "match_confidence": _clamp_conf(entry.get("match_confidence")),
                    "rationale": str(entry.get("rationale") or "") or "LLM 重排选择",
                    "candidates_seen": cands,
                    "mapping_source": SOURCE_PENDING if (
                        _clamp_conf(entry.get("match_confidence"))
                        < config.LABEL_RERANK_CONFIDENCE_THRESHOLD
                    ) else SOURCE_LLM_RERANK,
                }
            else:
                # matched 不合法（不在 candidates 也不是 NEW）→ 降级
                rerank_results_by_idx[it.get("idx")] = _degrade_item(it, SOURCE_RERANK_FAILED)

    # 新标签防滥：超额降级选 candidates[0]
    new_label_count = sum(
        1 for v in rerank_results_by_idx.values()
        if v.get("mapping_source") == SOURCE_NEW_LABEL
    )
    new_cap = config.LABEL_NEW_LABEL_MAX_PER_EMP
    if new_label_count > new_cap:
        over = 0
        for k, v in rerank_results_by_idx.items():
            if v.get("mapping_source") == SOURCE_NEW_LABEL:
                over += 1
                if over > new_cap:
                    cands = v.get("candidates_seen", [])
                    v["matched_label"] = cands[0] if cands else v.get("matched_label", "")
                    v["is_new_label"] = False
                    v["mapping_source"] = SOURCE_NEW_CAPPED
                    v["rationale"] = f"新标签超额({new_cap})，降级选 top1 候选"

    # 把 rerank 结果填回 results（保留原 items 顺序）
    for i, item in enumerate(items):
        if results[i] is None:
            results[i] = rerank_results_by_idx.get(item.get("idx")) or _degrade_item(
                item, SOURCE_RERANK_FAILED
            )

    # C1 对称：补齐所有 key
    return [{k: r.get(k) for k in _RERANK_ITEM_KEYS} for r in results]  # type: ignore[arg-type]


def _build_new_or_pending(it: dict, entry: dict, cands: list) -> dict:
    """LLM 返回 NEW 时的结果构造（受 confidence 阈值 + 新标签上限双重节制）。"""
    conf = _clamp_conf(entry.get("match_confidence"))
    is_new = conf >= config.LABEL_RERANK_CONFIDENCE_THRESHOLD
    return {
        "idx": it.get("idx"),
        "matched_label": it.get("concept", "") if is_new else (cands[0] if cands else ""),
        "is_new_label": is_new,
        "match_confidence": conf,
        "rationale": str(entry.get("rationale") or "") or "LLM 判定无合适候选",
        "candidates_seen": cands,
        "mapping_source": SOURCE_NEW_LABEL if is_new else SOURCE_PENDING,
    }


def _clamp_conf(v) -> float:
    """置信度夹紧 [0,1]，非数字→0.0。"""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, f))


# ════════════════════════════════════════════════════════════════════
# Stage 3: cross-encoder 精排（Step 8c，替换 zero-shot LLM 重排）
# ════════════════════════════════════════════════════════════════════

# 模块级 cross-encoder 单例（惰性加载，C10；加载失败→None 触发降级）
_cross_encoder = None
_cross_encoder_load_attempted = False


def _load_cross_encoder():
    """惰性加载 BGE-Reranker-v2-m3 cross-encoder 单例。

    优先 config.RERANKER_LOCAL_PATH（本地 git clone 目录），None→HF hub。
    加载失败返回 None（触发 rerank_cross_encoder 降级到 rerank_label_llm）。
    单次尝试（D6 确定性故障不重试，避免每员工重复加载耗时）。
    """
    global _cross_encoder, _cross_encoder_load_attempted
    if _cross_encoder_load_attempted:
        return _cross_encoder
    # 配置缺失：确定性故障（配置不会运行时变化）→ 缓存避免重复检查
    if not getattr(config, "RERANKER_FALLBACK_TO_LLM", True) is False and \
       not getattr(config, "RERANKER_MODEL_NAME", ""):
        logger.info("cross-encoder 未配置 RERANKER_MODEL_NAME，降级 LLM")
        _cross_encoder = None
        _cross_encoder_load_attempted = True
        return None
    try:
        # 惰性导入（torch 重，C10；测试可 mock 此函数）
        from sentence_transformers import CrossEncoder
        path = getattr(config, "RERANKER_LOCAL_PATH", None)
        model_name = path or getattr(config, "RERANKER_MODEL_NAME", "BAAI/bge-reranker-v2-m3")
        _cross_encoder = CrossEncoder(model_name)
        _cross_encoder_load_attempted = True  # 仅成功才缓存（D6：成功不重复加载）
        logger.info("cross-encoder 加载成功: %s", model_name)
    except Exception as e:
        # 加载异常可能临时性（冷启动/文件锁/首次下载）→ 不缓存，允许下次重试
        # D6 防雪崩针对 LLM 重试退避叠加；模型本地加载无退避叠加，重试成本可接受
        logger.warning("cross-encoder 加载失败（不缓存，下次调用重试），降级 zero-shot LLM: %s", e)
        _cross_encoder = None
        # 故意不设 _cross_encoder_load_attempted = True，允许后续调用重试
    return _cross_encoder


def _reset_cross_encoder_for_test():
    """测试专用：重置单例与尝试标记，强制下次重新加载。"""
    global _cross_encoder, _cross_encoder_load_attempted
    _cross_encoder = None
    _cross_encoder_load_attempted = False


def rerank_cross_encoder(
    items: list[dict],
    employee_context: dict,
    corpus: list[dict] | None = None,
    cross_encoder_fn=None,
    call_llm_json_fn=None,
) -> list[dict]:
    """Stage 3 cross-encoder 精排（替换 zero-shot LLM 重排）。

    对每项的 (concept, candidate) pair 用 cross-encoder 打分，选 top1。
    新标签判定：top1 score < RERANKER_NEW_LABEL_THRESHOLD → is_new_label。
    降级：cross_encoder_fn None/加载失败 → 调 rerank_label_llm（D6 确定性降级不重试）。
    S1 终裁：config.RERANKER_LLM_ADJUDICATION 开启时，SOURCE_CROSS_NEW_LABEL /
        SOURCE_CROSS_PENDING 项单轮送 rerank_label_llm 复核（confirmed=救回候选 /
        rejected=维持新标签并计入 cap；LLM 失败或返回长度不符 → 保留原判定，零重试）。

    Args:
        items: [{idx, concept, standard_label, category, candidates (list[str]),
                 extract_confidence}] 待匹配项（同 rerank_label_llm 入参契约）。
        employee_context: 员工 dict（降级到 LLM 时传入）。
        corpus: 标签库 corpus，快路径精确名匹配用。
        cross_encoder_fn: 测试注入打分函数，签名 fn(pairs: list[tuple[str,str]]) -> np.ndarray。
            None→用 _load_cross_encoder() 加载的真实模型。
        call_llm_json_fn: 降级路径 rerank_label_llm 用，测试注入 fake。

    Returns:
        list[dict] 与 items 同序，每项含
        {idx, matched_label, is_new_label, match_confidence, rationale,
         candidates_seen, mapping_source}（C1 对称：与 rerank_label_llm 同 key 集合）。

    多 return 路径顶层 key 集合（E 节错误路径等价性）：
        - 空 items → []
        - 降级 LLM → rerank_label_llm 返回（已对齐 _RERANK_ITEM_KEYS）
        - cross-encoder 打分失败 → 整批降级 LLM
        - 正常打分（含 S1 终裁救回/维持/保留三分支）→ 每项 {_RERANK_ITEM_KEYS} 全 7 key
    """
    # C3 守卫：空 items
    if not items:
        return []

    # 🔴 Step 1.10 修复：禁用 exact 快路径锁定。
    # 旧逻辑（Step 8e）：standard_label 精确匹配 corpus 名时，用 cross-encoder 对
    #   (concept, standard_label) 单 pair 打分确认，高分即跳过全候选重排。
    # 副作用：LLM 选错相近标签时（如"项目管理方法论"→"项目管理知识体系"而非 GT 的"项目管理"），
    #   单 pair 确认 score 高（语义近）→ 锁死错误标签，cross-encoder 没机会选正确标签。
    # 新逻辑：所有 items 直接进全候选重排，cross-encoder 对 (concept, top-k 全候选) 打分
    #   选最优。LLM 提议若在 candidates 中且最优会被自然选中，选错时能纠正。
    results: list[dict | None] = [None] * len(items)
    to_rerank_indices = list(range(len(items)))

    # 加载 cross-encoder（测试注入优先；否则惰性加载）
    encoder = cross_encoder_fn
    if encoder is None:
        encoder = _load_cross_encoder()

    if not to_rerank_indices:
        return []

    if encoder is None:
        # D6 确定性降级：cross-encoder 不可用 → fallback zero-shot LLM
        logger.info("cross-encoder 不可用，降级 rerank_label_llm")
        llm_results = rerank_label_llm(
            items, employee_context, corpus, call_llm_json_fn=call_llm_json_fn,
            trust_exact_match=False,  # P0：cross-encoder 不可用时降级，不无条件信任 exact
        )
        # 把降级路径的 mapping_source 改标 fallback_llm（保留 LLM 内部 source 不覆盖，
        # 仅对未命中的兜底项标记；exact_name_match 等保留原值以统计准确）
        for i, r in enumerate(llm_results):
            src = r.get("mapping_source", "")
            if src in (SOURCE_RERANK_FAILED, SOURCE_NEW_LABEL, SOURCE_NEW_CAPPED,
                       SOURCE_PENDING, SOURCE_LLM_RERANK):
                # 这些是 LLM 重排/降级产物 → 标 fallback 来源（实验指标区分用）
                if src == SOURCE_RERANK_FAILED:
                    r["mapping_source"] = SOURCE_CROSS_FAILED_FALLBACK_LLM
                    r["rationale"] = "cross-encoder 不可用，降级 LLM 后再失败，信任原始提议"
        return llm_results

    # 构造 (concept, candidate) pairs 批量打分
    to_rerank_items = [items[i] for i in to_rerank_indices]
    pairs: list[tuple[str, str]] = []
    pair_owner: list[tuple[int, int]] = []  # (to_rerank_index, candidate_index)
    for ri, it in enumerate(to_rerank_items):
        concept = it.get("concept", "") or ""
        cands = it.get("candidates", []) or []
        for ci, cand in enumerate(cands):
            if not isinstance(cand, str) or not cand:
                continue
            pairs.append((concept, cand))
            pair_owner.append((ri, ci))

    # 批量打分
    try:
        # 兼容：CrossEncoder 用 .predict，测试注入的 callable 直接调用
        _score_fn = getattr(encoder, "predict", None) or encoder
        scores = _score_fn(pairs) if pairs else []
        scores_arr = np.asarray(scores, dtype=float)
        if scores_arr.size != len(pairs):
            raise ValueError(
                f"cross-encoder 返回 {scores_arr.size} 分数，预期 {len(pairs)}"
            )
    except Exception as e:
        # 打分失败 → 整批降级 LLM（不重试 cross-encoder，D6）
        logger.warning("cross-encoder 打分失败，整批降级 LLM: %s", e)
        llm_results = rerank_label_llm(
            items, employee_context, corpus, call_llm_json_fn=call_llm_json_fn,
            trust_exact_match=False,  # P0：打分失败降级，让 LLM 重新评估所有项（含 exact）
        )
        for r in llm_results:
            if r.get("mapping_source") == SOURCE_RERANK_FAILED:
                r["mapping_source"] = SOURCE_CROSS_FAILED_FALLBACK_LLM
                r["rationale"] = "cross-encoder 打分失败，降级 LLM 后再失败"
        return llm_results

    # 按 to_rerank_index 聚合分数，选 top1
    new_threshold = getattr(config, "RERANKER_NEW_LABEL_THRESHOLD", 0.15)
    conf_threshold = getattr(config, "RERANKER_CONFIDENCE_THRESHOLD", 0.5)
    rerank_results_by_idx: dict = {}
    # 初始化每项的候选分数列表
    scores_by_ri: dict[int, list[tuple[float, int]]] = {}
    for k, (ri, ci) in enumerate(pair_owner):
        scores_by_ri.setdefault(ri, []).append((float(scores_arr[k]), ci))

    for ri, it in enumerate(to_rerank_items):
        cands = it.get("candidates", []) or []
        scored = scores_by_ri.get(ri, [])
        if not scored or not cands:
            # 无候选或无打分 → 降级 LLM 单项
            rerank_results_by_idx[it.get("idx")] = _degrade_item(
                it, SOURCE_CROSS_FAILED_FALLBACK_LLM
            )
            continue
        # 选最高分候选
        scored.sort(key=lambda x: x[0], reverse=True)
        top_score, top_ci = scored[0]
        top_label = cands[top_ci] if top_ci < len(cands) else cands[0]
        if top_score < new_threshold:
            # 新标签
            rerank_results_by_idx[it.get("idx")] = {
                "idx": it.get("idx"),
                "matched_label": it.get("concept", ""),
                "is_new_label": True,
                "match_confidence": _clamp_conf(top_score),
                "rationale": f"cross-encoder top1 score={top_score:.3f}<{new_threshold}，判定新标签",
                "candidates_seen": cands,
                "mapping_source": SOURCE_CROSS_NEW_LABEL,
            }
        elif top_score < conf_threshold:
            # 待复核
            rerank_results_by_idx[it.get("idx")] = {
                "idx": it.get("idx"),
                "matched_label": top_label,
                "is_new_label": False,
                "match_confidence": _clamp_conf(top_score),
                "rationale": f"cross-encoder top1 score={top_score:.3f}<{conf_threshold}，待人工复核",
                "candidates_seen": cands,
                "mapping_source": SOURCE_CROSS_PENDING,
            }
        else:
            # 正常命中
            rerank_results_by_idx[it.get("idx")] = {
                "idx": it.get("idx"),
                "matched_label": top_label,
                "is_new_label": False,
                "match_confidence": _clamp_conf(top_score),
                "rationale": f"cross-encoder top1 score={top_score:.3f}",
                "candidates_seen": cands,
                "mapping_source": SOURCE_CROSS_RERANK,
            }

    # ── S1 LLM 终裁（plan T1 Phase 1）：低分项送 rerank_label_llm 单轮复核 ──
    # 收集 cross-encoder 判新标签/待复核项的原始条目（含 idx/concept/standard_label/
    # category/candidates/extract_confidence，入参契约与 rerank_label_llm 一致）。
    # D6：每员工最多 1 轮终裁（单次批量调用）、零重试；复核失败保留原判定。
    if config.RERANKER_LLM_ADJUDICATION:
        adj_items = [
            it for it in to_rerank_items
            if rerank_results_by_idx.get(it.get("idx"), {}).get("mapping_source")
            in (SOURCE_CROSS_NEW_LABEL, SOURCE_CROSS_PENDING)
        ]
        if adj_items:
            adj_results = rerank_label_llm(
                adj_items, employee_context, corpus,
                call_llm_json_fn=call_llm_json_fn,
                trust_exact_match=False,  # 与既有两处降级调用同语义（Step 1.10：不让 exact 锁死）
            )
            # C3 守卫：非 list / 长度不符 → 整体保留原 cross-encoder 判定（不重试）
            if isinstance(adj_results, list) and len(adj_results) == len(adj_items):
                for it, llm_r in zip(adj_items, adj_results):
                    orig = rerank_results_by_idx.get(it.get("idx"))
                    if not isinstance(llm_r, dict) or orig is None:
                        continue
                    src = llm_r.get("mapping_source")
                    if src in (SOURCE_LLM_RERANK, SOURCE_PENDING):
                        # ① LLM 复核选中候选 → 救回（置信度用 LLM 值）
                        orig["matched_label"] = llm_r.get("matched_label", "")
                        orig["is_new_label"] = False
                        orig["mapping_source"] = SOURCE_CROSS_NEW_LLM_CONFIRMED
                        orig["rationale"] = "LLM复核救回: " + str(orig.get("rationale", ""))
                        orig["match_confidence"] = llm_r.get(
                            "match_confidence", orig.get("match_confidence", 0.0)
                        )
                    elif src in (SOURCE_NEW_LABEL, SOURCE_NEW_CAPPED):
                        # ②③ LLM 判 NEW / 内部 cap 改写（HIGH-1 第四分支）→ 维持新标签，
                        #    计入下方外层 cap（不二次惩罚），不采纳内部 cap 的降级改写
                        orig["matched_label"] = it.get("concept", "")
                        orig["is_new_label"] = True
                        orig["mapping_source"] = SOURCE_CROSS_NEW_LLM_REJECTED
                    # ④ SOURCE_RERANK_FAILED 等 → 保留原 cross-encoder 判定（不改任何字段）

    # 新标签防滥：超额项降级选 candidates[0]（与 LLM 路径同逻辑）
    # S1：cross_new_llm_rejected（LLM 终裁维持新标签）与原判定同计入 cap
    new_label_count = sum(
        1 for v in rerank_results_by_idx.values()
        if v.get("mapping_source") in (SOURCE_CROSS_NEW_LABEL, SOURCE_CROSS_NEW_LLM_REJECTED)
    )
    new_cap = config.LABEL_NEW_LABEL_MAX_PER_EMP
    if new_label_count > new_cap:
        over = 0
        for v in rerank_results_by_idx.values():
            if v.get("mapping_source") in (SOURCE_CROSS_NEW_LABEL, SOURCE_CROSS_NEW_LLM_REJECTED):
                over += 1
                if over > new_cap:
                    cands = v.get("candidates_seen", [])
                    v["matched_label"] = cands[0] if cands else v.get("matched_label", "")
                    v["is_new_label"] = False
                    v["mapping_source"] = SOURCE_NEW_CAPPED
                    v["rationale"] = f"新标签超额({new_cap})，降级选 top1 候选"

    # 填回 results 保留原顺序
    for i, item in enumerate(items):
        if results[i] is None:
            results[i] = rerank_results_by_idx.get(item.get("idx")) or _degrade_item(
                item, SOURCE_CROSS_FAILED_FALLBACK_LLM
            )

    # C1 对称：补齐所有 key
    return [{k: r.get(k) for k in _RERANK_ITEM_KEYS} for r in results]  # type: ignore[arg-type]

