"""Pipeline readiness smoke test.

Checks that the pipeline can be scheduled without API Key.
Run after adding a new pipeline stage.

Usage:
    python scripts/validate_pipeline_readiness.py

Checks:
    1. Data file completeness (5 files exist)
    2. filter_conditions.json valid JSON
    3. BasicFilter importable + instantiable
    4. Agent1 importable + validate_input passes
    5. PipelineRunner constructable
    6. run_pipeline_phase1.py parses args correctly
    7. No missing scripts from dev guide
    8. data/intermediate/ empty check (non-blocking)
    9. Zero FutureWarning in tests

Exit code:
    0 - all checks passed
    1 - at least one critical check failed
"""
import json
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BOLD = "\033[1m"
RESET = "\033[0m"

PASS = f"{GREEN}[OK]{RESET}"
FAIL = f"{RED}[FAIL]{RESET}"
WARN = f"{YELLOW}[WARN]{RESET}"

results: list[dict] = []


def check(name: str, fn, critical: bool = True) -> None:
    t0 = time.perf_counter()
    try:
        ok, msg = fn()
        elapsed = time.perf_counter() - t0
        icon = PASS if ok else (FAIL if critical else WARN)
        tag = f" [{YELLOW}WARN{RESET}]" if not ok and not critical else ""
        print(f"  {icon} {name} ({elapsed*1000:.0f}ms){tag}")
        if not ok:
            print(f"      {msg}")
        results.append({"name": name, "ok": ok, "critical": critical, "msg": msg})
    except Exception as e:
        elapsed = time.perf_counter() - t0
        icon = FAIL if critical else WARN
        print(f"  {icon} {name} ({elapsed*1000:.0f}ms) - exception: {e}")
        results.append({"name": name, "ok": False, "critical": critical, "msg": str(e)})


def main() -> int:
    print(f"\n{BOLD}Pipeline Readiness Check{RESET}")
    print(f"  Project: {PROJECT_ROOT}")
    print(f"  Time:    {time.strftime('%Y-%m-%d %H:%M:%S')}\n")

    data_dir = PROJECT_ROOT / "data" / "raw"
    expected_files = ["employees.csv", "performance.csv", "projects.json",
                      "training.csv", "evaluation_360.csv"]

    # ── 1. Data file completeness ──
    print(f"{BOLD}[1/9] Data Files{RESET}")

    def _check_data_files():
        missing = [f for f in expected_files if not (data_dir / f).exists()]
        if missing:
            return False, f"missing: {', '.join(missing)}"
        sizes = {f: (data_dir / f).stat().st_size for f in expected_files}
        empty = [f for f, s in sizes.items() if s == 0]
        if empty:
            return False, f"empty: {', '.join(empty)}"
        return True, f"all {len(expected_files)} files exist"

    check("data files exist", _check_data_files)

    # ── 2. filter_conditions.json valid JSON ──
    print(f"\n{BOLD}[2/9] Filter Config{RESET}")
    filter_path = PROJECT_ROOT / "pipeline_config" / "filter_conditions.json"

    def _check_filter_json():
        if not filter_path.exists():
            return False, f"not found: {filter_path}"
        with open(filter_path, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return False, "top-level is not dict"
        if len(data) == 0:
            return False, "empty dict, need at least 1 condition"
        return True, f"valid JSON, {len(data)} conditions"

    check("filter_conditions.json", _check_filter_json)

    # ── 3. BasicFilter importable + instantiable ──
    print(f"\n{BOLD}[3/9] BasicFilter{RESET}")

    def _check_basic_filter():
        import pandas as pd
        from filter.basic_filter import BasicFilter
        emp = pd.DataFrame({"employee_id": ["T1"], "age": [30],
                            "political_status": ["member"], "major": ["CS"],
                            "years_of_service": [5], "current_level": ["P5"]})
        perf = pd.DataFrame({"employee_id": ["T1"], "year": [2024],
                             "performance_grade": ["B"]})
        bf = BasicFilter(emp, perf)
        result = bf.apply({"age_range": [25, 40]})
        assert result["total_before"] == 1
        return True, f"filter engine ok, {len(BasicFilter._SUPPORTED_KEYS)} conditions"

    check("BasicFilter import+instantiate", _check_basic_filter)

    # ── 4. Agent1 importable + validate_input passes ──
    print(f"\n{BOLD}[4/9] Agent1 DataUnderstanding{RESET}")

    def _check_agent1():
        from agents.data_understanding import DataUnderstanding
        agent = DataUnderstanding()
        emp_path = str(data_dir / "employees.csv")
        perf_path = str(data_dir / "performance.csv")
        proj_path = str(data_dir / "projects.json")
        train_path = str(data_dir / "training.csv")
        eval_path = str(data_dir / "evaluation_360.csv")
        test_input = {
            "employees": emp_path,
            "performance": perf_path,
            "projects": proj_path,
            "training": train_path,
            "evaluation_360": eval_path,
        }
        valid = agent.validate_input(test_input)
        if not valid:
            return False, "validate_input returned False (check column names)"
        return True, f"validate_input OK, timeout={agent.timeout_seconds}s"

    check("DataUnderstanding import+validate", _check_agent1)

    # ── 5. PipelineRunner constructable ──
    print(f"\n{BOLD}[5/9] PipelineRunner{RESET}")

    def _check_pipeline():
        from orchestrator.pipeline import PipelineRunner
        runner = PipelineRunner([])
        result = runner.run({"test": True}, trace_id="smoke-test")
        assert "trace_id" in result
        assert "status" in result
        assert "steps" in result
        return True, "PipelineRunner construct+dry-run OK"

    check("PipelineRunner construct", _check_pipeline)

    # ── 6. run_pipeline_phase1.py arg parsing ──
    print(f"\n{BOLD}[6/9] Pipeline Script{RESET}")

    def _check_phase1_script():
        script = PROJECT_ROOT / "scripts" / "run_pipeline_phase1.py"
        if not script.exists():
            return False, "scripts/run_pipeline_phase1.py not found"
        r = subprocess.run(
            [sys.executable, str(script), "--help"],
            capture_output=True, text=True, timeout=10,
        )
        if r.returncode != 0:
            return False, f"--help exit {r.returncode}: {r.stderr[:200]}"
        if "usage:" not in r.stdout.lower():
            return False, "--help output missing 'usage:'"
        r2 = subprocess.run(
            [sys.executable, str(script), "--skip-filter", "--help"],
            capture_output=True, text=True, timeout=10,
        )
        if r2.returncode != 0:
            return False, f"--skip-filter + --help exit {r2.returncode}"
        return True, "arg parsing OK, --skip-filter accepted"

    check("run_pipeline_phase1.py args", _check_phase1_script)

    # ── 7. Dev guide script completeness ──
    print(f"\n{BOLD}[7/9] Script Completeness{RESET}")

    def _check_scripts_completeness():
        scripts_dir = PROJECT_ROOT / "scripts"
        existing = {p.name for p in scripts_dir.glob("*.py")}
        required = {"generate_mock_data.py", "clean_intermediate.py",
                    "run_pipeline_phase1.py"}
        missing = required - existing
        # validate_phase1.py is a known missing item (non-blocking)
        dev_guide_known_missing = {"validate_phase1.py"}
        still_missing = missing - dev_guide_known_missing
        if still_missing:
            return False, f"missing scripts: {', '.join(sorted(still_missing))}"
        extra = existing - required
        extra_str = f", extra: {', '.join(sorted(extra))}" if extra else ""
        return True, f"scripts/ complete{extra_str}"

    check("dev guide script completeness", _check_scripts_completeness, critical=False)

    # ── 8. data/intermediate/ empty check ──
    print(f"\n{BOLD}[8/9] Intermediate Dir{RESET}")

    def _check_intermediate():
        interm_dir = PROJECT_ROOT / "data" / "intermediate"
        if not interm_dir.exists():
            return False, "directory not found"
        files = list(interm_dir.iterdir())
        json_files = [f for f in files if f.suffix == ".json"]
        csv_files = [f for f in files if f.suffix == ".csv"]
        if not json_files and not csv_files:
            return True, "empty (pipeline never run, OK)"
        return True, f"{len(json_files)} JSON + {len(csv_files)} CSV files"

    check("data/intermediate/", _check_intermediate, critical=False)

    # ── 9. Zero FutureWarning in tests ──
    print(f"\n{BOLD}[9/9] Zero Warning{RESET}")

    def _check_no_warning():
        r = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/",
             "-W", "error::FutureWarning", "--tb=short", "-q"],
            capture_output=True, text=True, timeout=120,
        )
        if r.returncode != 0:
            lines = r.stderr.split("\n") if r.stderr else r.stdout.split("\n")
            fail_lines = [l for l in lines if "FutureWarning" in l or "FAILED" in l]
            detail = "; ".join(fail_lines[:5]) if fail_lines else "check failed"
            return False, f"FutureWarning or test failure: {detail[:200]}"
        last_line = r.stdout.strip().split("\n")[-1] if r.stdout else ""
        return True, f"all passed: {last_line}"

    check("pytest -W error::FutureWarning", _check_no_warning)

    # ── Summary ──
    print(f"\n{'='*50}")
    print(f"  {BOLD}Summary{RESET}")
    passed = sum(1 for r in results if r["ok"])
    failed_critical = sum(1 for r in results if not r["ok"] and r["critical"])
    failed_warn = sum(1 for r in results if not r["ok"] and not r["critical"])
    total = len(results)

    if failed_critical > 0:
        print(f"  {BOLD}{RED}Result: {passed}/{total} passed ({failed_critical} failed, {failed_warn} warnings){RESET}")
        for r in results:
            if not r["ok"] and r["critical"]:
                print(f"    {FAIL} {r['name']}: {r['msg']}")
        return 1
    else:
        icon = GREEN if failed_warn == 0 else YELLOW
        print(f"  {BOLD}{icon}Result: {passed}/{total} passed ({failed_warn} warnings){RESET}")
        for r in results:
            if not r["ok"] and not r["critical"]:
                print(f"    {WARN} {r['name']}: {r['msg']}")
        print(f"  {GREEN}Pipeline ready{RESET}")
        return 0


if __name__ == "__main__":
    sys.exit(main())