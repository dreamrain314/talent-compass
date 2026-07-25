"""第一阶段流水线：基础过滤 → Agent① 数据理解

串联 BasicFilter 和 Agent① (DataUnderstanding)，输出融合 JSON。

用法：
    # 使用默认过滤条件 (pipeline_config/filter_conditions.json)
    python scripts/run_pipeline_phase1.py

    # 跳过过滤，直接处理全量 100 人
    python scripts/run_pipeline_phase1.py --skip-filter

    # 指定自定义过滤条件文件
    python scripts/run_pipeline_phase1.py --filter my_conditions.json

    # 指定数据目录（默认 data/raw）
    python scripts/run_pipeline_phase1.py --data-dir data/raw

扩展接口（为后续 Agent②③④ 预留，当前静默接受）：
    --agent2         准备 Agent② 输入（仅输出路径，不执行）
    --agent3         准备 Agent③ 输入
    --agent4         准备 Agent④ 输入
    --agent2-config  指定 Agent② 配置文件路径

依赖：
    config.py 中的路径常量（RAW_DATA_DIR, INTERMEDIATE_DIR, PIPELINE_CONFIG_DIR）
"""
import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

# ── 项目路径 ──────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config import (
    RAW_DATA_DIR,
    INTERMEDIATE_DIR,
    PIPELINE_CONFIG_DIR,
    AGENT_DATAUNDERSTANDING_TIMEOUT,
)
from filter.basic_filter import BasicFilter
from agents.data_understanding import DataUnderstanding
from orchestrator.pipeline import PipelineRunner
from utils.logger import generate_trace_id


# ── 数据文件映射 ──────────────────────────────────────────────────────────────
# 与 Agent① 的输入 schema 要求一致
DATA_FILES = {
    "employees": "employees.csv",
    "performance": "performance.csv",
    "projects": "projects.json",
    "training": "training.csv",
    "evaluation_360": "evaluation_360.csv",
}


def load_data_paths(data_dir: Path) -> dict[str, str]:
    """构建数据文件路径字典，校验文件存在性。"""
    paths = {}
    for key, filename in DATA_FILES.items():
        fp = data_dir / filename
        if not fp.exists():
            print(f"  ❌ 文件不存在: {fp}")
            sys.exit(1)
        paths[key] = str(fp)
    return paths


def load_filter_conditions(filter_path: Path | None) -> dict | None:
    """加载过滤条件 JSON 文件。文件不存在或解析失败 → 返回 None。"""
    if filter_path is None:
        return None
    if not filter_path.exists():
        print(f"  ⚠ 过滤条件文件不存在: {filter_path}，跳过过滤")
        return None
    try:
        with open(filter_path, "r", encoding="utf-8-sig") as f:
            conditions = json.load(f)
        if not isinstance(conditions, dict):
            print(f"  ⚠ 过滤条件格式错误（非 dict），跳过过滤")
            return None
        print(f"  ✓ 加载过滤条件: {len(conditions)} 项")
        return conditions
    except (json.JSONDecodeError, OSError) as e:
        print(f"  ⚠ 过滤条件文件读取失败: {e}，跳过过滤")
        return None


def apply_filter(employees_path: str, performance_path: str,
                 conditions: dict) -> pd.DataFrame | None:
    """应用基础过滤，返回过滤后的员工 DataFrame。"""
    print(f"  ── 过滤前: 加载数据...")
    employees_df = pd.read_csv(employees_path, dtype={"employee_id": str})
    performance_df = pd.read_csv(performance_path, dtype={"employee_id": str})
    print(f"    员工总数: {len(employees_df)}")

    bf = BasicFilter(employees_df, performance_df)
    result = bf.apply(conditions)

    total_after = result["total_after"]
    total_before = result["total_before"]
    print(f"  ── 过滤结果: {total_after}/{total_before} 人通过")

    skipped = result.get("skipped_conditions", [])
    if skipped:
        print(f"  ⚠ 跳过的条件: {skipped}")

    for log_entry in result["filter_log"]:
        cond = log_entry["condition"]
        removed = log_entry["removed_count"]
        note = log_entry.get("note", "")
        note_str = f" — {note}" if note else ""
        print(f"    {cond}: 移除 {removed} 人{note_str}")

    if total_after == 0:
        print("  ❌ 全部员工被过滤，建议放宽条件")
        return None

    records = result["filtered_employees"]
    return pd.DataFrame(records)


def save_filtered_employees(df: pd.DataFrame, trace_id: str) -> str:
    """将过滤后的员工表写入临时 CSV，返回路径。"""
    out_dir = INTERMEDIATE_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = out_dir / f"filtered_employees_{timestamp}_{trace_id}.csv"
    # 确保 employee_id 为字符串写入
    df["employee_id"] = df["employee_id"].astype(str)
    df.to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"  ✓ 过滤结果写入: {out_path}")
    return str(out_path)


def run_agent1(agent_input: dict, trace_id: str) -> dict:
    """通过 PipelineRunner 运行 Agent①，返回流水线结果。"""
    agent = DataUnderstanding()
    runner = PipelineRunner([agent])
    print(f"  ── Agent① 数据理解 (timeout={AGENT_DATAUNDERSTANDING_TIMEOUT}s)...")

    t_start = time.perf_counter()
    pipeline_result = runner.run(agent_input, trace_id=trace_id)
    elapsed = time.perf_counter() - t_start

    step = pipeline_result["steps"][0] if pipeline_result["steps"] else {}
    status = step.get("status", "?")
    duration = step.get("duration_ms", 0)
    print(f"  ── Agent① 完成: status={status}, {duration}ms ({elapsed:.1f}s 总耗时)")

    return pipeline_result


def print_summary(pipeline_result: dict, trace_id: str,
                  total_duration: float, filtered: bool) -> None:
    """打印执行摘要。"""
    step = pipeline_result["steps"][0] if pipeline_result["steps"] else {}
    agent_status = step.get("status", "?")
    final_output = pipeline_result.get("final_output", {})

    if isinstance(final_output, dict):
        employees = final_output.get("employees", [])
        llm_stats = final_output.get("llm_stats", {})
        data_quality = final_output.get("data_quality_report", {})
    else:
        employees = []
        llm_stats = {}
        data_quality = {}

    print(f"\n{'='*60}")
    print(f"  第一阶段流水线执行摘要")
    print(f"{'='*60}")
    print(f"  Trace ID:     {trace_id}")
    print(f"  过滤:         {'是' if filtered else '否（全量）'}")
    print(f"  Agent① 状态:  {agent_status}")
    print(f"  处理员工数:   {data_quality.get('total_employees', '?')}")
    print(f"  LLM 调用:     {llm_stats.get('succeeded', '?')}/{llm_stats.get('total', '?')} 成功")
    print(f"  Token 消耗:   {llm_stats.get('total_tokens', '?')}")
    print(f"  融合记录数:   {len(employees)}")
    print(f"  总耗时:       {total_duration:.1f}s")
    print(f"  中间结果:     {INTERMEDIATE_DIR}")
    print(f"{'='*60}\n")


def parse_args() -> argparse.Namespace:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(
        description="第一阶段流水线：基础过滤 → Agent① 数据理解",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
扩展接口（后续 Agent 使用，当前静默接受）：
  --agent2, --agent3, --agent4  预留 Agent 参数位
  --agent2-config               预留 Agent② 配置路径
        """,
    )
    parser.add_argument(
        "--data-dir", type=str, default=str(RAW_DATA_DIR),
        help=f"数据目录 (默认: {RAW_DATA_DIR})",
    )
    parser.add_argument(
        "--filter", type=str, default=None,
        help="过滤条件 JSON 文件路径 (默认: pipeline_config/filter_conditions.json)",
    )
    parser.add_argument(
        "--skip-filter", action="store_true",
        help="跳过基础过滤，直接处理全量数据",
    )
    parser.add_argument(
        "--output-dir", type=str, default=str(INTERMEDIATE_DIR),
        help=f"输出目录 (默认: {INTERMEDIATE_DIR})",
    )

    # ── 后续 Agent 扩展接口（当前静默接受，不报错） ──
    parser.add_argument("--agent2", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--agent3", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--agent4", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--agent2-config", type=str, default=None, help=argparse.SUPPRESS)

    return parser.parse_args()


def main() -> None:
    """主入口。"""
    args = parse_args()
    data_dir = Path(args.data_dir)
    trace_id = generate_trace_id()

    print(f"\n{'='*60}")
    print(f"  Talent Compass — 第一阶段流水线")
    print(f"  开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Trace ID: {trace_id}")
    print(f"{'='*60}\n")

    t_total = time.perf_counter()

    # ── Step 1: 加载数据文件路径 ──
    print("▶ 步骤 1/3: 加载数据文件")
    data_paths = load_data_paths(data_dir)
    for key, path in data_paths.items():
        print(f"  ✓ {key}: {Path(path).name}")

    # ── Step 2: 基础过滤（可选） ──
    print("\n▶ 步骤 2/3: 基础过滤")
    filter_path = None
    if not args.skip_filter:
        filter_path = Path(args.filter) if args.filter else (PIPELINE_CONFIG_DIR / "filter_conditions.json")
    conditions = load_filter_conditions(filter_path)

    if conditions:
        filtered_df = apply_filter(
            data_paths["employees"],
            data_paths["performance"],
            conditions,
        )
        if filtered_df is None or filtered_df.empty:
            print("  ❌ 无通过过滤的员工，退出")
            sys.exit(1)
        # 写入临时 CSV → 作为 Agent① 的 employees 输入
        temp_csv = save_filtered_employees(filtered_df, trace_id)
        agent_input = {**data_paths, "employees": temp_csv}
        filtered = True
    else:
        print("  跳过过滤，使用全量数据")
        agent_input = dict(data_paths)
        filtered = False

    # ── Step 3: Agent① 数据理解 ──
    print("\n▶ 步骤 3/3: Agent① 数据理解")
    pipeline_result = run_agent1(agent_input, trace_id)

    # ── 摘要 ──
    total_duration = time.perf_counter() - t_total
    print_summary(pipeline_result, trace_id, total_duration, filtered)


if __name__ == "__main__":
    main()