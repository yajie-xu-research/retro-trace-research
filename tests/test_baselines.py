"""Three comparison baselines: naive heuristic, fixed thresholds, per-stage SPC."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from retro_trace.a1 import baselines as b
from retro_trace.a1 import dictionary as d


def _durations_frame(case_key: str, hours: dict) -> pd.DataFrame:
    rows = [
        {"case_key": case_key, "canonical_stage": stage, "duration_hours": hours.get(stage, 1.0),
         "first_at": pd.Timestamp("2024-01-01", tz="UTC"), "last_at": pd.Timestamp("2024-01-01", tz="UTC")}
        for stage in d.CANONICAL_STAGES
    ]
    return pd.DataFrame(rows).set_index(["case_key", "canonical_stage"])


def test_naive_heuristic_uses_raw_order_without_dictionary():
    # codes are gibberish (no dictionary) but order/timing carry the signal:
    # the longest wait precedes the SEQUENCING_STARTED milestone position
    events = pd.DataFrame(
        {
            "case_key": ["C1"] * 7,
            "event_code_raw": ["X1", "X2", "X3", "X4", "X5", "X6", "X7"],
            "occurred_at_utc": pd.to_datetime(
                ["2024-01-01T00:00:00Z", "2024-01-01T02:00:00Z", "2024-01-01T04:00:00Z",
                 "2024-01-02T04:00:00Z", "2024-01-03T04:00:00Z", "2024-01-03T06:00:00Z",
                 "2024-01-03T08:00:00Z"],
                utc=True,
            ),
        }
    )
    result = b.naive_heuristic(events)
    # the 24h wait delays the 4th milestone -> SEQUENCING_STARTED position
    assert result["C1"] == "SEQUENCING_STARTED"


def test_fixed_threshold_blames_stage_exceeding_its_threshold():
    durations = _durations_frame("C1", {"LIBRARY_PREPARED": 500.0})
    result = b.fixed_threshold(durations)
    assert result["C1"] == "LIBRARY_PREPARED"


def test_fixed_threshold_falls_back_to_longest_stage():
    durations = _durations_frame("C1", {"REVIEWED": 20.0})  # nothing above thresholds
    result = b.fixed_threshold(durations)
    assert result["C1"] == "REVIEWED"


def test_spc_flags_stage_beyond_three_sigma():
    rows = []
    for i in range(60):
        rows.append(_durations_frame(f"C{i}", {"SEQUENCING_STARTED": 10.0 + (i % 5) * 0.5}))
    out = pd.concat(rows)
    spike = _durations_frame("C-SPIKE", {"SEQUENCING_STARTED": 400.0})
    out = pd.concat([out, spike])
    result = b.spc_control_chart(out)
    assert result["C-SPIKE"] == "SEQUENCING_STARTED"
    # ordinary cases fall back to their longest stage
    ordinary = b.spc_control_chart(out[out.index.get_level_values("case_key") == "C0"])
    assert ordinary["C0"] == "SEQUENCING_STARTED"


def test_spc_falls_back_to_longest_when_nothing_flagged():
    durations = _durations_frame("C1", {"REVIEWED": 20.0})
    result = b.spc_control_chart(durations)
    assert result["C1"] == "REVIEWED"


def test_baselines_cover_all_flagged_cases_without_abstention(attribute_run):
    comparison = pd.read_csv(attribute_run / "results" / "baselines_comparison.csv", dtype=str)
    attribution = pd.read_csv(attribute_run / "results" / "attribution_rows.csv", dtype=str)
    flagged = sorted(set(attribution["case_key"]))
    assert sorted(comparison["case_key"].tolist()) == flagged
    assert set(comparison.columns) == {"case_key", "naive_stage", "threshold_stage", "spc_stage"}
    # baselines always emit a stage - no abstention column exists
    assert comparison[["naive_stage", "threshold_stage", "spc_stage"]].notna().all().all()
