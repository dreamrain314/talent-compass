"""Round 3 Day 3-5 冒烟（预注册 §二 实现骨架）：要求—证据对齐覆盖评分。

定位：开发资产调试运行（泄漏记账 §五：旧 5 岗 in-sample / 新 5 岗开发资产），
**非验收**——验收须等 Day 8 冻结 + Day 9-10 新采岗位。要求集为离线解析初版，
尚未人工核验冻结（§2.1 验收前置条件），本脚本结果只用于：骨架连通性检查、
证据矩阵样例、覆盖率分布观察、CE 成本实测（延迟数据写入验收报告的输入）。

用法（talent-compass 根目录）：
    python scripts/day35_coverage_smoke.py                  # 10 岗全量（含 CE）
    python scripts/day35_coverage_smoke.py --jobs B06,B01   # 指定岗位
    python scripts/day35_coverage_smoke.py --no-ce          # 规则通道（快，验证确定性）
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("TC_OFFLINE", "1")  # 运行时零 LLM（CE 本地 + 规则）

import config  # noqa: E402
from scripts.day12_ce_full_diagnostic import load_inputs, rank_of  # noqa: E402
from utils.coverage_engine import (  # noqa: E402
    build_evidence_matrix,
    extract_requirements,
    load_verified_equivalences,
    score_coverage,
)
from utils.evidence_index import EvidenceIndex  # noqa: E402
from utils.label_embedding import load_label_corpus  # noqa: E402  # noqa: F401 (保持导入路径一致性)


def main() -> int:
    parser = argparse.ArgumentParser(description="Round 3 Day3-5 覆盖评分冒烟（开发资产，非验收）")
    parser.add_argument("--jobs", type=str, default=None, help="只跑指定岗位（逗号分隔，如 B06,B01）")
    parser.add_argument("--no-ce", action="store_true", help="跳过 CE（规则+双通道，确定性最快）")
    parser.add_argument("--cache", type=Path, default=config.INTERMEDIATE_DIR / "evidence_cache.npy")
    args = parser.parse_args()

    jobs, gold, employees = load_inputs()
    if args.jobs:
        wanted = {"JOB_" + j if not j.startswith("JOB_") else j for j in args.jobs.split(",")}
        jobs = [j for j in jobs if j["job_id"] in wanted]

    index = EvidenceIndex.build(employees, cache_path=args.cache)
    equiv = load_verified_equivalences()
    encoder = None
    if not args.no_ce:
        print("加载 cross-encoder（bge-reranker-v2-m3，逐对评分）…")
        from utils.label_matching import _load_cross_encoder

        loaded = _load_cross_encoder()
        if loaded is None:
            print("⚠ CE 不可用，回退 --no-ce 规则通道")
        else:
            # 双契约（同 match_engine.calibrate_t1_with_ce）：本版 sentence-transformers
            # 的 CrossEncoder.__call__ 走不通（'list' has no attribute 'get'），必须走 .predict
            encoder = loaded.predict if hasattr(loaded, "predict") else loaded

    out_jobs: dict[str, dict] = {}
    t0 = time.time()
    n_pairs = 0
    for job in jobs:
        jid = str(job["job_id"])
        reqs = extract_requirements(job)
        gold_id = gold.get(jid, "")
        t_job = time.time()
        res = score_coverage(reqs, employees, index, cross_encoder_fn=encoder,
                             equivalences=equiv)
        totals = {eid: r["total"] for eid, r in res.items()}
        gold_rank = rank_of(totals, gold_id)
        gold_res = res.get(gold_id, {})
        # CE 成本：每要求×每员工×k
        n_pairs += len(reqs) * len(employees) * (config.COVERAGE_RECALL_K if encoder else 0)
        cov_vals = [r["coverage"] for r in res.values()]
        out_jobs[jid] = {
            "title": str(job.get("title", "")),
            "gold_emp_id": gold_id,
            "n_requirements": len(reqs),
            "requirements": [
                {"rid": r["rid"], "head": r["head"], "instances": r["instances"],
                 "kind": r["kind"], "weight": r["weight"]}
                for r in reqs
            ],
            "gold_total": gold_res.get("total"),
            "gold_coverage": gold_res.get("coverage"),
            "gold_rank_among_50": gold_rank,
            "coverage_stats": {
                "mean": round(sum(cov_vals) / len(cov_vals), 4) if cov_vals else 0.0,
                "max": round(max(cov_vals), 4) if cov_vals else 0.0,
            },
            "top5": [eid for eid, _ in sorted(totals.items(), key=lambda kv: (-kv[1], kv[0]))[:5]],
        }
        print(f"  {jid}: m={len(reqs)} 金标 total={gold_res.get('total')} "
              f"coverage={gold_res.get('coverage')} rank={gold_rank} "
              f"（{time.time() - t_job:.1f}s）")

    result = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "protocol": "Round3 Day3-5 冒烟（开发资产调试，非验收；要求集未人工核验冻结）",
        "prereg": "docs/preregister_round3_evidence_alignment_20261022.md",
        "ce_enabled": encoder is not None,
        "elapsed_seconds": round(time.time() - t0, 1),
        "ce_pairs_estimated": n_pairs,
        "equivalence_table_size": len(equiv),
        "jobs": out_jobs,
    }
    out_path = config.DATA_DIR / "experiment" / (
        f"day35_coverage_smoke_{datetime.now().strftime('%Y%m%d')}.json")
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n结果 JSON: {out_path}（总耗时 {result['elapsed_seconds']}s，CE 对数 ~{n_pairs}）")

    # 证据矩阵样例：B06 金标（失败案例的「哪里不知道」展示）
    print("\n===== 证据矩阵样例（B06 金标 JZ0009）=====")
    b06 = next((j for j in jobs if j["job_id"] == "JOB_B06"), None)
    if b06:
        reqs = extract_requirements(b06)
        res = score_coverage(reqs, [e for e in employees if e.get("employee_id") == gold.get("JOB_B06")],
                             index, cross_encoder_fn=None, equivalences=equiv)
        gold_res = res.get(gold.get("JOB_B06"))
        if gold_res:
            for row in build_evidence_matrix(reqs, gold_res):
                ev = row["evidence"][0] if row["evidence"] else {}
                print(f"  [{row['support_status']}] {row['requirement'][:36]}"
                      f" ← {ev.get('source', '—')}「{(ev.get('text') or '')[:40]}」"
                      f" ｜限制：{row['limitation'][:30]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
