# ST-0803 — local TEST_ONLY comparison validator

Classification:
`PURE_DETERMINISTIC_LOCAL_TEST_ONLY_COMPARISON_VALIDATOR`.

This slice validates one already assembled synthetic comparison matrix. It is
local, non-persistent, non-authoritative, and ineligible for publication or
Production. It does not resolve product identity, merge or split products,
convert units, impute values, rank products, calculate recommendations or
coverage, or call any external system.

## Closed validation boundary

- Inputs contain 2 through 20 unique products, 1 through 30 unique axes, and
  exactly one cell for every product/axis pair.
- Product identity and variant bindings are supplied pre-resolved for the
  synthetic fixture. Unresolved, conflicting, or mismatched bindings block.
- A known cell has an explicit finite scalar and exact unit, evidence,
  identity, and variant bindings. An unknown cell has no invented value or
  unit, and unknown values must remain visible.
- Imputation, incompatible units, finance or affiliate fields, mutable
  collections, subclasses, booleans used as scalar values, non-finite numbers,
  and malformed runtime types fail closed with stable redacted findings.
- Findings expose closed codes only. They never echo product, axis, evidence,
  identity, variant, value, or field-name input.

OD-006 remains `EXTERNAL_EVIDENCE_REQUIRED` and blocking. This validator does
not turn a synthetic pre-resolved binding into a category identity rule or an
ST-0504 identity decision. ST-0605 claim/evidence coverage remains
`UNEVALUABLE`; its vocabulary mapping remains `UNAVAILABLE` and no coverage
calculation occurs.

## Completion boundary

A finding-free local fixture returns `PASS`, but
`publication_authorized=false` and `production_eligible=false` remain exact.
Identity resolution, coverage calculation, formal TST-007/TST-020 execution,
and live validation remain `NOT_EXECUTED`. Local unit, lint, and type checks are
implementation evidence only; they do not establish formal CI, runtime,
staging, release, live-provider, or Production readiness.
