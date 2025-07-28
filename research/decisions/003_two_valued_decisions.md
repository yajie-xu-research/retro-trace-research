# Decision 003 — Two-valued attribution decisions

**Date:** 2025-07-21
**Status:** Accepted

## Question

What should the engine output when the evidence does not single out one
stage?

## Options

1. Always output the single best stage (highest recall, silently wrong on
   ambiguous cases).
2. Output LOCALIZED only when the evidence supports a single stage,
   otherwise ABSTAIN (explicit uncertainty).
3. Output a ranked list of candidate stages with scores (rich but hard to
   evaluate and to act on).

## Decision

Option 2. The engine returns `decision = LOCALIZED | ABSTAIN`. A LOCALIZED
decision carries exactly one stage and an uncertainty tier (LOW/HIGH). An
ABSTAIN carries exactly one reason.

## Rationale

The downstream consumer is a quality review queue, where a wrong single
answer costs reviewer time and erodes trust. Explicit abstention is
actionable: it routes the case to a different review path instead of
pretending confidence. A two-valued decision also makes evaluation
unambiguous.
