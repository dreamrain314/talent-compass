# -*- coding: utf-8 -*-
"""Tests for scripts/eval_label_extraction.py — locks metric definitions.

Locked semantics (must not drift):
  P   = TP / len(path_c items); TP = items with in_ground_truth == true
  R   = file-level path_c.recall_at_gt / path_c.total_gt_labels (NOT recomputed;
        mismatch vs per-employee dedup hits only cross-checked with a WARNING)
  F1  = 2*P*R / (P+R), 0.0 when P+R == 0
  std = statistics.stdev (sample std); n < 2 rounds -> WARNING + 'n/a' in band

All fixtures are synthetic run JSONs built in tmp_path and fed through the
real CLI via subprocess (no mocking of the I/O path).
"""
import json
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "eval_label_extraction.py"


def make_item(label, hit):
    return {
        "concept": "concept-%s" % label,
        "matched_label": label,
        "mapping_source": "exact",
        "match_confidence": 0.9,
        "is_new_label": False,
        "in_ground_truth": hit,
    }


def make_run(hit_labels, all_labels, recall_at_gt, total_gt_labels, eid="E1"):
    """One run file: employee eid, items = all_labels, hits = hit_labels."""
    items = [make_item(lbl, lbl in hit_labels) for lbl in all_labels]
    return {
        "path_c": {
            "recall_at_gt": recall_at_gt,
            "total_gt_labels": total_gt_labels,
        },
        "per_employee": [
            {"employee_id": eid, "path_c": items, "ground_truth_count": total_gt_labels}
        ],
    }


def write_runs(tmp_path, name, runs):
    paths = []
    for i, run in enumerate(runs):
        p = tmp_path / ("%s_r%s.json" % (name, i))
        p.write_text(json.dumps(run, ensure_ascii=False), encoding="utf-8")
        paths.append(str(p))
    return ",".join(paths)


def run_cli(arm_specs):
    argv = [sys.executable, str(SCRIPT)]
    for spec in arm_specs:
        argv += ["--arm", spec]
    proc = subprocess.run(argv, capture_output=True)
    return proc.returncode, proc.stdout.decode("utf-8"), proc.stderr.decode("utf-8", "replace")


def test_exact_prf1_mean_and_std(tmp_path):
    # 3 rounds with P=R=F1 = 0.25 / 0.5 / 0.75 (binary-clean values):
    # means = 0.5 exactly, sample stdev = 0.25 exactly.
    labels = ["L1", "L2", "L3", "L4"]
    rounds = [
        make_run(hit_labels=["L1"], all_labels=labels, recall_at_gt=1, total_gt_labels=4),
        make_run(hit_labels=["L1", "L2"], all_labels=labels, recall_at_gt=2, total_gt_labels=4),
        make_run(hit_labels=["L1", "L2", "L3"], all_labels=labels,
                 recall_at_gt=3, total_gt_labels=4),
    ]
    arm = write_runs(tmp_path, "a", rounds)
    code, out, err = run_cli(["a=%s" % arm])
    assert code == 0, err
    assert "a: P=0.5000 R=0.5000 F1=0.5000  (round means)" in out
    assert "a noise band (mean±std): P=0.5000±0.2500 R=0.5000±0.2500 F1=0.5000±0.2500" in out
    assert "WARNING" not in out  # 3 consistent rounds: no warnings


def test_r_uses_file_level_key_and_crosschecks(tmp_path):
    # recall_at_gt=2 (file-level) vs 1 dedup hit: R must use the file-level
    # key (2/4=0.5), and the mismatch must surface as a WARNING.
    labels = ["L1", "L2", "L3", "L4"]
    run = make_run(hit_labels=["L1"], all_labels=labels, recall_at_gt=2, total_gt_labels=4)
    arm = write_runs(tmp_path, "b", [run])
    code, out, err = run_cli(["b=%s" % arm])
    assert code == 0, err
    assert "b: P=0.2500 R=0.5000" in out          # P=1/4, R=file-level 2/4
    assert "WARNING" in out and "dedup hits=1" in out


def test_single_round_warns_and_std_na(tmp_path):
    run = make_run(hit_labels=["L1"], all_labels=["L1", "L2"], recall_at_gt=1, total_gt_labels=2)
    arm = write_runs(tmp_path, "solo", [run])
    code, out, err = run_cli(["solo=%s" % arm])
    assert code == 0, err
    assert "WARNING: solo: n=1 round(s); sample std undefined, noise band shows n/a" in out
    assert "P=0.5000±n/a" in out  # std representation pinned to 'n/a'


def test_empty_path_c_no_division_by_zero(tmp_path):
    run = {
        "path_c": {"recall_at_gt": 0, "total_gt_labels": 0},
        "per_employee": [{"employee_id": "E9", "path_c": [], "ground_truth_count": 0}],
    }
    arm = write_runs(tmp_path, "empty", [run])
    code, out, err = run_cli(["empty=%s" % arm])
    assert code == 0, err
    assert "empty: P=0.0000 R=0.0000 F1=0.0000  (round means)" in out
    assert "empty noise band (mean±std): P=0.0000±n/a R=0.0000±n/a F1=0.0000±n/a" in out


def test_matrix_union_shows_zero_rows(tmp_path):
    # (E1, L1) hit in arm a, never mapped in arm b -> b must still show 0/1.
    run_a = make_run(hit_labels=["L1"], all_labels=["L1", "L2"], recall_at_gt=1, total_gt_labels=2)
    run_b = make_run(hit_labels=["L2"], all_labels=["L2"], recall_at_gt=1, total_gt_labels=2)
    arm_a = write_runs(tmp_path, "a", [run_a])
    arm_b = write_runs(tmp_path, "b", [run_b])
    code, out, err = run_cli(["a=%s" % arm_a, "b=%s" % arm_b])
    assert code == 0, err
    assert "E1 L1: a=1/1 b=0/1" in out
    assert "E1 L2: a=0/1 b=1/1" in out


def test_writes_no_files_and_has_no_output_option(tmp_path):
    run = make_run(hit_labels=["L1"], all_labels=["L1", "L2"], recall_at_gt=1, total_gt_labels=2)
    arm = write_runs(tmp_path, "ro", [run])
    before = sorted(p.name for p in tmp_path.iterdir())
    code, out, err = run_cli(["ro=%s" % arm])
    assert code == 0, err
    after = sorted(p.name for p in tmp_path.iterdir())
    assert before == after  # negative: no new files anywhere in the run dir
    proc = subprocess.run([sys.executable, str(SCRIPT), "--help"], capture_output=True)
    assert b"--output" not in proc.stdout  # negative: no output-file option exists
