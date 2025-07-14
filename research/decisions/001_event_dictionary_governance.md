# Decision 001 — Event dictionary governance

**Date:** 2025-07-10
**Status:** Accepted

## Question

How should the raw event codes of three sites and three workflow versions be
unified so every research stream uses identical stage semantics?

## Options

1. Each analysis maintains its own mapping (fast, drifts over time).
2. One shared, versioned dictionary with pinned integrity (single source of
   truth, requires governance).
3. Heuristic fuzzy matching of raw codes (no explicit dictionary, high error
   rate).

## Decision

Option 2. A single stage-map table maps every (site, workflow version, raw
event code) triple to one of seven canonical stages. The file is frozen and
its SHA-256 is recorded in `configs/qa_labels.yaml` under
`pinned_dictionary`. The loader refuses to proceed on any modification.

## Rationale

Raw codes encode site and workflow generation; without a dictionary, the same
concept has different codes across sites and versions, and the same code can
mean different stages in different versions. A pinned dictionary makes stage
semantics auditable and reproducible, and the integrity check makes silent
tampering impossible.
