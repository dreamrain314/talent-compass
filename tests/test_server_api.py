"""server/app.py API 层测试（M-Web 匹配工作台）。

fake 注入（字符桶编码 + 裸函数 CE）保证确定性、不加载 torch/fastembed。
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from server.app import create_app  # noqa: E402

DIM = 64


def char_bucket_encode(texts: list[str]) -> np.ndarray:
    vecs = []
    for t in texts:
        v = np.zeros(DIM)
        for ch in str(t):
            v[ord(ch) % DIM] += 1.0
        n = np.linalg.norm(v)
        vecs.append(v / n if n > 0 else v)
    return np.array(vecs) if vecs else np.array([])


def fake_ce(pairs):
    return np.array([2.0] * len(pairs))


@pytest.fixture
def employees() -> list[dict]:
    return [
        {
            "employee_id": "E001",
            "structured": {"name": "周工", "education": "本科",
                           "years_of_service": 16, "current_position": "质量工程师",
                           "current_level": "P6", "job_sequence": "技术研发类",
                           "major": "人工智能", "certificates": "无",
                           "political_status": "群众"},
            "projects": [{"project_name": "工业IoT管理平台", "role": "核心开发",
                          "tools": ["InfluxDB"], "description": "质量管控模块"}],
            "performance": [{"year": 2024, "grade": "B", "comment": "稳"},
                            {"year": 2026, "grade": "A", "comment": "翻盘"}],
            "training": [{"course_name": "质量管理体系ISO9001", "status": "已完成",
                          "score": 91}],
            "scores_360": {"专业能力": 4.2, "沟通协作": 3.6, "领导力": 3.9,
                           "责任心": 3.9, "学习能力": 3.5},
            "text_summaries": {"performance_summary": "绩效向上",
                               "project_summary": "IoT平台",
                               "evaluation_summary": "质量意识强；跨部门沟通顺畅"},
        },
        {
            "employee_id": "E002",
            "structured": {"name": "程芳", "education": "本科",
                           "years_of_service": 11, "current_position": "薪酬福利专员",
                           "current_level": "P3", "job_sequence": "管理职能类",
                           "major": "法学", "certificates": "高级会计师",
                           "political_status": "群众"},
            "projects": [{"project_name": "企业内控体系建设", "role": "协调人",
                          "tools": ["COSO"], "description": "内控流程梳理"}],
            "performance": [{"year": 2025, "grade": "B", "comment": "稳"}],
            "training": [],
            "scores_360": {"专业能力": 4.5, "沟通协作": 4.0, "领导力": 3.0,
                           "责任心": 4.5, "学习能力": 3.8},
            "text_summaries": {"evaluation_summary": "风险意识强"},
        },
    ]


@pytest.fixture
def client(employees):
    app = create_app(employees=employees, encode_fn=char_bucket_encode,
                     cross_encoder_fn=fake_ce)
    app.config["TESTING"] = True
    return app.test_client()


JOB_PAYLOAD = {
    "job_id": "JOB_T",
    "title": "质量体系工程师",
    "responsibilities": ["负责智能制造平台项目的质量管控"],
    "requirements": ["本科及以上学历，3年及以上相关经验",
                     "熟悉质量管理体系（ISO9001）"],
    "top_k": 5,
}


class TestStateAndLibrary:
    def test_state(self, client):
        res = client.get("/api/state")
        assert res.status_code == 200
        data = res.get_json()
        assert data["n_employees"] == 2
        assert data["formula"]["t0_direct"] == 50.0
        assert "自动推荐" in data["decision_labels"].values()
        assert "项目经历" in data["source_labels"].values()

    def test_employees_list(self, client):
        data = client.get("/api/employees").get_json()
        ids = {e["employee_id"] for e in data["employees"]}
        assert ids == {"E001", "E002"}
        e1 = next(e for e in data["employees"] if e["employee_id"] == "E001")
        assert e1["name"] == "周工"
        assert e1["performance_trend"] == ["B", "A"]
        assert e1["n_evidence"] > 0

    def test_employee_detail(self, client):
        data = client.get("/api/employees/E001").get_json()
        assert data["summary"]["name"] == "周工"
        assert data["structured"]["current_position"] == "质量工程师"
        assert any(e["source"] == "training" for e in data["evidence"])
        assert all("source_label" in e for e in data["evidence"])

    def test_employee_detail_404(self, client):
        assert client.get("/api/employees/NOPE").status_code == 404

    def test_jobs_library(self, client):
        data = client.get("/api/jobs").get_json()
        assert len(data["jobs"]) == 5
        assert {j["job_id"] for j in data["jobs"]} >= {"JOB_B01"}


class TestMatchEndpoint:
    def test_match_happy_path(self, client):
        res = client.post("/api/match", json=JOB_PAYLOAD)
        assert res.status_code == 200
        data = res.get_json()
        assert data["job"]["title"] == "质量体系工程师"
        assert data["job"]["skill_requirements"]
        cands = data["candidates"]
        assert len(cands) >= 2
        # 排序：total 降序
        totals = [c["scores"]["total"] for c in cands]
        assert totals == sorted(totals, reverse=True)
        # 结构契约：每个候选带证据链与理由
        for c in cands[:2]:
            assert set(c["scores"]) == {"t0", "t1", "t2", "t3", "total", "confidence"}
            assert c["decision"] in {"recommend", "review", "backup_pool", "rejected"}
            assert isinstance(c["reason"], str) and c["reason"]
            for e in c["evidence"]:
                assert {"query", "source", "text", "anchor", "sim"} <= set(e)
        assert data["summary"]["n_candidates"] == 2
        assert data["summary"]["duration_ms"] >= 0

    def test_match_gold_style_job(self, client):
        """质量岗 → E001 应排在 E002 前（证据密集度决定）。"""
        data = client.post("/api/match", json=JOB_PAYLOAD).get_json()
        ids = [c["emp_id"] for c in data["candidates"]]
        assert ids.index("E001") < ids.index("E002")

    def test_match_empty_body_400(self, client):
        res = client.post("/api/match", json={"title": "空岗位"})
        assert res.status_code == 400
        assert "不能同时为空" in res.get_json()["error"]

    def test_match_top_k_clamped(self, client):
        payload = {**JOB_PAYLOAD, "top_k": 99}
        data = client.post("/api/match", json=payload).get_json()
        assert len(data["candidates"]) <= 20
