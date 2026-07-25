"""PipelineRunner — 编排器核心

确定性 Python 代码（if/else/try/except），零 AI 调用。
按顺序执行 Agent 列表，保存中间结果 JSON，处理超时和异常。
"""
import json
import time
import logging
import concurrent.futures
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import INTERMEDIATE_DIR, AGENT_EXEC_TIMEOUT

from agents.base_agent import BaseAgent
from utils.logger import setup_logger, generate_trace_id
from utils import numpy_to_native

logger = setup_logger()


class PipelineRunner:

    def __init__(
        self,
        agents: list[BaseAgent],
        output_dir: str | None = None,
        default_timeout: int = AGENT_EXEC_TIMEOUT,
    ):
        self.agents = agents
        self.output_dir = Path(output_dir) if output_dir is not None else Path(str(INTERMEDIATE_DIR))
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.default_timeout = default_timeout

    @staticmethod
    def _agent_timeout(agent: BaseAgent, default: int) -> int:
        """返回 Agent 的超时值：优先用 Agent 类属性，否则用默认值。"""
        val = getattr(agent, "timeout_seconds", default)
        if isinstance(val, int) and val > 0:
            return val
        logger.warning(
            f"Agent {getattr(agent, 'agent_name', '?')} has invalid timeout_seconds={val!r} "
            f"(type={type(val).__name__}), falling back to default={default}"
        )
        return default

    def run(self, initial_data: dict, trace_id: str | None = None) -> dict:
        if trace_id is None:
            trace_id = generate_trace_id()

        t_pipeline = time.perf_counter()
        current_data = initial_data
        steps = []
        upstream_results: list[dict] = []
        pipeline_status = "success"

        logger.info(
            f"Pipeline start: {len(self.agents)} agents",
            extra={"trace_id": trace_id, "agent_name": "PipelineRunner"},
        )

        upstream_lineage: list[dict] = []

        for i, agent in enumerate(self.agents):
            agent_timeout = self._agent_timeout(agent, self.default_timeout)
            context = {
                "trace_id": trace_id,
                "timeout_seconds": agent_timeout,
                "upstream_results": list(upstream_results),
                "upstream_lineage": list(upstream_lineage),
                "upstream_errors": [],
            }

            step_result = self._execute_with_timeout(agent, current_data, context, timeout=agent_timeout)

            step_entry = {
                "step": i,
                "agent": agent.agent_name,
                "status": step_result.get("status", "error"),
                "duration_ms": step_result.get("metadata", {}).get("duration_ms", 0),
            }

            output_file = self._save_intermediate(i, agent.agent_name, step_result, trace_id)
            step_entry["output_file"] = output_file
            steps.append(step_entry)

            if step_result.get("status") == "error":
                pipeline_status = "partial"
                context["upstream_errors"].append({
                    "agent": agent.agent_name,
                    "step": i,
                    "error": step_result.get("metadata", {}).get("error", "unknown"),
                })
                logger.error(
                    f"Agent {agent.agent_name} failed, pipeline marked partial",
                    extra={"trace_id": trace_id, "agent_name": "PipelineRunner"},
                )
            elif step_result.get("status") == "degraded":
                if pipeline_status == "success":
                    pipeline_status = "partial"
                logger.warning(
                    f"Agent {agent.agent_name} degraded",
                    extra={"trace_id": trace_id, "agent_name": "PipelineRunner"},
                )

            val = step_result.get("data")
            if step_result.get("status") == "error":
                # On error, keep current_data unchanged — downstream agents get the same data
                # the failed agent received, with error info in context["upstream_errors"]
                pass
            else:
                current_data = {} if val is None else val

            # ── 累积 data_lineage 链，供下游 Agent 追溯完整数据来源 ──
            lineage = step_result.get("metadata", {}).get("data_lineage", {})
            if lineage:
                upstream_lineage.append({
                    "agent_name": agent.agent_name,
                    "step": i,
                    "data_lineage": lineage,
                })
            # summary 截断（仅用于前端展示，不保证 JSON 完整性）；
            # 截断后追加 "..." 标记提示信息不完整
            raw_summary = json.dumps(current_data, ensure_ascii=False, default=str)
            if len(raw_summary) > 200:
                raw_summary = raw_summary[:197] + "..."
            upstream_results.append({
                "agent_name": agent.agent_name,
                "status": step_result.get("status"),
                "duration_ms": step_result.get("metadata", {}).get("duration_ms", 0),
                "summary": raw_summary,
            })

        total_duration_ms = int((time.perf_counter() - t_pipeline) * 1000)

        logger.info(
            f"Pipeline done: {pipeline_status} ({total_duration_ms}ms)",
            extra={
                "trace_id": trace_id,
                "agent_name": "PipelineRunner",
                "duration_ms": total_duration_ms,
            },
        )

        return {
            "trace_id": trace_id,
            "status": pipeline_status,
            "steps": steps,
            "final_output": current_data,
            "total_duration_ms": total_duration_ms,
        }

    def _execute_with_timeout(
        self, agent: BaseAgent, data: dict, context: dict, timeout: int = AGENT_EXEC_TIMEOUT
    ) -> dict:
        """带真正超时控制的 Agent 执行。

        使用 threading.Event 作为取消信号传给 Agent（Agent 应周期性检查），
        超时后 shutdown(wait=False) 确保 Pipeline 不被阻塞。

        Args:
            agent: 要执行的 Agent 实例
            data: 输入数据
            context: 上下文字典（会被注入 cancel_event）
            timeout: 超时秒数，默认 AGENT_EXEC_TIMEOUT（来自 config.py）

        Returns:
            Agent 执行结果字典
        """
        import threading

        trace_id = context.get("trace_id", "-")
        cancel_event = threading.Event()
        # 将取消事件注入 context，Agent 可在长时间操作中检查
        ctx = {**context, "cancel_event": cancel_event}
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        future = executor.submit(agent.run, data, ctx)
        # 提前通知 Agent 退出（至少等待 1 秒，给优雅关闭窗口）
        # 提前 timeout-5 秒通知 Agent 优雅退出；clamp 最小 1s 防负延迟。
        # 注意: timeout<=6 时 cancel_delay 被 clamp 为 1s，Timer 与硬超时接近同时触发，
        # 但两者都返回 degraded 状态，结果一致。
        cancel_delay = max(1, timeout - 5)
        cancel_timer = threading.Timer(cancel_delay, cancel_event.set)
        cancel_timer.start()
        t_start = time.perf_counter()
        try:
            result = future.result(timeout=timeout)
            cancel_timer.cancel()
            executor.shutdown(wait=False)
            return result
        except concurrent.futures.TimeoutError:
            cancel_timer.cancel()
            elapsed_ms = int((time.perf_counter() - t_start) * 1000)
            logger.warning(
                f"Agent {agent.agent_name} timeout ({timeout}s)",
                extra={"trace_id": trace_id, "agent_name": agent.agent_name},
            )
            # cancel_event 已由 Timer 在超时前 5 秒设置
            # 关键：wait=False 不阻塞 Pipeline，cancel_futures 通知线程（Python 3.9+）
            executor.shutdown(wait=False, cancel_futures=True)
            return {
                "status": "degraded",
                "data": data,
                "metadata": {
                    "agent_name": agent.agent_name,
                    "agent_version": agent.agent_version,
                    "duration_ms": elapsed_ms,
                    "trace_id": trace_id,
                    "error": f"timeout ({timeout}s)",
                    "data_lineage": {"model": "", "timestamp": datetime.now(timezone.utc).isoformat(), "audit_status": "pending"},
                },
            }
        except Exception as exc:
            cancel_timer.cancel()
            elapsed_ms = int((time.perf_counter() - t_start) * 1000)
            logger.error(
                f"Agent {agent.agent_name} exception: {exc}",
                extra={"trace_id": trace_id, "agent_name": agent.agent_name},
            )
            executor.shutdown(wait=False, cancel_futures=True)
            return {
                "status": "error",
                "data": data,
                "metadata": {
                    "agent_name": agent.agent_name,
                    "agent_version": agent.agent_version,
                    "duration_ms": elapsed_ms,
                    "trace_id": trace_id,
                    "error": str(exc),
                    "data_lineage": {"model": "", "timestamp": datetime.now(timezone.utc).isoformat(), "audit_status": "pending"},
                },
            }

    def _save_intermediate(
        self, step_index: int, agent_name: str, result: dict, trace_id: str
    ) -> str:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{step_index:02d}_{agent_name}_{timestamp}_{trace_id}.json"
        filepath = self.output_dir / filename
        try:
            data = result.get("data")
            if isinstance(data, list) and data and isinstance(data[0], dict):
                try:
                    for item in data:
                        for k, v in item.items():
                            item[k] = numpy_to_native(v)
                except Exception:
                    pass
            serialized = json.dumps(result, ensure_ascii=False, indent=2, default=str)
        except (TypeError, ValueError) as e:
            logger.warning(
                f"JSON serialize partial failure: {e}",
                extra={"trace_id": trace_id, "agent_name": "PipelineRunner"},
            )
            # 降级处理：只保存可安全序列化的部分
            try:
                safe_data = result.get("data")
                safe = {
                    "status": result.get("status", "error"),
                    "error": str(e),
                    "data": safe_data,
                    "metadata": {
                        k: json.loads(json.dumps(v, ensure_ascii=False, default=str)) if isinstance(v, (dict, list)) else v
                        for k, v in result.get("metadata", {}).items()
                    },
                }
                serialized = json.dumps(safe, ensure_ascii=False, indent=2, default=str)
            except Exception:
                safe_data = result.get("data")
                safe = {
                    "status": result.get("status", "error"),
                    "error": str(e),
                    "data": safe_data,
                    "metadata": {},
                }
                try:
                    serialized = json.dumps(safe, ensure_ascii=False, indent=2, default=str)
                except Exception:
                    serialized = '{"error": "serialization failed completely"}'
        filepath.write_text(serialized, encoding="utf-8")
        return str(filepath)
