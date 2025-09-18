"""Research data generator: reproducibility, rates, planted structure."""

from __future__ import annotations

import pandas as pd
import pytest

from retro_trace.a1 import generator as g

pytestmark = pytest.mark.full_data


def test_seed_reproducibility():
    t1 = g.generate_tables(seed=20250710)
    t2 = g.generate_tables(seed=20250710)
    for key in ("events", "quality_events", "sample_classes", "load_staffing", "case_table"):
        pd.testing.assert_frame_equal(t1[key], t2[key], check_exact=True)


def test_counts_and_rates(full_data):
    cases = pd.read_csv(full_data / "cases.csv", dtype=str)
    qe = pd.read_csv(full_data / "quality_events.csv", dtype=str)
    n = len(cases)
    assert n == g.N_TOTAL
    delay_rate = (qe["event_type"] == "DELAY").sum() / n
    rework_rate = (qe["event_type"] == "REWORK").sum() / n
    assert abs(delay_rate - 0.12) < 0.01
    assert abs(rework_rate - 0.08) < 0.01
    two_stage = (qe["basis"].str.contains(",")).sum() / n
    assert abs(two_stage - 0.03) < 0.01


def test_not_comparable_combination_present(full_data):
    cases = pd.read_csv(full_data / "cases.csv", dtype=str)
    combo = ((cases["site_key"] == "SITE_C") & (cases["workflow_version"] == "WF_V1")).sum()
    assert combo > 150  # roughly 7.5% of cases


def test_small_class_is_below_baseline_floor(full_data, configs):
    cases = pd.read_csv(full_data / "cases.csv", dtype=str)
    small = (cases["sample_class"] == g.CLS_SMALL).sum()
    assert 0 < small < configs[0]["baselines"]["min_samples_per_class"]


def test_unmapped_event_codes_present(full_data):
    events = pd.read_csv(full_data / "events.csv", dtype=str)
    n_unmapped = events["event_code_raw"].isin(g.UNMAPPED_CODES).sum()
    assert 20 <= n_unmapped <= 60  # ~1% of 3500


def test_event_stream_shape(full_data):
    events = pd.read_csv(full_data / "events.csv", dtype=str)
    per_case = events.groupby("case_key").size()
    assert (per_case >= 6).all()  # SITE_C streams carry six stages; A/B carry seven
    assert (per_case <= 9).all()  # repeats and unmapped noise only
    # repeat events carry record_version 2
    v2 = events[events["record_version"] == "2"]
    assert len(v2) > 200  # the rework population (~8%)


def test_quality_events_schema(full_data):
    qe = pd.read_csv(full_data / "quality_events.csv", dtype=str)
    assert set(qe["event_type"]) <= {"DELAY", "REWORK"}
    assert qe["basis"].str.len().gt(0).all()
    assert qe["rule_version"].eq(g.RULE_VERSION).all()
    assert (qe["adjudicated_at"] <= "2026-06-30T00:00:00Z").all()
    cases = set(pd.read_csv(full_data / "cases.csv", dtype=str)["case_key"])
    assert qe["case_key"].isin(cases).all()


def test_all_dates_within_era_window(full_data):
    import re

    for name in ("events.csv", "cases.csv", "quality_events.csv", "load_staffing.csv", "sample_classes.csv"):
        df = pd.read_csv(full_data / name, dtype=str)
        for col in df.columns:
            for value in df[col].dropna().astype(str):
                for match in re.findall(r"\d{4}-\d{2}-\d{2}", value):
                    assert match <= "2026-06-30", f"{name}.{col}: {match}"
