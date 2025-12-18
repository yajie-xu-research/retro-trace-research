"""Three comparison baselines for stage localization.

Each baseline answers the same question as the engine ("which stage is the
dominant deviation concentrated in?") with a simpler, commonly used rule.
Baselines never abstain and carry no uncertainty statement; that difference is
itself part of the comparison. None of the baselines reads any quality-event
label.

1. Naive manual heuristic: no dictionary assistance; a reviewer looks at the
   raw log gaps and blames the longest one. Simulated as a rule over raw event
   order.
2. Single-stage fixed thresholds: each canonical stage has one fixed absolute
   duration threshold; the stage exceeding its threshold by the largest ratio
   is blamed; when nothing exceeds, the longest stage is blamed.
3. Per-stage SPC control chart: per stage, mean +/- 3 sigma over all cases;
   the stage with the highest standardized excess is blamed; when nothing
   exceeds, the longest stage is blamed.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .dictionary import CANONICAL_STAGES

FIXED_THRESHOLDS_HOURS = {
    "SAMPLE_RECEIVED": 24.0,
    "ACCESSIONED": 24.0,
    "LIBRARY_PREPARED": 72.0,
    "SEQUENCING_STARTED": 96.0,
    "ANALYSIS_COMPLETE": 72.0,
    "REVIEWED": 48.0,
    "RELEASED": 24.0,
}

SPC_SIGMA = 3.0


def _longest_stage(durations: pd.DataFrame, case_key: str) -> str:
    row = durations.loc[case_key]
    return row["duration_hours"].idxmax()


def naive_heuristic(events: pd.DataFrame) -> pd.Series:
    """Naive manual heuristic over the raw log (no dictionary).

    A reviewer scans the raw log, finds the longest wait between consecutive
    event records, and blames the milestone that wait delayed. Simulated as a
    rule over raw event order; no abstention, no uncertainty statement.

    Returns Series case_key -> localized stage (positional guess).
    """
    events = events.sort_values(["case_key", "occurred_at_utc"])
    result = {}
    for case_key, group in events.groupby("case_key", sort=False):
        times = group["occurred_at_utc"].to_numpy()
        if len(times) < 2:
            result[case_key] = CANONICAL_STAGES[0]
            continue
        gaps = np.diff(times)
        longest = int(np.argmax(gaps))
        stage_idx = min(longest + 1, len(CANONICAL_STAGES) - 1)
        result[case_key] = CANONICAL_STAGES[stage_idx]
    return pd.Series(result, name="naive_stage")


def fixed_threshold(durations: pd.DataFrame) -> pd.Series:
    """Single-stage fixed thresholds over canonical stage durations."""
    result = {}
    for case_key, row in durations.groupby(level="case_key", sort=False):
        d = row["duration_hours"].reset_index(level="case_key", drop=True)
        excess = pd.Series(
            {
                stage: d.get(stage, np.nan) / FIXED_THRESHOLDS_HOURS[stage]
                for stage in CANONICAL_STAGES
            },
            dtype=float,
        )
        over = excess[excess > 1.0]
        if over.empty:
            result[case_key] = d.idxmax()
        else:
            result[case_key] = over.idxmax()
    return pd.Series(result, name="threshold_stage")


def spc_control_chart(durations: pd.DataFrame) -> pd.Series:
    """Per-stage SPC: mean +/- 3 sigma over all cases; top standardized excess."""
    stats = durations.groupby(level="canonical_stage")["duration_hours"].agg(["mean", "std"])
    result = {}
    for case_key, row in durations.groupby(level="case_key", sort=False):
        d = row["duration_hours"].reset_index(level="case_key", drop=True)
        z_spc = {}
        for stage in CANONICAL_STAGES:
            mean = stats.loc[stage, "mean"]
            std = stats.loc[stage, "std"] if stats.loc[stage, "std"] > 0 else 1e-6
            z_spc[stage] = (d.get(stage, np.nan) - mean) / std
        z_spc = pd.Series(z_spc, dtype=float)
        over = z_spc[z_spc > SPC_SIGMA]
        if over.empty:
            result[case_key] = d.idxmax()
        else:
            result[case_key] = over.idxmax()
    return pd.Series(result, name="spc_stage")


def run_baselines(
    events: pd.DataFrame,
    durations: pd.DataFrame,
    flagged_case_keys: pd.Index,
) -> pd.DataFrame:
    """Run all three baselines for the flagged universe."""
    naive = naive_heuristic(events[events["case_key"].isin(flagged_case_keys)])
    thr = fixed_threshold(durations[durations.index.get_level_values("case_key").isin(flagged_case_keys)])
    spc = spc_control_chart(durations[durations.index.get_level_values("case_key").isin(flagged_case_keys)])
    out = pd.DataFrame({"case_key": flagged_case_keys}).set_index("case_key")
    out.index.name = "case_key"
    out["naive_stage"] = naive
    out["threshold_stage"] = thr
    out["spc_stage"] = spc
    return out.sort_index()
