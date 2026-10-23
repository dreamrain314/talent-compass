"""金标排名差距诊断（L0 只读）：为「金标进前五」优化提供分析原料。

对每个未进前五的岗位输出：
1. 前六名 vs 金标：total/coverage/B/P 全分量对照（谁在压、靠什么压）
2. 逐要求对照：金标 v vs 压过者 max v——「输分要求」按权重×差距排序
3. 金标未成立要求（v=0）的召回证据——金标手里有什么但没接上
4. 一键之遥映射：day67 提议池中未入表、但恰好能接通金标证据的候选（用户可直接裁决）
5. B/P 基座对照：设计金标的中性 360 是否先天吃亏（注入设计 vs 池均值）

零参数触碰、零 LLM。用法：python scripts/gold_gap_diagnostic.py [--jobs B02,B04]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

import config  # noqa: E402
from utils.coverage_engine import (  # noqa: E402
    _expand_requirements,
    classify_relation,
    extract_requirements,
    head_lookup_keys,
    load_atomic_splits,
    load_verified_equivalences,
    recall_candidates,
    encode_query_texts,
    score_coverage,
)
from utils.evidence_index import EvidenceIndex  # noqa: E402

FAILING = ["JOB_B02", "JOB_B04", "JOB_B05", "JOB_B06", "JOB_B07", "JOB_B08", "JOB_B09"]
GOLD_MAP = {
    "JOB_B01": "JZ0051", "JOB_B02": "JZ0052", "JOB_B03": "JZ0053", "JOB_B04": "JZ0054",
    "JOB_B05": "JZ0036", "JOB_B06": "JZ0009", "JOB_B07": "JZ0006", "JOB_B08": "JZ0029",
    "JOB_B09": "JZ0037", "JOB_B10": "JZ0025",
}
REPORT = ROOT / "docs" / "reports" / "gold_gap_diagnostic_20261023.md"


def load_inputs():
    jobs = (json.loads((config.DATA_DIR / "jobs" / "blind_gold_jobs.json").read_text(encoding="utf-8"))["jobs"]
            + json.loads((config.DATA_DIR / "jobs" / "blind_gold_jobs_batch2.json").read_text(encoding="utf-8"))["jobs"])
    employees = json.loads((config.INTERMEDIATE_DIR / "phase1_output.json").read_text(encoding="utf-8"))["employees"]
    return {j["job_id"]: j for j in jobs}, employees


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--jobs", default=",".join(FAILING))
    args = ap.parse_args()
    targets = {"JOB_" + j if not j.startswith("JOB_") else j for j in args.jobs.split(",")}

    jobs, employees = load_inputs()
    index = EvidenceIndex.build(employees, cache_path=config.INTERMEDIATE_DIR / "evidence_cache.npy")
    equiv = load_verified_equivalences()
    splits = load_atomic_splits()
    proposals = json.loads((config.DATA_DIR / "experiment" / "day67_equivalence_proposals.json").read_text(encoding="utf-8"))["proposals"]
    table_keys = {k for k in equiv}
    applied_pairs = {(k, v) for k, vs in equiv.items() for v in vs}
    names = {e["employee_id"]: (e.get("structured") or {}).get("name", "") for e in employees}
    positions = {e["employee_id"]: (e.get("structured") or {}).get("current_position", "") for e in employees}
    emps_by_id = {e["employee_id"]: e for e in employees}
    chunk_emp = [c["emp_id"] for c in index.chunks]

    # 池基线（B/P 先天对照）
    pool_b = float(np.mean([r["b"] for r in score_coverage(
        extract_requirements(jobs["JOB_B01"]), employees, index).values()]))

    out_lines = ["# 金标排名差距诊断（L0 只读，2026-10-23）", "",
                 "> 引擎=覆盖引擎+等价表 v1（no-CE 最终分）；池 54 人；仅分析未进前五岗位", ""]
    for jid in sorted(targets):
        job = jobs[jid]
        gid = GOLD_MAP[jid]
        reqs_raw = extract_requirements(job)
        reqs = _expand_requirements(reqs_raw, splits)
        res = score_coverage(reqs_raw, employees, index, equivalences=equiv)
        totals = {eid: r["total"] for eid, r in res.items()}
        order = sorted(totals.items(), key=lambda kv: (-kv[1], kv[0]))
        gold_rank = [i for i, (e, _) in enumerate(order, 1) if e == gid][0]
        g = res[gid]
        top6 = order[:6]
        top5_ids = [e for e, _ in top6]

        print(f"\n{'='*70}\n{jid} {job.get('title','')}｜金标 {gid} {names.get(gid,'')} 排名 {gold_rank}")
        print(f"  金标 total={g['total']} coverage={g['coverage']} B={g['b']} P={g['p']}")
        print(f"  前六名：")
        for i, (eid, t) in enumerate(top6, 1):
            r = res[eid]
            tag = " ←金标" if eid == gid else ""
            print(f"   {i}. {eid} {names.get(eid,'')}（{positions.get(eid,'')}）"
                  f" total={t} cov={r['coverage']} B={r['b']} P={r['p']}{tag}")

        # 输分要求：金标 v < 前五 max v，按 w×Δv 排序
        pressers = [e for e in top5_ids if e != gid]
        print(f"  逐要求输分（金标 v < 压过者 max v，按权重×差距）：")
        req_by_rid = {r["rid"]: r for r in reqs}
        losses = []
        for rid, rr in g["requirements"].items():
            pv = max((res[e]["requirements"].get(rid, {}).get("v", 0) for e in pressers), default=0)
            d = pv - rr["v"]
            if d > 0.01:
                w = req_by_rid[rid]["weight"]
                losses.append((w * d, rid, rr["v"], pv, rr.get("relation"), rr.get("note", "")[:30]))
        losses.sort(reverse=True)
        for loss, rid, gv, pv, rel, note in losses[:8]:
            req = req_by_rid[rid]
            print(f"   [{loss:.2f}分] {rid} v金标={gv} v压者={pv}｜{(req['head'] or req['text'])[:38]}")
        if not losses:
            print("   （无——金标逐要求不输，差距在 B/P 或全员命中同样的分）")

        # 金标 v=0 的要求：手里有什么 + 一键之遥
        print(f"  金标未成立要求（v=0）的召回证据与可接通映射：")
        qvecs = encode_query_texts([r["text"] for r in reqs], None)
        for rid, rr in g["requirements"].items():
            if rr["v"] > 0:
                continue
            req = req_by_rid[rid]
            ri = [i for i, r in enumerate(reqs) if r["rid"] == rid][0]
            idxs = [i for i, c in enumerate(index.chunks) if c["emp_id"] == gid]
            cands = recall_candidates(req, [index.chunks[i] for i in idxs],
                                      index.matrix[idxs], np.asarray(qvecs[ri]).reshape(-1), top_k=2)
            keys = head_lookup_keys(req)
            # 提议池里 req 侧对得上、且证据词出现在金标 chunk 里的未入表映射
            one_tick = []
            req_norm_text = req["text"] + req["head"]
            for p in proposals:
                if (p["req_term"], p["chunk_term"]) in applied_pairs:
                    continue
                k = p["req_term"]
                if k in keys or (len(k) >= 2 and k in req_norm_text):
                    for c in cands:
                        if p["chunk_term"] and p["chunk_term"] in _norm_of(c["text"]):
                            one_tick.append((k, p["chunk_term"], c["text"][:30], p["count"]))
            head_short = (req["head"] or req["text"])[:34]
            ev0 = cands[0]["text"][:34] if cands else "（无召回）"
            print(f"   · {rid} {head_short}")
            print(f"     证据: {ev0}")
            if one_tick:
                for k, ct, _, cnt in one_tick[:3]:
                    print(f"     ★一键之遥: {k} ↔ {ct}（提议支持 {cnt} 对，未入表）")
        # B/P 先天对照
        print(f"  B/P：金标 B={g['b']}（池均值≈{pool_b:.2f}）P={g['p']}｜B 差距贡献≈{(pool_b-g['b'])*10:.1f} 分")

        # 汇总进报告
        out_lines += [f"## {jid} {job.get('title','')}｜金标 {gid} 排名 {gold_rank}", ""]
        out_lines.append("| 排名 | 员工 | 岗位 | total | coverage | B | P |")
        out_lines.append("|---|---|---|---|---|---|---|")
        for i, (eid, t) in enumerate(top6, 1):
            r = res[eid]
            out_lines.append(f"| {i} | {eid} {names.get(eid,'')}{'**←金标**' if eid==gid else ''} | "
                             f"{positions.get(eid,'')} | {t} | {r['coverage']} | {r['b']} | {r['p']} |")
        out_lines.append("")

    REPORT.write_text("\n".join(out_lines), encoding="utf-8")
    print(f"\n报告骨架已落盘: {REPORT}")
    return 0


def _norm_of(s: str) -> str:
    return "".join(str(s).lower().split())


if __name__ == "__main__":
    sys.exit(main())
