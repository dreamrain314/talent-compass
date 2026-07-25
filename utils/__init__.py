"""工具函数导出模块

包含 LLM 客户端、日志工具、数据转换工具。
"""
import numpy as np
from .llm_client import call_llm, call_llm_json, reset_client
from .logger import setup_logger, generate_trace_id


def numpy_to_native(obj):
    """递归将 numpy 数值类型转换为 Python 原生类型，确保 json.dumps 安全。

    使用场景：BasicFilter.apply() 返回 df.to_dict(orient="records")
    后，PipelineRunner 对返回值做 json.dumps 序列化。numpy.int64 等
    类型无法被 json 库序列化，必须预先转换。

    Args:
        obj: 任意嵌套结构（dict/list/scalar），可能包含 numpy 数值。

    Returns:
        结构相同但所有 numpy 数值已转为 Python int/float 的副本。
    """
    if isinstance(obj, dict):
        return {k: numpy_to_native(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [numpy_to_native(v) for v in obj]
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        if np.isnan(obj):
            return None
        return float(obj)
    if isinstance(obj, np.ndarray):
        return numpy_to_native(obj.tolist())
    if isinstance(obj, np.bool_):
        return bool(obj)
    return obj


__all__ = [
    "call_llm", "call_llm_json", "reset_client",
    "setup_logger", "generate_trace_id",
    "numpy_to_native",
]
