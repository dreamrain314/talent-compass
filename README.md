# 🧭 Talent Compass

> AI 驱动的动态胜任力画像与智能人岗匹配系统
> 竞赛：AI 先锋人才竞赛（AI 赋能产业升级赛道）

---

## 项目简介

Talent Compass 是一个基于多 Agent 协作的智能人岗匹配系统。它从多源员工数据（基础信息、绩效、项目、培训、360 评价）出发，通过**基础过滤层 → 数据理解 Agent → 画像生成 Agent → 岗位分析 Agent → 匹配解释 Agent → 质量审计 Agent** 的流水线，生成动态胜任力画像并推荐最适合岗位的候选人。

---

## 系统架构

```
九洲多源数据 → 数据接入层 → 基础过滤层 → [Agent 流水线] → 匹配推荐输出
                                    ↑                  ↑
                              运营监控看板 ← 质量审计 Agent ←┘
```

### Agent 流水线（开发进度）

| Agent | 职责 | 状态 |
|-------|------|------|
| 🟢 **Agent① 数据理解** | 读取多源数据 → 清洗 → LLM 摘要 → 360 加权 → 融合 JSON | ✅ 完成 |
| ⏳ **Agent② 画像生成** | T0/T1/T2/T3 标签抽取 → 标准标签映射 → 画像输出 | 📅 第 2 周 |
| ⏳ **Agent③ 岗位分析** | JD 解析 → 层间/层内权重 → 岗位画像 | 📅 第 3 周 |
| ⏳ **Agent④ 匹配解释** | 五层加权匹配 → 证据链 → BEI 追问 → 反事实解释 | 📅 第 3 周 |
| ⏳ **Agent⑤ 质量审计** | 输入校验 → 输出校验 → 360 异常评价者复检 | 📅 第 3-4 周 |

---

## 环境要求

- Python 3.10+
- 依赖：`pip install -r requirements.txt`
- API Key：DeepSeek（必需），Qwen（可选，审计用）

---

## 快速开始

```bash
# 1. 克隆项目
cd talent-compass

# 2. 安装依赖
pip install -r requirements.txt

# 3. 配置 API Key
# 编辑 .env 文件，填入 DeepSeek API Key
# DEEPSEEK_API_KEY=sk-your-key-here

# 4. 生成模拟数据（100 名员工，6 种数据源）
python data/generate_mock_data.py

# 5. 启动 Streamlit 界面
streamlit run main.py

# 6. （可选）运行第一阶段流水线
python scripts/run_pipeline_phase1.py --skip-filter
```

---

## 第一阶段功能清单

### ✅ 已完成

| 模块 | 功能 | 测试数 |
|------|------|--------|
| 编排器框架 | BaseAgent 基类 + PipelineRunner + 超时控制 + 中间件持久化 | 13 |
| 模拟数据集 | 100 员工 × 4 岗位序列 × 5 数据源（含隐形高潜 + 异常评价者） | — |
| 基础过滤层 | 6 种 Pandas 筛选条件（年龄/政治面貌/专业/工龄/职级/绩效） | 41 |
| Agent① 数据理解 | 文件读取 → 缺失检测 → LLM 摘要 → 360 预处理 → 融合输出 | 32+39 |
| LLM 摘要模块 | 绩效/项目/360 文本摘要 + 锚点验证 + 幻觉检测 + 离线占位符 | 21 |
| 数据质量检测 | 缺失值/类型/范围/文本不足检测 | 28 |
| 360 评价预处理 | 偏差校准 + 时间衰减 + 角色权重 + 区分度检测 + 置信度 | 5 |
| 标准标签库种子 | 35 标签（T1 专业能力 13 / T2 行为能力 13 / T3 发展潜力 9） | — |
| T0 初始词典 | 60 条目（工具 35 + 行业领域 12 + 知识体系 13），含别名/分类 | — |
| Streamlit 界面 | 8 步骤化 UI（上传/过滤/质量/摘要/360/画像/匹配/推荐） | 5 |
| 命令行流水线 | `scripts/run_pipeline_phase1.py`（过滤 + Agent① 串联，支持 --offline） | — |

### 📅 规划中

| 阶段 | 时间 | 目标 |
|------|------|------|
| 第 2 周 | 07.28-08.03 | Agent② 画像生成（核心难点） |
| 第 3 周 | 08.04-08.10 | Agent③④⑤ + 全流程联调 |
| 第 4 周 | 08.11-08.16 | 集成测试 + 文档 + 提交 |

---

## 关键文件索引

| 文件 | 说明 |
|------|------|
| `main.py` | Streamlit 入口 |
| `config.py` | 全局配置（路径/超时/模型名） |
| `agents/base_agent.py` | Agent 基类契约 |
| `agents/data_understanding.py` | Agent① 数据理解 |
| `orchestrator/pipeline.py` | 编排器核心 |
| `filter/basic_filter.py` | 基础过滤引擎 |
| `ui/app.py` | Streamlit 界面 |
| `utils/llm_client.py` | LLM API 封装 |
| `utils/llm_summarizer.py` | LLM 摘要模块 |
| `utils/data_quality.py` | 数据质量检测 |
| `scripts/run_pipeline_phase1.py` | 第一阶段流水线脚本 |
| `scripts/generate_mock_data.py` | 模拟数据生成 |
| `pipeline_config/filter_conditions.json` | 默认过滤条件 |
| `data/raw/` | 原始模拟数据 |
| `data/intermediate/` | 流水线中间结果 |
| `docs/task-plan.md` | 完整任务计划 |
| `docs/change-log.md` | 变更日志 |

---

## 运行验证

```bash
# 全量测试
python -m pytest tests/ -v

# 第一阶段端到端验证（跳过过滤，直达 Agent①）
python scripts/run_pipeline_phase1.py --skip-filter

# 使用默认过滤条件
python scripts/run_pipeline_phase1.py
```

---

*详情请参阅 `docs/task-plan.md`（任务规划）和 `docs/change-log.md`（变更记录）。*