"""匹配流水线编排（M5）：phase1 员工 × 岗位 → Agent③'(解析) → Agent④'(匹配)。

走 PipelineRunner（确定性编排器），输出排序候选 JSON 到 data/intermediate/。

用法（talent-compass 根目录）：
    python scripts/run_matching.py --job data/jobs/blind_gold_jobs.json --job-index 0
    python scripts/run_matching.py --all-jobs data/jobs/blind_gold_jobs.json
    python scripts/run_matching.py --offline ...   # 附加 TC_OFFLINE=1（默认已离线友好）
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

if "--offline" in sys.argv:
    os.environ["TC_OFFLINE"] = "1"

import config  # noqa: E402
from agents.job_analysis import JobAnalysis  # noqa: E402
from agents.matching import MatchingAgent  # noqa: E402
from orchestrator.pipeline import PipelineRunner  # noqa: E402
from utils.logger import generate_trace_id  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="向量直配匹配流水线（Agent③'→④'）")
    parser.add_argument("--job", type=Path, default=config.DATA_DIR / "jobs" / "blind_gold_jobs.json",
                        help="岗位 JSON（含 jobs 数组）或单岗位对象")
    parser.add_argument("--job-index", type=int, default=0, help="--job 为数组时取第几个岗位")
    parser.add_argument("--all-jobs", action="store_true", help="跑岗位文件里全部岗位")
    parser.add_argument("--phase1", type=Path,
                        default=config.INTERMEDIATE_DIR / "phase1_output.json")
    parser.add_argument("--top-k", type=int, default=config.MATCH_TOP_K)
    parser.add_argument("--out-dir", type=Path, default=config.INTERMEDIATE_DIR)
    parser.add_argument("--offline", action="store_true",
                        help="强制 TC_OFFLINE=1（零 LLM 路径；须放在首个位置参数前生效）")
    args = parser.parse_args()

    doc = json.loads(args.job.read_text(encoding="utf-8"))
    if isinstance(doc, dict) and "jobs" in doc:
        jobs = doc["jobs"] if args.all_jobs else [doc["jobs"][args.job_index]]
    else:
        jobs = [doc]

    phase1 = json.loads(args.phase1.read_text(encoding="utf-8"))
    employees = phase1.get("employees") or []
    if not employees:
        raise SystemExit(f"phase1_output 无员工数据: {args.phase1}")

    runner = PipelineRunner(agents=[JobAnalysis(), MatchingAgent()])
    outputs: list[dict] = []
    for job in jobs:
        trace_id = generate_trace_id()
        print(f"▶ 匹配岗位 {job.get('job_id', '')} {job.get('title', '')}（trace {trace_id}）")
        result = runner.run({"job": job, "employees": employees}, trace_id=trace_id)
        ranking = (result.get("final_output") or {}).get("ranking") or {}
        cands = ranking.get("candidates") or []
        print(f"  status={result['status']} candidates={len(cands)}")
        for i, c in enumerate(cands[: args.top_k]):
            print(f"   {i + 1}. {c['name'] or c['emp_id']} "
                  f"{c['scores']['total']:.1f} [{c['decision']}]")
        outputs.append({"trace_id": trace_id, "pipeline_status": result["status"],
                        "steps": result["steps"], "ranking": ranking})

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = args.out_dir / f"matching_output_{stamp}.json"
    out_path.write_text(
        json.dumps({"jobs": outputs}, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    print(f"✔ 输出已落盘: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
