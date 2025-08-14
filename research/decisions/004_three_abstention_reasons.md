# Decision 004 — Three abstention reasons

**Date:** 2025-08-02
**Status:** Accepted

## Question

When the engine abstains, what must it tell the reviewer?

## Options

1. One generic "uncertain" reason (simple, unactionable).
2. Three specific reasons: `AMBIGUOUS_STAGES` (several stages deviate
   simultaneously), `INSUFFICIENT_BASELINE` (fewer than the floor number of
   comparable cases in the sample class), `NOT_COMPARABLE_SITE` (the
   site/version combination lacks a validated dictionary mapping).
3. A free-text explanation per case (unstructured, unreproducible).

## Decision

Option 2. Each ABSTAIN row carries exactly one of the three reasons from a
frozen enumeration. Coverage-limited reasons (baseline, comparability) take
precedence over ambiguity when both apply.

## Rationale

Different abstention causes need different remedies: ambiguity is a property
of the case, baseline shortage is a property of the reference population,
and comparability is a property of the dictionary coverage. Reporting them
separately lets the quality team size each fix and keeps the ambiguity
metric meaningful (ambiguity recall excludes coverage-limited cases).
