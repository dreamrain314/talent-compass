"""BasicFilter — 纯 Pandas 确定性过滤引擎

非 AI 组件，不继承 BaseAgent。由 PipelineRunner 或 Streamlit UI 直接调用。

用法:
    filter = BasicFilter(employees_df, performance_df)
    result = filter.apply({"age_range": [30, 45], "political_status": ["中共党员"]})
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from config import PERFORMANCE_FULL_YEARS, PERFORMANCE_ORDINAL
from utils import numpy_to_native


# ── 工具函数 ──────────────────────────────────────────────────────────────
# 🔴 D2 单一来源：numpy_to_native 由 utils/__init__.py 提供，禁止在此处独立定义。
#    本地版本曾用 hasattr(obj, "dtype") 兜底，在多元素 ndarray 上调用 .item()
#    会崩溃；utils 版本通过 isinstance(obj, np.ndarray) → obj.tolist() 正确处理。
#    参见 utils/__init__.py 第 10-37 行。


# ── 主类 ──────────────────────────────────────────────────────────────────
class BasicFilter:
    """Pandas 过滤引擎，基于条件字典逐层叠加过滤员工数据集。

    Attributes:
        employees_df: 员工主表 DataFrame（13 字段）
        performance_df: 绩效表 DataFrame（employee_id / year / performance_grade / comment）
        _hire_years: {employee_id: hire_year} 预计算映射
    """

    # 支持的 conditions key → 对应私有方法
    _SUPPORTED_KEYS = frozenset({
        "age_range",
        "political_status",
        "major_keywords",
        "min_years_of_service",
        "level_range",
        "min_performance",
    })

    def __init__(self, employees_df: pd.DataFrame, performance_df: pd.DataFrame) -> None:
        """初始化 filter。

        Args:
            employees_df: 员工主表（含 employee_id / hire_date / years_of_service 等）
            performance_df: 绩效表（含 employee_id / year / performance_grade）
        """
        self.employees_df = employees_df.copy()
        self.performance_df = performance_df.copy()

        # 预计算员工入职年份映射 {employee_id: hire_year}
        self._hire_years: dict[str, int] = {}
        for _, row in self.employees_df.iterrows():
            hire_date = row.get("hire_date", "")
            try:
                self._hire_years[row["employee_id"]] = int(str(hire_date)[:4])
            except (ValueError, TypeError):
                self._hire_years[row["employee_id"]] = 9999  # 无法解析 → 视为新员工

    # ── 公共接口 ────────────────────────────────────────────────────────────

    def apply(self, conditions: dict) -> dict:
        """应用过滤条件，返回过滤结果。

        Args:
            conditions: 过滤条件字典，key 为条件名，value 为参数。
                        支持的 key 见 _SUPPORTED_KEYS。
                        不支持的 key 被追加到 skipped_conditions。

        Returns:
            {
                "filtered_employees": [...],   # 过滤后的员工列表（Python 原生类型）
                "filter_log": [...],            # 每步过滤日志
                "skipped_conditions": [...],    # 不支持的条件名称列表
                "total_before": int,            # 过滤前总人数
                "total_after": int              # 过滤后总人数
            }
        """
        if not isinstance(conditions, dict):
            return {
                "filtered_employees": [],
                "filter_log": [],
                "skipped_conditions": [],
                "total_before": 0,
                "total_after": 0,
                "error": f"conditions must be a dict, got {type(conditions).__name__}",
            }

        skipped: list[str] = []
        filter_log: list[dict] = []
        df = self.employees_df.copy()

        total_before = len(df)

        for key, value in conditions.items():
            if key not in self._SUPPORTED_KEYS:
                skipped.append(key)
                continue

            # 值为 None 或非法类型 → 跳过该条件
            if value is None:
                skipped.append(key)
                continue

            before_count = len(df)

            try:
                if key == "age_range":
                    df = self._apply_age_range(df, value)
                elif key == "political_status":
                    df = self._apply_political_status(df, value)
                elif key == "major_keywords":
                    df = self._apply_major_keywords(df, value)
                elif key == "min_years_of_service":
                    df = self._apply_min_years(df, value)
                elif key == "level_range":
                    df = self._apply_level_range(df, value)
                elif key == "min_performance":
                    df, extra = self._apply_min_performance(df, value)
                    filter_log.append({
                        "condition": key,
                        "before_count": before_count,
                        "after_count": len(df),
                        "removed_count": before_count - len(df),
                        **extra,
                    })
                    continue
            except (ValueError, TypeError, KeyError) as exc:
                # 条件抛异常（如 level_range 畸形值）→ 标记 skipped 不中断
                skipped.append(key)
                continue

            after_count = len(df)
            filter_log.append({
                "condition": key,
                "before_count": before_count,
                "after_count": after_count,
                "removed_count": before_count - after_count,
            })

        total_after = len(df)

        # 全部被过滤 → 追加提示
        if total_after == 0 and filter_log:
            filter_log[-1]["note"] = "建议放宽条件"

        # 递归转换 numpy 类型（D2 单一来源：使用 utils.numpy_to_native）
        filtered_employees = numpy_to_native(df.to_dict(orient="records"))

        return {
            "filtered_employees": filtered_employees,
            "filter_log": filter_log,
            "skipped_conditions": skipped,
            "total_before": total_before,
            "total_after": total_after,
            "error": None,
        }

    # ── 私有过滤方法 ────────────────────────────────────────────────────────

    def _apply_age_range(self, df: pd.DataFrame, value: Any) -> pd.DataFrame:
        """按年龄区间 [min, max] 过滤。

        - min=0 → 不过滤下限
        - max=999 → 不过滤上限
        - 非列表/非法值 → 原样返回
        """
        if not isinstance(value, (list, tuple)) or len(value) != 2:
            return df
        try:
            min_age, max_age = int(value[0]), int(value[1])
        except (ValueError, TypeError):
            return df
        return df[df["age"].between(min_age, max_age)]

    def _apply_political_status(self, df: pd.DataFrame, value: Any) -> pd.DataFrame:
        """按政治面貌列表过滤。

        - 空列表 → 不过滤
        - 非列表 → 原样返回
        """
        if not isinstance(value, (list, tuple)):
            return df
        if len(value) == 0:
            return df
        return df[df["political_status"].isin(value)]

    def _apply_major_keywords(self, df: pd.DataFrame, value: Any) -> pd.DataFrame:
        """按专业关键词 OR 匹配过滤。

        - 空列表 → 不过滤
        - 非列表 → 原样返回
        - regex=False 防止特殊字符被解释为正则
        - na=False 防止 NaN 抛异常
        """
        if not isinstance(value, (list, tuple)):
            return df
        if len(value) == 0:
            return df
        mask = pd.Series(False, index=df.index)
        for kw in value:
            if not isinstance(kw, str):
                continue
            mask |= df["major"].str.contains(kw, na=False, regex=False)
        return df[mask]

    def _apply_min_years(self, df: pd.DataFrame, value: Any) -> pd.DataFrame:
        """按最低工龄过滤。

        - 非数值 → 原样返回
        - 0 → 全通过
        """
        try:
            min_years = int(value)
        except (ValueError, TypeError):
            return df
        return df[df["years_of_service"] >= min_years]

    def _apply_level_range(self, df: pd.DataFrame, value: Any) -> pd.DataFrame:
        """按职级区间 [min, max] 数值比较过滤。

        - 字符串比较 "P10" < "P5" 为 True → 必须用 int(level[1:])
        - 畸形值（如 ""）→ 抛 ValueError → 由调用方捕获并标记 skipped
        """
        if not isinstance(value, (list, tuple)) or len(value) != 2:
            return df
        try:
            min_str, max_str = str(value[0]), str(value[1])
            min_num = int(min_str.lstrip("Pp"))
            max_num = int(max_str.lstrip("Pp"))
        except (ValueError, TypeError):
            raise ValueError(f"level_range 含畸形值: {value}")

        df = df.copy()
        df["_level_num"] = df["current_level"].str.lstrip("Pp").astype(int)
        result = df[df["_level_num"].between(min_num, max_num)]
        result = result.drop(columns=["_level_num"])
        return result

    def _apply_min_performance(self, df: pd.DataFrame, value: Any) -> tuple[pd.DataFrame, dict]:
        """按绩效底线过滤。

        检查最近完整年度（2024/2025）的绩效：
        - 入职前的年度跳过
        - 某一年绩效低于底线 → 排除
        - 新员工无完整年度数据 → insufficient_data 标记，不排除

        Returns:
            (filtered_df, extra_log_dict)
        """
        try:
            min_grade = str(value).strip().upper()
        except (ValueError, TypeError):
            return df, {}

        min_ordinal = PERFORMANCE_ORDINAL.get(min_grade, 0)
        if min_ordinal == 0:
            return df, {}

        # 只取完整年度
        full_year_perf = self.performance_df[
            self.performance_df["year"].isin(PERFORMANCE_FULL_YEARS)
        ]

        exclude_ids: set[str] = set()
        insufficient_data = 0

        for emp_id in df["employee_id"]:
            emp_perf = full_year_perf[full_year_perf["employee_id"] == emp_id]
            if emp_perf.empty:
                insufficient_data += 1
                continue

            hire_year = self._hire_years.get(emp_id, 9999)
            below_threshold = False
            for _, row in emp_perf.iterrows():
                year = int(row["year"])
                if year < hire_year:
                    continue  # 入职前的年度跳过
                grade = str(row["performance_grade"]).strip().upper()
                if PERFORMANCE_ORDINAL.get(grade, 0) < min_ordinal:
                    below_threshold = True
                    break

            if below_threshold:
                exclude_ids.add(emp_id)

        result = df[~df["employee_id"].isin(exclude_ids)]
        extra: dict = {}
        if insufficient_data > 0:
            extra["insufficient_data"] = insufficient_data
        return result, extra