"""Round 3 Day 6-7：等价表离线裁决（预注册 §三 流程，运行时零 LLM 不动摇）。

流程（预注册 §三 + eval_log §十 永久规则）：
  完整原始概念流（10 岗 × 54 人 × 全部召回候选，不筛选不精选）
  → LLM 离线逐对五类关系判定 + 词级映射提议（temperature=0）
  → 聚合为词对提议 + 核验清单（人工打勾，从严准入）
  → --apply 读清单 ✓ 行 → 版本化写入 data/jobs/equivalence_table.json
  → 运行时只查表（coverage_engine.classify_relation），未覆盖项保留 unknown

断点续跑：每批响应追加 checkpoint JSONL，重跑跳过已完成批。

用法：
    python scripts/day67_equivalence_adjudication.py --jobs B06      # 单岗冒烟
    python scripts/day67_equivalence_adjudication.py                 # 全量 10 岗
    python scripts/day67_equivalence_adjudication.py --apply         # 读清单✓ → 入表
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

import config  # noqa: E402
from utils.coverage_engine import (  # noqa: E402
    classify_relation,
    extract_requirements,
    head_lookup_keys,
    load_verified_equivalences,
    recall_candidates,
    encode_query_texts,
    _norm_literal,
)
from utils.evidence_index import EvidenceIndex  # noqa: E402

STREAM_OUT = ROOT / "data" / "experiment" / "day67_concept_stream.json"
CHECKPOINT = ROOT / "data" / "experiment" / "day67_adjudication_checkpoint.jsonl"
CHECKPOINT_BLIND = ROOT / "data" / "experiment" / "day67_checkpoint_blind.jsonl"
PROPOSALS_OUT = ROOT / "data" / "experiment" / "day67_equivalence_proposals.json"
PROPOSALS_BLIND = ROOT / "data" / "experiment" / "day67_equivalence_proposals_blind.json"
CHECKLIST_OUT = ROOT / "docs" / "reports" / "day67_equivalence_checklist_20261023.md"
CHECKLIST_BLIND = ROOT / "docs" / "reports" / "day67_checklist_blind_20261025.md"
TABLE_OUT = ROOT / "data" / "jobs" / "equivalence_table.json"

BATCH_SIZE = 50
SYSTEM = ("你是人力资源岗位匹配系统的离线映射裁决器。只输出 JSON，不输出任何解释文字。"
          "判定从严：没有把握一律 relevant_only。")


def load_inputs(job_filter: set[str] | None, jobs_file: str | None = None):
    if jobs_file:
        jobs = json.loads((config.DATA_DIR / "jobs" / jobs_file).read_text(encoding="utf-8"))["jobs"]
    else:
        jobs = (json.loads((config.DATA_DIR / "jobs" / "blind_gold_jobs.json").read_text(encoding="utf-8"))["jobs"]
                + json.loads((config.DATA_DIR / "jobs" / "blind_gold_jobs_batch2.json").read_text(encoding="utf-8"))["jobs"])
    if job_filter:
        jobs = [j for j in jobs if j["job_id"] in job_filter]
    employees = json.loads((config.INTERMEDIATE_DIR / "phase1_output.json").read_text(encoding="utf-8"))["employees"]
    return jobs, employees


def build_stream(jobs, employees, index, equiv) -> list[dict]:
    """完整原始概念流：全部 (要求, 候选chunk) 对，去重 (job,rid,chunk)；不筛不选。"""
    qv_cache: dict[str, np.ndarray] = {}
    stream, seen = [], set()
    for job in jobs:
        reqs = extract_requirements(job)
        for req in reqs:
            if req["text"] not in qv_cache:
                v = encode_query_texts([req["text"]], None)
                qv_cache[req["text"]] = np.asarray(v[0]).reshape(-1)
            qvec = qv_cache[req["text"]]
            emp_chunks: dict[str, list] = defaultdict(list)
            emp_vecs: dict[str, list] = defaultdict(list)
            for i, c in enumerate(index.chunks):
                emp_chunks[c["emp_id"]].append(c)
                emp_vecs[c["emp_id"]].append(i)
            for eid, chunks in emp_chunks.items():
                cands = recall_candidates(req, chunks, index.matrix[emp_vecs[eid]], qvec)
                for c in cands:
                    key = (job["job_id"], req["rid"], c["text"])
                    if key in seen:
                        continue
                    seen.add(key)
                    cls = classify_relation(req, c, equiv)
                    stream.append({
                        "job": job["job_id"], "rid": req["rid"],
                        "req_text": req["text"],
                        "keys_raw": head_lookup_keys(req),
                        "chunk_source": c["source"], "chunk_text": c["text"],
                        "emp_id": eid,
                        "pre_relation": cls["relation"],  # 规则通道预判（字面命中已成立）
                    })
    return stream


def judge_batch(req_text: str, keys_raw: list[str], items: list[dict]) -> list[dict]:
    """LLM 裁决一批（≤60 对）。返回每对的 {idx, relation, req_term, chunk_term, reason}。"""
    from utils.llm_client import call_llm

    lines = []
    for i, it in enumerate(items, 1):
        lines.append(f"{i}. [{it['chunk_source']}] {it['chunk_text']}")
    prompt = f"""岗位原子要求：{req_text}
要求侧词表（映射提议的 req_term 只能从中逐字选一个）：{json.dumps(keys_raw, ensure_ascii=False)}

候选证据片段：
{chr(10).join(lines)}

对每条证据独立判定五类关系，输出 JSON 数组（每条一个对象，顺序与编号一致）：
[{{"id":1,"relation":"equivalent","req_term":"要求侧词","chunk_term":"证据原文连续子串","reason":"≤15字"}}, ...]

五类定义：
- equivalent：证据用不同措辞表达了要求侧词的同一能力（同义改写，如"调度工具"↔"调度平台"）
- direct_support：证据是要求侧词的下位实例（要求"数据分析"，证据写"Pandas/SQL取数建模"）
- state_different：证据为计划/学习中/进行中，未完成
- relevant_only：主题相邻但不能证明该能力
- contradiction：证据明确否定该能力

硬规则：
1. relation 为 equivalent/direct_support 时，req_term 必须从要求侧词表逐字选取；chunk_term 必须是证据原文中逐字连续的子串；两者都必填。
2. equivalent 与 direct_support 的区别：改写用不同的词表达同一能力=equivalent；证据是更具体的实例=direct_support。分不清就 relevant_only。
3. 禁止编造证据中不存在的词；禁止把"相关经历"拔高为"能力成立"。"""

    for attempt in range(3):
        resp = call_llm(prompt, system_prompt=SYSTEM, temperature=0.0,
                        max_tokens=8000, timeout=120)
        if resp.get("error"):
            time.sleep(3 * (attempt + 1))
            continue
        text = (resp.get("content") or "").strip()
        m = re.search(r"\[.*\]", text, re.S)
        if not m:
            time.sleep(2)
            continue
        try:
            arr = json.loads(m.group(0))
            if isinstance(arr, list):
                return arr
        except Exception:
            continue
    return []  # 三次失败：该批标记空（checkpoint 记 failed，续跑可重试）


def run_adjudication(job_filter, jobs_file=None):
    ckpt_path = CHECKPOINT_BLIND if jobs_file else CHECKPOINT
    proposals_path = PROPOSALS_BLIND if jobs_file else PROPOSALS_OUT
    checklist_path = CHECKLIST_BLIND if jobs_file else CHECKLIST_OUT
    jobs, employees = load_inputs(job_filter, jobs_file)
    index = EvidenceIndex.build(employees, cache_path=config.INTERMEDIATE_DIR / "evidence_cache.npy")
    equiv = load_verified_equivalences()
    print(f"岗位 {len(jobs)}｜员工 {len(employees)}｜索引 {len(index.chunks)} chunks")

    stream_path = STREAM_OUT.with_name(STREAM_OUT.stem + ("_blind" if jobs_file else "") + ".json")
    if stream_path.exists():
        stream = json.loads(stream_path.read_text(encoding="utf-8"))["pairs"]
        print(f"概念流：读缓存 {len(stream)} 对")
    else:
        t0 = time.time()
        stream = build_stream(jobs, employees, index, equiv)
        stream_path.write_text(json.dumps(
            {"generated_at": datetime.now().isoformat(timespec="seconds"),
             "protocol": "Round3 §三 全量未筛选概念流", "n_pairs": len(stream),
             "pairs": stream}, ensure_ascii=False), encoding="utf-8")
        print(f"概念流：新建 {len(stream)} 对（{time.time()-t0:.0f}s）→ {stream_path.name}")

    # 分批（按 job+rid 分组，组内再切 60）
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for p in stream:
        groups[(p["job"], p["rid"])].append(p)
    batches = []
    for (job, rid), items in sorted(groups.items()):
        for bi in range(0, len(items), BATCH_SIZE):
            batches.append(((job, rid, bi // BATCH_SIZE), items[bi:bi + BATCH_SIZE]))

    done: set[tuple] = set()
    if ckpt_path.exists():
        for line in ckpt_path.read_text(encoding="utf-8").splitlines():
            try:
                rec = json.loads(line)
                done.add((rec["job"], rec["rid"], rec["batch"]))
            except Exception:
                pass
    todo = [(k, v) for k, v in batches if k not in done]
    print(f"裁决批次：共 {len(batches)}，已完成 {len(done)}，待跑 {len(todo)}")

    ckpt = open(ckpt_path, "a", encoding="utf-8")
    t0 = time.time()
    for n, (key, items) in enumerate(todo, 1):
        arr = judge_batch(items[0]["req_text"], items[0]["keys_raw"], items)
        # 位置对齐（LLM 可能跳 id）：verdict 与 items 按序 zip，数量不齐取小者
        pairs = []
        for it, v in zip(items, arr if isinstance(arr, list) else []):
            pairs.append({"job": key[0], "rid": key[1],
                          "chunk_text": it["chunk_text"], "emp_id": it["emp_id"],
                          "req_text": it["req_text"], "chunk_source": it["chunk_source"],
                          "verdict": v if isinstance(v, dict) else {}})
        ckpt.write(json.dumps({"job": key[0], "rid": key[1], "batch": key[2],
                               "pairs": pairs, "n_items": len(items),
                               "ok": bool(arr)}, ensure_ascii=False) + "\n")
        ckpt.flush()
        if n % 10 == 0 or n == len(todo):
            rate = n / (time.time() - t0)
            eta = (len(todo) - n) / rate if rate else 0
            print(f"  批 {n}/{len(todo)}（{key[0]}/{key[1]}#b{key[2]} n={len(items)} 判定={len(arr)}）"
                  f" | {rate:.2f}批/s ETA {eta/60:.0f}min", flush=True)
    ckpt.close()
    print("裁决完成，聚合提议…")
    aggregate(ckpt_path, proposals_path, checklist_path)


def aggregate(ckpt_path=None, proposals_path=None, checklist_path=None):
    """checkpoint（自带 chunk 上下文，无 id 对齐问题）→ 词对提议 + 核验清单。"""
    ckpt_path = ckpt_path or CHECKPOINT
    proposals_path = proposals_path or PROPOSALS_OUT
    checklist_path = checklist_path or CHECKLIST_OUT
    pairs_all = []
    n_failed_batches = 0
    for line in ckpt_path.read_text(encoding="utf-8").splitlines():
        try:
            rec = json.loads(line)
        except Exception:
            continue
        if not rec.get("ok"):
            n_failed_batches += 1
        pairs_all.extend(rec.get("pairs") or [])

    prop_counter: dict[tuple, dict] = defaultdict(lambda: {
        "count": 0, "emps": set(), "jobs": set(), "examples": [], "relation": ""})
    rel_hist = defaultdict(int)
    judged = 0
    for rec_pair in pairs_all:
        v = rec_pair.get("verdict") or {}
        rel = v.get("relation") or "unjudged"
        rel_hist[rel] += 1
        if rel in ("unjudged",):
            continue
        judged += 1
        if rel in ("equivalent", "direct_support") and v.get("req_term") and v.get("chunk_term"):
            k = (_norm_literal(v["req_term"]), _norm_literal(v["chunk_term"]))
            pc = prop_counter[k]
            pc["count"] += 1
            pc["emps"].add(rec_pair["emp_id"])
            pc["jobs"].add(rec_pair.get("job", ""))
            pc["relation"] = rel
            if len(pc["examples"]) < 3 and v["chunk_term"] in rec_pair["chunk_text"]:
                pc["examples"].append({"emp": rec_pair["emp_id"], "job": rec_pair.get("job", ""),
                                       "chunk": rec_pair["chunk_text"],
                                       "req": rec_pair["req_text"],
                                       "reason": v.get("reason", "")})
    if n_failed_batches:
        print(f"⚠ {n_failed_batches} 批三次重试仍失败（checkpoint ok=false），续跑可重试")

    props = []
    for (k_raw, v_raw), pc in sorted(prop_counter.items(), key=lambda kv: -kv[1]["count"]):
        props.append({"req_term": k_raw, "chunk_term": v_raw,
                      "relation": pc["relation"], "count": pc["count"],
                      "n_emps": len(pc["emps"]), "jobs": sorted(pc["jobs"]),
                      "examples": pc["examples"], "approved": None})
    proposals_path.write_text(json.dumps({
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "protocol": "Round3 §三 LLM 离线提议（未筛选全量概念流），人工核验后 --apply 入表",
        "n_pairs_total": len(pairs_all), "n_pairs_judged": judged,
        "relation_histogram": dict(rel_hist),
        "proposals": props}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"提议 {len(props)} 条词对 → {proposals_path.name}｜判定直方图 {dict(rel_hist)}")

    # 核验清单
    lines = [
        "# 等价表核验清单（Round 3 §三，人工打勾）",
        "",
        f"> 生成：{datetime.now().isoformat(timespec='seconds')}｜全量未筛选概念流判定 "
        f"{len(pairs_all)} 对（LLM 有效判定 {judged} 对），聚合出词对提议 {len(props)} 条",
        "> **核验规则：只勾你确认成立的映射（核验列填 ✓）；不确定/不成立留空或填 ✗。"
        "宁可少勾——表是运行时硬闸门，错一条污染所有岗位。**",
        "> 勾完保存本文件，告诉我「核验完成」，我跑 `--apply` 入表（版本化 v1）。",
        "",
        "| # | 要求侧词 | 证据侧词 | 关系 | 支持对数 | 涉及岗位 | 核验 |",
        "|---|----------|----------|------|----------|----------|------|",
    ]
    for i, p in enumerate(props, 1):
        lines.append(f"| {i} | {p['req_term']} | {p['chunk_term']} | "
                     f"{p['relation']} | {p['count']} | {','.join(p['jobs'])} | |")
    lines += ["", "## 附：代表性证据示例", ""]
    for i, p in enumerate(props[:30], 1):
        for ex in p["examples"][:1]:
            lines.append(f"{i}. **{p['req_term']} ↔ {p['chunk_term']}**（{ex['job']}/{ex['emp']}）"
                         f"：{ex['chunk'][:70]}")
    CHECKLIST_OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"核验清单 → {CHECKLIST_OUT.name}")


def apply_approved(blind: bool = False):
    """读核验清单 ✓ 行 → 版本化等价表。"""
    checklist = CHECKLIST_BLIND if blind else CHECKLIST_OUT
    proposals = PROPOSALS_BLIND if blind else PROPOSALS_OUT
    text = checklist.read_text(encoding="utf-8")
    props = {i: p for i, p in enumerate(
        json.loads(proposals.read_text(encoding="utf-8"))["proposals"], 1)}
    table: dict[str, list[str]] = defaultdict(list)
    n_ok = n_skip = 0
    for line in text.splitlines():
        m = re.match(r"\|\s*(\d+)\s*\|([^|]+)\|([^|]+)\|[^|]*\|[^|]*\|[^|]*\|\s*✓\s*\|", line)
        if not m:
            continue
        idx = int(m.group(1))
        p = props.get(idx)
        if not p:
            n_skip += 1
            continue
        k, v = p["req_term"], p["chunk_term"]
        if v not in table[k]:
            table[k].append(v)
        n_ok += 1
    out = {
        "version": "v1_20261023",
        "created": datetime.now().isoformat(timespec="seconds"),
        "provenance": "Round3 §三：LLM 离线提议（全量未筛选概念流）→ 人工核验 ✓ → 版本化发布；"
                      "运行时只查表零 LLM。加载时与 alias_patches 种子合并（coverage_engine）。"
                      f"本次人工确认 {n_ok} 条。",
        "equivalences": dict(table),
    }
    TABLE_OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"等价表 v1 入表：{n_ok} 条 ✓，{len(table)} 个要求侧键 → {TABLE_OUT.name}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--jobs", type=str, default=None, help="只跑指定岗位（逗号分隔）")
    ap.add_argument("--jobs-file", type=str, default=None, help="岗位文件名（data/jobs/ 下，如 agent_blind_jobs_v1.json）——checkpoint/提议/清单走 blind 独立文件")
    ap.add_argument("--aggregate-only", action="store_true", help="跳过 LLM，只聚合 checkpoint")
    ap.add_argument("--apply", action="store_true", help="读核验清单 ✓ → 写等价表")
    args = ap.parse_args()
    blind = bool(args.jobs_file)
    if args.apply:
        apply_approved(blind=blind)
        return 0
    if not args.aggregate_only:
        run_adjudication({"JOB_" + j if not j.startswith("JOB_") else j
                          for j in args.jobs.split(",")} if args.jobs else None,
                         jobs_file=args.jobs_file)
    else:
        aggregate(CHECKPOINT_BLIND if blind else CHECKPOINT,
                  PROPOSALS_BLIND if blind else PROPOSALS_OUT,
                  CHECKLIST_BLIND if blind else CHECKLIST_OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
