"""证书字段解析器。

从 employees.csv 的 certificates 字段解析证书列表。

来源约束（C3: 外部值先守卫）：
- 实测 data/raw/employees.csv certificates 字段 45/100 为 "无"（哨兵），
  10/100 用半角分号分隔，0/100 用逗号。
- 仍兼容中文分号/逗号（中文输入法误录入鲁棒性，D4 假阳列举）。

消费者：agents/profile_generation.py 构造 h1_credentials（见 docs/plan-profile-agent-schema.md）。
"""

from __future__ import annotations

import re

__all__ = ["parse_certificates"]


# 哨兵集：表示「无证书」的值，全部过滤（C3/C4）。
# 实测数据仅出现 "无"，其余为防御性扩展（未来数据源可能用其他表达）。
_CERTIFICATE_SENTINELS = {"无", "none", "无证书", "-", "/", "无。", "null"}

# 分隔符正则：半角/全角分号与逗号（用户确认兼容中文输入法误录入）。
_SPLIT_RE = re.compile(r"[;；,，]")


def parse_certificates(cert_str: str | None) -> list[str]:
    """解析 certificates 字符串为证书列表。

    - None / 空串 / 纯空格 → 空列表
    - 半角或全角分号/逗号分隔
    - 哨兵值（"无" / "none" / "-" / "/" 等）过滤
    - 每项 strip 去空格（含全角空格），去空串

    Args:
        cert_str: certificates 字段原始值，可能为 None / "无" / "PMP;系统架构设计师"

    Returns:
        证书名列表，如 ["PMP", "系统架构设计师"]；无证书时返回 []。

    返回格式对称（C1）：所有路径返回 list[str]，空即 []。
    """
    # C3 守卫：跨边界值（CSV / LLM / 反序列化）可能传入非 str。
    # None / int / float / list 等 → 空列表，不在 .strip() 崩。
    if not isinstance(cert_str, str):
        return []
    if not cert_str.strip():
        return []

    parts = _SPLIT_RE.split(cert_str)
    out: list[str] = []
    for p in parts:
        c = p.strip()
        if not c:
            continue
        if c.lower() in _CERTIFICATE_SENTINELS:
            continue
        out.append(c)
    return out
