"""Day 2 5 员工对比实验：LLM 提议→验证→纠正 vs Embedding 纯映射

对比两条标签映射路径的正确率，定稿 Embedding 阈值（threshold=0.50, margin=0.12）
或触发 Plan B（Day 3 改 Top-3 推荐）。

用法:
    # 真实 LLM 实验（需 DeepSeek API key，非 offline）
    python scripts/experiment_embedding_vs_llm.py \
        --from-phase1 data/intermediate/phase1_output.json \
        --ground-truth data/experiment/ground_truth_5.json

    # offline 冒烟（验证脚本骨架不崩，不验证正确率 — _llm_extract 返回空标签）
    TC_OFFLINE=1 python scripts/experiment_embedding_vs_llm.py \
        --from-phase1 data/intermediate/phase1_output.json

路径定义（第二周开发指南 Day 2 Task 2.2）:
- Path A（LLM 提议→验证→纠正）: _llm_extract 抽取 concept+standard_label →
  对每个 t1/t2 项调 verify_mapping(concept, proposed=standard_label, corpus) →
  分类 verified / embedding_corrected / pending → 对照 ground truth 记正确/错误
- Path B（Embedding 纯映射）: 复用 _llm_extract 的 concept（忽略 LLM 的
  standard_label）→ 纯 embedding top-1/top-3 映射 → 对照 ground truth 记命中

⚠ Path B 复用 _llm_extract 的 concept 而非另起"自由 prompt"，避免 2× LLM 成本。
  两条路径的差异仅在映射阶段（LLM labeling + verify/correct vs 纯 embedding），
  这正是要对比的核心。

决策（指南 L492-495）:
- Path A 最终正确率 ≥ 90% → 阈值定稿 threshold=0.50, margin=0.12
- ≥ 80% < 90% → 调阈值重跑
- < 80% 或两轮仍 < 90% → Plan B（Day 3 改 Top-3 推荐，不做自动纠正）
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

# Windows GBK 编码修复
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if sys.stderr and hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from agents.profile_generation import ProfileGeneration
from config import (
    EMBEDDING_MIN_SIM,
    INTERMEDIATE_DIR,
    LABEL_CONFIDENCE_THRESHOLD,
    LABEL_RECALL_TOP_K,
)
from utils.label_embedding import (
    load_label_corpus,
    verify_mapping,
)
from utils.label_matching import recall_top_k, rerank_label_llm, rerank_cross_encoder
from utils.logger import generate_trace_id
from utils import numpy_to_native


# ── 实验员工（与 ground_truth_5.json 对齐）──
TARGET_EMPLOYEES = ["JZ0001", "JZ0003", "JZ0004"]  # 先跑 3 人验证 k=20 效果


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Day 2 5 员工对比实验：LLM+verify/correct vs Embedding 纯映射",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--from-phase1", type=str,
        default=str(INTERMEDIATE_DIR / "phase1_output.json"),
        help="Agent① 输出 JSON 路径",
    )
    p.add_argument(
        "--ground-truth", type=str,
        default="data/experiment/ground_truth_5.json",
        help="5 员工 ground truth 标签 JSON",
    )
    p.add_argument(
        "--output-dir", type=str, default=str(INTERMEDIATE_DIR),
        help="实验结果 JSON 输出目录",
    )
    return p.parse_args()


def load_phase1_employees(path: str) -> list[dict]:
    """加载 phase1_output.json，返回 employees 列表。"""
    with open(path, encoding="utf-8-sig") as f:
        data = json.load(f)
    emps = data.get("employees", []) if isinstance(data, dict) else data
    if not isinstance(emps, list):
        raise ValueError(f"phase1 输出 employees 非 list: {type(emps).__name__}")
    return emps


def load_ground_truth(path: str) -> dict:
    """加载 ground truth，返回 {employee_id: set(standard_label)}。"""
    with open(path, encoding="utf-8-sig") as f:
        gt = json.load(f)
    result = {}
    for eid, info in gt.items():
        if eid.startswith("_"):
            continue
        labels = {lb["label"] for lb in info.get("labels", []) if isinstance(lb, dict)}
        result[eid] = labels
    return result


def adapt_employee(emp: dict) -> dict:
    """将 Agent① 原始员工转为 _llm_extract 需要的适配格式。

    复用 ProfileGeneration._adapt_input 的单员工逻辑（D2 不重复）。
    """
    agent = ProfileGeneration()
    adapted = agent._adapt_input({"employees": [emp]})["employees"]
    if not adapted:
        raise ValueError(f"员工适配失败: {emp.get('employee_id')}")
    return adapted[0]


def path_b_top_k(concept: str, corpus: list[dict], top_k: int = 3,
                 corpus_text_vecs=None) -> list[str]:
    """Path B: 纯 embedding top-k 映射（concept → 标签名列表，按 sim 降序）。

    薄包装：复用 utils.label_matching.recall_top_k（F1 不重复 cosine 逻辑），
    仅抽取 name（实验脚本只比对标签名，不需要 sim 分数）。
    """
    pairs = recall_top_k(
        concept, corpus, corpus_text_vecs=corpus_text_vecs, top_k=top_k
    )
    return [name for name, _sim in pairs]


def _call_ollama_json(prompt, system_prompt, temperature=0.0, max_tokens=2048, timeout=60):
    """调用本地 Ollama qwen3:14b，返回 JSON 格式结果。

    签名匹配 utils.llm_client.call_llm_json（供 rerank_label_llm 注入测试用）。
    """
    import json as _json
    import re as _re
    import urllib.request as _req
    payload = _json.dumps({
        "model": "qwen3:14b",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
        "options": {"temperature": temperature, "num_predict": max_tokens},
    }).encode("utf-8")
    try:
        resp = _req.urlopen(
            "http://localhost:11434/api/chat",
            data=payload,
            timeout=timeout,
        )
        data = _json.loads(resp.read().decode("utf-8"))
        content_text = data.get("message", {}).get("content", "")

        # 尝试解析整个内容为 JSON
        try:
            parsed = _json.loads(content_text)
            return {"content": parsed, "error": None}
        except _json.JSONDecodeError:
            # 尝试提取 ```json ... ``` 块
            m = _re.search(r'```(?:json)?\s*([\s\S]*?)```', content_text)
            if m:
                try:
                    parsed = _json.loads(m.group(1))
                    return {"content": parsed, "error": None}
                except _json.JSONDecodeError:
                    pass
            return {"content": None, "error": f"无法从 Ollama 输出解析 JSON: {content_text[:200]}"}
    except Exception as e:
        return {"content": None, "error": f"ollama 调用异常: {e}"}


def run_experiment(
    employees: list[dict],
    ground_truth: dict,
    corpus: list[dict],
) -> dict:
    """跑双路径实验，返回聚合结果。"""
    agent = ProfileGeneration()
    context = {"trace_id": "experiment", "cancel_event": None}

    # 预编码 corpus 文本（一次，所有员工/所有 concept 复用，避免逐 concept 重算矩阵）
    # recall_top_k 接受 corpus_text_vecs 参数复用此矩阵
    from utils.label_embedding import encode_labels
    corpus_texts = [c.get("text", "") for c in corpus]
    corpus_text_vecs = encode_labels(tuple(corpus_texts))

    per_employee = []
    # 聚合计数
    path_a_total = 0
    path_a_verified = 0
    path_a_corrected_correct = 0
    path_a_corrected_wrong = 0
    path_a_pending = 0
    path_a_pending_correct = 0  # C8: pending 项命中 GT 的子集（低相似度但 LLM 提议本就对的）
    path_a_final_correct = 0
    path_b_top1_hit = 0
    path_b_top3_hit = 0
    path_b_total = 0
    llm_call_attempts = 0   # C8: 计所有真实 LLM 尝试（含超时/失败），offline_skipped 除外
    llm_call_failures = 0   # 超时/网络/认证错误计数（区分质量 vs infra 信号）
    # Path C: Stage 3 LLM 重排（embedding 召回 top-3 → LLM 精排拍板）
    path_c_total = 0
    path_c_final_correct = 0
    path_c_new_labels = 0
    path_c_rerank_failures = 0
    path_c_rerank_calls = 0
    # recall@GT 公平口径：命中 GT 的 unique 标签数 / GT 总标签数（按员工聚合）
    path_a_gt_hit = 0          # Path A 命中 GT 的 unique 标签数（员工内去重）
    path_b_top1_gt_hit = 0     # Path B top1 命中 GT 的 unique 标签数
    path_c_gt_hit = 0          # Path C 命中 GT 的 unique 标签数
    total_gt_labels = 0        # 全员工 GT 标签数（跨员工求和，含重复员工内的不同标签）
    # 误导指标修正：真实 LLM/cross-encoder 调用次数（非入口计数）
    llm_rerank_actual_calls = 0     # mapping_source 非 exact_name_match* 的项数（推断 LLM 触发）
    cross_encoder_actual_calls = 0  # cross-encoder 打分项数（Step 8c 预留，当前 0）
    # B3 统计扩展（plan 第七节 A/B 序 1）：S1 LLM 终裁产物独立计数。
    # llm_adjudication_calls = 终裁改判项数（confirmed + rejected），独立于
    # cross_encoder_actual_calls / llm_rerank_actual_calls 的 A/B 归因口径。
    llm_adjudication_calls = 0
    path_c_cross_new_llm_confirmed = 0   # 终裁救回项（原判新标签 → LLM 选回候选）
    path_c_cross_new_llm_rejected = 0    # 终裁维持新标签项（计入新标签 cap）

    for emp in employees:
        eid = emp.get("employee_id", "")
        if eid not in ground_truth:
            continue
        gt_labels = ground_truth[eid]
        total_gt_labels += len(gt_labels)
        # 本员工三条路径命中 GT 的 unique 标签 set（员工内去重）
        emp_a_hit = set()
        emp_b_top1_hit = set()
        emp_c_hit = set()
        adapted = adapt_employee(emp)

        # ── _llm_extract（单次 LLM 调用，两路径复用 concept）──
        extract = agent._llm_extract(adapted, context)
        # C8 审计完整性：先计 LLM 尝试（含失败），再判 error 跳过
        if not extract.get("offline_skipped"):
            llm_call_attempts += 1
        if extract.get("error"):
            llm_call_failures += 1
            # C1 对称：error 路径 per_employee 项 key 集合必须与成功路径 emp_result 一致
            # （E 节：多 return 路径顶层 key 等价）。下游迭代 per_employee 读 t1_count/path_c 等
            # 任一 key 时不应 KeyError。失败员工无映射数据，各 count=0、各 path=[]。
            per_employee.append({
                "employee_id": eid,
                "error": extract["error"],
                "model": extract.get("model", ""),
                "usage": extract.get("usage", {}) or {},
                "content_keys": {},
                "t1_count": 0,
                "t2_count": 0,
                "t3_count": 0,
                # B3 统计扩展：与成功路径 emp_result 对称（失败员工无映射数据 → 0）
                "cross_new_llm_confirmed": 0,
                "cross_new_llm_rejected": 0,
                "ground_truth_count": len(gt_labels),
                "path_a": [],
                "path_b": [],
                "path_c": [],
            })
            continue
        content = extract.get("content") or {}

        # F6 审计：存 content 摘要（顶层 key + 各数组长度）+ token usage，供诊断 LLM 返回结构
        content_audit = {}
        if isinstance(content, dict):
            for k, v in content.items():
                if isinstance(v, list):
                    content_audit[k] = f"list[{len(v)}]"
                elif isinstance(v, dict):
                    content_audit[k] = f"dict{{{len(v)}}}"
                else:
                    content_audit[k] = type(v).__name__

        emp_result = {
            "employee_id": eid,
            "model": extract.get("model", ""),
            "usage": extract.get("usage", {}) or {},
            "content_keys": content_audit,
            "t1_count": len(content.get("t1_professional", []) or []) if isinstance(content, dict) else 0,
            "t2_count": len(content.get("t2_behavioral", []) or []) if isinstance(content, dict) else 0,
            "t3_count": len(content.get("t3_labels", []) or []) if isinstance(content, dict) else 0,
            "ground_truth_count": len(gt_labels),
            # B3 统计扩展：per-employee 级 S1 终裁 source 计数（key 名与
            # summary["path_c"] 同名，防跨 level 契约漂移；error 路径对称为 0）
            "cross_new_llm_confirmed": 0,
            "cross_new_llm_rejected": 0,
            "path_a": [],
            "path_b": [],
            "path_c": [],
        }

        # 收集 t1+t2+t3 的 (concept, proposed_label) 对 + Path C 重排输入项
        # Step 1.8：加 "t3_labels" 对齐生产 _collect_rerank_items（agents/profile_generation.py L762）
        # t3_labels 项有 concept/standard_label/category/confidence（与 t1/t2 同名同语义），
        # 无 sfia_level/ability_score（T3 不挂等级）——rerank_items dict 本就只抽
        # concept/standard_label/category/candidates/extract_confidence，不碰 sfia/ability，安全。
        pairs = []
        rerank_items = []
        for key in ("t1_professional", "t2_behavioral", "t3_labels"):
            for item in content.get(key, []) or []:
                if not isinstance(item, dict):
                    continue
                concept = item.get("concept", "")
                proposed = item.get("standard_label", "")
                if concept:
                    pairs.append((concept, proposed))
                    # Path C 输入项：召回 top-3 候选构造 rerank item
                    cands_pairs = recall_top_k(
                        concept, corpus, corpus_text_vecs=corpus_text_vecs,
                    )
                    rerank_items.append({
                        "idx": len(rerank_items),
                        "concept": concept,
                        "standard_label": proposed,
                        "category": item.get("category", ""),
                        "candidates": [n for n, _ in cands_pairs],
                        "extract_confidence": item.get("confidence", 0.5),
                    })

        # ── Path A: LLM 提议 → verify_mapping 验证/纠正 ──
        for concept, proposed in pairs:
            path_a_total += 1
            r = verify_mapping(concept, proposed, corpus)
            source = r["mapping_source"]
            corrected = r.get("corrected_label")
            final_label = corrected or proposed  # 纠正路径用 corrected_label
            in_gt = final_label in gt_labels

            if source == "llm_proposed:verified" or source == "embedding_corrected_renamed":
                path_a_verified += 1
                if in_gt:
                    path_a_final_correct += 1
            elif source == "embedding_corrected":
                if in_gt:
                    path_a_corrected_correct += 1
                    path_a_final_correct += 1
                else:
                    path_a_corrected_wrong += 1
            else:  # low_margin / both_low / label_not_found
                path_a_pending += 1
                # 修复统计 bug：pending 项的 final_label=proposed（无纠正），若 proposed 在 GT 仍算命中
                # 旧逻辑漏数此分支 → final_correct 虚低（实测 15.7% 应为 23.5%）
                if in_gt:
                    path_a_pending_correct += 1
                    path_a_final_correct += 1
            # recall@GT：命中 GT 的 final_label 计入员工 unique 命中集
            if in_gt and final_label:
                emp_a_hit.add(final_label)

            emp_result["path_a"].append({
                "concept": concept, "proposed": proposed,
                "mapping_source": source, "similarity": round(r["similarity"], 4),
                "final_label": final_label, "in_ground_truth": in_gt,
            })

        # ── Path B: 纯 embedding top-1/top-3 ──
        for concept, _proposed in pairs:
            path_b_total += 1
            top3 = path_b_top_k(concept, corpus, top_k=LABEL_RECALL_TOP_K,
                                corpus_text_vecs=corpus_text_vecs)
            top1 = top3[0] if top3 else ""
            top1_in_gt = top1 in gt_labels
            emp_result["path_b"].append({
                "concept": concept,
                "top1": top1, "top3": top3,
                "top1_hit": top1_in_gt,
                "top3_hit": bool(set(top3) & gt_labels),
            })
            if top1_in_gt:
                path_b_top1_hit += 1
                if top1:
                    emp_b_top1_hit.add(top1)
            if set(top3) & gt_labels:
                path_b_top3_hit += 1

        # ── Path C: cross-encoder 精排（本地 BGE-reranker-v2-m3）──
        # 架构：embedding 召回 top-3 → BGE cross-encoder 对 (concept, candidate) 打分选 top1
        # 降级：BGE 加载/推理失败 → rerank_label_llm（默认 DeepSeek call_llm_json，非 Ollama）
        if rerank_items:
            path_c_rerank_calls += 1
            c_results = rerank_cross_encoder(rerank_items, adapted, corpus)
            for r in c_results:
                path_c_total += 1
                matched = r.get("matched_label", "")
                source = r.get("mapping_source", "")
                in_gt = matched in gt_labels
                if in_gt:
                    path_c_final_correct += 1
                if source in ("new_label", "cross_encoder_new_label"):
                    path_c_new_labels += 1
                if source in ("rerank_failed_trust_llm", "rerank_failed_fallback_llm"):
                    path_c_rerank_failures += 1
                # B3 统计扩展：S1 终裁 source 计数（per-employee + summary 双级）。
                # 注意：cross_new_llm_rejected 不并入上方 path_c_new_labels——既有 key
                # 语义零变化（new_labels 仅 = new_label/cross_encoder_new_label），
                # 总新标签可由消费方 new_labels + cross_new_llm_rejected 合成。
                if source == "cross_new_llm_confirmed":
                    path_c_cross_new_llm_confirmed += 1
                    emp_result["cross_new_llm_confirmed"] += 1
                elif source == "cross_new_llm_rejected":
                    path_c_cross_new_llm_rejected += 1
                    emp_result["cross_new_llm_rejected"] += 1
                # 指标修正（A9 分流修复）：cross_new_llm_* 既不匹配 cross_encoder_ 前缀
                # 也非 exact 前缀，原逻辑会误入 llm_rerank_actual_calls（纯 LLM 通道
                # 口径被污染）→ 独立计数 llm_adjudication_calls，保持三口径互斥。
                if source in ("cross_new_llm_confirmed", "cross_new_llm_rejected"):
                    llm_adjudication_calls += 1
                elif source == "exact_name_match_confirmed" or source.startswith("cross_encoder_"):
                    cross_encoder_actual_calls += 1
                elif not source.startswith("exact_name_match"):
                    llm_rerank_actual_calls += 1
                # idx → 回查原 concept（rerank_items 与 c_results 同序）
                ridx = r.get("idx")
                concept = (
                    rerank_items[ridx]["concept"]
                    if isinstance(ridx, int) and ridx < len(rerank_items)
                    else ""
                )
                if in_gt and matched:
                    emp_c_hit.add(matched)
                emp_result["path_c"].append({
                    "concept": concept,
                    "matched_label": matched,
                    "mapping_source": source,
                    "match_confidence": r.get("match_confidence", 0.0),
                    "is_new_label": r.get("is_new_label", False),
                    "in_ground_truth": in_gt,
                })

        # recall@GT：员工内命中 GT 的 unique 标签数（限定该员工 GT 内）
        path_a_gt_hit += len(emp_a_hit & gt_labels)
        path_b_top1_gt_hit += len(emp_b_top1_hit & gt_labels)
        path_c_gt_hit += len(emp_c_hit & gt_labels)

        per_employee.append(emp_result)

    # ── 聚合 ──
    path_a_rate = (path_a_final_correct / path_a_total * 100) if path_a_total else 0.0
    path_b_top1_rate = (path_b_top1_hit / path_b_total * 100) if path_b_total else 0.0
    path_b_top3_rate = (path_b_top3_hit / path_b_total * 100) if path_b_total else 0.0
    path_c_rate = (path_c_final_correct / path_c_total * 100) if path_c_total else 0.0
    # recall@GT 公平口径（分母=GT 总标签数，跨员工求和；非 recall@1 的总映射数）
    path_a_recall_at_gt = (path_a_gt_hit / total_gt_labels * 100) if total_gt_labels else 0.0
    path_b_top1_recall_at_gt = (path_b_top1_gt_hit / total_gt_labels * 100) if total_gt_labels else 0.0
    path_c_recall_at_gt = (path_c_gt_hit / total_gt_labels * 100) if total_gt_labels else 0.0

    # 决策（V5：先排 infra 失败伪装，再判质量信号）
    # 全 LLM 失败时 path_a_total=0 → 0% 会误触 Plan B，但那是超时不是质量信号
    valid_run = path_a_total > 0  # 有至少 1 个 LLM 成功提取的标签可评
    if llm_call_attempts > 0 and llm_call_failures == llm_call_attempts:
        # 全部 LLM 调用失败（超时/网络/认证）→ 实验无效，不可评估 prompt 质量
        decision = (
            f"INVALID: 全部 {llm_call_failures} 次 LLM 调用失败（超时/网络/认证），"
            "实验无法评估 prompt 质量 — 修 API 连通性后重跑，勿据此改 Day 3 策略"
        )
        plan_b = False  # 不触发 Plan B（infra 失败 ≠ 质量信号）
    elif not valid_run:
        decision = "INVALID: 无成功 LLM 提取（path_a_total=0），实验无映射可评 — 检查 API 后重跑"
        plan_b = False
    elif path_a_rate >= 90:
        decision = "定稿: threshold=0.50, margin=0.12（Path A ≥ 90%）"
        plan_b = False
    elif path_a_rate >= 80:
        decision = f"调阈值重跑（Path A {path_a_rate:.1f}%，80-90% 区间）"
        plan_b = False
    else:
        decision = "Plan B: Day 3 改 Top-3 推荐，不做自动纠正（Path A < 80%）"
        plan_b = True

    summary = {
        "total_employees": len(per_employee),
        "llm_call_attempts": llm_call_attempts,
        "llm_call_failures": llm_call_failures,
        "llm_calls": llm_call_attempts - llm_call_failures,  # 成功调用数（向后兼容旧字段）
        "valid_run": valid_run and llm_call_failures < llm_call_attempts,
        "threshold": EMBEDDING_MIN_SIM,
        "confidence_threshold": LABEL_CONFIDENCE_THRESHOLD,
        "path_a": {
            "total_mappings": path_a_total,
            "verified": path_a_verified,
            "corrected_correct": path_a_corrected_correct,
            "corrected_wrong": path_a_corrected_wrong,
            "pending": path_a_pending,
            "pending_correct": path_a_pending_correct,  # C8: pending 项命中 GT 的子集
            "final_correct": path_a_final_correct,
            "final_correct_rate_pct": round(path_a_rate, 1),
            "recall_at_gt": path_a_gt_hit,
            "total_gt_labels": total_gt_labels,
            "recall_at_gt_pct": round(path_a_recall_at_gt, 1),
        },
        "path_b": {
            "total_mappings": path_b_total,
            "top1_hit": path_b_top1_hit,
            "top3_hit": path_b_top3_hit,
            "top1_rate_pct": round(path_b_top1_rate, 1),
            "top3_rate_pct": round(path_b_top3_rate, 1),
            "top1_recall_at_gt": path_b_top1_gt_hit,
            "total_gt_labels": total_gt_labels,
            "top1_recall_at_gt_pct": round(path_b_top1_recall_at_gt, 1),
        },
        "path_c": {
            "total_mappings": path_c_total,
            "final_correct": path_c_final_correct,
            "final_correct_rate_pct": round(path_c_rate, 1),
            "new_labels": path_c_new_labels,
            "rerank_failures": path_c_rerank_failures,
            "rerank_calls": path_c_rerank_calls,
            "recall_at_gt": path_c_gt_hit,
            "total_gt_labels": total_gt_labels,
            "recall_at_gt_pct": round(path_c_recall_at_gt, 1),
            "llm_rerank_actual_calls": llm_rerank_actual_calls,
            "cross_encoder_actual_calls": cross_encoder_actual_calls,
            # B3 统计扩展（向后兼容：纯新增 key，既有 key 与语义零变化）
            "cross_new_llm_confirmed": path_c_cross_new_llm_confirmed,
            "cross_new_llm_rejected": path_c_cross_new_llm_rejected,
            "llm_adjudication_calls": llm_adjudication_calls,
        },
        "decision": decision,
        "plan_b_triggered": plan_b,
        "per_employee": per_employee,
    }
    return numpy_to_native(summary)


def print_summary(summary: dict) -> None:
    """终端表格输出（对齐指南 L478-490 格式）。"""
    pa = summary["path_a"]
    pb = summary["path_b"]
    pc = summary.get("path_c", {})
    print("\n" + "=" * 60)
    print("Day 2 5 员工对比实验结果")
    print("=" * 60)
    print(f"员工数: {summary['total_employees']}  "
          f"LLM 尝试: {summary['llm_call_attempts']}  "
          f"成功: {summary['llm_calls']}  失败: {summary['llm_call_failures']}")
    print(f"阈值: threshold={summary['threshold']}, confidence<{summary['confidence_threshold']}")
    if not summary.get("valid_run", True):
        print("⚠ 实验无效 — LLM 调用全部/部分失败，正确率不反映 prompt 质量")
    print()
    print("路径 A (LLM 提议→embedding 自动纠正):")
    print(f"  总映射数: {pa['total_mappings']}")
    print(f"  验证通过: {pa['verified']} ({pa['verified']/max(pa['total_mappings'],1)*100:.1f}%)")
    print(f"  纠正正确: {pa['corrected_correct']} ({pa['corrected_correct']/max(pa['total_mappings'],1)*100:.1f}%)")
    print(f"  纠正错误: {pa['corrected_wrong']} ({pa['corrected_wrong']/max(pa['total_mappings'],1)*100:.1f}%)")
    print(f"  pending:  {pa['pending']} ({pa['pending']/max(pa['total_mappings'],1)*100:.1f}%)"
          f"  其中命中GT: {pa['pending_correct']}")
    print(f"  最终正确率: {pa['final_correct_rate_pct']}%  (recall@1)")
    print(f"  recall@GT: {pa.get('recall_at_gt',0)}/{pa.get('total_gt_labels',0)} = {pa.get('recall_at_gt_pct',0)}%  (公平口径)")
    print()
    print("路径 B (Embedding 纯映射):")
    print(f"  Top-1 命中: {pb['top1_hit']} ({pb['top1_rate_pct']}%)  (recall@1)")
    print(f"  Top-3 命中: {pb['top3_hit']} ({pb['top3_rate_pct']}%)")
    print(f"  Top-1 recall@GT: {pb.get('top1_recall_at_gt',0)}/{pb.get('total_gt_labels',0)} = {pb.get('top1_recall_at_gt_pct',0)}%")
    print()
    print("路径 C (Stage 3 LLM 重排: embedding 召回→LLM 精排):")
    if pc:
        print(f"  总映射数: {pc['total_mappings']}")
        print(f"  最终正确率: {pc['final_correct_rate_pct']}%  (recall@1)")
        print(f"  recall@GT: {pc.get('recall_at_gt',0)}/{pc.get('total_gt_labels',0)} = {pc.get('recall_at_gt_pct',0)}%  (公平口径)")
        print(f"  新标签: {pc['new_labels']}  重排失败降级: {pc['rerank_failures']}")
        print(f"  重排入口调用: {pc['rerank_calls']}  真实 LLM 触发项: {pc.get('llm_rerank_actual_calls',0)}"
              f"  cross-encoder 打分项: {pc.get('cross_encoder_actual_calls',0)}")
        print(f"  LLM 终裁: 救回 {pc.get('cross_new_llm_confirmed',0)}  维持新标签 {pc.get('cross_new_llm_rejected',0)}"
              f"  终裁项合计: {pc.get('llm_adjudication_calls',0)}")
    print()
    print(f"决策: {summary['decision']}")
    if summary["plan_b_triggered"]:
        print("⚠ 触发 Plan B — 错误纠正比不纠正更危险，Day 3 改 Top-3 推荐")
    print("=" * 60)


def main() -> int:
    args = parse_args()
    trace_id = generate_trace_id()
    print(f"▶ trace_id: {trace_id}")

    # 加载 phase1 + ground truth + corpus
    print(f"▶ 加载 phase1 输出: {args.from_phase1}")
    all_emps = load_phase1_employees(args.from_phase1)
    emps_by_id = {e.get("employee_id"): e for e in all_emps if isinstance(e, dict)}
    target_emps = [emps_by_id[eid] for eid in TARGET_EMPLOYEES if eid in emps_by_id]
    missing = [eid for eid in TARGET_EMPLOYEES if eid not in emps_by_id]
    if missing:
        print(f"⚠ phase1 缺失员工: {missing}")
    print(f"▶ 实验员工: {[e.get('employee_id') for e in target_emps]}")

    print(f"▶ 加载 ground truth: {args.ground_truth}")
    ground_truth = load_ground_truth(args.ground_truth)

    print("▶ 加载标签库 corpus（T1/T2/T3，registry 融合进 T1）...")
    corpus = load_label_corpus()
    print(f"  corpus 项数: {len(corpus)}")

    offline = os.getenv("TC_OFFLINE", "").lower() in ("1", "true", "yes", "on")
    if offline:
        print("⚠ offline 模式: _llm_extract 返回空标签，实验正确率无意义（仅冒烟）")

    t0 = time.time()
    summary = run_experiment(target_emps, ground_truth, corpus)
    elapsed = time.time() - t0

    summary["trace_id"] = trace_id
    summary["elapsed_seconds"] = round(elapsed, 2)
    summary["offline_mode"] = offline

    print_summary(summary)

    # 持久化
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    mode = "offline" if offline else "live"
    out_path = out_dir / f"experiment_5emp_{mode}_{ts}_{trace_id[-8:]}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"▶ 结果已保存: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
