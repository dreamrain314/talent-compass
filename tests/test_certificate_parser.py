"""tests/test_certificate_parser.py — parse_certificates 单元测试。

覆盖（C4 边界穷举 + V7 残缺输入）：
- 正常分隔（半角/全角分号逗号）
- 哨兵过滤（实测 45/100 为 "无"）
- 混合哨兵+合法值
- None / 空串 / 纯空格
- 多分隔符连缀
- 全角空格
"""

from utils.certificate_parser import parse_certificates


class TestParseCertificatesBasic:
    """基本分隔符。"""

    def test_half_width_comma(self):
        assert parse_certificates("PMP,系统架构设计师") == ["PMP", "系统架构设计师"]

    def test_half_width_semicolon(self):
        assert parse_certificates("PMP;CPA") == ["PMP", "CPA"]

    def test_full_width_semicolon(self):
        # 中文输入法误录入（用户确认兼容）
        assert parse_certificates("PMP；系统架构设计师") == ["PMP", "系统架构设计师"]

    def test_full_width_comma(self):
        assert parse_certificates("PMP，系统架构设计师") == ["PMP", "系统架构设计师"]

    def test_multi_separator_chinese(self):
        # 实测数据典型：信息系统项目管理师;电气工程师
        assert parse_certificates("信息系统项目管理师;电气工程师") == [
            "信息系统项目管理师",
            "电气工程师",
        ]


class TestParseCertificatesSentinels:
    """哨兵过滤（实测 45/100 为 "无"）。"""

    def test_none(self):
        assert parse_certificates(None) == []

    def test_empty(self):
        assert parse_certificates("") == []

    def test_whitespace_only(self):
        assert parse_certificates("   ") == []

    def test_full_width_whitespace(self):
        # 全角空格 strip 覆盖
        assert parse_certificates("　") == []

    def test_wu(self):
        # 🔴 实测数据最常见值
        assert parse_certificates("无") == []

    def test_wu_with_spaces(self):
        assert parse_certificates("  无  ") == []

    def test_wu_full_width_spaces(self):
        assert parse_certificates("　无　") == []

    def test_none_en(self):
        assert parse_certificates("none") == []

    def test_null(self):
        assert parse_certificates("null") == []

    def test_dash(self):
        assert parse_certificates("-") == []

    def test_slash(self):
        assert parse_certificates("/") == []

    def test_wu_cert(self):
        assert parse_certificates("无证书") == []

    def test_wu_period(self):
        assert parse_certificates("无。") == []


class TestParseCertificatesMixed:
    """混合哨兵+合法值。"""

    def test_wu_then_pmp(self):
        # 哨兵被滤掉，PMP 保留
        assert parse_certificates("无;PMP") == ["PMP"]

    def test_pmp_then_wu(self):
        assert parse_certificates("PMP;无") == ["PMP"]

    def test_all_sentinels(self):
        assert parse_certificates("无,无,无") == []

    def test_mixed_sentinels_and_valid(self):
        assert parse_certificates("无;-;PMP;/;CPA") == ["PMP", "CPA"]


class TestParseCertificatesEdgeCases:
    """边界（C4 穷举）。"""

    def test_consecutive_separators(self):
        # 多分隔符连缀产生空段，被过滤
        assert parse_certificates("PMP;;,系统架构") == ["PMP", "系统架构"]

    def test_consecutive_full_width(self):
        assert parse_certificates("PMP；；，系统架构") == ["PMP", "系统架构"]

    def test_leading_trailing_separator(self):
        assert parse_certificates(";PMP;") == ["PMP"]

    def test_single_valid(self):
        assert parse_certificates("PMP") == ["PMP"]

    def test_single_valid_with_spaces(self):
        assert parse_certificates("  PMP  ") == ["PMP"]

    def test_empty_segments_with_valid(self):
        assert parse_certificates("；；PMP；；") == ["PMP"]

    def test_return_type_is_list(self):
        result = parse_certificates("PMP;CPA")
        assert isinstance(result, list)
        assert all(isinstance(x, str) for x in result)

    def test_empty_return_type_is_list(self):
        result = parse_certificates("无")
        assert isinstance(result, list)
        assert result == []


class TestParseCertificatesNonStr:
    """非 str 输入守卫（C3：跨边界值不崩）。"""

    def test_int_zero(self):
        assert parse_certificates(0) == []  # type: ignore[arg-type]

    def test_int_nonzero(self):
        # truthy int 不应在 .strip() 崩
        assert parse_certificates(123) == []  # type: ignore[arg-type]

    def test_float(self):
        assert parse_certificates(1.5) == []  # type: ignore[arg-type]

    def test_list(self):
        assert parse_certificates(["PMP"]) == []  # type: ignore[arg-type]

    def test_dict(self):
        assert parse_certificates({"a": 1}) == []  # type: ignore[arg-type]
