"""Run directory layout and artifact writers.

Ground-truth isolation: rule-labeled quality-event labels are written to a
physically separated directory (data/_ground_truth/) inside a run. No feature,
model, or attribution code path may read from that directory; the only allowed
consumers are the copy-on-write writer in this module and the evaluation step,
which reads the labels after attribution has been finalized.

The isolation property is enforced by test_ground_truth_isolation.py: deleting
the _ground_truth directory and re-running attribution must leave every
attribution output byte-identical.
"""

from __future__ import annotations

import json
from pathlib import Path

GROUND_TRUTH_DIR = "_ground_truth"
TRUE_LABELS_FILENAME = "true_qa_labels.csv"

RUN_LAYOUT = {
    "data": "data",
    "results": "results",
    "log": "run.log",
    "manifest": "manifest.json",
    "excluded": "excluded_rows.csv",
}


def ensure_run_dir(run_dir: str | Path) -> Path:
    run = Path(run_dir)
    run.mkdir(parents=True, exist_ok=True)
    (run / RUN_LAYOUT["data"]).mkdir(exist_ok=True)
    (run / RUN_LAYOUT["data"] / GROUND_TRUTH_DIR).mkdir(exist_ok=True)
    (run / RUN_LAYOUT["results"]).mkdir(exist_ok=True)
    return run


def ground_truth_path(run_dir: str | Path) -> Path:
    return Path(run_dir) / RUN_LAYOUT["data"] / GROUND_TRUTH_DIR / TRUE_LABELS_FILENAME


def write_manifest(run_dir: str | Path, manifest: dict) -> None:
    path = Path(run_dir) / RUN_LAYOUT["manifest"]
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, sort_keys=True)
        fh.write("\n")


def read_manifest(run_dir: str | Path) -> dict:
    with open(Path(run_dir) / RUN_LAYOUT["manifest"], encoding="utf-8") as fh:
        return json.load(fh)


def append_log(run_dir: str | Path, lines: str) -> None:
    with open(Path(run_dir) / RUN_LAYOUT["log"], "a", encoding="utf-8") as fh:
        fh.write(lines)
        if not lines.endswith("\n"):
            fh.write("\n")


def write_excluded_rows(run_dir: str | Path, df) -> None:
    """Write the per-command excluded-rows ledger. df may be empty (header only)."""
    path = Path(run_dir) / RUN_LAYOUT["excluded"]
    df.to_csv(path, index=False)
