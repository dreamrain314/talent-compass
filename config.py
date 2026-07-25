"""Talent Compass 全局配置

读取 .env 环境变量，导出 API Key、Base URL 和项目路径常量。
"""
import os
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

# 项目根目录
PROJECT_ROOT = Path(__file__).resolve().parent

# 加载 .env 文件
_env_path = PROJECT_ROOT / ".env"
if not _env_path.exists():
    import sys
    print(
        f"\n⚠ [config] 未找到 .env 文件: {_env_path}\n"
        f"  请复制 .env.template（若存在）或手动创建 .env 并填入 API Key。\n"
        f"  无 API Key 时所有 LLM 调用将失败。\n",
        file=sys.stderr,
    )
load_dotenv(_env_path)

# ── DeepSeek API ────────────────────────────────────────────
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
# 代码默认值为官方 API 基线；生产/代理场景通过 .env 覆盖。
#   官方 API → model="deepseek-chat"（兼容所有官方模型）
#   帕德拉代理 → model="DeepSeek-V4-Pro"/"DeepSeek-V4-Flash"（需与 .env 中 BASE_URL 配套）
# 模型槽位分配参见 CLAUDE.md 配置表。
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

# ── 运行时一致性警告 ─────────────────────────────────────────
# 🔴 修复：自定义 BASE_URL 但未在 .env 设置模型名 → 模型名与代理不匹配
_warned_model = False
_default_urls = {"https://api.deepseek.com", "https://api.deepseek.com/v1"}
_is_non_default_base = DEEPSEEK_BASE_URL not in _default_urls
_is_default_model = os.getenv("DEEPSEEK_MODEL") is None
if _is_non_default_base and _is_default_model and not _warned_model:
    import sys as _sys
    _warned_model = True
    print(
        "\n⚠ [config] DEEPSEEK_BASE_URL 已自定义但 DEEPSEEK_MODEL 未在 .env 中设置。\n"
        f"   当前模型回退默认值: \"{DEEPSEEK_MODEL}\"\n"
        "   如果代理/私有部署需要特定模型名，请在 .env 中增加 DEEPSEEK_MODEL=你的模型名\n"
        "   否则可能遇到 model_not_found 错误。\n",
        file=_sys.stderr,
    )

# 二次警告：.env 存在但 Key 为空
if not DEEPSEEK_API_KEY:
    import sys
    print(
        "\n⚠ [config] DEEPSEEK_API_KEY 为空。LLM 调用将在认证阶段失败。\n"
        "  请在 .env 中设置 DEEPSEEK_API_KEY=你的密钥\n",
        file=sys.stderr,
    )

# ── Qwen API（审计用，Demo 阶段可选）─────────────────────────
QWEN_API_KEY = os.getenv("QWEN_API_KEY", "")
QWEN_BASE_URL = os.getenv("QWEN_BASE_URL", "")
QWEN_MODEL = os.getenv("QWEN_MODEL", "qwen-max")

# ── 超时常量（单一来源，参见 CLAUDE.md D2）────────────────────
LLM_API_TIMEOUT = 60.0  # LLM API 调用超时（秒）
AGENT_EXEC_TIMEOUT = 120  # 单个 Agent 执行超时（秒）
# Agent① 数据理解 Agent 超时（100 人 × ~3.5s/人 ≈ 350s + 余量）
AGENT_DATAUNDERSTANDING_TIMEOUT = 600

# ── 绩效等级序数映射（用于 BasicFilter.min_performance 数值比较）───
# 🔴 Day 2 关键：绩效等级 A>B>C>D 语义上优于，但 Python 字符串比较
#    "A"<"B" 为 True（ASCII 序），必须用序数映射避免反向筛选。
#    消费者：filter/basic_filter.py（Day 2 Task 2.1）—— 禁止在此文件外重复定义。
PERFORMANCE_ORDINAL = {"A": 4, "B": 3, "C": 2, "D": 1}

# ── 绩效检查的完整年度范围 ──────────────────────────────────────
# 🔴 仅包含"当前年份-2"和"当前年份-1"（不包含当前不完整年度）
# 消费者：filter/basic_filter.py 的 min_performance 逻辑（Day 2.1）
# 禁止在其他文件中重新定义此值（参见 CLAUDE.md D2 单一来源原则）
PERFORMANCE_FULL_YEARS = [datetime.now().year - 2, datetime.now().year - 1]

# ── Agent 配置常量 ────────────────────────────────────────────
# Agent① 360 异常检测：评价者样本量低于此值 → 跳过该评价者的异常检测
# （域级 σ 计算在 <15 个数据点上不可靠，参见统计方法样本量遗漏根因）
EVALUATOR_MIN_SAMPLE_SIZE = 15

# ── 路径常量 ─────────────────────────────────────────────────
DATA_DIR = PROJECT_ROOT / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
INTERMEDIATE_DIR = DATA_DIR / "intermediate"
LOG_DIR = PROJECT_ROOT / "logs"
# 🔴 修复：原 "config" 与 config.py 模块名冲突 → 改为 pipeline_config
PIPELINE_CONFIG_DIR = PROJECT_ROOT / "pipeline_config"

# ── 目录创建已移至 main.py（避免 import 时因磁盘满/无权限崩溃）──
