"""满分探针员工入库（用户指令：作为测试展示进员工库，名字带标注）。

- JZ9001-9005（满分甲乙丙丁戊）追加到 raw 五文件 + phase1_output.json
- 名字标注：满分甲【测试】——卡片/档案/匹配结果均可见
- 幂等：已存在跳过；证据构造复用 ceiling_probe.py 的 SYNTH（单一来源）

用法：python scripts/add_probe_employees.py [--dry-run]
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

MARK = "【测试】"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    dry = args.dry_run
    tag = "[dry] " if dry else ""

    src = (Path(__file__).resolve().parent / "ceiling_probe.py").read_text(encoding="utf-8")
    ns = {"__file__": str(Path(__file__).resolve())}
    exec(src.split("SYNTH = [")[0], ns)
    exec("SYNTH = [" + src.split("SYNTH = [")[1].split("\nJOBS = [")[0], ns)
    probes = []
    for e in ns["SYNTH"]:
        e = json.loads(json.dumps(e))  # 深拷贝防污染探针
        e["structured"]["name"] = e["structured"]["name"] + MARK
        e["data_quality_flags"]["probe_employee"] = True
        probes.append(e)
    ids = {e["employee_id"] for e in probes}

    raw = ROOT / "data" / "raw"
    # 1) 花名册
    with open(raw / "employees.csv", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        fieldnames = reader.fieldnames
    have = {r["employee_id"] for r in rows}
    DEPT = {"JZ9001": "质量与标准化部", "JZ9002": "信息技术部", "JZ9003": "信息技术部",
            "JZ9004": "人力资源部", "JZ9005": "审计部"}
    added = 0
    for e in probes:
        st = e["structured"]
        row = {
            "employee_id": e["employee_id"], "name": st["name"], "age": st["age"],
            "gender": st["gender"], "political_status": st["political_status"],
            "education": st["education"], "major": st["major"],
            "department": DEPT.get(e["employee_id"], "综合管理部"),
            "job_sequence": st["job_sequence"], "current_position": st["current_position"],
            "current_level": st["current_level"], "hire_date": "2015-01-01",
            "years_of_service": st["years_of_service"], "certificates": st["certificates"],
        }
        if e["employee_id"] in have:  # upsert：修复历史空行
            rows = [row if r["employee_id"] == e["employee_id"] else r for r in rows]
        else:
            rows.append(row)
            added += 1
    rows.sort(key=lambda r: r["employee_id"])
    if not dry:
        with open(raw / "employees.csv", "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader(); w.writerows(rows)
    print(f"{tag}employees.csv: +{added}（upsert 总 {len(rows)} 行）")

    # 2) projects.json
    projs = json.loads((raw / "projects.json").read_text(encoding="utf-8-sig"))
    have_p = {(p.get("employee_id"), p.get("project_name")) for p in projs}
    new_p = [{"employee_id": e["employee_id"], **p} for e in probes for p in e["projects"]
             if (e["employee_id"], p["project_name"]) not in have_p]
    projs.extend(new_p)
    projs.sort(key=lambda p: (p.get("employee_id", ""), p.get("start_date", "")))
    if not dry and new_p:
        (raw / "projects.json").write_text(json.dumps(projs, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{tag}projects.json: +{len(new_p)}")

    # 3-5) performance / training / evaluation_360（同 inject 模式）
    def replace_csv(fname, build):
        """upsert：先删探针 ids 的旧行（修复历史脏数据），再追加正确行。"""
        with open(raw / fname, encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            rr = list(reader)
            fn = reader.fieldnames
        ids = {e["employee_id"] for e in probes}
        rr = [r for r in rr if r.get("employee_id") not in ids]
        new_rows = []
        for e in probes:
            for tup in build(e):
                row = dict(zip(fn, tup))
                row["employee_id"] = e["employee_id"]
                new_rows.append(row)
        rr.extend(new_rows)
        rr.sort(key=lambda r: r.get("employee_id", ""))
        if not dry:
            with open(raw / fname, "w", encoding="utf-8-sig", newline="") as f:
                w = csv.DictWriter(f, fieldnames=fn)
                w.writeheader(); w.writerows(rr)
        print(f"{tag}{fname}: upsert {len(new_rows)}")

    replace_csv("performance.csv", lambda e: [
        (e["employee_id"], p["year"], p["grade"], p["comment"]) for p in e["performance"]])
    replace_csv("training.csv", lambda e: [
        (e["employee_id"], t["course_name"], t["completion_date"], t["status"], t["score"]) for t in e["training"]])
    def eval360_rows(e):
        # finalize 后 _eval360 已删除：从 scores_360（维度均分）+ evaluation_summary（按分句）重建
        comments = (e["text_summaries"]["evaluation_summary"] or "").split("；")
        rows = []
        for i, (dim, avg) in enumerate(e["scores_360"].items()):
            comment = comments[i].strip() if i < len(comments) else f"{dim}维度评估"
            rows.append((e["employee_id"], f"JZ0099{i:02d}",
                         ["上级", "同事", "自评", "下属", "同事"][i % 5], dim, str(int(avg)), comment, "2026"))
        return rows

    replace_csv("evaluation_360.csv", eval360_rows)

    # 6) phase1
    ph_path = ROOT / "data" / "intermediate" / "phase1_output.json"
    ph = json.loads(ph_path.read_text(encoding="utf-8"))
    existing = {e["employee_id"] for e in ph["employees"]}
    added_ph = 0
    for e in probes:
        if e["employee_id"] in existing:
            continue
        rec = {k: v for k, v in e.items() if k != "_eval360"}
        ph["employees"].append(rec)
        added_ph += 1
    ph["employees"].sort(key=lambda x: x["employee_id"])
    if not dry and added_ph:
        ph_path.write_text(json.dumps(ph, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{tag}phase1_output.json: +{added_ph} → 共 {len(ph['employees'])} 人")
    return 0


if __name__ == "__main__":
    sys.exit(main())
