# Attribution evaluation summary

All numbers below are statistical associations computed on this data
package. They are not causal claims: a localized stage is a candidate
focus area for quality review, not proof that the stage caused the
event (association, not causation).

- flagged rows evaluated: 633
- rule-labeled quality events: 700
- flag precision: 0.9953
- flag recall: 0.9000
- localized rows: 371
- localization agreement (LOCALIZED): 0.8895
- tier LOW: agreement 0.9938 (n=325, chance 0.1429, exact binomial p=0.0000)
- tier HIGH: agreement 0.1522 (n=46, chance 0.1429, exact binomial p=0.8328)
- false positives: multi-basis localized 0, wrong stage 41, flag without a matching label 3
- false negatives: ambiguous false-abstain 0, insufficient baseline 5, not comparable 168
- ambiguity recall: 86 of 86 multi-basis labels
- rejection rate: 0.4092 by reason {'NOT_COMPARABLE_SITE': 168, 'AMBIGUOUS_STAGES': 86, 'INSUFFICIENT_BASELINE': 5}

## Baselines (same universe, no abstention)
- naive_stage: single-basis agreement 0.2783 (n=521)
- threshold_stage: single-basis agreement 0.3071 (n=521)
- spc_stage: single-basis agreement 0.3109 (n=521)

## Correct-and-confident (correct localizations over all flagged rows)
- engine: 0.5213
- naive_stage: 0.3665
- threshold_stage: 0.4297
- spc_stage: 0.4313

stage localization is reported as a statistical association, not causation; localized stages are candidate focus areas for quality review and are not evidence that a stage caused the event
