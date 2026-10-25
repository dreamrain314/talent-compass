# Day 8 冻结清单（Round 3 挑战版本，2026-10-24）

> 生成：2026-10-25T23:45:46｜依据预注册 §四：模型与映射文件、评分公式与权重、要求集与解析规则、阈值、依赖版本、种子、批处理配置、输入顺序全部定版记哈希；同分排序以员工 ID 稳定键

## 一、资产哈希（SHA256 前 16 位）

| 资产 | 哈希 | 说明 |
|------|------|------|
| `utils/coverage_engine.py` | `8ef701b24a1c88ed` | 覆盖引擎（两类划分/拆句/分池/矩阵/加分/k线性闸门/五类关系/等价表双向激活/字面包含快速通道） |
| `data/jobs/equivalence_table.json` | `c9305679c1e02a7d` | 人工核验等价表 v2.2（255+10+2 接桥映射/8 拆解组/1 减分对） |
| `data/jobs/alias_patches.json` | `b4dcc78c0c2b0c20` | 受控别名（4 对种子 + Python开发→Python） |
| `data/jobs/blind_gold_jobs.json` | `92d8f0cf90cf609e` | 旧 5 岗 JD（B02/B04 已按新金标重写，旧文存 _meta.revision） |
| `data/jobs/blind_gold_jobs_batch2.json` | `7c4dfbb6b51bf1b1` | 新 5 岗 JD（开发资产） |
| `data/jobs/agent_blind_jobs_v1.json` | `7962f3e1ce2f3b93` | agent 盲写 5 岗 C01-C05（泛化考卷） |
| `data/experiment/blind_test_gold.json` | `06669d14532765d9` | 金标映射（B01-B05 设计金标/JZ0036） |
| `data/experiment/blind_test_gold_batch2.json` | `3ea226bcd1c6c375` | 新 5 岗金标映射 |
| `data/intermediate/phase1_output.json` | `ca3d75cfef396ae9` | 员工池 59 人（4 设计金标+毛文风险+郑燕审计+5 探针测试员工） |
| `data/raw/projects.json` | `4d6f96bff32ecd6e` | 原始项目记录（设计金标/郑燕审计/毛文风险/探针员工注入） |
| `data/raw/employees.csv` | `831bc38b47007937` | 花名册（105 人：100 原始 + 5 探针测试员工） |
| `tests/test_coverage_engine.py` | `c6b3ae50e083d867` | 覆盖引擎测试 41 项 |
| `scripts/verify_typing_adjudication.py` | `8592ceed41e998e9` | 划界回归闸门（用户 83 条裁决=冻结真值） |
| `scripts/day35_coverage_smoke.py` | `9199e92551ae1a32` | 冒烟协议脚本 |
| `scripts/day9_blind_jobs_eval.py` | `49c8cef630963fa0` | 盲写验收跑分脚本 |
| `scripts/day67_equivalence_adjudication.py` | `a2a29b8b9d24ce9c` | 等价表离线裁决流程（LLM 提议→人工核验→入表） |
| `scripts/semantic_bridge_calibration.py` | `aa596954715c657f` | 语义桥校准（阈值 0.72 冻结依据） |
| `server/app.py` | `ab1e235c74f03bf0` | 本地工作台（已切新覆盖引擎 + 硬性过滤 + 启动预热） |

## 二、参数快照（冻结值）

```json
{
 "COVERAGE_JOB_WEIGHT_MATRIX": {
  "技术类": [
   70.0,
   15.0,
   15.0
  ],
  "职能类": [
   40.0,
   30.0,
   30.0
  ],
  "业务类": [
   45.0,
   35.0,
   20.0
  ],
  "创意类": [
   45.0,
   20.0,
   35.0
  ],
  "_default": [
   45.0,
   35.0,
   20.0
  ]
 },
 "COVERAGE_PREFERRED_K": 2.0,
 "COVERAGE_GATE_STEP": 0.05,
 "COVERAGE_SEMANTIC_BRIDGE_THRESHOLD": 0.72,
 "COVERAGE_RECALL_K": 3,
 "COVERAGE_W_MUST": 1.0,
 "COVERAGE_DEDUCTION_VALUE": 0.8,
 "EMBEDDING_MODEL_NAME": "BAAI/bge-small-zh-v1.5",
 "RERANKER_MODEL_NAME": "BAAI/bge-reranker-v2-m3"
}
```

## 三、冻结纪律

1. 上述资产与参数自本清单落盘起**冻结**：任何改动 = 重开事件，须记 eval_log（含理由与用户授权），并重跑本脚本更新哈希
2. 划界词典改动必须过 `verify_typing_adjudication.py` 83/83 闸门
3. 等价表改动必须走人工核验流程（LLM 提议→用户✓→版本化）
4. **Day 9-10 独立验收（新采岗位）期间零改动**——验收完成前本清单为唯一有效版本
5. 冒烟基线（2026-10-25，59 人池，拆句+线性闸门+语义桥后）：9/10 金标前五（B01#4 B02#2 B03#2 B04#4 B05#5 B06#1 B07#1 B08#1 B09#6 B10#4），B09 缺 3 项待用户裁决（ceiling_probe 复验 5/5 合成员工全要求 v=1：B01 96.8/B02 96.69/B03 89.72/B04 93.27/B05 94.63）

## 四、效力边界（预注册 §五 口径）

本清单资产在开发资产上校准（含考题重写/证据注入/接桥等 L3 拟合事件，均已记账 §十四-§十九）；其泛化证明唯一来源 = Day 9-10 新采岗位独立验收（nDCG@5 主指标 + 指定金标 Top-5 连续性指标）。

*脚本：scripts/day8_freeze_manifest.py（--check 复验哈希）｜共 18 项资产*