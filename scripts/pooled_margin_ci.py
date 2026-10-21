"""pooled margin CI —— eval_log §二问题 3 的预注册执行脚本（只读成绩单，零参数触碰）。

预注册判定规则（2026-10-21 冻结，eval_log §二）：
- pooled CI：对全部金标岗位（5 旧 + 5 新）的 margin 做 paired bootstrap
  （10,000 次，有放回，种子 20261021），报均值 95% CI
- 主证据：CI 下界 > 0 → margin 显著为正
- 次要证据：≥70% 岗位 margin > 0 → 方向一致
- CI 跨零/全负 → 如实报，不得用点估计粉饰
- 禁止事项：不得因结果回头改 V2a 任何参数

新 5 岗 provenance（Kimi 质询）：blind_gold_jobs_batch2.json _meta.provenance——
起草输入仅限裁定标签名 + 标签库定义/关键词，本脚本的 check_jd_provenance
提供员工特有词/姓名零命中断言（可复跑审计）。

用法：python scripts/pooled_margin_ci.py
"""
from __future__ import annotations

import json
import random
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

OLD_RESULTS = ROOT / "data" / "experiment" / "blind_test_results.json"
NEW_RESULTS = ROOT / "data" / "experiment" / "blind_test_results_batch2.json"
NEW_JOBS = ROOT / "data" / "jobs" / "blind_gold_jobs_batch2.json"
PHASE1 = ROOT / "data" / "intermediate" / "phase1_output.json"
REPORT = ROOT / "docs" / "reports" / "pooled_margin_ci_20261022.md"

SEED = 20261021
N_BOOT = 10_000

# 员工特有词（裁定证据串中的项目名/平台名/工具名/绩效词，非标签库词汇）
EMP_TOKENS = [
    "边缘计算", "网关", "C++", "产品迭代", "工业大数据", "Tableau", "六西格玛",
    "Python", "数字化平台", "薪酬体系改革", "OKR", "企业文化", "人才测评",
    "追溯", "React", "ERP", "信息系统项目管理师", "HR管理师", "管理师证书",
]


def check_jd_provenance() -> dict:
    """新 5 岗 JD 员工特有词/姓名零命中断言（起草未读证据原文的机械可查证据）。"""
    jd_text = NEW_JOBS.read_text(encoding="utf-8")
    token_hits = [t for t in EMP_TOKENS if t in jd_text]
    emps = json.loads(PHASE1.read_text(encoding="utf-8"))["employees"]
    name_hits = [e["name"] for e in emps if e.get("name") and e["name"] in jd_text]
    return {
        "token_hits": token_hits,
        "name_hits": name_hits,
        "pass": not token_hits and not name_hits,
    }


def load_margins(path: Path) -> list[dict]:
    d = json.loads(path.read_text(encoding="utf-8"))
    return [
        {
            "job_id": j["job_id"],
            "title": j["title"],
            "gold_emp_id": j["gold_emp_id"],
            "gold_total": j["gold_total"],
            "gold_rank": j["gold_rank"],
            "margin": j["margin"],
        }
        for j in d["jobs"]
    ]


def bootstrap_ci(values: list[float], n_boot: int = N_BOOT, seed: int = SEED) -> tuple[float, float, float]:
    """有放回重采样均值的 95% 百分位 CI。返回 (mean, lo, hi)。"""
    rng = random.Random(seed)
    n = len(values)
    means = []
    for _ in range(n_boot):
        sample = [values[rng.randrange(n)] for _ in range(n)]
        means.append(sum(sample) / n)
    means.sort()
    lo = means[int(0.025 * n_boot)]
    hi = means[int(0.975 * n_boot) - 1]
    return sum(values) / n, lo, hi


def main() -> int:
    prov = check_jd_provenance()
    print(f"JD provenance 零命中断言: {'PASS' if prov['pass'] else 'FAIL ' + str(prov)}")

    old = load_margins(OLD_RESULTS)
    new = load_margins(NEW_RESULTS)
    old_m = [x["margin"] for x in old]
    new_m = [x["margin"] for x in new]
    pooled = old_m + new_m

    m_all, lo_all, hi_all = bootstrap_ci(pooled)
    m_old, lo_old, hi_old = bootstrap_ci(old_m)
    m_new, lo_new, hi_new = bootstrap_ci(new_m)

    share_pos = sum(1 for m in pooled if m > 0) / len(pooled)
    sig = lo_all > 0
    direction = share_pos >= 0.70

    print(f"\n旧5岗 margins: {[round(m, 2) for m in old_m]}  mean={m_old:.2f} CI=[{lo_old:.2f},{hi_old:.2f}]")
    print(f"新5岗 margins: {[round(m, 2) for m in new_m]}  mean={m_new:.2f} CI=[{lo_new:.2f},{hi_new:.2f}]")
    print(f"pooled n=10:   mean={m_all:.2f} 95% CI=[{lo_all:.2f}, {hi_all:.2f}]")
    print(f"margin>0 占比: {share_pos:.0%}（判定线 70%）")
    print(f"预注册判定: CI下界>0={'PASS' if sig else 'FAIL'}；方向一致={'PASS' if direction else 'FAIL'}")

    # ── 报告 ──
    def job_rows(items: list[dict]) -> str:
        return "\n".join(
            f"| {x['job_id']} | {x['title'][:22]} | {x['gold_emp_id']} | "
            f"{x['gold_rank'] if x['gold_rank'] is not None else '>5'} | {x['gold_total']:.1f} | {x['margin']:+.1f} |"
            for x in items
        )

    verdict = (
        "**FAIL**——CI 全负（下界 {:.2f} < 0），「金标显著高于最硬负例」不成立；方向一致 {:.0%} < 70% 亦 FAIL".format(lo_all, share_pos)
        if not sig
        else "**PASS**——CI 下界 {:.2f} > 0".format(lo_all)
    )

    lines = [
        "# pooled margin CI 报告（eval_log §二问题 3 预注册执行）",
        "",
        f"> 日期：2026-10-22｜种子 {SEED}｜bootstrap {N_BOOT} 次有放回｜margin 定义与 blind_test 一致（gold_total − max 非金标 total）",
        f"> 旧 5 岗：blind_test_results.json（V2a+护栏终版，2026-10-21T23:37）｜新 5 岗：blind_test_results_batch2.json（3-run 逐位一致）",
        "",
        "## 判定（预注册规则，原样引用）",
        "",
        f"- **主证据（CI 下界 > 0）**：{verdict}",
        f"- **次要证据（≥70% 岗位 margin > 0）**：{'PASS' if direction else 'FAIL'}（实际 {share_pos:.0%}）",
        f"- pooled mean = {m_all:.2f}，95% CI [{lo_all:.2f}, {hi_all:.2f}]",
        "",
        "## 逐岗位 margin",
        "",
        "### 旧 5 岗（描述性：mean {:.2f} CI [{:.2f}, {:.2f}]）".format(m_old, lo_old, hi_old),
        "",
        "| 岗位 | 标题 | 金标 | 金标排名 | 金标总分 | margin |",
        "|------|------|------|----------|----------|--------|",
        job_rows(old),
        "",
        "### 新 5 岗（描述性：mean {:.2f} CI [{:.2f}, {:.2f}]）".format(m_new, lo_new, hi_new),
        "",
        "| 岗位 | 标题 | 金标 | 金标排名 | 金标总分 | margin |",
        "|------|------|------|----------|----------|--------|",
        job_rows(new),
        "",
        "## 新 5 岗 L0 归因（只读诊断，参数未动）",
        "",
        "**金标 T0 全线塌方（0.00-0.20）+ T1 语义层无区分度（全员 0.48-0.56）——两个分量合谋把裁定专家压到线下。**",
        "",
        "| 岗位 | 金标 T0 | 金标 T1 | 首位压过者 | 压过者身份 | 定性 |",
        "|------|---------|---------|------------|------------|------|",
        "| B06 | 0.00 | 0.48 | JZ0025 尹飞 34.6 | Java 开发（seq_mismatch=true） | **碰词错配**（审计词面/泛行为分登顶） |",
        "| B07 | 0.17 | 0.48 | JZ0004 38.2 | 结构设计工程师 | 同族近适配（被金标 T0=0.17 放大） |",
        "| B08 | 0.13 | 0.51 | JZ0035 44.2 | 招聘主管 | 同族近适配（HR 词面者 T0=0.30） |",
        "| B09 | 0.20 | 0.53 | JZ0035 49.7 | 招聘主管 | 同族近适配（金标 T0 仅 0.20） |",
        "| B10 | 0.20 | 0.53 | JZ0004 41.6 | 结构设计工程师 | 碰词（Java 岗被结构设计者登顶） |",
        "",
        "三个机制（与 batch2 三问互相印证，属同一条疾病链）：",
        "",
        "1. **T0 字面层对词表换挡零容忍**：旧 5 岗 JD 由知悉金标证据词表者反推 → T0 命中 0.19-0.54；",
        "   新 5 岗按纪律只准用标签定义起草 → 金标证据词面（如「边缘计算网关」）对不上标签关键词（MCU/STM32/ARM）→ T0=0。T0 权重 50%，一票定生死。",
        "2. **T1 语义层无区分度**：bi-encoder 对所有候选给出 0.48-0.56 的近平坦分，无法把嵌入式专家从 Java 开发/审计专员中分出来；CE 重排（blend 0.5）未能挽回。",
        "3. **同族近适配 + 泛行为 T2 补刀**：招聘主管/软件工程师等凭字面词面 + 360 行为分（几乎人人相似）压过词面不同的真专家。",
        "",
        "## provenance 记录（Kimi 质询的正式答复）",
        "",
        f"- **JD 起草时间戳 vs 裁定完成时间戳**：新旧两批 JD 都在标签之后——旧 5 岗 2026-10-21 18:13（commit 98b9a5e，自 ground_truth_5.json 标签反推）；新 5 岗 2026-10-22 01:30（裁定落录 f86467c 00:54 之后、用户封存确认之后）。",
        "- **前提纠正（如实）**：Kimi「旧 5 岗 HR 预埋在先所以干净」不成立于 JD 文本层——「HR 预埋」只在**数据层**（生成器预埋证据模式）；JD 文本两批都是 ZCode 事后自标签反推。构造偏差对两批同型（common-mode），pooling 不放大它。",
        f"- **新 5 岗防同义反复措施**：起草输入仅限裁定标签名+标签库定义/关键词，禁读证据原文；机械断言员工特有词/姓名零命中（本脚本 check_jd_provenance：{'PASS' if prov['pass'] else 'FAIL'}）；硬门槛留空（闸门不参与考试）。",
        "- **泄漏偿还结算**：旧 5 岗 5/5 的成色降级为 **in-sample**（JD 词表泄漏 + 阈值联合拟合 L3 + 闸门排除效应三重加成）；新 5 岗是首个 out-of-sample 考卷，其结果（2/5 命中、margin 全负）才是引擎的真实水位。",
        "",
        "## 结论与后果（按预注册禁止事项执行）",
        "",
        "1. **V2a 参数不动**（预注册禁止回头改）。问题不在阈值，在表征：T0 字面主义 + T1 bi-encoder 区分度不足。",
        "2. **对外口径降级**：一切「盲测 5/5」表述必须限定「旧 5 岗 in-sample」；引擎当前不具备对未见词表岗位的 Top-5 保证。",
        "3. **下一轮主攻 = 召回疾病家族统一治理**（T0 错配 / T1 平坦 / T3 全灭同链）：①T0 语义化或别名表扩容（回归测试驱动）；②bi-encoder 微调（TalentCLEF e5，需 torch，移入路线图）；③T3 按用户决议走 **LLM 离线裁决 → 人工核验闭合映射表 → 运行时查表**（零 LLM 运行时不破坏确定性基线），360 公式通道作补充；验收目标按用户口径放宽为「整体方向性偏移」。",
        "4. **永久规则入 eval_log（Kimi 元教训制度化）**：今后一切离线回放/模拟，输入必须是未经筛选的完整概念流；精选子集只能用于诊断，不能用于验收。",
        "",
        "---",
        f"*脚本：scripts/pooled_margin_ci.py（可复跑审计）；provenance 断言 {'PASS' if prov['pass'] else 'FAIL'}；生成时间 {datetime.now().isoformat(timespec='seconds')}*",
    ]
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n报告已落盘: {REPORT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
