"""utils 模块单元测试 — numpy_to_native + reset_client"""
import json
import pytest
import numpy as np
from utils import numpy_to_native


class TestNumpyToNative:
    """验证 numpy_to_native 的 6 种类型转换 + 边界条件"""

    def test_numpy_int64(self):
        result = numpy_to_native(np.int64(42))
        assert result == 42
        assert isinstance(result, int)

    def test_numpy_float64(self):
        result = numpy_to_native(np.float64(3.14))
        assert result == 3.14
        assert isinstance(result, float)

    def test_numpy_float64_nan(self):
        """NaN 应转为 None（JSON 兼容）"""
        result = numpy_to_native(np.float64("nan"))
        assert result is None

    def test_numpy_bool(self):
        result = numpy_to_native(np.bool_(True))
        assert result is True
        assert isinstance(result, bool)

    def test_numpy_array(self):
        """ndarray 应转为 list"""
        arr = np.array([1, 2, 3])
        result = numpy_to_native(arr)
        assert result == [1, 2, 3]

    def test_nested_dict(self):
        """嵌套 dict 中的 numpy 值应递归转换"""
        obj = {"a": np.int64(1), "b": {"c": np.float64(2.0)}}
        result = numpy_to_native(obj)
        assert result["a"] == 1
        assert result["b"]["c"] == 2.0
        assert isinstance(result["a"], int)
        assert isinstance(result["b"]["c"], float)

    def test_list_of_dicts(self):
        """list[dict] 中的 numpy 值应递归转换"""
        obj = [{"x": np.int64(10)}, {"x": np.int64(20)}]
        result = numpy_to_native(obj)
        assert result[0]["x"] == 10
        assert result[1]["x"] == 20

    def test_round_trip_json(self):
        """转换后的结果应可被 json.dumps 序列化"""
        obj = {"a": np.int64(1), "b": np.float64(2.5), "c": np.bool_(True)}
        native = numpy_to_native(obj)
        json_str = json.dumps(native)
        parsed = json.loads(json_str)
        assert parsed["a"] == 1
        assert parsed["b"] == 2.5
        assert parsed["c"] is True

    def test_python_native_passthrough(self):
        """普通 Python 类型应原样返回"""
        obj = {"a": 1, "b": "hello", "c": [1, 2, 3], "d": None}
        result = numpy_to_native(obj)
        assert result == obj

    def test_tuple_to_list(self):
        """tuple 应转为 list（JSON 兼容）"""
        result = numpy_to_native((1, 2, 3))
        assert result == [1, 2, 3]

    def test_ndarray_2d(self):
        """二维 ndarray 应转为嵌套 list"""
        arr = np.array([[1, 2], [3, 4]])
        result = numpy_to_native(arr)
        assert result == [[1, 2], [3, 4]]


class TestResetClient:
    """验证 reset_client 的线程安全缓存重建"""

    def test_reset_does_not_crash(self):
        """reset_client 应不抛异常，且重建后的客户端可正常获取"""
        from utils.llm_client import reset_client, _get_client
        reset_client()
        c1 = _get_client()
        reset_client()
        c2 = _get_client()
        assert c1 is not None
        assert c2 is not None

    def test_reset_clears_cache(self):
        """reset_client 后 _get_client 应重新创建实例"""
        from utils.llm_client import reset_client, _get_client
        reset_client()
        c1 = _get_client()
        reset_client()
        c2 = _get_client()
        # 两次 reset 后的客户端实例应不同（内存地址不同）
        assert c1 is not c2

    def test_reset_consecutive_no_error(self):
        """连续多次 reset 不应报错"""
        from utils.llm_client import reset_client
        for _ in range(5):
            reset_client()
        # 如果能执行到这里，说明没有异常
        assert True