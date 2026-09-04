# E 方案模拟验证计划

## 目标
验证"层内正交重排版"（E 方案：T2=14 含尽责性 / T3=7 含合并后韧性与成长心态）的 argmax 命中率是否优于 D 方案（T2=83% / T3=81%）。

## Step 1：改 verify 脚本加 E 方案
文件：`scripts/verify_argmax_routing.py`
- 新增 `NEW_LABELS_T2`（14 标签完整 definition+keywords，按定稿表）
- 新增 `NEW_LABELS_T3`（7 标签完整 definition+keywords）
- 新增 `E_MERGE_MAP`（成长型思维/抗压韧性 → 韧性与成长心态）映射旧 TEST_CASES 的 GT
- 新增 `EXTRA_TEST_CASES`（尽责性、开放性、战略眼光、跨界整合潜力、影响力构建、韧性与成长心态 的 queries）
- 新增 `run_e()`：用 NEW_LABELS 构造矩阵，跑 (TEST_CASES 经 merge + EXTRA)
- `__main__` 末尾追加 E 方案运行段

## Step 2：跑模拟
```
python scripts/verify_argmax_routing.py
```
看 E 方案 T2/T3 命中率，与 D 方案同屏对比。

## Step 3：报告对比
- E 优于 D（T2>83% 且 T3>81%）→ 进入 Step 4 落地
- E 不优于 D → 回讨论（是否补 LLM 兜底或调结构）

## Step 4（若 E 通过）：落地
1. 改 `data/standard_label_library_v1.json` 为 E 方案标签集（直接改 v1 + git 备份）
2. 同步 `data/experiment/ground_truth_5.json`：成长型思维/抗压韧性→韧性与成长心态，删 T3 尽责性
3. 新增 `argmax_route()` 到 `utils/label_matching.py`
4. 改 `agents/profile_generation.py` 分流：T1 走旧 recall+rerank，T2/T3 走 argmax_route
5. `config.py` 加 `ARGMAX_TIERS` 常量
6. 改造 verify 脚本为读 json（删 OVERRIDES/MERGE 双源）
7. C2 闸门验证：`pytest tests/ -v` 全绿 + 新增 `TestArgmaxRoute` + 端到端 recall@GT ≥70%
8. tracking 三件套同步（progress.md / task-plan.md / change-log.md）

## 不做的事
- 本计划只执行 Step 1-3（验证），Step 4 等 E 方案验证通过后再启动
- 不动 json、不动 GT、不动 profile_generation.py，直到模拟结果出来
