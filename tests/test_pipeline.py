"""PipelineRunner 单元测试"""
import json
import pytest
from pathlib import Path
from agents.base_agent import BaseAgent
from orchestrator.pipeline import PipelineRunner


class _StepAgent(BaseAgent):
    agent_version = "0.1.0"

    def __init__(self, name: str, multiplier: int = 2):
        self.agent_name = name
        self.multiplier = multiplier

    def validate_input(self, data: dict) -> bool:
        return True

    def execute(self, data: dict, context: dict) -> dict:
        val = data.get("value", 0)
        return {
            "status": "success",
            "data": {"value": val * self.multiplier},
            "metadata": {},
        }

    def get_input_schema(self) -> dict:
        return {"type": "object"}

    def get_output_schema(self) -> dict:
        return {"type": "object"}


class TestPipelineRunner:
    def test_single_agent(self, tmp_path):
        agent = _StepAgent("Double", 2)
        runner = PipelineRunner([agent], output_dir=str(tmp_path))
        result = runner.run({"value": 42}, trace_id="pipe-test-001")

        assert result["status"] == "success"
        assert result["final_output"]["value"] == 84
        assert len(result["steps"]) == 1
        assert result["steps"][0]["agent"] == "Double"
        assert result["steps"][0]["status"] == "success"

    def test_multi_agent_pipeline(self, tmp_path):
        a1 = _StepAgent("Double", 2)
        a2 = _StepAgent("Triple", 3)
        runner = PipelineRunner([a1, a2], output_dir=str(tmp_path))
        result = runner.run({"value": 5}, trace_id="pipe-test-002")

        # 5 * 2 = 10, then 10 * 3 = 30
        assert result["final_output"]["value"] == 30
        assert len(result["steps"]) == 2
        assert result["status"] == "success"

    def test_intermediate_files(self, tmp_path):
        a1 = _StepAgent("Agent1", 2)
        runner = PipelineRunner([a1], output_dir=str(tmp_path))
        result = runner.run({"value": 1}, trace_id="pipe-test-003")

        output_file = result["steps"][0]["output_file"]
        assert Path(output_file).exists()
        saved = json.loads(Path(output_file).read_text(encoding="utf-8"))
        assert saved["status"] == "success"

    def test_trace_id_auto_generation(self, tmp_path):
        a1 = _StepAgent("Agent1", 1)
        runner = PipelineRunner([a1], output_dir=str(tmp_path))
        result = runner.run({"value": 1})
        assert result["trace_id"].startswith("TC-")
        assert "total_duration_ms" in result

    def test_failing_agent_partial_pipeline(self, tmp_path):
        class FailAgent(BaseAgent):
            agent_name = "FailAgent"
            agent_version = "0.1.0"
            def validate_input(self, data): return True
            def execute(self, data, context):
                raise RuntimeError("Boom")
            def get_input_schema(self): return {}
            def get_output_schema(self): return {}

        a1 = FailAgent()
        a2 = _StepAgent("Recovery", 1)
        runner = PipelineRunner([a1, a2], output_dir=str(tmp_path))
        result = runner.run({"value": 10}, trace_id="pipe-test-004")

        assert result["status"] == "partial"
        assert result["steps"][0]["status"] == "error"
        # 验证下游 Agent 在错误后仍正常执行（Pipeline 不会提前终止）
        assert len(result["steps"]) == 2, "Pipeline should continue after error"
        assert result["steps"][1]["status"] == "success", "Recovery agent should execute after failure"
        assert result["steps"][1]["agent"] == "Recovery"
