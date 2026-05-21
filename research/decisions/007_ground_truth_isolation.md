# Decision 007 — Ground-truth isolation by physical separation

**Date:** 2025-09-30
**Status:** Accepted

## Question

How do we guarantee the attribution run cannot peek at the quality-event
labels?

## Options

1. Convention: "do not load quality_events.csv in attribution code" (fragile,
   unenforceable).
2. Physical separation: the quality-event labels are copied into
   `data/_ground_truth/` inside the run directory; no attribution or feature
   code path may read that directory. Only the copy-on-write writer and the
   evaluation step may touch it.
3. Encrypted labels with runtime key management (overkill for this stage).

## Decision

Option 2, enforced twice: a source-level whitelist test (which modules may
reference the directory) and a behavioral test that deletes the directory
and re-runs attribution, asserting every output is byte-identical.

## Rationale

Leakage is invisible until it inflates a metric. Physical separation plus a
byte-identity test makes leakage fail loudly and specifically, and the
behavioral test also covers indirect reads through shared helpers.
