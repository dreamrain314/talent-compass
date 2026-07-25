# Talent Compass — Findings Log

> **目的:** 记录开发过程中发现的关键问题、解决方案、经验教训和技术决策。
> **最后更新:** 2026-07-21

---

## 分类索引

| 类别 | 说明 |
|------|------|
| 🔴 严重 | 影响系统正确性或安全性的发现 |
| 🟡 重要 | 影响开发效率或代码质量 |
| 🟢 经验 | Vibe Coding / AI 辅助开发的经验教训 |
| 📋 决策 | 技术选型或架构决策记录 |

---

## 🔴 严重发现

### F-001: `ThreadPoolExecutor` 超时机制在 `with` 语句中失效

- **日期:** 2026-07-21
- **来源:** 构建审查 Bug #1
- **现象:** 设置 `timeout=120s`，但 Agent 线程卡死时 Pipeline 被永久阻塞
- **根因:** `ThreadPoolExecutor.__exit__` 内部调用 `shutdown(wait=True)`，即使 `future.result(timeout=...)` 抛出 `TimeoutError`，`with` 退出时仍等待线程完成。Python 线程无法被强制终止
- **实测:** 10 秒任务 + timeout=2 秒 → 实际耗时 10.0 秒
- **修复:** 不用 `with` 语句；使用显式 `executor.shutdown(wait=False, cancel_futures=True)` + `threading.Event` 取消信号
- **教训:** → [[F-007]] 超时/重试代码必须附带边界验证测试

---

### F-002: 360 偏差评价者公式是恒等变换

- **日期:** 2026-07-21
- **来源:** 构建审查 Bug #2
- **根因:** `sc = abs(sc-3)+3 if sc>3 else 3-abs(sc-3)` 对任意输入输出恒等
- **数学验证:** 对 sc=1,2,3,4,5 全部 output == input
- **影响:** 偏差评价者数据完全无效，Agent① 的异常评价者检测缺少测试数据
- **修复:** `sc >= 4 → min(5, sc + rand(1,2))`，`sc <= 2 → max(1, sc - rand(1,2))`
- **教训:** → [[F-008]] 数学变换必须附带 I/O 验证表
- **关联:** 这是一个典型的 Vibe Coding 风险——代码"看起来有逻辑"但实际是数学恒等式

---

## 🟡 重要发现

### F-003: Paratera 代理对流式连接的并发限制

- **日期:** 2026-07-21
- **来源:** 多轮诊断链确认（见 `CLAUDE.md` 根目录）
- **现象:** `parallel()` 同时发起 ≥3 个 Agent 时，多余连接被断开（`"API Error: Connection closed mid-response"` + 0 tokens）
- **根因:** Paratera 代理（`llmapi.paratera.com`）限制单 API Key 的并发流式连接数为 ~2-3
- **影响范围:** Workflow 脚本中 `parallel()` 用法
- **解决方案:**
  - **短期:** 用 `pipeline()` 替代 `parallel()`（agent 启动自然错开，18-agent workflow 全部成功）
  - **长期:** 切换到 DeepSeek 官方 API（`api.deepseek.com`）——无此限制
- **相关规则:** `CLAUDE.md` Rule D（根目录）+ `talent-compass/CLAUDE.md` Rule D

---

### F-004: 单例缓存导致 Streamlit 中 API Key 运行时更新无效

- **日期:** 2026-07-21
- **来源:** 构建审查 Bug #6
- **现象:** 用户在 Streamlit 侧边栏输入新 API Key → 设置环境变量 → 但 LLM 客户端仍用旧 Key
- **根因:** `_get_client()` 在首次调用时缓存 OpenAI client，之后永不再检查配置变化
- **修复:** 每次访问检查 `os.getenv("DEEPSEEK_API_KEY")` 变化并重建 client
- **教训:** → [[F-009]] Streamlit 长连接模型下，所有全局状态必须支持运行时重配置

---

### F-005: Windows GBK 编码导致 emoji 和特殊字符报错

- **日期:** 2026-07-21
- **来源:** Bug 修复过程中的 `UnicodeEncodeError`
- **现象:** `print("✅")` 在 Windows 终端报 `'gbk' codec can't encode character`
- **影响:** 测试脚本、print 调试、日志输出中的非 ASCII 字符
- **解决方案:**
  - 测试脚本：用 `[OK]` / `[FAIL]` 替代 emoji
  - 数据文件：统一使用 `utf-8-sig` 编码（CSV ✅ / JSON 目前用 `utf-8` 需改为 `utf-8-sig`）
- **关联:** 构建审查发现 4.1（JSON 编码问题）

---

### F-006: Workflow JS 引擎不支持 ES2018+ 语法

- **日期:** 2026-07-21
- **来源:** Workflow 脚本执行错误
- **现象:** `Array.flatMap()`、`??`、`?.` 等语法导致 `"Unexpected token"` 硬解析错误
- **根因:** Workflow 脚本引擎是受限 JS 运行时（非 Node.js）
- **安全语法:** `var/let/const`、箭头函数、模板字符串、`Array.map/filter/reduce`、`Promise.all`、`async/await`、展开运算符、`JSON.parse/stringify`、`Object.keys/values/assign`
- **相关规则:** `talent-compass/CLAUDE.md` Rule C

---

## 🟢 Vibe Coding 经验教训

### F-007: 超时/重试代码必须附带边界验证

- **对应:** [[F-001]]
- **规则:** 任何涉及 `timeout`、`retry`、`ThreadPoolExecutor`、`asyncio.wait_for` 的代码，必须同时生成一个边界测试（如 `sleep(10) + timeout(2)`），立即运行验证
- **原因:** AI 容易假设 Python 的 timeout 能"终止"线程，但实际线程模型不支持强制终止

---

### F-008: 数学公式必须附带输入输出验证

- **对应:** [[F-002]]
- **规则:** 任何数学变换/公式生成后，立即用 5-10 个典型输入值验证输出符合预期
- **原因:** AI 生成的公式"看起来有逻辑"但可能是恒等变换或无意义变换，视觉 review 极难发现

---

### F-009: 有状态单例必须考虑运行时更新

- **对应:** [[F-004]]
- **规则:** 全局单例（client、db connection、cache）必须每次检查最新配置并支持重建
- **原因:** AI 默认"一次性初始化"模型，但 Streamlit 是长连接 + 用户交互式修改配置

---

### F-010: 异常处理必须有实质差异

- **来源:** 构建审查 Bug #5
- **规则:** 每个 `except` 块必须至少做一件 `try` 块做不了的事（降级策略、不同序列化方式）；如果无法降级，直接让异常向上传播
- **原因:** AI 倾向于生成 try/except 来显得"健壮"，但 except 块经常是复制粘贴的死代码

---

### F-011: 数据生成脚本必须保证字段间一致性

- **来源:** 构建审查 Bug #8
- **规则:** 用随机数生成"应该一致"的多个字段时，必须从源字段推导依赖字段（不可独立随机），并在末尾追加一致性断言
- **原因:** 独立随机 jitter 会导致 `years_of_service` 和 `hire_date` 等字段出现逻辑矛盾

---

### F-012: Edit 工具可能导致缩进破坏

- **来源:** Bug #8 修复过程
- **现象:** `Edit` 工具做字符串替换时，替换文本的缩进层级与原代码不一致，导致代码被移到错误的作用域
- **教训:** 修复涉及缩进层级的代码时，先确认替换文本的缩进字符数量与目标位置匹配；复杂重构场景考虑用 `Write` 重写整个函数

---

## 📋 技术决策

### D-001: Demo 阶段使用 JSON 文件持久化，不使用数据库

- **日期:** 2026-07-19（设计阶段）
- **决策:** Demo 期（07.20-08.16）不使用 Redis/PostgreSQL，所有中间结果以时间戳 JSON 文件存储
- **理由:** 简化部署；数据量小（100 人）；编排器中间 JSON 支持断点续调
- **升级路径:** 生产部署（比赛后）切换到 Redis + PostgreSQL
- **来源:** 行为逻辑文档第五章

---

### D-002: 编排器使用确定性 Python 代码，不使用 LangGraph

- **日期:** 2026-07-19（设计阶段）
- **决策:** 编排器为纯 Python（if/else + try/except），零 AI 调用
- **理由:** Demo 阶段流程固定（5 Agent 串行），LangGraph 的学习成本和复杂度不匹配
- **升级路径:** 生产部署时切换到 LangGraph 图驱动编排
- **来源:** 行为逻辑文档编排器章节

---

### D-003: 生成模型用 DeepSeek，审计模型用 Qwen3

- **日期:** 2026-07-19（设计阶段）
- **决策:** Agent①-④ 用 DeepSeek V4-Flash（生成），Agent⑤ 用 Qwen3-Max（审计）
- **理由:** 审计模型的独立视角可减少"自己审计自己"的盲区
- **当前状态:** Qwen 未配置（环境变量为空），审计 Agent 降级为同模型校验，Demo 可运行

---

### D-004: Agent③ 使用 temperature=0 并缓存结果

- **日期:** 2026-07-19（设计阶段）
- **决策:** 岗位分析 Agent 设定 temperature=0，结果缓存
- **理由:** 同一岗位需求应产生完全一致的岗位画像；缓存减少重复 API 调用
- **来源:** 行为逻辑文档 Agent③ 章节

---

*——发现日志结束——*
*关联文件: [[task_plan]] | [[progress]]*
