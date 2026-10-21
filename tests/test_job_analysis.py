"""agents/job_analysis.py 单元测试（M2 岗位要求解析）。

LLM 路径只测结构校验与回退；offline 路径用真实标签库 corpus（JSON 加载，轻）。
"""
from __future__ import annotations

import pytest

from agents.job_analysis import (
    JobAnalysis,
    _offline_extract,
    _validate_llm_profile,
    build_queries,
)
from utils.label_embedding import load_label_corpus


@pytest.fixture
def job_jd() -> dict:
    return {
        "job_id": "JOB_X1",
        "title": "Java后端开发工程师",
        "company": "九洲",
        "department": "信息技术中心",
        "responsibilities": ["负责 ERP 系统定制开发与 Java 微服务方案设计"],
        "requirements": [
            "本科及以上学历，计算机相关专业",
            "5年以上相关工作经验",
            "持有信息系统项目管理师认证者优先",
        ],
    }


@pytest.fixture
def corpus():
    return load_label_corpus()


class TestOfflineExtract:
    def test_hard_requirements_regex(self, job_jd, corpus):
        profile = _offline_extract(job_jd, corpus)
        hard = profile["hard_requirements"]
        assert hard["education_min"] == "本科"
        assert hard["years_min"] == 5
        assert "项目管理师" in "".join(hard["certificates"]) or hard["certificates"]

    def test_skill_reqs_from_corpus(self, job_jd, corpus):
        profile = _offline_extract(job_jd, corpus)
        names = [s["name"] for s in profile["skill_requirements"]]
        assert "Java开发" in names  # JD 含 Java → corpus 字面命中

    def test_structure_keys(self, job_jd, corpus):
        profile = _offline_extract(job_jd, corpus)
        assert set(profile.keys()) == {"hard_requirements", "skill_requirements",
                                       "soft_requirements", "summary"}

    def test_deterministic(self, job_jd, corpus):
        assert _offline_extract(job_jd, corpus) == _offline_extract(job_jd, corpus)

    def test_single_char_keyword_denoise(self, corpus):
        """C语言 假阳性修复：关键词 'C' 单字符不再命中「SPC/FMEA」中的 C（2026-10-21 降噪）。"""
        job = {
            "job_id": "J", "title": "质量体系工程师",
            "responsibilities": ["负责质量管控与体系审核"],
            "requirements": ["熟悉质量工具（SPC/FMEA/8D）"],
        }
        profile = _offline_extract(job, corpus)
        assert "C语言" not in [s["name"] for s in profile["skill_requirements"]]


class TestValidateLLMProfile:
    def test_valid(self):
        content = {
            "hard_requirements": {"education_min": "本科", "years_min": 5,
                                  "certificates": ["PMP"]},
            "skill_requirements": [{"name": "Java开发", "detail": "微服务"}],
            "soft_requirements": [],
            "summary": "后端岗",
        }
        out = _validate_llm_profile(content)
        assert out is not None and out["hard_requirements"]["years_min"] == 5

    def test_invalid_shapes(self):
        assert _validate_llm_profile(None) is None
        assert _validate_llm_profile({"skill_requirements": []}) is None
        assert _validate_llm_profile({"hard_requirements": {},
                                      "skill_requirements": [{"no_name": 1}]}) is None
        assert _validate_llm_profile("junk") is None

    def test_years_min_coerced(self):
        content = {"hard_requirements": {"education_min": "", "years_min": "5",
                                         "certificates": None},
                   "skill_requirements": [{"name": "x", "detail": "y"}]}
        out = _validate_llm_profile(content)
        assert out["hard_requirements"]["years_min"] is None  # 非法类型 → None


class TestBuildQueries:
    def test_enriched_with_definition(self, corpus):
        profile = {"skill_requirements": [{"name": "Java开发", "detail": "微服务架构"}]}
        queries = build_queries(profile, corpus)
        assert len(queries) == 1
        assert "Java开发" in queries[0]
        assert "微服务" in queries[0]  # definition 富化生效

    def test_unknown_label_fallback(self, corpus):
        profile = {"skill_requirements": [{"name": "量子算法", "detail": "Shor"}]}
        queries = build_queries(profile, corpus)
        assert queries == ["量子算法：Shor"]


class TestJobAnalysisAgent:
    def test_validate_input(self, job_jd):
        agent = JobAnalysis()
        assert agent.validate_input({"job": job_jd})
        assert agent.validate_input({"job": job_jd, "employees": [1]})
        assert not agent.validate_input({})
        assert not agent.validate_input({"job": {"title": ""}})
        assert not agent.validate_input("junk")

    def test_execute_offline_mode(self, job_jd, monkeypatch):
        monkeypatch.setenv("TC_OFFLINE", "1")
        agent = JobAnalysis()
        result = agent.run({"job": job_jd, "employees": [{"employee_id": "E1"}]},
                           {"trace_id": "t1"})
        assert result["status"] == "success"
        jp = result["data"]["job_profile"]
        assert jp["parse_source"] == "offline"
        assert jp["job_id"] == "JOB_X1"
        assert jp["queries"] and all(isinstance(q, str) for q in jp["queries"])
        assert result["data"]["employees"] == [{"employee_id": "E1"}]
        assert result["metadata"]["data_lineage"]["audit_status"] == "verified"

    def test_execute_llm_failure_falls_back(self, job_jd, monkeypatch):
        """LLM 抛异常 → 回退离线结果（D6 确定性降级，零重试）。"""
        monkeypatch.setenv("TC_OFFLINE", "0")
        monkeypatch.delenv("TC_OFFLINE", raising=False)
        monkeypatch.setenv("TC_OFFLINE", "")

        import agents.job_analysis as mod

        def boom(**kwargs):
            raise RuntimeError("api down")

        monkeypatch.setattr(mod, "call_llm_json", boom)
        agent = JobAnalysis()
        result = agent.run({"job": job_jd, "employees": []}, {"trace_id": "t2"})
        assert result["status"] == "success"
        assert result["data"]["job_profile"]["parse_source"] == "offline"

    def test_execute_llm_success_overrides(self, job_jd, monkeypatch):
        """LLM 返回合法结构 → parse_source=llm 且 queries 用 LLM 技能项。"""
        monkeypatch.setenv("TC_OFFLINE", "")

        import agents.job_analysis as mod

        fake = {
            "content": {
                "hard_requirements": {"education_min": "硕士", "years_min": 8,
                                      "certificates": []},
                "skill_requirements": [
                    {"name": "Java开发", "detail": "Spring 微服务"},
                    {"name": "系统架构", "detail": "高并发设计"},
                ],
                "soft_requirements": [],
                "summary": "资深后端",
            },
            "error": None,
        }
        monkeypatch.setattr(mod, "call_llm_json", lambda **kwargs: fake)
        agent = JobAnalysis()
        result = agent.run({"job": job_jd, "employees": []}, {"trace_id": "t3"})
        jp = result["data"]["job_profile"]
        assert jp["parse_source"] == "llm"
        assert jp["hard_requirements"]["education_min"] == "硕士"
        assert [q.split("：")[0] for q in jp["queries"]] == ["Java开发", "系统架构"]
