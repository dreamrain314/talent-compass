# Progress — Talent Compass

## [VERIFIED] — 2026-07-25

验证完成：
1. `python -m pytest tests/ -v` → **231/231 passed**
2. `python scripts/run_pipeline_phase1.py --skip-filter --max-employees 3 --offline` → status=success, 3/3 成功, 1.0s
3. 对抗审查发现并修复：
   - C8 缺口：degraded/offline 占位符返回 error=None，但 `_merge_records` 漏传 `summary_model` → 下游不可审计。已补 `summary_model` 字段贯穿 `_process_employees` → `_merge_records` → final_output。
   - C1 对称：`_process_employees` 4 条失败路径与 1 条成功路径的 record key 集合 → 在 `record = {...}` 初始化处统一设 `summary_model=""` 默认值，成功路径覆盖。
   - 测试断言 bug：`test_offline_mode_no_llm_call` 硬编码锚点 12 字，实际 `[:10]`=10 字 → 改用 `perf[:10]` 派生。

变更范围（跳出"修 JSON 等 API 配合"框架）：

- `config.py` — 新增 `is_offline_mode()` + `PLACEHOLDER_SUMMARY_LEN/ANCHOR_LEN` 常量
- `utils/llm_summarizer.py` —
  - 顶部 offline dispatch → `_derive_placeholder_summary`（不调 API）
  - call_llm_json 解析失败时改用 `_derive_placeholder_summary`（**砍掉原 `_fallback_text_summary` 第 2 次 LLM 调用**，杀退避雪崩）
  - 删除 `_fallback_text_summary` + `_extract_field`（被占位符派生取代，D2/F1 去重）
  - 移除未用的 `call_llm` 导入
- `utils/llm_client.py` — `_repair_truncated_json` 增加第 2 轮截断字符串值捕获（finish_reason=length 最常见情形）
- `scripts/run_pipeline_phase1.py` — 新增 `--offline` 标志 → `os.environ["TC_OFFLINE"]="1"`
- `agents/data_understanding.py` — `_process_employees` 设 `summary_model`；`_merge_records` 传播 `summary_model` 到最终 record
- `tests/test_llm_client.py`（新）— 覆盖 `_try_parse_json` / `_repair_truncated_json` 边界（含截断字符串值、转义引号、混合完整+截断）
- `tests/test_llm_summarizer.py` — 增 offline + degraded 占位符派生测试（含"不调第 2 次 LLM"断言）


变更范围（跳出"修 JSON 等 API 配合"框架）：

- `config.py` — 新增 `is_offline_mode()` + `PLACEHOLDER_SUMMARY_LEN/ANCHOR_LEN` 常量
- `utils/llm_summarizer.py` —
  - 顶部 offline dispatch → `_derive_placeholder_summary`（不调 API）
  - call_llm_json 解析失败时改用 `_derive_placeholder_summary`（**砍掉原 `_fallback_text_summary` 第 2 次 LLM 调用**，杀退避雪崩）
  - 删除 `_fallback_text_summary` + `_extract_field`（被占位符派生取代，D2/F1 去重）
  - 移除未用的 `call_llm` 导入
- `utils/llm_client.py` — `_repair_truncated_json` 增加第 2 轮截断字符串值捕获（finish_reason=length 最常见情形）
- `scripts/run_pipeline_phase1.py` — 新增 `--offline` 标志 → `os.environ["TC_OFFLINE"]="1"`
- `tests/test_llm_client.py`（新）— 覆盖 `_try_parse_json` / `_repair_truncated_json` 边界
- `tests/test_llm_summarizer.py` — 增 offline + degraded 占位符派生测试

## [VERIFIED] — 2026-07-26（Day 6）

### 完成内容

| 领域 | 子项 | 说明 | 状态 |
|------|------|------|------|
| 词典编写 | 标准标签库种子 | `data/standard_label_library_v1.json` — 35 标签（T1 13 / T2 13 / T3 9），冰山模型+大五人格框架 | ✅ |
| 词典编写 | T0 初始词典 | `data/t0_registries.json` — 60 条目（35 工具 / 12 行业领域 / 13 知识体系），含别名/分类/典型用途 | ✅ |
| 修复 | ADV-4 line_height 修复 | `ui/app.py:1012` `line_height=24` 无效参数 → 删除 kwarg（F8 修 API 调用必查签名） | ✅ |
| 修复 | S4 str_score 360 崩溃 | `ui/app.py` + `agents/data_understanding.py` 3 处 score 聚合加 `pd.to_numeric(... errors="coerce")` 守卫 | ✅ |
| 前端对抗测试 | Day 6 报告 | `docs/frontend-adversarial-report-day6.md` — 8/8 PASS（含 S4 回归），7 个对抗夹具包 | ✅ |
| 前端完整性检验 | Day 7 报告 | `docs/frontend-inspect-report-day7.md` — Step 1-5 全模块构造正确，Step 6-8 占位符合计划 | ✅ |
| 截图文档 | 检验截图 | `docs/screenshots/inspect/`（13 张）+ `docs/screenshots/regression/`（14 张）+ `docs/screenshots/boundary/`（5 张） | ✅ |

### 学到的经验（防不同步机制）

1. **task-plan.md 未随 commit 更新** — commit `08416ec` 完成了词典编写但 2.1.9 仍标记 ⏳
2. **progress.md 未随修复生成** — Day 6 的 3 处修复+前端验证无 tracking 条目
3. **change-log.md 遗漏** — Day 6 修复记录同样缺失
4. **截图产出未 git add** — 测试脚本生成的 32 张截图未纳入版本管理

→ 详见[防不同步流程改进方案]（本文件末尾）

---

## [VERIFIED] — 2026-07-26（第 2 周准备 · Step 1: certificates 字段）

**变更文件:** `scripts/generate_mock_data.py`
**变更摘要:** 为 H1Filter 数据来源做准备 —— employees 新增 `certificates` 字段

具体修改：
1. 新增 `SEQ_CERTS` 证书池（4 个岗位序列各 4-6 个序列相关证书，PMP 跨序列通用）
2. 新增 `_gen_certificates(seq, level_num)` —— 权重：~55% 无 / ~30% 持 1 个 / ~15% 持 2 个；高职级上浮 15% 但保留 ≥30% 无证书下限
3. `gen_emps` 的 `rows.append` 增加 `certificates=_gen_certificates(sq, lv)`
4. `generate_all` 的 `wcsv("employees.csv", ...)` fieldnames 增加 `certificates`
5. 新增 certificates 校验块：空值检查 + 序列一致性 + 分序列持证率统计
6. **关键隔离**：用独立 `_CERT_RNG = random.Random(2026)`，不污染主 `random.seed(42)` 链路 → 保证 perf/proj/train/eval360 baseline 可重复

**验证结果（V2 闸门通过）：**
- [x] 跑生成脚本 → certificates 55/100 持证 (55%)、无空值、序列一致性通过；分序列持证：技术研发 10/25 / 管理职能 19/25 / 市场业务 12/25 / 新业务创新 14/25
- [x] 独立 RNG 隔离成功 → perf/proj/train hash 与 baseline **完全一致**（`performance.csv`/`projects.json`/`training.csv` 三文件 hash 未变）
- [x] `data/raw/employees.csv` 已同步 certificates 列（cp 自 `scripts/raw`），其余 4 文件 hash 不变
- [x] `pytest tests/ -v -W error::FutureWarning` → **231/231 passed**（14.75s）
- [x] 对抗审查：`_gen_certificates` 9 个边界值推演通过（未知序列/level=1,9,5,6/pool 长度=1/random=0.0/PMP 不重复/证书无 `;`）

**发现的既存问题（不在本任务范围，记录备修）：**
1. `evaluation_360.csv` baseline 与当前脚本输出不一致（hash `96c92946` vs `6ca9590f`）——用 HEAD 版本（无 certificates）跑脚本仍不一致，证明 baseline 过时、与 certificates 修改**无关**。建议单独任务重新生成 eval360 baseline。
2. `generate_mock_data.py` 的 `RAW_DIR = Path(__file__).parent / "raw"` 硬编码为 `scripts/raw`，违反 D2（config.py 已定义 `RAW_DATA_DIR = data/raw`）。当前靠手动 cp `scripts/raw/*` 同步 `data/raw`。建议改用 `config.RAW_DATA_DIR` 一劳永逸。

---

## [VERIFIED] — 2026-07-26（第 2 周准备 · Step 1.5: 修既存 D2 违规 + eval360 baseline 同步）

**变更文件:** `scripts/generate_mock_data.py`
**变更摘要:** 修 RAW_DIR 硬编码（D2 合规）+ 重新生成 data/raw 让 eval360 baseline 与脚本同步

具体修改：
1. import: `from config import EVALUATOR_MIN_SAMPLE_SIZE` → 加 `RAW_DATA_DIR`
2. `RAW_DIR = Path(__file__).resolve().parent / "raw"` → `RAW_DIR = RAW_DATA_DIR`（直接写 data/raw，消除手动 cp）

**附带操作:** 跑脚本重新生成 data/raw 全部 5 文件 → eval360 baseline 与脚本重新同步（解决既存问题①）

**验证结果（V2 闸门通过）：**
- [x] 脚本直接写 data/raw —— `scripts/raw` 不再产生（D2 合规达成，消除手动 cp）
- [x] perf/proj/train hash 与之前 baseline **完全一致**（`5a7ad6bc`/`cd853969`/`7c034dc5`，独立 RNG 仍隔离）
- [x] employees.csv 含 certificates 列（JZ0001=无，持证率 55/100）
- [x] eval360 重新生成 → hash `96c92946`→`6ca9590f`（baseline 与脚本同步，既存问题①解决）
- [x] `pytest tests/ -v -W error::FutureWarning` → **231/231 passed**（9.14s，eval360 baseline 变化不破坏测试——下游只测结构/异常检测逻辑，不依赖具体 score 值）

**对抗审查（边界推演）：** RAW_DATA_DIR 是 config 绝对路径 → 脚本从任意 cwd 跑都写 data/raw ✅；`mkdir(exist_ok=True)` data/raw 已存在不报错 ✅；import 失败风险排除（config 已定义且他模块已用）✅

---

## [定稿] — 2026-07-26（第 2 周准备 · Step 2: Agent② 输出 JSON Schema）

**变更文件:** `docs/plan-profile-agent-schema.md`（新建，设计文档非代码，不触发 V1 闸门）

**设计内容：**
- Agent② 输出 JSON Schema：H1 资质 + T0 显性 + T1/T2/T3 标签 + 成长曲线 + 大五 + summary
- 包装在 BaseAgent 契约（`status`/`data`/`metadata`，C1 对称）
- 7 条设计决策（D1-D7）+ §6 决策点定稿 + §7 config 常量清单

**关键决策（用户 2026-07-26 确认）：**
- D2: T1 双字段 `ability_score`(0-100) + `sfia_level`(0-7)
- 大五: 0-100（与 ability_score 对齐）
- summary: 保留（约束仅基于已抽标签，防幻觉）
- D4: Demo 期跳过聚类（第四阶段扩展，向前兼容）

**边界澄清（防下游混淆）：**
- Agent② **只产员工侧 `sfia_level`，不算 T1 得分** —— T1 得分公式 `Σ w_i × SFIA_diff` 是 Agent④ 职责（需 Agent③ 要求侧 SFIA）
- 实现时 config 常量待加：`SFIA_MAX_LEVEL=7` / `SFIA_CAP_EXCESS=2` / `LABEL_CONFIDENCE_THRESHOLD=0.6` 等（D2 单一来源，详见文档 §7）

---

## [VERIFIED] — 2026-07-26（第 2 周准备 · Step 3: Embedding demo + 框架选型）

**变更文件:** `scripts/embedding_demo.py`（新建）+ `requirements.txt`（加 fastembed）+ `docs/plan-profile-agent-schema.md`（加 §8）
**状态:** demo 验证脚本（非核心逻辑，不触发 V1 闸门；已跑通验证 6/6 top-1 命中）

**选型决策:**
- 框架: `fastembed` + `BAAI/bge-small-zh-v1.5`（ONNX 后端, 无 torch, 离线, ~95MB）
- 理由: DeepSeek/Paratera 无 embedding API；OpenAI key 未配置；本地唯一可行；竞赛现场离线稳

**验证结果:** 6 查询 top-1 排序 6/6 命中预期（Java微服务→Java开发 sim=0.89 强映射；其余 0.59-0.69）

**⚠ 阈值标定发现（07.31 实现前必须解决）:**
- 原四档 `0.6/0.75/0.85/0.95` 为 OpenAI 标定，对 bge 过严（几乎全落 <0.60 pending）
- 现象: 词汇重叠高 sim 高（Java 0.89）；语义近用词异 sim 低（带团队→团队管理 0.59）
- 07.31 建议: top-1 + 相对 margin 判定（不依赖绝对值）+ 绝对下限兜底
- 详见 `docs/plan-profile-agent-schema.md` §8
