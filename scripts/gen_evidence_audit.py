# -*- coding: utf-8 -*-
"""证据审计材料生成器（块 B5）。

从 20260910 live run 文件的 path_c 命中项（in_ground_truth==true）中确定性抽样，
join phase1_output.json（员工原文）与 ground_truth_5.json（GT evidence 列）拼出
「证据原文」，产出人工核验表 CSV（'是否支持' 列留空待人工勾选）。

背景（planner 实证修正）：run JSON 的 path_c 命中项【无】证据原文字段，实测字段仅
concept/matched_label/mapping_source/match_confidence/is_new_label/in_ground_truth，
故证据须从 phase1 + GT 两个只读源 join 拼合。

用法：
    python scripts/gen_evidence_audit.py \
        --runs "data/intermediate/experiment_5emp_live_20260910_*.json" \
        --phase1 data/intermediate/phase1_output.json \
        --gt data/experiment/ground_truth_5.json \
        --out data/audit/evidence_audit_20260910.csv --n 40 --seed 42

返回格式对称（run() 顶层 key 恒为 ok/error/detail），脚本退出码 0=成功、1=失败。
"""

from __future__ import annotations

import argparse
import csv
import glob
import json
import os
import random
import sys
from collections import defaultdict

# ---- 常量（唯一权威定义，不重复） ----
CSV_COLUMNS = [
    "员工ID",
    "姓名",
    "标签",
    "概念(concept)",
    "证据原文",
    "是否支持",
    "来源run文件",
    "match_confidence",
]
UNIT_MAX_CHARS = 150   # 单个原文单元截断长度
MAX_UNITS = 3          # 证据原文最多收录的原文单元数
EVIDENCE_MAX_CHARS = 800  # 证据原文总截断长度


def load_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"{path}: 顶层不是 dict，实际类型 {type(data).__name__}")
    return data


def load_runs(pattern: str) -> list[tuple[str, dict]]:
    """按文件名排序加载所有 run 文件（顺序确定 → 抽样确定）。"""
    files = sorted(glob.glob(pattern))
    if not files:
        raise ValueError(f"run glob 未匹配任何文件: {pattern}")
    return [(os.path.basename(f), load_json(f)) for f in files]


def collect_gt_hits(runs: list[tuple[str, dict]]) -> list[dict]:
    """收集全部 in_ground_truth==true 的 path_c 命中项（附来源文件）。"""
    hits = []
    for fname, run in runs:
        per_emp = run.get("per_employee")
        if not isinstance(per_emp, list):
            continue
        for emp in per_emp:
            if not isinstance(emp, dict):
                continue
            emp_id = emp.get("employee_id")
            for item in emp.get("path_c") or []:
                if not isinstance(item, dict):
                    continue
                if item.get("in_ground_truth") is True:
                    hits.append(
                        {
                            "run_file": fname,
                            "employee_id": emp_id,
                            "concept": item.get("concept", ""),
                            "matched_label": item.get("matched_label", ""),
                            "match_confidence": item.get("match_confidence"),
                        }
                    )
    return hits


def stratified_sample(hits: list[dict], n: int, seed: int) -> list[dict]:
    """按 (employee_id, matched_label) 分层 round-robin 抽样，固定 seed 确定性。

    组内先按确定性 key 排序，组的遍历起点由 random.Random(seed) 决定，
    同参数重跑结果逐字节一致。
    """
    buckets: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for h in hits:
        buckets[(h["employee_id"], h["matched_label"])].append(h)

    def item_key(h: dict) -> tuple:
        return (
            h["run_file"],
            h["concept"],
            h["match_confidence"] if isinstance(h["match_confidence"], (int, float)) else -1.0,
        )

    for key in buckets:
        buckets[key].sort(key=item_key)

    combos = sorted(buckets.keys())
    rng = random.Random(seed)
    start = rng.randrange(len(combos)) if combos else 0
    ordered = combos[start:] + combos[:start]

    picked: list[dict] = []
    idx = {c: 0 for c in ordered}
    while len(picked) < n:
        progressed = False
        for c in ordered:
            if len(picked) >= n:
                break
            if idx[c] < len(buckets[c]):
                picked.append(buckets[c][idx[c]])
                idx[c] += 1
                progressed = True
        if not progressed:
            break  # 所有组已取尽
    return picked


def build_raw_units(phase1_emp: dict) -> list[str]:
    """从 phase1 员工记录提取原文单元：绩效评语 / 项目 / 三段摘要。"""
    units: list[str] = []
    for perf in phase1_emp.get("performance") or []:
        if isinstance(perf, dict) and perf.get("comment"):
            units.append(f"[绩效{perf.get('year', '')}] {perf['comment']}")
    for proj in phase1_emp.get("projects") or []:
        if isinstance(proj, dict):
            seg = f"[项目:{proj.get('project_name', '')}({proj.get('role', '')})] {proj.get('description', '')}"
            units.append(seg)
    ts = phase1_emp.get("text_summaries") or {}
    if isinstance(ts, dict):
        if ts.get("performance_summary"):
            units.append(f"[绩效摘要] {ts['performance_summary']}")
        if ts.get("project_summary"):
            units.append(f"[项目摘要] {ts['project_summary']}")
        if ts.get("evaluation_summary"):
            units.append(f"[评价摘要] {ts['evaluation_summary']}")
    return [u.strip() for u in units if u and u.strip()]


def build_evidence(
    hit: dict,
    gt_evidence: str,
    raw_units: list[str],
) -> str:
    """拼合 GT 侧 evidence + phase1 侧含概念/标签的原文单元，确定性截断。"""
    parts: list[str] = []
    if gt_evidence:
        parts.append(f"【GT证据】{gt_evidence.strip()}")
    keywords = {k for k in (hit["concept"], hit["matched_label"]) if k}
    # 截断容错：概念是长词时其 ≥3 字前缀也参与匹配——上游摘要可能存残词
    # （实例：360 评价摘要被截断在「主动学」，全词「主动学习」匹配失败曾误导核验）
    prefix_kw = {k[:n] for k in keywords if len(k) >= 4 for n in range(len(k) - 1, 2, -1)}
    matched = [u for u in raw_units if any(k in u for k in keywords | prefix_kw)]
    for u in matched[:MAX_UNITS]:
        parts.append(f"【原文】{u[:UNIT_MAX_CHARS]}")
    if not matched:  # 兜底：优先含 GT 证据关键词的单元（360 类行为证据常在评价摘要），再退绩效摘要
        gt_kw = [w for w in (gt_evidence or "").replace("360:", " ").replace("；", " ").replace("、", " ").split() if len(w) >= 3]
        fallback = next((u for u in raw_units if any(w in u for w in gt_kw)), None)
        if fallback is None:
            fallback = next((u for u in raw_units if u.startswith("[绩效摘要]")), raw_units[0] if raw_units else "")
        if fallback:
            parts.append(f"【原文(兜底)】 {fallback[:UNIT_MAX_CHARS]}")
    evidence = " ｜ ".join(parts)
    if not evidence:  # 终极兜底（phase1 该员工完全无原文时）
        evidence = "（phase1 无原文，GT 证据缺失）"
    return evidence[:EVIDENCE_MAX_CHARS]


def run(args: argparse.Namespace) -> dict:
    """执行主体。返回格式对称：{ok, error, detail}。"""
    # 1. 加载输入（data/intermediate、data/experiment 只读，不写回）
    runs = load_runs(args.runs)
    phase1 = load_json(args.phase1)
    gt = load_json(args.gt)

    emp_map: dict[str, dict] = {}
    for emp in phase1.get("employees") or []:
        if isinstance(emp, dict) and emp.get("employee_id"):
            emp_map[emp["employee_id"]] = emp

    gt_map: dict[str, dict] = {k: v for k, v in gt.items() if k != "_meta" and isinstance(v, dict)}

    # 2. 收集 + 抽样
    hits = collect_gt_hits(runs)
    if not hits:
        return {"ok": False, "error": "无 in_ground_truth==true 命中项", "detail": None}
    n_eff = min(args.n, len(hits))
    picked = stratified_sample(hits, n_eff, args.seed)

    # 3. 拼行
    rows = []
    for h in picked:
        emp_id = h["employee_id"]
        p1 = emp_map.get(emp_id, {})
        name = ""
        structured = p1.get("structured") or {}
        if isinstance(structured, dict):
            name = structured.get("name", "")
        if not name and emp_id in gt_map:
            name = gt_map[emp_id].get("name", "")

        gt_evidence = ""
        gt_entry = gt_map.get(emp_id, {})
        for lab in gt_entry.get("labels") or []:
            if isinstance(lab, dict) and lab.get("label") == h["matched_label"]:
                gt_evidence = str(lab.get("evidence", "") or "")
                break

        raw_units = build_raw_units(p1)
        evidence = build_evidence(h, gt_evidence, raw_units)

        conf = h["match_confidence"]
        conf_str = f"{conf:.4f}" if isinstance(conf, (int, float)) else ""

        rows.append(
            {
                "员工ID": emp_id,
                "姓名": name,
                "标签": h["matched_label"],
                "概念(concept)": h["concept"],
                "证据原文": evidence,
                "是否支持": "",  # 待人工
                "来源run文件": h["run_file"],
                "match_confidence": conf_str,
            }
        )

    # 4. 写出（唯一写入点：--out；目录不存在则建）
    out_dir = os.path.dirname(os.path.abspath(args.out))
    os.makedirs(out_dir, exist_ok=True)
    with open(args.out, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    combos = {(r["员工ID"], r["标签"]) for r in rows}
    return {
        "ok": True,
        "error": None,
        "detail": {
            "runs_matched": len(runs),
            "total_gt_hits": len(hits),
            "rows_written": len(rows),
            "distinct_combos": len(combos),
            "out": args.out,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="生成 GT 证据人工核验表 CSV")
    parser.add_argument("--runs", required=True, help="run 文件 glob 模式（引号包裹）")
    parser.add_argument("--phase1", required=True, help="phase1_output.json 路径")
    parser.add_argument("--gt", required=True, help="ground_truth_5.json 路径")
    parser.add_argument("--out", required=True, help="输出 CSV 路径")
    parser.add_argument("--n", type=int, default=40, help="抽样条数")
    parser.add_argument("--seed", type=int, default=42, help="随机种子")
    args = parser.parse_args()

    try:
        result = run(args)
    except Exception as exc:  # noqa: BLE001 - 顶层兜底，保证对称返回
        result = {"ok": False, "error": f"{type(exc).__name__}: {exc}", "detail": None}

    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
