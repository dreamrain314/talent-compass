"""Day 9 盲写验收跑分（冻结引擎，零改动）：agent 盲写岗位 → Top-5 + 证据摘要 → 用户裁决。

用法：python scripts/day9_blind_jobs_eval.py            # 跑分出报告
      python scripts/day9_blind_jobs_eval.py --top-evidence  # 打印前 2 名证据矩阵
"""
from __future__ import annotations

import argparse
import json
import sys
import os
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("TC_OFFLINE", "1")

import config  # noqa: E402
from utils.coverage_engine import (  # noqa: E402
    _expand_requirements,
    build_evidence_matrix,
    extract_requirements,
    load_atomic_splits,
    load_verified_equivalences,
    score_coverage,
)
from utils.evidence_index import EvidenceIndex  # noqa: E402

JOBS_IN = ROOT / "data" / "jobs" / "agent_blind_jobs_v1.json"
REPORT = ROOT / "docs" / "reports" / "day9_blind_eval_20261024.md"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--top-evidence", action="store_true")
    ap.add_argument("--cache", type=Path, default=config.INTERMEDIATE_DIR / "evidence_cache.npy")
    args = ap.parse_args()

    jobs = json.loads(JOBS_IN.read_text(encoding="utf-8"))["jobs"]
    employees = json.loads((config.INTERMEDIATE_DIR / "phase1_output.json").read_text(encoding="utf-8"))["employees"]
    index = EvidenceIndex.build(employees, cache_path=args.cache)
    equiv = load_verified_equivalences()
    splits = load_atomic_splits()
    names = {e["employee_id"]: (e.get("structured") or {}).get("name", "") for e in employees}
    positions = {e["employee_id"]: (e.get("structured") or {}).get("current_position", "") for e in employees}

    out = {"generated_at": datetime.now().isoformat(timespec="seconds"),
           "protocol": "Day9 盲写验收（agent 盲写 JD / 冻结引擎 / 用户裁决）", "jobs": {}}
    lines = ["# Day 9 盲写岗位验收跑分（冻结引擎，2026-10-24）", "",
             "> 岗位=agent 盲写（未见任何员工数据）｜引擎=冻结版（day8 manifest）｜54 人池｜无金标——**你就是裁判**", ""]
    for job in jobs:
        jid = job["job_id"]
        jt = str(job.get("job_type", ""))
        reqs_raw = extract_requirements(job)
        res = score_coverage(reqs_raw, employees, index, equivalences=equiv,
                             atomic_splits=splits, job_type=jt)
        order = sorted(((eid, r["total"]) for eid, r in res.items()), key=lambda kv: (-kv[1], kv[0]))
        out["jobs"][jid] = {"title": job["title"], "job_type": jt,
                            "top10": [{"emp": e, "name": names.get(e, ""), "pos": positions.get(e, ""),
                                       "total": res[e]["total"], "prof": res[e]["s_prof"],
                                       "behav": res[e]["s_behav"], "p": res[e]["p"],
                                       "bonus": res[e]["bonus"], "gate": bool(res[e]["required_skill_gate"])}
                                      for e, _ in order[:10]]}
        lines.append(f"## {jid} {job['title']}（{jt}｜{job['department']}）")
        lines.append("")
        lines.append("| 排名 | 员工 | 现岗位 | 总分 | S_prof | S_behav | P | bonus | 闸门 |")
        lines.append("|---|---|---|---|---|---|---|---|---|")
        for i, (eid, t) in enumerate(order[:5], 1):
            r = res[eid]
            lines.append(f"| {i} | {eid} {names.get(eid,'')} | {positions.get(eid,'')} | {t} | "
                         f"{r['s_prof']} | {r['s_behav']} | {r['p']} | {r['bonus']} | {'⚠' if r['required_skill_gate'] else '-'} |")
        lines.append("")
        if args.top_evidence:
            print(f"\n===== {jid} {job['title']} =====")
            for i, (eid, t) in enumerate(order[:2], 1):
                r = res[eid]
                print(f"  #{i} {eid} {names.get(eid,'')}（{positions.get(eid,'')}）total={t} "
                      f"prof={r['s_prof']} behav={r['s_behav']}")
                reqs = _expand_requirements(reqs_raw, splits)
                for row in build_evidence_matrix(reqs, r)[:6]:
                    ev = row["evidence"][0] if row["evidence"] else {}
                    print(f"    [{row['support_status']}] {row['requirement'][:30]} ← {(ev.get('text') or '')[:38]}")
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    (ROOT / "data" / "experiment" / "day9_blind_eval_20261024.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"报告 → {REPORT.name}")
    # 控制台精简表
    for jid in sorted(out["jobs"]):
        j = out["jobs"][jid]
        print(f"\n{jid} {j['title']} [{j['job_type']}]")
        for i, t in enumerate(j["top10"][:5], 1):
            print(f"  {i}. {t['emp']} {t['name']}（{t['pos']}）{t['total']} prof={t['prof']} "
                  f"behav={t['behav']} {'⚠闸门' if t['gate'] else ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
