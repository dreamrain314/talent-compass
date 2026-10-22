"""Round 3 Day 1-2 诊断（预注册 §一 问题 2/3/4，已封存 2026-10-22）：全 50 人 CE 诊断。

只读回放（泄漏级别 L0）——不改打分主链路，不落地任何参数。

覆盖预注册四问中的三问（问题 1 可证性复核为人工表，另行产出）：
- 问题 2：每岗位让 CE 看全部 50 人（不让 T0 掩盖结果）。记录金标在 bi 阶段的
  rank / Recall@10（CE 在生产路径是否实际见到金标）、CE 单独排名、最终融合排名、
  以及「Top-10 内外是否用了不可比打分路径」的量化证据。
- 问题 3（可脚本化部分）：chunk 粒度/长度分布、超长 chunk（截断风险）清点。
- 问题 4：bi cosine 与 CE sigmoid 输出的量纲对比（短名单成员的 t1_bi vs ce01）。

判定树见 docs/preregister_round3_evidence_alignment_20261022.md §一 问题 2 表——
本脚本只产出观测值，判定按冻结表对号入座，不临场发挥。

用法（talent-compass 根目录）：
    python scripts/day12_ce_full_diagnostic.py            # 10 岗 × 全 50 人
    python scripts/day12_ce_full_diagnostic.py --jobs B06 # 单岗快查
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("TC_OFFLINE", "1")  # 诊断协议：零 LLM，纯本地模型

import numpy as np  # noqa: E402

import config  # noqa: E402
from agents.job_analysis import _offline_extract, build_queries  # noqa: E402
from utils.evidence_index import EvidenceIndex, build_evidence_chunks  # noqa: E402
from utils.label_embedding import load_label_corpus  # noqa: E402
from utils.label_matching import _load_cross_encoder  # noqa: E402
from utils.match_engine import (  # noqa: E402
    calibrate_t1_with_ce,
    rank_candidates,
    score_t1_bi,
)


def load_inputs() -> tuple[list[dict], dict[str, str], list[dict]]:
    """10 岗（旧 5 + 新 5）+ 合并金标映射 + 50 人员工池。"""
    jobs: list[dict] = []
    gold: dict[str, str] = {}
    for jf, gf in (
        ("blind_gold_jobs.json", "blind_test_gold.json"),
        ("blind_gold_jobs_batch2.json", "blind_test_gold_batch2.json"),
    ):
        jobs += json.loads((config.DATA_DIR / "jobs" / jf).read_text(encoding="utf-8"))["jobs"]
        gold.update(json.loads((config.DATA_DIR / "experiment" / gf).read_text(encoding="utf-8"))["gold"])
    employees = json.loads(
        (config.INTERMEDIATE_DIR / "phase1_output.json").read_text(encoding="utf-8")
    )["employees"]
    return jobs, gold, employees


def rank_of(scores: dict[str, float], emp_id: str) -> int | None:
    """按分数降序（并列按 emp_id 升序，与 rank_candidates 同规则）求名次，1 起。"""
    if emp_id not in scores:
        return None
    order = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
    for i, (eid, _) in enumerate(order, 1):
        if eid == emp_id:
            return i
    return None


def top_ids(scores: dict[str, float], k: int = 5) -> list[str]:
    return [eid for eid, _ in sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))[:k]]


def spearman(a: dict[str, float], b: dict[str, float]) -> float | None:
    """两分数表在共有键上的 Spearman 等级相关（无并列处理，诊断够用）。"""
    keys = sorted(set(a) & set(b))
    n = len(keys)
    if n < 3:
        return None
    ra = {k: r for r, (k, _) in enumerate(sorted(((k, a[k]) for k in keys), key=lambda kv: -kv[1]))}
    rb = {k: r for r, (k, _) in enumerate(sorted(((k, b[k]) for k in keys), key=lambda kv: -kv[1]))}
    d2 = sum((ra[k] - rb[k]) ** 2 for k in keys)
    return 1.0 - 6.0 * d2 / (n * (n * n - 1))


def chunk_stats(employees: list[dict]) -> dict:
    """问题 3（可脚本化部分）：chunk 粒度与超长清点。"""
    chunks = build_evidence_chunks(employees)
    lens = [len(c["text"]) for c in chunks]
    per_emp: dict[str, int] = {}
    for c in chunks:
        per_emp[c["emp_id"]] = per_emp.get(c["emp_id"], 0) + 1
    # bge-small-zh 默认 max_seq_length=512 token；中文 1 token ≈ 1-2 字，
    # 用 400 字作为「可能被截断」的保守预警线（只作清点，不作断言）
    long_chunks = [c for c in chunks if len(c["text"]) > 400]
    return {
        "n_chunks": len(chunks),
        "len_mean": round(float(np.mean(lens)), 1) if lens else 0.0,
        "len_p50": float(np.percentile(lens, 50)) if lens else 0.0,
        "len_p95": float(np.percentile(lens, 95)) if lens else 0.0,
        "len_max": max(lens) if lens else 0,
        "chunks_per_emp_min": min(per_emp.values()) if per_emp else 0,
        "chunks_per_emp_max": max(per_emp.values()) if per_emp else 0,
        "long_chunks_over_400chars": [
            {"emp_id": c["emp_id"], "source": c["source"], "len": len(c["text"]),
             "head": c["text"][:60]}
            for c in sorted(long_chunks, key=lambda c: -len(c["text"]))[:20]
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Round 3 Day1-2：全 50 人 CE 诊断（L0 只读）")
    parser.add_argument("--jobs", type=str, default=None, help="只跑指定岗位（逗号分隔，如 B06,B10）")
    parser.add_argument("--cache", type=Path, default=config.INTERMEDIATE_DIR / "evidence_cache.npy")
    args = parser.parse_args()

    jobs, gold, employees = load_inputs()
    if args.jobs:
        wanted = {"JOB_" + j if not j.startswith("JOB_") else j for j in args.jobs.split(",")}
        jobs = [j for j in jobs if j["job_id"] in wanted]
    corpus = load_label_corpus()
    emp_ids = [str(e.get("employee_id", "")) for e in employees if e.get("employee_id")]

    print(f"诊断：{len(jobs)} 岗位 × {len(emp_ids)} 员工｜TC_OFFLINE={config.is_offline_mode()}")
    index = EvidenceIndex.build(employees, cache_path=args.cache)
    print(f"证据索引：{len(index.chunks)} chunks")

    print("加载 cross-encoder（bge-reranker-v2-m3，仅本次诊断全量使用）…")
    encoder = _load_cross_encoder()
    if encoder is None:
        raise SystemExit("cross-encoder 不可用，全量 CE 诊断无法进行")

    out_jobs: dict[str, dict] = {}
    for job in jobs:
        jid = str(job["job_id"])
        profile = _offline_extract(job, corpus)
        profile["job_id"] = jid
        profile["title"] = str(job.get("title", ""))
        profile["queries"] = build_queries(profile, corpus)
        gold_id = gold.get(jid, "")

        # ── bi 全员（生产初排同路径）──
        bi_raw_all = index.employee_scores(profile["queries"])
        bi_norm_all: dict[str, float] = {}
        floor = config.MATCH_SEMANTIC_FLOOR
        for eid in emp_ids:
            raw = bi_raw_all.get(eid, 0.0)
            bi_norm_all[eid] = min(1.0, max(0.0, (raw - floor) / (1.0 - floor))) if raw > floor else 0.0

        # ── CE 全员（诊断独有：不让 Top-10 截断掩盖）──
        ce_all = calibrate_t1_with_ce(profile, index, emp_ids, cross_encoder_fn=encoder)

        # ── 生产融合终排（Top-10 CE + blend，同 rank_candidates）──
        fused = rank_candidates(profile, employees, index, cross_encoder_fn=encoder)
        fused_scores = {c["emp_id"]: c["scores"]["total"] for c in fused["candidates"]}
        fused_t1 = {c["emp_id"]: c["scores"]["t1"] for c in fused["candidates"]}
        shortlist = [c["emp_id"] for c in fused["candidates"] if c["ce_calibrated"]]

        gold_bi_rank = rank_of(bi_norm_all, gold_id)
        gold_ce_rank = rank_of(ce_all, gold_id)
        gold_fused_rank = rank_of(fused_scores, gold_id)
        gold_in_top10 = gold_bi_rank is not None and gold_bi_rank <= config.MATCH_RERANK_TOPN

        # 量纲对比（问题 4）：短名单成员 bi_norm vs ce01
        pair_stats = None
        if shortlist:
            diffs = [ce_all[e] - bi_norm_all[e] for e in shortlist if e in ce_all]
            pair_stats = {
                "shortlist_n": len(shortlist),
                "bi_mean": round(float(np.mean([bi_norm_all[e] for e in shortlist])), 4),
                "ce_mean": round(float(np.mean([ce_all[e] for e in shortlist if e in ce_all])), 4),
                "ce_minus_bi_mean": round(float(np.mean(diffs)), 4) if diffs else None,
            }

        ce_vals = list(ce_all.values())
        out_jobs[jid] = {
            "title": profile["title"],
            "gold_emp_id": gold_id,
            "n_queries": len(profile["queries"]),
            "gold_bi_rank": gold_bi_rank,
            "gold_in_bi_top10": gold_in_top10,  # = 生产路径 CE 是否见到了金标
            "gold_ce_rank_all50": gold_ce_rank,
            "gold_fused_rank": gold_fused_rank,
            "ce_score_stats": {
                "min": round(min(ce_vals), 4), "max": round(max(ce_vals), 4),
                "mean": round(float(np.mean(ce_vals)), 4),
                "gold": round(ce_all.get(gold_id, 0.0), 4),
            },
            "bi_norm_stats": {
                "min": round(min(bi_norm_all.values()), 4),
                "max": round(max(bi_norm_all.values()), 4),
                "mean": round(float(np.mean(list(bi_norm_all.values()))), 4),
                "gold": round(bi_norm_all.get(gold_id, 0.0), 4),
            },
            "spearman_ce_vs_bi_all50": None
            if not ce_all else round(spearman(ce_all, bi_norm_all) or 0.0, 4),
            "top5_bi": top_ids(bi_norm_all),
            "top5_ce": top_ids(ce_all),
            "top5_fused": top_ids(fused_scores),
            "gold_fused_t1": fused_t1.get(gold_id),
            "blend_magnitude_check": pair_stats,
        }
        print(f"  {jid}: gold bi#{gold_bi_rank} ce#{gold_ce_rank} fused#{gold_fused_rank} "
              f"| Recall@10={'Y' if gold_in_top10 else 'N'} "
              f"| ce_gold={out_jobs[jid]['ce_score_stats']['gold']}")

    result = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "protocol": "Round3 Day1-2 预注册 §一（已封存 2026-10-22）｜L0 只读回放｜TC_OFFLINE=1",
        "prereg": "docs/preregister_round3_evidence_alignment_20261022.md",
        "n_employees": len(emp_ids),
        "rerank_topn_production": config.MATCH_RERANK_TOPN,
        "blend_production": config.MATCH_RERANK_BLEND,
        "chunk_stats": chunk_stats(employees),
        "jobs": out_jobs,
    }
    out_path = config.DATA_DIR / "experiment" / "day12_ce_diagnostic_20261022.json"
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n结果 JSON: {out_path}")

    # 汇总表（控制台）
    print("\n===== 汇总（判定树见预注册 §一 问题 2 表）=====")
    print(f"{'岗位':<8} {'gold':<7} {'bi#':>4} {'R@10':>4} {'ce#':>4} {'fuse#':>5} {'ce_gold':>7} {'ce_mean':>7}")
    for jid in sorted(out_jobs):
        j = out_jobs[jid]
        print(f"{jid:<8} {j['gold_emp_id']:<7} {str(j['gold_bi_rank']):>4} "
              f"{'Y' if j['gold_in_bi_top10'] else 'N':>4} {str(j['gold_ce_rank_all50']):>4} "
              f"{str(j['gold_fused_rank']):>5} {j['ce_score_stats']['gold']:>7} "
              f"{j['ce_score_stats']['mean']:>7}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
