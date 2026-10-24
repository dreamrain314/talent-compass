"""划界回归闸门：引擎 requirement_type 输出 vs 用户 83 条裁决（xlsx）逐行对照。

用户裁决=冻结真值（《要求类归属·修改后总表(2026-10-24).xlsx》修改后总表 sheet）。
词典或判定次序的任何改动必须保持本对照 100% 一致。

用法：python scripts/verify_typing_adjudication.py [--xlsx 路径]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import config  # noqa: E402
from utils.coverage_engine import (  # noqa: E402
    _expand_requirements,
    extract_requirements,
    load_atomic_splits,
    requirement_type,
)

DEFAULT_XLSX = r"D:\xwechat_files\wxid_ssjx8zam72wp22_6a40\msg\file\2026-10\要求类归属·修改后总表(2026-10-24).xlsx"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--xlsx", default=DEFAULT_XLSX)
    args = ap.parse_args()

    wb = openpyxl.load_workbook(args.xlsx, data_only=True)
    ws = wb["修改后总表"]
    adjudicated: dict[tuple[str, str], str] = {}  # (job, rid) -> class
    for row in ws.iter_rows(min_row=2, values_only=True):
        if not row or row[0] is None:
            continue
        job, _w, rid, _text, cls = row[:5]
        if job and rid and cls:
            adjudicated[(str(job), str(rid))] = str(cls).strip()

    jobs = (json.loads((config.DATA_DIR / "jobs" / "blind_gold_jobs.json").read_text(encoding="utf-8"))["jobs"]
            + json.loads((config.DATA_DIR / "jobs" / "blind_gold_jobs_batch2.json").read_text(encoding="utf-8"))["jobs"])
    splits = load_atomic_splits()

    n_match = n_diff = 0
    diffs: list[tuple] = []
    seen: set[tuple[str, str]] = set()
    for job in jobs:
        jid = str(job["job_id"])
        # 闸门对照用旧抽取（clause_split=False）：用户 83 条表按旧 rid 空间记录，
        # 拆句改动不得污染词典校准对照
        reqs = _expand_requirements(extract_requirements(job, clause_split=False), splits)
        for r in reqs:
            key = (jid, r["rid"])
            seen.add(key)
            got = requirement_type(r)
            want = adjudicated.get(key)
            if want is None:
                continue  # 用户表未覆盖（拆解子项 rid 带后缀，按主 rid 对照）
            if got == want:
                n_match += 1
            else:
                n_diff += 1
                diffs.append((jid, r["rid"], r["head"][:26], want, got))
    # 用户表里有、引擎没产出的 rid（拆解差异）报告出来
    missing = [k for k in adjudicated if k not in seen]

    print(f"对照：一致 {n_match}｜不一致 {n_diff}｜用户表独有 {len(missing)}")
    for jid, rid, head, want, got in diffs:
        print(f"  ✗ {jid}/{rid} {head}｜用户={want} 引擎={got}")
    for k in missing[:10]:
        print(f"  ? 用户表条目引擎未产出: {k}")
    return 0 if (n_diff == 0 and not missing) else 1


if __name__ == "__main__":
    sys.exit(main())
