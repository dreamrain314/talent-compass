"""BaseAgent 单元测试"""
import pytest
from agents.base_agent import BaseAgent


class _TestAgent(BaseAgent):
    agent_name = "TestAgent"
    agent_version = "0.1.0"

    def validate_input(self, data: dict) -> bool:
        return "input" in data

    def execute(self, data: dict, context: dict) -> dict:
        return {
            "status": "success",
            "data": {"result": data["input"] * 2},
            "metadata": {},
        }

    def get_input_schema(self) -> dict:
        return {"type": "object", "required": ["input"]}

    def get_output_schema(self) -> dict:
        return {"type": "object", "properties": {"result": {"type": "integer"}}}


class _FailingAgent(BaseAgent):
    agent_name = "FailingAgent"
    agent_version = "0.1.0"

    def validate_input(self, data: dict) -> bool:
        return True

    def execute(self, data: dict, context: dict) -> dict:
        raise RuntimeError("Simulated failure")

    def get_input_schema(self) -> dict:
        return {"type": "object"}

    def get_output_schema(self) -> dict:
        return {"type": "object"}


class TestBaseAgent:
    def test_successful_execution(self):
        agent = _TestAgent()
        result = agent.run({"input": 42}, {"trace_id": "test-001", "timeout_seconds": 120})
        assert result["status"] == "success"
        assert result["data"]["result"] == 84
        assert result["metadata"]["agent_name"] == "TestAgent"
        assert result["metadata"]["agent_version"] == "0.1.0"
        assert result["metadata"]["trace_id"] == "test-001"
        assert "duration_ms" in result["metadata"]

    def test_validation_failure(self):
        agent = _TestAgent()
        result = agent.run({}, {"trace_id": "test-002", "timeout_seconds": 120})
        assert result["status"] == "error"
        assert result["data"] is None

    def test_execution_exception(self):
        agent = _FailingAgent()
        result = agent.run({"any": "data"}, {"trace_id": "test-003", "timeout_seconds": 120})
        assert result["status"] == "error"
        assert "Simulated failure" in result["metadata"]["error"]

    def test_output_schema(self):
        agent = _TestAgent()
        schema = agent.get_output_schema()
        assert schema["type"] == "object"
        assert "result" in schema["properties"]

    def test_input_schema(self):
        agent = _TestAgent()
        schema = agent.get_input_schema()
        assert "input" in schema["required"]
