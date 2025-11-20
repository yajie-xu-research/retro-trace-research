# Decision 008 — Wording: statistical association, not causation

**Date:** 2025-10-21
**Status:** Accepted

## Question

How should localized stages be described in reports and summaries?

## Options

1. "The delay was caused by stage X" (overclaiming; the evidence is
   observational).
2. "The delay is statistically associated with stage X; a candidate focus
   area for quality review" (accurate, actionable).
3. Avoid stage-level statements entirely (loses the value of localization).

## Decision

Option 2. Every human-readable output (evaluation summary, run receipts,
docs) states the conclusion as a statistical association, not a causal
claim, and the summary text includes the exact phrase
"association, not causation". This wording is test-enforced
(`tests/test_cli.py::test_conclusion_states_association_not_causation`).

## Rationale

The pipeline observes event logs; it cannot exclude confounders such as
instrument sharing, staff scheduling, or sample mix. Overclaiming causation
would misdirect quality interventions; the correct framing keeps the
localization useful without exceeding the evidence.
