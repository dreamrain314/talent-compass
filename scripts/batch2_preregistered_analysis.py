"""batch2 预注册分析（eval_log §二 三问，2026-10-21 冻结，标签到位只执行不发挥）。

问题 1：标签级 P/R——10 名 batch2 员工的抽取匹配结果 vs 裁定 GT（58 条：
支持 55 + 支持(降权) 3；不支持 4 条已排除），按 tier 分层 + bootstrap CI
（对 GT 标签有放回重采样 10,000 次，种子 20261021）。
问题 2：负例排斥力——batch2 员工的裁定 T1 标签与岗位核心要求名零交集
→ 构造型负例，断言其决策档 ≠ recommend（偿还闸门泄漏：REVIEW=0.40 对
负例的排斥力第一次独立检验）。
问题 3：pooled margin CI——需要用户确认 batch2 新金标岗位后方可执行，
本脚本只输出起草候选（见输出末尾）。

只读分析：不改任何评分参数（V2a 冻结维持）。
"""

from __future__ import annotations

import json
import os
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("TC_OFFLINE", "1")

import config  # noqa: E402
from agents.job_analysis import _offline_extract, build_queries  # noqa: E402
from utils.evidence_index import EvidenceIndex  # noqa: E402
from utils.label_embedding import load_label_corpus  # noqa: E402
from utils.match_engine import rank_candidates  # noqa: E402

SEED = 20261021
N_BOOT = 10000
RUN_JSON = ROOT / "data" / "intermediate" / "experiment_5emp_live_20261022_004248_367-bd47.json"
GT_JSON = ROOT / "data" / "experiment" / "ground_truth_batch2_adjudicated.json"
JOBS_JSON = ROOT / "data" / "jobs" / "blind_gold_jobs.json"


def bootstrap_ci(values: list[float], n_boot: int = N_BOOT, seed: int = SEED) -> tuple[float, float]:
    if not values:
        return (0.0, 0.0)
    rng = random.Random(seed)
    means = []
    for _ in range(n_boot):
        sample = [rng.choice(values) for _ in values]
        means.append(sum(sample) / len(sample))
    means.sort()
    return (means[int(0.025 * n_boot)], means[int(0.975 * n_boot)])


def main() -> int:
    run = json.loads(RUN_JSON.read_text(encoding="utf-8"))
    gt = json.loads(GT_JSON.read_text(encoding="utf-8"))
    jobs = json.loads(JOBS_JSON.read_text(encoding="utf-8"))["jobs"]

    # ── 问题 1：标签级 P/R（分层 + CI）──────────────────────────
    # GT label → tier 映射（裁定 58 条）
    gt_tier = {}
    gt_by_emp: dict[str, set[str]] = {}
    for eid, info in gt.items():
        if eid.startswith("_"):
            continue
        gt_by_emp[eid] = {lb["label"] for lb in info["labels"]}
        for lb in info["labels"]:
            gt_tier[(eid, lb["label"])] = lb["tier"]

    items = []  # 抽取映射项: (eid, matched_label, in_gt)
    for pe in run.get("per_employee", []):
        eid = pe.get("employee_id")
        for it in pe.get("path_c") or []:
            items.append((eid, it.get("matched_label"), it.get("in_ground_truth") is True))

    tp = [(e, l) for e, l, ok in items if ok]
    precision = len(tp) / len(items) if items else 0.0
    total_gt = sum(len(v) for k, v in gt_by_emp.items() if not k.startswith("_"))
    hit_gt = {(e, l) for e, l, ok in items if ok}
    recall = len(hit_gt) / total_gt if total_gt else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0

    # tier 分层
    tier_report = {}
    for tier in ("T1", "T2", "T3"):
        tier_tp = sum(1 for e, l in tp if gt_tier.get((e, l)) == tier)
        tier_gt = sum(1 for (e, l) in gt_tier if gt_tier[(e, l)] == tier)
        tier_p = tier_tp / max(1, sum(1 for e, l, ok in items if ok and gt_tier.get((e, l)) == tier))
        tier_r = tier_tp / tier_gt if tier_gt else 0.0
        tier_report[tier] = {"tp": tier_tp, "gt_total": tier_gt, "P": round(tier_p, 3), "R": round(tier_r, 3)}

    # bootstrap CI：R（对 GT 标签重采样——每个 GT 标签"是否被命中"）
    gt_hit_flags = [1 if (e, l) in hit_gt else 0
                    for e, l in gt_tier]
    r_ci = bootstrap_ci([float(x) for x in gt_hit_flags])
    # P 的 CI（对抽取项重采样）
    p_flags = [1.0 if ok else 0.0 for _, _, ok in items]
    p_ci = bootstrap_ci(p_flags)

    print("===== 预注册问题 1：标签级 P/R（batch2，10 员工 / 58 GT / 137 映射项）=====")
    print(f"  P = {precision:.3f}  (95% CI [{p_ci[0]:.3f}, {p_ci[1]:.3f}])")
    print(f"  R = {recall:.3f}  (95% CI [{r_ci[0]:.3f}, {r_ci[1]:.3f}])")
    print(f"  F1 = {f1:.3f}")
    for tier, rep in tier_report.items():
        print(f"  {tier}: P={rep['P']} R={rep['R']} (TP {rep['tp']}/{rep['gt_total']})")

    # ── 问题 2：构造型负例排斥力 ────────────────────────────────
    employees = json.loads((config.INTERMEDIATE_DIR / "phase1_output.json").read_text(encoding="utf-8"))["employees"]
    emp_by_id = {e["employee_id"]: e for e in employees}
    corpus = load_label_corpus()
    idx = EvidenceIndex.build(employees, cache_path=config.INTERMEDIATE_DIR / "evidence_cache.npy")
    b2_ids = [e for e in gt_by_emp]

    print("\n===== 预注册问题 2：构造型负例排斥力（零 T1 交集 → 禁 recommend）=====")
    violations, negatives = [], []
    for job in jobs:
        p = _offline_extract(job, corpus)
        p["job_id"] = job["job_id"]
        p["title"] = job["title"]
        p["queries"] = build_queries(p, corpus)
        req_names = {s["name"] for s in p["skill_requirements"]}
        ranking = rank_candidates(p, employees, idx, cross_encoder_fn=None)
        dec = {c["emp_id"]: c for c in ranking["candidates"]}
        for eid in b2_ids:
            t1_labels = {lb for lb in gt_by_emp[eid]
                         if gt_tier.get((eid, lb)) == "T1"}
            overlap = t1_labels & req_names
            if overlap:
                continue
            c = dec.get(eid)
            if c is None:
                continue
            is_violation = c["decision"] == "recommend"
            negatives.append({"job": job["job_id"], "emp": eid, "total": c["scores"]["total"],
                              "decision": c["decision"], "violation": is_violation})
            if is_violation:
                violations.append((job["job_id"], eid))
            flag = "✗ 违规" if is_violation else "✓"
            print(f"  {flag} {job['job_id']} 负例 {eid} total={c['scores']['total']} [{c['decision']}]"
                  f"（T1交集=∅）")
    if not negatives:
        print("  （无可判定负例）")
    n_neg = len(negatives)
    n_viol = len(violations)
    print(f"  负例排斥力: {n_neg - n_viol}/{n_neg} 通过"
          f"（{'PASS' if n_viol == 0 else 'FAIL'}——偿还闸门泄漏的独立检验）")

    # ── 问题 3：新金标岗位起草候选（需用户确认，pooled CI 暂不执行）────
    print("\n===== 预注册问题 3：batch2 新金标岗位起草候选（待用户确认封存）=====")
    print("  依据裁定 T1/T2/T3 标签密度最高的 5 名 batch2 员工起草：")
    counts = sorted(((e, len(v)) for e, v in gt_by_emp.items()), key=lambda x: -x[1])[:5]
    for e, n in counts:
        print(f"    {e}（{n} 条裁定标签）")

    # 落盘
    out = {
        "generated_at": datetime_now(),
        "seed": SEED,
        "q1": {"precision": round(precision, 3), "recall": round(recall, 3), "f1": round(f1, 3),
               "p_ci": [round(p_ci[0], 3), round(p_ci[1], 3)],
               "r_ci": [round(r_ci[0], 3), round(r_ci[1], 3)],
               "tier": tier_report, "n_items": len(items), "n_gt": total_gt},
        "q2": {"n_negatives": n_neg, "n_violations": n_viol,
               "pass": n_viol == 0, "negatives": negatives},
    }
    out_path = ROOT / "data" / "experiment" / "batch2_preregistered_results.json"
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n结果落盘: {out_path.name}")
    return 0


def datetime_now() -> str:
    from datetime import datetime
    return datetime.now().isoformat(timespec="seconds")


if __name__ == "__main__":
    sys.exit(main())
