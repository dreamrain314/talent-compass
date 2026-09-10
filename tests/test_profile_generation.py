"""tests/test_profile_generation.py — ProfileGeneration 骨架测试。

覆盖：
- validate_input 双格式兼容（Agent① structured / 适配后 raw）
- _adapt_input 字段映射（含 confidence_360=None 兜底、training None 元素）
- execute 空员工→degraded；有员工→success 骨架（Phase 0 corpus 加载）
- 返回结构含 status/data/metadata（C1 对称）
"""

import pytest

import config
from agents.profile_generation import ProfileGeneration
from utils.label_embedding import load_label_corpus


def _agent1_employee(emp_id="E001", with_360=True, confidence=None):
    """构造 Agent① 原始格式员工记录。"""
    emp = {
        "employee_id": emp_id,
        "structured": {
            "name": "张三",
            "age": 30,
            "political_status": "党员",
            "major": "计算机",
            "years_of_service": 5,
            "current_level": "P5",
            "certificates": "PMP;系统架构设计师",
            "job_sequence": "技术研发",
        },
        "text_summaries": {"performance_summary": {"2024": "优秀"}},
        "scores_360": {"专业能力": 85} if with_360 else {},
        "confidence_360": confidence,
        "performance": [{"year": 2024, "grade": "A", "comment": "表现良好"}],
        "training": [
            {"course_name": "AI 训练", "completion_date": "2024-06-01", "status": "完成", "score": 90.0}
        ],
    }
    return emp


def _adapted_employee(emp_id="E001"):
    """构造适配后格式员工记录。"""
    return {
        "employee_id": emp_id,
        "name": "张三",
        "raw": {"age": 30, "years_of_service": 5, "current_level": "P5",
                "political_status": "党员", "major": "计算机",
                "certificates": "PMP", "job_sequence": "技术研发"},
        "summary": {"performance_summary": {}},
        "scores_360": {"dimensions": {}, "confidence": 0.0},
        "performance_history": [{"year": 2024, "grade": "A"}],
        "training": [],
    }


@pytest.fixture
def agent():
    return ProfileGeneration()


# ════════════ validate_input 双格式 ════════════

class TestValidateInput:
    def test_agent1_format_passes(self, agent):
        data = {"employees": [_agent1_employee()]}
        assert agent.validate_input(data) is True

    def test_adapted_format_passes(self, agent):
        data = {"employees": [_adapted_employee()]}
        assert agent.validate_input(data) is True

    def test_empty_employees_passes(self, agent):
        # 空列表合法
        assert agent.validate_input({"employees": []}) is True

    def test_missing_employees_fails(self, agent):
        assert agent.validate_input({}) is False

    def test_non_list_employees_fails(self, agent):
        assert agent.validate_input({"employees": "not a list"}) is False

    def test_non_dict_data_fails(self, agent):
        assert agent.validate_input("not a dict") is False  # type: ignore[arg-type]

    def test_agent1_missing_required_field_fails(self, agent):
        emp = _agent1_employee()
        del emp["text_summaries"]
        assert agent.validate_input({"employees": [emp]}) is False

    def test_adapted_missing_required_field_fails(self, agent):
        emp = _adapted_employee()
        del emp["raw"]
        assert agent.validate_input({"employees": [emp]}) is False

    def test_neither_format_fails(self, agent):
        # 既无 structured 也无 raw
        emp = {"employee_id": "E001"}
        assert agent.validate_input({"employees": [emp]}) is False

    def test_first_employee_non_dict_fails(self, agent):
        assert agent.validate_input({"employees": ["not a dict"]}) is False


# ════════════ _adapt_input 字段映射 ════════════

class TestAdaptInput:
    def test_field_mapping(self, agent):
        data = {"employees": [_agent1_employee(confidence=0.85)], "llm_stats": {"calls": 3}}
        result = agent._adapt_input(data)
        assert "employees" in result and "llm_stats" in result
        adapted = result["employees"][0]
        # structured → raw
        assert adapted["raw"]["age"] == 30
        assert adapted["raw"]["political_status"] == "党员"
        assert adapted["raw"]["certificates"] == "PMP;系统架构设计师"
        # name 提取
        assert adapted["name"] == "张三"
        assert adapted["employee_id"] == "E001"
        # text_summaries → summary
        assert adapted["summary"] == {"performance_summary": {"2024": "优秀"}}
        # performance → performance_history
        assert adapted["performance_history"] == [{"year": 2024, "grade": "A", "comment": "表现良好"}]
        # scores_360 + confidence_360 → scores_360{dimensions+confidence}
        assert adapted["scores_360"]["dimensions"] == {"专业能力": 85}
        assert adapted["scores_360"]["confidence"] == 0.85

    def test_confidence_360_none_defaults_zero(self, agent):
        # 🔴 confidence_360 显式 None → or 0.0 兜底（dict.get 返回 None 不走 default）
        data = {"employees": [_agent1_employee(confidence=None)]}
        adapted = agent._adapt_input(data)["employees"][0]
        assert adapted["scores_360"]["confidence"] == 0.0

    def test_confidence_360_missing_defaults_zero(self, agent):
        # 键缺失 → emp.get("confidence_360") = None → or 0.0
        emp = _agent1_employee()
        del emp["confidence_360"]
        adapted = agent._adapt_input({"employees": [emp]})["employees"][0]
        assert adapted["scores_360"]["confidence"] == 0.0

    def test_training_preserved(self, agent):
        data = {"employees": [_agent1_employee()]}
        adapted = agent._adapt_input(data)["employees"][0]
        t = adapted["training"][0]
        assert t["course_name"] == "AI 训练"
        assert t["completion_date"] == "2024-06-01"
        assert t["status"] == "完成"
        assert t["score"] == 90.0

    def test_training_none_completion_date(self, agent):
        # 无 completion_date 时置 None
        emp = _agent1_employee()
        emp["training"] = [{"course_name": "X", "status": "进行中"}]  # 无 completion_date
        adapted = agent._adapt_input({"employees": [emp]})["employees"][0]
        assert adapted["training"][0]["completion_date"] is None

    def test_training_with_none_element(self, agent):
        # 🔴 training 列表含 None 元素：不崩
        emp = _agent1_employee()
        emp["training"] = [None, {"course_name": "X", "status": "完成"}]
        adapted = agent._adapt_input({"employees": [emp]})["employees"][0]
        assert len(adapted["training"]) == 2
        # 第一个 None 元素 → course_name="", completion_date=None
        assert adapted["training"][0]["course_name"] == ""
        assert adapted["training"][0]["completion_date"] is None

    def test_multiple_employees(self, agent):
        data = {"employees": [_agent1_employee("E001"), _agent1_employee("E002")]}
        result = agent._adapt_input(data)
        assert len(result["employees"]) == 2
        assert result["employees"][0]["employee_id"] == "E001"
        assert result["employees"][1]["employee_id"] == "E002"

    def test_empty_employees(self, agent):
        result = agent._adapt_input({"employees": []})
        assert result["employees"] == []

    def test_structured_none(self, agent):
        # C3 守卫：structured 为 None → 空字典
        emp = {"employee_id": "E001", "structured": None, "text_summaries": {},
               "scores_360": {}, "performance": [], "training": []}
        adapted = agent._adapt_input({"employees": [emp]})["employees"][0]
        assert adapted["raw"] == {
            "age": None, "political_status": None, "major": None,
            "years_of_service": 0, "current_level": "", "certificates": "", "job_sequence": "",
        }

    def test_employee_non_dict_skipped(self, agent):
        # C3 守卫：非 dict 员工跳过
        data = {"employees": ["not a dict", _agent1_employee()]}
        result = agent._adapt_input(data)
        assert len(result["employees"]) == 1


# ════════════ execute 骨架（offline 模式，不调真实 LLM/embedding）════════════

class TestExecute:
    def test_empty_employees_degraded(self, agent):
        result = agent.execute({"employees": []}, {})
        assert result["status"] == "degraded"
        assert result["data"] == {"employees": [], "stats": {}}
        assert "error" in result["metadata"]
        assert result["metadata"]["error"] == "empty employee list"

    def test_agent1_format_adapted_and_succeeds(self, agent, monkeypatch):
        # execute 入口自动适配 Agent① 格式；offline 避免 LLM/embedding 真实调用
        monkeypatch.setenv("TC_OFFLINE", "1")
        data = {"employees": [_agent1_employee()]}
        result = agent.execute(data, {})
        assert result["status"] == "success"
        assert "employees" in result["data"]
        assert "stats" in result["data"]

    def test_adapted_format_succeeds(self, agent, monkeypatch):
        monkeypatch.setenv("TC_OFFLINE", "1")
        data = {"employees": [_adapted_employee()]}
        result = agent.execute(data, {})
        assert result["status"] == "success"

    def test_stats_content(self, agent, monkeypatch):
        monkeypatch.setenv("TC_OFFLINE", "1")
        data = {"employees": [_agent1_employee("E001"), _agent1_employee("E002")]}
        result = agent.execute(data, {})
        stats = result["data"]["stats"]
        assert stats["total"] == 2
        assert stats["llm_calls"] == 0  # offline 短路不计 LLM 调用
        assert stats["offline_skipped_llm"] == 2
        # 新 schema 字段（替换旧 embedding_corrections）
        assert stats["rerank_calls"] == 0  # offline 跳 Stage 2+3
        assert stats["rerank_failures"] == 0
        assert stats["new_labels"] == 0
        assert stats["exact_matches"] == 0
        # T1 优化新 3 key（R7 三处对称：offline 路径全 0）
        assert stats["llm_adjudications"] == 0
        assert stats["expanded_labels"] == 0
        assert stats["t1_below_min"] == 0

    def test_stats_keys_symmetric_success_vs_worker_degraded(self, agent, monkeypatch):
        """R7 stats 三处对称：worker 异常降级路径与成功路径聚合 stats key 集一致（含 S1 新 3 key）。"""
        monkeypatch.setenv("TC_OFFLINE", "1")
        expected = {
            "total", "llm_calls", "rerank_calls", "rerank_failures", "new_labels",
            "exact_matches", "offline_skipped_llm", "timeouts", "exceptions",
            "llm_adjudications", "expanded_labels", "t1_below_min",
        }
        ok = agent.execute({"employees": [_agent1_employee("E001")]}, {})
        assert set(ok["data"]["stats"].keys()) == expected

        def _boom(emp, context, corpus, vecs):
            raise RuntimeError("simulated worker crash")
        monkeypatch.setattr(agent, "_process_employee", _boom)
        bad = agent.execute({"employees": [_agent1_employee("E002")]}, {})
        assert bad["data"]["stats"]["exceptions"] == 1
        assert bad["data"]["stats"]["llm_adjudications"] == 0
        assert set(bad["data"]["stats"].keys()) == expected

    def test_s1_timeout_linkage_and_timeout_stats_keys(self, agent, monkeypatch):
        """MED-4 S1 超时联动 + 超时降级路径 stats key 对称。

        行为化验证公式：AGENT_PROFILE_TIMEOUT=0 + 慢 worker(0.2s)：
        - S1 关 → timeout=0 → fut.result 立即超时（worker 0.2s 必未完成，非竞态）
        - S1 开 → timeout=0+LABEL_RERANK_TIMEOUT(30) → worker 在预算内完成
        """
        import time as _time
        monkeypatch.setenv("TC_OFFLINE", "1")
        expected = {
            "total", "llm_calls", "rerank_calls", "rerank_failures", "new_labels",
            "exact_matches", "offline_skipped_llm", "timeouts", "exceptions",
            "llm_adjudications", "expanded_labels", "t1_below_min",
        }

        def _slow(emp, context, corpus, vecs):
            _time.sleep(0.2)
            return ({"employee_id": emp.get("employee_id", ""), "status": "success"}, {})

        monkeypatch.setattr(agent, "_process_employee", _slow)
        monkeypatch.setattr(config, "AGENT_PROFILE_TIMEOUT", 0)

        # S1 关：timeout = 0 + 0 = 0 → 超时降级
        monkeypatch.setattr(config, "RERANKER_LLM_ADJUDICATION", False)
        r_off = agent.execute({"employees": [_agent1_employee("E001")]}, {})
        assert r_off["data"]["stats"]["timeouts"] == 1
        assert r_off["data"]["employees"][0]["status"] == "degraded"
        assert set(r_off["data"]["stats"].keys()) == expected  # 超时降级 dict 含新 3 key

        # S1 开：timeout = 0 + 30 = 30 → 不超时
        monkeypatch.setattr(config, "RERANKER_LLM_ADJUDICATION", True)
        monkeypatch.setattr(config, "LABEL_RERANK_TIMEOUT", 30)
        r_on = agent.execute({"employees": [_agent1_employee("E002")]}, {})
        assert r_on["data"]["stats"]["timeouts"] == 0
        assert r_on["data"]["stats"]["total"] == 1

    def test_corpus_loaded(self, agent, monkeypatch):
        # Phase 0 加载 corpus 成功（execute 不崩溃 + status=success 即隐式验证）
        monkeypatch.setenv("TC_OFFLINE", "1")
        data = {"employees": [_adapted_employee()]}
        result = agent.execute(data, {})
        assert result["status"] == "success"
        assert result["data"]["stats"]["total"] == 1

    def test_return_keys_symmetric(self, agent, monkeypatch):
        # C1: success 与 degraded 路径都含 status/data/metadata
        monkeypatch.setenv("TC_OFFLINE", "1")
        ok = agent.execute({"employees": [_adapted_employee()]}, {})
        degraded = agent.execute({"employees": []}, {})
        for r in (ok, degraded):
            assert set(r.keys()) == {"status", "data", "metadata"}

    def test_numpy_clean(self, agent, monkeypatch):
        # numpy_to_native 清洗：json.dumps 不抛
        import json
        monkeypatch.setenv("TC_OFFLINE", "1")
        data = {"employees": [_adapted_employee()]}
        result = agent.execute(data, {})
        s = json.dumps(result["data"])
        assert "NaN" not in s
        assert "Infinity" not in s

    def test_profile_offline_status_and_t3(self, agent, monkeypatch):
        """offline 路径：profile status=offline，t3_potential 含 confidence（全空→0.3）。"""
        monkeypatch.setenv("TC_OFFLINE", "1")
        data = {"employees": [_adapted_employee()]}
        result = agent.execute(data, {})
        profile = result["data"]["employees"][0]
        assert profile["status"] == "offline"
        assert "t3_potential" in profile
        assert "confidence" in profile["t3_potential"]


# ════════════ run() 集成（BaseAgent 包装）════════════

class TestRunIntegration:
    def test_run_wraps_metadata(self, agent, monkeypatch):
        monkeypatch.setenv("TC_OFFLINE", "1")
        result = agent.run({"employees": [_adapted_employee()]}, {"trace_id": "T123"})
        assert result["status"] == "success"
        assert result["metadata"]["agent_name"] == "ProfileGeneration"
        assert result["metadata"]["trace_id"] == "T123"
        assert "duration_ms" in result["metadata"]
        assert result["metadata"]["error"] is None  # D3 对称

    def test_run_invalid_input_returns_error(self, agent):
        result = agent.run({}, {"trace_id": "T1"})
        assert result["status"] == "error"
        assert result["metadata"]["error"] == "输入校验失败"

    def test_timeout_seconds_from_config(self, agent):
        assert agent.timeout_seconds == 120


# ════════════ Phase 1 三阶段串联集成（mock LLM + embedding）════════════

class TestPhase1Integration:
    """验证 _llm_extract → recall_top_k → rerank_label_llm → 注入字段 的完整接线。

    全 mock，不调真实 LLM / bge 模型。
    """

    _MOCK_CONTENT = {
        "t1_professional": [
            {"concept": "Java开发", "standard_label": "Java开发",
             "category": "skill", "confidence": 0.9},
            {"concept": "团队协作", "standard_label": "团队管理",
             "category": "behavior", "confidence": 0.7},
        ],
        "t2_behavioral": [],
        "big_five": {"openness": 70, "conscientiousness": 80,
                     "extraversion": 60, "agreeableness": 75, "neuroticism": 40},
        "t3_raw": {"learning_activities": [], "career_roles": [],
                   "growth_evidence": [], "feedback_signals": []},
        "t3_labels": [
            {"concept": "为下属争取资源", "standard_label": "领导力潜质",
             "category": "potential", "confidence": 0.75, "evidence": []},
        ],
    }

    def _mock_extract(self, employee, context):
        return {
            "content": self._MOCK_CONTENT, "error": None,
            "model": "mock-llm", "usage": {"prompt_tokens": 100, "completion_tokens": 200},
            "offline_skipped": False,
        }

    def test_phase1_injects_matching_fields(self, agent, monkeypatch):
        """Stage 1+2+3 串联：t1 每项注入 matched_label/mapping_source 等字段。"""
        # mock Stage 1
        monkeypatch.setattr(agent, "_llm_extract", self._mock_extract)
        # mock Phase 0 编码（避免 bge 模型）
        monkeypatch.setattr("agents.profile_generation.encode_labels",
                            lambda texts, **kw: None)
        # mock Stage 2 召回
        monkeypatch.setattr("agents.profile_generation.recall_top_k",
                            lambda concept, corpus, **kw: [("Java开发", 0.9), ("Python开发", 0.7)])
        # mock Stage 3 重排（Step 8d：execute 接线 cross-encoder）
        # Step 1.5：T3 项也进 rerank，故返回 3 项（t1[0], t1[1], t3_labels[0]）
        def fake_rerank(items, emp, corpus, **kw):
            return [
                {"idx": 0, "matched_label": "Java开发", "is_new_label": False,
                 "match_confidence": 0.95, "rationale": "ok",
                 "candidates_seen": ["Java开发", "Python开发"], "mapping_source": "cross_encoder_rerank"},
                {"idx": 1, "matched_label": "团队管理", "is_new_label": False,
                 "match_confidence": 0.85, "rationale": "ok",
                 "candidates_seen": ["团队管理"], "mapping_source": "cross_encoder_rerank"},
                {"idx": 2, "matched_label": "领导力潜质", "is_new_label": False,
                 "match_confidence": 0.9, "rationale": "潜质信号明确",
                 "candidates_seen": ["领导力潜质"], "mapping_source": "cross_encoder_rerank"},
            ]
        monkeypatch.setattr("agents.profile_generation.rerank_cross_encoder", fake_rerank)

        result = agent.execute({"employees": [_adapted_employee()]}, {})
        profile = result["data"]["employees"][0]
        assert profile["status"] == "success"
        item0 = profile["t1_professional"][0]
        assert item0["matched_label"] == "Java开发"
        assert item0["mapping_source"] == "cross_encoder_rerank"
        assert item0["match_confidence"] == 0.95
        assert item0["rerank_candidates"] == ["Java开发", "Python开发"]
        assert item0["rerank_rationale"] == "ok"
        # Step 1.5：T3 通道注入匹配字段（idx=2 对应 t3_labels[0]）
        assert "t3_labels" in profile
        t3_item = profile["t3_labels"][0]
        assert t3_item["matched_label"] == "领导力潜质"
        assert t3_item["mapping_source"] == "cross_encoder_rerank"
        assert t3_item["match_confidence"] == 0.9
        # t3_potential 注入
        assert "t3_potential" in profile
        assert "confidence" in profile["t3_potential"]
        # stats 实算
        stats = result["data"]["stats"]
        assert stats["llm_calls"] == 1
        assert stats["rerank_calls"] == 1
        assert stats["exact_matches"] == 0  # cross-encoder mock 接管，全走 rerank 非 exact

    def test_phase1_llm_error_degrades(self, agent, monkeypatch):
        """_llm_extract 返回 error → 员工 degraded，不调 Stage 2+3。"""
        def err_extract(self_, employee, context):
            return {"content": None, "error": "auth failed",
                    "model": "", "usage": {}, "offline_skipped": False}
        monkeypatch.setattr(ProfileGeneration, "_llm_extract", err_extract)
        monkeypatch.setattr("agents.profile_generation.encode_labels",
                            lambda texts, **kw: None)
        rerank_called = {"n": 0}
        monkeypatch.setattr("agents.profile_generation.rerank_cross_encoder",
                            lambda *a, **kw: rerank_called.__setitem__("n", rerank_called["n"] + 1) or [])

        result = agent.execute({"employees": [_adapted_employee()]}, {})
        profile = result["data"]["employees"][0]
        assert profile["status"] == "degraded"
        assert "degraded_reason" in profile
        assert rerank_called["n"] == 0  # error 时不进 Stage 2+3

    def test_phase1_cancel_degrades(self, agent, monkeypatch):
        """cancel_event set → worker 入口即查 → 员工 degraded（reason=cancelled）。"""
        import threading
        monkeypatch.setattr("agents.profile_generation.encode_labels",
                            lambda texts, **kw: None)
        # _llm_extract 不应被调（cancel 在其之前）
        llm_called = {"n": 0}
        def counting_extract(self_, employee, context):
            llm_called["n"] += 1
            return {"content": None, "error": None, "model": "",
                    "usage": {}, "offline_skipped": True}
        monkeypatch.setattr(ProfileGeneration, "_llm_extract", counting_extract)

        cancel = threading.Event()
        cancel.set()
        result = agent.execute(
            {"employees": [_adapted_employee()]},
            {"cancel_event": cancel},
        )
        profile = result["data"]["employees"][0]
        assert profile["status"] == "degraded"
        assert "cancelled" in profile["degraded_reason"]
        assert llm_called["n"] == 0  # cancel 在 _llm_extract 之前，不调 LLM


# ════════════ _llm_extract（Day 2 Task 2.1）════════════

# 模仿 test_llm_summarizer.py mock 模式：patch call_llm_json 入口，不 patch _cache
from unittest.mock import patch

_MOCK_SUCCESS_PROFILE = {
    "content": {
        "t1_professional": [
            {"concept": "Java微服务", "standard_label": "Java开发", "category": "skill",
             "sfia_level": 5, "ability_score": 71, "confidence": 0.85,
             "evidence": [{"source": "绩效评语_2024", "text_snippet": "Java微服务"}]},
            {"concept": "Spring Cloud", "standard_label": "Docker", "category": "tool",
             "sfia_level": 4, "ability_score": 65, "confidence": 0.80,
             "evidence": [{"source": "项目_2025", "text_snippet": "Spring Cloud"}]},
        ],
        "t2_behavioral": [
            {"concept": "跨部门沟通", "standard_label": "跨部门协调", "category": "behavior",
             "sfia_level": 4, "ability_score": 80, "confidence": 0.78,
             "evidence": [{"source": "360评价_2024", "text_snippet": "跨部门"}]},
        ],
        "big_five": {"openness": 72, "conscientiousness": 80, "extraversion": 55,
                     "agreeableness": 68, "neuroticism": 40},
        "t3_raw": {"learning_activities": ["学Docker"], "career_roles": ["研发"],
                   "growth_evidence": ["PMP认证"], "feedback_signals": ["主动学习"]},
        "t3_labels": [
            {"concept": "为下属争取资源、关键时刻兜底", "standard_label": "领导力潜质",
             "category": "potential", "confidence": 0.8,
             "evidence": [{"source": "360评价_2024", "text_snippet": "为下属争取"}]},
        ],
    },
    "error": None,
    "raw_content": None,
    "usage": {"prompt_tokens": 500, "completion_tokens": 200},
    "model": "deepseek-chat",
    "schema_validated": None,
}

_MOCK_PARSE_ERROR_PROFILE = {
    "content": None,
    "error": "JSON parse failed: Expecting value",
    "raw_content": "截断的JSON...",
    "usage": {"prompt_tokens": 500, "completion_tokens": 100},
    "model": "deepseek-chat",
    "schema_validated": False,
}

_MOCK_NETWORK_ERROR_PROFILE = {
    "content": None,
    "error": "Authentication failed: invalid api key",
    "raw_content": None,
    "usage": {},
    "model": "",
    "schema_validated": None,
}

_MOCK_NON_DICT_CONTENT = {
    "content": ["not", "a", "dict"],
    "error": None,
    "raw_content": None,
    "usage": {"prompt_tokens": 100, "completion_tokens": 50},
    "model": "deepseek-chat",
    "schema_validated": None,
}


class TestLlmExtract:
    """_llm_extract 单元测试：offline 短路 + 降级防雪崩 + 范围守卫 + C1 对称。"""

    def test_offline_short_circuits_no_llm_call(self, agent, monkeypatch):
        monkeypatch.setenv("TC_OFFLINE", "1")
        with patch("agents.profile_generation.call_llm_json") as mock_call:
            result = agent._llm_extract(_adapted_employee(), {})
            mock_call.assert_not_called()
        assert result["error"] is None
        assert result["model"] == "offline-placeholder"
        assert result["offline_skipped"] is True
        assert result["content"]["t1_professional"] == []
        assert result["content"]["big_five"] == {
            d: 0 for d in ["openness", "conscientiousness", "extraversion",
                           "agreeableness", "neuroticism"]
        }

    def test_success_returns_content_with_keys(self, agent, monkeypatch):
        monkeypatch.delenv("TC_OFFLINE", raising=False)
        with patch("agents.profile_generation.call_llm_json",
                   return_value=_MOCK_SUCCESS_PROFILE) as mock_call:
            result = agent._llm_extract(_adapted_employee(), {"trace_id": "T1"})
        mock_call.assert_called_once()
        assert result["error"] is None
        assert result["model"] == "deepseek-chat"
        assert result["offline_skipped"] is False
        assert result["usage"]["prompt_tokens"] == 500
        c = result["content"]
        assert {"t1_professional", "t2_behavioral", "big_five", "t3_raw", "t3_labels"} <= set(c.keys())
        assert len(c["t1_professional"]) == 2
        assert c["t1_professional"][0]["standard_label"] == "Java开发"
        # Step 1.4: T3 升级为标签抽取，t3_labels 含标准标签
        assert len(c["t3_labels"]) == 1
        assert c["t3_labels"][0]["standard_label"] == "领导力潜质"
        assert c["t3_labels"][0]["category"] == "potential"

    def test_passes_profile_extract_timeout_to_llm(self, agent, monkeypatch):
        # Day 2 补丁：_llm_extract 用 PROFILE_EXTRACT_LLM_TIMEOUT（非默认 30s），
        # 因结构化 JSON 输出比 Agent① summary 重，30s 实测超时
        import config as _cfg
        monkeypatch.delenv("TC_OFFLINE", raising=False)
        with patch("agents.profile_generation.call_llm_json",
                   return_value=_MOCK_SUCCESS_PROFILE) as mock_call:
            agent._llm_extract(_adapted_employee(), {})
        kwargs = mock_call.call_args.kwargs
        assert kwargs.get("timeout") == _cfg.PROFILE_EXTRACT_LLM_TIMEOUT
        assert kwargs.get("timeout") != 30  # 确认不是默认 LLM_API_TIMEOUT
        # max_tokens 也用独立常量（推理模型 thinking tokens 计入，4096 不够）
        assert kwargs.get("max_tokens") == _cfg.PROFILE_EXTRACT_MAX_TOKENS
        assert kwargs.get("max_tokens") != 4096

    def test_parse_failure_degrades_no_second_llm(self, agent, monkeypatch):
        # V8 防雪崩：解析失败 → 确定性降级，不调第 2 次 LLM
        monkeypatch.delenv("TC_OFFLINE", raising=False)
        with patch("agents.profile_generation.call_llm_json",
                   return_value=_MOCK_PARSE_ERROR_PROFILE) as mock_call:
            result = agent._llm_extract(_adapted_employee(), {})
        assert mock_call.call_count == 1
        assert result["error"] is None
        assert result["model"] == "degraded-placeholder"
        assert result["content"]["t1_professional"] == []

    def test_network_error_propagates(self, agent, monkeypatch):
        monkeypatch.delenv("TC_OFFLINE", raising=False)
        with patch("agents.profile_generation.call_llm_json",
                   return_value=_MOCK_NETWORK_ERROR_PROFILE):
            result = agent._llm_extract(_adapted_employee(), {})
        assert result["error"] == "Authentication failed: invalid api key"
        assert result["content"] is None
        assert result["model"] == ""

    def test_non_dict_content_returns_error_with_type(self, agent, monkeypatch):
        # C3/G：LLM 返回非 dict → error 含实际类型名
        monkeypatch.delenv("TC_OFFLINE", raising=False)
        with patch("agents.profile_generation.call_llm_json",
                   return_value=_MOCK_NON_DICT_CONTENT):
            result = agent._llm_extract(_adapted_employee(), {})
        assert result["error"] is not None
        assert "list" in result["error"]

    def test_cancel_event_returns_error(self, agent):
        import threading
        ctx = {"cancel_event": threading.Event()}
        ctx["cancel_event"].set()
        with patch("agents.profile_generation.call_llm_json") as mock_call:
            result = agent._llm_extract(_adapted_employee(), ctx)
            mock_call.assert_not_called()
        assert result["error"] == "cancelled"
        assert result["content"] is None

    def test_clamps_out_of_range_values(self, agent, monkeypatch):
        monkeypatch.delenv("TC_OFFLINE", raising=False)
        over = {
            "content": {
                "t1_professional": [{"concept": "X", "standard_label": "Java开发",
                                     "category": "skill",
                                     "sfia_level": 9, "ability_score": 150,
                                     "confidence": 1.5, "evidence": []}],
                "t2_behavioral": [{"concept": "Y", "standard_label": "跨部门协调",
                                   "category": "behavior",
                                   "sfia_level": -1, "ability_score": -5,
                                   "confidence": -0.2, "evidence": []}],
                "big_five": {"openness": 120, "conscientiousness": -10,
                             "extraversion": 50, "agreeableness": 50, "neuroticism": 50},
                "t3_raw": {"learning_activities": [], "career_roles": [],
                           "growth_evidence": [], "feedback_signals": []},
                "t3_labels": [{"concept": "兜底", "standard_label": "领导力潜质",
                               "category": "potential", "confidence": 1.4,
                               "evidence": []}],
            },
            "error": None, "raw_content": None,
            "usage": {}, "model": "deepseek-chat", "schema_validated": None,
        }
        with patch("agents.profile_generation.call_llm_json", return_value=over):
            result = agent._llm_extract(_adapted_employee(), {})
        c = result["content"]
        assert c["t1_professional"][0]["ability_score"] == 100
        assert c["t1_professional"][0]["sfia_level"] == 7
        assert c["t1_professional"][0]["confidence"] == 1.0
        assert c["t2_behavioral"][0]["ability_score"] == 0
        assert c["t2_behavioral"][0]["sfia_level"] == 0
        assert c["t2_behavioral"][0]["confidence"] == 0.0
        assert c["big_five"]["openness"] == 100
        assert c["big_five"]["conscientiousness"] == 0
        # Step 1.6: T3 项只夹紧 confidence（不挂 sfia/ability，无此字段不崩）
        assert c["t3_labels"][0]["confidence"] == 1.0
        assert "sfia_level" not in c["t3_labels"][0]
        assert "ability_score" not in c["t3_labels"][0]

    def test_clamp_fills_missing_ability_score_from_level(self, agent, monkeypatch):
        """Step 1.6 + 1.2 接线：T1/T2 项缺 ability_score 但有 level → 映射补全。"""
        monkeypatch.delenv("TC_OFFLINE", raising=False)
        missing = {
            "content": {
                "t1_professional": [
                    # IT 类 Java开发，sfia=7 → 缺 ability_score → 映射 100
                    {"concept": "Java", "standard_label": "Java开发", "category": "skill",
                     "sfia_level": 7, "confidence": 0.8, "evidence": []},
                    # 非 IT 工艺工程，缺 ability_score 也缺 level → 不补（保持无字段）
                    {"concept": "工艺", "standard_label": "工艺工程", "category": "skill",
                     "confidence": 0.5, "evidence": []},
                ],
                "t2_behavioral": [
                    # T2 强制 SFIA，sfia=4 → 缺 ability_score → 映射 57
                    {"concept": "协作", "standard_label": "跨部门协调", "category": "behavior",
                     "sfia_level": 4, "confidence": 0.7, "evidence": []},
                ],
                "big_five": {d: 50 for d in config.BIG_FIVE_DIMENSIONS},
                "t3_raw": {"learning_activities": [], "career_roles": [],
                           "growth_evidence": [], "feedback_signals": []},
                "t3_labels": [],
            },
            "error": None, "raw_content": None,
            "usage": {}, "model": "deepseek-chat", "schema_validated": None,
        }
        with patch("agents.profile_generation.call_llm_json", return_value=missing):
            result = agent._llm_extract(_adapted_employee(), {})
        c = result["content"]
        # IT 类 sfia=7 → 100
        assert c["t1_professional"][0]["ability_score"] == 100
        # 非 IT 缺 level 不补 ability_score（保持无字段，不强制塞 0）
        assert "ability_score" not in c["t1_professional"][1]
        # T2 强制 SFIA sfia=4 → 57
        assert c["t2_behavioral"][0]["ability_score"] == 57

    def test_return_key_symmetry_all_paths(self, agent, monkeypatch):
        # C1 对称：所有返回路径顶层 key 集合相同
        expected_keys = {"content", "error", "model", "usage", "offline_skipped"}
        monkeypatch.setenv("TC_OFFLINE", "1")
        r1 = agent._llm_extract(_adapted_employee(), {})
        assert set(r1.keys()) == expected_keys

        monkeypatch.delenv("TC_OFFLINE", raising=False)
        with patch("agents.profile_generation.call_llm_json",
                   return_value=_MOCK_SUCCESS_PROFILE):
            r2 = agent._llm_extract(_adapted_employee(), {})
        assert set(r2.keys()) == expected_keys

        with patch("agents.profile_generation.call_llm_json",
                   return_value=_MOCK_PARSE_ERROR_PROFILE):
            r3 = agent._llm_extract(_adapted_employee(), {})
        assert set(r3.keys()) == expected_keys

        with patch("agents.profile_generation.call_llm_json",
                   return_value=_MOCK_NETWORK_ERROR_PROFILE):
            r4 = agent._llm_extract(_adapted_employee(), {})
        assert set(r4.keys()) == expected_keys

    def test_build_system_prompt_includes_all_categories(self, agent):
        sp = agent._build_system_prompt()
        for cat in ["skill", "tool", "domain", "knowledge", "behavior", "potential"]:
            assert cat in sp
        assert "Java开发" in sp
        assert "跨部门协调" in sp

    def test_build_system_prompt_three_channel_structure(self, agent):
        """Step 1.3：三通道分块 + T3 证据模式 + T3 few-shot。"""
        sp = agent._build_system_prompt()
        # 三通道分块标题
        assert "【T1 通道·专业能力】" in sp
        assert "【T2 通道·行为能力】" in sp
        assert "【T3 通道·发展潜力】" in sp
        # T3 证据模式 5 类引导
        assert "领导力潜质" in sp
        assert "成长型思维" in sp
        assert "自驱力" in sp
        assert "抗压韧性" in sp
        assert "战略眼光" in sp
        # T3 few-shot（concept→领导力潜质/成长型思维）
        assert "为下属争取资源" in sp
        assert "绩效 B→C→A 翻盘" in sp
        # T3 标签库（potential 项展示）
        assert "领导力潜质" in sp  # 既是证据模式也是标签库项

    def test_build_system_prompt_includes_definition_and_few_shot(self, agent):
        """Step 8b：prompt 含 definition/keywords（区分相似标签）+ few-shot 示例。"""
        sp = agent._build_system_prompt()
        # definition 出现（取 corpus 某项的 definition 字段值）
        corpus = load_label_corpus()
        sample = next((c for c in corpus if c.get("definition")), None)
        assert sample is not None, "corpus 至少有一项含 definition"
        assert sample["definition"] in sp, f"definition 未进 prompt: {sample['definition']}"
        # keywords 标记出现（至少一项有 keywords）
        sample_kw = next((c for c in corpus if c.get("keywords")), None)
        if sample_kw:
            assert "[关键词:" in sp, "keywords 标记未进 prompt"
            assert sample_kw["keywords"][0] in sp, "keyword 值未进 prompt"
        # few-shot 示例出现（3 个 concept→standard_label 映射样例）
        assert "concept=" in sp, "few-shot concept= 标记未进 prompt"
        assert "智能制造" in sp, "few-shot 智能制造示例缺失"
        assert "Java开发" in sp, "few-shot Java开发示例缺失"
        assert "团队管理" in sp, "few-shot 团队管理示例缺失"

    def test_build_user_prompt_includes_employee_data(self, agent):
        emp = _adapted_employee()
        emp["performance_history"] = [{"year": 2024, "grade": "A"}]
        emp["summary"] = {"performance_summary": "优秀表现"}
        up = agent._build_user_prompt(emp)
        assert "E001" in up
        assert "A" in up
        assert "优秀表现" in up

    def test_build_user_prompt_handles_missing_fields(self, agent):
        # C3 守卫：员工字段缺失/None 不崩
        emp = {"employee_id": "E999"}
        up = agent._build_user_prompt(emp)
        assert "E999" in up
        assert "无" in up
