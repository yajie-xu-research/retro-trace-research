"""Attribution engine: six-step pipeline, abstention rules, counterexamples."""

from __future__ import annotations

import pandas as pd
import pytest

from retro_trace.a1 import engine as eng
from retro_trace.common.enums import (
    DECISION_ABSTAIN,
    DECISION_LOCALIZED,
    REASON_AMBIGUOUS_STAGES,
    REASON_INSUFFICIENT_BASELINE,
    REASON_NOT_COMPARABLE_SITE,
)
from retro_trace.a1 import generator as g
from retro_trace.a1.evaluate import parse_basis_stages


@pytest.fixture()
def artifacts(small_data, configs):
    return eng.run_attribution(small_data, configs[0], configs[1])


def test_six_step_artifacts_present(artifacts):
    assert set(artifacts) == {
        "attribution_rows",
        "excluded_rows",
        "comparability_ledger",
        "subgroup_association",
        "baselines_comparison",
    }
    for key in ("attribution_rows", "subgroup_association", "baselines_comparison"):
        assert len(artifacts[key]) > 0


def test_decisions_and_reasons_from_frozen_enums(artifacts):
    rows = artifacts["attribution_rows"]
    assert set(rows["decision"]) <= {DECISION_LOCALIZED, DECISION_ABSTAIN}
    reasons = rows.loc[rows["decision"] == DECISION_ABSTAIN, "reason"].dropna()
    assert set(reasons) <= {
        REASON_AMBIGUOUS_STAGES,
        REASON_INSUFFICIENT_BASELINE,
        REASON_NOT_COMPARABLE_SITE,
    }


def test_double_stage_deviation_abstains_as_ambiguous(artifacts, small_data):
    qe = pd.read_csv(small_data / "quality_events.csv", dtype=str)
    qe["basis_stages"] = qe["basis"].map(parse_basis_stages)
    multi = qe[qe["basis_stages"].map(len) > 1]
    rows = artifacts["attribution_rows"]
    for _, label_row in multi.iterrows():
        engine_rows = rows[
            (rows["case_key"] == label_row["case_key"]) & (rows["event_type"] == label_row["event_type"])
        ]
        if engine_rows.empty:
            continue  # not rule-flagged (manual review cases are not engine rows)
        reason = engine_rows.iloc[0]["reason"]
        # either abstained as ambiguous, or coverage-limited (site/class)
        assert engine_rows.iloc[0]["decision"] == DECISION_ABSTAIN
        assert reason in (
            REASON_AMBIGUOUS_STAGES,
            REASON_NOT_COMPARABLE_SITE,
            REASON_INSUFFICIENT_BASELINE,
        )
    # at least one genuinely ambiguous abstention exists in the small package
    ambiguous = rows[rows["reason"] == REASON_AMBIGUOUS_STAGES]
    assert len(ambiguous) > 0


def test_not_comparable_site_combination_abstains(artifacts):
    rows = artifacts["attribution_rows"]
    not_comparable = rows[(rows["site_key"] == "SITE_C") & (rows["workflow_version"] == "WF_V1")]
    assert len(not_comparable) > 0
    assert (not_comparable["decision"] == DECISION_ABSTAIN).all()
    assert (not_comparable["reason"] == REASON_NOT_COMPARABLE_SITE).all()
    # the ledger registers the combination
    ledger = artifacts["comparability_ledger"]
    assert (ledger["kind"] == REASON_NOT_COMPARABLE_SITE).any()


def test_insufficient_baseline_for_small_class(artifacts, configs, small_data):
    cases = pd.read_csv(small_data / "cases.csv", dtype=str)
    small = cases[cases["sample_class"] == g.CLS_SMALL]["case_key"]
    rows = artifacts["attribution_rows"]
    flagged_small = rows[rows["case_key"].isin(set(small))]
    if flagged_small.empty:
        pytest.skip("no flagged cases landed in the small class for this seed")
    assert (flagged_small["decision"] == DECISION_ABSTAIN).all()
    assert set(flagged_small["reason"]) <= {REASON_INSUFFICIENT_BASELINE, REASON_NOT_COMPARABLE_SITE}
    assert (flagged_small["reason"] == REASON_INSUFFICIENT_BASELINE).any()


def test_unmapped_events_registered_and_excluded(artifacts):
    excluded = artifacts["excluded_rows"]
    assert (excluded["reason"] == "UNMAPPED_EVENT_CODE").all()
    assert excluded["event_code_raw"].isin(g.UNMAPPED_CODES).all()
    ledger = artifacts["comparability_ledger"]
    assert (ledger["kind"] == "UNMAPPED_EVENT_CODE").all(axis=None) or (
        ledger["kind"] == "UNMAPPED_EVENT_CODE"
    ).any()


def test_localized_rows_have_stage_and_tier(artifacts):
    rows = artifacts["attribution_rows"]
    localized = rows[rows["decision"] == DECISION_LOCALIZED]
    assert len(localized) > 0
    assert localized["localized_stage"].isin(
        ["SAMPLE_RECEIVED", "ACCESSIONED", "LIBRARY_PREPARED", "SEQUENCING_STARTED",
         "ANALYSIS_COMPLETE", "REVIEWED", "RELEASED"]
    ).all()
    assert set(localized["uncertainty_tier"]) <= {"LOW", "HIGH"}


def test_subgroup_association_columns(artifacts):
    sub = artifacts["subgroup_association"]
    for col in ("sample_class", "period", "queue_quartile", "n_cases", "n_delay", "n_rework",
                "delay_rate", "delay_lift", "top_localized_stage"):
        assert col in sub.columns


def test_engine_output_deterministic(artifacts, small_data, configs):
    again = eng.run_attribution(small_data, configs[0], configs[1])
    pd.testing.assert_frame_equal(
        artifacts["attribution_rows"], again["attribution_rows"], check_exact=True
    )
