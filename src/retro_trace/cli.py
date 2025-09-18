"""retro-trace command line interface.

Commands:
  retro-trace generate-synthetic --output synthetic_data/ --seed 20250710
  retro-trace validate --input synthetic_data/ --config configs/qa_labels.yaml
  retro-trace a1 attribute --input synthetic_data/ --out runs/a1_attribution/
  retro-trace a1 evaluate --run runs/a1_attribution/ --out runs/a1_evaluation/
  retro-trace manifest inspect --run runs/a1_attribution/

Every producing command writes, into its output directory: manifest.json,
per-row result files, excluded_rows.csv, and run.log. The manifest carries
the deterministic result hash; utc / operator / command are outside the
byte-identity scope.
"""

from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yaml

from . import __version__
from .a1 import dictionary as dictionary_mod
from .a1 import engine as engine_mod
from .a1 import evaluate as evaluate_mod
from .a1 import generator as generator_mod
from .a1 import ground_truth_io, label_rules as label_rules_mod
from .a1 import validate as validate_mod
from .common import enums
from .common.hashing import data_hash, result_hash, sha256_file, sha256_text
from .common.run_layout import (
    append_log,
    ensure_run_dir,
    read_manifest,
    write_excluded_rows,
    write_manifest,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = REPO_ROOT / "configs"
QA_CONFIG_PATH = CONFIG_DIR / "qa_labels.yaml"
LABEL_RULES_PATH = CONFIG_DIR / "label_rules.yaml"

ATTRIBUTE_INPUT_FILES = ["events.csv", "cases.csv", "sample_classes.csv", "load_staffing.csv", "stage_map.csv"]

COMMAND_STR = ""


ERA_STAMP = "2026-06-30T00:00:00Z"  # wall clock is not recorded; all package timestamps are era-capped


def utc_now() -> str:
    return ERA_STAMP


def _current_commit() -> str:
    """Return the repository HEAD hash, or "unknown" outside a git tree."""
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return proc.stdout.strip()
    except Exception:
        pass
    return "unknown"


def _load_configs() -> tuple[dict, dict]:
    with open(QA_CONFIG_PATH, encoding="utf-8") as fh:
        qa_config = yaml.safe_load(fh)
    with open(LABEL_RULES_PATH, encoding="utf-8") as fh:
        label_rules = yaml.safe_load(fh)
    return qa_config, label_rules


def _config_hash() -> str:
    payload = (
        sha256_file(QA_CONFIG_PATH)
        + "\n"
        + sha256_file(LABEL_RULES_PATH)
        + "\n"
        + dictionary_mod.compute_pin()
    )
    return sha256_text(payload)


def _manifest(
    run_id: str,
    data_hash_value: str,
    result_hash_value: str,
    seed: int,
    input_rows: int,
    excluded_rows: int,
    known_issues: list[str],
) -> dict:
    qa_config, label_rules = _load_configs()
    return {
        "run_id": run_id,
        "stamp": utc_now(),
        "project": "retro-trace-research",
        "status": enums.RUN_STATUS_INTERNAL,
        "commit": _current_commit(),
        "config_hash": _config_hash(),
        "data_hash": data_hash_value,
        "permissions_pointer": enums.PERMISSIONS_POINTER,
        "operator": enums.OPERATOR,
        "input_rows": input_rows,
        "excluded_rows": excluded_rows,
        "rule_version": f"{qa_config['config_version']}|{label_rules['rule_version']}",
        "command": COMMAND_STR,
        "environment": f"{platform.python_implementation()} {platform.python_version()}",
        "result_hash": result_hash_value,
        "seed": seed,
        "known_issues": known_issues,
    }


def _result_hash_from_files(files: dict[str, Path], config_hash: str, data_hash_value: str, seed: int, rule_version: str) -> str:
    file_hashes = {name: sha256_file(path) for name, path in sorted(files.items())}
    return result_hash(config_hash, data_hash_value, seed, rule_version, file_hashes)


def cmd_generate_synthetic(args) -> int:
    out = Path(args.output)
    seed = int(args.seed)
    tables = generator_mod.generate_tables(seed=seed)
    file_hashes = generator_mod.write_tables(tables, out)
    generator_mod.write_params(out, seed, tables)

    data_hash_value = data_hash(
        out, ["events.csv", "cases.csv", "sample_classes.csv", "load_staffing.csv", "stage_map.csv", "params.json"]
    )
    qa_config, label_rules = _load_configs()
    rule_version = f"{qa_config['config_version']}|{label_rules['rule_version']}"
    result_hash_value = result_hash(data_hash_value, data_hash_value, seed, rule_version, file_hashes)
    run_id = f"run-gen-{seed}-{data_hash_value[:12]}"
    manifest = _manifest(
        run_id, data_hash_value, result_hash_value, seed, input_rows=0, excluded_rows=0,
        known_issues=["deterministic per seed; regenerating with the same seed reproduces the tables byte for byte"],
    )
    write_manifest(out, manifest)
    empty_excluded = pd.DataFrame(columns=["case_key", "reason"])
    write_excluded_rows(out, empty_excluded)
    append_log(
        out,
        f"{manifest['stamp']} generate-synthetic seed={seed} n_cases={len(tables['case_table'])} "
        f"n_delay={int((tables['quality_events']['event_type']=='DELAY').sum())} "
        f"n_rework={int((tables['quality_events']['event_type']=='REWORK').sum())} data_hash={data_hash_value}",
    )
    print(f"wrote {out}")
    print(
        f"n_cases={len(tables['case_table'])} "
        f"n_delay={int((tables['quality_events']['event_type']=='DELAY').sum())} "
        f"n_rework={int((tables['quality_events']['event_type']=='REWORK').sum())} "
        f"n_two_stage={int((tables['case_table']['plant_type']=='AMBIGUOUS').sum())}"
    )
    return 0


def cmd_validate(args) -> int:
    qa_config, label_rules = _load_configs()
    config_path = Path(args.config)
    if config_path.name == QA_CONFIG_PATH.name and config_path != QA_CONFIG_PATH:
        with open(config_path, encoding="utf-8") as fh:
            qa_config = yaml.safe_load(fh)
    result = validate_mod.validate_package(args.input, qa_config, label_rules)
    out = Path(args.out) if getattr(args, "out", None) else REPO_ROOT / "outputs" / "runs" / "validation"
    ensure_run_dir(out)
    checks = pd.DataFrame(result["checks"])
    checks.to_csv(out / "results" / "validation_report.csv", index=False)
    excluded = pd.DataFrame(result["excluded_rows"])
    write_excluded_rows(out, excluded)
    n_fail = int((checks["status"] == "FAIL").sum())
    data_hash_value = data_hash(
        args.input, ["events.csv", "cases.csv", "sample_classes.csv", "load_staffing.csv", "stage_map.csv"]
    )
    seed = _read_seed(Path(args.input))
    rule_version = f"{qa_config['config_version']}|{label_rules['rule_version']}"
    result_hash_value = _result_hash_from_files(
        {"validation_report.csv": out / "results" / "validation_report.csv",
         "excluded_rows.csv": out / "excluded_rows.csv"},
        _config_hash(), data_hash_value, seed, rule_version,
    )
    run_id = f"run-val-{data_hash_value[:12]}"
    manifest = _manifest(
        run_id, data_hash_value, result_hash_value, seed,
        input_rows=len(pd.read_csv(Path(args.input) / "events.csv")),
        excluded_rows=len(excluded),
        known_issues=[],
    )
    write_manifest(out, manifest)
    append_log(out, f"{manifest['stamp']} validate status={'FAIL' if n_fail else 'PASS'} checks={len(checks)} failed={n_fail}")
    print(f"validate: {len(checks)} checks, {n_fail} failed -> {out}")
    if n_fail:
        for _, row in checks[checks["status"] == "FAIL"].iterrows():
            print(f"  FAIL {row['check_id']}: {row['detail']}")
        return 1
    return 0


def cmd_attribute(args) -> int:
    data_dir = Path(args.input)
    out = Path(args.out)
    ensure_run_dir(out)
    qa_config, label_rules = _load_configs()
    seed = _read_seed(data_dir)

    artifacts = engine_mod.run_attribution(data_dir, qa_config, label_rules)

    results_dir = out / "results"
    artifacts["attribution_rows"].to_csv(results_dir / "attribution_rows.csv", index=False)
    artifacts["subgroup_association"].to_csv(results_dir / "subgroup_association.csv", index=False)
    artifacts["comparability_ledger"].to_csv(results_dir / "comparability_ledger.csv", index=False)
    artifacts["baselines_comparison"].reset_index().to_csv(results_dir / "baselines_comparison.csv", index=False)
    write_excluded_rows(out, artifacts["excluded_rows"])

    gt_path = ground_truth_io.stage_ground_truth(data_dir, out)

    data_hash_value = data_hash(data_dir, ATTRIBUTE_INPUT_FILES)
    rule_version = f"{qa_config['config_version']}|{label_rules['rule_version']}"
    files = {
        "attribution_rows.csv": results_dir / "attribution_rows.csv",
        "subgroup_association.csv": results_dir / "subgroup_association.csv",
        "comparability_ledger.csv": results_dir / "comparability_ledger.csv",
        "baselines_comparison.csv": results_dir / "baselines_comparison.csv",
        "excluded_rows.csv": out / "excluded_rows.csv",
    }
    result_hash_value = _result_hash_from_files(files, _config_hash(), data_hash_value, seed, rule_version)
    run_id = f"run-a1-{seed}-{data_hash_value[:12]}"
    manifest = _manifest(
        run_id, data_hash_value, result_hash_value, seed,
        input_rows=len(pd.read_csv(data_dir / "events.csv")),
        excluded_rows=len(artifacts["excluded_rows"]),
        known_issues=[
            "stage localization is a statistical association, not a causal claim",
            "attribution uses occurred_at only; known_at is carried for log compatibility with the shared dictionary",
            "quality-event labels are staged under data/_ground_truth/ and are read only by the evaluation step",
        ],
    )
    write_manifest(out, manifest)
    n_localized = int((artifacts["attribution_rows"]["decision"] == "LOCALIZED").sum())
    n_abstain = int((artifacts["attribution_rows"]["decision"] == "ABSTAIN").sum())
    append_log(
        out,
        f"{manifest['stamp']} attribute rows={len(artifacts['attribution_rows'])} "
        f"localized={n_localized} abstain={n_abstain} excluded={len(artifacts['excluded_rows'])} "
        f"ground_truth_staged={gt_path} result_hash={result_hash_value}",
    )
    print(f"attribution rows={len(artifacts['attribution_rows'])} localized={n_localized} abstain={n_abstain}")
    print(f"ground truth staged at {gt_path}")
    print(f"run manifest -> {out / 'manifest.json'}")
    return 0


def cmd_evaluate(args) -> int:
    run_dir = Path(args.run)
    out = Path(args.out)
    ensure_run_dir(out)
    manifest = read_manifest(run_dir)
    result = evaluate_mod.evaluate_run(run_dir)
    metrics = result["metrics"]

    results_dir = out / "results"
    result["engine_eval"].to_csv(results_dir / "evaluation_report.csv", index=False)
    result["baseline_eval"].to_csv(results_dir / "baseline_report.csv", index=False)
    _write_metrics_csv(metrics, results_dir / "metrics.csv")

    excluded = result["engine_eval"][
        result["engine_eval"]["outcome"].isin(["FN_INSUFFICIENT_BASELINE", "FN_NOT_COMPARABLE"])
    ][["case_key", "event_type", "reason"]].copy()
    excluded["detail"] = "excluded from localization denominators"
    write_excluded_rows(out, excluded)

    seed = int(manifest["seed"])
    upstream = manifest["result_hash"]
    rule_version = f"{manifest['rule_version']}|upstream:{upstream}"
    files = {
        "evaluation_report.csv": results_dir / "evaluation_report.csv",
        "baseline_report.csv": results_dir / "baseline_report.csv",
        "metrics.csv": results_dir / "metrics.csv",
        "excluded_rows.csv": out / "excluded_rows.csv",
    }
    result_hash_value = _result_hash_from_files(
        files, manifest["config_hash"], manifest["data_hash"], seed, rule_version
    )
    run_id = f"run-eval-{manifest['run_id'][-12:]}"
    manifest_eval = _manifest(
        run_id, manifest["data_hash"], result_hash_value, seed,
        input_rows=len(result["engine_eval"]),
        excluded_rows=len(excluded),
        known_issues=["metrics are statistical associations on this data package only; external validation is not obtained"],
    )
    write_manifest(out, manifest_eval)

    receipt = {
        "run_id": run_id,
        "upstream_run": str(run_dir),
        "upstream_result_hash": upstream,
        "result_hash": result_hash_value,
        "data_hash": manifest["data_hash"],
        "config_hash": manifest["config_hash"],
        "seed": seed,
        "rule_version": manifest["rule_version"],
        "metrics": metrics,
        "conclusion": metrics["conclusion"],
    }
    with open(out / "run_receipt.json", "w", encoding="utf-8") as fh:
        json.dump(receipt, fh, indent=2, sort_keys=True)
        fh.write("\n")

    summary = _summary_text(metrics)
    with open(results_dir / "summary.md", "w", encoding="utf-8") as fh:
        fh.write(summary)
    append_log(out, f"{manifest_eval['stamp']} evaluate result_hash={result_hash_value}")
    print(summary)
    return 0


def cmd_manifest_inspect(args) -> int:
    manifest = read_manifest(args.run)
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


def _read_seed(data_dir: Path) -> int:
    params = data_dir / "params.json"
    if params.exists():
        with open(params, encoding="utf-8") as fh:
            return int(json.load(fh)["seed"])
    return generator_mod.SEED_DEFAULT


def _write_metrics_csv(metrics: dict, path: Path) -> None:
    rows = []
    for key, value in metrics.items():
        rows.append({"metric": key, "value": json.dumps(value, sort_keys=True)})
    pd.DataFrame(rows).to_csv(path, index=False)


def _summary_text(metrics: dict) -> str:
    lines = [
        "# Attribution evaluation summary",
        "",
        "All numbers below are statistical associations computed on this data",
        "package. They are not causal claims: a localized stage is a candidate",
        "focus area for quality review, not proof that the stage caused the",
        "event (association, not causation).",
        "",
        f"- flagged rows evaluated: {metrics['n_cases_flagged']}",
        f"- rule-labeled quality events: {metrics['n_labeled_quality_events']}",
        f"- flag precision: {metrics['flag_precision']:.4f}",
        f"- flag recall: {metrics['flag_recall']:.4f}",
        f"- localized rows: {metrics['n_localized']}",
    ]
    agreement = metrics["localization_agreement"]
    lines.append(f"- localization agreement (LOCALIZED): {agreement:.4f}" if agreement is not None else "- localization agreement: n/a")
    for tier in ("LOW", "HIGH"):
        t = metrics[f"tier_{tier}"]
        if t["agreement"] is not None:
            lines.append(
                f"- tier {tier}: agreement {t['agreement']:.4f} (n={t['n']}, "
                f"chance {t['chance']:.4f}, exact binomial p={t['p_value_vs_chance']:.4f})"
            )
        else:
            lines.append(f"- tier {tier}: n={t['n']} (no localized rows)")
    lines.append(
        f"- false positives: multi-basis localized {metrics['fp_localized_on_multi_basis']}, "
        f"wrong stage {metrics['fp_localized_wrong_stage']}, flag without a matching label {metrics['fp_flag_no_label']}"
    )
    lines.append(
        f"- false negatives: ambiguous false-abstain {metrics['fn_ambiguous_false_abstain']}, "
        f"insufficient baseline {metrics['fn_insufficient_baseline']}, "
        f"not comparable {metrics['fn_not_comparable']}"
    )
    lines.append(
        f"- ambiguity recall: {metrics['ambiguity_recall']} of {metrics['n_labeled_multi_basis']} "
        f"multi-basis labels"
    )
    if metrics["rejection_rate"] is not None:
        lines.append(f"- rejection rate: {metrics['rejection_rate']:.4f} by reason {metrics['rejection_by_reason']}")
    lines.append("")
    lines.append("## Baselines (same universe, no abstention)")
    for method, stats in metrics["baselines"].items():
        agreement = stats["agreement_single_basis"]
        lines.append(
            f"- {method}: single-basis agreement "
            f"{agreement:.4f} (n={stats['n']})" if agreement is not None else f"- {method}: n={stats['n']}"
        )
    if metrics["correct_and_confident_engine"] is not None:
        lines.append("")
        lines.append("## Correct-and-confident (correct localizations over all flagged rows)")
        lines.append(f"- engine: {metrics['correct_and_confident_engine']:.4f}")
        for method, value in metrics["correct_and_confident_baselines"].items():
            lines.append(f"- {method}: {value:.4f}" if value is not None else f"- {method}: n/a")
    lines.append("")
    lines.append(metrics["conclusion"])
    return "\n".join(lines) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="retro-trace")
    parser.add_argument("--version", action="version", version=f"retro-trace {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p_gen = sub.add_parser("generate-synthetic")
    p_gen.add_argument("--output", required=True)
    p_gen.add_argument("--seed", default=generator_mod.SEED_DEFAULT)
    p_gen.set_defaults(func=cmd_generate_synthetic)

    p_val = sub.add_parser("validate")
    p_val.add_argument("--input", required=True)
    p_val.add_argument("--config", default=str(QA_CONFIG_PATH))
    p_val.add_argument("--out", default=None)
    p_val.set_defaults(func=cmd_validate)

    p_a1 = sub.add_parser("a1")
    a1_sub = p_a1.add_subparsers(dest="a1_command", required=True)
    p_attr = a1_sub.add_parser("attribute")
    p_attr.add_argument("--input", required=True)
    p_attr.add_argument("--out", required=True)
    p_attr.set_defaults(func=cmd_attribute)
    p_eval = a1_sub.add_parser("evaluate")
    p_eval.add_argument("--run", required=True)
    p_eval.add_argument("--out", required=True)
    p_eval.set_defaults(func=cmd_evaluate)

    p_man = sub.add_parser("manifest")
    man_sub = p_man.add_subparsers(dest="manifest_command", required=True)
    p_inspect = man_sub.add_parser("inspect")
    p_inspect.add_argument("--run", required=True)
    p_inspect.set_defaults(func=cmd_manifest_inspect)

    return parser


def main(argv: list[str] | None = None) -> int:
    global COMMAND_STR
    parser = build_parser()
    args = parser.parse_args(argv)
    COMMAND_STR = "retro-trace " + " ".join(argv) if argv else "retro-trace"
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
