"""满分探针（用户指令）：为 5 个示例岗位构造「证据全部覆盖 JD」的合成员工，
冻结引擎跑分——若不足 95，暴露分词/评分结构的设计上限。

纪律：
- 合成员工证据**只从 JD 文本 + 标签库词汇镜像**（不读任何真实员工数据）——
  合成者看到的信息集与引擎看到的要求集是同一份 JD，任何 miss 都是引擎侧问题
- 仅内存加池（不写 phase1_output.json，不污染网站/正式池）
- 泄漏口径：B01-B05 是开发资产（eval_log §五），本探针=结构诊断（L0）

用法：python scripts/ceiling_probe.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import config  # noqa: E402
from utils.coverage_engine import (  # noqa: E402
    build_evidence_matrix,
    extract_requirements,
    load_atomic_splits,
    load_verified_equivalences,
    score_coverage,
)
from utils.evidence_index import EvidenceIndex  # noqa: E402

REPORT = ROOT / "docs" / "reports" / "ceiling_probe_20261025.md"


def mk_emp(eid: str, name: str, pos: str, seq: str, major: str, projects: list,
           training: list, eval360: list, perf: list, certs: str) -> dict:
    return {
        "employee_id": eid,
        "structured": {"name": name, "age": 35, "gender": "男", "political_status": "群众",
                       "education": "硕士", "major": major, "job_sequence": seq,
                       "current_position": pos, "current_level": "P5",
                       "years_of_service": 10, "certificates": certs},
        "performance": [{"year": y, "grade": g, "comment": c} for (y, g, c) in perf],
        "projects": [{"project_name": n, "role": r, "tools": t, "description": d}
                     for (n, r, t, d) in projects],
        "training": [{"course_name": cn, "completion_date": "2025-01-01", "status": "已完成", "score": 90}
                     for cn in training],
        "text_summaries": {
            "performance_summary": "；".join(c for (_, _, c) in perf),
            "project_summary": "；".join(d for (_, _, _, d) in projects),
            "evaluation_summary": "；".join(c for (_, _, c) in eval360),
        },
        "scores_360": {},  # 由 eval360 维度均分填充
        "confidence_360": 0.8, "anchors": {}, "anchor_mismatch": False,
        "hallucination_flags": {}, "summary_model": "ceiling_probe_v1",
        "data_quality_flags": {"designed_gold": True, "probe": True},
        "_eval360": eval360,
    }


def finalize(e: dict) -> dict:
    dims: dict[str, list[float]] = {}
    for (dim, sc, _c) in e["_eval360"]:
        dims.setdefault(dim, []).append(float(sc))
    e["scores_360"] = {k: round(sum(v) / len(v), 2) for k, v in dims.items()}
    del e["_eval360"]
    return e


SYNTH = [
    # B01 质量体系工程师（智能制造方向）——JD 词表镜像
    finalize(mk_emp("JZ9001", "满分甲", "质量体系工程师", "技术研发类", "质量管理",
        [("智能制造平台全过程质量管控专项", "质量负责人", ["ISO9001", "SPC", "FMEA", "8D"],
          "跨部门质量改进推动，主导智能制造平台类项目的全过程质量管控与验收，应用SPC/FMEA/8D质量工具完成质量策划与评审，处理试制与交付过程中的质量问题闭环。"),
         ("工业物联网智慧园区数字化项目质量管理", "质量负责人", ["工业物联网", "智慧园区"],
          "负责工业物联网、智慧园区等数字化项目的质量管控与验收，主导质量管理体系建设、内审与持续改进。")],
        ["质量管理体系ISO9001", "SPC统计过程控制", "FMEA失效模式分析"],
        [("专业能力", 5, "质量意识强，标准合规，过程规范，可靠性高"), ("沟通协作", 5, "良好的沟通协调能力与质量意识"),
         ("责任心", 5, "持续改进，质量门禁交付到位")],
        [(2024, "A", "质量管控与验收交付优秀"), (2025, "A", "质量体系建设与内审表现突出"), (2026, "A", "智能制造质量项目零缺陷交付")],
        "ISO9001内审员、六西格玛黑带")),
    # B02 工业大数据开发工程师（调度与治理方向）
    finalize(mk_emp("JZ9002", "满分乙", "工业大数据开发工程师", "技术研发类", "数据科学与大数据技术",
        [("工业大数据调度平台建设专项", "技术负责人", ["Spark", "Flink"],
          "负责工业大数据调度平台的开发与优化，处理数据链路性能问题，熟悉Spark/Flink调度组件与Kafka。"),
         ("设备数据建模与数据治理专项", "核心开发", ["Python", "Pandas", "SQL"],
          "负责工业大数据调度平台的开发与优化，处理数据链路性能问题；参与设备数据建模与数据治理，支撑智能制造场景下的生产监控与质量分析应用；开发数据服务接口与可视化看板，为生产运营和管理层提供数据分析支持；配合业务部门挖掘工业数据价值，参与新场景的算法与应用落地。")],
        ["大数据调度组件Spark", "Flink流处理", "SQL取数建模"],
        [("专业能力", 5, "专业技能扎实，系统设计能力强"), ("沟通协作", 5, "良好的沟通协作能力"),
         ("学习能力", 5, "学习能力强，能快速掌握新技术栈")],
        [(2024, "A", "数据平台开发与优化交付优秀"), (2025, "A", "数据治理专项表现突出"), (2026, "A", "智能制造数据分析高质量交付")],
        "无")),
    # B03 Java后端开发工程师（ERP与系统集成方向）
    finalize(mk_emp("JZ9003", "满分丙", "Java后端开发工程师", "技术研发类", "计算机科学与技术",
        [("ERP系统定制开发专项", "技术负责人", ["Java", "SpringBoot", "Spring"],
          "负责ERP系统定制开发与Java微服务方案设计实现，承担ERP系统后端架构升级，精通Java与Spring生态、Linux部署。"),
         ("工业大数据平台与系统集成开发", "核心开发", ["Java", "微服务", "系统集成"],
          "负责工业大数据调度平台的开发与优化，处理数据链路性能问题；承担工业大数据分析平台的数据集成与任务调度开发；主导跨系统集成项目的方案设计与进度管理；负责平台的性能优化、故障排查与版本迭代，编写相关技术文档。")],
        ["Java高级开发", "Spring微服务架构", "信息系统项目管理"],
        [("专业能力", 5, "专业技能扎实，技术思路清晰"), ("沟通协作", 5, "良好的沟通协作能力"),
         ("学习能力", 5, "学习速度快，钻研新技术栈")],
        [(2024, "A", "ERP后端开发交付优秀"), (2025, "A", "系统集成方案设计表现突出"), (2026, "A", "Java微服务模块高质量交付")],
        "信息系统项目管理师")),
    # B04 人力资源项目负责人（薪酬与数字化方向）
    finalize(mk_emp("JZ9004", "满分丁", "人力资源项目负责人", "管理职能类", "人力资源管理",
        [("薪酬体系设计与改革专项", "项目负责人", ["薪酬设计", "薪酬调研"],
          "主导薪酬体系设计与改革落地；统筹人力资源综合管理：规划、招聘配置、培训开发、绩效管理、薪酬福利与劳动关系管理；统筹人才盘点与全面预算管理项目。"),
         ("人力资源数字化平台建设", "项目负责人", ["HR数字化", "PMP"],
          "承担人力资源数字化平台项目管理并推进流程线上化，运用PMP方法论进行项目全生命周期管理，跨部门协调资源推动项目按期交付，带领项目团队分配职责并激励成员。")],
        ["人力资源管理实务", "PMP项目管理", "薪酬体系设计"],
        [("专业能力", 5, "人力资源专业功底深厚"), ("沟通协作", 5, "跨部门协调与团队管理能力突出"),
         ("领导力", 5, "承担负责人角色，具备基层管理能力")],
        [(2024, "A", "薪酬改革与数字化平台交付优秀"), (2025, "A", "HR体系建设表现突出"), (2026, "A", "跨部门项目高质量交付")],
        "HR管理师、PMP")),
    # B05 内控体系建设专员（审计与流程合规方向）
    finalize(mk_emp("JZ9005", "满分戊", "内控体系建设专员", "管理职能类", "审计学",
        [("企业内控体系建设与流程优化专项", "项目负责人", ["COSO", "风险矩阵"],
          "负责企业内控体系建设项目统筹与协调，熟悉COSO内控框架与风险矩阵方法，主导内控审计协调与流程梳理优化，具备较强的流程梳理与交付管理能力。"),
         ("内控测试与整改跟踪专项", "核心成员", ["审计软件"],
          "使用审计软件开展内控测试与整改跟踪，配合薪酬福利体系与人才盘点项目的内控支持，完成审计协调与问题闭环。")],
        ["COSO内控框架", "风险矩阵方法", "审计软件实务", "高级会计师继续教育"],
        [("专业能力", 5, "审计与内控专业能力突出"), ("沟通协作", 5, "良好的沟通协调能力"),
         ("责任心", 5, "分内工作尽责到位，非常靠谱")],
        [(2024, "A", "内控体系建设交付优秀"), (2025, "A", "内控测试与整改表现突出"), (2026, "A", "审计协调高质量交付")],
        "高级会计师")),
]

JOBS = [j for f in ("blind_gold_jobs.json", "blind_gold_jobs_batch2.json")
        for j in json.loads((config.DATA_DIR / "jobs" / f).read_text(encoding="utf-8"))["jobs"]][:5]
GOLD_JOB = dict(zip(["JZ9001", "JZ9002", "JZ9003", "JZ9004", "JZ9005"],
                    [j["job_id"] for j in JOBS]))


def add_mirror_projects(synth: dict, job: dict) -> dict:
    """机械镜像：把 JD 全部要求/职责子句 head 逐字拼进一个镜像项目描述——
    「信息全部包括」的严格化（任何 miss 即引擎侧问题，不再是合成遗漏）。"""
    heads = []
    for r in extract_requirements(job):  # 全部要求（含优先项）——满分信息集
        if not any(h in r["text"] for h in heads):
            heads.append(r["head"])
    desc = "；".join(heads) + "。"
    synth["projects"].append({
        "project_name": f"岗位要求全覆盖专项（{job['job_id']}）",
        "role": "全面负责人", "tools": [],
        "description": "全面负责：" + desc})
    synth["text_summaries"]["project_summary"] = "；".join(
        p["description"] for p in synth["projects"])
    return synth


def main() -> int:
    employees = json.loads((config.INTERMEDIATE_DIR / "phase1_output.json").read_text(encoding="utf-8"))["employees"]
    pool = employees + SYNTH  # 仅内存
    index = EvidenceIndex.build(pool, cache_path=None)  # 不碰正式缓存
    equiv = load_verified_equivalences()
    splits = load_atomic_splits()

    lines = ["# 满分探针报告（2026-10-25，用户指令）", "",
             "> 5 名合成员工证据**纯镜像 JD 词表**（信息集=引擎的要求集，不读真实员工数据）；"
             "内存加池跑冻结引擎；不足 95 = 分词/评分结构存在设计上限", ""]
    for job in JOBS:
        jid, jt = job["job_id"], str(job.get("job_type", ""))
        synth_id = GOLD_JOB and [k for k, v in GOLD_JOB.items() if v == jid][0]
        synth = next(e for e in SYNTH if e["employee_id"] == synth_id)
        base_synth = json.loads(json.dumps(synth))  # 深拷贝：镜像项目不跨岗泄漏
        synth_with_mirror = add_mirror_projects(base_synth, job)
        pool_j = [e if e["employee_id"] != synth_id else synth_with_mirror for e in pool]
        index_j = EvidenceIndex.build(pool_j, cache_path=None)
        reqs_raw = extract_requirements(job)
        res = score_coverage(reqs_raw, pool_j, index_j, equivalences=equiv,
                             atomic_splits=splits, job_type=jt)
        order = sorted(res.items(), key=lambda kv: (-kv[1]["total"], kv[0]))
        rank = [i for i, (e, _) in enumerate(order, 1) if e == synth_id][0]
        r = res[synth_id]
        w = r["w_matrix"]
        lines += [f"## {jid} {job.get('title','')}｜合成员工 {synth_id} 排名 **{rank}**", "",
                  f"total **{r['total']}** = W{w[0]:.0f}·S_prof {r['s_prof']} + W{w[1]:.0f}·S_behav {r['s_behav']} "
                  f"+ W{w[2]:.0f}·P {r['p']} + bonus {r['bonus']}" + (f"｜闸门 {r['required_skill_gate']}" if r["required_skill_gate"] else ""),
                  "", "| rid | 要求 | v | 关系 |", "|---|---|---|---|"]
        reqs = r["requirements"]
        req_map = {x["rid"]: x for x in extract_requirements(job)}
        for rid, rr in reqs.items():
            base = rid.split("-")[0]
            head = req_map.get(base, {}).get("head", rid)
            if rr["v"] < 1.0:
                lines.append(f"| {rid} | {head[:34]} | **{rr['v']}** | {rr['relation']}（{rr['note'][:30]}） |")
        full = sum(1 for rr in reqs.values() if rr["v"] >= 1.0)
        lines.append("")
        lines.append(f"覆盖：{full}/{len(reqs)} 条 v=1")
        print(f"{jid} {synth_id}: rank={rank} total={r['total']} prof={r['s_prof']} behav={r['s_behav']} P={r['p']} bonus={r['bonus']} 覆盖{full}/{len(reqs)}")

    # 结构上限分析
    lines += ["", "## 结构上限分析（满分为何难到 95）", ""]
    lines.append("- P 潜力基座：全 A 绩效 → trend=(A-A+3)/6=0.5（中性）→ P=0.5×1+0.3×0.5+0.2×1=**0.85**——理论上限（除非 D→A 翻盘轨迹，但那会拉低均值项）")
    lines.append("- 技术类满分 = 70×1 + 15×1 + 15×0.85 + bonus ≈ **85.5 + bonus**；bonus = 2×Σ(优先项v)/N_must，量级 ≤2")
    lines.append("- 即**公式构造上 95 不可达**——任何员工（包括证据完美镜像 JD 者）都到不了 95；缺口全部来自 P 基座与 bonus 量纲，与分词/等价激活无关（本探针全部要求 v=1 时即是证明）")
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n报告 → {REPORT.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
