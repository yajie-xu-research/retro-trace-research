"""Ground-truth isolation: attribution must not depend on the quality-event
labels.

The rule-labeled labels are staged under data/_ground_truth/ inside a run.
No
feature, model, or attribution code path may read that directory; deleting it
must leave every attribution output byte-identical.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from retro_trace.cli import main
from retro_trace.common.run_layout import GROUND_TRUTH_DIR, ground_truth_path


def test_deleting_ground_truth_leaves_attribution_byte_identical(small_data, tmp_path):
    out_a = tmp_path / "run_a"
    out_b = tmp_path / "run_b"
    assert main(["a1", "attribute", "--input", str(small_data), "--out", str(out_a)]) == 0
    assert (out_a / "data" / GROUND_TRUTH_DIR).exists()

    # snapshot outputs with ground truth present
    def snapshot(run: Path) -> dict:
        files = {
            "attribution_rows.csv": run / "results" / "attribution_rows.csv",
            "subgroup_association.csv": run / "results" / "subgroup_association.csv",
            "comparability_ledger.csv": run / "results" / "comparability_ledger.csv",
            "baselines_comparison.csv": run / "results" / "baselines_comparison.csv",
            "excluded_rows.csv": run / "excluded_rows.csv",
        }
        snap = {name: path.read_bytes() for name, path in files.items()}
        manifest = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
        # the command string embeds this run's own output path (run identity)
        manifest.pop("command", None)
        snap["manifest_fields"] = json.dumps(manifest, sort_keys=True).encode()
        return snap

    snap_a = snapshot(out_a)
    assert ground_truth_path(out_a).exists()

    # delete the isolated labels and re-run to a fresh directory
    shutil.rmtree(out_a / "data" / GROUND_TRUTH_DIR)
    assert main(["a1", "attribute", "--input", str(small_data), "--out", str(out_b)]) == 0
    snap_b = snapshot(out_b)

    # run identity: same seed + data + config => same hashes, status and stamp
    manifest_a = json.loads((out_a / "manifest.json").read_text(encoding="utf-8"))
    manifest_b = json.loads((out_b / "manifest.json").read_text(encoding="utf-8"))
    for key in ("result_hash", "data_hash", "config_hash", "status", "stamp", "seed"):
        assert manifest_a[key] == manifest_b[key], f"{key} differs after removing ground truth"

    for name in snap_a:
        assert snap_a[name] == snap_b[name], f"{name} differs after removing ground truth"


def test_only_whitelisted_modules_touch_the_ground_truth_dir(repo):
    """Grep the source: the isolated directory may only appear in the layout
    constants, the copy-on-write writer, and the evaluation reader."""
    whitelist = {
        repo / "src" / "retro_trace" / "common" / "run_layout.py",
        repo / "src" / "retro_trace" / "a1" / "ground_truth_io.py",
        repo / "src" / "retro_trace" / "a1" / "evaluate.py",
        repo / "src" / "retro_trace" / "cli.py",  # orchestrator stages the isolated copy
    }
    offenders = []
    for path in (repo / "src").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "_ground_truth" in text or GROUND_TRUTH_DIR in text:
            if path not in whitelist:
                offenders.append(path)
    assert offenders == [], f"unexpected modules referencing the ground-truth dir: {offenders}"
