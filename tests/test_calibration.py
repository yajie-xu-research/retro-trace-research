"""Attribution uncertainty calibration (design-frozen success criteria).

The testable definition of calibration: localization accuracy within the
ABSTAIN tiers. On the high-uncertainty tier, accuracy must not be
significantly above chance (1/7); on the low-uncertainty tier, accuracy must
be significantly above the comparison baselines.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.full_data


def test_high_uncertainty_tier_not_above_chance(full_evaluation):
    metrics = full_evaluation["metrics"]
    tier = metrics["tier_HIGH"]
    assert tier["n"] >= 40, "high-uncertainty tier too small to test calibration"
    # not significantly above chance at the 5% level
    assert tier["p_value_vs_chance"] >= 0.05
    assert tier["agreement"] <= 0.30


def test_low_uncertainty_tier_significantly_above_baselines(full_evaluation):
    metrics = full_evaluation["metrics"]
    tier = metrics["tier_LOW"]
    best_baseline = max(stats["agreement_single_basis"] for stats in metrics["baselines"].values())
    assert tier["n"] >= 100
    assert tier["agreement"] >= 0.90
    assert tier["agreement"] > best_baseline + 0.3
    assert tier["p_value_vs_chance"] < 0.01


def test_engine_beats_all_three_baselines_on_agreement(full_evaluation):
    metrics = full_evaluation["metrics"]
    engine = metrics["localization_agreement"]
    for stats in metrics["baselines"].values():
        assert engine > stats["agreement_single_basis"] + 0.2
    # correct-and-confident comparison as well
    assert metrics["correct_and_confident_engine"] > max(metrics["correct_and_confident_baselines"].values())
