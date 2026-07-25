"""BaseAgent 基类

所有 Agent 必须继承此类，实现 validate_input / execute /
get_input_schema / get_output_schema 四个方法。

---
文件：agents/base_agent.py
项目：Talent Compass
依据：《多Agent协作完整行为逻辑与实现方法.md》BaseAgent 契约
"""
import json
import time
import logging
from abc import ABC, abstractmethod
from typing import Any
from datetime import datetime, timezone

from utils.logger import setup_logger

logger = setup_logger()


class BaseAgent(ABC):
    """Agent 抽象基类。

    子类必须定义类属性 agent_name 和 agent_version，
    并实现四个抽象方法。

    可选类属性:
        timeout_seconds: 覆盖 PipelineRunner 默认超时（int）。
            例如 DataUnderstanding 需要 300s 处理大量 LLM 调用。
    """

    agent_name: str
    agent_version: str

    @abstractmethod
    def validate_input(self, data: dict) -> bool:
        """校验输入数据是否符合本 Agent 的输入 Schema。

        Args:
            data: 待校验的输入字典。

        Returns:
            True 表示通过校验，False 表示校验失败。
        """
        ...

    @abstractmethod
    def execute(self, data: dict, context: dict) -> dict:
        """执行 Agent 核心逻辑。

        Args:
            data: 输入数据（已通过 validate_input 校验）。
            context: 上下文字典，含 trace_id, timeout_seconds, upstream_results。

        Returns:
            {
                "status": "success" | "degraded" | "error",
                "data": ...,
                "metadata": {
                    "agent_name": str,
                    "agent_version": str,
                    "duration_ms": int,
                    "trace_id": str,
                    "data_lineage": {"model": str, "timestamp": str, "audit_status": str}
                }
            }
        """
        ...

    @abstractmethod
    def get_input_schema(self) -> dict:
        """返回输入 JSON Schema。"""
        ...

    @abstractmethod
    def get_output_schema(self) -> dict:
        """返回输出 JSON Schema。"""
        ...

    @staticmethod
    def _check_cancel(context: dict) -> bool:
        """检查 PipelineRunner 是否已请求取消当前 Agent 执行。

        子类应在每次 LLM API 调用前调用此方法。若返回 True，
        应尽快返回 {"status": "degraded", ...} 并停止处理。

        PipelineRunner 通过 context["cancel_event"]（threading.Event）
        在超时前 5 秒设置此信号，给 Agent 优雅退出的窗口。

        注意：此方法在当前基线（Day 1）无调用方——Day 3 Agent① 实现
        （agents/data_understanding.py）将在逐员工 LLM 循环中调用。

        Args:
            context: 上下文字典（由 PipelineRunner 注入 cancel_event）。

        Returns:
            True 表示应取消执行，False 表示继续正常执行。
        """
        cancel = context.get("cancel_event")
        if cancel is not None and cancel.is_set():
            return True
        return False

    def run(self, data: dict, context: dict) -> dict:
        """公共入口：校验 → 执行 → 包装 metadata。

        子类不应覆盖此方法；如有自定义行为，覆盖 execute 即可。

        Args:
            data: 输入数据。
            context: 上下文字典。

        Returns:
            标准格式的 Agent 执行结果。
        """
        trace_id = context.get("trace_id", "-")
        t0 = time.perf_counter()

        # 1. 输入校验
        if not self.validate_input(data):
            duration_ms = int((time.perf_counter() - t0) * 1000)
            logger.warning(
                f"Agent {self.agent_name} 输入校验失败",
                extra={"trace_id": trace_id, "agent_name": self.agent_name},
            )
            return {
                "status": "error",
                "data": None,
                "metadata": {
                    "agent_name": self.agent_name,
                    "agent_version": self.agent_version,
                    "duration_ms": duration_ms,
                    "trace_id": trace_id,
                    "error": "输入校验失败",
                    "data_lineage": {
                        "model": "",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "audit_status": "pending",
                    },
                },
            }

        logger.info(
            f"Agent {self.agent_name} 开始执行",
            extra={"trace_id": trace_id, "agent_name": self.agent_name},
        )

        # 2. 执行
        try:
            result = self.execute(data, context)

            # 防御：子类 execute() 可能返回非 dict 或缺少 "status" 键
            if not isinstance(result, dict):
                duration_ms = int((time.perf_counter() - t0) * 1000)
                return {
                    "status": "error",
                    "data": None,
                    "metadata": {
                        "agent_name": self.agent_name,
                        "agent_version": self.agent_version,
                        "duration_ms": duration_ms,
                        "trace_id": trace_id,
                        "error": f"execute() 返回非 dict 类型: {type(result).__name__}",
                        "data_lineage": {
                            "model": "",
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "audit_status": "pending",
                        },
                    },
                }
            if "status" not in result:
                result["status"] = "success"
        except Exception as exc:
            duration_ms = int((time.perf_counter() - t0) * 1000)
            logger.error(
                f"Agent {self.agent_name} 执行异常: {exc}",
                extra={"trace_id": trace_id, "agent_name": self.agent_name},
            )
            return {
                "status": "error",
                "data": None,
                "metadata": {
                    "agent_name": self.agent_name,
                    "agent_version": self.agent_version,
                    "duration_ms": duration_ms,
                    "trace_id": trace_id,
                    "error": str(exc),
                    "data_lineage": {
                        "model": "",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "audit_status": "pending",
                    },
                },
            }

        duration_ms = int((time.perf_counter() - t0) * 1000)

        # 3. 补全 metadata
        if "metadata" not in result:
            result["metadata"] = {}
        result["metadata"].update({
            "agent_name": self.agent_name,
            "agent_version": self.agent_version,
            "duration_ms": duration_ms,
            "trace_id": trace_id,
        })
        # D3: 对称契约 — 成功路径注入 error: None，与错误路径 key 集合一致
        result["metadata"].setdefault("error", None)

        # 4. 注入默认 data_lineage（基类强制，参见 CLAUDE.md D4）
        if "data_lineage" not in result["metadata"]:
            result["metadata"]["data_lineage"] = {
                "model": "",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "audit_status": "pending",
            }

        logger.info(
            f"Agent {self.agent_name} 执行完成 ({duration_ms}ms)",
            extra={
                "trace_id": trace_id,
                "agent_name": self.agent_name,
                "duration_ms": duration_ms,
            },
        )

        return result
