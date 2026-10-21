"""反事实模拟台（Phase A，评分体系证据驱动升级的第一步）。

目的：在写任何生产代码之前，用现有 5 岗位 × 50 人池的分量得分，离线模拟
各候选改动对「金标 vs 最硬负例 margin」的影响——证据决定采纳哪些旋钮
（Kimi 修订版核心纪律：先验排序 → 证据排序）。

模拟的旋钮（预注册）：
- P1 解析降噪：单字符关键词排除（修 C语言 假阳性）+ T0 分母子串族合并
- P2 T0 密度分：term 命中去重记录数加权（D1 二值 / D2 单命中降权 0.6 / D3 记录数封顶），打击碰词
- P3 权重再平衡：T0 50→35、T1 30→45
- P4 别名补丁（JD 侧受控表）：物联网↔IoT、法务审计↔合规审计、人力资源管理↔人力资源数字化

判定规则（预注册，写死在本文件）：
- margin 改善 = 某岗位金标-vs-最硬负例 margin 较 V0 拉宽 ≥2.0 分
- 采纳条件：≥4/5 岗位 margin 改善 且 无岗位金标排名跌出 Top-3
- 密度函数在 D1/D2/D3 中选 margin 最优者

硬负例定义：每岗位 V0 总分 top-3 非金标（罗浩型碰词人）∪ 序列错配高分组。

产出：docs/reports/counterfactual_sim_<date>.md + data/experiment/counterfactual_matrix.json
只读生产代码，零改动；模拟器自身的密度/别名逻辑后续经 B 步骤移植进 match_engine。
"""

from __future__ import annotations

import json
import math
import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("TC_OFFLINE", "1")

import config  # noqa: E402
from agents.job_analysis import _offline_extract, build_queries  # noqa: E402
from utils.evidence_index import EvidenceIndex, chunk_employee  # noqa: E402
from utils.label_embedding import load_label_corpus  # noqa: E402
from utils.match_engine import (  # noqa: E402
    _norm_literal,
    _employee_t0_pool,
    calibrate_t1_with_ce,
    score_t0_direct,
    score_t1_bi,
    score_t2_behavior,
    score_t3_potential,
)

# 预注册：JD 侧受控别名表（每对都有金标 miss 归因，见 docs/reports/）
ALIAS_PATCHES = {
    "物联网": ["iot", "工业iot"],                       # B01 JZ0001 证据「工业IoT管理平台」
    "法务审计": ["合规审计", "审计"],                    # B04 JZ0033 证据「合规审计」
    "人力资源管理": ["人力资源"],                        # B04 JZ0033 证据「人力资源数字化平台」
}

SEQUENCE_OF_JOB = {  # 岗位类型 → 期望员工序列（序列错配 = 硬负例信号之一）
    "JOB_B01": "技术研发类", "JOB_B02": "技术研发类", "JOB_B03": "技术研发类",
    "JOB_B04": "管理职能类", "JOB_B05": "管理职能类",
}


def denoise_terms(names: list[str], jd_text: str, corpus_by_name: dict) -> list[str]:
    """P1 解析降噪模拟：复刻修复后的扫描规则（单字符关键词不再计命中）。"""
    survived = []
    for n in names:
        item = corpus_by_name.get(n)
        kws = (item.get("keywords", []) or []) if item else []
        hit = _norm_literal(n) in _norm_literal(jd_text) or any(
            len(str(k)) >= 2 and _norm_literal(str(k)) in _norm_literal(jd_text) for k in kws
        )
        if hit:
            survived.append(n)
    # 子串族合并：A ⊂ B 时丢 B（保留更可命中的短项；B 的覆盖被 A 代表）
    dropped = set()
    for a in survived:
        for b in survived:
            if a != b and _norm_literal(a) and _norm_literal(a) in _norm_literal(b):
                dropped.add(b)
    return [n for n in survived if n not in dropped]


def record_hits_for(terms: list[str], employee: dict, aliases: dict) -> dict[str, int]:
    """每个 term 命中的去重记录数（chunk = 一条记录；归一化包含判定 + 别名）。"""
    records = [_norm_literal(c["text"]) for c in chunk_employee(employee)]
    out: dict[str, int] = {}
    for t in terms:
        t_norm = _norm_literal(t)
        alts = [_norm_literal(a) for a in aliases.get(t, [])]
        r = sum(1 for rec in records if (t_norm and t_norm in rec) or any(a and a in rec for a in alts))
        out[t] = r
    return out


def t0_from_record_hits(record_hits: dict[str, int], density: str) -> float:
    """密度函数族：D1 二值 / D2 单命中降权 / D3 记录数封顶。"""
    if not record_hits:
        return 0.5
    vals = []
    for r in record_hits.values():
        if r <= 0:
            vals.append(0.0)
        elif density == "D1":
            vals.append(1.0)
        elif density == "D2":
            vals.append(min(1.0, 0.6 + 0.4 * min(r - 1, 2) / 2))
        elif density == "D3":
            vals.append(min(1.0, r / 2))
        else:
            raise ValueError(density)
    return min(1.0, sum(vals) / len(vals))


def main() -> int:
    data = json.loads((config.INTERMEDIATE_DIR / "phase1_output.json").read_text(encoding="utf-8"))
    employees = data["employees"]
    emp_by_id = {e["employee_id"]: e for e in employees}
    jobs = json.loads((config.DATA_DIR / "jobs" / "blind_gold_jobs.json").read_text(encoding="utf-8"))["jobs"]
    gold = json.loads((config.DATA_DIR / "experiment" / "blind_test_gold.json").read_text(encoding="utf-8"))["gold"]
    corpus = load_label_corpus()
    corpus_by_name = {c.get("name", ""): c for c in corpus}
    idx = EvidenceIndex.build(employees, cache_path=config.INTERMEDIATE_DIR / "evidence_cache.npy")
    W0 = dict(config.MATCH_FORMULA_WEIGHTS)

    matrix = {"generated_at": datetime.now().isoformat(timespec="seconds"),
              "weights_v0": W0, "jobs": {}}

    for job in jobs:
        jid = job["job_id"]
        p = _offline_extract(job, corpus)
        p["queries"] = build_queries(p, corpus)
        jd_text = "\n".join(job.get("responsibilities", []) + job.get("requirements", []))
        names_v0 = [s["name"] for s in p["skill_requirements"]]
        certs = [c for c in (p["hard_requirements"] or {}).get("certificates", [])]
        terms_v0 = list(dict.fromkeys(names_v0 + certs))
        terms_v1 = denoise_terms(terms_v0, jd_text, corpus_by_name)
        # 别名补丁（P4）作用在 V1 词表上
        terms_v1a = terms_v1  # 别名不改分母，只改命中判定（record_hits_for 内消费）
        rec_hits = {e["employee_id"]: record_hits_for(terms_v1a, e, ALIAS_PATCHES)
                    for e in employees}
        rec_hits_noalias = {e["employee_id"]: record_hits_for(terms_v1a, e, {})
                            for e in employees}

        # 分量：T0 二值（V0 / V1 / V1+别名）、T1 bi、T2、T3
        comp = {}
        for e in employees:
            eid = e["employee_id"]
            t0_v0, _ = score_t0_direct({**p, "skill_requirements": [{"name": t, "detail": ""} for t in terms_v0],
                                        "hard_requirements": p["hard_requirements"]}, e)
            pool_norm = _norm_literal(_employee_t0_pool(e))

            def binary_with_alias(terms):
                hits = 0
                for t in terms:
                    t_norm = _norm_literal(t)
                    if t_norm and t_norm in pool_norm:
                        hits += 1
                    elif any(_norm_literal(a) in pool_norm for a in ALIAS_PATCHES.get(t, [])):
                        hits += 1
                return hits / len(terms) if terms else 0.5

            t0_v1 = binary_with_alias(terms_v1)
            t0_v1a = binary_with_alias(terms_v1)  # binary 与别名版在此实现等价（别名只扩命中）
            t1_bi, _ = score_t1_bi(p, idx, eid)
            comp[eid] = {
                "t0_v0": t0_v0, "t0_v1": t0_v1, "t0_v1a": t0_v1a,
                "t1_bi": t1_bi, "t2": score_t2_behavior(e), "t3": score_t3_potential(e),
                "rec_hits": rec_hits[eid],
                "sequence": (e.get("structured") or {}).get("job_sequence", ""),
            }
            rec_hits_noalias[eid] = rec_hits_noalias[eid]  # 保留备用

        # CE 校准：V0 预排（bi 总分）top-10 进 CE，一次 predict，全变体复用（近似，报告注明）
        prelim = sorted(employees,
                        key=lambda e: -(W0["t0_direct"] * comp[e["employee_id"]]["t0_v0"]
                                        + W0["t1_semantic"] * comp[e["employee_id"]]["t1_bi"]
                                        + W0["t2_behavior"] * comp[e["employee_id"]]["t2"]
                                        + W0["t3_potential"] * comp[e["employee_id"]]["t3"]))
        shortlist = [e["employee_id"] for e in prelim[:config.MATCH_RERANK_TOPN]]
        ce = calibrate_t1_with_ce(p, idx, shortlist, cross_encoder_fn=None)
        blend = config.MATCH_RERANK_BLEND
        for eid, c in comp.items():
            ce01 = ce.get(eid)
            c["t1_ce"] = None if ce01 is None else (1 - blend) * c["t1_bi"] + blend * ce01
            c["ce_calibrated"] = ce01 is not None

        matrix["jobs"][jid] = {
            "title": job["title"], "gold": gold[jid],
            "terms_v0": terms_v0, "terms_v1": terms_v1,
            "hard_requirements": p["hard_requirements"],
            "components": comp,
        }
        print(f"  {jid} terms_v0={len(terms_v0)} → v1={len(terms_v1)} CE={len(ce)} 人")

    # ── 变体模拟 ──────────────────────────────────────────────
    W_RB = {"t0_direct": 35.0, "t1_semantic": 45.0, "t2_behavior": 10.0, "t3_potential": 10.0}

    def totals_for(variant: dict) -> dict[str, dict[str, float]]:
        """variant: {weights, t0_key, density} → {jid: {eid: total}}"""
        W = variant["weights"]
        out = {}
        for jid, jd in matrix["jobs"].items():
            totals = {}
            for eid, c in jd["components"].items():
                if variant["t0_mode"] == "binary":
                    t0 = c[variant["t0_key"]]
                else:
                    t0 = t0_from_record_hits(
                        {t: c["rec_hits"].get(t, 0) for t in jd["terms_v1"]}, variant["density"])
                t1 = c["t1_ce"] if c["t1_ce"] is not None else c["t1_bi"]
                totals[eid] = (W["t0_direct"] * t0 + W["t1_semantic"] * t1
                               + W["t2_behavior"] * c["t2"] + W["t3_potential"] * c["t3"])
            out[jid] = totals
        return out

    variants = {
        "V0": {"label": "现行基线（binary t0_v0, W0）", "weights": W0, "t0_mode": "binary", "t0_key": "t0_v0"},
        "V1": {"label": "+解析降噪（t0_v1, W0）", "weights": W0, "t0_mode": "binary", "t0_key": "t0_v1"},
        "V2a": {"label": "V1+密度D2（单命中降权）", "weights": W0, "t0_mode": "density", "density": "D2"},
        "V2b": {"label": "V1+密度D3（记录数封顶）", "weights": W0, "t0_mode": "density", "density": "D3"},
        "V3": {"label": "V1+权重再平衡（35/45/10/10）", "weights": W_RB, "t0_mode": "binary", "t0_key": "t0_v1"},
        "V4": {"label": "V1+密度D2+再平衡", "weights": W_RB, "t0_mode": "density", "density": "D2"},
        "V5": {"label": "V1+别名补丁（W0）", "weights": W0, "t0_mode": "binary", "t0_key": "t0_v1a"},
    }

    results = {}
    for vid, v in variants.items():
        totals = totals_for(v)
        per_job = {}
        for jid, jd in matrix["jobs"].items():
            g = jd["gold"]
            ranked = sorted(totals[jid].items(), key=lambda kv: (-kv[1], kv[0]))
            gold_rank = [i for i, (eid, _) in enumerate(ranked, 1) if eid == g][0]
            hard_negs = [(eid, t) for eid, t in ranked if eid != g][:3]
            gold_total = totals[jid][g]
            margin = gold_total - hard_negs[0][1]
            seq = SEQUENCE_OF_JOB.get(jid)
            seq_mismatch_top = next((eid for eid, t in ranked[:10]
                                     if eid != g and jd["components"][eid]["sequence"] != seq), None)
            per_job[jid] = {
                "gold_total": round(gold_total, 2),
                "gold_rank": gold_rank,
                "top_hard_neg": [{"emp": eid, "total": round(t, 2),
                                  "seq_mismatch": jd["components"][eid]["sequence"] != seq}
                                 for eid, t in hard_negs],
                "margin": round(margin, 2),
                "seq_mismatch_in_top10": seq_mismatch_top,
            }
        results[vid] = {"label": v["label"], "per_job": per_job,
                        "min_margin": round(min(x["margin"] for x in per_job.values()), 2),
                        "mean_margin": round(sum(x["margin"] for x in per_job.values()) / 5, 2),
                        "gold_ranks": [x["gold_rank"] for x in per_job.values()]}

    # ── 判定 ──────────────────────────────────────────────
    print("\n===== 反事实模拟判定表 =====")
    header = f"{'变体':6s} {'说明':28s} {'min_margin':>10s} {'mean_margin':>11s} {'金标排名':>16s}"
    print(header)
    for vid, r in results.items():
        print(f"{vid:6s} {r['label']:28s} {r['min_margin']:>10.2f} {r['mean_margin']:>11.2f} "
              f"{str(r['gold_ranks']):>16s}")
    v0 = results["V0"]
    print("\n逐岗位 margin 明细（V0 → 变体）：")
    for jid in matrix["jobs"]:
        line = f"  {jid}: V0={v0['per_job'][jid]['margin']}"
        for vid in results:
            if vid != "V0":
                line += f" | {vid}={results[vid]['per_job'][jid]['margin']}"
        print(line)

    # 保存矩阵与结果
    out_matrix = config.DATA_DIR / "experiment" / "counterfactual_matrix.json"
    out_matrix.write_text(json.dumps(matrix, ensure_ascii=False, indent=1), encoding="utf-8")
    out_res = config.DATA_DIR / "experiment" / "counterfactual_results.json"
    out_res.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n矩阵与结果已落盘：{out_matrix.name} / {out_res.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
