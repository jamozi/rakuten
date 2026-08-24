# ST-1906 — disabled aggregate causal-attribution seam

Status: `LOCAL_IMPLEMENTATION_COMPLETE` within the maximum-safe Post-MVP
boundary. Canonical status remains `DEFERRED_POST_MVP`; formal TST-032 remains
`NOT_EXECUTED`.

## Preflight and authority

- Story/objective: `ST-1906`, improve attribution only after sufficient signal
  and Privacy review.
- Read inputs: repository and Canonical implementation rules, integration
  precedence/decisions/open decisions, ST-1906 and dependency ST-1303, the full
  analytics attribution/event/KPI boundary, TST-032 and acceptance design, and
  the full security/privacy data/control/threat boundary.
- Open decisions: OD-012 (consent/privacy) and OD-014 (retention) remain human
  decisions. This Story does not approve a live privacy purpose, tracking,
  consent mode, retention, deletion, provider, experiment, or release.
- Owned files: additive `changes/st-1906/**`, one provider-neutral domain
  module, one inward port, one application service, one caller-bytes recorded
  adapter, one owner generator, one work log, and `tests/st1906/**`.
- Out of scope: personal rows/identifiers, arbitrary observational linkage,
  tracking activation, provider/network calls, credentials, persistence,
  finance allocation, editorial/recommendation mutation, publication, formal
  TST-032, staging, release, and Production.

## Maximum-safe implementation

`DEFAULT_CAUSAL_ATTRIBUTION_SCOPE` is exactly `DISABLED`. The only executable
state is `RECORDED_SYNTHETIC_AGGREGATE_EVALUATION_ONLY`, accepted solely in
`ENV-DEV` or `ENV-CI`. Disabled evaluation fails before the inward port call.
There is no live, canary, activation, provider, persistence, or release state.

The adapter consumes one exact caller-supplied canonical JSON recording once.
It contains five ST-1303-bound article cells with only aggregate two-arm counts,
source/assignment hashes, verification state, cohort maturity, program and
period. Unknown fields, duplicate keys, floats, non-canonical encoding,
personal/tracking fields, finance fields, duplicate cells, source drift and
contract drift fail closed without retaining rejected material.

An available local result requires all of the following: a recorded-synthetic
privacy-scope review hash; no personal data, persistent identifier, raw IP,
full user agent, free text or tracking activation; exact five-slot packet
binding; the fixed program and one 14-day period; verified measurements;
mature cohorts; verified randomized assignment; equal arm exposures within each
article cell; at least 500 exposures and 20 outcomes in each arm of every cell;
and a 95% aggregate risk-difference interval that excludes zero. Missing,
unreviewed, unverified, immature, mismatched, zero-denominator or low-signal
inputs return `UNAVAILABLE` with no numeric estimate. They never become an
invented zero.

The deterministic estimate is `ANALYSIS_CANDIDATE_ONLY`. It is not a Provider
Fact and does not allocate provider totals. The value types and projection fix
all editorial, HTML, CTA, product-selection, recommendation-order, publication
snapshot, tracking, publication, release and Production authority to false.
Affiliate commission, confirmed/unattributed reward, cost, EPC, RPM and profit
are absent from the estimator and structurally forbidden as automatic
recommendation or editorial inputs.

## Owner generation

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=python:. \
  /home/minami/rakuten/.venv/bin/python \
  scripts/build_st1906_advanced_causal_attribution.py

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=python:. \
  /home/minami/rakuten/.venv/bin/python \
  scripts/build_st1906_advanced_causal_attribution.py --check
```

Only that owner writes
`changes/st-1906/generated/causal-attribution-report.v1.json` and
`changes/st-1906/manifest.yaml`. Local evidence is not formal TST-032, live
privacy/statistical evidence, staging, release, Production, or Story-acceptance
evidence.
