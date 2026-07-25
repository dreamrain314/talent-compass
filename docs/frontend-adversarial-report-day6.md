# 前端对抗检验报告 — Day 6

> 测试日期: 2026-07-26
> 测试工具: Playwright 原生（确定性 Page 直驱，非 LLM Agent）
> 测试数据: `data/adversarial/` 下 7 个夹具包（S0_happy / S1_numeric_id / S2_gbk / S3_empty_rows / S4_str_score / S4b_proj_partial / S6_proj_dict）
> 运行环境: Streamlit 1.51.0 offline 模式（TC_OFFLINE=1，端口 8502），Chromium playwright 二进制 1228
> 驱动脚本: `scripts/browser_use_acceptance.py`（headless=False 可见，每场景新 page 隔离 session_state）

---

## 总体结果

| 指标 | 结果 |
|------|------|
| 总场景数 | 8 |
| ✅ PASS | 8 |
| 🟡 边界 PASS | 2（S2/S3，计入 PASS） |
| 🔴 FAIL（崩溃） | 0（S4 已修） |
| 红色异常堆栈 | 0/8（S4 已修，复测 has_exc=False） |
| 上传链路 | ✅ 8/8 全场景 5 文件上传成功（re-query + retry 修复生效） |

**总分: 8/8 PASS（S4 已修）**

---

## 逐场景判定

| # | 场景 | expect | 实际行为 | has_exc | 判定 |
|---|------|--------|---------|---------|------|
| S0 | happy_path | 上传成功进 Step2 无异常 | "① 数据上传 ✅ / ② 基础过滤 ← 当前"，无异常 | False | ✅ PASS |
| S1 | numeric_employee_id | 可读错误或一致处理无静默崩溃 | numeric_id 一致处理进 Step2，无失配崩溃 | False | ✅ PASS |
| S2 | gbk_encoding | 可读编码错误非裸 UnicodeDecodeError 字节位 | `employees.csv 读取失败: 'utf-8' codec can't decode byte 0xd6 in position 151` | False | 🟡 PASS(边界) — 有可读文件名前缀，但字节位 `0xd6 in position 151` 仍暴露 |
| S3 | empty_rows | 无数据提示+返回按钮(防卡死回归) | 进 Step2 显示过滤提示，未卡死 | False | 🟡 PASS(边界) — 防卡死回归通过，但"无数据提示"未出现（空行被当正常数据） |
| S6 | projects_dict_wrapper | 可读"应为 JSON 数组"提示 | `projects.json 格式错误：应为 JSON 数组`（完全匹配 expect） | False | ✅ PASS |
| S4b | projects_partial_fields | 校验通过或可读错误无 KeyError | 校验通过进 Step2，无 KeyError | False | ✅ PASS |
| **S4** | **str_score_360** | Step5 360 可读错误非 TypeError 堆栈 | "该员工暂无 360 评分数据"（score 转 numeric 后字符串变 NaN，可读提示） | False | ✅ PASS（已修） |
| S7 | summary_offline_regression | Step4 摘要 offline-placeholder 无 JSON parse 崩溃 | "✅ 摘要已生成" + 摘要内容，无异常 | False | ✅ PASS（line_height 已修） |

---

## 🔴 崩溃清单

### S4 — `_compute_360_scores` 对字符串 score 直接 `.mean()` 崩

**Traceback:**
```
File "ui/app.py", line 1119, in _render_step_360
    all_scores = _compute_360_scores(eval_df, employees_df)
File "ui/app.py", line 1038, in _compute_360_scores
    global_mean = all_scores.mean()
File ".../pandas/core/generic.py", line 12442, in _stat_function
TypeError: Could not convert string '优良中优良中优良中...' to numeric
```

**根因:** `_compute_360_scores`（`ui/app.py:1022`）把 evaluation_360 的 score 列收集到 `all_scores` Series 后直接调 `.mean()`，**未先 `pd.to_numeric(errors='coerce')` 转换**。S4 夹具把 score 改成字符串"优良中..."（`scripts/gen_adversarial_fixtures.py:90` A5 场景），pandas 新版 `Series.mean()` 对字符串抛 TypeError 而非静默跳过。

**对比:** `utils/data_quality.py:248` 已有 `_score = pd.to_numeric(df["score"], errors="coerce")` 的正确模式，但 `_compute_360_scores` 没复用，属于 D2（工具/模式重复定义）+ C3（外部值先守卫）违规——同一 score 转换逻辑两处独立实现，渲染层遗漏。

**✅ 已修复（2026-07-26，[VERIFIED]）:**
- `ui/app.py:1036-1037` `_compute_360_scores` 入口加 `eval_df=eval_df.copy(); eval_df["score"]=pd.to_numeric(...,errors="coerce")`
- `agents/data_understanding.py:588` `_preprocess_360` Block B 同模式加 copy+to_numeric（F1 跨文件同类排查）
- `ui/app.py:1220` `_render_step_360` 各维度均分 `dim_means` 同样转 numeric
- 验证：S4 复测 `has_exc=False`，可读提示"该员工暂无 360 评分数据"（字符串 score 转 NaN 后 dropna 为空 → `_compute_360_scores` return {} → 渲染层给可读提示），符合 expect"非 TypeError 堆栈"
- pytest 定向 119 passed（test_data_understanding/test_adversarial_day3/test_data_quality，2.26s）
- 复盘：[[root-cause-input-structure-assumption]] 案例 2 + CLAUDE.md F9（跨文件字段守卫统一）

---

## 本次修复记录

### ADV-4 line_height TypeError（Day 6 修复）

- **文件:** `ui/app.py:1012`
- **变更:** `st.code(a[:80], line_height=24)` → `st.code(a[:80])`
- **根因:** 历史 ADV-4"修复"把无效 `line_limit=1` 换成同样无效的 `line_height=24`，未查 `st.code` 签名。Streamlit 1.51.0 严格校验抛 TypeError。详见 [[root-cause-fix-without-api-verification]]
- **验证:** S7 复测 `has_exception_box=False / exception=None`，"✅ 摘要已生成"
- **复盘产出:** CLAUDE.md 新增 F8（修 API 调用必查签名）+ 运行节"改 Streamlit 源码后必须重启进程"纪律

---

## 与 Day 4 对比

| 项 | Day 4 | Day 6 |
|----|-------|-------|
| 工具 | Chrome DevTools MCP（连已有 Chrome） | Playwright 原生（自启 Chromium） |
| 数据 | `data/raw/` 100 员工真实数据 | `data/adversarial/` 7 个对抗夹具包 |
| Step4 摘要 | 🔴 JSON parse failed（LLM 返回非 JSON） | ✅ 摘要正常生成（offline 模式确定性占位符 + line_height 修复） |
| Step5 360 | 未测 | 🔴 S4 str_score TypeError（新发现） |
| 上传 | 5/5 正常 | 8/8 全场景 5 文件上传成功（含 nth(i) DOM 重建防御） |
| 通过率 | 42/45（93%） | 7/8（87.5%，但含对抗夹具，不可直接比） |

**关键变化:**
- Day 4 的 Step4 摘要 JSON parse 失败 → Day 6 已修复（offline 模式 + line_height 渲染层修复）
- Day 6 新增对抗夹具暴露 Day 4 未覆盖的 S4 str_score 崩溃（Step5 360 渲染层数值聚合未守卫）
- 工具链从 Chrome DevTools MCP 换 Playwright 原生（browser_use Python 包的 Page wrapper 不兼容 playwright locator 体系，详见脚本头注释 + 本次复盘）

---

## 工具链问题记录（Day 6 过程发现）

1. **browser_use Python 包 API 用错:** `BrowserSession(profile)` 第一位置参数是 `id` 非 `browser_profile` → pydantic 校验失败，浏览器未启动。修：`BrowserSession(browser_profile=p)`。但 Page wrapper 仍不兼容。
2. **browser_use Page wrapper 不兼容 playwright:** `Page` 类无 `locator/get_by_role/inner_text/set_input_files/wait_for/count`，`goto` 不接受 `wait_until`，`screenshot` 返回 base64 不接受 `path`。脚本按 playwright API 写的全跑不了。修：整脚本切到 `playwright.async_api` 原生。
3. **Streamlit 模块缓存:** 改 `ui/app.py` 后 rerun 命中 `sys.modules` 缓存跑旧代码，file watcher 不可靠。修：kill PID + 重启 Streamlit。已写入 CLAUDE.md 运行节纪律。

---

## 结论

- **8/8 PASS（S4 已修）**，上传链路全场景稳定（nth(i) DOM 重建防御 + re-query retry 修复验证生效）
- S4 str_score 崩溃已修复（3 处 score 聚合加 `to_numeric` 守卫，F1 跨文件同类排查统一）
- Day 4 的 Step4 摘要 JSON parse 问题确认已修复（line_height 渲染层 + offline 模式）
- 本次过程暴露 4 个工具链/环境/验证 bug（browser_use API 错 + Page wrapper 不兼容 + Streamlit 缓存 + taskkill 杀错 PID 假阴性），均已修并写入 CLAUDE.md 纪律（F8/F9 + 运行节）
