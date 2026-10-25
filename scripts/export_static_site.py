"""GitHub Pages 静态站导出器：Python 引擎资产 → site/data/*.json。

导出物（JS 端零硬编码，全部以 Python 口径为准）：
- employees.json   54 人档案 + 预切证据 chunk（chunk_employee 原样，保对齐）
- engine_config.json 等价表(v2.2) + 划界词典(strong/weak/behavior/exclude) + 矩阵 + 参数
- presets.json     15 岗（B01-B10 + 盲写 C01-C05）Python 引擎完整结果（官方口径快照）
- meta.json        来源 commit / 引擎版本 / 生成时间

用法：python scripts/export_static_site.py [--out site]
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import config  # noqa: E402
from utils.coverage_engine import (  # noqa: E402
    _build_professional_lexicons,
    _get_behavior_lexicon,
    extract_requirements,
    load_atomic_splits,
    load_verified_equivalences,
    score_coverage,
)
from utils.evidence_index import EvidenceIndex, chunk_employee  # noqa: E402

SOURCE_LABELS = {
    "position": "岗位与证书", "projects": "项目经历", "performance": "绩效记录",
    "training": "培训记录", "summary_performance": "绩效摘要",
    "summary_project": "项目摘要", "summary_evaluation": "360 评价摘要",
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="site")
    args = ap.parse_args()
    out = ROOT / args.out
    (out / "data").mkdir(parents=True, exist_ok=True)

    employees = json.loads((config.INTERMEDIATE_DIR / "phase1_output.json").read_text(encoding="utf-8"))["employees"]
    index = EvidenceIndex.build(employees, cache_path=config.INTERMEDIATE_DIR / "evidence_cache.npy")
    equiv = load_verified_equivalences()
    splits = load_atomic_splits()
    strong, weak = _build_professional_lexicons()
    behavior = sorted(_get_behavior_lexicon())

    # 1) 员工档案 + 预切 chunk
    emp_out = []
    for e in employees:
        st = e.get("structured") or {}
        emp_out.append({
            "id": e["employee_id"], "name": st.get("name", ""),
            "position": st.get("current_position", ""), "level": st.get("current_level", ""),
            "sequence": st.get("job_sequence", ""), "education": st.get("education", ""),
            "major": st.get("major", ""), "years": st.get("years_of_service", 0),
            "certificates": st.get("certificates", ""),
            "performance": e.get("performance") or [],
            "projects": e.get("projects") or [],
            "training": e.get("training") or [],
            "scores_360": e.get("scores_360") or {},
            "summaries": e.get("text_summaries") or {},
            "chunks": chunk_employee(e),
        })
    (out / "data" / "employees.json").write_text(
        json.dumps(emp_out, ensure_ascii=False), encoding="utf-8")

    # 2) 引擎配置（词典/等价表/参数——JS 规则引擎的全部输入）
    eng_cfg = {
        "equivalences": equiv,
        "deduct": [list(x) for x in _load_deduct_pairs()],
        "atomic_splits": splits,
        "lexicons": {
            "professional_strong": sorted(strong),
            "professional_weak": sorted(weak),
            "behavior": behavior,
        },
        "matrix": {k: list(v) for k, v in config.COVERAGE_JOB_WEIGHT_MATRIX.items()},
        "params": {
            "preferred_k": config.COVERAGE_PREFERRED_K,
            "gate_step": config.COVERAGE_GATE_STEP,
            "recall_k": config.COVERAGE_RECALL_K,
            "w_must": config.COVERAGE_W_MUST,
            "deduction_value": config.COVERAGE_DEDUCTION_VALUE,
            "semantic_bridge": {  # JS 轻量版无编码器：桥与 embedding 召回标注为不可用
                "enabled": False, "reason": "浏览器端无 bge 编码器；在线匹配走词法召回+等价表（官方数字见预计算快照）",
                "python_threshold": config.COVERAGE_SEMANTIC_BRIDGE_THRESHOLD,
            },
        },
        "source_labels": SOURCE_LABELS,
    }
    (out / "data" / "engine_config.json").write_text(
        json.dumps(eng_cfg, ensure_ascii=False), encoding="utf-8")

    # 3) 15 岗官方预计算（Python 引擎完整结果）
    presets = []
    for jf in ("blind_gold_jobs.json", "blind_gold_jobs_batch2.json", "agent_blind_jobs_v1.json"):
        jobs = json.loads((config.DATA_DIR / "jobs" / jf).read_text(encoding="utf-8"))["jobs"]
        for job in jobs:
            jt = str(job.get("job_type", ""))
            res = score_coverage(extract_requirements(job), employees, index,
                                 equivalences=equiv, atomic_splits=splits, job_type=jt)
            order = sorted(res.items(), key=lambda kv: (-kv[1]["total"], kv[0]))
            top = []
            for eid, r in order[:10]:
                emp = next(x for x in employees if x["employee_id"] == eid)
                st = emp.get("structured") or {}
                reqs = {rid: {"v": rr["v"], "relation": rr["relation"], "note": rr["note"],
                              "evidence": rr["evidence"][:1]} for rid, rr in r["requirements"].items()}
                top.append({"id": eid, "name": st.get("name", ""), "position": st.get("current_position", ""),
                            "total": r["total"], "s_prof": r["s_prof"], "s_behav": r["s_behav"],
                            "p": r["p"], "bonus": r["bonus"], "gate": r["required_skill_gate"],
                            "requirements": reqs})
            presets.append({"job_id": job["job_id"], "title": job.get("title", ""),
                            "job_type": jt, "w_matrix": config.COVERAGE_JOB_WEIGHT_MATRIX.get(
                                jt, config.COVERAGE_JOB_WEIGHT_MATRIX["_default"]),
                            "source": jf, "top": top,
                            "jd": {"requirements": job.get("requirements") or [],
                                   "responsibilities": job.get("responsibilities") or []}})
    (out / "data" / "presets.json").write_text(
        json.dumps(presets, ensure_ascii=False), encoding="utf-8")

    # 4) meta
    import subprocess
    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True,
                            text=True, cwd=ROOT).stdout.strip()
    (out / "data" / "meta.json").write_text(json.dumps({
        "generated": datetime.now().isoformat(timespec="seconds"), "commit": commit,
        "engine": "coverage_engine（两类划分+四类矩阵+等价表 v2.2+语义桥 0.72）",
        "pool": f"{len(employees)} 人（含 4 设计金标注入）",
    }, ensure_ascii=False), encoding="utf-8")

    for f in ("employees.json", "engine_config.json", "presets.json", "meta.json"):
        size = (out / "data" / f).stat().st_size
        print(f"{f}: {size/1024:.0f} KB")
    return 0


def _load_deduct_pairs():
    p = config.COVERAGE_EQUIVALENCE_PATH
    if not Path(p).exists():
        return []
    data = json.loads(Path(p).read_text(encoding="utf-8"))
    return [tuple(x) for x in (data.get("deduct") or [])]


if __name__ == "__main__":
    sys.exit(main())
