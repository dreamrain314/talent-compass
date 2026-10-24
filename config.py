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

# GLM-5.3 系（智谱网关）思考强度档位。GLM-5.3 始终思考、thinking.type 仅支持
# enabled（关不掉），档位走独立顶层字段 reasoning_effort（low/high/max，网关默认
# max）。默认 max 会把 max_tokens 预算 ~99% 耗在 reasoning_tokens 上（2026-09-10
# 实测 8129/8192、content=0、finish_reason=length），长 JSON 抽取全部截断。
# 空串=不发送该参数（DeepSeek 官方/Paratera 网关行为不变）。
# 消费者：utils/llm_client.call_llm（extra_body 注入）。文档：
# docs.bigmodel.cn/cn/guide/models/text/glm-5.3
LLM_REASONING_EFFORT = os.getenv("TC_LLM_REASONING_EFFORT", "").strip().lower()

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
LLM_API_TIMEOUT = 30.0  # LLM API 调用超时（秒）— Agent① 串行 100 次调用，偏小防卡住
AGENT_EXEC_TIMEOUT = 120  # 单个 Agent 执行超时（秒）
# Agent① 数据理解 Agent 超时（100 人 × ~5s/人 + 0.5s sleep + 360 预处理 ≈ 600s + 余量）
AGENT_DATAUNDERSTANDING_TIMEOUT = 900

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

# ── 360 评价预处理常量（D1: 单一来源，替代 data_understanding.py 内联常量）──
ROLE_WEIGHTS_BASELINE = {"上级": 0.47, "同事": 0.26, "下属": 0.13, "HR": 0.14}
SELF_EVAL_ROLE = "自评"
KNOWN_360_DIMENSIONS = {"专业能力", "沟通协作", "领导力", "责任心", "学习能力"}
ANOMALY_SIGMA_THRESHOLD = 2
ANOMALY_PENALTY_FACTOR = 0.2
TIME_DECAY_RATE = 0.3
DISCRIMINATION_PERFUNCTORY_WEIGHT = 0.1
DISCRIMINATION_POSITIVE_THRESHOLD = 4
CONFIDENCE_EVALUATOR_BASELINE = 5
CONFIDENCE_YEAR_COVERAGE = {3: 1.0, 2: 0.85, 1: 0.7}

# ── 环境变量真值集合（LOW-2 消重 2026-09-10：is_offline_mode 与 _env_flag 共用单一来源）──
_TRUTHY = ("1", "true", "yes", "on")

# ── 离线模式（不调用真实 LLM，用确定性占位符）──────────────────
# TC_OFFLINE=1 时，summarize_employee_texts 跳过 API，从原文截前 N 字
# 派生摘要与锚点。用于：① 无 API Key 时跑通 pipeline 验证编排逻辑
# ② 真实 API 截断/限流时绕过雪崩。运行时读 env（非 import 冻结），
# 支持 CLI flag 注入。消费者：utils/llm_summarizer.py
def is_offline_mode() -> bool:
    """运行时读取 TC_OFFLINE 环境变量判断是否启用离线模式。"""
    return os.getenv("TC_OFFLINE", "").strip().lower() in _TRUTHY


# ── 占位符摘要派生常量（offline + degraded 共用，单一来源 D1）──
PLACEHOLDER_SUMMARY_LEN = 150  # 摘要截取原文前 N 字
PLACEHOLDER_ANCHOR_LEN = 10    # 锚点截取原文前 N 字

# ── 目录创建已移至 main.py（避免 import 时因磁盘满/无权限崩溃）──

# ── Embedding ────────────────────────────────────────────────
EMBEDDING_MODEL_NAME = "BAAI/bge-small-zh-v1.5"
EMBEDDING_BACKEND = "fastembed"       # fastembed（ONNX）或 sentence-transformers
EMBEDDING_MIN_SIM = 0.50              # 绝对下限：低于此值 → 纠正或 pending
EMBEDDING_MARGIN = 0.12               # top1-top2 最小差值
EMBEDDING_CONFIDENCE_PENALTY = 0.15   # 纠正路径的置信度扣减
EMBEDDING_CACHE_SIZE = 4096           # LRU 缓存容量

# ── SFIA ─────────────────────────────────────────────────────
SFIA_MAX_LEVEL = 7                    # SFIA 0-7
SFIA_CAP_EXCESS = 2                   # SFIA_diff 上限 cap+2

# ── 标签置信度 ────────────────────────────────────────────────
LABEL_CONFIDENCE_THRESHOLD = 0.6      # 低于此值 → labels_pending_review
LABEL_LIBRARY_VERSION = "1.0"         # 当前标签库版本
LABEL_LIBRARY_PATH = DATA_DIR / "standard_label_library_v1.json"
# T0 显性条件注册表（工具/行业领域/知识体系），供 Agent② load_label_corpus 合并
# Day 2（2026-07-28）：扩展 corpus 覆盖 tool/domain/knowledge category
T0_REGISTRIES_PATH = DATA_DIR / "t0_registries.json"

# ── ability_score 范围（Schema §7，T1/T2 标签能力评分，整数尺度）──
ABILITY_SCORE_MIN = 0
ABILITY_SCORE_MAX = 100

# ── 能力等级双框架（双层三通道方案 §2.3，Step 1.2）──────────────
# IT 类 T1 标签用 SFIA（0-7）→ ability_score = sfia_level × (100/7)
# 非 IT 类 T1 标签用通用能力等级（1-5：新手/基础/熟练/资深/专家）→ ability_score = (level-1) × 25
# T2 沿用 SFIA（0-7）。T3 不挂等级。
# D2 单一来源：IT 标签集合在此定义，映射函数在 utils/label_embedding.ability_score_from_level
GENERAL_ABILITY_MAX_LEVEL = 5            # 通用能力等级 1-5
GENERAL_ABILITY_LEVELS = ["新手", "基础", "熟练", "资深", "专家"]  # 等级 1-5 对应名
# IT 类 T1 标签名集合（用 SFIA 0-7）；其余 T1 标签走通用能力等级 1-5
# 口径：SFIA 是 Information Age 信息技术框架，仅覆盖软件/数据/算法/数字嵌入式/网络安全。
# 机械/光学/模具/工艺/制造/硬件电路/通信/系统工程/研发管理等工程虽带技术成分但非 SFIA 范畴 → 走通用能力。
# 标签名须与 data/standard_label_library_v1.json T1 项严格一致（防幽灵标签）。
IT_T1_TAG_NAMES = frozenset({
    # 软件开发/测试
    "Java开发", "Python开发", "前端开发", "Android开发", "全栈开发", "软件测试",
    # 算法/数据
    "算法工程", "AI算法", "数据分析", "数据工程",
    # 数字嵌入式
    "嵌入式开发", "FPGA开发",
    # 网络安全/运维
    "网络安全", "运维工程",
})

# ── T3 代理指标 ────────────────────────────────────────────────
# ⚠ 预校准默认值，需在 Day 2 实验（5 员工对比）后用真实数据调整
T3_PROXY_WEIGHTS = {
    "learning_speed": 0.25, "career_diversity": 0.25,
    "growth_orientation": 0.25, "growth_signals_360": 0.25,
}
T3_CONFIDENCE_BASELINE = 0.7
T3_CONFIDENCE_DEGRADED = 0.3
T3_LEARNING_SPEED_SCALE = 50          # 原 300 → 预校准：1 项活动/年 ≈ 50 分
T3_CAREER_DIVERSITY_SCALE = 15        # 原 20 → 预校准：7 角色触顶
T3_GROWTH_EVIDENCE_SCALE = 8          # 原 15 → 预校准
T3_TRAINING_SCALE = 5                 # 原 10 → 预校准
T3_FEEDBACK_SCALE = 12                # 原 25 → 预校准

# ── 大五人格 ──────────────────────────────────────────────────
BIG_FIVE_DIMENSIONS = [
    "openness", "conscientiousness", "extraversion",
    "agreeableness", "neuroticism",
]
# 大五 ↔ T3 标签交叉验证映射（T3 标签名 → 大五维度）
# 仅验证对比用，不参与评分权重
BIG_FIVE_LABEL_MAP = {
    "开放性": "openness",
    "尽责性": "conscientiousness",
}

# ── 成长曲线 ──────────────────────────────────────────────────
GROWTH_CURVE_MIN_POINTS = 2          # 线性回归最少数据点数，不足时 trend="insufficient_data"
# 绩效等级 → 数值映射（与 PERFORMANCE_ORDINAL 保持同步，D2 单一来源）
PERFORMANCE_GRADE_SCORE = {"S": 100, "A": 90, "B": 75, "C": 60, "D": 45}

# ── Agent② 超时（50 人 × (5s LLM + 1s overhead) / W=5 + 余量 ≈ 80s）──
AGENT_PROFILE_TIMEOUT = 120
# Agent② Step F 汇总 LLM 单次调用超时：输入含全员标签，比单员工 LLM_API_TIMEOUT=30 长。
# 消费者：utils/llm_client.call_llm_json(timeout=SUMMARY_LLM_TIMEOUT)（per-call 覆盖）
SUMMARY_LLM_TIMEOUT = 60
# Agent② _llm_extract 单员工 LLM 调用超时：输出结构化 JSON（T1/T2 数组 × evidence），
# 比 Agent① summary 输出重（summary 仅 3 段文本 ~600 tokens，_llm_extract 多标签 + 锚点 ~1500+ tokens 生成）。
# LLM_API_TIMEOUT=30 实测对 _llm_extract 偏紧（Paratera 代理按 token 计延迟，长 JSON 生成超 30s）。
# 消费者：agents/profile_generation._llm_extract → call_llm_json(timeout=PROFILE_EXTRACT_LLM_TIMEOUT)
# Day 3 注意：per-employee 90s × 50 员工 / W=5 = 900s，需配合调高 AGENT_PROFILE_TIMEOUT 或 W
PROFILE_EXTRACT_LLM_TIMEOUT = 90
# Agent② _llm_extract 单次 LLM 最大输出 token。
# DeepSeek-V4-Pro 是推理模型，thinking tokens 计入 max_tokens；4096 实测被推理
# 吃光致 finish_reason=length → 空内容 → 触发 call_llm_json short-prompt 重试
# （截断 prompt 丢 JSON schema）→ 假性"成功"返回空标签数组。8192 给 thinking+JSON 留够。
# 消费者：agents/profile_generation._llm_extract → call_llm_json(max_tokens=PROFILE_EXTRACT_MAX_TOKENS)
PROFILE_EXTRACT_MAX_TOKENS = 8192

# ── 三阶段标签匹配（Stage 2 召回 + Stage 3 LLM 重排）──
# 架构反转：旧 verify_mapping 让 embedding 自动纠正 LLM（5 害 1 助，净负 4）；
# 新设计 embedding 只召回 top-K 候选，LLM 从候选里拍板或判新标签。
# 消费者：utils/label_matching.recall_top_k / rerank_label_llm；
#         agents/profile_generation.execute Phase 1 串联。
LABEL_RECALL_TOP_K = 20                     # Stage 2 embedding 召回候选数（corpus 94 项，k=20 覆盖足够候选，原 3 太低致 GT 常不在候选内）
LABEL_RERANK_MAX_TOKENS = 2048              # Stage 3 重排 JSON 小，2048 充裕
LABEL_RERANK_TIMEOUT = 180                  # Stage 3 重排比抽取轻（qwen3:14b 本地冷启动 ~50s，设 180 安全）
LABEL_RERANK_CONFIDENCE_THRESHOLD = 0.7     # 低于此 → pending_review 人工复核
LABEL_NEW_LABEL_MAX_PER_EMP = 2             # 新标签防滥上限（超限降级选 top1）

# ── Stage 3 cross-encoder 精排（Step 8c，替换 zero-shot LLM 重排）──
# 文献依据：BLINK/BGE 90%+ 靠 fine-tuned cross-encoder 联合编码 (query, doc) pair，
#   精度远高于 bi-encoder 召回 + zero-shot LLM。BGE-Reranker-v2-m3 多语言含中文。
# 消费者：utils/label_matching.rerank_cross_encoder。
# 降级：加载失败 → rerank_label_llm（zero-shot LLM fallback，D6 确定性降级不重试）。
RERANKER_MODEL_NAME = "BAAI/bge-reranker-v2-m3"        # cross-encoder 多语言
# 本地模型路径（git clone 下载，优先于 HF hub 下载，省网络）。
# 存在才启用（可移植性：云端/他人机器无此目录 → None → 走 HF hub 下载同名模型，
# 需 HF_ENDPOINT=hf-mirror 或可访问 hf.co）；非 None 但不存在会静默降级纯 bi 分。
RERANKER_LOCAL_PATH = (
    "D:/workplace/bge-reranker-v2-m3"
    if Path("D:/workplace/bge-reranker-v2-m3").exists() else None
)
RERANKER_FALLBACK_TO_LLM = True                        # 加载/推理失败 → zero-shot LLM
RERANKER_NEW_LABEL_THRESHOLD = 0.15                    # top1 score < 此 → is_new_label（Step 1.10：0.3→0.15，BGE 对中文抽象词打分偏低，0.15-0.3 区间应收为 pending_review 而非判新标签）
RERANKER_CONFIDENCE_THRESHOLD = 0.5                    # score < 此且 ≥ new 阈值 → pending_review

# ── 向量直配匹配层（upgrade/vector-matching M1-M3，竞品思路迁移）──
# 固定公式评分（零 LLM 评分）：总分 = T0 直接技能 50 + T1 语义匹配 30
#   + T2 行为 10 + T3 潜力 10（百分制）。权重和不必校验为 100：缺失层
#   发中性分（该层权重×0.5），公式确定性优先。
# 消费者：utils/match_engine.py / agents/matching.py / scripts/blind_test.py
MATCH_FORMULA_WEIGHTS = {
    "t0_direct": 50.0,     # T0 直接技能：证书/培训/工具/岗位的字面+别名命中
    "t1_semantic": 30.0,   # T1 语义：bi-encoder 召回 + cross-encoder 校准
    "t2_behavior": 10.0,   # T2 行为：360 五维映射
    "t3_potential": 10.0,  # T3 潜力：绩效轨迹 + 培训 + 360 学习能力（确定性代理）
}
# 置信三档（总分/100）：低于 REJECT → 驳回；REJECT-REVIEW → 待审（=备选池）；≥REVIEW → 自动推荐
# 标定依据（2026-10-21 V2a 基线 = T0 密度 D2 + 解析降噪，反事实模拟采纳）：
#   实测全员总分 P50=0.285 / P80=0.354 / max=0.529；金标带 0.426-0.502。
#   REJECT 对齐新 P80（相关性低于全员前 20% → 驳回）；
#   REVIEW = 金标带下沿 0.426 减 2 分余量 → 0.40（5 金标全部 ≥REVIEW+2 分：
#   实际余量 2.6/2.2/2.6/2.8/10.2 分）。历史：V0 期曾为 0.32/0.45。
# ⚠ 泄漏声明（2026-10-21，docs/eval_log.md）：本阈值与金标 holdout 联合拟合，
#   「金标 ≥ 推荐线」验收是自洽性检查而非独立效度验证；对负例的排斥力
#   待 GT batch2 复核后验证。batch2 复核前本阈值冻结不得改动。
MATCH_REJECT_THRESHOLD = 0.35
MATCH_REVIEW_THRESHOLD = 0.40
MATCH_TOP_K = 5                    # Top-N 推荐
MATCH_RERANK_TOPN = 10             # bi 初排总分前 N 进 cross-encoder 校准（成本分层）
MATCH_SEMANTIC_FLOOR = 0.30        # T1 语义原始 sim 低于此视为噪声归 0（防低分填充）
MATCH_RERANK_BLEND = 0.5           # T1 语义最终 = bi-encoder×(1-b) + cross-encoder 校准×b
EVIDENCE_CHUNK_MAX_CHARS = 600     # 单证据切片上限（超长截断，防摘要超长稀释向量）
# 备选池：H 闸门未过但 T1 语义归一分 ≥ 此值的候选进备选池而非直接驳回（原设计四象限）
MATCH_POOL_SEMANTIC_MIN = 0.60

# ── T0 密度分（V2a 新基线，2026-10-21 反事实模拟采纳，报告 docs/reports/counterfactual_sim_20261021.md）──
# 判定依据：模拟显示密度 D2 使 min_margin -4.81→-3.58、金标排名 [2,2,1,5,1]→[1,2,1,3,1]（全部 Top-3）；
# 权重再平衡被否决（B03 恶化 6.05→2.38）。
# D2 公式：term 命中 r 条去重记录 → 得分 base + bonus·min(r-1, cap)/cap（单记录碰词 0.6，≥3 条多源印证 1.0）
T0_DENSITY_ENABLED = os.getenv("TC_T0_BINARY", "").strip().lower() not in _TRUTHY  # TC_T0_BINARY=1 回退二值版（A/B 用）
T0_DENSITY_BASE = 0.6
T0_DENSITY_BONUS = 0.4
T0_DENSITY_CAP_RECORDS = 2
# JD 侧受控别名表（每对来自金标 miss 归因；扩充须逐对过盲测——回归驱动打补丁）
T0_ALIAS_PATCHES_PATH = DATA_DIR / "jobs" / "alias_patches.json"

# ── Round 3 要求—证据对齐引擎（docs/preregister_round3_evidence_alignment_20261022.md
#    §二/§七 已封存 2026-10-22；参数为「减少同时变动因素」的暂定值，Day 8 冻结定版）──
COVERAGE_RECALL_K = 3            # §七-3 用户确认：每要求×每员工候选证据上限 k≤3
# 必须项类内等权（原案 Demo 期等权兜底）；优先项不进加权求和、走加分制（见下）
COVERAGE_W_MUST = 1.0
# 人工核验等价表（§2.3 等价表达唯一入口；不存在/无条目 → 相关改写如实报未证实）
COVERAGE_EQUIVALENCE_PATH = DATA_DIR / "jobs" / "equivalence_table.json"
# 等价表 deduct 条目的计分值（用户 D组 #10 决议：受众错位映射「酌情减分」按 0.8 计）
COVERAGE_DEDUCTION_VALUE = 0.8
# ── 两类能力划分（用户 2026-10-24 五决议；预注册修订见 eval_log §十八；
#    结构来源=开题报告《五层匹配评分体系细化方案_2026-07-24.md》§2.8 四类职业矩阵）──
# total = [ W1·S_prof + W2·S_behav + W3·P ]×100 + bonus；闸门：专业必须未成立→total×GATE
# 矩阵键匹配 JD 的 job_type 字段；未识别用 _default（业务运营档，三类最均衡）
COVERAGE_JOB_WEIGHT_MATRIX = {
    "技术类": (70.0, 15.0, 15.0),   # Ⅰ 技术研发：技术深度核心
    "职能类": (40.0, 30.0, 30.0),   # Ⅲ 管理领导：潜力至关重要（管理职能类映射此档）
    "业务类": (45.0, 35.0, 20.0),   # Ⅱ 业务运营：行为沟通几乎与专业同等重要
    "创意类": (45.0, 20.0, 35.0),   # Ⅳ 创意创新：潜力和学习速度决定未来产出
    "_default": (45.0, 35.0, 20.0),
}
# 优先项加分制（原案 §2.6）：bonus = k×Σ(优先项v)/max(1,N_must)，不进加权、不满足不扣分
COVERAGE_PREFERRED_K = 2.0
# 专业类必须项缺 k 项 → total ×(1-0.05k)（用户 2026-10-25 指令：线性递减，封 0）
COVERAGE_GATE_STEP = 0.05
# 负向证据标记（2026-10-21 batch2/gt5 复核类1「只证做过、未证达标」）：含任一标记的
# 记录不得作为 T0 直接技能命中依据（「做砸了」≠「会做」）。当前 _T0_SOURCES 本就
# 不含 performance/summary，此护栏防未来 sources 扩展时负向证据混入（用户指令）。
T0_NEGATIVE_MARKERS = ["延迟", "返工", "不稳定", "事故", "质量差", "失误", "整改", "绩效有改进空间"]
# 展示层金标锚定映射（Phase D）：分段线性 [raw, display]，锚点来自 V2a 实测分布
# （硬负例带顶 ~52.9、金标带 42.6-50.2，见 docs/reports/blind_test_report_20261021.md）。
# 语义：驳回区（<35）不变形；待审区拉伸到 35-75；金标带 42.6-50.2 → 75-85；上限 98。
# 只进展示层，API 原始分保留（Kimi 修订版：固定公式下绝对分值无意义，margin 和闸门才有）。
MATCH_DISPLAY_ANCHORS = [[0, 0], [35, 35], [42.6, 75], [50.2, 85], [100, 98]]

# ── T1 recall 优化（plan: S1/S8b/B3/S2/S3，2026-09）──
def _env_flag(name, default="0"):  # [MED-3 修复 2026-09-10] 默认关（opt-in）：默认开会破坏 A/B baseline 纪律与测试隔离
    return os.getenv(name, default).strip().lower() in _TRUTHY  # _TRUTHY 提炼为模块级共享常量，与 is_offline_mode 复用（LOW-2，实施时顺手消重）

# S1：cross-encoder 低分项（SOURCE_CROSS_NEW_LABEL / SOURCE_CROSS_PENDING）送 LLM 终裁
# 消费者：utils/label_matching.rerank_cross_encoder（A/B 开关：TC_LLM_ADJUDICATION）
RERANKER_LLM_ADJUDICATION = _env_flag("TC_LLM_ADJUDICATION")
# B3：soft 类（behavior/potential）新标签阈值分轨；hard 轨沿用 RERANKER_NEW_LABEL_THRESHOLD=0.15
# 消费者：utils/label_matching.rerank_cross_encoder（A/B 开关：TC_SOFT_TRACK）
RERANKER_SOFT_CATEGORIES = frozenset({"behavior", "potential"})
RERANKER_NEW_LABEL_THRESHOLD_SOFT = 0.05
RERANKER_SOFT_TRACK = _env_flag("TC_SOFT_TRACK")
# S8b：抽取后间接映射扩展（近邻阈值 / 每源近邻数 / 每员工上限）
# 消费者：agents/profile_generation._expand_indirect_labels（A/B 开关：TC_EXPAND）
EXPAND_NEIGHBOR_SIM = 0.75
EXPAND_TOP_N = 2
EXPAND_MAX_PER_EMP = 2
EXPAND_ENABLED = _env_flag("TC_EXPAND")
# S2：T1 抽取数量下限（prompt 文案 + 低于下限记 stats，不触发二次 LLM）与 few-shot kNN 选取数
# 消费者：agents/profile_generation._build_system_prompt / _process_employee / _select_few_shot_examples
T1_EXTRACT_MIN_COUNT = 5
FEWSHOT_KNN_K = 2
# S2 总开关（TC_S2_PROMPT，默认关——S2 判负处置 2026-09-11，B3）：四件套整体门控
# （kNN few-shot + T1 数量下限文案 + 逐字段自查 + 证书证据价值文案）。
# 关 = 抽取行为回到序1（pre-S2）形态：静态 5 条种子 few-shot、无 kNN、无 S2 约束文案；
# t1_below_min stats 记录不受此开关影响（常开，stats-only 不影响抽取行为）。
# 消费者：agents/profile_generation._select_few_shot_examples / _build_system_prompt
S2_PROMPT_ENABLED = _env_flag("TC_S2_PROMPT")
# S3：多遍抽取并集（预算门控：>1 需用户确认；A/B 开关：TC_EXTRACT_PASSES）
# 消费者：agents/profile_generation._multi_pass_extract / execute 超时预算联动
EXTRACT_PASSES = int(os.getenv("TC_EXTRACT_PASSES", "1"))
EXTRACT_UNION_TEMPERATURE = 0.7  # ADU 温度实验：适中温度换多样性，高温单次质量崩
