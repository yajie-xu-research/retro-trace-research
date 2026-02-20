# External validation protocol (draft)

## Scope

Validate the attribution method and the frozen metrics from this repository
on data external to the research package: records from sites not present in
the package, or a withheld time window, adjudicated by an independent review
group.

## Protocol

1. **Data eligibility.** A fixed observation window, at least one site not
   used in the research package, and event logs that can be mapped to the
   canonical stage dictionary without new event codes. New codes require a
   dictionary extension, a new pin, and a config version bump before any
   run.
2. **Blinding.** Reviewers receive the evaluation dataset without
   ground-truth labels. Engine outputs and rule flags are withheld until
   the review closes.
3. **Isolation.** The review labels are written to
   `data/_ground_truth/true_qa_labels.csv` in the validation run. The same
   byte-identity test applies: deleting the directory must not change
   attribution outputs.
4. **Metrics.** Recompute the frozen metric set from `docs/frozen_metrics.md`
   on the validation data; report the same tier calibration checks without
   re-tuning any threshold.
5. **Reporting.** All conclusions use the association wording; no causal
   claims. Deviations from this protocol are recorded in the run manifest
   under `known_issues`.

## Status

Not obtained. See `status.json`.
