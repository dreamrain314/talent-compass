# Day 5 实现计划：360 预处理增强 + 端到端验证脚本

> **日期**: 2026-07-25  
> **Git 基线**: commit `af87423`（Day 0-4 verified, 209/209 测试通过）  
> **用户确认**: UI 方案选择"完整展示"（新增独立 Step ⑤ 360 评价）

---

## 〇、前置条件

| 检查项 | 状态 |
|--------|:---:|
| Git 基线 af87423 | ✅ |
| 209/209 测试通过 | ✅ |
| evaluation_360.csv 含 year 列 | ✅ |
| 无 [AWAITING_VERIFY] 闸门 | ✅ |

## 一、修改文件清单与顺序

| # | 文件 | 操作 |
|:-:|------|------|
| 0 | 基线保存 | 运行 `_preprocess_360()` → `data/intermediate/baseline_360_v1.json` |
| 1 | `config.py` | 新增 360 常量（D1 修复） |
| 2 | `agents/data_understanding.py` | REQUIRED_COLUMNS加year；删内联常量改import；删ROLE_ADJUSTMENTS+bonus；重写`_preprocess_360()`；更新`_merge_records()`+`execute()` |
| 3 | `ui/app.py` | `_STEPS` 7→8；新增Step⑤"360评价"；新增`_render_step_360()` |
| 4 | `tests/test_data_understanding.py` | fixture加year；断言适配新结构；新增极端case |
| 5 | `tests/test_adversarial_day3.py` | fixture加year；断言适配；ROLE_WEIGHTS_BASELINE import改来源 |
| 6 | `scripts/validate_phase1.py` | 新建 |
| 7 | `docs/change-log.md` | 追加[AWAITING_VERIFY] |

---

## 二、config.py 新增常量

在文件末尾添加（不迁移 ROLE_ADJUSTMENTS 和 bonus 常量，它们被综合公式替代后直接删除）：

```python
# ── 360 评价预处理常量 ──────────────────────────────────────
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
```

---

## 三、data_understanding.py 核心修改

### 3.1 删除内联常量 + import 更新

- 删除 lines 44-67 的 `ROLE_WEIGHTS_BASELINE`、`SELF_ROLE`、`ROLE_ADJUSTMENTS`、`KNOWN_DIMENSIONS`
- 新增 `import math` + `from config import` 上述所有常量
- 全库引用替换: `SELF_ROLE`→`SELF_EVAL_ROLE`, `KNOWN_DIMENSIONS`→`KNOWN_360_DIMENSIONS`

### 3.2 REQUIRED_COLUMNS 加 "year"

```python
"evaluation_360": {"employee_id", "evaluator_id", "evaluator_role", "dimension",
                   "score", "comment", "year"},
```

### 3.3 `_preprocess_360()` 重写

**保留**: 全局统计、评价者均值、异常检测（用命名常量）、低样本量跳过、自评排除

**删除**: ROLE_ADJUSTMENTS、emp_job_type映射、同角色bonus、原始不归一化的weighted_sum/weight_total

**新增综合公式**:

```
Block A: year列守卫(C3) — 缺year→time_decay=1.0, logger.warning
Block B: 全局统计量(保持)
Block C: 异常检测(保持, 用ANOMALY_SIGMA_THRESHOLD)
Block D: 区分度权重 per evaluator — std=0且mean≤DISCRIMINATION_POSITIVE_THRESHOLD → 0.1, else 1.0
Block E: 每员工计算:
  year_coverage = CONFIDENCE_YEAR_COVERAGE[n_years]
  confidence = min(1, evaluators/CONFIDENCE_EVALUATOR_BASELINE) × (1-anomaly_ratio) × year_coverage
  每维度:
    raw_weight = role_weight × time_decay × discrimination × anomaly_penalty
    全敷衍守卫 → 等权平均(1/n)
    零除守卫 → 同上
    归一化 → normalized_weight = raw_weight / Σ(raw_weights)
    score = Σ(score_i × normalized_weight_i)
  result[emp_id] = {"dimensions": {dim: score}, "confidence": float}
Block F: _summary 新增 perfunctory_evaluators_count
```

**输出结构**: `{emp_id: {"dimensions": {dim: float}, "confidence": float}}` (原flat dict改为nested)

### 3.4 `_merge_records()` 适配

```python
scores_data = score_keys.get(emp_id, {})
if isinstance(scores_data, dict) and "dimensions" in scores_data:
    record["scores_360"] = scores_data["dimensions"]
    record["confidence_360"] = scores_data.get("confidence", None)
else:
    record["scores_360"] = scores_data if isinstance(scores_data, dict) else {}
    record["confidence_360"] = None
```

### 3.5 C1/E: ≥3条return末尾注释key集合

---

## 四、UI 修改

### 4.1 `_STEPS` 7→8

```python
_STEPS = [
    ("①","数据上传"), ("②","基础过滤"), ("③","数据质量"),
    ("④","文本摘要"), ("⑤","360评价"),  # ←新增
    ("⑥","画像生成"), ("⑦","岗位匹配"), ("⑧","推荐结果"),
]
```

### 4.2 render() 路由新增 `elif step == 5: _render_step_360()`

### 4.3 `_render_step_360()` 功能

- 前置条件: session_state 有 uploaded_data
- 员工选择器 + 5维度得分(数值+条形图) + 置信度(色彩编码) + 折叠权重因子详情 + 全局摘要

---

## 五、测试修改

### 5.1 两个 `_make_minimal_data()` 加 year

```python
from datetime import datetime
current_year = datetime.now().year
# eval_rows 生成加 year 循环:
for year in [current_year-2, current_year-1, current_year]:
    eval_rows.append({... "year": year})
```

### 5.2 断言更新

- `result[emp_id]` → `result[emp_id]["dimensions"]` (所有 TestRoleWeights, Test360WeightTotalZero 等)
- TestRoleWeights.test_tech_role_adjustment → **删除**(ROLE_ADJUSTMENTS已移除)
- TestMergeRecords → 加 `"confidence_360" in rec`
- test_adversarial_day3.py → `ROLE_WEIGHTS_BASELINE` import改来源: `from config import ROLE_WEIGHTS_BASELINE`

### 5.3 新增极端case (test_data_understanding.py)

`Test360ComprehensiveFormula` 类:
1. `test_3yr_full_no_anomaly` — confidence≈1.0, 权重≈角色基线
2. `test_1yr_perfunctory` — discrimination=0.1, 等权回退
3. `test_all_anomalous` — confidence≈0
4. `test_time_decay_recent_heavier` — 近年权重更高
5. `test_std0_high_not_penalized` — std=0但≥4 → disc=1.0
6. `test_no_year_fallback` — year缺失 → time_decay=1.0
7. `test_all_perfunctory_zero_div_guard` — 全敷衍 → 等权平均

### 5.4 新增对抗测试 (test_adversarial_day3.py)

- 全敷衍零除 / 无year列 / year含None/str / confidence边界

---

## 六、validate_phase1.py 设计

5 类检查 + `--skip-llm` 参数:
1. 数据完整性 (5文件+100行+year列)
2. 基础过滤 (6条件单独+组合+空结果)
3. Agent①数据 (≥5员工 merged record 含 scores_360+confidence_360)
4. 中间JSON (可parse)
5. 一致性 (过滤ID在Agent①输出中存在)

---

## 七、验证策略

1. **基线对比**: baseline_360_v1.json vs 新输出
2. **C6极端case**: 3极端输入+计算链打印
3. **回归**: `pytest tests/ -v -W error::FutureWarning` + `run_pipeline_phase1.py --skip-filter`
4. **闸门**: change-log.md [AWAITING_VERIFY] → pytest+对抗审查 → [VERIFIED]; 失败→git checkout

---

## 八、CLAUDE.md 规则检查点

| 规则 | 落地 |
|------|------|
| D1 | 内联常量→config.py |
| C1 | ≥3 return→key集合注释 |
| C3 | year列守卫; isinstance守卫 |
| C4 | discrimination边界穷举 |
| C6 | 3极端case+计算链 |
| E | 所有return路径结构一致 |
| V1 | change-log [AWAITING_VERIFY] |
| V2 | pytest+对抗审查; 失败→git checkout |
