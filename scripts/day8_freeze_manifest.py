"""Round 3 Day 8 冻结清单生成：全部可变资产哈希定版（预注册 §四）。

产出 docs/reports/day8_freeze_manifest_20261024.md：
- 代码资产：coverage_engine / config COVERAGE_* 段 / 等价表 / JD 文件 / phase1 池
- 每项记 SHA256 + 版本说明 + 变更重开条件
- 参数快照（矩阵/k/闸门/召回k）逐项列出

用法：python scripts/day8_freeze_manifest.py [--check]  # --check 只校验不写
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import config  # noqa: E402

ASSETS = [
    ("utils/coverage_engine.py", "覆盖引擎（两类划分/拆句/分池/矩阵/加分/k线性闸门/五类关系/等价表双向激活/字面包含快速通道）"),
    ("data/jobs/equivalence_table.json", "人工核验等价表 v2.2（255+10+2 接桥映射/8 拆解组/1 减分对）"),
    ("data/jobs/alias_patches.json", "受控别名（4 对种子 + Python开发→Python）"),
    ("data/jobs/blind_gold_jobs.json", "旧 5 岗 JD（B02/B04 已按新金标重写，旧文存 _meta.revision）"),
    ("data/jobs/blind_gold_jobs_batch2.json", "新 5 岗 JD（开发资产）"),
    ("data/jobs/agent_blind_jobs_v1.json", "agent 盲写 5 岗 C01-C05（泛化考卷）"),
    ("data/experiment/blind_test_gold.json", "金标映射（B01-B05 设计金标/JZ0036）"),
    ("data/experiment/blind_test_gold_batch2.json", "新 5 岗金标映射"),
    ("data/intermediate/phase1_output.json", "员工池 59 人（4 设计金标+毛文风险+郑燕审计+5 探针测试员工）"),
    ("data/raw/projects.json", "原始项目记录（设计金标/郑燕审计/毛文风险/探针员工注入）"),
    ("data/raw/employees.csv", "花名册（105 人：100 原始 + 5 探针测试员工）"),
    ("tests/test_coverage_engine.py", "覆盖引擎测试 41 项"),
    ("scripts/verify_typing_adjudication.py", "划界回归闸门（用户 83 条裁决=冻结真值）"),
    ("scripts/day35_coverage_smoke.py", "冒烟协议脚本"),
    ("scripts/day9_blind_jobs_eval.py", "盲写验收跑分脚本"),
    ("scripts/day67_equivalence_adjudication.py", "等价表离线裁决流程（LLM 提议→人工核验→入表）"),
    ("scripts/semantic_bridge_calibration.py", "语义桥校准（阈值 0.72 冻结依据）"),
    ("server/app.py", "本地工作台（已切新覆盖引擎 + 硬性过滤 + 启动预热）"),
]


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()[:16]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    rows = []
    missing = []
    for rel, desc in ASSETS:
        p = ROOT / rel
        if not p.exists():
            missing.append(rel)
            continue
        rows.append((rel, sha256(p), desc))
    if missing:
        print("缺失资产:", missing)
        return 1

    params = {
        "COVERAGE_JOB_WEIGHT_MATRIX": {k: list(v) for k, v in config.COVERAGE_JOB_WEIGHT_MATRIX.items()},
        "COVERAGE_PREFERRED_K": config.COVERAGE_PREFERRED_K,
        "COVERAGE_GATE_STEP": config.COVERAGE_GATE_STEP,
        "COVERAGE_SEMANTIC_BRIDGE_THRESHOLD": getattr(config, "COVERAGE_SEMANTIC_BRIDGE_THRESHOLD", 0.72),
        "COVERAGE_RECALL_K": config.COVERAGE_RECALL_K,
        "COVERAGE_W_MUST": config.COVERAGE_W_MUST,
        "COVERAGE_DEDUCTION_VALUE": config.COVERAGE_DEDUCTION_VALUE,
        "EMBEDDING_MODEL_NAME": config.EMBEDDING_MODEL_NAME,
        "RERANKER_MODEL_NAME": getattr(config, "RERANKER_MODEL_NAME", "bge-reranker-v2-m3"),
    }

    lines = [
        "# Day 8 冻结清单（Round 3 挑战版本，2026-10-24）",
        "",
        f"> 生成：{datetime.now().isoformat(timespec='seconds')}｜依据预注册 §四：模型与映射文件、评分公式与权重、"
        "要求集与解析规则、阈值、依赖版本、种子、批处理配置、输入顺序全部定版记哈希；同分排序以员工 ID 稳定键",
        "",
        "## 一、资产哈希（SHA256 前 16 位）",
        "",
        "| 资产 | 哈希 | 说明 |",
        "|------|------|------|",
    ]
    for rel, h, desc in rows:
        lines.append(f"| `{rel}` | `{h}` | {desc} |")
    lines += [
        "",
        "## 二、参数快照（冻结值）",
        "",
        "```json",
        json.dumps(params, ensure_ascii=False, indent=1),
        "```",
        "",
        "## 三、冻结纪律",
        "",
        "1. 上述资产与参数自本清单落盘起**冻结**：任何改动 = 重开事件，须记 eval_log（含理由与用户授权），并重跑本脚本更新哈希",
        "2. 划界词典改动必须过 `verify_typing_adjudication.py` 83/83 闸门",
        "3. 等价表改动必须走人工核验流程（LLM 提议→用户✓→版本化）",
        "4. **Day 9-10 独立验收（新采岗位）期间零改动**——验收完成前本清单为唯一有效版本",
        "5. 冒烟基线（2026-10-25，59 人池，拆句+线性闸门+语义桥后）：9/10 金标前五（B01#4 B02#2 B03#2 B04#4 B05#5 B06#1 B07#1 B08#1 B09#6 B10#4），B09 缺 3 项待用户裁决（ceiling_probe 复验 5/5 合成员工全要求 v=1：B01 96.8/B02 96.69/B03 89.72/B04 93.27/B05 94.63）",
        "",
        "## 四、效力边界（预注册 §五 口径）",
        "",
        "本清单资产在开发资产上校准（含考题重写/证据注入/接桥等 L3 拟合事件，均已记账 §十四-§十九）；"
        "其泛化证明唯一来源 = Day 9-10 新采岗位独立验收（nDCG@5 主指标 + 指定金标 Top-5 连续性指标）。",
        "",
        f"*脚本：scripts/day8_freeze_manifest.py（--check 复验哈希）｜共 {len(rows)} 项资产*",
    ]
    out = ROOT / "docs" / "reports" / "day8_freeze_manifest_20261024.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"冻结清单已写：{out.name}（{len(rows)} 项资产）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
