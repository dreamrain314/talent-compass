"""表 v2.1 接桥映射：B02/B04 考题重写 + B05 证据注入后的措辞接桥（按用户杠杆决议口径）。

成因：等价表 v1/v2 的键绑定旧 JD 措辞（如「人力资源六大模块综合实务」），考题重写后
新措辞（「人力资源综合管理实务」「HR数字化」「审计软件」「高级会计师职称」）激活不了
旧键。本脚本补 10 条「新措辞↔既有证据词」接桥——与杠杆一同原理，逐条可否决。
另修：JZ0036 phase1 structured.certificates 漏同步（roster 已加高级会计师）。

用法：python scripts/table_v2_1_bridges.py [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from utils.coverage_engine import _norm_literal  # noqa: E402

TABLE = ROOT / "data" / "jobs" / "equivalence_table.json"
PHASE1 = ROOT / "data" / "intermediate" / "phase1_output.json"

BRIDGES = [
    # B04（新 JD 措辞 ↔ 方悦证据词）
    ("人力资源综合管理实务", "hr管理师", "B04 R01 必要技能"),
    ("人力资源综合管理实务", "人力资源主管", "B04 R01"),
    ("hr数字化", "人力资源数字化平台", "B04 R03 优先项"),
    ("跨部门协调与团队管理能力", "跨部门沟通顺畅", "B04 R05 行为"),
    ("跨部门协调与团队管理能力", "承担负责人角色", "B04 R05 行为"),
    # B05（JD 措辞 ↔ 郑燕新注入审计证据词）
    ("使用审计软件开展内控测试与整改跟踪", "审计软件", "B05 R09 必要技能"),
    ("coso内控框架与风险矩阵方法", "风险矩阵", "B05 R03"),
    ("主导内控审计协调与流程梳理优化", "内控审计协调", "B05 R07"),
    ("高级会计师职称", "高级会计师", "B05 R05 优先项"),
    ("主导内控体系建设与优化", "内控体系建设", "B05 R06 兜底"),
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    dry = args.dry_run

    data = json.loads(TABLE.read_text(encoding="utf-8"))
    before = sum(len(v) for v in data["equivalences"].values())
    for k, v, _why in BRIDGES:
        kn, vn = _norm_literal(k), _norm_literal(v)
        bucket = data["equivalences"].setdefault(kn, [])
        if vn and vn not in bucket:
            bucket.append(vn)
    data["version"] = "v2.1_20261024"
    data["provenance"] += (
        "｜v2.1（2026-10-24）：B02/B04 考题重写与 B05 证据注入后的措辞接桥 10 条"
        "（ZCode 提议，用户杠杆决议口径，逐条可否决——清单见 gold_gap 复盘报告）。"
    )
    if not dry:
        TABLE.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    after = sum(len(v) for v in data["equivalences"].values())
    print(f"[{'dry' if dry else 'OK'}] 表 v2→v2.1：{before}→{after} 条（+{after - before} 接桥）")

    # JZ0036 phase1 证书同步
    ph = json.loads(PHASE1.read_text(encoding="utf-8"))
    rec = next(e for e in ph["employees"] if e["employee_id"] == "JZ0036")
    old_cert = (rec.get("structured") or {}).get("certificates")
    if "高级会计师" not in str(old_cert or ""):
        certs = old_cert if old_cert and old_cert != "无" else ""
        rec["structured"]["certificates"] = (certs + "、" if certs else "") + "高级会计师"
        if not dry:
            PHASE1.write_text(json.dumps(ph, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"[{'dry' if dry else 'OK'}] JZ0036 structured.certificates：{old_cert} → {rec['structured']['certificates']}")
    else:
        print("[skip] JZ0036 证书已同步")
    return 0


if __name__ == "__main__":
    sys.exit(main())
