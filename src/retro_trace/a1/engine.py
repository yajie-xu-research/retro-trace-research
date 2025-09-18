"""Six-step retrospective stage-attribution engine.

Steps (internal order, fixed):
  1. unify stages with the frozen event dictionary; register non-comparable
     nodes (unmapped raw codes);
  2. mark delay/rework events retrospectively with the predefined label rules;
  3. compute per-stage duration deviations against same-class baselines;
  4. subgroup association analysis (sample class x period x load);
  5. attribution with uncertainty rules (multiple simultaneously deviating
     stages -> AMBIGUOUS_STAGES, attribution not unique);
  6. cross-site comparability check (registered combinations ->
     NOT_COMPARABLE_SITE).

The engine never reads the quality-event labels; it consumes only the
event log,
the case registry, class definitions, staffing snapshots, configuration, and
the frozen dictionary. All output statements are statistical associations,
not causal claims.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
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
from . import label_rules as label_rules_mod
from .baselines import run_baselines
from .deviation import class_baselines, stage_durations
from .dictionary import (
    PACKAGED_DICTIONARY,
    build_code_index,
    load_dictionary,
    map_event,
    non_comparable_combinations,
)

EXCLUSION_UNMAPPED = "UNMAPPED_EVENT_CODE"

Z_CLAMP = 50.0


def _parse_utc(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, format="ISO8601", utc=True)


def load_inputs(data_dir: str | Path) -> dict[str, pd.DataFrame]:
    data = Path(data_dir)
    events = pd.read_csv(data / "events.csv", dtype=str)
    events["occurred_at_utc"] = _parse_utc(events["occurred_at_utc"])
    cases = pd.read_csv(data / "cases.csv", dtype=str)
    cases["received_at_utc"] = _parse_utc(cases["received_at_utc"])
    cases["released_at_utc"] = _parse_utc(cases["released_at_utc"])
    sample_classes = pd.read_csv(data / "sample_classes.csv", dtype=str)
    load_staffing = pd.read_csv(data / "load_staffing.csv", dtype=str)
    load_staffing["snapshot_at_utc"] = _parse_utc(load_staffing["snapshot_at_utc"])
    return {
        "events": events,
        "cases": cases,
        "sample_classes": sample_classes,
        "load_staffing": load_staffing,
    }


def _queue_quartile_for_cases(cases: pd.DataFrame, load_staffing: pd.DataFrame) -> pd.Series:
    staffing = load_staffing.copy()
    qq = (
        staffing.groupby(["site_key", "workflow_version"])["queue_size"]
        .transform(lambda s: pd.qcut(s.rank(method="first"), 4, labels=[1, 2, 3, 4]))
    ).astype(int)
    staffing["queue_quartile"] = qq
    snap_index = (
        staffing.set_index(["site_key", "workflow_version", "snapshot_at_utc"])["queue_quartile"]
        .sort_index()
    )
    out = []
    for _, row in cases.iterrows():
        key = (row["site_key"], row["workflow_version"])
        sub = snap_index.loc[key]
        past = sub[sub.index <= row["received_at_utc"]]
        out.append(int(past.iloc[-1]) if len(past) else 1)
    return pd.Series(out, index=cases.index)


def run_attribution(
    data_dir: str | Path,
    qa_config: dict,
    label_rules: dict,
    dictionary_path: str | Path = PACKAGED_DICTIONARY,
) -> dict[str, pd.DataFrame]:
    inputs = load_inputs(data_dir)
    events = inputs["events"]
    cases = inputs["cases"]
    load_staffing = inputs["load_staffing"]

    stage_map = load_dictionary(qa_config, dictionary_path)
    code_index = build_code_index(stage_map)
    case_combo = cases.set_index("case_key")[["site_key", "workflow_version"]]

    # ---- step 1: unify stages; register non-comparable nodes ----
    unified_rows = []
    excluded_rows = []
    ledger_rows = []
    for _, ev in events.iterrows():
        case_key = ev["case_key"]
        combo = tuple(case_combo.loc[case_key])
        stage = map_event(code_index, combo[0], combo[1], ev["event_code_raw"])
        if stage is None:
            excluded_rows.append(
                {
                    "case_key": case_key,
                    "event_code_raw": ev["event_code_raw"],
                    "occurred_at_utc": ev["occurred_at_utc"].strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "reason": EXCLUSION_UNMAPPED,
                }
            )
            ledger_rows.append(
                {
                    "case_key": case_key,
                    "site_key": combo[0],
                    "workflow_version": combo[1],
                    "kind": EXCLUSION_UNMAPPED,
                    "event_code_raw": ev["event_code_raw"],
                    "detail": "raw code not present in the frozen dictionary for this site and workflow version",
                }
            )
            continue
        unified_rows.append(
            {
                "case_key": case_key,
                "canonical_stage": stage,
                "occurred_at_utc": ev["occurred_at_utc"],
            }
        )
    unified = pd.DataFrame(unified_rows)
    excluded = pd.DataFrame(excluded_rows)

    # ---- step 2: predefined retrospective delay/rework marking ----
    durations, counts, totals = stage_durations(unified)
    cases_indexed = cases.set_index("case_key")
    class_of = cases_indexed["sample_class"]
    totals = totals.join(class_of, on="case_key")
    totals = totals.join(cases_indexed[["site_key", "workflow_version"]], on="case_key")
    flags = label_rules_mod.apply_label_rules(totals, counts, label_rules)
    flags = flags.join(cases_indexed[["site_key", "workflow_version", "sample_class"]], on="case_key")
    flags = flags.join(totals[["total_duration_hours"]], on="case_key")

    # ---- step 3: same-class baseline deviations (robust median/MAD) ----
    min_samples = qa_config["baselines"]["min_samples_per_class"]
    baselines, class_sizes = class_baselines(durations, class_of, min_samples)
    z = _robust_z(durations, baselines, class_of)

    # ---- step 6 (pre-check): cross-site comparability registry ----
    non_comparable = non_comparable_combinations(qa_config)

    # ---- step 5: attribution with uncertainty rules ----
    z_amb = qa_config["attribution"]["ambiguity_z_threshold"]
    tier_margin = qa_config["attribution"]["tier_margin_threshold"]
    p90 = totals.groupby("sample_class")["total_duration_hours"].quantile(0.90)

    attribution_rows = []
    flagged = flags[flags["event_type"].notna() & (flags["event_type"] != "")]
    for case_key, flag_row in flagged.sort_index().iterrows():
        combo = (flag_row["site_key"], flag_row["workflow_version"])
        cls = flag_row["sample_class"]
        event_types = [t for t in str(flag_row["event_type"]).split("+") if t]
        base = {
            "case_key": case_key,
            "site_key": combo[0],
            "workflow_version": combo[1],
            "sample_class": cls,
        }
        if combo in non_comparable:
            for et in event_types:
                attribution_rows.append(
                    {**base, "event_type": et, "decision": DECISION_ABSTAIN,
                     "localized_stage": "", "uncertainty_tier": "",
                     "reason": REASON_NOT_COMPARABLE_SITE,
                     "z_top": np.nan, "z_second": np.nan, "margin": np.nan,
                     "repeat_max_count": 0, "repeat_stage": ""}
                )
            ledger_rows.append(
                {
                    "case_key": case_key,
                    "site_key": combo[0],
                    "workflow_version": combo[1],
                    "kind": REASON_NOT_COMPARABLE_SITE,
                    "event_code_raw": "",
                    "detail": "site-version combination registered as not comparable; stage boundaries do not align with the canonical dictionary",
                }
            )
            continue
        if class_sizes.get(cls, 0) < min_samples:
            for et in event_types:
                attribution_rows.append(
                    {**base, "event_type": et, "decision": DECISION_ABSTAIN,
                     "localized_stage": "", "uncertainty_tier": "",
                     "reason": REASON_INSUFFICIENT_BASELINE,
                     "z_top": np.nan, "z_second": np.nan, "margin": np.nan,
                     "repeat_max_count": 0, "repeat_stage": ""}
                )
            continue

        case_z = z.loc[case_key]["z"] if case_key in z.index else pd.Series(dtype=float)
        case_counts = counts.loc[case_key]["count"] if case_key in counts.index else pd.Series(dtype=int)
        repeat_stage = ""
        repeat_max = int(case_counts.max()) if len(case_counts) else 0
        if repeat_max >= 2:
            cand = case_counts[case_counts == repeat_max]
            repeat_stage = cand.index[0] if len(cand) == 1 else ""

        z_sorted = case_z.sort_values(ascending=False)
        z_top = float(z_sorted.iloc[0]) if len(z_sorted) else np.nan
        z_second = float(z_sorted.iloc[1]) if len(z_sorted) > 1 else np.nan
        margin = (z_top - z_second) if (pd.notna(z_top) and pd.notna(z_second)) else np.nan
        n_above = int((case_z > z_amb).sum()) if len(case_z) else 0
        delay_stage = z_sorted.index[0] if len(z_sorted) else ""

        for et in event_types:
            if et == EVENT_REWORK:
                if repeat_stage:
                    decision, stage, tier, reason = DECISION_LOCALIZED, repeat_stage, "LOW", ""
                else:
                    decision, stage, tier, reason = DECISION_ABSTAIN, "", "", REASON_AMBIGUOUS_STAGES
            elif et == EVENT_DELAY:
                if EVENT_REWORK in event_types:
                    # both labels: agree only when the repeated stage is the top deviation
                    if repeat_stage and repeat_stage == delay_stage and n_above < 2:
                        decision, stage, tier, reason = DECISION_LOCALIZED, delay_stage, "LOW", ""
                    else:
                        decision, stage, tier, reason = DECISION_ABSTAIN, "", "", REASON_AMBIGUOUS_STAGES
                elif n_above >= 2:
                    decision, stage, tier, reason = DECISION_ABSTAIN, "", "", REASON_AMBIGUOUS_STAGES
                else:
                    decision = DECISION_LOCALIZED
                    stage = delay_stage
                    if pd.notna(margin):
                        tier = "LOW" if margin >= tier_margin else "HIGH"
                    else:
                        tier = "HIGH"
                    reason = ""
            else:
                decision, stage, tier, reason = DECISION_ABSTAIN, "", "", REASON_AMBIGUOUS_STAGES
            attribution_rows.append(
                {
                    **base,
                    "event_type": et,
                    "decision": decision,
                    "localized_stage": stage,
                    "uncertainty_tier": tier,
                    "reason": reason,
                    "z_top": z_top,
                    "z_second": z_second,
                    "margin": margin,
                    "repeat_max_count": repeat_max,
                    "repeat_stage": repeat_stage,
                }
            )

    attribution = pd.DataFrame(attribution_rows).sort_values(["case_key", "event_type"]).reset_index(drop=True)

    # ---- step 4: subgroup association analysis ----
    case_qq = _queue_quartile_for_cases(cases, load_staffing)
    cases_w_q = cases.assign(queue_quartile=case_qq)
    subgroup = _subgroup_association(cases_w_q, attribution, flags)

    # ---- comparison baselines (no labels, no abstention) ----
    flagged_keys = pd.Index(sorted(set(attribution["case_key"])), name="case_key")
    baseline_out = run_baselines(events, durations, flagged_keys)

    ledger = pd.DataFrame(ledger_rows)
    if not ledger.empty:
        ledger = ledger.sort_values(["case_key", "kind"]).reset_index(drop=True)

    return {
        "attribution_rows": attribution,
        "excluded_rows": excluded,
        "comparability_ledger": ledger,
        "subgroup_association": subgroup,
        "baselines_comparison": baseline_out,
    }


def _robust_z(
    durations: pd.DataFrame,
    baselines: pd.DataFrame,
    class_of: pd.Series,
) -> pd.DataFrame:
    """Robust standardized deviation: (x - median) / (1.4826 * MAD)."""
    joined = durations.join(class_of.rename("sample_class"), on="case_key").reset_index()
    key_cols = ["sample_class", "canonical_stage"]
    med = baselines["median_hours"].reindex(pd.MultiIndex.from_frame(joined[key_cols])).to_numpy()
    mad = baselines["mad_hours"].reindex(pd.MultiIndex.from_frame(joined[key_cols])).to_numpy()
    sigma = 1.4826 * mad
    sigma = np.where(sigma > 0, sigma, 1e-6)
    raw = joined["duration_hours"].to_numpy()
    z = np.where(sigma > 1e-6, (raw - med) / sigma, 0.0)
    z = np.clip(z, -Z_CLAMP, Z_CLAMP)
    return pd.DataFrame(
        {
            "case_key": joined["case_key"].to_numpy(),
            "canonical_stage": joined["canonical_stage"].to_numpy(),
            "z": z,
        }
    ).set_index(["case_key", "canonical_stage"]).sort_index()


def _subgroup_association(
    cases: pd.DataFrame,
    attribution: pd.DataFrame,
    flags: pd.DataFrame,
) -> pd.DataFrame:
    """Subgroup rates and lifts: sample class x quarter x load quartile."""
    cases = cases.copy()
    cases["period"] = cases["received_at_utc"].dt.tz_localize(None).dt.to_period("Q").astype(str)
    all_cases = cases.set_index("case_key")[["sample_class", "period", "queue_quartile"]].copy()
    all_cases["is_delay"] = False
    all_cases["is_rework"] = False
    flag_types = flags["event_type"].astype(str)
    all_cases.loc[flags.index, "is_delay"] = flag_types.str.contains(EVENT_DELAY, na=False).to_numpy()
    all_cases.loc[flags.index, "is_rework"] = flag_types.str.contains(EVENT_REWORK, na=False).to_numpy()

    overall_delay_rate = all_cases["is_delay"].mean()
    overall_rework_rate = all_cases["is_rework"].mean()

    localized = attribution[
        (attribution["decision"] == DECISION_LOCALIZED)
        & (attribution["event_type"] == EVENT_DELAY)
    ]

    rows = []
    for (cls, period, qq), group in all_cases.groupby(["sample_class", "period", "queue_quartile"], sort=True):
        n = len(group)
        n_delay = int(group["is_delay"].sum())
        n_rework = int(group["is_rework"].sum())
        sub_loc = localized[localized["sample_class"] == cls]
        sub_loc = sub_loc[sub_loc["case_key"].isin(group.index)]
        top_stage = sub_loc["localized_stage"].mode()
        rows.append(
            {
                "sample_class": cls,
                "period": period,
                "queue_quartile": int(qq),
                "n_cases": n,
                "n_delay": n_delay,
                "n_rework": n_rework,
                "delay_rate": round(n_delay / n, 5),
                "delay_lift": round((n_delay / n) / overall_delay_rate, 4) if overall_delay_rate else 0.0,
                "rework_rate": round(n_rework / n, 5),
                "rework_lift": round((n_rework / n) / overall_rework_rate, 4) if overall_rework_rate else 0.0,
                "top_localized_stage": top_stage.iloc[0] if len(top_stage) else "",
                "n_localized": len(sub_loc),
            }
        )
    return pd.DataFrame(rows).sort_values(["sample_class", "period", "queue_quartile"]).reset_index(drop=True)
