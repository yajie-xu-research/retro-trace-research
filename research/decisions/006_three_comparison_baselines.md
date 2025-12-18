# Decision 006 — Three comparison baselines

**Date:** 2025-09-05
**Status:** Accepted

## Question

Against what should the attribution engine be compared?

## Options

1. No baselines: absolute metrics only (uninformative about the value of
   the added machinery).
2. One baseline (cheap, but hides which parts of the engine matter).
3. Three baselines of increasing sophistication: a naive manual heuristic,
   a single fixed-threshold rule per stage, and per-stage statistical
   process control (mean +- 3 sigma).

## Decision

Option 3. All three baselines run over the same flagged universe, output a
stage for every case (no abstention), and are compared on single-basis
agreement and on correct-and-confident (correct localizations over all
flagged rows, which punishes the baselines' lack of abstention).

## Rationale

The naive heuristic represents what a reviewer does scanning the raw log:
blame the stage delayed by the longest wait. The fixed-threshold rule is the
common operational shortcut. SPC is the established statistical approach
applied per stage. Covering all three shows precisely where the engine
adds value: uncertainty handling, dictionary alignment, and subgroup
association — not just deviation detection.
