# CLAUDE.md — Talent Compass

> 📖 记忆索引 → `C:\Users\Long\.claude\projects\D--workplace\memory\MEMORY.md`
> 按类别分组: 操作规范 / Bug 根因 / 审查盲区 / 项目参考。
> 每条规则的「来源」列指向对应的根因 Memory 文件。遇到不理解的规则，先去读对应 Memory 的 Why 部分。

## 🔴 触发规则

| 条件 | 行为 |
|------|------|
| "工作流 / use workflow / fan out" | 必须调用 `Workflow`，禁止跳过 |
| >2 文件或架构决策 | 先调研提案，确认后实现 |
| pipeline() items > 5 | 分 batch ≤5，禁止逐条 agent |
| 子 agent 总数 > 10 | 先获得用户确认 |

## 🎯 设计阶段 — 落笔前想清楚

| # | 规则 | 来源 |
|---|------|------|
| D1 | **配置单一来源** — 路径/阈值/模型名只在 config.py 定义；硬编码数字问"明年还正确吗？"→ 用 `datetime.now()` 动态计算 | [[root-cause-static-assumptions]] |
| D2 | **跨表时间维度逐表核对** — 列出所有需要 year 字段的表，关联字段写 `assert` 约束（如 `start_date >= hire_date`）| [[root-cause-data-model-time-dimension]] |
| D3 | **统计方法标注样本量** — 统计函数前注释预期样本量，不足时跳过或回退到确定性逻辑 | [[root-cause-anomaly-detection-sample-size]] |
| D4 | **规则设计列举假阳性** — 每条 if/权重规则，先列出"可能被误杀的合法数据"再加限幅条件 | [[first-second-round-bug-patterns]] |
| D5 | **多任务接口明确契约** — 跨任务共享的入口写"保留 XXX 不动，仅修改 YYY"，防语义冲突 | [[talent-compass-bug-taxonomy]] |

## ✍️ 编码阶段 — 写代码时盯住

| # | 规则 | 来源 |
|---|------|------|
| C1 | **返回格式对称** — 公共函数成功/失败含相同顶层 key，`error: null` vs `error: "msg"`；≥3 条 return 的末尾注释 key 集合 | [[talent-compass-bug-taxonomy]] |
| C2 | **基类强制 > 文档约定** — 规范要求的 metadata 字段由基类自动注入（`data_lineage`），不靠子类自觉 | [[talent-compass-bug-taxonomy]] |
| C3 | **外部值先守卫再索引** — `resp.choices[0]` 前检查 `len>0`；跨边界值用 `isinstance`，失败信息含实际类型；DataFrame 列访问前检查列存在性（`"col" in df.columns`），不假设输入结构完整 | [[root-cause-input-structure-assumption]] |
| C4 | **防御代码自证 + 类型穷举** — `or {}` / `str(v)` / try/except 取 5 个边界值（`None`/`""`/`0`/`[]`/`{}`）验证不丢弃合法数据；守卫缺失值类型时穷举所有可能（`None`/`np.nan`/`pd.NA`/`pd.NaT`），不只覆盖最常见子集 | [[root-cause-guard-type-blindness]] |
| C5 | **标识符禁止字符串比较** — `"P3"<=x<="P5"` → `int(x[1:])`；数字嵌入字符串不可靠 | [[first-second-round-bug-patterns]] |
| C6 | **公式验证走极端 case** — 构造 3 个极端输入（全 0/全最大值/随机×1000 看分布），人工走通计算链，确认非恒等变换 | [[first-second-round-bug-patterns]] |
| C7 | **数据生成含跨字段断言** — 源字段随机后，派生字段推导，末尾 assert 校验；随机采样后检查最低数量，不足则补足 | [[root-cause-mock-data-edge-cases]] |
| C8 | **错误路径保留诊断数据** — 错误分支有可用中间值时写入返回值，禁止写死 `None`；降级分支必须修改返回值，调用方不能仅靠日志发现 | [[talent-compass-bug-taxonomy]] |
| C9 | **文件操作显式 encoding** — 所有 `open()` + `json.load()` 指定 `encoding="utf-8-sig"`，禁止依赖系统默认编码 | [[first-second-round-bug-patterns]] |
| C10 | **Streamlit：惰性导入 + render() 模式** — `from openai import OpenAI` 在函数内导入；`st.*` 调用全在 `render()` 内，入口用 `from ui.app import render; render()` | [[talent-compass-bug-taxonomy]] |

## 🔧 修复阶段 — 修 Bug 时

| # | 规则 | 来源 |
|---|------|------|
| F1 | **全库同类排查** — 修一个反模式 → `grep` 全库，列出全部命中逐个确认，禁止仅修发现点 | [[root-cause-utility-function-duplication]] |
| F2 | **修复影响面分析** — Edit 前列出 ≥3 个下游影响点（调用方/序列化/测试/错误路径）；改返回值 → grep 全部调用点 | [[fix-validation-feedback-loop]] |
| F3 | **线程禁止重试** — Python 线程不可杀，重试=并发；`_execute_with_timeout` 用 `cancel_event` 提前通知，禁止 `ThreadPoolExecutor` 重试循环 | [[first-second-round-bug-patterns]] |
| F4 | **单例每次访问检查配置变化** — 变化时重建；`_get_client()` 动态读环境变量 + `_last_key` 追踪 | [[first-second-round-bug-patterns]] |
| F5 | **数据 key ↔ 代码分支双向验证** — 新增 key → grep 读取方；新增分支 → 构造可达数据；创建目录前 grep 同名 .py 文件 | [[first-second-round-bug-patterns]] |
| F6 | **消费者视角验证** — 写完后切换到"谁会消费这个产出？"视角：AI 看得见吗？格式与周围一致吗？同模式在全库出现几次？| [[view-layer-structure-blindness]] |

## ✅ 验证阶段 — 写完确认

| # | 规则 | 来源 |
|---|------|------|
| V1 | **写入即锁定** — Edit/Write 核心逻辑 → 同 turn 在 progress.md 追加 `[AWAITING_VERIFY]`，闸门存在时禁止继续编码 | [[talent-compass-bug-taxonomy]] |
| V2 | **强制验证** — 清闸门必须：① `pytest tests/ -v` 全绿 ② 对抗审查（切换"假设有 bug"框架逐行边界推演）。失败 → `git checkout` 回退 | [[talent-compass-bug-taxonomy]] |
| V3 | **超时测试用真实阻塞 I/O** — socket 连不可路由地址，不用 `time.sleep()`；必须含一个完全不检查 cancel 的纯阻塞 agent | [[first-second-round-bug-patterns]] |
| V4 | **全库重审** — 每 3 轮修复后，全部文件做一次无预设全量通读，不跳过已审文件 | [[talent-compass-bug-taxonomy]] |
| V5 | **症状 → 根因下钻** — 发现一个限制/异常时，多问一层"为什么？"：技术约束是什么？调用方能否满足？是否影响其他模块？| [[talent-compass-bug-taxonomy]] |
| V6 | **结构 + 格式一致性检查** — 改完后与周围 3 个同类段落对比格式，确认缩进/标记/空行/引用风格一致 | [[view-layer-structure-blindness]] |
| V7 | **测试必须包括残缺输入 + 边界行为** — 残缺输入：测试数据含 `pd.NA`/`None`/空列表/缺失列等边缘值；边界行为：超时/并发机制验证资源释放而不止异常抛出；数学公式附带 ≥5 个典型输入 I/O 验证表 | [[review-blind-spot-input-structure]] |

## 📐 编码契约

```python
# Agent 输出格式（C1: 对称契约）
{"status": "success|degraded|error", "data": ..., "metadata": {
    "agent_name": str, "agent_version": str, "duration_ms": int, "trace_id": str,
    "error": None|str, "data_lineage": {"model": str, "timestamp": str, "audit_status": str}
}}

# BaseAgent 子类必须实现
class XxxAgent(BaseAgent):
    agent_name: str; agent_version: str
    def validate_input(self, data: dict) -> bool: ...
    def execute(self, data: dict, context: dict) -> dict: ...
    def get_input_schema(self) -> dict: ...
    def get_output_schema(self) -> dict: ...
```

## 🏗️ 架构速查

```
Pipeline: HR输入 → BasicFilter → ①DataUnderstanding → ②ProfileGen → ③JobAnalysis → ④MatchExplain → 输出
Matching:  H0(硬排除) → H1(证书不足→备选池) → T0(显性工具) → T1/T2/T3(胜任力推断)
```

## ⚙️ 运行

```bash
pip install -r requirements.txt
python data/generate_mock_data.py   # 生成 100 人模拟数据
python -m pytest tests/ -v          # 跑测试
streamlit run main.py               # 启动 UI
```

| 配置 | 值 |
|------|-----|
| 模型 | `.env` → `DEEPSEEK_MODEL`（Paratera: `DeepSeek-V4-Pro`，官方: `deepseek-chat`） |
| 超时 | `LLM_API_TIMEOUT=60s`, `AGENT_EXEC_TIMEOUT=120s`（单次，无重试） |
| 日志 | `utils.logger` — JSON 结构化，含 trace_id/agent_name |