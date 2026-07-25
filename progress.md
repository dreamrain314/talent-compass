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

闸门清掉前禁止继续编码新功能。
