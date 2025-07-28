"""Predefined retrospective label rules for delay and rework events.

The rules are frozen in configs/label_rules.yaml before data release. They are
applied to the event log to mark quality events retrospectively (pipeline step
2). The quality-event labels recorded against these rules in
quality_events.csv are the ground truth for evaluation; these rules are the
predefined marking procedure, not a substitute for the labels.
"""

from __future__ import annotations

import pandas as pd
import yaml

from ..common.enums import EVENT_DELAY, EVENT_REWORK


def load_label_rules(path) -> dict:
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def mark_delays(
    totals: pd.DataFrame,
    label_rules: dict,
) -> pd.Series:
    """Mark DELAY: total duration above the p90 of the same sample class.

    totals: DataFrame indexed by case_key with columns
    [sample_class, total_duration_hours].
    Returns a boolean Series indexed by case_key.
    """
    p90 = totals.groupby("sample_class")["total_duration_hours"].quantile(0.90)
    thresholds = totals["sample_class"].map(p90)
    return totals["total_duration_hours"] > thresholds


def mark_rework(stage_counts: pd.DataFrame) -> pd.Series:
    """Mark REWORK: any canonical stage has two or more event records.

    stage_counts: DataFrame indexed by (case_key, canonical_stage) with a count
    column. Returns a boolean Series indexed by case_key.
    """
    repeated = stage_counts["count"] >= 2
    case_repeated = repeated.groupby(level="case_key").any()
    return case_repeated


def apply_label_rules(
    totals: pd.DataFrame,
    stage_counts: pd.DataFrame,
    label_rules: dict,
) -> pd.DataFrame:
    """Apply both predefined rules; returns a flag table indexed by case_key."""
    flags = pd.DataFrame(index=totals.index)
    flags["event_type"] = pd.NA
    delay_hit = mark_delays(totals, label_rules)
    rework_hit = mark_rework(stage_counts)
    flags.loc[delay_hit & ~rework_hit, "event_type"] = EVENT_DELAY
    flags.loc[rework_hit & ~delay_hit, "event_type"] = EVENT_REWORK
    flags.loc[delay_hit & rework_hit, "event_type"] = EVENT_DELAY + "+" + EVENT_REWORK
    flags["delay_flag"] = delay_hit
    flags["rework_flag"] = rework_hit
    return flags
