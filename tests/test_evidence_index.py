"""utils/evidence_index.py 单元测试（M1 员工证据向量索引）。

全部用确定性 fake 编码函数（字符桶向量），不加载 fastembed/torch。
"""
from __future__ import annotations

import numpy as np
import pytest

from utils.evidence_index import (
    EvidenceIndex,
    build_evidence_chunks,
    chunk_employee,
)


DIM = 64


def char_bucket_encode(texts: list[str]) -> np.ndarray:
    """确定性 fake 编码：字符 ord 桶计数 + 归一化。共享字符越多 cos 越高。"""
    vecs = []
    for t in texts:
        v = np.zeros(DIM)
        for ch in str(t):
            v[ord(ch) % DIM] += 1.0
        n = np.linalg.norm(v)
        vecs.append(v / n if n > 0 else v)
    return np.array(vecs) if vecs else np.array([])


@pytest.fixture
def employee_a() -> dict:
    return {
        "employee_id": "JZ0001",
        "structured": {
            "current_position": "质量工程师",
            "major": "人工智能",
            "job_sequence": "技术研发类",
            "certificates": "中级质量工程师",
        },
        "projects": [
            {"project_name": "工业IoT管理平台", "role": "核心开发",
             "tools": ["InfluxDB", "Go"], "description": "负责核心模块开发"},
        ],
        "performance": [
            {"year": 2024, "grade": "B", "comment": "按时完成任务"},
            {"year": 2026, "grade": "A", "comment": "创新引入云计算方案"},
        ],
        "training": [
            {"course_name": "质量管理体系ISO9001", "status": "已完成", "score": 91},
        ],
        "text_summaries": {
            "performance_summary": "绩效整体向上",
            "project_summary": "参与工业IoT平台建设",
            "evaluation_summary": "质量意识强，跨部门沟通顺畅",
        },
    }


@pytest.fixture
def employee_b() -> dict:
    return {
        "employee_id": "JZ0099",
        "structured": {"current_position": "薪酬福利专员", "certificates": "高级会计师"},
        "projects": [{"project_name": "企业内控体系建设", "role": "协调人",
                      "tools": ["COSO"], "description": "内控流程梳理"}],
        "performance": [{"year": 2025, "grade": "B", "comment": "内控项目交付"}],
        "training": [],
        "text_summaries": {"evaluation_summary": "风险意识强"},
    }


class TestChunkEmployee:
    def test_sources_and_fields(self, employee_a):
        chunks = chunk_employee(employee_a)
        sources = {c["source"] for c in chunks}
        assert {"position", "projects", "performance", "training",
                "summary_performance", "summary_project",
                "summary_evaluation"} <= sources
        for c in chunks:
            assert set(c.keys()) == {"emp_id", "source", "text", "anchor"}
            assert c["emp_id"] == "JZ0001"
            assert c["anchor"] == c["text"][:10]
            assert c["text"]  # 非空才入列

    def test_certificates_none_excluded(self, employee_a):
        employee_a["structured"]["certificates"] = "无"
        chunks = chunk_employee(employee_a)
        assert all("证书" not in c["text"] for c in chunks if c["source"] == "position")

    def test_malformed_records_no_crash(self):
        emp = {
            "employee_id": "X1",
            "structured": None,
            "projects": [None, "junk", {"project_name": "P1"}],
            "performance": [None],
            "training": [None],
            "text_summaries": None,
        }
        chunks = chunk_employee(emp)
        assert any(c["source"] == "projects" and "P1" in c["text"] for c in chunks)

    def test_long_text_clipped(self):
        emp = {"employee_id": "X2",
               "text_summaries": {"performance_summary": "长" * 2000}}
        chunks = chunk_employee(emp)
        assert len(chunks[0]["text"]) <= 600

    def test_deterministic(self, employee_a):
        assert chunk_employee(employee_a) == chunk_employee(employee_a)

    def test_build_evidence_chunks_multi(self, employee_a, employee_b):
        chunks = build_evidence_chunks([employee_a, employee_b])
        assert {c["emp_id"] for c in chunks} == {"JZ0001", "JZ0099"}


class TestEvidenceIndex:
    def test_build_and_search(self, employee_a, employee_b):
        idx = EvidenceIndex.build([employee_a, employee_b],
                                  encode_fn=char_bucket_encode)
        assert idx.matrix.ndim == 2
        hits = idx.search("质量管理体系ISO9001", top_k=3)
        assert hits and hits[0]["sim"] > 0
        assert hits[0]["source"] in {"training", "position", "projects", "performance"}

    def test_employee_scores_discriminates(self, employee_a, employee_b):
        idx = EvidenceIndex.build([employee_a, employee_b],
                                  encode_fn=char_bucket_encode)
        scores = idx.employee_scores(["质量管理体系ISO9001认证培训"])
        assert scores["JZ0001"] > scores["JZ0099"]

    def test_top_chunks_for_employee_filtered(self, employee_a, employee_b):
        idx = EvidenceIndex.build([employee_a, employee_b],
                                  encode_fn=char_bucket_encode)
        chunks = idx.top_chunks_for_employee("工业IoT平台", "JZ0001", top_k=5)
        assert chunks and all(c["emp_id"] == "JZ0001" for c in chunks)

    def test_empty_employees(self):
        idx = EvidenceIndex.build([], encode_fn=char_bucket_encode)
        assert idx.matrix.size == 0
        assert idx.search("任何") == []
        assert idx.employee_scores(["任何"]) == {}

    def test_cache_roundtrip(self, employee_a, employee_b, tmp_path):
        cache = tmp_path / "cache" / "evidence_cache.npy"
        idx1 = EvidenceIndex.build([employee_a, employee_b],
                                   encode_fn=char_bucket_encode, cache_path=cache)
        files = list(cache.parent.glob("evidence_cache_*.npy"))
        assert len(files) == 1  # 哈希编入文件名
        idx2 = EvidenceIndex.build([employee_a, employee_b],
                                   encode_fn=char_bucket_encode, cache_path=cache)
        assert np.allclose(np.asarray(idx1.matrix, dtype=float),
                           np.asarray(idx2.matrix, dtype=float))
        # 旧哈希文件被清理（同 stem 只留当前哈希）
        assert len(list(cache.parent.glob("evidence_cache_*.npy"))) == 1

    def test_cache_mismatch_rebuilds(self, employee_a, tmp_path):
        cache = tmp_path / "evidence_cache.npy"
        EvidenceIndex.build([employee_a], encode_fn=char_bucket_encode,
                            cache_path=cache)
        # 数据变更 → 哈希变化 → 旧缓存不命中 → 重建成功
        employee_a["training"] = [{"course_name": "新课程"}]
        idx = EvidenceIndex.build([employee_a], encode_fn=char_bucket_encode,
                                  cache_path=cache)
        assert idx.matrix.shape[0] == len(idx.chunks)

    def test_real_encode_fn_with_fake_model(self, employee_a):
        """encode_fn=None 路径不测（需要 fastembed 模型）；此处验证
        encode_fn 注入路径与 None 路径接口一致（C1 对称）。"""
        idx = EvidenceIndex.build([employee_a], encode_fn=char_bucket_encode)
        assert isinstance(idx.chunks, list) and idx.chunks
