"""Evaluation of attribution runs against the rule-labeled quality-event
labels.

The true labels are the rule-labeled DELAY/REWORK decisions recorded in
quality_events.csv (staged under data/_ground_truth/ inside the run). The
engine's predefined label rules are the marking procedure; the rule-labeled
labels are the reference. The naive manual heuristic, the fixed-threshold
rule, and the per-stage SPC chart are comparison baselines only - never
ground truth.

Metrics computed (all from the run artifacts, deterministic):
  - flag precision / recall (engine rules vs the rule-labeled labels)
  - localization agreement among LOCALIZED decisions, overall and split by
    uncertainty tier (LOW / HIGH); a two-sided exact binomial test against
    chance (1 / number of stages) is reported for each tier
  - false positives (localized stage not in the labeled basis) and false
    negatives (single-stage basis where the engine abstained)
  - ambiguity recall (multi-stage basis where the engine abstained with
    AMBIGUOUS_STAGES)
  - rejection rate with reason breakdown
  - the three baselines scored on the same universe (they never abstain)
  - correct-and-confident rate (correct localizations over all flagged rows)

All conclusions are statistical associations, not causation.
"""

from __future__ import annotations

import math
import re
from pathlib import Path

import pandas as pd

from ..common.enums import (
    DECISION_ABSTAIN,
    DECISION_LOCALIZED,
    EVENT_DELAY,
    EVENT_REWORK,
    REASON_AMBIGUOUS_STAGES,
    REASON_INSUFFICIENT_BASELINE,
    REASON_NOT_COMPARABLE_SITE,
)
from ..common.run_layout import ground_truth_path
from .dictionary import CANONICAL_STAGES

STAGE_TOKEN = re.compile("|".join(re.escape(s) for s in CANONICAL_STAGES))

N_CHANCE = len(CANONICAL_STAGES)


def _exact_binomial_p(n_correct: int, n_total: int, p: float) -> float:
    """Two-sided exact binomial p-value against success probability p."""
    if n_total == 0:
        return 1.0
    n_correct = min(n_correct, n_total)
    p_value = 0.0
    # sum over k with P(X=k) <= P(X=n_correct), two-sided
    prob_obs = math.comb(n_total, n_correct) * (p ** n_correct) * ((1 - p) ** (n_total - n_correct))
    for k in range(n_total + 1):
        prob_k = math.comb(n_total, k) * (p ** k) * ((1 - p) ** (n_total - k))
        if prob_k <= prob_obs * (1 + 1e-12):
            p_value += prob_k
    return min(1.0, p_value)


def parse_basis_stages(basis: str) -> set[str]:
    if not isinstance(basis, str):
        return set()
    return set(STAGE_TOKEN.findall(basis))


def evaluate_run(run_dir: str | Path) -> dict:
    run = Path(run_dir)
    attribution = pd.read_csv(run / "results" / "attribution_rows.csv", dtype=str)
    baselines = pd.read_csv(run / "results" / "baselines_comparison.csv", dtype=str)
    true_labels = pd.read_csv(ground_truth_path(run), dtype=str)

    # ground truth indexed by (case_key, event_type)
    true_labels["basis_stages"] = true_labels["basis"].map(parse_basis_stages)
    true_idx = true_labels.set_index(["case_key", "event_type"])

    flagged_keys = sorted(set(attribution["case_key"]))
    engine_flagged = set(
        zip(attribution["case_key"], attribution["event_type"])
    )
    labeled = set(zip(true_labels["case_key"], true_labels["event_type"]))

    # ---- flag precision / recall ----
    tp_flags = engine_flagged & labeled
    precision = len(tp_flags) / len(engine_flagged) if engine_flagged else 1.0
    recall = len(tp_flags) / len(labeled) if labeled else 1.0

    # ---- per-row scoring for engine ----
    engine_rows = []
    for _, row in attribution.iterrows():
        key = (row["case_key"], row["event_type"])
        true_row = true_idx.loc[key] if key in true_idx.index else None
        if true_row is None:
            engine_rows.append({**row.to_dict(), "outcome": "FP_FLAG", "true_stages": "", "correct": ""})
            continue
        stages = true_row["basis_stages"]
        multi = len(stages) > 1
        if row["decision"] == DECISION_LOCALIZED:
            correct = row["localized_stage"] in stages
            if multi:
                outcome = "FP_LOCALIZED_ON_MULTI"
            else:
                outcome = "LOCALIZED"
            engine_rows.append({**row.to_dict(), "outcome": outcome,
                                "true_stages": ",".join(sorted(stages)), "correct": bool(correct)})
        else:
            reason = row["reason"]
            if multi and reason == REASON_AMBIGUOUS_STAGES:
                outcome = "AMBIGUITY_RECALL"
            elif reason == REASON_INSUFFICIENT_BASELINE:
                outcome = "FN_INSUFFICIENT_BASELINE"
            elif reason == REASON_NOT_COMPARABLE_SITE:
                outcome = "FN_NOT_COMPARABLE"
            elif not multi and reason == REASON_AMBIGUOUS_STAGES:
                outcome = "FN_AMBIGUOUS"
            else:
                outcome = "FN_OTHER"
            engine_rows.append({**row.to_dict(), "outcome": outcome,
                                "true_stages": ",".join(sorted(stages)), "correct": ""})
    engine_eval = pd.DataFrame(engine_rows)

    localized = engine_eval[engine_eval["outcome"] == "LOCALIZED"]
    n_localized = len(localized)
    agreement = float(localized["correct"].mean()) if n_localized else None

    tier_stats = {}
    for tier in ("LOW", "HIGH"):
        sub = localized[localized["uncertainty_tier"] == tier]
        n_tier = len(sub)
        n_correct = int(sub["correct"].sum()) if n_tier else 0
        acc = n_correct / n_tier if n_tier else None
        p_value = _exact_binomial_p(n_correct, n_tier, 1.0 / N_CHANCE) if n_tier else None
        tier_stats[tier] = {"n": n_tier, "agreement": acc, "chance": 1.0 / N_CHANCE, "p_value_vs_chance": p_value}

    # false positives / negatives over labeled rows
    n_fp_localized_multi = int((engine_eval["outcome"] == "FP_LOCALIZED_ON_MULTI").sum())
    n_fp_localized_wrong = int(
        ((engine_eval["outcome"] == "LOCALIZED") & (~engine_eval["correct"].astype(bool))).sum()
    )
    n_fp_flag = int((engine_eval["outcome"] == "FP_FLAG").sum())
    n_fn_ambiguous = int((engine_eval["outcome"] == "FN_AMBIGUOUS").sum())
    n_fn_insufficient = int((engine_eval["outcome"] == "FN_INSUFFICIENT_BASELINE").sum())
    n_fn_not_comparable = int((engine_eval["outcome"] == "FN_NOT_COMPARABLE").sum())
    n_ambiguity_recall = int((engine_eval["outcome"] == "AMBIGUITY_RECALL").sum())
    coverage_limited = engine_eval["outcome"].isin(["FN_INSUFFICIENT_BASELINE", "FN_NOT_COMPARABLE"])
    multi_eligible = (engine_eval["outcome"] != "FP_FLAG") & (~coverage_limited)
    n_labeled_multi = int(
        (engine_eval[multi_eligible]["true_stages"].str.split(",").map(len).gt(1)).sum()
    )

    n_flagged_rows = len(attribution)
    n_abstain = int((attribution["decision"] == DECISION_ABSTAIN).sum())
    rejection_rate = n_abstain / n_flagged_rows if n_flagged_rows else None
    reason_breakdown = (
        attribution[attribution["decision"] == DECISION_ABSTAIN]["reason"].value_counts().to_dict()
    )

    # ---- baseline scoring ----
    baseline_rows = []
    for _, row in baselines.iterrows():
        for method in ("naive_stage", "threshold_stage", "spc_stage"):
            key_delay = (row["case_key"], EVENT_DELAY)
            key_rework = (row["case_key"], EVENT_REWORK)
            if key_delay in true_idx.index:
                true_key = key_delay
                true_row = true_idx.loc[true_key]
                stages = true_row["basis_stages"]
                correct = row[method] in stages
                multi = len(stages) > 1
                stages_str = ",".join(sorted(stages))
            elif key_rework in true_idx.index:
                true_key = key_rework
                true_row = true_idx.loc[true_key]
                stages = true_row["basis_stages"]
                correct = row[method] in stages
                multi = len(stages) > 1
                stages_str = ",".join(sorted(stages))
            else:
                # engine flag without any label row: scored as incorrect
                correct = False
                multi = False
                stages_str = ""
            baseline_rows.append(
                {
                    "case_key": row["case_key"],
                    "method": method,
                    "predicted_stage": row[method],
                    "true_stages": stages_str,
                    "multi_basis": multi,
                    "correct": bool(correct),
                }
            )
    baseline_eval = pd.DataFrame(baseline_rows)
    baseline_stats = {}
    for method in ("naive_stage", "threshold_stage", "spc_stage"):
        sub = baseline_eval[baseline_eval["method"] == method]
        single = sub[~sub["multi_basis"]]
        n_single = len(single)
        baseline_stats[method] = {
            "n": n_single,
            "agreement_single_basis": float(single["correct"].mean()) if n_single else None,
            "agreement_all": float(sub["correct"].mean()) if len(sub) else None,
        }

    # ---- correct-and-confident over all flagged rows ----
    engine_cc = 0
    for _, row in attribution.iterrows():
        key = (row["case_key"], row["event_type"])
        if key in true_idx.index and row["decision"] == DECISION_LOCALIZED:
            if row["localized_stage"] in true_idx.loc[key]["basis_stages"]:
                engine_cc += 1
    cc_rate = engine_cc / n_flagged_rows if n_flagged_rows else None
    cc_rates = {}
    for method in ("naive_stage", "threshold_stage", "spc_stage"):
        cc_rates[method] = (
            float((baseline_eval[baseline_eval["method"] == method]["correct"]).sum()) / n_flagged_rows
            if n_flagged_rows
            else None
        )

    metrics = {
        "n_cases_flagged": n_flagged_rows,
        "n_labeled_quality_events": len(labeled),
        "flag_precision": round(precision, 5),
        "flag_recall": round(recall, 5),
        "n_localized": n_localized,
        "localization_agreement": round(agreement, 5) if agreement is not None else None,
        "tier_LOW": tier_stats["LOW"],
        "tier_HIGH": tier_stats["HIGH"],
        "fp_localized_on_multi_basis": n_fp_localized_multi,
        "fp_localized_wrong_stage": n_fp_localized_wrong,
        "fp_flag_no_label": n_fp_flag,
        "fn_ambiguous_false_abstain": n_fn_ambiguous,
        "fn_insufficient_baseline": n_fn_insufficient,
        "fn_not_comparable": n_fn_not_comparable,
        "ambiguity_recall": n_ambiguity_recall,
        "n_labeled_multi_basis": n_labeled_multi,
        "rejection_rate": round(rejection_rate, 5) if rejection_rate is not None else None,
        "rejection_by_reason": {k: int(v) for k, v in reason_breakdown.items()},
        "baselines": baseline_stats,
        "correct_and_confident_engine": round(cc_rate, 5) if cc_rate is not None else None,
        "correct_and_confident_baselines": {k: (round(v, 5) if v is not None else None) for k, v in cc_rates.items()},
        "conclusion": (
            "stage localization is reported as a statistical association, "
            "not causation; localized stages are candidate focus areas for "
            "quality review and are not evidence that a stage caused the event"
        ),
    }

    return {
        "metrics": metrics,
        "engine_eval": engine_eval,
        "baseline_eval": baseline_eval,
        "attribution": attribution,
        "true_labels": true_labels,
    }
