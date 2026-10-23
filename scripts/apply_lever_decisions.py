"""杠杆决议落地（用户 2026-10-23 三项指令）：表 v2 / B02+B04 考题重写 / B05 审计证据注入。

用法：
    python scripts/apply_lever_decisions.py --dry-run   # 预览
    python scripts/apply_lever_decisions.py             # 执行
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from utils.coverage_engine import _norm_literal  # noqa: E402

TABLE = ROOT / "data" / "jobs" / "equivalence_table.json"
JOBS_OLD = ROOT / "data" / "jobs" / "blind_gold_jobs.json"
RAW_PROJECTS = ROOT / "data" / "raw" / "projects.json"
RAW_ROSTER = ROOT / "data" / "raw" / "employees.csv"
PHASE1 = ROOT / "data" / "intermediate" / "phase1_output.json"

# ── 杠杆一：一键之遥映射全入（用户「全入」决议）──────────────────────
# 来源标记：pool=LLM 提议池未入表条目；zcode=诊断补充提议（非 LLM 池，用户知情）
LEVER1_ENTRIES = [
    ("软件测试", "测试工程师", "pool"),
    ("承担软件测试方案设计", "岗位：测试工程师", "pool"),
    ("质量导向：标准合规", "合规管理体系", "pool"),
    ("交付", "完成工业大数据分析交付", "pool"),
    ("跨部门协调与团队管理行为能力突出", "跨部门沟通顺畅", "pool"),
    ("交付", "成功交付薪酬体系改革", "pool"),
    ("有效倾听", "跨部门沟通顺畅", "pool"),
    ("主导人力资源数字化平台建设与bi分析落地",
     "担任人力资源数字化平台项目负责人，推进流程数字化落地", "pool"),
    ("结构设计工具与仿真分析", "岗位：结构设计工程师", "zcode"),
    ("人力资源六大模块综合实务", "hr管理师", "zcode"),
]

# ── 杠杆二a：B02/B04 考题重写（对齐新金标证据面，剥离旧金标指纹）──────
JOB_B02_NEW = {
    "job_id": "JOB_B02",
    "title": "工业大数据开发工程师（调度与治理方向）",
    "company": "四川九洲电器集团",
    "department": "信息技术部（数据平台组）",
    "job_type": "技术类",
    "responsibilities": [
        "负责工业大数据调度平台的开发与优化，处理数据链路性能问题",
        "承担数据治理专项建设，保障数据质量与项目交付",
        "运用 Python/Pandas/SQL 进行日常取数与建模分析",
        "输出数据分析结果，支撑平台迭代决策",
        "与业务团队沟通协作，推进数据需求落地",
    ],
    "requirements": [
        "熟悉 Spark/Flink 等大数据调度组件",
        "掌握 Python 数据分析与 SQL 取数建模",
        "有数据治理或数据平台项目交付经验者优先",
        "学习能力强，能快速掌握新技术栈",
        "具备良好的沟通协作能力",
    ],
}
JOB_B04_NEW = {
    "job_id": "JOB_B04",
    "title": "人力资源项目负责人（薪酬与数字化方向）",
    "company": "四川九洲电器集团",
    "department": "人力资源部",
    "job_type": "职能类",
    "responsibilities": [
        "统筹人力资源综合管理：规划、绩效、培训与员工关系",
        "主导薪酬体系设计与改革落地",
        "承担人力资源数字化平台项目管理，推进流程线上化",
        "跨部门协调资源，推动项目按期交付",
        "带领项目团队，分配职责并激励成员",
    ],
    "requirements": [
        "熟悉人力资源综合管理实务",
        "具备薪酬体系设计或改革项目经验",
        "有HR数字化或信息化平台项目经验者优先",
        "具备项目管理方法论（PMP/Scrum）",
        "跨部门协调与团队管理能力",
    ],
}

# ── 杠杆二b：B05 郑燕审计项目证据注入（用户决议；日期/工具为中性代拟待复核）──
B05_AUDIT_PROJECTS = [
    {
        "employee_id": "JZ0036",
        "project_name": "企业内控体系建设与优化",
        "role": "项目负责人",
        "start_date": "2023-03-01",
        "end_date": "2024-08-31",
        "description": "主导企业内控体系建设，运用COSO框架与风险矩阵方法开展内控审计协调与流程梳理优化。",
        "team_size": 5,
        "tools_used": ["COSO", "风险矩阵", "审计软件"],
    },
    {
        "employee_id": "JZ0036",
        "project_name": "内控测试与整改跟踪专项",
        "role": "核心成员",
        "start_date": "2025-03-10",
        "end_date": "2026-05-20",
        "description": "参与内控测试与整改跟踪，运用审计软件完成测试执行与问题闭环。",
        "team_size": 4,
        "tools_used": ["审计软件"],
    },
]
B05_CERT_APPEND = "高级会计师"  # JD「优先」项；★代拟待用户复核


def patch_table(dry: bool) -> None:
    data = json.loads(TABLE.read_text(encoding="utf-8"))
    before = sum(len(v) for v in data["equivalences"].values())
    src_count = {}
    for k, v, src in LEVER1_ENTRIES:
        kn, vn = _norm_literal(k), _norm_literal(v)
        bucket = data["equivalences"].setdefault(kn, [])
        if vn and vn not in bucket:
            bucket.append(vn)
        src_count[src] = src_count.get(src, 0) + 1
    data["version"] = "v2_20261023"
    data["provenance"] += (
        "｜v2（2026-10-23 用户「杠杆一全入」决议）：+10 条（LLM 池 8 + ZCode 诊断补充 2——"
        "结构设计工具与仿真分析↔岗位：结构设计工程师、人力资源六大模块综合实务↔hr管理师）。"
    )
    if not dry:
        TABLE.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    after = sum(len(v) for v in data["equivalences"].values())
    print(f"[{'dry' if dry else 'OK'}] 等价表 v1→v2：{before}→{after} 条（+{after-before}，来源 {src_count}）")


def rewrite_jobs(dry: bool) -> None:
    data = json.loads(JOBS_OLD.read_text(encoding="utf-8"))
    old = {j["job_id"]: j for j in data["jobs"]}
    data["jobs"] = [JOB_B02_NEW if j["job_id"] == "JOB_B02"
                    else JOB_B04_NEW if j["job_id"] == "JOB_B04" else j
                    for j in data["jobs"]]
    data.setdefault("_meta", {})["revision_2026_10_23"] = {
        "reason": "杠杆二决议：换金标未换考题——B02 旧 JD 带孟华项目指纹（数字孪生/IoT），"
                  "B04 旧 JD 带崔超世界（人才盘点/预算/BI/会计师）；按新金标（罗源/方悦）证据面重写",
        "old_JOB_B02_title": old["JOB_B02"]["title"],
        "old_JOB_B04_title": old["JOB_B04"]["title"],
        "old_jobs_archived": {"JOB_B02": old["JOB_B02"], "JOB_B04": old["JOB_B04"]},
    }
    if not dry:
        JOBS_OLD.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[{'dry' if dry else 'OK'}] B02→《{JOB_B02_NEW['title']}》 B04→《{JOB_B04_NEW['title']}》（旧文存 _meta.revision）")


def inject_b05(dry: bool) -> None:
    # raw projects.json
    projs = json.loads(RAW_PROJECTS.read_text(encoding="utf-8-sig"))
    existing_names = {p.get("project_name") for p in projs if p.get("employee_id") == "JZ0036"}
    added = [p for p in B05_AUDIT_PROJECTS if p["project_name"] not in existing_names]
    projs.extend(added)
    projs.sort(key=lambda p: (p.get("employee_id", ""), p.get("start_date", "")))
    # roster 证书
    with open(RAW_ROSTER, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        fieldnames = reader.fieldnames
    for r in rows:
        if r["employee_id"] == "JZ0036":
            certs = (r.get("certificates") or "").strip()
            if B05_CERT_APPEND not in certs:
                r["certificates"] = (certs + "、" + B05_CERT_APPEND) if certs and certs != "无" else B05_CERT_APPEND
    # phase1 记录：projects 追加 + project_summary 重拼接（锚点=首条不动）
    ph = json.loads(PHASE1.read_text(encoding="utf-8"))
    rec = next(e for e in ph["employees"] if e["employee_id"] == "JZ0036")
    have = {p["project_name"] for p in rec.get("projects") or []}
    for p in added:
        if p["project_name"] not in have:
            rec["projects"].append({
                "project_name": p["project_name"], "role": p["role"],
                "tools": p["tools_used"], "description": p["description"]})
    rec["text_summaries"]["project_summary"] = "；".join(p["description"] for p in rec["projects"])
    if not dry:
        RAW_PROJECTS.write_text(json.dumps(projs, ensure_ascii=False, indent=1), encoding="utf-8")
        with open(RAW_ROSTER, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            w.writerows(rows)
        PHASE1.write_text(json.dumps(ph, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[{'dry' if dry else 'OK'}] B05 郑燕：+{len(added)} 审计项目（COSO/风险矩阵/审计软件）+证书「{B05_CERT_APPEND}」"
          f"（★日期/团队规模为中性代拟，待用户复核；绩效/培训/360 未动）")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    dry = args.dry_run
    print(f"=== 杠杆决议落地 {'[DRY]' if dry else ''} {datetime.now().isoformat(timespec='seconds')} ===")
    patch_table(dry)
    rewrite_jobs(dry)
    inject_b05(dry)
    return 0


if __name__ == "__main__":
    sys.exit(main())
