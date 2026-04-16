# USAGE_GUIDE

## Setup

```bash
cd retro-trace-research
uv venv venv --python 3.12
uv pip install --python venv/bin/python3 -e ".[dev]"
```

## The five commands

All commands share the run-directory contract: every run directory contains
`manifest.json` (inputs, hashes, status), `run.log`, per-command results,
and `excluded_rows.csv` (rows dropped or skipped, with reasons). Run status
is `INTERNAL_RESEARCH`; external validation runs would use the other status
value.

### 1. generate-synthetic

```bash
venv/bin/python3 -m retro_trace generate-synthetic --output synthetic_data/ --seed 20250710
```

Deterministic research data package: events, cases, quality events, sample
classes, load snapshots, and the shipped dictionary copy.

### 2. validate

```bash
venv/bin/python3 -m retro_trace validate --input synthetic_data/
```

Schema and cross-table checks (dictionary pin, event coverage, label rule
conformance, date windows, key referential integrity).

### 3. a1 attribute

```bash
venv/bin/python3 -m retro_trace a1 attribute --input synthetic_data/ --out outputs/runs/a1_attribution
```

Runs the six-step attribution engine. Writes `attribution_rows.csv`
(decision, reason, localized stage, uncertainty tier, evidence),
`comparability_ledger.csv`, `subgroup_association.csv`,
`baselines_comparison.csv`, and stages the quality-event labels under
`data/_ground_truth/true_qa_labels.csv` (never read by this command).

### 4. a1 evaluate

```bash
venv/bin/python3 -m retro_trace a1 evaluate --run outputs/runs/a1_attribution/ --out outputs/runs/a1_evaluation
```

Reads the attribution run (including its isolated ground truth) and writes
`results/summary.md`, `results/engine_outcomes.csv`,
`results/calibration.csv`, `results/baseline_agreement.csv`, and
`run_receipt.json`.

### 5. manifest inspect

```bash
venv/bin/python3 -m retro_trace manifest inspect --run outputs/runs/a1_attribution
```

Prints the run manifest (hashes, config, status, exclusions).

## Tests

```bash
venv/bin/python3 -m pytest
```

## Reproduce the frozen metrics

Regenerate and re-run exactly as in `docs/frozen_metrics.md`; the data hash
and attribution result hash are deterministic given the same seed and
configuration.

## Interpretation rules

- LOCALIZED + tier LOW: the association is strong; a candidate for review.
- LOCALIZED + tier HIGH: localization is at chance level by design; treat
  the stage as one of several candidates, not a finding.
- ABSTAIN AMBIGUOUS_STAGES: several stages deviate together; route to
  multi-stage review.
- ABSTAIN INSUFFICIENT_BASELINE: the sample class has too few comparable
  cases for deviation analysis.
- ABSTAIN NOT_COMPARABLE_SITE: the site/version combination has no
  validated dictionary mapping.

All stage attributions are statistical associations, not causal claims
(association, not causation).
