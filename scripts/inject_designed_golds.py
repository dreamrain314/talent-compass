"""用户金标大修落地（2026-10-23）：注入 4 名设计员工 + 更新金标映射 + GT 标签落盘。

来源（用户提供 xlsx，2026-10-22/23）：
- GT批2·原复核+新增金标汇总表.xlsx：可证性复核结果（原 10 岗 8「仅背景推断」/
  2「不支持」，失败归类以证据缺失为主）→ B01-B04 替换为设计补位金标、B05 换 JZ0036
- 抢人_无替代岗位·新金标设计表.xlsx：JZ0051-54（周清/罗源/韩正/方悦）的 16 条
  裁定 GT 标签（全部「支持」），按岗位一对一免抢人设计

设计纪律：
- 证据字段（项目/证书/360 评语/绩效要点）严格来自用户设计表；**未指明字段一律中性化**
  （中性绩效 B、无技能词培训课、无词根评语），全部列入 MANIFEST 待用户复核
- 注入对象 JZ0051-54 原身份（谭文/董梓轩/程秀英/程睿）从未进管线（phase1 仅 50 人），
  全量替换其 raw 行，无下游引用
- phase1 记录按现有 50 人的 offline-placeholder 模式确定式构造（summary=原文拼接，
  scores_360=维度均分），summary_model 标 designed_injection_v1 溯源
- 引擎全程未见过设计内容——HR 预埋在先条件重建（预注册 §五 泄漏记账口径）

用法：python scripts/inject_designed_golds.py [--dry-run]
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

RAW = ROOT / "data" / "raw"
PHASE1 = ROOT / "data" / "intermediate" / "phase1_output.json"
GT_OUT = ROOT / "data" / "experiment" / "ground_truth_designed_golds.json"

# ── 4 名设计员工（证据字段=用户设计表原文；★ 标记为代拟中性字段）──────────
DESIGNED = [
    {
        "employee_id": "JZ0051", "name": "周清", "age": "38", "gender": "女",
        "political_status": "群众", "education": "本科", "major": "工业工程",
        "department": "质量与标准化部", "job_sequence": "技术研发类",
        "current_position": "质量工程师", "current_level": "P3",
        "hire_date": "2013-06-03", "years_of_service": "13",
        "certificates": "ISO9001内审员证书",  # 用户证据
        "projects": [
            {"project_name": "质量过程控制与问题闭环改进", "role": "核心开发",
             "start_date": "2024-03-01", "end_date": "2025-01-15",
             "tools_used": ["SPC", "FMEA", "8D"],
             "description": "应用SPC/FMEA/8D质量工具开展质量过程控制与问题闭环改进。",
             "team_size": 5},
            {"project_name": "智慧园区工业IoT质量监控平台", "role": "质量负责人",
             "start_date": "2025-02-10", "end_date": "2026-06-30",
             "tools_used": ["工业IoT", "质量门禁"],
             "description": "主导智慧园区工业IoT质量监控平台质量工作，负责质量门禁机制交付。",
             "team_size": 8},
        ],
        # ★ 绩效等级用户未指明 → 中性 B（评语仅复述用户证据中的零缺陷交付）
        "performance": [
            ("2024", "B", "2024年整体良好，按时完成质量过程控制任务，认真负责。"),
            ("2025", "B", "2025年工作态度端正，较好完成质量工具应用交付。"),
            ("2026", "B", "2026年零缺陷交付，质量监控平台质量门禁落地。"),
        ],
        # ★ 培训用户未指明 → 1 门纯噪声课程
        "training": [("安全生产标准化培训", "2024-09-11", "已完成", "76")],
        "eval360": [
            ("专业能力", "4", "质量意识强，零缺陷交付记录", "2026"),       # 用户证据
            ("沟通协作", "4", "口头表达清晰，主导跨部门质量评审", "2026"),   # 用户证据
            ("领导力", "3", "管理经验需积累", "2026"),                      # ★ 中性
            ("责任心", "4", "分内工作尽责到位", "2026"),                    # ★ 中性
            ("学习能力", "3", "态度端正", "2026"),                          # ★ 中性（刻意不用速度词根）
        ],
        "gold_job": "JOB_B01",
    },
    {
        "employee_id": "JZ0052", "name": "罗源", "age": "33", "gender": "男",
        "political_status": "群众", "education": "本科", "major": "数据科学与大数据技术",
        "department": "信息技术部", "job_sequence": "技术研发类",
        "current_position": "Python数据分析工程师", "current_level": "P2",
        "hire_date": "2018-03-12", "years_of_service": "8",
        "certificates": "无",
        "projects": [
            {"project_name": "工业大数据调度平台", "role": "技术负责人",
             "start_date": "2024-05-20", "end_date": "2025-08-30",
             "tools_used": ["Spark", "Flink"],
             "description": "担任工业大数据调度平台技术负责人，主导Spark/Flink调度链路建设，Pandas/SQL日常取数建模支撑。",
             "team_size": 6},
            {"project_name": "数据治理专项", "role": "核心开发",
             "start_date": "2025-09-01", "end_date": "2026-04-15",
             "tools_used": ["数据治理"],
             "description": "参与数据治理专项并完成交付，当年绩效评定为A。",
             "team_size": 4},
        ],
        "performance": [
            ("2024", "B", "2024年整体良好，按时完成调度平台建设任务，认真负责。"),   # ★ 中性
            ("2025", "B", "2025年工作态度端正，较好完成调度链路交付。"),             # ★ 中性
            ("2026", "A", "2026年数据治理专项高质量交付，绩效优秀A。"),             # 用户证据（绩效A）
        ],
        "training": [("安全生产标准化培训", "2023-06-08", "已完成", "80")],  # ★ 中性
        "eval360": [
            ("专业能力", "4", "专业技能扎实", "2026"),                          # ★ 中性
            ("沟通协作", "4", "沟通高效，协作顺畅", "2026"),                     # 用户证据
            ("领导力", "3", "管理经验需积累", "2026"),                          # ★ 中性
            ("责任心", "4", "分内工作尽责到位", "2026"),                        # ★ 中性
            ("学习能力", "4", "学习速度快，快速掌握新调度框架", "2026"),          # 用户证据（速度词根）
        ],
        "gold_job": "JOB_B02",
    },
    {
        "employee_id": "JZ0053", "name": "韩正", "age": "35", "gender": "男",
        "political_status": "群众", "education": "本科", "major": "计算机科学与技术",
        "department": "信息技术部", "job_sequence": "技术研发类",
        "current_position": "Java开发工程师", "current_level": "P3",
        "hire_date": "2015-07-01", "years_of_service": "11",
        "certificates": "信息系统项目管理师",  # 用户证据（证书+负责人实践互证）
        "projects": [
            {"project_name": "ERP系统后端架构升级", "role": "技术负责人",
             "start_date": "2024-04-01", "end_date": "2025-10-31",
             "tools_used": ["Java", "Spring Boot", "微服务", "Linux"],
             "description": "担任ERP系统后端架构师，负责Java/Spring Boot微服务架构与Linux部署。",
             "team_size": 7},
            {"project_name": "工业大数据平台", "role": "核心开发",
             "start_date": "2025-11-05", "end_date": "2026-08-20",
             "tools_used": ["Java", "微服务"],
             "description": "参与工业大数据平台Java微服务后端核心模块开发。",
             "team_size": 9},
        ],
        "performance": [
            ("2024", "B", "2024年整体良好，按时完成后端开发任务，认真负责。"),   # ★ 中性
            ("2025", "A", "2025年后端架构升级高质量交付，绩效优秀A。"),         # 用户证据（2025绩效A）
            ("2026", "B", "2026年工作态度端正，较好完成微服务模块交付。"),       # ★ 中性
        ],
        "training": [("安全生产标准化培训", "2022-11-19", "已完成", "79")],  # ★ 中性
        "eval360": [
            ("专业能力", "4", "专业技能扎实", "2026"),                          # ★ 中性
            ("沟通协作", "4", "团队协作顺畅", "2026"),                          # ★ 中性
            ("领导力", "3", "管理经验需积累", "2026"),                          # ★ 中性
            ("责任心", "4", "分内工作尽责到位", "2026"),                        # ★ 中性
            ("学习能力", "4", "学习速度快，钻研新技术栈", "2026"),               # 用户证据（速度词根）
        ],
        "gold_job": "JOB_B03",
    },
    {
        "employee_id": "JZ0054", "name": "方悦", "age": "40", "gender": "女",
        "political_status": "群众", "education": "本科", "major": "人力资源管理",
        "department": "人力资源部", "job_sequence": "管理职能类",
        "current_position": "人力资源主管", "current_level": "P5",
        "hire_date": "2015-01-05", "years_of_service": "11",
        "certificates": "HR管理师、PMP",  # 用户证据
        "projects": [
            {"project_name": "薪酬体系改革", "role": "项目负责人",
             "start_date": "2024-06-01", "end_date": "2025-05-31",
             "tools_used": ["薪酬设计"],
             "description": "担任薪酬体系改革项目负责人，负责方案设计与落地交付。",
             "team_size": 5},
            {"project_name": "人力资源数字化平台", "role": "项目负责人",
             "start_date": "2025-06-10", "end_date": "2026-07-15",
             "tools_used": ["HR数字化"],
             "description": "担任人力资源数字化平台项目负责人，推进流程数字化落地。",
             "team_size": 6},
        ],
        "performance": [
            ("2024", "B", "2024年整体良好，按时完成薪酬改革任务，认真负责。"),   # ★ 中性
            ("2025", "B", "2025年工作态度端正，较好完成薪酬体系落地。"),         # ★ 中性
            ("2026", "A", "2026年获得跨部门一致认可，绩效优秀A。"),             # 用户证据（2026绩效一级）
        ],
        "training": [("安全生产标准化培训", "2023-04-14", "已完成", "82")],  # ★ 中性
        "eval360": [
            ("专业能力", "4", "专业技能扎实", "2026"),                          # ★ 中性
            ("沟通协作", "4", "跨部门沟通顺畅，2026年获得跨部门一致认可", "2026"), # 用户证据
            ("领导力", "4", "承担负责人角色，具备基层管理能力", "2026"),          # 用户证据
            ("责任心", "4", "分内工作尽责到位", "2026"),                        # ★ 中性
            ("学习能力", "3", "态度端正", "2026"),                              # ★ 中性
        ],
        "gold_job": "JOB_B04",
    },
]

# 用户表 2 的 16 条裁定标签（verbatim，provenance=用户 xlsx）
GT_LABELS = [
    ("JOB_B01", "JZ0051", "周清", "质量体系", "skill", "T1",
     "ISO9001内审员证书 + SPC/FMEA/8D工具实际应用项目（质量过程控制/问题闭环）"),
    ("JOB_B01", "JZ0051", "周清", "智能制造", "skill", "T1",
     "智慧园区工业IoT质量监控平台 质量负责人（项目主导+质量门禁交付）"),
    ("JOB_B01", "JZ0051", "周清", "质量导向", "behavior", "T2",
     "360: 质量意识强、零缺陷交付记录"),
    ("JOB_B01", "JZ0051", "周清", "沟通表达", "behavior", "T2",
     "360: 口头表达清晰、主导跨部门质量评审"),
    ("JOB_B02", "JZ0052", "罗源", "工业大数据分析", "skill", "T1",
     "工业大数据调度平台 Spark/Flink 技术负责人 + 数据治理项目交付（绩效A）"),
    ("JOB_B02", "JZ0052", "罗源", "数据处理分析", "skill", "T1",
     "Python数据分析工程师（Pandas/SQL 日常取数建模）"),
    ("JOB_B02", "JZ0052", "罗源", "学习敏捷性", "behavior", "T2",
     "360: 学习速度快、快速掌握新调度框架（速度词根）"),
    ("JOB_B02", "JZ0052", "罗源", "沟通表达", "behavior", "T2",
     "360: 沟通高效、协作顺畅"),
    ("JOB_B03", "JZ0053", "韩正", "Java开发", "skill", "T1",
     "ERP系统后端架构师（Java/Spring Boot/微服务/Linux部署）技术负责人 + 2025绩效A"),
    ("JOB_B03", "JZ0053", "韩正", "智能制造", "skill", "T1",
     "工业大数据平台 Java微服务后端 核心开发"),
    ("JOB_B03", "JZ0053", "韩正", "项目管理", "skill", "T1",
     "信息系统项目管理师证书 + 项目负责人实践（证书+实践互证）"),
    ("JOB_B03", "JZ0053", "韩正", "学习敏捷性", "behavior", "T2",
     "360: 学习速度快、钻研新技术栈"),
    ("JOB_B04", "JZ0054", "方悦", "人力资源管理", "skill", "T1",
     "人力资源主管10年(P5) + HR管理师证书 + 薪酬体系改革 项目负责人（方案设计+落地交付）"),
    ("JOB_B04", "JZ0054", "方悦", "项目管理", "skill", "T1",
     "人力资源数字化平台 项目负责人 + PMP证书（负责人实践+证书互证）"),
    ("JOB_B04", "JZ0054", "方悦", "跨部门协调", "behavior", "T2",
     "360: 跨部门沟通顺畅、2026跨部门一致认可（绩效一级，无协调负面）"),
    ("JOB_B04", "JZ0054", "方悦", "团队管理", "behavior", "T2",
     "360: 承担负责人角色、具备基层管理能力 + 主管岗"),
]

NEW_GOLD_MAP = {"JOB_B01": "JZ0051", "JOB_B02": "JZ0052", "JOB_B03": "JZ0053",
                "JOB_B04": "JZ0054", "JOB_B05": "JZ0036"}


def replace_roster(dry: bool) -> None:
    path = RAW / "employees.csv"
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        fieldnames = reader.fieldnames
    ids = {d["employee_id"] for d in DESIGNED}
    kept = [r for r in rows if r["employee_id"] not in ids]
    for d in DESIGNED:
        kept.append({k: str(d.get(k, "")) for k in fieldnames})
    kept.sort(key=lambda r: r["employee_id"])
    if not dry:
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            w.writerows(kept)
    print(f"employees.csv: {len(rows)} → {len(kept)} 行（替换 {len(DESIGNED)} 身份）")


def replace_json_projects(dry: bool) -> None:
    path = RAW / "projects.json"
    projs = json.loads(path.read_text(encoding="utf-8-sig"))
    ids = {d["employee_id"] for d in DESIGNED}
    kept = [p for p in projs if p.get("employee_id") not in ids]
    added = 0
    for d in DESIGNED:
        for p in d["projects"]:
            kept.append({"employee_id": d["employee_id"], **p})
            added += 1
    kept.sort(key=lambda p: (p["employee_id"], p.get("start_date", "")))
    if not dry:
        path.write_text(json.dumps(kept, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"projects.json: {len(projs)} → {len(kept)} 条（+{added}）")


def replace_csv_rows(fname: str, build, dry: bool) -> None:
    path = RAW / fname
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        fieldnames = reader.fieldnames
    ids = {d["employee_id"] for d in DESIGNED}
    kept = [r for r in rows if r.get("employee_id") not in ids]
    added = 0
    for d in DESIGNED:
        for tup in build(d):
            row = dict(zip(fieldnames, tup))
            row["employee_id"] = d["employee_id"]
            kept.append(row)
            added += 1
    kept.sort(key=lambda r: r.get("employee_id", ""))
    if not dry:
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            w.writerows(kept)
    print(f"{fname}: {len(rows)} → {len(kept)} 行（+{added}）")


def _perf_rows(d):
    # performance.csv 列: employee_id, year, performance_grade, performance_comment
    return [(d["employee_id"], y, g, c) for (y, g, c) in d["performance"]]


def _train_rows(d):
    # training.csv 列: employee_id, course_name, completion_date, status, score
    return [(d["employee_id"], cn, dt, st, sc) for (cn, dt, st, sc) in d["training"]]


def _eval_rows(d):
    # evaluation_360.csv 列: employee_id, evaluator_id, evaluator_role, dimension, score, comment, year
    roles = ["上级", "同事", "自评", "下属", "同事"]
    evs = []
    for i, (dim, sc, cmt, yr) in enumerate(d["eval360"]):
        evs.append((d["employee_id"], f"JZ000{i % 50 + 1:02d}", roles[i % 5], dim, sc, cmt, yr))
    return evs


def build_phase1_record(d: dict) -> dict:
    """按现有 50 人 offline-placeholder 模式确定式构造 phase1 记录。"""
    perf = [{"year": int(y), "grade": g, "comment": c} for (y, g, c) in d["performance"]]
    projects = [{"project_name": p["project_name"], "role": p["role"],
                 "tools": p["tools_used"], "description": p["description"]}
                for p in d["projects"]]
    training = [{"course_name": cn, "completion_date": dt, "status": st, "score": int(sc)}
                for (cn, dt, st, sc) in d["training"]]
    perf_summary = "；".join(p["comment"] for p in perf)
    proj_summary = "；".join(p["description"] for p in projects)
    eval_summary = "；".join(c for (_, _, c, _) in d["eval360"])
    dims: dict[str, list[float]] = {}
    for (dim, sc, _, _) in d["eval360"]:
        dims.setdefault(dim, []).append(float(sc))
    scores_360 = {k: round(sum(v) / len(v), 4) for k, v in dims.items()}
    return {
        "employee_id": d["employee_id"],
        "structured": {
            "name": d["name"], "age": int(d["age"]), "gender": d["gender"],
            "political_status": d["political_status"], "education": d["education"],
            "major": d["major"], "job_sequence": d["job_sequence"],
            "current_position": d["current_position"], "current_level": d["current_level"],
            "years_of_service": int(d["years_of_service"]),
            "certificates": d["certificates"],
        },
        "performance": perf,
        "projects": projects,
        "training": training,
        "text_summaries": {
            "performance_summary": perf_summary,
            "project_summary": proj_summary,
            "evaluation_summary": eval_summary,
        },
        "scores_360": scores_360,
        "confidence_360": 0.8,
        "anchors": {
            "performance": [perf[0]["comment"][:8]] if perf else [],
            "projects": [projects[0]["description"][:8]] if projects else [],
            "evaluation": [d["eval360"][0][2][:8]] if d["eval360"] else [],
        },
        "anchor_mismatch": False,
        "hallucination_flags": {},
        "summary_model": "designed_injection_v1",  # 溯源标记（区别于 offline-placeholder）
        "data_quality_flags": {"missing_rate": None, "text_sufficient": True,
                               "severe_missing": False, "summary_error": None,
                               "designed_gold": True, "gold_job": d["gold_job"]},
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    dry = args.dry_run
    tag = "[dry] " if dry else ""

    replace_roster(dry)
    replace_json_projects(dry)
    replace_csv_rows("performance.csv", _perf_rows, dry)
    replace_csv_rows("training.csv", _train_rows, dry)
    replace_csv_rows("evaluation_360.csv", _eval_rows, dry)

    # phase1 追加（先备份语义由 git 承担；去重防重跑翻倍）
    data = json.loads(PHASE1.read_text(encoding="utf-8"))
    existing = {e["employee_id"] for e in data["employees"]}
    added = 0
    for d in DESIGNED:
        if d["employee_id"] in existing:
            print(f"{tag}{d['employee_id']} 已在 phase1，跳过")
            continue
        data["employees"].append(build_phase1_record(d))
        added += 1
    if not dry and added:
        data["employees"].sort(key=lambda e: e["employee_id"])
        PHASE1.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{tag}phase1_output.json: +{added} 员工 → 共 {len(data['employees'])} 人")

    # GT 标签落盘
    gt = {
        "_meta": {
            "status": "[USER_DESIGNED_ADJUDICATED]",
            "created": "2026-10-23",
            "source": "抢人_无替代岗位·新金标设计表.xlsx（用户设计+裁定，16/16 支持）",
            "provenance": "用户设计证据 → 注入 raw（JZ0051-54 原闲置身份替换）→ 引擎盲配；"
                          "设计时点先于任何引擎运行（HR 预埋在先条件重建）",
            "note": "★字段清单见 scripts/inject_designed_golds.py MANIFEST 注释（未指明字段中性化）",
        },
    }
    for (job, eid, name, label, cat, tier, ev) in GT_LABELS:
        gt.setdefault(eid, {"name": name, "profile": {}, "labels": []})
        gt[eid]["labels"].append({"label": label, "category": cat, "tier": tier,
                                  "evidence": ev, "weighted": False,
                                  "source_job": job})
    if not dry:
        GT_OUT.write_text(json.dumps(gt, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{tag}GT 标签: {len(GT_LABELS)} 条 → {GT_OUT.name}")

    # 金标映射更新（旧映射保存进 _meta）
    gold_path = ROOT / "data" / "experiment" / "blind_test_gold.json"
    gold = json.loads(gold_path.read_text(encoding="utf-8"))
    old = dict(gold["gold"])
    gold["gold"] = {**old, **NEW_GOLD_MAP}
    gold["_meta"]["revision_2026_10_23"] = {
        "reason": "可证性复核（用户汇总表）：原 5 岗金标 8/10 仅背景推断、2/10 不支持",
        "old_gold": old,
        "new_gold": NEW_GOLD_MAP,
        "b05_note": "JZ0036 郑燕为 GT 池现成人选（审计22年，batch2 已裁定）",
    }
    if not dry:
        gold_path.write_text(json.dumps(gold, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{tag}金标映射: B01→JZ0051, B02→JZ0052, B03→JZ0053, B04→JZ0054, B05→JZ0036")
    return 0


if __name__ == "__main__":
    sys.exit(main())
