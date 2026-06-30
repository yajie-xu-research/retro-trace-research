# CHANGELOG

## 1.2.0 (2026-06-30)

- Attribution engine: six-step pipeline (dictionary unification,
  retrospective rule flags, per-stage deviation against class baselines,
  subgroup association, ambiguity abstention, comparability gate).
- Three comparison baselines: naive longest-wait heuristic, fixed
  thresholds, per-stage statistical process control.
- Uncertainty tiers with design-frozen calibration criterion; tests assert
  HIGH-tier accuracy is not above chance and LOW-tier accuracy beats all
  baselines.
- Ground-truth isolation via `data/_ground_truth/` with byte-identity test.
- CLI: generate-synthetic / validate / a1 attribute / a1 evaluate /
  manifest inspect.
- Frozen metrics on the seed-20250710 data package in `docs/frozen_metrics.md`.
- External validation protocol draft; status not obtained.

## 1.0.0 (2026-03-19)

- Two-pass quality-event labeling: frozen delay/rework rules plus a
  borderline review-path population.
- Load-quartile snapshots and subgroup association tables.
- Validation command with cross-table checks.
- Cross-site validation protocol draft.

## 0.5.0 (2026-01-15)

- Cross-site comparability mapping and baseline stratification by sample
  class.
- Class-stratified stage-duration baselines with three comparison methods.
- Retrospective replay validation run.

## 0.2.0 (2025-09-18)

- Deterministic research data generator (three sites, three workflow
  versions, seven canonical stages).
- Pinned event dictionary with SHA-256 integrity enforcement.
- Delay/rework label rules, stage-duration deviation engine, and stage
  localization with uncertainty rules.
- Initial run layout and manifest contract.
