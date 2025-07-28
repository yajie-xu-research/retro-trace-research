# Decision 002 — Ground truth: rule-labeled labels only

**Date:** 2025-07-14
**Status:** Accepted

## Question

What is the truth against which the attribution engine is evaluated?

## Options

1. The rule-based flags themselves (circular: the engine applies the same
   rules it is tested against).
2. The quality events produced by the frozen label rules
   (`quality_events.csv`), independent of the engine's features.
3. No truth; qualitative review only.

## Decision

Option 2. Truth is the set of rule-labeled quality events
(`quality_events.csv`): each row carries `event_type`, the review-basis
stages, the rule version, and the label assignment timestamp. The
retrospective rule flags are features of the pipeline, never truth.

## Rationale

Rules capture what was knowable at event time; the quality-event labels
capture the target population the rules define, including borderline cases
with diffuse timestamps that no hard rule could have flagged. Testing the
engine against its own rules would inflate every metric. The honest
false-negative population (cases the flagging rules intentionally miss) is
intentionally retained in the data.
