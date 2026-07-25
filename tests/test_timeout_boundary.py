"""超时机制边界验证测试 —— 验证 Pipeline 超时不会被线程卡死阻塞

这些测试直接验证 Bug #1 的修复：
- 修复前: timeout=2s 但实际耗时 10s（被 shutdown(wait=True) 阻塞）
- 修复后: timeout=2s 且实际耗时 ~2s（shutdown(wait=False) 不阻塞）

Windows 兼容性说明：
- socket.connect("198.51.100.1") 在 Windows 上立即返回（不阻塞）
- 因此改用 UDP socket.recvfrom() 做每轮阻塞（_HangingAgent，检查 cancel_event）
- 用本地 TCP server 做纯阻塞（_PureBlockingAgent，不检查 cancel_event）
"""
import time
import socket
import threading
import contextlib
import pytest
from agents.base_agent import BaseAgent
from orchestrator.pipeline import PipelineRunner


class _HangingAgent(BaseAgent):
    """模拟卡死的 Agent（如 LLM 网络超时）

    使用 UDP socket.recvfrom(timeout=0.1) 做每轮阻塞 I/O，
    每轮后检查 cancel_event 实现优雅取消。
    UDP socket 无需连接，recvfrom 在没有数据到达时阻塞到超时。
    """
    agent_name = "HangingAgent"
    agent_version = "0.1.0"

    def __init__(self, sleep_seconds: float = 10.0):
        self.sleep_seconds = sleep_seconds

    def validate_input(self, data: dict) -> bool:
        return True

    def execute(self, data: dict, context: dict) -> dict:
        """
        使用 UDP socket.recvfrom(timeout=0.1) 做每轮阻塞 I/O。
        D5 要求：阻塞 I/O 而非 time.sleep —— 真实 LLM 卡死时不检查 cancel flag。
        对于 _HangingAgent（会检查 cancel_event），此方法模拟可优雅取消的卡死。
        """
        cancel = context.get("cancel_event")
        # 创建 UDP socket 用于每轮阻塞，复用避免反复创建
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.1)
        try:
            for _ in range(int(self.sleep_seconds * 10)):
                if cancel and cancel.is_set():
                    return {
                        "status": "error",
                        "data": {"cancelled": True},
                        "metadata": {},
                    }
                # recvfrom 阻塞 0.1s —— 跨平台 UDP I/O 阻塞
                try:
                    s.recvfrom(1024)
                except socket.timeout:
                    pass
        finally:
            s.close()
        return {"status": "success", "data": {"result": "done"}, "metadata": {}}

    def get_input_schema(self) -> dict:
        return {"type": "object"}

    def get_output_schema(self) -> dict:
        return {"type": "object"}


@contextlib.contextmanager
def _blocking_tcp_server():
    """启动一个本地 TCP 服务器，接受连接但不发送数据。

    客户端连接后调用 recv() 将永久阻塞（因为服务器从不调用 send）。
    客户端 socket.settimeout 控制最大阻塞时间。
    port=0 让 OS 分配空闲端口，避免冲突。
    """
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("127.0.0.1", 0))  # port=0 → OS 分配
    server.listen(5)
    server_port = server.getsockname()[1]

    # 持有引用防止连接被 GC 回收
    accepted_connections = []

    def _accept():
        try:
            conn, addr = server.accept()
            accepted_connections.append(conn)  # 保持引用，防止 close
            # 接受连接后不 send —— 客户端 recv 永久阻塞
        except OSError:
            pass

    t = threading.Thread(target=_accept, daemon=True)
    t.start()

    # server.listen() 是同步的，此时已处于 listen 状态
    # accept() 在 daemon 线程中，无需额外等待

    try:
        yield server_port
    finally:
        for c in accepted_connections:
            try:
                c.close()
            except OSError:
                pass
        try:
            server.close()
        except OSError:
            pass


class _PureBlockingAgent(BaseAgent):
    """纯阻塞 Agent —— 不检查 cancel_event，模拟真实 LLM 线程卡死场景

    连接到本地 TCP 服务器后调用 recv()，在内核层被永久阻塞，
    无法响应 cancel_event。此 Agent 验证硬超时机制是否真正有效。
    """
    agent_name = "PureBlockingAgent"
    agent_version = "0.1.0"

    def __init__(self, block_seconds: float = 10.0, server_port: int = 18999):
        self.block_seconds = block_seconds
        self.server_port = server_port

    def validate_input(self, data: dict) -> bool:
        return True

    def execute(self, data: dict, context: dict) -> dict:
        # 纯阻塞 I/O，绝不检查 cancel_event
        # 连接本地 TCP 服务器后调用 recv() —— 内核层真正阻塞
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(self.block_seconds)
        try:
            s.connect(("127.0.0.1", self.server_port))
            # recv 阻塞 —— 服务器接受但不发送数据
            s.recv(1024)
        except (socket.timeout, OSError):
            pass
        finally:
            s.close()
        return {"status": "success", "data": {"result": "done"}, "metadata": {}}

    def get_input_schema(self) -> dict:
        return {"type": "object"}

    def get_output_schema(self) -> dict:
        return {"type": "object"}


class TestTimeoutBoundary:
    """超时边界验证 — 确保超时机制不会永久阻塞 Pipeline

    Bug #9 修复后，Timer 在 timeout-5 秒时提前设置 cancel_event。
    对于短超时（<=5s），延迟 clamp 为至少 1s，Agent 检测到取消后优雅退出。
    """

    def test_timer_cancels_agent_before_hard_timeout(self, tmp_path):
        """核心测试：Timer 提前通知 → Agent 检测 cancel_event → 优雅退出

        用 timeout=2s + sleep_seconds=10s：Timer 在 1s 时触发，
        Agent 应在 ~1s 内检测到并返回 cancelled，不会等到硬超时。
        """
        agent = _HangingAgent(sleep_seconds=10.0)
        runner = PipelineRunner([], output_dir=str(tmp_path))

        t0 = time.perf_counter()
        result = runner._execute_with_timeout(
            agent,
            data={"input": "test"},
            context={"trace_id": "timeout-test-001", "timeout_seconds": 2},
            timeout=2,
        )
        elapsed = time.perf_counter() - t0

        # Timer 提前通知 → Agent 返回 cancelled，不进入 TimeoutError 分支
        assert result["data"].get("cancelled") is True, (
            f"Agent should have been cancelled by Timer, got: {result}"
        )
        # 应在 Timer 触发时间（1s）+ Agent 检测延迟（<1s）内完成
        assert elapsed < 4.0, (
            f"Timer cancel FAILED: elapsed={elapsed:.1f}s, expected < 4s. "
            f"Agent should be cancelled by Timer, not by hard timeout."
        )

    def test_cancel_event_propagates_to_agent(self, tmp_path):
        """测试 cancel_event 确实传递给了 Agent 并被检测到"""
        agent = _HangingAgent(sleep_seconds=5.0)
        runner = PipelineRunner([], output_dir=str(tmp_path))

        t0 = time.perf_counter()
        result = runner._execute_with_timeout(
            agent,
            data={"input": "test"},
            context={"trace_id": "cancel-test-001"},
            timeout=2,
        )
        elapsed = time.perf_counter() - t0

        # Timer 在 max(1, 2-5)=1s 时触发，Agent 应在 ~1s 左右检测到
        assert result["data"].get("cancelled") is True, (
            f"cancel_event was NOT detected by agent: {result}"
        )
        assert elapsed < 3.0, (
            f"Cancel propagation too slow: {elapsed:.1f}s"
        )

    def test_pipeline_with_timeout_continues(self, tmp_path):
        """测试 Pipeline 在 Agent 被取消后仍能继续执行下游 Agent

        核心验证：即使上游 Agent 被 cancel_event 取消，
        下游 Agent 可以继续执行，Pipeline 不会被阻塞。
        """
        # 会检测到 cancel_event 并优雅取消的 Agent
        slow_agent = _HangingAgent(sleep_seconds=2.0)
        slow_agent.agent_name = "Slowpoke"

        class FastAgent(BaseAgent):
            agent_name = "Fast"
            agent_version = "0.1.0"
            def validate_input(self, data): return True
            def execute(self, data, context):
                return {"status": "success", "data": {"value": 42}, "metadata": {}}
            def get_input_schema(self): return {}
            def get_output_schema(self): return {}

        runner = PipelineRunner([], output_dir=str(tmp_path))

        # timeout=3: Timer fires at max(1,3-5)=1s,
        # future.result(timeout=3) 给 3s 窗口，Timer 在 1s 通知，Agent 在 ~1.1s 取消
        t0 = time.perf_counter()
        cancelled_result = runner._execute_with_timeout(
            slow_agent,
            data={"value": 1},
            context={"trace_id": "pipe-timeout-test"},
            timeout=3,
        )
        elapsed = time.perf_counter() - t0

        # Agent 被 Timer 取消
        assert cancelled_result["data"].get("cancelled") is True, (
            f"Agent not cancelled. data={cancelled_result['data']}"
        )
        assert elapsed < 3.0, (
            f"Timer blocked: {elapsed:.1f}s, expected < 3s"
        )

        # 验证取消后 FastAgent 仍能正常执行（Pipeline 未卡死）
        fast_agent = FastAgent()
        t1 = time.perf_counter()
        ok_result = runner._execute_with_timeout(
            fast_agent,
            data={"value": 1},
            context={"trace_id": "pipe-timeout-test-2"},
            timeout=5,
        )
        elapsed_fast = time.perf_counter() - t1

        assert ok_result["status"] == "success"
        assert ok_result["data"]["value"] == 42
        assert elapsed_fast < 2.0, (
            f"FastAgent blocked after cancel: {elapsed_fast:.1f}s"
        )

    def test_hard_timeout_with_real_blocking(self, tmp_path):
        """验证硬超时对纯阻塞 I/O 真正生效（不依赖 cancel_event）

        使用 _PureBlockingAgent（完全不检查 cancel_event 的真正阻塞 I/O），
        连接到本地 TCP 服务器后 recv() 永久阻塞。
        验证 Pipeline 硬超时机制在超时后返回 degraded 状态。
        """
        with _blocking_tcp_server() as server_port:
            agent = _PureBlockingAgent(block_seconds=3.0, server_port=server_port)
            runner = PipelineRunner([], output_dir=str(tmp_path))

            t0 = time.perf_counter()
            result = runner._execute_with_timeout(
                agent,
                data={"input": "test"},
                context={"trace_id": "hard-timeout-test"},
                timeout=2,
            )
            elapsed = time.perf_counter() - t0

            # 硬超时：Agent 不检查 cancel_event，超时后返回 degraded
            assert result["status"] == "degraded", (
                f"Hard timeout should return degraded for pure blocking agent. "
                f"Got status={result['status']}, data={result.get('data')}"
            )
            # 确保不是 cancelled（Agent 根本不检查 cancel_event）
            assert result["data"].get("cancelled") is not True, (
                f"Should NOT be cancelled (agent doesn't check cancel_event). "
                f"Got data={result['data']}"
            )
            # 单次 future.result(timeout=2) → 耗时约 2s，容忍到 6s
            assert elapsed < 6.0, (
                f"Hard timeout took too long: {elapsed:.1f}s"
            )