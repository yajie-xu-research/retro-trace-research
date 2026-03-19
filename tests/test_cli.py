"""CLI end-to-end: five commands, manifests, reproducibility, corruption."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pandas as pd
import pytest

from retro_trace.cli import main

MANIFEST_FIELDS = {
    "run_id", "stamp", "project", "status", "commit", "config_hash", "data_hash",
    "permissions_pointer", "operator", "input_rows", "excluded_rows", "rule_version",
    "command", "environment", "result_hash", "seed", "known_issues",
}


def _manifest(path: Path) -> dict:
    return json.loads((path / "manifest.json").read_text(encoding="utf-8"))


def test_five_commands_end_to_end(small_data, tmp_path):
    gen_out = tmp_path / "gen"
    rc = main(["generate-synthetic", "--output", str(gen_out), "--seed", "20250711"])
    assert rc == 0
    for name in ("events.csv", "quality_events.csv", "sample_classes.csv", "load_staffing.csv",
                 "cases.csv", "stage_map.csv", "params.json"):
        assert (gen_out / name).exists()

    rc = main(["validate", "--input", str(gen_out), "--out", str(tmp_path / "validation")])
    assert rc == 0
    assert (tmp_path / "validation" / "results" / "validation_report.csv").exists()

    attr_out = tmp_path / "attr"
    rc = main(["a1", "attribute", "--input", str(gen_out), "--out", str(attr_out)])
    assert rc == 0

    eval_out = tmp_path / "eval"
    rc = main(["a1", "evaluate", "--run", str(attr_out), "--out", str(eval_out)])
    assert rc == 0
    assert (eval_out / "run_receipt.json").exists()

    rc = main(["manifest", "inspect", "--run", str(attr_out)])
    assert rc == 0


def test_every_command_writes_manifest_log_and_excluded(small_data, tmp_path):
    gen_out = tmp_path / "gen"
    main(["generate-synthetic", "--output", str(gen_out), "--seed", "20250711"])
    for run in (gen_out,):
        assert (run / "manifest.json").exists()
        assert (run / "run.log").exists()
        assert (run / "excluded_rows.csv").exists()
    val_out = tmp_path / "validation"
    main(["validate", "--input", str(gen_out), "--out", str(val_out)])
    attr_out = tmp_path / "attr"
    main(["a1", "attribute", "--input", str(gen_out), "--out", str(attr_out)])
    eval_out = tmp_path / "eval"
    main(["a1", "evaluate", "--run", str(attr_out), "--out", str(eval_out)])
    for run in (val_out, attr_out, eval_out):
        assert (run / "manifest.json").exists()
        assert (run / "run.log").exists()
        assert (run / "excluded_rows.csv").exists()


def test_manifest_fields_and_status(attribute_run):
    manifest = _manifest(attribute_run)
    assert MANIFEST_FIELDS <= set(manifest)
    assert manifest["project"] == "retro-trace-research"
    assert manifest["status"] == "INTERNAL_RESEARCH"


def test_result_hash_reproducible(small_data, tmp_path):
    out_a = tmp_path / "attr_a"
    out_b = tmp_path / "attr_b"
    main(["a1", "attribute", "--input", str(small_data), "--out", str(out_a)])
    main(["a1", "attribute", "--input", str(small_data), "--out", str(out_b)])
    manifest_a = _manifest(out_a)
    manifest_b = _manifest(out_b)
    assert manifest_a["result_hash"] == manifest_b["result_hash"]
    assert manifest_a["data_hash"] == manifest_b["data_hash"]
    assert manifest_a["config_hash"] == manifest_b["config_hash"]
    # stamp is era-capped (fixed) across runs by design
    assert manifest_a["stamp"] == manifest_b["stamp"]


def test_result_hash_changes_with_input(small_data, tmp_path):
    altered = tmp_path / "altered"
    shutil.copytree(small_data, altered)
    cases = pd.read_csv(altered / "cases.csv", dtype=str)
    cases.loc[0, "released_at_utc"] = "2024-05-01T00:00:00Z"
    cases.to_csv(altered / "cases.csv", index=False)
    out_a = tmp_path / "attr_a"
    out_b = tmp_path / "attr_b"
    main(["a1", "attribute", "--input", str(small_data), "--out", str(out_a)])
    main(["a1", "attribute", "--input", str(altered), "--out", str(out_b)])
    assert _manifest(out_a)["data_hash"] != _manifest(out_b)["data_hash"]


def test_validate_detects_corruption(small_data, tmp_path):
    corrupted = tmp_path / "corrupted"
    shutil.copytree(small_data, corrupted)
    qe = pd.read_csv(corrupted / "quality_events.csv", dtype=str)
    qe.loc[0, "event_type"] = "BOGUS"
    qe.to_csv(corrupted / "quality_events.csv", index=False)
    val_out = tmp_path / "validation_corrupt"
    rc = main(["validate", "--input", str(corrupted), "--out", str(val_out)])
    assert rc == 1
    report = pd.read_csv(val_out / "results" / "validation_report.csv", dtype=str)
    assert (report["status"] == "FAIL").any()


def test_conclusion_states_association_not_causation(small_data, tmp_path):
    attr_out = tmp_path / "attr"
    eval_out = tmp_path / "eval"
    main(["a1", "attribute", "--input", str(small_data), "--out", str(attr_out)])
    main(["a1", "evaluate", "--run", str(attr_out), "--out", str(eval_out)])
    summary = (eval_out / "results" / "summary.md").read_text(encoding="utf-8")
    assert "association, not causation" in summary
    receipt = json.loads((eval_out / "run_receipt.json").read_text(encoding="utf-8"))
    assert "not causation" in receipt["conclusion"]
    assert "statistical association" in receipt["conclusion"]
