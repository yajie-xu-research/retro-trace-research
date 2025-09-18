# Decision 005 — Uncertainty calibration as a design-frozen success criterion

**Date:** 2025-08-18
**Status:** Accepted

## Question

How do we know the uncertainty tiers mean what they claim?

## Options

1. Trust the design; report only overall agreement.
2. Freeze a testable calibration criterion in the analysis plan:
   localization accuracy on the HIGH-uncertainty tier must not be
   significantly above chance, and on the LOW-uncertainty tier must be
   significantly above the comparison baselines.
3. Calibrate tiers on the evaluation data itself (leaks, overfits).

## Decision

Option 2. Tier assignment is fixed by the configuration (deviation margins
against class baselines). The calibration criterion is asserted in
`tests/test_calibration.py` on the frozen data package: HIGH tier accuracy
vs chance (exact binomial, 5% level) and LOW tier accuracy vs the best
baseline.

## Rationale

A confidence label that does not predict accuracy is a liability: reviewers
either distrust all labels or over-trust them. A design-frozen, testable
criterion turns the tier semantics into a falsifiable claim and prevents
silent calibration drift as the pipeline evolves.
