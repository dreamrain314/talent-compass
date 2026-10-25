"""Talent Compass 匹配工作台（Flask，端口 8082 per AGENTS.md ZCode 段）。

架构：薄 API 层——业务逻辑全部复用已测试的 utils/agents 模块：
- 员工数据：data/intermediate/phase1_output.json（启动时加载，EvidenceIndex 全局单例）
- 匹配：job_analysis 离线抽取（网页默认零 LLM，确定性）+ match_engine 固定公式
- 溯源：候选 evidence 带 {query, source, text, anchor, sim}，员工详情接口返回
  全部原始记录与证据切片，前端"点回原文"

启动：python server/app.py  （或 uvicorn server.app:app --port 8082，Flask 内置服务器即可）
测试：create_app(employees=..., encode_fn=..., cross_encoder_fn=...) 工厂注入 fake。
"""

from __future__ import annotations

import json
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import config  # noqa: E402
from utils.coverage_engine import (  # noqa: E402
    _expand_requirements,
    build_evidence_matrix,
    extract_requirements,
    load_atomic_splits,
    load_verified_equivalences,
    score_coverage,
)
from utils.evidence_index import EvidenceIndex, chunk_employee  # noqa: E402
from utils.match_engine import _EDU_ORDINAL  # noqa: E402

from flask import Flask, jsonify, request, send_from_directory  # noqa: E402

SOURCE_LABELS = {
    "position": "岗位与证书",
    "projects": "项目经历",
    "performance": "绩效记录",
    "training": "培训记录",
    "summary_performance": "绩效摘要",
    "summary_project": "项目摘要",
    "summary_evaluation": "360 评价摘要",
}


class Workspace:
    """进程级共享状态（索引/语料/员工），惰性构建 + 匹配互斥（确定性保障）。"""

    def __init__(self, employees=None, encode_fn=None, cross_encoder_fn=None):
        self._employees = employees
        self._encode_fn = encode_fn
        self._cross_encoder_fn = cross_encoder_fn
        self._index: EvidenceIndex | None = None
        self._corpus = None
        self._lock = threading.Lock()

    @property
    def employees(self) -> list[dict]:
        if self._employees is None:
            data = json.loads(
                (config.INTERMEDIATE_DIR / "phase1_output.json").read_text(encoding="utf-8")
            )
            self._employees = data.get("employees") or []
        return self._employees

    @property
    def corpus(self) -> list[dict]:
        if self._corpus is None:
            self._corpus = load_label_corpus()
        return self._corpus

    @property
    def index(self) -> EvidenceIndex:
        if self._index is None:
            self._index = EvidenceIndex.build(
                self.employees,
                encode_fn=self._encode_fn,
                cache_path=None if self._encode_fn else
                (config.INTERMEDIATE_DIR / "evidence_cache.npy"),
            )
        return self._index

    def warmup(self) -> None:
        """启动预热（仅 __main__ 调用）：索引构建 + CE 加载都在启动期完成，
        用户首次匹配即秒出（此前冷启动首匹配要 1-5 分钟：索引重建 ~24s +
        2.2GB reranker 磁盘加载分钟级，前端只有一个转圈）。"""
        t0 = time.perf_counter()
        n_chunks = len(self.index.chunks)
        t1 = time.perf_counter()
        if self._cross_encoder_fn is None:
            from utils.label_matching import _load_cross_encoder

            enc = _load_cross_encoder()
            if enc is not None:
                self._cross_encoder_fn = enc.predict if hasattr(enc, "predict") else enc
        t2 = time.perf_counter()
        print(f"预热完成：索引 {n_chunks} chunks（{t1 - t0:.1f}s）+ "
              f"cross-encoder（{t2 - t1:.1f}s，{'已加载' if self._cross_encoder_fn else '不可用·降级纯 bi'}）"
              f"——首次匹配不再冷启动等待")

    def match(self, job: dict, top_k: int, employees: list[dict] | None = None,
              job_type: str = "") -> dict:
        """一次完整匹配（Round 3 覆盖引擎：要求—证据对齐，运行时零 LLM）。

        employees: 传入则用过滤后的候选池（用户硬性条件），None=全员。
        返回 {candidates, meta}——candidates 按新引擎 total 降序。
        """
        t0 = time.perf_counter()
        pool = employees if employees is not None else self.employees
        with self._lock:
            reqs_raw = extract_requirements(job)
            reqs = _expand_requirements(reqs_raw, load_atomic_splits())
            res = score_coverage(reqs_raw, pool, self.index,
                                 equivalences=load_verified_equivalences(),
                                 atomic_splits=load_atomic_splits(),
                                 job_type=job_type)
        order = sorted(res.items(), key=lambda kv: (-kv[1]["total"], kv[0]))
        candidates = []
        for eid, r in order:
            emp = next((x for x in pool if str(x.get("employee_id")) == eid), None)
            st = (emp or {}).get("structured") or {}
            candidates.append({
                "emp_id": eid,
                "name": st.get("name", ""),
                "total": r["total"],
                "s_prof": r["s_prof"], "s_behav": r["s_behav"],
                "p": r["p"], "bonus": r["bonus"],
                "gate": r["required_skill_gate"],
                "class_neutral": r["class_neutral"],
                "requirements": {
                    rid: {"v": rr["v"], "relation": rr["relation"], "note": rr["note"],
                          "evidence": [{**ev, "source_label": SOURCE_LABELS.get(ev["source"], ev["source"])}
                                       for ev in rr["evidence"]]}
                    for rid, rr in r["requirements"].items()},
            })
        return {
            "candidates": candidates,
            "meta": {
                "n_requirements": len(reqs),
                "reqs": [{"rid": x["rid"], "head": x["head"], "rtype": x.get("rtype", ""),
                          "kind": x["kind"], "weight": x["weight"]} for x in reqs],
                "w_matrix": list(config.COVERAGE_JOB_WEIGHT_MATRIX.get(
                    job_type, config.COVERAGE_JOB_WEIGHT_MATRIX["_default"])),
                "duration_ms": int((time.perf_counter() - t0) * 1000),
            },
        }


def _emp_summary(emp: dict) -> dict:
    structured = emp.get("structured") or {}
    perf = [p.get("grade") for p in (emp.get("performance") or [])
            if isinstance(p, dict) and p.get("grade")]
    s360 = emp.get("scores_360") or {}
    s360_vals = [v for v in s360.values() if isinstance(v, (int, float))]
    return {
        "employee_id": emp.get("employee_id", ""),
        "name": structured.get("name", ""),
        "position": structured.get("current_position", ""),
        "level": structured.get("current_level", ""),
        "job_sequence": structured.get("job_sequence", ""),
        "education": structured.get("education", ""),
        "years": structured.get("years_of_service"),
        "gender": structured.get("gender", ""),
        "age": structured.get("age"),
        "major": structured.get("major", ""),
        "political_status": structured.get("political_status", ""),
        "performance_trend": perf,
        "s360_avg": round(sum(s360_vals) / len(s360_vals), 2) if s360_vals else None,
        "n_evidence": len(chunk_employee(emp)),
    }


def _hard_filter(employees: list[dict], filters: dict) -> tuple[list[dict], int]:
    """用户硬性条件过滤（性别/学历下限/专业）。返回 (通过池, 被排除数)。"""
    gender = str(filters.get("gender") or "").strip()
    edu_min = str(filters.get("education_min") or "").strip()
    major = str(filters.get("major") or "").strip().lower()
    if not (gender or edu_min or major):
        return employees, 0
    need = _EDU_ORDINAL.get(edu_min.replace("及以上", ""))
    passed, excluded = [], 0
    for e in employees:
        st = e.get("structured") or {}
        if gender and str(st.get("gender", "")) != gender:
            excluded += 1
            continue
        if need is not None:
            have = _EDU_ORDINAL.get(str(st.get("education", "")).strip())
            if have is None or have < need:
                excluded += 1
                continue
        if major:
            m = str(st.get("major", "")).lower()
            if not m or (major not in m and m not in major):
                excluded += 1
                continue
        passed.append(e)
    return passed, excluded


def create_app(employees=None, encode_fn=None, cross_encoder_fn=None) -> Flask:
    app = Flask(__name__, static_folder=str(ROOT / "server" / "static"))
    ws = Workspace(employees=employees, encode_fn=encode_fn,
                   cross_encoder_fn=cross_encoder_fn)

    @app.get("/")
    def index_page():
        return send_from_directory(str(ROOT / "server" / "static"), "index.html")

    @app.get("/static/<path:filename>")
    def static_files(filename: str):
        return send_from_directory(str(ROOT / "server" / "static"), filename)

    @app.get("/api/state")
    def api_state():
        return jsonify({
            "n_employees": len(ws.employees),
            "engine": "Round 3 要求—证据对齐（两类矩阵 + 等价表 + 专业闸门，零 LLM）",
            "w_matrix": {k: list(v) for k, v in config.COVERAGE_JOB_WEIGHT_MATRIX.items()},
            "parse_mode": "offline（零 LLM，确定性）",
            "source_labels": SOURCE_LABELS,
        })

    @app.get("/api/employees")
    def api_employees():
        return jsonify({"employees": [_emp_summary(e) for e in ws.employees]})

    @app.get("/api/employees/<emp_id>")
    def api_employee_detail(emp_id: str):
        emp = next((e for e in ws.employees
                    if str(e.get("employee_id")) == emp_id), None)
        if emp is None:
            return jsonify({"error": "employee not found"}), 404
        return jsonify({
            "summary": _emp_summary(emp),
            "structured": emp.get("structured") or {},
            "performance": emp.get("performance") or [],
            "projects": emp.get("projects") or [],
            "training": emp.get("training") or [],
            "scores_360": emp.get("scores_360") or {},
            "text_summaries": emp.get("text_summaries") or {},
            "evidence": [
                {**c, "source_label": SOURCE_LABELS.get(c["source"], c["source"])}
                for c in chunk_employee(emp)
            ],
        })

    @app.get("/api/jobs")
    def api_jobs():
        path = config.DATA_DIR / "jobs" / "blind_gold_jobs.json"
        doc = json.loads(path.read_text(encoding="utf-8"))
        return jsonify({"jobs": doc.get("jobs", [])})

    @app.post("/api/match")
    def api_match():
        body = request.get_json(silent=True) or {}
        job = {
            "job_id": str(body.get("job_id", "")),
            "title": str(body.get("title", "") or "未命名岗位"),
            "responsibilities": [str(x) for x in (body.get("responsibilities") or []) if str(x).strip()],
            "requirements": [str(x) for x in (body.get("requirements") or []) if str(x).strip()],
        }
        if not job["responsibilities"] and not job["requirements"]:
            return jsonify({"error": "职责与任职要求不能同时为空"}), 400
        job_type = str(body.get("job_type") or "技术类")
        top_k = body.get("top_k") or config.MATCH_TOP_K
        try:
            top_k = max(1, min(int(top_k), 20))
        except (TypeError, ValueError):
            top_k = config.MATCH_TOP_K

        filters = body.get("filters") or {}
        pool, filtered_out = _hard_filter(ws.employees, filters if isinstance(filters, dict) else {})
        if not pool:
            return jsonify({"error": "硬性条件过滤后无候选员工，请放宽条件", "filtered_out": filtered_out}), 200

        result = ws.match(job, top_k, employees=pool, job_type=job_type)
        candidates = result["candidates"]
        meta = result["meta"]
        n_gate = sum(1 for c in candidates if c["gate"])
        return jsonify({
            "job": {"title": job["title"], "job_type": job_type},
            "candidates": candidates[: max(top_k, 10)],
            "summary": {
                "n_candidates": len(candidates),
                "filtered_out": filtered_out,
                "n_requirements": meta["n_requirements"],
                "n_prof": sum(1 for r in meta["reqs"] if r["rtype"] == "professional"),
                "n_behav": sum(1 for r in meta["reqs"] if r["rtype"] == "behavioral"),
                "n_pref": sum(1 for r in meta["reqs"] if r["kind"] == "preferred"),
                "w_matrix": meta["w_matrix"],
                "n_gate": n_gate,
                "duration_ms": meta["duration_ms"],
            },
        })

    app.extensions["workspace"] = ws
    return app


if __name__ == "__main__":
    app = create_app()
    print("Talent Compass 匹配工作台 → http://127.0.0.1:8082")
    app.extensions["workspace"].warmup()
    app.run(host="127.0.0.1", port=8082, threaded=True, debug=False)
