# frozen metrics (locked on 2026-06-30)

Metrics below were computed with `a1 evaluate` on the run
`outputs/runs/a1_attribution` over the shipped data package
(`synthetic_data/`, seed 20250710) with config hashes as recorded in that
run's manifest. They are frozen: subsequent changes must either reproduce
them exactly or land in a new config version with an updated metric record.

## Run manifest (constituents)

| Field | Value |
| --- | --- |
| attribution run_id | `run-a1-20250710-08218bfe7004` |
| evaluation run_id | `run-eval-08218bfe7004` |
| stamp | `2026-06-30T00:00:00Z` (generated 2026-06-30) |
| seed | `20250710` |
| rule version | `1.1.0\|RR-2025-07-28A` |
| data hash | `08218bfe7004c1593de8561c621f46ef70f9e828bff66f7b02396c0669d31032` |
| config hash | `2f8bcdabf6233365c7a81e81e4a58135350323cf2c88befcee70a7a06d9fc397` |
| attribution result hash | `8aacadc5cd2e46a356614b2c62eff7fca42a266bb77fd05a164633f361e2696a` |
| evaluation result hash | `78310fa740aeda0f614fbcc68b7e0b53c659de25efac9230f3d0d7e306f31a68` |

Code version: the release recorded in `CHANGELOG.md` 1.2.0; the run
manifests record the commit at which each run was produced.

Reproduction:

```bash
venv/bin/python3 -m retro_trace a1 attribute --input synthetic_data/ --out outputs/runs/a1_attribution
venv/bin/python3 -m retro_trace a1 evaluate --run outputs/runs/a1_attribution/ --out outputs/runs/a1_evaluation
```

## Frozen metrics

- data package: 3,500 cases (seed 20250710), 23,892 event rows
- rule-labeled quality events: 700 (420 delays, 280 rework; 112 dual-stage)

### Detection

- flagged rows: 633 (630 match a rule-labeled quality event + 3 without a
  matching label)
- flag precision: 0.9953 (630/633)
- flag recall: 0.9000 (630/700) — the observed value of this run. The 70
  unflagged quality events are single-basis DELAY events whose stage
  durations fell below the rule-based flagging threshold (diffuse
  timestamps); they were never flagged, so no decision was produced for
  them (see the error ledger).

### Localization (371 localized rows with a matching label)

- localization agreement: 0.8895 (330/371; of the 374 localized rows, 3
  have no matching label and are counted among the flag false positives)

### Uncertainty calibration (design-frozen criterion)

| tier | n | agreement | chance | exact binomial p vs chance |
|---|---|---|---|---|
| LOW | 325 | 0.9938 | 0.1429 | 0.0000 |
| HIGH | 46 | 0.1522 | 0.1429 | 0.8328 |

Method note: chance is 1/7 (one of seven canonical stages) and the table
covers single-stage localizations only — dual-stage events are abstained,
never localized. The LOW-tier p-value is displayed as 0.0000; the exact
binomial value is 4.18e-269.

HIGH-tier rows are low-confidence localizations, not abstentions: all 46
rows were localized, at chance-level agreement (0.1522, p = 0.8328).
LOW-tier localization is significantly above chance and above every
baseline.

### Abstention

- rejection rate: 0.4092 (259/633)
- by reason: AMBIGUOUS_STAGES 86, NOT_COMPARABLE_SITE 168,
  INSUFFICIENT_BASELINE 5
- ambiguity recall: 86 of 86 dual-stage events on comparable sites. Of the
  112 dual-stage quality events: 86 sit on comparable sites and abstained
  with AMBIGUOUS_STAGES, 25 sit on the not-comparable site and abstained
  with NOT_COMPARABLE_SITE, and 1 sits in the deliberately small sample
  class and abstained with INSUFFICIENT_BASELINE — all 112 abstained, none
  localized.
- ambiguous false-abstain: 0
- not-comparable cases all come from SITE_C (all three workflow versions):
  its local event stream lacks the sequencing step declared in the frozen
  seven-stage dictionary, so those cases are rejected rather than
  localized on a chain the dictionary cannot map.

### Error ledger

- 633 flagged = 371 localized (with a matching label) + 259 abstained +
  3 flagged without a matching label
- false positives: 41 wrong stage, 3 flagged without a matching label,
  0 localized on dual-stage basis
- false negatives: 168 not-comparable, 5 insufficient baseline,
  0 ambiguous false-abstain, plus 70 never-flagged DELAY events
  (flag recall 0.9000 = 630/700)

### Baselines (same flagged universe, no abstention)

Baselines localize every flagged row. The 521 single-basis events
(633 - 112 dual-stage) are the strict comparison: a baseline localization
counts only when it names the single true stage. Correct-and-confident
covers all 633 flagged rows and counts a baseline localization as correct
when it matches one of the event's true stages (on dual-stage events any
true stage earns credit; the engine's abstentions count as incorrect).

| method | single-basis agreement (n=521) | correct-and-confident (n=633) |
|---|---|---|
| naive longest-wait heuristic | 0.2783 (145/521) | 0.3665 (232/633) |
| fixed thresholds | 0.3071 (160/521) | 0.4297 (272/633) |
| per-stage SPC | 0.3109 (162/521) | 0.4313 (273/633) |
| engine | - | 0.5213 (330/633; 323 LOW-tier + 7 HIGH-tier) |

Baseline correct-and-confident exceeds single-basis agreement because the
112 dual-stage events award credit for matching any true stage; the
single-basis rows are the harder, single-target comparison.

All conclusions above are statistical associations, not causal claims
(association, not causation).
