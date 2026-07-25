"""生成前端对抗性检验夹具（data/adversarial/<scenario>/）

每个场景一个 5 文件夹具包（employees/performance/projects/training/evaluation_360），
非目标文件用 data/raw 真实子集（前 N 行，保证 UI 加载快），目标文件按场景畸形化。
不动 data/raw/。

用法：python scripts/gen_adversarial_fixtures.py
"""
import json
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW = PROJECT_ROOT / "data" / "raw"
OUT = PROJECT_ROOT / "data" / "adversarial"

# 每场景非目标文件的子集行数（保证 UI 加载快 + 360 样本足够）
SUBSET_ROWS = 40


def _read_raw_csv(name: str) -> pd.DataFrame:
    return pd.read_csv(RAW / name, dtype={"employee_id": str, "evaluator_id": str},
                      encoding="utf-8-sig")


def _read_raw_projects() -> list:
    with open(RAW / "projects.json", encoding="utf-8-sig") as f:
        return json.load(f)


def _write_csv(df: pd.DataFrame, path: Path, encoding: str = "utf-8-sig") -> None:
    """写 CSV。utf-8-sig 带 BOM（与 raw 一致），gbk 用于 A2 编码场景。"""
    df.to_csv(path, index=False, encoding=encoding)


def _write_projects(data, path: Path) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _base_bundle() -> dict:
    """5 文件基准子集（前 SUBSET_ROWS 行），供场景覆写目标文件。"""
    emp = _read_raw_csv("employees.csv").head(SUBSET_ROWS)
    perf = _read_raw_csv("performance.csv").head(SUBSET_ROWS * 3)
    train = _read_raw_csv("training.csv").head(SUBSET_ROWS * 3)
    eval_ = _read_raw_csv("evaluation_360.csv").head(SUBSET_ROWS * 5)
    proj = _read_raw_projects()[:SUBSET_ROWS]
    return {"employees": emp, "performance": perf, "training": train,
            "evaluation_360": eval_, "projects": proj}


def _write_bundle(bundle: dict, scenario_dir: Path) -> None:
    scenario_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(bundle["employees"], scenario_dir / "employees.csv")
    _write_csv(bundle["performance"], scenario_dir / "performance.csv")
    _write_csv(bundle["training"], scenario_dir / "training.csv")
    _write_csv(bundle["evaluation_360"], scenario_dir / "evaluation_360.csv")
    _write_projects(bundle["projects"], scenario_dir / "projects.json")


# ── 各场景：覆写目标文件 ──────────────────────────────────────────────

def s1_numeric_id(bundle):
    """A1: employee_id 改纯数字 → pd.read_csv 无 dtype 读成 int64。"""
    emp = bundle["employees"].copy()
    emp["employee_id"] = range(1001, 1001 + len(emp))
    bundle["employees"] = emp
    # 同步 performance/projects/eval 的 id 以便交叉匹配仍能连（验"静默失配"用 raw id）
    # 这里故意不同步 → 验 employee_id 类型不一致导致的失配
    return bundle


def s2_gbk(bundle):
    """A2: employees.csv 用 GBK 编码 → UnicodeDecodeError。"""
    # _write_bundle 默认 utf-8-sig；此场景需特殊写法，返回标记
    bundle["__encoding_override__"] = ("employees", "gbk")
    return bundle


def s3_empty_rows(bundle):
    """A8: employees 仅表头无数据行 → 空表 + 卡死回归。"""
    emp = bundle["employees"].iloc[0:0].copy()  # 保留列名，去数据
    bundle["employees"] = emp
    return bundle


def s4_str_score(bundle):
    """A5: evaluation_360 的 score 列改字符串 → Step5 数值崩溃。"""
    ev = bundle["evaluation_360"].copy()
    ev["score"] = ["优", "良", "中", "差", "特优"][0:len(ev)] if len(ev) <= 5 else (
        ["优", "良", "中"] * (len(ev) // 3 + 1))[:len(ev)]
    bundle["evaluation_360"] = ev
    return bundle


def s6_proj_dict_wrapper(bundle):
    """A3: projects.json 顶层包一层 dict → 非 JSON 数组。"""
    bundle["projects"] = {"projects": bundle["projects"]}
    return bundle


def s_proj_partial_fields(bundle):
    """A4: projects 数组首元素字段全、第二个缺 description。"""
    proj = bundle["projects"]
    if len(proj) >= 2:
        proj[1] = {k: v for k, v in proj[1].items() if k != "description"}
    bundle["projects"] = proj
    return bundle


SCENARIOS = {
    "S1_numeric_id": s1_numeric_id,
    "S2_gbk": s2_gbk,
    "S3_empty_rows": s3_empty_rows,
    "S4_str_score": s4_str_score,
    "S6_proj_dict": s6_proj_dict_wrapper,
    "S4b_proj_partial": s_proj_partial_fields,
}


def main() -> None:
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print("生成对抗性夹具 → data/adversarial/")
    OUT.mkdir(parents=True, exist_ok=True)
    for name, fn in SCENARIOS.items():
        bundle = _base_bundle()
        bundle = fn(bundle)
        enc_override = bundle.pop("__encoding_override__", None)
        scen_dir = OUT / name
        scen_dir.mkdir(parents=True, exist_ok=True)
        if enc_override:
            col, enc = enc_override
            # 非目标文件正常写
            for k, df in bundle.items():
                if k == col:
                    continue
                if k == "projects":
                    _write_projects(df, scen_dir / "projects.json")
                else:
                    _write_csv(df, scen_dir / f"{k}.csv")
            # 目标文件用指定编码
            _write_csv(bundle[col], scen_dir / f"{col}.csv", encoding=enc)
        else:
            _write_bundle(bundle, scen_dir)
        files = sorted(p.name for p in scen_dir.iterdir())
        print(f"  ✓ {name}: {files}")
    # S0 happy path 直接用 raw 子集（无需畸形）
    s0 = _base_bundle()
    _write_bundle(s0, OUT / "S0_happy")
    print(f"  ✓ S0_happy: {sorted(p.name for p in (OUT/'S0_happy').iterdir())}")
    print(f"\n夹具根目录: {OUT}")


if __name__ == "__main__":
    main()
