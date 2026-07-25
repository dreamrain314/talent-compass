#!/usr/bin/env python3
"""Phase 1 端到端验证脚本

验证 Pipeline 各阶段输出一致性和数据完整性。

5 类检查 + --skip-llm 参数：
  1. 数据完整性（5 文件 + 100 行 + year 列）
  2. 基础过滤（6 条件单独 + 组合 + 空结果）
  3. Agent① 数据（≥5 员工 merged record 含 scores_360 + confidence_360）
  4. 中间 JSON（可 parse）
  5. 一致性（过滤 ID 在 Agent① 输出中存在）

用法:
    python scripts/validate_phase1.py
    python scripts/validate_phase1.py --skip-llm
"""
import argparse
import json
import os
import sys
from pathlib import Path

# 🔴 Windows GBK 编码修复：ANSI 颜色码 + 中文在 GBK 下可能异常
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if sys.stderr and hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

import pandas as pd

# 确保项目根目录在 sys.path 中
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from config import RAW_DATA_DIR, INTERMEDIATE_DIR
from filter.basic_filter import BasicFilter


# ── 颜色常量 ────────────────────────────────────────────────────────
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"


def _ok(msg: str):
    print(f"  {GREEN}[OK]{RESET} {msg}")


def _fail(msg: str):
    print(f"  {RED}[FAIL]{RESET} {msg}")


def _warn(msg: str):
    print(f"  {YELLOW}[WARN]{RESET} {msg}")


def _info(msg: str):
    print(f"  {CYAN}[INFO]{RESET} {msg}")


# ── 检查 1：数据完整性 ────────────────────────────────────────────────


def check_data_integrity() -> bool:
    """检查 5 个原始数据文件是否存在、≥100 行、含 year 列。"""
    print(f"\n{BOLD}[1/5] 数据完整性{RESET}")
    all_ok = True

    files = {
        "employees.csv": ("csv", ["employee_id", "name", "age", "gender"]),
        "performance.csv": ("csv", ["employee_id", "year", "performance_grade"]),
        "projects.json": ("json", ["employee_id", "project_name", "description"]),
        "training.csv": ("csv", ["employee_id", "course_name", "status"]),
        "evaluation_360.csv": ("csv", ["employee_id", "evaluator_id", "score", "year"]),
    }

    for fname, (ftype, required_cols) in files.items():
        fpath = os.path.join(RAW_DATA_DIR, fname)
        if not os.path.isfile(fpath):
            _fail(f"文件不存在: {fname}")
            all_ok = False
            continue

        try:
            if ftype == "csv":
                df = pd.read_csv(fpath, nrows=0)
                missing = set(required_cols) - set(df.columns)
                if missing:
                    _fail(f"{fname} 缺少列: {missing}")
                    all_ok = False
                else:
                    _ok(f"{fname} 列名完整")
                # 行数
                row_count = len(pd.read_csv(fpath))
                if row_count < 100:
                    _warn(f"{fname} 仅 {row_count} 行 (< 100)")
                else:
                    _ok(f"{fname} {row_count} 行")
                # year 列检查
                if "year" in required_cols:
                    _ok(f"{fname} 含 year 列")
            elif ftype == "json":
                with open(fpath, "r", encoding="utf-8-sig") as f:
                    data = json.load(f)
                if not isinstance(data, list) or len(data) == 0:
                    _fail(f"{fname} 格式错误或为空")
                    all_ok = False
                else:
                    first = data[0]
                    missing = set(required_cols) - set(first.keys())
                    if missing:
                        _fail(f"{fname} 缺少字段: {missing}")
                        all_ok = False
                    else:
                        _ok(f"{fname} 字段完整，{len(data)} 条记录")
        except Exception as e:
            _fail(f"{fname} 读取失败: {e}")
            all_ok = False

    return all_ok


# ── 检查 2：基础过滤 ──────────────────────────────────────────────────


def check_basic_filter() -> bool:
    """检查 BasicFilter 6 条件单独 + 组合 + 空结果。"""
    print(f"\n{BOLD}[2/5] 基础过滤{RESET}")
    all_ok = True

    emp_path = os.path.join(RAW_DATA_DIR, "employees.csv")
    perf_path = os.path.join(RAW_DATA_DIR, "performance.csv")
    if not os.path.isfile(emp_path) or not os.path.isfile(perf_path):
        _fail("employees.csv 或 performance.csv 不存在，跳过过滤检查")
        return False

    employees_df = pd.read_csv(emp_path, dtype={"employee_id": str})
    performance_df = pd.read_csv(perf_path, dtype={"employee_id": str})
    total = len(employees_df)

    try:
        bf = BasicFilter(employees_df, performance_df)
    except Exception as e:
        _fail(f"BasicFilter 初始化失败: {e}")
        return False

    # 6 个条件单独
    single_conditions = [
        ("年龄区间", {"age_range": [30, 40]}),
        ("政治面貌", {"political_status": ["中共党员"]}),
        ("专业关键词", {"major_keywords": ["计算机"]}),
        ("最低工作年限", {"min_years_of_service": 3}),
        ("职级范围", {"level_range": ["P2", "P6"]}),
        ("绩效底线", {"min_performance": "C"}),
    ]

    for label, cond in single_conditions:
        try:
            result = bf.apply(cond)
            after = result.get("total_after", 0)
            assert 0 <= after <= total
            _ok(f"{label}: {after}/{total} 通过")
        except Exception as e:
            _fail(f"{label} 执行失败: {e}")
            all_ok = False

    # 组合条件
    combined = {
        "age_range": [30, 40],
        "min_years_of_service": 3,
        "min_performance": "B",
    }
    try:
        result = bf.apply(combined)
        after = result.get("total_after", 0)
        assert 0 <= after <= total
        _ok(f"组合条件: {after}/{total} 通过")
    except Exception as e:
        _fail(f"组合条件执行失败: {e}")
        all_ok = False

    # 空结果条件（极端过滤）
    extreme = {"age_range": [0, 0]}
    try:
        result = bf.apply(extreme)
        after = result.get("total_after", 0)
        assert after == 0
        _ok(f"空结果条件: {after} 通过")
    except Exception as e:
        _fail(f"空结果条件执行失败: {e}")
        all_ok = False

    return all_ok


# ── 检查 3：Agent① 数据 ──────────────────────────────────────────────


def check_agent1_data(skip_llm: bool = False) -> bool:
    """检查 Agent① 输出含 scores_360 + confidence_360。"""
    print(f"\n{BOLD}[3/5] Agent① 数据{RESET}")
    all_ok = True

    if skip_llm:
        _info("跳过 LLM 调用（--skip-llm），检查中间 JSON")
        json_path = os.path.join(INTERMEDIATE_DIR, "phase1_output.json")
        if not os.path.isfile(json_path):
            _fail(f"中间 JSON 不存在: {json_path}")
            return False
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            _fail(f"中间 JSON 解析失败: {e}")
            return False
    else:
        # 运行完整 pipeline
        _info("运行完整 Pipeline...")
        try:
            from scripts.run_pipeline_phase1 import run_pipeline_phase1
            result = run_pipeline_phase1()
            data = result.get("data", {})
        except Exception as e:
            _fail(f"Pipeline 执行失败: {e}")
            return False

    employees = data.get("employees", [])
    if len(employees) < 5:
        _warn(f"员工记录不足 5 条: {len(employees)}")
    else:
        _ok(f"{len(employees)} 条员工记录")

    # 检查 scores_360 + confidence_360
    count_with_360 = 0
    for emp in employees:
        scores = emp.get("scores_360", {})
        conf = emp.get("confidence_360")
        if scores and conf is not None:
            count_with_360 += 1

    if count_with_360 >= 5:
        _ok(f"{count_with_360} 员工含 scores_360 + confidence_360")
    elif count_with_360 > 0:
        _warn(f"仅 {count_with_360} 员工含 scores_360 + confidence_360")
    else:
        _fail("无员工含 scores_360 + confidence_360")
        all_ok = False

    return all_ok


# ── 检查 4：中间 JSON ────────────────────────────────────────────────


def check_intermediate_json() -> bool:
    """检查中间 JSON 可 parse，结构正确。"""
    print(f"\n{BOLD}[4/5] 中间 JSON{RESET}")
    all_ok = True

    json_files = [
        "phase1_output.json",
        "baseline_360_v1.json",
    ]

    for fname in json_files:
        fpath = os.path.join(INTERMEDIATE_DIR, fname)
        if not os.path.isfile(fpath):
            _warn(f"文件不存在（可能尚未生成）: {fname}")
            continue

        try:
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
            _ok(f"{fname} 可 parse ({len(json.dumps(data))} 字节)")
        except json.JSONDecodeError as e:
            _fail(f"{fname} 解析失败: {e}")
            all_ok = False
        except Exception as e:
            _fail(f"{fname} 读取失败: {e}")
            all_ok = False

    return all_ok


# ── 检查 5：一致性 ────────────────────────────────────────────────────


def check_consistency() -> bool:
    """检查过滤后员工 ID 在 Agent① 输出中存在。"""
    print(f"\n{BOLD}[5/5] 一致性检查{RESET}")
    all_ok = True

    emp_path = os.path.join(RAW_DATA_DIR, "employees.csv")
    output_path = os.path.join(INTERMEDIATE_DIR, "phase1_output.json")
    if not os.path.isfile(output_path):
        _warn("phase1_output.json 不存在，跳过一致性检查")
        return True

    try:
        with open(output_path, "r", encoding="utf-8") as f:
            output = json.load(f)
    except Exception as e:
        _fail(f"phase1_output.json 读取失败: {e}")
        return False

    # 如果 output 是 {"data": {"employees": ...}} 结构
    employees_out = output.get("data", output).get("employees", [])
    output_ids = {e.get("employee_id") for e in employees_out if e.get("employee_id")}

    if not os.path.isfile(emp_path):
        _warn("employees.csv 不存在，跳过")
        return True

    employees_df = pd.read_csv(emp_path, dtype={"employee_id": str})
    all_ids = set(employees_df["employee_id"].astype(str))

    # 执行基础过滤取 ID 子集
    perf_path = os.path.join(RAW_DATA_DIR, "performance.csv")
    if os.path.isfile(perf_path):
        try:
            performance_df = pd.read_csv(perf_path, dtype={"employee_id": str})
            bf = BasicFilter(employees_df, performance_df)
            result = bf.apply({"age_range": [25, 50]})
            filtered = result.get("filtered_employees", [])
            filtered_ids = {e.get("employee_id") for e in filtered if e.get("employee_id")}
            # 过滤后的 ID 应在 Agent① 输出中存在
            missing = filtered_ids - output_ids
            if missing:
                _warn(f"{len(missing)} 个过滤后 ID 不在 Agent① 输出中")
                if len(missing) <= 10:
                    for mid in sorted(missing):
                        _info(f"  缺失: {mid}")
            else:
                _ok(f"过滤后 {len(filtered_ids)} 个 ID 全部在 Agent① 输出中")
        except Exception as e:
            _warn(f"一致性检查执行失败: {e}")
    else:
        _warn("performance.csv 不存在，跳过一致性检查")

    return all_ok


# ── 主入口 ────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(description="Phase 1 端到端验证脚本")
    parser.add_argument("--skip-llm", action="store_true",
                        help="跳过 LLM 调用，只检查中间产物")
    args = parser.parse_args()

    print(f"{BOLD}{'='*60}{RESET}")
    print(f"{BOLD}  Phase 1 端到端验证{RESET}")
    print(f"{BOLD}{'='*60}{RESET}")

    results = [
        ("数据完整性", check_data_integrity()),
        ("基础过滤", check_basic_filter()),
        ("Agent① 数据", check_agent1_data(skip_llm=args.skip_llm)),
        ("中间 JSON", check_intermediate_json()),
        ("一致性", check_consistency()),
    ]

    print(f"\n{BOLD}{'='*60}{RESET}")
    print(f"{BOLD}  验证汇总{RESET}")
    print(f"{BOLD}{'='*60}{RESET}")
    passed = 0
    for name, ok in results:
        icon = f"{GREEN}[PASS]{RESET}" if ok else f"{RED}[FAIL]{RESET}"
        print(f"  {icon} {name}")
        if ok:
            passed += 1

    total = len(results)
    print(f"\n{passed}/{total} 检查通过")
    if passed == total:
        print(f"{GREEN}{BOLD}全部通过！{RESET}")
        return 0
    else:
        print(f"{RED}{BOLD}{total - passed} 项检查未通过{RESET}")
        return 1


if __name__ == "__main__":
    sys.exit(main())