"""Agent④' 匹配引擎封装（M3，向量直配 + 固定公式评分）。

BaseAgent 契约封装：输入 {job_profile, employees}，内部构建员工证据向量索引
（EvidenceIndex，含 .npy 缓存），调 match_engine.rank_candidates 输出排序候选。
LLM 不参与评分（零 LLM 评分纪律）；证据锚点沿用 Agent① 锚点语义可点回原文。

消费者：scripts/run_matching.py（M5 编排）、scripts/blind_test.py（M4 盲测直调
match_engine 时绕过本封装）。
"""

from __future__ import annotations

from agents.base_agent import BaseAgent
from utils.evidence_index import EvidenceIndex
from utils.match_engine import rank_candidates
from utils.logger import setup_logger

logger = setup_logger()

__all__ = ["MatchingAgent"]


class MatchingAgent(BaseAgent):
    agent_name = "matching"
    agent_version = "1.0.0"
    timeout_seconds = 600  # 索引构建（50 人 ~750 chunk 编码）+ 重排余量

    def validate_input(self, data: dict) -> bool:
        if not isinstance(data, dict):
            return False
        jp = data.get("job_profile")
        if not isinstance(jp, dict) or not jp.get("queries"):
            return False
        return isinstance(data.get("employees"), list)

    def execute(self, data: dict, context: dict) -> dict:
        job_profile = data["job_profile"]
        employees = data["employees"]

        index = EvidenceIndex.build(
            employees,
            cache_path=None,  # Pipeline 编排走内存直传；盲测脚本自带缓存
        )
        ranking = rank_candidates(
            job_profile, employees, index, cross_encoder_fn=None
        )

        recommended = sum(
            1 for c in ranking["candidates"] if c["decision"] == "recommend"
        )
        pool = sum(1 for c in ranking["candidates"] if c["decision"] == "backup_pool")
        logger.info(
            "matching done: %s candidates=%d recommend=%d pool=%d",
            ranking["job_id"], len(ranking["candidates"]), recommended, pool,
            extra={"trace_id": context.get("trace_id", "-"), "agent_name": self.agent_name},
        )

        return {
            "status": "success",
            "data": {"ranking": ranking},
            "metadata": {
                "data_lineage": {
                    "model": "fastembed+bge-reranker(零LLM评分)",
                    "timestamp": "",
                    "audit_status": "verified",
                },
            },
        }

    def get_input_schema(self) -> dict:
        return {
            "type": "object",
            "required": ["job_profile", "employees"],
            "properties": {
                "job_profile": {"type": "object", "required": ["queries"]},
                "employees": {"type": "array"},
            },
        }

    def get_output_schema(self) -> dict:
        return {
            "type": "object",
            "required": ["ranking"],
            "properties": {"ranking": {"type": "object"}},
        }
