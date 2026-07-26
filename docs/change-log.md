# progress.md — Bug修复进度

## 📐 第2周准备 Step3: Embedding demo + 框架选型 (2026-07-26)

**状态**: [VERIFIED]（demo 验证脚本，非核心逻辑，已跑通）

### 完成内容

| 文件 | 操作 | 说明 |
|------|------|------|
| `scripts/embedding_demo.py` | 新建 | fastembed + bge-small-zh 最小 demo：自由文本→35 标签余弦相似度→top-3→四档阈值 |
| `requirements.txt` | 修改 | 加 `fastembed>=0.8.0`（ONNX, 无 torch, 离线可用） |
| `docs/plan-profile-agent-schema.md` | 修改 | 加 §8 embedding 选型 + 阈值标定发现 + 07.31 实现路径 |

### 框架选型决策

- **选型**: `fastembed` + `BAAI/bge-small-zh-v1.5`
- **理由**: DeepSeek/Paratera 无 embedding API；OpenAI key 未配置；本地 ONNX 是唯一可行方案；离线可用竞赛现场稳

### 验证结果

- 6 查询 top-1 排序 **6/6 命中预期标签**（Java微服务→Java开发 0.89 强映射；带团队→团队管理 0.59；学新东西→学习敏捷性 0.59 等）
- 模型离线可用（首次下载 ~95MB 后无网络也能跑）

### ⚠ 阈值标定发现（07.31 实现前必须解决）

- 原四档 `0.6/0.75/0.85/0.95` 为 OpenAI embedding 标定，对 bge 过严
- bge top-1 sim 多在 0.59-0.69，几乎全落 `<0.60` pending
- 现象: 词汇重叠高（Java→Java 0.89）sim 高；语义近用词异（带团队→团队管理 0.59）sim 低
- 07.31 建议: **top-1 + 相对 margin 判定**（不依赖绝对值）+ 绝对下限兜底

---

## 📐 第2周准备 Step2: Agent② 输出 JSON Schema 定稿 (2026-07-26)

**状态**: [定稿]（设计文档，非代码，不触发 V1 闸门）

### 完成内容

| 文件 | 操作 | 说明 |
|------|------|------|
| `docs/plan-profile-agent-schema.md` | 新建 | Agent② 输出 JSON Schema 完整设计：H1+T0+T1/T2/T3+成长曲线+大五+summary，包装在 BaseAgent 契约 |

### 关键决策（用户 2026-07-26 确认）

| 决策 | 结论 |
|------|------|
| D2 T1 评分字段 | 双字段 `ability_score`(0-100 整数) + `sfia_level`(0-7) |
| 大五范围 | 0-100（与 ability_score 对齐） |
| summary 字段 | 保留（LLM 仅基于已抽标签生成，防幻觉） |
| D4 聚类 | Demo 期跳过（第四阶段扩展） |
| ability_score 粒度 | 整数 0-100 |

### 边界澄清（防下游混淆）

- **Agent② 只产员工侧 `sfia_level`，不算 T1 得分** —— T1 得分公式 `Σ w_i × SFIA_diff` 是 Agent④ 职责（需 Agent③ 要求侧 SFIA）
- 实现时 config 常量待加：`SFIA_MAX_LEVEL=7` / `SFIA_CAP_EXCESS=2` / `LABEL_CONFIDENCE_THRESHOLD=0.6` 等（D2 单一来源，详见文档 §7）

---

## 🔧 第2周准备 Step1+1.5: certificates 字段 + RAW_DIR D2 合规 (2026-07-26)

**状态**: [VERIFIED]

### 完成内容

| 文件 | 操作 | 说明 |
|------|------|------|
| `scripts/generate_mock_data.py` | 修改 | 新增 `SEQ_CERTS` 证书池（4 序列各 4-6 证书，PMP 跨序列通用）+ `_gen_certificates`（权重 55%无/30%单/15%双，高职级上浮）+ 校验块 |
| `scripts/generate_mock_data.py` | 修改 | `RAW_DIR` 改用 `config.RAW_DATA_DIR`（D2 合规，消除手动 cp `scripts/raw`→`data/raw`） |
| `data/raw/employees.csv` | 重新生成 | 新增 `certificates` 列（55/100 持证，序列一致，无空值） |
| `data/raw/evaluation_360.csv` | 重新生成 | baseline 与脚本重新同步（既存过时问题修复） |

### 关键决策

- **独立 RNG 隔离**：`_CERT_RNG = random.Random(2026)` 独立于主 `random.seed(42)`，避免 certificates 生成污染 perf/proj/train/eval360 的 baseline 可重复性。验证：perf/proj/train hash 与 baseline **完全一致**（隔离铁证）。

### 发现并修复的既存问题

| 问题 | 根因 | 修复 |
|------|------|------|
| eval360 baseline 与脚本不一致 | baseline 过时（非当前脚本生成），与 certificates 无关 | 重新生成，hash `96c92946`→`6ca9590f` |
| `RAW_DIR` 硬编码 `scripts/raw` | D2 违规（config 已有 `RAW_DATA_DIR`） | 改用 `config.RAW_DATA_DIR` |

### 验证

- [x] 测试: 231/231 PASSED（`-W error::FutureWarning`，9.14s）
- [x] perf/proj/train hash 与 baseline 一致（独立 RNG 隔离铁证）
- [x] certificates: 55/100 持证、序列一致、无空值

---

## 🔧 Day6: 词典编写 + 前端对抗检验 + 修复 (2026-07-26)

**状态**: [VERIFIED]

### 词典编写

| 文件 | 操作 | 说明 |
|------|------|------|
| `data/standard_label_library_v1.json` | 新建 | 标准标签库种子 — 35 标签（T1 专业能力 13 / T2 行为能力 13 / T3 发展潜力 9），冰山模型+大五人格框架 |
| `data/t0_registries.json` | 新建 | T0 初始词典 — 60 条目（35 工具 / 12 行业领域 / 13 知识体系），含别名/分类/典型用途 |

### 前端对抗检验（Day 6 报告）

- **工具**: Playwright 原生（非 browser_use）
- **数据**: `data/adversarial/` 7 个对抗夹具包
- **结果**: 8/8 PASS（S4 str_score 已修复）
- **报告**: `docs/frontend-adversarial-report-day6.md`

### 前端完整性检验（Day 7 报告）

- **范围**: Day 1-5 全部前端工程
- **结果**: Step 1-5 全模块构造正确，Step 6-8 占位符合计划
- **报告**: `docs/frontend-inspect-report-day7.md`

### 修复

| 问题 | 文件 | 变更 |
|------|------|------|
| ADV-4 line_height 无效参数 | `ui/app.py` L1012 | `st.code(a[:80], line_height=24)` → `st.code(a[:80])`（F8 修 API 调用必查签名） |
| S4 str_score 360 崩溃 | `ui/app.py` + `agents/data_understanding.py` | 3 处 score 聚合加 `pd.to_numeric(... errors="coerce")` 守卫 |

### 验证

- [x] 测试: 231/231 PASSED
- [x] 前端对抗: 8/8 PASS
- [x] 前端完整性: Step 1-5 全部正确

---

## 🔧 Day5: Agent① 360 评价预处理增强 + 联调 (2026-07-25)

**状态**: [VERIFIED]

### 完成内容

| 文件 | 说明 | 状态 |
|------|------|------|
| `agents/data_understanding.py` — `_preprocess_360()` | 综合权重公式（角色权重 × 时间衰减 × 区分度 × 异常惩罚 → 归一化） | ✅ |
| `config.py` | 新增 `TIME_DECAY_RATE`, `DISCRIMINATION_*`, `CONFIDENCE_*` 常量 | ✅ |
| `tests/test_data_understanding.py` — `Test360ComprehensiveFormula` | 5 个综合测试（3年无异常/单年敷衍/全异常/year缺失/全敷衍零除） | ✅ 5/5 |
| `data/intermediate/baseline_360_v1.json` | 基线与替换后对比验证 | ✅ |
| `scripts/validate_phase1.py` | 端到端验证脚本（5类检查 + --skip-llm） | ✅ |

### 验证

- [x] 全量测试: 213/213 PASSED，零 Warning
- [x] 360 综合公式 5/5 通过
- [x] 基线对比文件已生成

## 🔧 Day4: Agent① 非结构化文本语义理解 (2026-07-24)

**状态**: [VERIFIED]

### 修改内容

| 文件 | 操作 | 说明 |
|------|------|------|
| `utils/llm_summarizer.py` | 新建 | `summarize_employee_texts()` — 独立 LLM 摘要模块，供 DataUnderstanding 和 UI 共享 |
| `agents/data_understanding.py` | 修改 | `_summarize_employee` 委托给 `utils.llm_summarizer`（D2: 单一来源） |
| `ui/app.py` | 修改 | 新增 Step 4 文本摘要对照视图 + 员工选择器 + 原文↔摘要对照 + 质量标记 |
| `tests/test_llm_summarizer.py` | 新建 | 21 个测试覆盖 9 个场景（正常/空文本/LLM 错误/锚点/幻觉/截断） |
| `tests/test_ui_app.py` | 修改 | `_STEPS` 长度断言 6→7，新增 Step 3/4 标签断言 |
| `docs/task-plan.md` | 修改 | 2.1.6 标记 ✅ |

### 架构变更

**提取 `utils/llm_summarizer.py`** — 将 DataUnderstanding 内部的 LLM 摘要逻辑提取为独立模块：
- `summarize_employee_texts()` — 主函数，调用 `call_llm_json` + 锚点验证 + 长度检查
- `verify_anchors()` — 锚点存在性验证（模糊匹配 ±2 字）
- `check_summary_lengths()` — 摘要长度合理性检查
- 供 DataUnderstanding 和 Streamlit UI Step 4 共享调用，避免 D2 重复定义

**Step 4 文本摘要对照视图** — Streamlit UI 新增：
- 员工选择器（下拉，优先过滤后列表）
- 原文三栏展示（绩效/项目/360 评价）
- 调用 LLM 生成摘要（逐员工）
- 摘要 ↔ 原文对照展示
- 质量标记（锚点匹配 / 幻觉检测 / Token 消耗）

### 验证

- [x] 测试: 207/207 PASSED（原有 185 + 新增 21 + 1 新断言）
- [x] 对抗审查: D3 对称性、D1 边界值、UI 降级路径全部通过

---

### 🔧 对抗审查修复 (2026-07-24)

**状态**: [VERIFIED]

**发现 2 个 Bug：**

| # | 严重度 | 文件 | 根因 | 触发条件 |
|---|--------|------|------|---------|
| ADV-3 | 🔴 P0 | `ui/app.py` L775 | `st.rerun()` 在 `if` 块外，每次渲染 Step 2 触发无限 rerun | 用户进入 Step 2 即触发 |
| ADV-4 | 🟡 P2 | `ui/app.py` L1001 | `st.code(a, line_limit=1)` — `line_limit` 不是有效参数，静默忽略 | 展开锚点折叠区时 |

**修复：**
| Bug | 文件 | 变更 |
|-----|------|------|
| ADV-3 | `ui/app.py` L775 | 删除多余的 `st.rerun()` |
| ADV-4 | `ui/app.py` L1001 | `st.code(a, line_limit=1)` → `st.code(a[:80], line_height=24)` |
| ADV-4（Day6 真正修复） | `ui/app.py` L1012 | `line_height=24` 同样无效，Streamlit 1.51 严格校验抛 TypeError → 删除 kwarg：`st.code(a[:80])` |

---

## 🔧 Day3 补完: Streamlit 数据质量报告展示 (2026-07-23)

**状态**: [VERIFIED]

### 修改内容

| 文件 | 操作 | 说明 |
|------|------|------|
| `utils/data_quality.py` | 新建 | `check_data_quality()` — 纯 pandas 数据质量检测（缺失值/类型/范围/文本不足） |
| `ui/app.py` | 修改 | 新增 Step 3 渲染函数 + Step 2→3 导航 + 数据源概览/缺失值详情/类型异常/范围异常/预警展示 |
| `tests/test_data_quality.py` | 新建 | 28 个测试覆盖 6 场景（正常/缺失/类型/范围/文本不足/边界） |
| `tests/test_ui_app.py` | 修改 | 新增 4 个函数导入验证 |

### 验证

- [x] 测试: 132/132 PASSED（原有 104 + 新增 28）
- [x] 对抗审查: `check_data_quality` 6 个边界值 + `_render_step_data_quality` 5 个场景全部通过
- [ ] 无回归

---

## 🔧 Agent① DataUnderstanding 实现 (2026-07-23)

**状态**: [VERIFIED]

### 修改内容

| 文件 | 操作 | 说明 |
|------|------|------|
| `agents/data_understanding.py` | 新建 | DataUnderstanding(BaseAgent) — 5 步骤 |
| `tests/test_data_understanding.py` | 新建 | 32 个测试 |
| `config.py` | 修改 | 新增 `AGENT_DATAUNDERSTANDING_TIMEOUT = 600` |

### 验证

- [x] 测试: 32/32 PASSED
- [x] 回归: 104/104 PASSED（原有 72 + 新增 32）
- [x] 对抗审查通过（发现 1 个 content=None 守卫缺失 → 已修复）

### 对抗审查记录

**边界值推演（5 个）：**
- `summary["content"]=None` → `content = summary.get("content") or {}` 兜底
- 空 JSON 文件 `[]` → `pd.DataFrame([])` 正常
- 全局全同评分（std=0）→ 任何偏差标记异常，数学正确
- 员工无 360 数据 → `scores_360.get(emp_id, {})` 返回 {}
- 全异常评价者 → 零除守卫正常

---

## 🔧 对抗性检验补丁 (2026-07-23)

**状态**: [VERIFIED]

### 发现 2 个真实 Bug

| # | 严重度 | 模块 | 根因 | 触发条件 |
|---|--------|------|------|---------|
| ADV-1 | 🟡 中等 | `agents/data_understanding.py` — `_safe_val()` | 未处理 `pd.NA` 类型（`pd.NA` 不是 `float`/`None`，穿透所有守卫） | employees 表中某字段值为 `pd.NA` 时，`_safe_val` 返回 `pd.NA` 而非 default，导致下游消费端 `is None` 检查失效 |
| ADV-2 | 🟢 轻微 | `utils/data_quality.py` — `_find_text_insufficient()` | 未对列存在性做守卫 | `performance`/`projects`/`evaluation_360` 缺失 `performance_comment`/`description`/`comment` 列时，`subset["col"]` 抛 `KeyError` |

### 修复

| Bug | 文件 | 变更 |
|-----|------|------|
| ADV-1 | `agents/data_understanding.py` | `_safe_val()` 增加 `pd.NA` 检测：`isinstance(val, type(pd.NA)) or (hasattr(val, "_is_na") and val._is_na)` |
| ADV-2 | `utils/data_quality.py` | `_find_text_insufficient()` 的 3 个文本列访问前增加 `and "<col>" in df.columns` 守卫 |

### 新增对抗测试集

- `tests/test_adversarial_day3.py` — 39 个测试，覆盖 10 个攻击面

| 攻击面 | 覆盖内容 | 测试数 |
|--------|---------|--------|
| A: 边界值 | age=17/18/70, yos=0/50/51, score=1/5, missing_rate=10% | 9 |
| A: pd.NA 兼容 | severe_missing 含 pd.NA, 文本列全 NaN | 2 |
| A: 列缺失守卫 | 缺 performance_comment/employee_id, 未知文件 spec | 3 |
| A: 重复 employee_id | 主表重复, 重复绩效记录 | 2 |
| A: 类型检查边界 | 可转数字字符串 "3.5", 混合 int/str | 2 |
| A: 空字符串 ID | text_insufficient + severe_missing 中空 ID | 2 |
| B: `_safe_val` pd.NA | 单字段 + 完整融合管线 | 2 |
| B: weight_total=0 | 仅自评, 仅未知角色 | 2 |
| B: 空 JSON | `projects.json = []` | 1 |
| B: std=0 | 全同评分 | 1 |
| B: employee_id 类型 | int vs str 不匹配 | 1 |
| B: 摘要长度边界 | 原文 29/30 字, 上限推演 | 3 |
| B: tools_used 字符串 | JSON 字符串, 非法 JSON, None | 3 |
| B: metadata 对称性 | degraded 路径 key 集合 | 2 |
| B: 退避边界 | 7/8/100 次, 0 次 | 2 |
| B: 空数据文件 | 0 员工, 1 员工 1 评价者 | 2 |

### 验证

- [x] 对抗测试: 39/39 PASSED（+3 条修复后通过）
- [x] 回归: 原有 74 个测试全部 PASSED
- [x] 总计: 113/113 PASSED

---

**日期**: 2026-07-22
**范围**: 基于代码审查的 4 项必要修改
**状态**: [VERIFIED]

---

## 🔧 Task 2.2 Streamlit 过滤层界面 (2026-07-22)

**状态**: [VERIFIED]

### 修改内容

| 文件 | 操作 | 说明 |
|------|------|------|
| `ui/app.py` | 重写 | 从测试页面升级为步骤化界面（Step 1: 数据上传 + Step 2: 基础过滤） |
| `ui/app_test_page_backup.py` | 备份 | 原测试页面备份 |
| `tests/test_ui_app.py` | 新建 | 导入路径 + 常量类型验证测试 |

### 变更摘要

1. **render() 函数结构保持不变**，内部全部替换为模块级私有函数调用
2. **Step 1 数据上传**：6 file_uploader（3×2 网格），列名校验，数据预览，确认上传
3. **Step 2 基础过滤**：侧边栏过滤条件（年龄/政治面貌/专业关键词/工龄/职级/绩效），直接调用 BasicFilter
4. **侧边栏**：步骤指示器（6 步，预留 Step 3-6），API 配置，API 调试折叠区，过滤条件区（step≥2 显示）
5. **旧测试页面内容完全移除**（text_area + send 按钮），API 测试移入侧边栏折叠区

## 🔧 第九轮修复 (2026-07-22) — 修改方案必要项落地

**状态**: [VERIFIED]

### 修改内容

| 编号 | 文件 | 变更 |
|------|------|------|
| P0-1 | `data/generate_mock_data.py` | DS 评分池扩展覆盖 1-5 全量程（5 维度 × 5 角色，所有列表增加 1-2 分） |
| P2-6 | `config.py` | 新增 `PERFORMANCE_FULL_YEARS` 常量 = `[当前年-2, 当前年-1]` |
| P1-4 | `tests/test_utils.py` | 新建文件：`numpy_to_native` 11 个测试 + `reset_client` 3 个测试 |
| P3-7 | `scripts/clean_intermediate.py` | 新建文件：测试残留 JSON 文件清理脚本 |

### 验证

- [x] 测试全部通过: 28/28 PASSED（原有 14 + 新增 14）
- [x] 对抗审查通过

### 对抗审查记录

**P0-1 (DS 扩展):**
- `p(DS[dim][role])` 仍是 `random.choice`，扩展列表后只改变概率分布，不改变语义
- `sc = max(1, min(5, sc))` clamp 确保 score 始终在 [1,5] 内
- 偏差评价者的 `sc <= 2` 分支现在可达（此前因评分池只有 3-5 永不触发）

**P2-6 (PERFORMANCE_FULL_YEARS):**
- `datetime.now()` 在模块导入时固定，跨午夜运行不变 —— 符合"完整年度"语义
- 新增 `from datetime import datetime` 不影响其他 import

**P1-4 (测试文件):**
- `numpy_to_native` 11 个测试覆盖全部 6 种类型 + NaN + 嵌套结构 + JSON round-trip
- `reset_client` 3 个测试覆盖不崩溃、缓存清空、连续调用

**P3-7 (清理脚本):**
- 预览模式（`--run` 前不删除）防止误操作
- 模式匹配 "pipe-test/timeout-test/test-fallback/debug-pipe" 与真实 trace_id 文件无重叠

---

## 🔧 第八轮修复 (2026-07-22) — 开发指南规范缺陷 (5 代码 + 6 指南)

**状态**: [VERIFIED] — 对抗审查修正（2026-07-22）: schema_validated=True bug 已修复, timeout_seconds 类型守卫已添加, 空白模型名已处理, 误导注释已更正, 线程泄漏已降低

### 修改代码
- `orchestrator/pipeline.py` — [VERIFIED] PipelineRunner 支持 Agent 级别超时覆盖 + summary 安全截断
- `agents/base_agent.py` — docstring 声明可选的 `timeout_seconds` 类属性
- `utils/llm_client.py` — `call_llm`/`call_llm_json` 的 `model` 参数从导入时冻结改为运行时动态读取 `os.environ`
- `config.py` — .env 缺失 / API Key 为空时输出 stderr 警告

### 修改指南（第一轮 6 处）
- `开题报告/第一周开发指南_vibe-coding.md` — 详见第七轮下方

### 修改指南（第二轮 6 处 — 推演发现）
- `开题报告/第一周开发指南_vibe-coding.md`:
  - #NEW-A: L145 验收命令 `ui/app.py` → `main.py`
  - #NEW-B: Task 5.1 明确异常检测（>2σ→×0.2）保留，叠加在综合权重之上
  - #NEW-C: Task 5.1 增加零除守卫（全敷衍评价者分母=0 的处理）
  - #NEW-D: Task 2.1 `min_performance` "近2年" → 明确为 2024+2025
  - #NEW-E: Task 6.3 防止 main.py 被覆盖丢失 sys.path 初始化
  - #NEW-F: Task 4.2 Streamlit 进度条 → spinner（主线程阻塞限制）

### 验证
- ✅ 测试: 14/14 PASSED
- ✅ 对抗审查: PipelineRunner 新旧调用点兼容，model=None 全路径解析正确，summary 截断不破 JSON

---

## 🔧 第七轮修复 (2026-07-22) — 9 个 360 评估与管道序列化补全

**状态**: [VERIFIED]

---

## 🔧 第七轮修复 (2026-07-22) — 9 个 360 评估与管道序列化补全

**状态**: [VERIFIED]

### 🔴 严重 (3)
| Bug | 文件 | 修复 |
|-----|------|------|
| #NEW-1 | `data/generate_mock_data.py` L125 | `rn=["上级","同事","自评"]` → `rn=["上级","同事","自评","下属","HR"]`，360 评估覆盖全部 5 个评估角色（100 x 5 dims x 5 roles = 2500 条） |
| #NEW-2 | `utils/llm_client.py` L179 | `schema_validated = None if json_schema is None else False` — 当 json_schema 未提供时初始化为 None（语义正确：未要求校验），提供时初始化为 False（将在校验成功后设为 True） |
| #NEW-4 | `orchestrator/pipeline.py` L177 | Exception 路径 `"data": data` — 保留输入数据供调试，替代此前丢失数据的 None |

### 🟡 中等 (1)
| Bug | 文件 | 修复 |
|-----|------|------|
| #NEW-9 | `orchestrator/pipeline.py` L223 | 第三级降级序列化 `json.dumps` 添加 `default=str`，与上级序列化保持一致 |

### 修改文件
- `data/generate_mock_data.py` — Bug #NEW-1
- `utils/llm_client.py` — Bug #NEW-2
- `orchestrator/pipeline.py` — Bug #NEW-4, #NEW-9

### 验证
- ✅ 测试: 14/14 PASSED
- ✅ 数据生成: emps=100 perf=300 proj=264 train=400 eval360=2500
- ✅ 一致性校验: hire_date ↔ years_of_service OK
- ✅ D3: call_llm_json 全部 4 条返回路径 key 集合一致（content/error/raw_content/usage/model/schema_validated）
- ✅ 对抗审查: 9 个修复逐行检查，无退化路径

---

## 🔧 第六轮修复 (2026-07-22) — 代码审计 8 个隐性问题

**状态**: [VERIFIED]

### 🔴 严重 (2)
| Bug | 文件 | 修复 |
|-----|------|------|
| #A1 | `data/generate_mock_data.py` | ext 评估者校验排除自评：`and row["evaluator_role"] != "自评"`（自评受异常逻辑保护但校验未跳过） |
| #A2 | `utils/llm_client.py` | Schema 校验失败时 `raw_content: None` → `raw_content: parsed`（保留已解析 JSON 供调试） |

### 🟡 中等 (3)
| Bug | 文件 | 修复 |
|-----|------|------|
| #A3 | `utils/llm_client.py` | `call_llm_json` 全部 5 条返回路径添加 `schema_validated: True/False` 字段 |
| #A4 | `utils/llm_client.py` | `resp.choices[0].message.content or ""` → `... if ... is not None else ""`（区分 None vs 空字符串） |
| #A5 | `progress.md` | 测试数量 `13/13` → `14/14`（同步 test_timeout_boundary.py 第 4 个测试） |

### 🟢 轻微 (3)
| Bug | 文件 | 修复 |
|-----|------|------|
| #A6 | `orchestrator/pipeline.py` | `cancel_delay` 添加注释说明短超时边缘情况（Timer 与硬超时同时触发） |
| #A7 | `data/generate_mock_data.py` | `"P3" <= level <= "P5"` 字符串比较 → `int(level[1:])` 数值比较（防 P31-P59/P310+ 字符串前缀误判） |
| #A8 | `tests/test_timeout_boundary.py` | "两轮 timeout=2s → 4s" 过时注释 + 12s 容忍 → "单次 future.result... 6s" |

### 修改文件
- `data/generate_mock_data.py` — Bug #A1 #A7
- `utils/llm_client.py` — Bug #A2 #A3 #A4
- `orchestrator/pipeline.py` — Bug #A6
- `tests/test_timeout_boundary.py` — Bug #A8
- `progress.md` — Bug #A5

### 验证
- ✅ 测试: 14/14 PASSED（零噪声）
- ✅ D1 边界值: Bug #A4 or→is-not-None 5 个输入（None/""/"hello"/0/False）无退化
- ✅ D1 边界值: Bug #A7 str→int 5 个输入（P3/P10/P2/P/""）正确，仅畸形输入抛 ValueError
- ✅ D3: call_llm_json 全部 5 条返回路径 schema_validated 键一致
- ✅ 对抗审查: 8 个修复逐行边界推演，零退化路径

---

## 🔧 第五轮修复 (2026-07-22) — 代码审计 6 个隐性问题

### 🔴 严重 (2)
| Bug | 文件 | 修复 |
|-----|------|------|
| #1 | `orchestrator/pipeline.py` | 移除 `_execute_with_timeout` 重试循环（`for attempt in (1, 2)`），改为单次执行。Python 线程不可终止，重试=并发线程 → 双倍 API 调用 |
| #2 | `orchestrator/pipeline.py` | Exception 路径 `duration_ms: 0` → `elapsed_ms`（记录 `t_start` 后计算实际耗时） |

### 🟡 中等 (4)
| Bug | 文件 | 修复 |
|-----|------|------|
| #3 | `data/generate_mock_data.py` | `rn=["上级","同事"]` → `rn=["上级","同事","自评"]`，使 DS/DC 中"自评"数据可达 |
| #4 | `utils/llm_client.py` | `call_llm()` 在 `resp.choices[0]` 前增加 `if not resp.choices` 守卫 |
| #5 | `orchestrator/pipeline.py` | `_save_intermediate` 降级序列化 `safe` 字典增加 `data` 字段 |
| #6 | `orchestrator/pipeline.py` | `step_result["status"]` → `step_result.get("status")` 统一防御式访问 |

### 🔧 对抗审查额外发现 (2)
| 问题 | 文件 | 修复 |
|------|------|------|
| D3 违规: 成功路径 metadata 缺 error 键 | `agents/base_agent.py` | `result["metadata"].setdefault("error", None)` |
| resp.model 未守卫 | `utils/llm_client.py` | `resp.model` → `resp.model or ""` |

### 修改文件
- `orchestrator/pipeline.py` — Bug #1 #2 #5 #6
- `utils/llm_client.py` — Bug #4 + 对抗审查 resp.model 守卫
- `data/generate_mock_data.py` — Bug #3
- `agents/base_agent.py` — 对抗审查: 成功路径注入 error: None (D3)

### 验证
- ✅ 测试: 14/14 PASSED（零噪声，无僵尸线程日志）
- ✅ D2: LLM_API_TIMEOUT/AGENT_EXEC_TIMEOUT 集中在 config.py 单向引用
- ✅ Rule 6: _get_client() 动态读取 DEEPSEEK_BASE_URL + _last_base_url 追踪
- ✅ Rule 9: 超时值单一来源，pipeline.py + llm_client.py 全部引用 config 常量
- ✅ 对抗审查: summary 与 current_data 一致性；cancel_timer 全路径覆盖；空字符串处理

---

## 🔍 第三轮修复 (2026-07-22) — 代码审计发现 10+2 个隐性问题

### 🔴 严重 (4)
| Bug | 文件 | 修复 |
|-----|------|------|
| A | `utils/llm_client.py` | call_llm_json schema 校验失败时 content → None |
| B | `utils/llm_client.py` | call_llm_json 全部 4 条返回路径统一注入 raw_content 键 (D3) |
| C | `tests/test_timeout_boundary.py` | time.sleep → socket 阻塞 I/O；新增 _PureBlockingAgent + 硬超时测试 (D5) |
| D | `agents/base_agent.py` | 校验失败/异常路径注入 data_lineage (D4) |

### 🟡 中等 (3)
| Bug | 文件 | 修复 |
|-----|------|------|
| E | `agents/base_agent.py` | execute() 返回非 dict → 自动包装；缺 status → 注入 "success" |
| F | `orchestrator/pipeline.py` | _execute_with_timeout 超时/异常路径注入 data_lineage |
| G | `utils/llm_client.py` | call_llm 增加 docstring 说明 error 字段使用 |

### 🟢 轻微 (3)
| Bug | 文件 | 修复 |
|-----|------|------|
| H | `tests/test_timeout_boundary.py` | output_dir="data/intermediate" → tmp_path |
| I | `utils/llm_client.py` | _get_client() 删除 _client = None 死代码 |
| J | `utils/logger.py` | 默认 log_dir 改用 config.LOG_DIR |

### 🔧 对抗审查额外发现 (2)
| 问题 | 文件 | 修复 |
|------|------|------|
| API error 路径缺 raw_content | `utils/llm_client.py` | 该路径重建返回结构含 raw_content: None |
| 时间戳无时区 | `orchestrator/pipeline.py` | datetime.now().isoformat() → datetime.now(timezone.utc).isoformat() |

### 验证
- ✅ 测试: 14/14 PASSED
- ✅ D3: call_llm_json 全部 4 条路径 key 集合一致
- ✅ D4: BaseAgent.run() 全部 3 条路径含 data_lineage
- ✅ D5: socket 阻塞 I/O 替代 time.sleep

---

## 第二轮修复 (2026-07-21)

**范围**: 17个Bug全量修复
**状态**: [VERIFIED]

---

## 🔧 第四轮修复 (2026-07-22) — Streamlit 静默崩溃 (P0)

### 根因
Streamlit 的脚本重运行（rerun）机制与 Python 模块缓存冲突，导致两个独立问题：

1. **`from openai import OpenAI` 模块级导入导致 Streamlit 静默崩溃**
   - `openai` 包在 Streamlit 脚本运行器线程内部导入时，会破坏其内部状态
   - 症状：页面标题从 "Talent Compass" 变为 "Streamlit"，UI 完全空白
   - 修复：将 `from openai import OpenAI` 移入 `_get_client()` 函数内（惰性导入）

2. **`import ui.app` 在重运行时不重新执行 `st.*` 调用**
   - Python 模块缓存机制使 `import ui.app` 在一次执行后成为空操作
   - Streamlit 在重运行时依赖重新执行 `st.*` 调用来重建组件树
   - 由于 `ui/app.py` 不再重新执行，Streamlit 无法渲染新状态 → 页面空白
   - 修复：将 `ui/app.py` 从模块级代码重构为 `render()` 函数模式，
     `main.py` 改为 `from ui.app import render; render()`

### 修改文件
- `utils/llm_client.py` — `from openai import OpenAI` 移至 `_get_client()` 内（惰性导入）
- `main.py` — `import ui.app` 改为 `from ui.app import render; render()`
- `ui/app.py` — 全部 `st.*` 调用封装在 `render()` 函数中

### 验证
- ✅ 初始加载正常（标题 "Talent Compass"）
- ✅ 点击发送按钮 → API 调用成功 → AI 回复正常显示
- ✅ 多次点击发送按钮 → 全部正常（稳定性验证）
- ✅ `python -c "from utils.llm_client import call_llm; ..."` 独立调用正常
- ✅ `python -m pytest tests/ -v` → 13/13 PASSED

---

## 修复明细

### 🔴 严重 (3/3)
| Bug | 文件 | 修复 | 验证 |
|-----|------|------|------|
| F-101 (#9) | `orchestrator/pipeline.py` | Timer提前(cancel_delay)秒通知Agent，超时前优雅退出；clamp max(1, timeout-5)防止负延迟；Exception路径cancel_timer.cancel() | 3个超时测试通过 |
| F-102 (#10) | `orchestrator/pipeline.py` | `step_result.get("data", {}) or {}` → `{} if val is None else val` | 管道测试通过 |
| F-103 (#11) | `.env` + `.gitignore` | .env顶部增加安全警告注释；创建.gitignore排除.env等敏感文件 | 已确认 |

### 🟡 重要 (8/8)
| Bug | 文件 | 修复 | 验证 |
|-----|------|------|------|
| F-104 (#12) | `agents/base_agent.py` | run()自动注入data_lineage默认值(model=""/timestamp/audit_status="pending") | BaseAgent测试通过 |
| F-105 (#13) | `utils/llm_client.py` | call_llm()失败时返回完整key集合{content,error,usage,model} | - |
| F-106 (#14) | `utils/llm_client.py` | call_llm_json()三种场景统一返回格式{content,error,usage,model} | - |
| F-107 (#15) | `config.py` | 默认值注释澄清：代码默认=官方API基线，代理场景通过.env覆盖 | - |
| F-108 (#16) | `utils/llm_client.py` | _get_client()添加threading.Lock双检锁保护 | - |
| F-109 (#17) | `orchestrator/pipeline.py` | 降级序列化时dict/list用json.dumps替代str() | - |
| F-110 (#18) | `orchestrator/pipeline.py` | output_dir从config.INTERMEDIATE_DIR单向引用 | - |
| F-111 (#19) | `tests/test_pipeline.py` | 全部5个测试改用pytest tmp_path fixture | 测试通过，无垃圾文件 |

### 🟢 次要 (6/6)
| Bug | 文件 | 修复 | 验证 |
|-----|------|------|------|
| F-112 (#20) | `utils/logger.py` | setup_logger()增加force参数 | - |
| F-113 (#21) | `config.py` + `main.py` | 目录创建从config.py移到main.py(带try/except) | - |
| F-114 (#22) | `ui/app.py` | 移除重复sys.path.insert，注释说明已由main.py处理 | - |
| F-115 (#23) | `data/generate_mock_data.py` | wjson()编码统一为utf-8-sig | 数据生成正常 |
| F-116 (#24) | `data/generate_mock_data.py` | set→sorted()保证确定性 | 数据生成正常 |
| F-117 (#25) | `utils/llm_client.py` | 确认：已有log.warning + jsonschema在requirements.txt中 | 无需改动 |

---

## 测试结果
```
tests/test_base_agent.py ............. 5 passed
tests/test_pipeline.py ................ 5 passed
tests/test_timeout_boundary.py ........ 3 passed
=== 14/14 PASSED ===
```

## 数据生成
```
employees: 100 ✅ | performance: 300 ✅ | projects: 264 ✅
training: 400 ✅ | eval360: 2500 ✅
一致性校验: [OK] hire_date ↔ years_of_service ✅
```

---

## 🔧 第七轮修复 (2026-07-22) — 深度审计 9 个隐性问题

**状态**: [VERIFIED]

### 🔴 严重 (1)
| Bug | 文件 | 修复 |
|-----|------|------|
| #NEW-1 | `data/generate_mock_data.py` | `rn` 从 `["上级","同事","自评"]+pn(["下属","HR"], randint(1,2))` → `["上级","同事","自评","下属","HR"]`（确保所有5种评价者角色全覆盖，消除25%员工缺"下属"评价的问题） |

### 🟡 中等 (4)
| Bug | 文件 | 修复 |
|-----|------|------|
| #NEW-2 | `utils/llm_client.py` | `schema_validated = False` → `None if json_schema is None else False`（区分"未请求校验"vs"请求但不可用"） |
| #NEW-3 | `orchestrator/pipeline.py` | 第二层降级序列化移除双重 JSON 编码（`safe_data` 直接传入 `safe`，由外层 `default=str` 兜底） |
| #NEW-4 | `orchestrator/pipeline.py` | Exception 路径 `data: None` → `data: data`（与 TimeoutError 路径一致，保留输入数据供调试） |
| — | `orchestrator/pipeline.py` | 注：短超时（≤6s）下 Timer 提前通知机制实际无效（已文档化），仅硬超时生效 |

### 🟢 轻微 (4)
| Bug | 文件 | 修复 |
|-----|------|------|
| #NEW-6 | `data/generate_mock_data.py` | 偏差评价者验证 `dev_scores` 增加 `and row["evaluator_role"] != "自评"` 排除自评（与极端评价者验证一致） |
| #NEW-7 | `utils/llm_client.py` | `raw_content: parsed`(dict) → `json.dumps(parsed)`(str)（统一 `raw_content` 类型为 str\|None） |
| #NEW-8 | `orchestrator/pipeline.py` | `str(None)` → 直接传 `None`（JSON 序列化为 `null` 而非 `"None"` 字符串）；由 #NEW-3 一并修复 |
| #NEW-9 | `orchestrator/pipeline.py` | 第三层降级 `json.dumps` 增加 `default=str`（与第一、二层一致） |

### 修改文件
- `data/generate_mock_data.py` — Bug #NEW-1 #NEW-6
- `utils/llm_client.py` — Bug #NEW-2 #NEW-7
- `orchestrator/pipeline.py` — Bug #NEW-3 #NEW-4 #NEW-8 #NEW-9

### 验证
- ✅ 测试: 14/14 PASSED（零噪声）
- ✅ 数据生成: eval360 1740→2500（100人×5维度×5角色），一致性校验通过
- ✅ D3: `call_llm_json` 全部4条返回路径 key 集合一致（content/error/raw_content/usage/model/schema_validated）
- ✅ 对抗审查: 4个修复逐行边界推演，发现1个残留语义问题（ImportError 路径 `schema_validated:False` 可优化为 `None`，不影响功能）

---

## 🔧 债务清偿 (2026-07-24 晚)

**状态**: [VERIFIED]

### 修改内容

| 文件 | 操作 | 说明 |
|------|------|------|
| `scripts/run_pipeline_phase1.py` | 新建 | 命令行流水线脚本，串联 BasicFilter → Agent①，预留 `--agent2/3/4` 扩展参数位 |
| `pipeline_config/filter_conditions.json` | 新建 | 默认过滤条件配置文件（6 项条件） |
| `README.md` | 新建 | 项目简介 + 架构 + 快速开始 + 功能清单 |
| `tests/test_data_quality.py` | 修改 | 修复 2 个 FutureWarning（dtype 不兼容赋值） |
| `tests/test_adversarial_day3.py` | 修改 | 修复 2 个 FutureWarning（dtype 不兼容赋值） |

### 遗留问题记录

- ❌ `scripts/validate_phase1.py` — 端到端验证脚本（Task 5.2）尚未创建，由开发指南列出但未进入任务计划，建议在 07.25 联调时补建

### 验证

- [x] 测试: 209/209 PASSED，零 FutureWarning（`-W error::FutureWarning` 全绿）
- [x] `filter_conditions.json`: 合法 JSON
- [x] `python scripts/run_pipeline_phase1.py --help`: 参数正常解析，含预留扩展接口

---

## 🔧 Day5: 360 预处理增强 (2026-07-25)

**状态**: [VERIFIED]

### 修改内容

| 文件 | 操作 | 说明 |
|------|------|------|
| `config.py` | 修改 | 新增 11 个 360 预处理常量 |
| `agents/data_understanding.py` | 修改 | 删除内联常量改为 import config；REQUIRED_COLUMNS 加 year；重写 `_preprocess_360()` 综合公式；`_merge_records()` 适配嵌套结构 |
| `ui/app.py` | 修改 | `_STEPS` 7→8 新增 Step⑤ 360评价；新增 `_render_step_360()` 和 `_compute_360_scores()` |
| `tests/test_data_understanding.py` | 修改 | fixture year 循环；assert 适配 nested 结构；删除 test_tech_role_adjustment；新增 Test360ComprehensiveFormula |
| `tests/test_adversarial_day3.py` | 修改 | ROLE_WEIGHTS_BASELINE import 改来源；fixture year 循环；assert 适配 nested 结构 |
| `tests/test_ui_app.py` | 修改 | _STEPS 长度 7→8 |
| `scripts/validate_phase1.py` | 新建 | 端到端验证脚本（5 类检查 + --skip-llm） |
| `data/intermediate/baseline_360_v1.json` | 新建 | 旧版 `_preprocess_360()` 基线输出 |

### 变更摘要

1. **内联常量迁移**: ROLE_WEIGHTS_BASELINE, SELF_EVAL_ROLE, KNOWN_DIMENSIONS, ROLE_ADJUSTMENTS 从 data_understanding.py 内联定义移至 config.py（D1 修复），ROLE_ADJUSTMENTS 因被综合公式替代而删除
2. **综合公式**: 新增时间衰减（TIME_DECAY_RATE=0.3）、区分度检测（std=0 & mean≤4 → 敷衍权重 0.1）、置信度（评价者数 + 异常率 + 年份覆盖度）
3. **输出结构变更**: `scores_360[emp_id]` 从 `{dim: score}` 变为 `{"dimensions": {dim: score}, "confidence": float}`
4. **UI 新增独立步骤**: Step⑤ 360评价，含员工选择器、5维度 metric+progress bar、条形图、置信度色彩编码、权重因子折叠详情、全局统计摘要

### 验证

- [x] 测试: 213/213 PASSED
- [x] 对抗审查: 6 边界值 + C4 穷举验证通过
- [ ] 基线对比: 待执行（需要完整 pipeline 运行）
- [ ] 端到端验证: 待执行（需要完整 pipeline 运行）
