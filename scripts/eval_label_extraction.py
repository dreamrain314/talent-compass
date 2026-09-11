# -*- coding: utf-8 -*-
"""Multi-arm label-extraction evaluation tool.

Formalizes the three-arm comparison prototype into a reusable evaluator:
given one or more arms (each a list of run JSON files, glob patterns allowed),
print per-arm P / R / F1 round means with a mean+-std noise band, plus a
per-concept rounds-hit matrix aggregated by (employee_id, matched_label)
across the union of labels seen in any arm (so 0/N rows are visible).

Metric definitions (locked by tests/test_eval_label_extraction.py):
  P   = TP / len(path_c items); TP = items with in_ground_truth == true
  R   = path_c.recall_at_gt / path_c.total_gt_labels
        (file-level keys; cross-checked against per-employee dedup hits)
  F1  = 2*P*R / (P+R), 0.0 when P+R == 0
  std = statistics.stdev (sample std); n < 2 rounds -> WARNING, band shows n/a

Read-only tool: writes no files; all results go to stdout.
"""
import argparse
import glob
import json
import statistics
import sys


def expand_arm_spec(spec):
    """Parse 'name=path1,path2,...' (each path may be a glob pattern)."""
    if "=" not in spec:
        raise SystemExit("ERROR: --arm expects NAME=path1,path2,... got: %r" % spec)
    name, _, paths_str = spec.partition("=")
    name = name.strip()
    if not name:
        raise SystemExit("ERROR: empty arm name in --arm %r" % spec)
    files = []
    for pattern in paths_str.split(","):
        pattern = pattern.strip()
        if not pattern:
            continue
        matches = sorted(glob.glob(pattern))
        if not matches:
            raise SystemExit("ERROR: no file matches pattern: %s" % pattern)
        files.extend(matches)
    if not files:
        raise SystemExit("ERROR: arm %r has no input files" % name)
    return name, files


def round_metrics(data, src):
    """Compute (P, R, F1) for one run file; return cross-check warning if any."""
    pc = data.get("path_c") or {}
    items = []
    for pe in data.get("per_employee") or []:
        items.extend(pe.get("path_c") or [])
    tp = sum(1 for it in items if it.get("in_ground_truth") is True)
    precision = tp / len(items) if items else 0.0

    recall_at_gt = pc.get("recall_at_gt")
    total_gt = pc.get("total_gt_labels")
    recall = recall_at_gt / total_gt if total_gt else 0.0

    denom = precision + recall
    f1 = 2 * precision * recall / denom if denom else 0.0

    dedup_hits = 0
    for pe in data.get("per_employee") or []:
        dedup_hits += len({it.get("matched_label") for it in (pe.get("path_c") or [])
                           if it.get("in_ground_truth") is True})
    warning = None
    if recall_at_gt is not None and dedup_hits != recall_at_gt:
        warning = ("WARNING: %s: file-level recall_at_gt=%s != per-employee dedup hits=%s"
                   % (src, recall_at_gt, dedup_hits))
    return precision, recall, f1, warning


def concept_hits(data):
    """(employee_id, matched_label) -> hit-in-this-round (dedup within round)."""
    hits = {}
    for pe in data.get("per_employee") or []:
        eid = pe.get("employee_id")
        for it in pe.get("path_c") or []:
            key = (eid, it.get("matched_label"))
            hits[key] = hits.get(key, False) or (it.get("in_ground_truth") is True)
    return hits


def fmt_band(values):
    """Format 'mean+-std' noise band; sample std undefined for n < 2 -> n/a."""
    mean = statistics.mean(values)
    if len(values) < 2:
        return "%s±n/a" % format(mean, ".4f")
    return "%s±%s" % (format(mean, ".4f"), format(statistics.stdev(values), ".4f"))


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(
        description="Per-arm P/R/F1 label-extraction evaluation (stdout only, writes nothing).")
    parser.add_argument("--arm", action="append", required=True,
                        metavar="NAME=FILE1,FILE2,...",
                        help="arm definition; each FILE may be a glob pattern (repeatable)")
    args = parser.parse_args(argv)

    arms = [expand_arm_spec(spec) for spec in args.arm]

    stats = {}
    all_keys = set()
    for name, files in arms:
        p_list, r_list, f_list = [], [], []
        key_round_hits = {}
        for path in files:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
            p, r, f, warning = round_metrics(data, path)
            p_list.append(p)
            r_list.append(r)
            f_list.append(f)
            if warning:
                print(warning)
            for key, hit in concept_hits(data).items():
                all_keys.add(key)
                if hit:
                    key_round_hits[key] = key_round_hits.get(key, 0) + 1
        stats[name] = (p_list, r_list, f_list, key_round_hits, len(files))

    names = [name for name, _ in arms]
    for name in names:
        p_list, r_list, f_list, _, n_rounds = stats[name]
        print("====== %s (n=%s rounds) ======" % (name, n_rounds))
        print("%s: P=%s R=%s F1=%s  (round means)" % (
            name, format(statistics.mean(p_list), ".4f"),
            format(statistics.mean(r_list), ".4f"),
            format(statistics.mean(f_list), ".4f")))
        print("%s noise band (mean±std): P=%s R=%s F1=%s" % (
            name, fmt_band(p_list), fmt_band(r_list), fmt_band(f_list)))
        if n_rounds < 2:
            print("WARNING: %s: n=%s round(s); sample std undefined, noise band shows n/a"
                  % (name, n_rounds))
        print()

    print("====== per-concept rounds-hit matrix (n/N) ======")
    for eid, label in sorted(all_keys, key=lambda k: (str(k[0]), str(k[1]))):
        cells = " ".join(
            "%s=%s/%s" % (nm, stats[nm][3].get((eid, label), 0), stats[nm][4])
            for nm in names)
        print("%s %s: %s" % (eid, label, cells))


if __name__ == "__main__":
    main()
