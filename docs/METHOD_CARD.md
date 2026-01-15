# METHOD_CARD

## Purpose

Retrospective attribution of laboratory workflow quality events (delays,
rework) to one of seven canonical workflow stages, with calibrated
uncertainty handling and abstention.

## Inputs

- `events.csv` — raw event log with per-site, per-workflow-version event
  codes.
- `cases.csv` — case-level metadata (site, workflow version at receipt,
  sample class, receipt time).
- `quality_events.csv` — rule-labeled quality events (labels assigned by
  the frozen label rules; ground truth; staged under `data/_ground_truth/`
  in runs).
- `sample_classes.csv` — class definitions and priority.
- `load_staffing.csv` — queue snapshots (load quartiles).
- `configs/qa_labels.yaml`, `configs/label_rules.yaml` — frozen config.
- Pinned event dictionary (`stage_map_v1_0.csv`).

## Method (six steps)

1. **Dictionary unification.** Map every raw event to a canonical stage via
   the pinned dictionary; register unmapped codes and not-comparable
   site/version combinations in the comparability ledger.
2. **Retrospective flagging.** Apply the pre-defined label rules from
   `label_rules.yaml` (delay: total case duration above the class p90;
   rework: a repeated stage event) to flag candidate cases.
3. **Per-stage deviation.** For each flagged case, compute per-stage
   durations (time from the previous milestone to this milestone, anchored
   at receipt) and standardized deviations against class baselines
   (median, MAD-scaled).
4. **Subgroup association.** Cross-tabulate flagged rates by sample class,
   quarter, and load quartile; report lifts and top localized stage.
5. **Ambiguity detection.** When more than one stage deviates
   simultaneously beyond the ambiguity threshold, abstain with
   `AMBIGUOUS_STAGES`. Abstain with `INSUFFICIENT_BASELINE` below the class
   baseline floor, and with `NOT_COMPARABLE_SITE` for unvalidated
   combinations.
6. **Comparability check.** The ledger from step 1 gates cross-site
   comparison; attribution proceeds only over comparable cases.

Uncertainty tiers: LOW (a single stage deviates with a wide margin) vs
HIGH (a narrow band of stages deviates together; localization is at chance
level by design). HIGH-tier rows are still localized: they are
low-confidence localizations, not abstentions.

## Baselines

- `naive_stage` — manual heuristic: blame the milestone delayed by the
  longest wait in the raw log; no dictionary, no abstention.
- `threshold_stage` — fixed duration thresholds per stage.
- `spc_stage` — per-stage statistical process control: flag stages beyond
  mean +- 3 sigma.

All baselines localize every flagged case (no abstention), which is
reflected in their correct-and-confident comparison.

## Evaluation

`a1 evaluate` compares engine outputs against the rule-labeled quality
events:
flag precision/recall, localization agreement by tier, tier calibration
(exact binomial vs chance and vs baselines), rejection rate by reason,
ambiguity recall, and baseline comparisons.

## Interpretation

Localized stages are statistical associations, not causal claims
(association, not causation). They are candidate focus areas for quality
review.
