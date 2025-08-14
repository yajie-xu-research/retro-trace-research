"""Stage-duration deviation computation relative to same-class baselines.

Pipeline step 3. For every released case the duration of each canonical stage
is computed from the unified event log (last occurrence per stage defines the
stage boundary; repeated occurrences are counted separately for rework
detection). Deviations are standardized against the median and standard
deviation of the stage duration within the case's own sample class.

If a sample class holds fewer than min_samples_per_class cases, every flagged
case in that class abstains with INSUFFICIENT_BASELINE.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ..common.enums import REASON_INSUFFICIENT_BASELINE
from .dictionary import CANONICAL_STAGES


def stage_durations(
    unified: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Compute per-case stage durations and repeat counts from unified events.

    A stage's duration is the time from its first occurrence to the first
    occurrence of the next canonical stage; the final stage (RELEASED) has
    zero duration by convention. Repeated occurrences within a stage are
    counted separately for rework detection and do not change the stage
    boundary.
    """
    unified = unified.sort_values(["case_key", "occurred_at_utc"])
    counts = (
        unified.groupby(["case_key", "canonical_stage"]).size().rename("count").to_frame()
    )

    first = unified.groupby(["case_key", "canonical_stage"])["occurred_at_utc"].min()
    last = unified.groupby(["case_key", "canonical_stage"])["occurred_at_utc"].max()

    # A stage's duration is the time from the previous milestone to this
    # stage's milestone: how long the case waited to reach this stage. The
    # first stage is anchored at case receipt. Repeated occurrences within a
    # stage are counted separately for rework detection; the earliest
    # occurrence defines the milestone.
    first_pivot = first.unstack().reindex(columns=list(CANONICAL_STAGES))
    prev_pivot = first_pivot.shift(1, axis=1)
    received_at = unified[unified["canonical_stage"] == "SAMPLE_RECEIVED"]
    received_at = received_at.groupby("case_key")["occurred_at_utc"].min()
    prev_pivot[list(CANONICAL_STAGES)[0]] = received_at
    gap = first_pivot - prev_pivot
    durations = gap.stack().rename("duration_hours").to_frame()
    durations.index = durations.index.set_names(["case_key", "canonical_stage"])
    durations["first_at"] = first
    durations["last_at"] = last
    durations["duration_hours"] = durations["duration_hours"].dt.total_seconds() / 3600.0
    durations = durations.sort_index()

    released = unified[unified["canonical_stage"] == "RELEASED"]
    released_at = released.groupby("case_key")["occurred_at_utc"].min()

    totals = pd.DataFrame({"received_at": received_at, "released_at": released_at})
    totals["total_duration_hours"] = (
        (totals["released_at"] - totals["received_at"]).dt.total_seconds() / 3600.0
    )
    return durations, counts, totals


def class_baselines(
    durations: pd.DataFrame,
    class_of: pd.Series,
    min_samples_per_class: int = 30,
) -> tuple[pd.DataFrame, pd.Series]:
    """Per-(sample_class, stage) median/MAD/std baselines and per-class sizes.

    class_of: Series case_key -> sample_class.
    Returns:
      baselines: DataFrame indexed by (sample_class, canonical_stage) with
        columns [median_hours, mad_hours, std_hours, n_cases]
      class_sizes: Series sample_class -> number of cases
    """
    del min_samples_per_class  # sufficiency is enforced at attribution time
    durations = durations.join(class_of.rename("sample_class"), on="case_key")
    grouped = durations.groupby(["sample_class", "canonical_stage"])["duration_hours"]
    med = grouped.median()
    mad = grouped.apply(lambda s: (s - s.median()).abs().median())
    baselines = pd.DataFrame(
        {
            "median_hours": med,
            "mad_hours": mad,
            "std_hours": grouped.std(ddof=0).fillna(1e-6),
            "n_cases": grouped.count(),
        }
    )
    class_sizes = class_of.value_counts()
    return baselines, class_sizes


def standardized_deviations(
    durations: pd.DataFrame,
    baselines: pd.DataFrame,
    class_of: pd.Series,
) -> pd.DataFrame:
    """z = (duration - class median) / class std per (case, stage)."""
    joined = durations.join(class_of.rename("sample_class"), on="case_key").reset_index()
    key_cols = ["sample_class", "canonical_stage"]
    med = baselines["median_hours"].reindex(
        pd.MultiIndex.from_frame(joined[key_cols])
    ).to_numpy()
    std = baselines["std_hours"].reindex(
        pd.MultiIndex.from_frame(joined[key_cols])
    ).to_numpy()
    raw = joined["duration_hours"].to_numpy()
    z = np.where(std > 0, (raw - med) / std, 0.0)
    return pd.DataFrame(
        {
            "case_key": joined["case_key"].to_numpy(),
            "canonical_stage": joined["canonical_stage"].to_numpy(),
            "z": z,
        }
    ).set_index(["case_key", "canonical_stage"]).sort_index()


def insufficient_baseline_mask(
    class_sizes: pd.Series, class_of: pd.Series, min_samples_per_class: int
) -> pd.Series:
    """True for cases whose sample class is below the baseline size floor."""
    return class_of.map(lambda c: class_sizes.get(c, 0) < min_samples_per_class)
