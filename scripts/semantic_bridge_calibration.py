"""语义桥校准（Day0，阈值冻结前唯一一次分布观察）：

正样本 = 等价表全部同指对（表键↔证据词，人工核验过「同一能力的两种说法」——
         语义桥要识别的正是这种关系）
负样本 = 确定性错配（种子 20261025，表键↔非对应证据词交叉采样）
双指标 = bge 词级 cos（fastembed，本地）+ CE sigmoid（bge-reranker-v2-m3，本地）
实证预览 = 盲写 5 岗拆句子句 ↔ 全部表键的 top 对（万强案例目标对落位）

输出：docs/reports/semantic_bridge_calibration_20261025.md
用法：python scripts/semantic_bridge_calibration.py
"""
from __future__ import annotations

import json
import random
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

import config  # noqa: E402
from utils.coverage_engine import extract_requirements, load_verified_equivalences  # noqa: E402
from utils.label_embedding import encode_labels  # noqa: E402
from utils.label_matching import _load_cross_encoder  # noqa: E402

REPORT = ROOT / "docs" / "reports" / "semantic_bridge_calibration_20261025.md"
SEED = 20261025


def cos_pairs(pairs: list[tuple[str, str]]):
    """bge 词级 cos：分批编码两侧再逐对余弦。"""
    lefts = [p[0] for p in pairs]
    rights = [p[1] for p in pairs]
    lv = np.asarray(encode_labels(lefts), dtype=float)
    rv = np.asarray(encode_labels(rights), dtype=float)
    lv = lv / np.where(np.linalg.norm(lv, axis=1, keepdims=True) == 0, 1.0, np.linalg.norm(lv, axis=1, keepdims=True))
    rv = rv / np.where(np.linalg.norm(rv, axis=1, keepdims=True) == 0, 1.0, np.linalg.norm(rv, axis=1, keepdims=True))
    return np.sum(lv * rv, axis=1)


def ce_pairs(pairs: list[tuple[str, str]], encoder_fn):
    """CE sigmoid 批判别（reranker 输出 logit → sigmoid，与 match_engine 口径一致）。"""
    out = encoder_fn([(a, b) for a, b in pairs])
    arr = np.asarray(out, dtype=float)
    return 1.0 / (1.0 + np.exp(-arr))


def pct(arr, q):
    return float(np.percentile(arr, q)) if len(arr) else 0.0


def main() -> int:
    equiv = load_verified_equivalences()
    pos = [(k, v) for k, vs in equiv.items() for v in vs]
    rng = random.Random(SEED)
    all_values = [v for vs in equiv.values() for v in vs]
    keys = list(equiv.keys())
    neg = []
    pos_set = set(pos)
    while len(neg) < len(pos):
        k = rng.choice(keys)
        v = rng.choice(all_values)
        if (k, v) not in pos_set and v not in equiv.get(k, []):
            neg.append((k, v))

    print(f"正样本 {len(pos)} 对｜负样本 {len(neg)} 对（种子 {SEED}）")
    enc = _load_cross_encoder()
    ce_fn = enc.predict if hasattr(enc, "predict") else enc

    pos_cos = cos_pairs(pos)
    neg_cos = cos_pairs(neg)
    pos_ce = ce_pairs(pos, ce_fn)
    neg_ce = ce_pairs(neg, ce_fn)

    def dist(name, arr):
        return (f"{name}: p5={pct(arr,5):.3f} p25={pct(arr,25):.3f} p50={pct(arr,50):.3f} "
                f"p75={pct(arr,75):.3f} p95={pct(arr,95):.3f} mean={arr.mean():.3f}")

    print(dist("正cos", pos_cos))
    print(dist("负cos", neg_cos))
    print(dist("正CE ", pos_ce))
    print(dist("负CE ", neg_ce))

    # 双阈值组合查准率/查全率
    grid = []
    for cos_th in (0.75, 0.80, 0.85, 0.88, 0.90, 0.92):
        for ce_th in (0.5, 0.6, 0.7, 0.8):
            tp = int(((pos_cos >= cos_th) & (pos_ce >= ce_th)).sum())
            fp = int(((neg_cos >= cos_th) & (neg_ce >= ce_th)).sum())
            prec = tp / (tp + fp) if tp + fp else 1.0
            rec = tp / len(pos)
            grid.append((cos_th, ce_th, tp, fp, prec, rec))
    # 实证预览：盲写 5 岗拆句子句 ↔ 表键 top 对
    jobs = json.loads((config.DATA_DIR / "jobs" / "agent_blind_jobs_v1.json").read_text(encoding="utf-8"))["jobs"]
    probe_terms = []
    for job in jobs:
        for r in extract_requirements(job):
            terms = [r["head"]] + list(r["instances"])
            for t in terms:
                if len(t) >= 4 and t not in probe_terms:
                    probe_terms.append(t)
    probe_terms = probe_terms[:80]
    probe_pairs = [(t, k) for t in probe_terms for k in keys]
    print(f"实证矩阵：{len(probe_terms)} 个要求词 × {len(keys)} 表键 = {len(probe_pairs)} 对")
    probe_cos = cos_pairs(probe_pairs)
    probe_ce = ce_pairs(probe_pairs, ce_fn)
    top_idx = np.argsort(-(probe_cos + probe_ce))[:40]

    lines = ["# 语义桥校准报告（阈值冻结依据，2026-10-25）", "",
             f"> 正样本=等价表 {len(pos)} 条同指对（人工核验）；负样本=确定性错配 {len(neg)} 对（种子 {SEED}）",
             f"> 双指标：bge-small-zh 词级 cos + bge-reranker-v2-m3 sigmoid（均本地）", "",
             "## 一、分布", "", "```",
             dist("正样本 cos", pos_cos), dist("负样本 cos", neg_cos),
             dist("正样本 CE", pos_ce), dist("负样本 CE", neg_ce), "```", "",
             "## 二、双阈值组合（查准/查全）", "",
             "| cos≥ | CE≥ | TP | FP | 查准 | 查全 |", "|---|---|---|---|---|---|"]
    for cos_th, ce_th, tp, fp, prec, rec in grid:
        lines.append(f"| {cos_th} | {ce_th} | {tp} | {fp} | {prec:.3f} | {rec:.3f} |")
    lines += ["", "## 三、实证预览：盲写要求词 ↔ 表键 top40（按 cos+CE 排序）", "",
              "| 要求词 | 表键 | cos | CE |", "|---|---|---|---|"]
    for i in top_idx:
        t, k = probe_pairs[i]
        lines.append(f"| {t[:24]} | {k[:24]} | {probe_cos[i]:.3f} | {probe_ce[i]:.3f} |")
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n报告 → {REPORT.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
